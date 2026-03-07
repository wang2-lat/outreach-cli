"""Layer 7: Benchmark Tracking.

Targets:
- Beat S&P 500 annualized return
- Sharpe ratio > 1.0
- Max drawdown < 20%
- Win rate > 45%
- Profit factor > 1.5
- Paper trade 3+ months before live
"""

from datetime import datetime, timedelta

import numpy as np

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from trading.db import TradingDatabase
from trading.config import (
    BENCHMARK_SYMBOL,
    TARGET_SHARPE_RATIO,
    TARGET_MAX_DRAWDOWN,
    TARGET_WIN_RATE,
    TARGET_PROFIT_FACTOR,
    PAPER_TRADING_MIN_DAYS,
)


class BenchmarkTracker:
    """Track performance against targets and decide readiness for live trading."""

    def __init__(self, db: TradingDatabase):
        self.db = db
        self.console = Console()

    def get_metrics(self) -> dict:
        """Calculate all benchmark metrics from trade history."""
        equity_data = self.db.get_equity_series(365)
        closed_trades = self.db.get_closed_trades(10000)

        # Annualized return
        annualized_return = 0.0
        if len(equity_data) >= 2:
            start_eq = equity_data[0]["equity"]
            end_eq = equity_data[-1]["equity"]
            days = len(equity_data)
            if start_eq > 0 and days > 0:
                total_return = (end_eq - start_eq) / start_eq
                years = days / 252
                if years > 0:
                    annualized_return = (1 + total_return) ** (1 / years) - 1

        # Sharpe ratio
        sharpe = 0.0
        if len(equity_data) >= 2:
            returns = []
            for i in range(1, len(equity_data)):
                prev = equity_data[i - 1]["equity"]
                curr = equity_data[i]["equity"]
                if prev > 0:
                    returns.append((curr - prev) / prev)

            if returns:
                arr = np.array(returns)
                if arr.std() > 0:
                    sharpe = (arr.mean() / arr.std()) * np.sqrt(252)

        # Max drawdown
        max_dd = 0.0
        if equity_data:
            max_dd = max((e["drawdown_pct"] for e in equity_data), default=0)

        # Win rate and profit factor
        wins = [t for t in closed_trades if (t["pnl"] or 0) > 0]
        losses = [t for t in closed_trades if (t["pnl"] or 0) < 0]
        win_rate = len(wins) / len(closed_trades) if closed_trades else 0

        avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
        avg_loss = abs(sum(t["pnl"] for t in losses) / len(losses)) if losses else 1
        profit_factor = avg_win / avg_loss if avg_loss > 0 else 0

        # Trading days
        trading_days = len(equity_data)

        return {
            "annualized_return": annualized_return,
            "sharpe_ratio": sharpe,
            "max_drawdown": max_dd,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "total_trades": len(closed_trades),
            "trading_days": trading_days,
        }

    def is_paper_ready(self) -> tuple[bool, list[str]]:
        """Check if paper trading period requirements are met."""
        metrics = self.get_metrics()
        issues = []

        if metrics["trading_days"] < PAPER_TRADING_MIN_DAYS:
            issues.append(
                f"Need {PAPER_TRADING_MIN_DAYS} trading days, have {metrics['trading_days']}"
            )

        return len(issues) == 0, issues

    def is_live_ready(self) -> tuple[bool, list[str]]:
        """Check if all benchmarks are met for live trading."""
        metrics = self.get_metrics()
        issues = []

        # Paper trading minimum
        if metrics["trading_days"] < PAPER_TRADING_MIN_DAYS:
            issues.append(
                f"Paper trading: {metrics['trading_days']}/{PAPER_TRADING_MIN_DAYS} days"
            )

        # Sharpe
        if metrics["sharpe_ratio"] < TARGET_SHARPE_RATIO:
            issues.append(
                f"Sharpe ratio: {metrics['sharpe_ratio']:.2f} < {TARGET_SHARPE_RATIO}"
            )

        # Drawdown
        if metrics["max_drawdown"] > TARGET_MAX_DRAWDOWN:
            issues.append(
                f"Max drawdown: {metrics['max_drawdown']:.1%} > {TARGET_MAX_DRAWDOWN:.0%}"
            )

        # Win rate
        if metrics["win_rate"] < TARGET_WIN_RATE:
            issues.append(
                f"Win rate: {metrics['win_rate']:.1%} < {TARGET_WIN_RATE:.0%}"
            )

        # Profit factor
        if metrics["profit_factor"] < TARGET_PROFIT_FACTOR:
            issues.append(
                f"Profit factor: {metrics['profit_factor']:.2f} < {TARGET_PROFIT_FACTOR}"
            )

        return len(issues) == 0, issues

    def display_dashboard(self):
        """Display benchmark dashboard with pass/fail indicators."""
        metrics = self.get_metrics()
        ready, issues = self.is_live_ready()

        status = "[green]LIVE READY[/green]" if ready else "[red]NOT READY[/red]"
        self.console.print(Panel(
            f"[bold]Benchmark Dashboard[/bold]  |  Status: {status}",
            style="blue"
        ))

        table = Table()
        table.add_column("Metric", style="cyan")
        table.add_column("Current", justify="right")
        table.add_column("Target", justify="right")
        table.add_column("Status", justify="center")

        def check(current, target, higher_is_better=True):
            if higher_is_better:
                return "[green]PASS[/green]" if current >= target else "[red]FAIL[/red]"
            return "[green]PASS[/green]" if current <= target else "[red]FAIL[/red]"

        table.add_row(
            "Annualized Return",
            f"{metrics['annualized_return']:.1%}",
            f"> {BENCHMARK_SYMBOL}",
            "[dim]vs benchmark[/dim]",
        )
        table.add_row(
            "Sharpe Ratio",
            f"{metrics['sharpe_ratio']:.2f}",
            f"> {TARGET_SHARPE_RATIO}",
            check(metrics["sharpe_ratio"], TARGET_SHARPE_RATIO),
        )
        table.add_row(
            "Max Drawdown",
            f"{metrics['max_drawdown']:.1%}",
            f"< {TARGET_MAX_DRAWDOWN:.0%}",
            check(metrics["max_drawdown"], TARGET_MAX_DRAWDOWN, higher_is_better=False),
        )
        table.add_row(
            "Win Rate",
            f"{metrics['win_rate']:.1%}",
            f"> {TARGET_WIN_RATE:.0%}",
            check(metrics["win_rate"], TARGET_WIN_RATE),
        )
        table.add_row(
            "Profit Factor",
            f"{metrics['profit_factor']:.2f}",
            f"> {TARGET_PROFIT_FACTOR}",
            check(metrics["profit_factor"], TARGET_PROFIT_FACTOR),
        )
        table.add_row(
            "Paper Trading Days",
            str(metrics["trading_days"]),
            f"> {PAPER_TRADING_MIN_DAYS}",
            check(metrics["trading_days"], PAPER_TRADING_MIN_DAYS),
        )
        table.add_row(
            "Total Trades",
            str(metrics["total_trades"]),
            "> 200",
            check(metrics["total_trades"], 200),
        )

        self.console.print(table)

        if issues:
            self.console.print("\n[bold red]Issues to resolve:[/bold red]")
            for issue in issues:
                self.console.print(f"  - {issue}")
