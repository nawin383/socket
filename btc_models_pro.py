"""
Data Models and Database Management for Bitcoin Trading Platform Pro
"""
import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict, field
from pathlib import Path


@dataclass
class Trade:
    """Trade model"""
    id: int
    trade_type: str  # 'buy' or 'sell'
    instrument: str
    trading_symbol: str
    exchange: str
    instrument_type: str  # 'FUT', 'PERP', 'CE', 'PE'
    quantity: float
    entry_price: float
    current_price: float
    entry_date: str
    status: str  # 'open' or 'closed'

    # Optional fields
    exit_price: Optional[float] = None
    exit_date: Optional[str] = None
    strike: Optional[float] = None
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0

    # Order management
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    # Greeks (for options)
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    rho: Optional[float] = None
    iv: Optional[float] = None

    # Metadata
    notes: str = ""
    tags: str = ""  # comma-separated

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)

    def calculate_pnl(self) -> float:
        """Calculate P&L"""
        if self.status == 'closed' and self.exit_price:
            if self.trade_type == 'buy':
                return (self.exit_price - self.entry_price) * self.quantity
            else:
                return (self.entry_price - self.exit_price) * self.quantity
        else:
            if self.trade_type == 'buy':
                return (self.current_price - self.entry_price) * self.quantity
            else:
                return (self.entry_price - self.current_price) * self.quantity


@dataclass
class Portfolio:
    """Portfolio model"""
    id: int = 1
    initial_capital: float = 100000.0
    current_capital: float = 100000.0
    total_pnl: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


class DatabaseManager:
    """Database manager for trades and portfolio"""

    def __init__(self, db_path: str = "btc_trading_pro.db"):
        self.db_path = Path(db_path)
        self.conn: Optional[sqlite3.Connection] = None
        self.init_database()

    def init_database(self) -> None:
        """Initialize database tables"""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        cursor = self.conn.cursor()

        # Trades table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY,
                trade_type TEXT NOT NULL,
                instrument TEXT NOT NULL,
                trading_symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                instrument_type TEXT NOT NULL,
                quantity REAL NOT NULL,
                entry_price REAL NOT NULL,
                current_price REAL NOT NULL,
                entry_date TEXT NOT NULL,
                status TEXT NOT NULL,
                exit_price REAL,
                exit_date TEXT,
                strike REAL,
                unrealized_pnl REAL DEFAULT 0,
                realized_pnl REAL DEFAULT 0,
                stop_loss REAL,
                take_profit REAL,
                delta REAL,
                gamma REAL,
                theta REAL,
                vega REAL,
                rho REAL,
                iv REAL,
                notes TEXT,
                tags TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Portfolio table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS portfolio (
                id INTEGER PRIMARY KEY,
                initial_capital REAL NOT NULL,
                current_capital REAL NOT NULL,
                total_pnl REAL DEFAULT 0,
                realized_pnl REAL DEFAULT 0,
                unrealized_pnl REAL DEFAULT 0,
                total_trades INTEGER DEFAULT 0,
                winning_trades INTEGER DEFAULT 0,
                losing_trades INTEGER DEFAULT 0,
                max_drawdown REAL DEFAULT 0,
                sharpe_ratio REAL DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Analytics table for historical performance
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS portfolio_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                capital REAL NOT NULL,
                pnl REAL NOT NULL,
                daily_return REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Create portfolio if not exists
        cursor.execute('SELECT COUNT(*) FROM portfolio')
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO portfolio (id, initial_capital, current_capital)
                VALUES (1, 100000, 100000)
            ''')

        self.conn.commit()

    def add_trade(self, trade: Trade) -> int:
        """Add new trade"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO trades (
                id, trade_type, instrument, trading_symbol, exchange, instrument_type,
                quantity, entry_price, current_price, entry_date, status, exit_price,
                exit_date, strike, unrealized_pnl, realized_pnl, stop_loss, take_profit,
                delta, gamma, theta, vega, rho, iv, notes, tags
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            trade.id, trade.trade_type, trade.instrument, trade.trading_symbol,
            trade.exchange, trade.instrument_type, trade.quantity, trade.entry_price,
            trade.current_price, trade.entry_date, trade.status, trade.exit_price,
            trade.exit_date, trade.strike, trade.unrealized_pnl, trade.realized_pnl,
            trade.stop_loss, trade.take_profit, trade.delta, trade.gamma, trade.theta,
            trade.vega, trade.rho, trade.iv, trade.notes, trade.tags
        ))
        self.conn.commit()
        return cursor.lastrowid

    def update_trade(self, trade: Trade) -> None:
        """Update existing trade"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE trades SET
                current_price = ?,
                status = ?,
                exit_price = ?,
                exit_date = ?,
                unrealized_pnl = ?,
                realized_pnl = ?,
                stop_loss = ?,
                take_profit = ?,
                delta = ?,
                gamma = ?,
                theta = ?,
                vega = ?,
                rho = ?,
                iv = ?,
                notes = ?,
                tags = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (
            trade.current_price, trade.status, trade.exit_price, trade.exit_date,
            trade.unrealized_pnl, trade.realized_pnl, trade.stop_loss, trade.take_profit,
            trade.delta, trade.gamma, trade.theta, trade.vega, trade.rho, trade.iv,
            trade.notes, trade.tags, trade.id
        ))
        self.conn.commit()

    def get_trade(self, trade_id: int) -> Optional[Trade]:
        """Get trade by ID"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM trades WHERE id = ?', (trade_id,))
        row = cursor.fetchone()
        if row:
            return self._row_to_trade(row)
        return None

    def get_all_trades(self, status: Optional[str] = None) -> List[Trade]:
        """Get all trades"""
        cursor = self.conn.cursor()
        if status:
            cursor.execute('SELECT * FROM trades WHERE status = ? ORDER BY entry_date DESC', (status,))
        else:
            cursor.execute('SELECT * FROM trades ORDER BY entry_date DESC')

        return [self._row_to_trade(row) for row in cursor.fetchall()]

    def get_open_trades(self) -> List[Trade]:
        """Get open trades"""
        return self.get_all_trades(status='open')

    def get_closed_trades(self) -> List[Trade]:
        """Get closed trades"""
        return self.get_all_trades(status='closed')

    def delete_trade(self, trade_id: int) -> None:
        """Delete trade"""
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM trades WHERE id = ?', (trade_id,))
        self.conn.commit()

    def _row_to_trade(self, row: sqlite3.Row) -> Trade:
        """Convert database row to Trade object"""
        return Trade(
            id=row['id'],
            trade_type=row['trade_type'],
            instrument=row['instrument'],
            trading_symbol=row['trading_symbol'],
            exchange=row['exchange'],
            instrument_type=row['instrument_type'],
            quantity=row['quantity'],
            entry_price=row['entry_price'],
            current_price=row['current_price'],
            entry_date=row['entry_date'],
            status=row['status'],
            exit_price=row['exit_price'],
            exit_date=row['exit_date'],
            strike=row['strike'],
            unrealized_pnl=row['unrealized_pnl'] or 0,
            realized_pnl=row['realized_pnl'] or 0,
            stop_loss=row['stop_loss'],
            take_profit=row['take_profit'],
            delta=row['delta'],
            gamma=row['gamma'],
            theta=row['theta'],
            vega=row['vega'],
            rho=row['rho'],
            iv=row['iv'],
            notes=row['notes'] or "",
            tags=row['tags'] or ""
        )

    def get_portfolio(self) -> Portfolio:
        """Get portfolio"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM portfolio WHERE id = 1')
        row = cursor.fetchone()

        if row:
            return Portfolio(
                id=row['id'],
                initial_capital=row['initial_capital'],
                current_capital=row['current_capital'],
                total_pnl=row['total_pnl'],
                realized_pnl=row['realized_pnl'],
                unrealized_pnl=row['unrealized_pnl'],
                total_trades=row['total_trades'],
                winning_trades=row['winning_trades'],
                losing_trades=row['losing_trades'],
                max_drawdown=row['max_drawdown'],
                sharpe_ratio=row['sharpe_ratio'],
                updated_at=row['updated_at']
            )
        return Portfolio()

    def update_portfolio(self, portfolio: Portfolio) -> None:
        """Update portfolio"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE portfolio SET
                initial_capital = ?,
                current_capital = ?,
                total_pnl = ?,
                realized_pnl = ?,
                unrealized_pnl = ?,
                total_trades = ?,
                winning_trades = ?,
                losing_trades = ?,
                max_drawdown = ?,
                sharpe_ratio = ?,
                updated_at = ?
            WHERE id = 1
        ''', (
            portfolio.initial_capital, portfolio.current_capital, portfolio.total_pnl,
            portfolio.realized_pnl, portfolio.unrealized_pnl, portfolio.total_trades,
            portfolio.winning_trades, portfolio.losing_trades, portfolio.max_drawdown,
            portfolio.sharpe_ratio, datetime.now().isoformat()
        ))
        self.conn.commit()

    def add_portfolio_snapshot(self, capital: float, pnl: float, daily_return: float = 0) -> None:
        """Add portfolio snapshot for historical tracking"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO portfolio_history (date, capital, pnl, daily_return)
            VALUES (?, ?, ?, ?)
        ''', (datetime.now().strftime('%Y-%m-%d'), capital, pnl, daily_return))
        self.conn.commit()

    def get_portfolio_history(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get portfolio history"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM portfolio_history
            ORDER BY date DESC
            LIMIT ?
        ''', (days,))

        return [dict(row) for row in cursor.fetchall()]

    def close(self) -> None:
        """Close database connection"""
        if self.conn:
            self.conn.close()
