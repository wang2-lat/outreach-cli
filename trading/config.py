"""Central configuration for the trading system.

All strategy parameters are defined here. Total parameter count is kept
under 10 to avoid overfitting (see backtester validation).
"""

# ---------------------------------------------------------------------------
# Risk Control (Layer 1) — These are HARD limits, never relaxed at runtime
# ---------------------------------------------------------------------------

# Maximum loss on any single trade as a fraction of total equity.
# This is the iron rule — Renaissance-grade granularity.
MAX_LOSS_PER_TRADE_PCT = 0.02  # 2%

# Maximum position size for a single stock as a fraction of total equity.
MAX_POSITION_PCT = 0.05  # 5%

# Maximum exposure to a single GICS industry as a fraction of total equity.
MAX_INDUSTRY_PCT = 0.20  # 20%

# Target portfolio breadth.
MIN_POSITIONS = 15
MAX_POSITIONS = 25

# Portfolio-level drawdown circuit breakers.
WEEKLY_DRAWDOWN_LIMIT = 0.05   # 5% weekly → reduce to 50% exposure
TOTAL_DRAWDOWN_LIMIT = 0.15    # 15% from peak → full liquidation + pause

# Leverage — hardcoded False.  There is intentionally NO setter or toggle.
USE_LEVERAGE = False

# ---------------------------------------------------------------------------
# Trading Frequency (Layer 2)
# ---------------------------------------------------------------------------

# Minimum holding period in trading days.
MIN_HOLD_DAYS = 5

# Target holding period range (weeks).  For reference only — not enforced as
# a hard sell rule, but the rebalance cadence naturally targets this range.
TARGET_HOLD_WEEKS_MIN = 1
TARGET_HOLD_WEEKS_MAX = 12

# Maximum new positions opened per calendar week.
MAX_NEW_POSITIONS_PER_WEEK = 5

# Mandatory cooldown after any stop-loss event (hours).
COOLDOWN_HOURS_AFTER_STOP_LOSS = 24

# ---------------------------------------------------------------------------
# Factor Weights (Layer 3) — must sum to 1.0
# ---------------------------------------------------------------------------

FACTOR_WEIGHT_MOMENTUM = 0.30
FACTOR_WEIGHT_VALUE = 0.25
FACTOR_WEIGHT_QUALITY = 0.20
FACTOR_WEIGHT_SENTIMENT = 0.15
FACTOR_WEIGHT_MACRO = 0.10

# Momentum look-back in months, skipping the most recent month to avoid
# short-term reversal (Jegadeesh & Titman, 1993).
MOMENTUM_LOOKBACK_MONTHS = 12
MOMENTUM_SKIP_MONTHS = 1

# VIX threshold — no new positions opened above this level.
VIX_THRESHOLD = 35

# ---------------------------------------------------------------------------
# Rebalancing
# ---------------------------------------------------------------------------

# Rebalance cadence in calendar days.
REBALANCE_INTERVAL_DAYS = 14  # every 2 weeks

# Minimum expected improvement (in score points) to justify a rebalance
# after accounting for estimated transaction costs.
MIN_REBALANCE_IMPROVEMENT = 0.005

# Estimated round-trip transaction cost (slippage + spread) as a fraction
# of trade value.  Used to decide whether a rebalance is worth executing.
ESTIMATED_TRANSACTION_COST_PCT = 0.001  # 10 bps round-trip

# ---------------------------------------------------------------------------
# Backtesting (Layer 4)
# ---------------------------------------------------------------------------

BACKTEST_MIN_YEARS = 5
BACKTEST_TRAIN_PCT = 0.70   # 70% in-sample, 30% out-of-sample
BACKTEST_MIN_TRADES = 200
BACKTEST_MAX_STRATEGY_PARAMS = 10
BACKTEST_SLIPPAGE_PCT = 0.001  # 10 bps per leg

# ---------------------------------------------------------------------------
# Benchmarks (Layer 7)
# ---------------------------------------------------------------------------

BENCHMARK_SYMBOL = "SPY"
TARGET_SHARPE_RATIO = 1.0
TARGET_MAX_DRAWDOWN = 0.20      # 20%
TARGET_WIN_RATE = 0.45           # 45%
TARGET_PROFIT_FACTOR = 1.5       # avg win / avg loss
PAPER_TRADING_MIN_DAYS = 90      # 3 months minimum paper trading

# ---------------------------------------------------------------------------
# Broker
# ---------------------------------------------------------------------------

ALPACA_PAPER = True  # Always start in paper mode

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

TRADING_DB_PATH = "trading.db"
