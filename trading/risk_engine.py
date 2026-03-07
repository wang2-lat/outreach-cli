"""Layer 1: Risk Control Engine — the foundation of the entire system.

Every order MUST pass through RiskEngine.validate_order() before submission.
There is intentionally NO manual override interface.
"""

from dataclasses import dataclass
from typing import Optional

from trading.config import (
    MAX_LOSS_PER_TRADE_PCT,
    MAX_POSITION_PCT,
    MAX_INDUSTRY_PCT,
    MIN_POSITIONS,
    MAX_POSITIONS,
    WEEKLY_DRAWDOWN_LIMIT,
    TOTAL_DRAWDOWN_LIMIT,
    USE_LEVERAGE,
)


@dataclass
class OrderRequest:
    symbol: str
    side: str           # 'buy' or 'sell'
    quantity: float
    price: float        # estimated fill price
    industry: str       # GICS industry classification
    signal_type: str    # which factor triggered this order


@dataclass
class RiskVerdict:
    approved: bool
    reason: str = ""
    stop_loss_price: Optional[float] = None
    max_shares: Optional[int] = None


class RiskEngine:
    """Stateless risk checker — call validate_order() for every trade."""

    def validate_order(
        self,
        order: OrderRequest,
        total_equity: float,
        current_positions: dict,       # {symbol: market_value}
        industry_exposure: dict,       # {industry: market_value}
        peak_equity: float,
        week_start_equity: float,
    ) -> RiskVerdict:
        """Run all risk checks and return approve/reject with reason."""

        # 0. Leverage — absolute prohibition
        if USE_LEVERAGE:
            return RiskVerdict(False, "LEVERAGE IS DISABLED — config corrupted")

        # Only check buy-side constraints (sells are always allowed for risk reduction)
        if order.side == "sell":
            return RiskVerdict(True, "Sell orders always pass risk checks")

        # 1. Portfolio drawdown check — if breached, block ALL new buys
        drawdown_verdict = self.check_portfolio_drawdown(
            total_equity, peak_equity, week_start_equity
        )
        if drawdown_verdict:
            return RiskVerdict(False, drawdown_verdict)

        # 2. Position size limit
        order_value = order.quantity * order.price
        position_verdict = self.check_position_size(
            order.symbol, order_value, total_equity, current_positions
        )
        if not position_verdict.approved:
            return position_verdict

        # 3. Industry concentration limit
        industry_verdict = self.check_industry_exposure(
            order.industry, order_value, total_equity, industry_exposure
        )
        if not industry_verdict.approved:
            return industry_verdict

        # 4. Portfolio breadth — don't exceed MAX_POSITIONS
        unique_symbols = set(current_positions.keys())
        if order.symbol not in unique_symbols and len(unique_symbols) >= MAX_POSITIONS:
            return RiskVerdict(
                False,
                f"Already at max {MAX_POSITIONS} positions, cannot add new symbol"
            )

        # 5. Calculate mandatory stop-loss
        stop_loss = self.calculate_stop_loss(order.price, total_equity, order.quantity)

        # 6. Max shares we can buy within risk budget
        max_shares = self.max_shares_for_risk_budget(
            order.price, total_equity, current_positions.get(order.symbol, 0.0)
        )

        return RiskVerdict(
            approved=True,
            reason="All risk checks passed",
            stop_loss_price=stop_loss,
            max_shares=max_shares,
        )

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def check_position_size(
        self, symbol: str, order_value: float,
        total_equity: float, current_positions: dict
    ) -> RiskVerdict:
        """Single stock cannot exceed MAX_POSITION_PCT of equity."""
        existing = current_positions.get(symbol, 0.0)
        new_total = existing + order_value
        limit = total_equity * MAX_POSITION_PCT

        if new_total > limit:
            allowed = max(0, limit - existing)
            return RiskVerdict(
                False,
                f"{symbol}: position would be {new_total/total_equity:.1%} of equity "
                f"(limit {MAX_POSITION_PCT:.0%}). Max additional: ${allowed:,.0f}"
            )
        return RiskVerdict(True)

    def check_industry_exposure(
        self, industry: str, order_value: float,
        total_equity: float, industry_exposure: dict
    ) -> RiskVerdict:
        """Single industry cannot exceed MAX_INDUSTRY_PCT of equity."""
        existing = industry_exposure.get(industry, 0.0)
        new_total = existing + order_value
        limit = total_equity * MAX_INDUSTRY_PCT

        if new_total > limit:
            allowed = max(0, limit - existing)
            return RiskVerdict(
                False,
                f"{industry}: exposure would be {new_total/total_equity:.1%} of equity "
                f"(limit {MAX_INDUSTRY_PCT:.0%}). Max additional: ${allowed:,.0f}"
            )
        return RiskVerdict(True)

    def calculate_stop_loss(
        self, entry_price: float, total_equity: float, quantity: float
    ) -> float:
        """Calculate stop-loss price so max loss = MAX_LOSS_PER_TRADE_PCT of equity."""
        max_loss_dollars = total_equity * MAX_LOSS_PER_TRADE_PCT
        max_loss_per_share = max_loss_dollars / quantity if quantity > 0 else 0
        stop_loss_price = entry_price - max_loss_per_share
        return round(max(stop_loss_price, 0.01), 2)

    def max_shares_for_risk_budget(
        self, price: float, total_equity: float, existing_position_value: float
    ) -> int:
        """Max shares buyable within both position-size and per-trade-loss limits."""
        # Position size limit
        position_budget = (total_equity * MAX_POSITION_PCT) - existing_position_value
        shares_by_position = int(position_budget / price) if price > 0 else 0

        # Per-trade loss limit — assuming worst case of hitting stop-loss
        max_loss = total_equity * MAX_LOSS_PER_TRADE_PCT
        # If stock drops to 0 (extreme), loss = price * qty.  But with stop-loss
        # the loss per share is bounded.  Use 2x the stop-loss distance as a
        # conservative estimate for position sizing.
        risk_per_share = price * MAX_LOSS_PER_TRADE_PCT * 2
        shares_by_risk = int(max_loss / risk_per_share) if risk_per_share > 0 else 0

        return max(0, min(shares_by_position, shares_by_risk))

    def check_portfolio_drawdown(
        self, current_equity: float, peak_equity: float,
        week_start_equity: float
    ) -> Optional[str]:
        """Check drawdown levels.  Returns reason string if breached, else None."""
        if peak_equity <= 0:
            return None

        # Total drawdown from peak
        total_dd = (peak_equity - current_equity) / peak_equity
        if total_dd >= TOTAL_DRAWDOWN_LIMIT:
            return (
                f"TOTAL DRAWDOWN {total_dd:.1%} >= {TOTAL_DRAWDOWN_LIMIT:.0%} — "
                f"FULL LIQUIDATION required.  No new buys."
            )

        # Weekly drawdown
        if week_start_equity > 0:
            weekly_dd = (week_start_equity - current_equity) / week_start_equity
            if weekly_dd >= WEEKLY_DRAWDOWN_LIMIT:
                return (
                    f"WEEKLY DRAWDOWN {weekly_dd:.1%} >= {WEEKLY_DRAWDOWN_LIMIT:.0%} — "
                    f"reduce to 50% exposure.  No new buys until next week."
                )

        return None

    def check_leverage(self, buying_power: float, equity: float) -> RiskVerdict:
        """Reject if account shows signs of margin/leverage usage."""
        if equity <= 0:
            return RiskVerdict(False, "Equity is zero or negative")

        # In a cash account, buying power should not exceed equity
        if buying_power > equity * 1.01:  # 1% tolerance for rounding
            return RiskVerdict(
                False,
                f"Buying power (${buying_power:,.0f}) exceeds equity "
                f"(${equity:,.0f}) — possible margin account.  "
                f"Switch to cash account or disable margin."
            )
        return RiskVerdict(True)
