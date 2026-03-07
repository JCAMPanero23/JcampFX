"""
JcampFX — Daily OHLC Data Loader

Provides daily OHLC data by resampling 4H OHLC.
Used by SwingRider for daily regime filters and Chandelier exit calculations.
"""

from datetime import datetime
from pathlib import Path
import logging

import pandas as pd

log = logging.getLogger(__name__)


def load_daily_ohlc_for_pair(
    pair: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> pd.DataFrame:
    """
    Load daily OHLC for a given pair.

    If cached daily data exists, load from cache.
    Otherwise, resample from 4H OHLC and cache the result.

    Parameters
    ----------
    pair : str
        Canonical pair name (e.g., "GBPJPY")
    start_date : datetime, optional
        Filter data from this date onwards
    end_date : datetime, optional
        Filter data up to this date

    Returns
    -------
    pd.DataFrame
        Daily OHLC with columns: time, open, high, low, close
        Index is DatetimeIndex in UTC timezone
    """
    cache_path = Path("data/ohlc_daily") / f"{pair}_D1.parquet"

    # Load from cache if exists
    if cache_path.exists():
        log.debug(f"Loading daily OHLC from cache: {cache_path}")
        df = pd.read_parquet(cache_path)
        df['time'] = pd.to_datetime(df['time'], utc=True)
        df.set_index('time', inplace=True)
    else:
        # Resample from 4H OHLC
        log.info(f"Daily OHLC cache not found for {pair}, resampling from 4H...")
        df = _resample_4h_to_daily(pair)

        # Cache result
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        df_to_save = df.reset_index()
        df_to_save.to_parquet(cache_path, index=False)
        log.info(f"Cached daily OHLC to {cache_path}")

    # Apply date filters if provided
    if start_date is not None:
        df = df[df.index >= pd.Timestamp(start_date, tz='UTC')]
    if end_date is not None:
        df = df[df.index <= pd.Timestamp(end_date, tz='UTC')]

    return df


def _resample_4h_to_daily(pair: str) -> pd.DataFrame:
    """
    Resample 4H OHLC to daily timeframe.

    Parameters
    ----------
    pair : str
        Canonical pair name

    Returns
    -------
    pd.DataFrame
        Daily OHLC with DatetimeIndex
    """
    h4_path = Path("data/ohlc_4h") / f"{pair}_H4.parquet"

    if not h4_path.exists():
        raise FileNotFoundError(
            f"Cannot resample to daily: 4H OHLC not found at {h4_path}"
        )

    # Load 4H data
    df_4h = pd.read_parquet(h4_path)
    df_4h['time'] = pd.to_datetime(df_4h['time'], utc=True)
    df_4h.set_index('time', inplace=True)

    # Resample to daily (using calendar days)
    # Daily bars close at 23:59:59 UTC
    df_daily = df_4h.resample('D').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
    }).dropna()

    log.info(
        f"Resampled {pair} 4H → Daily: {len(df_4h)} bars → {len(df_daily)} days"
    )

    return df_daily


def calculate_atr(ohlc: pd.DataFrame, period: int = 14) -> float:
    """
    Calculate Average True Range (ATR) on OHLC data.

    Parameters
    ----------
    ohlc : pd.DataFrame
        OHLC data with columns: high, low, close
    period : int
        ATR period (default: 14)

    Returns
    -------
    float
        ATR value (latest value in series)
    """
    if len(ohlc) < period:
        return 0.0

    # Calculate True Range
    high_low = ohlc['high'] - ohlc['low']
    high_close = (ohlc['high'] - ohlc['close'].shift()).abs()
    low_close = (ohlc['low'] - ohlc['close'].shift()).abs()

    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)

    # Calculate ATR using exponential moving average
    atr = true_range.ewm(span=period, adjust=False).mean()

    return atr.iloc[-1]
