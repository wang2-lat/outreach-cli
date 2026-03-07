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
def run(
    execute: bool = typer.Option(False, "--execute", "-x", help="Execute trades in paper account (default: dry run)"),
    top_n: int = typer.Option(20, "--top", "-t", help="Number of top stocks to display"),
):
    """Run the full pipeline: score S&P 500, select top stocks, optionally execute."""
    from rich.table import Table
    from trading.broker import AlpacaBroker
    from trading.signal import SignalEngine
    from trading.portfolio import PortfolioManager
    from trading.universe import UniverseProvider
    from trading.notifications import NotificationManager

    db, risk, freq, enforcer = _init_components()
    notifier = NotificationManager()
    broker = AlpacaBroker(db, risk, freq, enforcer, notification_manager=notifier)
    signal = SignalEngine(db)
    portfolio = PortfolioManager(broker, signal, risk, db)
    universe = UniverseProvider(broker)

    mode = "[yellow]PAPER[/yellow]" if ALPACA_PAPER else "[red]LIVE[/red]"
    console.print(Panel(f"[bold]Trading Pipeline[/bold] — {mode}", style="blue"))

    # 1. Get universe
    console.print("Fetching S&P 500 constituents...")
    symbols = universe.get_sp500_symbols()
    console.print(f"  Universe: {len(symbols)} stocks")

    # 2. Fetch data
    console.print("Fetching price data (2 years)...")
    price_data = universe.get_price_data(symbols, days=504)
    console.print(f"  Price data: {len(price_data)} stocks with sufficient history")

    # Only fetch fundamentals/news for stocks with price data
    scored_symbols = list(price_data.keys())

    console.print("Fetching fundamentals...")
    fundamentals = universe.get_fundamentals(scored_symbols)
    console.print(f"  Fundamentals: {len(fundamentals)} stocks")

    console.print("Fetching news headlines...")
    news_data = universe.get_news_data(scored_symbols[:100])  # limit to top 100 for speed
    console.print(f"  News: {len(news_data)} stocks")

    console.print("Fetching macro data...")
    macro_data = universe.get_macro_data()
    console.print(f"  VIX: {macro_data.get('vix', 'N/A'):.1f}  |  "
                  f"10Y: {macro_data.get('yield_10y', 'N/A'):.2f}  |  "
                  f"2Y: {macro_data.get('yield_2y', 'N/A'):.2f}")

    industry_map = universe.get_industry_map(scored_symbols)

    # 3. Score universe
    console.print("\nScoring universe with multi-factor model...")
    scores = signal.score_universe(price_data, fundamentals, news_data, macro_data)
    console.print(f"  Scored: {len(scores)} stocks")

    if not scores:
        console.print("[red]No scores generated. Check data availability.[/red]")
        return

    # 4. Display top N stocks with factor scores
    console.print(f"\n")
    table = Table(title=f"Top {top_n} Stocks — Multi-Factor Ranking")
    table.add_column("Rank", style="bold", width=5)
    table.add_column("Symbol", style="cyan", width=8)
    table.add_column("Composite", justify="right", width=10)
    table.add_column("Momentum", justify="right", width=10)
    table.add_column("Value", justify="right", width=10)
    table.add_column("Quality", justify="right", width=10)
    table.add_column("Industry", width=25)

    # Get individual factor scores from DB
    today = __import__("datetime").datetime.utcnow().strftime("%Y-%m-%d")
    conn = db._conn()

    for rank, (symbol, composite) in enumerate(list(scores.items())[:top_n], 1):
        # Query individual factor scores
        row = conn.execute(
            "SELECT momentum_score, value_score, quality_score FROM factor_scores "
            "WHERE symbol=? AND date=? ORDER BY rowid DESC LIMIT 1",
            (symbol, today)
        ).fetchone()

        mom = f"{row['momentum_score']:.3f}" if row and row['momentum_score'] is not None else "—"
        val = f"{row['value_score']:.3f}" if row and row['value_score'] is not None else "—"
        qual = f"{row['quality_score']:.3f}" if row and row['quality_score'] is not None else "—"
        industry = industry_map.get(symbol, "Unknown")

        table.add_row(
            str(rank),
            symbol,
            f"{composite:.4f}",
            mom, val, qual,
            industry,
        )

    console.print(table)
    db._close(conn)

    # 5. Execute if requested
    if execute:
        console.print("\n[bold]Executing rebalance in paper trading account...[/bold]")
        try:
            result = portfolio.execute_rebalance(
                price_data, fundamentals, news_data, macro_data, industry_map
            )

            if result["action"] == "skip":
                console.print(f"[yellow]Skipped: {result['reason']}[/yellow]")
            else:
                console.print(f"[green]Rebalanced![/green]")
                console.print(f"  Orders submitted: {result['orders']}")
                console.print(f"  Executed: {result['executed']}")
                console.print(f"  Rejected by risk engine: {result['rejected']}")

                if result.get("details"):
                    console.print("\nOrder Details:")
                    for d in result["details"]:
                        status = "[green]OK[/green]" if d.get("success") else f"[red]REJECTED: {d.get('reason', '?')}[/red]"
                        console.print(f"  {d['side'].upper()} {d.get('quantity', '?')} {d['symbol']} — {status}")

        except Exception as e:
            console.print(f"[red]Execution failed: {e}[/red]")
    else:
        console.print(
            "\n[dim]Dry run complete. Use --execute to place orders in paper trading.[/dim]"
        )


@trading_app.command(name="equity-update")
def equity_update():
    """Update daily equity tracking (for cron usage)."""
    from trading.broker import AlpacaBroker
    from trading.signal import SignalEngine
    from trading.portfolio import PortfolioManager

    db, risk, freq, enforcer = _init_components()
    broker = AlpacaBroker(db, risk, freq, enforcer)
    signal = SignalEngine(db)
    portfolio = PortfolioManager(broker, signal, risk, db)

    try:
        portfolio.update_equity_tracking()
        console.print("[green]Daily equity tracking updated.[/green]")
    except Exception as e:
        console.print(f"[red]Failed: {e}[/red]")


@trading_app.command(name="weekly-summary")
def weekly_summary():
    """Send weekly summary email notification."""
    from trading.notifications import NotificationManager

    db = TradingDatabase()
    notifier = NotificationManager()

    if not notifier._is_configured():
        console.print("[yellow]Notifications not configured. Set TRADING_NOTIFICATIONS_ENABLED=true "
                      "and SMTP environment variables.[/yellow]")
        return

    notifier.notify_weekly_summary(db)
    console.print("[green]Weekly summary email sent.[/green]")


@trading_app.command()
def schedule():
    """Start the trading scheduler (runs as a daemon).

    Scheduled jobs:
      - Rebalance: every 14 days
      - Equity tracking: weekdays at 16:30 ET
      - Weekly summary email: Sundays at 09:00

    Alternative: use crontab entries instead:
      0 10 1,15 * * cd /path/to/outreach-cli && python main.py trading run --execute
      30 16 * * 1-5 cd /path/to/outreach-cli && python main.py trading equity-update
      0 9 * * 0 cd /path/to/outreach-cli && python main.py trading weekly-summary
    """
    from trading.scheduler import TradingScheduler

    console.print(Panel("[bold]Trading Scheduler[/bold]", style="green"))
    console.print("Starting scheduler daemon...")
    console.print("  Rebalance: every 14 days")
    console.print("  Equity tracking: weekdays at 16:30")
    console.print("  Weekly summary: Sundays at 09:00")
    console.print("\nPress Ctrl+C to stop.\n")

    scheduler = TradingScheduler()
    try:
        scheduler.start()
    except KeyboardInterrupt:
        console.print("\n[yellow]Scheduler stopped.[/yellow]")


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
