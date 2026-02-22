"""
JcampFX — BacktestTrade state machine (Phase 3, PRD §9.1)

A BacktestTrade has two phases:
  "open"   → monitoring for 1.5R partial exit or original SL
  "runner" → partial exit fired; monitoring Chandelier SL on remaining position
  "closed" → trade completed (SL_HIT | CHANDELIER_HIT | 2R_CAP | WEEKEND_CLOSE)

The partial_exit_pct and composite_score are frozen at entry time (VE.7).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


@dataclass
class BacktestTrade:
    """Mutable trade state for the backtester event loop."""

    # Identity
    trade_id: str
    pair: str
    direction: str          # "BUY" | "SELL"
    strategy: str           # "TrendRider" | "BreakoutRider" | "RangeRider"

    # Entry (after slippage)
    entry_price: float
    sl_price: float
    entry_time: pd.Timestamp
    lot_size: float
    initial_r_pips: float   # abs(entry - sl) / pip_size — for R-multiple calc

    # DCRD frozen at entry (VE.7)
    composite_score: float
    partial_exit_pct: float  # 0.60 | 0.70 | 0.75 | 0.80

    # DCRD layer breakdown (stored for accurate Trade Inspector display)
    regime: str = "transitional"  # "trending" | "breakout" | "ranging" | "transitional"
    layer1_structural: float = 0.0
    layer2_modifier: float = 0.0
    layer3_rb_intelligence: float = 0.0

    # Trade state machine
    phase: str = "open"     # "open" | "runner" | "closed"

    # Partial exit (populated when 1.5R reached)
    partial_exit_price: float = 0.0
    partial_exit_time: Optional[pd.Timestamp] = None
    chandelier_sl: float = 0.0  # Set by initial_chandelier_sl() at partial exit

    # Range Bar trailing exit fields (Phase 3.1.1 — 3-bar SL system)
    trailing_sl: float = 0.0              # Range Bar trailing SL (replaces chandelier_sl)
    counter_trend_bar_count: int = 0      # Consecutive counter-trend bars in runner
    last_bar_direction: str = ""          # "trend" or "counter" (for tracking consecutive)

    # Close (populated when trade ends)
    close_price: float = 0.0
    close_time: Optional[pd.Timestamp] = None
    close_reason: str = ""   # "SL_HIT" | "CHANDELIER_HIT" | "2R_CAP" | "WEEKEND_CLOSE"

    # Results (populated on close by BacktestAccount.close_trade)
    r_multiple_partial: float = 0.0   # R earned on partial exit leg
    r_multiple_runner: float = 0.0    # R earned on runner leg
    r_multiple_total: float = 0.0     # Weighted average total R
    pnl_usd: float = 0.0             # Net PnL after commission
    commission_usd: float = 0.0       # Commission charged at entry

    # ATR snapshot at partial exit (used for chandelier initialisation)
    atr14_at_partial: float = 0.0

    # Debug metadata (TrendRider only -- None for other strategies)
    adx_at_entry: Optional[float] = None
    adx_slope_rising: Optional[bool] = None
    staircase_depth: Optional[int] = None
    pullback_bar_idx: Optional[int] = None     # absolute index in Range Bar cache
    pullback_depth_pips: Optional[float] = None
    entry_bar_idx: Optional[int] = None        # absolute index in Range Bar cache

    def is_open(self) -> bool:
        return self.phase in ("open", "runner")

    def is_closed(self) -> bool:
        return self.phase == "closed"

    def to_dict(self) -> dict:
        """Serialise to flat dict for trade log DataFrame."""
        return {
            "trade_id": self.trade_id,
            "pair": self.pair,
            "direction": self.direction,
            "strategy": self.strategy,
            "entry_time": self.entry_time,
            "entry_price": self.entry_price,
            "sl_price": self.sl_price,
            "lot_size": self.lot_size,
            "composite_score": self.composite_score,
            "regime": self.regime,
            "layer1_structural": self.layer1_structural,
            "layer2_modifier": self.layer2_modifier,
            "layer3_rb_intelligence": self.layer3_rb_intelligence,
            "partial_exit_pct": self.partial_exit_pct,
            "partial_exit_price": self.partial_exit_price,
            "partial_exit_time": self.partial_exit_time,
            "close_price": self.close_price,
            "close_time": self.close_time,
            "close_reason": self.close_reason,
            "r_multiple_partial": self.r_multiple_partial,
            "r_multiple_runner": self.r_multiple_runner,
            "r_multiple_total": self.r_multiple_total,
            "pnl_usd": self.pnl_usd,
            "commission_usd": self.commission_usd,
            "adx_at_entry": self.adx_at_entry,
            "adx_slope_rising": self.adx_slope_rising,
            "staircase_depth": self.staircase_depth,
            "pullback_bar_idx": self.pullback_bar_idx,
            "pullback_depth_pips": self.pullback_depth_pips,
            "entry_bar_idx": self.entry_bar_idx,
        }
