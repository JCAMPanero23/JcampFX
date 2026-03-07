"""
JcampFX — Live Range Bar Engine (Phase 4)

Real-time Range Bar builder that processes incoming ticks from MT5 via ZMQ.

Architecture:
- Maintains separate RangeBarConverter state for each pair
- Processes ticks as they arrive (mid = (bid + ask) / 2)
- Emits bar close events for DCRD calculation
- Caches completed bars to Parquet (append mode)
- Detects phantom bars (weekend gaps >4 hours)

Integration:
- Called by BrainOrchestrator on each tick
- Triggers strategy analysis on bar close
- Provides rolling window of bars for DCRD
"""

import logging
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.config import (
    DATA_RANGE_BARS_DIR,
    PIP_SIZE,
    RANGE_BAR_PIPS,
)
from src.range_bar_converter import RangeBar, RangeBarConverter

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent


@dataclass
class BarCloseEvent:
    """Event emitted when a Range Bar closes."""
    pair: str
    bar: RangeBar
    bar_index: int  # Sequential bar number for this pair (0-indexed)
    bars_from_tick: int  # How many bars this single tick produced (for phantom detection)


class LiveRangeBarEngine:
    """
    Real-time Range Bar builder for live trading.

    Maintains separate state for each trading pair and processes incoming ticks
    to build Range Bars using the same logic as the backtest engine.

    Usage:
        engine = LiveRangeBarEngine(pairs=["EURUSD", "USDJPY"])
        engine.on_bar_close = my_callback  # Set callback

        # On each tick from ZMQ:
        events = engine.process_tick("EURUSD", bid=1.0850, ask=1.0852, timestamp=now)
        # events contains list of BarCloseEvent for any completed bars
    """

    def __init__(
        self,
        pairs: list[str],
        on_bar_close: Optional[Callable[[BarCloseEvent], None]] = None,
        cache_dir: Optional[Path] = None,
        lookback_bars: int = 200,  # Keep last N bars in memory for DCRD
    ):
        """
        Initialize live Range Bar engine.

        Args:
            pairs: List of trading pairs (e.g. ["EURUSD", "USDJPY"])
            on_bar_close: Callback function called on each bar close
            cache_dir: Directory for Parquet caching (default: data/range_bars)
            lookback_bars: Number of bars to keep in memory for rolling calculations
        """
        self.pairs = pairs
        self.on_bar_close = on_bar_close
        self.lookback_bars = lookback_bars

        # Cache directory for Parquet files
        self.cache_dir = cache_dir or (PROJECT_ROOT / DATA_RANGE_BARS_DIR)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Range Bar converters (one per pair)
        self.converters: dict[str, RangeBarConverter] = {}

        # Rolling bar history (deque of RangeBar objects, one per pair)
        self.bar_history: dict[str, deque[RangeBar]] = defaultdict(
            lambda: deque(maxlen=lookback_bars)
        )

        # Bar counters (sequential index per pair)
        self.bar_counts: dict[str, int] = defaultdict(int)

        # Statistics
        self.ticks_processed: dict[str, int] = defaultdict(int)
        self.bars_produced: dict[str, int] = defaultdict(int)

        # Initialize converters
        for pair in pairs:
            bar_pips = RANGE_BAR_PIPS.get(pair, 15)
            pip_size = PIP_SIZE.get(pair, 0.0001)
            self.converters[pair] = RangeBarConverter(
                bar_pips=bar_pips,
                pip_size=pip_size,
            )
            log.info(
                "LiveRangeBarEngine: %s initialized (bar_size=%d pips, pip=%.5f)",
                pair, bar_pips, pip_size
            )

        log.info(
            "LiveRangeBarEngine: %d pairs initialized, lookback=%d bars",
            len(pairs), lookback_bars
        )

    def process_tick(
        self,
        pair: str,
        bid: float,
        ask: float,
        timestamp: datetime,
    ) -> list[BarCloseEvent]:
        """
        Process a single tick and return any completed Range Bars.

        Args:
            pair: Trading pair (e.g. "EURUSD")
            bid: Bid price
            ask: Ask price
            timestamp: Tick timestamp (UTC)

        Returns:
            List of BarCloseEvent objects (usually 0-1, occasionally more on gaps)
        """
        if pair not in self.converters:
            log.warning("LiveRangeBarEngine: unknown pair %s, skipping tick", pair)
            return []

        # Calculate mid-price
        mid = (bid + ask) / 2.0

        # Convert to pandas Timestamp (required by RangeBarConverter)
        if isinstance(timestamp, pd.Timestamp):
            ts = timestamp
        else:
            ts = pd.Timestamp(timestamp)

        # Ensure UTC timezone
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")

        # Feed to converter
        completed_bars = self.converters[pair].feed(mid, ts)

        # Update statistics
        self.ticks_processed[pair] += 1
        self.bars_produced[pair] += len(completed_bars)

        # Build events and update cache
        events = []
        for i, bar in enumerate(completed_bars):
            # Add to rolling history
            self.bar_history[pair].append(bar)

            # Create event
            event = BarCloseEvent(
                pair=pair,
                bar=bar,
                bar_index=self.bar_counts[pair],
                bars_from_tick=len(completed_bars),
            )
            events.append(event)

            # Increment bar counter
            self.bar_counts[pair] += 1

            # Log bar close
            log.info(
                "Range Bar close: %s #%d | O=%.5f H=%.5f L=%.5f C=%.5f | Vol=%d | "
                "Phantom=%s GapAdj=%s | Duration=%s",
                pair, event.bar_index,
                bar.open, bar.high, bar.low, bar.close,
                bar.tick_volume,
                bar.is_phantom, bar.is_gap_adjacent,
                bar.end_time - bar.start_time,
            )

            # Cache to Parquet (append mode)
            self._cache_bar(pair, bar)

            # Trigger callback
            if self.on_bar_close:
                try:
                    self.on_bar_close(event)
                except Exception as e:
                    log.error("LiveRangeBarEngine: bar close callback error: %s", e, exc_info=True)

        return events

    def get_bar_history(
        self,
        pair: str,
        n_bars: Optional[int] = None,
        as_dataframe: bool = False,
    ) -> list[RangeBar] | pd.DataFrame:
        """
        Get recent bar history for a pair.

        Args:
            pair: Trading pair
            n_bars: Number of bars to return (default: all in memory)
            as_dataframe: Return as DataFrame instead of list

        Returns:
            List of RangeBar objects or DataFrame
        """
        if pair not in self.bar_history:
            return pd.DataFrame() if as_dataframe else []

        bars = list(self.bar_history[pair])
        if n_bars is not None:
            bars = bars[-n_bars:]

        if as_dataframe:
            if not bars:
                return pd.DataFrame()
            df = pd.DataFrame([b.to_dict() for b in bars])
            df["start_time"] = pd.to_datetime(df["start_time"], utc=True)
            df["end_time"] = pd.to_datetime(df["end_time"], utc=True)
            return df

        return bars

    def get_current_bar_state(self, pair: str) -> dict:
        """
        Get the current open (incomplete) bar state for debugging.

        Returns:
            Dictionary with current bar state (open, high, low, tick_volume, start_time)
        """
        if pair not in self.converters:
            return {}

        conv = self.converters[pair]
        return {
            "pair": pair,
            "bar_open": conv._bar_open,
            "bar_high": conv._bar_high,
            "bar_low": conv._bar_low,
            "bar_tick_vol": conv._bar_tick_vol,
            "bar_start": conv._bar_start,
            "last_tick_ts": conv._last_tick_ts,
        }

    def _cache_bar(self, pair: str, bar: RangeBar) -> None:
        """
        Append completed bar to Parquet cache.

        Uses append mode to efficiently add new bars without rewriting entire file.
        """
        bar_pips = RANGE_BAR_PIPS.get(pair, 15)
        cache_file = self.cache_dir / f"{pair}_RB{bar_pips}_live.parquet"

        # Convert to DataFrame
        df = pd.DataFrame([bar.to_dict()])
        df["start_time"] = pd.to_datetime(df["start_time"], utc=True)
        df["end_time"] = pd.to_datetime(df["end_time"], utc=True)

        # Append to Parquet
        try:
            if cache_file.exists():
                # Append mode
                existing = pq.read_table(cache_file)
                new_table = pa.Table.from_pandas(df)
                combined = pa.concat_tables([existing, new_table])
                pq.write_table(combined, cache_file, compression="snappy")
            else:
                # Create new file
                pq.write_table(pa.Table.from_pandas(df), cache_file, compression="snappy")
        except Exception as e:
            log.error("LiveRangeBarEngine: failed to cache bar to %s: %s", cache_file, e)

    def load_historical_bars(self, pair: str, lookback: Optional[int] = None) -> None:
        """
        Load historical bars from Parquet cache to initialize rolling window.

        Useful for starting the engine with existing bar history (e.g., after restart).

        Args:
            pair: Trading pair
            lookback: Number of bars to load (default: self.lookback_bars)
        """
        bar_pips = RANGE_BAR_PIPS.get(pair, 15)

        # Try live cache first
        cache_file = self.cache_dir / f"{pair}_RB{bar_pips}_live.parquet"
        if not cache_file.exists():
            # Fall back to backtest cache
            cache_file = self.cache_dir / f"{pair}_RB{bar_pips}.parquet"

        if not cache_file.exists():
            log.warning("LiveRangeBarEngine: no cached bars for %s, starting fresh", pair)
            return

        try:
            df = pd.read_parquet(cache_file)
            df["start_time"] = pd.to_datetime(df["start_time"], utc=True)
            df["end_time"] = pd.to_datetime(df["end_time"], utc=True)

            # Ensure v2.2 phantom columns exist
            if "is_phantom" not in df.columns:
                df["is_phantom"] = False
            if "is_gap_adjacent" not in df.columns:
                df["is_gap_adjacent"] = False
            if "tick_boundary_price" not in df.columns:
                df["tick_boundary_price"] = df["close"]

            # Take last N bars
            n = lookback or self.lookback_bars
            df = df.tail(n).reset_index(drop=True)

            # Convert to RangeBar objects and load into history
            for row in df.itertuples(index=False):
                bar = RangeBar(
                    open=row.open,
                    high=row.high,
                    low=row.low,
                    close=row.close,
                    tick_volume=row.tick_volume,
                    start_time=row.start_time,
                    end_time=row.end_time,
                    is_phantom=row.is_phantom,
                    is_gap_adjacent=row.is_gap_adjacent,
                    tick_boundary_price=row.tick_boundary_price,
                )
                self.bar_history[pair].append(bar)

            # Update bar counter to continue from last index
            self.bar_counts[pair] = len(df)
            self.bars_produced[pair] = len(df)  # Update bars_produced for dashboard display

            log.info(
                "LiveRangeBarEngine: loaded %d historical bars for %s from %s",
                len(df), pair, cache_file
            )
        except Exception as e:
            log.error("LiveRangeBarEngine: failed to load historical bars for %s: %s", pair, e)

    def get_stats(self) -> dict:
        """Get engine statistics."""
        return {
            "pairs": self.pairs,
            "ticks_processed": dict(self.ticks_processed),
            "bars_produced": dict(self.bars_produced),
            "bar_counts": dict(self.bar_counts),
            "bars_in_memory": {p: len(self.bar_history[p]) for p in self.pairs},
        }

    def reset(self, pair: Optional[str] = None) -> None:
        """
        Reset engine state for a pair (or all pairs).

        Clears rolling history and reinitializes converters.
        Useful for testing or recovery from errors.
        """
        if pair:
            pairs_to_reset = [pair]
        else:
            pairs_to_reset = self.pairs

        for p in pairs_to_reset:
            if p not in self.converters:
                continue

            # Reinitialize converter
            bar_pips = RANGE_BAR_PIPS.get(p, 15)
            pip_size = PIP_SIZE.get(p, 0.0001)
            self.converters[p] = RangeBarConverter(
                bar_pips=bar_pips,
                pip_size=pip_size,
            )

            # Clear history
            self.bar_history[p].clear()
            self.bar_counts[p] = 0
            self.ticks_processed[p] = 0
            self.bars_produced[p] = 0

            log.info("LiveRangeBarEngine: %s state reset", p)


# ---------------------------------------------------------------------------
# Test mode
# ---------------------------------------------------------------------------

def main():
    """Test LiveRangeBarEngine with simulated ticks."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    def on_bar_close(event: BarCloseEvent):
        print(f"\n=== BAR CLOSE EVENT ===")
        print(f"Pair: {event.pair}")
        print(f"Bar Index: {event.bar_index}")
        print(f"OHLC: {event.bar.open:.5f} / {event.bar.high:.5f} / {event.bar.low:.5f} / {event.bar.close:.5f}")
        print(f"Tick Volume: {event.bar.tick_volume}")
        print(f"Duration: {event.bar.end_time - event.bar.start_time}")
        print(f"Phantom: {event.bar.is_phantom}, Gap Adjacent: {event.bar.is_gap_adjacent}")
        print("=" * 40)

    # Initialize engine
    engine = LiveRangeBarEngine(
        pairs=["EURUSD", "USDJPY"],
        on_bar_close=on_bar_close,
        lookback_bars=50,
    )

    # Simulate ticks
    print("\nSimulating ticks for EURUSD (15-pip bars)...")
    base_time = pd.Timestamp.now(tz="UTC")
    base_price = 1.0850

    for i in range(100):
        # Simulate price movement
        price_change = (i % 20 - 10) * 0.00005  # Small random walk
        bid = base_price + price_change
        ask = bid + 0.00002  # 0.2 pip spread
        timestamp = base_time + pd.Timedelta(seconds=i)

        events = engine.process_tick("EURUSD", bid, ask, timestamp)

        if i % 10 == 0:
            print(f"Tick {i}: Bid={bid:.5f} Ask={ask:.5f} | Bars closed: {len(events)}")

    # Print stats
    print("\n=== ENGINE STATISTICS ===")
    stats = engine.get_stats()
    print(f"Ticks processed: {stats['ticks_processed']}")
    print(f"Bars produced: {stats['bars_produced']}")
    print(f"Bars in memory: {stats['bars_in_memory']}")

    # Test bar history retrieval
    print("\n=== BAR HISTORY (last 5 bars) ===")
    df = engine.get_bar_history("EURUSD", n_bars=5, as_dataframe=True)
    if not df.empty:
        print(df[["open", "high", "low", "close", "tick_volume", "is_phantom"]])


if __name__ == "__main__":
    main()
