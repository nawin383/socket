"""
Single-shot Telegram poll for GitHub Actions (free, no VPS).

Called as:  python -m src.telegram_poll   (from auto_trader/ dir)
Or via workflow:  actions/checkout → setup-python → pip install → python -m src.telegram_poll

Does one getUpdates batch, handles commands via TelegramBot handlers,
persists offset to data/telegram_offset.txt (committed), and replies via
Telegram sendMessage. Works on ephemeral Actions runners without long-polling.

Uses same handlers as the VPS bot (TelegramBot) so command list is identical.
Requires env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, KITE_* (for /status /positions etc
that need live kite data). If kite auth fails, monitor commands still work partially
but /status positions will show error.

Exit code 0 even if Telegram has no messages — not a failure.
"""

import logging
from pathlib import Path
from datetime import datetime

from kiteconnect import KiteConnect

from . import auth
from .instruments import InstrumentStore
from .notifier import Notifier
from .order_manager import OrderManager
from .risk import RiskGuard
from .settings import BASE_DIR, load_settings
from .state import StateStore
from .strategy import NiftyOptionSellerStrategy
from .telegram_bot import TelegramBot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("auto_trader.telegram_poll")


def main():
    settings = load_settings()
    config = settings.config

    notifier = Notifier(settings.telegram_bot_token, settings.telegram_chat_id,
                        config.get("notifications", {}).get("telegram_enabled", True))

    # If no Telegram config, nothing to poll
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.info("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — skipping telegram poll")
        return

    # Try to get kite for commands that need live data (/status, /positions, etc.)
    # If auth fails, we still handle /pause /resume etc. which don't need kite for the core,
    # but we attempt kite anyway for richer replies.
    kite = None
    store = None
    try:
        token = auth.get_access_token(
            settings.api_key, settings.api_secret, settings.kite_user_id,
            settings.kite_password, settings.kite_totp_secret,
            BASE_DIR / "data" / "access_token.json",
        )
        kite = KiteConnect(api_key=settings.api_key)
        kite.set_access_token(token)
        # Instrument store (for /status lot size, /legs strike lookup)
        # Use temp cache dir on Actions (ephemeral) — no need to persist NFO dump
        import tempfile
        store = InstrumentStore(kite, Path(tempfile.gettempdir()))
        try:
            store.load()
        except Exception as e:
            logger.warning("InstrumentStore load failed (non-critical for telegram): %s", e)
            # Fallback: dummy store with lot_size fallback
            store = type("DummyStore", (), {"lot_size": lambda self, n: 75, "strike_for_tradingsymbol": lambda *a, **k: None})()
    except Exception as e:
        logger.warning("Kite auth failed for telegram poll (commands like /pause still work): %s", e)
        # Create dummy kite that will error on ltp but not crash handler
        class DummyKite:
            def ltp(self, *a, **k):
                raise RuntimeError(f"Kite not authenticated: {e}")
            def positions(self, *a, **k):
                raise RuntimeError(f"Kite not authenticated: {e}")
            def quote(self, *a, **k):
                raise RuntimeError(f"Kite not authenticated: {e}")
        kite = DummyKite()
        import tempfile
        store = InstrumentStore(kite, Path(tempfile.gettempdir())) if 'store' not in locals() or store is None else store
        # Ensure store has lot_size fallback
        if not hasattr(store, "lot_size"):
            store.lot_size = lambda n: 75

    # State / Risk / Orders / Strategy — needed for most handlers
    try:
        state = StateStore(BASE_DIR / "data" / "state.db")
    except Exception as e:
        logger.error("StateStore init failed: %s", e)
        return

    kill_switch_path = BASE_DIR / "data" / config["risk"]["kill_switch_file"]
    risk = RiskGuard(config["risk"], state, kill_switch_path)

    # Orders and Strategy need kite, but if kite is dummy, they still construct (mode handling)
    try:
        orders = OrderManager(kite, config["orders"], mode=config.get("mode", "paper"))
    except Exception as e:
        logger.warning("OrderManager init failed: %s", e)
        orders = None

    try:
        strategy = NiftyOptionSellerStrategy(kite, store, orders, state, risk, notifier, config)
        # Reconcile like main/poll_once do, so /positions is accurate
        try:
            strategy.reconcile_from_broker()
        except Exception as e:
            logger.warning("reconcile_from_broker failed: %s", e)
    except Exception as e:
        logger.error("Strategy init failed: %s", e)
        return

    config_path = BASE_DIR / "config" / "config.yaml"
    status_ref = {"ok": True, "last_heartbeat": datetime.now().isoformat(), "mode": config.get("mode", "paper")}

    bot = TelegramBot(
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
        status_ref=status_ref,
        poll_timeout=0,
    )

    # One batch, zero long-poll wait (Actions runners should finish in 10-20s)
    handled = bot.process_one_batch(timeout=0)
    logger.info("Telegram poll finished: %s messages handled", handled)

    # The workflow's "git add" step will commit telegram_offset.txt if it changed,
    # plus STOP_TRADING / state.db / config.yaml if commands modified them.
    # We just ensure offset file exists even if no messages, so first run persists offset 0?
    # No need to create empty file if no messages — but handled count 0 is fine.


if __name__ == "__main__":
    main()
