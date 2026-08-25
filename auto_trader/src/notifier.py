"""Telegram notifications for trade events, errors, startup/shutdown, and command replies."""

import logging

import requests

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self, bot_token: str, chat_id: str, enabled: bool = True):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = enabled and bool(bot_token) and bool(chat_id)

    def _post(self, chat_id: str, message: str, parse_mode: str = None) -> bool:
        """
        POST sendMessage and verify Telegram actually accepted it.

        A malformed parse_mode payload (e.g. unbalanced Markdown from an
        interpolated exception string) gets HTTP 400 with ok:false — requests
        doesn't raise for that, so a naive fire-and-forget silently drops the
        message with no log and no retry. Check the response body explicitly.
        """
        payload = {"chat_id": chat_id, "text": message}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                data=payload,
                timeout=10,
            )
        except Exception as e:
            logger.error("Telegram send request failed: %s", e)
            return False
        if resp.status_code == 200:
            return True
        logger.warning("Telegram send rejected (%s): %s", resp.status_code, resp.text[:300])
        return False

    def send(self, message: str, parse_mode: str = None, chat_id: str = None):
        """Send a notification. Keeps backward-compat with existing calls."""
        target_chat = chat_id or self.chat_id
        logger.info("NOTIFY: %s", message)
        if not self.enabled:
            return
        if not target_chat:
            logger.warning("No chat_id configured — skipping Telegram send")
            return
        if self._post(target_chat, message, parse_mode):
            return
        if parse_mode and self._post(target_chat, message, None):
            logger.info("Telegram send succeeded on plain-text fallback")
            return
        logger.error("Telegram notification dropped after formatted + plain-text attempts")

    def reply(self, chat_id: str, message: str, parse_mode: str = "Markdown"):
        """Reply to a specific chat (used by TelegramBot command handler)."""
        if self._post(chat_id, message, parse_mode):
            return
        if parse_mode and self._post(chat_id, message, None):
            return
        logger.error("Telegram reply to %s dropped after formatted + plain-text attempts", chat_id)
