"""Unit tests for market-hours, kill-switch, and daily-loss guardrails."""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

from src.risk import RiskGuard

CONFIG = {
    "max_daily_loss": 15000,
    "kill_switch_file": "STOP_TRADING",
    "trading_start": "09:20",
    "trading_end": "15:20",
    "eod_square_off_time": "15:25",
    "holidays": ["2026-01-26"],
}


class TestRiskGuard(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.kill_switch_path = Path(self.tmpdir.name) / "STOP_TRADING"
        self.state = MagicMock()
        self.state.today_state.return_value = {"realized_pnl": 0}
        self.risk = RiskGuard(CONFIG, self.state, self.kill_switch_path)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_weekend_is_not_a_trading_day(self):
        saturday = datetime(2026, 1, 24, 10, 0)  # a Saturday
        self.assertFalse(self.risk.is_trading_day(saturday))

    def test_holiday_is_not_a_trading_day(self):
        holiday = datetime(2026, 1, 26, 10, 0)  # Monday, configured holiday
        self.assertFalse(self.risk.is_trading_day(holiday))

    def test_market_open_within_hours_on_a_weekday(self):
        monday = datetime(2026, 1, 19, 10, 0)
        self.assertTrue(self.risk.is_market_open(monday))

    def test_market_closed_before_open(self):
        monday = datetime(2026, 1, 19, 9, 0)
        self.assertFalse(self.risk.is_market_open(monday))

    def test_kill_switch_blocks_trading(self):
        self.kill_switch_path.touch()
        monday = datetime(2026, 1, 19, 10, 0)
        self.assertFalse(self.risk.trading_allowed(monday))

    def test_daily_loss_breach_blocks_trading(self):
        self.state.today_state.return_value = {"realized_pnl": -16000}
        monday = datetime(2026, 1, 19, 10, 0)
        self.assertTrue(self.risk.daily_loss_breached())
        self.assertFalse(self.risk.trading_allowed(monday))

    def test_trading_allowed_under_normal_conditions(self):
        monday = datetime(2026, 1, 19, 10, 0)
        self.assertTrue(self.risk.trading_allowed(monday))


if __name__ == "__main__":
    unittest.main()
