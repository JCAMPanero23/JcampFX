"""Tests for backtester/playback.py — requires real backtest run."""
import pytest
from pathlib import Path
import pandas as pd

RESULTS_DIR = Path("data/backtest_results")
SKIP_IF_NO_RESULTS = pytest.mark.skipif(
    not any(RESULTS_DIR.iterdir()) if RESULTS_DIR.exists() else True,
    reason="No backtest results available"
)

@SKIP_IF_NO_RESULTS
def test_get_trade_context_returns_required_keys():
    from backtester.playback import get_trade_context
    runs = sorted(RESULTS_DIR.iterdir())
    run_dir = str(runs[-1])
    trades = pd.read_parquet(Path(run_dir) / "trades.parquet")
    trade_id = str(trades.iloc[0]["trade_id"])

    ctx = get_trade_context(run_dir, trade_id)

    assert "trade" in ctx
    assert "range_bars" in ctx
    assert "dcrd_per_bar" in ctx
    assert "dcrd_at_entry" in ctx
    assert "entry_bar_local_idx" in ctx
    assert "partial_exit_bar_local_idx" in ctx
    assert "close_bar_local_idx" in ctx

@SKIP_IF_NO_RESULTS
def test_range_bars_window_contains_entry():
    from backtester.playback import get_trade_context
    runs = sorted(RESULTS_DIR.iterdir())
    run_dir = str(runs[-1])
    trades = pd.read_parquet(Path(run_dir) / "trades.parquet")
    trade_id = str(trades.iloc[0]["trade_id"])
    trade_row = trades.iloc[0]

    ctx = get_trade_context(run_dir, trade_id, context_bars=20)
    rb = ctx["range_bars"]
    entry_idx = ctx["entry_bar_local_idx"]

    # The bar at entry_bar_local_idx should be near entry_time
    entry_time = pd.Timestamp(trade_row["entry_time"])
    bar_time = pd.Timestamp(rb.iloc[entry_idx]["end_time"])
    assert bar_time >= entry_time - pd.Timedelta("2h")

@SKIP_IF_NO_RESULTS
def test_dcrd_at_entry_has_all_components():
    from backtester.playback import get_trade_context
    runs = sorted(RESULTS_DIR.iterdir())
    run_dir = str(runs[-1])
    trades = pd.read_parquet(Path(run_dir) / "trades.parquet")
    trade_id = str(trades.iloc[0]["trade_id"])

    ctx = get_trade_context(run_dir, trade_id)
    dcrd = ctx["dcrd_at_entry"]

    assert "composite_score" in dcrd
    assert "layer1_structural" in dcrd
    assert "layer2_modifier" in dcrd
    assert "layer3_rb_intelligence" in dcrd
