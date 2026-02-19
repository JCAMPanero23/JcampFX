"""
JcampFX — DCRD Layer 2: 1H Dynamic Modifier (−15 to +15)
PRD §3.3 — Three sub-components, each +5 / 0 / −5.

Sub-components:
  1. BB Width       — Bollinger Band width expanding vs percentile
  2. ADX Acceleration — ADX slope rising vs collapsing
  3. CSM Acceleration — Currency differential widening vs rotating

Validation: VD.2 (modifier stays −15 to +15, never overrides structural classification)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.dcrd.calibrate import load_config as _load_dcrd_config

# Load calibrated thresholds at module import (VC.4)
_dcrd_config: dict = _load_dcrd_config()


# ---------------------------------------------------------------------------
# Indicator helpers
# ---------------------------------------------------------------------------

def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _bb_width(ohlc_1h: pd.DataFrame, period: int = 20, std_dev: float = 2.0) -> pd.Series:
    """Bollinger Band width = (upper - lower) / middle."""
    mid = ohlc_1h["close"].rolling(period).mean()
    std = ohlc_1h["close"].rolling(period).std()
    width = (2 * std_dev * std) / (mid + 1e-9)
    return width


def _adx_1h(ohlc_1h: pd.DataFrame, period: int = 14) -> pd.Series:
    """ADX on 1H data (Wilder smoothing)."""
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


# ---------------------------------------------------------------------------
# Sub-component 1 — BB Width (+5 / 0 / −5)
# ---------------------------------------------------------------------------

def bb_width_score(ohlc_1h: pd.DataFrame, period: int = 20, percentile_window: int = 100) -> int:
    """
    PRD §3.3 (v2.2): BB Width expanding rapidly → +5 | In lowest 20th percentile → −5 | else 0

    P20/P80 boundaries loaded from dcrd_config.json when available; otherwise uses
    rolling within-window percentiles (self-referential, always data-relative).
    """
    min_rows = period + percentile_window
    if len(ohlc_1h) < min_rows:
        return 0

    width = _bb_width(ohlc_1h, period)
    current = width.iloc[-1]
    recent = width.iloc[-percentile_window:]

    # Use calibrated absolute thresholds if available, else rolling percentiles
    bb_cfg = _dcrd_config.get("bb_width", {})
    abs_p20 = bb_cfg.get("p20", None)
    abs_p80 = bb_cfg.get("p80", None)

    if abs_p20 is not None and abs_p80 is not None:
        p20 = abs_p20
        p80 = abs_p80
    else:
        p20 = recent.quantile(0.20)
        p80 = recent.quantile(0.80)

    # "Expanding rapidly" = current is above 80th percentile AND rising
    rising = current > width.iloc[-3]
    if current >= p80 and rising:
        return 5
    if current <= p20:
        return -5
    return 0


# ---------------------------------------------------------------------------
# Sub-component 2 — ADX Acceleration (+5 / 0 / −5)
# ---------------------------------------------------------------------------

def adx_acceleration_score(ohlc_1h: pd.DataFrame, period: int = 14, slope_bars: int = 5) -> int:
    """
    PRD §3.3 (v2.2): ADX slope rising strongly → +5 | Slope collapsing → −5 | else 0

    Slope threshold loaded from dcrd_config.json (VC.4).
    Default: 0.2 ADX points per bar (v2.1 value — valid for both pip sizes).
    """
    min_rows = period * 3 + slope_bars
    if len(ohlc_1h) < min_rows:
        return 0

    slope_threshold = _dcrd_config.get("adx_slope_threshold", 0.2)

    adx = _adx_1h(ohlc_1h, period)
    recent_adx = adx.iloc[-slope_bars:]

    slope = (recent_adx.iloc[-1] - recent_adx.iloc[0]) / slope_bars
    if slope > slope_threshold:
        return 5
    if slope < -slope_threshold:
        return -5
    return 0


# ---------------------------------------------------------------------------
# Sub-component 3 — CSM Acceleration (+5 / 0 / −5)
# ---------------------------------------------------------------------------

def csm_acceleration_score(
    csm_1h_data: dict[str, pd.DataFrame],
    pair: str,
    lookback: int = 10,
) -> int:
    """
    PRD: CSM differential widening → +5 | Currency rotation increasing → −5 | else 0

    Measures whether the base/quote strength differential is widening (momentum)
    or narrowing/rotating (adverse).
    """
    if not csm_1h_data or len(csm_1h_data) < 3:
        return 0

    if len(pair) != 6:
        return 0

    base = pair[:3]
    quote = pair[3:]

    def _currency_score(data: dict[str, pd.DataFrame], offset: int) -> dict[str, float]:
        scores: dict[str, float] = {}
        for p, df in data.items():
            if len(df) < offset + 2:
                continue
            ret = (df["close"].iloc[-(offset)] - df["close"].iloc[-(offset + lookback)]) / (
                df["close"].iloc[-(offset + lookback)] + 1e-9
            )
            b, q = p[:3], p[3:]
            scores[b] = scores.get(b, 0) + ret
            scores[q] = scores.get(q, 0) - ret
        return scores

    # Current differential
    current = _currency_score(csm_1h_data, 1)
    # Previous differential (lookback bars ago)
    previous = _currency_score(csm_1h_data, lookback + 1)

    if base not in current or quote not in current:
        return 0

    curr_diff = current.get(base, 0) - current.get(quote, 0)
    prev_diff = previous.get(base, 0) - previous.get(quote, 0)

    # Widening = differential growing in magnitude (same sign, bigger)
    if abs(curr_diff) > abs(prev_diff) * 1.1:
        return 5
    # Rotating = sign flip or rapid narrowing
    if abs(curr_diff) < abs(prev_diff) * 0.7:
        return -5
    return 0


# ---------------------------------------------------------------------------
# Composite Layer 2 Modifier
# ---------------------------------------------------------------------------

def dynamic_modifier(
    ohlc_1h: pd.DataFrame,
    csm_1h_data: dict[str, pd.DataFrame],
    pair: str,
) -> int:
    """
    Compute the 1H Dynamic Modifier (−15 to +15).

    Sum of 3 sub-components × +5/−5.
    VD.2: result is clamped to [−15, +15].
    """
    modifier = (
        bb_width_score(ohlc_1h)
        + adx_acceleration_score(ohlc_1h)
        + csm_acceleration_score(csm_1h_data, pair)
    )
    return int(max(-15, min(15, modifier)))
