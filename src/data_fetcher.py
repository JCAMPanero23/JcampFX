"""
JcampFX — MT5 Data Fetcher (Phase 1, PRD §7.1)

Downloads tick data and M15 OHLC candles from MetaTrader 5 for all pairs
in the pair universe, stores as Parquet files for Range Bar conversion.

Supports incremental downloads: only fetches missing date ranges.

Usage:
    python -m src.data_fetcher              # Fetch all pairs
    python -m src.data_fetcher --pair EURUSD --years 2
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# MT5 import is optional at module level to allow offline unit testing
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

from src.config import (
    DATA_OHLC_DIR,
    DATA_TICKS_DIR,
    M15_TIMEFRAME,
    PAIRS,
    TICK_DATA_YEARS,
    mt5_symbol,
)

log = logging.getLogger(__name__)

# Project root = parent of src/
PROJECT_ROOT = Path(__file__).parent.parent


def _ticks_path(pair: str) -> Path:
    return PROJECT_ROOT / DATA_TICKS_DIR / f"{pair}_ticks.parquet"


def _ohlc_path(pair: str) -> Path:
    return PROJECT_ROOT / DATA_OHLC_DIR / f"{pair}_M15.parquet"


# ---------------------------------------------------------------------------
# MT5 connection helpers
# ---------------------------------------------------------------------------

def connect_mt5() -> bool:
    """Initialise MT5 terminal connection. Returns True on success."""
    if not MT5_AVAILABLE:
        log.error("MetaTrader5 package not installed. Run: pip install MetaTrader5")
        return False
    if not mt5.initialize():
        log.error("MT5 initialize() failed: %s", mt5.last_error())
        return False
    info = mt5.terminal_info()
    log.info("MT5 connected — build %s, broker: %s", info.build, info.company)
    return True


def disconnect_mt5() -> None:
    if MT5_AVAILABLE:
        mt5.shutdown()


# ---------------------------------------------------------------------------
# Tick data
# ---------------------------------------------------------------------------

_MT5_COPY_TICKS_ALL = 1  # COPY_TICKS_ALL flag value


def _fetch_ticks_mt5(pair: str, date_from: datetime, date_to: datetime) -> pd.DataFrame:
    """
    Fetch raw ticks from MT5 for a date range.
    Returns DataFrame with columns: time, bid, ask, last, volume, flags.
    """
    ticks = mt5.copy_ticks_range(mt5_symbol(pair), date_from, date_to, _MT5_COPY_TICKS_ALL)
    if ticks is None or len(ticks) == 0:
        log.warning(
            "%s (%s): no ticks returned for %s → %s",
            pair, mt5_symbol(pair), date_from.date(), date_to.date(),
        )
        return pd.DataFrame()

    df = pd.DataFrame(ticks)
    # MT5 returns 'time' as Unix seconds — convert to UTC datetime
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df[["time", "bid", "ask", "last", "volume", "flags"]].copy()
    log.info("%s: fetched %d ticks (%s → %s)", pair, len(df), date_from.date(), date_to.date())
    return df


def fetch_ticks(
    pair: str,
    years: int = TICK_DATA_YEARS,
    force: bool = False,
) -> Path:
    """
    Download tick data for `pair` covering the last `years` years.

    Implements incremental download: if a Parquet file already exists,
    only fetches ticks after the last stored timestamp.

    Returns the path to the Parquet file.
    """
    out_path = _ticks_path(pair)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    now_utc = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    date_from = now_utc - timedelta(days=years * 365)

    # Incremental: find existing max timestamp
    existing_df: pd.DataFrame | None = None
    if out_path.exists() and not force:
        try:
            existing_df = pd.read_parquet(out_path)
            last_ts = existing_df["time"].max()
            # Start 1 minute after last tick to avoid duplicates
            date_from = last_ts + timedelta(minutes=1)
            log.info("%s: incremental fetch from %s", pair, date_from)
        except Exception as exc:
            log.warning("%s: could not read existing file (%s) — full fetch", pair, exc)
            existing_df = None

    if date_from >= now_utc:
        log.info("%s: tick data is up-to-date, nothing to fetch", pair)
        return out_path

    # Fetch in monthly chunks to avoid MT5 buffer limits
    chunks: list[pd.DataFrame] = []
    cursor = date_from
    while cursor < now_utc:
        chunk_end = min(cursor + timedelta(days=30), now_utc)
        chunk = _fetch_ticks_mt5(pair, cursor, chunk_end)
        if not chunk.empty:
            chunks.append(chunk)
        cursor = chunk_end

    if not chunks:
        log.warning("%s: no new tick data fetched", pair)
        return out_path

    new_df = pd.concat(chunks, ignore_index=True)
    new_df.drop_duplicates(subset=["time"], inplace=True)
    new_df.sort_values("time", inplace=True)

    if existing_df is not None and not existing_df.empty:
        combined = pd.concat([existing_df, new_df], ignore_index=True)
        combined.drop_duplicates(subset=["time"], inplace=True)
        combined.sort_values("time", inplace=True)
    else:
        combined = new_df

    pq.write_table(pa.Table.from_pandas(combined), out_path, compression="snappy")
    log.info("%s: saved %d total ticks → %s", pair, len(combined), out_path)
    return out_path


# ---------------------------------------------------------------------------
# M15 OHLC candles
# ---------------------------------------------------------------------------

_MT5_TIMEFRAME_MAP = {
    "M1":  mt5.TIMEFRAME_M1  if MT5_AVAILABLE else 1,
    "M5":  mt5.TIMEFRAME_M5  if MT5_AVAILABLE else 5,
    "M15": mt5.TIMEFRAME_M15 if MT5_AVAILABLE else 15,
    "H1":  mt5.TIMEFRAME_H1  if MT5_AVAILABLE else 60,
    "H4":  mt5.TIMEFRAME_H4  if MT5_AVAILABLE else 240,
    "D1":  mt5.TIMEFRAME_D1  if MT5_AVAILABLE else 1440,
}


def fetch_ohlc(
    pair: str,
    timeframe: str = M15_TIMEFRAME,
    years: int = TICK_DATA_YEARS,
    force: bool = False,
) -> Path:
    """
    Download OHLC candles from MT5 for `pair` on `timeframe`.
    Stores as Parquet with columns: time, open, high, low, close, tick_volume, spread, real_volume.
    """
    out_path = _ohlc_path(pair)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    now_utc = datetime.now(timezone.utc)
    date_from = now_utc - timedelta(days=years * 365)

    # Incremental
    existing_df: pd.DataFrame | None = None
    if out_path.exists() and not force:
        try:
            existing_df = pd.read_parquet(out_path)
            last_ts = existing_df["time"].max()
            date_from = last_ts + timedelta(minutes=1)
            log.info("%s %s: incremental OHLC fetch from %s", pair, timeframe, date_from)
        except Exception as exc:
            log.warning("%s: could not read existing OHLC (%s) — full fetch", pair, exc)
            existing_df = None

    if date_from >= now_utc:
        log.info("%s: OHLC data up-to-date", pair)
        return out_path

    tf_mt5 = _MT5_TIMEFRAME_MAP.get(timeframe)
    if tf_mt5 is None:
        raise ValueError(f"Unknown timeframe: {timeframe}")

    rates = mt5.copy_rates_range(mt5_symbol(pair), tf_mt5, date_from, now_utc)
    if rates is None or len(rates) == 0:
        log.warning("%s %s: no OHLC data returned", pair, timeframe)
        return out_path

    new_df = pd.DataFrame(rates)
    new_df["time"] = pd.to_datetime(new_df["time"], unit="s", utc=True)

    if existing_df is not None and not existing_df.empty:
        combined = pd.concat([existing_df, new_df], ignore_index=True)
        combined.drop_duplicates(subset=["time"], inplace=True)
        combined.sort_values("time", inplace=True)
    else:
        combined = new_df

    pq.write_table(pa.Table.from_pandas(combined), out_path, compression="snappy")
    log.info("%s %s: saved %d bars → %s", pair, timeframe, len(combined), out_path)
    return out_path


# ---------------------------------------------------------------------------
# Bulk fetch (all pairs)
# ---------------------------------------------------------------------------

def fetch_all(years: int = TICK_DATA_YEARS, force: bool = False) -> None:
    """Fetch tick data and M15 OHLC for every pair in the universe."""
    if not connect_mt5():
        sys.exit(1)

    try:
        for pair in PAIRS:
            log.info("=== %s ===", pair)
            fetch_ticks(pair, years=years, force=force)
            fetch_ohlc(pair, years=years, force=force)
    finally:
        disconnect_mt5()


# ---------------------------------------------------------------------------
# Convenience loaders (read-only, no MT5 required)
# ---------------------------------------------------------------------------

def load_ticks(pair: str) -> pd.DataFrame:
    """Load stored tick Parquet for `pair`. Raises FileNotFoundError if missing."""
    path = _ticks_path(pair)
    if not path.exists():
        raise FileNotFoundError(
            f"No tick data for {pair}. Run: python -m src.data_fetcher --pair {pair}"
        )
    df = pd.read_parquet(path)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df.sort_values("time").reset_index(drop=True)


def load_ohlc(pair: str, timeframe: str = M15_TIMEFRAME) -> pd.DataFrame:
    """Load stored M15 OHLC Parquet for `pair`. Raises FileNotFoundError if missing."""
    path = _ohlc_path(pair)
    if not path.exists():
        raise FileNotFoundError(
            f"No OHLC data for {pair}. Run: python -m src.data_fetcher --pair {pair}"
        )
    df = pd.read_parquet(path)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df.sort_values("time").reset_index(drop=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="JcampFX MT5 data fetcher")
    p.add_argument("--pair", nargs="+", default=PAIRS, help="Pair(s) to fetch (default: all)")
    p.add_argument("--years", type=int, default=TICK_DATA_YEARS, help="Years of history")
    p.add_argument("--force", action="store_true", help="Force full re-download")
    p.add_argument("--ticks-only", action="store_true", help="Skip OHLC download")
    p.add_argument("--ohlc-only", action="store_true", help="Skip tick download")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


if __name__ == "__main__":
    args = _build_parser().parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if not connect_mt5():
        sys.exit(1)

    try:
        for pair in args.pair:
            log.info("=== %s ===", pair)
            if not args.ohlc_only:
                fetch_ticks(pair, years=args.years, force=args.force)
            if not args.ticks_only:
                fetch_ohlc(pair, years=args.years, force=args.force)
    finally:
        disconnect_mt5()
