"""Alpaca API wrapper — all market interactions go through this module.

Paper trading is the default.  Every order passes through the risk engine
and anti-pattern enforcer before submission.
"""

import os
from datetime import datetime, timedelta
from typing import Optional

from trading.config import ALPACA_PAPER, VIX_THRESHOLD
from trading.risk_engine import RiskEngine, OrderRequest, RiskVerdict
from trading.anti_patterns import AntiPatternEnforcer
from trading.frequency_guard import FrequencyGuard
from trading.db import TradingDatabase


class AlpacaBroker:
    """Wrapper around Alpaca API with built-in risk gating."""

    def __init__(self, db: TradingDatabase, risk_engine: RiskEngine,
                 freq_guard: FrequencyGuard, enforcer: AntiPatternEnforcer,
                 notification_manager=None):
        self.db = db
        self.risk_engine = risk_engine
        self.freq_guard = freq_guard
        self.enforcer = enforcer
        self.notifications = notification_manager
        self._client = None
        self._data_client = None

    def _get_client(self):
        """Lazy-initialize the Alpaca trading client."""
        if self._client is None:
            from alpaca.trading.client import TradingClient
            api_key = os.environ.get("ALPACA_API_KEY", "")
            secret_key = os.environ.get("ALPACA_SECRET_KEY", "")
            self._client = TradingClient(
                api_key, secret_key, paper=ALPACA_PAPER
            )
        return self._client

    def _get_data_client(self):
        """Lazy-initialize the Alpaca data client."""
        if self._data_client is None:
            from alpaca.data.historical import StockHistoricalDataClient
            api_key = os.environ.get("ALPACA_API_KEY", "")
            secret_key = os.environ.get("ALPACA_SECRET_KEY", "")
            self._data_client = StockHistoricalDataClient(api_key, secret_key)
        return self._data_client

    # ------------------------------------------------------------------
    # Account & Positions
    # ------------------------------------------------------------------

    def get_account(self) -> dict:
        """Get account info: equity, cash, buying power."""
        client = self._get_client()
        acct = client.get_account()
        return {
            "equity": float(acct.equity),
            "cash": float(acct.cash),
            "buying_power": float(acct.buying_power),
            "portfolio_value": float(acct.portfolio_value),
        }

    def get_positions(self) -> list[dict]:
        """Get all current positions."""
        client = self._get_client()
        positions = client.get_all_positions()
        return [
            {
                "symbol": p.symbol,
                "quantity": float(p.qty),
                "market_value": float(p.market_value),
                "avg_entry_price": float(p.avg_entry_price),
                "current_price": float(p.current_price),
                "unrealized_pnl": float(p.unrealized_pl),
                "unrealized_pnl_pct": float(p.unrealized_plpc),
            }
            for p in positions
        ]

    def get_position_map(self) -> dict[str, float]:
        """Return {symbol: market_value} for risk engine."""
        return {p["symbol"]: p["market_value"] for p in self.get_positions()}

    # ------------------------------------------------------------------
    # Market Data
    # ------------------------------------------------------------------

    def get_bars(self, symbols: list[str], timeframe: str = "1Day",
                 days: int = 365) -> dict:
        """Fetch historical bars.  Returns dict keyed by symbol."""
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        tf_map = {"1Day": TimeFrame.Day, "1Week": TimeFrame.Week}
        tf = tf_map.get(timeframe, TimeFrame.Day)

        client = self._get_data_client()
        request = StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=tf,
            start=datetime.utcnow() - timedelta(days=days),
        )
        bars = client.get_stock_bars(request)
        return bars.data

    def get_latest_quote(self, symbol: str) -> Optional[float]:
        """Get latest trade price for a symbol."""
        from alpaca.data.requests import StockLatestTradeRequest

        client = self._get_data_client()
        request = StockLatestTradeRequest(symbol_or_symbols=[symbol])
        trades = client.get_stock_latest_trade(request)
        if symbol in trades:
            return float(trades[symbol].price)
        return None

    def get_vix(self) -> float:
        """Get current VIX level.  Falls back to yfinance if Alpaca doesn't have it."""
        try:
            import yfinance as yf
            vix = yf.Ticker("^VIX")
            hist = vix.history(period="1d")
            if not hist.empty:
                return float(hist["Close"].iloc[-1])
        except Exception:
            pass
        return 0.0  # default to 0 (permissive) if unavailable

    # ------------------------------------------------------------------
    # Order Submission (risk-gated)
    # ------------------------------------------------------------------

    def submit_order(
        self,
        symbol: str,
        quantity: float,
        side: str,
        price: float,
        industry: str,
        signal_type: str,
        industry_exposure: dict,
        peak_equity: float,
        week_start_equity: float,
    ) -> dict:
        """Submit an order after passing all risk and anti-pattern checks.

        Returns dict with 'success', 'order_id' or 'reason'.
        """
        order_req = OrderRequest(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            industry=industry,
            signal_type=signal_type,
        )

        account = self.get_account()
        total_equity = account["equity"]
        current_positions = self.get_position_map()

        # Leverage check
        leverage_check = self.risk_engine.check_leverage(
            account["buying_power"], total_equity
        )
        if not leverage_check.approved:
            return {"success": False, "reason": leverage_check.reason}

        # Get VIX
        vix = self.get_vix()

        # Anti-pattern enforcer (includes risk engine checks)
        verdict = self.enforcer.check_all(
            order=order_req,
            total_equity=total_equity,
            current_positions=current_positions,
            industry_exposure=industry_exposure,
            peak_equity=peak_equity,
            week_start_equity=week_start_equity,
            current_vix=vix,
        )

        if not verdict.approved:
            self.db.record_risk_event(
                event_type="order_rejected",
                details=verdict.reason,
                symbol=symbol,
                equity=total_equity,
            )
            return {"success": False, "reason": verdict.reason}

        # Min hold check for sells
        if side == "sell":
            ok, reason = self.freq_guard.check_min_hold(symbol)
            if not ok:
                return {"success": False, "reason": reason}

        # Submit to Alpaca
        from alpaca.trading.requests import (
            MarketOrderRequest, StopLossRequest
        )
        from alpaca.trading.enums import OrderSide, TimeInForce

        alpaca_side = OrderSide.BUY if side == "buy" else OrderSide.SELL

        order_data = MarketOrderRequest(
            symbol=symbol,
            qty=quantity,
            side=alpaca_side,
            time_in_force=TimeInForce.DAY,
        )

        # Attach stop-loss for buy orders
        if side == "buy" and verdict.stop_loss_price:
            order_data.stop_loss = StopLossRequest(
                stop_price=verdict.stop_loss_price
            )

        try:
            client = self._get_client()
            order = client.submit_order(order_data)

            # Record in trade journal
            trade_id = self.db.record_entry(
                symbol=symbol,
                side=side,
                quantity=quantity,
                entry_price=price,
                stop_loss_price=verdict.stop_loss_price or 0.0,
                signal_type=signal_type,
            )

            # Send notification
            if self.notifications:
                self.notifications.notify_trade(
                    symbol, side, quantity, price, verdict.stop_loss_price
                )

            return {
                "success": True,
                "order_id": str(order.id),
                "trade_id": trade_id,
                "stop_loss": verdict.stop_loss_price,
            }

        except Exception as e:
            return {"success": False, "reason": f"Alpaca API error: {str(e)}"}

    def liquidate_all(self, reason: str = "drawdown"):
        """Emergency liquidation — sell everything."""
        client = self._get_client()
        client.close_all_positions(cancel_orders=True)

        account = self.get_account()
        self.db.record_risk_event(
            event_type="total_drawdown",
            details=f"Full liquidation: {reason}",
            equity=account["equity"],
        )

        if self.notifications:
            self.notifications.notify_risk_alert(
                "total_drawdown", f"Full liquidation: {reason}", account["equity"]
            )

    def reduce_to_half(self):
        """Reduce all positions by 50% — triggered by weekly drawdown."""
        positions = self.get_positions()
        for pos in positions:
            half_qty = int(float(pos["quantity"]) / 2)
            if half_qty > 0:
                from alpaca.trading.requests import MarketOrderRequest
                from alpaca.trading.enums import OrderSide, TimeInForce

                order_data = MarketOrderRequest(
                    symbol=pos["symbol"],
                    qty=half_qty,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY,
                )
                try:
                    client = self._get_client()
                    client.submit_order(order_data)
                except Exception:
                    pass  # best-effort during emergency

        account = self.get_account()
        self.db.record_risk_event(
            event_type="weekly_drawdown",
            details="Reduced all positions to 50%",
            equity=account["equity"],
        )

        if self.notifications:
            self.notifications.notify_risk_alert(
                "weekly_drawdown", "Reduced all positions to 50%", account["equity"]
            )
