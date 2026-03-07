"""Layer 6: Anti-Pattern Hard Constraints.

These 10 rules are coded as immutable checks.  Every order passes through
AntiPatternEnforcer.check_all() before reaching the broker.  The system
gives humans zero opportunity to make these known-losing mistakes.
"""

from datetime import datetime, timedelta
from typing import Optional

from trading.config import (
    USE_LEVERAGE,
    MAX_NEW_POSITIONS_PER_WEEK,
    VIX_THRESHOLD,
    ESTIMATED_TRANSACTION_COST_PCT,
)
from trading.risk_engine import OrderRequest, RiskVerdict, RiskEngine
from trading.frequency_guard import FrequencyGuard
from trading.db import TradingDatabase


class AntiPatternEnforcer:
    """10 hard-coded anti-pattern rules.  No exceptions, no overrides."""

    def __init__(self, db: TradingDatabase, risk_engine: RiskEngine,
                 freq_guard: FrequencyGuard):
        self.db = db
        self.risk_engine = risk_engine
        self.freq_guard = freq_guard

    def check_all(
        self,
        order: OrderRequest,
        total_equity: float,
        current_positions: dict,
        industry_exposure: dict,
        peak_equity: float,
        week_start_equity: float,
        current_vix: float = 0.0,
        todays_return_pct: Optional[dict] = None,
    ) -> RiskVerdict:
        """Run all 10 anti-pattern checks.  Returns first failure or approval."""

        if order.side == "sell":
            # Sells are always allowed — we want to be able to cut losses
            return RiskVerdict(True, "Sell orders bypass anti-pattern checks")

        checks = [
            self._no_leverage,
            lambda: self._no_intraday(order),
            lambda: self._no_chasing(order, todays_return_pct or {}),
            lambda: self._no_averaging_down(order, current_positions),
            lambda: self._no_overtrading(),
            lambda: self._transaction_cost_check(order, total_equity),
            lambda: self._no_signal_no_trade(order),
            lambda: self._no_high_vix(current_vix),
            lambda: self._risk_engine_gate(
                order, total_equity, current_positions, industry_exposure,
                peak_equity, week_start_equity
            ),
        ]

        for check in checks:
            verdict = check()
            if not verdict.approved:
                return verdict

        return RiskVerdict(True, "All anti-pattern checks passed")

    # ------------------------------------------------------------------
    # The 10 rules (rule 3 = "no manual stop-loss override" is enforced
    # architecturally — there simply is no API for it)
    # ------------------------------------------------------------------

    def _no_leverage(self) -> RiskVerdict:
        """Rule 1: No leverage.  Ever."""
        if USE_LEVERAGE:
            return RiskVerdict(False, "ANTI-PATTERN #1: Leverage is forbidden")
        return RiskVerdict(True)

    def _no_intraday(self, order: OrderRequest) -> RiskVerdict:
        """Rule 2: No intraday / day-trading.  No same-day round trips."""
        today = datetime.utcnow().date().isoformat()
        trades_today = self.db.get_trades_since(today)

        # Check if we already sold this symbol today (buying it back = day trade)
        sold_today = {t["symbol"] for t in trades_today
                      if t["side"] == "sell" and t["symbol"] == order.symbol}
        if order.symbol in sold_today:
            return RiskVerdict(
                False,
                f"ANTI-PATTERN #2: {order.symbol} was sold today — "
                f"no same-day re-entry (day trading)"
            )
        return RiskVerdict(True)

    def _no_chasing(self, order: OrderRequest,
                    todays_return_pct: dict) -> RiskVerdict:
        """Rule 4: No chasing — reject buys on stocks up >5% today."""
        ret = todays_return_pct.get(order.symbol, 0.0)
        if ret > 0.05:
            return RiskVerdict(
                False,
                f"ANTI-PATTERN #4: {order.symbol} is up {ret:.1%} today — "
                f"do not chase momentum"
            )
        return RiskVerdict(True)

    def _no_averaging_down(self, order: OrderRequest,
                           current_positions: dict) -> RiskVerdict:
        """Rule 5: No averaging down on losing positions."""
        if order.symbol not in current_positions:
            return RiskVerdict(True)

        # Check if any open trade for this symbol is underwater
        open_trades = self.db.get_open_trades()
        for trade in open_trades:
            if (trade["symbol"] == order.symbol and
                    trade["entry_price"] and
                    order.price < trade["entry_price"]):
                return RiskVerdict(
                    False,
                    f"ANTI-PATTERN #5: {order.symbol} is below entry "
                    f"(${trade['entry_price']:.2f} → ${order.price:.2f}) — "
                    f"no averaging down on losers"
                )
        return RiskVerdict(True)

    def _no_overtrading(self) -> RiskVerdict:
        """Rule 6: No overtrading — enforced by FrequencyGuard."""
        ok, reason = self.freq_guard.can_open_position()
        if not ok:
            return RiskVerdict(False, f"ANTI-PATTERN #6: {reason}")
        return RiskVerdict(True)

    def _transaction_cost_check(self, order: OrderRequest,
                                total_equity: float) -> RiskVerdict:
        """Rule 7: Transaction cost awareness — reject tiny trades where
        costs dominate expected returns."""
        order_value = order.quantity * order.price
        est_cost = order_value * ESTIMATED_TRANSACTION_COST_PCT
        # Reject if order is so small that cost > 1% of order value
        if order_value > 0 and est_cost / order_value > 0.01:
            return RiskVerdict(
                False,
                f"ANTI-PATTERN #7: Order too small (${order_value:.0f}), "
                f"transaction costs would dominate"
            )
        return RiskVerdict(True)

    def _no_signal_no_trade(self, order: OrderRequest) -> RiskVerdict:
        """Rule 8: No orders without signal justification."""
        if not order.signal_type or order.signal_type.lower() in ("manual", "none", ""):
            return RiskVerdict(
                False,
                "ANTI-PATTERN #8: No signal justification — manual entries forbidden"
            )
        return RiskVerdict(True)

    def _no_high_vix(self, current_vix: float) -> RiskVerdict:
        """Rule 9: No new positions when VIX > threshold."""
        if current_vix > VIX_THRESHOLD:
            return RiskVerdict(
                False,
                f"ANTI-PATTERN #9: VIX at {current_vix:.1f} > {VIX_THRESHOLD} — "
                f"no new positions in high volatility"
            )
        return RiskVerdict(True)

    def _risk_engine_gate(
        self, order: OrderRequest,
        total_equity: float, current_positions: dict,
        industry_exposure: dict, peak_equity: float,
        week_start_equity: float
    ) -> RiskVerdict:
        """Rule 10: Must pass all RiskEngine checks."""
        verdict = self.risk_engine.validate_order(
            order, total_equity, current_positions, industry_exposure,
            peak_equity, week_start_equity
        )
        if not verdict.approved:
            return RiskVerdict(False, f"ANTI-PATTERN #10: {verdict.reason}")
        return verdict
