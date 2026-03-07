# SwingRider Hybrid Model — Specification

**Branch**: `feature/swingrider-hybrid`
**Date**: February 28, 2026
**Status**: Implementation in progress

---

## Design Philosophy

Combine the **proven Range Bar entry pattern** (52.6% WR) with the **superior daily Chandelier exit system** (multi-day trending holds) to create a convex swing trading system for GBPJPY.

**Key Insight**: The original convex design exit system is excellent. The problem was entry quality. Solution: Use proven TrendRider-style Range Bar resumption entry, but gate it with daily regime filter and extend hold time with daily Chandelier.

---

## System Identity

| Parameter | Value |
|-----------|-------|
| Pair | GBPJPY only |
| Strategy Role | Convex Swing Amplifier |
| Entry Timeframe | **Range Bar (20-pip)** |
| Exit Timeframe | **Daily** |
| Entry Pattern | **Resumption bar** (TrendRider-style) |
| Entry Gate | Daily EMA50 regime filter |
| Max Positions | 1 |
| Risk per Trade | 0.7% |
| Initial SL | Swing-based (staircase depth × 1.5-2.5 bars, typically 200-400 pips) |
| Partial Exit | 2R @ 40% → move SL to BE+0.2R |
| Runner Exit | **Daily Chandelier** (ATR22 × 3.0, or 2.2 during volatility expansion) |
| Expected Trades | 8-15 per year |
| Expected Win Rate | 40-50% |
| Expected Avg Win | 2.5R-4.5R |

---

## Entry Logic (Hybrid)

### Step 1: Daily Regime Filter (Gate)

**Purpose**: Only allow trades when daily chart shows clear directional bias.

**Long Conditions**:
- Price above EMA50 on daily chart
- EMA50 slope upward (compare last 5 days)
- Market structure: HH + HL pattern (last 10 days)

**Short Conditions**:
- Price below EMA50 on daily chart
- EMA50 slope downward
- Market structure: LL + LH pattern

**If regime filter fails**: No entry allowed (skip Range Bar signal)

---

### Step 2: Range Bar Resumption Entry (TrendRider Pattern)

**Purpose**: Use proven entry pattern (52.6% WR from Phase 3.6).

**Entry Conditions** (same as TrendRider):
1. **Staircase detected**: 5+ consecutive trend-direction Range Bars (impulse)
2. **Pullback detected**: 2-4 counter-trend bars (consolidation)
3. **Resumption bar**: First trend-direction bar after pullback (entry trigger)

**Entry Price**: Close of resumption Range Bar

**Direction**: Determined by staircase direction (BUY if upward staircase, SELL if downward)

---

### Step 3: Swing SL Placement (NOT 60 pips)

**Purpose**: Use swing-based SL for multi-day holds (not tight intraday SL).

**SL Calculation**:
```
SL Distance = Staircase Depth × SL Multiplier × Bar Size

Where:
- Staircase Depth = Number of bars in impulse phase (5-15 typically)
- SL Multiplier = 1.5-2.5 (adaptive based on staircase strength)
- Bar Size = 20 pips (GBPJPY Range Bar size)
```

**Example**:
- Staircase of 8 bars
- SL Multiplier = 2.0 (moderate strength)
- SL Distance = 8 × 2.0 × 20 = 320 pips

**Adaptive Multiplier**:
- Strong staircase (10+ bars): 1.5× (tighter)
- Moderate staircase (7-9 bars): 2.0× (medium)
- Weak staircase (5-6 bars): 2.5× (wider)

**Typical SL Range**: 200-400 pips (swing-sized, not 60 pips)

---

### Step 4: Additional Entry Gates

**Optional Weekly Pivot Filter**:
- Long trades: Price above weekly pivot
- Short trades: Price below weekly pivot
- **Config**: `SWINGRIDER_WEEKLY_PIVOT_FILTER_ENABLED = True`

**Session Filter** (from TrendRider):
- Respect TrendRider session preferences (London/NY preferred)
- Block Tokyo-only entries (unless configured otherwise)

**Price Level Cooldown**:
- Apply existing ±20 pip, 4-hour cooldown
- Prevent revenge trading near recent losses

---

## Exit Logic (Daily Chandelier)

### Partial Exit: 2R @ 40%

**When**: Price reaches entry + 2R distance (NOT 1.5R like TrendRider)
**Action**: Close 40% of position (keep 60% as runner)
**SL Move**: Move SL to BE + 0.2R (protects runner)

**Example**:
- Entry: 195.00, SL: 191.00 (400 pips = 1R)
- 2R Target: 195.00 + 8.00 = 203.00
- When 203.00 hit: Close 40%, move SL to 195.80 (BE + 0.2R)

---

### Runner Exit: Daily Chandelier

**Update Frequency**: **Once per daily close** (NOT every Range Bar)

**Calculation**:
```
Daily Chandelier SL = Highest High (since entry) - (ATR22 × Multiplier)

Where:
- ATR22 = Average True Range on daily chart (22 periods)
- Multiplier = 3.0 (normal) or 2.2 (volatility expansion)
```

**Volatility Expansion Trigger** (Accelerator):
- ATR(14) > 1.5 × 20-day ATR average AND
- Daily range > 1.8 × 20-day average range
- **Action**: Tighten multiplier from 3.0 to 2.2 (27% tighter)

**SL Movement Rule**: Only tighten (never move backwards)

---

### Hard Invalidation (Forced Exit)

**Rare structural exits** (emergency only):

**Triggers**:
1. **Opposite structure break**: New LL in uptrend, new HH in downtrend (on daily chart)
2. **EMA50 penetration**: Close through EMA50 with momentum (> 0.5×ATR penetration)

**Action**: Force-close runner immediately (at current bar close)

**Expected Frequency**: <5 per year (should be rare)

---

## Configuration Parameters

### New Config Values (`src/config.py`)

```python
# SwingRider Hybrid Model (Range Bar Entry + Daily Chandelier Exit)
SWINGRIDER_HYBRID_ENABLED = True

# Entry: Range Bar resumption (TrendRider pattern)
SWINGRIDER_MIN_STAIRCASE_DEPTH = 5  # Min impulse bars
SWINGRIDER_MIN_PULLBACK_BARS = 2
SWINGRIDER_MAX_PULLBACK_BARS = 4

# SL: Swing-based (NOT 60 pips)
SWINGRIDER_SL_MULTIPLIER_STRONG = 1.5   # Staircase >= 10 bars
SWINGRIDER_SL_MULTIPLIER_MEDIUM = 2.0   # Staircase 7-9 bars
SWINGRIDER_SL_MULTIPLIER_WEAK = 2.5     # Staircase 5-6 bars
SWINGRIDER_SL_MIN_PIPS = 200            # Minimum SL (prevent too tight)
SWINGRIDER_SL_MAX_PIPS = 500            # Maximum SL (prevent too wide)

# Daily regime filter (entry gate)
SWINGRIDER_DAILY_REGIME_FILTER_ENABLED = True
SWINGRIDER_DAILY_EMA_PERIOD = 50

# Exit: Daily Chandelier (same as original)
SWINGRIDER_PARTIAL_EXIT_R = 2.0
SWINGRIDER_PARTIAL_EXIT_PCT = 0.40
SWINGRIDER_PARTIAL_SL_OFFSET_R = 0.2
SWINGRIDER_CHANDELIER_ATR_PERIOD = 22
SWINGRIDER_CHANDELIER_MULTIPLIER_NORMAL = 3.0
SWINGRIDER_CHANDELIER_MULTIPLIER_EXPANSION = 2.2

# Volatility expansion accelerator
SWINGRIDER_VOLATILITY_ATR_THRESHOLD = 1.5
SWINGRIDER_VOLATILITY_RANGE_THRESHOLD = 1.8

# Hard invalidation
SWINGRIDER_HARD_INVALIDATION_ENABLED = True

# Optional filters
SWINGRIDER_WEEKLY_PIVOT_FILTER_ENABLED = False  # Optional (test with/without)
```

---

## Expected Performance Profile

### Target Metrics (Based on Hybrid Design)

| Metric | Target | Rationale |
|--------|--------|-----------|
| **Trades/Year** | 8-15 | Range Bar entry (more frequent than daily pullback) gated by daily regime (less frequent than pure TrendRider) |
| **Win Rate** | 40-50% | Range Bar entry quality (52.6% proven) minus daily gate selectivity |
| **Avg R/Winner** | 2.5R-4.5R | Daily Chandelier allows multi-day holds (larger than 1.61R from Range Bar baseline) |
| **Avg R/Loser** | -1.0R | Full SL hit (same as baseline) |
| **Largest Winners** | 6R-10R | Daily Chandelier captures full trend moves (vs Range Bar tight trailing) |
| **Typical Hold** | 3-10 days | Multi-day swings (vs 1-3 days for TrendRider) |
| **Convexity** | 30-40% of profit from top 3 trades | Daily Chandelier creates fat tail wins |

### Comparison to Baselines

| Metric | Range Bar Baseline | Original Convex | Hybrid Target |
|--------|-------------------|-----------------|---------------|
| **Entry Pattern** | Resumption bar | Daily pullback + H4 trigger | **Resumption bar** |
| **Entry Gate** | DCRD CS 60-100 | Daily EMA50 + structure | **Daily EMA50** |
| **SL Size** | 60 pips | 400-730 pips | **200-400 pips** |
| **Runner Exit** | Range Bar trailing | Daily Chandelier | **Daily Chandelier** |
| **Win Rate** | 52.6% | 16.7% | **40-50%** |
| **Avg Winner** | 1.61R | 1.45R | **2.5R-4.5R** |
| **Trades/Year** | ~57 | 4 | **8-15** |
| **Expected R** | Positive | Negative | **Positive** |

---

## Implementation Checklist

### Phase 1: Strategy Rewrite

- [x] Modify `src/strategies/swing_rider.py`:
  - [x] Add daily regime filter check (call helper functions)
  - [x] Use Range Bar resumption entry (copy from TrendRider)
  - [x] Calculate swing SL (staircase depth × multiplier × bar size)
  - [x] Return signal with swing_level for tracking

### Phase 2: Config Updates

- [x] Update `src/config.py`:
  - [x] Add hybrid-specific parameters
  - [x] Keep daily Chandelier config (already exists)

### Phase 3: Exit System (Already Implemented)

- [x] Daily Chandelier exit logic (already in `backtester/engine.py`)
- [x] Volatility expansion accelerator (already implemented)
- [x] Hard invalidation checks (already implemented)
- [x] BE+0.2R after partial (already in `backtester/account.py`)

### Phase 4: Testing

- [ ] Run backtest on 1.5-year GBPJPY data (July 2024 - Feb 2026)
- [ ] Validate win rate 40-50%
- [ ] Validate avg R/winner > 2.0R
- [ ] Compare to Range Bar baseline and original convex
- [ ] Check trade frequency (target 8-15/year)

---

## Success Criteria

### Minimum Viable Performance (1.5-Year Test)

✅ **Net profit positive**
✅ **Win rate > 35%** (better than original 16.7%)
✅ **Avg R/winner > 2.0R** (better than Range Bar 1.61R)
✅ **Trade frequency 6-12** (8-15/year × 1.5 years)
✅ **At least 1 large winner > 4R** (convexity proof)

### Gate for Full Validation (7-Year Test, When Data Available)

✅ **Net profit positive over 7 years**
✅ **Win rate 40-50%**
✅ **Sharpe > 1.0**
✅ **Max DD < 25%** (acceptable for convex system)
✅ **Top 3 trades = 30-40% of profit** (convexity validation)

---

## Risk Mitigation

### Risk 1: Win Rate Still Too Low

**Symptom**: Win rate < 35% (similar to original)
**Diagnosis**: Daily regime filter too restrictive (blocking good Range Bar signals)
**Mitigation**: Make daily regime filter optional (test with/without)

### Risk 2: Avg R/Winner Not Improving

**Symptom**: Avg R/winner < 2.0R (similar to Range Bar baseline)
**Diagnosis**: Daily Chandelier exiting too early
**Mitigation**: Test wider multiplier (3.5× instead of 3.0×)

### Risk 3: Trade Frequency Too Low

**Symptom**: < 6 trades in 1.5 years (< 4/year)
**Diagnosis**: Daily regime filter + Range Bar combo too selective
**Mitigation**: Relax daily regime requirements (e.g., remove market structure check)

### Risk 4: SL Sizes Too Wide (Drawdown Risk)

**Symptom**: Max DD > 30% due to large SLs (200-400 pips)
**Diagnosis**: Swing SL multipliers too aggressive
**Mitigation**: Reduce SL multipliers (1.5× max) or cap SL at 300 pips

---

## Conclusion

The hybrid approach is the **optimal middle ground**:

- Uses **proven entry pattern** (Range Bar resumption, 52.6% WR)
- Adds **daily regime quality gate** (filter weak signals)
- Extends **hold time via daily Chandelier** (capture larger moves)
- Creates **convex profit profile** (fat tail winners from multi-day holds)

**Expected Result**: 40-50% WR, 2.5R-4.5R avg winners, 8-15 trades/year, positive expectancy with convexity.

---

**Status**: Ready to implement ✅
