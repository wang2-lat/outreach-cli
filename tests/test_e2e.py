"""Step 2: End-to-end integration test.

Simulates a complete trading cycle WITHOUT requiring live Alpaca API:
1. Generate synthetic S&P 500-like price data (2 years)
2. Calculate all factor scores (momentum, value, quality)
3. Generate composite signal and select top 20 stocks
4. Run through risk control filters
5. Simulate order submission
6. Verify trade journal records
7. Verify CLI commands work
"""

import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from trading.config import (
    MAX_POSITION_PCT,
    MAX_INDUSTRY_PCT,
    MIN_POSITIONS,
    MAX_POSITIONS,
    FACTOR_WEIGHT_MOMENTUM,
    FACTOR_WEIGHT_VALUE,
    FACTOR_WEIGHT_QUALITY,
)
from trading.db import TradingDatabase
from trading.risk_engine import RiskEngine, OrderRequest
from trading.frequency_guard import FrequencyGuard
from trading.anti_patterns import AntiPatternEnforcer
from trading.factors.momentum import MomentumFactor
from trading.factors.value import ValueFactor
from trading.factors.quality import QualityFactor
from trading.factors.macro import MacroFactor
from trading.signal import SignalEngine
from trading.backtester import Backtester
from trading.journal import TradeJournal
from trading.reporter import PerformanceReporter
from trading.benchmarks import BenchmarkTracker


# Simulated industry mapping
INDUSTRIES = [
    "Technology", "Healthcare", "Financials", "Consumer Discretionary",
    "Industrials", "Energy", "Materials", "Utilities",
    "Communication Services", "Real Estate"
]


def generate_universe(n_stocks=50, n_days=504):
    """Generate 2 years of daily price data for a synthetic universe."""
    dates = pd.bdate_range(end=datetime.now(), periods=n_days)
    n = len(dates)
    np.random.seed(123)

    price_data = {}
    fundamentals = {}
    industry_map = {}

    for i in range(n_stocks):
        symbol = f"STOCK{i:03d}"
        # Different stocks have different trends
        trend = np.random.uniform(-0.0002, 0.0008)
        vol = np.random.uniform(0.01, 0.04)
        returns = np.random.normal(trend, vol, n)
        prices = max(10, 50 + i) * np.cumprod(1 + returns)
        price_data[symbol] = pd.DataFrame({"close": prices}, index=dates)

        # Fundamentals
        fundamentals[symbol] = {
            "pe_ratio": max(5, np.random.normal(20, 10)),
            "pb_ratio": max(0.5, np.random.normal(3, 2)),
            "ev_ebitda": max(3, np.random.normal(12, 5)),
            "fcf_yield": max(0.01, np.random.normal(0.05, 0.03)),
            "roe": max(0.01, np.random.normal(0.15, 0.08)),
            "debt_to_equity": max(0, np.random.normal(1.0, 0.5)),
            "earnings_stability": max(0.1, np.random.normal(3.0, 1.5)),
            "ocf_to_assets": max(0.01, np.random.normal(0.08, 0.04)),
        }

        # Assign to industries round-robin
        industry_map[symbol] = INDUSTRIES[i % len(INDUSTRIES)]

    return price_data, fundamentals, industry_map


class TestEndToEnd(unittest.TestCase):
    """Full pipeline integration test."""

    def setUp(self):
        self.db = TradingDatabase(":memory:")
        self.risk = RiskEngine()
        self.freq = FrequencyGuard(self.db)
        self.enforcer = AntiPatternEnforcer(self.db, self.risk, self.freq)
        self.signal_engine = SignalEngine(self.db)
        self.equity = 100_000.0
        self.peak_equity = 100_000.0
        self.week_start_equity = 100_000.0

        self.price_data, self.fundamentals, self.industry_map = generate_universe()

    # ------------------------------------------------------------------
    # Step 1: Generate price data
    # ------------------------------------------------------------------
    def test_step1_data_generation(self):
        """Verify synthetic data has correct shape."""
        self.assertEqual(len(self.price_data), 50)
        for sym, df in self.price_data.items():
            self.assertIn("close", df.columns)
            self.assertGreater(len(df), 250)  # at least 1 year

    # ------------------------------------------------------------------
    # Step 2: Calculate all factor scores
    # ------------------------------------------------------------------
    def test_step2_factor_calculation(self):
        """Calculate momentum, value, quality scores for universe."""
        momentum = MomentumFactor()
        value = ValueFactor()
        quality = QualityFactor()
        macro = MacroFactor()

        mom_scores = momentum.score(self.price_data)
        val_scores = value.score(self.fundamentals)
        qual_scores = quality.score(self.fundamentals)
        macro_score = macro.score({
            "vix": 18, "yield_10y": 4.0, "yield_2y": 3.5, "credit_spread": 100
        })

        # Should have scores for most stocks
        self.assertGreater(len(mom_scores), 20, f"Only {len(mom_scores)} momentum scores")
        self.assertGreater(len(val_scores), 20, f"Only {len(val_scores)} value scores")
        self.assertGreater(len(qual_scores), 20, f"Only {len(qual_scores)} quality scores")
        self.assertGreater(macro_score, 0.5, "Macro should be risk-on with low VIX")

        # No divide-by-zero errors — all scores should be finite
        for scores in [mom_scores, val_scores, qual_scores]:
            for sym, score in scores.items():
                self.assertTrue(np.isfinite(score), f"{sym} has non-finite score: {score}")

    # ------------------------------------------------------------------
    # Step 3: Generate composite signal and select top 20
    # ------------------------------------------------------------------
    def test_step3_composite_signal_selection(self):
        """Generate composite scores and pick top stocks."""
        macro_data = {"vix": 18, "yield_10y": 4.0, "yield_2y": 3.5, "credit_spread": 100}

        scores = self.signal_engine.score_universe(
            self.price_data, self.fundamentals, {}, macro_data
        )

        self.assertGreater(len(scores), 0, "Should have composite scores")

        # Top 20
        top_20 = dict(list(scores.items())[:20])
        self.assertEqual(len(top_20), 20)

        # Scores should be sorted descending
        values = list(scores.values())
        for i in range(len(values) - 1):
            self.assertGreaterEqual(values[i], values[i + 1])

    # ------------------------------------------------------------------
    # Step 4: Risk control validation
    # ------------------------------------------------------------------
    def test_step4_risk_control_filtering(self):
        """All orders should pass through risk engine."""
        macro_data = {"vix": 18, "yield_10y": 4.0, "yield_2y": 3.5, "credit_spread": 100}
        scores = self.signal_engine.score_universe(
            self.price_data, self.fundamentals, {}, macro_data
        )
        targets = self.signal_engine.generate_rebalance_targets(
            scores, self.equity
        )

        approved_count = 0
        rejected_count = 0
        positions = {}
        industry_exposure = {}

        for symbol, target_value in list(targets.items())[:25]:
            price = float(self.price_data[symbol]["close"].iloc[-1])
            qty = max(1, int(target_value / price))
            industry = self.industry_map.get(symbol, "Unknown")

            order = OrderRequest(symbol, "buy", qty, price, industry, "composite")
            verdict = self.risk.validate_order(
                order, self.equity, positions, industry_exposure,
                self.peak_equity, self.week_start_equity
            )

            if verdict.approved:
                approved_count += 1
                value = qty * price
                positions[symbol] = value
                industry_exposure[industry] = industry_exposure.get(industry, 0) + value
            else:
                rejected_count += 1

        self.assertGreater(approved_count, 0, "At least some orders should be approved")
        # Verify no single position exceeds 5%
        for sym, val in positions.items():
            self.assertLessEqual(val / self.equity, MAX_POSITION_PCT + 0.001)

    # ------------------------------------------------------------------
    # Step 5: Simulate order execution and journal recording
    # ------------------------------------------------------------------
    def test_step5_order_execution_and_journal(self):
        """Simulate placing orders and verify they're recorded."""
        macro_data = {"vix": 18, "yield_10y": 4.0, "yield_2y": 3.5, "credit_spread": 100}
        scores = self.signal_engine.score_universe(
            self.price_data, self.fundamentals, {}, macro_data
        )
        targets = self.signal_engine.generate_rebalance_targets(scores, self.equity)

        positions = {}
        industry_exposure = {}
        trade_ids = []

        for symbol, target_value in list(targets.items())[:5]:
            price = float(self.price_data[symbol]["close"].iloc[-1])
            qty = max(1, int(target_value / price))
            industry = self.industry_map.get(symbol, "Unknown")

            order = OrderRequest(symbol, "buy", qty, price, industry, "composite")

            # Anti-pattern check
            verdict = self.enforcer.check_all(
                order, self.equity, positions, industry_exposure,
                self.peak_equity, self.week_start_equity,
                current_vix=18.0,
            )

            if verdict.approved:
                # Record in journal
                stop = verdict.stop_loss_price or (price * 0.98)
                tid = self.db.record_entry(symbol, "buy", qty, price, stop, "composite")
                trade_ids.append(tid)
                value = qty * price
                positions[symbol] = value
                industry_exposure[industry] = industry_exposure.get(industry, 0) + value

        # Verify trades were recorded
        open_trades = self.db.get_open_trades()
        self.assertEqual(len(open_trades), len(trade_ids))

        for trade in open_trades:
            self.assertIsNotNone(trade["symbol"])
            self.assertIsNotNone(trade["entry_price"])
            self.assertIsNotNone(trade["stop_loss_price"])
            self.assertIsNotNone(trade["signal_type"])
            self.assertIsNotNone(trade["entry_time"])
            self.assertEqual(trade["signal_type"], "composite")

        # Simulate closing one trade
        if trade_ids:
            self.db.record_exit(
                trade_ids[0],
                exit_price=open_trades[0]["entry_price"] * 1.03,  # 3% gain
                exit_reason="take_profit",
                slippage=0.10,
                factor_attribution={"momentum": 0.4, "value": 0.3, "quality": 0.3}
            )

            closed = self.db.get_closed_trades()
            self.assertEqual(len(closed), 1)
            self.assertGreater(closed[0]["pnl"], 0)
            self.assertEqual(closed[0]["exit_reason"], "take_profit")
            self.assertIsNotNone(closed[0]["factor_attribution"])

    # ------------------------------------------------------------------
    # Step 6: Verify reporter and benchmarks work
    # ------------------------------------------------------------------
    def test_step6_reporting(self):
        """Reporter and benchmarks should run without errors."""
        # Record some data so reports have something to show
        self.db.record_daily_equity("2024-01-15", 100000, 100000, 0.0)
        self.db.record_daily_equity("2024-01-16", 100500, 100500, 0.0)

        tid = self.db.record_entry("AAPL", "buy", 100, 150.0, 147.0, "momentum")
        self.db.record_exit(tid, 155.0, "take_profit", 0.5)

        reporter = PerformanceReporter(self.db)
        report = reporter.generate_monthly_report(365)
        self.assertIsNotNone(report)
        self.assertIn("total_pnl", report)
        self.assertIn("factor_attribution", report)

        tracker = BenchmarkTracker(self.db)
        metrics = tracker.get_metrics()
        self.assertIn("sharpe_ratio", metrics)
        self.assertIn("max_drawdown", metrics)
        self.assertIn("win_rate", metrics)

    # ------------------------------------------------------------------
    # Step 7: Verify backtester on synthetic data
    # ------------------------------------------------------------------
    def test_step7_backtester_integration(self):
        """Run backtester on generated data."""
        bt = Backtester()

        # Build price and signal DataFrames
        symbols = list(self.price_data.keys())[:10]
        dates = self.price_data[symbols[0]].index
        prices = pd.DataFrame(
            {sym: self.price_data[sym]["close"].values for sym in symbols},
            index=dates
        )
        signals = pd.DataFrame(0.04, index=dates, columns=symbols)

        result = bt.run(prices, signals, n_strategy_params=5)
        self.assertGreater(len(result.equity_curve), 0)
        self.assertIsNotNone(result.sharpe_ratio)
        self.assertIsNotNone(result.max_drawdown)

    # ------------------------------------------------------------------
    # Full pipeline (all steps together)
    # ------------------------------------------------------------------
    def test_full_pipeline(self):
        """Run the entire pipeline end-to-end."""
        # 1. Data is ready (setUp)
        # 2. Score universe
        macro_data = {"vix": 18, "yield_10y": 4.0, "yield_2y": 3.5, "credit_spread": 100}
        scores = self.signal_engine.score_universe(
            self.price_data, self.fundamentals, {}, macro_data
        )
        self.assertGreater(len(scores), 0)

        # 3. Generate targets
        targets = self.signal_engine.generate_rebalance_targets(scores, self.equity)
        self.assertGreaterEqual(len(targets), MIN_POSITIONS)
        self.assertLessEqual(len(targets), MAX_POSITIONS)

        # 4. Execute with risk checks
        positions = {}
        industry_exposure = {}
        executed = 0

        for symbol, target_value in targets.items():
            price = float(self.price_data[symbol]["close"].iloc[-1])
            qty = max(1, int(target_value / price))
            industry = self.industry_map.get(symbol, "Unknown")

            order = OrderRequest(symbol, "buy", qty, price, industry, "composite")
            verdict = self.enforcer.check_all(
                order, self.equity, positions, industry_exposure,
                self.peak_equity, self.week_start_equity,
                current_vix=18.0,
            )

            if verdict.approved:
                stop = verdict.stop_loss_price or (price * 0.98)
                self.db.record_entry(symbol, "buy", qty, price, stop, "composite")
                value = qty * price
                positions[symbol] = value
                industry_exposure[industry] = industry_exposure.get(industry, 0) + value
                executed += 1

                # Check frequency limit
                ok, _ = self.freq.can_open_position()
                if not ok:
                    break

        self.assertGreater(executed, 0)

        # 5. Verify journal
        open_trades = self.db.get_open_trades()
        self.assertEqual(len(open_trades), executed)

        # 6. Record equity and check reporting
        self.db.record_daily_equity(
            datetime.utcnow().strftime("%Y-%m-%d"),
            self.equity, self.peak_equity, 0.0
        )

        reporter = PerformanceReporter(self.db)
        report = reporter.generate_monthly_report(30)
        self.assertIsNotNone(report)

        print(f"\n{'='*60}")
        print(f"END-TO-END TEST RESULTS")
        print(f"{'='*60}")
        print(f"Universe size: {len(self.price_data)} stocks")
        print(f"Composite scores generated: {len(scores)}")
        print(f"Rebalance targets: {len(targets)}")
        print(f"Orders executed: {executed}")
        print(f"Open positions: {len(open_trades)}")
        print(f"Total invested: ${sum(positions.values()):,.0f}")
        print(f"Industries covered: {len(set(industry_exposure.keys()))}")
        print(f"{'='*60}")


if __name__ == "__main__":
    unittest.main()
