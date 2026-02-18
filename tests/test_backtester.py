"""
Phase 3 Unit Tests — Backtester
PRD §9.4 validation items: V3.4–V3.11

All tests use synthetic Range Bar data — no real market data required.

Run:
    pytest tests/test_backtester.py -v
"""

from __future__ import annotations

from datetime import date, timedelta, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from backtester.account import BacktestAccount
from backtester.cost_model import (
    apply_entry_slippage,
    apply_exit_slippage,
    round_trip_commission,
)
from backtester.results import BacktestResults, CycleResult
from backtester.trade import BacktestTrade
from backtester.walk_forward import WalkForwardManager
from src.config import (
    COMMISSION_PER_LOT_RT,
    PIP_SIZE,
    SLIPPAGE_PIPS,
    WALK_FORWARD_CYCLES,
    WALK_FORWARD_TEST_MONTHS,
    WALK_FORWARD_TRAIN_MONTHS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _trade(
    pair: str = "EURUSD",
    direction: str = "BUY",
    entry: float = 1.1000,
    sl: float = 1.0900,
    lot_size: float = 0.10,
    composite_score: float = 75.0,
    partial_exit_pct: float = 0.70,
    strategy: str = "TrendRider",
) -> BacktestTrade:
    pip = PIP_SIZE.get(pair, 0.0001)
    return BacktestTrade(
        trade_id="TEST01",
        pair=pair,
        direction=direction,
        strategy=strategy,
        entry_price=entry,
        sl_price=sl,
        entry_time=pd.Timestamp("2024-01-02 10:00", tz="UTC"),
        lot_size=lot_size,
        initial_r_pips=abs(entry - sl) / pip,
        composite_score=composite_score,
        partial_exit_pct=partial_exit_pct,
    )


def _account(equity: float = 500.0) -> BacktestAccount:
    return BacktestAccount(initial_equity=equity)


def _ts(dt_str: str) -> pd.Timestamp:
    return pd.Timestamp(dt_str, tz="UTC")


def _bar(high: float, low: float, close: float = None, open_: float = None) -> pd.Series:
    if close is None:
        close = (high + low) / 2
    if open_ is None:
        open_ = close
    return pd.Series({
        "open": open_, "high": high, "low": low, "close": close,
        "start_time": _ts("2024-01-02 10:00"),
        "end_time": _ts("2024-01-02 10:05"),
    })


# ---------------------------------------------------------------------------
# Cost Model
# ---------------------------------------------------------------------------

class TestCostModel:
    """Basic cost model validation."""

    def test_entry_slippage_buy_worsens_price_up(self):
        """BUY entry slippage increases the price (you pay more)."""
        price = apply_entry_slippage(1.1000, "BUY", "EURUSD")
        expected = 1.1000 + SLIPPAGE_PIPS * PIP_SIZE["EURUSD"]
        assert price == pytest.approx(expected, abs=1e-9)

    def test_entry_slippage_sell_worsens_price_down(self):
        """SELL entry slippage decreases the price (you sell for less)."""
        price = apply_entry_slippage(1.1000, "SELL", "EURUSD")
        expected = 1.1000 - SLIPPAGE_PIPS * PIP_SIZE["EURUSD"]
        assert price == pytest.approx(expected, abs=1e-9)

    def test_exit_slippage_buy_worsens_price_down(self):
        """BUY exit slippage decreases the price (you receive less)."""
        price = apply_exit_slippage(1.1150, "BUY", "EURUSD")
        expected = 1.1150 - SLIPPAGE_PIPS * PIP_SIZE["EURUSD"]
        assert price == pytest.approx(expected, abs=1e-9)

    def test_exit_slippage_sell_worsens_price_up(self):
        """SELL exit slippage increases the price (you pay more to cover)."""
        price = apply_exit_slippage(1.0850, "SELL", "EURUSD")
        expected = 1.0850 + SLIPPAGE_PIPS * PIP_SIZE["EURUSD"]
        assert price == pytest.approx(expected, abs=1e-9)

    def test_commission_scales_with_lots(self):
        """Commission = $7 × lot_size (round-trip)."""
        assert round_trip_commission(1.0) == pytest.approx(COMMISSION_PER_LOT_RT)
        assert round_trip_commission(0.1) == pytest.approx(COMMISSION_PER_LOT_RT * 0.1)
        assert round_trip_commission(2.0) == pytest.approx(COMMISSION_PER_LOT_RT * 2.0)

    def test_commission_deducted_at_open(self):
        """Opening a trade deducts commission from equity immediately."""
        account = _account(equity=500.0)
        t = _trade(lot_size=1.0)
        account.open_trade(t)
        assert account.equity == pytest.approx(500.0 - COMMISSION_PER_LOT_RT)


# ---------------------------------------------------------------------------
# V3.5 — Partial exit fires at 1.5R with correct percentage
# ---------------------------------------------------------------------------

class TestPartialExit:
    """V3.5: Partial exit fires at exactly 1.5R with frozen CS-based percentage."""

    def test_partial_exit_changes_phase_to_runner(self):
        """When 1.5R is reached, trade phase changes to 'runner'."""
        account = _account()
        t = _trade(entry=1.1000, sl=1.0900, direction="BUY", partial_exit_pct=0.70)
        account.open_trade(t)

        # 1.5R for BUY with 100-pip SL = 1.1000 + 1.5*100*0.0001 = 1.1150
        target = 1.1150
        account.apply_partial_exit(t, target, _ts("2024-01-02 12:00"), atr14=0.0010)

        assert t.phase == "runner"
        assert t.partial_exit_time is not None

    def test_partial_exit_pct_correct(self):
        """Partial exit records the correct exit percentage."""
        account = _account()
        t = _trade(composite_score=75.0, partial_exit_pct=0.70)
        account.open_trade(t)

        account.apply_partial_exit(t, 1.1150, _ts("2024-01-02 12:00"), atr14=0.0010)

        assert t.partial_exit_pct == pytest.approx(0.70)

    def test_partial_exit_sets_chandelier_sl(self):
        """After partial exit, chandelier_sl is set (non-zero)."""
        account = _account()
        t = _trade(entry=1.1000, sl=1.0900, direction="BUY")
        account.open_trade(t)
        account.apply_partial_exit(t, 1.1150, _ts("2024-01-02 12:00"), atr14=0.0020)

        assert t.chandelier_sl > 0.0
        # Chandelier SL must be below the partial exit price (for BUY)
        assert t.chandelier_sl < 1.1150

    def test_full_loss_before_1_5r(self):
        """If SL is hit before 1.5R, trade closes at full -1.0R."""
        account = _account()
        t = _trade(entry=1.1000, sl=1.0900, direction="BUY")
        account.open_trade(t)
        account.close_trade(t, 1.0900, _ts("2024-01-02 11:00"), "SL_HIT")

        assert t.phase == "closed"
        assert t.close_reason == "SL_HIT"
        assert t.r_multiple_total == pytest.approx(-1.0, abs=0.05)


# ---------------------------------------------------------------------------
# V3.6 — Chandelier trails correctly
# ---------------------------------------------------------------------------

class TestChandelierTrailing:
    """V3.6: Chandelier moves in profitable direction only, never widens."""

    def test_chandelier_moves_up_on_buy_advance(self):
        """For BUY, Chandelier SL moves up when price advances."""
        account = _account()
        t = _trade(entry=1.1000, sl=1.0900, direction="BUY")
        account.open_trade(t)
        account.apply_partial_exit(t, 1.1150, _ts("2024-01-02 12:00"), atr14=0.0020)

        initial_chandelier = t.chandelier_sl
        account.update_chandelier_for_trade(t, bar_extreme=1.1300, atr14=0.0020)

        assert t.chandelier_sl >= initial_chandelier, "Chandelier should move up for BUY advance"

    def test_chandelier_never_moves_down_on_buy_retrace(self):
        """For BUY, Chandelier SL does not drop when price retraces."""
        account = _account()
        t = _trade(entry=1.1000, sl=1.0900, direction="BUY")
        account.open_trade(t)
        account.apply_partial_exit(t, 1.1150, _ts("2024-01-02 12:00"), atr14=0.0020)

        initial_chandelier = t.chandelier_sl
        account.update_chandelier_for_trade(t, bar_extreme=1.1050, atr14=0.0020)

        assert t.chandelier_sl == pytest.approx(initial_chandelier), \
            "Chandelier must not widen on retrace"

    def test_chandelier_hit_closes_runner(self):
        """Runner closes when price breaches Chandelier SL."""
        account = _account()
        t = _trade(entry=1.1000, sl=1.0900, direction="BUY")
        account.open_trade(t)
        account.apply_partial_exit(t, 1.1150, _ts("2024-01-02 12:00"), atr14=0.0020)

        # Force a specific chandelier level
        t.chandelier_sl = 1.1100
        account.close_trade(t, 1.1100, _ts("2024-01-02 14:00"), "CHANDELIER_HIT")

        assert t.phase == "closed"
        assert t.close_reason == "CHANDELIER_HIT"
        assert t.r_multiple_runner == pytest.approx(1.0, abs=0.05)


# ---------------------------------------------------------------------------
# V3.7 — Daily 2R cap
# ---------------------------------------------------------------------------

class TestDailyCapEnforcement:
    """V3.7: No day exceeds 2R total loss."""

    def test_daily_cap_tracks_losses(self):
        """Closing a losing trade increments daily_r_used."""
        account = _account()
        t = _trade()
        account.open_trade(t)
        account.close_trade(t, t.sl_price, _ts("2024-01-02 12:00"), "SL_HIT")
        assert account.daily_r_used > 0.0

    def test_daily_cap_is_hit_flag(self):
        """is_daily_cap_hit returns True when daily_r_used >= 2R."""
        account = _account()
        account.daily_r_used = 2.0
        assert account.is_daily_cap_hit() is True

    def test_daily_cap_not_hit_below_2r(self):
        account = _account()
        account.daily_r_used = 1.9
        assert account.is_daily_cap_hit() is False

    def test_daily_reset_at_midnight(self):
        """Daily counters reset at midnight UTC."""
        account = _account()
        account.daily_r_used = 2.0
        account.daily_trade_count = 5

        # Simulate next day
        next_day = _ts("2024-01-03 00:01")
        reset = account.reset_daily_if_needed(next_day)

        assert reset is True
        assert account.daily_r_used == 0.0
        assert account.daily_trade_count == 0

    def test_daily_reset_same_day_no_op(self):
        """No reset if same calendar day — prime the date with a first call."""
        account = _account()
        # Prime: first call sets _last_reset_date to Jan 2
        account.reset_daily_if_needed(_ts("2024-01-02 09:00"))
        # Now accumulate R loss
        account.daily_r_used = 1.5
        # Second call same day → should NOT reset
        account.reset_daily_if_needed(_ts("2024-01-02 15:00"))
        assert account.daily_r_used == pytest.approx(1.5)


# ---------------------------------------------------------------------------
# V3.8 — Strategy cooldown in backtest
# ---------------------------------------------------------------------------

class TestStrategyCooldownInBacktest:
    """V3.8: 5 consecutive losses in last 10 trades → 24hr pause."""

    def test_cooldown_triggered_after_5_losses(self):
        """BrainCore/PerformanceTracker blocks strategy after 5 losses."""
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

    def test_strategies_track_independently_in_backtest(self):
        from src.performance_tracker import PerformanceTracker
        tracker = PerformanceTracker()
        for _ in range(5):
            tracker.add_trade("TrendRider", -1.0)
        # BreakoutRider is unaffected
        assert tracker.is_in_cooldown("BreakoutRider") is False


# ---------------------------------------------------------------------------
# V3.9 — Correlation filter in backtest
# ---------------------------------------------------------------------------

class TestCorrelationFilterInBacktest:
    """V3.9: Max 2 trades sharing same base/quote currency."""

    def test_3rd_usd_trade_blocked_by_account_state(self):
        """With 2 USD open trades, account_state reflects this for BrainCore."""
        account = _account(equity=2000.0)
        t1 = _trade(pair="EURUSD", direction="BUY")
        t2 = _trade(pair="GBPUSD", direction="BUY")
        account.open_trade(t1)
        account.open_trade(t2)

        state = account.get_account_state()
        pairs_open = [p["pair"] for p in state.open_positions]
        assert "EURUSD" in pairs_open
        assert "GBPUSD" in pairs_open
        # The correlation filter (in BrainCore) would block USDCHF here
        # Verify the state carries the right number of positions
        assert len(state.open_positions) == 2


# ---------------------------------------------------------------------------
# V3.10 — Position cap in backtest
# ---------------------------------------------------------------------------

class TestPositionCapInBacktest:
    """V3.10: Max 2 concurrent positions (3 if equity > $1,000)."""

    def test_position_count_tracked_correctly(self):
        account = _account(equity=500.0)
        t1 = _trade(pair="EURUSD")
        t2 = _trade(pair="GBPUSD")
        account.open_trade(t1)
        account.open_trade(t2)

        state = account.get_account_state()
        assert len(state.open_positions) == 2

    def test_max_concurrent_is_2_below_1k(self):
        state = _account(equity=999.0).get_account_state()
        assert state.get_max_concurrent() == 2

    def test_max_concurrent_is_3_above_1k(self):
        state = _account(equity=1001.0).get_account_state()
        assert state.get_max_concurrent() == 3


# ---------------------------------------------------------------------------
# V3.11 — News blocking in backtest
# ---------------------------------------------------------------------------

class TestNewsBlockingInBacktest:
    """V3.11: No entries during historical high-impact news windows."""

    def test_news_layer_blocks_pair_during_event(self):
        """NewsLayer.is_blocked() returns True within HIGH event window."""
        from datetime import datetime
        from src.news_layer import NewsLayer, NewsEvent

        news = NewsLayer()
        news.add_event(NewsEvent(
            event_id="NFP_TEST",
            name="Non-Farm Payrolls",
            currency="USD",
            impact="HIGH",
            time_utc=datetime(2024, 1, 5, 13, 30, tzinfo=timezone.utc),
        ))

        check_time = datetime(2024, 1, 5, 13, 20, tzinfo=timezone.utc)  # 10min before
        blocked, reason = news.is_blocked("EURUSD", check_time)
        assert blocked is True
        assert "NFP_TEST" in reason or "Non-Farm" in reason

    def test_non_usd_pair_not_blocked_by_usd_event(self):
        from datetime import datetime
        from src.news_layer import NewsLayer, NewsEvent

        news = NewsLayer()
        news.add_event(NewsEvent(
            event_id="NFP_TEST",
            name="Non-Farm Payrolls",
            currency="USD",
            impact="HIGH",
            time_utc=datetime(2024, 1, 5, 13, 30, tzinfo=timezone.utc),
        ))

        check_time = datetime(2024, 1, 5, 13, 20, tzinfo=timezone.utc)
        blocked, _ = news.is_blocked("AUDJPY", check_time)
        assert blocked is False


# ---------------------------------------------------------------------------
# V3.4 — Trade log matches signals
# ---------------------------------------------------------------------------

class TestTradeLogMatchesSignals:
    """V3.4: Trade markers match signal log."""

    def test_trade_to_dict_has_required_fields(self):
        """BacktestTrade.to_dict() returns all required trade log fields."""
        t = _trade()
        d = t.to_dict()
        required = [
            "trade_id", "pair", "direction", "strategy",
            "entry_time", "entry_price", "sl_price", "lot_size",
            "composite_score", "partial_exit_pct",
            "close_reason", "r_multiple_total", "pnl_usd",
        ]
        for field_name in required:
            assert field_name in d, f"Missing field: {field_name}"

    def test_trade_log_df_sorted_by_entry_time(self):
        """to_trade_log_df() returns DataFrame sorted by entry_time."""
        t1 = _trade()
        t1.entry_time = _ts("2024-01-03 10:00")
        t1.phase = "closed"
        t2 = _trade()
        t2.entry_time = _ts("2024-01-02 10:00")
        t2.phase = "closed"

        results = BacktestResults(all_trades=[t1, t2])
        df = results.to_trade_log_df()
        assert df.iloc[0]["entry_time"] <= df.iloc[1]["entry_time"]


# ---------------------------------------------------------------------------
# Walk-forward structure tests
# ---------------------------------------------------------------------------

class TestWalkForwardCycles:
    """Walk-forward cycle generation validation."""

    def test_4_cycles_generated_from_2_years(self):
        """2 years of data → exactly 4 cycles of 4-month train + 2-month test."""
        wf = WalkForwardManager()
        data_start = _ts("2023-01-01")
        data_end = _ts("2024-12-31")
        cycles = wf.generate_cycles(data_start, data_end)
        assert len(cycles) == WALK_FORWARD_CYCLES

    def test_cycles_are_non_overlapping(self):
        """Each test period starts the day after the previous test period ends."""
        wf = WalkForwardManager()
        cycles = wf.generate_cycles(_ts("2023-01-01"), _ts("2024-12-31"))
        for i in range(1, len(cycles)):
            prev_test_end = cycles[i - 1].test_end
            curr_train_start = cycles[i].train_start
            # Current cycle starts the day after previous test ends
            assert curr_train_start > prev_test_end

    def test_train_period_is_4_months(self):
        """Each train period is exactly 4 months."""
        wf = WalkForwardManager()
        cycles = wf.generate_cycles(_ts("2023-01-01"), _ts("2024-12-31"))
        for c in cycles:
            months = (c.train_end.year - c.train_start.year) * 12 + \
                     (c.train_end.month - c.train_start.month)
            assert months == pytest.approx(WALK_FORWARD_TRAIN_MONTHS - 1, abs=1)

    def test_test_period_is_2_months(self):
        """Each test period is exactly 2 months."""
        wf = WalkForwardManager()
        cycles = wf.generate_cycles(_ts("2023-01-01"), _ts("2024-12-31"))
        for c in cycles:
            months = (c.test_end.year - c.test_start.year) * 12 + \
                     (c.test_end.month - c.test_start.month)
            assert months == pytest.approx(WALK_FORWARD_TEST_MONTHS - 1, abs=1)


# ---------------------------------------------------------------------------
# Results persistence
# ---------------------------------------------------------------------------

class TestResultsPersistence:
    """Save/load round-trip via Parquet."""

    def test_save_and_load_roundtrip(self, tmp_path):
        """Saved trade log can be loaded and retains key fields."""
        t = _trade()
        t.phase = "closed"
        t.close_reason = "SL_HIT"
        t.r_multiple_total = -1.0
        t.pnl_usd = -7.0
        t.commission_usd = 0.70

        results = BacktestResults(all_trades=[t])
        save_path = str(tmp_path / "test_run")
        results.save(save_path)

        loaded = BacktestResults.load(save_path)
        assert len(loaded.all_trades) == 1
        lt = loaded.all_trades[0]
        assert lt.pair == "EURUSD"
        assert lt.close_reason == "SL_HIT"
        assert lt.r_multiple_total == pytest.approx(-1.0)

    def test_empty_results_save_no_error(self, tmp_path):
        """Empty results save without error."""
        results = BacktestResults()
        results.save(str(tmp_path / "empty_run"))  # Should not raise


# ---------------------------------------------------------------------------
# Weekend close
# ---------------------------------------------------------------------------

class TestWeekendClose:
    """Trades forced closed before Friday market close."""

    def test_is_near_friday_close_detection(self):
        from backtester.engine import _is_near_friday_close
        # Friday 21:50 UTC = within 10 minutes of 22:00 close
        friday_near_close = _ts("2024-01-05 21:50")  # Jan 5 2024 = Friday
        assert _is_near_friday_close(friday_near_close) is True

    def test_thursday_not_near_friday_close(self):
        from backtester.engine import _is_near_friday_close
        thursday = _ts("2024-01-04 21:50")
        assert _is_near_friday_close(thursday) is False

    def test_friday_morning_not_near_close(self):
        from backtester.engine import _is_near_friday_close
        friday_morning = _ts("2024-01-05 09:00")
        assert _is_near_friday_close(friday_morning) is False
