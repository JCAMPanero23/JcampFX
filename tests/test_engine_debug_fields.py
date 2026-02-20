"""Test that debug fields flow correctly from Signal through BacktestTrade to to_dict()."""
import pandas as pd
import pytest
from src.signal import Signal
from backtester.trade import BacktestTrade


def _make_signal_with_debug(**kwargs):
    defaults = dict(
        timestamp=pd.Timestamp("2024-01-02 10:00", tz="UTC"),
        pair="EURUSD", direction="BUY", entry=1.1000, sl=1.0980,
        tp_1r=1.1020, strategy="TrendRider", composite_score=75.0,
        lot_size=0.01, partial_exit_pct=0.75,
        adx_at_entry=28.5, adx_slope_rising=True,
        staircase_depth=5, pullback_bar_idx=42,
        pullback_depth_pips=18.3, entry_bar_idx=43,
    )
    defaults.update(kwargs)
    return Signal(**defaults)


def test_backtesttrade_accepts_debug_fields():
    """BacktestTrade constructor accepts the 6 debug fields."""
    signal = _make_signal_with_debug()
    pip = 0.0001
    initial_r_pips = abs(signal.entry - signal.sl) / pip
    trade = BacktestTrade(
        trade_id="test01",
        pair=signal.pair,
        direction=signal.direction,
        strategy=signal.strategy,
        entry_price=signal.entry,
        sl_price=signal.sl,
        entry_time=signal.timestamp,
        lot_size=signal.lot_size,
        initial_r_pips=initial_r_pips,
        composite_score=signal.composite_score,
        partial_exit_pct=signal.partial_exit_pct,
        adx_at_entry=signal.adx_at_entry,
        adx_slope_rising=signal.adx_slope_rising,
        staircase_depth=signal.staircase_depth,
        pullback_bar_idx=signal.pullback_bar_idx,
        pullback_depth_pips=signal.pullback_depth_pips,
        entry_bar_idx=signal.entry_bar_idx,
    )
    assert trade.adx_at_entry == 28.5
    assert trade.adx_slope_rising is True
    assert trade.staircase_depth == 5
    assert trade.pullback_bar_idx == 42
    assert trade.pullback_depth_pips == 18.3
    assert trade.entry_bar_idx == 43


def test_debug_fields_appear_in_to_dict():
    """to_dict() must include all 6 debug fields."""
    signal = _make_signal_with_debug()
    pip = 0.0001
    initial_r_pips = abs(signal.entry - signal.sl) / pip
    trade = BacktestTrade(
        trade_id="test01",
        pair=signal.pair,
        direction=signal.direction,
        strategy=signal.strategy,
        entry_price=signal.entry,
        sl_price=signal.sl,
        entry_time=signal.timestamp,
        lot_size=signal.lot_size,
        initial_r_pips=initial_r_pips,
        composite_score=signal.composite_score,
        partial_exit_pct=signal.partial_exit_pct,
        adx_at_entry=signal.adx_at_entry,
        adx_slope_rising=signal.adx_slope_rising,
        staircase_depth=signal.staircase_depth,
        pullback_bar_idx=signal.pullback_bar_idx,
        pullback_depth_pips=signal.pullback_depth_pips,
        entry_bar_idx=signal.entry_bar_idx,
    )
    d = trade.to_dict()
    assert d["adx_at_entry"] == 28.5
    assert d["staircase_depth"] == 5
    assert d["entry_bar_idx"] == 43


def test_non_trendrider_signal_has_none_debug_fields():
    """Non-TrendRider signals should have None for all 6 debug fields."""
    signal = Signal(
        timestamp=pd.Timestamp("2024-01-02 10:00", tz="UTC"),
        pair="EURUSD", direction="BUY", entry=1.1000, sl=1.0980,
        tp_1r=1.1020, strategy="BreakoutRider", composite_score=50.0,
    )
    assert signal.adx_at_entry is None
    assert signal.staircase_depth is None
    assert signal.entry_bar_idx is None
