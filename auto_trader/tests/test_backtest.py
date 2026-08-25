"""
Unit tests for the backtest harness's pure decision functions. Every
expected value here is hand-computed so a wrong trigger-price formula or
off-by-one condition shows up as a mismatched number, not just "it ran".
"""

import unittest

from src.backtest import PeBacktestRow, CeBacktestRow, backtest_pe_leg, backtest_ce_leg


class TestBacktestPeLeg(unittest.TestCase):
    def test_stop_loss_with_no_reentry(self):
        # entry 700, trigger_pct 40 -> trigger 980.
        rows = [PeBacktestRow("2026-01-02", 680.0), PeBacktestRow("2026-01-05", 990.0)]

        result = backtest_pe_leg(rows, entry_price=700.0, quantity=75, trigger_pct=40)

        self.assertEqual(result["trigger_price"], 980.0)
        self.assertEqual(len(result["trades"]), 1)
        trade = result["trades"][0]
        self.assertEqual(trade.action, "STOP_LOSS")
        self.assertEqual(trade.exit_price, 990.0)
        self.assertAlmostEqual(trade.pnl_points, (700.0 - 990.0) * 75)
        self.assertAlmostEqual(result["total_pnl_points"], -21750.0)

    def test_stop_loss_then_capped_reentry_loss(self):
        # trigger 980, reentry rests at 980-20=960.
        rows = [
            PeBacktestRow("d1", 680.0),
            PeBacktestRow("d2", 985.0),  # STOP_LOSS fires here
            PeBacktestRow("d3", 970.0),  # above 960, still waiting
            PeBacktestRow("d4", 955.0),  # <=960 -> re-enter at 960
            PeBacktestRow("d5", 975.0),  # below flat stop 980, holds
            PeBacktestRow("d6", 982.0),  # >=980 -> STOP_LOSS_REENTRY exit
        ]

        result = backtest_pe_leg(rows, entry_price=700.0, quantity=75, trigger_pct=40,
                                  reentry_enabled=True, discount_points=20.0)

        self.assertEqual(len(result["trades"]), 2)
        first, second = result["trades"]
        self.assertEqual(first.action, "STOP_LOSS")
        self.assertEqual(first.exit_price, 985.0)
        self.assertEqual(second.action, "STOP_LOSS_REENTRY")
        self.assertEqual(second.entry_price, 960.0)
        self.assertEqual(second.exit_price, 982.0)
        # Capped near discount_points (20), not a fresh 40% of the new entry.
        self.assertAlmostEqual(second.pnl_points, (960.0 - 982.0) * 75)

    def test_reentry_never_fills_stays_waiting_forever(self):
        rows = [
            PeBacktestRow("d1", 680.0),
            PeBacktestRow("d2", 985.0),  # STOP_LOSS
            PeBacktestRow("d3", 970.0),  # never drops to <=960
        ]

        result = backtest_pe_leg(rows, entry_price=700.0, quantity=75, trigger_pct=40,
                                  reentry_enabled=True, discount_points=20.0)

        # Only the original stop-loss trade — no second leg was ever opened,
        # so there's nothing to hold-to-end either.
        self.assertEqual(len(result["trades"]), 1)
        self.assertEqual(result["trades"][0].action, "STOP_LOSS")

    def test_no_stop_hit_holds_to_end_of_data(self):
        rows = [PeBacktestRow("d1", 650.0), PeBacktestRow("d2", 600.0), PeBacktestRow("d3", 580.0)]

        result = backtest_pe_leg(rows, entry_price=700.0, quantity=75, trigger_pct=40)

        self.assertEqual(len(result["trades"]), 1)
        trade = result["trades"][0]
        self.assertEqual(trade.action, "HELD_TO_END")
        self.assertEqual(trade.exit_price, 580.0)
        self.assertAlmostEqual(trade.pnl_points, (700.0 - 580.0) * 75)


class TestBacktestCeLeg(unittest.TestCase):
    def test_counts_only_otm_below_threshold_rolls(self):
        rows = [
            CeBacktestRow("d1", premium=95.0, strike=24200.0, spot=24000.0),   # above threshold, no roll
            CeBacktestRow("d2", premium=85.0, strike=24200.0, spot=24000.0),   # below, OTM (24200>24000) -> roll
            CeBacktestRow("d3", premium=80.0, strike=24200.0, spot=24500.0),   # below, but ITM now -> no roll
            CeBacktestRow("d4", premium=70.0, strike=24800.0, spot=24500.0),   # below, OTM -> roll
        ]

        result = backtest_ce_leg(rows, exit_threshold=90.0, requires_otm=True)

        self.assertEqual(result["roll_count"], 2)
        self.assertEqual([e.date for e in result["roll_events"]], ["d2", "d4"])

    def test_otm_not_required_counts_every_below_threshold_row(self):
        rows = [
            CeBacktestRow("d1", premium=85.0, strike=24200.0, spot=24500.0),  # ITM, but OTM not required
        ]

        result = backtest_ce_leg(rows, exit_threshold=90.0, requires_otm=False)

        self.assertEqual(result["roll_count"], 1)


if __name__ == "__main__":
    unittest.main()
