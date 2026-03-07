"""Macro Factor (10% weight).

Adjusts overall portfolio allocation based on macro indicators:
- VIX (volatility index)
- Yield curve (10Y-2Y Treasury spread)
- Credit spreads (investment grade vs treasuries)

Output: allocation multiplier 0.0 to 1.0 (1.0 = fully invested, 0.0 = all cash)
"""

from trading.config import VIX_THRESHOLD


class MacroFactor:
    """Assess macro environment to determine overall allocation level."""

    def score(self, macro_data: dict) -> float:
        """Calculate macro allocation multiplier.

        Args:
            macro_data: {
                "vix": float,           # VIX index level
                "yield_10y": float,     # 10-year Treasury yield
                "yield_2y": float,      # 2-year Treasury yield
                "credit_spread": float, # IG credit spread (bps)
            }

        Returns:
            float in [0.0, 1.0] — portfolio allocation multiplier
        """
        vix = macro_data.get("vix", 20.0)
        yield_10y = macro_data.get("yield_10y", 4.0)
        yield_2y = macro_data.get("yield_2y", 4.0)
        credit_spread = macro_data.get("credit_spread", 100)

        # VIX scoring — higher VIX = lower allocation
        vix_score = self._score_vix(vix)

        # Yield curve — inverted curve = risk-off
        curve_spread = yield_10y - yield_2y
        curve_score = self._score_yield_curve(curve_spread)

        # Credit spread — widening = stress
        credit_score = self._score_credit_spread(credit_spread)

        # Weighted combination
        allocation = (
            0.50 * vix_score +
            0.30 * curve_score +
            0.20 * credit_score
        )

        return round(max(0.0, min(1.0, allocation)), 2)

    def _score_vix(self, vix: float) -> float:
        """VIX → allocation score."""
        if vix >= VIX_THRESHOLD:
            return 0.0   # full stop — no new positions
        if vix >= 30:
            return 0.25
        if vix >= 25:
            return 0.50
        if vix >= 20:
            return 0.75
        return 1.0  # VIX < 20 = low volatility = fully invested

    def _score_yield_curve(self, spread: float) -> float:
        """Yield curve spread (10Y-2Y) → allocation score."""
        if spread < -0.5:
            return 0.25  # deeply inverted — recession signal
        if spread < 0:
            return 0.50  # mildly inverted — caution
        if spread < 0.5:
            return 0.75  # flat — neutral
        return 1.0  # positive slope — risk-on

    def _score_credit_spread(self, spread_bps: float) -> float:
        """Credit spread (basis points) → allocation score."""
        if spread_bps > 300:
            return 0.25  # stress
        if spread_bps > 200:
            return 0.50
        if spread_bps > 150:
            return 0.75
        return 1.0  # tight spreads — calm market

    def get_macro_data(self) -> dict:
        """Fetch current macro indicators from yfinance."""
        data = {"vix": 20.0, "yield_10y": 4.0, "yield_2y": 4.0, "credit_spread": 100}

        try:
            import yfinance as yf

            # VIX
            vix = yf.Ticker("^VIX")
            hist = vix.history(period="1d")
            if not hist.empty:
                data["vix"] = float(hist["Close"].iloc[-1])

            # 10-year Treasury yield
            tnx = yf.Ticker("^TNX")
            hist = tnx.history(period="1d")
            if not hist.empty:
                data["yield_10y"] = float(hist["Close"].iloc[-1])

            # 2-year Treasury yield
            two_yr = yf.Ticker("2YY=F")
            hist = two_yr.history(period="1d")
            if not hist.empty:
                data["yield_2y"] = float(hist["Close"].iloc[-1])

            # Credit spread approximation: LQD (IG bonds) yield - treasury
            # This is simplified — in production you'd use FRED API
            lqd = yf.Ticker("LQD")
            info = lqd.info
            if "yield" in info and info["yield"]:
                ig_yield = info["yield"] * 100  # convert to percentage
                data["credit_spread"] = max(0, (ig_yield - data["yield_10y"]) * 100)

        except Exception:
            pass  # use defaults if data unavailable

        return data
