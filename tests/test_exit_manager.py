"""
Phase 2 Unit Tests — Exit Manager
PRD §5 validation items: VE.1–VE.7

Run:
    pytest tests/test_exit_manager.py -v
"""

from __future__ import annotations

import pytest

from src.exit_manager import (
    calculate_1_5r_price,
    calculate_r_multiple,
    expected_locked_profit_r,
    get_partial_exit_pct,
    initial_chandelier_sl,
    is_at_1_5r,
    is_chandelier_hit,
    update_chandelier,
)


# ---------------------------------------------------------------------------
# VE.1 — Partial exit fires at exactly 1.5R
# ---------------------------------------------------------------------------

class TestPartialExitTrigger:
    """VE.1: Partial exit fires at exactly 1.5R on > 95% of qualifying trades."""

    def test_1_5r_price_buy(self):
        """BUY: entry=1.1000, SL=1.0900 → 1R=100 pips → 1.5R target=1.1150"""
        target = calculate_1_5r_price(entry=1.1000, sl=1.0900, direction="BUY")
        assert target == pytest.approx(1.1150, abs=1e-8)

    def test_1_5r_price_sell(self):
        """SELL: entry=1.1000, SL=1.1100 → 1R=100 pips → 1.5R target=1.0850"""
        target = calculate_1_5r_price(entry=1.1000, sl=1.1100, direction="SELL")
        assert target == pytest.approx(1.0850, abs=1e-8)

    def test_is_at_1_5r_buy_exact(self):
        assert is_at_1_5r(1.1150, entry=1.1000, sl=1.0900, direction="BUY") is True

    def test_is_at_1_5r_buy_exceeded(self):
        assert is_at_1_5r(1.1200, entry=1.1000, sl=1.0900, direction="BUY") is True

    def test_is_at_1_5r_buy_not_reached(self):
        assert is_at_1_5r(1.1100, entry=1.1000, sl=1.0900, direction="BUY") is False

    def test_is_at_1_5r_sell_exact(self):
        assert is_at_1_5r(1.0850, entry=1.1000, sl=1.1100, direction="SELL") is True

    def test_is_at_1_5r_sell_not_reached(self):
        assert is_at_1_5r(1.0900, entry=1.1000, sl=1.1100, direction="SELL") is False


# ---------------------------------------------------------------------------
# VE.2 — Regime-aware split: all 4 tiers correct
# ---------------------------------------------------------------------------

class TestPartialExitPct:
    """VE.2: 60% (CS>85), 70% (CS 70–85), 75% (CS 30–70), 80% (CS<30)."""

    def test_deep_trending_60pct(self):
        """CS > 85 → close 60%, keep 40% runner."""
        assert get_partial_exit_pct(90) == pytest.approx(0.60)
        assert get_partial_exit_pct(86) == pytest.approx(0.60)

    def test_trending_70pct(self):
        """CS 70–85 → close 70%, keep 30% runner."""
        assert get_partial_exit_pct(80) == pytest.approx(0.70)
        assert get_partial_exit_pct(70) == pytest.approx(0.70)

    def test_transitional_75pct(self):
        """CS 30–70 → close 75%, keep 25% runner."""
        assert get_partial_exit_pct(50) == pytest.approx(0.75)
        assert get_partial_exit_pct(30) == pytest.approx(0.75)

    def test_range_80pct(self):
        """CS < 30 → close 80%, keep 20% runner."""
        assert get_partial_exit_pct(20) == pytest.approx(0.80)
        assert get_partial_exit_pct(0) == pytest.approx(0.80)

    def test_boundary_85(self):
        """CS = 85 is NOT > 85, so should be in the 70–85 tier → 70%."""
        assert get_partial_exit_pct(85) == pytest.approx(0.70)

    def test_all_4_tiers_covered(self):
        tiers_found = {get_partial_exit_pct(cs) for cs in [90, 75, 50, 15]}
        assert tiers_found == {0.60, 0.70, 0.75, 0.80}


# ---------------------------------------------------------------------------
# VE.3 — Chandelier = max(0.5R, ATR14) with pip floors
# ---------------------------------------------------------------------------

class TestChandelierFormula:
    """VE.3: Chandelier SL = max(0.5R, ATR14) with floor ≥15 pips majors / ≥25 pips JPY."""

    def test_half_r_dominates(self):
        """When 0.5R > ATR14 and > floor, chandelier uses 0.5R."""
        # entry=1.1000, SL=1.0700 → 1R=300 pips, 0.5R=150 pips = 0.0150
        # ATR14=0.0050 (50 pips), floor=15 pips=0.0015
        # → chandelier_distance = max(0.0150, 0.0050, 0.0015) = 0.0150
        entry = 1.1000
        sl = 1.0700
        atr14 = 0.0050
        chandelier_sl = initial_chandelier_sl(entry, sl, "BUY", atr14, "EURUSD")
        # 1.5R target = 1.1000 + 1.5 * 0.03 = 1.1450
        # chandelier = 1.1450 - 0.0150 = 1.1300
        expected_distance = 0.0150
        target_1_5r = calculate_1_5r_price(entry, sl, "BUY")
        assert chandelier_sl == pytest.approx(target_1_5r - expected_distance, abs=1e-6)

    def test_atr14_dominates(self):
        """When ATR14 > 0.5R and > floor, chandelier uses ATR14."""
        # entry=1.1000, SL=1.0990 → 1R=10 pips=0.0010, 0.5R=0.0005
        # ATR14=0.0025, floor=0.0015
        # → chandelier_distance = max(0.0005, 0.0025, 0.0015) = 0.0025
        entry = 1.1000
        sl = 1.0990
        atr14 = 0.0025
        chandelier_sl = initial_chandelier_sl(entry, sl, "BUY", atr14, "EURUSD")
        target_1_5r = calculate_1_5r_price(entry, sl, "BUY")
        assert chandelier_sl == pytest.approx(target_1_5r - 0.0025, abs=1e-6)

    def test_floor_dominates_majors_15pips(self):
        """Floor ≥ 15 pips on EURUSD (floor = 0.0015)."""
        entry = 1.1000
        sl = 1.0998  # 2-pip SL → 0.5R = 1 pip
        atr14 = 0.0001  # 1 pip
        # floor = 15 pips = 0.0015 → dominates
        chandelier_sl = initial_chandelier_sl(entry, sl, "BUY", atr14, "EURUSD")
        target_1_5r = calculate_1_5r_price(entry, sl, "BUY")
        assert chandelier_sl == pytest.approx(target_1_5r - 0.0015, abs=1e-6)

    def test_floor_jpy_25pips(self):
        """Floor ≥ 25 pips on USDJPY (floor = 25 * 0.01 = 0.25)."""
        entry = 150.00
        sl = 149.98  # 2-pip SL
        atr14 = 0.05
        chandelier_sl = initial_chandelier_sl(entry, sl, "BUY", atr14, "USDJPY")
        target_1_5r = calculate_1_5r_price(entry, sl, "BUY")
        assert chandelier_sl == pytest.approx(target_1_5r - 0.25, abs=1e-4)

    def test_chandelier_sell_direction(self):
        """SELL: chandelier SL is above the partial exit price."""
        entry = 1.1000
        sl = 1.1050
        atr14 = 0.0010
        chandelier_sl = initial_chandelier_sl(entry, sl, "SELL", atr14, "EURUSD")
        target_1_5r = calculate_1_5r_price(entry, sl, "SELL")
        assert chandelier_sl > target_1_5r  # SL is above price for SELL


# ---------------------------------------------------------------------------
# VE.4 — Chandelier never widens
# ---------------------------------------------------------------------------

class TestChandelierNeverWidens:
    """VE.4: Chandelier moves only in profitable direction."""

    def test_buy_sl_never_moves_down(self):
        """For BUY, update_chandelier should never return a lower SL than current."""
        current_sl = 1.1200
        # Price moves higher → SL moves up
        new_sl = update_chandelier(
            new_extreme=1.1400,
            current_sl=current_sl,
            direction="BUY",
            atr14=0.0020,
            initial_r_pips=100,
            pair="EURUSD",
        )
        assert new_sl >= current_sl, "BUY Chandelier should never move down"

    def test_buy_sl_stays_when_price_drops(self):
        """For BUY, if new extreme is lower than current, SL stays."""
        current_sl = 1.1200
        new_sl = update_chandelier(
            new_extreme=1.1100,   # lower than current position
            current_sl=current_sl,
            direction="BUY",
            atr14=0.0020,
            initial_r_pips=100,
            pair="EURUSD",
        )
        assert new_sl == current_sl

    def test_sell_sl_never_moves_up(self):
        """For SELL, update_chandelier should never return a higher SL than current."""
        current_sl = 1.0900
        # Price moves lower → SL moves down
        new_sl = update_chandelier(
            new_extreme=1.0700,
            current_sl=current_sl,
            direction="SELL",
            atr14=0.0020,
            initial_r_pips=100,
            pair="EURUSD",
        )
        assert new_sl <= current_sl, "SELL Chandelier should never move up"

    def test_multiple_updates_monotonic(self):
        """Successive updates should produce monotonically moving SL."""
        current_sl = 1.1200
        extremes = [1.1300, 1.1280, 1.1350, 1.1340, 1.1400]
        sl = current_sl
        prev_sl = sl
        for extreme in extremes:
            sl = update_chandelier(extreme, sl, "BUY", 0.0020, 100, "EURUSD")
            assert sl >= prev_sl, f"SL dropped from {prev_sl} to {sl}"
            prev_sl = sl


# ---------------------------------------------------------------------------
# VE.5 — Runner stays open until Chandelier hit
# ---------------------------------------------------------------------------

class TestRunnerBehavior:
    """VE.5: Runner portion stays open until Chandelier SL is hit."""

    def test_not_hit_before_threshold(self):
        chandelier_sl = 1.1200
        assert is_chandelier_hit(1.1250, chandelier_sl, "BUY") is False

    def test_hit_at_threshold_buy(self):
        chandelier_sl = 1.1200
        assert is_chandelier_hit(1.1200, chandelier_sl, "BUY") is True

    def test_hit_below_threshold_buy(self):
        chandelier_sl = 1.1200
        assert is_chandelier_hit(1.1150, chandelier_sl, "BUY") is True

    def test_not_hit_sell(self):
        chandelier_sl = 1.0900
        assert is_chandelier_hit(1.0850, chandelier_sl, "SELL") is False

    def test_hit_sell(self):
        chandelier_sl = 1.0900
        assert is_chandelier_hit(1.0950, chandelier_sl, "SELL") is True


# ---------------------------------------------------------------------------
# VE.6 — Full losers show exactly −1.0R
# ---------------------------------------------------------------------------

class TestFullLoss:
    """VE.6: Full losers (exit at SL) = exactly −1.0R."""

    def test_full_loss_buy(self):
        """BUY: entry=1.1000, SL=1.0900 → exit at SL → −1.0R."""
        r = calculate_r_multiple(entry=1.1000, exit_price=1.0900, sl=1.0900, direction="BUY")
        assert r == pytest.approx(-1.0, abs=1e-8)

    def test_full_loss_sell(self):
        """SELL: entry=1.1000, SL=1.1100 → exit at SL → −1.0R."""
        r = calculate_r_multiple(entry=1.1000, exit_price=1.1100, sl=1.1100, direction="SELL")
        assert r == pytest.approx(-1.0, abs=1e-8)

    def test_full_win_1_5r(self):
        """1.5R exit → +1.5R."""
        r = calculate_r_multiple(entry=1.1000, exit_price=1.1150, sl=1.0900, direction="BUY")
        assert r == pytest.approx(1.5, abs=1e-6)

    def test_locked_profit_deep_trending(self):
        """CS > 85 → 60% close → locked profit = 60% × 1.5R = 0.90R."""
        pct = get_partial_exit_pct(90)
        locked = expected_locked_profit_r(pct)
        assert locked == pytest.approx(0.90, abs=1e-8)

    def test_locked_profit_range(self):
        """CS < 30 → 80% close → locked profit = 80% × 1.5R = 1.20R."""
        pct = get_partial_exit_pct(15)
        locked = expected_locked_profit_r(pct)
        assert locked == pytest.approx(1.20, abs=1e-8)


# ---------------------------------------------------------------------------
# VE.7 — CS at entry time used for partial exit % (not at 1.5R hit)
# ---------------------------------------------------------------------------

class TestCSFrozenAtEntry:
    """VE.7: CompositeScore used for partial exit is the one AT entry, not at 1.5R."""

    def test_partial_pct_uses_entry_cs_not_current(self):
        """
        Simulate: entry CS = 90 (deep trending → 60% close).
        Even if regime changes by the time 1.5R is hit, partial% stays at 60%.
        This is enforced by storing partial_exit_pct on the Signal at entry time.
        """
        from src.signal import Signal
        import pandas as pd

        entry_cs = 90.0
        signal = Signal(
            timestamp=pd.Timestamp("2024-01-01", tz="UTC"),
            pair="EURUSD",
            direction="BUY",
            entry=1.1000,
            sl=1.0900,
            tp_1r=1.1100,
            strategy="TrendRider",
            composite_score=entry_cs,
            partial_exit_pct=get_partial_exit_pct(entry_cs),
        )

        # Signal stores 60% from entry CS
        assert signal.partial_exit_pct == pytest.approx(0.60)
        assert signal.composite_score == 90.0

        # Even if current market CS is now 50 (regime changed), signal.partial_exit_pct is still 60%
        current_cs_at_1_5r = 50.0
        current_pct = get_partial_exit_pct(current_cs_at_1_5r)
        assert current_pct == pytest.approx(0.75)  # would be 75% if re-evaluated

        # But the signal uses its frozen value
        assert signal.partial_exit_pct == pytest.approx(0.60)  # frozen at entry
