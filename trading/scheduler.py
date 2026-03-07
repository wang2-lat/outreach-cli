"""Automated trading scheduler.

Runs as a long-lived daemon process with three scheduled jobs:
  1. Bi-weekly rebalance (every 14 days)
  2. Daily equity tracking (weekdays at 16:30 ET)
  3. Weekly summary email (Sundays at 09:00)
"""

import time
import logging
from datetime import datetime

import schedule

from trading.config import REBALANCE_INTERVAL_DAYS

logger = logging.getLogger(__name__)


class TradingScheduler:
    """In-process scheduler for automated trading operations."""

    def __init__(self):
        self._setup_jobs()

    def _setup_jobs(self):
        """Configure all scheduled jobs."""
        # Rebalance every 14 days (Monday at 10:00 AM)
        schedule.every(REBALANCE_INTERVAL_DAYS).days.at("10:00").do(self._run_rebalance)

        # Daily equity tracking at 16:30 (after market close)
        schedule.every().monday.at("16:30").do(self._run_daily_equity)
        schedule.every().tuesday.at("16:30").do(self._run_daily_equity)
        schedule.every().wednesday.at("16:30").do(self._run_daily_equity)
        schedule.every().thursday.at("16:30").do(self._run_daily_equity)
        schedule.every().friday.at("16:30").do(self._run_daily_equity)

        # Weekly summary email on Sundays at 09:00
        schedule.every().sunday.at("09:00").do(self._run_weekly_summary)

    def start(self):
        """Start the blocking scheduler loop."""
        logger.info("Trading scheduler started")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Scheduler running. Next jobs:")
        for job in schedule.get_jobs():
            print(f"  {job}")

        while True:
            schedule.run_pending()
            time.sleep(60)

    def _init_pipeline(self):
        """Initialize all trading components."""
        from trading.db import TradingDatabase
        from trading.risk_engine import RiskEngine
        from trading.frequency_guard import FrequencyGuard
        from trading.anti_patterns import AntiPatternEnforcer
        from trading.broker import AlpacaBroker
        from trading.signal import SignalEngine
        from trading.portfolio import PortfolioManager
        from trading.notifications import NotificationManager

        db = TradingDatabase()
        risk = RiskEngine()
        freq = FrequencyGuard(db)
        enforcer = AntiPatternEnforcer(db, risk, freq)
        notifier = NotificationManager()
        broker = AlpacaBroker(db, risk, freq, enforcer, notification_manager=notifier)
        signal = SignalEngine(db)
        portfolio = PortfolioManager(broker, signal, risk, db)

        return db, broker, signal, portfolio, notifier

    def _run_rebalance(self):
        """Execute a full rebalance cycle."""
        logger.info("Scheduled rebalance starting")
        try:
            from trading.universe import UniverseProvider

            db, broker, signal, portfolio, notifier = self._init_pipeline()
            universe = UniverseProvider(broker)

            symbols = universe.get_sp500_symbols()
            price_data = universe.get_price_data(symbols, days=504)
            scored_symbols = list(price_data.keys())

            fundamentals = universe.get_fundamentals(scored_symbols)
            news_data = universe.get_news_data(scored_symbols[:100])
            macro_data = universe.get_macro_data()
            industry_map = universe.get_industry_map(scored_symbols)

            result = portfolio.execute_rebalance(
                price_data, fundamentals, news_data, macro_data, industry_map
            )

            logger.info(f"Rebalance result: {result['action']}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Rebalance: {result['action']}")

        except Exception as e:
            logger.error(f"Rebalance failed: {e}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Rebalance FAILED: {e}")

    def _run_daily_equity(self):
        """Update daily equity tracking and check drawdown triggers."""
        logger.info("Daily equity update starting")
        try:
            db, broker, signal, portfolio, notifier = self._init_pipeline()
            portfolio.update_equity_tracking()
            logger.info("Daily equity updated")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Equity tracking updated")

        except Exception as e:
            logger.error(f"Equity update failed: {e}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Equity update FAILED: {e}")

    def _run_weekly_summary(self):
        """Send weekly summary email."""
        logger.info("Weekly summary starting")
        try:
            from trading.db import TradingDatabase
            from trading.notifications import NotificationManager

            db = TradingDatabase()
            notifier = NotificationManager()

            if notifier._is_configured():
                notifier.notify_weekly_summary(db)
                logger.info("Weekly summary sent")
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Weekly summary email sent")
            else:
                logger.debug("Notifications not configured, skipping weekly summary")

        except Exception as e:
            logger.error(f"Weekly summary failed: {e}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Weekly summary FAILED: {e}")
