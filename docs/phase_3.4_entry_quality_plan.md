# Phase 3.4 — Entry Quality & DCRD Rebalancing Implementation Plan

**Date:** February 25, 2026
**Status:** PLANNING
**Goal:** Fix 62% SL hit rate + Enable all strategies to trade

---

## Executive Summary

**Current Baseline (Phase 3.2.2):**
- Net P&L: +$34.94 ✅
- Win Rate: 43.8%
- Total R: +6.30R
- Trades: 128 over 651 days
- **System is profitable but has two critical inefficiencies**

**Problem 1: Entry Quality (62% SL Hit Rate)**
- 62% of trades hit SL before reaching 1.5R partial exit
- Average loss on SL hits: -0.982R
- Only 38% reach partial exit (need 40%+ for consistent profit)
- **Impact:** Leaving money on the table, high capital turnover

**Problem 2: DCRD Concentration (89% TrendRider)**
- DCRD stays at CS≥70 for 89% of all opportunities
- TrendRider: 176 trades over 2 years
- BreakoutRider: **2 trades** over 2 years (99% idle)
- RangeRider: **0 trades** (100% idle)
- USDJPY: 47% of all trades (concentration risk)
- **Impact:** Portfolio not diversified, strategies underutilized

**Success Criteria:**
1. ✅ Win Rate ≥ 45% (currently 43.8%)
2. ✅ Partial-reach rate ≥ 42% (currently 38%)
3. ✅ Net P&L ≥ +$50 (currently +$34.94)
4. ✅ BreakoutRider ≥ 20 trades/2yr (currently 2)
5. ✅ RangeRider ≥ 10 trades/2yr (currently 0)
6. ✅ Max single-pair concentration ≤ 35% (currently 47% USDJPY)

---

## Phase 3.4.1 — Entry Quality Analysis (Week 1)

**Objective:** Understand WHY 62% of trades hit SL before 1.5R

### Task 1.1: Data Collection & Segmentation

**Create Entry Quality Analyzer Script:**
```python
# src/analysis/entry_quality_analyzer.py

def analyze_entry_quality(trades_df, range_bars_dict):
    """
    Analyze all SL_HIT trades to identify common failure patterns.

    Metrics to calculate:
    1. Pullback depth (how far price pulled back before entry)
    2. Entry bar position (where in bar did we enter - open/mid/close)
    3. SL distance in R (is 60 pips appropriate for all conditions?)
    4. ATR at entry (volatility context)
    5. Time to SL (immediate vs gradual)
    6. Session (Tokyo/London/NY/Overlap)
    7. DCRD momentum (was CS rising, falling, or flat?)
    8. Pair-specific patterns
    9. Staircase depth (5-bar vs 10-bar impulse)
    10. Pullback bar count (1-bar vs 2-bar pullback)
    """

    sl_hits = trades_df[trades_df['close_reason'] == 'SL_HIT']
    partial_reaches = trades_df[trades_df['partial_exit_time'].notna()]

    results = {
        'sl_hits': analyze_group(sl_hits, range_bars_dict),
        'partial_reaches': analyze_group(partial_reaches, range_bars_dict),
        'comparison': compare_groups(sl_hits, partial_reaches)
    }

    return results
```

**Outputs:**
- `entry_quality_report.md` - Human-readable analysis
- `entry_patterns.csv` - Structured data for filtering
- `failure_heatmap.png` - Visualizations

---

### Task 1.2: Identify Top 5 Failure Patterns

**Questions to Answer:**

1. **Pullback Depth Issue?**
   - Are failed trades entering on shallow pullbacks (< 30% retrace)?
   - Are failed trades entering on deep pullbacks (> 70% retrace = reversal)?
   - **Hypothesis:** Optimal pullback = 40-60% of prior impulse

2. **SL Distance Issue?**
   - Is 60 pips (3× bar) too tight in high volatility?
   - Is 75 pips too wide in low volatility?
   - **Compare:** SL distance vs ATR(14) at entry
   - **Hypothesis:** SL should be 2-3× ATR, not fixed 3× bar

3. **Session Timing Issue?**
   - Do Tokyo entries fail more (low liquidity)?
   - Do NY open entries fail more (high volatility spikes)?
   - **Compare:** Win rate by session (Tokyo/London/NY/Overlap)
   - **Hypothesis:** Avoid Tokyo-only entries

4. **DCRD Momentum Issue?**
   - Are entries happening when DCRD is declining (trend weakening)?
   - Do winners enter when DCRD is rising/stable?
   - **Compare:** DCRD slope (last 3 bars) for winners vs losers
   - **Hypothesis:** Only enter when DCRD stable or rising

5. **Staircase Quality Issue?**
   - Are 5-bar staircases too weak (just met minimum)?
   - Do winners have deeper staircases (8+ bars)?
   - **Compare:** Staircase depth for winners vs losers
   - **Hypothesis:** Require 7+ bar staircase (not just 5)

**Deliverable:** Ranked list of top 5 issues with statistical evidence

---

### Task 1.3: Design Entry Filters

Based on findings from Task 1.2, design filters to block low-quality entries:

**Example Filters (will adjust based on analysis):**

```python
# Filter 1: Pullback Depth Check
def check_pullback_depth(pullback_low, staircase_high, staircase_low):
    retrace_pct = (staircase_high - pullback_low) / (staircase_high - staircase_low)
    return 0.40 <= retrace_pct <= 0.70  # 40-70% pullback only

# Filter 2: ATR-Based SL
def calculate_dynamic_sl(entry, direction, atr_14, pair):
    sl_distance = 2.5 * atr_14  # 2.5× ATR instead of fixed 3× bar
    # Still respect minimum (3× bar) and maximum (4× bar)
    bar_size_pips = RANGE_BAR_PIPS[pair]
    min_sl = 3 * bar_size_pips * PIP_SIZE[pair]
    max_sl = 4 * bar_size_pips * PIP_SIZE[pair]
    sl_distance = max(min_sl, min(sl_distance, max_sl))
    return entry - sl_distance if direction == "BUY" else entry + sl_distance

# Filter 3: Session Quality
def check_session_quality(timestamp, pair):
    session = get_session(timestamp, pair)
    # Block Tokyo-only for trending strategies (low liquidity)
    if session == "TOKYO" and strategy == "TrendRider":
        return False
    # Require overlap or major session
    return session in ["LONDON", "NY", "LONDON_NY_OVERLAP"]

# Filter 4: DCRD Momentum
def check_dcrd_momentum(dcrd_history):
    # Require DCRD stable or rising (not declining)
    if len(dcrd_history) < 3:
        return True  # Can't check, allow
    slope = (dcrd_history[-1] - dcrd_history[-3]) / 2
    return slope >= -5  # Allow if declining < 5 pts over 2 bars

# Filter 5: Staircase Quality
def check_staircase_quality(staircase_depth):
    return staircase_depth >= 7  # Require 7+ bars (not just 5)
```

**Deliverable:** `entry_filters.py` with 3-5 filters ranked by impact

---

## Phase 3.4.2 — DCRD Rebalancing Analysis (Week 2)

**Objective:** Enable BreakoutRider and RangeRider to trade

### Task 2.1: DCRD Distribution Analysis

**Analyze DCRD behavior over 2-year backtest:**

```python
# src/analysis/dcrd_distribution_analyzer.py

def analyze_dcrd_distribution(dcrd_history_per_pair):
    """
    Analyze how DCRD scores are distributed over time.

    Questions:
    1. What % of time is CS in each regime?
       - CS 0-30 (RangeRider): ???%
       - CS 30-70 (BreakoutRider): ???%
       - CS 70-100 (TrendRider): 89%

    2. Are transitions rare or frequent?
       - How often does CS cross 70 → 69 (trend → breakout)?
       - How long does each regime last?

    3. Are thresholds calibrated correctly?
       - Is CS=70 too low (catching weak trends)?
       - Is CS=30 too low (missing breakout opportunities)?

    4. Pair-specific patterns?
       - Does USDJPY stay trending longer than EURUSD?
       - Does GBPUSD range more than others?
    """

    results = {
        'regime_time_pct': {},  # % of time in each regime
        'regime_transitions': {},  # Transition matrix
        'threshold_sensitivity': {},  # Impact of threshold changes
        'pair_regime_affinity': {}  # Which pairs prefer which regimes
    }

    return results
```

**Deliverable:** `dcrd_distribution_report.md` with charts

---

### Task 2.2: Threshold Sensitivity Testing

**Test alternative DCRD thresholds:**

| Test | TrendRider | BreakoutRider | RangeRider | Rationale |
|------|------------|---------------|------------|-----------|
| **Current** | CS ≥ 70 | CS 30-70 | CS 0-30 | Baseline (89% Trend) |
| **Test 1** | CS ≥ 80 | CS 40-80 | CS 0-40 | Higher bars for trending |
| **Test 2** | CS ≥ 75 | CS 35-75 | CS 0-35 | Moderate shift |
| **Test 3** | CS ≥ 85 | CS 40-85 | CS 0-40 | Aggressive rebalance |
| **Test 4** | CS ≥ 70 | CS 25-70 | CS 0-25 | Widen breakout zone |

**For each test, measure:**
- Trade count per strategy
- Win rate per strategy
- Net P&L
- Max DD
- Pair diversification

**Run command:**
```bash
python backtester/threshold_sensitivity.py --start-date 2024-04-01 --end-date 2026-02-25
```

**Deliverable:** Threshold comparison table + recommendation

---

### Task 2.3: Strategy-Specific Entry Logic Review

**Review each strategy's current entry logic:**

**TrendRider (currently dominant):**
```
✅ 5-bar staircase detection
✅ 2-bar pullback
✅ ADX > 25 confirmation
✅ EMA200 trend direction
❓ May be TOO lenient (catching weak trends)
🎯 Consider: 7-bar staircase minimum (from Task 1.3)
```

**BreakoutRider (only 2 trades in 2 years):**
```
✅ Keltner Channel breakout
✅ BB compression (P20)
✅ Range Bar speed ≥2/30min
❓ Requirements may be TOO strict (almost never triggers)
🎯 Investigate:
   - Is BB compression P20 too tight? (try P30)
   - Is Keltner 1.5× ATR too wide? (try 1.2× ATR)
   - Is speed threshold 2 bars/30min too fast? (try 1.5 bars/30min)
```

**RangeRider (0 trades in 2 years):**
```
✅ 8-bar range block detection
✅ Width > 2× bar size
❓ Requirements impossible to meet?
🎯 Investigate:
   - Does forex ever form clean 8-bar ranges at 20-pip resolution?
   - Is width threshold too tight?
   - Alternative: Use M15 consolidation zones instead?
```

**Deliverable:** Updated entry logic for BreakoutRider and RangeRider

---

## Phase 3.4.3 — Implementation & Testing (Week 3)

### Task 3.1: Implement Entry Quality Filters

**Code changes:**
1. Update `src/strategies/trend_rider.py` with filters from Task 1.3
2. Add `src/entry_quality_filter.py` module (shared filters)
3. Add filter bypass flags for A/B testing
4. Update unit tests

**Integration:**
```python
# In trend_rider.py check() method:

# Existing checks...
if not staircase_depth:
    return None

# NEW: Entry quality filters (Phase 3.4)
if ENTRY_QUALITY_FILTERS_ENABLED:
    # Filter 1: Pullback depth
    if not check_pullback_depth(pullback_low, staircase_high, staircase_low):
        log.debug("TrendRider: Pullback depth out of range (40-70%) — skip")
        return None

    # Filter 2: DCRD momentum
    if dcrd_history and not check_dcrd_momentum(dcrd_history):
        log.debug("TrendRider: DCRD declining — skip")
        return None

    # Filter 3: Session quality
    if not check_session_quality(timestamp, pair):
        log.debug("TrendRider: Session quality insufficient — skip")
        return None

    # Filter 4: Staircase quality
    if staircase_depth < 7:  # Raised from 5
        log.debug("TrendRider: Staircase depth < 7 bars — skip")
        return None
```

**Deliverable:** Updated strategy files + tests

---

### Task 3.2: Implement DCRD Threshold Changes

**Code changes:**
1. Update `src/config.py` with new thresholds
2. Update strategy `is_regime_active()` methods
3. Regenerate `dcrd_config.json` with new percentile mappings

**Example:**
```python
# src/config.py (if Test 2 wins: CS 75/35/35)

STRATEGY_TRENDRIDER_MIN_CS = 75.0     # Raised from 70
STRATEGY_BREAKOUTRIDER_MIN_CS = 35.0  # Raised from 30
STRATEGY_BREAKOUTRIDER_MAX_CS = 75.0  # Raised from 70
STRATEGY_RANGERIDER_MAX_CS = 35.0     # Raised from 30
```

**Deliverable:** Updated config + regenerated thresholds

---

### Task 3.3: Full Backtest Comparison

**Run 4 backtests:**

1. **Baseline:** Current system (Phase 3.2.2)
2. **Entry Filters Only:** Baseline + entry quality filters
3. **DCRD Rebalance Only:** Baseline + new thresholds
4. **Combined:** Both changes together

**Comparison metrics:**
```
| Version | Net P&L | WR | Trades | Trend/BO/Range | Max DD | USDJPY % |
|---------|---------|----|----|----------------|--------|----------|
| Baseline | +$34.94 | 43.8% | 128 | 176/2/0 | 15.3% | 47% |
| Entry Filters | ??? | ??? | ??? | ???/???/??? | ??? | ??? |
| DCRD Rebal | ??? | ??? | ??? | ???/???/??? | ??? | ??? |
| Combined | ??? | ??? | ??? | ???/???/??? | ??? | ??? |
```

**Acceptance criteria for Combined:**
- Net P&L ≥ +$50 (43% improvement)
- Win Rate ≥ 45%
- BreakoutRider ≥ 20 trades
- RangeRider ≥ 10 trades (or justified why 0 is correct)
- USDJPY ≤ 35% of trades

**Deliverable:** Backtest comparison report + recommendation

---

### Task 3.4: Visual Validation (Trade Inspector)

**Manual review of 20 random trades:**
- 10 SL_HIT trades (check if filters would have prevented)
- 10 Partial-reach trades (check if filters don't block winners)

**Launch Trade Inspector:**
```bash
python dashboard/app.py
```

**Review checklist per trade:**
- ✅ Entry quality filters working correctly?
- ✅ M15 shadow shows context clearly?
- ✅ DCRD score aligned with actual market structure?
- ✅ Strategy choice makes sense for regime?

**Deliverable:** Visual validation report (screenshot top 5 examples)

---

## Phase 3.4.4 — Walk-Forward Validation (Week 4)

**Objective:** Confirm improvements hold up in out-of-sample periods

### Task 4.1: Define Walk-Forward Windows

**2-year backtest split into 4 periods:**

| Period | Train | Test | Purpose |
|--------|-------|------|---------|
| **WF1** | Apr-Sep 2024 (6mo) | Oct-Dec 2024 (3mo) | Optimize on H1, validate on Q4 |
| **WF2** | Apr-Dec 2024 (9mo) | Jan-Mar 2025 (3mo) | Optimize on Y1H1+Q4, validate on Q1 |
| **WF3** | Apr-Jun 2025 (12mo) | Jul-Sep 2025 (3mo) | Optimize on Y1+Q1, validate on Q3 |
| **WF4** | Apr-Sep 2025 (15mo) | Oct-Feb 2026 (5mo) | Optimize on Y1+H1, validate on Q4+Jan |

**For each WF cycle:**
1. Run Task 1.1-1.3 on TRAIN period
2. Apply filters to TEST period (no re-optimization)
3. Measure Net P&L on TEST period
4. Pass if ≥3/4 cycles profitable

**Deliverable:** Walk-forward validation report

---

### Task 4.2: Robustness Testing

**Stress tests:**

1. **Spread sensitivity:** Test at 1.5 pips, 2.0 pips, 2.5 pips spreads
2. **Slippage sensitivity:** Test at 0.5 pips, 1.0 pips, 1.5 pips slippage
3. **Commission sensitivity:** Test at $5, $7, $10 per lot
4. **Starting capital:** Test at $400, $500, $600 (±20%)

**Deliverable:** Robustness matrix

---

## Timeline & Milestones

| Week | Phase | Deliverables | Status |
|------|-------|--------------|--------|
| **Week 1** | 3.4.1 Entry Quality | Analysis + filters | 📋 Pending |
| **Week 2** | 3.4.2 DCRD Rebalance | Threshold testing | 📋 Pending |
| **Week 3** | 3.4.3 Implementation | Combined backtest | 📋 Pending |
| **Week 4** | 3.4.4 Validation | Walk-forward + stress | 📋 Pending |

**Next Session:** Task 1.1 - Build entry quality analyzer

---

## Success Metrics (Phase 3.4 Gate)

**PASS Criteria (Combined system):**
- ✅ Net P&L ≥ +$50 (2-year backtest)
- ✅ Win Rate ≥ 45%
- ✅ BreakoutRider ≥ 20 trades (vs 2 currently)
- ✅ Walk-forward: ≥3/4 cycles profitable
- ✅ Max DD ≤ 18%
- ✅ USDJPY concentration ≤ 35% (vs 47% currently)

**If PASS → Proceed to Phase 4 (Live Demo Trading)**
**If FAIL → Iterate on filters or revert to baseline**

---

## Files to Create

1. `src/analysis/entry_quality_analyzer.py` - Task 1.1
2. `src/analysis/dcrd_distribution_analyzer.py` - Task 2.1
3. `src/entry_quality_filter.py` - Task 1.3
4. `backtester/threshold_sensitivity.py` - Task 2.2
5. `docs/entry_quality_report.md` - Task 1.2 output
6. `docs/dcrd_distribution_report.md` - Task 2.1 output
7. `docs/phase_3.4_results.md` - Task 3.3 output

---

**Status:** Plan complete, ready for execution
**Next Action:** Start Task 1.1 - Entry Quality Data Collection
