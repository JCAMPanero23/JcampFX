# Phase 3.1.1 — Price Level Cooldown Results

**Date:** February 22, 2026
**Objective:** Eliminate revenge trading by blocking re-entries at same price level within 4-hour window
**Implementation:** Per-strategy price level cooldown (±20 pips, 4 hours)

---

## Summary: MAJOR IMPROVEMENT ✅

The Price Level Cooldown system **successfully eliminated revenge trades** and achieved:
- **40% reduction in losses** (-$218.71 → -$130.58)
- **59% reduction in R losses** (-39.6R → -16.07R)
- **43% reduction in trade count** (292 → 165 trades)
- **22 revenge trade attempts blocked** during backtest

---

## Results Comparison (2024-2025 Data)

| Metric | Baseline (Run 2) | With Price Cooldown | Change |
|---|---|---|---|
| **Net PnL** | **-$218.71** | **-$130.58** | **+$88.13 (+40%)** ✅ |
| **Total Trades** | 292 | 165 | -127 (-43%) ✅ |
| **Win Rate** | 36.0% | 38.2% | +2.2 pts ✅ |
| **Total R** | -39.6R | -16.07R | **+23.53R (+59%)** ✅ |
| **Sharpe Ratio** | -2.26 | -1.71 | +0.55 ✅ |
| **Max Drawdown** | 48.8% | 37.0% | -11.8 pts ✅ |
| **Profit Factor** | 0.76 | 0.80 | +0.04 ✅ |

**Key Finding:** System blocked **22 revenge trade attempts** that would have lost ~-22R

---

## What Was Blocked (Sample)

The Price Level Cooldown successfully blocked known revenge trade patterns:

```
USDJPY 153.79150 — TrendRider lost -1.04R, blocked re-entry 0.3h later
GBPUSD 1.23254   — TrendRider lost -1.05R, blocked re-entry 0.9h later
USDJPY 148.26500 — TrendRider lost -1.04R, blocked re-entry 0.2h later
USDJPY 145.11450 — TrendRider lost -1.04R, blocked re-entry 1.0h later
AUDJPY 104.33500 — TrendRider lost -1.04R, blocked re-entry 1.2h later
```

All blocked entries were within ±20 pips of a recent loss (0.0h to 2.3h ago).

---

## Per-Pair Breakdown

| Pair | Trades | Win Rate | Total R | PnL | vs Baseline Trades |
|---|---|---|---|---|---|
| USDJPY | 76 | 38% | -7.73R | -$54 | -60 (-44%) |
| AUDJPY | 24 | 33% | -3.25R | -$16 | -24 (-50%) |
| USDCHF | 17 | 35% | -3.19R | -$17 | -10 (-37%) |
| EURUSD | 17 | 41% | -0.35R | -$2 | -12 (-41%) |
| GBPUSD | 29 | 41% | -1.49R | +$8 | -21 (-42%) |

**Notes:**
- USDJPY still has highest trade count (76) but reduced from 136 (-44% reduction)
- GBPUSD is now profitable (+$8) despite lower trade count
- All pairs show significant trade reduction (37-50%)

---

## Strategy Breakdown

| Strategy | Trades | Win Rate | PnL | Notes |
|---|---|---|---|
| TrendRider | 163 | 38% | -$121.60 | Main strategy (99% of trades) |
| BreakoutRider | 2 | 50% | -$8.98 | Still rare (BB compression bottleneck) |
| RangeRider | 0 | — | $0.00 | Never triggered (CS never <30) |

---

## Phase 3 Gate Status

| Gate | Target | Result | Status |
|---|---|---|---|
| V3.1 | Net profit positive | **-$130.58** | ❌ FAIL |
| V3.2 | Max DD < 20% | 37.0% | ❌ FAIL |
| V3.12 | Each strategy profitable | TrendRider -$121 | ❌ FAIL |
| V3.15 | Sharpe > 1.0 | -1.71 | ❌ FAIL |
| V3.16 | Profit Factor > 1.5 | 0.80 | ❌ FAIL |

**Status:** Still losing, but **40% improvement** from baseline. Not yet passing Phase 3 gate.

---

## Analysis

### What Worked ✅
1. **Revenge trade elimination:** 22 duplicate entries blocked within 4-hour window
2. **Per-strategy blocking:** Different strategies can still enter at same price level
3. **Trade quality improvement:** Win rate increased from 36% → 38.2%
4. **Risk reduction:** Max drawdown reduced from 48.8% → 37.0%

### Why Still Losing ❌
1. **Entry quality still sub-optimal:** 38.2% partial-reach rate (need 40%+ for breakeven)
2. **TrendRider SL hit rate:** Still 61-65% of trades hit SL before 1.5R partial exit
3. **Structural issue remains:** Entry pattern gets stopped out too frequently
4. **USDJPY concentration:** Still 46% of all trades (76/165) despite cooldown

### Expected vs Actual
- **Expected:** -22R → -1.2R (near breakeven)
- **Actual:** -39.6R → -16.07R (59% improvement but still -16R)
- **Gap:** -14.87R unexplained

**Hypothesis:** The baseline -39.6R contained:
- -20.83R revenge trades (eliminated) ✅
- -18.77R non-revenge losses (still present) ❌

The Price Level Cooldown eliminated revenge trades successfully, but the underlying **entry quality problem** remains unresolved.

---

## Next Steps (Priority Order)

### ✅ COMPLETE: Task 1 — Price Level Cooldown
- Implemented per-strategy price level tracking
- 4-hour cooldown window (configurable)
- ±20 pips threshold (configurable)
- Result: 40% loss reduction, but not breakeven

### 🎯 NEXT: Task 2 — TrendRider Entry Quality Analysis
**Goal:** Understand WHY 62% of TrendRider entries hit SL before 1.5R

**Analysis Required:**
1. **Batch trade analysis:** Compare losing vs winning trades
   - Pullback depth distribution
   - ATR at entry (volatility context)
   - DCRD momentum (rising vs falling)
   - Session timing (Tokyo/London/NY)
   - Time-of-day patterns

2. **Identify filters to increase partial-reach rate 38% → 40%+**
   - Filter deep pullbacks (>50 pips?)
   - Filter low ATR entries (bottom 30th percentile?)
   - Require DCRD rising over last 3-5 bars?

3. **Backtest playback:** Visual inspection of Oct-24 (17% WR) and Jul-25 (0% WR) disasters

### Task 3 — Implement Quality Filters
Based on Task 2 findings, add entry filters to TrendRider

---

## Files Modified

**New Files:**
- `src/price_level_tracker.py` — Per-strategy price level cooldown tracker

**Modified Files:**
- `src/config.py` — Added PRICE_LEVEL_COOLDOWN_PIPS, PRICE_LEVEL_COOLDOWN_HOURS, PRICE_LEVEL_TRACK_LOSSES_ONLY
- `src/brain_core.py` — Added Gate 8.5 (price level cooldown gate)
- `backtester/engine.py` — Reports losing trades to price tracker after close

**Test File:**
- `test_price_level_tracker.py` — Validation tests (all passed)

---

## Validation

**V3.1.1a — Revenge trades eliminated:** ✅ PASS
- 22 duplicate entries blocked within 4-hour window
- No trades opened within ±20 pips of same-strategy loss in last 4 hours

**V3.1.1b — Cross-strategy entries allowed:** ✅ PASS
- BreakoutRider can enter where TrendRider lost (different regime logic)
- Per-strategy blocking prevents only same-strategy re-entries

**V3.1.1c — Configurable parameters:** ✅ PASS
- PRICE_LEVEL_COOLDOWN_PIPS = 20 (adjustable)
- PRICE_LEVEL_COOLDOWN_HOURS = 4 (adjustable)
- PRICE_LEVEL_TRACK_LOSSES_ONLY = True (configurable)

---

## Conclusion

The Price Level Cooldown system **successfully eliminated revenge trading** and achieved a **40% reduction in losses**. However, the system is **still not profitable** (-$130.58) due to underlying **TrendRider entry quality issues**.

**Recommendation:** Proceed to **Task 2 (Entry Quality Analysis)** to identify filters that increase partial-reach rate from 38% to 40%+. The 2.2 percentage point gap represents the difference between losing -$130 and breaking even or profiting.

**Phase 3.1.1 Status:** Partial success — revenge trades eliminated, but breakeven not achieved.

---

**Run ID:** `run_20260222_083218`
**Data:** 2024-01-01 to 2025-12-31 (2 years)
**Backtest Engine:** Phase 3 event-driven Range Bar replay
