"""
JcampFX — DCRD Engine: Dynamic Composite Regime Detection
PRD §3.1 — Composites all 3 layers + anti-flipping filter.

Formula:
    CompositeScore = StructuralScore (0–100)
                   + ModifierScore  (−15 to +15)
                   + RangeBarScore  (0–20)
    Clamped to [0, 100]

Anti-Flipping Filter (PRD §3.6):
    Regime change ONLY if: score crosses threshold by ≥15 points
    AND new regime persists for ≥2 consecutive 4H closes.

Validation:
    VD.1 — All 3 layers contribute to output
    VD.2 — Modifier clamped to [−15, +15]
    VD.3 — RB score independent of structural layer
    VD.4 — CompositeScore maps correctly: >70 Trending, 30–70 Transitional, <30 Range
    VD.5 — Anti-flipping: ≥15pt cross + 2× 4H persistence required
    VD.8 — Risk multiplier applied correctly per regime zone
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from src.config import (
    ANTI_FLIP_PERSISTENCE,
    ANTI_FLIP_THRESHOLD_PTS,
    STRATEGY_BREAKOUTRIDER_MIN_CS,
    STRATEGY_TRENDRIDER_MIN_CS,
)
from src.dcrd.structural_score import structural_score
from src.dcrd.dynamic_modifier import dynamic_modifier
from src.dcrd.range_bar_intelligence import range_bar_score


# ---------------------------------------------------------------------------
# Regime constants
# ---------------------------------------------------------------------------

REGIME_TRENDING = "trending"
REGIME_TRANSITIONAL = "transitional"
REGIME_RANGE = "range"


def _raw_regime(score: float) -> str:
    """Map a raw score to a regime label (no anti-flip)."""
    if score >= STRATEGY_TRENDRIDER_MIN_CS:
        return REGIME_TRENDING
    if score >= STRATEGY_BREAKOUTRIDER_MIN_CS:
        return REGIME_TRANSITIONAL
    return REGIME_RANGE


# ---------------------------------------------------------------------------
# Risk multiplier per regime (PRD §3.5 + §6.2)
# ---------------------------------------------------------------------------

REGIME_RISK_MULTIPLIER: dict[str, float] = {
    REGIME_TRENDING:     1.0,   # 0.8x–1.0x (base 1.0x; DCRD confidence adjusts further)
    REGIME_TRANSITIONAL: 0.6,   # 0.6x
    REGIME_RANGE:        0.7,   # 0.7x
}


# ---------------------------------------------------------------------------
# Per-pair anti-flipping state
# ---------------------------------------------------------------------------

@dataclass
class _AntiFlipState:
    """Tracks pending regime transitions per pair."""
    confirmed_regime: str = REGIME_TRANSITIONAL
    confirmed_score: float = 50.0
    pending_regime: Optional[str] = None
    pending_score: float = 0.0
    pending_count: int = 0      # consecutive 4H bars with pending regime


# ---------------------------------------------------------------------------
# DCRD Engine
# ---------------------------------------------------------------------------

class DCRDEngine:
    """
    Stateful DCRD scoring engine.

    One instance per pair is recommended (stores anti-flip state per pair).
    Alternatively, use a single instance and pass `pair` to maintain per-pair state.

    Usage
    -----
    engine = DCRDEngine()
    score, regime = engine.score(ohlc_4h, ohlc_1h, range_bars, csm_data, pair="EURUSD")
    """

    def __init__(self) -> None:
        self._state: dict[str, _AntiFlipState] = {}

    def _get_state(self, pair: str) -> _AntiFlipState:
        if pair not in self._state:
            self._state[pair] = _AntiFlipState()
        return self._state[pair]

    def score(
        self,
        ohlc_4h: pd.DataFrame,
        ohlc_1h: pd.DataFrame,
        range_bars: pd.DataFrame,
        csm_data: dict[str, pd.DataFrame],
        pair: str,
    ) -> tuple[float, str]:
        """
        Compute the CompositeScore and regime for a pair at the current bar close.

        Parameters
        ----------
        ohlc_4h   : 4H OHLC DataFrame (for structural score)
        ohlc_1h   : 1H OHLC DataFrame (for dynamic modifier)
        range_bars: Range Bar DataFrame (for RB intelligence)
        csm_data  : dict of pair → 4H OHLC for all CSM pairs (for CSM alignment)
        pair      : Canonical pair name (e.g. "EURUSD")

        Returns
        -------
        (composite_score, regime)  where regime is "trending" | "transitional" | "range"
        Anti-flipping filter is applied — regime only changes on confirmed persistence.
        """
        # Layer 1: 4H Structural (0–100)
        layer1 = structural_score(ohlc_4h, csm_data, pair)

        # Layer 2: 1H Dynamic Modifier (−15 to +15)
        # Build 1H CSM data from the same csm_data (resampled or passed separately)
        layer2 = dynamic_modifier(ohlc_1h, csm_data, pair)

        # Layer 3: Range Bar Intelligence (0–20)
        layer3 = range_bar_score(range_bars)

        # Composite (clamped 0–100)
        raw_score = float(max(0, min(100, layer1 + layer2 + layer3)))
        raw_regime = _raw_regime(raw_score)

        # Apply anti-flipping filter
        filtered_score, filtered_regime = self._apply_anti_flip(raw_score, raw_regime, pair)

        return filtered_score, filtered_regime

    def score_components(
        self,
        ohlc_4h: pd.DataFrame,
        ohlc_1h: pd.DataFrame,
        range_bars: pd.DataFrame,
        csm_data: dict[str, pd.DataFrame],
        pair: str,
    ) -> dict:
        """
        Return all component scores for diagnostics / dashboard display.
        """
        from src.dcrd.structural_score import (
            adx_strength_score,
            market_structure_score,
            atr_expansion_score,
            csm_alignment_score,
            trend_persistence_score,
        )
        from src.dcrd.dynamic_modifier import (
            bb_width_score,
            adx_acceleration_score,
            csm_acceleration_score,
        )
        from src.dcrd.range_bar_intelligence import (
            rb_speed_score,
            rb_structure_quality_score,
        )

        l1_adx = adx_strength_score(ohlc_4h)
        l1_struct = market_structure_score(ohlc_4h)
        l1_atr = atr_expansion_score(ohlc_4h)
        l1_csm = csm_alignment_score(csm_data, pair)
        l1_persist = trend_persistence_score(ohlc_4h)
        layer1 = l1_adx + l1_struct + l1_atr + l1_csm + l1_persist

        l2_bb = bb_width_score(ohlc_1h)
        l2_adx_acc = adx_acceleration_score(ohlc_1h)
        l2_csm_acc = csm_acceleration_score(csm_data, pair)
        layer2 = max(-15, min(15, l2_bb + l2_adx_acc + l2_csm_acc))

        l3_speed = rb_speed_score(range_bars)
        l3_struct = rb_structure_quality_score(range_bars)
        layer3 = l3_speed + l3_struct

        raw_score = float(max(0, min(100, layer1 + layer2 + layer3)))
        filtered_score, filtered_regime = self._apply_anti_flip(
            raw_score, _raw_regime(raw_score), pair
        )

        return {
            "pair": pair,
            "layer1_structural": layer1,
            "l1_adx_strength": l1_adx,
            "l1_market_structure": l1_struct,
            "l1_atr_expansion": l1_atr,
            "l1_csm_alignment": l1_csm,
            "l1_trend_persistence": l1_persist,
            "layer2_modifier": layer2,
            "l2_bb_width": l2_bb,
            "l2_adx_acceleration": l2_adx_acc,
            "l2_csm_acceleration": l2_csm_acc,
            "layer3_rb_intelligence": layer3,
            "l3_rb_speed": l3_speed,
            "l3_rb_structure": l3_struct,
            "raw_composite": raw_score,
            "composite_score": filtered_score,
            "regime": filtered_regime,
        }

    def _apply_anti_flip(self, new_score: float, new_regime: str, pair: str) -> tuple[float, str]:
        """
        PRD §3.6 Anti-Flipping Filter:
        Regime change ONLY if:
          1. Score crosses threshold by ≥15 points
          2. New regime persists for ≥2 consecutive 4H closes

        If conditions not met, returns the confirmed (stable) regime.
        """
        state = self._get_state(pair)

        if new_regime == state.confirmed_regime:
            # No regime change — update confirmed score and reset pending
            state.confirmed_score = new_score
            state.pending_regime = None
            state.pending_count = 0
            return new_score, state.confirmed_regime

        # Potential regime change — check the ≥15-point cross requirement
        boundary = _regime_boundary(state.confirmed_regime, new_regime)
        cross_magnitude = abs(new_score - boundary)

        if cross_magnitude < ANTI_FLIP_THRESHOLD_PTS:
            # Cross too small — ignore, stay in confirmed regime
            state.pending_regime = None
            state.pending_count = 0
            return state.confirmed_score, state.confirmed_regime

        # Large enough cross — start persistence counter
        if state.pending_regime == new_regime:
            state.pending_count += 1
            state.pending_score = new_score
        else:
            state.pending_regime = new_regime
            state.pending_score = new_score
            state.pending_count = 1

        if state.pending_count >= ANTI_FLIP_PERSISTENCE:
            # Confirmed — lock in new regime
            state.confirmed_regime = new_regime
            state.confirmed_score = new_score
            state.pending_regime = None
            state.pending_count = 0
            return new_score, new_regime

        # Pending but not confirmed yet — return confirmed regime with confirmed score
        return state.confirmed_score, state.confirmed_regime

    def get_regime(self, score: float) -> str:
        """
        Stateless regime mapping (no anti-flip). Used for testing and backtesting.
        VD.4: >70 → Trending, 30–70 → Transitional, <30 → Range.
        """
        return _raw_regime(score)

    def get_risk_multiplier(self, regime: str) -> float:
        """VD.8: Return the regime-based risk multiplier."""
        return REGIME_RISK_MULTIPLIER.get(regime, 1.0)

    def reset_state(self, pair: str | None = None) -> None:
        """Reset anti-flip state for a pair (or all pairs)."""
        if pair is not None:
            self._state.pop(pair, None)
        else:
            self._state.clear()


def _regime_boundary(from_regime: str, to_regime: str) -> float:
    """Return the score threshold being crossed between two regimes."""
    pair = frozenset([from_regime, to_regime])
    if pair == frozenset([REGIME_TRENDING, REGIME_TRANSITIONAL]):
        return float(STRATEGY_TRENDRIDER_MIN_CS)   # 70
    if pair == frozenset([REGIME_TRANSITIONAL, REGIME_RANGE]):
        return float(STRATEGY_BREAKOUTRIDER_MIN_CS)  # 30
    # Direct trending ↔ range (unusual but possible on extreme data)
    return 50.0
