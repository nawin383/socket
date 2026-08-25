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
    entry_time TEXT NOT NULL,
    sl_reference_price REAL
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

CREATE TABLE IF NOT EXISTS sl_events (
    leg TEXT NOT NULL,
    trading_day TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL NOT NULL,
    time TEXT NOT NULL,
    PRIMARY KEY (leg, trading_day)
);

CREATE TABLE IF NOT EXISTS tp_events (
    leg TEXT NOT NULL,
    trading_day TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL NOT NULL,
    time TEXT NOT NULL,
    PRIMARY KEY (leg, trading_day)
);

CREATE TABLE IF NOT EXISTS squareoff_events (
    leg TEXT NOT NULL,
    trading_day TEXT NOT NULL,
    reason TEXT NOT NULL,
    time TEXT NOT NULL,
    PRIMARY KEY (leg, trading_day)
);

CREATE TABLE IF NOT EXISTS pending_orders (
    leg TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    tradingsymbol TEXT NOT NULL,
    instrument_token INTEGER NOT NULL,
    exchange TEXT NOT NULL,
    strike REAL NOT NULL,
    quantity INTEGER NOT NULL,
    limit_price REAL NOT NULL,
    sl_reference_price REAL NOT NULL,
    valid_until TEXT NOT NULL,
    placed_time TEXT NOT NULL
);
"""


class StateStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        with closing(self._connect()) as conn:
            conn.executescript(SCHEMA)
            self._migrate(conn)
            conn.commit()

    def _migrate(self, conn: sqlite3.Connection):
        """CREATE TABLE IF NOT EXISTS only helps brand-new databases — this repo's
        committed state.db already had a `legs` table before sl_reference_price
        existed, so that column needs an explicit ALTER on existing databases."""
        cols = {row[1] for row in conn.execute("PRAGMA table_info(legs)")}
        if "sl_reference_price" not in cols:
            conn.execute("ALTER TABLE legs ADD COLUMN sl_reference_price REAL")

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_leg(self, leg: str) -> Optional[sqlite3.Row]:
        with closing(self._connect()) as conn:
            return conn.execute("SELECT * FROM legs WHERE leg = ?", (leg,)).fetchone()

    def set_leg(self, leg: str, tradingsymbol: str, instrument_token: int, exchange: str,
                strike: float, option_type: str, quantity: int, entry_price: float,
                sl_reference_price: Optional[float] = None):
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO legs "
                "(leg, tradingsymbol, instrument_token, exchange, strike, option_type, "
                " quantity, entry_price, entry_time, sl_reference_price) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (leg, tradingsymbol, instrument_token, exchange, strike, option_type,
                 quantity, entry_price, datetime.now().isoformat(), sl_reference_price),
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
        """Read-only when today's row already exists, so polling this on every
        run (as the GitHub Actions poller does) doesn't churn the on-disk file
        and create a noisy commit when nothing actually changed."""
        today = datetime.now().date().isoformat()
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM daily_state WHERE trading_day = ?", (today,)).fetchone()
            if row is None:
                conn.execute("INSERT INTO daily_state (trading_day) VALUES (?)", (today,))
                conn.commit()
                row = conn.execute("SELECT * FROM daily_state WHERE trading_day = ?", (today,)).fetchone()
            return row

    def record_stop_loss(self, leg: str, trading_day: str, entry_price: float, exit_price: float):
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sl_events (leg, trading_day, entry_price, exit_price, time) "
                "VALUES (?,?,?,?,?)",
                (leg, trading_day, entry_price, exit_price, datetime.now().isoformat()),
            )
            conn.commit()

    def stop_loss_fired_today(self, leg: str) -> bool:
        today = datetime.now().date().isoformat()
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT 1 FROM sl_events WHERE leg = ? AND trading_day = ?", (leg, today)
            ).fetchone()
            return row is not None

    def record_take_profit(self, leg: str, trading_day: str, entry_price: float, exit_price: float):
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO tp_events (leg, trading_day, entry_price, exit_price, time) "
                "VALUES (?,?,?,?,?)",
                (leg, trading_day, entry_price, exit_price, datetime.now().isoformat()),
            )
            conn.commit()

    def take_profit_fired_today(self, leg: str) -> bool:
        today = datetime.now().date().isoformat()
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT 1 FROM tp_events WHERE leg = ? AND trading_day = ?", (leg, today)
            ).fetchone()
            return row is not None

    def record_squareoff(self, leg: str, trading_day: str, reason: str):
        """
        Mark that this leg was deliberately squared off (EOD/expiry, daily-loss
        halt, or a manual /squareoff) today — distinct from a CE roll, which
        re-enters immediately and never leaves the leg flat across cycles.

        reconcile_from_broker() checks this before adopting: in paper mode a
        square-off is simulated only, so a real broker-adopted position stays
        genuinely open at the broker afterward. Without this flag, the very
        next poll would see that still-open real position, re-adopt it as if
        it were brand new, and immediately hit the same square-off condition
        again — an infinite adopt/square-off loop, one fake PnL entry and one
        "Adopted existing broker position" Telegram message per poll cycle.
        """
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO squareoff_events (leg, trading_day, reason, time) "
                "VALUES (?,?,?,?)",
                (leg, trading_day, reason, datetime.now().isoformat()),
            )
            conn.commit()

    def squared_off_today(self, leg: str) -> bool:
        today = datetime.now().date().isoformat()
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT 1 FROM squareoff_events WHERE leg = ? AND trading_day = ?", (leg, today)
            ).fetchone()
            return row is not None

    def set_pending_order(self, leg: str, order_id: str, tradingsymbol: str, instrument_token: int,
                           exchange: str, strike: float, quantity: int, limit_price: float,
                           sl_reference_price: float, valid_until: str):
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO pending_orders "
                "(leg, order_id, tradingsymbol, instrument_token, exchange, strike, quantity, "
                " limit_price, sl_reference_price, valid_until, placed_time) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (leg, order_id, tradingsymbol, instrument_token, exchange, strike, quantity,
                 limit_price, sl_reference_price, valid_until, datetime.now().isoformat()),
            )
            conn.commit()

    def get_pending_order(self, leg: str) -> Optional[sqlite3.Row]:
        with closing(self._connect()) as conn:
            return conn.execute("SELECT * FROM pending_orders WHERE leg = ?", (leg,)).fetchone()

    def clear_pending_order(self, leg: str):
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM pending_orders WHERE leg = ?", (leg,))
            conn.commit()
