# tests/test_signal_debug_fields.py
from src.signal import Signal
import pandas as pd

def _make_signal(**kwargs):
    defaults = dict(
        timestamp=pd.Timestamp("2024-01-02 10:00", tz="UTC"),
        pair="EURUSD", direction="BUY", entry=1.1000, sl=1.0980,
        tp_1r=1.1020, strategy="TrendRider", composite_score=75.0,
    )
    defaults.update(kwargs)
    return Signal(**defaults)

def test_signal_debug_fields_default_none():
    s = _make_signal()
    assert s.adx_at_entry is None
    assert s.adx_slope_rising is None
    assert s.staircase_depth is None
    assert s.pullback_bar_idx is None
    assert s.pullback_depth_pips is None
    assert s.entry_bar_idx is None

def test_signal_debug_fields_populate():
    s = _make_signal(adx_at_entry=28.5, adx_slope_rising=True,
                     staircase_depth=5, pullback_bar_idx=42,
                     pullback_depth_pips=18.3, entry_bar_idx=43)
    assert s.adx_at_entry == 28.5
    assert s.adx_slope_rising is True
    assert s.staircase_depth == 5
    assert s.pullback_bar_idx == 42
    assert s.pullback_depth_pips == 18.3
    assert s.entry_bar_idx == 43
