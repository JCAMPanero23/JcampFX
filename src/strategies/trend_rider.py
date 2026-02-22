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
_ADX_SLOPE_BARS = 5    # bars over which ADX slope is measured (1H bars)
_STAIRCASE_BARS = 5    # minimum consecutive directional bars for staircase (5×bar_size impulse)
_PULLBACK_MAX_BARS = 2  # maximum bars in a pullback sequence


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _adx_series(ohlc_1h: pd.DataFrame, period: int = 14) -> pd.Series:
    """Return full ADX series from 1H OHLC."""
    if len(ohlc_1h) < period * 3:
        return pd.Series(dtype=float)
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
    return dx.ewm(span=period, adjust=False).mean()


def _adx_1h(ohlc_1h: pd.DataFrame, period: int = 14) -> float:
    """Return the latest ADX value from 1H OHLC."""
    adx = _adx_series(ohlc_1h, period)
    return float(adx.iloc[-1]) if len(adx) > 0 else 0.0


def _adx_is_rising(ohlc_1h: pd.DataFrame, period: int = 14, slope_bars: int = _ADX_SLOPE_BARS) -> bool:
    """Return True if ADX is rising over the last slope_bars 1H bars."""
    adx = _adx_series(ohlc_1h, period)
    if len(adx) < slope_bars + 1:
        return False
    return float(adx.iloc[-1]) > float(adx.iloc[-slope_bars - 1])


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


def _detect_3bar_staircase(range_bars: pd.DataFrame, direction: str, lookback: int = 15) -> int:
    """
    Detect a 3-bar staircase pattern in Range Bars.
    Returns the staircase depth (>= _STAIRCASE_BARS) if found, or 0 if not found.
    Return value is bool-compatible: truthy if found, falsy (0) if not.

    BUY staircase: consecutive bars making HH/HL (higher highs and higher lows)
    SELL staircase: consecutive bars making LL/LH (lower lows and lower highs)
    """
    if len(range_bars) < _STAIRCASE_BARS + 1:
        return 0

    recent = range_bars.tail(lookback).reset_index(drop=True)
    highs = recent["high"].values
    lows = recent["low"].values

    consecutive = 0
    max_consecutive = 0
    for i in range(1, len(recent)):
        if direction == "BUY":
            if highs[i] > highs[i - 1] and lows[i] > lows[i - 1]:
                consecutive += 1
                max_consecutive = max(max_consecutive, consecutive)
            else:
                consecutive = 0
        else:
            if highs[i] < highs[i - 1] and lows[i] < lows[i - 1]:
                consecutive += 1
                max_consecutive = max(max_consecutive, consecutive)
            else:
                consecutive = 0

    return max_consecutive if max_consecutive >= _STAIRCASE_BARS else 0


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

    # Range bar entry pattern: wait for the RESUMPTION bar after the pullback.
    # This confirms the pullback has ended before entering (vs predicting reversal).
    #
    # BUY pattern (SELL is mirror):
    #   bar[-2]: pullback bar — close < open (down bar, pullback against uptrend)
    #   bar[-1]: resumption bar — close >= open (up bar, trend direction confirmed)
    #
    # Entry  = close of the resumption bar (confirmed continuation)
    # SL     = low of the pullback bar (structural swing low)
    # r_dist = entry − SL (1–2 bar-sizes depending on pullback depth)
    last_idx = len(recent) - 1

    # bar[-1] must be a trend-direction (resumption) bar
    last_is_resumption = (
        (direction == "BUY" and closes[last_idx] >= opens[last_idx]) or
        (direction == "SELL" and closes[last_idx] <= opens[last_idx])
    )
    if not last_is_resumption:
        return None

    # bar[-2] must be a pullback (counter-trend) bar
    prev_is_pullback = (
        (direction == "BUY" and closes[last_idx - 1] < opens[last_idx - 1]) or
        (direction == "SELL" and closes[last_idx - 1] > opens[last_idx - 1])
    )
    if not prev_is_pullback:
        return None

    entry = closes[last_idx]

    if direction == "BUY":
        sl = lows[last_idx - 1]           # pullback bar's structural low
        r_dist = abs(entry - sl)
        if r_dist <= 0:
            return None
        tp_1r = entry + r_dist
    else:
        sl = highs[last_idx - 1]          # pullback bar's structural high
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
        dcrd_history: Optional[list[float]] = None,  # Phase 3.1.1: DCRD momentum
    ) -> Optional[Signal]:
        """
        Return a Signal if a TrendRider setup is found, else None.

        V2.2: Returns None if composite_score < 70.
        Phase 3.1.1: Returns None if DCRD momentum < 0 (trend deteriorating).
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
        staircase_depth = _detect_3bar_staircase(range_bars, direction)
        if not staircase_depth:
            return None

        # Step 2.5: DCRD momentum filter (Phase 3.1.1)
        # CRITICAL: Block entries when DCRD is declining (trend deteriorating)
        # Analysis showed 100% correlation across 66 trades:
        #   - All 24 wins had stable DCRD (momentum ≥ 0)
        #   - All 42 losses had declining DCRD (momentum < 0)
        # Formula: DCRD_momentum = CS_current - CS_5bars_ago
        pair = news_state.get("pair", "UNKNOWN")
        if dcrd_history is None:
            log.warning("TrendRider %s: dcrd_history is None! Filter skipped.", pair)
        elif len(dcrd_history) < 6:
            log.warning("TrendRider %s: dcrd_history too short (%d < 6)! Filter skipped.", pair, len(dcrd_history))
        else:
            cs_5bars_ago = dcrd_history[-6]  # -1 is current, -6 is 5 bars ago
            dcrd_momentum = composite_score - cs_5bars_ago
            log.info(
                "TrendRider %s: DCRD momentum check: CS %.1f → %.1f (%.1f momentum, %s)",
                pair, cs_5bars_ago, composite_score, dcrd_momentum,
                "PASS" if dcrd_momentum >= 0 else "BLOCK"
            )
            if dcrd_momentum < 0:
                return None

        # Step 3: Confirm ADX > 25 AND rising (trend gaining strength, not exhausting)
        adx = _adx_1h(ohlc_1h)
        adx_rising = _adx_is_rising(ohlc_1h)
        if adx <= _ADX_THRESHOLD:
            log.debug("TrendRider: ADX %.1f <= 25 -- no signal", adx)
            return None
        if not adx_rising:
            log.debug("TrendRider: ADX %.1f not rising -- declining momentum, skip", adx)
            return None

        # Step 4: Find pullback entry
        setup = _find_pullback_entry(range_bars, direction)
        if setup is None:
            return None

        entry, sl, tp_1r = setup
        pair = news_state.get("pair", "UNKNOWN")
        timestamp = range_bars.iloc[-1]["end_time"] if "end_time" in range_bars.columns else pd.Timestamp.utcnow()

        partial_pct = get_partial_exit_pct(composite_score)

        pip = PIP_SIZE.get(pair, 0.0001)

        # CRITICAL: Validate minimum SL distance (PRD v2.2 bug fix - trade 9bb53c06)
        # Without this, shallow pullbacks create SL too close to entry
        # causing inflated negative R-multiples (e.g. -6.00R instead of -1.05R max)
        # Root cause: pullback bar's extreme can be within 0.2 pips of entry
        MIN_SL_PIPS = 10  # 10 pips minimum for all pairs
        r_dist = abs(entry - sl)
        r_dist_pips = r_dist / pip
        if r_dist < MIN_SL_PIPS * pip:
            log.debug(
                "TrendRider: SL too tight (%.2f pips < %d pips min) -- skip signal",
                r_dist_pips, MIN_SL_PIPS
            )
            return None
        pullback_bar_abs_idx = len(range_bars) - 2
        entry_bar_abs_idx = len(range_bars) - 1
        pullback_bar = range_bars.iloc[-2]
        pullback_depth_pips = float(pullback_bar["high"] - pullback_bar["low"]) / pip

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
            adx_at_entry=adx,
            adx_slope_rising=adx_rising,
            staircase_depth=staircase_depth,
            pullback_bar_idx=pullback_bar_abs_idx,
            pullback_depth_pips=pullback_depth_pips,
            entry_bar_idx=entry_bar_abs_idx,
        )

        log.info(
            "TrendRider signal: %s %s @ %.5f SL=%.5f ADX=%.1f CS=%.1f partial=%.0f%%",
            direction, pair, entry, sl, adx, composite_score, partial_pct * 100,
        )
        return signal
