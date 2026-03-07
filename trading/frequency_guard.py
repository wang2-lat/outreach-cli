"""Layer 2: Trading Frequency Controls.

Prevents overtrading — research shows active traders underperform by 6.5% annually.
"""

from datetime import datetime, timedelta
from typing import Optional

from trading.config import (
    MIN_HOLD_DAYS,
    MAX_NEW_POSITIONS_PER_WEEK,
    COOLDOWN_HOURS_AFTER_STOP_LOSS,
)
from trading.db import TradingDatabase


class FrequencyGuard:
    """Enforces holding-period minimums, weekly position limits, and cooldowns."""

    def __init__(self, db: TradingDatabase):
        self.db = db

    def can_open_position(self) -> tuple[bool, str]:
        """Check if we're allowed to open a new position this week."""
        # Check cooldown first
        ok, reason = self.check_cooldown()
        if not ok:
            return False, reason

        # Check weekly limit
        week_start = (datetime.utcnow() - timedelta(
            days=datetime.utcnow().weekday()
        )).replace(hour=0, minute=0, second=0, microsecond=0)

        trades = self.db.get_trades_since(week_start.isoformat())
        buy_count = sum(1 for t in trades if t["side"] == "buy" and t["exit_time"] is None)

        if buy_count >= MAX_NEW_POSITIONS_PER_WEEK:
            return False, (
                f"Weekly limit reached: {buy_count}/{MAX_NEW_POSITIONS_PER_WEEK} "
                f"new positions this week"
            )

        return True, "OK"

    def check_min_hold(self, symbol: str) -> tuple[bool, str]:
        """Check if a position has been held for the minimum holding period."""
        open_trades = self.db.get_open_trades()
        for trade in open_trades:
            if trade["symbol"] == symbol and trade["entry_time"]:
                entry = datetime.fromisoformat(trade["entry_time"])
                hold_days = (datetime.utcnow() - entry).days
                if hold_days < MIN_HOLD_DAYS:
                    return False, (
                        f"{symbol}: held {hold_days} days, minimum is "
                        f"{MIN_HOLD_DAYS} trading days"
                    )
        return True, "OK"

    def check_cooldown(self) -> tuple[bool, str]:
        """Check if we're in a post-stop-loss cooldown period."""
        last_sl = self.db.get_last_stop_loss_time()
        if last_sl is None:
            return True, "OK"

        last_sl_dt = datetime.fromisoformat(last_sl)
        cooldown_end = last_sl_dt + timedelta(hours=COOLDOWN_HOURS_AFTER_STOP_LOSS)

        if datetime.utcnow() < cooldown_end:
            remaining = cooldown_end - datetime.utcnow()
            hours_left = remaining.total_seconds() / 3600
            return False, (
                f"Cooldown active: {hours_left:.1f}h remaining after stop-loss. "
                f"No new positions until {cooldown_end.strftime('%Y-%m-%d %H:%M')} UTC"
            )

        return True, "OK"

    def record_stop_loss_event(self, symbol: str, equity: float):
        """Record a stop-loss event to start the cooldown timer."""
        self.db.record_risk_event(
            event_type="stop_loss",
            details=f"Stop-loss triggered for {symbol}",
            symbol=symbol,
            equity=equity,
        )
