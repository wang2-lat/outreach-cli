"""Unit tests for Layer 5: Trade Journal & Database."""

import unittest
from trading.db import TradingDatabase


class TestTradeJournal(unittest.TestCase):

    def setUp(self):
        self.db = TradingDatabase(":memory:")

    # ------------------------------------------------------------------
    # 1. All required fields are recorded on entry
    # ------------------------------------------------------------------
    def test_entry_records_all_fields(self):
        """Trade entry must record symbol, side, qty, price, stop, signal."""
        tid = self.db.record_entry(
            symbol="AAPL",
            side="buy",
            quantity=100,
            entry_price=150.0,
            stop_loss_price=147.0,
            signal_type="momentum",
        )

        trades = self.db.get_open_trades()
        self.assertEqual(len(trades), 1)

        t = trades[0]
        self.assertEqual(t["symbol"], "AAPL")
        self.assertEqual(t["side"], "buy")
        self.assertEqual(t["quantity"], 100)
        self.assertEqual(t["entry_price"], 150.0)
        self.assertEqual(t["stop_loss_price"], 147.0)
        self.assertEqual(t["signal_type"], "momentum")
        self.assertIsNotNone(t["entry_time"])

    # ------------------------------------------------------------------
    # 2. Exit records signal and reason
    # ------------------------------------------------------------------
    def test_exit_records_reason_and_pnl(self):
        """Trade exit must record exit_reason and calculate P&L."""
        tid = self.db.record_entry("AAPL", "buy", 100, 150.0, 147.0, "momentum")
        self.db.record_exit(tid, exit_price=155.0, exit_reason="take_profit", slippage=0.5)

        closed = self.db.get_closed_trades()
        self.assertEqual(len(closed), 1)

        t = closed[0]
        self.assertEqual(t["exit_reason"], "take_profit")
        self.assertIsNotNone(t["exit_time"])
        self.assertAlmostEqual(t["pnl"], 500.0)  # (155-150)*100
        self.assertEqual(t["slippage"], 0.5)

    def test_exit_stop_loss_reason(self):
        """Stop-loss exit should record 'stop_loss' as reason."""
        tid = self.db.record_entry("MSFT", "buy", 50, 300.0, 294.0, "value")
        self.db.record_exit(tid, exit_price=294.0, exit_reason="stop_loss")

        closed = self.db.get_closed_trades()
        self.assertEqual(closed[0]["exit_reason"], "stop_loss")
        self.assertAlmostEqual(closed[0]["pnl"], -300.0)  # (294-300)*50

    def test_exit_rebalance_reason(self):
        """Rebalance exit should record 'rebalance' as reason."""
        tid = self.db.record_entry("GOOG", "buy", 20, 140.0, 137.0, "quality")
        self.db.record_exit(tid, exit_price=145.0, exit_reason="rebalance")

        closed = self.db.get_closed_trades()
        self.assertEqual(closed[0]["exit_reason"], "rebalance")

    # ------------------------------------------------------------------
    # 3. Open vs closed trade queries
    # ------------------------------------------------------------------
    def test_open_and_closed_separation(self):
        """Open and closed trades should be queried separately."""
        tid1 = self.db.record_entry("AAPL", "buy", 100, 150.0, 147.0, "momentum")
        tid2 = self.db.record_entry("MSFT", "buy", 50, 300.0, 294.0, "value")
        self.db.record_exit(tid1, 155.0, "take_profit")

        open_trades = self.db.get_open_trades()
        closed_trades = self.db.get_closed_trades()

        self.assertEqual(len(open_trades), 1)
        self.assertEqual(open_trades[0]["symbol"], "MSFT")
        self.assertEqual(len(closed_trades), 1)
        self.assertEqual(closed_trades[0]["symbol"], "AAPL")

    # ------------------------------------------------------------------
    # 4. Factor attribution stored
    # ------------------------------------------------------------------
    def test_factor_attribution_stored(self):
        """Factor attribution JSON should be stored on exit."""
        tid = self.db.record_entry("AAPL", "buy", 100, 150.0, 147.0, "momentum")
        self.db.record_exit(
            tid, 155.0, "take_profit",
            factor_attribution={"momentum": 0.5, "value": 0.3, "quality": 0.2}
        )

        closed = self.db.get_closed_trades()
        self.assertIsNotNone(closed[0]["factor_attribution"])
        self.assertIn("momentum", closed[0]["factor_attribution"])

    # ------------------------------------------------------------------
    # 5. Risk events
    # ------------------------------------------------------------------
    def test_risk_event_recorded(self):
        """Risk events should be stored and retrievable."""
        self.db.record_risk_event("stop_loss", "AAPL hit stop", "AAPL", 95000.0)
        events = self.db.get_recent_risk_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "stop_loss")
        self.assertEqual(events[0]["symbol"], "AAPL")

    # ------------------------------------------------------------------
    # 6. Daily equity tracking
    # ------------------------------------------------------------------
    def test_daily_equity_recorded(self):
        """Daily equity snapshots should be stored."""
        self.db.record_daily_equity("2024-01-15", 100000.0, 100000.0, 0.0)
        self.db.record_daily_equity("2024-01-16", 99000.0, 100000.0, 0.01)

        series = self.db.get_equity_series(365)
        self.assertEqual(len(series), 2)
        self.assertAlmostEqual(series[1]["drawdown_pct"], 0.01)

    # ------------------------------------------------------------------
    # 7. Factor scores stored
    # ------------------------------------------------------------------
    def test_factor_scores_stored(self):
        """Factor scores should be stored per symbol per date."""
        self.db.save_factor_scores(
            "2024-01-15", "AAPL",
            momentum=0.8, value=0.5, quality=0.7,
            sentiment=0.3, macro=0.9, composite=0.65
        )
        # No error = success. We can also verify via direct query.
        conn = self.db._conn()
        rows = conn.execute("SELECT * FROM factor_scores WHERE symbol='AAPL'").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["composite_score"], 0.65)

    # ------------------------------------------------------------------
    # 8. Sell trade P&L calculation
    # ------------------------------------------------------------------
    def test_short_sell_pnl_calculation(self):
        """Sell-side P&L should be calculated correctly (price drop = profit)."""
        tid = self.db.record_entry("TSLA", "sell", 50, 200.0, 210.0, "momentum")
        self.db.record_exit(tid, exit_price=180.0, exit_reason="take_profit")

        closed = self.db.get_closed_trades()
        # For sell: pnl = (entry - exit) * qty = (200-180)*50 = 1000
        self.assertAlmostEqual(closed[0]["pnl"], 1000.0)


if __name__ == "__main__":
    unittest.main()
