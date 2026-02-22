# Phase 3.1.1 — Price Level Cooldown & Entry Quality Improvement

**Phase:** 3.1.1 (Critical Fixes Before Gate)
**Focus:** Eliminate revenge trades (95% of loss) + improve TrendRider entry quality
**Gate:** Phase 3 Validation (V3.1: Net profit positive)

## Phase 3 Status

| Phase | Status | Gate | Current Result |
|---|---|---|---|
| **Phase 3** | IN PROGRESS | Net profit positive | ❌ FAIL (-$218.71 baseline) |
| **Phase 3.1** | IN PROGRESS | Identify loss drivers | ✅ COMPLETE (revenge trades) |
| **Phase 3.1.1** | PENDING | Eliminate revenge trades | 🎯 NEXT SESSION |

**Phase 3.1.1 Objectives:**
1. Implement Price Level Cooldown (eliminate 94.7% of losses)
2. Achieve breakeven or small profit on 2024-2025 backtest
3. Pass Phase 3 Gate V3.1 (Net profit positive)

---

## Context

### Issues Identified from Backtest Analysis

**1. Multiple Losses at Same Price Level ("Revenge Trading")**
- Example: USDJPY entered at 145.1145 twice, 1.5 hours apart (17:51 → 19:20)
- Both trades: same entry, same SL (144.8545), both -1.04R losses
- System re-enters failed price levels without learning from recent losses

**2. TrendRider Entry Quality Below Breakeven**
- Current partial-reach rate: 34-36% (65% hit SL before reaching 1.5R)
- Breakeven requires: ~40% partial-reach rate
- Gap: 5.2 percentage points
- Root cause: Entries getting stopped out before trend confirmation

### Existing Mechanisms
- ✅ Strategy cooldown: 5 consecutive losses → 24hr pause (in `PerformanceTracker`)
- ✅ Correlation filter: max 2 trades per currency
- ✅ Pair cooldown: NOT implemented (gap!)
- ❌ Price level cooldown: NOT implemented (gap!)

---

## Proposed Solutions

### Task 0: Adjust DCRD Regime Thresholds ❌ TESTED & REJECTED

**Goal:** Shift regime distribution to give BreakoutRider more opportunities

**Current Thresholds:**
- TRENDING: CS ≥70 (77.7% of time) → TrendRider dominant
- TRANSITIONAL: CS 30-70 (22.3% of time) → BreakoutRider rarely active
- RANGING: CS <30 (0% of time) → RangeRider never fires

**Proposed Thresholds:**
- TRENDING: CS ≥85 (41.4% of time) → TrendRider more selective
- TRANSITIONAL: CS 40-85 (58.5% of time) → BreakoutRider 2.6x more regime time
- RANGING: CS <40 (0.1% of time) → RangeRider still minimal

**Impact Analysis (2025 backtest data):**
```
Current:     TRENDING 77.7% | TRANSITIONAL 22.3% | RANGING 0%
Proposed:    TRENDING 41.4% | TRANSITIONAL 58.5% | RANGING 0.1%
Net Change:  -36.3%         | +36.2%             | +0.1%

Samples moved to TRANSITIONAL: 3,762 (CS 70, 75, 80)
Samples moved to RANGING: 10 (CS 30, 35)
```

**Benefits:**
1. **Strategy Diversification** — BreakoutRider gets 2.6x more monitoring time
2. **TrendRider Quality** — Higher CS threshold (≥85) = higher conviction trending
3. **Low Risk** — Code change is trivial (config only), easily reversible
4. **No Entry Logic Changes** — BreakoutRider keeps strict BB compression + Keltner filters

**Implementation:**
1. Update `src/config.py`:
   ```python
   STRATEGY_TRENDRIDER_MIN_CS = 85  # Was 70
   STRATEGY_BREAKOUTRIDER_MIN_CS = 40  # Was 30
   STRATEGY_RANGERIDER_MAX_CS = 40  # Was 30
   ```
2. Run backtest with new thresholds (2024 or 2025 data)
3. Compare:
   - Trade count by strategy (expect more BreakoutRider signals)
   - TrendRider partial-reach rate (might improve due to higher CS)
   - Overall R/trade and PnL

**Files to modify:**
- `src/config.py` (3 constants)

**Testing:**
```bash
# Backtest with new thresholds
python -m backtester.run_backtest --start 2025-01-01 --end 2025-12-31

# Expected outcomes:
# - BreakoutRider: 2 trades → ~50+ trades (if entry conditions allow)
# - TrendRider: 290 trades → ~150 trades (more selective)
# - Overall trade count: might increase or stay similar
```

**TEST RESULTS (Feb 22, 2026):**
```
Run: run_20260222_070424
PnL: -$140.92 (vs baseline -$218.71)
Win Rate: 30.4% (WORSE than baseline 36.0%)
Trades: 79 (vs baseline 292)
Sharpe: -4.83 (WORSE than baseline -2.26)
```

**Findings:**
- BreakoutRider still only 2 trades (BB compression bottleneck confirmed)
- TrendRider win rate DROPPED (31.2% vs 36% baseline)
- CS 85-100 = trend exhaustion (late entries, worse timing)
- CS 70-85 = early trend (better entries) — we excluded this!

**Decision: REJECT threshold adjustment, revert to CS 70/30/30**

**See:** `Documentation/threshold_test_analysis_20260222.md` for full analysis

---

### Task 1: Add Price Level Cooldown 🔥 CRITICAL — Eliminates 94.7% of Losses!

**Goal:** Prevent re-entry within ±20 pips of a recent losing trade for N hours

**CRITICAL FINDING (Feb 22, 2026):**
- Revenge trades account for **94.7% of total loss** (-20.83R out of -22.00R)
- 10 pairs of trades re-entering same price level within 0.5-2 hours
- Pattern: Enter → SL (-1.04R) → Re-enter same level → SL (-1.04R)
- **If eliminated:** -22R → -1.2R (near breakeven!)

**Examples:**
```
USDJPY 153.79150: 2 entries in 0.6h → -2.08R total
USDJPY 148.26500: 2 entries in 0.7h → -2.08R total
GBPUSD 1.23254:   2 entries in 1.1h → -2.10R total
```

**Implementation Approach:**

1. **Create new `PriceLevelTracker` class** in `src/price_level_tracker.py`
   - Track losing trades: `{pair: deque[(price, timestamp, r_result)]}`
   - Config params:
     - `PRICE_LEVEL_COOLDOWN_PIPS = 20`  # Don't re-enter within ±20 pips
     - `PRICE_LEVEL_COOLDOWN_HOURS = 4`  # Cooldown duration
     - `PRICE_LEVEL_TRACK_LOSSES_ONLY = True`  # Only track losses (R < 0)

2. **Modify `BrainCore` to integrate price level gating**
   - Add `self._price_tracker = PriceLevelTracker()` in `__init__`
   - In `process()`, before calling strategy:
     ```python
     # Check if signal price is too close to recent loss
     if self._price_tracker.is_blocked(pair, proposed_entry_price, now):
         signal.blocked_reason = "PRICE_LEVEL_COOLDOWN"
         return signal
     ```
   - After trade closes (in backtest engine's `_report_closed_trades`):
     ```python
     if trade.r_multiple_total < 0:  # Loss
         self._brain.price_tracker.add_losing_price(
             pair=trade.pair,
             price=trade.entry_price,
             timestamp=close_time,
             r_result=trade.r_multiple_total
         )
     ```

3. **Files to modify:**
   - **NEW:** `src/price_level_tracker.py` (new module)
   - **MODIFY:** `src/brain_core.py` (integrate price tracker)
   - **MODIFY:** `backtester/engine.py` (report losing prices)
   - **MODIFY:** `src/config.py` (add config params)

---

### Task 2: Improve TrendRider Entry Quality (Priority 2)

**Goal:** Increase partial-reach rate from 34-36% to 40%+ by filtering low-quality entries

**Hypotheses to Test (backtest playback required):**

1. **Pullback Depth Validation**
   - Hypothesis: Deep pullbacks (>50 pips?) indicate trend reversing, not resuming
   - Filter: Reject if `pullback_depth_pips > MAX_PULLBACK_DEPTH` (config)

2. **ATR Context**
   - Hypothesis: Entering during low volatility = wider stops = lower R:R
   - Filter: Reject if `current_ATR < ATR_PERCENTILE_THRESHOLD` (e.g., 30th percentile)

3. **DCRD Momentum**
   - Hypothesis: Entering when DCRD is dropping (even if still >70) = weaker trend
   - Filter: Require DCRD rising over last 3-5 bars, or at least stable

4. **Time-of-Day Filter (optional)**
   - Hypothesis: Certain sessions have better partial-reach rates
   - Analyze: Backtest results by session (Tokyo/London/NY)

**Implementation Approach:**

1. **First: Build Trade Inspector Batch Analysis**
   - Goal: Analyze all losing trades to identify patterns
   - Create `backtester/analysis.py`:
     - `analyze_losing_trades(run_dir)` → DataFrame with:
       - pullback_depth_pips
       - ATR at entry
       - DCRD slope (last 5 bars)
       - Session
       - Partial-reached (yes/no)
     - Statistical comparison: winning vs losing entry characteristics

2. **Then: Add Quality Filters to TrendRider**
   - Based on analysis results, add filters to `src/strategies/trend_rider.py`
   - Example:
     ```python
     # Filter 1: Pullback depth
     if pullback_depth_pips > MAX_PULLBACK_DEPTH:
         return None  # Reject entry

     # Filter 2: ATR context
     if current_atr < atr_threshold:
         return None  # Low volatility, skip

     # Filter 3: DCRD momentum
     if dcrd_score < previous_dcrd_score - 5.0:
         return None  # DCRD dropping, trend weakening
     ```

3. **Files to modify:**
   - **NEW:** `backtester/analysis.py` (batch trade analysis)
   - **MODIFY:** `src/strategies/trend_rider.py` (add quality filters)
   - **MODIFY:** `src/config.py` (add filter thresholds)

---

### Task 3: Fix Regime Display in Trade Log (Quick Fix)

**Goal:** Show full regime name instead of single letter

**Current Issue:**
- Trade log shows: "T" (only first letter)
- Should show: "TRENDING", "BREAKOUT", "RANGING", "TRANSITIONAL"

**Implementation:**
- Modify `dashboard/app.py` line ~1015 in `_fmt()` function:
  ```python
  if col == "regime":
      # Current: return val[0].upper()  # Only first letter
      # Fix: return full capitalized regime name
      if val and isinstance(val, str):
          return val.upper()  # Full text
      return "—"
  ```

---

### Task 4: Investigate Why All Trades are TrendRider ✅ COMPLETE

**Goal:** Understand strategy routing - why no BreakoutRider or RangeRider trades?

**Observations from Backtest:**
- Run 2 (2024 data): 290 trades, mostly TrendRider
- DCRD locked to CS ≥70 (TrendRider regime) ~77.7% of time
- BreakoutRider: only 2 trades in 2 years
- RangeRider: 0 trades

---

## ROOT CAUSE ANALYSIS — COMPLETED

**Finding 1: DCRD Score Distribution (Data-Driven, NOT a Bug)**
- ✅ No hardcoded floor exists in the code
- ✅ DCRD scores range from 30.0 to 100.0 (never below 30)
- ✅ Regime breakdown:
  - TRENDING (CS ≥70): 77.7% of time
  - TRANSITIONAL (CS 30-70): 22.3% of time
  - RANGING (CS <30): **0% of time** (never occurs)
- ✅ Scores appear in 5-point increments (30, 35, 40, ..., 95, 100)

**Why DCRD Stays Above 30:**
- Layer 1 (Structural) components:
  - ADX Strength: 0/10/20 points
  - Market Structure: 0/10/20 points
  - ATR Expansion: 0/10/20 points
  - CSM Alignment: 0/10/20 points (defaults to 10 if insufficient data)
  - Trend Persistence: 0/10/20 points
- During 2024-2025 backtest period, market was:
  - **Volatile** (ATR expansion scoring 10-20)
  - **Trending vs EMA200** (Trend persistence scoring 10-20)
  - **Structured** (Market structure scoring 10-20)
- Result: Layer 1 consistently scored 30-100 points (at least 2-3 components at 10-20)

**Finding 2: BreakoutRider Conditions Extremely Strict** (only 2 trades in 2 years)
- ✅ Reviewed `src/strategies/breakout_rider.py`
- ✅ Entry requires ALL of:
  1. **BB Compression** (volatility in lowest 20th percentile)
  2. **Close Outside Keltner Channel** (1.5×ATR breakout)
  3. **Micro-structure Break** (break previous bar's high/low)
  4. **RB Speed** ≥2 bars/30min (fast momentum)

**The Paradox:**
- BB compression requires **LOW volatility** (narrow Bollinger Bands)
- Keltner breakout requires **LARGE move** (break out of 1.5×ATR channel)
- RB speed requires **FAST formation** (momentum building)
- This is a "coiled spring release" pattern — legitimately rare event

**Finding 3: RangeRider Never Fires**
- ✅ Reviewed `src/strategies/range_rider.py`
- ✅ Entry requires:
  1. **CompositeScore < 30** (Range regime) ← **NEVER occurred during backtest**
  2. ≥8 consecutive Range Bars in consolidation block
  3. Block width > 2× RB size
  4. Price at boundary

---

## STRATEGIC IMPLICATIONS

**Strategy Diversification Problem:**
- TrendRider gets 99% of opportunities (290/292 trades)
- TrendRider's 34-36% partial-reach rate determines overall profitability
- System is vulnerable to trending market failure
- No hedge against prolonged trend reversals

**Two Paths Forward:**

**Option A: Improve TrendRider Quality** ✅ PRIORITIZE THIS
- Increase partial-reach rate from 34% to 40%+ via entry filters
- Focus on USDJPY/AUDJPY/USDCHF (main loss drivers)
- Use backtest playback to find patterns in losing trades
- Lower risk, higher probability of success

**Option B: Relax BreakoutRider Conditions** (more aggressive)
- Consider removing BB compression requirement
- Or lower percentile threshold (20th → 35th or 40th)
- Add session filter (London/NY open only)
- Trade-off: more signals but potentially lower quality
- Higher risk, uncertain impact on profitability

**Recommendation:**
- Execute Option A (Task 2: TrendRider quality filters) FIRST
- If TrendRider reaches 40%+ partial-reach rate → system profitable
- THEN consider Option B as diversification (Phase 4+)

---

## Implementation Order

**✅ Session 0: Completed Tasks**
1. ✅ Fix Regime display (Task 3) - DONE
2. ✅ Analyze why only TrendRider trades (Task 4) - DONE
   - Root cause: 2024-2025 market conditions kept DCRD ≥30
   - BreakoutRider conditions too strict (only 2 trades in 2 years)
   - RangeRider never triggered (CS never <30)
   - Recommendation: Focus on TrendRider quality improvement first
3. ✅ Threshold adjustment test (CS 85/40/40) - TESTED & REJECTED
   - Result: -$140.92 (better than baseline -$218.71 but still losing)
   - Win rate: 30.4% (WORSE than baseline 36.0%)
   - 79 trades (vs 292 baseline) - sample size too small
   - **Finding:** Higher CS threshold = worse entry timing (trend exhaustion)
   - **Conclusion:** Revert to CS 70/30/30, threshold not the solution
4. ✅ Revenge trade analysis - **CRITICAL DISCOVERY**
   - **94.7% of total loss** (-20.83R out of -22.00R) from revenge trades!
   - 10 pairs of trades re-entering same price level within 0.5-2h
   - Pattern: Enter → SL hit (-1.04R) → Re-enter same level → SL hit again (-1.04R)
   - **Impact:** Price Level Cooldown could eliminate ~95% of losses
5. ✅ Enhanced config override system - DONE
   - Added trade management presets (partial exit %, Chandelier floors)
   - Added custom preset save/load commands
   - 8 total presets now available

**Session 1: Price Level Cooldown Implementation (TOP PRIORITY)**
1. Create `PriceLevelTracker` class in `src/price_level_tracker.py`
2. Integrate into `BrainCore` signal gating
3. Update backtest engine to report losing prices
4. Test with new backtest run (2024 or 2025 data)
5. Validate: no duplicate entries within ±20 pips / 4 hours

**Session 2: Entry Quality Analysis (Priority 2 - Research)**
1. Build batch analysis tool in `backtester/analysis.py`
2. Analyze Run 2 losing trades vs winning trades
3. Identify statistical patterns:
   - Pullback depth distribution (losers vs winners)
   - ATR at entry (losers vs winners)
   - DCRD slope/momentum (losers vs winners)
   - Session timing (Tokyo/London/NY)
4. Output: Recommended filter thresholds with statistical confidence

**Session 3: Entry Quality Filters (Priority 3 - Optimization)**
1. Add validated filters to TrendRider based on Session 2 analysis
2. Run backtest with filters enabled (2024 data)
3. Compare metrics:
   - Baseline: 34.8% partial-reach rate, -$219 PnL
   - Target: 40%+ partial-reach rate, breakeven or better
4. If successful, validate on 2025 data (walk-forward test)

---

## Testing & Validation

**After Task 1 (Price Level Cooldown):**
```bash
# Run new backtest
python -m backtester.run_backtest --start 2025-01-01 --end 2025-12-31

# Expected results:
# - No duplicate entries at same price within 4 hours
# - Slightly fewer total trades
# - Potentially better R/trade (avoiding "revenge" losses)
```

**After Task 2 (Entry Quality Filters):**
```bash
# Compare metrics:
# - Baseline: 34.8% partial-reach rate
# - Target: 40%+ partial-reach rate
# - Trade count reduction acceptable if quality improves
```

---

## Risk Considerations

**Price Level Cooldown:**
- ⚠️ May reduce trade count significantly if price levels repeat frequently
- ⚠️ Could miss valid re-entries if market structure changes quickly
- ✅ Mitigation: Start with 4-hour cooldown (not 24hr), tune based on results

**Entry Quality Filters:**
- ⚠️ Overfitting risk if thresholds are based on single backtest run
- ⚠️ May filter out valid signals, reducing sample size
- ✅ Mitigation: Use walk-forward validation (train on 2024, test on 2025)

---

## Critical Files

**New Files:**
- `src/price_level_tracker.py`
- `backtester/analysis.py`

**Modified Files:**
- `src/brain_core.py`
- `src/config.py`
- `backtester/engine.py`
- `src/strategies/trend_rider.py`
