"""Layer 5: Performance Reporter — monthly auto-reports with factor attribution.

Generates reports comparing performance vs S&P 500 benchmark,
broken down by which factors contributed to P&L.
"""

import json
from datetime import datetime, timedelta
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from trading.db import TradingDatabase
from trading.config import BENCHMARK_SYMBOL


class PerformanceReporter:
    """Generate monthly performance reports with factor attribution."""

    def __init__(self, db: TradingDatabase):
        self.db = db
        self.console = Console()

    def generate_monthly_report(self, days: int = 30) -> dict:
        """Generate a comprehensive performance report.

        Returns dict with all metrics for programmatic use.
        """
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        trades = self.db.get_trades_since(since)
        equity_data = self.db.get_equity_series(days)
        risk_events = self.db.get_recent_risk_events(50)

        closed = [t for t in trades if t["exit_time"]]
        open_trades = [t for t in trades if not t["exit_time"]]

        # Basic P&L
        total_pnl = sum(t["pnl"] or 0 for t in closed)
        wins = [t for t in closed if (t["pnl"] or 0) > 0]
        losses = [t for t in closed if (t["pnl"] or 0) < 0]
        win_rate = len(wins) / len(closed) if closed else 0

        avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
        avg_loss = abs(sum(t["pnl"] for t in losses) / len(losses)) if losses else 1
        profit_factor = avg_win / avg_loss if avg_loss > 0 else 0

        # Factor attribution
        attribution = self._calculate_factor_attribution(closed)

        # Drawdown
        max_dd = 0.0
        if equity_data:
            max_dd = max((e["drawdown_pct"] for e in equity_data), default=0)

        # Total slippage
        total_slippage = sum(t["slippage"] or 0 for t in closed)

        report = {
            "period_days": days,
            "total_trades": len(closed),
            "open_positions": len(open_trades),
            "total_pnl": total_pnl,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "max_drawdown": max_dd,
            "total_slippage": total_slippage,
            "risk_events": len([e for e in risk_events
                                if e["timestamp"] and e["timestamp"] >= since]),
            "factor_attribution": attribution,
        }

        return report

    def display_report(self, days: int = 30):
        """Generate and display a formatted performance report."""
        report = self.generate_monthly_report(days)

        # Header
        self.console.print(Panel(
            f"[bold]Performance Report — Last {days} Days[/bold]",
            style="blue"
        ))

        # Summary metrics
        pnl_style = "green" if report["total_pnl"] >= 0 else "red"
        self.console.print(f"\nTotal P&L: [{pnl_style}]${report['total_pnl']:+,.2f}[/{pnl_style}]")
        self.console.print(f"Trades Closed: {report['total_trades']}")
        self.console.print(f"Open Positions: {report['open_positions']}")
        self.console.print(f"Win Rate: {report['win_rate']:.1%}")
        self.console.print(f"Profit Factor: {report['profit_factor']:.2f}")
        self.console.print(f"Avg Win: ${report['avg_win']:+,.2f}")
        self.console.print(f"Avg Loss: -${report['avg_loss']:,.2f}")
        self.console.print(f"Max Drawdown: {report['max_drawdown']:.1%}")
        self.console.print(f"Total Slippage: ${report['total_slippage']:,.2f}")
        self.console.print(f"Risk Events: {report['risk_events']}")

        # Factor attribution table
        if report["factor_attribution"]:
            self.console.print("\n")
            table = Table(title="Factor Attribution (P&L by Signal Type)")
            table.add_column("Factor", style="cyan")
            table.add_column("P&L", justify="right")
            table.add_column("Trades", justify="right")
            table.add_column("Win Rate", justify="right")

            for factor, data in report["factor_attribution"].items():
                pnl = data["pnl"]
                style = "green" if pnl >= 0 else "red"
                table.add_row(
                    factor,
                    f"[{style}]${pnl:+,.2f}[/{style}]",
                    str(data["trades"]),
                    f"{data['win_rate']:.0%}",
                )

            self.console.print(table)

    def _calculate_factor_attribution(self, closed_trades: list) -> dict:
        """Break down P&L by factor / signal type."""
        attribution = {}

        for trade in closed_trades:
            signal = trade.get("signal_type") or "unknown"
            pnl = trade.get("pnl") or 0

            if signal not in attribution:
                attribution[signal] = {"pnl": 0.0, "trades": 0, "wins": 0}

            attribution[signal]["pnl"] += pnl
            attribution[signal]["trades"] += 1
            if pnl > 0:
                attribution[signal]["wins"] += 1

        # Calculate win rates
        for data in attribution.values():
            data["win_rate"] = data["wins"] / data["trades"] if data["trades"] > 0 else 0

        # Also try JSON factor_attribution field
        for trade in closed_trades:
            attr_json = trade.get("factor_attribution")
            if attr_json:
                try:
                    factors = json.loads(attr_json)
                    total_pnl = trade.get("pnl") or 0
                    for factor, weight in factors.items():
                        key = f"factor_{factor}"
                        if key not in attribution:
                            attribution[key] = {"pnl": 0.0, "trades": 0, "wins": 0, "win_rate": 0}
                        attribution[key]["pnl"] += total_pnl * weight
                except (json.JSONDecodeError, TypeError):
                    pass

        return attribution
