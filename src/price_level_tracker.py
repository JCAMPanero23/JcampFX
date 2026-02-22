"""
JcampFX — Price Level Cooldown Tracker (Phase 3.1.1)

Prevents "revenge trading" by blocking re-entries at the same price level
within a configurable time window after a losing trade.

Implementation:
  - Tracks losing trade locations (price + timestamp + strategy)
  - Blocks new entries if within PRICE_LEVEL_COOLDOWN_PIPS of recent loss
  - Per-strategy blocking: TrendRider can't re-enter where TrendRider lost,
    but BreakoutRider can (different regime, different logic)
  - Cooldown window: PRICE_LEVEL_COOLDOWN_HOURS (default 4 hours)

Validation:
  V3.1.1a — Revenge trades eliminated (no duplicate entries at same price/strategy within cooldown)
  V3.1.1b — Cross-strategy entries allowed (BreakoutRider can enter where TrendRider lost)
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timedelta
from typing import Optional

from src.config import (
    PIP_SIZE,
    PRICE_LEVEL_COOLDOWN_HOURS,
    PRICE_LEVEL_COOLDOWN_PIPS,
    PRICE_LEVEL_TRACK_LOSSES_ONLY,
)

log = logging.getLogger(__name__)


class PriceLevelTracker:
    """
    Tracks losing trade price levels and blocks re-entries within cooldown window.

    Each pair tracks a deque of (price, timestamp, strategy, r_result) tuples.
    Only losing trades (R < 0) are tracked if PRICE_LEVEL_TRACK_LOSSES_ONLY is True.
    """

    def __init__(self) -> None:
        # Storage: {pair: deque[(price, timestamp, strategy, r_result)]}
        self._history: dict[str, deque] = {}
        self._cooldown_hours = PRICE_LEVEL_COOLDOWN_HOURS
        self._cooldown_pips = PRICE_LEVEL_COOLDOWN_PIPS
        self._track_losses_only = PRICE_LEVEL_TRACK_LOSSES_ONLY

    def add_losing_trade(
        self,
        pair: str,
        price: float,
        strategy: str,
        timestamp: datetime,
        r_result: float,
    ) -> None:
        """
        Record a losing trade location for cooldown tracking.

        Parameters
        ----------
        pair       : Canonical pair name (e.g., "USDJPY")
        price      : Entry price of the losing trade
        strategy   : Strategy name (e.g., "TrendRider")
        timestamp  : Trade close time (when loss was realized)
        r_result   : R-multiple result (should be negative for losses)
        """
        # Only track losses (if config flag enabled)
        if self._track_losses_only and r_result >= 0:
            return

        if pair not in self._history:
            self._history[pair] = deque(maxlen=100)  # Cap at 100 records per pair

        self._history[pair].append((price, timestamp, strategy, r_result))

        log.info(
            "PriceLevelTracker: recorded loss for %s/%s at %.5f (%.2fR) @ %s",
            pair, strategy, price, r_result, timestamp,
        )

    def is_blocked(
        self,
        pair: str,
        price: float,
        strategy: str,
        now: datetime,
    ) -> tuple[bool, Optional[str]]:
        """
        Check if a new entry is blocked due to recent loss at this price level
        BY THE SAME STRATEGY within the cooldown window.

        Different strategies are allowed to enter at the same price level
        (different market regime, different entry logic).

        Parameters
        ----------
        pair     : Canonical pair name
        price    : Proposed entry price
        strategy : Strategy attempting entry
        now      : Current timestamp

        Returns
        -------
        (is_blocked, reason_if_blocked)
        """
        if pair not in self._history:
            return False, None

        pip_size = PIP_SIZE.get(pair, 0.0001)
        if pip_size == 0:
            log.warning("PriceLevelTracker: unknown pip size for %s, skipping check", pair)
            return False, None

        price_threshold_distance = self._cooldown_pips * pip_size
        cutoff_time = now - timedelta(hours=self._cooldown_hours)

        # Check recent losses for this pair
        for loss_price, loss_time, loss_strategy, r_result in self._history[pair]:
            # Skip if loss is outside cooldown window
            if loss_time < cutoff_time:
                continue

            # Skip if different strategy (allow cross-strategy entries)
            if loss_strategy != strategy:
                continue

            # Check if proposed price is within ±N pips of the loss price
            price_distance = abs(price - loss_price)
            if price_distance <= price_threshold_distance:
                hours_ago = (now - loss_time).total_seconds() / 3600
                reason = (
                    f"PRICE_LEVEL_COOLDOWN:{strategy} lost {r_result:.2f}R at "
                    f"{loss_price:.5f} ({hours_ago:.1f}h ago) — "
                    f"new entry {price:.5f} within {self._cooldown_pips} pips"
                )
                log.info("PriceLevelTracker: BLOCKED %s — %s", pair, reason)
                return True, reason

        return False, None

    def clear(self) -> None:
        """Clear all tracked price levels (for testing or reset)."""
        self._history.clear()
        log.info("PriceLevelTracker: cleared all history")

    def get_history(self, pair: str) -> list[tuple[float, datetime, str, float]]:
        """
        Get tracked price level history for a pair (for debugging/analysis).

        Returns
        -------
        List of (price, timestamp, strategy, r_result) tuples.
        """
        if pair not in self._history:
            return []
        return list(self._history[pair])
