"""Step 3: Stress tests — extreme market scenarios and edge cases."""

import unittest
from datetime import datetime, timedelta

from trading.risk_engine import RiskEngine, OrderRequest
from trading.frequency_guard import FrequencyGuard
from trading.anti_patterns import AntiPatternEnforcer
from trading.db import TradingDatabase
from trading.factors.momentum import MomentumFactor
from trading.factors.macro import MacroFactor
from trading.config import (
    WEEKLY_DRAWDOWN_LIMIT,
    TOTAL_DRAWDOWN_LIMIT,
    MAX_POSITIONS,
    MIN_HOLD_DAYS,
)

import pandas as pd
import numpy as np


class TestCovidCrashScenario(unittest.TestCase):
    """Simulate March 2020-style crash: market drops 20% in one week."""

    def setUp(self):
        self.db = TradingDatabase(":memory:")
        self.risk = RiskEngine()
        self.freq = FrequencyGuard(self.db)
        self.enforcer = AntiPatternEnforcer(self.db, self.risk, self.freq)

    def test_weekly_5pct_drawdown_triggers_half_reduction(self):
        """5% weekly drawdown should trigger the reduce-to-half signal."""
        peak = 100_000
        week_start = 100_000
        current = 94_000  # 6% weekly drawdown

        result = self.risk.check_portfolio_drawdown(current, peak, week_start)
        self.assertIsNotNone(result)
        self.assertIn("WEEKLY DRAWDOWN", result)

    def test_total_15pct_drawdown_triggers_full_liquidation(self):
        """15% total drawdown should trigger full liquidation."""
        peak = 100_000
        current = 84_000  # 16% drawdown from peak

        result = self.risk.check_portfolio_drawdown(current, peak, current)
        self.assertIsNotNone(result)
        self.assertIn("TOTAL DRAWDOWN", result)

    def test_after_liquidation_no_new_buys(self):
        """After total drawdown trigger, all buy orders should be blocked."""
        peak = 100_000
        current = 83_000  # 17% drawdown

        order = OrderRequest("AAPL", "buy", 10, 100.0, "Technology", "momentum")
        verdict = self.risk.validate_order(
            order, current, {}, {}, peak, current
        )
        self.assertFalse(verdict.approved)

    def test_progressive_drawdown_escalation(self):
        """3% → OK, 5% → half, 15% → liquidate."""
        peak = 100_000

        # 3% drawdown — should still be OK
        result_3pct = self.risk.check_portfolio_drawdown(97_000, peak, 100_000)
        self.assertIsNone(result_3pct)

        # 5% weekly — should trigger half
        result_5pct = self.risk.check_portfolio_drawdown(94_500, peak, 100_000)
        self.assertIn("WEEKLY", result_5pct)

        # 15% total — should trigger full liquidation
        result_15pct = self.risk.check_portfolio_drawdown(84_000, peak, 84_000)
        self.assertIn("TOTAL DRAWDOWN", result_15pct)


class TestQuantCrashScenario(unittest.TestCase):
    """Simulate 2024 quant crash: small-cap stocks drop 30% collectively."""

    def setUp(self):
        self.db = TradingDatabase(":memory:")
        self.risk = RiskEngine()
        self.freq = FrequencyGuard(self.db)

    def test_multiple_stop_losses_trigger_cooldown(self):
        """Multiple stop-losses should activate the 24h cooldown."""
        # Record several stop-loss events
        for i in range(5):
            self.freq.record_stop_loss_event(f"SMALL{i}", 90_000 - i * 1000)

        ok, reason = self.freq.check_cooldown()
        self.assertFalse(ok)
        self.assertIn("Cooldown", reason)

    def test_system_stable_after_many_stop_losses(self):
        """System should not crash after processing many stop-loss events."""
        # Record 50 stop-loss events
        for i in range(50):
            self.freq.record_stop_loss_event(f"SYM{i}", 100_000 - i * 100)

        # System should still respond correctly
        ok, reason = self.freq.check_cooldown()
        self.assertFalse(ok)

        events = self.db.get_recent_risk_events(100)
        self.assertEqual(len(events), 50)

    def test_cooldown_does_not_stack_indefinitely(self):
        """Multiple stop-losses shouldn't create weeks of cooldown.
        Cooldown is always 24h from the LAST stop-loss, not cumulative."""
        # Record stop-loss now
        self.freq.record_stop_loss_event("SYM1", 95_000)

        # Check cooldown — should be ~24h, not more
        ok, reason = self.freq.check_cooldown()
        self.assertFalse(ok)
        self.assertIn("remaining", reason.lower())


class TestDataAnomalies(unittest.TestCase):
    """Test handling of missing/corrupted data."""

    def test_missing_prices_in_momentum(self):
        """Momentum factor should handle NaN prices gracefully."""
        factor = MomentumFactor()
        dates = pd.bdate_range(end=datetime.now(), periods=300)
        n = len(dates)
        prices = np.ones(n) * 100.0
        prices[50:60] = np.nan  # gap in the middle

        data = {"GAPPY": pd.DataFrame({"close": prices}, index=dates)}
        # Should not crash
        scores = factor.score(data)
        # May or may not include GAPPY — but should not raise

    def test_zero_price_handled(self):
        """Zero stock price should not cause division by zero."""
        engine = RiskEngine()
        # Price is 0 — should handle gracefully
        stop = engine.calculate_stop_loss(0.0, 100_000, 10)
        self.assertGreaterEqual(stop, 0.01)

    def test_negative_price_handled(self):
        """Negative price input should not crash the system."""
        engine = RiskEngine()
        stop = engine.calculate_stop_loss(-10.0, 100_000, 10)
        # Should clamp to minimum
        self.assertGreaterEqual(stop, 0.01)

    def test_zero_equity_handled(self):
        """Zero equity should not cause division by zero."""
        engine = RiskEngine()
        result = engine.check_portfolio_drawdown(0, 0, 0)
        # Should return None (no drawdown check possible with 0 peak)
        self.assertIsNone(result)

    def test_macro_factor_with_defaults(self):
        """Macro factor should work with empty/default data."""
        factor = MacroFactor()
        score = factor.score({})  # all defaults
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)


class TestBoundaryConditions(unittest.TestCase):
    """Edge case testing."""

    def setUp(self):
        self.db = TradingDatabase(":memory:")
        self.risk = RiskEngine()
        self.freq = FrequencyGuard(self.db)
        self.enforcer = AntiPatternEnforcer(self.db, self.risk, self.freq)

    def test_small_account_1000_dollars(self):
        """Position sizing should still work with only $1000."""
        equity = 1000.0
        # 2% of $1000 = $20 max loss, 5% = $50 max position
        order = OrderRequest("AAPL", "buy", 1, 45.0, "Technology", "momentum")
        verdict = self.risk.validate_order(
            order, equity, {}, {}, equity, equity
        )
        self.assertTrue(verdict.approved, verdict.reason)
        self.assertIsNotNone(verdict.stop_loss_price)

    def test_small_account_rejects_large_position(self):
        """$1000 account should reject a $60 position (>5%)."""
        equity = 1000.0
        order = OrderRequest("AAPL", "buy", 1, 60.0, "Technology", "momentum")
        verdict = self.risk.validate_order(
            order, equity, {}, {}, equity, equity
        )
        self.assertFalse(verdict.approved)

    def test_exactly_25_positions_blocks_new_symbol(self):
        """At exactly 25 positions, adding a new symbol should be blocked."""
        positions = {f"SYM{i}": 1000.0 for i in range(25)}
        order = OrderRequest("NEW_STOCK", "buy", 1, 10.0, "Technology", "momentum")
        verdict = self.risk.validate_order(
            order, 100_000, positions, {}, 100_000, 100_000
        )
        self.assertFalse(verdict.approved)
        self.assertIn("25", verdict.reason)

    def test_exactly_5_days_hold_allows_sell(self):
        """Position held exactly 5 days should be sellable."""
        entry_time = (datetime.utcnow() - timedelta(days=5)).isoformat()
        conn = self.db._conn()
        conn.execute(
            "INSERT INTO trades (symbol, side, quantity, entry_time, entry_price, "
            "stop_loss_price, signal_type) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("AAPL", "buy", 100, entry_time, 150.0, 147.0, "momentum")
        )
        conn.commit()

        ok, reason = self.freq.check_min_hold("AAPL")
        self.assertTrue(ok, f"5 days should be allowed: {reason}")

    def test_drawdown_exactly_at_5pct_triggers(self):
        """Exactly 5% weekly drawdown should trigger (>=5%, not >5%)."""
        peak = 100_000
        week_start = 100_000
        current = 95_000  # exactly 5%

        result = self.risk.check_portfolio_drawdown(current, peak, week_start)
        self.assertIsNotNone(result)
        self.assertIn("WEEKLY", result)

    def test_drawdown_exactly_at_15pct_triggers(self):
        """Exactly 15% total drawdown should trigger."""
        peak = 100_000
        current = 85_000  # exactly 15%

        result = self.risk.check_portfolio_drawdown(current, peak, current)
        self.assertIsNotNone(result)
        self.assertIn("TOTAL", result)

    def test_vix_exactly_35_not_blocked(self):
        """VIX at exactly 35 should NOT block (threshold is >35)."""
        order = OrderRequest("AAPL", "buy", 10, 100.0, "Technology", "momentum")
        verdict = self.enforcer.check_all(
            order, 100_000, {}, {},
            100_000, 100_000,
            current_vix=35.0,
        )
        # Should not be blocked by VIX rule specifically
        if not verdict.approved:
            self.assertNotIn("#9", verdict.reason)

    def test_vix_35_point_1_is_blocked(self):
        """VIX at 35.1 should be blocked."""
        order = OrderRequest("AAPL", "buy", 10, 100.0, "Technology", "momentum")
        verdict = self.enforcer.check_all(
            order, 100_000, {}, {},
            100_000, 100_000,
            current_vix=35.1,
        )
        self.assertFalse(verdict.approved)
        self.assertIn("#9", verdict.reason)


if __name__ == "__main__":
    unittest.main()
