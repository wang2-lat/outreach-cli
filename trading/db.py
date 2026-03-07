"""Trading-specific SQLite database (separate from outreach.db).

Stores trades, portfolio snapshots, risk events, daily equity, and factor scores.
"""

import sqlite3
import json
from datetime import datetime
from typing import Optional

from trading.config import TRADING_DB_PATH


class TradingDatabase:
    def __init__(self, db_path: str = TRADING_DB_PATH):
        self.db_path = db_path
        self._persistent_conn = None  # for :memory: databases
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        if self.db_path == ":memory:":
            if self._persistent_conn is None:
                self._persistent_conn = sqlite3.connect(":memory:")
                self._persistent_conn.row_factory = sqlite3.Row
            return self._persistent_conn
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _close(self, conn: sqlite3.Connection):
        if self.db_path != ":memory:":
            self._close(conn)

    def _init_db(self):
        conn = self._conn()
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,           -- 'buy' or 'sell'
                quantity REAL NOT NULL,
                entry_time TEXT,
                entry_price REAL,
                exit_time TEXT,
                exit_price REAL,
                stop_loss_price REAL,
                signal_type TEXT,             -- which factor triggered
                exit_reason TEXT,             -- 'stop_loss', 'take_profit', 'rebalance', 'drawdown'
                pnl REAL,
                slippage REAL,
                factor_attribution TEXT,      -- JSON: {"momentum": 0.3, "value": 0.1, ...}
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT DEFAULT (datetime('now')),
                total_equity REAL NOT NULL,
                cash REAL NOT NULL,
                positions_json TEXT,          -- JSON array of holdings
                industry_exposure_json TEXT   -- JSON: {"Technology": 0.15, ...}
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS risk_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT DEFAULT (datetime('now')),
                event_type TEXT NOT NULL,     -- 'stop_loss', 'weekly_drawdown', 'total_drawdown', 'cooldown', 'vix_block'
                details TEXT,
                symbol TEXT,
                equity_at_event REAL
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS daily_equity (
                date TEXT PRIMARY KEY,
                equity REAL NOT NULL,
                peak_equity REAL NOT NULL,
                drawdown_pct REAL NOT NULL
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS factor_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                momentum_score REAL,
                value_score REAL,
                quality_score REAL,
                sentiment_score REAL,
                macro_score REAL,
                composite_score REAL,
                UNIQUE(date, symbol)
            )
        """)

        conn.commit()
        self._close(conn)

    # ------------------------------------------------------------------
    # Trades
    # ------------------------------------------------------------------

    def record_entry(self, symbol: str, side: str, quantity: float,
                     entry_price: float, stop_loss_price: float,
                     signal_type: str) -> int:
        conn = self._conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO trades (symbol, side, quantity, entry_time, entry_price,
                                stop_loss_price, signal_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (symbol, side, quantity, datetime.utcnow().isoformat(),
              entry_price, stop_loss_price, signal_type))
        trade_id = c.lastrowid
        conn.commit()
        self._close(conn)
        return trade_id

    def record_exit(self, trade_id: int, exit_price: float,
                    exit_reason: str, slippage: float = 0.0,
                    factor_attribution: Optional[dict] = None):
        conn = self._conn()
        c = conn.cursor()
        # Fetch entry to compute P&L
        c.execute("SELECT entry_price, quantity, side FROM trades WHERE id = ?",
                  (trade_id,))
        row = c.fetchone()
        if row is None:
            self._close(conn)
            return

        entry_price, quantity, side = row["entry_price"], row["quantity"], row["side"]
        if side == "buy":
            pnl = (exit_price - entry_price) * quantity
        else:
            pnl = (entry_price - exit_price) * quantity

        attr_json = json.dumps(factor_attribution) if factor_attribution else None

        c.execute("""
            UPDATE trades
            SET exit_time = ?, exit_price = ?, exit_reason = ?,
                pnl = ?, slippage = ?, factor_attribution = ?
            WHERE id = ?
        """, (datetime.utcnow().isoformat(), exit_price, exit_reason,
              pnl, slippage, attr_json, trade_id))
        conn.commit()
        self._close(conn)

    def get_open_trades(self) -> list:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM trades WHERE exit_time IS NULL ORDER BY entry_time"
        ).fetchall()
        self._close(conn)
        return [dict(r) for r in rows]

    def get_closed_trades(self, limit: int = 100) -> list:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM trades WHERE exit_time IS NOT NULL "
            "ORDER BY exit_time DESC LIMIT ?", (limit,)
        ).fetchall()
        self._close(conn)
        return [dict(r) for r in rows]

    def get_trades_since(self, since_iso: str) -> list:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM trades WHERE entry_time >= ? ORDER BY entry_time",
            (since_iso,)
        ).fetchall()
        self._close(conn)
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Portfolio snapshots
    # ------------------------------------------------------------------

    def save_snapshot(self, total_equity: float, cash: float,
                      positions: list, industry_exposure: dict):
        conn = self._conn()
        conn.execute("""
            INSERT INTO portfolio_snapshots
                (total_equity, cash, positions_json, industry_exposure_json)
            VALUES (?, ?, ?, ?)
        """, (total_equity, cash, json.dumps(positions),
              json.dumps(industry_exposure)))
        conn.commit()
        self._close(conn)

    # ------------------------------------------------------------------
    # Risk events
    # ------------------------------------------------------------------

    def record_risk_event(self, event_type: str, details: str = "",
                          symbol: str = "", equity: float = 0.0):
        conn = self._conn()
        conn.execute("""
            INSERT INTO risk_events (event_type, details, symbol, equity_at_event)
            VALUES (?, ?, ?, ?)
        """, (event_type, details, symbol, equity))
        conn.commit()
        self._close(conn)

    def get_recent_risk_events(self, limit: int = 20) -> list:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM risk_events ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        ).fetchall()
        self._close(conn)
        return [dict(r) for r in rows]

    def get_last_stop_loss_time(self) -> Optional[str]:
        conn = self._conn()
        row = conn.execute(
            "SELECT timestamp FROM risk_events WHERE event_type = 'stop_loss' "
            "ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        self._close(conn)
        return row["timestamp"] if row else None

    # ------------------------------------------------------------------
    # Daily equity tracking
    # ------------------------------------------------------------------

    def record_daily_equity(self, date_str: str, equity: float,
                            peak_equity: float, drawdown_pct: float):
        conn = self._conn()
        conn.execute("""
            INSERT OR REPLACE INTO daily_equity (date, equity, peak_equity, drawdown_pct)
            VALUES (?, ?, ?, ?)
        """, (date_str, equity, peak_equity, drawdown_pct))
        conn.commit()
        self._close(conn)

    def get_equity_series(self, days: int = 365) -> list:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM daily_equity ORDER BY date DESC LIMIT ?", (days,)
        ).fetchall()
        self._close(conn)
        return [dict(r) for r in reversed(rows)]

    def get_weekly_equity(self, days: int = 7) -> list:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM daily_equity WHERE date >= date('now', '-' || ? || ' days') "
            "ORDER BY date", (days,)
        ).fetchall()
        self._close(conn)
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Factor scores
    # ------------------------------------------------------------------

    def save_factor_scores(self, date_str: str, symbol: str,
                           momentum: float, value: float, quality: float,
                           sentiment: float, macro: float, composite: float):
        conn = self._conn()
        conn.execute("""
            INSERT OR REPLACE INTO factor_scores
                (date, symbol, momentum_score, value_score, quality_score,
                 sentiment_score, macro_score, composite_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (date_str, symbol, momentum, value, quality,
              sentiment, macro, composite))
        conn.commit()
        self._close(conn)
