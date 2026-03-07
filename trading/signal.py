"""Layer 3: Multi-Factor Composite Signal Engine.

Combines momentum (30%), value (25%), quality (20%), sentiment (15%),
and macro (10%) into a single composite score for each stock.
Rebalances every 2 weeks, only if improvement exceeds transaction costs.
"""

from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

from trading.config import (
    FACTOR_WEIGHT_MOMENTUM,
    FACTOR_WEIGHT_VALUE,
    FACTOR_WEIGHT_QUALITY,
    FACTOR_WEIGHT_SENTIMENT,
    FACTOR_WEIGHT_MACRO,
    MIN_POSITIONS,
    MAX_POSITIONS,
    REBALANCE_INTERVAL_DAYS,
    MIN_REBALANCE_IMPROVEMENT,
    ESTIMATED_TRANSACTION_COST_PCT,
)
from trading.factors.momentum import MomentumFactor
from trading.factors.value import ValueFactor
from trading.factors.quality import QualityFactor
from trading.factors.sentiment import SentimentFactor
from trading.factors.macro import MacroFactor
from trading.db import TradingDatabase


class SignalEngine:
    """Composite multi-factor scoring and rebalance target generation."""

    def __init__(self, db: TradingDatabase):
        self.db = db
        self.momentum = MomentumFactor()
        self.value = ValueFactor()
        self.quality = QualityFactor()
        self.sentiment = SentimentFactor(db)
        self.macro = MacroFactor()
        self._last_rebalance: Optional[datetime] = None

    def score_universe(
        self,
        price_data: dict[str, pd.DataFrame],
        fundamentals: dict[str, dict],
        news_data: dict[str, list[str]],
        macro_data: dict,
    ) -> dict[str, float]:
        """Calculate composite score for all stocks in the universe.

        Returns {symbol: composite_score} sorted descending.
        """
        # Individual factor scores
        momentum_scores = self.momentum.score(price_data)
        value_scores = self.value.score(fundamentals)
        quality_scores = self.quality.score(fundamentals)
        sentiment_scores = self.sentiment.score(news_data)
        macro_allocation = self.macro.score(macro_data)

        # Combine all symbols that have at least momentum + one other factor
        all_symbols = set(momentum_scores.keys())
        composite = {}

        for symbol in all_symbols:
            mom = momentum_scores.get(symbol, 0.0)
            val = value_scores.get(symbol, 0.0)
            qual = quality_scores.get(symbol, 0.0)
            sent = sentiment_scores.get(symbol, 0.0)

            score = (
                FACTOR_WEIGHT_MOMENTUM * mom +
                FACTOR_WEIGHT_VALUE * val +
                FACTOR_WEIGHT_QUALITY * qual +
                FACTOR_WEIGHT_SENTIMENT * sent
            )

            # Macro factor adjusts the overall score (allocation multiplier)
            score *= (FACTOR_WEIGHT_MACRO + (1.0 - FACTOR_WEIGHT_MACRO) * macro_allocation)

            composite[symbol] = round(score, 4)

            # Store in database
            today = datetime.utcnow().strftime("%Y-%m-%d")
            self.db.save_factor_scores(
                date_str=today,
                symbol=symbol,
                momentum=mom,
                value=val,
                quality=qual,
                sentiment=sent,
                macro=macro_allocation,
                composite=score,
            )

        # Sort by score descending
        return dict(sorted(composite.items(), key=lambda x: x[1], reverse=True))

    def generate_rebalance_targets(
        self, scores: dict[str, float], total_equity: float,
        macro_allocation: float = 1.0,
    ) -> dict[str, float]:
        """Generate target portfolio allocation from scores.

        Returns {symbol: target_dollar_allocation}
        """
        if not scores:
            return {}

        # Take top MIN_POSITIONS to MAX_POSITIONS stocks
        n_positions = max(MIN_POSITIONS, min(MAX_POSITIONS, len(scores)))
        top_symbols = list(scores.keys())[:n_positions]
        top_scores = {s: scores[s] for s in top_symbols}

        # Score-weighted allocation within the invested portion
        total_score = sum(max(s, 0.01) for s in top_scores.values())
        invested_equity = total_equity * macro_allocation

        targets = {}
        for symbol, score in top_scores.items():
            weight = max(score, 0.01) / total_score
            # Cap individual position at 5% (enforced by risk engine too)
            weight = min(weight, 0.05 / macro_allocation if macro_allocation > 0 else 0.05)
            targets[symbol] = round(invested_equity * weight, 2)

        return targets

    def should_rebalance(
        self,
        current_scores: dict[str, float],
        current_positions: dict[str, float],
        total_equity: float,
    ) -> tuple[bool, str]:
        """Decide whether to rebalance based on cadence and expected improvement.

        Returns (should_rebalance, reason).
        """
        # Check cadence
        if self._last_rebalance:
            days_since = (datetime.utcnow() - self._last_rebalance).days
            if days_since < REBALANCE_INTERVAL_DAYS:
                return False, f"Only {days_since} days since last rebalance (min {REBALANCE_INTERVAL_DAYS})"

        if not current_scores:
            return False, "No scores available"

        # Estimate improvement vs current portfolio
        targets = self.generate_rebalance_targets(current_scores, total_equity)
        if not targets:
            return False, "No targets generated"

        # Calculate turnover
        all_symbols = set(list(targets.keys()) + list(current_positions.keys()))
        total_turnover = 0.0
        for sym in all_symbols:
            target = targets.get(sym, 0.0)
            current = current_positions.get(sym, 0.0)
            total_turnover += abs(target - current)

        # Estimated transaction cost
        est_cost = total_turnover * ESTIMATED_TRANSACTION_COST_PCT

        # Expected score improvement (simplified)
        current_avg_score = 0.0
        if current_positions:
            held_scores = [current_scores.get(s, 0) for s in current_positions]
            current_avg_score = sum(held_scores) / len(held_scores) if held_scores else 0

        target_symbols = list(targets.keys())
        target_avg_score = sum(current_scores.get(s, 0) for s in target_symbols) / len(target_symbols)
        improvement = target_avg_score - current_avg_score

        if improvement < MIN_REBALANCE_IMPROVEMENT:
            return False, (
                f"Expected improvement ({improvement:.4f}) < minimum "
                f"({MIN_REBALANCE_IMPROVEMENT}) after costs (${est_cost:.0f})"
            )

        self._last_rebalance = datetime.utcnow()
        return True, f"Rebalancing: improvement={improvement:.4f}, turnover=${total_turnover:.0f}"
