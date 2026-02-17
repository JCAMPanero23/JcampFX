"""
JcampFX — TrendRider Strategy (Phase 2, PRD §8.2)

Active when CompositeScore ≥ 70 (Trending regime).

Entry logic:
  1. Determine trend direction from EMA200 on 1H (or last Range Bar structure)
  2. Wait for a 3-bar staircase pattern in Range Bars
  3. Identify the 2nd pullback Range Bar in the trend direction
  4. Entry: on close of the 2nd pullback bar
  5. Confirmation: ADX(14) > 25 on 1H OHLC

SL: below the pullback low (BUY) or above the pullback high (SELL)
TP_1R: 1× risk distance from entry (direction-adjusted)

Validation: V2.2 (TrendRider triggers ONLY when CompositeScore ≥ 70)
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

from src.config import PIP_SIZE, STRATEGY_TRENDRIDER_MIN_CS
from src.exit_manager import get_partial_exit_pct
from src.signal import Signal
from src.strategies.base_strategy import BaseStrategy

log = logging.getLogger(__name__)

_ADX_THRESHOLD = 25.0
_STAIRCASE_BARS = 3   # minimum consecutive directional bars for staircase
_PULLBACK_MAX_BARS = 2  # maximum bars in a pullback sequence


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _adx_1h(ohlc_1h: pd.DataFrame, period: int = 14) -> float:
    """Return the latest ADX value from 1H OHLC."""
    if len(ohlc_1h) < period * 3:
        return 0.0
    high = ohlc_1h["high"]
    low = ohlc_1h["low"]
    prev_high = high.shift(1)
    prev_low = low.shift(1)
    prev_close = ohlc_1h["close"].shift(1)

    up_move = high - prev_high
    down_move = prev_low - low

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()

    plus_di = 100 * pd.Series(plus_dm, index=ohlc_1h.index).ewm(span=period, adjust=False).mean() / (atr + 1e-9)
    minus_di = 100 * pd.Series(minus_dm, index=ohlc_1h.index).ewm(span=period, adjust=False).mean() / (atr + 1e-9)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
    adx = dx.ewm(span=period, adjust=False).mean()
    return float(adx.iloc[-1])


def _detect_trend_direction(ohlc_1h: pd.DataFrame) -> str:
    """
    Determine trend direction using EMA200 on 1H close.
    Returns "BUY" (price above EMA200) or "SELL" (price below EMA200).
    Returns "" if insufficient data.
    """
    if len(ohlc_1h) < 200:
        return ""
    ema200 = _ema(ohlc_1h["close"], 200)
    last_close = ohlc_1h["close"].iloc[-1]
    last_ema = ema200.iloc[-1]
    if last_close > last_ema:
        return "BUY"
    if last_close < last_ema:
        return "SELL"
    return ""


def _detect_3bar_staircase(range_bars: pd.DataFrame, direction: str, lookback: int = 15) -> bool:
    """
    Detect a 3-bar staircase pattern in Range Bars.
    BUY staircase: 3+ consecutive bars making HH/HL (higher highs and higher lows)
    SELL staircase: 3+ consecutive bars making LL/LH (lower lows and lower highs)
    """
    if len(range_bars) < _STAIRCASE_BARS + 1:
        return False

    recent = range_bars.tail(lookback).reset_index(drop=True)
    highs = recent["high"].values
    lows = recent["low"].values

    consecutive = 0
    for i in range(1, len(recent)):
        if direction == "BUY":
            if highs[i] > highs[i - 1] and lows[i] > lows[i - 1]:
                consecutive += 1
                if consecutive >= _STAIRCASE_BARS:
                    return True
            else:
                consecutive = 0
        else:
            if highs[i] < highs[i - 1] and lows[i] < lows[i - 1]:
                consecutive += 1
                if consecutive >= _STAIRCASE_BARS:
                    return True
            else:
                consecutive = 0
    return False


def _find_pullback_entry(
    range_bars: pd.DataFrame,
    direction: str,
    lookback: int = 10,
) -> Optional[tuple[float, float, float]]:
    """
    Identify a 2nd pullback bar in the trend direction and return entry parameters.

    A "pullback" in a BUY trend is 1–2 bearish Range Bars (close < open) after
    a run of bullish bars. The 2nd pullback bar is the entry trigger.

    Returns
    -------
    (entry_price, sl_price, tp_1r_price) or None if no setup found.
    entry   = close of the pullback bar
    sl_buy  = low of the pullback bar - 0.5 pip buffer
    tp_buy  = entry + (entry - sl)
    """
    if len(range_bars) < lookback + 2:
        return None

    recent = range_bars.tail(lookback + 2).reset_index(drop=True)
    opens = recent["open"].values
    closes = recent["close"].values
    highs = recent["high"].values
    lows = recent["low"].values

    # Check if last 1–2 bars are counter-trend (pullback)
    # and the bar before them was trend-direction
    last_idx = len(recent) - 1
    last_is_pullback = (
        (direction == "BUY" and closes[last_idx] < opens[last_idx]) or
        (direction == "SELL" and closes[last_idx] > opens[last_idx])
    )
    if not last_is_pullback:
        return None

    # The bar before the pullback should be trend-direction
    prev_is_trend = (
        (direction == "BUY" and closes[last_idx - 1] >= opens[last_idx - 1]) or
        (direction == "SELL" and closes[last_idx - 1] <= opens[last_idx - 1])
    )
    if not prev_is_trend:
        return None

    entry = closes[last_idx]

    if direction == "BUY":
        sl = lows[last_idx]
        r_dist = abs(entry - sl)
        if r_dist <= 0:
            return None
        tp_1r = entry + r_dist
    else:
        sl = highs[last_idx]
        r_dist = abs(entry - sl)
        if r_dist <= 0:
            return None
        tp_1r = entry - r_dist

    return entry, sl, tp_1r


class TrendRider(BaseStrategy):
    """
    TrendRider strategy — active when CompositeScore ≥ 70 (Trending regime).

    Entry: 2nd Range Bar pullback in trend direction
    Confirmation: ADX(14) > 25 on 1H + 3-bar staircase in Range Bars
    """

    name = "TrendRider"
    min_score = float(STRATEGY_TRENDRIDER_MIN_CS)   # 70
    max_score = 100.0

    def analyze(
        self,
        range_bars: pd.DataFrame,
        ohlc_4h: pd.DataFrame,
        ohlc_1h: pd.DataFrame,
        composite_score: float,
        news_state: dict,
    ) -> Optional[Signal]:
        """
        Return a Signal if a TrendRider setup is found, else None.

        V2.2: Returns None if composite_score < 70.
        """
        if not self.is_regime_active(composite_score):
            return None

        if range_bars is None or len(range_bars) < 20:
            return None

        if ohlc_1h is None or len(ohlc_1h) < 210:  # EMA200 + buffer
            return None

        # Step 1: Determine trend direction from EMA200
        direction = _detect_trend_direction(ohlc_1h)
        if not direction:
            return None

        # Step 2: Confirm 3-bar staircase
        if not _detect_3bar_staircase(range_bars, direction):
            return None

        # Step 3: Confirm ADX > 25
        adx = _adx_1h(ohlc_1h)
        if adx <= _ADX_THRESHOLD:
            log.debug("TrendRider: ADX %.1f ≤ 25 — no signal", adx)
            return None

        # Step 4: Find pullback entry
        setup = _find_pullback_entry(range_bars, direction)
        if setup is None:
            return None

        entry, sl, tp_1r = setup
        pair = news_state.get("pair", "UNKNOWN")
        timestamp = range_bars.iloc[-1]["end_time"] if "end_time" in range_bars.columns else pd.Timestamp.utcnow()

        partial_pct = get_partial_exit_pct(composite_score)

        signal = Signal(
            timestamp=pd.Timestamp(timestamp, tz="UTC") if not hasattr(timestamp, "tzinfo") else timestamp,
            pair=pair,
            direction=direction,
            entry=entry,
            sl=sl,
            tp_1r=tp_1r,
            strategy=self.name,
            composite_score=composite_score,
            partial_exit_pct=partial_pct,
        )

        log.info(
            "TrendRider signal: %s %s @ %.5f SL=%.5f ADX=%.1f CS=%.1f partial=%.0f%%",
            direction, pair, entry, sl, adx, composite_score, partial_pct * 100,
        )
        return signal
