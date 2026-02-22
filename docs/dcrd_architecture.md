# DCRD Architecture — Dynamic Composite Regime Detection

**Version:** 2.2 (20-pip Range Bars, calibrated thresholds)
**Last Updated:** February 22, 2026
**Reference:** PRD §3.1–3.7

---

## Overview

DCRD is a 3-layer composite scoring system that combines 4H structural regime detection, 1H momentum modifiers, and Range Bar intelligence to produce a single 0–100 CompositeScore that determines which strategy is active.

---

## Formula

```
CompositeScore = Layer 1 (4H Structural)     [0–100]
               + Layer 2 (1H Dynamic Modifier) [−15 to +15]
               + Layer 3 (Range Bar Intelligence) [0–20]

Final Score: Clamped to [0–100]
```

**Regime Mapping:**
- **CS ≥70:** TRENDING → TrendRider active (risk multiplier 1.0x)
- **CS 30–70:** TRANSITIONAL → BreakoutRider active (risk multiplier 0.6x)
- **CS <30:** RANGING → RangeRider active (risk multiplier 0.7x)

**Thresholds:** Configurable via `STRATEGY_TRENDRIDER_MIN_CS` (default 70), `STRATEGY_BREAKOUTRIDER_MIN_CS` (default 30)

---

## Layer 1: 4H Structural Score (0–100 points)

**Purpose:** Long-term regime foundation based on 4-hour OHLC data
**Components:** 5 sub-scores, each worth 0, 10, or 20 points
**Data Source:** 4H OHLC candles + CSM 9-pair grid

### Component 1: ADX Strength (0/10/20)

**Measures:** Trend strength via ADX(14) level and slope

**Scoring:**
- **20 pts:** ADX > P75 (75th percentile, ~25) AND rising slope
- **10 pts:** ADX between P25–P75 (~18–25)
- **0 pts:** ADX < P25 (~18) — weak/no trend

**Thresholds:** Loaded from `dcrd_config.json` (calibrated via `src/dcrd/calibrate.py`)
**Fallback:** P25=18, P75=25 if config unavailable

**Code:** `src/dcrd/structural_score.py::adx_strength_score()`

---

### Component 2: Market Structure (0/10/20)

**Measures:** Price swing pattern over last 20 bars

**Method:**
- Count Higher Highs + Higher Lows (HH/HL) for uptrend
- Count Lower Lows + Lower Highs (LL/LH) for downtrend

**Scoring:**
- **20 pts:** Strong structure (≥14/20 bars confirming trend = 70%)
- **10 pts:** Moderate structure (8–14/20 bars = 40–70%)
- **0 pts:** Choppy/alternating (<8/20 bars = <40%)

**Code:** `src/dcrd/structural_score.py::market_structure_score()`

---

### Component 3: ATR Expansion (0/10/20)

**Measures:** Current volatility vs recent average

**Method:**
- Calculate ATR(14) on 4H bars
- Compare current ATR to 20-bar rolling average ATR

**Scoring:**
- **20 pts:** ATR/avg_ATR > P75 (~1.2x) — expanding volatility
- **10 pts:** ATR/avg_ATR between P25–P75 (~0.8x–1.2x)
- **0 pts:** ATR/avg_ATR < P25 (~0.8x) — contracting volatility

**Thresholds:** Loaded from `dcrd_config.json`
**Fallback:** P25=0.8, P75=1.2

**Code:** `src/dcrd/structural_score.py::atr_expansion_score()`

---

### Component 4: CSM Alignment (0/10/20) ⭐

**Measures:** Currency Strength Meter — Are base and quote currencies moving in opposite directions?

**CSM 9-Pair Grid:**
```
Active 5:  EURUSD, GBPUSD, USDJPY, AUDJPY, USDCHF
Cross 4:   EURJPY, GBPJPY, EURGBP, AUDUSD
Currencies: EUR, GBP, USD, JPY, AUD, CHF
```

**Method:**
1. Calculate 20-bar return for each pair in the grid
2. Aggregate returns to build strength score for each currency:
   ```
   EUR_strength = +EURUSD_return +EURJPY_return +EURGBP_return
   USD_strength = -EURUSD_return +USDJPY_return +USDCHF_return
   GBP_strength = +GBPUSD_return +GBPJPY_return -EURGBP_return
   JPY_strength = -USDJPY_return -AUDJPY_return -EURJPY_return -GBPJPY_return
   AUD_strength = +AUDJPY_return +AUDUSD_return
   CHF_strength = -USDCHF_return
   ```
3. Rank currencies from strongest to weakest
4. For pair being evaluated (e.g., EURUSD):
   - Check if EUR is in top half (above median)
   - Check if USD is in bottom half (below median)
   - Calculate alignment percentage

**Scoring:**
- **20 pts:** Strong alignment (base > median AND quote < median, with ≥70% rank separation)
- **10 pts:** Moderate alignment OR insufficient data (default)
- **0 pts:** Divergent (both strong or both weak)

**Example (EURUSD):**
- If EUR ranks 1st/6 (strongest) and USD ranks 5th/6 (weak) → 20 pts
- If EUR ranks 3rd/6 and USD ranks 4th/6 (neutral) → 10 pts
- If EUR ranks 6th/6 and USD ranks 1st/6 (opposite direction!) → 0 pts

**Code:** `src/dcrd/structural_score.py::csm_alignment_score()`

---

### Component 5: Trend Persistence (0/10/20)

**Measures:** How consistently price stays above/below EMA(200)

**Method:**
- Calculate EMA(200) on 4H close
- Count how many of last 20 bars close on same side of EMA200

**Scoring:**
- **20 pts:** ≥14/20 bars same side (≥70% persistence)
- **10 pts:** 8–14/20 bars (40–70%)
- **0 pts:** <8/20 bars (<40% — price rotating around EMA)

**Code:** `src/dcrd/structural_score.py::trend_persistence_score()`

---

### Layer 1 Summary

**Total Range:** 0–100 points (sum of 5 components)
**Typical Distribution:**
- **90–100:** Very strong trending (all 5 components scoring 18–20)
- **70–90:** Moderate trending (4–5 components scoring 10–20)
- **30–70:** Transitional (mixed scoring, 2–3 components active)
- **0–30:** Ranging (most components scoring 0–10)

---

## Layer 2: 1H Dynamic Modifier (−15 to +15 points)

**Purpose:** Short-term momentum boost or penalty based on 1-hour data
**Components:** 3 sub-scores, each worth −5, 0, or +5
**Data Source:** 1H OHLC candles + CSM grid (1H resolution)

### Sub-Component 1: BB Width (−5/0/+5)

**Measures:** Bollinger Band expansion/contraction

**Method:**
- Calculate BB(20, 2.0σ) on 1H close
- Measure current BB width vs percentile distribution
- Width = (upper - lower) / middle

**Scoring:**
- **+5 pts:** BB width > P75 (~0.015) — expanding volatility, momentum building
- **0 pts:** BB width between P25–P75 (~0.008–0.015)
- **−5 pts:** BB width < P25 (~0.008) — squeezing, momentum fading

**Thresholds:** Loaded from `dcrd_config.json`

**Code:** `src/dcrd/dynamic_modifier.py::bb_width_score()`

---

### Sub-Component 2: ADX Acceleration (−5/0/+5)

**Measures:** Is ADX rising or falling on 1H timeframe?

**Method:**
- Calculate ADX(14) on 1H bars
- Measure 5-bar slope of ADX

**Scoring:**
- **+5 pts:** ADX slope > 0 (trend accelerating)
- **0 pts:** ADX slope ≈ 0 (stable)
- **−5 pts:** ADX slope < 0 (trend decelerating)

**Code:** `src/dcrd/dynamic_modifier.py::adx_acceleration_score()`

---

### Sub-Component 3: CSM Acceleration (−5/0/+5)

**Measures:** Is currency differential widening or narrowing?

**Method:**
- Calculate base/quote strength spread on 1H CSM grid
- Measure if spread is widening (momentum) or narrowing (rotation)

**Scoring:**
- **+5 pts:** Spread widening (base strengthening OR quote weakening faster)
- **0 pts:** Spread stable
- **−5 pts:** Spread narrowing (momentum reversing, rotation beginning)

**Code:** `src/dcrd/dynamic_modifier.py::csm_acceleration_score()`

---

### Layer 2 Summary

**Total Range:** −15 to +15 points (sum of 3 components)
**Purpose:** Fine-tune Layer 1 structural score with short-term momentum
**Clamping:** Modifier is clamped to [−15, +15] so it can never override structural classification
**Example:** If Layer 1 = 65 (Transitional), Layer 2 can push it to 50–80 but not flip to Trending

---

## Layer 3: Range Bar Intelligence (0–20 points)

**Purpose:** Price action momentum independent of time
**Components:** 2 sub-scores, each worth 0, 5, or 10
**Data Source:** Range Bar stream (20-pip bars for majors, 25-pip for JPY pairs)

### Sub-Component 1: RB Speed Score (0/5/10)

**Measures:** How fast are Range Bars forming?

**Method:**
- Count how many Range Bars formed in last 60 minutes
- High speed = high momentum (price moving rapidly through levels)

**Scoring:**
- **10 pts:** ≥3 bars/hour (P75, high momentum)
- **5 pts:** 1–3 bars/hour (normal)
- **0 pts:** <1 bar/hour (P25, slow/grinding)

**Thresholds:** Loaded from `dcrd_config.json` (recalibrated for 20-pip bars vs original 10-pip)
**Fallback:** P75=3.0, P25=1.0 bars/hour

**Code:** `src/dcrd/range_bar_intelligence.py::rb_speed_score()`

---

### Sub-Component 2: RB Structure Quality (0/5/10)

**Measures:** Directional consistency of Range Bar sequence

**Method:**
- Analyze last 20 Range Bars
- Count directional bars (same-direction movement)
- Detect pullback patterns vs alternating chop

**Scoring:**
- **10 pts:** Strong directional (≥70% bars in same direction, clean trend)
- **5 pts:** Mixed (some pullbacks, moderate structure)
- **0 pts:** Alternating/choppy (<40% directional, no clear pattern)

**Code:** `src/dcrd/range_bar_intelligence.py::rb_structure_quality_score()`

---

### Layer 3 Summary

**Total Range:** 0–20 points (sum of 2 components)
**Independence:** RB score is calculated independently of 4H/1H OHLC data
**Unique Value:** Captures price momentum that time-based indicators miss (e.g., rapid 3-bar move in 30 min)

---

## Anti-Flipping Filter (PRD §3.6)

**Purpose:** Prevent regime oscillation when score hovers near thresholds (70 or 30)

**Rules:**
1. Regime change requires score to cross threshold by **≥15 points**
2. New regime must persist for **≥2 consecutive 4H closes**

**Example:**
```
Current regime: TRENDING (CS=72)
Bar 1: CS drops to 68 → Still TRENDING (no 15pt cross)
Bar 2: CS drops to 65 → Pending TRANSITIONAL (crossed by 7pts but <15)
Bar 3: CS = 54 → Pending TRANSITIONAL (crossed by 18pts, count=1)
Bar 4: CS = 52 → Confirmed TRANSITIONAL (persisted 2 bars) ✅
```

**Config:**
- `ANTI_FLIP_THRESHOLD_PTS = 15`
- `ANTI_FLIP_PERSISTENCE = 2` (4H bars)

**Code:** `src/dcrd/dcrd_engine.py::_apply_anti_flip()`

---

## Example Calculation

### Scenario: EURUSD Strong Uptrend

**Layer 1 (4H Structural):**
```
ADX Strength:      20  (ADX = 32, rising slope)
Market Structure:  20  (17/20 bars are HH/HL)
ATR Expansion:     10  (ATR at 60th percentile, moderate)
CSM Alignment:     20  (EUR strongest, USD weakest in grid)
Trend Persistence: 20  (19/20 bars above EMA200)
────────────────────
Layer 1 Total:     90
```

**Layer 2 (1H Modifier):**
```
BB Width:          +5  (BB expanding rapidly, P80)
ADX Acceleration:   0  (ADX stable on 1H)
CSM Acceleration:  +5  (EUR/USD spread widening)
────────────────────
Layer 2 Total:    +10
```

**Layer 3 (Range Bar):**
```
RB Speed:          10  (4 bars formed in last hour, fast)
RB Structure:       5  (mostly directional, 2 pullback bars)
────────────────────
Layer 3 Total:     15
```

**Final CompositeScore:**
```
90 + 10 + 15 = 115 → Clamped to 100
Regime: TRENDING (CS ≥70)
Strategy: TrendRider active
Risk Multiplier: 1.0x
```

---

## Calibration System (v2.2)

DCRD thresholds are **data-driven** and stored in `data/dcrd_config.json`:

**Calibration Script:** `src/dcrd/calibrate.py`
**Process:**
1. Load 2 years of 4H/1H OHLC data
2. Calculate percentiles (P25, P50, P75) for each component
3. Write thresholds to `dcrd_config.json`
4. DCRD engine loads config at runtime

**Config Structure:**
```json
{
  "adx_strength": {"p25": 18.0, "p75": 25.0},
  "atr_expansion": {"p25": 0.8, "p75": 1.2},
  "bb_width": {"p25": 0.008, "p75": 0.015},
  "rb_speed": {"p25": 1.0, "p75": 3.0}
}
```

**Fallback:** If `dcrd_config.json` is missing, system uses v2.1 hardcoded defaults

**Validation:** VC.1, VC.4, VC.5 (PRD §9.4)

---

## Files Reference

| Component | File | Function |
|---|---|---|
| Main Engine | `src/dcrd/dcrd_engine.py` | `DCRDEngine.score()` |
| Layer 1 | `src/dcrd/structural_score.py` | `structural_score()` |
| - ADX Strength | `structural_score.py` | `adx_strength_score()` |
| - Market Structure | `structural_score.py` | `market_structure_score()` |
| - ATR Expansion | `structural_score.py` | `atr_expansion_score()` |
| - CSM Alignment | `structural_score.py` | `csm_alignment_score()` |
| - Trend Persistence | `structural_score.py` | `trend_persistence_score()` |
| Layer 2 | `src/dcrd/dynamic_modifier.py` | `dynamic_modifier()` |
| - BB Width | `dynamic_modifier.py` | `bb_width_score()` |
| - ADX Acceleration | `dynamic_modifier.py` | `adx_acceleration_score()` |
| - CSM Acceleration | `dynamic_modifier.py` | `csm_acceleration_score()` |
| Layer 3 | `src/dcrd/range_bar_intelligence.py` | `range_bar_score()` |
| - RB Speed | `range_bar_intelligence.py` | `rb_speed_score()` |
| - RB Structure | `range_bar_intelligence.py` | `rb_structure_quality_score()` |
| Calibration | `src/dcrd/calibrate.py` | `calibrate_dcrd()` |
| Config Storage | `data/dcrd_config.json` | (generated by calibration) |

---

## Configuration

**Regime Thresholds:**
```python
# src/config.py
STRATEGY_TRENDRIDER_MIN_CS = 70      # CS ≥70 → TRENDING
STRATEGY_BREAKOUTRIDER_MIN_CS = 30   # CS 30–70 → TRANSITIONAL
STRATEGY_RANGERIDER_MAX_CS = 30      # CS <30 → RANGING
```

**Anti-Flipping:**
```python
ANTI_FLIP_THRESHOLD_PTS = 15   # Must cross by ≥15 points
ANTI_FLIP_PERSISTENCE = 2      # Must persist for ≥2 bars
```

**CSM Grid:**
```python
CSM_PAIRS = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDJPY", "USDCHF",  # Active 5
    "EURJPY", "GBPJPY", "EURGBP", "AUDUSD",            # Cross 4
]
```

---

## Validation Gates

| Gate | Description | Status |
|---|---|---|
| VD.1 | All 3 layers contribute to output | ✅ PASS |
| VD.2 | Modifier clamped [−15, +15] | ✅ PASS |
| VD.3 | RB score independent of structural | ✅ PASS |
| VD.4 | CompositeScore maps correctly to regimes | ✅ PASS |
| VD.5 | Anti-flipping: ≥15pt cross + 2× persistence | ✅ PASS |
| VD.8 | Risk multiplier applied per regime | ✅ PASS |
| VC.1 | ADX thresholds data-driven | ✅ PASS (v2.2) |
| VC.4 | All DCRD thresholds percentile-based | ✅ PASS (v2.2) |
| VC.5 | RB speed recalibrated for 20-pip bars | ✅ PASS (v2.2) |

---

## Version History

### v2.2 (Current - Feb 2026)
- Migrated from 10-pip to 20-pip Range Bars (25-pip for JPY)
- Percentile-based calibration system (`dcrd_config.json`)
- RB speed thresholds recalibrated for larger bar sizes
- All thresholds data-driven from 2-year backtest dataset

### v2.1 (Jan 2026)
- Initial DCRD implementation
- Hardcoded thresholds (ADX P25=18, P75=25, etc.)
- 10-pip Range Bars
- Anti-flipping filter added

---

**Maintained By:** JcampFX Development Team
**Next Review:** When changing Range Bar sizes or regime thresholds
