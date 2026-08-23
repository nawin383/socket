"""
Unit tests for the CE roll-trigger decision logic — the heart of "exit when
premium drops below threshold and the strike has gone OTM, then re-enter
ATM". Uses a real (temp-file) StateStore and fake order/notifier objects,
no live Kite API calls.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from src.risk import RiskGuard
from src.state import StateStore
from src.strategy import NiftyOptionSellerStrategy

CONFIG = {
    "underlying": {"name": "NIFTY", "spot_symbol": "NSE:NIFTY 50", "spot_instrument_token": 256265, "strike_step": 50},
    "pe_leg": {"enabled": True, "target_premium": 700, "premium_tolerance": 60, "strike_search_range": 15,
               "quantity_lots": 1, "product": "NRML", "close_before_expiry": {"enabled": True, "time": "15:15"}},
    "ce_leg": {"enabled": True, "target_premium": 120, "premium_tolerance": 15, "strike_search_range": 10,
               "quantity_lots": 1, "product": "NRML", "exit_premium_threshold": 90,
               "exit_requires_otm": True, "reentry_moneyness": "ATM",
               "min_seconds_between_rolls": 60, "max_rolls_per_day": 15,
               "close_before_expiry": {"enabled": True, "time": "15:15"}},
    "risk": {"max_daily_loss": 15000, "kill_switch_file": "STOP_TRADING",
             "trading_start": "09:20", "trading_end": "15:20", "eod_square_off_time": "15:25", "holidays": []},
}

LOT_SIZE = 75


class TestCeRollLogic(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.state = StateStore(Path(self.tmpdir.name) / "state.db")
        self.orders = MagicMock()
        self.orders.buy_to_close.return_value = 80.0
        self.notifier = MagicMock()
        risk = RiskGuard(CONFIG["risk"], self.state, Path(self.tmpdir.name) / "STOP_TRADING")

        self.strategy = NiftyOptionSellerStrategy(
            kite=MagicMock(), store=MagicMock(), orders=self.orders,
            state=self.state, risk=risk, notifier=self.notifier, config=CONFIG,
        )
        self.strategy._open_ce_leg = MagicMock()

        # An ATM CE sold at 24800 for 120, current spot still 24800 (leg is at-the-money).
        self.state.set_leg("CE", "NIFTY26FEB24800CE", 111, "NFO", 24800, "CE", LOT_SIZE, 120.0)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_no_roll_when_premium_still_above_threshold(self):
        self.strategy.check_ce_roll(ce_ltp=95, spot=24800)
        self.orders.buy_to_close.assert_not_called()
        self.assertIsNotNone(self.state.get_leg("CE"))

    def test_no_roll_when_premium_low_but_strike_still_not_otm(self):
        # Premium dropped from pure time decay but spot hasn't moved past the strike yet.
        self.strategy.check_ce_roll(ce_ltp=85, spot=24800)
        self.orders.buy_to_close.assert_not_called()

    def test_rolls_when_premium_below_threshold_and_strike_otm(self):
        # Spot dropped to 24700, so the 24800 CE is now OTM, and premium is below 90.
        self.strategy.check_ce_roll(ce_ltp=85, spot=24700)

        self.orders.buy_to_close.assert_called_once_with("NIFTY26FEB24800CE", "NFO", LOT_SIZE, 85, "NRML")
        self.strategy._open_ce_leg.assert_called_once()
        self.notifier.send.assert_called()

        # Realized P&L = (entry 120 - exit 80 fill) * lot size, recorded and leg cleared for re-entry.
        self.assertAlmostEqual(self.state.today_state()["realized_pnl"], (120.0 - 80.0) * LOT_SIZE)
        self.assertEqual(self.state.today_state()["roll_count"], 1)

    def test_no_leg_means_no_op(self):
        self.state.clear_leg("CE")
        self.strategy.check_ce_roll(ce_ltp=50, spot=24000)
        self.orders.buy_to_close.assert_not_called()

    def test_max_rolls_per_day_blocks_further_rolls(self):
        for _ in range(CONFIG["ce_leg"]["max_rolls_per_day"]):
            self.state.log_roll("CE", "EXIT", "X", 80.0, LOT_SIZE)

        self.strategy.check_ce_roll(ce_ltp=85, spot=24700)
        self.orders.buy_to_close.assert_not_called()

    def test_min_seconds_between_rolls_blocks_rapid_second_roll(self):
        self.state.log_roll("CE", "EXIT", "NIFTY26FEB24800CE", 80.0, LOT_SIZE)
        # Immediately try another roll on the same (still-recorded) leg.
        self.strategy.check_ce_roll(ce_ltp=85, spot=24700)
        self.orders.buy_to_close.assert_not_called()


if __name__ == "__main__":
    unittest.main()
