# JcampFX Dashboard Bug Report
**Date**: 2026-02-21
**Session**: Trade Inspector Testing
**Backtest Run**: run_20260219_190902 (v2.2 complete, 292 trades)

---

## Bug #1: Inspector 500 Error (FIXED)
**Severity**: HIGH
**Status**: ✅ FIXED (commit ea8a661)

**Problem**:
- Clicking "Inspect" links from Cinema tab caused HTTP 500 Internal Server Error
- Inspector page loaded but showed blank metadata panel and empty chart

**Root Cause**:
- Dash multi-page apps should have ONE `dcc.Location` component in root layout
- Inspector page had duplicate Location component, causing callback conflicts
- Page callbacks must reference root app's Location by id="url"

**Fix Applied**:
- Removed duplicate `dcc.Location` from Inspector page
- Changed Back button to use `Output("url", "pathname")` instead of clearing search
- All callbacks now reference root app's `dcc.Location(id="url")`

**Testing Needed**:
- Manual test via dashboard server (cannot unit test due to dash.register_page requirement)
- Click "Inspect" on any trade in Cinema tab
- Verify metadata panel and chart render correctly

---

## Bug #2: -6.00R Trade Anomaly (CRITICAL)
**Severity**: CRITICAL
**Status**: ❌ NOT FIXED

**Trade Details**:
- **Trade ID**: 9bb53c06
- **Pair**: USDJPY
- **Strategy**: TrendRider
- **Direction**: BUY
- **Entry Time**: 2024-04-29 01:02:41 UTC
- **Entry Price**: 158.14
- **SL Price**: 158.138 (only 0.2 pips away!)
- **Close Price**: 158.128
- **R-Multiple**: **-6.00R** (should never exceed -1.05R)
- **Close Reason**: SL_HIT

**Analysis**:
```
Risk (pips) = Entry - SL = 158.14 - 158.138 = 0.002 = 0.2 pips
Loss (pips) = Entry - Close = 158.14 - 158.128 = 0.012 = 1.2 pips
R-multiple = -1.2 pips / 0.2 pips = -6.00R
```

**Root Cause**:
TrendRider is placing the SL at the pullback bar's extreme, but when the pullback bar's low (for BUY) is VERY close to the entry bar's close, the SL becomes too tight. With USDJPY using 25-pip range bars, the SL should NEVER be less than ~5-10 pips minimum.

**Expected Behavior**:
- For USDJPY (25-pip range bars), minimum SL distance should be at least 10 pips
- TrendRider should validate that `abs(entry - SL) >= MIN_SL_PIPS` before generating signal
- If SL is too tight, skip the signal

**Files to Investigate**:
- `src/strategies/trend_rider.py:analyze()` - SL calculation logic
- Specifically: `sl_price = pullback_bar['low']` for BUY

**Recommended Fix**:
```python
# In TrendRider.analyze(), after calculating sl_price:
min_sl_distance = 10 * pip_size  # 10 pips minimum for all pairs
risk_distance = abs(entry_price - sl_price)

if risk_distance < min_sl_distance:
    # SL too tight, skip this signal
    return None
```

---

## Bug #3: Unusual Range Bar Patterns
**Severity**: MEDIUM
**Status**: ⚠️ INVESTIGATION NEEDED

**Observation** (from Unsual bars.png):
Several Range Bar clusters show unusual patterns (circled in yellow):
1. **Choppy consolidation zones** - many small bars clustered together
2. **Rapid bar succession** - high tick volume in short timeframe
3. **Possible weekend gaps** - bars may span Friday close → Monday open

**Questions**:
1. Are these phantom bars? (should have `is_phantom=True` flag)
2. Are these weekend gap bars? (should have `is_gap_adjacent=True` flag)
3. Is the Range Bar converter handling weekend gaps correctly?

**Files to Investigate**:
- `src/range_bar_converter.py` - weekend gap detection logic
- Check if `is_phantom` and `is_gap_adjacent` flags are being set correctly
- Verify Range Bar validation badges in dashboard (V1.3, V1.4)

**Testing Needed**:
1. Load EURUSD in Range Bar Chart tab
2. Navigate to the circled zones (around Oct 13-15, Oct 20, Nov 5)
3. Hover over suspicious bars to check:
   - `is_phantom` flag
   - `is_gap_adjacent` flag
   - Time span (should not span >4 hours for major pairs)
4. Verify V1.3 validation badge (High-Low==N pips) is passing

---

## Bug #4: Suspicious Multi-Loss Streak
**Severity**: MEDIUM
**Status**: 📊 DATA ANALYSIS NEEDED

**Observation** (from suspecious trades.png):
- Screenshot shows a highlighted sequence of losing trades
- All TrendRider, all USDJPY
- Includes the -6.00R anomaly trade

**Questions**:
1. Is this a single day where DCRD gave multiple false signals?
2. Are these overlapping trades (correlation filter failure)?
3. Why did TrendRider fire multiple times in quick succession?

**Analysis Needed**:
1. Use Trade Inspector to examine each losing trade in sequence
2. Check if entry conditions were genuinely met or if there's a signal spam bug
3. Verify correlation filter is working (max 2 trades with same base/quote)
4. Check if these trades are within the same 4-hour DCRD update cycle

**Files to Investigate**:
- `src/brain_core.py:_filter_correlated_pairs()` - correlation filter logic
- `backtester/account.py` - check if correlation filter is enforced in backtest

---

## Testing Checklist

### Inspector Page (after server restart)
- [ ] Click "Inspect" on any trade in Cinema tab
- [ ] Verify metadata panel shows trade details
- [ ] Verify Range Bar chart renders with candlesticks
- [ ] Verify DCRD timeline chart renders in bottom panel
- [ ] Verify entry/partial/close markers appear on chart
- [ ] Verify "Back to Cinema" button navigates to home page
- [ ] Verify "Prev/Next Trade" buttons navigate correctly
- [ ] Test with losing trade (no partial exit)
- [ ] Test with winning trade (has partial exit)

### Trade 9bb53c06 Investigation
- [ ] Inspect trade 9bb53c06 in Trade Inspector
- [ ] Check Range Bar window before entry
- [ ] Identify pullback bar and entry bar
- [ ] Measure distance from entry to SL visually
- [ ] Verify pullback bar's low is ~0.2 pips below entry
- [ ] Check if this is a valid TrendRider pattern or edge case

### Range Bar Validation
- [ ] Load EURUSD in Range Bar Chart tab
- [ ] Navigate to circled zones in unusual bars screenshot
- [ ] Hover over suspicious bars
- [ ] Check V1.3 validation badge status
- [ ] Identify if bars are phantom or gap-adjacent

---

## Next Steps

1. **Immediate**: Test Inspector page with dashboard server to verify 500 error is fixed
2. **High Priority**: Fix TrendRider 0.2-pip SL bug (add minimum SL distance check)
3. **Medium Priority**: Investigate unusual Range Bar patterns (phantom/gap detection)
4. **Analysis**: Use Inspector to debug Oct-24/Jul-25 losing months (17% WR, 0% WR)

---

## Files Modified This Session
- `dashboard/pages/inspector.py` - Fixed URL routing for multi-page Dash
- `dashboard/app.py` - Fixed Cinema "Inspect" links to use trade_id
- `test_inspector_callback.py` - Created callback test script (cannot run standalone)
- `test_inspector.py` - Created playback integration test (PASS)

**Commit**: ea8a661 - fix(dashboard): correct Inspector URL routing for multi-page Dash app
