# tests/test_trade_fields.py
from backtester.trade import BacktestTrade
import pandas as pd

def _make_trade(**kwargs):
    defaults = dict(
        trade_id="t1", pair="EURUSD", direction="BUY", strategy="TrendRider",
        entry_price=1.1000, sl_price=1.0980, entry_time=pd.Timestamp("2024-01-02 10:00", tz="UTC"),
        lot_size=0.01, initial_r_pips=20.0, composite_score=75.0, partial_exit_pct=0.75,
    )
    defaults.update(kwargs)
    return BacktestTrade(**defaults)

def test_new_debug_fields_default_none():
    t = _make_trade()
    assert t.adx_at_entry is None
    assert t.adx_slope_rising is None
    assert t.staircase_depth is None
    assert t.pullback_bar_idx is None
    assert t.pullback_depth_pips is None
    assert t.entry_bar_idx is None

def test_new_debug_fields_in_to_dict():
    t = _make_trade(adx_at_entry=28.5, adx_slope_rising=True,
                    staircase_depth=5, pullback_bar_idx=42,
                    pullback_depth_pips=18.3, entry_bar_idx=43)
    t.close_price = 1.103
    t.close_time = pd.Timestamp("2024-01-02 14:00", tz="UTC")
    t.close_reason = "CHANDELIER_HIT"
    d = t.to_dict()
    assert d["adx_at_entry"] == 28.5
    assert d["adx_slope_rising"] is True
    assert d["staircase_depth"] == 5
    assert d["pullback_bar_idx"] == 42
    assert d["pullback_depth_pips"] == 18.3
    assert d["entry_bar_idx"] == 43

def test_new_debug_fields_can_be_set():
    t = _make_trade()
    t.adx_at_entry = 31.2
    t.staircase_depth = 4
    assert t.adx_at_entry == 31.2
    assert t.staircase_depth == 4
