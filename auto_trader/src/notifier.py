"""Telegram notifications for trade events, errors, and startup/shutdown."""

import logging

import requests

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self, bot_token: str, chat_id: str, enabled: bool = True):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = enabled and bool(bot_token) and bool(chat_id)

    def send(self, message: str):
        logger.info("NOTIFY: %s", message)
        if not self.enabled:
            return
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                data={"chat_id": self.chat_id, "text": message},
                timeout=10,
            )
        except Exception as e:
            logger.error("Failed to send Telegram notification: %s", e)
