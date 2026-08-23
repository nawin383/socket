"""
Automated daily login for Kite Connect using TOTP.

Zerodha access tokens expire every day around 6 AM IST, so a bot running
unattended on a server needs a fresh one each morning. This logs in
headlessly using your Kite username/password + TOTP secret, walks the
Kite Connect authorize redirect to get a request_token, and exchanges it
for an access_token — without needing a real server behind your app's
registered redirect URL.

This relies on Zerodha's own web login pages (there is no official
"headless login" API). It is a widely used pattern in the retail
algo-trading community, but Zerodha can change the login flow at any
time, which would break auto-login here. The bot alerts you (Telegram +
logs) if login fails; keep an eye on it, and be ready to log in manually
if this ever stops working.

You are responsible for how you use your own login credentials. Keep the
.env file this reads from off any shared or public system.
"""

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pyotp
import requests
from kiteconnect import KiteConnect

logger = logging.getLogger(__name__)

LOGIN_URL = "https://kite.zerodha.com/api/login"
TWOFA_URL = "https://kite.zerodha.com/api/twofa"
CONNECT_URL = "https://kite.zerodha.com/connect/login"


class LoginError(Exception):
    pass


@dataclass
class TokenCache:
    path: Path

    def load(self):
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text())
            if data.get("date") == date.today().isoformat():
                return data.get("access_token")
        except Exception:
            logger.warning("Could not read cached token file, ignoring it", exc_info=True)
        return None

    def save(self, access_token: str):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({
            "date": date.today().isoformat(),
            "access_token": access_token,
            "saved_at": datetime.now().isoformat(),
        }))


def _fetch_request_token(api_key: str, user_id: str, password: str, totp_secret: str) -> str:
    session = requests.Session()

    r = session.post(LOGIN_URL, data={"user_id": user_id, "password": password}, timeout=15)
    r.raise_for_status()
    payload = r.json()
    if payload.get("status") != "success":
        raise LoginError(f"Login step failed: {payload}")
    request_id = payload["data"]["request_id"]

    totp_code = pyotp.TOTP(totp_secret).now()
    r = session.post(
        TWOFA_URL,
        data={"user_id": user_id, "request_id": request_id, "twofa_value": totp_code, "twofa_type": "totp"},
        timeout=15,
    )
    r.raise_for_status()
    if r.json().get("status") != "success":
        raise LoginError(f"TOTP step failed: {r.json()}")

    # Manually follow the Connect authorize redirect chain (never actually
    # requesting the final redirect_url, since it doesn't need to be a real
    # reachable server) until we see a Location containing request_token.
    url, params = CONNECT_URL, {"api_key": api_key, "v": "3"}
    for _ in range(10):
        r = session.get(url, params=params, allow_redirects=False, timeout=15)
        params = None
        location = r.headers.get("Location")
        if not location:
            break
        query = parse_qs(urlparse(location).query)
        if "request_token" in query:
            return query["request_token"][0]
        url = location

    raise LoginError(
        "Could not obtain a request_token from Zerodha's login redirect. "
        "The login flow may have changed — try a manual login to confirm your "
        "credentials/TOTP secret are correct."
    )


def get_access_token(api_key: str, api_secret: str, user_id: str, password: str,
                      totp_secret: str, cache_path: Path) -> str:
    """Return today's access_token, reusing a cached one if it's still from today."""
    cache = TokenCache(cache_path)
    cached = cache.load()
    if cached:
        return cached

    request_token = _fetch_request_token(api_key, user_id, password, totp_secret)

    kite = KiteConnect(api_key=api_key)
    session_data = kite.generate_session(request_token, api_secret=api_secret)
    access_token = session_data["access_token"]

    cache.save(access_token)
    logger.info("Generated fresh Kite access_token for %s", date.today().isoformat())
    return access_token


if __name__ == "__main__":
    # Standalone check: `python -m src.auth` from the auto_trader/ directory.
    # Run this BEFORE deploying, to confirm auto-login actually works.
    from .settings import BASE_DIR, load_settings

    logging.basicConfig(level=logging.INFO)
    settings = load_settings()
    token = get_access_token(
        settings.api_key, settings.api_secret, settings.kite_user_id,
        settings.kite_password, settings.kite_totp_secret,
        BASE_DIR / "data" / "access_token.json",
    )
    print("Login OK. Access token starts with:", token[:6] + "...")
