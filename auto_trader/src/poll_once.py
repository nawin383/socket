"""
Single-shot poll cycle for the GitHub Actions schedule (see
.github/workflows/trade.yml). Every invocation is a brand-new process on a
throwaway runner with no memory of previous runs — all cross-run state is
whatever the workflow checked out from the repo (data/state.db) or
restored from Actions cache (data/access_token.json).

Unlike main.py (the always-on VPS entrypoint), there is no persistent
WebSocket tick feed here: spot and the CE leg's price are fetched once via
REST (kite.ltp) each run, so a roll can lag up to one polling interval
behind a live tick-driven bot.
"""

import logging
import tempfile
from datetime import datetime
from pathlib import Path

from kiteconnect import KiteConnect

from . import auth
from .instruments import InstrumentStore
from .notifier import Notifier
from .order_manager import OrderManager
from .risk import RiskGuard
from .settings import BASE_DIR, load_settings
from .state import StateStore
from .strategy import NiftyOptionSellerStrategy

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("auto_trader.poll")


def main():
    settings = load_settings()
    config = settings.config
    mode = config.get("mode", "paper")

    notifier = Notifier(settings.telegram_bot_token, settings.telegram_chat_id,
                         config.get("notifications", {}).get("telegram_enabled", True))

    try:
        token = auth.get_access_token(
            settings.api_key, settings.api_secret, settings.kite_user_id,
            settings.kite_password, settings.kite_totp_secret,
            BASE_DIR / "data" / "access_token.json",
        )
    except Exception as e:
        notifier.send(f"Login FAILED this run: {e}")
        raise

    kite = KiteConnect(api_key=settings.api_key)
    kite.set_access_token(token)

    try:
        _run(kite, config, mode, notifier)
    except Exception as e:
        # Login failures are reported above with their own message; anything
        # past that point (order errors, bad API responses, instrument
        # lookups, ...) previously just died silently in the Actions log
        # with no Telegram alert at all. Catch-all so a crash is never quiet.
        logger.exception("Poll run crashed")
        notifier.send(f"Poll run crashed: {e}")
        raise


def _run(kite: KiteConnect, config: dict, mode: str, notifier: Notifier):
    # Not persisted across runs (each run is a fresh container) — only
    # cached for the lifetime of this one process.
    store = InstrumentStore(kite, Path(tempfile.gettempdir()))
    store.load()

    state = StateStore(BASE_DIR / "data" / "state.db")
    kill_switch_path = BASE_DIR / "data" / config["risk"]["kill_switch_file"]
    risk = RiskGuard(config["risk"], state, kill_switch_path)
    orders = OrderManager(kite, config["orders"], mode=mode)
    strategy = NiftyOptionSellerStrategy(kite, store, orders, state, risk, notifier, config)

    strategy.reconcile_from_broker()

    now = datetime.now()

    if not risk.is_trading_day(now):
        logger.info("Not a trading day, exiting")
        return

    if risk.is_eod_square_off_time(now):
        strategy.square_off_leg_if_near_expiry("PE", strategy.pe_cfg, now)
        strategy.square_off_leg_if_near_expiry("CE", strategy.ce_cfg, now)

    if risk.daily_loss_breached():
        if state.get_leg("PE") or state.get_leg("CE"):
            strategy.square_off_all("daily loss limit breached")
        return

    if not risk.trading_allowed(now):
        logger.info("Trading not allowed this run (outside hours, kill switch, or loss limit)")
        return

    strategy.ensure_pe_leg()
    strategy.ensure_ce_leg()

    ce_leg = state.get_leg("CE")
    pe_leg = state.get_leg("PE")
    pe_pending = state.get_pending_order("PE")

    if ce_leg or pe_leg or pe_pending:
        spot_symbol = config["underlying"]["spot_symbol"]
        keys = [spot_symbol]
        if ce_leg:
            keys.append(f"{ce_leg['exchange']}:{ce_leg['tradingsymbol']}")
        if pe_leg:
            keys.append(f"{pe_leg['exchange']}:{pe_leg['tradingsymbol']}")
        if pe_pending:
            keys.append(f"{pe_pending['exchange']}:{pe_pending['tradingsymbol']}")
        quotes = kite.ltp(keys)

        if ce_leg:
            spot = quotes[spot_symbol]["last_price"]
            ce_ltp = quotes[f"{ce_leg['exchange']}:{ce_leg['tradingsymbol']}"]["last_price"]
            strategy.check_ce_roll(ce_ltp, spot)
        if pe_leg:
            pe_ltp = quotes[f"{pe_leg['exchange']}:{pe_leg['tradingsymbol']}"]["last_price"]
            strategy.check_pe_stop_loss(pe_ltp)
        if pe_pending:
            pe_pending_ltp = quotes[f"{pe_pending['exchange']}:{pe_pending['tradingsymbol']}"]["last_price"]
            strategy.check_pending_pe_reentry(pe_pending_ltp, now)


if __name__ == "__main__":
    main()
