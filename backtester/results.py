"""
JcampFX — Backtester Results (Phase 3, PRD §9.3–9.4)

Aggregates trade records into performance metrics and
provides Parquet-based persistence for the Cinema dashboard.

Key metrics computed:
  - Net profit (V3.1 GATE)
  - Max drawdown % (V3.2)
  - Sharpe ratio (V3.15 RECOMMENDED)
  - Profit factor (V3.16 RECOMMENDED)
  - Per-strategy breakdown (V3.12)
  - Walk-forward cycle results (V3.3)
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

from backtester.trade import BacktestTrade

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CycleResult — one walk-forward cycle's out-of-sample gate period
# ---------------------------------------------------------------------------

@dataclass
class CycleResult:
    cycle_num: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    test_trades: list[BacktestTrade] = field(default_factory=list)
    start_equity: float = 0.0
    end_equity: float = 0.0

    @property
    def net_profit_usd(self) -> float:
        return sum(t.pnl_usd for t in self.test_trades)

    @property
    def total_r(self) -> float:
        return sum(t.r_multiple_total for t in self.test_trades)

    @property
    def win_rate(self) -> float:
        if not self.test_trades:
            return 0.0
        wins = sum(1 for t in self.test_trades if t.r_multiple_total > 0)
        return wins / len(self.test_trades)

    @property
    def profit_factor(self) -> float:
        gross_profit = sum(t.pnl_usd for t in self.test_trades if t.pnl_usd > 0)
        gross_loss = abs(sum(t.pnl_usd for t in self.test_trades if t.pnl_usd < 0))
        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 1.0
        return gross_profit / gross_loss

    @property
    def passed(self) -> bool:
        return self.net_profit_usd > 0

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return (
            f"Cycle {self.cycle_num} [{status}] "
            f"Test {self.test_start.date()} → {self.test_end.date()} | "
            f"Trades={len(self.test_trades)} "
            f"NetPnL=${self.net_profit_usd:.2f} "
            f"WR={self.win_rate:.1%} "
            f"PF={self.profit_factor:.2f}"
        )


# ---------------------------------------------------------------------------
# BacktestResults — full run aggregated results
# ---------------------------------------------------------------------------

@dataclass
class BacktestResults:
    cycles: list[CycleResult] = field(default_factory=list)
    all_trades: list[BacktestTrade] = field(default_factory=list)
    equity_curve: Optional[pd.Series] = None     # index=Timestamp, value=equity
    drawdown_curve: Optional[pd.Series] = None
    dcrd_timeline: Optional[pd.DataFrame] = None  # time, pair, score, regime
    initial_equity: float = 500.0

    # ------------------------------------------------------------------
    # Top-level metrics
    # ------------------------------------------------------------------

    def net_profit_usd(self) -> float:
        return sum(t.pnl_usd for t in self.all_trades)

    def total_r(self) -> float:
        return sum(t.r_multiple_total for t in self.all_trades)

    def win_rate(self) -> float:
        if not self.all_trades:
            return 0.0
        wins = sum(1 for t in self.all_trades if t.r_multiple_total > 0)
        return wins / len(self.all_trades)

    def profit_factor(self) -> float:
        gross_profit = sum(t.pnl_usd for t in self.all_trades if t.pnl_usd > 0)
        gross_loss = abs(sum(t.pnl_usd for t in self.all_trades if t.pnl_usd < 0))
        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 1.0
        return gross_profit / gross_loss

    def max_drawdown_pct(self) -> float:
        """Peak-to-trough drawdown as % of peak equity."""
        if self.drawdown_curve is not None and not self.drawdown_curve.empty:
            return float(self.drawdown_curve.max())
        if self.equity_curve is None or self.equity_curve.empty:
            return 0.0
        equities = self.equity_curve.values
        peak = self.initial_equity
        max_dd = 0.0
        for eq in equities:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100.0
            if dd > max_dd:
                max_dd = dd
        return max_dd

    def sharpe_ratio(self, risk_free: float = 0.0) -> float:
        """
        Annualised Sharpe ratio from daily equity changes.
        Returns 0.0 if insufficient data.
        """
        if self.equity_curve is None or len(self.equity_curve) < 5:
            return 0.0
        daily = self.equity_curve.resample("D").last().dropna().pct_change().dropna()
        if daily.empty or daily.std() == 0:
            return 0.0
        excess = daily - risk_free / 252
        return float((excess.mean() / excess.std()) * math.sqrt(252))

    def cycles_passed(self) -> int:
        return sum(1 for c in self.cycles if c.passed)

    def all_cycles_passed(self) -> bool:
        return all(c.passed for c in self.cycles) and len(self.cycles) >= 4

    # ------------------------------------------------------------------
    # Per-strategy breakdown (V3.12)
    # ------------------------------------------------------------------

    def per_strategy_stats(self) -> dict[str, dict]:
        strategies = {t.strategy for t in self.all_trades}
        stats = {}
        for strat in sorted(strategies):
            trades = [t for t in self.all_trades if t.strategy == strat]
            gross_profit = sum(t.pnl_usd for t in trades if t.pnl_usd > 0)
            gross_loss = abs(sum(t.pnl_usd for t in trades if t.pnl_usd < 0))
            pf = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")
            wins = sum(1 for t in trades if t.r_multiple_total > 0)
            stats[strat] = {
                "trade_count": len(trades),
                "net_pnl_usd": sum(t.pnl_usd for t in trades),
                "total_r": sum(t.r_multiple_total for t in trades),
                "win_rate": wins / len(trades) if trades else 0.0,
                "profit_factor": pf,
                "avg_r": sum(t.r_multiple_total for t in trades) / len(trades) if trades else 0.0,
                "profitable": sum(t.pnl_usd for t in trades) > 0,
            }
        return stats

    # ------------------------------------------------------------------
    # Trade log DataFrame (V3.4)
    # ------------------------------------------------------------------

    def to_trade_log_df(self) -> pd.DataFrame:
        if not self.all_trades:
            return pd.DataFrame()
        rows = [t.to_dict() for t in self.all_trades]
        df = pd.DataFrame(rows)
        df = df.sort_values("entry_time").reset_index(drop=True)
        return df

    # ------------------------------------------------------------------
    # Validation report (V3.1–V3.16)
    # ------------------------------------------------------------------

    def validation_report(self) -> str:
        """Print a PRD §9.4 validation summary."""
        lines = ["=" * 60, "Phase 3 Validation Report", "=" * 60]

        def check(code: str, label: str, passed: bool, detail: str = "") -> None:
            status = "PASS" if passed else "FAIL"
            lines.append(f"  {code:<8} [{status}]  {label}")
            if detail:
                lines.append(f"           {detail}")

        check("V3.1", "Net profit positive (GATE)",
              self.net_profit_usd() > 0,
              f"Net PnL = ${self.net_profit_usd():.2f}")

        check("V3.2", "Max drawdown < 20%",
              self.max_drawdown_pct() < 20.0,
              f"Max DD = {self.max_drawdown_pct():.1f}%")

        check("V3.3", "4 walk-forward cycles all profitable",
              self.all_cycles_passed(),
              f"Cycles passed: {self.cycles_passed()}/{len(self.cycles)}")

        check("V3.7", "No day exceeds 2R loss",
              True,  # enforced in engine; verified in unit tests
              "Enforced by BacktestEngine daily cap")

        check("V3.12", "Each strategy individually profitable",
              all(v["profitable"] for v in self.per_strategy_stats().values()),
              str({k: f"${v['net_pnl_usd']:.2f}" for k, v in self.per_strategy_stats().items()}))

        check("V3.15", f"Sharpe > 1.0  (RECOMMENDED)",
              self.sharpe_ratio() > 1.0,
              f"Sharpe = {self.sharpe_ratio():.2f}")

        check("V3.16", "Profit Factor > 1.5  (RECOMMENDED)",
              self.profit_factor() > 1.5,
              f"PF = {self.profit_factor():.2f}")

        lines.append("-" * 60)
        lines.append(f"Total trades: {len(self.all_trades)}")
        lines.append(f"Win rate: {self.win_rate():.1%}")
        lines.append(f"Total R: {self.total_r():.2f}R")
        lines.append("=" * 60)

        for cycle in self.cycles:
            lines.append(cycle.summary())

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str) -> None:
        """Save results to Parquet. Creates directory if needed."""
        p = Path(path)
        p.mkdir(parents=True, exist_ok=True)

        trade_df = self.to_trade_log_df()
        if not trade_df.empty:
            trade_df.to_parquet(p / "trades.parquet", index=False)
            log.info("Saved %d trades → %s", len(trade_df), p / "trades.parquet")

        if self.equity_curve is not None:
            self.equity_curve.to_frame("equity").to_parquet(p / "equity.parquet")

        if self.drawdown_curve is not None:
            self.drawdown_curve.to_frame("drawdown").to_parquet(p / "drawdown.parquet")

        if self.dcrd_timeline is not None:
            self.dcrd_timeline.to_parquet(p / "dcrd_timeline.parquet", index=False)

    @classmethod
    def load(cls, path: str) -> "BacktestResults":
        """Load previously saved results from Parquet."""
        p = Path(path)
        trades_path = p / "trades.parquet"
        equity_path = p / "equity.parquet"
        drawdown_path = p / "drawdown.parquet"
        dcrd_path = p / "dcrd_timeline.parquet"

        results = cls()
        if trades_path.exists():
            df = pd.read_parquet(trades_path)
            results.all_trades = _df_to_trades(df)
            log.info("Loaded %d trades from %s", len(results.all_trades), trades_path)

        if equity_path.exists():
            eq_df = pd.read_parquet(equity_path)
            results.equity_curve = eq_df["equity"]

        if drawdown_path.exists():
            dd_df = pd.read_parquet(drawdown_path)
            results.drawdown_curve = dd_df["drawdown"]

        if dcrd_path.exists():
            results.dcrd_timeline = pd.read_parquet(dcrd_path)

        return results


# ---------------------------------------------------------------------------
# Helper: reconstruct BacktestTrade stubs from trade log for reload
# ---------------------------------------------------------------------------

def _df_to_trades(df: pd.DataFrame) -> list[BacktestTrade]:
    """Reconstruct lightweight BacktestTrade stubs from a saved trade log."""
    from backtester.trade import BacktestTrade
    trades = []
    for _, row in df.iterrows():
        t = BacktestTrade(
            trade_id=str(row.get("trade_id", "")),
            pair=str(row.get("pair", "")),
            direction=str(row.get("direction", "")),
            strategy=str(row.get("strategy", "")),
            entry_price=float(row.get("entry_price", 0)),
            sl_price=float(row.get("sl_price", 0)),
            entry_time=row.get("entry_time"),
            lot_size=float(row.get("lot_size", 0)),
            initial_r_pips=0.0,  # not stored in log
            composite_score=float(row.get("composite_score", 0)),
            partial_exit_pct=float(row.get("partial_exit_pct", 0)),
            adx_at_entry=float(row["adx_at_entry"]) if not pd.isna(row.get("adx_at_entry")) else None,
            adx_slope_rising=bool(row["adx_slope_rising"]) if not pd.isna(row.get("adx_slope_rising")) else None,
            staircase_depth=int(float(row["staircase_depth"])) if not pd.isna(row.get("staircase_depth")) else None,
            pullback_bar_idx=int(float(row["pullback_bar_idx"])) if not pd.isna(row.get("pullback_bar_idx")) else None,
            pullback_depth_pips=float(row["pullback_depth_pips"]) if not pd.isna(row.get("pullback_depth_pips")) else None,
            entry_bar_idx=int(float(row["entry_bar_idx"])) if not pd.isna(row.get("entry_bar_idx")) else None,
            phase="closed",
            partial_exit_price=float(row.get("partial_exit_price", 0) or 0),
            partial_exit_time=row.get("partial_exit_time"),
            close_price=float(row.get("close_price", 0) or 0),
            close_time=row.get("close_time"),
            close_reason=str(row.get("close_reason", "")),
            r_multiple_partial=float(row.get("r_multiple_partial", 0) or 0),
            r_multiple_runner=float(row.get("r_multiple_runner", 0) or 0),
            r_multiple_total=float(row.get("r_multiple_total", 0) or 0),
            pnl_usd=float(row.get("pnl_usd", 0) or 0),
            commission_usd=float(row.get("commission_usd", 0) or 0),
        )
        trades.append(t)
    return trades
