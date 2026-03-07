# SwingRider Trade Count Bug - Investigation Required

**Date:** 2026-02-28
**Branch:** `feature/swingrider-convexity-amplifier`
**Status:** CRITICAL BUG - System reducing trades when adding GBPJPY

---

## Summary

Adding GBPJPY with SwingRider strategy (5+1 slot model) causes a **55% reduction in total trades** compared to baseline, even though SwingRider only took 1 trade and has a dedicated 6th slot that shouldn't interfere with the other 4 pairs.

---

## Evidence

### Full-Period Backtest (2024-02-01 → 2026-02-28)

| System | Pairs | Slot Model | Total Trades | Net PnL | Result |
|--------|-------|------------|--------------|---------|--------|
| Baseline (Phase 3.6) | 4 (no GBPJPY) | 5 slots | **256** | $183.16 | ✅ Works |
| SwingRider v1 (CS 90-100) | 5 (with GBPJPY) | 5+1 slots | **114** | $187.70 | ❌ 55% fewer trades |

**Trade Breakdown (SwingRider v1):**
- SwingRider: 1 trade (used dedicated 6th slot)
- TrendRider/RangeRider: 113 trades (should have ~256 like baseline)
- **Missing: 142 trades** (256 - 114 = 142 disappeared)

### Walk-Forward Validation

| System | Cycle 1 | Cycle 2 | Cycle 3 | Cycle 4 | Total | Result |
|--------|---------|---------|---------|---------|-------|--------|
| Baseline | 17 trades | 24 trades | 16 trades | 14 trades | **71** | 4/4 PASS ✅ |
| SwingRider v1 | 4 trades | 13 trades | 9 trades | 5 trades | **31** | 3/4 FAIL ❌ |

**Cycle 4 Deep Dive (Dec 2025 - Jan 2026):**
- Baseline: 14 trades, +$46.67 profit
- SwingRider v1: 5 trades, -$25.82 loss
- **9 trades mysteriously blocked**

---

## Expected vs Actual Behavior

### Expected (Correct Logic)

```
Baseline (4-pair):
  - 5 position slots available
  - TrendRider/RangeRider use all 5 slots
  - Result: 256 trades

SwingRider (5-pair, 5+1 model):
  - 5 position slots for TrendRider/RangeRider (same as baseline)
  - 1 DEDICATED slot for SwingRider (6th slot)
  - TrendRider/RangeRider should get ~256 trades (no interference)
  - SwingRider should get ~6-10 trades/year (using 6th slot)
  - Result: ~256 + 12-20 = 268-276 trades total
```

### Actual (Bug)

```
SwingRider (5-pair, 5+1 model):
  - Total trades: 114 (55% reduction!)
  - SwingRider: 1 trade
  - TrendRider/RangeRider: 113 trades (143 missing!)
  - 142 trades blocked by unknown mechanism
```

---

## Suspected Root Causes

### 1. Gate 2 Implementation Error (Most Likely)

**Gate 2 (brain_core.py:240-250):**
```python
# --- Gate 2: Max concurrent positions (Phase 3.7: 5+1 model for SwingRider) ---
# Allow up to 6 positions total (5 for others + 1 dedicated SwingRider slot)
open_count = account_state.open_position_count()
if open_count >= 6:
    # Hard limit: 6 total positions max
    log.debug("Max concurrent: 6/6 (hard limit) — no new trades")
    return None
```

**Potential Issue:** This gate fires BEFORE strategy selection, so if there are 6 positions open (5 normal + 1 SwingRider), it blocks ALL new trades including TrendRider/RangeRider that should have access to 5 slots.

**Fix:** Gate 2 should allow up to 6 total, but Gate 2.5 should enforce per-strategy limits AFTER checking which strategy is active.

### 2. Gate 2.5 Implementation Error

**Gate 2.5 (brain_core.py:362-384):**
```python
# --- Gate 2.5: SwingRider dedicated 6th slot (Phase 3.7: 5+1 model) ---
if active_strategy.name == "SwingRider":
    # SwingRider: Max 1 concurrent, can use 6th slot
    if len(swingrider_trades) >= SWINGRIDER_MAX_CONCURRENT:
        signal.blocked_reason = "SWINGRIDER_MAX_1"
        return signal
else:
    # TrendRider/RangeRider: Max 5 concurrent (standard limit)
    if open_count >= 5:
        signal.blocked_reason = "MAX_CONCURRENT_5"
        return signal
```

**Potential Issue:** If `open_count >= 5` includes the SwingRider trade in the count, then TrendRider/RangeRider would be blocked even though they should have 5 slots independent of SwingRider's 6th slot.

**Fix:** TrendRider/RangeRider limit should check `open_count - len(swingrider_trades) >= 5` to exclude SwingRider's dedicated slot.

### 3. GBPJPY Data Loading Timing

**Hypothesis:** Loading GBPJPY Range Bars might change the order/timing of when signals are processed, causing some signals to be missed or arrive at different times when position limits are full.

**Why This Matters:** If GBPJPY data is slow to load, it might delay the entire signal processing loop, causing some time-sensitive signals on other pairs to expire or fail entry conditions.

**Fix:** Profile data loading, optimize GBPJPY Range Bar caching, or process pairs in parallel.

### 4. Gate 9.6 Momentum Confirmation Bug

**Gate 9.6 (brain_core.py:394-400):**
```python
# --- Gate 9.6: Momentum confirmation (SwingRider only) ---
if active_strategy.name == "SwingRider":
    if not account_state.any_partial_hit:
        signal.blocked_reason = "NO_PARTIAL_MOMENTUM"
        return signal
```

**Potential Issue:** In walk-forward, `any_partial_hit` resets to False at the start of each cycle. If no trade hits partial exit early in a cycle, SwingRider is blocked for the entire cycle.

**Impact:** This only affects SwingRider (1 trade), not the 142 missing baseline trades.

---

## Test Results

### SwingRider v1 Configuration

```python
# src/config.py
SWINGRIDER_MIN_CS = 90.0                     # Deep Trending regime
SWINGRIDER_MAX_CS = 100.0                    # Exclusive to GBPJPY at CS 90-100
SWINGRIDER_BASE_RISK_PCT = 0.007             # 0.7% per trade
SWINGRIDER_PARTIAL_EXIT_R = 2.0              # Partial exit at 2R (NOT 1.5R)
SWINGRIDER_PARTIAL_EXIT_PCT = 0.40           # Close 40% at 2R
SWINGRIDER_CHANDELIER_MULTIPLIER = 1.5       # 1.5x wider trailing SL buffer
```

**Entry Logic:**
1. Weekly structure aligned (4H EMA200)
2. Impulse detected (5+ bar staircase)
3. Pullback detected (2-4 counter bars)
4. Resumption bar entry

**Results:**
- 1 trade over 2 years (CS 90-100 too narrow)
- 2.10R profit on that 1 trade
- Target was 6-10 trades/year (failed to achieve)

---

## Next Steps for Investigation

### 1. Fix Gate 2.5 Position Counting

**Current (Buggy):**
```python
else:
    # TrendRider/RangeRider: Max 5 concurrent
    if open_count >= 5:
        signal.blocked_reason = "MAX_CONCURRENT_5"
        return signal
```

**Fixed (Correct):**
```python
else:
    # TrendRider/RangeRider: Max 5 concurrent (exclude SwingRider trades)
    non_swingrider_count = open_count - len(swingrider_trades)
    if non_swingrider_count >= 5:
        signal.blocked_reason = "MAX_CONCURRENT_5"
        return signal
```

### 2. Add Debug Logging

Add detailed logging to track:
- When Gate 2 blocks trades
- When Gate 2.5 blocks trades
- Position counts at each gate (total, SwingRider, non-SwingRider)

### 3. Test Fix with Baseline Comparison

After fixing Gate 2.5:
- Run full-period backtest
- Expect: ~256 trades from TrendRider/RangeRider + SwingRider trades
- Compare to baseline to verify no trade reduction

### 4. Try SwingRider v2 with Looser CS

**New Configuration:**
```python
SWINGRIDER_MIN_CS = 70.0  # Lower threshold (was 90.0)
SWINGRIDER_MAX_CS = 100.0  # Keep upper bound
```

**Expected:**
- More trades (GBPJPY spends more time at CS 70-100)
- Better convexity capture
- Test if this passes walk-forward validation

---

## Files Modified (SwingRider v1)

### New Files (2)
1. `src/strategies/swing_rider.py` — SwingRider strategy implementation
2. `SWINGRIDER_BUG_REPORT.md` — This document

### Modified Files (8)
1. `src/config.py` — GBPJPY config + SwingRider constants
2. `src/strategies/base_strategy.py` — Add exit config attributes
3. `src/brain_core.py` — Add 4 SwingRider gates + AccountState fields (BUG HERE)
4. `src/exit_manager.py` — Generalize partial exit functions
5. `src/risk_engine.py` — Add strategy base risk override
6. `src/signal.py` — Add strategy_obj field
7. `backtester/engine.py` — Use strategy exit config
8. `backtester/account.py` — Add SwingRider gate tracking
9. `backtester/trade.py` — Add strategy_obj field
10. `data/dcrd_config.json` — GBPJPY calibration thresholds

---

## Commit Message Template

```
feat(phase-3.7): SwingRider convexity amplifier - BUG IDENTIFIED

SwingRider Implementation:
- CS 90-100 (Deep Trending regime)
- GBPJPY exclusive
- 2R partial exit @ 40%, 1.5x Chandelier multiplier
- 0.7% base risk per trade

Results:
- Single-run: $187.70 profit, 2.48 Sharpe, 5.5% DD, 114 trades
- Walk-forward: FAILED 3/4 cycles (Cycle 4: -$25.82)
- Only 1 SwingRider trade over 2 years (CS 90-100 too narrow)

CRITICAL BUG IDENTIFIED:
- Adding GBPJPY reduced baseline trades by 55% (256 → 114)
- 142 trades mysteriously blocked
- Suspected: Gate 2.5 position counting includes SwingRider trades
- Fix required: Exclude SwingRider from TrendRider/RangeRider slot count

Next Session:
- Fix Gate 2.5 bug
- Test SwingRider v2 with CS 70-100 (looser threshold)
- Re-validate walk-forward

See SWINGRIDER_BUG_REPORT.md for full analysis.
```

---

## Status

**INVESTIGATION REQUIRED - DO NOT MERGE TO MAIN**

Branch: `feature/swingrider-convexity-amplifier`
Bug Location: `src/brain_core.py` (Gate 2.5, line 379-383)
Next Session: Fix bug, test SwingRider v2 (CS 70-100), re-validate
