"""
JcampFX — Data Loader Package

Utilities for loading and resampling OHLC data for backtesting.
"""

from .daily_ohlc import load_daily_ohlc_for_pair

__all__ = ["load_daily_ohlc_for_pair"]
