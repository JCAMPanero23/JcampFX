# Staircase Pattern Detection — TrendRider Entry Logic

**Version:** 2.2 (5-bar staircase, resumption bar entry)
**Last Updated:** February 22, 2026
**File:** `src/strategies/trend_rider.py`

---

## Overview

The **Staircase Pattern** is a trend confirmation mechanism that detects consecutive directional Range Bars forming a "staircase" structure before allowing TrendRider entries.

**Purpose:** Filter out false signals by requiring proof of sustained momentum (minimum 5 consecutive directional bars).

---

## What is a Staircase?

A **staircase** is a sequence of consecutive Range Bars where BOTH the high and low are moving in the trend direction:

### BUY Staircase (Uptrend)
```
Each bar makes:
- Higher High (HH): bar[i].high > bar[i-1].high
- Higher Low (HL):  bar[i].low > bar[i-1].low

Visual:
    ┌─────┐  Bar 5: HH + HL
    │     │
  ┌─┼─────┤  Bar 4: HH + HL
  │ │     │
┌─┼─┤     │  Bar 3: HH + HL
│ │ │     │
│ │ │     │  Bar 2: HH + HL
│ │ │     │
│ │ │     │  Bar 1: HH + HL
└─┴─┴─────┘
 1 2 3 4 5

Result: 5-bar staircase detected ✅
```

### SELL Staircase (Downtrend)
```
Each bar makes:
- Lower Low (LL):  bar[i].low < bar[i-1].low
- Lower High (LH): bar[i].high < bar[i-1].high

Visual:
┌─────┬─┬─┐  Bar 1: LL + LH
│     ├─┤ │
│     │ ├─┤  Bar 2: LL + LH
│     │ │ │
│     ├─┤ │  Bar 3: LL + LH
│     │ ├─┤
│     │ │ │  Bar 4: LL + LH
│     ├─┤ │
│     │ │ │  Bar 5: LL + LH
└─────┴─┴─┘
 1 2 3 4 5

Result: 5-bar staircase detected ✅
```

---

## Configuration

**Staircase Minimum Depth:**
```python
# src/strategies/trend_rider.py
_STAIRCASE_BARS = 5  # minimum consecutive directional bars required
```

**Tested Configurations:**
| Staircase Bars | Trades | Win Rate | Total R | PnL | Notes |
|---|---|---|---|---|---|
| 5 bars | 292 | 36% | -39.6R | -$219 | ✅ Current (v2.2 baseline) |
| 3 bars | 430 | 34% | -81.2R | -$323 | ❌ Too noisy (47% more trades, worse WR) |

**Conclusion:** 5-bar staircase provides optimal balance between signal frequency and quality.

---

## Detection Algorithm

**Function:** `_detect_3bar_staircase()` (legacy name, actually detects N-bar staircase)

**Parameters:**
- `range_bars`: Range Bar DataFrame
- `direction`: "BUY" or "SELL"
- `lookback`: How many recent bars to check (default 15)

**Process:**
1. Take last 15 Range Bars
2. Loop through bars comparing each to previous bar
3. Count consecutive HH/HL (BUY) or LL/LH (SELL) patterns
4. Reset counter if pattern breaks
5. Track maximum consecutive count
6. Return max count if ≥5, else return 0

**Code:**
```python
def _detect_3bar_staircase(range_bars: pd.DataFrame, direction: str, lookback: int = 15) -> int:
    """
    Detect a staircase pattern in Range Bars.
    Returns the staircase depth (≥5) if found, or 0 if not found.
    """
    if len(range_bars) < _STAIRCASE_BARS + 1:
        return 0

    recent = range_bars.tail(lookback).reset_index(drop=True)
    highs = recent["high"].values
    lows = recent["low"].values

    consecutive = 0
    max_consecutive = 0

    for i in range(1, len(recent)):
        if direction == "BUY":
            if highs[i] > highs[i - 1] and lows[i] > lows[i - 1]:
                consecutive += 1
                max_consecutive = max(max_consecutive, consecutive)
            else:
                consecutive = 0  # Reset on pattern break
        else:  # SELL
            if highs[i] < highs[i - 1] and lows[i] < lows[i - 1]:
                consecutive += 1
                max_consecutive = max(max_consecutive, consecutive)
            else:
                consecutive = 0

    return max_consecutive if max_consecutive >= _STAIRCASE_BARS else 0
```

---

## Example Detection

### Scenario: BUY Staircase Forming

**Range Bars (USDJPY, 25-pip bars):**
```
Bar  High     Low      HH?  HL?  Consecutive
────────────────────────────────────────────
1    145.25   145.00   -    -    0 (start)
2    145.40   145.15   ✅   ✅   1
3    145.60   145.35   ✅   ✅   2
4    145.80   145.55   ✅   ✅   3
5    146.00   145.75   ✅   ✅   4
6    146.20   145.95   ✅   ✅   5  ← Staircase detected!
7    146.10   145.80   ❌   ❌   0  ← Pattern breaks (reset)
```

**Result:**
- `_detect_3bar_staircase()` returns `5` (staircase depth)
- TrendRider can now look for pullback entry

---

## Integration with TrendRider Entry Logic

The staircase is **Step 2** in the TrendRider entry sequence:

### Full Entry Sequence

**Step 1: Detect Trend Direction**
- Check if price is above (BUY) or below (SELL) EMA(200) on 1H

**Step 2: Confirm Staircase Pattern** ⭐
- Requires minimum 5 consecutive directional bars
- Proves sustained momentum, not just a spike

**Step 3: Confirm ADX > 25 AND Rising**
- ADX(14) on 1H must be > 25
- ADX must be rising over last 5 bars (trend accelerating, not exhausting)

**Step 4: Wait for Pullback**
- After staircase, wait for 1–2 counter-trend bars (pullback)
- Entry: On **resumption bar** (first bar that moves back in trend direction after pullback)

**Step 5: Set Stop Loss**
- SL = pullback bar's structural extreme (low for BUY, high for SELL)

---

## Why 5 Bars?

### Impulse Distance Calculation

**5 Range Bars = 5× bar size in price movement**

**For 20-pip majors (EURUSD, GBPUSD, USDCHF):**
- 5 bars × 20 pips = **100 pips minimum impulse**
- Equivalent to ~1.0% move on EURUSD (1.0000 → 1.0100)

**For 25-pip JPY pairs (USDJPY, AUDJPY):**
- 5 bars × 25 pips = **125 pips minimum impulse**
- Equivalent to ~0.85% move on USDJPY (145.00 → 146.25)

**Purpose:** Filters out weak trends that don't have sufficient directional strength.

---

## Staircase Depth vs Trade Quality

### Analysis (2024-2025 Backtest Data)

| Staircase Bars | Purpose | Trade Count | Win Rate | R/Trade |
|---|---|---|---|---|
| **3 bars** | Low threshold | 430 | 34% | -0.189R |
| **5 bars** ✅ | Balanced | 292 | 36% | -0.136R |
| **7 bars** | High threshold | ~150 (est) | TBD | TBD |

**Key Findings:**
- **3-bar = too permissive:** 47% more trades but 2 pts lower WR → worse R/trade
- **5-bar = optimal:** Balance between signal frequency and quality
- **7-bar = too restrictive:** May miss early trend entries, waiting for 7 consecutive bars

**Current Recommendation:** Keep `_STAIRCASE_BARS = 5`

---

## Staircase Breaking Scenarios

### What Breaks a Staircase?

**1. Inside Bar (consolidation)**
```
Bar 4: high = 145.80, low = 145.55
Bar 5: high = 145.70, low = 145.60  ← Inside bar (not HH/HL)
Result: Consecutive count resets to 0
```

**2. Pullback Bar (counter-trend)**
```
Bar 4: high = 145.80, low = 145.55
Bar 5: high = 145.70, low = 145.45  ← LL but not HL
Result: Consecutive count resets to 0
```

**3. Equal High/Low (sideways)**
```
Bar 4: high = 145.80, low = 145.55
Bar 5: high = 145.80, low = 145.60  ← High unchanged
Result: Consecutive count resets to 0
```

**After Reset:** Counter starts over from 0, needs another 5 consecutive bars.

---

## Staircase in Different Market Conditions

### Trending Market (CS ≥70)
```
Typical staircase: 5–10 consecutive bars common
Entry opportunities: Frequent (every 3–5 bars after pullback)
Example: USDJPY strong uptrend → 8-bar staircase, clean entry
```

### Transitional Market (CS 30–70)
```
Typical staircase: 3–5 consecutive bars (often breaks early)
Entry opportunities: Rare (TrendRider disabled, BreakoutRider active)
Example: EURUSD choppy range → 3-bar moves, no sustained staircase
```

### Ranging Market (CS <30)
```
Typical staircase: 0–2 consecutive bars (constant reversals)
Entry opportunities: None (TrendRider disabled, RangeRider active)
Example: GBPUSD consolidation → alternating bars, no staircase
```

**Insight:** Staircase detection naturally aligns with DCRD regime:
- High CS → frequent staircases → TrendRider active
- Low CS → no staircases → TrendRider inactive

---

## Relationship to ADX Slope Filter

### ADX Rising Requirement (v2.2)

In addition to the staircase pattern, TrendRider requires **ADX to be rising**:

**ADX Slope Calculation:**
```python
_ADX_SLOPE_BARS = 5  # measure slope over 5 bars

def _adx_is_rising(ohlc_1h: pd.DataFrame) -> bool:
    """Return True if ADX is rising over the last 5 bars."""
    adx = _adx_series(ohlc_1h, period=14)
    if len(adx) < 6:
        return False
    return adx.iloc[-1] > adx.iloc[-6]  # Compare now vs 5 bars ago
```

**Combined Filter:**
- Staircase (5 bars) = price action momentum confirmation
- ADX rising (5 bars) = directional strength confirmation
- Both required = high-conviction trend entry

**Test Results (Feb 19, 2026):**
| Config | Trades | Win Rate | Total R | Notes |
|---|---|---|---|
| Staircase only | 292 | 36% | -39.6R | Baseline |
| Staircase + ADX slope | 180 | 35% | -34.1R | ❌ Fewer trades but WR dropped |

**Conclusion:** ADX slope filter did NOT improve entry quality → removed in current version.

---

## Visual Examples in Charts

### How Staircase Appears on Range Bar Chart

**Uptrend Staircase:**
```
USDJPY 25-pip Range Bars

Time: 12:00 → 13:30 (1.5 hours, 6 bars formed)

      ╔═══════╗ Bar 6: 146.20/145.95 (HH/HL) ← Entry zone
      ║       ║
    ╔═╬═══════╝ Bar 5: 146.00/145.75 (HH/HL)
    ║ ║
  ╔═╬═╝         Bar 4: 145.80/145.55 (HH/HL)
  ║ ║
╔═╬═╝           Bar 3: 145.60/145.35 (HH/HL)
║ ║
║ ║             Bar 2: 145.40/145.15 (HH/HL)
║ ║
╚═╝             Bar 1: 145.25/145.00 (start)

└────────────────────────────────────────→ Time

Staircase Depth: 5 bars ✅
TrendRider: Looking for pullback entry
```

**Pullback After Staircase:**
```
      ╔═══════╗ Bar 6 (staircase peak)
      ║       ║
    ╔═╬═══════╝ Bar 5
    ║ ║
  ╔═╬═╝ ╔═╗     Bar 7: Pullback (lower high, lower low)
  ║ ║   ║ ║
╔═╬═╝   ║ ║     Bar 8: Pullback continues
║ ║     ╚═╝
║ ║       ╔═══╗ Bar 9: RESUMPTION ← ENTRY HERE!
║ ║       ║   ║ (first bar back in trend direction)
╚═╝       ╚═══╝

SL: Bar 8's low (pullback extreme)
Entry: Bar 9's close
```

---

## Signal Schema

When a staircase is detected, TrendRider includes metadata in the Signal object:

```python
@dataclass
class Signal:
    # ... other fields ...
    staircase_depth: Optional[int] = None  # e.g., 5, 6, 7 (max consecutive bars)
    pullback_bar_idx: Optional[int] = None # absolute index in Range Bar DataFrame
    entry_bar_idx: Optional[int] = None    # absolute index where entry fires
```

**Usage:**
- `staircase_depth`: Stored for analysis (deeper staircase = stronger trend?)
- `pullback_bar_idx`: Used for SL placement (pullback bar's extreme)
- `entry_bar_idx`: Used for backtest playback (exact bar where signal fired)

---

## Files Reference

| Component | File | Function/Constant |
|---|---|---|
| Staircase Detection | `src/strategies/trend_rider.py` | `_detect_3bar_staircase()` |
| Staircase Threshold | `src/strategies/trend_rider.py` | `_STAIRCASE_BARS = 5` |
| ADX Slope Filter | `src/strategies/trend_rider.py` | `_adx_is_rising()` |
| ADX Slope Bars | `src/strategies/trend_rider.py` | `_ADX_SLOPE_BARS = 5` |
| Pullback Entry | `src/strategies/trend_rider.py` | `_find_pullback_entry()` |
| Signal Metadata | `src/signal.py` | `Signal.staircase_depth` |

---

## Future Improvements

### Potential Enhancements (Phase 3.2+)

**1. Adaptive Staircase Threshold**
- Use DCRD score to adjust minimum bars required
- CS 90–100: 3-bar staircase (very strong trend, early entry)
- CS 70–90: 5-bar staircase (current)
- CS 70–75: 7-bar staircase (weak trend, more confirmation needed)

**2. Staircase Quality Score**
- Not just count, but measure "cleanness" of staircase
- Penalize inside bars or small HH/HL moves
- Reward large directional bars (high RB speed)

**3. Staircase Slope Angle**
- Measure steepness of staircase (pips per bar)
- Steep staircase (>30 pips/bar) = strong momentum
- Shallow staircase (<15 pips/bar) = weak trend

---

## Validation

**Test Cases:**

**TC1: 5-Bar BUY Staircase**
- Input: 5 consecutive Range Bars with HH/HL
- Expected: `_detect_3bar_staircase()` returns 5

**TC2: 4-Bar BUY Staircase (Insufficient)**
- Input: 4 consecutive bars with HH/HL, then break
- Expected: `_detect_3bar_staircase()` returns 0 (below threshold)

**TC3: 7-Bar BUY Staircase**
- Input: 7 consecutive bars with HH/HL
- Expected: `_detect_3bar_staircase()` returns 7

**TC4: Alternating Pattern (No Staircase)**
- Input: HH/HL, LL/LH, HH/HL, LL/LH (choppy)
- Expected: `_detect_3bar_staircase()` returns 0

**TC5: Inside Bar Breaks Staircase**
- Input: 4× HH/HL, then inside bar, then 2× HH/HL
- Expected: `_detect_3bar_staircase()` returns 2 (max consecutive before reset)

---

## Version History

### v2.2 (Current - Feb 2026)
- **5-bar staircase** confirmed as optimal (tested vs 3-bar)
- Resumption bar entry (vs pullback bar entry)
- ADX slope filter tested and REMOVED (no quality improvement)
- 20-pip Range Bars (vs 10-pip in v2.1)

### v2.1 (Jan 2026)
- Initial staircase implementation
- 3-bar minimum threshold (too noisy)
- 10-pip Range Bars
- Pullback bar entry (caused r_dist=0 bug)

---

**Maintained By:** JcampFX Development Team
**Next Review:** If changing Range Bar sizes or testing different staircase thresholds
