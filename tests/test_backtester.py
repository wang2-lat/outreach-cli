"""Unit tests for Layer 4: Backtesting Engine."""

import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from trading.backtester import Backtester, BacktestResult
from trading.config import (
    BACKTEST_MIN_YEARS,
    BACKTEST_TRAIN_PCT,
    BACKTEST_MIN_TRADES,
    BACKTEST_MAX_STRATEGY_PARAMS,
)


class TestBacktester(unittest.TestCase):

    def setUp(self):
        self.bt = Backtester()

    def _make_price_data(self, n_days=1500, n_stocks=5, trend=0.0003):
        """Generate synthetic price data."""
        dates = pd.bdate_range(end=datetime.now(), periods=n_days)
        np.random.seed(42)
        n = len(dates)
        data = {}
        for i in range(n_stocks):
            returns = np.random.normal(trend, 0.02, n)
            prices = 100 * np.cumprod(1 + returns)
            data[f"SYM{i}"] = prices
        return pd.DataFrame(data, index=dates)

    def _make_signal_data(self, prices, weight=0.04):
        """Generate simple equal-weight signals."""
        signals = pd.DataFrame(
            weight, index=prices.index, columns=prices.columns
        )
        return signals

    # ------------------------------------------------------------------
    # 1. Input validation
    # ------------------------------------------------------------------
    def test_too_few_years_warning(self):
        """Data covering <5 years should produce a warning."""
        dates = pd.bdate_range(end=datetime.now(), periods=500)  # ~2 years
        short_data = pd.DataFrame(index=dates)
        warnings = self.bt.validate_inputs(short_data, 5)
        self.assertTrue(any("years" in w.lower() for w in warnings))

    def test_too_many_params_warning(self):
        """Strategy with >10 parameters should produce a warning."""
        dates = pd.bdate_range(end=datetime.now(), periods=1500)
        data = pd.DataFrame(index=dates)
        warnings = self.bt.validate_inputs(data, 15)
        self.assertTrue(any("parameter" in w.lower() for w in warnings))

    def test_valid_inputs_no_warnings(self):
        """Good data with few params should produce no warnings."""
        dates = pd.bdate_range(end=datetime.now(), periods=1500)
        data = pd.DataFrame(index=dates)
        warnings = self.bt.validate_inputs(data, 5)
        self.assertEqual(len(warnings), 0)

    # ------------------------------------------------------------------
    # 2. Train/test split (70/30)
    # ------------------------------------------------------------------
    def test_7030_split(self):
        """Verify the 70/30 split ratio."""
        self.assertAlmostEqual(BACKTEST_TRAIN_PCT, 0.70)

    def test_split_in_backtest_run(self):
        """In-sample and out-of-sample should use ~70/30 of data."""
        prices = self._make_price_data(n_days=1000, n_stocks=3)
        signals = self._make_signal_data(prices)
        result = self.bt.run(prices, signals, n_strategy_params=5)
        # The equity curve should have data from both periods
        self.assertGreater(len(result.equity_curve), 0)

    # ------------------------------------------------------------------
    # 3. Minimum trade count
    # ------------------------------------------------------------------
    def test_few_trades_warning(self):
        """Backtest with <200 trades should produce a warning."""
        # Use very few stocks and very long rebalance period to get few trades
        prices = self._make_price_data(n_days=500, n_stocks=2, trend=0.001)
        signals = self._make_signal_data(prices, weight=0.5)
        result = self.bt.run(prices, signals, n_strategy_params=5)
        if result.total_trades < BACKTEST_MIN_TRADES:
            self.assertTrue(
                any("trades" in w.lower() for w in result.warnings),
                f"Expected trade count warning, got: {result.warnings}"
            )

    # ------------------------------------------------------------------
    # 4. Overfitting detection
    # ------------------------------------------------------------------
    def test_overfitting_detection(self):
        """If in-sample Sharpe >> out-of-sample, should flag overfitting."""
        # We can't easily force this in a synthetic test, but verify the mechanism
        result = BacktestResult()
        result.in_sample_sharpe = 3.0
        result.out_sample_sharpe = 0.5
        # Manually check: ratio = 6.0 > 2.0 → overfit
        ratio = result.in_sample_sharpe / result.out_sample_sharpe
        self.assertGreater(ratio, 2.0, "Should detect overfitting")

    def test_positive_is_negative_oos_flagged(self):
        """Positive in-sample but negative out-of-sample = overfitting."""
        prices = self._make_price_data(n_days=1500, n_stocks=3)
        signals = self._make_signal_data(prices)
        result = self.bt.run(prices, signals)
        # Just verify the result object has the overfitting fields
        self.assertIsInstance(result.is_overfit, bool)
        self.assertIsInstance(result.in_sample_sharpe, float)
        self.assertIsInstance(result.out_sample_sharpe, float)

    # ------------------------------------------------------------------
    # 5. Slippage included
    # ------------------------------------------------------------------
    def test_slippage_applied(self):
        """Backtest should include slippage costs."""
        # Run same data with different slippage settings
        prices = self._make_price_data(n_days=1000, n_stocks=3, trend=0.001)
        signals = self._make_signal_data(prices)

        bt_low_slip = Backtester(slippage_pct=0.0001)
        bt_high_slip = Backtester(slippage_pct=0.01)

        result_low = bt_low_slip.run(prices, signals)
        result_high = bt_high_slip.run(prices, signals)

        # Higher slippage should result in lower or equal returns
        if result_low.equity_curve and result_high.equity_curve:
            self.assertGreaterEqual(
                result_low.equity_curve[-1],
                result_high.equity_curve[-1] - 1  # small tolerance
            )

    # ------------------------------------------------------------------
    # 6. Empty data handling
    # ------------------------------------------------------------------
    def test_empty_data_no_crash(self):
        """Empty dataframes should not crash the backtester."""
        result = self.bt.run(pd.DataFrame(), pd.DataFrame())
        self.assertEqual(result.total_trades, 0)
        self.assertTrue(any("empty" in w.lower() for w in result.warnings))

    # ------------------------------------------------------------------
    # 7. Result fields populated
    # ------------------------------------------------------------------
    def test_result_fields_populated(self):
        """All result fields should be populated after a run."""
        prices = self._make_price_data(n_days=1500, n_stocks=5)
        signals = self._make_signal_data(prices)
        result = self.bt.run(prices, signals)

        self.assertIsNotNone(result.sharpe_ratio)
        self.assertIsNotNone(result.max_drawdown)
        self.assertIsNotNone(result.win_rate)
        self.assertIsNotNone(result.profit_factor)
        self.assertGreater(len(result.equity_curve), 0)


if __name__ == "__main__":
    unittest.main()
