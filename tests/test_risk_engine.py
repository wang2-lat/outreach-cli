"""Unit tests for Layer 1: Risk Engine."""

import unittest
from trading.risk_engine import RiskEngine, OrderRequest, RiskVerdict
from trading.config import (
    MAX_LOSS_PER_TRADE_PCT,
    MAX_POSITION_PCT,
    MAX_INDUSTRY_PCT,
    WEEKLY_DRAWDOWN_LIMIT,
    TOTAL_DRAWDOWN_LIMIT,
    USE_LEVERAGE,
)


class TestRiskEngine(unittest.TestCase):

    def setUp(self):
        self.engine = RiskEngine()
        self.equity = 100_000.0

    # ------------------------------------------------------------------
    # 1. Per-trade loss limit (2% iron rule)
    # ------------------------------------------------------------------
    def test_stop_loss_calculation_limits_loss_to_2pct(self):
        """Stop-loss must ensure max loss <= 2% of total equity."""
        entry_price = 100.0
        quantity = 50  # $5000 position
        stop = self.engine.calculate_stop_loss(entry_price, self.equity, quantity)
        max_loss_per_share = entry_price - stop
        total_loss = max_loss_per_share * quantity
        self.assertLessEqual(total_loss, self.equity * MAX_LOSS_PER_TRADE_PCT + 0.01)

    def test_stop_loss_never_negative(self):
        """Stop-loss should never go below $0.01."""
        stop = self.engine.calculate_stop_loss(1.0, self.equity, 1)
        self.assertGreaterEqual(stop, 0.01)

    # ------------------------------------------------------------------
    # 2. Position size limit (5% per stock)
    # ------------------------------------------------------------------
    def test_position_exceeding_5pct_rejected(self):
        """Buying >5% of equity in one stock must be rejected."""
        # 100 shares * $60 = $6000 = 6% of $100k
        order = OrderRequest("AAPL", "buy", 100, 60.0, "Technology", "momentum")
        verdict = self.engine.validate_order(
            order, self.equity, {}, {}, self.equity, self.equity
        )
        self.assertFalse(verdict.approved)
        self.assertIn("5%", verdict.reason)

    def test_position_within_5pct_approved(self):
        """Buying <=5% of equity should be approved."""
        # 20 shares * $100 = $2000 = 2% of $100k
        order = OrderRequest("AAPL", "buy", 20, 100.0, "Technology", "momentum")
        verdict = self.engine.validate_order(
            order, self.equity, {}, {}, self.equity, self.equity
        )
        self.assertTrue(verdict.approved, verdict.reason)

    def test_position_with_existing_holdings_cumulative_check(self):
        """Cumulative position (existing + new) must not exceed 5%."""
        # Already hold $4000 of AAPL, trying to add $2000 more = $6000 = 6%
        existing = {"AAPL": 4000.0}
        order = OrderRequest("AAPL", "buy", 20, 100.0, "Technology", "momentum")
        verdict = self.engine.validate_order(
            order, self.equity, existing, {}, self.equity, self.equity
        )
        self.assertFalse(verdict.approved)

    # ------------------------------------------------------------------
    # 3. Industry concentration limit (20%)
    # ------------------------------------------------------------------
    def test_industry_exceeding_20pct_rejected(self):
        """Industry exposure >20% must be rejected."""
        # Already 19% in Tech, adding 2% more = 21%
        industry_exp = {"Technology": 19_000.0}
        order = OrderRequest("MSFT", "buy", 20, 100.0, "Technology", "momentum")
        verdict = self.engine.validate_order(
            order, self.equity, {}, industry_exp, self.equity, self.equity
        )
        self.assertFalse(verdict.approved)
        self.assertIn("20%", verdict.reason)

    def test_industry_within_20pct_approved(self):
        """Industry exposure <=20% should be approved."""
        industry_exp = {"Technology": 15_000.0}
        order = OrderRequest("MSFT", "buy", 20, 100.0, "Technology", "momentum")
        verdict = self.engine.validate_order(
            order, self.equity, {}, industry_exp, self.equity, self.equity
        )
        self.assertTrue(verdict.approved, verdict.reason)

    # ------------------------------------------------------------------
    # 4. Weekly drawdown (5% → reduce to half)
    # ------------------------------------------------------------------
    def test_weekly_drawdown_5pct_blocks_new_buys(self):
        """If weekly drawdown >=5%, all new buys should be blocked."""
        week_start = 100_000.0
        current = 94_500.0  # 5.5% drop
        order = OrderRequest("AAPL", "buy", 10, 100.0, "Technology", "momentum")
        verdict = self.engine.validate_order(
            order, current, {}, {}, 100_000.0, week_start
        )
        self.assertFalse(verdict.approved)
        self.assertIn("WEEKLY DRAWDOWN", verdict.reason)

    def test_weekly_drawdown_below_5pct_allowed(self):
        """If weekly drawdown <5%, buys should be allowed."""
        week_start = 100_000.0
        current = 96_000.0  # 4% drop — under threshold
        order = OrderRequest("AAPL", "buy", 10, 100.0, "Technology", "momentum")
        verdict = self.engine.validate_order(
            order, current, {}, {}, 100_000.0, week_start
        )
        self.assertTrue(verdict.approved, verdict.reason)

    # ------------------------------------------------------------------
    # 5. Total drawdown (15% → full liquidation)
    # ------------------------------------------------------------------
    def test_total_drawdown_15pct_blocks_all_buys(self):
        """If total drawdown >=15% from peak, all buys blocked."""
        peak = 100_000.0
        current = 84_000.0  # 16% drawdown
        order = OrderRequest("AAPL", "buy", 10, 100.0, "Technology", "momentum")
        verdict = self.engine.validate_order(
            order, current, {}, {}, peak, current
        )
        self.assertFalse(verdict.approved)
        self.assertIn("TOTAL DRAWDOWN", verdict.reason)

    # ------------------------------------------------------------------
    # 6. Leverage hard prohibition
    # ------------------------------------------------------------------
    def test_leverage_config_is_always_false(self):
        """USE_LEVERAGE must always be False — this is hardcoded."""
        self.assertFalse(USE_LEVERAGE)

    def test_leverage_detected_via_buying_power(self):
        """If buying power exceeds equity, leverage is flagged."""
        verdict = self.engine.check_leverage(
            buying_power=200_000.0, equity=100_000.0
        )
        self.assertFalse(verdict.approved)
        self.assertIn("margin", verdict.reason.lower())

    def test_no_leverage_clean_account(self):
        """Clean cash account should pass leverage check."""
        verdict = self.engine.check_leverage(
            buying_power=100_000.0, equity=100_000.0
        )
        self.assertTrue(verdict.approved)

    # ------------------------------------------------------------------
    # 7. Sells always allowed (for risk reduction)
    # ------------------------------------------------------------------
    def test_sells_always_approved(self):
        """Sell orders should always pass risk checks."""
        order = OrderRequest("AAPL", "sell", 100, 100.0, "Technology", "momentum")
        verdict = self.engine.validate_order(
            order, 50_000.0, {}, {}, 100_000.0, 100_000.0
        )
        self.assertTrue(verdict.approved)

    # ------------------------------------------------------------------
    # 8. Max positions (25 cap)
    # ------------------------------------------------------------------
    def test_max_25_positions_enforced(self):
        """Cannot add a new symbol when already at 25 positions."""
        positions = {f"SYM{i}": 1000.0 for i in range(25)}
        order = OrderRequest("NEW", "buy", 10, 100.0, "Technology", "momentum")
        verdict = self.engine.validate_order(
            order, self.equity, positions, {}, self.equity, self.equity
        )
        self.assertFalse(verdict.approved)
        self.assertIn("25", verdict.reason)

    def test_adding_to_existing_symbol_at_25_allowed(self):
        """Adding to an existing position at 25 positions should work."""
        positions = {f"SYM{i}": 1000.0 for i in range(25)}
        # Adding to SYM0, which already exists
        order = OrderRequest("SYM0", "buy", 5, 100.0, "Technology", "momentum")
        verdict = self.engine.validate_order(
            order, self.equity, positions, {}, self.equity, self.equity
        )
        # Should pass the position count check (may fail on other checks)
        # The point is it shouldn't fail on "max 25 positions"
        if not verdict.approved:
            self.assertNotIn("25 positions", verdict.reason)


if __name__ == "__main__":
    unittest.main()
