"""
JcampFX — Standardized Signal Dataclass (Phase 2, PRD §8.6 V2.8)

All strategy modules return a Signal (or None). The Brain Core attaches
risk/lot-size/exit data before dispatching to the ZMQ bridge in Phase 4.

Blocked signals (correlation, risk-too-low, news, etc.) use blocked_reason
to preserve auditability — they are logged, not silently dropped (PRD VN.5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


@dataclass
class Signal:
    """
    Standardized trade signal produced by a strategy module.

    Fields set by the strategy
    --------------------------
    timestamp        : UTC bar close time that triggered the signal
    pair             : Canonical pair name (e.g. "EURUSD")
    direction        : "BUY" or "SELL"
    entry            : Proposed entry price
    sl               : Initial stop-loss price
    tp_1r            : Take-profit at 1R distance (for calculating 1.5R target)
    strategy         : Strategy name ("TrendRider" | "BreakoutRider" | "RangeRider")
    composite_score  : DCRD CompositeScore at signal time — FROZEN at entry (PRD VE.7)

    Fields set by Brain Core / Risk Engine
    ---------------------------------------
    risk_pct         : Final dynamic risk percentage (1–3%), 0 if skipped
    partial_exit_pct : Regime-aware partial exit % at 1.5R (0.60 / 0.70 / 0.75 / 0.80)
    lot_size         : Calculated lot size (0.0 until risk engine runs)
    blocked_reason   : Set when signal is generated but blocked before dispatch

    Blocked reason codes
    --------------------
    CORRELATION_BLOCKED  — max 2 trades sharing same base/quote currency
    RISK_TOO_LOW         — calculated risk% < 0.8% (lot size floor)
    NEWS_BLOCKED         — high/medium-impact event window
    MAX_CONCURRENT       — position limit reached
    MAX_DAILY_TRADES     — daily trade counter exhausted
    DAILY_LOSS_CAP       — 2R daily loss cap triggered
    STRATEGY_COOLDOWN    — strategy paused (5 consec losses in last 10)
    GOLD_GATE            — XAUUSD blocked until equity >= $2,000
    PHANTOM_BLOCKED      — entry on phantom bar blocked (PRD §8.4, VP.4)
    SESSION_BLOCKED      — entry outside strategy's allowed session (PRD §6.3, VS.5)
    """

    # --- Strategy-provided fields ---
    timestamp: pd.Timestamp
    pair: str
    direction: str            # "BUY" | "SELL"
    entry: float
    sl: float
    tp_1r: float              # price at +1R from entry
    strategy: str
    composite_score: float    # DCRD CS frozen at entry time

    # --- Brain Core / Risk Engine fields (defaults filled in later) ---
    risk_pct: float = 0.0
    partial_exit_pct: float = 0.0
    lot_size: float = 0.0
    blocked_reason: Optional[str] = None
    # v2.2: session tag (Tokyo/London/NY/Overlap/Off-Hours) set by BrainCore (PRD §6.3)
    session_tag: str = ""

    # --- Derived convenience properties ---
    @property
    def risk_pips(self) -> float:
        """Absolute pip distance from entry to SL."""
        from src.config import PIP_SIZE
        pip = PIP_SIZE.get(self.pair, 0.0001)
        return abs(self.entry - self.sl) / pip

    @property
    def tp_1_5r(self) -> float:
        """Price at 1.5R (Stage 1 partial exit trigger)."""
        r_distance = abs(self.entry - self.tp_1r)
        if self.direction == "BUY":
            return self.entry + 1.5 * r_distance
        return self.entry - 1.5 * r_distance

    @property
    def is_blocked(self) -> bool:
        return self.blocked_reason is not None

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "pair": self.pair,
            "direction": self.direction,
            "entry": self.entry,
            "sl": self.sl,
            "tp_1r": self.tp_1r,
            "tp_1_5r": self.tp_1_5r,
            "strategy": self.strategy,
            "composite_score": self.composite_score,
            "risk_pct": self.risk_pct,
            "partial_exit_pct": self.partial_exit_pct,
            "lot_size": self.lot_size,
            "blocked_reason": self.blocked_reason,
            "session_tag": self.session_tag,
        }
