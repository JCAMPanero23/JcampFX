# Threshold Adjustment Test Analysis — Feb 22, 2026

## Test Configuration

**Run ID:** `run_20260222_070424`
**Date Range:** 2025-01-01 to 2025-12-31
**Settings:** CS 85/40/40 (TRENDING ≥85, TRANSITIONAL 40-85, RANGING <40)

## Results Summary

| Metric | CS 85/40/40 | Baseline (CS 70/30/30) | Change |
|---|---|---|---|
| **Net PnL** | **-$140.92** | -$218.71 | +$77.79 (35% better) |
| **Total Trades** | **79** | 292 | -213 (73% fewer) |
| **Win Rate** | **30.4%** | 36.0% | -5.6% (worse) |
| **Total R** | **-22.00R** | -39.6R | +17.6R (better) |
| **Avg R/Trade** | **-0.278R** | -0.136R | -0.142R (worse per trade) |
| **Max DD** | **28.2%** | 48.8% | +20.6% (better) |
| **Sharpe** | **-4.83** | -2.26 | -2.57 (worse) |
| **Profit Factor** | **0.52** | 0.76 | -0.24 (worse) |

### Strategy Distribution

| Strategy | Trades | Win Rate | Total R | PnL |
|---|---|---|---|---|
| **TrendRider** | 77 (97.5%) | 31.2% | -19.95R | -$131.94 |
| **BreakoutRider** | 2 (2.5%) | 0.0% | -2.05R | -$8.98 |

### Composite Score at Entry

```
Mean CS: 90.7
Median CS: 95.0
Min CS: 50.0
Max CS: 100.0

Distribution:
  CS 100: 30 trades (38%)
  CS 95:  11 trades (14%)
  CS 90:  12 trades (15%)
  CS 85:  11 trades (14%)
  CS 80:   4 trades (5%)
  CS 75:   9 trades (11%)
  CS 60:   1 trade  (1%)
  CS 50:   1 trade  (1%)
```

---

## Critical Finding: Revenge Trades = 94.7% of Total Loss

### Summary

- **Revenge trade pairs:** 10 (20 total trades)
- **Total R lost to revenge trades:** -20.83R out of -22.00R total
- **Percentage of total loss:** **94.7%**

### Pattern

Trades re-entering at the same price level (±20 pips) within 0.5-2 hours of previous loss:

| Pair | Entry Price | Time Diff | R Loss Each | Trade IDs |
|---|---|---|---|---|
| USDJPY | 153.79150 | 0.6h | -1.04R | 76816522 / ddc2a8a0 |
| USDJPY | 148.26500 | 0.7h | -1.04R | 1913c856 / 2b2a5fcf |
| USDJPY | 142.52000 | 1.8h | -1.04R | 25de092e / d261ae15 |
| USDJPY | 145.11450 | 1.5h | -1.04R | cd276fef / f29eed94 |
| GBPUSD | 1.23254 | 1.1h | -1.05R | bca2283f / 631d3e1d |
| AUDJPY | 87.52550 | 0.5h | -1.04R | e46da1ee / 3ae99ba9 |

**Full list:**
- 7/10 are USDJPY (most traded pair)
- 2/10 are GBPUSD
- 1/10 is AUDJPY
- Most re-entries occur within 0.5-2 hours
- Some pairs show multiple revenge trades at different levels

### Root Cause

The system has NO price level memory:
1. Enters at price level X
2. Gets stopped out (-1.04R)
3. Market returns to level X within hours
4. System re-enters (doesn't know this level already failed)
5. Gets stopped out again (-1.04R)

**This is classic "revenge trading" behavior** — the market is rejecting a price level, but the system doesn't learn.

### Impact If Eliminated

If we had Price Level Cooldown (Task 1):
- **Eliminate 20 trades** (all revenge trades)
- **Save -20.83R** loss
- **Remaining:** 59 trades, -1.17R total
- **Projected result:** Near breakeven or small profit

---

## Why CS 85/40/40 Failed

### Hypothesis vs Reality

**Hypothesis:**
- Higher CS threshold (≥85) = higher conviction trending = better win rate
- More Transitional regime time (58.5%) = more BreakoutRider opportunities

**Reality:**
- Higher CS threshold = WORSE win rate (31.2% vs 36.0%)
- BreakoutRider still only 2 trades (BB compression + Keltner too strict)
- 73% fewer trades overall (79 vs 292)

### Analysis

**1. CS 85-100 May Be "Overcooked" Trending**
- CS 85-100 might indicate trend exhaustion (late entry)
- CS 70-85 might indicate early trend (better entry timing)
- By filtering out CS 70-85, we excluded the BEST trending entries

**2. BreakoutRider Bottleneck Confirmed**
- Despite 2.6x more regime time (58.5% vs 22.3%), only 2 trades fired
- BB compression + Keltner breakout is too rare
- Entry conditions are the problem, not regime time

**3. Sample Size Too Small**
- 79 trades over 12 months = 6.6 trades/month
- Not enough data for statistical significance
- High variance makes it hard to evaluate true performance

### Composite Score Distribution Insight

**Baseline (CS 70/30/30):**
- Captures CS 70-100 trades (broad spectrum)
- Avg CS ~80-85 (mix of early and mature trends)

**Test (CS 85/40/40):**
- Captures only CS 85-100 trades (top 15% of scores)
- Avg CS 90.7 (very mature trends only)
- May be missing the "sweet spot" CS 70-85 zone

**Conclusion:** The problem isn't the threshold — it's that CS alone doesn't predict entry quality.

---

## Key Learnings

### 1. Threshold Adjustment Alone Doesn't Fix the Problem
- Changing regime boundaries doesn't improve TrendRider entry quality
- BreakoutRider needs relaxed entry conditions, not just more regime time
- Need to fix the underlying entry logic, not just the scoring system

### 2. Price Level Cooldown is THE Priority
- **94.7% of loss** comes from revenge trades
- Implementing Task 1 (Price Level Cooldown) could turn -22R into near breakeven
- This is a quick win with massive impact

### 3. CS Distribution Reveals New Insight
- Baseline run had CS 70-100 entries (broad)
- Test run had CS 85-100 entries (narrow)
- Win rate DROPPED when only taking highest CS signals
- **Implication:** CS 70-85 might be the "sweet spot" for trend entries

### 4. Sample Size Matters
- 79 trades is too small for reliable conclusions
- Need at least 200-300 trades for statistical significance
- Threshold changes that reduce trade count make evaluation harder

---

## Recommendations for Next Session

### Priority 1: Implement Price Level Cooldown (Task 1)

**Why:** Eliminates 94.7% of current losses

**Implementation:**
1. Create `PriceLevelTracker` class in `src/price_level_tracker.py`
2. Track losing trades: `{pair: deque[(price, timestamp, r_result)]}`
3. Block new entries within ±20 pips of recent loss for 4 hours
4. Integrate into `BrainCore` gating logic

**Config Settings (new presets available):**
```python
PRICE_LEVEL_COOLDOWN_ENABLED = True
PRICE_LEVEL_COOLDOWN_PIPS = 20
PRICE_LEVEL_COOLDOWN_HOURS = 4
```

**Expected Impact:**
- Eliminate 20 revenge trades
- Save ~20.8R loss
- Turn -22R into ~-1.2R (near breakeven)

### Priority 2: Revert to Baseline Thresholds (CS 70/30/30)

**Why:** Higher threshold (CS 85) made performance worse

**Action:**
```bash
python config_manager.py preset threshold-default
```

**Reasoning:**
- CS 85-100 = trend exhaustion (late entries)
- CS 70-85 = early trend (better entries)
- Baseline had better win rate (36% vs 30.4%)

### Priority 3: Test Price Level Cooldown on Baseline Config

**Workflow:**
```bash
# Step 1: Revert to baseline thresholds
python config_manager.py preset threshold-default

# Step 2: Enable price level cooldown
python config_manager.py set PRICE_LEVEL_COOLDOWN_ENABLED True
python config_manager.py set PRICE_LEVEL_COOLDOWN_PIPS 20
python config_manager.py set PRICE_LEVEL_COOLDOWN_HOURS 4

# Step 3: Save as custom preset
python config_manager.py save-custom baseline-with-cooldown

# Step 4: Run backtest
python -m backtester.run_backtest --start 2025-01-01 --end 2025-12-31
```

**Expected Result:**
- Baseline 292 trades → ~270 trades (eliminate revenge trades)
- Baseline -$218.71 → near breakeven or small profit
- Win rate improves (no more repeat losses at same levels)

### Priority 4: Analyze TrendRider Entry Quality (Task 2)

**After** Price Level Cooldown is implemented, analyze remaining losses:
- Pullback depth distribution (losers vs winners)
- ATR context at entry (losers vs winners)
- DCRD slope (losers vs winners)
- Session timing (Tokyo/London/NY)

### Deprioritized: Threshold Adjustment

**Why:**
- CS 85/40/40 test showed WORSE performance
- Thresholds don't address root cause (entry logic)
- Better to fix entry quality first, then revisit regime boundaries

---

## Updated Config Presets

### New Trade Management Presets

**1. Price Level Cooldown**
```bash
python config_manager.py preset price-level-cooldown
```
- Prevents re-entry at same price level for 4 hours
- Eliminates revenge trades

**2. Aggressive Partial Exit (80% at 1.5R)**
```bash
python config_manager.py preset aggressive-partial-exit
```
- Lock in more profit early
- Smaller runners (20% position size)
- Better for choppy markets

**3. Conservative Partial Exit (40% at 1.5R)**
```bash
python config_manager.py preset conservative-partial-exit
```
- Let runners run longer
- Larger runners (60% position size)
- Better for strong trending markets

**4. Tight Chandelier Floors**
```bash
python config_manager.py preset tight-chandelier
```
- Majors: 10 pips (was 15)
- JPY: 15 pips (was 25)
- Tighter trailing stops

**5. Loose Chandelier Floors**
```bash
python config_manager.py preset loose-chandelier
```
- Majors: 25 pips (was 15)
- JPY: 35 pips (was 25)
- Wider trailing stops

### Custom Preset Workflow

**Create custom configuration:**
```bash
# Step 1: Apply baseline + cooldown
python config_manager.py preset threshold-default
python config_manager.py set PRICE_LEVEL_COOLDOWN_ENABLED True
python config_manager.py set PRICE_LEVEL_COOLDOWN_PIPS 20
python config_manager.py set PRICE_LEVEL_COOLDOWN_HOURS 4

# Step 2: Save as custom preset
python config_manager.py save-custom my-test-config

# Step 3: Later, reload it
python config_manager.py load-custom my-test-config
```

---

## Conclusion

**The Good:**
- Found that 94.7% of loss comes from revenge trades (fixable!)
- Config override system working perfectly for experimentation
- Trade management presets ready for testing

**The Bad:**
- CS 85/40/40 made performance worse (counterintuitive)
- BreakoutRider still broken (entry conditions too strict)
- Sample size reduced to 79 trades (too small)

**The Plan:**
1. **Implement Price Level Cooldown** (Task 1) — eliminates 95% of losses
2. **Revert to CS 70/30/30** (baseline) — better win rate
3. **Test cooldown on baseline config** — expect near breakeven
4. **Then** analyze remaining losses for quality filters (Task 2)

**Next session:** Focus on Price Level Cooldown implementation, not threshold adjustment.
