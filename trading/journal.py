"""Layer 5: Trade Journal — automatic logging of every trade.

Records: entry/exit time, price, signal, exit reason (stop-loss / take-profit /
rebalance), P&L, actual slippage.  Research shows traders who don't review
their journals never improve even after 10 years of losses.
"""

from datetime import datetime
from typing import Optional

from rich.console import Console
from rich.table import Table

from trading.db import TradingDatabase


class TradeJournal:
    """Read-only interface to the trade log (writing happens in broker/db)."""

    def __init__(self, db: TradingDatabase):
        self.db = db
        self.console = Console()

    def show_open_positions(self):
        """Display currently open trades."""
        trades = self.db.get_open_trades()

        if not trades:
            self.console.print("[yellow]No open positions[/yellow]")
            return

        table = Table(title="Open Positions")
        table.add_column("ID", style="cyan")
        table.add_column("Symbol", style="magenta")
        table.add_column("Side", style="white")
        table.add_column("Qty", justify="right")
        table.add_column("Entry Price", justify="right", style="green")
        table.add_column("Stop Loss", justify="right", style="red")
        table.add_column("Signal", style="dim")
        table.add_column("Entry Time", style="dim")

        for t in trades:
            table.add_row(
                str(t["id"]),
                t["symbol"],
                t["side"],
                f"{t['quantity']:.0f}",
                f"${t['entry_price']:.2f}" if t["entry_price"] else "N/A",
                f"${t['stop_loss_price']:.2f}" if t["stop_loss_price"] else "N/A",
                t["signal_type"] or "N/A",
                t["entry_time"][:16] if t["entry_time"] else "N/A",
            )

        self.console.print(table)

    def show_recent_trades(self, limit: int = 20):
        """Display recently closed trades."""
        trades = self.db.get_closed_trades(limit)

        if not trades:
            self.console.print("[yellow]No closed trades yet[/yellow]")
            return

        table = Table(title=f"Last {limit} Closed Trades")
        table.add_column("ID", style="cyan")
        table.add_column("Symbol", style="magenta")
        table.add_column("Side")
        table.add_column("Qty", justify="right")
        table.add_column("Entry", justify="right")
        table.add_column("Exit", justify="right")
        table.add_column("P&L", justify="right")
        table.add_column("Reason", style="dim")
        table.add_column("Slippage", justify="right", style="dim")

        total_pnl = 0.0
        wins = 0
        losses = 0

        for t in trades:
            pnl = t["pnl"] or 0.0
            total_pnl += pnl
            if pnl > 0:
                wins += 1
            elif pnl < 0:
                losses += 1

            pnl_style = "green" if pnl >= 0 else "red"
            table.add_row(
                str(t["id"]),
                t["symbol"],
                t["side"],
                f"{t['quantity']:.0f}",
                f"${t['entry_price']:.2f}" if t["entry_price"] else "N/A",
                f"${t['exit_price']:.2f}" if t["exit_price"] else "N/A",
                f"[{pnl_style}]${pnl:+,.2f}[/{pnl_style}]",
                t["exit_reason"] or "N/A",
                f"${t['slippage']:.2f}" if t["slippage"] else "$0.00",
            )

        self.console.print(table)

        # Summary
        total_trades = wins + losses
        win_rate = wins / total_trades * 100 if total_trades > 0 else 0
        pnl_style = "green" if total_pnl >= 0 else "red"
        self.console.print(
            f"\nTotal P&L: [{pnl_style}]${total_pnl:+,.2f}[/{pnl_style}]  |  "
            f"Win Rate: {win_rate:.0f}% ({wins}W / {losses}L)"
        )

    def show_risk_events(self, limit: int = 20):
        """Display recent risk events."""
        events = self.db.get_recent_risk_events(limit)

        if not events:
            self.console.print("[green]No risk events recorded[/green]")
            return

        table = Table(title="Risk Events")
        table.add_column("Time", style="dim")
        table.add_column("Type", style="red")
        table.add_column("Symbol", style="magenta")
        table.add_column("Details", style="white")
        table.add_column("Equity", justify="right")

        for e in events:
            table.add_row(
                e["timestamp"][:16] if e["timestamp"] else "N/A",
                e["event_type"],
                e["symbol"] or "",
                e["details"] or "",
                f"${e['equity_at_event']:,.0f}" if e["equity_at_event"] else "N/A",
            )

        self.console.print(table)
