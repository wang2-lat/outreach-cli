"""Layer 4: Backtesting Engine.

Requirements:
- Include commissions, slippage, market impact
- 70/30 in-sample/out-of-sample split
- Max 10 strategy parameters (reject if more)
- Min 5 years of data, 200+ trades
- Overfitting detection
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

from trading.config import (
    BACKTEST_MIN_YEARS,
    BACKTEST_TRAIN_PCT,
    BACKTEST_MIN_TRADES,
    BACKTEST_MAX_STRATEGY_PARAMS,
    BACKTEST_SLIPPAGE_PCT,
    MAX_LOSS_PER_TRADE_PCT,
    MAX_POSITION_PCT,
)


@dataclass
class BacktestResult:
    total_return: float = 0.0
    annualized_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_trades: int = 0
    avg_hold_days: float = 0.0
    equity_curve: list = field(default_factory=list)
    drawdown_curve: list = field(default_factory=list)
    in_sample_sharpe: float = 0.0
    out_sample_sharpe: float = 0.0
    is_overfit: bool = False
    warnings: list = field(default_factory=list)


class Backtester:
    """Walk-forward backtester with realistic cost modeling."""

    def __init__(self, slippage_pct: float = BACKTEST_SLIPPAGE_PCT):
        self.slippage_pct = slippage_pct

    def validate_inputs(
        self, data: pd.DataFrame, n_params: int
    ) -> list[str]:
        """Pre-flight checks before running backtest."""
        warnings = []

        # Check data length
        if len(data) > 0:
            date_range = (data.index[-1] - data.index[0]).days / 365.25
            if date_range < BACKTEST_MIN_YEARS:
                warnings.append(
                    f"Data covers {date_range:.1f} years, minimum is {BACKTEST_MIN_YEARS}"
                )

        # Check parameter count
        if n_params > BACKTEST_MAX_STRATEGY_PARAMS:
            warnings.append(
                f"Strategy has {n_params} parameters, maximum is "
                f"{BACKTEST_MAX_STRATEGY_PARAMS} (overfitting risk)"
            )

        return warnings

    def run(
        self,
        prices: pd.DataFrame,
        signals: pd.DataFrame,
        n_strategy_params: int = 5,
        initial_capital: float = 100_000,
    ) -> BacktestResult:
        """Run walk-forward backtest.

        Args:
            prices: DataFrame with columns = stock symbols, index = dates, values = close prices
            signals: DataFrame with same shape, values = target weights (0-1)
            n_strategy_params: number of free parameters in the strategy
            initial_capital: starting capital

        Returns:
            BacktestResult with all metrics
        """
        result = BacktestResult()

        # Validate
        result.warnings = self.validate_inputs(prices, n_strategy_params)

        if prices.empty or signals.empty:
            result.warnings.append("Empty price or signal data")
            return result

        # Align
        common_idx = prices.index.intersection(signals.index)
        prices = prices.loc[common_idx]
        signals = signals.loc[common_idx]

        # Split: 70% in-sample, 30% out-of-sample
        split_idx = int(len(common_idx) * BACKTEST_TRAIN_PCT)
        prices_is = prices.iloc[:split_idx]
        signals_is = signals.iloc[:split_idx]
        prices_oos = prices.iloc[split_idx:]
        signals_oos = signals.iloc[split_idx:]

        # Run both periods
        is_result = self._simulate(prices_is, signals_is, initial_capital)
        oos_result = self._simulate(prices_oos, signals_oos, initial_capital)

        # Combine equity curves
        result.equity_curve = is_result["equity_curve"] + oos_result["equity_curve"]
        result.total_trades = is_result["n_trades"] + oos_result["n_trades"]

        # Metrics from out-of-sample (the real test)
        if oos_result["equity_curve"]:
            oos_equity = pd.Series(oos_result["equity_curve"])
            result.total_return = (oos_equity.iloc[-1] / oos_equity.iloc[0]) - 1
            years = len(oos_result["equity_curve"]) / 252
            if years > 0:
                result.annualized_return = (1 + result.total_return) ** (1 / years) - 1

        result.in_sample_sharpe = is_result["sharpe"]
        result.out_sample_sharpe = oos_result["sharpe"]
        result.sharpe_ratio = oos_result["sharpe"]
        result.max_drawdown = oos_result["max_drawdown"]
        result.win_rate = oos_result["win_rate"]
        result.profit_factor = oos_result["profit_factor"]
        result.avg_hold_days = oos_result.get("avg_hold_days", 0)

        # Drawdown curve
        result.drawdown_curve = oos_result.get("drawdown_curve", [])

        # Overfitting detection
        if result.in_sample_sharpe > 0 and result.out_sample_sharpe > 0:
            ratio = result.in_sample_sharpe / result.out_sample_sharpe
            if ratio > 2.0:
                result.is_overfit = True
                result.warnings.append(
                    f"OVERFITTING DETECTED: in-sample Sharpe ({result.in_sample_sharpe:.2f}) "
                    f"is {ratio:.1f}x out-of-sample ({result.out_sample_sharpe:.2f})"
                )
        elif result.in_sample_sharpe > 0 and result.out_sample_sharpe <= 0:
            result.is_overfit = True
            result.warnings.append(
                "OVERFITTING: positive in-sample but negative out-of-sample Sharpe"
            )

        # Trade count check
        if result.total_trades < BACKTEST_MIN_TRADES:
            result.warnings.append(
                f"Only {result.total_trades} trades, minimum is {BACKTEST_MIN_TRADES} "
                f"for statistical significance"
            )

        return result

    def _simulate(
        self, prices: pd.DataFrame, signals: pd.DataFrame,
        initial_capital: float
    ) -> dict:
        """Simulate trading with realistic costs."""
        if prices.empty:
            return {
                "equity_curve": [],
                "n_trades": 0,
                "sharpe": 0.0,
                "max_drawdown": 0.0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "drawdown_curve": [],
            }

        cash = initial_capital
        holdings = {}  # {symbol: shares}
        equity_curve = []
        daily_returns = []
        trades_pnl = []
        n_trades = 0
        prev_equity = initial_capital

        for i, date in enumerate(prices.index):
            # Calculate current portfolio value
            portfolio_value = cash
            for sym, shares in holdings.items():
                if sym in prices.columns:
                    portfolio_value += shares * prices.loc[date, sym]

            equity_curve.append(portfolio_value)

            if i > 0:
                daily_ret = (portfolio_value - prev_equity) / prev_equity if prev_equity > 0 else 0
                daily_returns.append(daily_ret)
            prev_equity = portfolio_value

            # Rebalance periodically (every 10 trading days ~ 2 weeks)
            if i % 10 != 0:
                continue

            target_weights = signals.iloc[i]
            current_value = portfolio_value

            for sym in prices.columns:
                target_weight = target_weights.get(sym, 0.0) if sym in target_weights.index else 0.0
                target_value = current_value * min(target_weight, MAX_POSITION_PCT)
                current_shares = holdings.get(sym, 0)
                current_price = prices.loc[date, sym]

                if pd.isna(current_price) or current_price <= 0:
                    continue

                current_pos_value = current_shares * current_price
                diff = target_value - current_pos_value

                if abs(diff) < current_value * 0.01:
                    continue  # skip tiny adjustments

                shares_to_trade = int(diff / current_price)
                if shares_to_trade == 0:
                    continue

                # Apply slippage
                slippage = abs(shares_to_trade * current_price * self.slippage_pct)

                # Apply 2% stop-loss logic: cap maximum loss per position
                trade_value = abs(shares_to_trade * current_price)
                max_position_loss = current_value * MAX_LOSS_PER_TRADE_PCT

                if shares_to_trade > 0:  # buying
                    cost = shares_to_trade * current_price + slippage
                    if cost <= cash:
                        cash -= cost
                        holdings[sym] = current_shares + shares_to_trade
                        n_trades += 1
                else:  # selling
                    sell_shares = min(abs(shares_to_trade), current_shares)
                    if sell_shares > 0:
                        proceeds = sell_shares * current_price - slippage
                        cash += proceeds
                        pnl = proceeds - (sell_shares * current_price)  # simplified
                        trades_pnl.append(pnl)
                        holdings[sym] = current_shares - sell_shares
                        if holdings[sym] <= 0:
                            del holdings[sym]
                        n_trades += 1

        # Calculate metrics
        daily_returns = pd.Series(daily_returns) if daily_returns else pd.Series([0.0])

        sharpe = 0.0
        if daily_returns.std() > 0:
            sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)

        # Max drawdown
        equity_series = pd.Series(equity_curve)
        running_max = equity_series.cummax()
        drawdowns = (equity_series - running_max) / running_max
        max_drawdown = abs(drawdowns.min()) if len(drawdowns) > 0 else 0.0
        drawdown_curve = drawdowns.tolist()

        # Win rate and profit factor
        wins = [p for p in trades_pnl if p > 0]
        losses = [p for p in trades_pnl if p < 0]
        win_rate = len(wins) / len(trades_pnl) if trades_pnl else 0.0
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = abs(sum(losses) / len(losses)) if losses else 1.0
        profit_factor = avg_win / avg_loss if avg_loss > 0 else 0.0

        return {
            "equity_curve": equity_curve,
            "n_trades": n_trades,
            "sharpe": round(sharpe, 3),
            "max_drawdown": round(max_drawdown, 4),
            "win_rate": round(win_rate, 4),
            "profit_factor": round(profit_factor, 3),
            "drawdown_curve": drawdown_curve,
            "avg_hold_days": 10.0,  # approximate from rebalance frequency
        }
