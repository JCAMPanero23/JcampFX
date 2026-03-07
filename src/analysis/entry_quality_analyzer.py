"""
Entry Quality Analyzer - Phase 3.4.1 Task 1.1

Analyzes all trades to identify failure patterns.
Compares SL_HIT trades vs successful trades (partial-reach) to find:
- Pullback depth issues
- SL distance problems
- Session timing patterns
- DCRD momentum correlation
- Staircase quality differences
"""

import logging
from pathlib import Path
from typing import Dict, Any
import pandas as pd
import numpy as np
from datetime import datetime

from src.config import PIP_SIZE, RANGE_BAR_PIPS

log = logging.getLogger(__name__)


class EntryQualityAnalyzer:
    """Analyze entry quality patterns from backtest results."""

    def __init__(self, run_id: str):
        """
        Initialize analyzer with a backtest run.

        Args:
            run_id: Backtest run ID (e.g., "run_20260222_083218")
        """
        self.run_id = run_id
        self.run_dir = Path("data/backtest_results") / run_id

        if not self.run_dir.exists():
            raise FileNotFoundError(f"Run directory not found: {self.run_dir}")

        # Load data
        log.info(f"Loading backtest data from {run_id}")
        self.trades_df = pd.read_parquet(self.run_dir / "trades.parquet")
        self.range_bars_cache = {}  # Lazy load per pair

        log.info(f"Loaded {len(self.trades_df)} trades")

    def load_range_bars(self, pair: str) -> pd.DataFrame:
        """Lazy load range bars for a pair."""
        if pair not in self.range_bars_cache:
            # Determine bar size for this pair
            bar_size = RANGE_BAR_PIPS.get(pair, 20)
            rb_path = Path("data/range_bars") / f"{pair}_RB{bar_size}.parquet"

            if not rb_path.exists():
                log.warning(f"Range bar file not found: {rb_path}")
                return pd.DataFrame()

            rb_df = pd.read_parquet(rb_path)
            rb_df["start_time"] = pd.to_datetime(rb_df["start_time"], utc=True)
            rb_df["end_time"] = pd.to_datetime(rb_df["end_time"], utc=True)
            self.range_bars_cache[pair] = rb_df

        return self.range_bars_cache[pair]

    def analyze_all(self) -> Dict[str, Any]:
        """
        Run complete entry quality analysis.

        Returns:
            Dictionary with analysis results
        """
        log.info("Starting entry quality analysis...")

        # Segment trades
        sl_hits = self.trades_df[self.trades_df["close_reason"] == "SL_HIT"].copy()
        partial_reaches = self.trades_df[self.trades_df["partial_exit_time"].notna()].copy()

        log.info(f"SL_HIT trades: {len(sl_hits)} ({len(sl_hits)/len(self.trades_df)*100:.1f}%)")
        log.info(f"Partial-reach trades: {len(partial_reaches)} ({len(partial_reaches)/len(self.trades_df)*100:.1f}%)")

        # Calculate metrics for each group
        log.info("Analyzing SL_HIT group...")
        sl_hit_metrics = self._analyze_group(sl_hits, "SL_HIT")

        log.info("Analyzing partial-reach group...")
        partial_metrics = self._analyze_group(partial_reaches, "PARTIAL_REACH")

        # Compare groups
        log.info("Comparing groups...")
        comparison = self._compare_groups(sl_hit_metrics, partial_metrics)

        results = {
            "run_id": self.run_id,
            "total_trades": len(self.trades_df),
            "sl_hit_count": len(sl_hits),
            "partial_reach_count": len(partial_reaches),
            "sl_hit_rate": len(sl_hits) / len(self.trades_df) if len(self.trades_df) > 0 else 0,
            "sl_hit_metrics": sl_hit_metrics,
            "partial_reach_metrics": partial_metrics,
            "comparison": comparison,
        }

        return results

    def _analyze_group(self, trades: pd.DataFrame, group_name: str) -> Dict[str, Any]:
        """
        Analyze a group of trades (SL_HIT or partial-reach).

        Args:
            trades: DataFrame of trades to analyze
            group_name: "SL_HIT" or "PARTIAL_REACH"

        Returns:
            Dictionary with metrics
        """
        if len(trades) == 0:
            return {}

        metrics = {}

        # 1. Basic stats
        metrics["count"] = len(trades)
        metrics["avg_r_multiple"] = trades["r_multiple_total"].mean()
        metrics["avg_pnl"] = trades["pnl_usd"].mean()  # Fixed: column is pnl_usd, not pnl

        # 2. Pair distribution
        metrics["pair_distribution"] = trades["pair"].value_counts().to_dict()

        # 3. Strategy distribution
        metrics["strategy_distribution"] = trades["strategy"].value_counts().to_dict()

        # 4. Session analysis
        metrics["session_distribution"] = self._analyze_sessions(trades)

        # 5. SL distance analysis (calculate from entry and SL prices)
        sl_distance_pips = []
        for idx, trade in trades.iterrows():
            pip = PIP_SIZE.get(trade["pair"], 0.0001)
            sl_dist = abs(trade["entry_price"] - trade["sl_price"]) / pip
            sl_distance_pips.append(sl_dist)

        sl_dist_series = pd.Series(sl_distance_pips)
        metrics["sl_distance_stats"] = {
            "mean_r_pips": sl_dist_series.mean(),
            "median_r_pips": sl_dist_series.median(),
            "min_r_pips": sl_dist_series.min(),
            "max_r_pips": sl_dist_series.max(),
        }

        # 6. DCRD score distribution
        metrics["dcrd_stats"] = {
            "mean_cs": trades["composite_score"].mean(),
            "median_cs": trades["composite_score"].median(),
            "min_cs": trades["composite_score"].min(),
            "max_cs": trades["composite_score"].max(),
        }

        # 7. Per-trade detailed analysis (sample up to 50 trades)
        sample_trades = trades.head(min(50, len(trades)))
        detailed = []

        for idx, trade in sample_trades.iterrows():
            detail = self._analyze_single_trade(trade)
            if detail:
                detailed.append(detail)

        metrics["detailed_sample"] = detailed

        # 8. Aggregate detailed metrics
        if detailed:
            metrics["aggregated_detailed"] = self._aggregate_detailed_metrics(detailed)

        return metrics

    def _analyze_single_trade(self, trade: pd.Series) -> Dict[str, Any]:
        """
        Analyze a single trade in detail.

        Args:
            trade: Trade row from trades_df

        Returns:
            Dictionary with detailed metrics
        """
        try:
            pair = trade["pair"]
            rb_df = self.load_range_bars(pair)

            if rb_df.empty:
                return None

            # Find entry bar
            entry_time = pd.to_datetime(trade["entry_time"], utc=True)
            entry_bar_idx = self._find_bar_at_time(rb_df, entry_time)

            if entry_bar_idx is None or entry_bar_idx < 20:
                return None  # Need context

            # Get context bars
            lookback = 20
            context = rb_df.iloc[entry_bar_idx - lookback : entry_bar_idx + 1].copy()

            if len(context) < 10:
                return None

            # Calculate metrics
            detail = {
                "trade_id": trade["trade_id"],
                "pair": pair,
                "strategy": trade["strategy"],
                "direction": trade["direction"],
                "entry_price": trade["entry_price"],
                "sl_price": trade["sl_price"],
                "composite_score": trade["composite_score"],
                "r_multiple": trade["r_multiple_total"],
                "pnl": trade.get("pnl_usd", 0),  # Fixed: use pnl_usd
            }

            # 1. Pullback depth analysis
            pullback_metrics = self._calculate_pullback_depth(context, trade)
            detail.update(pullback_metrics)

            # 2. Staircase quality
            staircase_metrics = self._calculate_staircase_quality(context, trade)
            detail.update(staircase_metrics)

            # 3. SL distance vs ATR
            atr_metrics = self._calculate_atr_analysis(context, trade)
            detail.update(atr_metrics)

            # 4. Entry timing within bar
            timing_metrics = self._calculate_entry_timing(context, trade)
            detail.update(timing_metrics)

            # 5. DCRD momentum
            dcrd_momentum = self._calculate_dcrd_momentum(trade, entry_bar_idx)
            detail.update(dcrd_momentum)

            return detail

        except Exception as e:
            log.warning(f"Failed to analyze trade {trade.get('trade_id', 'unknown')}: {e}")
            return None

    def _calculate_pullback_depth(self, context: pd.DataFrame, trade: pd.Series) -> Dict[str, float]:
        """Calculate pullback depth metrics."""
        direction = trade["direction"]
        entry_price = trade["entry_price"]

        # Find the impulse (staircase) before entry
        # Look back to find highest high (BUY) or lowest low (SELL) in last 10 bars
        lookback = min(10, len(context) - 1)
        recent_bars = context.iloc[-lookback-1:-1]  # Exclude entry bar

        if direction == "BUY":
            impulse_high = recent_bars["high"].max()
            impulse_low = recent_bars["low"].min()
            pullback_depth = (impulse_high - entry_price) / (impulse_high - impulse_low) if impulse_high > impulse_low else 0
        else:  # SELL
            impulse_high = recent_bars["high"].max()
            impulse_low = recent_bars["low"].min()
            pullback_depth = (entry_price - impulse_low) / (impulse_high - impulse_low) if impulse_high > impulse_low else 0

        return {
            "pullback_depth_pct": pullback_depth * 100 if pullback_depth > 0 else 0,
            "impulse_range_pips": abs(impulse_high - impulse_low) / PIP_SIZE.get(trade["pair"], 0.0001),
        }

    def _calculate_staircase_quality(self, context: pd.DataFrame, trade: pd.Series) -> Dict[str, Any]:
        """Calculate staircase quality metrics."""
        direction = trade["direction"]

        # Count consecutive directional bars before entry
        lookback = min(15, len(context) - 1)
        recent_bars = context.iloc[-lookback-1:-1]

        staircase_depth = 0
        for i in range(len(recent_bars) - 1, 0, -1):
            current = recent_bars.iloc[i]
            previous = recent_bars.iloc[i - 1]

            if direction == "BUY":
                # Higher high and higher low
                if current["high"] > previous["high"] and current["low"] > previous["low"]:
                    staircase_depth += 1
                else:
                    break
            else:  # SELL
                # Lower low and lower high
                if current["low"] < previous["low"] and current["high"] < previous["high"]:
                    staircase_depth += 1
                else:
                    break

        return {
            "staircase_depth": staircase_depth,
        }

    def _calculate_atr_analysis(self, context: pd.DataFrame, trade: pd.Series) -> Dict[str, float]:
        """Calculate ATR-based SL analysis."""
        # Calculate ATR(14) at entry
        atr_period = 14
        if len(context) < atr_period:
            return {"atr_14": 0, "sl_to_atr_ratio": 0}

        recent = context.tail(atr_period).copy()

        # Calculate True Range
        recent["tr"] = recent.apply(
            lambda row: max(
                row["high"] - row["low"],
                abs(row["high"] - row["close"]),
                abs(row["low"] - row["close"])
            ),
            axis=1
        )

        atr_14 = recent["tr"].mean()

        # Compare SL distance to ATR
        pip = PIP_SIZE.get(trade["pair"], 0.0001)
        sl_distance_price = abs(trade["entry_price"] - trade["sl_price"])
        sl_to_atr_ratio = sl_distance_price / atr_14 if atr_14 > 0 else 0

        return {
            "atr_14_pips": atr_14 / pip,
            "sl_distance_pips": sl_distance_price / pip,
            "sl_to_atr_ratio": sl_to_atr_ratio,
        }

    def _calculate_entry_timing(self, context: pd.DataFrame, trade: pd.Series) -> Dict[str, Any]:
        """Calculate entry timing within bar."""
        entry_bar = context.iloc[-1]

        # Where in the bar did we enter? (approximation)
        # Entry is at bar close for TrendRider
        entry_price = trade["entry_price"]
        bar_open = entry_bar["open"]
        bar_close = entry_bar["close"]
        bar_high = entry_bar["high"]
        bar_low = entry_bar["low"]

        # Entry position within bar (0 = low, 1 = high)
        bar_range = bar_high - bar_low
        entry_position = (entry_price - bar_low) / bar_range if bar_range > 0 else 0.5

        return {
            "entry_position_in_bar": entry_position,  # 0-1 scale
            "bar_direction": "bullish" if bar_close > bar_open else "bearish",
        }

    def _calculate_dcrd_momentum(self, trade: pd.Series, entry_bar_idx: int) -> Dict[str, float]:
        """Calculate DCRD momentum at entry (if available)."""
        # TODO: This requires loading DCRD history from backtest
        # For now, return placeholder
        return {
            "dcrd_momentum": 0,  # Placeholder: slope of CS over last 3 bars
        }

    def _analyze_sessions(self, trades: pd.DataFrame) -> Dict[str, int]:
        """Analyze session distribution."""
        # Simple session detection based on hour (UTC)
        sessions = []
        for entry_time in trades["entry_time"]:
            dt = pd.to_datetime(entry_time, utc=True)
            hour = dt.hour

            # Approximate sessions (UTC):
            # Tokyo: 00:00-09:00
            # London: 08:00-17:00
            # NY: 13:00-22:00
            if 0 <= hour < 8:
                session = "TOKYO"
            elif 8 <= hour < 13:
                session = "LONDON"
            elif 13 <= hour < 17:
                session = "LONDON_NY_OVERLAP"
            elif 17 <= hour < 22:
                session = "NY"
            else:
                session = "OFF_HOURS"

            sessions.append(session)

        return pd.Series(sessions).value_counts().to_dict()

    def _find_bar_at_time(self, rb_df: pd.DataFrame, target_time: pd.Timestamp) -> int:
        """Find the index of the bar that contains target_time."""
        # Find bar where start_time <= target_time <= end_time
        mask = (rb_df["start_time"] <= target_time) & (rb_df["end_time"] >= target_time)
        matches = rb_df[mask]

        if len(matches) > 0:
            return matches.index[0]

        # Fallback: find closest end_time
        time_diffs = (rb_df["end_time"] - target_time).abs()
        closest_idx = time_diffs.idxmin()
        return closest_idx

    def _aggregate_detailed_metrics(self, detailed: list) -> Dict[str, Any]:
        """Aggregate detailed metrics across trades."""
        df = pd.DataFrame(detailed)

        agg = {
            "avg_pullback_depth_pct": df["pullback_depth_pct"].mean(),
            "median_pullback_depth_pct": df["pullback_depth_pct"].median(),
            "avg_staircase_depth": df["staircase_depth"].mean(),
            "median_staircase_depth": df["staircase_depth"].median(),
            "avg_sl_to_atr_ratio": df["sl_to_atr_ratio"].mean(),
            "median_sl_to_atr_ratio": df["sl_to_atr_ratio"].median(),
            "avg_entry_position_in_bar": df["entry_position_in_bar"].mean(),
        }

        # Distribution bins
        agg["pullback_depth_bins"] = self._create_bins(df["pullback_depth_pct"], [0, 30, 50, 70, 100])
        agg["staircase_depth_bins"] = self._create_bins(df["staircase_depth"], [0, 3, 5, 7, 10, 20])
        agg["sl_to_atr_bins"] = self._create_bins(df["sl_to_atr_ratio"], [0, 1.5, 2.0, 2.5, 3.0, 5.0])

        return agg

    def _create_bins(self, series: pd.Series, bins: list) -> Dict[str, int]:
        """Create histogram bins."""
        binned = pd.cut(series, bins=bins, include_lowest=True)
        return binned.value_counts().to_dict()

    def _compare_groups(self, sl_hit_metrics: Dict, partial_metrics: Dict) -> Dict[str, Any]:
        """Compare SL_HIT vs partial-reach metrics."""
        comparison = {}

        if not sl_hit_metrics or not partial_metrics:
            return comparison

        # Compare aggregated detailed metrics
        if "aggregated_detailed" in sl_hit_metrics and "aggregated_detailed" in partial_metrics:
            sl_agg = sl_hit_metrics["aggregated_detailed"]
            partial_agg = partial_metrics["aggregated_detailed"]

            comparison["pullback_depth"] = {
                "sl_hit_avg": sl_agg.get("avg_pullback_depth_pct", 0),
                "partial_avg": partial_agg.get("avg_pullback_depth_pct", 0),
                "difference": partial_agg.get("avg_pullback_depth_pct", 0) - sl_agg.get("avg_pullback_depth_pct", 0),
            }

            comparison["staircase_depth"] = {
                "sl_hit_avg": sl_agg.get("avg_staircase_depth", 0),
                "partial_avg": partial_agg.get("avg_staircase_depth", 0),
                "difference": partial_agg.get("avg_staircase_depth", 0) - sl_agg.get("avg_staircase_depth", 0),
            }

            comparison["sl_to_atr_ratio"] = {
                "sl_hit_avg": sl_agg.get("avg_sl_to_atr_ratio", 0),
                "partial_avg": partial_agg.get("avg_sl_to_atr_ratio", 0),
                "difference": partial_agg.get("avg_sl_to_atr_ratio", 0) - sl_agg.get("avg_sl_to_atr_ratio", 0),
            }

        # Compare DCRD scores
        comparison["dcrd_score"] = {
            "sl_hit_avg": sl_hit_metrics.get("dcrd_stats", {}).get("mean_cs", 0),
            "partial_avg": partial_metrics.get("dcrd_stats", {}).get("mean_cs", 0),
            "difference": partial_metrics.get("dcrd_stats", {}).get("mean_cs", 0) - sl_hit_metrics.get("dcrd_stats", {}).get("mean_cs", 0),
        }

        # Compare session distributions
        sl_sessions = sl_hit_metrics.get("session_distribution", {})
        partial_sessions = partial_metrics.get("session_distribution", {})

        all_sessions = set(sl_sessions.keys()) | set(partial_sessions.keys())
        session_comparison = {}
        for session in all_sessions:
            sl_count = sl_sessions.get(session, 0)
            partial_count = partial_sessions.get(session, 0)
            total = sl_count + partial_count
            if total > 0:
                session_comparison[session] = {
                    "sl_hit_count": sl_count,
                    "partial_count": partial_count,
                    "sl_hit_rate": sl_count / total,
                }

        comparison["session_analysis"] = session_comparison

        return comparison


def generate_report(results: Dict[str, Any], output_path: Path) -> None:
    """
    Generate markdown report from analysis results.

    Args:
        results: Analysis results dictionary
        output_path: Path to save report
    """
    lines = []

    # Header
    lines.append("# Entry Quality Analysis Report")
    lines.append(f"\n**Run ID:** {results['run_id']}")
    lines.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"\n---\n")

    # Summary stats
    lines.append("## Summary Statistics\n")
    lines.append(f"- **Total Trades:** {results['total_trades']}")
    lines.append(f"- **SL Hit Count:** {results['sl_hit_count']} ({results['sl_hit_rate']*100:.1f}%)")
    lines.append(f"- **Partial Reach Count:** {results['partial_reach_count']} ({(1-results['sl_hit_rate'])*100:.1f}%)")
    lines.append("\n")

    # SL Hit Analysis
    if results['sl_hit_metrics']:
        lines.append("## SL_HIT Trades Analysis\n")
        sl_m = results['sl_hit_metrics']

        lines.append(f"- **Average R-Multiple:** {sl_m.get('avg_r_multiple', 0):.2f}R")
        lines.append(f"- **Average PnL:** ${sl_m.get('avg_pnl', 0):.2f}")

        if "aggregated_detailed" in sl_m:
            agg = sl_m["aggregated_detailed"]
            lines.append(f"- **Avg Pullback Depth:** {agg.get('avg_pullback_depth_pct', 0):.1f}%")
            lines.append(f"- **Avg Staircase Depth:** {agg.get('avg_staircase_depth', 0):.1f} bars")
            lines.append(f"- **Avg SL/ATR Ratio:** {agg.get('avg_sl_to_atr_ratio', 0):.2f}×")

        lines.append("\n")

    # Partial Reach Analysis
    if results['partial_reach_metrics']:
        lines.append("## Partial-Reach Trades Analysis\n")
        partial_m = results['partial_reach_metrics']

        lines.append(f"- **Average R-Multiple:** {partial_m.get('avg_r_multiple', 0):.2f}R")
        lines.append(f"- **Average PnL:** ${partial_m.get('avg_pnl', 0):.2f}")

        if "aggregated_detailed" in partial_m:
            agg = partial_m["aggregated_detailed"]
            lines.append(f"- **Avg Pullback Depth:** {agg.get('avg_pullback_depth_pct', 0):.1f}%")
            lines.append(f"- **Avg Staircase Depth:** {agg.get('avg_staircase_depth', 0):.1f} bars")
            lines.append(f"- **Avg SL/ATR Ratio:** {agg.get('avg_sl_to_atr_ratio', 0):.2f}×")

        lines.append("\n")

    # Comparison
    if results['comparison']:
        lines.append("## Key Differences (Partial-Reach vs SL_HIT)\n")
        comp = results['comparison']

        if "pullback_depth" in comp:
            pd = comp["pullback_depth"]
            lines.append(f"- **Pullback Depth:** {pd['partial_avg']:.1f}% vs {pd['sl_hit_avg']:.1f}% (Δ {pd['difference']:.1f}%)")

        if "staircase_depth" in comp:
            sd = comp["staircase_depth"]
            lines.append(f"- **Staircase Depth:** {sd['partial_avg']:.1f} vs {sd['sl_hit_avg']:.1f} bars (Δ {sd['difference']:.1f})")

        if "sl_to_atr_ratio" in comp:
            atr = comp["sl_to_atr_ratio"]
            lines.append(f"- **SL/ATR Ratio:** {atr['partial_avg']:.2f}× vs {atr['sl_hit_avg']:.2f}× (Δ {atr['difference']:.2f}×)")

        if "dcrd_score" in comp:
            dcrd = comp["dcrd_score"]
            lines.append(f"- **DCRD Score:** {dcrd['partial_avg']:.1f} vs {dcrd['sl_hit_avg']:.1f} (Δ {dcrd['difference']:.1f})")

        lines.append("\n")

    # Session Analysis
    if "session_analysis" in results['comparison']:
        lines.append("## Session Analysis\n")
        lines.append("\n| Session | SL Hits | Partials | SL Hit Rate |")
        lines.append("|---------|---------|----------|-------------|")

        session_data = results['comparison']['session_analysis']
        for session, data in sorted(session_data.items()):
            lines.append(f"| {session} | {data['sl_hit_count']} | {data['partial_count']} | {data['sl_hit_rate']*100:.1f}% |")

        lines.append("\n")

    # Recommendations placeholder
    lines.append("## Recommended Filters (To Be Determined)\n")
    lines.append("Based on the analysis above, filters will be designed in Task 1.3.\n")

    # Write report (UTF-8 encoding for special characters)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    log.info(f"Report saved to {output_path}")


if __name__ == "__main__":
    # Example usage
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    if len(sys.argv) < 2:
        print("Usage: python -m src.analysis.entry_quality_analyzer <run_id>")
        print("Example: python -m src.analysis.entry_quality_analyzer run_20260222_083218")
        sys.exit(1)

    run_id = sys.argv[1]

    # Run analysis
    analyzer = EntryQualityAnalyzer(run_id)
    results = analyzer.analyze_all()

    # Generate report
    report_path = Path("docs") / "entry_quality_report.md"
    generate_report(results, report_path)

    print(f"\n✅ Analysis complete!")
    print(f"📄 Report: {report_path}")
    print(f"\nKey findings:")
    print(f"  - SL Hit Rate: {results['sl_hit_rate']*100:.1f}%")

    if results['comparison']:
        comp = results['comparison']
        if "pullback_depth" in comp:
            print(f"  - Pullback Depth: Winners {comp['pullback_depth']['partial_avg']:.1f}% vs Losers {comp['pullback_depth']['sl_hit_avg']:.1f}%")
        if "staircase_depth" in comp:
            print(f"  - Staircase Depth: Winners {comp['staircase_depth']['partial_avg']:.1f} vs Losers {comp['staircase_depth']['sl_hit_avg']:.1f} bars")
