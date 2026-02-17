"""
JcampFX — Per-Strategy Performance Tracker (Phase 2, PRD §6.3 + §10.3)

Tracks the last-10-trade R-result rolling window independently for each strategy.
Provides:
  1. Performance multiplier for dynamic risk sizing (0.6x – 1.3x)
  2. Strategy cooldown detection (5 consecutive losses in last 10 → 24hr pause)

Validation:
    VR.3 — Last-10-trade multiplier recalculates after every completed trade
    VR.4 — Strategies have independent performance tracking
    V2.12 — Performance tracker disables/re-enables strategies correctly
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from src.config import (
    COOLDOWN_HOURS,
    COOLDOWN_LOSSES_IN_WINDOW,
    COOLDOWN_WINDOW,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Trade record
# ---------------------------------------------------------------------------

@dataclass
class TradeRecord:
    r_result: float       # R-multiple outcome (positive = profit, negative = loss)
    timestamp: datetime   # UTC completion time
    is_weekend_close: bool = False  # Excluded from cooldown count (PRD §10.3)


# ---------------------------------------------------------------------------
# Performance multiplier table (PRD §6.3)
# ---------------------------------------------------------------------------

def _performance_multiplier_from_r(last10_r: float) -> float:
    """
    Map cumulative R of last 10 trades to performance multiplier.

    PRD §6.3:
        ≥ +5R  → 1.3x  (strong edge confirmed)
        +2R–+5R → 1.1x  (positive momentum)
        0–+2R  → 1.0x  (neutral)
        -2R–0  → 0.8x  (slight drawdown)
        < -2R  → 0.6x  (poor streak)
    """
    if last10_r >= 5.0:
        return 1.3
    if last10_r >= 2.0:
        return 1.1
    if last10_r >= 0.0:
        return 1.0
    if last10_r >= -2.0:
        return 0.8
    return 0.6


# ---------------------------------------------------------------------------
# Per-strategy tracker
# ---------------------------------------------------------------------------

@dataclass
class _StrategyState:
    trades: deque = field(default_factory=lambda: deque(maxlen=COOLDOWN_WINDOW))
    cooldown_until: Optional[datetime] = None

    @property
    def last10_r(self) -> float:
        return sum(t.r_result for t in self.trades)

    @property
    def trade_count(self) -> int:
        return len(self.trades)

    def consecutive_losses(self) -> int:
        """Count consecutive non-weekend-close losses from the tail of the window."""
        count = 0
        for trade in reversed(self.trades):
            if trade.is_weekend_close:
                continue  # PRD §10.3: exclude weekend protection closures
            if trade.r_result < 0:
                count += 1
            else:
                break
        return count

    def is_in_cooldown(self, now: datetime) -> bool:
        if self.cooldown_until is None:
            return False
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        cd = self.cooldown_until
        if cd.tzinfo is None:
            cd = cd.replace(tzinfo=timezone.utc)
        return now < cd

    def trigger_cooldown(self, now: datetime) -> None:
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        self.cooldown_until = now + timedelta(hours=COOLDOWN_HOURS)
        log.warning(
            "Strategy cooldown triggered — %d consecutive losses. Paused until %s",
            self.consecutive_losses(), self.cooldown_until,
        )

    def reset_cooldown(self) -> None:
        self.cooldown_until = None


# ---------------------------------------------------------------------------
# Public PerformanceTracker
# ---------------------------------------------------------------------------

class PerformanceTracker:
    """
    Independently tracks last-10-trade performance per strategy.

    Strategies: "TrendRider", "BreakoutRider", "RangeRider"
    (any string key is accepted — no enforcement)
    """

    def __init__(self) -> None:
        self._states: dict[str, _StrategyState] = {}

    def _get(self, strategy: str) -> _StrategyState:
        if strategy not in self._states:
            self._states[strategy] = _StrategyState()
        return self._states[strategy]

    def add_trade(
        self,
        strategy: str,
        r_result: float,
        timestamp: Optional[datetime] = None,
        is_weekend_close: bool = False,
    ) -> None:
        """
        Record a completed trade result.

        Parameters
        ----------
        strategy         : Strategy name
        r_result         : Trade outcome in R-multiples (e.g. +1.5, -1.0)
        timestamp        : UTC completion time (defaults to now)
        is_weekend_close : True if closed by Friday protection (excluded from cooldown count)
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        state = self._get(strategy)
        state.trades.append(TradeRecord(
            r_result=r_result,
            timestamp=timestamp,
            is_weekend_close=is_weekend_close,
        ))

        # Check for cooldown trigger: 5 consecutive non-weekend losses in window
        if (
            not is_weekend_close
            and r_result < 0
            and state.consecutive_losses() >= COOLDOWN_LOSSES_IN_WINDOW
        ):
            state.trigger_cooldown(timestamp)

        log.info(
            "%s: trade recorded R=%.2f | last10_R=%.2f | cooldown=%s",
            strategy, r_result, state.last10_r, state.cooldown_until,
        )

    def get_performance_multiplier(self, strategy: str) -> float:
        """
        Return the performance multiplier for dynamic risk sizing.
        VR.3: recalculates after every trade.
        """
        state = self._get(strategy)
        return _performance_multiplier_from_r(state.last10_r)

    def is_in_cooldown(self, strategy: str, now: Optional[datetime] = None) -> bool:
        """
        Return True if the strategy is in its 24-hour cooldown period.
        V2.12: Cooldown prevents new signals from this strategy.
        """
        if now is None:
            now = datetime.now(timezone.utc)
        return self._get(strategy).is_in_cooldown(now)

    def get_cooldown_until(self, strategy: str) -> Optional[datetime]:
        return self._get(strategy).cooldown_until

    def reset_cooldown(self, strategy: str) -> None:
        """Manually reset cooldown (e.g. after 24hr hold expires in live mode)."""
        self._get(strategy).reset_cooldown()
        log.info("%s: cooldown reset", strategy)

    def get_status(self, strategy: str) -> dict:
        """
        Return status dict for dashboard and Brain Core.
        Interface as specified in PRD §2.2:
            {active, cooldown_until, last10_R, trade_count}
        """
        now = datetime.now(timezone.utc)
        state = self._get(strategy)
        in_cd = state.is_in_cooldown(now)
        return {
            "strategy": strategy,
            "active": not in_cd,
            "cooldown_until": state.cooldown_until,
            "last10_R": round(state.last10_r, 4),
            "trade_count": state.trade_count,
            "consecutive_losses": state.consecutive_losses(),
            "performance_multiplier": _performance_multiplier_from_r(state.last10_r),
        }

    def get_all_status(self) -> dict[str, dict]:
        return {s: self.get_status(s) for s in self._states}
