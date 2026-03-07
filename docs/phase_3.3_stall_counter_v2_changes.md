# Phase 3.3 Stall Counter v2.0 — Implementation Changes
**Date:** Feb 24, 2026
**Status:** Ready for validation before backtest

## Summary of Changes

All requested fixes have been implemented to address bugs found in v1.0 and v1.5.

---

## 1. Trailing SL Function — DISABLED ✅

**File:** `backtester/engine.py` (lines 446-465)

**Change:**
- **REMOVED** Range Bar trailing stop logic (bar low/high - 5 pips)
- **KEPT** 2-bar counter-trend auto-close rule
- Stall Counter + 2-bar exit are now the ONLY runner exit mechanisms (besides regime deterioration)

**Rationale:** Trailing SL was causing premature exits immediately after partial exit. Stall Counter provides better momentum-based exit logic.

---

## 2. Stall Counter Display Format — FIXED ✅

**File:** `dashboard/pages/inspector.py` (lines 388-479)

**Changes:**
- **"D"** = Disabled/paused (no parentheses)
- **"0" to "8"** = Active in OPEN phase (no prefix)
- **"E0" to "E8"** = Active in RUNNER phase (E prefix)
- **Color coding:**
  - Green (0-2): Safe zone
  - Orange (3-5): Warning zone
  - Red (6-8): Danger zone
  - Gray (D): Disabled

**Before:**
```
(0) (8) 80 60 40 20 (17)
```

**After:**
```
D 0 1 2 E0 E1 E2
```

---

## 3. Entry Zone Pause — "D" Display ✅

**Files:**
- `src/stall_counter.py` (added `is_paused()` method)
- `dashboard/pages/inspector.py` (uses `is_paused()` for display)

**Logic:**
- Counter shows **"D"** when current price is within ±5 pips of entry price
- Allows normal consolidation near entry without penalty
- Only applies in OPEN phase

**Behavior:**
- Entry at 1.2000
- Bar closes at 1.2003 (3 pips from entry) → Display: **"D"**
- Bar closes at 1.2006 (6 pips from entry) → Display: **"0"** (counter active)

---

## 4. Exhaustion Detection — 4 Total Strikes ✅

**File:** `backtester/engine.py` (lines 359-372)

**Logic:**
- When price is within **1 range bar (20/25 pips)** of 1.5R target
- AND price stalls at that level (next bar forms without reaching target)
- → Switch to **exhaustion mode**

**Exhaustion Mode:**
- Starts at **counter = 4** (instead of 0)
- Exits at **counter = 8**
- Total strikes allowed: **8 - 4 = 4 strikes**
- Gives trade a chance to push through to 1.5R, but exits quickly if stalling continues

**Example:**
- 1.5R target: 1.2150
- Current bar close: 1.2135 (15 pips away, within 20-pip range bar)
- Next bar forms at 1.2137 (stalling, didn't reach 1.5R)
- → Activate exhaustion mode, counter = 4
- → If trade continues stalling, exits after 4 more strikes (counter = 8)

---

## 5. Grid Lines — Background Layer ✅

**File:** `dashboard/pages/inspector.py` (lines 714-723)

**Change:**
- Added `layer="below"` parameter to all grid lines
- Grid now appears **behind** candlesticks instead of in front

**Before:** Grid lines obscured price action
**After:** Grid provides subtle reference without obscuring candles

---

## 6. M15 Candlestick Shadow — ADDED ✅

**File:** `dashboard/pages/inspector.py` (lines 318-357)

**New Feature:**
- Loads M15 OHLC data from `data/ohlc/{pair}_M15.parquet`
- Displays M15 candlesticks as **75% transparent shadow** behind Range Bars
- Color:
  - Green M15: `rgba(38,166,154,0.25)`
  - Red M15: `rgba(239,83,80,0.25)`
- Helps visualize intrabar price action and context

**Fallback:** If M15 data not available, chart displays normally with Range Bars only.

---

## Files Modified

1. **`src/stall_counter.py`**
   - Added `is_paused()` method for entry zone detection

2. **`backtester/engine.py`**
   - Disabled trailing SL function (lines 446-465)
   - Updated exhaustion detection comments

3. **`dashboard/pages/inspector.py`**
   - Fixed counter display format (D, 0-8, E0-E8)
   - Added M15 shadow overlay
   - Moved grid lines to background layer
   - Updated color coding logic

---

## Validation Checklist (Before Backtest)

### Visual Inspection (Trade Inspector)
- [ ] Open Trade Inspector for a sample trade
- [ ] Verify counter displays as "D" near entry (within 5 pips)
- [ ] Verify counter shows 0-8 in OPEN phase (no prefix)
- [ ] Verify counter shows E0-E8 in RUNNER phase (after partial exit)
- [ ] Verify M15 shadow is visible and transparent
- [ ] Verify grid lines are behind candlesticks
- [ ] Verify color coding (green/orange/red) works correctly

### Code Validation
- [ ] Run Python syntax check: `python -m py_compile src/stall_counter.py`
- [ ] Run Python syntax check: `python -m py_compile backtester/engine.py`
- [ ] Run Python syntax check: `python -m py_compile dashboard/pages/inspector.py`
- [ ] Launch dashboard and check for errors: `python -m dashboard.app`

### Backtest Readiness
- [ ] All visual checks pass
- [ ] All code syntax checks pass
- [ ] Dashboard loads without errors
- [ ] Ready to run full 2-year backtest

---

## Expected Impact

### Hypothesis:
- **Trailing SL removal** → Fewer premature exits in runner phase
- **Entry zone pause** → No false stall penalties during entry consolidation
- **Exhaustion detection** → Capture near-1.5R stalls before they reverse
- **Better UI** → Easier to debug and validate counter behavior

### Success Criteria:
- Net PnL ≥ **$34.94** (baseline Phase 3.2.2)
- Max DD ≤ **15.3%** (baseline)
- Win Rate ≥ **43.8%** (baseline)
- Stall counter exits show positive avg R (not negative like v1.0/v1.5)

---

## Next Steps

1. **Validate changes** using checklist above
2. **Run backtest** with current config (2 years, Apr 2024 - Feb 2026)
3. **Compare results** to baseline (Phase 3.2.2: +$34.94)
4. **Decision point:**
   - If v2.0 ≥ baseline → KEEP and proceed to Phase 3.4
   - If v2.0 < baseline → DISABLE stall counter, use baseline for Phase 3.4

---

## Debug References

- **Screenshot 1:** `Debug/Stall Counter scoring2.png` - Shows wrong counter values (80, 60, 40)
- **Screenshot 2:** `Debug/loss instead of win.png` - Shows premature exit preventing win
- **Analysis:** `docs/phase_3.3_stall_counter_analysis.md` - Full bug analysis from v1.0/v1.5

---

## Contact

If bugs persist after validation:
1. Take screenshot of Trade Inspector showing issue
2. Note trade ID and run ID
3. Document expected vs actual behavior
4. Save screenshot to `Debug/` folder for analysis
