"""
Quick test script to verify Trade Inspector functionality
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from backtester.playback import get_trade_context
import pandas as pd

def test_inspector():
    """Test Inspector data loading with a real trade."""

    run_dir = "data/backtest_results/run_20260219_190902"

    # Load trades to get a losing trade (SL hit)
    trades_df = pd.read_parquet(Path(run_dir) / "trades.parquet")

    # Find a losing USDJPY trade (Oct 2024 - the bad month)
    usdjpy_trades = trades_df[trades_df["pair"] == "USDJPY"].copy()
    usdjpy_trades["entry_time"] = pd.to_datetime(usdjpy_trades["entry_time"])

    oct_2024_trades = usdjpy_trades[
        (usdjpy_trades["entry_time"] >= "2024-10-01") &
        (usdjpy_trades["entry_time"] < "2024-11-01")
    ]

    # Get a losing trade (no partial exit)
    losing_trades = oct_2024_trades[oct_2024_trades["partial_exit_time"].isna()]

    if losing_trades.empty:
        print("No losing trades found in Oct 2024 USDJPY")
        return False

    test_trade = losing_trades.iloc[0]
    trade_id = test_trade["trade_id"]

    print(f"\n=== Testing Inspector with Trade {trade_id} ===")
    print(f"Pair: {test_trade['pair']}")
    print(f"Direction: {test_trade['direction']}")
    print(f"Entry Time: {test_trade['entry_time']}")
    print(f"Close Reason: {test_trade['close_reason']}")
    r_mult = test_trade.get('total_r_multiple', test_trade.get('r_multiple', 0))
    print(f"Total R-Multiple: {r_mult:.2f}R")

    # Load trade context
    try:
        ctx = get_trade_context(run_dir, trade_id, context_bars=20)
        print("\n[OK] Trade context loaded")
    except Exception as e:
        print(f"\n[FAIL] Could not load trade context: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Verify context structure
    required_keys = [
        "trade", "range_bars", "dcrd_per_bar", "dcrd_at_entry",
        "entry_bar_local_idx", "partial_exit_bar_local_idx", "close_bar_local_idx"
    ]

    for key in required_keys:
        if key not in ctx:
            print(f"[FAIL] Missing key: {key}")
            return False

    print(f"[OK] All required keys present")

    # Verify data
    rb = ctx["range_bars"]
    dcrd = ctx["dcrd_at_entry"]

    print(f"\n=== Context Data ===")
    print(f"Range Bars: {len(rb)} bars")
    print(f"Entry Bar Local Idx: {ctx['entry_bar_local_idx']}")
    print(f"Close Bar Local Idx: {ctx['close_bar_local_idx']}")
    print(f"Partial Exit Local Idx: {ctx['partial_exit_bar_local_idx']}")

    print(f"\n=== DCRD at Entry ===")
    print(f"Composite Score: {dcrd['composite_score']:.1f}")
    print(f"Regime: {dcrd['regime']}")
    print(f"L1 Structural: {dcrd['layer1_structural']:.1f}")
    print(f"L2 Modifier: {dcrd['layer2_modifier']:+.1f}")
    print(f"L3 RB Intel: {dcrd['layer3_rb_intelligence']:.1f}")

    # Verify TrendRider debug fields
    if test_trade.get("staircase_depth"):
        print(f"\n=== TrendRider Debug Fields ===")
        print(f"Staircase Depth: {test_trade.get('staircase_depth', 0)} bars")
        print(f"ADX at Entry: {test_trade.get('adx_at_entry', 0):.1f}")
        print(f"ADX Slope Rising: {test_trade.get('adx_slope_rising', False)}")
        print(f"Pullback Bar Idx: {test_trade.get('pullback_bar_idx', 'N/A')}")
        print(f"Entry Bar Idx: {test_trade.get('entry_bar_idx', 'N/A')}")

    # Verify DCRD timeline
    dcrd_per_bar = ctx["dcrd_per_bar"]
    if not dcrd_per_bar.empty:
        print(f"\n[OK] DCRD timeline: {len(dcrd_per_bar)} bars")
    else:
        print(f"\n[WARN] DCRD timeline is empty")

    print(f"\n=== Test Result: PASS ===")
    return True


if __name__ == "__main__":
    success = test_inspector()
    sys.exit(0 if success else 1)
