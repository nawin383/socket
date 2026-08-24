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
from .telegram_bot import TelegramBot
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

    # --- Telegram command bot (VPS only) — remote control when away from laptop ---
    config_path = BASE_DIR / "config" / "config.yaml"
    tg_bot = TelegramBot(
        bot_token=settings.telegram_bot_token,
        allowed_chat_id=settings.telegram_chat_id,
        state=state,
        risk=risk,
        strategy=strategy,
        orders=orders,
        kite=kite,
        store=store,
        config=config,
        config_path=config_path,
        kill_switch_path=kill_switch_path,
        notifier=notifier,
        status_ref=status,
    )
    tg_bot.start()

    spot_token = config["underlying"]["spot_instrument_token"]
    latest = {"spot": None, "ce_ltp": None, "pe_ltp": None, "pe_pending_ltp": None}

    def on_ticks(ticks):
        for tick in ticks:
            token = tick["instrument_token"]
            if token == spot_token:
                latest["spot"] = tick["last_price"]
            ce_leg = state.get_leg("CE")
            if ce_leg and token == ce_leg["instrument_token"]:
                latest["ce_ltp"] = tick["last_price"]
            pe_leg = state.get_leg("PE")
            if pe_leg and token == pe_leg["instrument_token"]:
                latest["pe_ltp"] = tick["last_price"]
            pe_pending = state.get_pending_order("PE")
            if pe_pending and token == pe_pending["instrument_token"]:
                latest["pe_pending_ltp"] = tick["last_price"]

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
                    # Keep Telegram commands on fresh kite/connect
                    try:
                        tg_bot.kite = kite
                        tg_bot.orders = orders
                        tg_bot.strategy = strategy
                        tg_bot.store = store
                    except Exception:
                        pass
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

            # MAXLOSS now on total (realized + unrealized) — answers your question:
            # "how will you determine based on todays loss or entire loss" — we now use entire.
            # Compute overall via strategy helper (needs latest ltps if available)
            try:
                overall_pnl, _, _ = strategy._get_overall_pnl_today(
                    pe_ltp=latest.get("pe_ltp"), ce_ltp=latest.get("ce_ltp")
                )
            except Exception:
                overall_pnl = None
            # Prefer total check; fallback to realized-only if overall not available
            breached = False
            if overall_pnl is not None:
                breached = risk.total_loss_breached(overall_pnl=overall_pnl)
                # Keep status in sync for Telegram /status
                status["overall_pnl"] = overall_pnl
            else:
                breached = risk.daily_loss_breached()
            if breached:
                if state.get_leg("PE") or state.get_leg("CE"):
                    reason = "daily loss limit breached (total)" if overall_pnl is not None else "daily loss limit breached"
                    strategy.square_off_all(reason)
                time.sleep(poll_cfg.get("reconcile_interval_sec", 15))
                continue

            if risk.trading_allowed(now):
                strategy.ensure_pe_leg()
                strategy.ensure_ce_leg()
                ce_leg = state.get_leg("CE")
                pe_leg = state.get_leg("PE")
                pe_pending = state.get_pending_order("PE")
                tokens = [spot_token]
                if ce_leg:
                    tokens.append(ce_leg["instrument_token"])
                if pe_leg:
                    tokens.append(pe_leg["instrument_token"])
                if pe_pending:
                    tokens.append(pe_pending["instrument_token"])
                feed.set_tokens(tokens)

                if ce_leg and latest["spot"] and latest["ce_ltp"]:
                    strategy.check_ce_roll(latest["ce_ltp"], latest["spot"])
                if pe_leg and latest["pe_ltp"]:
                    strategy.check_pe_stop_loss(latest["pe_ltp"])
                    # Smart PE profit booking — you asked for premium<entry or overall profit
                    try:
                        strategy.check_pe_take_profit(latest["pe_ltp"], ce_ltp=latest.get("ce_ltp"))
                    except Exception as e:
                        logger.error("PE take-profit check failed: %s", e)
                if pe_pending and latest["pe_pending_ltp"]:
                    strategy.check_pending_pe_reentry(latest["pe_pending_ltp"], now)

            time.sleep(poll_cfg.get("reconcile_interval_sec", 15))

    except KeyboardInterrupt:
        logger.info("Shutting down")
    except Exception as e:
        logger.exception("Fatal error in main loop")
        notifier.send(f"Bot crashed: {e}")
        raise
    finally:
        try:
            tg_bot.stop()
        except Exception:
            pass
        feed.stop()


if __name__ == "__main__":
    main()
