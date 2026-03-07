"""Quality Factor (20% weight).

ROE, debt-to-equity, earnings stability, and cash flow quality.
High-quality companies = higher score.
"""

import pandas as pd


class QualityFactor:
    """Score stocks by fundamental quality metrics."""

    def score(self, fundamentals: dict[str, dict]) -> dict[str, float]:
        """Calculate quality score for each symbol.

        Args:
            fundamentals: {symbol: {
                "roe": float,                    # return on equity
                "debt_to_equity": float,         # total debt / equity
                "earnings_stability": float,     # 1 / std(EPS growth), higher = more stable
                "ocf_to_assets": float,          # operating cash flow / total assets
            }}

        Returns:
            {symbol: z-score} where higher = better quality
        """
        records = []

        for symbol, data in fundamentals.items():
            roe = data.get("roe")
            dte = data.get("debt_to_equity")
            stability = data.get("earnings_stability")
            ocf = data.get("ocf_to_assets")

            if roe is None:
                continue

            records.append({
                "symbol": symbol,
                "roe": roe,
                "debt_to_equity": dte,
                "earnings_stability": stability,
                "ocf_to_assets": ocf,
            })

        if not records:
            return {}

        df = pd.DataFrame(records).set_index("symbol")
        rank_cols = []

        # ROE: higher is better
        if df["roe"].notna().sum() > 0:
            df["roe_score"] = df["roe"].rank(ascending=True, pct=True)
            rank_cols.append("roe_score")

        # Debt-to-equity: lower is better
        if df["debt_to_equity"].notna().sum() > 0:
            df["dte_score"] = df["debt_to_equity"].rank(ascending=True, pct=True)
            df["dte_score"] = 1.0 - df["dte_score"]
            rank_cols.append("dte_score")

        # Earnings stability: higher is better
        if df["earnings_stability"].notna().sum() > 0:
            df["stab_score"] = df["earnings_stability"].rank(ascending=True, pct=True)
            rank_cols.append("stab_score")

        # Cash flow to assets: higher is better
        if df["ocf_to_assets"].notna().sum() > 0:
            df["ocf_score"] = df["ocf_to_assets"].rank(ascending=True, pct=True)
            rank_cols.append("ocf_score")

        if not rank_cols:
            return {}

        df["composite"] = df[rank_cols].mean(axis=1)

        mean = df["composite"].mean()
        std = df["composite"].std()
        if std > 0:
            df["z_score"] = (df["composite"] - mean) / std
        else:
            df["z_score"] = 0.0

        return df["z_score"].to_dict()
