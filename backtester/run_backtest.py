"""
JcampFX — Backtester CLI (Phase 3)

Run the backtest from the command line.

Examples:
    # Full walk-forward (all 5 pairs, 2 years, 4 cycles):
    python -m backtester.run_backtest --walk-forward

    # Single pair, custom date range:
    python -m backtester.run_backtest --pair EURUSD --start 2023-01-01 --end 2024-12-31

    # All pairs, 2 years (no walk-forward):
    python -m backtester.run_backtest --all-pairs --years 2

Results are saved to data/backtest_results/ and the validation report is printed.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# Ensure project root is on sys.path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backtester.engine import BacktestEngine
from backtester.walk_forward import WalkForwardManager
from src.config import BACKTEST_RESULTS_DIR, PAIRS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("run_backtest")


def _utc(dt_str: str) -> pd.Timestamp:
    return pd.Timestamp(dt_str, tz="UTC")


def main() -> None:
    parser = argparse.ArgumentParser(description="JcampFX Phase 3 Backtester")

    pair_group = parser.add_mutually_exclusive_group()
    pair_group.add_argument("--pair", type=str, help="Single pair (e.g. EURUSD)")
    pair_group.add_argument("--all-pairs", action="store_true",
                            help="Run all 5 active pairs (default)")

    parser.add_argument("--walk-forward", action="store_true",
                        help="Run 4-cycle walk-forward validation")
    parser.add_argument("--start", type=str, default=None,
                        help="Start date YYYY-MM-DD (UTC)")
    parser.add_argument("--end", type=str, default=None,
                        help="End date YYYY-MM-DD (UTC)")
    parser.add_argument("--years", type=int, default=2,
                        help="Years of history to replay (default: 2)")
    parser.add_argument("--equity", type=float, default=500.0,
                        help="Starting equity in USD (default: 500)")
    parser.add_argument("--data-dir", type=str, default="data",
                        help="Data directory (default: data)")
    parser.add_argument("--output", type=str, default=None,
                        help="Override output directory")

    args = parser.parse_args()

    # Resolve pairs
    if args.pair:
        pairs = [args.pair.upper()]
    else:
        pairs = list(PAIRS)

    # Resolve date range
    if args.end:
        end = _utc(args.end)
    else:
        end = pd.Timestamp.now(tz="UTC").normalize() - pd.Timedelta(days=1)

    if args.start:
        start = _utc(args.start)
    else:
        start = end - pd.DateOffset(years=args.years)

    log.info("Pairs: %s", pairs)
    log.info("Window: %s → %s", start.date(), end.date())
    log.info("Initial equity: $%.2f", args.equity)

    engine = BacktestEngine(pairs=pairs, data_dir=args.data_dir)

    if args.walk_forward:
        log.info("Running walk-forward validation (4 cycles)...")
        wf = WalkForwardManager()
        results = wf.run_all(
            engine=engine,
            pairs=pairs,
            data_start=start,
            data_end=end,
            initial_equity=args.equity,
        )
    else:
        log.info("Running single backtest run...")
        results = engine.run(start=start, end=end, initial_equity=args.equity)

    # Print validation report
    print("\n" + results.validation_report())

    # Save results
    out_dir = args.output or BACKTEST_RESULTS_DIR
    ts_tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    save_path = Path(out_dir) / f"run_{ts_tag}"
    results.save(str(save_path))
    log.info("Results saved to %s", save_path)


if __name__ == "__main__":
    main()
