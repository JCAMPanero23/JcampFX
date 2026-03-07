"""
JcampFX — Update OHLC Data from MT5

Fetches recent H1 and H4 OHLC data from MT5 and updates Parquet cache files.
Run this before starting live trading to ensure DCRD has current data.

Usage:
    python update_ohlc_data.py
"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import MetaTrader5 as mt5
import pandas as pd

from src.config import PAIRS, CSM_PAIRS, mt5_symbol

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent
OHLC_1H_DIR = PROJECT_ROOT / "data" / "ohlc_1h"
OHLC_4H_DIR = PROJECT_ROOT / "data" / "ohlc_4h"


def fetch_and_update_ohlc(pair: str, timeframe_str: str, bars: int = 1000) -> bool:
    """
    Fetch OHLC data from MT5 and update Parquet cache.

    Args:
        pair: Trading pair (e.g. "EURUSD")
        timeframe_str: "H1" or "H4"
        bars: Number of bars to fetch

    Returns:
        True if successful, False otherwise
    """
    try:
        # Map timeframe string to MT5 constant
        if timeframe_str == "H1":
            timeframe = mt5.TIMEFRAME_H1
            output_dir = OHLC_1H_DIR
        elif timeframe_str == "H4":
            timeframe = mt5.TIMEFRAME_H4
            output_dir = OHLC_4H_DIR
        else:
            log.error("Invalid timeframe: %s", timeframe_str)
            return False

        # Get broker symbol
        symbol = mt5_symbol(pair)

        # Fetch OHLC data from MT5
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)

        if rates is None or len(rates) == 0:
            log.warning("No data received for %s %s", pair, timeframe_str)
            return False

        # Convert to DataFrame
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
        df = df.set_index('time', drop=False)

        # Save to Parquet
        output_file = output_dir / f"{pair}_{timeframe_str}.parquet"
        df.to_parquet(output_file, index=False)

        log.info("Updated %s: %d bars (latest: %s)",
                 output_file.name, len(df), df['time'].iloc[-1])

        return True

    except Exception as e:
        log.error("Failed to update %s %s: %s", pair, timeframe_str, e)
        return False


def main():
    """Update OHLC data for all trading pairs and CSM pairs."""
    log.info("=" * 70)
    log.info("JcampFX — Update OHLC Data from MT5")
    log.info("=" * 70)

    # Initialize MT5
    if not mt5.initialize():
        log.error("MT5 initialization failed")
        return 1

    log.info("MT5 initialized successfully")

    # Ensure output directories exist
    OHLC_1H_DIR.mkdir(parents=True, exist_ok=True)
    OHLC_4H_DIR.mkdir(parents=True, exist_ok=True)

    # Update trading pairs
    all_pairs = list(set(PAIRS + CSM_PAIRS))  # Unique pairs
    log.info("Updating %d pairs (trading + CSM)...", len(all_pairs))

    success_count = 0
    fail_count = 0

    for pair in all_pairs:
        log.info("Processing %s...", pair)

        # Update H4 data
        if fetch_and_update_ohlc(pair, "H4", bars=500):
            success_count += 1
        else:
            fail_count += 1

        # Update H1 data
        if fetch_and_update_ohlc(pair, "H1", bars=1000):
            success_count += 1
        else:
            fail_count += 1

    # Shutdown MT5
    mt5.shutdown()

    log.info("=" * 70)
    log.info("Update complete: %d successful, %d failed", success_count, fail_count)
    log.info("=" * 70)

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    exit(main())
