"""
Entrypoint: authenticate, wire everything up, run the monitoring/trading loop.

Run with:  python -m src.main   (from the auto_trader/ directory)
Meant to run under Docker/systemd with automatic restart — see deploy/.
"""

import logging
import time
from datetime import datetime

from kiteconnect import KiteConnect

from . import auth
from .health import heartbeat, start_health_server
from .instruments import InstrumentStore
from .notifier import Notifier
from .order_manager import OrderManager
from .risk import RiskGuard
from .settings import BASE_DIR, load_settings
from .state import StateStore
from .strategy import NiftyOptionSellerStrategy
from .ticker_feed import TickerFeed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("auto_trader")


def build_kite(settings) -> KiteConnect:
    token = auth.get_access_token(
        settings.api_key, settings.api_secret, settings.kite_user_id,
        settings.kite_password, settings.kite_totp_secret,
        BASE_DIR / "data" / "access_token.json",
    )
    kite = KiteConnect(api_key=settings.api_key)
    kite.set_access_token(token)
    return kite


def main():
    settings = load_settings()
    config = settings.config
    mode = config.get("mode", "paper")

    notifier = Notifier(settings.telegram_bot_token, settings.telegram_chat_id,
                         config.get("notifications", {}).get("telegram_enabled", True))

    status = {"ok": False, "last_heartbeat": None, "mode": mode}
    start_health_server(config.get("health", {}).get("http_port", 8080), status)

    try:
        kite = build_kite(settings)
    except Exception as e:
        notifier.send(f"STARTUP FAILED: could not authenticate — {e}")
        raise

    store = InstrumentStore(kite, BASE_DIR / "data")
    store.load()

    state = StateStore(BASE_DIR / "data" / "state.db")
    kill_switch_path = BASE_DIR / "data" / config["risk"]["kill_switch_file"]
    risk = RiskGuard(config["risk"], state, kill_switch_path)
    orders = OrderManager(kite, config["orders"], mode=mode)
    strategy = NiftyOptionSellerStrategy(kite, store, orders, state, risk, notifier, config)

    strategy.reconcile_from_broker()

    spot_token = config["underlying"]["spot_instrument_token"]
    latest = {"spot": None, "ce_ltp": None}

    def on_ticks(ticks):
        for tick in ticks:
            token = tick["instrument_token"]
            if token == spot_token:
                latest["spot"] = tick["last_price"]
            leg = state.get_leg("CE")
            if leg and token == leg["instrument_token"]:
                latest["ce_ltp"] = tick["last_price"]

    feed = TickerFeed(settings.api_key, kite.access_token, on_ticks)
    feed.start()
    feed.set_tokens([spot_token])

    notifier.send(f"Bot started in {mode.upper()} mode. Kill switch: touch {kill_switch_path} to pause.")
    poll_cfg = config.get("polling", {})
    last_token_refresh_day = datetime.now().date()

    try:
        while True:
            now = datetime.now()
            heartbeat(status)

            if now.date() != last_token_refresh_day and now.hour >= poll_cfg.get("token_refresh_check_hour", 8):
                try:
                    kite = build_kite(settings)
                    orders.kite = kite
                    strategy.kite = kite
                    store.kite = kite
                    store.load()
                    feed.kws.access_token = kite.access_token
                    last_token_refresh_day = now.date()
                    notifier.send("Daily re-login successful")
                except Exception as e:
                    notifier.send(f"Daily re-login FAILED (will retry next cycle): {e}")

            if not risk.is_trading_day(now):
                time.sleep(60)
                continue

            if risk.is_eod_square_off_time(now):
                strategy.square_off_leg_if_near_expiry("PE", strategy.pe_cfg, now)
                strategy.square_off_leg_if_near_expiry("CE", strategy.ce_cfg, now)

            if risk.daily_loss_breached():
                if state.get_leg("PE") or state.get_leg("CE"):
                    strategy.square_off_all("daily loss limit breached")
                time.sleep(poll_cfg.get("reconcile_interval_sec", 15))
                continue

            if risk.trading_allowed(now):
                strategy.ensure_pe_leg()
                strategy.ensure_ce_leg()
                leg = state.get_leg("CE")
                if leg:
                    feed.set_tokens([spot_token, leg["instrument_token"]])
                    if latest["spot"] and latest["ce_ltp"]:
                        strategy.check_ce_roll(latest["ce_ltp"], latest["spot"])

            time.sleep(poll_cfg.get("reconcile_interval_sec", 15))

    except KeyboardInterrupt:
        logger.info("Shutting down")
    except Exception as e:
        logger.exception("Fatal error in main loop")
        notifier.send(f"Bot crashed: {e}")
        raise
    finally:
        feed.stop()


if __name__ == "__main__":
    main()
