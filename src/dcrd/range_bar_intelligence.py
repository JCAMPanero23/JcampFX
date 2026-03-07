"""
JcampFX — DCRD Layer 3: Range Bar Intelligence (0–20)
PRD §3.4 — Two sub-components, each 0–10 points.

Sub-components:
  1. RB Speed Score     — Bars formed per 60 minutes (High=10, Normal=5, Slow=0)
  2. RB Structure Quality — Directional bars + pullback pattern (Strong=10, Mixed=5, Alternating=0)

Validation: VD.3 (RB score 0–20, independent of structural layer)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.dcrd.calibrate import load_config as _load_dcrd_config

# Load calibrated RB speed thresholds at module import (VC.4, VC.5)
_dcrd_config: dict = _load_dcrd_config()


# ---------------------------------------------------------------------------
# Sub-component 1 — RB Speed Score (0 / 5 / 10)
# ---------------------------------------------------------------------------

def rb_speed_score(
    range_bars: pd.DataFrame,
    lookback_minutes: int = 60,
    high_threshold: float | None = None,
    slow_threshold: float | None = None,
) -> int:
    """
    PRD §3.4 (v2.2): Bars/60min — High = 10, Normal = 5, Slow = 0

    Thresholds loaded from dcrd_config.json (VC.5: recalibrated for 20-pip bars).
    Falls back to defaults (high=3, slow=1) for 20-pip bars if config unavailable.

    Counts how many Range Bars formed in the last `lookback_minutes` minutes.
    Uses the 'end_time' column to determine which bars fall in the window.

    Parameters
    ----------
    range_bars       : DataFrame with 'start_time' and 'end_time' columns
    lookback_minutes : Rolling window in minutes (default 60)
    high_threshold   : Override bars/hour for "High" speed (default: from config)
    slow_threshold   : Override bars/hour for "Slow" speed (default: from config)
    """
    if range_bars is None or len(range_bars) < 2:
        return 5  # insufficient data — default normal

    required_cols = {"end_time", "start_time"}
    if not required_cols.issubset(range_bars.columns):
        return 5

    # Load calibrated thresholds (VC.5)
    rb_cfg = _dcrd_config.get("rb_speed", {})
    _high = high_threshold if high_threshold is not None else rb_cfg.get("p75", 3.0)
    _slow = slow_threshold if slow_threshold is not None else rb_cfg.get("p25", 1.0)

    end_times = pd.to_datetime(range_bars["end_time"], utc=True)
    last_time = end_times.iloc[-1]
    window_start = last_time - pd.Timedelta(minutes=lookback_minutes)

    bars_in_window = (end_times >= window_start).sum()

    if bars_in_window >= _high:
        return 10
    if bars_in_window >= _slow:
        return 5
    return 0


# ---------------------------------------------------------------------------
# Sub-component 2 — RB Structure Quality (0 / 5 / 10)
# ---------------------------------------------------------------------------

def rb_structure_quality_score(
    range_bars: pd.DataFrame,
    lookback: int = 20,
) -> int:
    """
    PRD: Directional bars + pullback → Strong = 10 | Mixed = 5 | Alternating = 0

    Evaluates the last `lookback` Range Bars for directional quality:
    - Strong: ≥70% bars in same direction + at least 1 pullback sequence
    - Mixed: 50–70% same direction
    - Alternating: < 50% same direction (choppy)

    A "directional" bar is one where close > open (bullish) or close < open (bearish).
    """
    if range_bars is None or len(range_bars) < lookback:
        return 5  # insufficient data — default mixed

    required_cols = {"open", "close"}
    if not required_cols.issubset(range_bars.columns):
        return 5

    recent = range_bars.tail(lookback)
    opens = recent["open"].values
    closes = recent["close"].values

    # Count bullish vs bearish bars
    bullish = np.sum(closes > opens)
    bearish = np.sum(closes < opens)
    total = len(recent)

    dominant = max(bullish, bearish)
    dominant_pct = dominant / total if total > 0 else 0.5

    if dominant_pct < 0.5:
        return 0  # Alternating / choppy

    # Check for at least one pullback sequence in the dominant direction
    # A pullback = 1–2 counter-direction bars within a run of dominant bars
    has_pullback = _has_pullback_sequence(closes > opens, dominant_direction=bullish >= bearish)

    if dominant_pct >= 0.70 and has_pullback:
        return 10
    if dominant_pct >= 0.50:
        return 5
    return 0


def _has_pullback_sequence(is_bullish: np.ndarray, dominant_direction: bool) -> bool:
    """
    Detect a 1–2 bar counter-direction sequence within a dominant trend.
    dominant_direction: True = looking for bearish pullbacks in bullish trend
    """
    direction = is_bullish if dominant_direction else ~is_bullish
    in_run = False
    pullback_count = 0

    for i in range(len(direction)):
        if direction[i]:
            if not in_run:
                in_run = True
        else:
            if in_run:
                pullback_count += 1
                in_run = False  # reset — pullback found

    return pullback_count >= 1


# ---------------------------------------------------------------------------
# Composite Layer 3 Score
# ---------------------------------------------------------------------------

def range_bar_score(range_bars: pd.DataFrame, lookback_minutes: int = 60, lookback_bars: int = 20) -> int:
    """
    Compute Range Bar Intelligence score (0–20).

    VD.3: Independent of structural layer, uses only Range Bar data.
    """
    speed = rb_speed_score(range_bars, lookback_minutes=lookback_minutes)
    structure = rb_structure_quality_score(range_bars, lookback=lookback_bars)
    return int(max(0, min(20, speed + structure)))
