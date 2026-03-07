"""Unit tests for Layer 3: Signal Engine & Portfolio Manager."""

import unittest
import pandas as pd
import numpy as np
from datetime import datetime

from trading.signal import SignalEngine
from trading.db import TradingDatabase
from trading.config import MIN_POSITIONS, MAX_POSITIONS, REBALANCE_INTERVAL_DAYS


class TestSignalEngine(unittest.TestCase):

    def setUp(self):
        self.db = TradingDatabase(":memory:")
        self.engine = SignalEngine(self.db)

    def _make_price_data(self, symbols, n_days=300):
        """Create price data with different trends."""
        dates = pd.bdate_range(end=datetime.now(), periods=n_days)
        np.random.seed(42)
        data = {}
        n = len(dates)
        for i, sym in enumerate(symbols):
            trend = 0.001 * (len(symbols) - i)  # first symbol has highest trend
            returns = np.random.normal(trend, 0.02, n)
            prices = 100 * np.cumprod(1 + returns)
            data[sym] = pd.DataFrame({"close": prices}, index=dates)
        return data

    def _make_fundamentals(self, symbols):
        """Create fundamental data."""
        data = {}
        for i, sym in enumerate(symbols):
            data[sym] = {
                "pe_ratio": 10 + i * 5,
                "pb_ratio": 1 + i * 0.5,
                "ev_ebitda": 8 + i * 3,
                "fcf_yield": 0.1 - i * 0.01,
                "roe": 0.25 - i * 0.03,
                "debt_to_equity": 0.3 + i * 0.2,
                "earnings_stability": 5.0 - i * 0.5,
                "ocf_to_assets": 0.15 - i * 0.02,
            }
        return data

    # ------------------------------------------------------------------
    # 1. Universe scoring
    # ------------------------------------------------------------------
    def test_score_universe_ranks_correctly(self):
        """Stocks should be ranked by composite score, best first."""
        symbols = [f"SYM{i}" for i in range(30)]
        prices = self._make_price_data(symbols)
        fundamentals = self._make_fundamentals(symbols)
        macro_data = {"vix": 18, "yield_10y": 4.0, "yield_2y": 3.5, "credit_spread": 100}

        scores = self.engine.score_universe(
            prices, fundamentals, {}, macro_data
        )

        # Scores should be a non-empty dict
        self.assertGreater(len(scores), 0)

        # Values should be sorted descending
        score_values = list(scores.values())
        for i in range(len(score_values) - 1):
            self.assertGreaterEqual(score_values[i], score_values[i + 1])

    def test_score_universe_empty_input(self):
        """Empty input should return empty scores."""
        scores = self.engine.score_universe({}, {}, {}, {})
        self.assertEqual(len(scores), 0)

    # ------------------------------------------------------------------
    # 2. Rebalance target generation
    # ------------------------------------------------------------------
    def test_targets_respect_position_count(self):
        """Generated targets should have between MIN and MAX positions."""
        scores = {f"SYM{i}": 1.0 - i * 0.03 for i in range(50)}
        targets = self.engine.generate_rebalance_targets(scores, 100_000.0)

        self.assertGreaterEqual(len(targets), MIN_POSITIONS)
        self.assertLessEqual(len(targets), MAX_POSITIONS)

    def test_targets_dollar_amounts_reasonable(self):
        """Each target allocation should be reasonable fraction of equity."""
        scores = {f"SYM{i}": 1.0 - i * 0.03 for i in range(30)}
        targets = self.engine.generate_rebalance_targets(scores, 100_000.0)

        total_allocated = sum(targets.values())
        self.assertGreater(total_allocated, 0)
        self.assertLessEqual(total_allocated, 100_000.0)

    # ------------------------------------------------------------------
    # 3. Rebalance decision (cost vs improvement)
    # ------------------------------------------------------------------
    def test_skip_rebalance_if_improvement_too_small(self):
        """Should skip rebalance if expected improvement < transaction costs."""
        # Current portfolio scores similar to target
        scores = {f"SYM{i}": 0.5 for i in range(20)}
        positions = {f"SYM{i}": 5000.0 for i in range(20)}

        should, reason = self.engine.should_rebalance(
            scores, positions, 100_000.0
        )
        # With identical scores, improvement should be near zero
        self.assertFalse(should, f"Should skip rebalance: {reason}")

    def test_rebalance_when_significant_improvement(self):
        """Should rebalance when there's meaningful improvement potential."""
        # Current holds are all low-score stocks
        scores = {f"SYM{i}": 2.0 - i * 0.1 for i in range(30)}
        positions = {f"SYM{i+20}": 5000.0 for i in range(15)}  # hold worst 15

        # Force last rebalance to be old enough
        self.engine._last_rebalance = None

        should, reason = self.engine.should_rebalance(
            scores, positions, 100_000.0
        )
        self.assertTrue(should, f"Should rebalance: {reason}")

    def test_rebalance_cadence_enforced(self):
        """Should not rebalance within the interval period."""
        from datetime import datetime
        self.engine._last_rebalance = datetime.utcnow()  # just rebalanced

        scores = {f"SYM{i}": 2.0 - i * 0.1 for i in range(30)}
        positions = {f"SYM{i+20}": 5000.0 for i in range(15)}

        should, reason = self.engine.should_rebalance(
            scores, positions, 100_000.0
        )
        self.assertFalse(should)
        self.assertIn("days", reason.lower())


if __name__ == "__main__":
    unittest.main()
