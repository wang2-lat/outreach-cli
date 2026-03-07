"""Portfolio Manager — orchestrates rebalancing and emergency actions.

Bridges the signal engine with the broker, ensuring all actions go
through risk checks.
"""

from datetime import datetime
from typing import Optional

from trading.broker import AlpacaBroker
from trading.signal import SignalEngine
from trading.risk_engine import RiskEngine
from trading.db import TradingDatabase
from trading.config import WEEKLY_DRAWDOWN_LIMIT, TOTAL_DRAWDOWN_LIMIT


class PortfolioManager:
    """High-level portfolio operations: rebalance, emergency actions."""

    def __init__(self, broker: AlpacaBroker, signal_engine: SignalEngine,
                 risk_engine: RiskEngine, db: TradingDatabase):
        self.broker = broker
        self.signal = signal_engine
        self.risk = risk_engine
        self.db = db
        self._peak_equity: float = 0.0
        self._week_start_equity: float = 0.0

    def update_equity_tracking(self):
        """Update daily equity, peak, and drawdown tracking."""
        account = self.broker.get_account()
        equity = account["equity"]
        today = datetime.utcnow().strftime("%Y-%m-%d")

        if equity > self._peak_equity:
            self._peak_equity = equity

        # Reset weekly tracking on Monday
        if datetime.utcnow().weekday() == 0:
            self._week_start_equity = equity

        drawdown = (self._peak_equity - equity) / self._peak_equity if self._peak_equity > 0 else 0.0

        self.db.record_daily_equity(
            date_str=today,
            equity=equity,
            peak_equity=self._peak_equity,
            drawdown_pct=drawdown,
        )

        # Check portfolio-level stop-losses
        self._check_drawdown_triggers(equity)

        # Snapshot
        positions = self.broker.get_positions()
        industry_exp = self._estimate_industry_exposure(positions)
        self.db.save_snapshot(
            total_equity=equity,
            cash=account["cash"],
            positions=[{"symbol": p["symbol"], "value": p["market_value"]} for p in positions],
            industry_exposure=industry_exp,
        )

    def _check_drawdown_triggers(self, current_equity: float):
        """Check if drawdown circuit breakers should fire."""
        if self._peak_equity <= 0:
            return

        total_dd = (self._peak_equity - current_equity) / self._peak_equity

        if total_dd >= TOTAL_DRAWDOWN_LIMIT:
            self.broker.liquidate_all(
                reason=f"Total drawdown {total_dd:.1%} >= {TOTAL_DRAWDOWN_LIMIT:.0%}"
            )
            return

        if self._week_start_equity > 0:
            weekly_dd = (self._week_start_equity - current_equity) / self._week_start_equity
            if weekly_dd >= WEEKLY_DRAWDOWN_LIMIT:
                self.broker.reduce_to_half()

    def calculate_rebalance_orders(
        self, targets: dict[str, float]
    ) -> list[dict]:
        """Calculate orders needed to move from current to target portfolio.

        Returns list of {symbol, side, quantity, price} dicts.
        """
        positions = self.broker.get_positions()
        current = {p["symbol"]: p for p in positions}
        orders = []

        # Sells first (free up capital)
        for symbol, pos in current.items():
            if symbol not in targets:
                # Fully exit
                orders.append({
                    "symbol": symbol,
                    "side": "sell",
                    "quantity": float(pos["quantity"]),
                    "price": float(pos["current_price"]),
                })
            elif targets[symbol] < pos["market_value"] * 0.95:
                # Reduce position
                reduce_value = pos["market_value"] - targets[symbol]
                reduce_qty = int(reduce_value / pos["current_price"])
                if reduce_qty > 0:
                    orders.append({
                        "symbol": symbol,
                        "side": "sell",
                        "quantity": reduce_qty,
                        "price": float(pos["current_price"]),
                    })

        # Buys second
        for symbol, target_value in targets.items():
            current_value = current[symbol]["market_value"] if symbol in current else 0.0
            if target_value > current_value * 1.05:
                # Need to buy more
                buy_value = target_value - current_value
                price = self.broker.get_latest_quote(symbol)
                if price and price > 0:
                    qty = int(buy_value / price)
                    if qty > 0:
                        orders.append({
                            "symbol": symbol,
                            "side": "buy",
                            "quantity": qty,
                            "price": price,
                        })

        return orders

    def execute_rebalance(
        self,
        price_data: dict,
        fundamentals: dict,
        news_data: dict,
        macro_data: dict,
        industry_map: dict[str, str],
    ) -> dict:
        """Full rebalance cycle: score → decide → execute.

        Returns summary of actions taken.
        """
        account = self.broker.get_account()
        total_equity = account["equity"]
        current_positions = self.broker.get_position_map()

        # Score universe
        scores = self.signal.score_universe(
            price_data, fundamentals, news_data, macro_data
        )

        # Check if rebalance is warranted
        should, reason = self.signal.should_rebalance(
            scores, current_positions, total_equity
        )

        if not should:
            return {"action": "skip", "reason": reason}

        # Generate targets (with industry limits and quality filter)
        macro_alloc = self.signal.macro.score(macro_data)
        targets = self.signal.generate_rebalance_targets(
            scores, total_equity, macro_alloc,
            industry_map=industry_map,
        )

        # Calculate and execute orders
        orders = self.calculate_rebalance_orders(targets)
        results = []
        industry_exp = self._get_industry_exposure(industry_map)

        for order in orders:
            industry = industry_map.get(order["symbol"], "Unknown")
            result = self.broker.submit_order(
                symbol=order["symbol"],
                quantity=order["quantity"],
                side=order["side"],
                price=order["price"],
                industry=industry,
                signal_type="rebalance",
                industry_exposure=industry_exp,
                peak_equity=self._peak_equity,
                week_start_equity=self._week_start_equity,
            )
            results.append({**order, **result})

            # Update exposure after each order
            if result["success"]:
                industry_exp = self._get_industry_exposure(industry_map)

        return {
            "action": "rebalanced",
            "orders": len(orders),
            "executed": sum(1 for r in results if r.get("success")),
            "rejected": sum(1 for r in results if not r.get("success")),
            "details": results,
        }

    def _get_industry_exposure(self, industry_map: dict[str, str]) -> dict[str, float]:
        """Calculate current industry exposure from positions."""
        positions = self.broker.get_positions()
        exposure = {}
        for pos in positions:
            industry = industry_map.get(pos["symbol"], "Unknown")
            exposure[industry] = exposure.get(industry, 0.0) + pos["market_value"]
        return exposure

    def _estimate_industry_exposure(self, positions: list[dict]) -> dict[str, float]:
        """Simplified industry exposure estimate (without industry map)."""
        # In production, this would use a proper industry classification
        return {pos["symbol"]: pos["market_value"] for pos in positions}
