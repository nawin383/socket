"""
Smoke tests for poll_once.main()'s wiring — construct every object it's
supposed to construct and call through in the right order. Deliberately
NOT testing strategy/risk decision logic here (that's test_strategy.py's
job); this exists to catch wiring bugs like an object being referenced
before it's constructed, which py_compile's syntax check can't catch and
no other test currently exercises main() at all.
"""

import unittest
from unittest.mock import MagicMock, patch

from src.risk import IST
from src.settings import Settings
from src import poll_once


def _fake_settings():
    return Settings(
        api_key="key", api_secret="secret", kite_user_id="user",
        kite_password="pass", kite_totp_secret="totp",
        telegram_bot_token="", telegram_chat_id="",
        config={
            "mode": "paper",
            "notifications": {"telegram_enabled": False},
            "underlying": {"name": "NIFTY", "spot_symbol": "NSE:NIFTY 50",
                            "spot_instrument_token": 256265, "strike_step": 50},
            "pe_leg": {"enabled": True}, "ce_leg": {"enabled": True},
            "orders": {}, "risk": {"kill_switch_file": "STOP_TRADING"},
        },
    )


class TestPollOnceMainWiring(unittest.TestCase):
    @patch("src.poll_once._run")
    @patch("src.poll_once.KiteConnect")
    @patch("src.poll_once.auth.get_access_token", return_value="fake-token")
    @patch("src.poll_once.load_settings", return_value=_fake_settings())
    def test_main_constructs_kite_client_before_running(self, _settings, _auth, kite_cls, run):
        poll_once.main()

        kite_cls.assert_called_once_with(api_key="key")
        kite_instance = kite_cls.return_value
        kite_instance.set_access_token.assert_called_once_with("fake-token")

        # _run must receive the actual constructed kite instance, not None/undefined.
        run.assert_called_once()
        called_kite = run.call_args[0][0]
        self.assertIs(called_kite, kite_instance)

    @patch("src.poll_once._run", side_effect=RuntimeError("order rejected: insufficient margin"))
    @patch("src.poll_once.KiteConnect")
    @patch("src.poll_once.auth.get_access_token", return_value="fake-token")
    @patch("src.poll_once.load_settings", return_value=_fake_settings())
    @patch("src.poll_once.Notifier")
    def test_crash_after_login_still_notifies_and_reraises(self, notifier_cls, _settings, _auth, _kite, _run):
        notifier = notifier_cls.return_value

        with self.assertRaises(RuntimeError):
            poll_once.main()

        sent = " ".join(str(call.args[0]) for call in notifier.send.call_args_list)
        self.assertIn("Poll run crashed", sent)
        self.assertIn("insufficient margin", sent)

    @patch("src.poll_once.auth.get_access_token", side_effect=RuntimeError("bad TOTP"))
    @patch("src.poll_once.load_settings", return_value=_fake_settings())
    @patch("src.poll_once.Notifier")
    def test_login_failure_notifies_with_its_own_message(self, notifier_cls, _settings, _auth):
        notifier = notifier_cls.return_value

        with self.assertRaises(RuntimeError):
            poll_once.main()

        sent = " ".join(str(call.args[0]) for call in notifier.send.call_args_list)
        self.assertIn("Login FAILED this run", sent)


class TestPollOnceUsesIST(unittest.TestCase):
    """
    Regression test: GitHub Actions runners default to UTC, but
    trading_start/trading_end in config.yaml are IST wall-clock times.
    _run() must build `now` with IST tzinfo (via risk.IST) before handing
    it to RiskGuard — a naive datetime.now() silently checks the wrong
    5.5-hour window instead of erroring, which is exactly what happened in
    production (a 10:29 IST run logged "Trading not allowed").
    """

    @patch("src.poll_once.NiftyOptionSellerStrategy")
    @patch("src.poll_once.OrderManager")
    @patch("src.poll_once.RiskGuard")
    @patch("src.poll_once.StateStore")
    @patch("src.poll_once.InstrumentStore")
    def test_run_passes_ist_aware_now_to_risk_guard(
        self, _store_cls, _state_cls, risk_cls, _orders_cls, _strategy_cls
    ):
        risk = risk_cls.return_value
        risk.is_trading_day.return_value = True
        risk.is_eod_square_off_time.return_value = False
        risk.daily_loss_breached.return_value = False
        risk.trading_allowed.return_value = False

        strategy = _strategy_cls.return_value
        strategy._get_overall_pnl_today.side_effect = RuntimeError("no quotes yet")

        config = {
            "underlying": {"spot_symbol": "NSE:NIFTY 50"},
            "risk": {"kill_switch_file": "STOP_TRADING"},
            "orders": {},
        }

        poll_once._run(MagicMock(), config, "paper", MagicMock())

        risk.is_trading_day.assert_called_once()
        now_arg = risk.is_trading_day.call_args[0][0]
        self.assertEqual(now_arg.tzinfo, IST)


if __name__ == "__main__":
    unittest.main()
