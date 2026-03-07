"""Unit tests for Layer 6: Anti-Pattern Enforcer."""

import unittest
from trading.anti_patterns import AntiPatternEnforcer
from trading.risk_engine import RiskEngine, OrderRequest
from trading.frequency_guard import FrequencyGuard
from trading.db import TradingDatabase
from trading.config import VIX_THRESHOLD
from datetime import datetime


class TestAntiPatterns(unittest.TestCase):

    def setUp(self):
        self.db = TradingDatabase(":memory:")
        self.risk = RiskEngine()
        self.freq = FrequencyGuard(self.db)
        self.enforcer = AntiPatternEnforcer(self.db, self.risk, self.freq)
        self.equity = 100_000.0

    def _make_order(self, symbol="AAPL", qty=10, price=100.0,
                    industry="Technology", signal="momentum"):
        return OrderRequest(symbol, "buy", qty, price, industry, signal)

    # ------------------------------------------------------------------
    # 1. No averaging down on losers
    # ------------------------------------------------------------------
    def test_averaging_down_rejected(self):
        """Adding to a losing position must be rejected."""
        # Record an open trade at $150, current price is $120
        conn = self.db._conn()
        conn.execute(
            "INSERT INTO trades (symbol, side, quantity, entry_time, entry_price, "
            "stop_loss_price, signal_type) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("AAPL", "buy", 100, datetime.utcnow().isoformat(), 150.0, 147.0, "momentum")
        )
        conn.commit()

        order = self._make_order("AAPL", qty=10, price=120.0)
        verdict = self.enforcer.check_all(
            order, self.equity, {"AAPL": 12_000.0}, {},
            self.equity, self.equity
        )
        self.assertFalse(verdict.approved)
        self.assertIn("ANTI-PATTERN #5", verdict.reason)

    def test_adding_to_winning_position_ok(self):
        """Adding to a winning position should not trigger anti-pattern #5."""
        conn = self.db._conn()
        conn.execute(
            "INSERT INTO trades (symbol, side, quantity, entry_time, entry_price, "
            "stop_loss_price, signal_type) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("AAPL", "buy", 10, datetime.utcnow().isoformat(), 100.0, 98.0, "momentum")
        )
        conn.commit()

        # Price is now $120 (winning), buy more at $120
        order = self._make_order("AAPL", qty=5, price=120.0)
        verdict = self.enforcer.check_all(
            order, self.equity, {"AAPL": 1_200.0}, {},
            self.equity, self.equity
        )
        # Should not fail on anti-pattern #5 specifically
        if not verdict.approved:
            self.assertNotIn("#5", verdict.reason)

    # ------------------------------------------------------------------
    # 2. No manual stop-loss override (architectural check)
    # ------------------------------------------------------------------
    def test_no_manual_stop_loss_override_interface(self):
        """There should be no method to disable or override stop-losses."""
        # Check that RiskEngine has no override methods
        risk_methods = dir(self.risk)
        forbidden = ["override_stop", "disable_stop", "cancel_stop",
                      "remove_stop", "ignore_stop"]
        for method in forbidden:
            self.assertNotIn(method, risk_methods,
                             f"Found forbidden method: {method}")

        # Check that AntiPatternEnforcer has no override methods
        enforcer_methods = dir(self.enforcer)
        for method in forbidden:
            self.assertNotIn(method, enforcer_methods,
                             f"Found forbidden method: {method}")

    # ------------------------------------------------------------------
    # 3. VIX > 35 blocks new positions
    # ------------------------------------------------------------------
    def test_high_vix_blocks_new_positions(self):
        """VIX=40 should block all new buy orders."""
        order = self._make_order()
        verdict = self.enforcer.check_all(
            order, self.equity, {}, {},
            self.equity, self.equity,
            current_vix=40.0,
        )
        self.assertFalse(verdict.approved)
        self.assertIn("ANTI-PATTERN #9", verdict.reason)
        self.assertIn("VIX", verdict.reason)

    def test_low_vix_allows_positions(self):
        """VIX=20 should allow new positions."""
        order = self._make_order()
        verdict = self.enforcer.check_all(
            order, self.equity, {}, {},
            self.equity, self.equity,
            current_vix=20.0,
        )
        # Should not fail on VIX check
        if not verdict.approved:
            self.assertNotIn("#9", verdict.reason)

    def test_vix_exactly_35_allowed(self):
        """VIX exactly at 35 should still allow (threshold is >35, not >=35)."""
        order = self._make_order()
        verdict = self.enforcer.check_all(
            order, self.equity, {}, {},
            self.equity, self.equity,
            current_vix=35.0,
        )
        if not verdict.approved:
            self.assertNotIn("#9", verdict.reason)

    # ------------------------------------------------------------------
    # 4. No manual entries without signal
    # ------------------------------------------------------------------
    def test_no_signal_rejected(self):
        """Orders without a signal source must be rejected."""
        order = OrderRequest("AAPL", "buy", 10, 100.0, "Technology", "manual")
        verdict = self.enforcer.check_all(
            order, self.equity, {}, {},
            self.equity, self.equity
        )
        self.assertFalse(verdict.approved)
        self.assertIn("ANTI-PATTERN #8", verdict.reason)

    def test_empty_signal_rejected(self):
        """Empty signal type must be rejected."""
        order = OrderRequest("AAPL", "buy", 10, 100.0, "Technology", "")
        verdict = self.enforcer.check_all(
            order, self.equity, {}, {},
            self.equity, self.equity
        )
        self.assertFalse(verdict.approved)
        self.assertIn("#8", verdict.reason)

    # ------------------------------------------------------------------
    # 5. No chasing (stocks up >5% today)
    # ------------------------------------------------------------------
    def test_chasing_hot_stock_rejected(self):
        """Buying a stock up >5% today should be rejected."""
        order = self._make_order("TSLA")
        verdict = self.enforcer.check_all(
            order, self.equity, {}, {},
            self.equity, self.equity,
            todays_return_pct={"TSLA": 0.08},  # up 8%
        )
        self.assertFalse(verdict.approved)
        self.assertIn("ANTI-PATTERN #4", verdict.reason)

    # ------------------------------------------------------------------
    # 6. Sells always allowed (bypass anti-patterns)
    # ------------------------------------------------------------------
    def test_sells_bypass_anti_patterns(self):
        """Sell orders should always be allowed regardless of anti-patterns."""
        order = OrderRequest("AAPL", "sell", 100, 100.0, "Technology", "momentum")
        verdict = self.enforcer.check_all(
            order, self.equity, {}, {},
            self.equity, self.equity,
            current_vix=50.0,  # extreme VIX
        )
        self.assertTrue(verdict.approved)

    # ------------------------------------------------------------------
    # 7. No intraday
    # ------------------------------------------------------------------
    def test_same_day_re_entry_rejected(self):
        """Buying back a stock sold today = day trading = rejected."""
        # Record a sell of AAPL today
        conn = self.db._conn()
        conn.execute(
            "INSERT INTO trades (symbol, side, quantity, entry_time, entry_price, "
            "exit_time, exit_price, stop_loss_price, signal_type, exit_reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("AAPL", "sell", 100, datetime.utcnow().isoformat(), 150.0,
             datetime.utcnow().isoformat(), 148.0, 147.0, "momentum", "stop_loss")
        )
        conn.commit()

        order = self._make_order("AAPL")
        verdict = self.enforcer.check_all(
            order, self.equity, {}, {},
            self.equity, self.equity
        )
        self.assertFalse(verdict.approved)
        self.assertIn("ANTI-PATTERN #2", verdict.reason)


if __name__ == "__main__":
    unittest.main()
