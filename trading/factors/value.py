"""Value Factor (25% weight).

Composite of PE, PB, EV/EBITDA, and free cash flow yield.
Lower valuation = higher score (value investing).
"""

import pandas as pd


class ValueFactor:
    """Score stocks by composite valuation metrics."""

    def score(self, fundamentals: dict[str, dict]) -> dict[str, float]:
        """Calculate value score for each symbol.

        Args:
            fundamentals: {symbol: {
                "pe_ratio": float,
                "pb_ratio": float,
                "ev_ebitda": float,
                "fcf_yield": float,  # free cash flow / market cap
            }}

        Returns:
            {symbol: z-score} where higher = cheaper (better value)
        """
        records = []

        for symbol, data in fundamentals.items():
            pe = data.get("pe_ratio")
            pb = data.get("pb_ratio")
            ev_ebitda = data.get("ev_ebitda")
            fcf_yield = data.get("fcf_yield")

            # Skip if missing critical data
            if pe is None and pb is None:
                continue
            # Filter out negative earnings (unprofitable)
            if pe is not None and pe <= 0:
                continue

            records.append({
                "symbol": symbol,
                "pe_rank": pe if pe and pe > 0 else None,
                "pb_rank": pb if pb and pb > 0 else None,
                "ev_ebitda_rank": ev_ebitda if ev_ebitda and ev_ebitda > 0 else None,
                "fcf_yield": fcf_yield if fcf_yield else None,
            })

        if not records:
            return {}

        df = pd.DataFrame(records).set_index("symbol")

        # For PE, PB, EV/EBITDA: lower is better → rank ascending, then invert
        # For FCF yield: higher is better → rank descending
        rank_cols = []

        if df["pe_rank"].notna().sum() > 0:
            df["pe_score"] = df["pe_rank"].rank(ascending=True, pct=True)
            df["pe_score"] = 1.0 - df["pe_score"]  # invert: low PE = high score
            rank_cols.append("pe_score")

        if df["pb_rank"].notna().sum() > 0:
            df["pb_score"] = df["pb_rank"].rank(ascending=True, pct=True)
            df["pb_score"] = 1.0 - df["pb_score"]
            rank_cols.append("pb_score")

        if df["ev_ebitda_rank"].notna().sum() > 0:
            df["ev_score"] = df["ev_ebitda_rank"].rank(ascending=True, pct=True)
            df["ev_score"] = 1.0 - df["ev_score"]
            rank_cols.append("ev_score")

        if df["fcf_yield"].notna().sum() > 0:
            df["fcf_score"] = df["fcf_yield"].rank(ascending=False, pct=True)
            rank_cols.append("fcf_score")

        if not rank_cols:
            return {}

        # Equal-weight average of available sub-scores
        df["composite"] = df[rank_cols].mean(axis=1)

        # Convert to z-scores
        mean = df["composite"].mean()
        std = df["composite"].std()
        if std > 0:
            df["z_score"] = (df["composite"] - mean) / std
        else:
            df["z_score"] = 0.0

        return df["z_score"].to_dict()
