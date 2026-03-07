"""Unit tests for Layer 3: Factor Modules."""

import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from trading.factors.momentum import MomentumFactor
from trading.factors.value import ValueFactor
from trading.factors.quality import QualityFactor
from trading.factors.sentiment import SentimentFactor
from trading.factors.macro import MacroFactor
from trading.config import (
    FACTOR_WEIGHT_MOMENTUM,
    FACTOR_WEIGHT_VALUE,
    FACTOR_WEIGHT_QUALITY,
    FACTOR_WEIGHT_SENTIMENT,
    FACTOR_WEIGHT_MACRO,
    VIX_THRESHOLD,
)


class TestFactorWeights(unittest.TestCase):
    """Verify factor weights sum to 1.0."""

    def test_weights_sum_to_one(self):
        total = (FACTOR_WEIGHT_MOMENTUM + FACTOR_WEIGHT_VALUE +
                 FACTOR_WEIGHT_QUALITY + FACTOR_WEIGHT_SENTIMENT +
                 FACTOR_WEIGHT_MACRO)
        self.assertAlmostEqual(total, 1.0, places=5,
                               msg=f"Factor weights sum to {total}, expected 1.0")


class TestMomentumFactor(unittest.TestCase):

    def setUp(self):
        self.factor = MomentumFactor()

    def _make_price_series(self, start_price, end_price, days=300):
        """Create a simple linear price series."""
        dates = pd.date_range(end=datetime.now(), periods=days, freq="B")
        prices = np.linspace(start_price, end_price, len(dates))
        return pd.DataFrame({"close": prices}, index=dates)

    def test_high_momentum_scores_higher(self):
        """Stock that doubled should score higher than one that's flat."""
        data = {
            "WINNER": self._make_price_series(50, 100),   # +100%
            "FLAT": self._make_price_series(100, 100),     # 0%
            "LOSER": self._make_price_series(100, 50),     # -50%
        }
        scores = self.factor.score(data)
        self.assertGreater(scores.get("WINNER", 0), scores.get("FLAT", 0))
        self.assertGreater(scores.get("FLAT", 0), scores.get("LOSER", 0))

    def test_empty_data_returns_empty(self):
        """Empty input should return empty dict."""
        scores = self.factor.score({})
        self.assertEqual(scores, {})

    def test_insufficient_data_skipped(self):
        """Stocks with <252 days of data should be skipped."""
        dates = pd.date_range(end=datetime.now(), periods=100, freq="B")
        short_data = {"SHORT": pd.DataFrame({"close": np.ones(len(dates))}, index=dates)}
        scores = self.factor.score(short_data)
        self.assertNotIn("SHORT", scores)


class TestValueFactor(unittest.TestCase):

    def setUp(self):
        self.factor = ValueFactor()

    def test_cheaper_stock_scores_higher(self):
        """Low PE/PB stock should score higher than expensive one."""
        fundamentals = {
            "CHEAP": {"pe_ratio": 10, "pb_ratio": 1.5, "ev_ebitda": 8, "fcf_yield": 0.08},
            "EXPENSIVE": {"pe_ratio": 50, "pb_ratio": 10, "ev_ebitda": 30, "fcf_yield": 0.01},
        }
        scores = self.factor.score(fundamentals)
        self.assertGreater(scores["CHEAP"], scores["EXPENSIVE"])

    def test_negative_pe_skipped(self):
        """Negative PE (unprofitable) should be filtered out."""
        fundamentals = {
            "LOSING": {"pe_ratio": -5, "pb_ratio": 2, "ev_ebitda": None, "fcf_yield": None},
        }
        scores = self.factor.score(fundamentals)
        self.assertNotIn("LOSING", scores)

    def test_missing_data_handled(self):
        """Stocks missing all key metrics should be skipped."""
        fundamentals = {
            "NODATA": {"pe_ratio": None, "pb_ratio": None, "ev_ebitda": None, "fcf_yield": None},
        }
        scores = self.factor.score(fundamentals)
        self.assertNotIn("NODATA", scores)


class TestQualityFactor(unittest.TestCase):

    def setUp(self):
        self.factor = QualityFactor()

    def test_high_quality_scores_higher(self):
        """High ROE, low debt should score higher."""
        fundamentals = {
            "GOOD": {"roe": 0.25, "debt_to_equity": 0.3, "earnings_stability": 5.0, "ocf_to_assets": 0.15},
            "OK1": {"roe": 0.18, "debt_to_equity": 0.8, "earnings_stability": 3.5, "ocf_to_assets": 0.10},
            "OK2": {"roe": 0.12, "debt_to_equity": 1.5, "earnings_stability": 2.0, "ocf_to_assets": 0.07},
            "POOR": {"roe": 0.08, "debt_to_equity": 2.2, "earnings_stability": 1.0, "ocf_to_assets": 0.04},
            "BAD": {"roe": 0.05, "debt_to_equity": 3.0, "earnings_stability": 0.5, "ocf_to_assets": 0.02},
        }
        scores = self.factor.score(fundamentals)
        self.assertGreater(scores["GOOD"], scores["BAD"])


class TestMacroFactor(unittest.TestCase):

    def setUp(self):
        self.factor = MacroFactor()

    def test_low_vix_full_allocation(self):
        """VIX < 20 should give ~1.0 allocation."""
        score = self.factor.score({
            "vix": 15, "yield_10y": 4.0, "yield_2y": 3.5, "credit_spread": 100
        })
        self.assertGreaterEqual(score, 0.8)

    def test_high_vix_low_allocation(self):
        """VIX >= 35 with stressed macro should give low allocation."""
        score = self.factor.score({
            "vix": 40, "yield_10y": 3.5, "yield_2y": 4.5, "credit_spread": 500
        })
        self.assertLessEqual(score, 0.3)

    def test_inverted_yield_curve_reduces_allocation(self):
        """Inverted yield curve should reduce allocation."""
        normal = self.factor.score({
            "vix": 18, "yield_10y": 4.5, "yield_2y": 3.5, "credit_spread": 100
        })
        inverted = self.factor.score({
            "vix": 18, "yield_10y": 3.5, "yield_2y": 4.5, "credit_spread": 100
        })
        self.assertGreater(normal, inverted)

    def test_output_clamped_0_to_1(self):
        """Output must always be between 0 and 1."""
        for vix in [5, 15, 25, 35, 50, 80]:
            score = self.factor.score({
                "vix": vix, "yield_10y": 4.0, "yield_2y": 3.5, "credit_spread": 100
            })
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 1.0)


class TestSentimentFactor(unittest.TestCase):

    def setUp(self):
        self.factor = SentimentFactor()

    def test_empty_news_returns_empty(self):
        """No news data should return empty scores."""
        scores = self.factor.score({})
        self.assertEqual(scores, {})

    def test_empty_text_list_skipped(self):
        """Symbol with empty text list should be skipped."""
        scores = self.factor.score({"AAPL": []})
        self.assertNotIn("AAPL", scores)

    def test_fallback_when_api_unavailable(self):
        """When Claude API is unavailable, should return None (no crash)."""
        # With no API key set, the API call should fail gracefully
        result = self.factor._analyze_sentiment("AAPL", ["Some news text"])
        # Should be None (API not configured) — but should NOT raise an exception
        # This is the fallback behavior we're testing
        self.assertTrue(result is None or isinstance(result, float))


if __name__ == "__main__":
    unittest.main()
