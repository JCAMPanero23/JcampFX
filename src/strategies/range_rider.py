"""
JcampFX — RangeRider Strategy (Phase 2, PRD §8.2)

Active when CompositeScore < 30 (Range/Mean-Reversion regime).

Entry logic:
  1. Detect a consolidation block: ≥8 consecutive Range Bars where
     the high-to-low width of the block > 2× the individual bar size
  2. Identify upper and lower boundaries of the block
  3. Enter on fade (counter-trend) when price touches a boundary:
     - At upper boundary → SELL (fade the high)
     - At lower boundary → BUY  (fade the low)
  4. Entry on close of the boundary touch bar

SL: just beyond the boundary (1× RB size buffer)
TP_1R: towards the opposite boundary (1× risk distance)

Validation: V2.4 (RangeRider: min 8 RBs + width > 2x RB size)
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

from src.config import PIP_SIZE, RANGE_BAR_PIPS, STRATEGY_RANGERIDER_MAX_CS
from src.exit_manager import get_partial_exit_pct
from src.signal import Signal
from src.strategies.base_strategy import BaseStrategy

log = logging.getLogger(__name__)

_MIN_BLOCK_BARS = 8        # PRD §8.2: minimum consecutive RBs in range block
_BOUNDARY_TOUCH_BUFFER = 0.3  # fraction of bar size = "close enough to boundary"


def _detect_range_block(
    range_bars: pd.DataFrame,
    pair: str,
    lookback: int = 30,
) -> Optional[tuple[float, float, float]]:
    """
    Detect a consolidation block of ≥8 Range Bars with width > 2× RB size.

    Returns
    -------
    (upper_boundary, lower_boundary, rb_size_price) or None if no block found.
    """
    if len(range_bars) < _MIN_BLOCK_BARS:
        return None

    pip = PIP_SIZE.get(pair, 0.0001)
    rb_pips = RANGE_BAR_PIPS.get(pair, 10)
    rb_size_price = rb_pips * pip

    recent = range_bars.tail(lookback).reset_index(drop=True)

    # Scan backwards to find a sequence of ≥8 bars with width > 2× bar size
    best_block = None
    for end_idx in range(len(recent) - 1, _MIN_BLOCK_BARS - 2, -1):
        for start_idx in range(max(0, end_idx - lookback), end_idx - _MIN_BLOCK_BARS + 2):
            block = recent.iloc[start_idx:end_idx + 1]
            if len(block) < _MIN_BLOCK_BARS:
                continue

            block_high = block["high"].max()
            block_low = block["low"].min()
            block_width = block_high - block_low

            if block_width > 2 * rb_size_price:
                best_block = (block_high, block_low, rb_size_price)
                break
        if best_block is not None:
            break

    return best_block


def _is_at_boundary(
    last_bar: pd.Series,
    upper: float,
    lower: float,
    rb_size_price: float,
) -> Optional[str]:
    """
    Return "SELL" if last bar touches upper boundary, "BUY" if lower boundary, else None.
    Tolerance = _BOUNDARY_TOUCH_BUFFER × rb_size_price.
    """
    tolerance = _BOUNDARY_TOUCH_BUFFER * rb_size_price
    close = float(last_bar["close"])

    if close >= upper - tolerance:
        return "SELL"
    if close <= lower + tolerance:
        return "BUY"
    return None


class RangeRider(BaseStrategy):
    """
    RangeRider strategy — active when CompositeScore < 30 (Range regime).

    Entry: fade at consolidation boundaries
    Confirmation: ≥8 RBs in range block + block width > 2× RB size
    """

    name = "RangeRider"
    min_score = 0.0
    max_score = float(STRATEGY_RANGERIDER_MAX_CS)   # 30

    def analyze(
        self,
        range_bars: pd.DataFrame,
        ohlc_4h: pd.DataFrame,
        ohlc_1h: pd.DataFrame,
        composite_score: float,
        news_state: dict,
        dcrd_history: Optional[list[float]] = None,  # Phase 3.1.1: DCRD momentum (not used yet)
    ) -> Optional[Signal]:
        """
        Return a Signal if a RangeRider setup is found, else None.

        V2.4: Returns None if CS ≥ 30, or no 8-bar block with width > 2× RB size.
        """
        if not self.is_regime_active(composite_score):
            return None

        if range_bars is None or len(range_bars) < _MIN_BLOCK_BARS + 2:
            return None

        pair = news_state.get("pair", "UNKNOWN")

        # Step 1: Detect range block (≥8 bars, width > 2× RB size)
        block = _detect_range_block(range_bars, pair)
        if block is None:
            log.debug("RangeRider: no valid range block detected")
            return None

        upper, lower, rb_size_price = block

        # Step 2: Check if last bar is at a boundary
        last_rb = range_bars.iloc[-1]
        direction = _is_at_boundary(last_rb, upper, lower, rb_size_price)
        if direction is None:
            return None

        # Step 3: Build entry parameters
        entry = float(last_rb["close"])
        pip = PIP_SIZE.get(pair, 0.0001)

        if direction == "SELL":
            # Fade from upper boundary
            sl = upper + rb_size_price     # SL just above upper boundary
            r_dist = abs(entry - sl)
            if r_dist <= 0:
                return None
            tp_1r = entry - r_dist         # Target towards lower boundary
        else:
            # Fade from lower boundary
            sl = lower - rb_size_price     # SL just below lower boundary
            r_dist = abs(entry - sl)
            if r_dist <= 0:
                return None
            tp_1r = entry + r_dist         # Target towards upper boundary

        timestamp = last_rb.get("end_time", pd.Timestamp.utcnow())
        partial_pct = get_partial_exit_pct(composite_score)

        signal = Signal(
            timestamp=pd.Timestamp(timestamp, tz="UTC") if not hasattr(timestamp, "tzinfo") else timestamp,
            pair=pair,
            direction=direction,
            entry=entry,
            sl=sl,
            tp_1r=tp_1r,
            strategy=self.name,
            composite_score=composite_score,
            partial_exit_pct=partial_pct,
        )

        log.info(
            "RangeRider signal: %s %s @ %.5f SL=%.5f CS=%.1f partial=%.0f%%"
            " block=[%.5f–%.5f width=%.1fpips]",
            direction, pair, entry, sl, composite_score, partial_pct * 100,
            lower, upper, (upper - lower) / pip,
        )
        return signal
