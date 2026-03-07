"""
JcampFX — Monte Carlo Simulator (Phase 3.4)

Trade sequence randomization to generate probability distributions
for key performance metrics.

Purpose:
  - Test robustness of backtest results
  - Identify worst-case drawdown scenarios
  - Generate statistical confidence intervals
  - Validate that results aren't due to lucky trade sequencing

Method:
  - Shuffle the sequence of closed trades N times (default 10,000)
  - Replay equity curve for each permutation
  - Calculate final equity, max DD, Sharpe, etc.
  - Generate percentile distributions (5th/50th/95th)

Usage:
    python -m backtester.monte_carlo --run-id run_20260227_202447 --iterations 10000
"""

from __future__ import annotations

import argparse
import logging
import random
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from backtester.results import BacktestResults
from backtester.trade import BacktestTrade

log = logging.getLogger(__name__)


@dataclass
class MonteCarloResult:
    """Single Monte Carlo simulation result."""
    iteration: int
    final_equity: float
    max_drawdown_pct: float
    total_return_pct: float
    sharpe_ratio: float
    total_r: float
    win_rate: float
    profit_factor: float

    def to_dict(self) -> dict:
        return {
            'iteration': self.iteration,
            'final_equity': self.final_equity,
            'max_drawdown_pct': self.max_drawdown_pct,
            'total_return_pct': self.total_return_pct,
            'sharpe_ratio': self.sharpe_ratio,
            'total_r': self.total_r,
            'win_rate': self.win_rate,
            'profit_factor': self.profit_factor,
        }


class MonteCarloSimulator:
    """
    Monte Carlo simulator for trade sequence randomization.

    Shuffles completed trades to generate probability distributions
    for performance metrics.
    """

    def __init__(
        self,
        trades: list[BacktestTrade],
        initial_equity: float = 500.0,
        seed: int | None = None,
    ):
        self.trades = trades
        self.initial_equity = initial_equity
        self.seed = seed

        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)

    def simulate_equity_curve(self, shuffled_trades: list[BacktestTrade]) -> tuple[float, float, float]:
        """
        Replay equity curve from shuffled trades.

        Returns:
            (final_equity, max_drawdown_pct, sharpe_ratio)
        """
        equity = self.initial_equity
        peak = equity
        max_dd_pct = 0.0
        equity_points = [equity]

        for trade in shuffled_trades:
            equity += trade.pnl_usd
            equity_points.append(equity)

            # Track peak and drawdown
            if equity > peak:
                peak = equity

            dd_pct = ((peak - equity) / peak) * 100 if peak > 0 else 0.0
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct

        # Calculate Sharpe (simple: mean R / std R * sqrt(252 trading days / avg trade duration))
        r_multiples = [t.r_multiple_total for t in shuffled_trades]
        if len(r_multiples) > 1:
            mean_r = np.mean(r_multiples)
            std_r = np.std(r_multiples, ddof=1)
            if std_r > 0:
                # Annualization factor (assume ~1.3 day avg hold from backtest)
                trades_per_year = 252 / 1.3
                sharpe = mean_r / std_r * np.sqrt(trades_per_year)
            else:
                sharpe = 0.0
        else:
            sharpe = 0.0

        return equity, max_dd_pct, sharpe

    def run_iteration(self, iteration: int) -> MonteCarloResult:
        """Run a single Monte Carlo iteration with shuffled trades."""
        shuffled = self.trades.copy()
        random.shuffle(shuffled)

        final_equity, max_dd_pct, sharpe = self.simulate_equity_curve(shuffled)

        # Calculate metrics
        total_return_pct = ((final_equity - self.initial_equity) / self.initial_equity) * 100
        total_r = sum(t.r_multiple_total for t in shuffled)
        wins = sum(1 for t in shuffled if t.r_multiple_total > 0)
        win_rate = wins / len(shuffled) if shuffled else 0.0

        gross_profit = sum(t.pnl_usd for t in shuffled if t.pnl_usd > 0)
        gross_loss = abs(sum(t.pnl_usd for t in shuffled if t.pnl_usd < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        return MonteCarloResult(
            iteration=iteration,
            final_equity=final_equity,
            max_drawdown_pct=max_dd_pct,
            total_return_pct=total_return_pct,
            sharpe_ratio=sharpe,
            total_r=total_r,
            win_rate=win_rate,
            profit_factor=profit_factor,
        )

    def run(self, iterations: int = 10000, verbose: bool = True) -> list[MonteCarloResult]:
        """
        Run Monte Carlo simulation.

        Args:
            iterations: Number of trade sequence permutations
            verbose: Log progress every 1000 iterations

        Returns:
            List of MonteCarloResult objects
        """
        log.info(f"Starting Monte Carlo simulation: {iterations} iterations, {len(self.trades)} trades")

        results = []
        for i in range(iterations):
            result = self.run_iteration(i)
            results.append(result)

            if verbose and (i + 1) % 1000 == 0:
                log.info(f"  Completed {i + 1}/{iterations} iterations")

        log.info(f"Monte Carlo simulation complete: {iterations} iterations")
        return results


def analyze_results(
    results: list[MonteCarloResult],
    actual_equity: float,
    actual_dd: float,
    actual_sharpe: float,
) -> str:
    """
    Generate statistical analysis report.

    Args:
        results: List of Monte Carlo simulation results
        actual_equity: Actual backtest final equity
        actual_dd: Actual backtest max DD %
        actual_sharpe: Actual backtest Sharpe ratio

    Returns:
        Formatted report string
    """
    df = pd.DataFrame([r.to_dict() for r in results])

    report_lines = []
    report_lines.append("=" * 75)
    report_lines.append("Monte Carlo Simulation Analysis")
    report_lines.append("=" * 75)
    report_lines.append(f"Iterations: {len(results):,}")
    report_lines.append(f"Trades per iteration: 255")
    report_lines.append("")

    # Final Equity Distribution
    report_lines.append("Final Equity Distribution:")
    report_lines.append("-" * 75)
    eq_5th = np.percentile(df['final_equity'], 5)
    eq_50th = np.percentile(df['final_equity'], 50)
    eq_95th = np.percentile(df['final_equity'], 95)
    eq_mean = df['final_equity'].mean()
    eq_std = df['final_equity'].std()

    report_lines.append(f"  5th percentile:  ${eq_5th:8.2f} (worst case)")
    report_lines.append(f"  50th percentile: ${eq_50th:8.2f} (median)")
    report_lines.append(f"  95th percentile: ${eq_95th:8.2f} (best case)")
    report_lines.append(f"  Mean:            ${eq_mean:8.2f}")
    report_lines.append(f"  Std Dev:         ${eq_std:8.2f}")
    report_lines.append(f"  Actual result:   ${actual_equity:8.2f}")

    # Percentile rank of actual result
    eq_rank = (df['final_equity'] <= actual_equity).mean() * 100
    report_lines.append(f"  Actual percentile: {eq_rank:.1f}%")
    report_lines.append("")

    # Max Drawdown Distribution
    report_lines.append("Max Drawdown Distribution:")
    report_lines.append("-" * 75)
    dd_5th = np.percentile(df['max_drawdown_pct'], 5)
    dd_50th = np.percentile(df['max_drawdown_pct'], 50)
    dd_95th = np.percentile(df['max_drawdown_pct'], 95)
    dd_mean = df['max_drawdown_pct'].mean()
    dd_std = df['max_drawdown_pct'].std()

    report_lines.append(f"  5th percentile:  {dd_5th:5.1f}% (best case)")
    report_lines.append(f"  50th percentile: {dd_50th:5.1f}% (median)")
    report_lines.append(f"  95th percentile: {dd_95th:5.1f}% (worst case)")
    report_lines.append(f"  Mean:            {dd_mean:5.1f}%")
    report_lines.append(f"  Std Dev:         {dd_std:5.1f}%")
    report_lines.append(f"  Actual result:   {actual_dd:5.1f}%")

    dd_rank = (df['max_drawdown_pct'] <= actual_dd).mean() * 100
    report_lines.append(f"  Actual percentile: {dd_rank:.1f}%")
    report_lines.append("")

    # Sharpe Ratio Distribution
    report_lines.append("Sharpe Ratio Distribution:")
    report_lines.append("-" * 75)
    sharpe_5th = np.percentile(df['sharpe_ratio'], 5)
    sharpe_50th = np.percentile(df['sharpe_ratio'], 50)
    sharpe_95th = np.percentile(df['sharpe_ratio'], 95)
    sharpe_mean = df['sharpe_ratio'].mean()

    report_lines.append(f"  5th percentile:  {sharpe_5th:5.2f} (worst case)")
    report_lines.append(f"  50th percentile: {sharpe_50th:5.2f} (median)")
    report_lines.append(f"  95th percentile: {sharpe_95th:5.2f} (best case)")
    report_lines.append(f"  Mean:            {sharpe_mean:5.2f}")
    report_lines.append(f"  Actual result:   {actual_sharpe:5.2f}")

    sharpe_rank = (df['sharpe_ratio'] <= actual_sharpe).mean() * 100
    report_lines.append(f"  Actual percentile: {sharpe_rank:.1f}%")
    report_lines.append("")

    # Probability Analysis
    report_lines.append("Probability Analysis:")
    report_lines.append("-" * 75)
    prob_profitable = (df['final_equity'] > results[0].final_equity - df['final_equity'].iloc[0]).mean() * 100
    prob_dd_20 = (df['max_drawdown_pct'] > 20.0).mean() * 100
    prob_dd_25 = (df['max_drawdown_pct'] > 25.0).mean() * 100
    prob_dd_30 = (df['max_drawdown_pct'] > 30.0).mean() * 100
    prob_sharpe_gt1 = (df['sharpe_ratio'] > 1.0).mean() * 100

    report_lines.append(f"  Probability of profit:     {prob_profitable:5.1f}%")
    report_lines.append(f"  Probability DD > 20%:      {prob_dd_20:5.1f}%")
    report_lines.append(f"  Probability DD > 25%:      {prob_dd_25:5.1f}%")
    report_lines.append(f"  Probability DD > 30%:      {prob_dd_30:5.1f}%")
    report_lines.append(f"  Probability Sharpe > 1.0:  {prob_sharpe_gt1:5.1f}%")
    report_lines.append("")

    # Interpretation
    report_lines.append("Interpretation:")
    report_lines.append("-" * 75)

    if eq_rank > 40 and eq_rank < 60:
        report_lines.append("  [+] Actual equity near median - typical result")
    elif eq_rank < 25:
        report_lines.append("  [!] Actual equity below 25th percentile - below average sequencing")
    elif eq_rank > 75:
        report_lines.append("  [!] Actual equity above 75th percentile - above average sequencing")

    if dd_rank < 50:
        report_lines.append("  [+] Actual DD below median - favorable drawdown sequencing")
    else:
        report_lines.append("  [-] Actual DD above median - unfavorable drawdown sequencing")

    if prob_dd_25 < 10:
        report_lines.append("  [+] Low probability (<10%) of extreme DD (>25%)")
    elif prob_dd_25 > 25:
        report_lines.append("  [!] High probability (>25%) of extreme DD (>25%) - risky")

    if prob_sharpe_gt1 > 80:
        report_lines.append("  [+] High confidence (>80%) of Sharpe > 1.0")
    elif prob_sharpe_gt1 < 60:
        report_lines.append("  [!] Lower confidence (<60%) of Sharpe > 1.0")

    report_lines.append("=" * 75)

    return "\n".join(report_lines)


def load_backtest_trades(run_dir: Path) -> tuple[list[BacktestTrade], float, float, float]:
    """
    Load trades from backtest results directory.

    Returns:
        (trades, actual_final_equity, actual_max_dd, actual_sharpe)
    """
    trades_path = run_dir / "trades.parquet"
    equity_path = run_dir / "equity.parquet"
    dd_path = run_dir / "drawdown.parquet"

    if not trades_path.exists():
        raise FileNotFoundError(f"Trades file not found: {trades_path}")

    # Load trades
    df_trades = pd.read_parquet(trades_path)
    trades = []

    for _, row in df_trades.iterrows():
        # Calculate initial_r_pips from SL distance
        sl_distance_price = abs(row['entry_price'] - row['sl_price'])
        # Get pip size from pair name (simple heuristic)
        pip_size = 0.01 if 'JPY' in row['pair'] else 0.0001
        initial_r_pips = sl_distance_price / pip_size

        trade = BacktestTrade(
            trade_id=row['trade_id'],
            pair=row['pair'],
            direction=row['direction'],
            strategy=row['strategy'],
            entry_time=row['entry_time'],
            entry_price=row['entry_price'],
            sl_price=row['sl_price'],
            lot_size=row['lot_size'],
            initial_r_pips=initial_r_pips,
            composite_score=row.get('composite_score', 50.0),
            partial_exit_pct=row.get('partial_exit_pct', 0.70),
        )
        # Set completed trade data
        trade.close_price = row['close_price']
        trade.close_time = row['close_time']
        trade.close_reason = row['close_reason']
        trade.r_multiple_total = row['r_multiple_total']
        trade.pnl_usd = row['pnl_usd']
        trade.phase = "closed"

        trades.append(trade)

    # Load actual metrics
    if equity_path.exists():
        df_equity = pd.read_parquet(equity_path)
        actual_final_equity = df_equity['equity'].iloc[-1]
    else:
        actual_final_equity = 500.0 + df_trades['pnl_usd'].sum()

    if dd_path.exists():
        df_dd = pd.read_parquet(dd_path)
        actual_max_dd = df_dd['drawdown'].max()
    else:
        actual_max_dd = 0.0

    # Calculate actual Sharpe (simplified)
    r_multiples = df_trades['r_multiple_total'].values
    if len(r_multiples) > 1:
        mean_r = np.mean(r_multiples)
        std_r = np.std(r_multiples, ddof=1)
        if std_r > 0:
            trades_per_year = 252 / 1.3
            actual_sharpe = mean_r / std_r * np.sqrt(trades_per_year)
        else:
            actual_sharpe = 0.0
    else:
        actual_sharpe = 0.0

    return trades, actual_final_equity, actual_max_dd, actual_sharpe


def main():
    parser = argparse.ArgumentParser(description="JcampFX Monte Carlo Simulator")
    parser.add_argument("--run-id", required=True, help="Backtest run ID (e.g., run_20260227_202447)")
    parser.add_argument("--iterations", type=int, default=10000, help="Number of simulations (default: 10000)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Locate run directory
    run_dir = Path(f"data/backtest_results/{args.run_id}")
    if not run_dir.exists():
        log.error(f"Run directory not found: {run_dir}")
        return 1

    # Load trades and actual metrics
    log.info(f"Loading backtest results from {run_dir}")
    trades, actual_equity, actual_dd, actual_sharpe = load_backtest_trades(run_dir)
    log.info(f"Loaded {len(trades)} trades")
    log.info(f"Actual results: Equity=${actual_equity:.2f}, DD={actual_dd:.1f}%, Sharpe={actual_sharpe:.2f}")

    # Run Monte Carlo
    simulator = MonteCarloSimulator(trades, initial_equity=500.0, seed=args.seed)
    results = simulator.run(iterations=args.iterations, verbose=True)

    # Generate report
    report = analyze_results(results, actual_equity, actual_dd, actual_sharpe)
    print("\n" + report)

    # Save results
    output_path = run_dir / "monte_carlo.parquet"
    df_results = pd.DataFrame([r.to_dict() for r in results])
    df_results.to_parquet(output_path, compression='snappy')
    log.info(f"Saved Monte Carlo results to {output_path}")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
