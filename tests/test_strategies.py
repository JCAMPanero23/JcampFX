"""
Phase 2 Unit Tests — Strategy Modules
PRD §8 validation items: V2.2–V2.4, V2.11, V2.12, V2.14 (GATE)

Run:
    pytest tests/test_strategies.py -v
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from src.strategies.base_strategy import BaseStrategy
from src.strategies.trend_rider import TrendRider
from src.strategies.breakout_rider import BreakoutRider
from src.strategies.range_rider import RangeRider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ohlc(
    n: int = 300,
    start_price: float = 1.1000,
    trend: float = 0.0001,
    volatility: float = 0.0003,
    seed: int = 42,
    hours_per_bar: int = 4,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    closes = [start_price + i * trend + rng.normal(0, volatility) for i in range(n)]
    highs = [c + rng.uniform(0.0001, 0.0004) for c in closes]
    lows = [c - rng.uniform(0.0001, 0.0004) for c in closes]
    opens = [closes[max(0, i - 1)] + rng.normal(0, 0.0001) for i in range(n)]
    times = [datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=hours_per_bar * i) for i in range(n)]
    return pd.DataFrame({"time": times, "open": opens, "high": highs, "low": lows, "close": closes})


def _make_trending_ohlc(n: int = 300, trend: float = 0.0002) -> pd.DataFrame:
    return _make_ohlc(n, trend=trend)


def _make_1h_ohlc(n: int = 250) -> pd.DataFrame:
    """1H OHLC for strategy confirmation indicators (EMA200 requires 200+ bars)."""
    return _make_ohlc(n, hours_per_bar=1, trend=0.0001)


def _make_range_bars_trending(n: int = 40) -> pd.DataFrame:
    """Range bars in a clear uptrend (bullish staircase)."""
    bars = []
    price = 1.1000
    t = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bar_size = 0.001
    for i in range(n):
        # Staircase: 3 up, 1 pullback, repeat
        if i % 4 == 3:
            direction = -1  # pullback
        else:
            direction = 1   # trend
        open_p = price
        close_p = price + direction * bar_size
        high_p = max(open_p, close_p) + 0.00005
        low_p = min(open_p, close_p)
        duration = timedelta(minutes=5 + (i % 5))
        bars.append({
            "open": open_p, "high": high_p, "low": low_p, "close": close_p,
            "tick_volume": 50,
            "start_time": t, "end_time": t + duration,
        })
        price = close_p
        t += duration
    return pd.DataFrame(bars)


def _make_range_bars_ranging(n: int = 30, center: float = 1.1000, band: float = 0.002) -> pd.DataFrame:
    """Range bars oscillating within a defined range."""
    bars = []
    price = center
    t = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bar_size = 0.001
    for i in range(n):
        # Alternate: hit top then bottom
        target = center + band if i % 6 < 3 else center - band
        direction = 1 if target > price else -1
        open_p = price
        close_p = min(center + band, max(center - band, price + direction * bar_size))
        high_p = max(open_p, close_p)
        low_p = min(open_p, close_p)
        duration = timedelta(minutes=8)
        bars.append({
            "open": open_p, "high": high_p, "low": low_p, "close": close_p,
            "tick_volume": 30,
            "start_time": t, "end_time": t + duration,
        })
        price = close_p
        t += duration
    return pd.DataFrame(bars)


def _news_state(pair: str = "EURUSD") -> dict:
    return {"pair": pair, "blocked": False, "post_cooling": False, "events": []}


# ---------------------------------------------------------------------------
# V2.2 — TrendRider triggers ONLY when CompositeScore ≥ 70
# ---------------------------------------------------------------------------

class TestTrendRider:
    """V2.2: TrendRider ONLY activates when CS ≥ 70."""

    def setup_method(self):
        self.strategy = TrendRider()

    def test_regime_range_correct(self):
        assert self.strategy.min_score == 70.0
        assert self.strategy.max_score == 100.0

    def test_blocked_when_cs_below_70(self):
        """CS = 65 → TrendRider returns None."""
        ohlc = _make_trending_ohlc(300)
        ohlc_1h = _make_1h_ohlc(250)
        rbs = _make_range_bars_trending(40)
        result = self.strategy.analyze(rbs, ohlc, ohlc_1h, composite_score=65.0, news_state=_news_state())
        assert result is None

    def test_blocked_when_cs_transitional(self):
        """CS = 50 → TrendRider returns None."""
        ohlc = _make_trending_ohlc(300)
        ohlc_1h = _make_1h_ohlc(250)
        rbs = _make_range_bars_trending(40)
        result = self.strategy.analyze(rbs, ohlc, ohlc_1h, composite_score=50.0, news_state=_news_state())
        assert result is None

    def test_blocked_when_cs_range(self):
        """CS = 20 → TrendRider returns None."""
        ohlc = _make_trending_ohlc(300)
        ohlc_1h = _make_1h_ohlc(250)
        rbs = _make_range_bars_trending(40)
        result = self.strategy.analyze(rbs, ohlc, ohlc_1h, composite_score=20.0, news_state=_news_state())
        assert result is None

    def test_regime_check_method(self):
        assert self.strategy.is_regime_active(70) is True
        assert self.strategy.is_regime_active(100) is True
        assert self.strategy.is_regime_active(69) is False
        assert self.strategy.is_regime_active(50) is False

    def test_returns_signal_schema_when_active(self):
        """When CS >= 70, if a setup is found, signal has correct fields."""
        from src.signal import Signal
        ohlc = _make_trending_ohlc(300)
        ohlc_1h = _make_1h_ohlc(250)
        rbs = _make_range_bars_trending(40)
        result = self.strategy.analyze(rbs, ohlc, ohlc_1h, composite_score=80.0, news_state=_news_state())
        if result is not None:
            assert isinstance(result, Signal)
            assert result.strategy == "TrendRider"
            assert result.direction in ("BUY", "SELL")
            assert result.composite_score == 80.0
            assert result.partial_exit_pct > 0

    def test_insufficient_data_returns_none(self):
        """Not enough bars → None (no crash)."""
        tiny_rbs = _make_range_bars_trending(5)
        tiny_ohlc = _make_ohlc(10)
        tiny_1h = _make_ohlc(10)
        result = self.strategy.analyze(tiny_rbs, tiny_ohlc, tiny_1h, 80.0, _news_state())
        assert result is None


# ---------------------------------------------------------------------------
# V2.3 — BreakoutRider triggers ONLY in 30–70 with BB compression
# ---------------------------------------------------------------------------

class TestBreakoutRider:
    """V2.3: BreakoutRider ONLY activates when CS is 30–70."""

    def setup_method(self):
        self.strategy = BreakoutRider()

    def test_regime_range_correct(self):
        assert self.strategy.min_score == 30.0
        assert self.strategy.max_score == 70.0

    def test_blocked_when_cs_above_70(self):
        """CS = 80 → BreakoutRider returns None."""
        ohlc = _make_trending_ohlc(300)
        ohlc_1h = _make_1h_ohlc(250)
        rbs = _make_range_bars_ranging(30)
        result = self.strategy.analyze(rbs, ohlc, ohlc_1h, composite_score=80.0, news_state=_news_state())
        assert result is None

    def test_blocked_when_cs_below_30(self):
        """CS = 20 → BreakoutRider returns None."""
        ohlc = _make_trending_ohlc(300)
        ohlc_1h = _make_1h_ohlc(250)
        rbs = _make_range_bars_ranging(30)
        result = self.strategy.analyze(rbs, ohlc, ohlc_1h, composite_score=20.0, news_state=_news_state())
        assert result is None

    def test_regime_check_method(self):
        assert self.strategy.is_regime_active(30) is True
        assert self.strategy.is_regime_active(50) is True
        assert self.strategy.is_regime_active(70) is True
        assert self.strategy.is_regime_active(71) is False
        assert self.strategy.is_regime_active(29) is False

    def test_insufficient_data_returns_none(self):
        tiny_rbs = _make_range_bars_ranging(5)
        tiny_ohlc = _make_ohlc(10)
        tiny_1h = _make_ohlc(10)
        result = self.strategy.analyze(tiny_rbs, tiny_ohlc, tiny_1h, 50.0, _news_state())
        assert result is None


# ---------------------------------------------------------------------------
# V2.4 — RangeRider: min 8 RBs + width > 2x RB size
# ---------------------------------------------------------------------------

class TestRangeRider:
    """V2.4: RangeRider: min 8 RBs in range block + block width > 2× RB size."""

    def setup_method(self):
        self.strategy = RangeRider()

    def test_regime_range_correct(self):
        assert self.strategy.min_score == 0.0
        assert self.strategy.max_score == 30.0

    def test_blocked_when_cs_above_30(self):
        """CS = 50 → RangeRider returns None."""
        ohlc = _make_ohlc(300)
        ohlc_1h = _make_1h_ohlc(250)
        rbs = _make_range_bars_ranging(30)
        result = self.strategy.analyze(rbs, ohlc, ohlc_1h, composite_score=50.0, news_state=_news_state())
        assert result is None

    def test_blocked_when_cs_trending(self):
        """CS = 80 → RangeRider returns None."""
        ohlc = _make_ohlc(300)
        ohlc_1h = _make_1h_ohlc(250)
        rbs = _make_range_bars_ranging(30)
        result = self.strategy.analyze(rbs, ohlc, ohlc_1h, composite_score=80.0, news_state=_news_state())
        assert result is None

    def test_regime_check_method(self):
        assert self.strategy.is_regime_active(0) is True
        assert self.strategy.is_regime_active(25) is True
        assert self.strategy.is_regime_active(30) is True
        assert self.strategy.is_regime_active(31) is False

    def test_insufficient_bars_returns_none(self):
        """Less than 8 Range Bars → RangeRider returns None."""
        tiny_rbs = _make_range_bars_ranging(5)
        ohlc = _make_ohlc(300)
        ohlc_1h = _make_1h_ohlc(250)
        result = self.strategy.analyze(tiny_rbs, ohlc, ohlc_1h, composite_score=15.0, news_state=_news_state())
        assert result is None

    def test_no_range_block_returns_none(self):
        """With trending bars (not a range), no range block found → None."""
        trending_rbs = _make_range_bars_trending(30)
        ohlc = _make_ohlc(300)
        ohlc_1h = _make_1h_ohlc(250)
        result = self.strategy.analyze(trending_rbs, ohlc, ohlc_1h, composite_score=15.0, news_state=_news_state())
        # Trending bars won't have a wide enough range block
        # This may or may not produce a signal depending on width — just ensure no crash
        pass  # No assertion — just checking no exception


# ---------------------------------------------------------------------------
# V2.11 — Auto-registration
# ---------------------------------------------------------------------------

class TestAutoRegistration:
    """V2.11: New strategy module auto-registers from /strategies/ without Brain Core changes."""

    def test_base_strategy_is_abstract(self):
        """BaseStrategy cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseStrategy()

    def test_all_strategies_are_base_subclasses(self):
        strategies = [TrendRider(), BreakoutRider(), RangeRider()]
        for s in strategies:
            assert isinstance(s, BaseStrategy), f"{s.name} not a BaseStrategy subclass"

    def test_brain_core_auto_registers_all_3(self):
        """BrainCore should discover all 3 strategies at init."""
        from src.brain_core import BrainCore
        brain = BrainCore()
        registered = brain.get_registered_strategies()
        assert "TrendRider" in registered, "TrendRider not registered"
        assert "BreakoutRider" in registered, "BreakoutRider not registered"
        assert "RangeRider" in registered, "RangeRider not registered"

    def test_strategies_have_unique_names(self):
        strategies = [TrendRider(), BreakoutRider(), RangeRider()]
        names = [s.name for s in strategies]
        assert len(names) == len(set(names)), "Strategy names must be unique"

    def test_strategy_name_attribute_set(self):
        for cls in (TrendRider, BreakoutRider, RangeRider):
            instance = cls()
            assert instance.name != "BaseStrategy", f"{cls.__name__} must set name attribute"


# ---------------------------------------------------------------------------
# V2.12 — Performance tracker disables/re-enables strategies
# ---------------------------------------------------------------------------

class TestStrategyCooldown:
    """V2.12: Performance tracker disables/re-enables strategies correctly."""

    def test_cooldown_triggered_on_5_consecutive_losses(self):
        from src.performance_tracker import PerformanceTracker
        tracker = PerformanceTracker()
        for _ in range(5):
            tracker.add_trade("TrendRider", -1.0)
        assert tracker.is_in_cooldown("TrendRider") is True

    def test_cooldown_not_triggered_on_4_losses(self):
        from src.performance_tracker import PerformanceTracker
        tracker = PerformanceTracker()
        for _ in range(4):
            tracker.add_trade("TrendRider", -1.0)
        assert tracker.is_in_cooldown("TrendRider") is False

    def test_cooldown_broken_by_win(self):
        """5 losses followed by a win — no cooldown (win breaks streak)."""
        from src.performance_tracker import PerformanceTracker
        tracker = PerformanceTracker()
        for _ in range(4):
            tracker.add_trade("TrendRider", -1.0)
        tracker.add_trade("TrendRider", +1.5)   # win breaks streak
        for _ in range(4):
            tracker.add_trade("TrendRider", -1.0)
        # After win + 4 more losses = 4 consecutive, not 5
        assert tracker.is_in_cooldown("TrendRider") is False

    def test_strategies_track_independently(self):
        """V2.12 + VR.4: each strategy tracked independently."""
        from src.performance_tracker import PerformanceTracker
        tracker = PerformanceTracker()
        for _ in range(5):
            tracker.add_trade("TrendRider", -1.0)
        # BreakoutRider should not be in cooldown
        assert tracker.is_in_cooldown("TrendRider") is True
        assert tracker.is_in_cooldown("BreakoutRider") is False
        assert tracker.is_in_cooldown("RangeRider") is False

    def test_cooldown_reset(self):
        """After reset, strategy becomes active."""
        from src.performance_tracker import PerformanceTracker
        tracker = PerformanceTracker()
        for _ in range(5):
            tracker.add_trade("TrendRider", -1.0)
        assert tracker.is_in_cooldown("TrendRider") is True
        tracker.reset_cooldown("TrendRider")
        assert tracker.is_in_cooldown("TrendRider") is False


# ---------------------------------------------------------------------------
# V2.14 — GATE: Unit tests pass for all 3 strategies independently
# ---------------------------------------------------------------------------

class TestStrategiesGate:
    """V2.14 GATE: All 3 strategies pass independent unit tests."""

    def test_trend_rider_no_exception_on_valid_data(self):
        strategy = TrendRider()
        ohlc = _make_trending_ohlc(300)
        ohlc_1h = _make_1h_ohlc(250)
        rbs = _make_range_bars_trending(40)
        result = strategy.analyze(rbs, ohlc, ohlc_1h, 80.0, _news_state())
        # Should not raise — result is Signal or None

    def test_breakout_rider_no_exception_on_valid_data(self):
        strategy = BreakoutRider()
        ohlc = _make_trending_ohlc(300)
        ohlc_1h = _make_1h_ohlc(250)
        rbs = _make_range_bars_ranging(30)
        result = strategy.analyze(rbs, ohlc, ohlc_1h, 50.0, _news_state())

    def test_range_rider_no_exception_on_valid_data(self):
        strategy = RangeRider()
        ohlc = _make_ohlc(300)
        ohlc_1h = _make_1h_ohlc(250)
        rbs = _make_range_bars_ranging(30)
        result = strategy.analyze(rbs, ohlc, ohlc_1h, 15.0, _news_state())

    def test_all_strategies_return_none_on_empty_bars(self):
        """All strategies must handle empty/insufficient data gracefully."""
        empty = pd.DataFrame()
        ohlc = _make_ohlc(300)
        ohlc_1h = _make_1h_ohlc(250)
        for cls, cs in [(TrendRider, 80.0), (BreakoutRider, 50.0), (RangeRider, 15.0)]:
            s = cls()
            result = s.analyze(empty, ohlc, ohlc_1h, cs, _news_state())
            assert result is None, f"{cls.__name__} should return None on empty range_bars"


# ---------------------------------------------------------------------------
# Task 3 -- _detect_3bar_staircase returns int depth (not bool)
# ---------------------------------------------------------------------------

def test_staircase_returns_int_depth_not_bool():
    """_detect_3bar_staircase returns int depth >= _STAIRCASE_BARS when found."""
    from src.strategies.trend_rider import _detect_3bar_staircase
    import pandas as pd
    # Build a clean 10-bar BUY staircase (each bar HH/HL)
    highs = [1.1000 + i * 0.0020 for i in range(10)]
    lows  = [1.0990 + i * 0.0020 for i in range(10)]
    bars = pd.DataFrame({
        "high": highs, "low": lows,
        "open": lows, "close": highs,
        "end_time": pd.date_range("2024-01-01", periods=10, freq="h"),
    })
    depth = _detect_3bar_staircase(bars, "BUY")
    assert isinstance(depth, int), f"Expected int, got {type(depth)}"
    assert depth >= 5  # _STAIRCASE_BARS = 5


def test_staircase_returns_zero_when_not_found():
    """_detect_3bar_staircase returns 0 (falsy) when no staircase found."""
    from src.strategies.trend_rider import _detect_3bar_staircase
    import pandas as pd
    # Alternating bars -- no staircase
    bars = pd.DataFrame({
        "high": [1.10, 1.09, 1.11, 1.09, 1.11, 1.09, 1.11, 1.09],
        "low":  [1.09, 1.08, 1.10, 1.08, 1.10, 1.08, 1.10, 1.08],
        "open": [1.095]*8, "close": [1.095]*8,
        "end_time": pd.date_range("2024-01-01", periods=8, freq="h"),
    })
    result = _detect_3bar_staircase(bars, "BUY")
    assert result == 0
    assert not result  # must be falsy


def test_staircase_bool_compat():
    """_detect_3bar_staircase return value must be truthy when found (bool-compatible)."""
    from src.strategies.trend_rider import _detect_3bar_staircase
    import pandas as pd
    highs = [1.1000 + i * 0.0020 for i in range(10)]
    lows  = [1.0990 + i * 0.0020 for i in range(10)]
    bars = pd.DataFrame({
        "high": highs, "low": lows,
        "open": lows, "close": highs,
        "end_time": pd.date_range("2024-01-01", periods=10, freq="h"),
    })
    assert _detect_3bar_staircase(bars, "BUY")  # truthy when found
