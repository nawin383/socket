"""Telegram notifications for trade events, errors, startup/shutdown, and command replies."""

import logging

import requests

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self, bot_token: str, chat_id: str, enabled: bool = True):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = enabled and bool(bot_token) and bool(chat_id)

    def send(self, message: str, parse_mode: str = None, chat_id: str = None):
        """Send a notification. Keeps backward-compat with existing calls."""
        target_chat = chat_id or self.chat_id
        logger.info("NOTIFY: %s", message)
        if not self.enabled:
            return
        if not target_chat:
            logger.warning("No chat_id configured — skipping Telegram send")
            return
        try:
            payload = {"chat_id": target_chat, "text": message}
            if parse_mode:
                payload["parse_mode"] = parse_mode
            # Prefer Markdown if message contains formatting, but keep plain as fallback
            requests.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                data=payload,
                timeout=10,
            )
        except Exception as e:
            logger.error("Failed to send Telegram notification: %s", e)

    def reply(self, chat_id: str, message: str, parse_mode: str = "Markdown"):
        """Reply to a specific chat (used by TelegramBot command handler)."""
        try:
            payload = {"chat_id": chat_id, "text": message}
            if parse_mode:
                payload["parse_mode"] = parse_mode
            requests.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                data=payload,
                timeout=10,
            )
        except Exception as e:
            logger.error("Failed to reply to %s: %s", chat_id, e)
            # fallback without markdown
            try:
                requests.post(
                    f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                    data={"chat_id": chat_id, "text": message},
                    timeout=10,
                )
            except Exception:
                pass
