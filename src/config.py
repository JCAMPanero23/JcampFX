"""
JcampFX — Pair universe and Range Bar configuration.
Single source of truth for pair-level constants referenced across all modules.

Canonical vs broker symbols
----------------------------
All internal logic, file names, and config keys use *canonical* names
(e.g. "EURUSD").  FP Markets ECN appends ".r" to every instrument symbol
in MT5.  Use `mt5_symbol(pair)` whenever calling the MetaTrader5 package.

    mt5_symbol("EURUSD")  → "EURUSD.r"
"""


def mt5_symbol(canonical: str) -> str:
    """Return the broker-suffixed MT5 symbol for a canonical pair name."""
    return canonical + MT5_SUFFIX


def broker_symbol(canonical: str, platform: str = "mt5") -> str:
    """
    Return the broker-suffixed symbol for a given platform.

    Args:
        canonical: Canonical pair name (e.g., "EURUSD")
        platform: Trading platform ("mt5" or "ctrader")

    Returns:
        Broker-specific symbol name with suffix
    """
    if platform.lower() == "ctrader":
        return canonical + CTRADER_SUFFIX
    else:
        return canonical + MT5_SUFFIX


def strip_broker_suffix(symbol: str) -> str:
    """
    Strip broker suffix from symbol name to get canonical name.
    Handles both MT5 (.r) and cTrader (TBD) suffixes.

    Args:
        symbol: Broker-specific symbol (e.g., "EURUSD.r" or "EURUSD.ct")

    Returns:
        Canonical symbol name (e.g., "EURUSD")
    """
    # Strip MT5 suffix
    if symbol.endswith(MT5_SUFFIX):
        return symbol[:-len(MT5_SUFFIX)]

    # Strip cTrader suffix
    if CTRADER_SUFFIX and symbol.endswith(CTRADER_SUFFIX):
        return symbol[:-len(CTRADER_SUFFIX)]

    # No suffix found - return as-is
    return symbol


# FP Markets ECN broker suffix applied to all MT5 instrument symbols
MT5_SUFFIX = ".r"

# cTrader suffix (TBD - check FP Markets cTrader account)
# Common options: ".ct", ".raw", or "" (no suffix)
# Update after checking Market Watch in cTrader
CTRADER_SUFFIX = ""  # Default: no suffix (most common)

# Pair universe (Gold unlocks at $2,000 equity)
# Phase 3.6: GBPUSD removed (negative R contribution: -8.05R, -$50 over 56 trades)
# Phase 3.6.1: AUDUSD tested and removed (25% WR, -3.80R over 12 trades)
# Phase 3.6.2: EURGBP tested and deferred (profitable +$17.76 but breached 20% DD gate by 0.6%)
#              → Set aside for post-demo optimization (separate branch)
# Phase 3.7: GBPJPY experimental (separate branch, NOT validated for production)
PAIRS = ["EURUSD", "USDJPY", "AUDJPY", "USDCHF"]
GOLD_PAIR = "XAUUSD"
GOLD_UNLOCK_EQUITY = 2000.0

# CSM 9-pair grid for Currency Strength Meter (PRD §3.2 — VD.7)
# Active 5 + 4 cross pairs covering EUR, GBP, USD, JPY, AUD, CHF
CSM_PAIRS = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDJPY", "USDCHF",
    "EURJPY", "GBPJPY", "EURGBP", "AUDUSD",
]

# Pip sizes (1 pip in price terms)
# JPY pairs: 1 pip = 0.01; all others: 1 pip = 0.0001
PIP_SIZE: dict[str, float] = {
    "EURUSD": 0.0001,
    "GBPUSD": 0.0001,
    "USDJPY": 0.01,
    "AUDJPY": 0.01,
    "USDCHF": 0.0001,
    "EURGBP": 0.0001,  # Phase 3.6.2: Experimental (deferred)
    "XAUUSD": 0.01,  # Gold: $0.01 per pip equivalent (1¢/oz)
    # CSM cross pairs
    "EURJPY": 0.01,
    "GBPJPY": 0.01,    # CSM only (not trading)
    "AUDUSD": 0.0001,
}

# Range Bar sizes in pips (Phase 3.5 — middle ground test)
# Majors: 15 pips; JPY pairs: 20 pips; Gold: 50 pips (unlocks at $2k)
# Compromise between swing (20/25) and intraday (10/15)
RANGE_BAR_PIPS: dict[str, int] = {
    "EURUSD": 15,
    "GBPUSD": 15,
    "USDJPY": 20,
    "AUDJPY": 20,
    "USDCHF": 15,
    "EURGBP": 12,  # Phase 3.6.2: Experimental (deferred)
    "XAUUSD": 50,  # Gold placeholder — not used until $2k
}

# MT5 data parameters
TICK_DATA_YEARS = 2          # Minimum history required (PRD §7.1)
M15_TIMEFRAME = "M15"        # Comparison overlay timeframe
TIMEFRAME_1H = "H1"          # 1H OHLC for DCRD Layer 2 (dynamic modifier)
TIMEFRAME_4H = "H4"          # 4H OHLC for DCRD Layer 1 (structural score)

# Broker cost model (PRD §1.2)
COMMISSION_PER_LOT_RT = 7.0  # USD round-trip per standard lot
SLIPPAGE_PIPS = 1.0          # Applied to every entry and exit in backtester

# Risk parameters
MIN_RISK_PCT = 0.008          # 0.8% — skip trade below this (PRD §6.1)
BASE_RISK_PCT = 0.01          # 1.0% base risk (Phase 3.5 baseline - optimal)
MAX_RISK_PCT = 0.03           # 3.0% cap
MIN_LOT = 0.01                # MT5 minimum lot size
MAX_LOT = 5.0                 # Hard safety cap — prevents runaway compounding

# Portfolio limits (PRD §1.2)
MAX_CONCURRENT_POSITIONS = 5  # Phase 3.4: Increased to allow more simultaneous trades
MAX_CONCURRENT_UPGRADED = 5   # Same as base (already at max)
EQUITY_UPGRADE_THRESHOLD = 1000.0
MAX_DAILY_TRADES = 5
DAILY_LOSS_CAP_R = 2.0        # CLOSE_ALL + PAUSE at −2R/day

# Chandelier SL floors in pips (Phase 3.5 — adjusted for 15/20-pip bars)
CHANDELIER_FLOOR_MAJORS = 15  # EURUSD, GBPUSD, USDCHF (matches bar size)
CHANDELIER_FLOOR_JPY = 20     # USDJPY, AUDJPY (matches bar size)

JPY_PAIRS = {"USDJPY", "AUDJPY"}

# Weekend protection: minutes before Friday market close (PRD §10.4)
WEEKEND_CLOSE_MINUTES = 20

# News gating windows in minutes (PRD §4.2)
NEWS_HIGH_BLOCK_BEFORE = 30
NEWS_HIGH_BLOCK_AFTER = 15
NEWS_MEDIUM_BLOCK_BEFORE = 15
NEWS_MEDIUM_BLOCK_AFTER = 10
NEWS_POST_EVENT_COOL_MIN = 15
NEWS_POST_EVENT_MIN_CS = 80   # Only CS > 80 signals allowed during cool

# DCRD anti-flipping filter (PRD §3.6)
ANTI_FLIP_THRESHOLD_PTS = 10  # Phase 3.4: Reduced from 15 (allows CS=100 to cross CS≥90 boundary)
ANTI_FLIP_PERSISTENCE = 2     # Must persist for >= 2 consecutive 4H closes

# Strategy cooldown (PRD §10.3)
COOLDOWN_LOSSES_IN_WINDOW = 5     # Consecutive losses in last N trades
COOLDOWN_WINDOW = 10              # Rolling window size
COOLDOWN_HOURS = 24

# Price level cooldown (Phase 3.1.1 — revenge trade elimination)
PRICE_LEVEL_COOLDOWN_PIPS = 20      # Block re-entry within ±N pips of recent loss
PRICE_LEVEL_COOLDOWN_HOURS = 4      # Cooldown duration (configurable)
PRICE_LEVEL_TRACK_LOSSES_ONLY = True  # Only track losing trades (R < 0)

# Strategy regime boundaries
STRATEGY_TRENDRIDER_MIN_CS = 30  # Phase 3.4: Extended to Transitional regime (CS 30-100)
STRATEGY_BREAKOUTRIDER_MIN_CS = 999  # DISABLED (broken strategy, 0-4 trades, losing)
STRATEGY_RANGERIDER_MAX_CS = 30

# Phase 3.4 Filter 2: Session Quality (strengthened Tokyo filter)
# Entry quality analysis: Tokyo-only = 66.7% SL hit rate vs NY = 55.2%
# TrendRider now requires London or NY session (blocks Tokyo-only for ALL pairs)
FILTER_2_SESSION_QUALITY_ENABLED = True  # Set False to revert to old behavior

# Phase 3.4 Trade Frequency Optimization: TrendRider Extended + Pivot Filter
# Strategy: Extend TrendRider to CS≥30 (Transitional regime) + Pivot confluence filter
# BreakoutRider: DISABLED (broken, 0-4 trades, losing)
# PivotScalper: REVERTED (blocked TrendRider, wrong portfolio fit)
BREAKOUT_BB_COMPRESSION_PERCENTILE = 20  # Not used (BreakoutRider disabled)

# Pivot Level Filter for TrendRider (Optional quality enhancement)
TRENDRIDER_PIVOT_FILTER_ENABLED = False   # Disabled - pivot filter degraded results
TRENDRIDER_PIVOT_ZONE_PIPS = 10.0         # Distance to pivot level (S1/S2/R1/R2/Pivot)

# Partial exit regime thresholds (PRD §5.1)
PARTIAL_EXIT_TIERS = [
    (85, 0.60),   # CS > 85 → close 60%
    (70, 0.70),   # CS 70–85 → close 70%
    (30, 0.75),   # CS 30–70 → close 75%
    (0,  0.80),   # CS < 30  → close 80%
]
PARTIAL_EXIT_R = 1.5  # Stage 1 fires at 1.5R

# Data directories (relative to project root — callers use pathlib)
DATA_TICKS_DIR = "data/ticks"
DATA_RANGE_BARS_DIR = "data/range_bars"
DATA_OHLC_DIR = "data/ohlc"        # M15 (Phase 1 overlay)
DATA_OHLC_1H_DIR = "data/ohlc_1h"  # 1H for DCRD Layer 2
DATA_OHLC_4H_DIR = "data/ohlc_4h"  # 4H for DCRD Layer 1
DATA_NEWS_JSON = "data/news_events.json"
BACKTEST_RESULTS_DIR = "data/backtest_results"

# Walk-forward backtest structure (PRD §9.1)
WALK_FORWARD_TRAIN_MONTHS = 4   # In-sample period per cycle
WALK_FORWARD_TEST_MONTHS = 2    # Out-of-sample gate period per cycle
WALK_FORWARD_CYCLES = 4         # Minimum cycles required

# Regime deterioration (v2.2, PRD §3.7 + §9.2)
REGIME_DETERIORATION_THRESHOLD = 40  # Force-close runner if CS drops > this many pts from entry

# DCRD calibration (v2.2, PRD §4.5)
DCRD_CONFIG_PATH = "data/dcrd_config.json"  # Generated by calibration script

# Phantom detection (v2.2, PRD §8)
PHANTOM_DETECTION_ENABLED = True  # Block entries on is_phantom bars

# Session filter (v2.2, PRD §6.2) — UTC hours
SESSION_TOKYO_START = 0
SESSION_TOKYO_END = 9
SESSION_LONDON_START = 7
SESSION_LONDON_END = 16
SESSION_NY_START = 12
SESSION_NY_END = 21
SESSION_OVERLAP_START = 12    # London/NY overlap
SESSION_OVERLAP_END = 16
SESSION_OFF_HOURS_START = 21  # Low-liquidity window
SESSION_OFF_HOURS_END = 0     # Wraps midnight

# ===================================================================
# Phase 3.7: SwingRider Hybrid Model (Range Bar Entry + Daily Chandelier Exit)
# ===================================================================
# Combines proven Range Bar resumption entry (52.6% WR) with superior daily Chandelier exit
# Target: 40-50% WR, 2.5R-4.5R avg wins, 8-15 trades/year, convex profit profile

# Core identity
SWINGRIDER_BASE_RISK_PCT = 0.007             # 0.7% per trade (lower than base 1.0%)
SWINGRIDER_MAX_CONCURRENT = 1                # Max 1 SwingRider trade at a time
SWINGRIDER_PORTFOLIO_DD_GATE = 15.0          # Disable SwingRider if portfolio DD > 15%

# Entry: Range Bar resumption (TrendRider pattern)
SWINGRIDER_MIN_STAIRCASE_DEPTH = 5           # Min impulse bars required

# Daily regime filter (entry gate)
SWINGRIDER_DAILY_REGIME_FILTER_ENABLED = False  # DISABLED: Too restrictive (test without filter first)
SWINGRIDER_DAILY_EMA_PERIOD = 50             # EMA50 regime filter (price above/below + slope)

# SL: Swing-based (adaptive, NOT 60 pips)
# SL Distance = Staircase Depth × Multiplier × Bar Size (20 pips)
# Multipliers are adaptive based on staircase strength
SWINGRIDER_SL_MULTIPLIER_STRONG = 1.5        # Staircase >= 10 bars (tight)
SWINGRIDER_SL_MULTIPLIER_MEDIUM = 2.0        # Staircase 7-9 bars (medium)
SWINGRIDER_SL_MULTIPLIER_WEAK = 2.5          # Staircase 5-6 bars (wide)
SWINGRIDER_SL_MIN_PIPS = 200                 # Minimum SL (prevent too tight)
SWINGRIDER_SL_MAX_PIPS = 500                 # Maximum SL (prevent too wide)

# Partial exit + runner protection
SWINGRIDER_PARTIAL_EXIT_R = 2.0              # Partial exit at 2R (NOT 1.5R)
SWINGRIDER_PARTIAL_EXIT_PCT = 0.40           # Close 40% at 2R
SWINGRIDER_PARTIAL_SL_OFFSET_R = 0.2         # Move SL to BE + 0.2R after partial

# Daily Chandelier exit (NOT Range Bar trailing)
SWINGRIDER_CHANDELIER_ATR_PERIOD = 22
SWINGRIDER_CHANDELIER_MULTIPLIER_NORMAL = 3.0       # Normal Chandelier: ATR22 × 3.0
SWINGRIDER_CHANDELIER_MULTIPLIER_EXPANSION = 2.2    # Volatility expansion: ATR22 × 2.2

# Volatility expansion accelerator thresholds
SWINGRIDER_VOLATILITY_ATR_THRESHOLD = 1.5    # ATR(14) > 1.5 × 20-day ATR avg
SWINGRIDER_VOLATILITY_RANGE_THRESHOLD = 1.8  # Daily range > 1.8 × 20-day avg range
SWINGRIDER_VOLATILITY_LOOKBACK_DAYS = 20     # Rolling window for avg calculations

# Hard invalidation (rare structural exits)
SWINGRIDER_HARD_INVALIDATION_ENABLED = True
SWINGRIDER_INVALIDATION_STRUCTURE_LOOKBACK = 6  # Bars to check for opposite structure
SWINGRIDER_INVALIDATION_EMA_ATR_BUFFER = 0.5    # EMA50 penetration threshold (0.5×ATR)
