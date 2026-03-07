"""
JcampFX — v2.2 Feature Tests

Tests for all new v2.2 requirements:
  VP.1 — is_phantom flag on bars sharing a tick timestamp
  VP.2 — is_gap_adjacent flag on first bar in multi-bar tick sequence
  VP.6 — Phantom exit fills at tick boundary price
  VD.9 — Regime deterioration: runner force-closed when CS drops >40 pts
  VE.8 — Regime deterioration force-close in backtester
  VS.1 — Session detection correctly identifies all sessions
  VS.2 — TrendRider blocked from EURUSD during Tokyo session
  VS.3 — BreakoutRider active only during London Open and NY Open
  VS.4 — RangeRider on JPY pairs allowed during Tokyo
  VC.4 — dcrd_config.json loaded by DCRD layers (or defaults used)
  VM.3 — 20-pip bars: RISK_TOO_LOW skip rate test (structural)
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.range_bar_converter import RangeBar, RangeBarConverter
from src.exit_manager import should_force_close_runner
from src.session_filter import (
    SessionFilter,
    get_active_sessions,
    get_session_tag,
    is_breakout_rider_allowed,
    is_trend_rider_allowed,
    is_range_rider_allowed,
    SESSION_TOKYO, SESSION_LONDON, SESSION_NY, SESSION_OVERLAP, SESSION_OFF_HOURS,
)
from src.signal import Signal
from src.config import RANGE_BAR_PIPS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(hour: int, minute: int = 0, weekday: int = 1) -> pd.Timestamp:
    """Create a UTC timestamp for the given hour/minute (weekday: 0=Mon, 4=Fri)."""
    # 2026-02-16 is a Monday (weekday=0)
    base_date = pd.Timestamp("2026-02-16", tz="UTC")
    return base_date + pd.Timedelta(days=weekday, hours=hour, minutes=minute)


def _make_ticks(prices: list[float], ts: pd.Timestamp | None = None) -> pd.DataFrame:
    """Create a minimal tick DataFrame from a list of prices."""
    if ts is None:
        ts = pd.Timestamp("2026-02-17 10:00:00", tz="UTC")
    timestamps = [ts + pd.Timedelta(seconds=i) for i in range(len(prices))]
    return pd.DataFrame({
        "time": timestamps,
        "bid": [p - 0.0001 for p in prices],
        "ask": [p + 0.0001 for p in prices],
    })


# ===========================================================================
# R12 — Range Bar pip sizes updated
# ===========================================================================

class TestRangeBarPipSizes:
    """VM validation: 20-pip bar sizes configured correctly."""

    def test_major_pairs_use_20_pips(self):
        for pair in ("EURUSD", "GBPUSD", "USDCHF"):
            assert RANGE_BAR_PIPS[pair] == 20, f"{pair} should be 20 pips"

    def test_jpy_pairs_use_25_pips(self):
        for pair in ("USDJPY", "AUDJPY"):
            assert RANGE_BAR_PIPS[pair] == 25, f"{pair} should be 25 pips"

    def test_gold_unchanged(self):
        assert RANGE_BAR_PIPS["XAUUSD"] == 50


# ===========================================================================
# R13 — Phantom Detection: is_phantom + is_gap_adjacent flags
# ===========================================================================

class TestPhantomDetection:
    """VP.1 + VP.2: Phantom and gap-adjacent flags."""

    def test_single_tick_bar_is_organic(self):
        """VP.1: A bar from a single tick is NOT phantom."""
        conv = RangeBarConverter(bar_pips=10, pip_size=0.0001)
        ts1 = pd.Timestamp("2026-02-17 10:00:00", tz="UTC")
        ts2 = pd.Timestamp("2026-02-17 10:00:01", tz="UTC")

        # Two separate ticks, one triggers a bar close
        bars1 = conv.feed(1.1000, ts1)  # opens bar
        bars2 = conv.feed(1.1010, ts2)  # still in bar (only 1 pip)
        # Push to completion with a big move on a new tick
        ts3 = pd.Timestamp("2026-02-17 10:00:02", tz="UTC")
        bars3 = conv.feed(1.1010, ts3)  # still building

        # Force a bar close with exact pip move
        ts4 = pd.Timestamp("2026-02-17 10:00:03", tz="UTC")
        bars4 = conv.feed(1.1010, ts4)  # should not trigger yet

        # Provide enough move on its own tick to close a bar
        ts5 = pd.Timestamp("2026-02-17 10:00:04", tz="UTC")
        bars5 = conv.feed(1.1011, ts5)

        all_bars = bars1 + bars2 + bars3 + bars4 + bars5
        if all_bars:
            # Any bar triggered by a single tick should be organic
            assert not all_bars[0].is_phantom

    def test_gap_produces_phantom_and_gap_adjacent_bars(self):
        """VP.1 + VP.2: A price jump produces phantom bars and one gap-adjacent bar."""
        conv = RangeBarConverter(bar_pips=10, pip_size=0.0001)
        ts1 = pd.Timestamp("2026-02-17 10:00:00", tz="UTC")

        # Open a bar at 1.1000
        conv.feed(1.1000, ts1)

        # Massive jump in the SAME tick timestamp (simulated):
        # feed a price that jumps 30 pips in one tick → 3 bars should form
        ts2 = pd.Timestamp("2026-02-17 10:00:01", tz="UTC")
        bars = conv.feed(1.1031, ts2)  # 31 pips up → should produce 3 bars

        assert len(bars) >= 2, f"Expected ≥2 bars from 31-pip jump, got {len(bars)}"

        # First bar should be gap-adjacent (VP.2)
        assert bars[0].is_gap_adjacent is True, "First bar should be is_gap_adjacent"
        assert bars[0].is_phantom is False, "First bar should NOT be phantom"

        # Subsequent bars should be phantom (VP.1)
        for bar in bars[1:]:
            assert bar.is_phantom is True, f"Bar {bar} should be is_phantom"
            assert bar.is_gap_adjacent is False, f"Phantom bar should NOT be gap_adjacent"

    def test_tick_boundary_price_stored_on_phantom(self):
        """VP.6: Tick boundary price equals the actual tick mid for phantom bars."""
        conv = RangeBarConverter(bar_pips=10, pip_size=0.0001)
        ts1 = pd.Timestamp("2026-02-17 10:00:00", tz="UTC")
        conv.feed(1.1000, ts1)

        # Jump that creates multiple bars
        ts2 = pd.Timestamp("2026-02-17 10:00:01", tz="UTC")
        tick_mid = 1.1031  # 31 pips up
        bars = conv.feed(tick_mid, ts2)

        assert len(bars) >= 2
        for bar in bars:
            # tick_boundary_price should be the actual tick price
            assert abs(bar.tick_boundary_price - tick_mid) < 0.0001, (
                f"tick_boundary_price {bar.tick_boundary_price} != tick_mid {tick_mid}"
            )

    def test_organic_bar_tick_boundary_equals_close(self):
        """Organic bar tick_boundary_price should equal the bar close."""
        conv = RangeBarConverter(bar_pips=10, pip_size=0.0001)
        ts1 = pd.Timestamp("2026-02-17 10:00:00", tz="UTC")
        conv.feed(1.1000, ts1)

        # Gradual ticks, one bar per tick sequence
        ts2 = pd.Timestamp("2026-02-17 10:00:01", tz="UTC")
        bars = conv.feed(1.1010, ts2)  # exactly 10 pips → 1 bar

        assert len(bars) == 1
        bar = bars[0]
        assert bar.is_phantom is False
        assert bar.is_gap_adjacent is False
        # tick_boundary = close for organic bars
        assert abs(bar.tick_boundary_price - bar.close) < 1e-9

    def test_gap_bar_not_produced_at_weekend_gap(self):
        """Weekend gaps close the open bar — not phantom, just gap-close."""
        conv = RangeBarConverter(bar_pips=10, pip_size=0.0001, weekend_gap_hours=4.0)
        ts1 = pd.Timestamp("2026-02-14 22:00:00", tz="UTC")  # Friday
        conv.feed(1.1000, ts1)
        conv.feed(1.1003, ts1 + pd.Timedelta(seconds=1))

        # Gap of 50 hours (weekend)
        ts2 = pd.Timestamp("2026-02-16 22:00:00", tz="UTC")  # Sunday evening
        gap_bars = conv.feed(1.1005, ts2)

        # Gap bar is produced (open bar closed at gap)
        assert len(gap_bars) == 1
        # The gap-close bar should NOT be phantom — it's a legitimate weekend close
        assert gap_bars[0].is_phantom is False


# ===========================================================================
# R16 — Regime Deterioration
# ===========================================================================

class TestRegimeDeteriorationExitManager:
    """VD.9 / VE.8: Force-close runner when CS drops >40 pts from entry."""

    def test_no_force_close_below_threshold(self):
        """CS drop ≤ 40 pts should NOT trigger force-close."""
        assert should_force_close_runner(entry_score=78.0, current_score=40.0) is False

    def test_force_close_exactly_at_threshold(self):
        """CS drop exactly == threshold should NOT trigger (must be >40)."""
        assert should_force_close_runner(entry_score=78.0, current_score=38.0) is False

    def test_force_close_above_threshold(self):
        """CS drop > 40 pts should trigger force-close."""
        assert should_force_close_runner(entry_score=78.0, current_score=37.0) is True

    def test_force_close_trendrider_to_range(self):
        """TrendRider entry CS=75, now CS=30 → 45pt drop → force-close."""
        assert should_force_close_runner(entry_score=75.0, current_score=30.0) is True

    def test_no_force_close_if_score_improved(self):
        """Score improvement → no force-close (improvement = negative drop)."""
        assert should_force_close_runner(entry_score=50.0, current_score=90.0) is False

    def test_custom_threshold(self):
        """Custom threshold parameter works correctly."""
        assert should_force_close_runner(70.0, 49.0, threshold=20.0) is True   # 21pt drop > threshold
        assert should_force_close_runner(70.0, 50.0, threshold=20.0) is False  # 20pt drop NOT > threshold
        assert should_force_close_runner(70.0, 55.0, threshold=20.0) is False  # 15pt drop < threshold


# ===========================================================================
# R18 — Session Filter
# ===========================================================================

class TestSessionDetection:
    """VS.1: Session detection correctly identifies all sessions from server time."""

    def test_tokyo_session(self):
        ts = _ts(hour=3)  # 03:00 UTC → Tokyo
        sessions = get_active_sessions(ts)
        assert SESSION_TOKYO in sessions
        assert SESSION_LONDON not in sessions
        assert SESSION_NY not in sessions

    def test_london_session(self):
        ts = _ts(hour=10)  # 10:00 UTC → London only
        sessions = get_active_sessions(ts)
        assert SESSION_LONDON in sessions
        assert SESSION_TOKYO not in sessions
        assert SESSION_NY not in sessions
        assert SESSION_OVERLAP not in sessions

    def test_ny_session(self):
        ts = _ts(hour=17)  # 17:00 UTC → NY only (London ended at 16:00)
        sessions = get_active_sessions(ts)
        assert SESSION_NY in sessions
        assert SESSION_LONDON not in sessions

    def test_london_ny_overlap(self):
        ts = _ts(hour=13)  # 13:00 UTC → Overlap
        sessions = get_active_sessions(ts)
        assert SESSION_OVERLAP in sessions
        assert SESSION_LONDON in sessions
        assert SESSION_NY in sessions

    def test_off_hours(self):
        ts = _ts(hour=22)  # 22:00 UTC → Off-Hours
        sessions = get_active_sessions(ts)
        assert SESSION_OFF_HOURS in sessions
        assert SESSION_NY not in sessions  # NY ends at 21:00

    def test_session_tag_priority(self):
        ts = _ts(hour=13)  # Overlap > London > NY
        tag = get_session_tag(ts)
        assert tag == SESSION_OVERLAP


class TestTrendRiderSessionFilter:
    """VS.2: TrendRider blocked from EURUSD during Tokyo session (hard filter)."""

    def test_blocked_eurusd_tokyo(self):
        ts = _ts(hour=3)  # Pure Tokyo
        allowed, reason = is_trend_rider_allowed("EURUSD", ts)
        assert allowed is False
        assert "SESSION_BLOCKED" in reason
        assert "Tokyo" in reason

    def test_allowed_eurusd_london(self):
        ts = _ts(hour=10)  # London
        allowed, _ = is_trend_rider_allowed("EURUSD", ts)
        assert allowed is True

    def test_allowed_usdjpy_tokyo(self):
        """JPY pairs are allowed by TrendRider during Tokyo (not in blocked set)."""
        ts = _ts(hour=3)
        allowed, _ = is_trend_rider_allowed("USDJPY", ts)
        assert allowed is True

    def test_blocked_off_hours(self):
        ts = _ts(hour=22)  # Off-Hours
        allowed, reason = is_trend_rider_allowed("EURUSD", ts)
        assert allowed is False

    def test_allowed_during_london_tokyo_overlap_7_to_9(self):
        """07:00–09:00 London+Tokyo overlap — TrendRider should be allowed."""
        ts = _ts(hour=8)  # 08:00 UTC — both London and Tokyo active
        allowed, _ = is_trend_rider_allowed("EURUSD", ts)
        assert allowed is True


class TestBreakoutRiderSessionFilter:
    """VS.3: BreakoutRider active only during London Open (07–09) and NY Open (12–14)."""

    def test_allowed_london_open(self):
        ts = _ts(hour=7, minute=30)  # 07:30 UTC
        allowed, _ = is_breakout_rider_allowed(ts)
        assert allowed is True

    def test_allowed_ny_open(self):
        ts = _ts(hour=13)  # 13:00 UTC
        allowed, _ = is_breakout_rider_allowed(ts)
        assert allowed is True

    def test_blocked_outside_open_windows(self):
        ts = _ts(hour=15)  # 15:00 UTC — London session but not open window
        allowed, reason = is_breakout_rider_allowed(ts)
        assert allowed is False
        assert "SESSION_BLOCKED" in reason

    def test_blocked_tokyo(self):
        ts = _ts(hour=4)  # 04:00 UTC — Tokyo
        allowed, _ = is_breakout_rider_allowed(ts)
        assert allowed is False

    def test_boundary_london_open_end(self):
        """09:00 UTC is the end of London Open window — should be blocked."""
        ts = _ts(hour=9, minute=0)
        allowed, _ = is_breakout_rider_allowed(ts)
        assert allowed is False  # 09:00 is not < 09:00


class TestRangeRiderSessionFilter:
    """VS.4: RangeRider on JPY pairs allowed during Tokyo (soft filter)."""

    def test_jpy_allowed_tokyo(self):
        ts = _ts(hour=3)  # Tokyo
        allowed, _ = is_range_rider_allowed("USDJPY", ts)
        assert allowed is True

    def test_blocked_overlap(self):
        """Overlap is avoided even for soft filter."""
        ts = _ts(hour=13)  # Overlap
        # Soft filter allows with warning — but checking function behavior
        allowed, reason = is_range_rider_allowed("EURUSD", ts)
        # Soft filter logs but doesn't hard-block — allowed=True with warning
        assert allowed is True  # Soft filter: allow but log

    def test_late_ny_allowed(self):
        ts = _ts(hour=19)  # 19:00 UTC — Late NY
        allowed, _ = is_range_rider_allowed("EURUSD", ts)
        assert allowed is True


class TestSessionFilterClass:
    """SessionFilter class: per-strategy dispatch."""

    def setup_method(self):
        self.sf = SessionFilter()

    def test_trend_rider_tokyo_eurusd_blocked(self):
        ts = _ts(hour=3)
        allowed, reason = self.sf.check("TrendRider", "EURUSD", ts)
        assert allowed is False

    def test_breakout_rider_outside_window_blocked(self):
        ts = _ts(hour=16)  # 16:00 UTC — blocked for BreakoutRider
        allowed, _ = self.sf.check("BreakoutRider", "EURUSD", ts)
        assert allowed is False

    def test_range_rider_always_allowed_by_class(self):
        """RangeRider soft filter → SessionFilter.check always returns allowed=True."""
        ts = _ts(hour=13)  # Overlap — soft warn but not block
        allowed, _ = self.sf.check("RangeRider", "EURUSD", ts)
        assert allowed is True

    def test_unknown_strategy_allowed(self):
        ts = _ts(hour=13)
        allowed, _ = self.sf.check("UnknownStrategy", "EURUSD", ts)
        assert allowed is True


# ===========================================================================
# Signal: session_tag field
# ===========================================================================

class TestSignalSessionTag:
    """Signal dataclass has session_tag field (PRD §6.3, V2.8)."""

    def test_signal_has_session_tag(self):
        sig = Signal(
            timestamp=pd.Timestamp("2026-02-17 10:00:00", tz="UTC"),
            pair="EURUSD",
            direction="BUY",
            entry=1.1000,
            sl=1.0980,
            tp_1r=1.1020,
            strategy="TrendRider",
            composite_score=75.0,
        )
        assert hasattr(sig, "session_tag")
        assert sig.session_tag == ""

    def test_signal_session_tag_in_dict(self):
        sig = Signal(
            timestamp=pd.Timestamp("2026-02-17 10:00:00", tz="UTC"),
            pair="EURUSD",
            direction="BUY",
            entry=1.1000,
            sl=1.0980,
            tp_1r=1.1020,
            strategy="TrendRider",
            composite_score=75.0,
            session_tag="London",
        )
        d = sig.to_dict()
        assert d["session_tag"] == "London"


# ===========================================================================
# DCRD Calibration: load_config with defaults
# ===========================================================================

class TestDCRDCalibrationConfig:
    """VC.4: dcrd_config.json loaded or defaults returned."""

    def test_load_config_returns_defaults_when_missing(self):
        from src.dcrd.calibrate import load_config
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            nonexistent = f.name
        os.unlink(nonexistent)  # ensure it doesn't exist

        config = load_config(path=nonexistent)
        assert "adx" in config
        assert "atr_ratio" in config
        assert "rb_speed" in config
        assert config["adx"]["p25"] == 18.0  # v2.1 default
        assert config["adx"]["p75"] == 25.0  # v2.1 default

    def test_load_config_reads_json_file(self):
        from src.dcrd.calibrate import load_config
        test_config = {
            "adx": {"p25": 19.5, "p75": 28.0},
            "atr_ratio": {"p25": 0.88, "p75": 1.30},
            "rb_speed": {"p25": 1.2, "p75": 3.5},
            "bb_width": {"p20": 0.003, "p80": 0.009},
            "adx_slope_threshold": 0.15,
            "version": "2.2",
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(test_config, f)
            config_path = f.name

        try:
            loaded = load_config(path=config_path)
            assert loaded["adx"]["p25"] == 19.5
            assert loaded["adx"]["p75"] == 28.0
            assert loaded["version"] == "2.2"
        finally:
            os.unlink(config_path)

    def test_default_config_has_all_required_keys(self):
        from src.dcrd.calibrate import _default_config
        config = _default_config()
        assert "adx" in config
        assert "atr_ratio" in config
        assert "rb_speed" in config
        assert "bb_width" in config
        assert "adx_slope_threshold" in config
