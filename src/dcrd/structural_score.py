"""
JcampFX — DCRD Layer 1: 4H Structural Regime Score (0–100)
PRD §3.2 — Five components, each 0–20 points.

Components:
  1. ADX Strength         — ADX(14) level + slope
  2. Market Structure     — HH/HL or LL/LH count (last 20 bars)
  3. ATR Expansion        — ATR_curr / ATR_20avg ratio
  4. CSM Alignment        — Currency Strength Meter: base/quote ≥70% across grid
  5. Trend Persistence    — % of last 20 candles closing same side of EMA200

Validation: VD.1 (all 5 components contributing to 0–100 output)
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Indicator helpers
# ---------------------------------------------------------------------------

def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _atr(ohlc: pd.DataFrame, period: int = 14) -> pd.Series:
    high = ohlc["high"]
    low = ohlc["low"]
    prev_close = ohlc["close"].shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def _adx(ohlc: pd.DataFrame, period: int = 14) -> pd.Series:
    """Return ADX series (Wilder smoothing)."""
    high = ohlc["high"]
    low = ohlc["low"]
    prev_high = high.shift(1)
    prev_low = low.shift(1)

    up_move = high - prev_high
    down_move = prev_low - low

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    atr_s = _atr(ohlc, period)
    plus_di = 100 * pd.Series(plus_dm, index=ohlc.index).ewm(span=period, adjust=False).mean() / atr_s
    minus_di = 100 * pd.Series(minus_dm, index=ohlc.index).ewm(span=period, adjust=False).mean() / atr_s

    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9))
    adx = dx.ewm(span=period, adjust=False).mean()
    return adx


# ---------------------------------------------------------------------------
# Component 1 — ADX Strength (0 / 10 / 20)
# ---------------------------------------------------------------------------

def adx_strength_score(ohlc_4h: pd.DataFrame, period: int = 14) -> int:
    """
    PRD: ADX > 25 + rising slope → 20 | ADX 20–25 → 10 | ADX < 18 → 0

    Requires at least 3 * period rows for stable ADX.
    Returns 0 if insufficient data.
    """
    min_rows = period * 3
    if len(ohlc_4h) < min_rows:
        return 0

    adx = _adx(ohlc_4h, period)
    current_adx = adx.iloc[-1]
    slope_rising = adx.iloc[-1] > adx.iloc[-3]  # last 3 bars trend

    if current_adx > 25 and slope_rising:
        return 20
    if current_adx >= 20:
        return 10
    if current_adx < 18:
        return 0
    return 10  # 18–20 zone → same as moderate


# ---------------------------------------------------------------------------
# Component 2 — Market Structure (0 / 10 / 20)
# ---------------------------------------------------------------------------

def market_structure_score(ohlc_4h: pd.DataFrame, lookback: int = 20) -> int:
    """
    PRD: ≥3 confirmed HH/HL or LL/LH → 20 | Mixed structure → 10 | Repeated failure → 0

    Counts swing highs and swing lows over the last `lookback` bars.
    A swing high/low is confirmed when the next bar closes below/above it.
    """
    if len(ohlc_4h) < lookback + 2:
        return 0

    df = ohlc_4h.tail(lookback + 2).reset_index(drop=True)
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values

    # Detect pivot highs and lows (simple 3-bar confirmation)
    pivot_highs = []
    pivot_lows = []
    for i in range(1, len(df) - 1):
        if highs[i] > highs[i - 1] and highs[i] > highs[i + 1]:
            pivot_highs.append(highs[i])
        if lows[i] < lows[i - 1] and lows[i] < lows[i + 1]:
            pivot_lows.append(lows[i])

    # Count HH/HL sequence
    hh_hl = 0
    if len(pivot_highs) >= 2:
        for i in range(1, len(pivot_highs)):
            if pivot_highs[i] > pivot_highs[i - 1]:
                hh_hl += 1
    if len(pivot_lows) >= 2:
        for i in range(1, len(pivot_lows)):
            if pivot_lows[i] > pivot_lows[i - 1]:
                hh_hl += 1

    # Count LL/LH sequence
    ll_lh = 0
    if len(pivot_highs) >= 2:
        for i in range(1, len(pivot_highs)):
            if pivot_highs[i] < pivot_highs[i - 1]:
                ll_lh += 1
    if len(pivot_lows) >= 2:
        for i in range(1, len(pivot_lows)):
            if pivot_lows[i] < pivot_lows[i - 1]:
                ll_lh += 1

    dominant = max(hh_hl, ll_lh)
    recessive = min(hh_hl, ll_lh)

    if dominant >= 3 and recessive <= 1:
        return 20
    if dominant >= 2:
        return 10
    return 0


# ---------------------------------------------------------------------------
# Component 3 — ATR Expansion (0 / 10 / 20)
# ---------------------------------------------------------------------------

def atr_expansion_score(ohlc_4h: pd.DataFrame, period: int = 14, avg_period: int = 20) -> int:
    """
    PRD: ATR_curr / ATR_20avg ≥ 1.2 → 20 | 0.9–1.2 → 10 | < 0.8 → 0
    """
    min_rows = period + avg_period
    if len(ohlc_4h) < min_rows:
        return 0

    atr_series = _atr(ohlc_4h, period)
    current_atr = atr_series.iloc[-1]
    avg_atr = atr_series.iloc[-avg_period:].mean()

    if avg_atr <= 0:
        return 0

    ratio = current_atr / avg_atr
    if ratio >= 1.2:
        return 20
    if ratio >= 0.9:
        return 10
    return 0


# ---------------------------------------------------------------------------
# Component 4 — CSM Alignment (0 / 10 / 20)
# ---------------------------------------------------------------------------

def csm_alignment_score(csm_data: dict[str, pd.DataFrame], pair: str) -> int:
    """
    PRD: Base/quote ≥70% alignment across 9-pair grid → 20 | Moderate → 10 | Divergent → 0

    csm_data: dict mapping pair → 4H OHLC DataFrame (for all CSM_PAIRS)
    pair:     the pair being evaluated (e.g. "EURUSD")

    Method: compute a simple relative strength score for each of the 8 major
    currencies from the CSM grid returns, then check if the base and quote
    currencies are on opposite sides (base strong + quote weak OR vice versa).
    """
    if not csm_data or len(csm_data) < 3:
        return 10  # insufficient data — default moderate

    # Extract base and quote from pair
    if len(pair) != 6:
        return 10
    base = pair[:3]
    quote = pair[3:]

    # Build currency strength ranks using last 20 bars' returns
    currency_scores: dict[str, float] = {}
    for p, df in csm_data.items():
        if len(df) < 21:
            continue
        ret = (df["close"].iloc[-1] - df["close"].iloc[-21]) / df["close"].iloc[-21]
        b, q = p[:3], p[3:]
        currency_scores[b] = currency_scores.get(b, 0) + ret
        currency_scores[q] = currency_scores.get(q, 0) - ret

    if base not in currency_scores or quote not in currency_scores:
        return 10

    base_strength = currency_scores[base]
    quote_strength = currency_scores[quote]

    # Compute how many pairs in the grid confirm the expected direction
    all_scores = list(currency_scores.values())
    if not all_scores:
        return 10

    # Rank base vs quote: are they on clearly opposite sides of the median?
    median = np.median(all_scores)
    base_above = base_strength > median
    quote_below = quote_strength < median

    # Count grid confirmation percentage
    n_currencies = len(all_scores)
    base_rank_pct = sum(1 for v in all_scores if base_strength > v) / n_currencies
    quote_rank_pct = sum(1 for v in all_scores if quote_strength < v) / n_currencies

    # Both base strong and quote weak → alignment
    alignment = (base_rank_pct + quote_rank_pct) / 2

    if alignment >= 0.70:
        return 20
    if alignment >= 0.40:
        return 10
    return 0


# ---------------------------------------------------------------------------
# Component 5 — Trend Persistence (0 / 10 / 20)
# ---------------------------------------------------------------------------

def trend_persistence_score(ohlc_4h: pd.DataFrame, ema_period: int = 200, lookback: int = 20) -> int:
    """
    PRD: ≥70% candles close vs EMA200 (same side consistently) → 20 | Mixed → 10 | Whipsaw → 0
    """
    min_rows = ema_period + lookback
    if len(ohlc_4h) < min_rows:
        return 0

    ema200 = _ema(ohlc_4h["close"], ema_period)
    recent_closes = ohlc_4h["close"].iloc[-lookback:]
    recent_ema = ema200.iloc[-lookback:]

    above = (recent_closes > recent_ema).sum()
    below = (recent_closes < recent_ema).sum()
    dominant_pct = max(above, below) / lookback

    if dominant_pct >= 0.70:
        return 20
    if dominant_pct >= 0.50:
        return 10
    return 0


# ---------------------------------------------------------------------------
# Composite Layer 1 Score
# ---------------------------------------------------------------------------

def structural_score(
    ohlc_4h: pd.DataFrame,
    csm_data: dict[str, pd.DataFrame],
    pair: str,
) -> int:
    """
    Compute the 4H Structural Regime Score (0–100).

    Returns sum of all 5 component scores (each 0–20).
    VD.1: all 5 components must contribute.
    """
    score = (
        adx_strength_score(ohlc_4h)
        + market_structure_score(ohlc_4h)
        + atr_expansion_score(ohlc_4h)
        + csm_alignment_score(csm_data, pair)
        + trend_persistence_score(ohlc_4h)
    )
    return int(max(0, min(100, score)))
