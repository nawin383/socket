"""
Loads secrets from .env and strategy/risk config from config/config.yaml.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

import yaml
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _env(name: str, default: str = None, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required environment variable: {name} (check auto_trader/.env)")
    return value


@dataclass
class Settings:
    api_key: str
    api_secret: str
    kite_user_id: str
    kite_password: str
    kite_totp_secret: str
    telegram_bot_token: str
    telegram_chat_id: str
    config: Dict[str, Any] = field(default_factory=dict)

    @property
    def mode(self) -> str:
        return self.config.get("mode", "paper")


def load_settings(config_path: Path = None) -> Settings:
    config_path = config_path or BASE_DIR / "config" / "config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    return Settings(
        api_key=_env("KITE_API_KEY", required=True),
        api_secret=_env("KITE_API_SECRET", required=True),
        kite_user_id=_env("KITE_USER_ID", required=True),
        kite_password=_env("KITE_PASSWORD", required=True),
        kite_totp_secret=_env("KITE_TOTP_SECRET", required=True),
        telegram_bot_token=_env("TELEGRAM_BOT_TOKEN", default=""),
        telegram_chat_id=_env("TELEGRAM_CHAT_ID", default=""),
        config=config,
    )
