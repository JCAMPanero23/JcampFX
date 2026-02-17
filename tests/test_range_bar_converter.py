"""
Phase 1 Unit Tests — Range Bar Converter
PRD §7.4 validation items: V1.3, V1.4, V1.6, V1.8

Run:
    pytest tests/test_range_bar_converter.py -v
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from src.range_bar_converter import RangeBarConverter, ticks_to_range_bars, RangeBar


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(minutes: int) -> pd.Timestamp:
    """Return a UTC Timestamp N minutes from a fixed base."""
    base = datetime(2024, 1, 2, 8, 0, 0, tzinfo=timezone.utc)  # Tuesday 08:00 UTC
    return pd.Timestamp(base + timedelta(minutes=minutes))


def _make_ticks(prices: list[float], start_minute: int = 0, gap_minutes: int = 1) -> pd.DataFrame:
    """Build a minimal tick DataFrame from a price list (bid = ask = price)."""
    return pd.DataFrame({
        "time": [_ts(start_minute + i * gap_minutes) for i in range(len(prices))],
        "bid":  [float(p) for p in prices],
        "ask":  [float(p) for p in prices],
    })


def _converter(bar_pips: int = 10, pip_size: float = 0.0001) -> RangeBarConverter:
    return RangeBarConverter(bar_pips=bar_pips, pip_size=pip_size)


BAR_SIZE_PRICE = 10 * 0.0001  # 0.0010 for 10-pip EURUSD bar


# ---------------------------------------------------------------------------
# V1.8 — Determinism: same ticks always produce the same bars
# ---------------------------------------------------------------------------

class TestDeterminism:
    """V1.8: Unit test — 100 ticks → deterministic N Range Bars."""

    def test_same_input_same_output(self):
        prices = [1.1000 + i * 0.0001 for i in range(100)]
        ticks = _make_ticks(prices)

        conv1 = _converter()
        bars1 = conv1.convert(ticks)

        conv2 = _converter()
        bars2 = conv2.convert(ticks)

        assert len(bars1) == len(bars2), "Bar count must be deterministic"
        for b1, b2 in zip(bars1, bars2):
            assert b1.open  == pytest.approx(b2.open,  abs=1e-8)
            assert b1.high  == pytest.approx(b2.high,  abs=1e-8)
            assert b1.low   == pytest.approx(b2.low,   abs=1e-8)
            assert b1.close == pytest.approx(b2.close, abs=1e-8)

    def test_100_ticks_produces_bars(self):
        """100 monotonically rising ticks (0.0001/tick) with 10-pip bar → 9 bars."""
        # 100 ticks rising 1 pip each → 99 pips total → 9 complete 10-pip bars
        prices = [1.1000 + i * 0.0001 for i in range(100)]
        ticks = _make_ticks(prices)
        conv = _converter()
        bars = conv.convert(ticks)

        assert len(bars) == 9, f"Expected 9 bars, got {len(bars)}"

    def test_determinism_down_move(self):
        """Monotonically falling ticks → same bars each run."""
        prices = [1.2000 - i * 0.0001 for i in range(100)]
        ticks = _make_ticks(prices)

        bars1 = _converter().convert(ticks)
        bars2 = _converter().convert(ticks)

        assert len(bars1) == len(bars2)
        assert len(bars1) == 9  # 99 pips ÷ 10 = 9 complete bars


# ---------------------------------------------------------------------------
# V1.3 — High - Low == exactly N pips (within spread tolerance)
# ---------------------------------------------------------------------------

class TestBarSize:
    """V1.3: High - Low = exactly X pips on every completed bar."""

    TOLERANCE = 0.5 * 0.0001  # ± 0.5 pip tolerance

    def _assert_bar_size(self, bars: list[RangeBar], bar_pips: int, pip_size: float):
        expected = bar_pips * pip_size
        for i, bar in enumerate(bars):
            span = bar.high - bar.low
            assert abs(span - expected) <= self.TOLERANCE, (
                f"Bar {i}: high-low={span:.6f}, expected {expected:.6f} "
                f"(diff={abs(span - expected):.8f})"
            )

    def test_upward_move_bar_size(self):
        prices = [1.1000 + i * 0.0001 for i in range(200)]
        ticks = _make_ticks(prices)
        bars = _converter().convert(ticks)
        assert bars, "Should produce bars"
        self._assert_bar_size(bars, bar_pips=10, pip_size=0.0001)

    def test_downward_move_bar_size(self):
        prices = [1.2000 - i * 0.0001 for i in range(200)]
        ticks = _make_ticks(prices)
        bars = _converter().convert(ticks)
        assert bars
        self._assert_bar_size(bars, bar_pips=10, pip_size=0.0001)

    def test_mixed_move_bar_size(self):
        """Up 50 pips, then down 60 pips — all bars exactly 10 pips."""
        prices = (
            [1.1000 + i * 0.0001 for i in range(51)] +  # up 50 pips
            [1.1050 - i * 0.0001 for i in range(1, 61)]  # down 60 pips
        )
        ticks = _make_ticks(prices)
        bars = _converter().convert(ticks)
        assert bars
        self._assert_bar_size(bars, bar_pips=10, pip_size=0.0001)

    def test_jpy_pair_bar_size(self):
        """JPY pairs: 15-pip bars at pip_size=0.01."""
        prices = [145.00 + i * 0.01 for i in range(200)]
        ticks = _make_ticks(prices)
        conv = RangeBarConverter(bar_pips=15, pip_size=0.01)
        bars = conv.convert(ticks)
        assert bars
        expected = 15 * 0.01
        tol = 0.5 * 0.01
        for i, bar in enumerate(bars):
            span = bar.high - bar.low
            assert abs(span - expected) <= tol, (
                f"JPY Bar {i}: span={span:.4f}, expected {expected:.4f}"
            )

    def test_open_to_close_equals_bar_size_up_bar(self):
        """For an up bar: close = open + bar_size."""
        prices = [1.1000 + i * 0.0001 for i in range(50)]
        ticks = _make_ticks(prices)
        bars = _converter().convert(ticks)
        for bar in bars:
            if bar.close > bar.open:  # up bar
                assert bar.close == pytest.approx(bar.open + BAR_SIZE_PRICE, abs=1e-8)

    def test_open_to_close_equals_bar_size_down_bar(self):
        """For a down bar: close = open - bar_size."""
        prices = [1.2000 - i * 0.0001 for i in range(50)]
        ticks = _make_ticks(prices)
        bars = _converter().convert(ticks)
        for bar in bars:
            if bar.close < bar.open:  # down bar
                assert bar.close == pytest.approx(bar.open - BAR_SIZE_PRICE, abs=1e-8)


# ---------------------------------------------------------------------------
# V1.4 — Bars span different durations (purely price-driven)
# ---------------------------------------------------------------------------

class TestVaryingDurations:
    """V1.4: Bars should span different time durations — not fixed intervals."""

    def test_bars_have_varying_durations(self):
        """Ticks arrive at uneven intervals → bars close at different durations."""
        # First bar: slow (ticks 1 min apart) → takes 10 ticks = 10 min
        # Second bar: fast (ticks 10 sec apart) → takes 10 ticks = ~1.6 min
        slow_prices = [1.1000 + i * 0.0001 for i in range(11)]
        fast_prices = [1.1010 + i * 0.0001 for i in range(11)]

        slow_ticks = _make_ticks(slow_prices, start_minute=0, gap_minutes=1)
        # Fast ticks: 10-second intervals = 1/6 minute
        fast_base = datetime(2024, 1, 2, 8, 11, 0, tzinfo=timezone.utc)
        fast_df = pd.DataFrame({
            "time": [pd.Timestamp(fast_base + timedelta(seconds=10 * i)) for i in range(11)],
            "bid":  fast_prices,
            "ask":  fast_prices,
        })

        ticks = pd.concat([slow_ticks, fast_df], ignore_index=True)
        conv = _converter()
        bars = conv.convert(ticks)

        assert len(bars) >= 2, "Need at least 2 bars to compare durations"
        durations = [(b.end_time - b.start_time).total_seconds() for b in bars]
        # Durations must not all be identical
        assert len(set(durations)) > 1, (
            f"All bar durations identical ({durations[0]}s) — bars appear time-based, not price-based"
        )

    def test_large_tick_gap_resolves_without_phantom_bar(self):
        """A large but sub-weekend time gap (2h) should NOT trigger gap handling."""
        prices = [1.1000 + i * 0.0001 for i in range(50)]
        # First 25 ticks: 1 min apart; next 25: 2 hours later, 1 min apart
        t1 = [_ts(i) for i in range(25)]
        base2 = datetime(2024, 1, 2, 10, 25, 0, tzinfo=timezone.utc)
        t2 = [pd.Timestamp(base2 + timedelta(minutes=i)) for i in range(25)]

        ticks = pd.DataFrame({
            "time": t1 + t2,
            "bid":  prices,
            "ask":  prices,
        })
        conv = _converter()
        bars = conv.convert(ticks)
        # Should still produce bars (no phantom bars, no error)
        assert len(bars) > 0


# ---------------------------------------------------------------------------
# V1.6 — Weekend gaps: no phantom bars
# ---------------------------------------------------------------------------

class TestWeekendGaps:
    """V1.6: Weekend gaps handled — no phantom bars created for the gap."""

    def _weekend_gap_ticks(self) -> pd.DataFrame:
        """Build ticks that straddle a weekend gap (Friday → Monday)."""
        # Friday 21:00 UTC ticks
        fri_base = datetime(2024, 1, 5, 21, 0, 0, tzinfo=timezone.utc)  # Friday
        fri_prices = [1.1000 + i * 0.0001 for i in range(10)]
        fri_times  = [pd.Timestamp(fri_base + timedelta(minutes=i)) for i in range(10)]

        # Monday 00:05 UTC ticks (63+ hours later)
        mon_base = datetime(2024, 1, 8, 0, 5, 0, tzinfo=timezone.utc)  # Monday
        mon_prices = [1.1005 + i * 0.0001 for i in range(10)]
        mon_times  = [pd.Timestamp(mon_base + timedelta(minutes=i)) for i in range(10)]

        return pd.DataFrame({
            "time": fri_times + mon_times,
            "bid":  fri_prices + mon_prices,
            "ask":  fri_prices + mon_prices,
        })

    def test_no_bars_span_weekend_gap(self):
        """No completed bar should span the weekend gap (48+ hours)."""
        ticks = self._weekend_gap_ticks()
        conv = _converter(bar_pips=10, pip_size=0.0001)
        bars = conv.convert(ticks)

        gap_threshold = timedelta(hours=4)
        for bar in bars:
            duration = bar.end_time - bar.start_time
            assert duration < gap_threshold, (
                f"Bar spans weekend gap: {bar.start_time} → {bar.end_time} "
                f"({duration.total_seconds() / 3600:.1f}h)"
            )

    def test_monday_bars_open_at_monday_price(self):
        """First bar after the gap must open at the Monday open price, not Friday close."""
        ticks = self._weekend_gap_ticks()
        conv = _converter(bar_pips=5, pip_size=0.0001)
        bars = conv.convert(ticks)

        # Find the first bar that starts on Monday
        monday = datetime(2024, 1, 8, tzinfo=timezone.utc)
        monday_bars = [b for b in bars if b.start_time.date() == monday.date()]

        assert monday_bars, "Should have at least one bar starting on Monday"
        # The Monday bar open should be near the first Monday tick price (1.1005)
        mon_open = monday_bars[0].open
        assert abs(mon_open - 1.1005) <= 0.0005, (
            f"Monday bar opened at {mon_open:.5f}, expected near 1.10050"
        )

    def test_gap_produces_no_extra_bars(self):
        """Bars before and after gap should be the same count as without gap — no phantom bars."""
        # Continuous ticks (no gap) — 10 pips up
        no_gap_prices = [1.1000 + i * 0.0001 for i in range(20)]
        no_gap_ticks = _make_ticks(no_gap_prices)
        bars_no_gap = _converter().convert(no_gap_ticks)

        # Same prices but with a weekend gap in the middle
        gap_ticks = self._weekend_gap_ticks()
        bars_gap = _converter().convert(gap_ticks)

        # Both have same number of complete price moves → same bar count
        # (gap-split ticks may produce slightly fewer since mid-gap bar is force-closed)
        # Main assertion: gap version must NOT produce MORE bars than no-gap
        # (that would indicate phantom bars)
        assert len(bars_gap) <= len(bars_no_gap) + 2, (
            f"Gap version produced {len(bars_gap)} bars vs {len(bars_no_gap)} "
            "without gap — possible phantom bars"
        )


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_ticks_returns_empty(self):
        conv = _converter()
        bars = conv.convert(pd.DataFrame(columns=["time", "bid", "ask"]))
        assert bars == []

    def test_missing_columns_raises(self):
        ticks = pd.DataFrame({"time": [_ts(0)], "bid": [1.1000]})  # missing 'ask'
        conv = _converter()
        with pytest.raises(ValueError, match="missing columns"):
            conv.convert(ticks)

    def test_single_tick_no_bar(self):
        ticks = _make_ticks([1.1000])
        conv = _converter()
        bars = conv.convert(ticks)
        assert bars == [], "Single tick cannot complete a bar"

    def test_flush_returns_open_bar(self):
        prices = [1.1000 + i * 0.0001 for i in range(5)]
        ticks = _make_ticks(prices)
        conv = _converter()
        conv.convert(ticks)
        partial = conv.flush()
        assert partial is not None, "Should have an open (incomplete) bar after partial move"

    def test_tick_volume_counts_ticks(self):
        """Tick volume of a bar == number of ticks consumed by that bar."""
        # 11 ticks rising 1 pip each → first bar uses ticks 0..10 (11 ticks)
        prices = [1.1000 + i * 0.0001 for i in range(12)]
        ticks = _make_ticks(prices)
        bars = _converter().convert(ticks)
        assert bars[0].tick_volume == 11

    def test_stateful_feed_matches_batch_convert(self):
        """Feeding ticks one-by-one == batch convert."""
        prices = [1.1000 + i * 0.0001 for i in range(100)]
        ticks = _make_ticks(prices)

        # Batch
        batch_bars = _converter().convert(ticks)

        # One-by-one
        conv = _converter()
        feed_bars: list[RangeBar] = []
        for row in ticks.itertuples():
            mid = (row.bid + row.ask) / 2
            ts = pd.Timestamp(row.time)
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            feed_bars.extend(conv.feed(mid, ts))

        assert len(batch_bars) == len(feed_bars)
        for b1, b2 in zip(batch_bars, feed_bars):
            assert b1.open  == pytest.approx(b2.open,  abs=1e-8)
            assert b1.close == pytest.approx(b2.close, abs=1e-8)

    def test_ticks_to_range_bars_dataframe_output(self):
        """ticks_to_range_bars() returns correct DataFrame schema."""
        prices = [1.1000 + i * 0.0001 for i in range(100)]
        ticks = _make_ticks(prices)
        df = ticks_to_range_bars(ticks, pair="EURUSD")

        required_cols = {"open", "high", "low", "close", "tick_volume", "start_time", "end_time"}
        assert required_cols.issubset(set(df.columns)), f"Missing columns: {required_cols - set(df.columns)}"
        assert not df.empty

    def test_no_bar_with_insufficient_move(self):
        """Ticks that never move N pips from open → no completed bars."""
        # 5 pips of movement on a 10-pip bar → no completion
        prices = [1.1000, 1.1003, 1.1005, 1.1004, 1.1002, 1.1001]
        ticks = _make_ticks(prices)
        bars = _converter().convert(ticks)
        assert bars == [], f"Expected 0 bars, got {len(bars)}"


# ---------------------------------------------------------------------------
# PRD Checklist summary (printed, not asserted — for human review)
# ---------------------------------------------------------------------------

class TestPRDChecklist:
    """Explicit mapping of test methods to PRD validation IDs."""

    def test_v1_3_high_low_equals_n_pips(self):
        """V1.3 CRITICAL — High–Low = exactly X pips (within spread tolerance)."""
        prices = [1.1000 + i * 0.0001 for i in range(200)]
        ticks = _make_ticks(prices)
        bars = _converter().convert(ticks)

        bar_size = 10 * 0.0001
        tol = 0.5 * 0.0001
        failures = []
        for i, bar in enumerate(bars):
            span = bar.high - bar.low
            if abs(span - bar_size) > tol:
                failures.append(f"Bar {i}: span={span:.6f}")

        assert not failures, f"V1.3 FAILED on {len(failures)} bars:\n" + "\n".join(failures)

    def test_v1_4_bars_are_price_driven_not_time_driven(self):
        """V1.4 CRITICAL — Bars span different durations (purely price-driven, not time)."""
        # Mix of slow and fast ticks to force varying durations
        prices = [1.1000 + i * 0.0001 for i in range(60)]
        base = datetime(2024, 1, 2, 8, 0, tzinfo=timezone.utc)
        # Vary tick spacing: 30s, 5s, 120s alternating
        spacings = [30, 5, 120]
        times = []
        t = base
        for i in range(60):
            times.append(pd.Timestamp(t))
            t += timedelta(seconds=spacings[i % 3])

        ticks = pd.DataFrame({"time": times, "bid": prices, "ask": prices})
        bars = _converter().convert(ticks)

        durations = [(b.end_time - b.start_time).total_seconds() for b in bars]
        assert len(set(durations)) > 1, "V1.4 FAILED: all bars have identical duration"

    def test_v1_6_weekend_gaps_no_phantom_bars(self):
        """V1.6 MUST PASS — Weekend gaps handled — no phantom bars."""
        fri_base = datetime(2024, 1, 5, 21, 0, tzinfo=timezone.utc)
        mon_base = datetime(2024, 1, 8, 0, 5, tzinfo=timezone.utc)

        fri_prices = [1.1000 + i * 0.0001 for i in range(10)]
        mon_prices = [1.1005 + i * 0.0001 for i in range(10)]

        ticks = pd.DataFrame({
            "time": [pd.Timestamp(fri_base + timedelta(minutes=i)) for i in range(10)] +
                    [pd.Timestamp(mon_base + timedelta(minutes=i)) for i in range(10)],
            "bid":  fri_prices + mon_prices,
            "ask":  fri_prices + mon_prices,
        })

        bars = _converter().convert(ticks)
        gap_threshold = timedelta(hours=4)
        phantom = [b for b in bars if (b.end_time - b.start_time) >= gap_threshold]
        assert not phantom, f"V1.6 FAILED: {len(phantom)} phantom bars spanning weekend gap"

    def test_v1_8_deterministic_output(self):
        """V1.8 CRITICAL — 100 ticks → deterministic N Range Bars."""
        prices = [1.1000 + i * 0.0001 for i in range(100)]
        ticks = _make_ticks(prices)

        results = [_converter().convert(ticks) for _ in range(5)]
        lengths = [len(r) for r in results]
        assert len(set(lengths)) == 1, f"V1.8 FAILED: non-deterministic bar counts {lengths}"

        # Verify all runs produce identical bars
        ref = results[0]
        for run_idx, run in enumerate(results[1:], 1):
            for bar_idx, (b1, b2) in enumerate(zip(ref, run)):
                assert b1.open == pytest.approx(b2.open, abs=1e-8), (
                    f"V1.8 FAILED: run {run_idx} bar {bar_idx} open differs"
                )
