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
    bars_after_close: int = 5,
) -> dict:
    """
    Load complete per-trade context for the Trade Inspector.

    Parameters
    ----------
    run_dir          : Path to backtest run directory (contains trades.parquet, dcrd_timeline.parquet)
    trade_id         : 8-char trade ID from trades.parquet
    context_bars     : Number of Range Bars to include BEFORE the entry bar
    bars_after_close : Number of Range Bars to include AFTER the close bar

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

    # Slice window: context_bars before entry → close bar + bars_after_close (inclusive)
    start_abs = max(0, entry_abs_idx - context_bars)
    end_abs = min(len(all_rb), close_abs_idx + 1 + bars_after_close)  # inclusive, capped at end
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
