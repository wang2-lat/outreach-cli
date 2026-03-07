"""CLI sub-app for the trading system.

Registered as `trading` subcommand group in main.py.
Usage: python main.py trading <command>
"""

import typer
from rich.console import Console
from rich.panel import Panel

from trading.db import TradingDatabase
from trading.risk_engine import RiskEngine
from trading.frequency_guard import FrequencyGuard
from trading.anti_patterns import AntiPatternEnforcer
from trading.journal import TradeJournal
from trading.reporter import PerformanceReporter
from trading.benchmarks import BenchmarkTracker
from trading.config import ALPACA_PAPER

trading_app = typer.Typer(
    name="trading",
    help="Alpaca trading bot with multi-factor signals and institutional-grade risk control",
)
console = Console()


def _init_components():
    """Initialize all trading system components."""
    db = TradingDatabase()
    risk = RiskEngine()
    freq = FrequencyGuard(db)
    enforcer = AntiPatternEnforcer(db, risk, freq)
    return db, risk, freq, enforcer


@trading_app.command()
def status():
    """Show current portfolio status, positions, and risk metrics."""
    db, risk, freq, enforcer = _init_components()

    console.print(Panel(
        "[bold]Trading System Status[/bold]",
        style="blue"
    ))

    mode = "[yellow]PAPER[/yellow]" if ALPACA_PAPER else "[red]LIVE[/red]"
    console.print(f"Mode: {mode}")

    try:
        from trading.broker import AlpacaBroker
        broker = AlpacaBroker(db, risk, freq, enforcer)
        account = broker.get_account()

        console.print(f"Equity: ${account['equity']:,.2f}")
        console.print(f"Cash: ${account['cash']:,.2f}")
        console.print(f"Buying Power: ${account['buying_power']:,.2f}")

        # Leverage check
        lev_check = risk.check_leverage(account["buying_power"], account["equity"])
        if not lev_check.approved:
            console.print(f"[red]WARNING: {lev_check.reason}[/red]")
        else:
            console.print("[green]Leverage check: CLEAN (no margin)[/green]")

        # Positions
        positions = broker.get_positions()
        if positions:
            console.print(f"\nPositions: {len(positions)}")
            for p in positions:
                pnl_style = "green" if p["unrealized_pnl"] >= 0 else "red"
                console.print(
                    f"  {p['symbol']}: {p['quantity']:.0f} shares @ "
                    f"${p['current_price']:.2f} "
                    f"[{pnl_style}]({p['unrealized_pnl_pct']:.1%})[/{pnl_style}]"
                )
        else:
            console.print("\n[dim]No open positions[/dim]")

    except Exception as e:
        console.print(f"[red]Cannot connect to Alpaca: {e}[/red]")
        console.print("[dim]Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables[/dim]")

    # Cooldown status
    ok, reason = freq.check_cooldown()
    if not ok:
        console.print(f"\n[red]{reason}[/red]")

    # Weekly trade count
    ok, reason = freq.can_open_position()
    if not ok:
        console.print(f"[yellow]{reason}[/yellow]")


@trading_app.command()
def risk():
    """Show risk dashboard — drawdown, exposure, VIX, anti-pattern status."""
    db, risk_engine, freq, enforcer = _init_components()

    console.print(Panel("[bold]Risk Dashboard[/bold]", style="red"))

    # Equity and drawdown
    equity_data = db.get_equity_series(30)
    if equity_data:
        latest = equity_data[-1]
        console.print(f"Current Equity: ${latest['equity']:,.2f}")
        console.print(f"Peak Equity: ${latest['peak_equity']:,.2f}")

        dd_style = "green" if latest["drawdown_pct"] < 0.05 else "red"
        console.print(f"Drawdown: [{dd_style}]{latest['drawdown_pct']:.1%}[/{dd_style}]")
    else:
        console.print("[dim]No equity data yet[/dim]")

    # VIX
    try:
        from trading.broker import AlpacaBroker
        broker = AlpacaBroker(db, risk_engine, freq, enforcer)
        vix = broker.get_vix()
        vix_style = "red" if vix > 35 else ("yellow" if vix > 25 else "green")
        console.print(f"\nVIX: [{vix_style}]{vix:.1f}[/{vix_style}]")
        if vix > 35:
            console.print("[red]VIX > 35: No new positions allowed[/red]")
    except Exception:
        console.print("\n[dim]VIX: unavailable[/dim]")

    # Recent risk events
    console.print("\n")
    journal = TradeJournal(db)
    journal.show_risk_events(10)


@trading_app.command()
def journal(limit: int = typer.Option(20, "--limit", "-n", help="Number of trades to show")):
    """View trade journal — recent entries and exits."""
    db = TradingDatabase()
    j = TradeJournal(db)

    j.show_open_positions()
    console.print("")
    j.show_recent_trades(limit)


@trading_app.command()
def report(days: int = typer.Option(30, "--days", "-d", help="Report period in days")):
    """Generate monthly performance report with factor attribution."""
    db = TradingDatabase()
    reporter = PerformanceReporter(db)
    reporter.display_report(days)


@trading_app.command()
def benchmarks():
    """Show benchmark dashboard — Sharpe, drawdown, win rate vs targets."""
    db = TradingDatabase()
    tracker = BenchmarkTracker(db)
    tracker.display_dashboard()


@trading_app.command()
def backtest():
    """Run backtester on historical data (placeholder — requires data setup)."""
    console.print(Panel("[bold]Backtesting System[/bold]", style="cyan"))
    console.print(
        "To run a backtest, use the Python API directly:\n\n"
        "  from trading.backtester import Backtester\n"
        "  bt = Backtester()\n"
        "  result = bt.run(prices_df, signals_df)\n"
        "  print(result)\n\n"
        "Requirements:\n"
        "  - Min 5 years of price data\n"
        "  - 70/30 in-sample/out-of-sample split\n"
        "  - Max 10 strategy parameters\n"
        "  - 200+ trade samples for significance"
    )


@trading_app.command()
def config():
    """Display current trading system configuration."""
    from trading import config as cfg

    console.print(Panel("[bold]Trading Configuration[/bold]", style="cyan"))

    console.print("[bold]Risk Control (Layer 1)[/bold]")
    console.print(f"  Max loss per trade: {cfg.MAX_LOSS_PER_TRADE_PCT:.0%}")
    console.print(f"  Max position size: {cfg.MAX_POSITION_PCT:.0%}")
    console.print(f"  Max industry exposure: {cfg.MAX_INDUSTRY_PCT:.0%}")
    console.print(f"  Portfolio size: {cfg.MIN_POSITIONS}-{cfg.MAX_POSITIONS} stocks")
    console.print(f"  Weekly drawdown limit: {cfg.WEEKLY_DRAWDOWN_LIMIT:.0%}")
    console.print(f"  Total drawdown limit: {cfg.TOTAL_DRAWDOWN_LIMIT:.0%}")
    console.print(f"  Leverage: {'ENABLED' if cfg.USE_LEVERAGE else 'DISABLED'}")

    console.print("\n[bold]Trading Frequency (Layer 2)[/bold]")
    console.print(f"  Min hold period: {cfg.MIN_HOLD_DAYS} trading days")
    console.print(f"  Max new positions/week: {cfg.MAX_NEW_POSITIONS_PER_WEEK}")
    console.print(f"  Stop-loss cooldown: {cfg.COOLDOWN_HOURS_AFTER_STOP_LOSS}h")

    console.print("\n[bold]Factor Weights (Layer 3)[/bold]")
    console.print(f"  Momentum: {cfg.FACTOR_WEIGHT_MOMENTUM:.0%}")
    console.print(f"  Value: {cfg.FACTOR_WEIGHT_VALUE:.0%}")
    console.print(f"  Quality: {cfg.FACTOR_WEIGHT_QUALITY:.0%}")
    console.print(f"  Sentiment: {cfg.FACTOR_WEIGHT_SENTIMENT:.0%}")
    console.print(f"  Macro: {cfg.FACTOR_WEIGHT_MACRO:.0%}")
    console.print(f"  VIX threshold: {cfg.VIX_THRESHOLD}")

    console.print("\n[bold]Rebalancing[/bold]")
    console.print(f"  Interval: every {cfg.REBALANCE_INTERVAL_DAYS} days")
    console.print(f"  Min improvement: {cfg.MIN_REBALANCE_IMPROVEMENT}")
    console.print(f"  Est. transaction cost: {cfg.ESTIMATED_TRANSACTION_COST_PCT:.2%}")

    console.print("\n[bold]Benchmarks (Layer 7)[/bold]")
    console.print(f"  Target Sharpe: > {cfg.TARGET_SHARPE_RATIO}")
    console.print(f"  Target max DD: < {cfg.TARGET_MAX_DRAWDOWN:.0%}")
    console.print(f"  Target win rate: > {cfg.TARGET_WIN_RATE:.0%}")
    console.print(f"  Target profit factor: > {cfg.TARGET_PROFIT_FACTOR}")
    console.print(f"  Paper trading min: {cfg.PAPER_TRADING_MIN_DAYS} days")
