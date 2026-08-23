"""
SQLite-backed state store for open legs, roll history, and daily P&L.

This file (data/state.db) is the bot's memory across restarts — as long as
it survives (e.g. it's on a mounted volume), a crash-and-restart won't lose
track of open positions or re-enter ones that are already live.
"""

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS legs (
    leg TEXT PRIMARY KEY,
    tradingsymbol TEXT NOT NULL,
    instrument_token INTEGER NOT NULL,
    exchange TEXT NOT NULL,
    strike REAL NOT NULL,
    option_type TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    entry_price REAL NOT NULL,
    entry_time TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS roll_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    leg TEXT NOT NULL,
    action TEXT NOT NULL,
    tradingsymbol TEXT NOT NULL,
    price REAL NOT NULL,
    quantity INTEGER NOT NULL,
    time TEXT NOT NULL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS daily_state (
    trading_day TEXT PRIMARY KEY,
    realized_pnl REAL NOT NULL DEFAULT 0,
    roll_count INTEGER NOT NULL DEFAULT 0,
    last_roll_time TEXT
);
"""


class StateStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        with closing(self._connect()) as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_leg(self, leg: str) -> Optional[sqlite3.Row]:
        with closing(self._connect()) as conn:
            return conn.execute("SELECT * FROM legs WHERE leg = ?", (leg,)).fetchone()

    def set_leg(self, leg: str, tradingsymbol: str, instrument_token: int, exchange: str,
                strike: float, option_type: str, quantity: int, entry_price: float):
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO legs "
                "(leg, tradingsymbol, instrument_token, exchange, strike, option_type, "
                " quantity, entry_price, entry_time) VALUES (?,?,?,?,?,?,?,?,?)",
                (leg, tradingsymbol, instrument_token, exchange, strike, option_type,
                 quantity, entry_price, datetime.now().isoformat()),
            )
            conn.commit()

    def clear_leg(self, leg: str):
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM legs WHERE leg = ?", (leg,))
            conn.commit()

    def log_roll(self, leg: str, action: str, tradingsymbol: str, price: float,
                 quantity: int, note: str = ""):
        today = datetime.now().date().isoformat()
        now_iso = datetime.now().isoformat()
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO roll_history (leg, action, tradingsymbol, price, quantity, time, note) "
                "VALUES (?,?,?,?,?,?,?)",
                (leg, action, tradingsymbol, price, quantity, now_iso, note),
            )
            conn.execute("INSERT OR IGNORE INTO daily_state (trading_day) VALUES (?)", (today,))
            conn.execute(
                "UPDATE daily_state SET roll_count = roll_count + 1, last_roll_time = ? "
                "WHERE trading_day = ?",
                (now_iso, today),
            )
            conn.commit()

    def add_realized_pnl(self, amount: float):
        today = datetime.now().date().isoformat()
        with closing(self._connect()) as conn:
            conn.execute("INSERT OR IGNORE INTO daily_state (trading_day) VALUES (?)", (today,))
            conn.execute(
                "UPDATE daily_state SET realized_pnl = realized_pnl + ? WHERE trading_day = ?",
                (amount, today),
            )
            conn.commit()

    def today_state(self) -> sqlite3.Row:
        today = datetime.now().date().isoformat()
        with closing(self._connect()) as conn:
            conn.execute("INSERT OR IGNORE INTO daily_state (trading_day) VALUES (?)", (today,))
            conn.commit()
            return conn.execute("SELECT * FROM daily_state WHERE trading_day = ?", (today,)).fetchone()
