"""Momentum Factor (30% weight).

Classic Jegadeesh-Titman momentum: 12-month return skipping the most recent
month to avoid short-term reversal.  Validated across global markets since 1993.
"""

import pandas as pd
from trading.config import MOMENTUM_LOOKBACK_MONTHS, MOMENTUM_SKIP_MONTHS


class MomentumFactor:
    """Score stocks by trailing return momentum."""

    def score(self, price_data: dict[str, pd.DataFrame]) -> dict[str, float]:
        """Calculate momentum score for each symbol.

        Args:
            price_data: {symbol: DataFrame with 'close' column and DatetimeIndex}

        Returns:
            {symbol: z-score} where higher = stronger momentum
        """
        raw_scores = {}

        for symbol, df in price_data.items():
            if df is None or len(df) < 252:  # need ~1 year of daily data
                continue

            try:
                # 12-month return skipping last 1 month
                lookback_days = MOMENTUM_LOOKBACK_MONTHS * 21  # ~21 trading days/month
                skip_days = MOMENTUM_SKIP_MONTHS * 21

                if len(df) < lookback_days:
                    continue

                end_price = df["close"].iloc[-skip_days] if skip_days > 0 else df["close"].iloc[-1]
                start_price = df["close"].iloc[-lookback_days]

                if start_price > 0:
                    raw_scores[symbol] = (end_price - start_price) / start_price
            except (IndexError, KeyError):
                continue

        if not raw_scores:
            return {}

        # Convert to z-scores for cross-sectional ranking
        scores_series = pd.Series(raw_scores)
        mean = scores_series.mean()
        std = scores_series.std()

        if std > 0:
            z_scores = ((scores_series - mean) / std).to_dict()
        else:
            z_scores = {s: 0.0 for s in raw_scores}

        return z_scores
