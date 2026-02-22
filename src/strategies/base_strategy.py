"""
JcampFX — Abstract Base Strategy (Phase 2, PRD §2.2)

All strategy modules must inherit from BaseStrategy and implement the
standardized interface. The Brain Core only knows about BaseStrategy —
concrete implementations are auto-discovered from the strategies/ directory.

Standard Module Interface (PRD §2.2):
    analyze(range_bars, ohlc_4h, ohlc_1h, composite_score, news_state) → Signal | None
    retrain(performance_data) → void  (future ML hook)
    get_status() → {active, cooldown_until, last10_R, trade_count}

Validation: V2.11 (auto-registration without Brain Core changes)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import pandas as pd

from src.signal import Signal


class BaseStrategy(ABC):
    """
    Abstract base class for all JcampFX strategy modules.

    Concrete strategies must implement `analyze()` and set `name`,
    `min_score`, and `max_score` class attributes.
    """

    #: Unique strategy identifier used throughout the system
    name: str = "BaseStrategy"

    #: Minimum CompositeScore for this strategy to be active
    min_score: float = 0.0

    #: Maximum CompositeScore for this strategy to be active (100 = no upper limit)
    max_score: float = 100.0

    #: v2.2 (PRD §8.4, VP.5): Whether strategy will enter on gap-adjacent bars.
    #: BreakoutRider: False (hard block). TrendRider/RangeRider: True (configurable).
    allow_gap_adjacent: bool = True

    def is_regime_active(self, composite_score: float) -> bool:
        """Return True if CompositeScore is within this strategy's regime range."""
        return self.min_score <= composite_score <= self.max_score

    @abstractmethod
    def analyze(
        self,
        range_bars: pd.DataFrame,
        ohlc_4h: pd.DataFrame,
        ohlc_1h: pd.DataFrame,
        composite_score: float,
        news_state: dict,
        dcrd_history: Optional[list[float]] = None,  # Phase 3.1.1: DCRD momentum
    ) -> Optional[Signal]:
        """
        Analyze market data and return a Signal or None.

        Parameters
        ----------
        range_bars      : Completed Range Bar DataFrame for this pair
        ohlc_4h         : 4H OHLC DataFrame (for confirmation indicators)
        ohlc_1h         : 1H OHLC DataFrame (for confirmation indicators)
        composite_score : Current DCRD CompositeScore (0–100)
        news_state      : Dict with keys: blocked, post_cooling, events
                          (populated by BrainCore from NewsLayer)
        dcrd_history    : Last N composite scores for momentum calculation (Phase 3.1.1)

        Returns
        -------
        Signal with strategy-provided fields populated, or None if no setup found.
        Brain Core attaches risk_pct, lot_size, partial_exit_pct after this returns.
        """
        ...

    def retrain(self, performance_data: dict) -> None:
        """
        Future ML hook — called by Brain Core when new performance data is available.
        Default: no-op. Override in ML-enabled strategy modules.
        """
        pass

    def get_status(self) -> dict:
        """
        Return current status dict (PRD §2.2 interface).
        Override in concrete strategies to include cooldown / last10_R data.
        """
        return {
            "strategy": self.name,
            "active": True,
            "cooldown_until": None,
            "last10_R": 0.0,
            "trade_count": 0,
            "regime_range": f"{self.min_score}–{self.max_score}",
        }
