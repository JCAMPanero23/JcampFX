# SwingRider Original Convex Design — Future Research Path

**Status**: Shelved (entry quality issues)
**Branch**: `feature/swingrider-convexity-amplifier`
**Commit**: d0a0ba1
**Date**: February 28, 2026

---

## Why Shelved

The original convex design implementation is **technically complete and functional**, but produces **poor entry quality**:

- **Win Rate**: 16.7% (vs target 35-45%)
- **Partial Reach Rate**: 16.7% (only 1/6 trades reached 2R)
- **Net Result**: -$124.63 (-2.87R) over 1.5 years
- **Entry Filters**: Too permissive (83.3% fail rate)

**Core Issue**: Daily regime filters + H4 breakout/engulfing triggers allow weak setups that fail to reach 2R partial exit target before hitting stop loss.

---

## What Was Implemented

### ✅ Technical Implementation (All Working)

1. **Data Infrastructure**:
   - `data_loader/daily_ohlc.py`: 4H → Daily OHLC resampling
   - Daily OHLC caching to `data/ohlc_daily/`
   - ATR calculation functions for daily charts

2. **Entry Logic** (`src/strategies/swing_rider.py`):
   - Daily EMA50 regime filter (price above/below + slope)
   - Market structure detection (HH/HL or LL/LH)
   - Weekly pivot bias filter
   - Daily pullback detection (2-5 candles + rejection wick)
   - H4 entry triggers (breakout OR engulfing)
   - Swing SL calculation (swing level ± 0.5×ATR14)

3. **Exit System** (`backtester/engine.py`):
   - Daily Chandelier SL (ATR22 × 3.0, updates once per day)
   - Volatility expansion accelerator (3.0 → 2.2 multiplier)
   - Hard invalidation checks (opposite structure / EMA50 penetration)
   - BE+0.2R runner protection after 2R partial exit

4. **Helper Functions** (`src/utils/swing_rider_helpers.py`):
   - Weekly pivot calculation
   - Daily regime checkers (long/short)
   - Pullback detection logic
   - H4 entry validators
   - Volatility expansion detector
   - Hard invalidation checker

---

## What Works Well

The **exit system** is excellent:
- Daily Chandelier successfully exited the ONE winning trade (+1.45R)
- Updates once per day (not every bar) as designed
- Volatility accelerator ready to activate
- BE+0.2R runner protection working
- Multi-day holds (winner held 14 days)

**When entries reach 2R, the system works beautifully.**

---

## What Needs Work

### Entry Filters Too Loose

**Problem**: 5 out of 6 trades hit SL before reaching 2R partial exit target.

**Potential Fixes** (not tested):

1. **Add Momentum Filter**:
   - Require ADX > 25 on daily chart (strong trend)
   - Require 1H momentum alignment (close above/below 1H EMA20)

2. **Tighten Pullback Rules**:
   - Reduce pullback range from 2-5 candles to 3-4 candles only
   - Increase rejection wick threshold from 30% to 40% of bar range
   - Require pullback to stay above/below key support/resistance

3. **Strengthen H4 Trigger**:
   - Require BOTH breakout AND engulfing (not OR)
   - Add H4 close confirmation (close in top/bottom 25% of bar)
   - Wait for second H4 confirmation bar

4. **Add Weekly Alignment**:
   - Require price above/below weekly EMA20 (not just pivot)
   - Require weekly trend alignment (weekly close in trend direction)

5. **Reduce Partial Target**:
   - Change from 2.0R to 1.5R (easier to reach)
   - This reduces required favorable move from 800-1400 pips to 600-1050 pips

---

## Future Research Paths

### Option 1: Fix and Re-test

**Approach**: Tighten entry filters as described above, obtain 7-year GBPJPY tick data (2018-2025), re-run full backtest.

**Expected Outcome**: Higher win rate (30-40%), better partial reach rate (40%+), but lower trade frequency (2-4/year).

**Risk**: May be over-optimizing to small sample size. Need minimum 40-100 trades to validate.

---

### Option 2: Hybrid Model (RECOMMENDED)

**Approach**: Keep daily regime + Chandelier exit, but replace daily pullback + H4 trigger with **Range Bar resumption entry**.

**Rationale**:
- Range Bar resumption entry has **52.6% win rate** (proven in Phase 3.6)
- Daily Chandelier exit is superior (allows multi-day trending holds)
- Hybrid leverages strengths of both systems

**Implementation**:
```python
# Entry: Range Bar resumption (like TrendRider)
if not self._detect_resumption_bar(range_bars, direction):
    return None

# But use daily regime filter as gate
if not check_daily_long_regime(ohlc_daily):
    return None

# And use swing SL (200-350 pips, not 60 pips)
sl = calculate_swing_sl(entry, swing_level, ohlc_daily)

# Runner: Daily Chandelier (not Range Bar trailing)
# (Already implemented in engine)
```

**Expected Outcome**:
- Win rate: 40-50% (Range Bar entry quality)
- Avg R/winner: 2.5R-4.5R (daily Chandelier captures larger moves)
- Trade frequency: 8-12/year (more selective due to daily regime gate)
- Convexity: Multi-day holds allow top 3 trades to be 30-50% of profit

---

### Option 3: Pure Swing System (For Future When Data Available)

**Approach**: Wait until 7-year GBPJPY tick data is available, then implement purist swing system:

- **Monthly regime filter**: Price above/below monthly EMA12
- **Weekly structure**: Weekly HH/HL or LL/LH
- **Daily pullback**: 5-10 candle deep retracement
- **H4 trigger**: Only take first H4 breakout after deep pullback
- **SL**: Weekly swing low/high (500-1000 pips)
- **Partial**: 3.0R @ 30%
- **Runner**: Weekly Chandelier (ATR30 × 4.0)
- **Expected**: 2-6 trades/year, 50% WR, 5R-10R avg winners

**Timeline**: Deferred until GBPJPY historical data acquired.

---

## Data Limitation

**Current**: GBPJPY Range Bar data from July 29, 2024 onwards (~1.5 years)
**Required**: GBPJPY tick data from 2018-2025 (7 years, 40-100 trade sample)

**To Acquire**:
1. Download GBPJPY tick data from Dukascopy or TrueFX (2018-2025)
2. Run `python -m src.data_fetcher --pair GBPJPY --start 2018-01-01 --end 2025-12-31`
3. Rebuild Range Bar cache: `python -m backtester.build_range_bars --pair GBPJPY`
4. Rebuild 4H/1H OHLC: `python -m src.data_fetcher --dcrd-only --pair GBPJPY`

---

## Key Learnings

1. **Exit system design is solid**: Daily Chandelier allows large wins when entries work
2. **Entry quality is critical**: Wide stops (200-730 pips) require high-quality entries
3. **2R partial target is ambitious**: Need 40%+ reach rate for positive expectancy
4. **Range Bar entry pattern works**: 52.6% WR proven in baseline (use it!)
5. **Daily regime filter has value**: But not sufficient on its own for entry timing

---

## References

- **Implementation Spec**: `docs/SwingRider_GBPJPY_Convex_Module.md`
- **Backtest Results**: `docs/SwingRider_Original_Backtest_Results.md`
- **Helper Functions**: `src/utils/swing_rider_helpers.py`
- **Strategy Code**: `src/strategies/swing_rider.py` (commit d0a0ba1)
- **Exit Logic**: `backtester/engine.py` (`_check_swingrider_runner_exits()`)

---

## Recommendation for Next Session

**Implement Option 2 (Hybrid Model)** on new branch:

```bash
git checkout -b feature/swingrider-hybrid
```

**Hybrid Spec**:
- Keep: Daily regime filter (gate)
- Keep: Daily Chandelier exit (runner)
- Keep: Swing SL sizes (200-350 pips)
- Keep: 2R partial @ 40% + BE+0.2R
- **Replace**: Daily pullback + H4 trigger → Range Bar resumption entry
- **Add**: Daily regime must confirm Range Bar signal

**Expected Result**: 40-50% WR, 2.5R-4.5R avg winners, 8-12 trades/year, convex profit profile.

---

**Status**: Ready to switch to hybrid approach ✅
