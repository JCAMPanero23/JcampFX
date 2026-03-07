# Trade Inspector / Backtest Playback Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a bar-by-bar Trade Inspector at `/inspector` that loads per-trade context (Range Bars, DCRD layer breakdown, staircase metadata) and plays back the trade with VCR controls (Play/Pause, step, slider).

**Architecture:** Dash multi-page app (`use_pages=True`). BacktestTrade gains 6 new debug fields populated by TrendRider at signal time. A `backtester/playback.py` module loads trade context. `dashboard/pages/inspector.py` is the new page with animated candlestick + VCR controls. Cinema tab gets Inspect links.

**Tech Stack:** Python 3.11+, Dash 2.x (multi-page), Plotly graph_objects, pandas, Parquet (pyarrow), existing `DCRDEngine.score_components()` (already returns all 14 sub-scores).

---

## Task 1: Extend BacktestTrade with 6 debug fields

**Files:**
- Modify: `backtester/trade.py`
- Test: `tests/test_trade_fields.py` (new)

**Step 1: Write the failing test**

```python
# tests/test_trade_fields.py
from backtester.trade import BacktestTrade
import pandas as pd

def _make_trade(**kwargs):
    defaults = dict(
        trade_id="t1", pair="EURUSD", direction="BUY", strategy="TrendRider",
        entry_price=1.1000, sl_price=1.0980, entry_time=pd.Timestamp("2024-01-02 10:00", tz="UTC"),
        lot_size=0.01, initial_r_pips=20.0, composite_score=75.0, partial_exit_pct=0.75,
    )
    defaults.update(kwargs)
    return BacktestTrade(**defaults)

def test_new_debug_fields_default_none():
    t = _make_trade()
    assert t.adx_at_entry is None
    assert t.adx_slope_rising is None
    assert t.staircase_depth is None
    assert t.pullback_bar_idx is None
    assert t.pullback_depth_pips is None
    assert t.entry_bar_idx is None

def test_new_debug_fields_in_to_dict():
    t = _make_trade(adx_at_entry=28.5, adx_slope_rising=True,
                    staircase_depth=5, pullback_bar_idx=42,
                    pullback_depth_pips=18.3, entry_bar_idx=43)
    t.close_price = 1.103
    t.close_time = pd.Timestamp("2024-01-02 14:00", tz="UTC")
    t.close_reason = "CHANDELIER_HIT"
    d = t.to_dict()
    assert d["adx_at_entry"] == 28.5
    assert d["adx_slope_rising"] is True
    assert d["staircase_depth"] == 5
    assert d["pullback_bar_idx"] == 42
    assert d["pullback_depth_pips"] == 18.3
    assert d["entry_bar_idx"] == 43

def test_new_debug_fields_can_be_set():
    t = _make_trade()
    t.adx_at_entry = 31.2
    t.staircase_depth = 4
    assert t.adx_at_entry == 31.2
    assert t.staircase_depth == 4
```

**Step 2: Run test to verify it fails**

```
pytest tests/test_trade_fields.py -v
```
Expected: FAIL — `BacktestTrade.__init__() got unexpected keyword argument 'adx_at_entry'`

**Step 3: Add 6 new optional fields to BacktestTrade**

In `backtester/trade.py`, after the `atr14_at_partial: float = 0.0` line (line 62), add:

```python
    # Debug metadata (TrendRider only — None for other strategies)
    adx_at_entry: Optional[float] = None
    adx_slope_rising: Optional[bool] = None
    staircase_depth: Optional[int] = None
    pullback_bar_idx: Optional[int] = None     # absolute index in Range Bar cache
    pullback_depth_pips: Optional[float] = None
    entry_bar_idx: Optional[int] = None        # absolute index in Range Bar cache
```

In `to_dict()`, add these entries at the end of the dict:

```python
            "adx_at_entry": self.adx_at_entry,
            "adx_slope_rising": self.adx_slope_rising,
            "staircase_depth": self.staircase_depth,
            "pullback_bar_idx": self.pullback_bar_idx,
            "pullback_depth_pips": self.pullback_depth_pips,
            "entry_bar_idx": self.entry_bar_idx,
```

**Step 4: Run test to verify it passes**

```
pytest tests/test_trade_fields.py -v
```
Expected: 3 tests PASS.

**Step 5: Also run existing trade tests to verify no regression**

```
pytest tests/ -v -k "not test_backtest" --tb=short
```
Expected: All previously-passing tests still PASS.

**Step 6: Commit**

```bash
git -C D:/JcampFX add backtester/trade.py tests/test_trade_fields.py
git -C D:/JcampFX commit -m "feat(backtester): add 6 TrendRider debug fields to BacktestTrade"
```

---

## Task 2: Extend Signal with matching debug fields

**Files:**
- Modify: `src/signal.py`
- Test: `tests/test_signal_debug_fields.py` (new)

**Step 1: Write the failing test**

```python
# tests/test_signal_debug_fields.py
from src.signal import Signal
import pandas as pd

def _make_signal(**kwargs):
    defaults = dict(
        timestamp=pd.Timestamp("2024-01-02 10:00", tz="UTC"),
        pair="EURUSD", direction="BUY", entry=1.1000, sl=1.0980,
        tp_1r=1.1020, strategy="TrendRider", composite_score=75.0,
    )
    defaults.update(kwargs)
    return Signal(**defaults)

def test_signal_debug_fields_default_none():
    s = _make_signal()
    assert s.adx_at_entry is None
    assert s.adx_slope_rising is None
    assert s.staircase_depth is None
    assert s.pullback_bar_idx is None
    assert s.pullback_depth_pips is None
    assert s.entry_bar_idx is None

def test_signal_debug_fields_populate():
    s = _make_signal(adx_at_entry=28.5, adx_slope_rising=True,
                     staircase_depth=5, pullback_bar_idx=42,
                     pullback_depth_pips=18.3, entry_bar_idx=43)
    assert s.staircase_depth == 5
    assert s.entry_bar_idx == 43
```

**Step 2: Run test to verify it fails**

```
pytest tests/test_signal_debug_fields.py -v
```
Expected: FAIL — `Signal.__init__() got unexpected keyword argument 'adx_at_entry'`

**Step 3: Add 6 new optional fields to Signal**

In `src/signal.py`, after `session_tag: str = ""` (line 72), add:

```python
    # TrendRider debug metadata — populated by TrendRider.analyze(), None for other strategies
    adx_at_entry: Optional[float] = None
    adx_slope_rising: Optional[bool] = None
    staircase_depth: Optional[int] = None
    pullback_bar_idx: Optional[int] = None     # absolute index in Range Bar DataFrame
    pullback_depth_pips: Optional[float] = None
    entry_bar_idx: Optional[int] = None        # absolute index in Range Bar DataFrame
```

**Step 4: Run test**

```
pytest tests/test_signal_debug_fields.py -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git -C D:/JcampFX add src/signal.py tests/test_signal_debug_fields.py
git -C D:/JcampFX commit -m "feat(signal): add 6 TrendRider debug metadata fields"
```

---

## Task 3: Modify TrendRider to populate debug fields on Signal

**Files:**
- Modify: `src/strategies/trend_rider.py`
- Test: `tests/test_strategies.py` (add new test cases)

### Context

Looking at `trend_rider.py`, the staircase detection currently:
- `_detect_3bar_staircase(range_bars, direction)` — returns `bool` only; needs to also return depth
- `_find_pullback_entry(range_bars, direction)` — pullback bar is always `range_bars.iloc[-2]` and entry bar is `range_bars.iloc[-1]`

**Step 1: Modify `_detect_3bar_staircase` to return `int` depth (0 if not detected)**

Replace the function signature and return type. The current code sets `consecutive` and returns `True` when `consecutive >= _STAIRCASE_BARS`. Change it to return the final `consecutive` count when it passes, or 0 when it fails:

```python
def _detect_3bar_staircase(range_bars: pd.DataFrame, direction: str, lookback: int = 15) -> int:
    """
    Detect a 3-bar staircase pattern. Returns staircase depth (>= _STAIRCASE_BARS)
    if found, or 0 if not found. Callers can bool-test the return value.
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
                consecutive = 0
        else:
            if highs[i] < highs[i - 1] and lows[i] < lows[i - 1]:
                consecutive += 1
                max_consecutive = max(max_consecutive, consecutive)
            else:
                consecutive = 0

    return max_consecutive if max_consecutive >= _STAIRCASE_BARS else 0
```

**Step 2: Write the failing test for staircase depth return**

In `tests/test_strategies.py`, add:

```python
def test_staircase_returns_depth_not_bool():
    """_detect_3bar_staircase returns int depth, not bool."""
    from src.strategies.trend_rider import _detect_3bar_staircase
    bars = _make_buy_staircase(n=7)
    depth = _detect_3bar_staircase(bars, "BUY")
    assert isinstance(depth, int)
    assert depth >= 5  # at least _STAIRCASE_BARS

def test_staircase_returns_zero_when_not_found():
    from src.strategies.trend_rider import _detect_3bar_staircase
    import pandas as pd
    # Alternating bars — no staircase
    bars = pd.DataFrame({
        "high": [1.10, 1.09, 1.11, 1.09, 1.11, 1.09, 1.11],
        "low":  [1.09, 1.08, 1.10, 1.08, 1.10, 1.08, 1.10],
        "open": [1.095]*7, "close": [1.095]*7,
        "end_time": pd.date_range("2024-01-01", periods=7, freq="h"),
    })
    result = _detect_3bar_staircase(bars, "BUY")
    assert result == 0
```

Run:
```
pytest tests/test_strategies.py::test_staircase_returns_depth_not_bool tests/test_strategies.py::test_staircase_returns_zero_when_not_found -v
```
Expected: FAIL (function returns bool, not int).

**Step 3: Apply the `_detect_3bar_staircase` change**

Replace the function body in `src/strategies/trend_rider.py` with the version above.

**Step 4: Update `TrendRider.analyze()` to populate debug fields**

In the `analyze()` method, change:

```python
        # Step 2: Confirm 3-bar staircase
        if not _detect_3bar_staircase(range_bars, direction):
            return None
```

to:

```python
        # Step 2: Confirm 3-bar staircase
        staircase_depth = _detect_3bar_staircase(range_bars, direction)
        if not staircase_depth:
            return None
```

And change:

```python
        # Step 3: Confirm ADX > 25 AND rising
        adx = _adx_1h(ohlc_1h)
        if adx <= _ADX_THRESHOLD:
            log.debug("TrendRider: ADX %.1f ≤ 25 — no signal", adx)
            return None
        if not _adx_is_rising(ohlc_1h):
            log.debug("TrendRider: ADX %.1f not rising — declining momentum, skip", adx)
            return None
```

to:

```python
        # Step 3: Confirm ADX > 25 AND rising
        adx = _adx_1h(ohlc_1h)
        adx_rising = _adx_is_rising(ohlc_1h)
        if adx <= _ADX_THRESHOLD:
            log.debug("TrendRider: ADX %.1f ≤ 25 — no signal", adx)
            return None
        if not adx_rising:
            log.debug("TrendRider: ADX %.1f not rising — declining momentum, skip", adx)
            return None
```

And after `entry, sl, tp_1r = setup`, compute the absolute bar indices:

```python
        pip = PIP_SIZE.get(pair, 0.0001)
        pullback_bar_abs_idx = len(range_bars) - 2
        entry_bar_abs_idx = len(range_bars) - 1
        pullback_bar = range_bars.iloc[-2]
        pullback_depth_pips = float(pullback_bar["high"] - pullback_bar["low"]) / pip
```

And update the `Signal()` constructor call to include the 6 new fields:

```python
        signal = Signal(
            timestamp=pd.Timestamp(timestamp, tz="UTC") if not hasattr(timestamp, "tzinfo") else timestamp,
            pair=pair,
            direction=direction,
            entry=entry,
            sl=sl,
            tp_1r=tp_1r,
            strategy=self.name,
            composite_score=composite_score,
            partial_exit_pct=partial_pct,
            adx_at_entry=adx,
            adx_slope_rising=adx_rising,
            staircase_depth=staircase_depth,
            pullback_bar_idx=pullback_bar_abs_idx,
            pullback_depth_pips=pullback_depth_pips,
            entry_bar_idx=entry_bar_abs_idx,
        )
```

**Step 5: Write a test that TrendRider signal carries debug fields**

Add to `tests/test_strategies.py`:

```python
def test_trend_rider_signal_has_debug_fields(trend_rider_inputs):
    """TrendRider.analyze() should populate the 6 debug fields on the Signal."""
    strategy = TrendRider()
    signal = strategy.analyze(**trend_rider_inputs)
    if signal is not None:
        assert signal.adx_at_entry is not None
        assert isinstance(signal.adx_at_entry, float)
        assert signal.staircase_depth is not None
        assert signal.staircase_depth >= 5
        assert signal.pullback_bar_idx is not None
        assert signal.entry_bar_idx is not None
        assert signal.entry_bar_idx == signal.pullback_bar_idx + 1
        assert signal.pullback_depth_pips is not None
        assert signal.pullback_depth_pips > 0
```

Note: `trend_rider_inputs` should be an existing pytest fixture or use the inline helper from the existing test file. Check `tests/test_strategies.py` for the fixture name.

**Step 6: Run all strategy tests**

```
pytest tests/test_strategies.py -v
```
Expected: All PASS (including the 2 new staircase tests + the debug-fields test if a signal fires).

**Step 7: Commit**

```bash
git -C D:/JcampFX add src/strategies/trend_rider.py tests/test_strategies.py
git -C D:/JcampFX commit -m "feat(trendrider): surface staircase depth + ADX + bar indices on Signal"
```

---

## Task 4: Propagate debug fields from Signal to BacktestTrade in engine

**Files:**
- Modify: `backtester/engine.py` (line 388–400, BacktestTrade construction)
- Modify: `backtester/results.py` (BacktestTrade reconstruction from Parquet)
- Test: `tests/test_engine_debug_fields.py` (new)

### Context

`engine.py:388` creates `BacktestTrade(...)`. Currently it does NOT copy the 6 new fields from `signal`. We need to add them.

`results.py:300` reconstructs a `BacktestTrade` from a Parquet row during `BacktestResults.load()`. We need to add the 6 new fields there too.

**Step 1: Write the failing test for engine field propagation**

```python
# tests/test_engine_debug_fields.py
"""Test that engine propagates TrendRider debug fields from Signal to BacktestTrade."""
from unittest.mock import MagicMock, patch
import pandas as pd
from src.signal import Signal
from backtester.trade import BacktestTrade


def _make_signal_with_debug():
    return Signal(
        timestamp=pd.Timestamp("2024-01-02 10:00", tz="UTC"),
        pair="EURUSD", direction="BUY", entry=1.1000, sl=1.0980,
        tp_1r=1.1020, strategy="TrendRider", composite_score=75.0,
        lot_size=0.01, partial_exit_pct=0.75,
        adx_at_entry=28.5, adx_slope_rising=True,
        staircase_depth=5, pullback_bar_idx=42,
        pullback_depth_pips=18.3, entry_bar_idx=43,
    )


def test_trade_created_from_signal_carries_debug_fields():
    """When engine creates a BacktestTrade from a Signal, debug fields must be copied."""
    signal = _make_signal_with_debug()
    # Simulate what engine._open_trade does:
    pip = 0.0001
    initial_r_pips = abs(signal.entry - signal.sl) / pip
    trade = BacktestTrade(
        trade_id="test01",
        pair=signal.pair,
        direction=signal.direction,
        strategy=signal.strategy,
        entry_price=signal.entry,
        sl_price=signal.sl,
        entry_time=signal.timestamp,
        lot_size=signal.lot_size,
        initial_r_pips=initial_r_pips,
        composite_score=signal.composite_score,
        partial_exit_pct=signal.partial_exit_pct,
        adx_at_entry=signal.adx_at_entry,
        adx_slope_rising=signal.adx_slope_rising,
        staircase_depth=signal.staircase_depth,
        pullback_bar_idx=signal.pullback_bar_idx,
        pullback_depth_pips=signal.pullback_depth_pips,
        entry_bar_idx=signal.entry_bar_idx,
    )
    assert trade.adx_at_entry == 28.5
    assert trade.staircase_depth == 5
    assert trade.entry_bar_idx == 43
```

**Step 2: Run**

```
pytest tests/test_engine_debug_fields.py -v
```
Expected: PASS (we're just testing the dataclass accepts the values — not the engine yet).

**Step 3: Update engine.py BacktestTrade construction**

In `backtester/engine.py` at line 388, the `BacktestTrade(...)` constructor call, add 6 lines after `partial_exit_pct=signal.partial_exit_pct,`:

```python
            adx_at_entry=signal.adx_at_entry,
            adx_slope_rising=signal.adx_slope_rising,
            staircase_depth=signal.staircase_depth,
            pullback_bar_idx=signal.pullback_bar_idx,
            pullback_depth_pips=signal.pullback_depth_pips,
            entry_bar_idx=signal.entry_bar_idx,
```

**Step 4: Update results.py BacktestTrade reconstruction**

In `backtester/results.py` at line 300, add to the `BacktestTrade(...)` constructor call:

```python
            adx_at_entry=float(row["adx_at_entry"]) if row.get("adx_at_entry") is not None and not pd.isna(row.get("adx_at_entry", float("nan"))) else None,
            adx_slope_rising=bool(row["adx_slope_rising"]) if row.get("adx_slope_rising") is not None and not pd.isna(row.get("adx_slope_rising", float("nan"))) else None,
            staircase_depth=int(row["staircase_depth"]) if row.get("staircase_depth") is not None and not pd.isna(row.get("staircase_depth", float("nan"))) else None,
            pullback_bar_idx=int(row["pullback_bar_idx"]) if row.get("pullback_bar_idx") is not None and not pd.isna(row.get("pullback_bar_idx", float("nan"))) else None,
            pullback_depth_pips=float(row["pullback_depth_pips"]) if row.get("pullback_depth_pips") is not None and not pd.isna(row.get("pullback_depth_pips", float("nan"))) else None,
            entry_bar_idx=int(row["entry_bar_idx"]) if row.get("entry_bar_idx") is not None and not pd.isna(row.get("entry_bar_idx", float("nan"))) else None,
```

**Step 5: Run all tests**

```
pytest tests/ -v --tb=short
```
Expected: All PASS.

**Step 6: Re-run the backtest to generate enriched trades.parquet**

```
python -m backtester.run_backtest --pairs EURUSD GBPUSD USDJPY AUDJPY USDCHF --start 2024-01-01 --end 2025-12-31
```

Verify the new columns exist in the output:
```python
import pandas as pd
df = pd.read_parquet("data/backtest_results/<latest_run>/trades.parquet")
print(df[["trade_id","strategy","adx_at_entry","staircase_depth","pullback_bar_idx","entry_bar_idx"]].head())
```

Expected: TrendRider rows have non-null values; other strategy rows have NaN.

**Step 7: Commit**

```bash
git -C D:/JcampFX add backtester/engine.py backtester/results.py tests/test_engine_debug_fields.py
git -C D:/JcampFX commit -m "feat(engine): propagate TrendRider debug fields Signal→BacktestTrade→Parquet"
```

---

## Task 5: Create backtester/playback.py — trade context loader

**Files:**
- Create: `backtester/playback.py`
- Test: `tests/test_playback.py` (new)

### Context

`DCRDEngine.score_components()` (in `src/dcrd/dcrd_engine.py:154`) already returns all 14 sub-scores. We just need to call it with the right data sliced at entry time. The Range Bar cache is at `data/range_bars/{pair}_RB{pips}.parquet`. The `RANGE_BAR_PIPS` dict in `src/config.py` maps pair → pip size.

**Step 1: Write tests first**

```python
# tests/test_playback.py
"""Tests for backtester/playback.py — requires a real backtest run in data/backtest_results/."""
import pytest
from pathlib import Path
import pandas as pd

RESULTS_DIR = Path("data/backtest_results")
SKIP_IF_NO_RESULTS = pytest.mark.skipif(
    not any(RESULTS_DIR.iterdir()) if RESULTS_DIR.exists() else True,
    reason="No backtest results available"
)


@SKIP_IF_NO_RESULTS
def test_get_trade_context_returns_required_keys():
    from backtester.playback import get_trade_context
    # Load the most recent run
    runs = sorted(RESULTS_DIR.iterdir())
    run_dir = str(runs[-1])
    trades = pd.read_parquet(Path(run_dir) / "trades.parquet")
    trade_id = str(trades.iloc[0]["trade_id"])

    ctx = get_trade_context(run_dir, trade_id)

    assert "trade" in ctx
    assert "range_bars" in ctx
    assert "dcrd_per_bar" in ctx
    assert "dcrd_at_entry" in ctx
    assert "entry_bar_local_idx" in ctx
    assert "partial_exit_bar_local_idx" in ctx
    assert "close_bar_local_idx" in ctx


@SKIP_IF_NO_RESULTS
def test_range_bars_window_contains_entry():
    from backtester.playback import get_trade_context
    runs = sorted(Path("data/backtest_results").iterdir())
    run_dir = str(runs[-1])
    trades = pd.read_parquet(Path(run_dir) / "trades.parquet")
    trade_id = str(trades.iloc[0]["trade_id"])
    trade_row = trades.iloc[0]

    ctx = get_trade_context(run_dir, trade_id, context_bars=20)
    rb = ctx["range_bars"]
    entry_idx = ctx["entry_bar_local_idx"]

    # The bar at entry_bar_local_idx should have end_time >= entry_time
    entry_time = pd.Timestamp(trade_row["entry_time"])
    bar_time = pd.Timestamp(rb.iloc[entry_idx]["end_time"])
    assert bar_time >= entry_time - pd.Timedelta("1h")


@SKIP_IF_NO_RESULTS
def test_dcrd_at_entry_has_all_components():
    from backtester.playback import get_trade_context
    runs = sorted(Path("data/backtest_results").iterdir())
    run_dir = str(runs[-1])
    trades = pd.read_parquet(Path(run_dir) / "trades.parquet")
    # Find a TrendRider trade for richest debug data
    tr_trades = trades[trades["strategy"] == "TrendRider"]
    if tr_trades.empty:
        pytest.skip("No TrendRider trades in this run")
    trade_id = str(tr_trades.iloc[0]["trade_id"])

    ctx = get_trade_context(run_dir, trade_id)
    dcrd = ctx["dcrd_at_entry"]

    assert "composite_score" in dcrd
    assert "layer1_structural" in dcrd
    assert "layer2_modifier" in dcrd
    assert "layer3_rb_intelligence" in dcrd
    assert "l1_adx_strength" in dcrd
    assert "l2_bb_width" in dcrd
    assert "l3_rb_speed" in dcrd
```

**Step 2: Run tests (expect skip or fail)**

```
pytest tests/test_playback.py -v
```
Expected: SKIP (no module `backtester.playback` yet) or ImportError.

**Step 3: Create backtester/playback.py**

```python
"""
JcampFX — Trade Context Loader for Inspector (Phase 3.5)

Loads per-trade context from a backtest run:
  - Range Bar window (context bars before entry + all bars to close)
  - DCRD score per bar from dcrd_timeline.parquet
  - DCRD layer breakdown re-computed at entry time using score_components()
  - Local bar indices for entry, partial exit, close events

Usage
-----
    from backtester.playback import get_trade_context
    ctx = get_trade_context("data/backtest_results/run_20260219_190902", "a1b2c3d4")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from src.config import RANGE_BAR_PIPS, PIP_SIZE
from src.dcrd.dcrd_engine import DCRDEngine

log = logging.getLogger(__name__)

_RANGE_BAR_DIR = Path("data/range_bars")
_OHLC_4H_DIR = Path("data/ohlc_4h")
_OHLC_1H_DIR = Path("data/ohlc_1h")
_CSM_PAIRS = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDJPY", "USDCHF",
    "EURJPY", "GBPJPY", "EURGBP", "AUDUSD",
]


def get_trade_context(
    run_dir: str,
    trade_id: str,
    context_bars: int = 20,
) -> dict:
    """
    Load complete per-trade context for the Trade Inspector.

    Parameters
    ----------
    run_dir      : Path to backtest run directory (contains trades.parquet, dcrd_timeline.parquet)
    trade_id     : 8-char trade ID from trades.parquet
    context_bars : Number of Range Bars to include BEFORE the entry bar

    Returns
    -------
    dict with keys:
      trade                   : dict — full row from trades.parquet
      range_bars              : pd.DataFrame — context_bars + entry bar + bars to close
      dcrd_per_bar            : pd.DataFrame — CS per bar from dcrd_timeline.parquet
      dcrd_at_entry           : dict — all 14 DCRD sub-scores re-computed at entry time
      entry_bar_local_idx     : int — index in range_bars where entry occurs
      partial_exit_bar_local_idx : int | None
      close_bar_local_idx     : int
    """
    run_path = Path(run_dir)

    # --- Load trade row ---
    trades_df = pd.read_parquet(run_path / "trades.parquet")
    matches = trades_df[trades_df["trade_id"] == trade_id]
    if matches.empty:
        raise ValueError(f"Trade {trade_id!r} not found in {run_dir}")
    trade_row = matches.iloc[0].to_dict()
    pair = trade_row["pair"]

    entry_time = pd.Timestamp(trade_row["entry_time"])
    close_time = pd.Timestamp(trade_row["close_time"])
    partial_exit_time = (
        pd.Timestamp(trade_row["partial_exit_time"])
        if trade_row.get("partial_exit_time") is not None
        and not pd.isna(trade_row.get("partial_exit_time"))  # type: ignore[arg-type]
        else None
    )

    # --- Load Range Bars for this pair ---
    bar_pips = RANGE_BAR_PIPS.get(pair, 20)
    rb_path = _RANGE_BAR_DIR / f"{pair}_RB{bar_pips}.parquet"
    if not rb_path.exists():
        raise FileNotFoundError(f"Range Bar cache not found: {rb_path}")

    all_rb = pd.read_parquet(rb_path)
    if "end_time" not in all_rb.columns:
        raise ValueError("Range Bar cache missing 'end_time' column")

    all_rb = all_rb.sort_values("end_time").reset_index(drop=True)

    # Find entry bar index (first bar with end_time >= entry_time)
    entry_mask = all_rb["end_time"] >= entry_time
    if not entry_mask.any():
        raise ValueError(f"No Range Bar found at or after entry_time {entry_time}")
    entry_abs_idx = int(all_rb[entry_mask].index[0])

    # Find close bar index (first bar with end_time >= close_time)
    close_mask = all_rb["end_time"] >= close_time
    close_abs_idx = int(all_rb[close_mask].index[0]) if close_mask.any() else len(all_rb) - 1

    # Find partial exit bar index
    partial_exit_abs_idx: Optional[int] = None
    if partial_exit_time is not None:
        pe_mask = all_rb["end_time"] >= partial_exit_time
        if pe_mask.any():
            partial_exit_abs_idx = int(all_rb[pe_mask].index[0])

    # Slice window: context_bars before entry → close bar (inclusive)
    start_abs = max(0, entry_abs_idx - context_bars)
    end_abs = close_abs_idx + 1  # inclusive
    rb_window = all_rb.iloc[start_abs:end_abs].reset_index(drop=True)

    # Local indices within window
    entry_local = entry_abs_idx - start_abs
    close_local = close_abs_idx - start_abs
    partial_local: Optional[int] = (
        partial_exit_abs_idx - start_abs if partial_exit_abs_idx is not None else None
    )

    # --- Load DCRD timeline for pair + time window ---
    dcrd_path = run_path / "dcrd_timeline.parquet"
    dcrd_per_bar = pd.DataFrame()
    if dcrd_path.exists():
        dcrd_all = pd.read_parquet(dcrd_path)
        if "pair" in dcrd_all.columns and "time" in dcrd_all.columns:
            pair_dcrd = dcrd_all[dcrd_all["pair"] == pair].copy()
            window_start = all_rb.iloc[start_abs]["end_time"]
            window_end = all_rb.iloc[min(end_abs, len(all_rb) - 1)]["end_time"]
            dcrd_per_bar = pair_dcrd[
                (pair_dcrd["time"] >= window_start) & (pair_dcrd["time"] <= window_end)
            ].reset_index(drop=True)

    # --- Re-compute DCRD layer breakdown at entry time ---
    dcrd_at_entry = _recompute_dcrd_at_entry(pair, entry_time, rb_window, entry_local)

    return {
        "trade": trade_row,
        "range_bars": rb_window,
        "dcrd_per_bar": dcrd_per_bar,
        "dcrd_at_entry": dcrd_at_entry,
        "entry_bar_local_idx": entry_local,
        "partial_exit_bar_local_idx": partial_local,
        "close_bar_local_idx": close_local,
    }


def _recompute_dcrd_at_entry(
    pair: str,
    entry_time: pd.Timestamp,
    rb_window: pd.DataFrame,
    entry_local_idx: int,
) -> dict:
    """
    Re-run DCRDEngine.score_components() at entry_time to get the full 14-score breakdown.
    Returns a flat dict of all component scores (see DCRDEngine.score_components() docstring).
    """
    # Load 4H OHLC sliced to entry_time
    ohlc_4h = _load_ohlc_up_to(pair, entry_time, _OHLC_4H_DIR, min_bars=60)
    ohlc_1h = _load_ohlc_up_to(pair, entry_time, _OHLC_1H_DIR, min_bars=250)

    if ohlc_4h is None or ohlc_1h is None:
        log.warning("OHLC data missing for %s at %s — returning zero DCRD breakdown", pair, entry_time)
        return _zero_dcrd_breakdown()

    # Load CSM data (all 9 pairs, 4H, up to entry_time)
    csm_data: dict[str, pd.DataFrame] = {}
    for csm_pair in _CSM_PAIRS:
        df = _load_ohlc_up_to(csm_pair, entry_time, _OHLC_4H_DIR, min_bars=20)
        if df is not None:
            csm_data[csm_pair] = df

    # Range bars up to and including the entry bar
    rb_at_entry = rb_window.iloc[: entry_local_idx + 1]
    if len(rb_at_entry) < 5:
        log.warning("Not enough Range Bars at entry — returning zero DCRD breakdown")
        return _zero_dcrd_breakdown()

    engine = DCRDEngine()
    try:
        return engine.score_components(ohlc_4h, ohlc_1h, rb_at_entry, csm_data, pair)
    except Exception as exc:
        log.warning("DCRD re-computation failed for %s: %s", pair, exc)
        return _zero_dcrd_breakdown()


def _load_ohlc_up_to(
    pair: str,
    up_to: pd.Timestamp,
    ohlc_dir: Path,
    min_bars: int = 60,
) -> Optional[pd.DataFrame]:
    """Load OHLC Parquet for a pair, sliced to bars with close_time <= up_to."""
    candidates = list(ohlc_dir.glob(f"{pair}*.parquet"))
    if not candidates:
        return None
    df = pd.read_parquet(candidates[0])
    # Normalise time column name
    time_col = "close_time" if "close_time" in df.columns else (
        "time" if "time" in df.columns else df.columns[0]
    )
    df = df.sort_values(time_col)
    sliced = df[df[time_col] <= up_to]
    if len(sliced) < min_bars:
        return None
    return sliced.reset_index(drop=True)


def _zero_dcrd_breakdown() -> dict:
    return {
        "pair": "", "layer1_structural": 0, "l1_adx_strength": 0,
        "l1_market_structure": 0, "l1_atr_expansion": 0, "l1_csm_alignment": 0,
        "l1_trend_persistence": 0, "layer2_modifier": 0, "l2_bb_width": 0,
        "l2_adx_acceleration": 0, "l2_csm_acceleration": 0,
        "layer3_rb_intelligence": 0, "l3_rb_speed": 0, "l3_rb_structure": 0,
        "raw_composite": 0, "composite_score": 0, "regime": "unknown",
    }
```

**Step 4: Run tests**

```
pytest tests/test_playback.py -v
```
Expected: Tests run (may skip if OHLC data unavailable for DCRD re-computation, but should not error).

**Step 5: Commit**

```bash
git -C D:/JcampFX add backtester/playback.py tests/test_playback.py
git -C D:/JcampFX commit -m "feat(backtester): add playback.py trade context loader for Inspector"
```

---

## Task 6: Enable Dash multi-page and add Inspect links to Cinema tab

**Files:**
- Modify: `dashboard/app.py`
- Create: `dashboard/pages/__init__.py` (empty)

### Context

`dashboard/app.py:57` creates `dash.Dash(__name__, ...)` without `use_pages=True`. The Cinema trade table is built in a callback; we need to add an "Inspect" link column.

**Step 1: Create the pages package**

```python
# dashboard/pages/__init__.py
# (empty — marks this as a Python package)
```

**Step 2: Add `use_pages=True` and `pages_folder` to Dash app**

In `dashboard/app.py`, change the `app = dash.Dash(...)` call:

```python
app = dash.Dash(
    __name__,
    title="JcampFX Dashboard",
    suppress_callback_exceptions=True,
    use_pages=True,
    pages_folder=str(Path(__file__).parent / "pages"),
)
```

**Step 3: Add page container to the layout**

Find the main `app.layout` assignment in `app.py`. It currently renders the two-tab layout as the entire page. We need to wrap it so the existing content becomes the "home" page and the `dash.page_container` handles routing.

Add a top-level layout that includes `dash.page_container`:

```python
app.layout = html.Div([
    dcc.Location(id="_app-location", refresh=False),
    dash.page_container,
])
```

Then wrap the existing tab content in a `dash.register_page()` call. The simplest approach: register the existing layout as the home page directly in `app.py` using `dash.register_page("home", path="/", layout=existing_layout)`.

**Important:** Check what the existing `app.layout` looks like in `app.py` and identify the variable holding the tab structure. Wrap it and register as:

```python
import dash

_main_layout = html.Div([...])  # existing layout here

dash.register_page("home", path="/", layout=_main_layout)

app.layout = html.Div([
    dash.page_container,
])
```

**Step 4: Add Inspect link column to Cinema trade table**

Find the callback that builds the Cinema trade log table (search for `cinema-trade-table` in `app.py`). In the function that builds HTML table rows, add an `html.Td` with a link:

```python
# Inside the row-building loop, add:
html.Td(
    html.A(
        "Inspect",
        href=f"/inspector?run={run_id}&trade={row['trade_id']}",
        target="_blank",
        style={"color": "#4af", "textDecoration": "none", "fontSize": "11px"},
    )
)
```

Where `run_id` is the currently-selected backtest run ID (available from the cinema results store).

**Step 5: Run the dashboard and verify routing works**

```
python -m dashboard.app
```

Open `http://localhost:8050` — should show the existing Cinema/Chart tabs.
Open `http://localhost:8050/inspector` — should show a blank page (Inspector not built yet) without errors.

**Step 6: Commit**

```bash
git -C D:/JcampFX add dashboard/app.py dashboard/pages/__init__.py
git -C D:/JcampFX commit -m "feat(dashboard): enable multi-page routing, add Inspect links to Cinema table"
```

---

## Task 7: Build the Inspector page — layout + data loading

**Files:**
- Create: `dashboard/pages/inspector.py`
- No new test file (integration test via browser)

### Step 1: Create the page skeleton with layout

```python
# dashboard/pages/inspector.py
"""
JcampFX — Trade Inspector Page (Phase 3.5)

URL: /inspector?run=<run_id>&trade=<trade_id>&pair=<pair>&month=<YYYY-MM>&outcome=<win|loss|all>&strategy=<name>

Provides bar-by-bar Range Bar playback with VCR controls for a single backtest trade.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import dash
from dash import Input, Output, State, callback, dcc, html, ctx
from dash.exceptions import PreventUpdate

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import BACKTEST_RESULTS_DIR

dash.register_page(__name__, path="/inspector", title="Trade Inspector — JcampFX")

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

layout = html.Div([
    # URL reader (no refresh — we update it via JS/dcc.Location)
    dcc.Location(id="insp-url", refresh=False),

    # Data stores
    dcc.Store(id="insp-context", storage_type="memory"),
    dcc.Store(id="insp-frame", data=0, storage_type="memory"),
    dcc.Store(id="insp-filtered-trades", data=[], storage_type="memory"),
    dcc.Store(id="insp-is-playing", data=False, storage_type="memory"),

    # Auto-play interval (starts disabled)
    dcc.Interval(id="insp-interval", interval=2000, disabled=True, n_intervals=0),

    # Page container
    html.Div([

        # --- Filter Bar ---
        html.Div([
            html.Span("Run: ", style={"color": "#888", "marginRight": "4px"}),
            dcc.Dropdown(
                id="insp-filter-run",
                options=_get_run_options(),
                style={"width": "220px", "display": "inline-block", "marginRight": "12px"},
                clearable=False,
            ),
            dcc.Dropdown(
                id="insp-filter-pair",
                options=[{"label": "All Pairs", "value": "all"}] +
                        [{"label": p, "value": p} for p in
                         ["EURUSD", "GBPUSD", "USDJPY", "AUDJPY", "USDCHF"]],
                value="all",
                style={"width": "140px", "display": "inline-block", "marginRight": "12px"},
                clearable=False,
            ),
            dcc.Dropdown(
                id="insp-filter-month",
                options=[{"label": "All Months", "value": "all"}],
                value="all",
                style={"width": "140px", "display": "inline-block", "marginRight": "12px"},
                clearable=False,
            ),
            dcc.Dropdown(
                id="insp-filter-outcome",
                options=[
                    {"label": "All Outcomes", "value": "all"},
                    {"label": "Win (R > 0)", "value": "win"},
                    {"label": "Loss (R <= 0)", "value": "loss"},
                ],
                value="all",
                style={"width": "160px", "display": "inline-block", "marginRight": "12px"},
                clearable=False,
            ),
            dcc.Dropdown(
                id="insp-filter-strategy",
                options=[
                    {"label": "All Strategies", "value": "all"},
                    {"label": "TrendRider", "value": "TrendRider"},
                    {"label": "BreakoutRider", "value": "BreakoutRider"},
                    {"label": "RangeRider", "value": "RangeRider"},
                ],
                value="all",
                style={"width": "160px", "display": "inline-block"},
                clearable=False,
            ),
        ], style={"padding": "8px 16px", "background": "#1a1a2e", "display": "flex",
                  "alignItems": "center", "flexWrap": "wrap", "gap": "4px"}),

        # --- Navigation Bar ---
        html.Div([
            html.Button("⟵ Prev", id="insp-btn-prev", n_clicks=0,
                        style={"marginRight": "12px"}),
            html.Span(id="insp-nav-label",
                      children="Trade — / —",
                      style={"color": "#ccc", "minWidth": "220px", "textAlign": "center",
                             "display": "inline-block"}),
            html.Button("Next ⟶", id="insp-btn-next", n_clicks=0,
                        style={"marginLeft": "12px"}),
        ], style={"padding": "6px 16px", "background": "#111",
                  "display": "flex", "alignItems": "center"}),

        # --- Main 3-column content ---
        html.Div([

            # Left: Trade metadata
            html.Div(id="insp-meta-panel", style={
                "width": "22%", "padding": "12px", "background": "#0d1117",
                "borderRight": "1px solid #333", "fontSize": "12px",
                "overflowY": "auto", "minHeight": "480px",
            }),

            # Center: Chart
            html.Div([
                dcc.Graph(
                    id="insp-rb-chart",
                    config={"displayModeBar": False},
                    style={"height": "480px"},
                ),
            ], style={"width": "54%", "padding": "0"}),

            # Right: DCRD breakdown
            html.Div(id="insp-dcrd-panel", style={
                "width": "24%", "padding": "12px", "background": "#0d1117",
                "borderLeft": "1px solid #333", "fontSize": "12px",
                "overflowY": "auto", "minHeight": "480px",
            }),

        ], style={"display": "flex", "height": "480px"}),

        # --- VCR Controls ---
        html.Div([
            # Buttons row
            html.Div([
                html.Button("|⟸", id="insp-btn-start", n_clicks=0, title="Jump to start"),
                html.Button("◁", id="insp-btn-step-back", n_clicks=0, title="Step back"),
                html.Button("▶ Play", id="insp-btn-play", n_clicks=0,
                            style={"minWidth": "80px"}),
                html.Button("▷", id="insp-btn-step-fwd", n_clicks=0, title="Step forward"),
                html.Button("⟹|", id="insp-btn-end", n_clicks=0, title="Jump to end"),
                html.Span("  Speed: ", style={"color": "#888", "marginLeft": "16px"}),
                dcc.Dropdown(
                    id="insp-speed",
                    options=[
                        {"label": "0.5x", "value": 4000},
                        {"label": "1x", "value": 2000},
                        {"label": "2x", "value": 1000},
                        {"label": "5x", "value": 400},
                        {"label": "10x", "value": 200},
                    ],
                    value=2000,
                    clearable=False,
                    style={"width": "90px", "display": "inline-block"},
                ),
            ], style={"display": "flex", "alignItems": "center", "gap": "4px",
                      "marginBottom": "8px"}),

            # Slider row
            html.Div([
                dcc.Slider(
                    id="insp-slider",
                    min=0, max=1, step=1, value=0,
                    marks={},
                    tooltip={"always_visible": False},
                    updatemode="drag",
                ),
            ], style={"padding": "0 8px"}),

            # Time label
            html.Div(id="insp-time-label",
                     style={"color": "#888", "fontSize": "11px",
                            "textAlign": "center", "marginTop": "4px"}),

        ], style={"padding": "12px 16px", "background": "#0d1117",
                  "borderTop": "1px solid #333"}),

    ], style={"fontFamily": "monospace", "background": "#0d0d14",
              "minHeight": "100vh", "color": "#ddd"}),
], style={"margin": 0, "padding": 0})


def _get_run_options() -> list[dict]:
    """Scan BACKTEST_RESULTS_DIR for available runs."""
    results_dir = Path(BACKTEST_RESULTS_DIR)
    if not results_dir.exists():
        return []
    runs = sorted(results_dir.iterdir(), reverse=True)
    return [{"label": r.name, "value": r.name} for r in runs if r.is_dir()]
```

**Step 2: Verify page loads**

```
python -m dashboard.app
```
Open `http://localhost:8050/inspector` — should show layout (no trade loaded yet, panels empty). No errors in console.

**Step 3: Commit the skeleton**

```bash
git -C D:/JcampFX add dashboard/pages/inspector.py
git -C D:/JcampFX commit -m "feat(inspector): add Inspector page skeleton layout"
```

---

## Task 8: Inspector callbacks — context loading, filtering, navigation

**Files:**
- Modify: `dashboard/pages/inspector.py` (add callbacks)

### Callback 1: Load trade context from URL params

```python
@callback(
    Output("insp-context", "data"),
    Output("insp-frame", "data"),
    Output("insp-slider", "max"),
    Output("insp-slider", "value"),
    Input("insp-url", "search"),
    Input("insp-filter-run", "value"),
    prevent_initial_call=True,
)
def load_context(url_search: str, selected_run: str):
    """When URL changes (trade= param), load trade context into store."""
    from backtester.playback import get_trade_context
    import urllib.parse

    if not url_search:
        raise PreventUpdate

    params = dict(urllib.parse.parse_qsl(url_search.lstrip("?")))
    trade_id = params.get("trade")
    run_id = params.get("run") or selected_run

    if not trade_id or not run_id:
        raise PreventUpdate

    run_dir = str(Path(BACKTEST_RESULTS_DIR) / run_id)
    try:
        ctx_data = get_trade_context(run_dir, trade_id, context_bars=20)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise PreventUpdate

    # Serialize for dcc.Store (DataFrames → JSON-safe dicts)
    serialized = {
        "trade": ctx_data["trade"],
        "range_bars": ctx_data["range_bars"].to_json(orient="records", date_format="iso"),
        "dcrd_per_bar": ctx_data["dcrd_per_bar"].to_json(orient="records", date_format="iso"),
        "dcrd_at_entry": ctx_data["dcrd_at_entry"],
        "entry_bar_local_idx": ctx_data["entry_bar_local_idx"],
        "partial_exit_bar_local_idx": ctx_data["partial_exit_bar_local_idx"],
        "close_bar_local_idx": ctx_data["close_bar_local_idx"],
    }

    total_frames = ctx_data["close_bar_local_idx"] + 1
    return serialized, 0, total_frames - 1, 0
```

### Callback 2: Populate filter dropdowns from run's trades

```python
@callback(
    Output("insp-filter-month", "options"),
    Output("insp-filtered-trades", "data"),
    Output("insp-nav-label", "children"),
    Input("insp-filter-run", "value"),
    Input("insp-filter-pair", "value"),
    Input("insp-filter-month", "value"),
    Input("insp-filter-outcome", "value"),
    Input("insp-filter-strategy", "value"),
    Input("insp-url", "search"),
    prevent_initial_call=True,
)
def filter_trades(run_id, pair, month, outcome, strategy, url_search):
    """Build filtered trade list from selected run + filter dropdowns."""
    import urllib.parse

    if not run_id:
        raise PreventUpdate

    trades_path = Path(BACKTEST_RESULTS_DIR) / run_id / "trades.parquet"
    if not trades_path.exists():
        raise PreventUpdate

    df = pd.read_parquet(trades_path)
    df["entry_month"] = pd.to_datetime(df["entry_time"]).dt.strftime("%Y-%m")

    # Month options
    months = sorted(df["entry_month"].unique())
    month_opts = [{"label": "All Months", "value": "all"}] + [
        {"label": m, "value": m} for m in months
    ]

    # Apply filters
    filtered = df.copy()
    if pair and pair != "all":
        filtered = filtered[filtered["pair"] == pair]
    if month and month != "all":
        filtered = filtered[filtered["entry_month"] == month]
    if outcome == "win":
        filtered = filtered[filtered["r_multiple_total"] > 0]
    elif outcome == "loss":
        filtered = filtered[filtered["r_multiple_total"] <= 0]
    if strategy and strategy != "all":
        filtered = filtered[filtered["strategy"] == strategy]

    trade_ids = filtered["trade_id"].tolist()

    # Find current position in filtered list
    params = dict(urllib.parse.parse_qsl((url_search or "").lstrip("?")))
    current_id = params.get("trade", "")
    try:
        pos = trade_ids.index(current_id) + 1
    except ValueError:
        pos = 0

    total = len(trade_ids)
    label = f"Trade {pos} of {total}" if pos else f"— of {total}"

    return month_opts, trade_ids, label
```

### Callback 3: Prev/Next navigation updates URL

```python
@callback(
    Output("insp-url", "search"),
    Input("insp-btn-prev", "n_clicks"),
    Input("insp-btn-next", "n_clicks"),
    State("insp-filtered-trades", "data"),
    State("insp-url", "search"),
    State("insp-filter-run", "value"),
    prevent_initial_call=True,
)
def navigate_trade(prev_clicks, next_clicks, trade_ids, url_search, run_id):
    import urllib.parse

    if not trade_ids:
        raise PreventUpdate

    params = dict(urllib.parse.parse_qsl((url_search or "").lstrip("?")))
    current_id = params.get("trade", "")

    try:
        idx = trade_ids.index(current_id)
    except ValueError:
        idx = -1

    triggered = ctx.triggered_id
    if triggered == "insp-btn-prev":
        new_idx = max(0, idx - 1)
    else:
        new_idx = min(len(trade_ids) - 1, idx + 1)

    new_id = trade_ids[new_idx]
    new_params = {**params, "trade": new_id, "run": run_id or params.get("run", "")}
    return "?" + urllib.parse.urlencode(new_params)
```

**Step 1: Add these 3 callbacks to `dashboard/pages/inspector.py`**

**Step 2: Start the app and verify**

```
python -m dashboard.app
```

Navigate to `/inspector?run=<latest_run>&trade=<first_trade_id>`.
Verify: trade context loads (check browser console for errors), month dropdown populates, nav label shows "Trade 1 of N".

**Step 3: Commit**

```bash
git -C D:/JcampFX add dashboard/pages/inspector.py
git -C D:/JcampFX commit -m "feat(inspector): add context loading, filter, and navigation callbacks"
```

---

## Task 9: Inspector callbacks — VCR playback controls

**Files:**
- Modify: `dashboard/pages/inspector.py` (add VCR callbacks)

### Callback 4: Play/Pause toggle

```python
@callback(
    Output("insp-interval", "disabled"),
    Output("insp-interval", "interval"),
    Output("insp-btn-play", "children"),
    Output("insp-is-playing", "data"),
    Input("insp-btn-play", "n_clicks"),
    State("insp-is-playing", "data"),
    State("insp-speed", "value"),
    prevent_initial_call=True,
)
def toggle_play(n_clicks, is_playing, speed_ms):
    new_playing = not is_playing
    return (
        not new_playing,    # interval disabled when not playing
        speed_ms,
        "▐▐ Pause" if new_playing else "▶ Play",
        new_playing,
    )
```

### Callback 5: Interval tick → advance frame

```python
@callback(
    Output("insp-frame", "data", allow_duplicate=True),
    Input("insp-interval", "n_intervals"),
    State("insp-frame", "data"),
    State("insp-slider", "max"),
    State("insp-is-playing", "data"),
    prevent_initial_call=True,
)
def interval_tick(n_intervals, frame, max_frame, is_playing):
    if not is_playing:
        raise PreventUpdate
    if frame >= max_frame:
        return 0  # wrap around
    return frame + 1
```

### Callback 6: Step / Jump buttons → set frame

```python
@callback(
    Output("insp-frame", "data", allow_duplicate=True),
    Input("insp-btn-start", "n_clicks"),
    Input("insp-btn-step-back", "n_clicks"),
    Input("insp-btn-step-fwd", "n_clicks"),
    Input("insp-btn-end", "n_clicks"),
    State("insp-frame", "data"),
    State("insp-slider", "max"),
    prevent_initial_call=True,
)
def step_buttons(start, back, fwd, end, frame, max_frame):
    triggered = ctx.triggered_id
    if triggered == "insp-btn-start":
        return 0
    if triggered == "insp-btn-end":
        return max_frame
    if triggered == "insp-btn-step-back":
        return max(0, frame - 1)
    if triggered == "insp-btn-step-fwd":
        return min(max_frame, frame + 1)
    raise PreventUpdate
```

### Callback 7: Slider sync (frame → slider)

```python
@callback(
    Output("insp-slider", "value", allow_duplicate=True),
    Input("insp-frame", "data"),
    prevent_initial_call=True,
)
def sync_slider(frame):
    return frame
```

### Callback 8: Slider → frame (with deduplication guard)

```python
@callback(
    Output("insp-frame", "data", allow_duplicate=True),
    Input("insp-slider", "value"),
    State("insp-frame", "data"),
    prevent_initial_call=True,
)
def slider_to_frame(slider_val, current_frame):
    if slider_val == current_frame:
        raise PreventUpdate
    return slider_val
```

**Step 1: Add all 5 VCR callbacks to inspector.py**

**Step 2: Verify in browser**

Load a trade in the inspector. Click ▶ Play — chart should animate. Click ▐▐ Pause — stops. Use ◁ / ▷ step buttons. Drag slider — jumps to frame. Change speed — interval updates.

**Step 3: Commit**

```bash
git -C D:/JcampFX add dashboard/pages/inspector.py
git -C D:/JcampFX commit -m "feat(inspector): add VCR playback controls (play/pause/step/slider)"
```

---

## Task 10: Inspector callbacks — chart rendering

**Files:**
- Modify: `dashboard/pages/inspector.py` (add render_frame callback)

### Callback 9: Render frame → animated candlestick chart

```python
@callback(
    Output("insp-rb-chart", "figure"),
    Output("insp-time-label", "children"),
    Input("insp-frame", "data"),
    State("insp-context", "data"),
    prevent_initial_call=True,
)
def render_frame(frame: int, context_data: dict):
    if not context_data:
        raise PreventUpdate

    rb_df = pd.read_json(context_data["range_bars"], orient="records")
    rb_df["end_time"] = pd.to_datetime(rb_df["end_time"])

    trade = context_data["trade"]
    entry_local = context_data["entry_bar_local_idx"]
    partial_local = context_data["partial_exit_bar_local_idx"]
    close_local = context_data["close_bar_local_idx"]

    # Only show bars up to current frame
    visible = rb_df.iloc[: frame + 1]

    fig = go.Figure()

    # --- Background color bands for staircase / pullback / resumption bars ---
    # Staircase bars: entry_local - staircase_depth to entry_local - 2
    # Pullback bar: entry_local - 1 (bar[-2] in context)
    # Resumption/entry bar: entry_local

    staircase_depth = trade.get("staircase_depth") or 0
    staircase_start = max(0, entry_local - staircase_depth - 1)
    staircase_end = max(0, entry_local - 2)

    shapes = []
    if frame >= entry_local and staircase_depth > 0:
        # Yellow band for staircase bars
        for i in range(staircase_start, staircase_end + 1):
            if i < len(rb_df):
                shapes.append(dict(
                    type="rect", xref="x", yref="paper",
                    x0=i - 0.4, x1=i + 0.4, y0=0, y1=1,
                    fillcolor="rgba(255,200,0,0.15)", line_width=0, layer="below",
                ))
        # Orange band for pullback bar (entry_local - 1)
        pb_i = entry_local - 1
        if pb_i >= 0:
            shapes.append(dict(
                type="rect", xref="x", yref="paper",
                x0=pb_i - 0.4, x1=pb_i + 0.4, y0=0, y1=1,
                fillcolor="rgba(255,120,0,0.25)", line_width=0, layer="below",
            ))
        # Blue band for entry/resumption bar
        shapes.append(dict(
            type="rect", xref="x", yref="paper",
            x0=entry_local - 0.4, x1=entry_local + 0.4, y0=0, y1=1,
            fillcolor="rgba(0,150,255,0.25)", line_width=0, layer="below",
        ))

    # Candlestick trace (visible bars only)
    fig.add_trace(go.Candlestick(
        x=list(range(len(visible))),
        open=visible["open"],
        high=visible["high"],
        low=visible["low"],
        close=visible["close"],
        increasing_line_color="#26a69a",
        decreasing_line_color="#ef5350",
        name="Range Bars",
        showlegend=False,
    ))

    # SL and 1.5R lines (appear from entry bar onward)
    if frame >= entry_local:
        entry_price = trade["entry_price"]
        sl_price = trade["sl_price"]
        r_dist = abs(entry_price - sl_price)
        tp_1_5r = entry_price + 1.5 * r_dist if trade["direction"] == "BUY" else entry_price - 1.5 * r_dist

        # SL line
        fig.add_hline(y=sl_price, line_dash="solid", line_color="red",
                      line_width=1.5, annotation_text="SL",
                      annotation_font_color="red")
        # 1.5R line
        fig.add_hline(y=tp_1_5r, line_dash="dash", line_color="#00ff88",
                      line_width=1.5, annotation_text="1.5R",
                      annotation_font_color="#00ff88")

        # Entry marker
        fig.add_trace(go.Scatter(
            x=[entry_local], y=[entry_price],
            mode="markers",
            marker=dict(symbol="triangle-up" if trade["direction"] == "BUY" else "triangle-down",
                        color="#00aaff", size=14),
            name="Entry", showlegend=False,
        ))

    # Partial exit marker
    if partial_local is not None and frame >= partial_local:
        pe_price = trade.get("partial_exit_price", 0)
        if pe_price:
            fig.add_trace(go.Scatter(
                x=[partial_local], y=[pe_price],
                mode="markers",
                marker=dict(symbol="diamond", color="orange", size=12),
                name="Partial Exit", showlegend=False,
            ))

    # Close marker
    if frame >= close_local:
        close_price = trade.get("close_price", 0)
        r_total = trade.get("r_multiple_total", 0)
        color = "#26a69a" if r_total > 0 else "#ef5350"
        fig.add_trace(go.Scatter(
            x=[close_local], y=[close_price],
            mode="markers+text",
            marker=dict(symbol="x", color=color, size=14, line_width=2),
            text=[f"{r_total:+.2f}R"],
            textposition="top center",
            textfont=dict(color=color, size=10),
            name="Close", showlegend=False,
        ))

    fig.update_layout(
        paper_bgcolor="#0d1117",
        plot_bgcolor="#0d1117",
        font=dict(color="#ddd", family="monospace", size=10),
        margin=dict(l=60, r=20, t=20, b=20),
        xaxis=dict(
            showgrid=True, gridcolor="#1e2a3a", zeroline=False,
            rangeslider=dict(visible=False),
            ticktext=[str(rb_df.iloc[i]["end_time"])[:16] for i in range(0, min(len(visible), 40), max(1, len(visible)//8))],
            tickvals=list(range(0, min(len(visible), 40), max(1, len(visible)//8))),
        ),
        yaxis=dict(showgrid=True, gridcolor="#1e2a3a", zeroline=False),
        shapes=shapes,
        hovermode="x unified",
    )

    # Time label
    if frame < len(rb_df):
        bar_time = str(rb_df.iloc[frame]["end_time"])[:19]
        time_label = f"bar {frame + 1} / {len(rb_df)}  ·  {bar_time} UTC"
    else:
        time_label = ""

    return fig, time_label
```

**Step 1: Add the render_frame callback to inspector.py**

**Step 2: Test in browser**

Load a trade. Step through bars — chart should build up one bar at a time. At entry bar: SL line, 1.5R line, and entry marker appear. At partial exit bar: orange diamond appears (if trade won). At close bar: X marker with R-multiple annotation.

**Step 3: Commit**

```bash
git -C D:/JcampFX add dashboard/pages/inspector.py
git -C D:/JcampFX commit -m "feat(inspector): add animated candlestick chart rendering with trade markers"
```

---

## Task 11: Inspector callbacks — metadata + DCRD panels

**Files:**
- Modify: `dashboard/pages/inspector.py` (add panel callbacks)

### Callback 10: Render meta panel (left)

```python
@callback(
    Output("insp-meta-panel", "children"),
    Input("insp-context", "data"),
    prevent_initial_call=True,
)
def render_meta_panel(context_data: dict):
    if not context_data:
        return html.Div("No trade loaded.", style={"color": "#555"})

    trade = context_data["trade"]

    def row(label: str, value) -> html.Div:
        return html.Div([
            html.Span(label + ": ", style={"color": "#888"}),
            html.Span(str(value) if value is not None else "—",
                      style={"color": "#eee", "fontWeight": "bold"}),
        ], style={"marginBottom": "4px"})

    entry_time_str = str(trade.get("entry_time", ""))[:19]
    close_time_str = str(trade.get("close_time", ""))[:19]
    r_total = trade.get("r_multiple_total", 0) or 0
    r_color = "#26a69a" if r_total > 0 else "#ef5350"

    close_reason = trade.get("close_reason", "—")
    reason_color = {
        "SL_HIT": "#ef5350", "CHANDELIER_HIT": "#ffa726",
        "2R_CAP": "#ab47bc", "WEEKEND_CLOSE": "#78909c",
        "REGIME_DETERIORATION": "#ff7043",
    }.get(close_reason, "#888")

    adx = trade.get("adx_at_entry")
    slope = trade.get("adx_slope_rising")
    staircase = trade.get("staircase_depth")
    pullback_pips = trade.get("pullback_depth_pips")

    return html.Div([
        html.Div("TRADE", style={"color": "#555", "fontSize": "10px",
                                  "marginBottom": "8px", "letterSpacing": "2px"}),
        row("Pair", trade.get("pair")),
        row("Direction", trade.get("direction")),
        row("Strategy", trade.get("strategy")),
        row("Entry", entry_time_str),
        row("Close", close_time_str),
        html.Div(style={"height": "8px"}),

        html.Div("REGIME", style={"color": "#555", "fontSize": "10px",
                                   "marginBottom": "8px", "letterSpacing": "2px"}),
        row("CS at Entry", f"{trade.get('composite_score', 0):.1f}"),
        row("Partial Exit %", f"{(trade.get('partial_exit_pct', 0) or 0)*100:.0f}%"),
        html.Div(style={"height": "8px"}),

        html.Div("RESULT", style={"color": "#555", "fontSize": "10px",
                                   "marginBottom": "8px", "letterSpacing": "2px"}),
        html.Div([
            html.Span("Close Reason: ", style={"color": "#888"}),
            html.Span(close_reason, style={"color": reason_color, "fontWeight": "bold"}),
        ], style={"marginBottom": "4px"}),
        html.Div([
            html.Span("R Total: ", style={"color": "#888"}),
            html.Span(f"{r_total:+.3f}R", style={"color": r_color, "fontWeight": "bold"}),
        ], style={"marginBottom": "4px"}),
        row("PnL", f"${trade.get('pnl_usd', 0):.2f}"),
        html.Div(style={"height": "8px"}),

        html.Div("ENTRY CONTEXT", style={"color": "#555", "fontSize": "10px",
                                          "marginBottom": "8px", "letterSpacing": "2px"}),
        row("ADX", f"{adx:.1f}" if adx is not None else "—"),
        row("ADX Slope", "Rising ↑" if slope else ("Falling ↓" if slope is False else "—")),
        row("Staircase Depth", str(staircase) if staircase is not None else "—"),
        row("Pullback Depth", f"{pullback_pips:.1f} pips" if pullback_pips is not None else "—"),
        row("Lot Size", f"{trade.get('lot_size', 0):.3f}"),
    ])
```

### Callback 11: Render DCRD panel (right) — updates per frame

```python
@callback(
    Output("insp-dcrd-panel", "children"),
    Input("insp-frame", "data"),
    State("insp-context", "data"),
    prevent_initial_call=True,
)
def render_dcrd_panel(frame: int, context_data: dict):
    if not context_data:
        return html.Div("No trade loaded.", style={"color": "#555"})

    dcrd = context_data.get("dcrd_at_entry", {})
    trade = context_data["trade"]
    entry_local = context_data["entry_bar_local_idx"]

    # Show live CS from dcrd_per_bar if available and frame < entry
    live_cs = None
    dcrd_per_bar_json = context_data.get("dcrd_per_bar", "[]")
    if dcrd_per_bar_json and frame < entry_local:
        try:
            dpb = pd.read_json(dcrd_per_bar_json, orient="records")
            if len(dpb) > frame:
                live_cs = dpb.iloc[frame].get("score")
        except Exception:
            pass

    cs_display = live_cs if live_cs is not None else dcrd.get("composite_score", 0)

    def score_row(label: str, value, max_val: int = 20) -> html.Div:
        pct = min(100, max(0, float(value or 0) / max_val * 100))
        bar_color = "#26a69a" if float(value or 0) >= 0 else "#ef5350"
        return html.Div([
            html.Div([
                html.Span(label, style={"color": "#888", "fontSize": "11px"}),
                html.Span(f"{value:+.0f}" if float(value or 0) < 0 else f"{value:.0f}",
                          style={"color": "#eee", "float": "right", "fontSize": "11px"}),
            ], style={"overflow": "hidden"}),
            html.Div(html.Div(style={
                "height": "3px", "width": f"{pct}%",
                "background": bar_color, "borderRadius": "2px",
            }), style={"background": "#1a2030", "borderRadius": "2px", "marginBottom": "6px"}),
        ])

    regime = dcrd.get("regime", "—").upper()
    regime_color = {"TRENDING": "#26a69a", "TRANSITIONAL": "#ffa726", "RANGE": "#ef5350"}.get(regime, "#888")

    return html.Div([
        html.Div(f"DCRD  {'@ Entry' if frame >= entry_local else '(live CS)'}",
                 style={"color": "#555", "fontSize": "10px", "marginBottom": "8px",
                        "letterSpacing": "2px"}),

        html.Div([
            html.Span("Structural: ", style={"color": "#888"}),
            html.Span(f"{dcrd.get('layer1_structural', 0):.0f}/100",
                      style={"color": "#eee", "fontWeight": "bold"}),
        ], style={"marginBottom": "6px"}),
        score_row("  ADX Strength", dcrd.get("l1_adx_strength", 0)),
        score_row("  Mkt Structure", dcrd.get("l1_market_structure", 0)),
        score_row("  ATR Expansion", dcrd.get("l1_atr_expansion", 0)),
        score_row("  CSM Alignment", dcrd.get("l1_csm_alignment", 0)),
        score_row("  Trend Persist.", dcrd.get("l1_trend_persistence", 0)),

        html.Div(style={"height": "8px"}),
        html.Div([
            html.Span("Modifier: ", style={"color": "#888"}),
            html.Span(f"{dcrd.get('layer2_modifier', 0):+.0f}",
                      style={"color": "#eee", "fontWeight": "bold"}),
        ], style={"marginBottom": "6px"}),
        score_row("  BB Width", dcrd.get("l2_bb_width", 0), max_val=5),
        score_row("  ADX Accel.", dcrd.get("l2_adx_acceleration", 0), max_val=5),
        score_row("  CSM Accel.", dcrd.get("l2_csm_acceleration", 0), max_val=5),

        html.Div(style={"height": "8px"}),
        html.Div([
            html.Span("RB Intelligence: ", style={"color": "#888"}),
            html.Span(f"{dcrd.get('layer3_rb_intelligence', 0):.0f}/20",
                      style={"color": "#eee", "fontWeight": "bold"}),
        ], style={"marginBottom": "6px"}),
        score_row("  RB Speed", dcrd.get("l3_rb_speed", 0), max_val=10),
        score_row("  RB Structure", dcrd.get("l3_rb_structure", 0), max_val=10),

        html.Div(style={"height": "12px"}),
        html.Div([
            html.Span("CS: ", style={"color": "#888", "fontSize": "14px"}),
            html.Span(f"{cs_display:.0f}",
                      style={"color": "#fff", "fontWeight": "bold", "fontSize": "18px"}),
        ], style={"marginBottom": "4px"}),
        html.Div([
            html.Span("Regime: ", style={"color": "#888"}),
            html.Span(regime, style={"color": regime_color, "fontWeight": "bold"}),
        ]),
    ])
```

**Step 1: Add both panel callbacks to inspector.py**

**Step 2: Test in browser**

Load a trade. Verify:
- Left panel shows trade metadata with correct values from trades.parquet
- Right panel shows DCRD breakdown with 14 scores and bar charts
- R-total is colored green (win) or red (loss)
- DCRD regime label colored correctly

**Step 3: Commit**

```bash
git -C D:/JcampFX add dashboard/pages/inspector.py
git -C D:/JcampFX commit -m "feat(inspector): add trade metadata and DCRD layer breakdown panels"
```

---

## Task 12: Wire Cinema Inspect links + end-to-end test

**Files:**
- Modify: `dashboard/app.py` (add run_id to Inspect link)
- Manual integration test

**Step 1: Find the Cinema trade log table builder in app.py**

Search for `cinema-trade-table` output in the callback:

```
grep -n "cinema-trade-table" dashboard/app.py
```

**Step 2: Extract the active run_id from cinema-results-store**

In the callback that builds the trade table, add a `State("cinema-results-store", "data")` to get the current `run_id`. The store dict should have a `run_id` key (or `run_dir` — check the serialization in `_results_to_store()`).

**Step 3: Add Inspect link column to each table row**

In the HTML table row construction, add:

```python
html.Td(
    dcc.Link("Inspect", href=f"/inspector?run={run_id}&trade={row['trade_id']}"),
    style={"padding": "2px 8px"},
)
```

Also add `"Inspect"` to the header row.

**Step 4: End-to-end test**

1. Start dashboard: `python -m dashboard.app`
2. Go to `http://localhost:8050` → Cinema tab
3. Run or load a backtest
4. Click "Inspect" on any trade row
5. Verify: navigates to `/inspector?run=...&trade=...`
6. Verify: Range Bar chart builds up bar by bar on Play
7. Verify: At entry frame — SL line, 1.5R line, blue entry marker appear
8. Filter to USDJPY + loss + Oct-24 → verify nav shows correct count
9. Click Next/Prev — verify trade changes and all panels update

**Step 5: Commit**

```bash
git -C D:/JcampFX add dashboard/app.py
git -C D:/JcampFX commit -m "feat(cinema): wire Inspect links to Trade Inspector page"
```

---

## Task 13: Run full test suite + commit final state

**Step 1: Run all tests**

```
pytest tests/ -v --tb=short
```
Expected: All tests PASS (or expected SKIPs for data-dependent tests).

**Step 2: Re-run backtest to confirm enriched trades.parquet**

```
python -m backtester.run_backtest --pairs EURUSD GBPUSD USDJPY AUDJPY USDCHF --start 2024-01-01 --end 2025-12-31
```

**Step 3: Verify in dashboard**

Load the new run. Inspect a TrendRider trade. Verify:
- `adx_at_entry`, `staircase_depth`, `pullback_depth_pips` all show real values (not `—`)
- DCRD panel shows non-zero scores (OHLC data available)

**Step 4: Final commit**

```bash
git -C D:/JcampFX add -A
git -C D:/JcampFX commit -m "feat: Phase 3.5 Trade Inspector complete — bar-by-bar playback with VCR controls"
```

---

## Summary: Files Changed

| File | Action |
|---|---|
| `backtester/trade.py` | Add 6 debug fields |
| `src/signal.py` | Add 6 debug fields |
| `src/strategies/trend_rider.py` | `_detect_3bar_staircase` returns int depth; populate 6 fields on Signal |
| `backtester/engine.py` | Copy 6 fields from Signal to BacktestTrade |
| `backtester/results.py` | Reconstruct 6 fields from Parquet |
| `backtester/playback.py` | New: trade context loader |
| `dashboard/app.py` | Enable `use_pages`, add Inspect links |
| `dashboard/pages/__init__.py` | New: empty package init |
| `dashboard/pages/inspector.py` | New: full Inspector page (layout + 11 callbacks) |
| `tests/test_trade_fields.py` | New |
| `tests/test_signal_debug_fields.py` | New |
| `tests/test_strategies.py` | Add staircase depth + debug-fields tests |
| `tests/test_engine_debug_fields.py` | New |
| `tests/test_playback.py` | New |
