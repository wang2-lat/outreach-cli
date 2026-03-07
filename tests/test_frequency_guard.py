"""Unit tests for Layer 2: Frequency Guard."""

import unittest
from datetime import datetime, timedelta
from trading.frequency_guard import FrequencyGuard
from trading.db import TradingDatabase
from trading.config import MIN_HOLD_DAYS, MAX_NEW_POSITIONS_PER_WEEK


class TestFrequencyGuard(unittest.TestCase):

    def setUp(self):
        self.db = TradingDatabase(":memory:")
        self.guard = FrequencyGuard(self.db)

    # ------------------------------------------------------------------
    # 1. Minimum hold period (5 trading days)
    # ------------------------------------------------------------------
    def test_sell_before_5_days_rejected(self):
        """Selling a position held <5 days should be rejected."""
        # Record a trade entry 3 days ago
        entry_time = (datetime.utcnow() - timedelta(days=3)).isoformat()
        conn = self.db._conn()
        conn.execute(
            "INSERT INTO trades (symbol, side, quantity, entry_time, entry_price, "
            "stop_loss_price, signal_type) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("AAPL", "buy", 100, entry_time, 150.0, 147.0, "momentum")
        )
        conn.commit()

        ok, reason = self.guard.check_min_hold("AAPL")
        self.assertFalse(ok)
        self.assertIn("3 days", reason)

    def test_sell_after_5_days_allowed(self):
        """Selling a position held >=5 days should be allowed."""
        entry_time = (datetime.utcnow() - timedelta(days=6)).isoformat()
        conn = self.db._conn()
        conn.execute(
            "INSERT INTO trades (symbol, side, quantity, entry_time, entry_price, "
            "stop_loss_price, signal_type) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("AAPL", "buy", 100, entry_time, 150.0, 147.0, "momentum")
        )
        conn.commit()

        ok, reason = self.guard.check_min_hold("AAPL")
        self.assertTrue(ok)

    def test_sell_exactly_5_days_allowed(self):
        """Selling at exactly 5 days should be allowed (>=5, not >5)."""
        entry_time = (datetime.utcnow() - timedelta(days=5)).isoformat()
        conn = self.db._conn()
        conn.execute(
            "INSERT INTO trades (symbol, side, quantity, entry_time, entry_price, "
            "stop_loss_price, signal_type) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("AAPL", "buy", 100, entry_time, 150.0, 147.0, "momentum")
        )
        conn.commit()

        ok, reason = self.guard.check_min_hold("AAPL")
        self.assertTrue(ok, f"Exactly 5 days should be allowed, got: {reason}")

    # ------------------------------------------------------------------
    # 2. Weekly position limit (max 5 per week)
    # ------------------------------------------------------------------
    def test_6th_position_this_week_rejected(self):
        """Opening a 6th new position in the same week should be rejected."""
        # Insert 5 buy trades this week (today)
        now = datetime.utcnow().isoformat()
        conn = self.db._conn()
        for i in range(5):
            conn.execute(
                "INSERT INTO trades (symbol, side, quantity, entry_time, entry_price, "
                "stop_loss_price, signal_type) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (f"SYM{i}", "buy", 10, now, 100.0, 98.0, "momentum")
            )
        conn.commit()

        ok, reason = self.guard.can_open_position()
        self.assertFalse(ok)
        self.assertIn("5", reason)

    def test_under_weekly_limit_allowed(self):
        """Opening positions under the weekly limit should be fine."""
        now = datetime.utcnow().isoformat()
        conn = self.db._conn()
        for i in range(3):
            conn.execute(
                "INSERT INTO trades (symbol, side, quantity, entry_time, entry_price, "
                "stop_loss_price, signal_type) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (f"SYM{i}", "buy", 10, now, 100.0, 98.0, "momentum")
            )
        conn.commit()

        ok, reason = self.guard.can_open_position()
        self.assertTrue(ok)

    # ------------------------------------------------------------------
    # 3. Post-stop-loss cooldown (24 hours)
    # ------------------------------------------------------------------
    def test_cooldown_after_stop_loss_blocks_new_positions(self):
        """Cannot open new positions within 24h of a stop-loss event."""
        self.guard.record_stop_loss_event("AAPL", 95_000.0)

        ok, reason = self.guard.check_cooldown()
        self.assertFalse(ok)
        self.assertIn("Cooldown", reason)

    def test_cooldown_expired_allows_new_positions(self):
        """After 24h cooldown expires, new positions should be allowed."""
        # Insert a stop-loss event 25 hours ago
        old_time = (datetime.utcnow() - timedelta(hours=25)).isoformat()
        conn = self.db._conn()
        conn.execute(
            "INSERT INTO risk_events (event_type, details, symbol, equity_at_event, timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            ("stop_loss", "test", "AAPL", 95000.0, old_time)
        )
        conn.commit()

        ok, reason = self.guard.check_cooldown()
        self.assertTrue(ok, f"Cooldown should have expired, got: {reason}")

    def test_can_open_position_checks_cooldown_first(self):
        """can_open_position() should check cooldown before weekly limit."""
        self.guard.record_stop_loss_event("AAPL", 95_000.0)
        ok, reason = self.guard.can_open_position()
        self.assertFalse(ok)
        self.assertIn("Cooldown", reason)


if __name__ == "__main__":
    unittest.main()
