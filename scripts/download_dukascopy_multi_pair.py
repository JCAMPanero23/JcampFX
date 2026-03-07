"""
Download historical tick data from Dukascopy for multiple pairs (2018-2024).

Dukascopy provides free historical tick data for forex pairs.
Downloads and converts to JcampFX tick format (Parquet).

Usage:
    python download_dukascopy_multi_pair.py              # All 9 pairs
    python download_dukascopy_multi_pair.py EURUSD       # Single pair
    python download_dukascopy_multi_pair.py EURUSD USDJPY  # Multiple pairs
"""

import logging
import lzma
import struct
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import urlopen

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger(__name__)

# Dukascopy URL format
# https://datafeed.dukascopy.com/datafeed/{PAIR}/{YEAR}/{MONTH}/{DAY}/{HOUR}h_ticks.bi5
DUKASCOPY_URL = "https://datafeed.dukascopy.com/datafeed/{pair}/{year:04d}/{month:02d}/{day:02d}/{hour:02d}h_ticks.bi5"

# All pairs we need (core trading + CSM coverage)
ALL_PAIRS = [
    "EURUSD",   # Core trading pair
    "USDJPY",   # Core trading pair
    "AUDJPY",   # Core trading pair
    "USDCHF",   # Core trading pair
    "GBPJPY",   # SwingRider convexity amplifier
    "EURJPY",   # CSM cross pair
    "GBPUSD",   # CSM pair (removed from trading but needed for CSM)
    "EURGBP",   # CSM cross pair
    "AUDUSD",   # CSM pair
]


def download_hour_ticks(pair: str, year: int, month: int, day: int, hour: int) -> list[dict]:
    """
    Download one hour of tick data from Dukascopy.

    Returns list of tick dicts: [{"time": datetime, "bid": float, "ask": float, "bid_vol": float, "ask_vol": float}, ...]
    """
    url = DUKASCOPY_URL.format(pair=pair, year=year, month=month - 1, day=day, hour=hour)  # month is 0-indexed

    try:
        # Download compressed binary file
        with urlopen(url, timeout=30) as response:
            compressed_data = response.read()

        if len(compressed_data) == 0:
            return []

        # Decompress LZMA
        try:
            data = lzma.decompress(compressed_data)
        except lzma.LZMAError:
            log.warning(f"{pair} LZMA decompress failed for {year}-{month:02d}-{day:02d} {hour:02d}h")
            return []

        # Parse binary tick data
        # Format: 5 int32 values per tick (20 bytes)
        # [timestamp_ms, ask, bid, ask_volume, bid_volume]
        ticks = []
        num_ticks = len(data) // 20

        base_time = datetime(year, month, day, hour, 0, 0)

        for i in range(num_ticks):
            offset = i * 20
            tick_data = struct.unpack('>5i', data[offset:offset + 20])

            timestamp_ms, ask_int, bid_int, ask_vol, bid_vol = tick_data

            # Convert to actual values
            tick_time = base_time + timedelta(milliseconds=timestamp_ms)
            ask = ask_int / 100000.0  # Dukascopy stores as int (multiply by 100000)
            bid = bid_int / 100000.0

            ticks.append({
                "time": tick_time,
                "ask": ask,
                "bid": bid,
                "ask_vol": ask_vol / 1_000_000.0,  # Convert to lots
                "bid_vol": bid_vol / 1_000_000.0,
            })

        return ticks

    except Exception as e:
        # Many hours have no data (weekends, holidays, etc.)
        # Only log errors, don't fail
        if "404" not in str(e):
            log.debug(f"{pair} Error downloading {year}-{month:02d}-{day:02d} {hour:02d}h: {e}")
        return []


def download_day_ticks(pair: str, year: int, month: int, day: int) -> pd.DataFrame:
    """Download all 24 hours for a given day."""
    all_ticks = []

    for hour in range(24):
        hour_ticks = download_hour_ticks(pair, year, month, day, hour)
        all_ticks.extend(hour_ticks)

    if not all_ticks:
        return pd.DataFrame()

    df = pd.DataFrame(all_ticks)
    df['time'] = pd.to_datetime(df['time'], utc=True)
    return df


def download_month_ticks(pair: str, year: int, month: int) -> pd.DataFrame:
    """Download all days in a month."""
    import calendar

    days_in_month = calendar.monthrange(year, month)[1]

    log.info(f"{pair}: Downloading {year}-{month:02d} ({days_in_month} days)...")

    month_ticks = []

    for day in range(1, days_in_month + 1):
        day_df = download_day_ticks(pair, year, month, day)

        if not day_df.empty:
            month_ticks.append(day_df)
            log.info(f"{pair}:   {year}-{month:02d}-{day:02d}: {len(day_df):,} ticks")

    if not month_ticks:
        log.warning(f"{pair}: No ticks for {year}-{month:02d}")
        return pd.DataFrame()

    df = pd.concat(month_ticks, ignore_index=True)
    df = df.sort_values('time').reset_index(drop=True)

    log.info(f"{pair}:   Total for {year}-{month:02d}: {len(df):,} ticks")

    return df


def save_ticks_parquet(df: pd.DataFrame, output_path: Path):
    """Save ticks to Parquet format (JcampFX format)."""
    # Convert to JcampFX tick format
    # Expected columns: time, bid, ask, last, volume, flags

    tick_df = pd.DataFrame({
        'time': df['time'],
        'bid': df['bid'],
        'ask': df['ask'],
        'last': (df['bid'] + df['ask']) / 2.0,  # Mid price
        'volume': df['bid_vol'] + df['ask_vol'],  # Total volume
        'flags': 0,  # No flags
    })

    # Convert to PyArrow
    schema = pa.schema([
        ('time', pa.timestamp('ns', tz='UTC')),
        ('bid', pa.float64()),
        ('ask', pa.float64()),
        ('last', pa.float64()),
        ('volume', pa.float64()),
        ('flags', pa.int32()),
    ])

    table = pa.Table.from_pandas(tick_df, schema=schema)

    # Write to Parquet
    pq.write_table(table, output_path, compression='snappy')

    log.info(f"{output_path.stem}: Saved {len(tick_df):,} ticks")


def download_pair(pair: str):
    """Download one pair (2018-2024, Jan-Jun only for 2024)."""

    output_dir = Path("data/ticks_dukascopy")
    output_dir.mkdir(exist_ok=True)

    # Download 2018-2024 (Jan-Jun only for 2024, we have Jul-Dec from MT5)
    years_to_download = [
        (2018, 1, 12),  # 2018: Jan-Dec
        (2019, 1, 12),  # 2019: Jan-Dec
        (2020, 1, 12),  # 2020: Jan-Dec
        (2021, 1, 12),  # 2021: Jan-Dec
        (2022, 1, 12),  # 2022: Jan-Dec
        (2023, 1, 12),  # 2023: Jan-Dec
        (2024, 1, 6),   # 2024: Jan-Jun (we have Jul onwards from MT5)
    ]

    all_ticks = []

    for year, start_month, end_month in years_to_download:
        log.info(f"\n{'=' * 60}")
        log.info(f"{pair}: Downloading {year} (months {start_month}-{end_month})")
        log.info(f"{'=' * 60}\n")

        year_ticks = []

        for month in range(start_month, end_month + 1):
            month_df = download_month_ticks(pair, year, month)
            if not month_df.empty:
                year_ticks.append(month_df)

        if year_ticks:
            year_df = pd.concat(year_ticks, ignore_index=True)
            year_df = year_df.sort_values('time').reset_index(drop=True)

            # Save year to separate file
            year_output = output_dir / f"{pair}_{year}_ticks.parquet"
            save_ticks_parquet(year_df, year_output)

            all_ticks.append(year_df)

    # Combine all years
    if all_ticks:
        log.info("\n" + "=" * 60)
        log.info(f"{pair}: Combining all years...")
        log.info("=" * 60)

        combined_df = pd.concat(all_ticks, ignore_index=True)
        combined_df = combined_df.sort_values('time').reset_index(drop=True)

        combined_output = output_dir / f"{pair}_2018-2024_ticks.parquet"
        save_ticks_parquet(combined_df, combined_output)

        log.info(f"\n✅ {pair} COMPLETE!")
        log.info(f"   Total ticks: {len(combined_df):,}")
        log.info(f"   Date range: {combined_df['time'].min()} → {combined_df['time'].max()}")
        log.info(f"   Output: {combined_output}\n")
    else:
        log.error(f"{pair}: No ticks downloaded!")


def main():
    """Download historical data for specified pairs (or all pairs by default)."""

    # Parse command line arguments
    if len(sys.argv) > 1:
        # User specified pairs
        pairs_to_download = [arg.upper() for arg in sys.argv[1:]]

        # Validate pairs
        invalid_pairs = [p for p in pairs_to_download if p not in ALL_PAIRS]
        if invalid_pairs:
            log.error(f"Invalid pairs: {invalid_pairs}")
            log.error(f"Valid pairs: {', '.join(ALL_PAIRS)}")
            sys.exit(1)
    else:
        # Download all pairs
        pairs_to_download = ALL_PAIRS

    log.info(f"\n{'=' * 60}")
    log.info(f"Downloading {len(pairs_to_download)} pair(s): {', '.join(pairs_to_download)}")
    log.info(f"Period: 2018-2024 (Jan-Jun 2024 only)")
    log.info(f"{'=' * 60}\n")

    # Download each pair
    for i, pair in enumerate(pairs_to_download, 1):
        log.info(f"\n{'#' * 60}")
        log.info(f"# PAIR {i}/{len(pairs_to_download)}: {pair}")
        log.info(f"{'#' * 60}\n")

        try:
            download_pair(pair)
        except Exception as e:
            log.error(f"{pair}: Download failed with error: {e}")
            import traceback
            traceback.print_exc()
            continue

    log.info("\n" + "=" * 60)
    log.info("ALL DOWNLOADS COMPLETE!")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
