"""
JcampFX — BacktestAccount (Phase 3, PRD §9.1)

Tracks all account state during a backtest replay:
  - Equity curve
  - Open / closed trades
  - Daily R usage and trade count (reset at midnight UTC)
  - Feeds BrainCore.process() via get_account_state()

R-multiple and PnL calculations are kept here so the engine stays thin.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import pandas as pd

from backtester.cost_model import apply_exit_slippage, round_trip_commission
from backtester.trade import BacktestTrade
from src.brain_core import AccountState
from src.config import (
    DAILY_LOSS_CAP_R,
    PIP_SIZE,
    SLIPPAGE_PIPS,
    WEEKEND_CLOSE_MINUTES,
)
from src.exit_manager import (
    calculate_r_multiple,
    initial_chandelier_sl,
    update_chandelier,
)

log = logging.getLogger(__name__)


@dataclass
class BacktestAccount:
    """Mutable account state for the backtester event loop."""

    initial_equity: float
    equity: float = field(init=False)
    open_trades: list[BacktestTrade] = field(default_factory=list)
    closed_trades: list[BacktestTrade] = field(default_factory=list)

    # Daily tracking
    daily_r_used: float = 0.0
    daily_trade_count: int = 0
    _last_reset_date: Optional[date] = field(default=None, repr=False)

    # Equity history: list of (timestamp, equity)
    equity_history: list[tuple] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.equity = self.initial_equity

    # ------------------------------------------------------------------
    # BrainCore interface
    # ------------------------------------------------------------------

    def get_account_state(self) -> AccountState:
        """Build the AccountState snapshot that BrainCore expects."""
        positions = [
            {"pair": t.pair, "direction": t.direction}
            for t in self.open_trades
        ]
        return AccountState(
            equity=self.equity,
            open_positions=positions,
            daily_r_used=self.daily_r_used,
            daily_trade_count=self.daily_trade_count,
        )

    # ------------------------------------------------------------------
    # Trade lifecycle
    # ------------------------------------------------------------------

    def open_trade(self, trade: BacktestTrade) -> None:
        """Register a new trade and deduct commission immediately."""
        commission = round_trip_commission(trade.lot_size)
        trade.commission_usd = commission
        self.equity -= commission
        self.daily_trade_count += 1
        self.open_trades.append(trade)
        self._record_equity(trade.entry_time)
        log.debug(
            "Opened %s %s %s entry=%.5f lots=%.2f comm=%.2f",
            trade.trade_id, trade.pair, trade.direction,
            trade.entry_price, trade.lot_size, commission,
        )

    def apply_partial_exit(
        self,
        trade: BacktestTrade,
        exit_price: float,
        timestamp: pd.Timestamp,
        atr14: float,
    ) -> None:
        """
        Close partial_exit_pct of position at 1.5R.

        Sets trade.phase = "runner" and initialises the Chandelier SL.
        """
        slipped_price = apply_exit_slippage(exit_price, trade.direction, trade.pair)

        r_partial = calculate_r_multiple(
            trade.entry_price, slipped_price, trade.sl_price, trade.direction
        )
        trade.partial_exit_price = slipped_price
        trade.partial_exit_time = timestamp
        trade.r_multiple_partial = r_partial
        trade.atr14_at_partial = atr14

        # Initialise Chandelier SL on the runner
        trade.chandelier_sl = initial_chandelier_sl(
            trade.entry_price, trade.sl_price, trade.direction, atr14, trade.pair
        )

        # Partial PnL (not yet in equity — added on full close)
        trade.phase = "runner"
        log.debug(
            "Partial exit %s at %.5f (%.2fR) chandelier=%.5f",
            trade.trade_id, slipped_price, r_partial, trade.chandelier_sl,
        )

    def close_trade(
        self,
        trade: BacktestTrade,
        exit_price: float,
        timestamp: pd.Timestamp,
        reason: str,
    ) -> None:
        """
        Close the trade (or its runner leg) and settle PnL.

        For trades that had a partial exit, this closes the runner portion.
        """
        slipped_price = apply_exit_slippage(exit_price, trade.direction, trade.pair)
        trade.close_price = slipped_price
        trade.close_time = timestamp
        trade.close_reason = reason
        trade.phase = "closed"

        pip = PIP_SIZE.get(trade.pair, 0.0001)

        if trade.partial_exit_time is not None:
            # Two-leg trade: partial (partial_exit_pct) + runner (1 - partial_exit_pct)
            runner_pct = 1.0 - trade.partial_exit_pct
            r_runner = calculate_r_multiple(
                trade.entry_price, slipped_price, trade.sl_price, trade.direction
            )
            trade.r_multiple_runner = r_runner
            trade.r_multiple_total = (
                trade.partial_exit_pct * trade.r_multiple_partial
                + runner_pct * r_runner
            )

            partial_pips = (
                (trade.partial_exit_price - trade.entry_price) / pip
                if trade.direction.upper() == "BUY"
                else (trade.entry_price - trade.partial_exit_price) / pip
            )
            runner_pips = (
                (slipped_price - trade.entry_price) / pip
                if trade.direction.upper() == "BUY"
                else (trade.entry_price - slipped_price) / pip
            )
            # PnL = pip_value × pips (simple model: pip value ≈ $10 per lot for USD-quoted)
            pip_value_per_lot = _pip_value_usd(trade.pair)
            trade.pnl_usd = (
                trade.lot_size * trade.partial_exit_pct * partial_pips * pip_value_per_lot
                + trade.lot_size * runner_pct * runner_pips * pip_value_per_lot
                - trade.commission_usd
            )
        else:
            # Single-leg trade: full loss (SL hit before 1.5R)
            r = calculate_r_multiple(
                trade.entry_price, slipped_price, trade.sl_price, trade.direction
            )
            trade.r_multiple_total = r
            trade.r_multiple_runner = r

            close_pips = (
                (slipped_price - trade.entry_price) / pip
                if trade.direction.upper() == "BUY"
                else (trade.entry_price - slipped_price) / pip
            )
            pip_value_per_lot = _pip_value_usd(trade.pair)
            trade.pnl_usd = (
                trade.lot_size * close_pips * pip_value_per_lot - trade.commission_usd
            )

        # Update equity:
        # Commission was already deducted at open (equity -= commission).
        # pnl_usd = gross_pnl - commission.
        # At close we add back gross_pnl = pnl_usd + commission_usd so that
        # net equity change = gross_pnl - commission (already taken) = pnl_usd.
        self.equity += trade.pnl_usd + trade.commission_usd

        # Daily R loss tracking
        if trade.r_multiple_total < 0:
            self.daily_r_used += abs(trade.r_multiple_total * trade.partial_exit_pct
                                     if trade.partial_exit_time is not None
                                     else trade.r_multiple_total)

        # Move to closed list
        self.open_trades.remove(trade)
        self.closed_trades.append(trade)
        self._record_equity(timestamp)
        log.debug(
            "Closed %s reason=%s R=%.2f PnL=%.2f equity=%.2f",
            trade.trade_id, reason, trade.r_multiple_total, trade.pnl_usd, self.equity,
        )

    def update_chandelier_for_trade(
        self, trade: BacktestTrade, bar_extreme: float, atr14: float
    ) -> None:
        """Update Chandelier SL on a runner trade. Never widens."""
        if trade.phase != "runner":
            return
        trade.chandelier_sl = update_chandelier(
            new_extreme=bar_extreme,
            current_sl=trade.chandelier_sl,
            direction=trade.direction,
            atr14=atr14,
            initial_r_pips=trade.initial_r_pips,
            pair=trade.pair,
        )

    # ------------------------------------------------------------------
    # Daily cap enforcement
    # ------------------------------------------------------------------

    def is_daily_cap_hit(self) -> bool:
        return self.daily_r_used >= DAILY_LOSS_CAP_R

    def reset_daily_if_needed(self, current_time: pd.Timestamp) -> bool:
        """Reset daily counters at midnight UTC. Returns True if reset occurred."""
        today = current_time.date()
        if self._last_reset_date is None or today > self._last_reset_date:
            self.daily_r_used = 0.0
            self.daily_trade_count = 0
            self._last_reset_date = today
            return True
        return False

    # ------------------------------------------------------------------
    # Metrics helpers
    # ------------------------------------------------------------------

    def get_max_drawdown_pct(self) -> float:
        """Peak-to-trough drawdown as a percentage of peak equity."""
        if not self.equity_history:
            return 0.0
        equities = [e for _, e in self.equity_history]
        peak = self.initial_equity
        max_dd = 0.0
        for eq in equities:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak
            if dd > max_dd:
                max_dd = dd
        return max_dd * 100.0

    def _record_equity(self, timestamp: pd.Timestamp) -> None:
        self.equity_history.append((timestamp, self.equity))


# ---------------------------------------------------------------------------
# Pip value helper
# ---------------------------------------------------------------------------

def _pip_value_usd(pair: str) -> float:
    """
    Approximate USD pip value per standard lot (1.0 lot).

    For pairs quoted in USD (EURUSD, GBPUSD, AUDUSD): $10/pip/lot exactly.
    For USD-base pairs (USDJPY, USDCHF): ~$10/pip/lot (approximate; ignores FX rate).
    For cross pairs (AUDJPY, EURJPY, etc.): ~$10/pip/lot approximation.
    Gold (XAUUSD): $10/pip/lot placeholder.

    The backtester uses this for PnL in USD. For Phase 3 validation purposes
    (pass/fail gates), this approximation is sufficient; exact live values
    come from MT5 in Phase 4+.
    """
    return 10.0
