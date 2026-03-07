"""
JcampFX — SwingRider Helper Functions

Daily/H4 timeframe analysis functions for SwingRider convex strategy.
"""

import logging
from typing import Optional

import pandas as pd

from data_loader.daily_ohlc import calculate_atr

log = logging.getLogger(__name__)


def calculate_weekly_pivot(ohlc_daily: pd.DataFrame, lookback_days: int = 7) -> dict:
    """
    Calculate weekly pivot from last week's H/L/C.

    Uses last 5-7 daily bars to compute pivot levels.

    Parameters
    ----------
    ohlc_daily : pd.DataFrame
        Daily OHLC data
    lookback_days : int
        Number of days to use for pivot calculation (default: 7)

    Returns
    -------
    dict
        Weekly pivot levels: {"wp": float, "r1": float, "s1": float}
    """
    if len(ohlc_daily) < lookback_days:
        return {"wp": 0.0, "r1": 0.0, "s1": 0.0}

    # Use last week's data (last 5-7 days, excluding today)
    last_week = ohlc_daily.tail(lookback_days).head(5)

    high = last_week['high'].max()
    low = last_week['low'].min()
    close = last_week['close'].iloc[-1]

    # Standard pivot formula
    wp = (high + low + close) / 3.0
    r1 = (2 * wp) - low
    s1 = (2 * wp) - high

    return {"wp": wp, "r1": r1, "s1": s1}


def check_pivot_bias(
    direction: str, current_price: float, weekly_pivots: dict
) -> bool:
    """
    Check if current price aligns with weekly pivot bias.

    Long trades require price above WP.
    Short trades require price below WP.

    Parameters
    ----------
    direction : str
        "BUY" or "SELL"
    current_price : float
        Current market price
    weekly_pivots : dict
        Weekly pivot levels from calculate_weekly_pivot()

    Returns
    -------
    bool
        True if bias is aligned, False otherwise
    """
    if direction == "BUY":
        return current_price > weekly_pivots["wp"]
    else:  # SELL
        return current_price < weekly_pivots["wp"]


def check_daily_long_regime(ohlc_daily: pd.DataFrame, ema_period: int = 50) -> bool:
    """
    Check if daily chart allows long trades.

    Conditions:
    1. Price above EMA50
    2. EMA50 slope upward (compare last 5 days)
    3. Market structure: Higher High + Higher Low (last 10 days)

    Parameters
    ----------
    ohlc_daily : pd.DataFrame
        Daily OHLC data
    ema_period : int
        EMA period (default: 50)

    Returns
    -------
    bool
        True if long regime is active
    """
    if len(ohlc_daily) < ema_period:
        return False

    # Calculate EMA50 on daily chart
    ema50 = ohlc_daily['close'].ewm(span=ema_period, adjust=False).mean()

    # Price must be above EMA50
    if ohlc_daily['close'].iloc[-1] <= ema50.iloc[-1]:
        return False

    # EMA50 slope must be upward (compare last 5 days)
    if len(ema50) < 6:
        return False
    ema_slope = ema50.iloc[-1] - ema50.iloc[-6]
    if ema_slope <= 0:
        return False

    # Market structure: Higher High + Higher Low (last 10 days)
    if len(ohlc_daily) < 10:
        return False

    recent = ohlc_daily.tail(10)

    # Not making higher highs
    if recent['high'].iloc[-1] <= recent['high'].iloc[-6]:
        return False

    # Not making higher lows
    if recent['low'].iloc[-1] <= recent['low'].iloc[-6]:
        return False

    return True


def check_daily_short_regime(ohlc_daily: pd.DataFrame, ema_period: int = 50) -> bool:
    """
    Check if daily chart allows short trades.

    Conditions:
    1. Price below EMA50
    2. EMA50 slope downward (compare last 5 days)
    3. Market structure: Lower Low + Lower High (last 10 days)

    Parameters
    ----------
    ohlc_daily : pd.DataFrame
        Daily OHLC data
    ema_period : int
        EMA period (default: 50)

    Returns
    -------
    bool
        True if short regime is active
    """
    if len(ohlc_daily) < ema_period:
        return False

    # Calculate EMA50 on daily chart
    ema50 = ohlc_daily['close'].ewm(span=ema_period, adjust=False).mean()

    # Price must be below EMA50
    if ohlc_daily['close'].iloc[-1] >= ema50.iloc[-1]:
        return False

    # EMA50 slope must be downward (compare last 5 days)
    if len(ema50) < 6:
        return False
    ema_slope = ema50.iloc[-1] - ema50.iloc[-6]
    if ema_slope >= 0:
        return False

    # Market structure: Lower Low + Lower High (last 10 days)
    if len(ohlc_daily) < 10:
        return False

    recent = ohlc_daily.tail(10)

    # Not making lower lows
    if recent['low'].iloc[-1] >= recent['low'].iloc[-6]:
        return False

    # Not making lower highs
    if recent['high'].iloc[-1] >= recent['high'].iloc[-6]:
        return False

    return True


def detect_daily_pullback(
    ohlc_daily: pd.DataFrame,
    direction: str,
    min_pullback_candles: int = 2,
    max_pullback_candles: int = 5,
    lookback_bars: int = 10,
    rejection_wick_threshold: float = 0.3,
) -> tuple[bool, float]:
    """
    Detect 2-5 candle pullback that doesn't break previous structure.

    Returns pullback status and swing level (swing low for BUY, swing high for SELL).

    Parameters
    ----------
    ohlc_daily : pd.DataFrame
        Daily OHLC data
    direction : str
        "BUY" or "SELL"
    min_pullback_candles : int
        Minimum pullback candles required
    max_pullback_candles : int
        Maximum pullback candles allowed
    lookback_bars : int
        Window to find structural high/low
    rejection_wick_threshold : float
        Minimum wick size as fraction of bar range (0.3 = 30%)

    Returns
    -------
    tuple[bool, float]
        (pullback_detected, swing_level)
    """
    if len(ohlc_daily) < lookback_bars:
        return False, 0.0

    recent = ohlc_daily.tail(lookback_bars)

    if direction == "BUY":
        # Find recent structural high (highest high in bars -8 to -2, not last 2)
        if len(recent) < 8:
            return False, 0.0

        structural_high = recent.iloc[-8:-2]['high'].max()

        # Count pullback candles (last 2-5 bars lower than structural high)
        pullback_count = 0
        swing_low = float('inf')

        for i in range(-5, 0):  # Check last 5 bars
            if abs(i) > len(recent):
                continue
            if recent.iloc[i]['high'] < structural_high:
                pullback_count += 1
                swing_low = min(swing_low, recent.iloc[i]['low'])

        # Pullback valid if 2-5 candles pulled back
        if not (min_pullback_candles <= pullback_count <= max_pullback_candles):
            return False, 0.0

        # Check for rejection wick (at least one candle with lower tail)
        has_rejection = any(
            recent.iloc[i]['close'] >
            recent.iloc[i]['low'] +
            (recent.iloc[i]['high'] - recent.iloc[i]['low']) * rejection_wick_threshold
            for i in range(-5, 0)
            if abs(i) <= len(recent)
        )

        if has_rejection and swing_low != float('inf'):
            return True, swing_low

    else:  # SELL
        # Mirror logic for downtrend pullback
        if len(recent) < 8:
            return False, 0.0

        structural_low = recent.iloc[-8:-2]['low'].min()
        pullback_count = 0
        swing_high = float('-inf')

        for i in range(-5, 0):
            if abs(i) > len(recent):
                continue
            if recent.iloc[i]['low'] > structural_low:
                pullback_count += 1
                swing_high = max(swing_high, recent.iloc[i]['high'])

        if not (min_pullback_candles <= pullback_count <= max_pullback_candles):
            return False, 0.0

        has_rejection = any(
            recent.iloc[i]['close'] <
            recent.iloc[i]['high'] -
            (recent.iloc[i]['high'] - recent.iloc[i]['low']) * rejection_wick_threshold
            for i in range(-5, 0)
            if abs(i) <= len(recent)
        )

        if has_rejection and swing_high != float('-inf'):
            return True, swing_high

    return False, 0.0


def check_h4_breakout_entry(
    ohlc_h4: pd.DataFrame, swing_level: float, direction: str
) -> bool:
    """
    Check if H4 close breaks above pullback high (BUY) or below pullback low (SELL).

    Parameters
    ----------
    ohlc_h4 : pd.DataFrame
        4H OHLC data
    swing_level : float
        Swing high (SELL) or swing low (BUY) from daily pullback
    direction : str
        "BUY" or "SELL"

    Returns
    -------
    bool
        True if breakout entry triggered
    """
    if len(ohlc_h4) < 2:
        return False

    last_h4 = ohlc_h4.iloc[-1]

    if direction == "BUY":
        # H4 close above swing low (breakout to upside)
        return last_h4['close'] > swing_level
    else:  # SELL
        # H4 close below swing high (breakout to downside)
        return last_h4['close'] < swing_level


def check_h4_engulfing_entry(ohlc_h4: pd.DataFrame, direction: str) -> bool:
    """
    Check for bullish/bearish engulfing candle at pullback zone.

    Parameters
    ----------
    ohlc_h4 : pd.DataFrame
        4H OHLC data
    direction : str
        "BUY" or "SELL"

    Returns
    -------
    bool
        True if engulfing entry triggered
    """
    if len(ohlc_h4) < 2:
        return False

    curr = ohlc_h4.iloc[-1]
    prev = ohlc_h4.iloc[-2]

    if direction == "BUY":
        # Bullish engulfing: prev bearish, curr bullish, curr body engulfs prev
        prev_bearish = prev['close'] < prev['open']
        curr_bullish = curr['close'] > curr['open']
        engulfs = curr['close'] > prev['open'] and curr['open'] < prev['close']
        return prev_bearish and curr_bullish and engulfs

    else:  # SELL
        # Bearish engulfing: prev bullish, curr bearish, curr body engulfs prev
        prev_bullish = prev['close'] > prev['open']
        curr_bearish = curr['close'] < curr['open']
        engulfs = curr['close'] < prev['open'] and curr['open'] > prev['close']
        return prev_bullish and curr_bearish and engulfs


def calculate_swing_sl(
    direction: str,
    entry_price: float,
    swing_level: float,
    ohlc_daily: pd.DataFrame,
    pip_size: float = 0.01,
    atr_period: int = 14,
    atr_multiplier: float = 0.5,
) -> float:
    """
    Calculate stop loss at pullback swing level ± 0.5×ATR(14).

    Typical GBPJPY range: 200-350 pips.

    Parameters
    ----------
    direction : str
        "BUY" or "SELL"
    entry_price : float
        Entry price
    swing_level : float
        Pullback swing low (BUY) or high (SELL)
    ohlc_daily : pd.DataFrame
        Daily OHLC data
    pip_size : float
        Pip size for the pair (default: 0.01 for GBPJPY)
    atr_period : int
        ATR period (default: 14)
    atr_multiplier : float
        ATR multiplier for buffer (default: 0.5)

    Returns
    -------
    float
        Stop loss price
    """
    # Calculate ATR(14) on daily chart
    atr14 = calculate_atr(ohlc_daily, period=atr_period)

    # Buffer: 0.5 × ATR(14)
    buffer = atr_multiplier * atr14

    if direction == "BUY":
        # SL = swing low - buffer
        sl = swing_level - buffer
    else:  # SELL
        # SL = swing high + buffer
        sl = swing_level + buffer

    # Verify typical range (200-350 pips for GBPJPY)
    sl_distance_pips = abs(entry_price - sl) / pip_size

    # Log warning if SL outside expected range
    if not (200 <= sl_distance_pips <= 350):
        log.warning(
            f"SwingRider SL distance {sl_distance_pips:.0f} pips "
            f"outside typical 200-350 range"
        )

    return sl


def is_volatility_expansion(
    ohlc_daily: pd.DataFrame,
    atr_threshold: float = 1.5,
    range_threshold: float = 1.8,
    lookback_days: int = 20,
) -> bool:
    """
    Detect volatility expansion to activate Chandelier accelerator.

    Conditions:
    - ATR(14) > 1.5 × 20-day ATR average
    - Daily range > 1.8 × 20-day average range

    Parameters
    ----------
    ohlc_daily : pd.DataFrame
        Daily OHLC data
    atr_threshold : float
        ATR expansion threshold multiplier (default: 1.5)
    range_threshold : float
        Range expansion threshold multiplier (default: 1.8)
    lookback_days : int
        Rolling window for averages (default: 20)

    Returns
    -------
    bool
        True if volatility expansion detected
    """
    if len(ohlc_daily) < max(lookback_days, 22):
        return False

    # Calculate ATR(14)
    atr14 = calculate_atr(ohlc_daily, period=14)

    # Calculate 20-day ATR average (using simple range as proxy)
    atr_series = ohlc_daily['high'] - ohlc_daily['low']
    atr_20day_avg = atr_series.tail(lookback_days).mean()

    # Condition 1: ATR expansion
    atr_expanded = atr14 > (atr_threshold * atr_20day_avg)

    # Calculate daily range
    last_range = ohlc_daily['high'].iloc[-1] - ohlc_daily['low'].iloc[-1]
    range_20day_avg = atr_series.tail(lookback_days).mean()

    # Condition 2: Range expansion
    range_expanded = last_range > (range_threshold * range_20day_avg)

    return atr_expanded and range_expanded


def check_hard_invalidation(
    trade_direction: str,
    ohlc_daily: pd.DataFrame,
    structure_lookback: int = 6,
    ema_period: int = 50,
    ema_atr_buffer: float = 0.5,
) -> bool:
    """
    Check if daily chart shows structural invalidation.

    Force-close runner if:
    1. Opposite structure break (new LL in uptrend, new HH in downtrend)
    2. Close through EMA50 with strong momentum

    Parameters
    ----------
    trade_direction : str
        "BUY" or "SELL"
    ohlc_daily : pd.DataFrame
        Daily OHLC data
    structure_lookback : int
        Bars to check for opposite structure (default: 6)
    ema_period : int
        EMA period (default: 50)
    ema_atr_buffer : float
        EMA penetration threshold in ATR units (default: 0.5)

    Returns
    -------
    bool
        True if hard invalidation detected (force-close runner)
    """
    if len(ohlc_daily) < max(10, ema_period):
        return False

    recent = ohlc_daily.tail(10)
    ema50 = ohlc_daily['close'].ewm(span=ema_period, adjust=False).mean()

    last_close = recent['close'].iloc[-1]
    last_ema50 = ema50.iloc[-1]

    if trade_direction == "BUY":
        # Opposite structure: New lower low
        if len(recent) > structure_lookback:
            prev_lows = recent['low'].iloc[-structure_lookback - 1:-1]
            if recent['low'].iloc[-1] < prev_lows.min():
                log.warning("SwingRider hard invalidation: new lower low in uptrend")
                return True

        # Close through EMA50 with momentum (close < EMA50 - 0.5×ATR)
        atr14 = calculate_atr(ohlc_daily, 14)
        if last_close < (last_ema50 - ema_atr_buffer * atr14):
            log.warning("SwingRider hard invalidation: close through EMA50")
            return True

    else:  # SELL
        # Opposite structure: New higher high
        if len(recent) > structure_lookback:
            prev_highs = recent['high'].iloc[-structure_lookback - 1:-1]
            if recent['high'].iloc[-1] > prev_highs.max():
                log.warning("SwingRider hard invalidation: new higher high in downtrend")
                return True

        # Close through EMA50 with momentum
        atr14 = calculate_atr(ohlc_daily, 14)
        if last_close > (last_ema50 + ema_atr_buffer * atr14):
            log.warning("SwingRider hard invalidation: close through EMA50")
            return True

    return False
