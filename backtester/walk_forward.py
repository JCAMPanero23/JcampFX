"""
JcampFX — Walk-Forward Manager (Phase 3, PRD §9.1 + V3.3)

Generates 4-month train / 2-month test cycles and orchestrates
out-of-sample gate validation.

Walk-forward structure (4 cycles × 6 months = 24 months):
  Cycle 1: Train Jan–Apr 2023 | Test May–Jun 2023
  Cycle 2: Train Jul–Oct 2023 | Test Nov–Dec 2023
  Cycle 3: Train Jan–Apr 2024 | Test May–Jun 2024
  Cycle 4: Train Jul–Oct 2024 | Test Nov–Dec 2024

V3.3 gate: each test period must be profitable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional

import pandas as pd
from dateutil.relativedelta import relativedelta

from backtester.results import BacktestResults, CycleResult
from src.config import (
    WALK_FORWARD_CYCLES,
    WALK_FORWARD_TEST_MONTHS,
    WALK_FORWARD_TRAIN_MONTHS,
)

log = logging.getLogger(__name__)


@dataclass
class WalkForwardCycle:
    cycle_num: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp

    def __str__(self) -> str:
        return (
            f"Cycle {self.cycle_num}: "
            f"Train {self.train_start.date()} → {self.train_end.date()} | "
            f"Test {self.test_start.date()} → {self.test_end.date()}"
        )


class WalkForwardManager:
    """
    Generates walk-forward cycles and runs the backtest engine on each.

    Each cycle runs the FULL period (train + test) so account state is
    warmed up correctly; only the test period results feed the V3.3 gate.
    """

    def generate_cycles(
        self,
        data_start: pd.Timestamp,
        data_end: pd.Timestamp,
        train_months: int = WALK_FORWARD_TRAIN_MONTHS,
        test_months: int = WALK_FORWARD_TEST_MONTHS,
    ) -> list[WalkForwardCycle]:
        """
        Generate non-overlapping train/test cycle pairs.

        Advances by (train + test) months each iteration.
        Stops when there isn't enough data for a complete test period.
        """
        cycles: list[WalkForwardCycle] = []
        cycle_num = 1
        period_start = data_start

        while True:
            train_start = period_start
            train_end = train_start + relativedelta(months=train_months) - pd.Timedelta(days=1)
            test_start = train_end + pd.Timedelta(days=1)
            test_end = test_start + relativedelta(months=test_months) - pd.Timedelta(days=1)

            # Stop if test period extends beyond available data
            if test_end > data_end:
                break

            cycles.append(WalkForwardCycle(
                cycle_num=cycle_num,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
            ))

            period_start = test_end + pd.Timedelta(days=1)
            cycle_num += 1

        log.info("Generated %d walk-forward cycles", len(cycles))
        for c in cycles:
            log.info("  %s", c)
        return cycles

    def run_all(
        self,
        engine,  # BacktestEngine (imported at call time to avoid circular imports)
        pairs: list[str],
        data_start: pd.Timestamp,
        data_end: pd.Timestamp,
        initial_equity: float = 500.0,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> BacktestResults:
        """
        Run all walk-forward cycles and aggregate into a single BacktestResults.

        For each cycle:
          1. Run backtest on [train_start, test_end] (full warm-up + test window)
          2. Extract test-period trades for the gate check
          3. Aggregate into combined equity curve

        Returns a BacktestResults with:
          - cycles: list[CycleResult] (test period stats)
          - all_trades: all trades across ALL cycles (for Cinema display)
          - equity_curve: continuous equity across all cycles
        """
        cycles = self.generate_cycles(data_start, data_end)
        if not cycles:
            log.warning("No walk-forward cycles generated for range %s → %s",
                        data_start.date(), data_end.date())
            return BacktestResults(initial_equity=initial_equity)

        all_cycle_results: list[CycleResult] = []
        all_trades = []
        equity_points = []
        running_equity = initial_equity

        for i, cycle in enumerate(cycles):
            log.info("Running cycle %d/%d: %s", i + 1, len(cycles), cycle)
            if progress_cb:
                progress_cb(i + 1, len(cycles))

            # Run full cycle period (train + test) — fresh account each cycle
            results = engine.run(
                start=cycle.train_start,
                end=cycle.test_end,
                initial_equity=running_equity,
            )

            # Extract test-period trades for gate check
            test_trades = [
                t for t in results.all_trades
                if t.entry_time is not None and t.entry_time >= cycle.test_start
            ]

            cycle_result = CycleResult(
                cycle_num=cycle.cycle_num,
                train_start=cycle.train_start,
                train_end=cycle.train_end,
                test_start=cycle.test_start,
                test_end=cycle.test_end,
                test_trades=test_trades,
                start_equity=running_equity,
                end_equity=running_equity + results.net_profit_usd(),
            )
            all_cycle_results.append(cycle_result)
            all_trades.extend(results.all_trades)

            # Carry equity forward for next cycle
            running_equity += results.net_profit_usd()

            # Append equity points
            if results.equity_curve is not None:
                equity_points.append(results.equity_curve)

            log.info("  %s", cycle_result.summary())

        # Build combined equity curve
        combined_equity = None
        if equity_points:
            combined_equity = pd.concat(equity_points).sort_index()
            combined_equity = combined_equity[~combined_equity.index.duplicated(keep="last")]

        combined = BacktestResults(
            cycles=all_cycle_results,
            all_trades=all_trades,
            equity_curve=combined_equity,
            initial_equity=initial_equity,
        )

        # Build drawdown curve
        if combined_equity is not None:
            combined.drawdown_curve = _compute_drawdown(combined_equity, initial_equity)

        log.info(
            "Walk-forward complete: %d/%d cycles passed | Net PnL $%.2f",
            combined.cycles_passed(), len(all_cycle_results), combined.net_profit_usd()
        )
        return combined


def _compute_drawdown(equity: pd.Series, initial_equity: float) -> pd.Series:
    """Return peak-to-trough drawdown % at each point in the equity series."""
    peak = initial_equity
    dd_values = []
    for eq in equity.values:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak * 100.0 if peak > 0 else 0.0
        dd_values.append(dd)
    return pd.Series(dd_values, index=equity.index, name="drawdown_pct")
