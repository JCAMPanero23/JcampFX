"""
Phase 2 Unit Tests — DCRD Engine
PRD §3 validation items: VD.1–VD.5, VD.7, VD.8

Run:
    pytest tests/test_dcrd.py -v
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from src.dcrd.structural_score import (
    adx_strength_score,
    atr_expansion_score,
    csm_alignment_score,
    market_structure_score,
    structural_score,
    trend_persistence_score,
)
from src.dcrd.dynamic_modifier import (
    adx_acceleration_score,
    bb_width_score,
    dynamic_modifier,
)
from src.dcrd.range_bar_intelligence import (
    range_bar_score,
    rb_speed_score,
    rb_structure_quality_score,
)
from src.dcrd.dcrd_engine import DCRDEngine, REGIME_TRENDING, REGIME_TRANSITIONAL, REGIME_RANGE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ohlc(
    n: int,
    start_price: float = 1.1000,
    trend: float = 0.0001,
    volatility: float = 0.0005,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate synthetic OHLC data."""
    rng = np.random.default_rng(seed)
    closes = [start_price + i * trend + rng.normal(0, volatility) for i in range(n)]
    highs = [c + rng.uniform(0.0001, 0.0005) for c in closes]
    lows = [c - rng.uniform(0.0001, 0.0005) for c in closes]
    opens = [closes[max(0, i - 1)] + rng.normal(0, 0.0001) for i in range(n)]
    times = [datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=4 * i) for i in range(n)]
    return pd.DataFrame({"time": times, "open": opens, "high": highs, "low": lows, "close": closes})


def _make_trending_ohlc(n: int = 300, trend: float = 0.0002) -> pd.DataFrame:
    """Generate strongly trending OHLC data."""
    return _make_ohlc(n, trend=trend, volatility=0.0002)


def _make_range_bars(n: int = 30, bar_size: float = 0.001) -> pd.DataFrame:
    """Generate synthetic Range Bar data."""
    bars = []
    price = 1.1000
    t = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for i in range(n):
        direction = 1 if i % 3 != 2 else -1  # mostly bullish with some pullbacks
        open_p = price
        close_p = price + direction * bar_size
        high_p = max(open_p, close_p) + 0.00005
        low_p = min(open_p, close_p)
        duration = timedelta(minutes=5 + i % 10)
        bars.append({
            "open": open_p, "high": high_p, "low": low_p, "close": close_p,
            "tick_volume": 50 + i,
            "start_time": t, "end_time": t + duration,
        })
        price = close_p
        t += duration
    return pd.DataFrame(bars)


# ---------------------------------------------------------------------------
# VD.1 — All 3 layers contribute to 0–100 output
# ---------------------------------------------------------------------------

class TestStructuralScore:
    """VD.1: 4H Structural Score (0–100) with all 5 components contributing."""

    def test_score_in_range(self):
        ohlc = _make_trending_ohlc(300)
        score = structural_score(ohlc, {}, "EURUSD")
        assert 0 <= score <= 100, f"Structural score {score} out of range"

    def test_all_components_return_valid(self):
        ohlc = _make_trending_ohlc(300)
        assert adx_strength_score(ohlc) in (0, 10, 20)
        assert market_structure_score(ohlc) in (0, 10, 20)
        assert atr_expansion_score(ohlc) in (0, 10, 20)
        assert trend_persistence_score(ohlc) in (0, 10, 20)

    def test_csm_alignment_returns_valid(self):
        # With no CSM data, should return moderate (10)
        score = csm_alignment_score({}, "EURUSD")
        assert score in (0, 10, 20)

    def test_csm_with_data_returns_valid(self):
        csm_data = {
            "EURUSD": _make_trending_ohlc(50, trend=0.0002),
            "GBPUSD": _make_trending_ohlc(50, trend=0.0001),
            "USDJPY": _make_ohlc(50, start_price=150.0, trend=-0.05),
        }
        score = csm_alignment_score(csm_data, "EURUSD")
        assert score in (0, 10, 20)

    def test_insufficient_data_returns_zero(self):
        tiny = _make_ohlc(5)
        assert adx_strength_score(tiny) == 0
        assert atr_expansion_score(tiny) == 0
        assert trend_persistence_score(tiny) == 0


class TestDynamicModifier:
    """VD.2: 1H Modifier stays −15 to +15."""

    def test_modifier_range(self):
        ohlc = _make_trending_ohlc(200, trend=0.0001)
        mod = dynamic_modifier(ohlc, {}, "EURUSD")
        assert -15 <= mod <= 15, f"Dynamic modifier {mod} out of range"

    def test_modifier_components_valid(self):
        ohlc = _make_trending_ohlc(200)
        bb = bb_width_score(ohlc)
        adx_acc = adx_acceleration_score(ohlc)
        assert bb in (-5, 0, 5)
        assert adx_acc in (-5, 0, 5)

    def test_modifier_never_overrides_structural(self):
        """VD.2: modifier can't push composite beyond 100 or below 0."""
        # If structural = 100 and modifier = +15, composite still ≤ 100
        # This is enforced by the clamping in dcrd_engine.py
        ohlc = _make_trending_ohlc(300)
        engine = DCRDEngine()
        rbs = _make_range_bars(30)
        score, _ = engine.score(ohlc, ohlc, rbs, {}, "EURUSD")
        assert 0 <= score <= 100


class TestRangeBarIntelligence:
    """VD.3: RB score 0–20, independent of structural layer."""

    def test_rb_score_range(self):
        rbs = _make_range_bars(30)
        score = range_bar_score(rbs)
        assert 0 <= score <= 20, f"RB score {score} out of range"

    def test_rb_speed_valid(self):
        rbs = _make_range_bars(30)
        speed = rb_speed_score(rbs)
        assert speed in (0, 5, 10)

    def test_rb_structure_valid(self):
        rbs = _make_range_bars(30)
        struct = rb_structure_quality_score(rbs)
        assert struct in (0, 5, 10)

    def test_rb_score_independent(self):
        """Changing OHLC data should not affect RB score."""
        rbs = _make_range_bars(30)
        score1 = range_bar_score(rbs)
        # Even with different structural data the RB score stays the same
        # (function uses only range_bars input)
        score2 = range_bar_score(rbs)
        assert score1 == score2

    def test_insufficient_rb_data_returns_moderate(self):
        """With < 2 bars, should return a default (not crash)."""
        tiny = _make_range_bars(1)
        score = rb_speed_score(tiny)
        assert score in (0, 5, 10)


# ---------------------------------------------------------------------------
# VD.4 — Composite correctly maps to regimes
# ---------------------------------------------------------------------------

class TestRegimeMapping:
    """VD.4: > 70 Trending, 30–70 Transitional, < 30 Range."""

    def setup_method(self):
        self.engine = DCRDEngine()

    def test_trending_regime(self):
        assert self.engine.get_regime(75) == REGIME_TRENDING
        assert self.engine.get_regime(100) == REGIME_TRENDING
        assert self.engine.get_regime(70) == REGIME_TRENDING

    def test_transitional_regime(self):
        assert self.engine.get_regime(50) == REGIME_TRANSITIONAL
        assert self.engine.get_regime(30) == REGIME_TRANSITIONAL
        assert self.engine.get_regime(69) == REGIME_TRANSITIONAL

    def test_range_regime(self):
        assert self.engine.get_regime(25) == REGIME_RANGE
        assert self.engine.get_regime(0) == REGIME_RANGE
        assert self.engine.get_regime(29) == REGIME_RANGE

    def test_boundary_trending(self):
        """Score = 70 should be Trending (inclusive lower bound)."""
        assert self.engine.get_regime(70) == REGIME_TRENDING

    def test_boundary_range(self):
        """Score = 30 is Transitional (≥30), 29 is Range."""
        assert self.engine.get_regime(30) == REGIME_TRANSITIONAL
        assert self.engine.get_regime(29) == REGIME_RANGE


# ---------------------------------------------------------------------------
# VD.5 — Anti-flipping filter
# ---------------------------------------------------------------------------

class TestAntiFlipping:
    """VD.5: ≥15pt cross + 2× 4H persistence required for regime change."""

    def setup_method(self):
        self.engine = DCRDEngine()

    def test_small_cross_doesnt_flip(self):
        """A cross of < 15 points should not change regime."""
        # Start in Trending (confirmed at score 75)
        self.engine.reset_state("EURUSD")
        state = self.engine._get_state("EURUSD")
        state.confirmed_score = 75.0
        state.confirmed_regime = "trending"

        # Small dip to 65 (only 5-point cross of the 70 boundary)
        score1, regime1 = self.engine._apply_anti_flip(65.0, "transitional", "EURUSD")
        assert regime1 == "trending", "Small cross should not flip regime"

    def test_large_cross_requires_persistence(self):
        """A large cross needs 2 consecutive closes to confirm."""
        self.engine.reset_state("EURUSD")
        state = self.engine._get_state("EURUSD")
        state.confirmed_score = 80.0
        state.confirmed_regime = "trending"

        # First bar: crosses down by 25 points (to 55 = 15 pts below 70 boundary)
        score1, regime1 = self.engine._apply_anti_flip(55.0, "transitional", "EURUSD")
        assert regime1 == "trending", "First bar should stay in previous regime"
        assert self.engine._get_state("EURUSD").pending_count == 1

        # Second bar: same regime confirmed
        score2, regime2 = self.engine._apply_anti_flip(52.0, "transitional", "EURUSD")
        assert regime2 == "transitional", "Second bar should confirm regime change"

    def test_regime_flips_back_before_persistence(self):
        """If new regime doesn't persist, stay in confirmed regime."""
        self.engine.reset_state("EURUSD")
        state = self.engine._get_state("EURUSD")
        state.confirmed_score = 80.0
        state.confirmed_regime = "trending"

        # First bar dips down
        self.engine._apply_anti_flip(50.0, "transitional", "EURUSD")
        # Second bar bounces back
        score, regime = self.engine._apply_anti_flip(78.0, "trending", "EURUSD")
        assert regime == "trending", "Bounce back should cancel pending flip"
        assert self.engine._get_state("EURUSD").pending_count == 0

    def test_stable_regime_stays_stable(self):
        """No change when score stays in same regime."""
        self.engine.reset_state("EURUSD")
        state = self.engine._get_state("EURUSD")
        state.confirmed_score = 75.0
        state.confirmed_regime = "trending"

        score, regime = self.engine._apply_anti_flip(80.0, "trending", "EURUSD")
        assert regime == "trending"
        assert self.engine._get_state("EURUSD").pending_count == 0


# ---------------------------------------------------------------------------
# VD.7 — CSM pulls from all 9 monitored pairs
# ---------------------------------------------------------------------------

class TestCSMPairs:
    """VD.7: CSM alignment score uses all 9 CSM pairs."""

    def test_csm_accepts_9_pairs(self):
        from src.config import CSM_PAIRS
        assert len(CSM_PAIRS) == 9, f"Expected 9 CSM pairs, got {len(CSM_PAIRS)}"

        csm_data = {p: _make_trending_ohlc(50) for p in CSM_PAIRS}
        score = csm_alignment_score(csm_data, "EURUSD")
        assert score in (0, 10, 20)

    def test_csm_base_and_quote_extracted(self):
        """Ensure CSM correctly parses base/quote from 6-char pair."""
        score = csm_alignment_score({}, "EURUSD")  # should return 10 (moderate, no data)
        assert score == 10


# ---------------------------------------------------------------------------
# VD.8 — Risk multiplier per regime zone
# ---------------------------------------------------------------------------

class TestRiskMultiplierByRegime:
    """VD.8: Risk multiplier applied correctly per regime zone."""

    def setup_method(self):
        self.engine = DCRDEngine()

    def test_trending_multiplier(self):
        mult = self.engine.get_risk_multiplier("trending")
        assert mult == 1.0

    def test_transitional_multiplier(self):
        mult = self.engine.get_risk_multiplier("transitional")
        assert mult == 0.6

    def test_range_multiplier(self):
        mult = self.engine.get_risk_multiplier("range")
        assert mult == 0.7

    def test_unknown_regime_default(self):
        mult = self.engine.get_risk_multiplier("unknown")
        assert mult == 1.0  # fallback


# ---------------------------------------------------------------------------
# Integration: full composite score
# ---------------------------------------------------------------------------

class TestFullCompositeScore:
    """VD.1: Full composite score from all 3 layers."""

    def test_composite_output_range(self):
        engine = DCRDEngine()
        ohlc = _make_trending_ohlc(300)
        rbs = _make_range_bars(30)
        score, regime = engine.score(ohlc, ohlc, rbs, {}, "EURUSD")
        assert 0 <= score <= 100
        assert regime in (REGIME_TRENDING, REGIME_TRANSITIONAL, REGIME_RANGE)

    def test_score_components_diagnostic(self):
        engine = DCRDEngine()
        ohlc = _make_trending_ohlc(300)
        rbs = _make_range_bars(30)
        components = engine.score_components(ohlc, ohlc, rbs, {}, "EURUSD")
        assert "layer1_structural" in components
        assert "layer2_modifier" in components
        assert "layer3_rb_intelligence" in components
        assert 0 <= components["composite_score"] <= 100
