"""Email notification system for trading events.

Sends email alerts on: trade execution, stop-loss triggers,
risk alerts (drawdown), and weekly summary reports.

Configure via environment variables:
  TRADING_NOTIFICATIONS_ENABLED=true
  TRADING_SMTP_HOST=smtp.gmail.com
  TRADING_SMTP_PORT=587
  TRADING_SMTP_USER=your@gmail.com
  TRADING_SMTP_PASS=your-app-password
  TRADING_NOTIFY_EMAIL=recipient@example.com
"""

import os
import smtplib
import logging
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from trading.db import TradingDatabase

logger = logging.getLogger(__name__)


class NotificationManager:
    """SMTP-based email notification manager for trading events."""

    def __init__(self):
        self.enabled = os.environ.get(
            "TRADING_NOTIFICATIONS_ENABLED", "false"
        ).lower() == "true"
        self.smtp_host = os.environ.get("TRADING_SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.environ.get("TRADING_SMTP_PORT", "587"))
        self.smtp_user = os.environ.get("TRADING_SMTP_USER", "")
        self.smtp_pass = os.environ.get("TRADING_SMTP_PASS", "")
        self.recipient = os.environ.get("TRADING_NOTIFY_EMAIL", "")

    def _is_configured(self) -> bool:
        """Check if SMTP is properly configured."""
        return bool(self.enabled and self.smtp_user and self.smtp_pass and self.recipient)

    def send(self, subject: str, body: str) -> bool:
        """Send an email. Returns True on success, False on failure.

        Never raises — email failures must not crash the trading pipeline.
        """
        if not self._is_configured():
            logger.debug("Notifications disabled or not configured, skipping")
            return False

        try:
            msg = MIMEMultipart()
            msg["From"] = self.smtp_user
            msg["To"] = self.recipient
            msg["Subject"] = f"[Trading Bot] {subject}"

            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_pass)
                server.send_message(msg)

            logger.info(f"Email sent: {subject}")
            return True

        except Exception as e:
            logger.warning(f"Failed to send email '{subject}': {e}")
            return False

    # ------------------------------------------------------------------
    # Event-specific notifications
    # ------------------------------------------------------------------

    def notify_trade(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        stop_loss: Optional[float] = None,
    ):
        """Notify on trade execution (buy or sell)."""
        action = "BOUGHT" if side == "buy" else "SOLD"
        value = quantity * price
        subject = f"{action} {int(quantity)} {symbol} @ ${price:.2f}"
        body = (
            f"Trade Executed\n"
            f"{'='*40}\n"
            f"Action: {action}\n"
            f"Symbol: {symbol}\n"
            f"Quantity: {int(quantity)}\n"
            f"Price: ${price:.2f}\n"
            f"Value: ${value:,.2f}\n"
        )
        if stop_loss and side == "buy":
            body += f"Stop Loss: ${stop_loss:.2f}\n"
            max_loss = (price - stop_loss) * quantity
            body += f"Max Loss: ${max_loss:,.2f}\n"
        body += f"\nTime: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        self.send(subject, body)

    def notify_stop_loss(
        self,
        symbol: str,
        entry_price: float,
        stop_price: float,
    ):
        """Notify when a stop-loss is triggered."""
        loss_pct = (entry_price - stop_price) / entry_price * 100
        subject = f"STOP LOSS: {symbol} hit ${stop_price:.2f} (-{loss_pct:.1f}%)"
        body = (
            f"Stop Loss Triggered\n"
            f"{'='*40}\n"
            f"Symbol: {symbol}\n"
            f"Entry Price: ${entry_price:.2f}\n"
            f"Stop Price: ${stop_price:.2f}\n"
            f"Loss: {loss_pct:.1f}%\n"
            f"\n24-hour cooldown period is now active.\n"
            f"\nTime: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        )
        self.send(subject, body)

    def notify_risk_alert(
        self,
        event_type: str,
        details: str,
        equity: float,
    ):
        """Notify on risk events (drawdown triggers, VIX blocks, etc.)."""
        severity = "CRITICAL" if "total" in event_type.lower() else "WARNING"
        subject = f"{severity}: {event_type.replace('_', ' ').title()}"
        body = (
            f"Risk Alert\n"
            f"{'='*40}\n"
            f"Severity: {severity}\n"
            f"Event: {event_type}\n"
            f"Details: {details}\n"
            f"Current Equity: ${equity:,.2f}\n"
            f"\nTime: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        )
        self.send(subject, body)

    def notify_weekly_summary(self, db: TradingDatabase):
        """Send weekly portfolio summary."""
        subject = f"Weekly Summary — {datetime.utcnow().strftime('%Y-%m-%d')}"

        # Gather data
        open_trades = db.get_open_trades()
        closed_trades = db.get_closed_trades()
        equity_series = db.get_equity_series(7)
        risk_events = db.get_recent_risk_events(20)

        # Calculate stats
        week_closed = [
            t for t in closed_trades
            if t.get("exit_time") and
            (datetime.utcnow() - datetime.fromisoformat(t["exit_time"])).days <= 7
        ]
        week_pnl = sum(t.get("pnl", 0) for t in week_closed)
        wins = sum(1 for t in week_closed if t.get("pnl", 0) > 0)
        losses = sum(1 for t in week_closed if t.get("pnl", 0) <= 0)

        # Equity
        current_equity = equity_series[-1]["equity"] if equity_series else 0
        peak_equity = equity_series[-1]["peak_equity"] if equity_series else 0
        drawdown = equity_series[-1]["drawdown_pct"] if equity_series else 0

        # Risk events this week
        week_events = [
            e for e in risk_events
            if (datetime.utcnow() - datetime.fromisoformat(e["timestamp"])).days <= 7
        ]

        body = (
            f"Weekly Trading Summary\n"
            f"{'='*50}\n\n"
            f"Portfolio\n"
            f"  Current Equity: ${current_equity:,.2f}\n"
            f"  Peak Equity: ${peak_equity:,.2f}\n"
            f"  Drawdown: {drawdown:.1%}\n"
            f"  Open Positions: {len(open_trades)}\n\n"
            f"This Week\n"
            f"  Trades Closed: {len(week_closed)}\n"
            f"  P&L: ${week_pnl:,.2f}\n"
            f"  Wins: {wins} | Losses: {losses}\n\n"
        )

        if open_trades:
            body += "Open Positions\n"
            for t in open_trades:
                body += f"  {t['symbol']}: {t['quantity']} @ ${t['entry_price']:.2f} (stop: ${t['stop_loss_price']:.2f})\n"
            body += "\n"

        if week_events:
            body += f"Risk Events ({len(week_events)})\n"
            for e in week_events:
                body += f"  [{e['event_type']}] {e.get('details', '')[:60]}\n"

        body += f"\nGenerated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        self.send(subject, body)
