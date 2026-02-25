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


# FP Markets ECN broker suffix applied to all MT5 instrument symbols
MT5_SUFFIX = ".r"

# Pair universe (Gold unlocks at $2,000 equity)
PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "AUDJPY", "USDCHF"]
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
    "XAUUSD": 0.01,  # Gold: $0.01 per pip equivalent (1¢/oz)
    # CSM cross pairs
    "EURJPY": 0.01,
    "GBPJPY": 0.01,
    "EURGBP": 0.0001,
    "AUDUSD": 0.0001,
}

# Range Bar sizes in pips (v2.2 — 20-pip migration, PRD §7.3)
# Majors: 20 pips; JPY pairs: 25 pips; Gold: 50 pips (unlocks at $2k)
RANGE_BAR_PIPS: dict[str, int] = {
    "EURUSD": 20,
    "GBPUSD": 20,
    "USDJPY": 25,
    "AUDJPY": 25,
    "USDCHF": 20,
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
BASE_RISK_PCT = 0.01          # 1.0% base risk
MAX_RISK_PCT = 0.03           # 3.0% cap
MIN_LOT = 0.01                # MT5 minimum lot size
MAX_LOT = 5.0                 # Hard safety cap — prevents runaway compounding

# Portfolio limits (PRD §1.2)
MAX_CONCURRENT_POSITIONS = 2
MAX_CONCURRENT_UPGRADED = 3   # Unlocks when equity > $1,000
EQUITY_UPGRADE_THRESHOLD = 1000.0
MAX_DAILY_TRADES = 5
DAILY_LOSS_CAP_R = 2.0        # CLOSE_ALL + PAUSE at −2R/day

# Chandelier SL floors in pips (PRD §5.1)
CHANDELIER_FLOOR_MAJORS = 15  # EURUSD, GBPUSD, USDCHF
CHANDELIER_FLOOR_JPY = 25     # USDJPY, AUDJPY

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
STRATEGY_TRENDRIDER_MIN_CS = 90  # Phase 3.4: Raised from 70 (avg winner CS = 95.5)
STRATEGY_BREAKOUTRIDER_MIN_CS = 30
STRATEGY_RANGERIDER_MAX_CS = 30

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
