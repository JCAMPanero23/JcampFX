"""
JcampFX — Pivot Level Calculator for TrendRider

Calculates daily pivot points from 4H OHLC data for entry quality filtering.
"""

from __future__ import annotations

import pandas as pd


def calculate_daily_pivots_from_4h(ohlc_4h: pd.DataFrame) -> dict[str, float]:
    """
    Calculate daily pivot points from 4H OHLC data.

    Uses the last complete day's H/L/C to calculate pivots.

    Parameters
    ----------
    ohlc_4h : pd.DataFrame
        4H OHLC data with columns: time, high, low, close

    Returns
    -------
    dict with keys: pivot, r1, r2, s1, s2
    """
    if len(ohlc_4h) < 6:  # Need at least 1 day of 4H bars
        return {"pivot": 0.0, "r1": 0.0, "r2": 0.0, "s1": 0.0, "s2": 0.0}

    # Get yesterday's data (last 6 bars = 24 hours)
    yesterday = ohlc_4h.tail(12).head(6)  # Skip today, get yesterday

    high = float(yesterday["high"].max())
    low = float(yesterday["low"].min())
    close = float(yesterday["close"].iloc[-1])

    pivot = (high + low + close) / 3.0
    r1 = (2 * pivot) - low
    s1 = (2 * pivot) - high
    r2 = pivot + (high - low)
    s2 = pivot - (high - low)

    return {
        "pivot": pivot,
        "r1": r1,
        "r2": r2,
        "s1": s1,
        "s2": s2,
    }


def is_near_pivot_level(
    price: float,
    pivots: dict[str, float],
    tolerance_pips: float,
    pip_size: float,
) -> bool:
    """
    Check if price is within tolerance of ANY pivot level.

    Parameters
    ----------
    price : float
        Current market price
    pivots : dict
        Pivot levels from calculate_daily_pivots_from_4h()
    tolerance_pips : float
        Distance in pips to consider "near" a level
    pip_size : float
        Pip size for the pair

    Returns
    -------
    True if price is within tolerance of any pivot level
    """
    tolerance_price = tolerance_pips * pip_size

    for level_name, level_price in pivots.items():
        if level_price == 0.0:
            continue
        if abs(price - level_price) <= tolerance_price:
            return True

    return False
