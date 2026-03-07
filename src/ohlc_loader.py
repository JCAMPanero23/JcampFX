"""
JcampFX — OHLC Data Loader (Phase 4)

Loads and manages OHLC data for live trading:
- 4H OHLC (for DCRD structural score)
- 1H OHLC (for DCRD dynamic modifier)
- CSM pairs 4H OHLC (for currency strength meter)

Data sources:
1. Historical cache (Parquet files from backtest)
2. Incremental updates from MT5 (optional)
3. Resampled from Range Bars (fallback)

Usage:
    loader = OHLCLoader(pairs=["EURUSD", "USDJPY"])
    loader.load_historical_data()

    # Get OHLC data
    ohlc_4h = loader.get_ohlc_4h("EURUSD")
    ohlc_1h = loader.get_ohlc_1h("EURUSD")
    csm_data = loader.get_csm_data()
"""

import logging
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from src.config import (
    CSM_PAIRS,
    DATA_OHLC_1H_DIR,
    DATA_OHLC_4H_DIR,
)

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent


class OHLCLoader:
    """
    Manages OHLC data for live trading.

    Loads historical data from Parquet cache and maintains rolling windows
    for DCRD calculation.
    """

    def __init__(
        self,
        pairs: list[str],
        lookback_4h: int = 200,  # Number of 4H bars to keep in memory
        lookback_1h: int = 500,  # Number of 1H bars to keep in memory
    ):
        """
        Initialize OHLC loader.

        Args:
            pairs: List of trading pairs (e.g. ["EURUSD", "USDJPY"])
            lookback_4h: Number of 4H bars to keep in memory
            lookback_1h: Number of 1H bars to keep in memory
        """
        self.pairs = pairs
        self.lookback_4h = lookback_4h
        self.lookback_1h = lookback_1h

        # OHLC data storage
        self.ohlc_4h: Dict[str, pd.DataFrame] = {}
        self.ohlc_1h: Dict[str, pd.DataFrame] = {}
        self.csm_data: Dict[str, pd.DataFrame] = {}  # CSM pairs 4H OHLC

        # Paths
        self.ohlc_4h_dir = PROJECT_ROOT / DATA_OHLC_4H_DIR
        self.ohlc_1h_dir = PROJECT_ROOT / DATA_OHLC_1H_DIR

    def load_historical_data(self) -> None:
        """
        Load historical OHLC data from Parquet cache.

        Loads:
        - 4H OHLC for each trading pair
        - 1H OHLC for each trading pair
        - 4H OHLC for all CSM pairs (for currency strength meter)
        """
        log.info("Loading historical OHLC data...")

        # Load 4H data for trading pairs
        for pair in self.pairs:
            try:
                df = self._load_ohlc_file(pair, "4H")
                if df is not None and not df.empty:
                    # Keep last N bars
                    self.ohlc_4h[pair] = df.tail(self.lookback_4h).copy()
                    log.info("Loaded 4H OHLC for %s: %d bars (last: %s)",
                             pair, len(self.ohlc_4h[pair]),
                             self.ohlc_4h[pair].index[-1] if len(self.ohlc_4h[pair]) > 0 else "N/A")
                else:
                    log.warning("No 4H data for %s", pair)
                    self.ohlc_4h[pair] = self._empty_ohlc_df()
            except Exception as e:
                log.error("Failed to load 4H data for %s: %s", pair, e)
                self.ohlc_4h[pair] = self._empty_ohlc_df()

        # Load 1H data for trading pairs
        for pair in self.pairs:
            try:
                df = self._load_ohlc_file(pair, "1H")
                if df is not None and not df.empty:
                    # Keep last N bars
                    self.ohlc_1h[pair] = df.tail(self.lookback_1h).copy()
                    log.info("Loaded 1H OHLC for %s: %d bars (last: %s)",
                             pair, len(self.ohlc_1h[pair]),
                             self.ohlc_1h[pair].index[-1] if len(self.ohlc_1h[pair]) > 0 else "N/A")
                else:
                    log.warning("No 1H data for %s", pair)
                    self.ohlc_1h[pair] = self._empty_ohlc_df()
            except Exception as e:
                log.error("Failed to load 1H data for %s: %s", pair, e)
                self.ohlc_1h[pair] = self._empty_ohlc_df()

        # Load CSM data (4H OHLC for all CSM pairs)
        for pair in CSM_PAIRS:
            try:
                df = self._load_ohlc_file(pair, "4H")
                if df is not None and not df.empty:
                    # Keep last N bars
                    self.csm_data[pair] = df.tail(self.lookback_4h).copy()
                    log.info("Loaded CSM 4H OHLC for %s: %d bars",
                             pair, len(self.csm_data[pair]))
                else:
                    log.warning("No CSM data for %s", pair)
                    self.csm_data[pair] = self._empty_ohlc_df()
            except Exception as e:
                log.error("Failed to load CSM data for %s: %s", pair, e)
                self.csm_data[pair] = self._empty_ohlc_df()

        log.info("Historical OHLC data loaded: %d pairs (4H), %d pairs (1H), %d CSM pairs",
                 len(self.ohlc_4h), len(self.ohlc_1h), len(self.csm_data))

    def _load_ohlc_file(self, pair: str, timeframe: str) -> Optional[pd.DataFrame]:
        """
        Load OHLC data from Parquet file.

        Args:
            pair: Trading pair (e.g. "EURUSD")
            timeframe: "4H" or "1H"

        Returns:
            DataFrame with OHLC data or None if file doesn't exist
        """
        if timeframe == "4H":
            file_path = self.ohlc_4h_dir / f"{pair}_H4.parquet"
        elif timeframe == "1H":
            file_path = self.ohlc_1h_dir / f"{pair}_H1.parquet"
        else:
            raise ValueError(f"Invalid timeframe: {timeframe}")

        if not file_path.exists():
            log.warning("OHLC file not found: %s", file_path)
            return None

        try:
            df = pd.read_parquet(file_path)

            # Ensure time column is datetime with UTC timezone
            if "time" in df.columns:
                df["time"] = pd.to_datetime(df["time"], utc=True)
                df = df.set_index("time", drop=False)
            else:
                log.warning("No 'time' column in %s", file_path)
                return None

            # Sort by time
            df = df.sort_index()

            return df

        except Exception as e:
            log.error("Error loading %s: %s", file_path, e)
            return None

    def get_ohlc_4h(self, pair: str) -> pd.DataFrame:
        """
        Get 4H OHLC data for a pair.

        Args:
            pair: Trading pair

        Returns:
            DataFrame with 4H OHLC data (may be empty if not loaded)
        """
        return self.ohlc_4h.get(pair, self._empty_ohlc_df())

    def get_ohlc_1h(self, pair: str) -> pd.DataFrame:
        """
        Get 1H OHLC data for a pair.

        Args:
            pair: Trading pair

        Returns:
            DataFrame with 1H OHLC data (may be empty if not loaded)
        """
        return self.ohlc_1h.get(pair, self._empty_ohlc_df())

    def get_csm_data(self) -> Dict[str, pd.DataFrame]:
        """
        Get CSM data (4H OHLC for all CSM pairs).

        Returns:
            Dictionary of pair → 4H OHLC DataFrame
        """
        return self.csm_data

    def update_ohlc_4h(self, pair: str, new_bar: pd.Series) -> None:
        """
        Append a new 4H bar to the OHLC data.

        Used for incremental updates as new 4H bars form.

        Args:
            pair: Trading pair
            new_bar: Series with OHLC data (must have 'time' index)
        """
        if pair not in self.ohlc_4h:
            self.ohlc_4h[pair] = self._empty_ohlc_df()

        # Convert to DataFrame if Series
        if isinstance(new_bar, pd.Series):
            new_df = pd.DataFrame([new_bar])
        else:
            new_df = new_bar

        # Append new bar
        self.ohlc_4h[pair] = pd.concat([self.ohlc_4h[pair], new_df], ignore_index=False)

        # Keep only last N bars
        self.ohlc_4h[pair] = self.ohlc_4h[pair].tail(self.lookback_4h)

        log.debug("Updated 4H OHLC for %s: %d bars", pair, len(self.ohlc_4h[pair]))

    def update_ohlc_1h(self, pair: str, new_bar: pd.Series) -> None:
        """
        Append a new 1H bar to the OHLC data.

        Used for incremental updates as new 1H bars form.

        Args:
            pair: Trading pair
            new_bar: Series with OHLC data (must have 'time' index)
        """
        if pair not in self.ohlc_1h:
            self.ohlc_1h[pair] = self._empty_ohlc_df()

        # Convert to DataFrame if Series
        if isinstance(new_bar, pd.Series):
            new_df = pd.DataFrame([new_bar])
        else:
            new_df = new_bar

        # Append new bar
        self.ohlc_1h[pair] = pd.concat([self.ohlc_1h[pair], new_df], ignore_index=False)

        # Keep only last N bars
        self.ohlc_1h[pair] = self.ohlc_1h[pair].tail(self.lookback_1h)

        log.debug("Updated 1H OHLC for %s: %d bars", pair, len(self.ohlc_1h[pair]))

    def resample_range_bars_to_4h(self, range_bars: pd.DataFrame) -> pd.DataFrame:
        """
        Resample Range Bars to 4H OHLC.

        Useful for generating synthetic 4H bars from Range Bars when
        historical data is not available or for validation.

        Args:
            range_bars: DataFrame with Range Bar data (columns: open, high, low, close, end_time)

        Returns:
            DataFrame with 4H OHLC data
        """
        if range_bars.empty:
            return self._empty_ohlc_df()

        try:
            # Use end_time as the timestamp
            df = range_bars.copy()
            if "end_time" in df.columns:
                df = df.set_index("end_time")
            elif "time" in df.columns:
                df = df.set_index("time")

            # Resample to 4H
            ohlc_4h = df.resample("4H").agg({
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "tick_volume": "sum",
            }).dropna()

            # Reset index to have 'time' column
            ohlc_4h = ohlc_4h.reset_index()
            ohlc_4h = ohlc_4h.rename(columns={"end_time": "time"})

            return ohlc_4h

        except Exception as e:
            log.error("Error resampling Range Bars to 4H: %s", e)
            return self._empty_ohlc_df()

    def resample_range_bars_to_1h(self, range_bars: pd.DataFrame) -> pd.DataFrame:
        """
        Resample Range Bars to 1H OHLC.

        Args:
            range_bars: DataFrame with Range Bar data

        Returns:
            DataFrame with 1H OHLC data
        """
        if range_bars.empty:
            return self._empty_ohlc_df()

        try:
            # Use end_time as the timestamp
            df = range_bars.copy()
            if "end_time" in df.columns:
                df = df.set_index("end_time")
            elif "time" in df.columns:
                df = df.set_index("time")

            # Resample to 1H
            ohlc_1h = df.resample("1H").agg({
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "tick_volume": "sum",
            }).dropna()

            # Reset index to have 'time' column
            ohlc_1h = ohlc_1h.reset_index()
            ohlc_1h = ohlc_1h.rename(columns={"end_time": "time"})

            return ohlc_1h

        except Exception as e:
            log.error("Error resampling Range Bars to 1H: %s", e)
            return self._empty_ohlc_df()

    def _empty_ohlc_df(self) -> pd.DataFrame:
        """Return empty OHLC DataFrame with correct schema."""
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "tick_volume"])

    def get_stats(self) -> dict:
        """Get loader statistics."""
        return {
            "pairs": self.pairs,
            "ohlc_4h_loaded": {p: len(df) for p, df in self.ohlc_4h.items()},
            "ohlc_1h_loaded": {p: len(df) for p, df in self.ohlc_1h.items()},
            "csm_pairs_loaded": {p: len(df) for p, df in self.csm_data.items()},
        }


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

def load_ohlc_4h(pair: str, lookback: int = 200) -> pd.DataFrame:
    """
    Load 4H OHLC data for a single pair.

    Args:
        pair: Trading pair
        lookback: Number of bars to load

    Returns:
        DataFrame with 4H OHLC data
    """
    loader = OHLCLoader(pairs=[pair], lookback_4h=lookback)
    file_path = loader.ohlc_4h_dir / f"{pair}_H4.parquet"

    if not file_path.exists():
        raise FileNotFoundError(f"4H OHLC file not found: {file_path}")

    df = pd.read_parquet(file_path)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.set_index("time", drop=False).sort_index()

    return df.tail(lookback)


def load_ohlc_1h(pair: str, lookback: int = 500) -> pd.DataFrame:
    """
    Load 1H OHLC data for a single pair.

    Args:
        pair: Trading pair
        lookback: Number of bars to load

    Returns:
        DataFrame with 1H OHLC data
    """
    loader = OHLCLoader(pairs=[pair], lookback_1h=lookback)
    file_path = loader.ohlc_1h_dir / f"{pair}_H1.parquet"

    if not file_path.exists():
        raise FileNotFoundError(f"1H OHLC file not found: {file_path}")

    df = pd.read_parquet(file_path)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.set_index("time", drop=False).sort_index()

    return df.tail(lookback)


# ---------------------------------------------------------------------------
# Test mode
# ---------------------------------------------------------------------------

def main():
    """Test OHLC loader."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    from src.config import PAIRS

    # Initialize loader
    loader = OHLCLoader(pairs=PAIRS, lookback_4h=200, lookback_1h=500)

    # Load historical data
    loader.load_historical_data()

    # Print stats
    stats = loader.get_stats()
    print("\n=== OHLC Loader Statistics ===")
    print(f"Trading pairs: {stats['pairs']}")
    print(f"\n4H OHLC loaded:")
    for pair, count in stats['ohlc_4h_loaded'].items():
        print(f"  {pair}: {count} bars")

    print(f"\n1H OHLC loaded:")
    for pair, count in stats['ohlc_1h_loaded'].items():
        print(f"  {pair}: {count} bars")

    print(f"\nCSM pairs loaded:")
    for pair, count in stats['csm_pairs_loaded'].items():
        print(f"  {pair}: {count} bars")

    # Test retrieval
    print("\n=== Sample 4H Data (EURUSD, last 5 bars) ===")
    ohlc_4h = loader.get_ohlc_4h("EURUSD")
    if not ohlc_4h.empty:
        print(ohlc_4h[["time", "open", "high", "low", "close"]].tail(5))

    print("\n=== Sample 1H Data (EURUSD, last 5 bars) ===")
    ohlc_1h = loader.get_ohlc_1h("EURUSD")
    if not ohlc_1h.empty:
        print(ohlc_1h[["time", "open", "high", "low", "close"]].tail(5))


if __name__ == "__main__":
    main()
