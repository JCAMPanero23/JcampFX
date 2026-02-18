"""
JcampFX — Backtester package (Phase 3)

Custom event-driven Range Bar replay engine with walk-forward validation.

Usage:
    from backtester.engine import BacktestEngine
    from backtester.walk_forward import WalkForwardManager

    engine = BacktestEngine(pairs=["EURUSD", "GBPUSD", "USDJPY"])
    wf = WalkForwardManager()
    results = wf.run_all(engine, pairs, data_start, data_end)
    print(results.validation_report())
"""

from backtester.engine import BacktestEngine
from backtester.results import BacktestResults, CycleResult
from backtester.walk_forward import WalkForwardManager

__all__ = [
    "BacktestEngine",
    "BacktestResults",
    "CycleResult",
    "WalkForwardManager",
]
