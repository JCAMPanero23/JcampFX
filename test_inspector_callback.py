"""
Test Inspector callback functions directly
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from dashboard.pages.inspector import _parse_query_string, _build_metadata_panel, _build_inspector_chart
from backtester.playback import get_trade_context

def test_inspector_functions():
    """Test Inspector helper functions"""

    # Test 1: Parse query string
    print("=== Test 1: Parse Query String ===")
    search = "?run=run_20260219_190902&trade=bf225d8f"
    params = _parse_query_string(search)
    print(f"Input: {search}")
    print(f"Parsed: {params}")
    assert params["run"] == "run_20260219_190902"
    assert params["trade"] == "bf225d8f"
    print("PASS\n")

    # Test 2: Load trade context
    print("=== Test 2: Load Trade Context ===")
    run_dir = "data/backtest_results/run_20260219_190902"
    trade_id = "bf225d8f"
    ctx = get_trade_context(run_dir, trade_id, context_bars=20)
    print(f"Loaded context for trade {trade_id}")
    print(f"  Range bars: {len(ctx['range_bars'])} bars")
    print(f"  Entry local idx: {ctx['entry_bar_local_idx']}")
    print(f"  DCRD CS: {ctx['dcrd_at_entry']['composite_score']:.1f}")
    print("PASS\n")

    # Test 3: Build metadata panel
    print("=== Test 3: Build Metadata Panel ===")
    panel = _build_metadata_panel(ctx)
    print(f"Panel type: {type(panel).__name__}")
    print(f"Panel has children: {hasattr(panel, 'children')}")
    if hasattr(panel, 'children'):
        print(f"Number of elements: {len(panel.children)}")
    print("PASS\n")

    # Test 4: Build chart
    print("=== Test 4: Build Inspector Chart ===")
    fig = _build_inspector_chart(ctx)
    print(f"Figure type: {type(fig).__name__}")
    print(f"Number of traces: {len(fig.data)}")
    print(f"Number of subplots: {len(fig.layout.annotations) if fig.layout.annotations else 0}")
    print("PASS\n")

    print("=== All Tests Passed ===")
    return True


if __name__ == "__main__":
    try:
        success = test_inspector_functions()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
