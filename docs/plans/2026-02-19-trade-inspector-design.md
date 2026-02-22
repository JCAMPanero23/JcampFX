# Trade Inspector / Backtest Playback — Design Document

**Date:** 2026-02-19
**Status:** Approved
**Phase:** 3.5 (between Phase 3 Backtester and Phase 4 ZMQ Bridge)

---

## Problem Statement

After Phase 3 backtesting revealed a 65.2% SL-hit rate and catastrophically bad months (Oct-24: 17% WR, Jul-25: 0% WR), we need to visually inspect what the backtest engine saw at each signal to understand WHY those losses occurred. Static aggregate stats are insufficient — we need bar-by-bar playback per trade.

**Key questions to answer:**
- Do losing trades have weaker staircase patterns than winning trades?
- Are losing trades entering near obvious S/R levels?
- Is the pullback bar unusually large (deep pullback = reversal, not continuation)?
- Are Oct-24/Jul-25 losses concentrated in a particular DCRD score range or regime?

---

## Architecture Decision

**Approach: Dash multi-page** (`use_pages=True`)

- Inspector lives at `/inspector?run=<run_id>&trade=<trade_id>&...`
- Cinema tab adds "Inspect" link buttons per trade row → navigates to Inspector URL
- Filter state persists in URL query params (bookmarkable)
- Single Dash process, no inter-process communication needed

---

## Section 1: Data Layer — BacktestTrade Extension

### New Fields in `backtester/trade.py`

Six new optional fields added to `BacktestTrade` (default `None` for non-TrendRider strategies):

| Field | Type | Description |
|---|---|---|
| `adx_at_entry` | `float \| None` | ADX(14) value on 1H OHLC at entry bar |
| `adx_slope_rising` | `bool \| None` | True if ADX was rising over last 5 1H bars at entry |
| `staircase_depth` | `int \| None` | Number of bars in confirmed staircase pattern (3–6+) |
| `pullback_bar_idx` | `int \| None` | Integer index in Range Bar cache of the pullback bar |
| `pullback_depth_pips` | `float \| None` | Pullback bar high−low range in pips |
| `entry_bar_idx` | `int \| None` | Integer index in Range Bar cache of the entry (resumption) bar |

### Signal Extension (`src/signal.py`)

Mirror the same 6 fields on the `Signal` dataclass (all `Optional`, default `None`). TrendRider populates them at signal generation time; BrainCore passes them through to BacktestAccount which copies them to BacktestTrade.

### TrendRider Changes (`src/strategies/trend_rider.py`)

At signal generation (after confirming staircase + resumption bar):
- Read ADX series → capture `adx_at_entry` and `adx_slope_rising` from existing `_adx_series()` / `_adx_is_rising()` methods
- Capture `staircase_depth` from the staircase detection loop (already computed)
- Capture `pullback_bar_idx`, `pullback_depth_pips`, `entry_bar_idx` from bar indices already tracked in the staircase logic

**No logic changes** — only surfacing values that are already computed internally.

### Re-run Required

After these changes, re-run the backtest to generate enriched `trades.parquet` with the 6 new columns.

---

## Section 2: Context Extraction Module (`backtester/playback.py`)

### Key Function

```python
def get_trade_context(
    run_dir: str,
    trade_id: str,
    context_bars: int = 20,
) -> dict:
```

**Returns:**

```python
{
    "trade": dict,                    # Full row from trades.parquet (all 26 fields)
    "range_bars": pd.DataFrame,       # context_bars before entry + all bars to close_time
    "dcrd_per_bar": pd.DataFrame,     # CS per bar from dcrd_timeline.parquet (filtered to pair + time window)
    "dcrd_at_entry": dict,            # Re-run DCRD at entry time → layer breakdown:
                                      #   structural_score (0–100), dynamic_modifier (-15 to +15),
                                      #   rbi_score (0–20), composite_score (0–100),
                                      #   adx_score, market_structure_score, atr_score,
                                      #   csm_score, trend_persistence_score,
                                      #   bb_width_score, adx_accel_score, csm_accel_score,
                                      #   rb_speed_score, rb_structure_score
    "entry_bar_local_idx": int,       # Index in range_bars DataFrame where entry occurred
    "partial_exit_bar_local_idx": int | None,
    "close_bar_local_idx": int,
}
```

**Implementation steps:**
1. Load `{run_dir}/trades.parquet` → find row by trade_id
2. Load `data/range_bars/{pair}_RB{pips}.parquet` → slice window [entry_bar_idx - context_bars : close_bar_idx + 1]
3. Load `{run_dir}/dcrd_timeline.parquet` → filter by pair + time window
4. Re-run DCRD modules at entry timestamp using stored 4H/1H OHLC + Range Bars slice

### DCRD Re-computation

Call existing DCRD layer modules directly:
- `src/dcrd/structural_score.py` → pass 4H OHLC slice up to entry time
- `src/dcrd/dynamic_modifier.py` → pass 1H OHLC slice
- `src/dcrd/range_bar_intelligence.py` → pass Range Bar window

This gives individual sub-scores (5 structural + 3 modifier + 2 RBI = 10 intermediate values) for display in the inspector's DCRD panel.

---

## Section 3: Inspector Page (`dashboard/pages/inspector.py`)

### URL Format

```
/inspector?run=run_20260219_190902&trade=a1b2c3d4&pair=USDJPY&month=2024-10&outcome=loss
```

All filter state lives in the URL — bookmarkable, shareable.

### Page Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│ FILTER BAR                                                          │
│ [Run ▼] [Pair ▼] [Month ▼] [Outcome ▼] [Strategy ▼]               │
│ [⟵ Prev]  Trade 3 of 17 (USDJPY losses, Oct-24)  [Next ⟶]         │
├────────────┬───────────────────────────────────┬────────────────────┤
│ TRADE META │ ANIMATED RANGE BAR CHART          │ DCRD BREAKDOWN     │
│            │                                   │                    │
│ entry_time │ [candlestick chart]               │ Structural: 72/100 │
│ pair       │  - SL horizontal line (red)       │  ADX:        20    │
│ direction  │  - 1.5R line (green dashed)       │  Mkt Struct: 16    │
│ strategy   │  - Entry marker (triangle-up)     │  ATR Exp:    12    │
│ CS: 78     │  - Pullback bar (orange bg)       │  CSM:        16    │
│ Partial%:75│  - Resumption bar (blue bg)       │  Trend Pers: 8     │
│ Close:CHAN │  - Partial exit (diamond)         │                    │
│ R: -0.73   │  - Close marker (X)              │ Modifier: +5       │
│ PnL: -$12  │  - Staircase bars (yellow bg)    │  BB Width:  +5     │
│            │                                   │  ADX Accel:  0     │
│ ADX: 28.4  │  Bars: [build up per frame]      │  CSM Accel:  0     │
│ Slope: ↑   │                                   │                    │
│ Staircase: │                                   │ RBI: 15/20         │
│  depth=4   │                                   │  Speed:     10     │
│  pullback: │                                   │  Structure:  5     │
│  8.2 pips  │                                   │                    │
│            │                                   │ TOTAL: 92/100      │
│            │                                   │ Regime: TRENDING   │
├────────────┴───────────────────────────────────┴────────────────────┤
│ VCR PLAYBACK CONTROLS                                               │
│ [|⟸] [◁ Step] [▶ Play / ▐▐ Pause] [Step ▷] [⟹|]   Speed: [1x ▼] │
│ [━━━━━━━━━━━━━━━━━━●━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━] bar 24/38     │
│ 2024-10-14 09:40 UTC                                                │
└─────────────────────────────────────────────────────────────────────┘
```

### Playback Frame Definition

- **Frames 0 to context_bars-1**: Pre-entry context bars (no trade yet)
- **Frame = entry_bar_local_idx**: Entry bar — price markers appear, SL + 1.5R lines draw
- **Frame = partial_exit_bar_local_idx**: Partial exit diamond appears (if trade reached 1.5R)
- **Frame = close_bar_local_idx**: Close X marker + final R/PnL annotation

The DCRD right panel uses `dcrd_per_bar` to show the live CompositeScore at each frame (layer breakdown stays fixed at entry-time values since we only re-run DCRD at entry).

### Dash Components

| Component | ID | Purpose |
|---|---|---|
| `dcc.Location` | `insp-url` | Read/write URL query params |
| `dcc.Store` | `insp-context` | Full `get_trade_context()` result (JSON) |
| `dcc.Store` | `insp-frame` | Current frame index (int) |
| `dcc.Store` | `insp-filtered-trades` | Ordered list of trade_ids matching current filters |
| `dcc.Interval` | `insp-interval` | Auto-play ticker (disabled when paused) |
| `dcc.Slider` | `insp-slider` | Manual frame step + position display |
| `dcc.Graph` | `insp-rb-chart` | Animated candlestick chart |
| `html.Div` | `insp-meta-panel` | Trade metadata left panel |
| `html.Div` | `insp-dcrd-panel` | DCRD layer breakdown right panel |

### Key Callbacks

1. **`load_context`**: URL change → load `get_trade_context()` → populate `insp-context` store
2. **`filter_trades`**: Filter dropdowns change → compute filtered trade list → update `insp-filtered-trades` + nav counter
3. **`interval_tick`**: `insp-interval` fires → increment `insp-frame` by 1 (or wrap to 0)
4. **`step_buttons`**: Step/Start/End buttons → set `insp-frame` directly
5. **`play_pause`**: Toggle `insp-interval.disabled`; update button label
6. **`render_frame`**: `insp-frame` changes → rebuild candlestick figure showing bars[0:frame+1] + markers
7. **`sync_slider`**: `insp-frame` → update `insp-slider.value`
8. **`slider_to_frame`**: `insp-slider.value` → update `insp-frame` (mutual exclusion with sync_slider via `prevent_initial_call`)
9. **`navigate_trade`**: Prev/Next buttons → find adjacent trade_id in filtered list → update URL

---

## Section 4: Cinema Tab Update (`dashboard/app.py`)

### Enable Multi-Page

```python
app = Dash(__name__, use_pages=True, pages_folder="pages")
```

Existing Cinema tab content moves to `dashboard/pages/home.py` or stays inline as the default page.

### Add Inspect Column to Trade Table

Each row in the Cinema trade log table gets a new column:
```python
html.A("Inspect", href=f"/inspector?run={run_id}&trade={trade_id}")
```

---

## Files Changed / Created

| File | Action | Description |
|---|---|---|
| `backtester/trade.py` | Modify | Add 6 new fields to BacktestTrade + to_dict() |
| `src/signal.py` | Modify | Mirror 6 new fields (Optional, default None) |
| `src/strategies/trend_rider.py` | Modify | Populate 6 fields at signal generation |
| `backtester/playback.py` | Create | get_trade_context() context extraction |
| `dashboard/app.py` | Modify | Enable use_pages, add Inspect links to Cinema table |
| `dashboard/pages/__init__.py` | Create | Empty (package init) |
| `dashboard/pages/inspector.py` | Create | Full Inspector page with VCR playback |

---

## Testing

- Run backtest after BacktestTrade extension → verify 6 new columns in trades.parquet
- Load Inspector page → verify trade context loads without error
- Step through a known winning trade → verify all markers appear at correct frames
- Step through a known losing trade → verify SL hit frame, no partial exit marker
- Filter to USDJPY / Oct-24 / loss → verify only matching trades shown in nav
- Auto-play at 5x speed → verify interval syncs with slider

---

## Out of Scope

- Sound effects / visual effects on trade events (post-Phase 4)
- Exporting Inspector frames to video/GIF
- Showing rejected/blocked signals (PHANTOM_BLOCKED, NEWS_BLOCKED) — add in future
- RangeRider / BreakoutRider staircase visualization (only TrendRider has staircase data)
