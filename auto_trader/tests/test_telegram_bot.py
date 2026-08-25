"""
Smoke + unit tests for TelegramBot's message formatting.

Focus: the _table() helper (new — previously "tables" were manually
space-padded strings that never actually rendered aligned in Telegram,
since only code-block/inline-code spans get a monospace font there), and
that the rewritten data-heavy commands (/status /positions /legs /pnl
/config /risk /overall /history /ping) run without crashing against a
realistic state/config and return a string. Not testing Telegram API
wire format — that's requests.post, not our code.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from src.state import StateStore
from src.telegram_bot import TelegramBot

CONFIG = {
    "mode": "paper",
    "underlying": {"name": "NIFTY", "spot_symbol": "NSE:NIFTY 50", "spot_instrument_token": 256265, "strike_step": 50},
    "pe_leg": {
        "enabled": True, "target_premium": 700, "premium_tolerance": 60, "strike_search_range": 15,
        "quantity_lots": 1, "product": "NRML", "expiry_type": "monthly",
        "stop_loss": {"enabled": True, "trigger_pct": 40},
        "take_profit": {"enabled": False, "trigger_pct": 15, "min_profit_points": 20, "require_overall_profit": True},
    },
    "ce_leg": {
        "enabled": True, "target_premium": 120, "premium_tolerance": 15, "strike_search_range": 2,
        "quantity_lots": 1, "product": "NRML", "exit_premium_threshold": 90,
        "max_rolls_per_day": 15, "avoid_zero_dte_entry": True,
    },
    "orders": {"slippage_buffer_pct": 1.0, "order_fill_timeout_sec": 20, "fallback_to_market": True},
    "risk": {
        "max_daily_loss": 15000, "kill_switch_file": "STOP_TRADING",
        "trading_start": "09:20", "trading_end": "15:20", "eod_square_off_time": "15:25", "holidays": [],
    },
    "polling": {"reconcile_interval_sec": 15},
    "health": {"http_port": 8080},
}


def _make_bot(tmpdir):
    state = StateStore(Path(tmpdir) / "state.db")
    kite = MagicMock()
    kite.ltp.return_value = {"NSE:NIFTY 50": {"last_price": 24800.0}}
    kite.positions.return_value = {"net": []}
    strategy = MagicMock()
    strategy._get_overall_pnl_today.return_value = (0.0, 0.0, 0.0)
    strategy._quote_ltp.return_value = 100.0
    orders = MagicMock()
    orders.mode = "paper"
    risk = MagicMock()
    risk.trading_allowed.return_value = True
    risk.kill_switch_active.return_value = False
    risk.is_trading_day.return_value = True
    risk.is_market_open.return_value = True
    risk.is_eod_square_off_time.return_value = False
    risk.daily_loss_breached.return_value = False
    risk.total_loss_breached.return_value = False
    risk.max_daily_loss = 15000
    risk.holidays = []
    store = MagicMock()
    store.lot_size.return_value = 75
    notifier = MagicMock()

    bot = TelegramBot(
        bot_token="",  # never actually sent over the wire in these tests
        allowed_chat_id="123",
        state=state, risk=risk, strategy=strategy, orders=orders, kite=kite, store=store,
        config=CONFIG, config_path=Path(tmpdir) / "config.yaml",
        kill_switch_path=Path(tmpdir) / "STOP_TRADING", notifier=notifier,
        status_ref={"last_heartbeat": "2026-08-25T10:00:00"},
    )
    return bot, state


class TestTableHelper(unittest.TestCase):
    def test_columns_align_and_wrapped_in_code_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot, _ = _make_bot(tmp)
        table = bot._table(["Leg", "Qty"], [["PE", 1], ["CE", 12]])
        self.assertTrue(table.startswith("```\n"))
        self.assertTrue(table.endswith("\n```"))
        lines = table.strip("`\n").split("\n")
        header, sep, *rows = lines
        # Every data line must be the same length as the header — that's what
        # "aligned" means once rendered in a monospace code block.
        for line in [sep] + rows:
            self.assertEqual(len(line), len(header))

    def test_empty_rows_still_renders_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot, _ = _make_bot(tmp)
        table = bot._table(["A", "B"], [])
        self.assertIn("A", table)
        self.assertIn("B", table)


class TestCommandsSmoke(unittest.TestCase):
    """Each command must return a non-empty string and never raise, both
    with no open legs (flat) and with both legs open."""

    def _run_all(self, bot):
        for cmd in ("ping", "status", "positions", "legs", "pnl", "config", "risk", "overall", "history"):
            with self.subTest(cmd=cmd):
                reply = bot.handlers[cmd]([], "123", {})
                self.assertIsInstance(reply, str)
                self.assertTrue(reply)

    def test_commands_when_flat(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot, _state = _make_bot(tmp)
            self._run_all(bot)

    def test_commands_with_open_legs(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot, state = _make_bot(tmp)
            state.set_leg("PE", "NIFTY26SEP25000PE", 111, "NFO", 25000, "PE", 75, 700.0)
            state.set_leg("CE", "NIFTY26O0724200CE", 222, "NFO", 24200, "CE", 75, 120.0)
            self._run_all(bot)

    def test_ping_has_no_dependencies(self):
        """/ping must work even if state/kite/strategy would blow up —
        it's the liveness check for when something else is broken."""
        with tempfile.TemporaryDirectory() as tmp:
            bot, _ = _make_bot(tmp)
        bot.state = None
        bot.kite = None
        bot.strategy = None
        reply = bot._cmd_ping([], "123", {})
        self.assertIn("pong", reply)


if __name__ == "__main__":
    unittest.main()
