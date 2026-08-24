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


if __name__ == "__main__":
    unittest.main()
