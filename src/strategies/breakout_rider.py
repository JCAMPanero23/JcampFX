"""
JcampFX — BreakoutRider Strategy (Phase 2, PRD §8.2)

Active when 30 ≤ CompositeScore ≤ 70 (Transitional/Breakout regime).

Entry logic:
  1. Detect BB compression: BB Width in lowest 20th percentile of recent history
  2. Look for Range Bar close outside Keltner Channel
  3. Confirm RB speed is increasing (momentum building)
  4. Confirm micro-structure break (previous bar's high/low broken)
  5. Entry: on close of the breakout Range Bar

SL: opposite Keltner midline (or the compressed range boundary)
TP_1R: 1× risk distance from entry

Validation: V2.3 (BreakoutRider triggers ONLY in 30–70 with BB compression)
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

from src.config import STRATEGY_BREAKOUTRIDER_MIN_CS, STRATEGY_TRENDRIDER_MIN_CS
from src.exit_manager import get_partial_exit_pct
from src.signal import Signal
from src.strategies.base_strategy import BaseStrategy

log = logging.getLogger(__name__)

_BB_PERIOD = 20
_BB_STD = 2.0
_KC_PERIOD = 20
_KC_MULT = 1.5    # Keltner Channel ATR multiplier
_ATR_PERIOD = 14
_BB_COMPRESSION_PERCENTILE = 20   # BB width in lowest 20th percentile
_SPEED_LOOKBACK = 3               # bars to compare for speed increase


def _bb_width(closes: pd.Series, period: int = _BB_PERIOD, std: float = _BB_STD) -> pd.Series:
    mid = closes.rolling(period).mean()
    sigma = closes.rolling(period).std()
    return (2 * std * sigma) / (mid + 1e-9)


def _atr(ohlc: pd.DataFrame, period: int = _ATR_PERIOD) -> pd.Series:
    high = ohlc["high"]
    low = ohlc["low"]
    prev_close = ohlc["close"].shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def _keltner_bands(ohlc: pd.DataFrame, period: int = _KC_PERIOD, mult: float = _KC_MULT) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (upper, mid, lower) Keltner Channel bands."""
    mid = ohlc["close"].ewm(span=period, adjust=False).mean()
    atr_s = _atr(ohlc, period)
    upper = mid + mult * atr_s
    lower = mid - mult * atr_s
    return upper, mid, lower


def _is_bb_compressed(closes: pd.Series, percentile_window: int = 100) -> bool:
    """Return True if current BB width is in the lowest 20th percentile."""
    if len(closes) < _BB_PERIOD + percentile_window:
        return False
    width = _bb_width(closes)
    current = width.iloc[-1]
    historical = width.iloc[-percentile_window:]
    threshold = historical.quantile(_BB_COMPRESSION_PERCENTILE / 100)
    return current <= threshold


def _rb_speed_increasing(range_bars: pd.DataFrame, lookback: int = _SPEED_LOOKBACK) -> bool:
    """
    Return True if Range Bar formation speed is increasing.
    Proxy: duration of last bar < average duration of prior bars.
    """
    if len(range_bars) < lookback + 2 or "start_time" not in range_bars.columns:
        return True  # insufficient data — assume speed is OK

    recent = range_bars.tail(lookback + 1)
    durations = (
        pd.to_datetime(recent["end_time"]) - pd.to_datetime(recent["start_time"])
    ).dt.total_seconds()

    last_duration = durations.iloc[-1]
    avg_duration = durations.iloc[:-1].mean()

    return last_duration < avg_duration  # faster bars = higher speed


def _is_breakout_bar(range_bars: pd.DataFrame, ohlc_as_rb: pd.DataFrame | None) -> tuple[bool, str]:
    """
    Check if the last Range Bar closes outside the Keltner Channel on RB data
    and breaks the previous bar's structure.

    Returns (is_breakout, direction) where direction is "BUY" or "SELL".
    """
    if len(range_bars) < _KC_PERIOD + 2:
        return False, ""

    # Build a pseudo-OHLC from range bars for Keltner calculation
    rb = range_bars.tail(_KC_PERIOD + 5).copy()
    rb = rb.rename(columns={"open": "open", "high": "high", "low": "low", "close": "close"})

    kc_upper, kc_mid, kc_lower = _keltner_bands(rb)

    last_close = rb["close"].iloc[-1]
    last_high = rb["high"].iloc[-1]
    last_low = rb["low"].iloc[-1]
    prev_high = rb["high"].iloc[-2]
    prev_low = rb["low"].iloc[-2]

    kc_up = kc_upper.iloc[-1]
    kc_dn = kc_lower.iloc[-1]

    # Bullish breakout: close outside upper Keltner + break previous bar high
    if last_close > kc_up and last_high > prev_high:
        return True, "BUY"

    # Bearish breakout: close outside lower Keltner + break previous bar low
    if last_close < kc_dn and last_low < prev_low:
        return True, "SELL"

    return False, ""


class BreakoutRider(BaseStrategy):
    """
    BreakoutRider strategy — active when 30 ≤ CompositeScore ≤ 70 (Transitional regime).

    Entry: RB close outside Keltner during BB compression breakout
    Confirmation: RB speed increasing + micro-structure break
    """

    name = "BreakoutRider"
    min_score = float(STRATEGY_BREAKOUTRIDER_MIN_CS)  # 30
    max_score = float(STRATEGY_TRENDRIDER_MIN_CS)      # 70

    def analyze(
        self,
        range_bars: pd.DataFrame,
        ohlc_4h: pd.DataFrame,
        ohlc_1h: pd.DataFrame,
        composite_score: float,
        news_state: dict,
    ) -> Optional[Signal]:
        """
        Return a Signal if a BreakoutRider setup is found, else None.

        V2.3: Returns None if composite_score outside 30–70 or no BB compression.
        """
        if not self.is_regime_active(composite_score):
            return None

        if range_bars is None or len(range_bars) < _KC_PERIOD + 5:
            return None

        if ohlc_1h is None or len(ohlc_1h) < _BB_PERIOD + 100:
            return None

        # Step 1: Check BB compression on 1H OHLC
        if not _is_bb_compressed(ohlc_1h["close"]):
            log.debug("BreakoutRider: no BB compression — skip")
            return None

        # Step 2 + 4: Check for breakout bar with micro-structure break
        is_breakout, direction = _is_breakout_bar(range_bars, None)
        if not is_breakout:
            return None

        # Step 3: Check RB speed is increasing
        if not _rb_speed_increasing(range_bars):
            log.debug("BreakoutRider: RB speed not increasing — skip")
            return None

        # Build entry parameters
        last_rb = range_bars.iloc[-1]
        entry = float(last_rb["close"])
        kc_mid_val = ohlc_1h["close"].ewm(span=_KC_PERIOD, adjust=False).mean().iloc[-1]

        if direction == "BUY":
            sl = kc_mid_val
            r_dist = abs(entry - sl)
            if r_dist <= 0:
                return None
            tp_1r = entry + r_dist
        else:
            sl = kc_mid_val
            r_dist = abs(entry - sl)
            if r_dist <= 0:
                return None
            tp_1r = entry - r_dist

        pair = news_state.get("pair", "UNKNOWN")
        timestamp = last_rb.get("end_time", pd.Timestamp.utcnow())
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
            "BreakoutRider signal: %s %s @ %.5f SL=%.5f CS=%.1f partial=%.0f%%",
            direction, pair, entry, sl, composite_score, partial_pct * 100,
        )
        return signal
