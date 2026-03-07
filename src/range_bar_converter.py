"""
JcampFX — Range Bar Converter (Phase 1, PRD §7.2)

Converts raw tick data (bid/ask) into Range Bars.

Rules (PRD-compliant):
  - Bar size = N pips (configurable per pair)
  - New bar opens only when price moves exactly N pips from the current bar's open
  - High - Low = exactly N pips (within spread tolerance)
  - Each bar stores: open, high, low, close, tick_volume, start_time, end_time
  - Weekend gaps produce NO phantom bars — ticks within weekend gaps are skipped
  - Purely price-driven: bars span varying durations

Algorithm (standard Range Bar construction):
  1. Mid-price = (bid + ask) / 2
  2. First tick opens first bar at mid-price
  3. Track current bar's open, high, low
  4. When high - open >= bar_size → bar closes at open + bar_size (up bar),
     next bar opens at that close
  5. When open - low >= bar_size → bar closes at open - bar_size (down bar),
     next bar opens at that close
  6. Otherwise → update high/low of current bar
  7. Weekend gap detection: skip ticks where time gap to previous tick
     exceeds WEEKEND_GAP_HOURS (default 48h)

Validation targets (PRD §7.4):
  V1.3 — High - Low = exactly N pips (within spread tolerance)
  V1.4 — Bars span different durations (purely price-driven)
  V1.6 — Weekend gaps handled — no phantom bars
  V1.8 — Unit test: 100 ticks → deterministic N Range Bars
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Iterator

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.config import (
    DATA_RANGE_BARS_DIR,
    PIP_SIZE,
    RANGE_BAR_PIPS,
)

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent

# Ticks with a gap larger than this from the previous tick are considered
# weekend/holiday gaps — the current bar closes and no phantom bars are created.
WEEKEND_GAP_HOURS = 4.0   # hours (covers typical weekend 5pm Fri → 5pm Sun EST)


# ---------------------------------------------------------------------------
# Data class for a completed Range Bar
# ---------------------------------------------------------------------------

@dataclass
class RangeBar:
    open:        float
    high:        float
    low:         float
    close:       float
    tick_volume: int
    start_time:  pd.Timestamp
    end_time:    pd.Timestamp
    # v2.2 Phantom Liquidity Detection flags (PRD §8)
    is_phantom:          bool  = False  # Bar 2+ produced from the same tick (VP.1)
    is_gap_adjacent:     bool  = False  # First bar in a multi-bar tick sequence (VP.2)
    tick_boundary_price: float = 0.0    # Actual tick mid-price — used for exit fills on phantom bars (VP.6)

    def to_dict(self) -> dict:
        return {
            "open":               self.open,
            "high":               self.high,
            "low":                self.low,
            "close":              self.close,
            "tick_volume":        self.tick_volume,
            "start_time":         self.start_time,
            "end_time":           self.end_time,
            "is_phantom":         self.is_phantom,
            "is_gap_adjacent":    self.is_gap_adjacent,
            "tick_boundary_price": self.tick_boundary_price,
        }


# ---------------------------------------------------------------------------
# Core converter
# ---------------------------------------------------------------------------

class RangeBarConverter:
    """
    Stateful Range Bar builder. Feed ticks one-by-one via `feed()`
    or pass a full tick DataFrame via `convert()`.

    Parameters
    ----------
    bar_pips : int
        Number of pips per bar (e.g. 10 for EURUSD).
    pip_size : float
        Price value of 1 pip (e.g. 0.0001 for USD pairs, 0.01 for JPY pairs).
    weekend_gap_hours : float
        Minimum gap (hours) between consecutive ticks to be treated as a
        weekend/holiday break. The current open bar closes at its current
        price (not extended to full bar size) and a new bar starts fresh.
    """

    def __init__(
        self,
        bar_pips: int,
        pip_size: float,
        weekend_gap_hours: float = WEEKEND_GAP_HOURS,
    ) -> None:
        self.bar_size: float = round(bar_pips * pip_size, 10)
        self.pip_size = pip_size
        self.weekend_gap_hours = weekend_gap_hours

        # Current open bar state
        self._bar_open:      float | None = None
        self._bar_high:      float | None = None
        self._bar_low:       float | None = None
        self._bar_start:     pd.Timestamp | None = None
        self._bar_tick_vol:  int = 0
        self._last_tick_ts:  pd.Timestamp | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _open_bar(self, price: float, ts: pd.Timestamp) -> None:
        self._bar_open = price
        self._bar_high = price
        self._bar_low  = price
        self._bar_start = ts
        self._bar_tick_vol = 1

    def _close_bar_up(
        self,
        ts: pd.Timestamp,
        is_phantom: bool = False,
        is_gap_adjacent: bool = False,
        tick_boundary_price: float = 0.0,
    ) -> RangeBar:
        """Close an up bar with exact high = open + bar_size, low = open (no wicks).
        PRD V1.3: High - Low = exactly bar_size."""
        close_price = round(self._bar_open + self.bar_size, 10)  # type: ignore[operator]
        tbp = tick_boundary_price if tick_boundary_price != 0.0 else close_price
        return RangeBar(
            open=self._bar_open,      # type: ignore[arg-type]
            high=close_price,         # exact: open + bar_size
            low=self._bar_open,       # exact: open (no downward wick)
            close=close_price,
            tick_volume=self._bar_tick_vol,
            start_time=self._bar_start,  # type: ignore[arg-type]
            end_time=ts,
            is_phantom=is_phantom,
            is_gap_adjacent=is_gap_adjacent,
            tick_boundary_price=tbp,
        )

    def _close_bar_down(
        self,
        ts: pd.Timestamp,
        is_phantom: bool = False,
        is_gap_adjacent: bool = False,
        tick_boundary_price: float = 0.0,
    ) -> RangeBar:
        """Close a down bar with exact low = open - bar_size, high = open (no wicks).
        PRD V1.3: High - Low = exactly bar_size."""
        close_price = round(self._bar_open - self.bar_size, 10)  # type: ignore[operator]
        tbp = tick_boundary_price if tick_boundary_price != 0.0 else close_price
        return RangeBar(
            open=self._bar_open,      # type: ignore[arg-type]
            high=self._bar_open,      # exact: open (no upward wick)
            low=close_price,          # exact: open - bar_size
            close=close_price,
            tick_volume=self._bar_tick_vol,
            start_time=self._bar_start,  # type: ignore[arg-type]
            end_time=ts,
            is_phantom=is_phantom,
            is_gap_adjacent=is_gap_adjacent,
            tick_boundary_price=tbp,
        )

    def _close_bar_gap(self, ts: pd.Timestamp) -> RangeBar:
        """Close an incomplete bar at a weekend/holiday gap (actual H/L preserved)."""
        mid = (self._bar_high + self._bar_low) / 2  # type: ignore[operator]
        return RangeBar(
            open=self._bar_open,      # type: ignore[arg-type]
            high=self._bar_high,      # type: ignore[arg-type]
            low=self._bar_low,        # type: ignore[arg-type]
            close=mid,
            tick_volume=self._bar_tick_vol,
            start_time=self._bar_start,  # type: ignore[arg-type]
            end_time=ts,
        )

    def _is_gap(self, ts: pd.Timestamp) -> bool:
        if self._last_tick_ts is None:
            return False
        delta_hours = (ts - self._last_tick_ts).total_seconds() / 3600
        return delta_hours >= self.weekend_gap_hours

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def feed(self, price: float, ts: pd.Timestamp) -> list[RangeBar]:
        """
        Process a single tick (mid-price). Returns a list of completed
        RangeBars (usually 0 or 1, occasionally more on large gaps).
        """
        completed: list[RangeBar] = []

        # --- Weekend / holiday gap handling ---
        if self._bar_open is not None and self._is_gap(ts):
            log.debug("Gap detected at %s — closing bar at gap", ts)
            completed.append(self._close_bar_gap(self._last_tick_ts))  # type: ignore[arg-type]
            self._last_tick_ts = ts
            self._open_bar(price, ts)
            return completed

        self._last_tick_ts = ts

        # --- No open bar yet ---
        if self._bar_open is None:
            self._open_bar(price, ts)
            return completed

        # --- Update current bar extremes ---
        if price > self._bar_high:     # type: ignore[operator]
            self._bar_high = price
        if price < self._bar_low:      # type: ignore[operator]
            self._bar_low = price
        self._bar_tick_vol += 1

        # --- Check completion conditions ---
        # Track how many bars are produced by this single tick (for phantom detection).
        bars_from_this_tick = 0

        # Up bar: price reached open + bar_size (no-wick: high=open+bar_size, low=open)
        while (self._bar_high - self._bar_open) >= self.bar_size - 1e-10:  # type: ignore[operator]
            is_phantom = bars_from_this_tick > 0
            is_gap_adj = False  # will be set after loop if needed
            bar = self._close_bar_up(ts, is_phantom=is_phantom, tick_boundary_price=price)
            completed.append(bar)
            bars_from_this_tick += 1
            self._open_bar(bar.close, ts)
            # Re-evaluate current price against the new bar
            if price > self._bar_high:
                self._bar_high = price
            if price < self._bar_low:
                self._bar_low = price

        # Down bar: price reached open - bar_size (no-wick: low=open-bar_size, high=open)
        while (self._bar_open - self._bar_low) >= self.bar_size - 1e-10:   # type: ignore[operator]
            is_phantom = bars_from_this_tick > 0
            bar = self._close_bar_down(ts, is_phantom=is_phantom, tick_boundary_price=price)
            completed.append(bar)
            bars_from_this_tick += 1
            self._open_bar(bar.close, ts)
            if price > self._bar_high:
                self._bar_high = price
            if price < self._bar_low:
                self._bar_low = price

        # Post-loop: if this tick produced multiple bars, mark the FIRST as gap_adjacent (VP.2)
        if bars_from_this_tick > 1:
            first_idx = len(completed) - bars_from_this_tick
            first_bar = completed[first_idx]
            # Rebuild with is_gap_adjacent=True (dataclass is immutable-ish; replace field)
            completed[first_idx] = RangeBar(
                open=first_bar.open,
                high=first_bar.high,
                low=first_bar.low,
                close=first_bar.close,
                tick_volume=first_bar.tick_volume,
                start_time=first_bar.start_time,
                end_time=first_bar.end_time,
                is_phantom=False,           # First bar is organic in direction, not phantom
                is_gap_adjacent=True,       # But marks it as gap-adjacent (VP.2)
                tick_boundary_price=first_bar.tick_boundary_price,
            )

        return completed

    def flush(self) -> RangeBar | None:
        """
        Close and return the current open (incomplete) bar if one exists.
        Useful at end-of-data to preserve state. The incomplete bar is
        NOT included in normal conversions.
        """
        if self._bar_open is None or self._bar_start is None:
            return None
        bar = RangeBar(
            open=self._bar_open,
            high=self._bar_high,  # type: ignore[arg-type]
            low=self._bar_low,    # type: ignore[arg-type]
            close=(self._bar_high + self._bar_low) / 2,  # type: ignore[operator]
            tick_volume=self._bar_tick_vol,
            start_time=self._bar_start,
            end_time=self._last_tick_ts or self._bar_start,
        )
        self._bar_open = None
        self._bar_tick_vol = 0
        return bar

    def convert(self, ticks: pd.DataFrame, include_open_bar: bool = False) -> list[RangeBar]:
        """
        Convert a full tick DataFrame to Range Bars.

        Parameters
        ----------
        ticks : pd.DataFrame
            Must have columns: 'time' (datetime, UTC), 'bid', 'ask'.
        include_open_bar : bool
            If True, append the incomplete open bar at the end.

        Returns
        -------
        list[RangeBar]
        """
        if ticks.empty:
            return []

        # Validate required columns
        required = {"time", "bid", "ask"}
        missing = required - set(ticks.columns)
        if missing:
            raise ValueError(f"Tick DataFrame missing columns: {missing}")

        ticks = ticks.sort_values("time").reset_index(drop=True)

        bars: list[RangeBar] = []
        for row in ticks.itertuples(index=False):
            mid = (row.bid + row.ask) / 2
            ts = pd.Timestamp(row.time)
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            bars.extend(self.feed(mid, ts))

        if include_open_bar:
            partial = self.flush()
            if partial is not None:
                bars.append(partial)

        return bars


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

def ticks_to_range_bars(
    ticks: pd.DataFrame,
    pair: str,
    bar_pips: int | None = None,
    include_open_bar: bool = False,
) -> pd.DataFrame:
    """
    Convert tick DataFrame to a Range Bar DataFrame for `pair`.

    Parameters
    ----------
    ticks : pd.DataFrame
        Columns: time (UTC datetime), bid, ask.
    pair : str
        e.g. "EURUSD". Used to look up default pip_size and bar_pips.
    bar_pips : int | None
        Override the default bar size from config.
    include_open_bar : bool
        Include the current incomplete bar at the end.

    Returns
    -------
    pd.DataFrame with columns:
        open, high, low, close, tick_volume, start_time, end_time
    """
    pip = PIP_SIZE[pair]
    pips = bar_pips if bar_pips is not None else RANGE_BAR_PIPS[pair]

    conv = RangeBarConverter(bar_pips=pips, pip_size=pip)
    bars = conv.convert(ticks, include_open_bar=include_open_bar)

    if not bars:
        log.warning("%s: no Range Bars produced from %d ticks", pair, len(ticks))
        return _empty_range_bar_df()

    df = pd.DataFrame([b.to_dict() for b in bars])
    df["start_time"] = pd.to_datetime(df["start_time"], utc=True)
    df["end_time"]   = pd.to_datetime(df["end_time"], utc=True)
    log.info("%s: %d ticks → %d Range Bars (bar_size=%d pips)", pair, len(ticks), len(df), pips)
    return df


def _empty_range_bar_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "open", "high", "low", "close", "tick_volume",
        "start_time", "end_time",
        "is_phantom", "is_gap_adjacent", "tick_boundary_price",
    ])


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def save_range_bars(df: pd.DataFrame, pair: str, bar_pips: int) -> Path:
    """Save Range Bar DataFrame to Parquet."""
    out_path = PROJECT_ROOT / DATA_RANGE_BARS_DIR / f"{pair}_RB{bar_pips}.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(df), out_path, compression="snappy")
    log.info("%s: saved %d bars → %s", pair, len(df), out_path)
    return out_path


def load_range_bars(pair: str, bar_pips: int | None = None) -> pd.DataFrame:
    """Load stored Range Bar Parquet. Raises FileNotFoundError if missing."""
    pips = bar_pips if bar_pips is not None else RANGE_BAR_PIPS[pair]
    path = PROJECT_ROOT / DATA_RANGE_BARS_DIR / f"{pair}_RB{pips}.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"No Range Bar data for {pair} (RB{pips}). "
            f"Run: python -m src.range_bar_converter --pair {pair}"
        )
    df = pd.read_parquet(path)
    df["start_time"] = pd.to_datetime(df["start_time"], utc=True)
    df["end_time"]   = pd.to_datetime(df["end_time"], utc=True)
    # Ensure v2.2 phantom columns exist (backward-compat with old Parquet files)
    if "is_phantom" not in df.columns:
        df["is_phantom"] = False
    if "is_gap_adjacent" not in df.columns:
        df["is_gap_adjacent"] = False
    if "tick_boundary_price" not in df.columns:
        df["tick_boundary_price"] = df["close"]
    return df.sort_values("start_time").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Iterator for memory-efficient streaming (large datasets)
# ---------------------------------------------------------------------------

def stream_range_bars(
    ticks_path: Path,
    pair: str,
    bar_pips: int | None = None,
    chunk_size: int = 500_000,
) -> Iterator[pd.DataFrame]:
    """
    Stream-convert a large tick Parquet file in chunks.
    Yields Range Bar DataFrames chunk-by-chunk.
    The converter state is preserved between chunks so bars are correct
    across chunk boundaries.
    """
    pip = PIP_SIZE[pair]
    pips = bar_pips if bar_pips is not None else RANGE_BAR_PIPS[pair]
    conv = RangeBarConverter(bar_pips=pips, pip_size=pip)

    parquet_file = pq.ParquetFile(ticks_path)
    for batch in parquet_file.iter_batches(batch_size=chunk_size):
        chunk = batch.to_pandas()
        chunk["time"] = pd.to_datetime(chunk["time"], utc=True)
        chunk = chunk.sort_values("time")

        bars: list[RangeBar] = []
        for row in chunk.itertuples(index=False):
            mid = (row.bid + row.ask) / 2
            ts = pd.Timestamp(row.time)
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            bars.extend(conv.feed(mid, ts))

        if bars:
            df = pd.DataFrame([b.to_dict() for b in bars])
            df["start_time"] = pd.to_datetime(df["start_time"], utc=True)
            df["end_time"]   = pd.to_datetime(df["end_time"], utc=True)
            yield df


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import sys
    from src.config import PAIRS
    from src.data_fetcher import load_ticks

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="JcampFX Range Bar converter")
    parser.add_argument("--pair", nargs="+", default=list(PAIRS), help="Pairs to convert")
    parser.add_argument("--bar-pips", type=int, default=None, help="Override bar size in pips")
    parser.add_argument("--stream", action="store_true", help="Use streaming mode (large files)")
    args = parser.parse_args()

    for pair in args.pair:
        if pair not in PIP_SIZE:
            log.error("Unknown pair: %s", pair)
            continue

        pips = args.bar_pips or RANGE_BAR_PIPS.get(pair, 10)

        if args.stream:
            from src.config import DATA_TICKS_DIR
            ticks_path = PROJECT_ROOT / DATA_TICKS_DIR / f"{pair}_ticks.parquet"
            if not ticks_path.exists():
                log.error("No tick file: %s", ticks_path)
                continue
            all_bars: list[pd.DataFrame] = []
            for chunk_df in stream_range_bars(ticks_path, pair, bar_pips=pips):
                all_bars.append(chunk_df)
            if all_bars:
                combined = pd.concat(all_bars, ignore_index=True)
                save_range_bars(combined, pair, pips)
        else:
            try:
                ticks = load_ticks(pair)
            except FileNotFoundError as e:
                log.error(str(e))
                continue
            rb_df = ticks_to_range_bars(ticks, pair, bar_pips=pips)
            if not rb_df.empty:
                save_range_bars(rb_df, pair, pips)
