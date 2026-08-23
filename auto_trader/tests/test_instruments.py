"""Unit tests for pure moneyness/strike math (no live API calls)."""

import unittest
from datetime import date

from src.instruments import is_itm, is_otm, round_to_strike_step


class TestMoneyness(unittest.TestCase):
    def test_round_to_strike_step(self):
        self.assertEqual(round_to_strike_step(24732, 50), 24750)
        self.assertEqual(round_to_strike_step(24710, 50), 24700)

    def test_ce_otm_when_strike_above_spot(self):
        self.assertTrue(is_otm("CE", 25000, 24800))
        self.assertFalse(is_otm("CE", 24700, 24800))

    def test_ce_itm_when_strike_below_spot(self):
        self.assertTrue(is_itm("CE", 24700, 24800))
        self.assertFalse(is_itm("CE", 25000, 24800))

    def test_pe_otm_when_strike_below_spot(self):
        self.assertTrue(is_otm("PE", 24700, 24800))
        self.assertFalse(is_otm("PE", 25000, 24800))

    def test_pe_itm_when_strike_above_spot(self):
        self.assertTrue(is_itm("PE", 25000, 24800))
        self.assertFalse(is_itm("PE", 24700, 24800))


class TestExpirySelection(unittest.TestCase):
    def _store_with_expiries(self, expiries):
        from src.instruments import InstrumentStore

        store = InstrumentStore(kite=None, cache_dir=None)
        store.expiries = lambda name: expiries
        return store

    def test_weekly_expiry_picks_nearest_upcoming(self):
        store = self._store_with_expiries([date(2026, 1, 1), date(2026, 1, 8), date(2026, 1, 15)])
        self.assertEqual(store.weekly_expiry("NIFTY", date(2026, 1, 2)), date(2026, 1, 8))

    def test_monthly_expiry_is_last_expiry_of_the_month(self):
        store = self._store_with_expiries(
            [date(2026, 1, 8), date(2026, 1, 15), date(2026, 1, 22), date(2026, 1, 29), date(2026, 2, 5)]
        )
        self.assertEqual(store.monthly_expiry("NIFTY", date(2026, 1, 2)), date(2026, 1, 29))

    def test_monthly_expiry_falls_back_to_next_month_after_this_months_expiry(self):
        store = self._store_with_expiries([date(2026, 2, 5), date(2026, 2, 26)])
        self.assertEqual(store.monthly_expiry("NIFTY", date(2026, 1, 30)), date(2026, 2, 26))


if __name__ == "__main__":
    unittest.main()
