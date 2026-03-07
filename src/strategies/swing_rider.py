"""
JcampFX — SwingRider Hybrid Strategy

Purpose: Convex swing trading for GBPJPY using Range Bar resumption entry + daily Chandelier exit.

Hybrid Design:
- Entry: Range Bar resumption pattern (TrendRider-style, proven 52.6% WR)
- Gate: Daily EMA50 regime filter (quality control)
- SL: Swing-based (200-400 pips, calculated from staircase depth)
- Exit: Daily Chandelier (ATR22 × 3.0, multi-day holds)
- Target: 40-50% WR, 2.5R-4.5R avg winners, 8-15 trades/year

Key Difference from TrendRider:
- Wider swing SLs (200-400 pips vs 60 pips)
- Daily Chandelier exit (not Range Bar trailing)
- 2R partial @ 40% (not 1.5R @ 60-80%)
- Daily regime gate (additional quality filter)
- GBPJPY only (convexity specialist)
"""

from typing import Optional
import logging

import pandas as pd

from src.strategies.base_strategy import BaseStrategy
from src.signal import Signal
from src.config import (
    SWINGRIDER_BASE_RISK_PCT,
    SWINGRIDER_PARTIAL_EXIT_R,
    SWINGRIDER_PARTIAL_EXIT_PCT,
    SWINGRIDER_DAILY_REGIME_FILTER_ENABLED,
    SWINGRIDER_DAILY_EMA_PERIOD,
    PIP_SIZE,
)

log = logging.getLogger(__name__)


class SwingRider(BaseStrategy):
    """
    Hybrid swing trading system for GBPJPY.

    Combines proven Range Bar resumption entry with superior daily Chandelier exit.
    """

    name = "SwingRider"
    allowed_pairs = ["GBPJPY"]

    # NO min_score/max_score (doesn't use DCRD for entry selection)
    allow_gap_adjacent = True

    # Exit config overrides
    partial_exit_r = SWINGRIDER_PARTIAL_EXIT_R  # 2.0
    partial_exit_pct_override = SWINGRIDER_PARTIAL_EXIT_PCT  # 0.40
    base_risk_pct = SWINGRIDER_BASE_RISK_PCT  # 0.007 (0.7%)

    def analyze(
        self,
        range_bars: pd.DataFrame,
        ohlc_4h: pd.DataFrame,
        ohlc_1h: pd.DataFrame,
        composite_score: float,
        news_state: dict,
        **kwargs
    ) -> Optional[Signal]:
        """
        Analyze GBPJPY for swing entries using Range Bar resumption + daily regime gate.

        Entry Flow:
        1. Check daily regime filter (EMA50 + structure) - GATE
        2. Detect Range Bar staircase (5+ bars impulse)
        3. Detect pullback (2-4 counter bars)
        4. Detect resumption bar (entry trigger)
        5. Calculate swing SL (staircase depth × multiplier × bar size)

        Parameters
        ----------
        range_bars : pd.DataFrame
            Range Bar data (20-pip for GBPJPY)
        ohlc_4h : pd.DataFrame
            4H OHLC data (not used for entry)
        ohlc_1h : pd.DataFrame
            1H OHLC data (not used for entry)
        composite_score : float
            DCRD score (not used for entry)
        news_state : dict
            News gating state (contains pair)
        **kwargs : dict
            Optional params including ohlc_daily

        Returns
        -------
        Signal or None
            Entry signal if all conditions met
        """
        # GBPJPY-only filter
        pair = news_state.get("pair")
        if pair != "GBPJPY":
            return None

        # Ensure we have enough Range Bar data
        if len(range_bars) < 20:
            return None

        # Step 1: Daily regime filter (GATE)
        if SWINGRIDER_DAILY_REGIME_FILTER_ENABLED:
            ohlc_daily = kwargs.get('ohlc_daily')
            if ohlc_daily is None or ohlc_daily.empty:
                return None  # Cannot apply daily filter without daily data

            if len(ohlc_daily) < 50:
                return None  # Not enough daily data

            # Check daily regime
            direction = self._check_daily_regime(ohlc_daily)
            if direction is None:
                return None  # No clear daily regime
        else:
            direction = None  # Will be determined by staircase

        # Step 2: Detect staircase (impulse phase)
        staircase_direction, staircase_depth = self._detect_staircase(range_bars)
        if staircase_depth < 5:
            return None  # No valid staircase

        # If daily regime filter enabled, check alignment
        if direction is not None:
            if staircase_direction != direction:
                return None  # Staircase direction doesn't match daily regime

        # Use staircase direction for entry
        direction = staircase_direction

        # Step 3: Detect pullback
        if not self._detect_pullback(range_bars, direction):
            return None  # No pullback detected

        # Step 4: Detect resumption bar (entry trigger)
        if not self._detect_resumption_bar(range_bars, direction):
            return None  # No resumption bar

        # Step 5: Calculate entry and swing SL
        last_bar = range_bars.iloc[-1]
        entry = last_bar["close"]
        pip_size = PIP_SIZE.get(pair, 0.01)

        # Calculate swing SL based on staircase depth
        sl = self._calculate_swing_sl(
            entry=entry,
            direction=direction,
            staircase_depth=staircase_depth,
            bar_size_pips=20,  # GBPJPY Range Bar size
            pip_size=pip_size,
        )

        # Calculate 1R target (for interface compatibility)
        sl_distance = abs(entry - sl)
        if direction == "BUY":
            tp_1r = entry + sl_distance
        else:
            tp_1r = entry - sl_distance

        # Log entry details
        sl_distance_pips = sl_distance / pip_size

        log.info(
            f"SwingRider {direction} signal @ {entry:.3f} | "
            f"SL: {sl:.3f} ({sl_distance_pips:.0f} pips) | "
            f"Staircase: {staircase_depth} bars | "
            f"Entry: resumption bar"
        )

        # Store staircase low/high as swing_level for tracking
        swing_level = self._get_staircase_extreme(range_bars, direction, staircase_depth)

        # Return signal
        return Signal(
            timestamp=last_bar["end_time"],  # Range Bar end time
            pair=pair,
            direction=direction,
            entry=entry,
            sl=sl,
            tp_1r=tp_1r,
            strategy=self.name,
            composite_score=0.0,  # Not used (set to 0 for clarity)
            partial_exit_pct=self.partial_exit_pct_override,  # 0.40
            swing_level=swing_level,  # Store for tracking
        )

    def _check_daily_regime(self, ohlc_daily: pd.DataFrame) -> Optional[str]:
        """
        Check daily chart for clear directional regime.

        Long: Price above EMA50 + upward slope + HH/HL structure
        Short: Price below EMA50 + downward slope + LL/LH structure

        Returns "BUY", "SELL", or None
        """
        from src.utils.swing_rider_helpers import check_daily_long_regime, check_daily_short_regime

        if check_daily_long_regime(ohlc_daily, SWINGRIDER_DAILY_EMA_PERIOD):
            return "BUY"
        elif check_daily_short_regime(ohlc_daily, SWINGRIDER_DAILY_EMA_PERIOD):
            return "SELL"
        else:
            return None

    def _detect_staircase(self, range_bars: pd.DataFrame) -> tuple[Optional[str], int]:
        """
        Detect consecutive trending Range Bars (impulse phase).

        Returns (direction, depth) where depth is number of consecutive bars.
        Returns (None, 0) if no valid staircase.
        """
        if len(range_bars) < 10:
            return None, 0

        recent = range_bars.tail(15)

        # Count upward staircase
        up_count = 0
        for i in range(len(recent) - 1, 0, -1):
            curr = recent.iloc[i]
            prev = recent.iloc[i - 1]
            if curr["high"] > prev["high"] and curr["low"] >= prev["low"]:
                up_count += 1
            else:
                break

        # Count downward staircase
        down_count = 0
        for i in range(len(recent) - 1, 0, -1):
            curr = recent.iloc[i]
            prev = recent.iloc[i - 1]
            if curr["low"] < prev["low"] and curr["high"] <= prev["high"]:
                down_count += 1
            else:
                break

        # Return strongest staircase
        if up_count >= 5:
            return "BUY", up_count
        elif down_count >= 5:
            return "SELL", down_count
        else:
            return None, 0

    def _detect_pullback(self, range_bars: pd.DataFrame, direction: str) -> bool:
        """
        Detect 2-4 counter-trend bars in recent history.

        Returns True if pullback detected.
        """
        if len(range_bars) < 8:
            return False

        recent = range_bars.tail(8)
        counter_bars = 0

        for i in range(1, len(recent)):
            bar = recent.iloc[i]
            prev = recent.iloc[i - 1]

            # Count counter-trend bars
            if direction == "BUY":
                if bar["close"] < prev["close"]:
                    counter_bars += 1
            else:  # SELL
                if bar["close"] > prev["close"]:
                    counter_bars += 1

        # Look for 2-4 counter bars
        return 2 <= counter_bars <= 4

    def _detect_resumption_bar(self, range_bars: pd.DataFrame, direction: str) -> bool:
        """
        Detect resumption bar (first trend-direction bar after pullback).

        Entry trigger: Last bar closes in trend direction relative to previous bar.
        """
        if len(range_bars) < 2:
            return False

        last_bar = range_bars.iloc[-1]
        prev_bar = range_bars.iloc[-2]

        if direction == "BUY":
            # Bullish resumption: close above previous high
            return last_bar["close"] > prev_bar["high"]
        else:  # SELL
            # Bearish resumption: close below previous low
            return last_bar["close"] < prev_bar["low"]

    def _calculate_swing_sl(
        self,
        entry: float,
        direction: str,
        staircase_depth: int,
        bar_size_pips: int,
        pip_size: float,
    ) -> float:
        """
        Calculate swing SL based on staircase depth.

        SL Distance = Staircase Depth × SL Multiplier × Bar Size

        SL Multiplier (adaptive):
        - Strong staircase (10+ bars): 1.5×
        - Moderate staircase (7-9 bars): 2.0×
        - Weak staircase (5-6 bars): 2.5×

        Capped at 200-500 pips for GBPJPY.
        """
        # Adaptive multiplier based on staircase strength
        if staircase_depth >= 10:
            multiplier = 1.5  # Strong staircase → tighter SL
        elif staircase_depth >= 7:
            multiplier = 2.0  # Moderate staircase
        else:  # 5-6 bars
            multiplier = 2.5  # Weak staircase → wider SL

        # Calculate SL distance in pips
        sl_distance_pips = staircase_depth * multiplier * bar_size_pips

        # Cap at 200-500 pips
        sl_distance_pips = max(200, min(500, sl_distance_pips))

        # Convert to price
        sl_distance = sl_distance_pips * pip_size

        # Place SL
        if direction == "BUY":
            sl = entry - sl_distance
        else:  # SELL
            sl = entry + sl_distance

        log.debug(
            f"SwingRider SL calc: staircase={staircase_depth} bars, "
            f"multiplier={multiplier:.1f}×, distance={sl_distance_pips:.0f} pips"
        )

        return sl

    def _get_staircase_extreme(
        self, range_bars: pd.DataFrame, direction: str, staircase_depth: int
    ) -> float:
        """
        Get the extreme (high/low) of the staircase for swing_level tracking.
        """
        if len(range_bars) < staircase_depth:
            return 0.0

        staircase_bars = range_bars.tail(staircase_depth + 5).head(staircase_depth)

        if direction == "BUY":
            # Swing low = lowest low in staircase
            return staircase_bars["low"].min()
        else:  # SELL
            # Swing high = highest high in staircase
            return staircase_bars["high"].max()
