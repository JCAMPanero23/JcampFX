"""
JcampFX — Session Filter (v2.2, PRD §6)

Provides session tagging and per-strategy session gating.

Session definitions (UTC hours):
  Tokyo    : 00:00–09:00  — JPY pairs active, majors low-volatility
  London   : 07:00–16:00  — Highest volatility, trend initiation
  New York : 12:00–21:00  — Continuation or reversal of London moves
  Overlap  : 12:00–16:00  — Peak liquidity (London/NY intersection)
  Off-Hours: 21:00–00:00  — Low liquidity, wide spreads

Note: Sessions overlap (London+Tokyo share 07:00–09:00; London+NY share 12:00–16:00).
A timestamp can belong to multiple sessions simultaneously.

Per-strategy filter modes (PRD §6.3):
  TrendRider    : London, NY, Overlap — HARD filter for EUR/GBP/CHF vs Tokyo
  BreakoutRider : London Open (07–09), NY Open (12–14) — HARD filter
  RangeRider    : Tokyo (JPY), Late NY (18–21) — SOFT filter (log only)

Validation:
  VS.1 — Session detection correctly identifies all sessions from server time
  VS.2 — TrendRider blocked from EURUSD during Tokyo session (hard filter)
  VS.3 — BreakoutRider active only during London Open and NY Open windows
  VS.4 — RangeRider on JPY pairs allowed during Tokyo (soft filter)
  VS.5 — Session-blocked signals logged as SESSION_BLOCKED with details
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from src.config import (
    SESSION_LONDON_END,
    SESSION_LONDON_START,
    SESSION_NY_END,
    SESSION_NY_START,
    SESSION_OFF_HOURS_END,
    SESSION_OFF_HOURS_START,
    SESSION_OVERLAP_END,
    SESSION_OVERLAP_START,
    SESSION_TOKYO_END,
    SESSION_TOKYO_START,
    JPY_PAIRS,
)

log = logging.getLogger(__name__)

# Session tag constants
SESSION_TOKYO = "Tokyo"
SESSION_LONDON = "London"
SESSION_NY = "NY"
SESSION_OVERLAP = "Overlap"
SESSION_OFF_HOURS = "Off-Hours"

# London Open and NY Open sub-windows for BreakoutRider (hard filter)
_LONDON_OPEN_START = 7
_LONDON_OPEN_END = 9
_NY_OPEN_START = 12
_NY_OPEN_END = 14

# Late NY sub-window for RangeRider (soft filter)
_LATE_NY_START = 18
_LATE_NY_END = 21

# JPY pairs that benefit from Tokyo session
_JPY_PAIR_SET = JPY_PAIRS

# Pairs that are blocked from Tokyo session for TrendRider (hard filter)
_TOKYO_BLOCKED_PAIRS = {"EURUSD", "GBPUSD", "USDCHF"}


def get_active_sessions(utc_time: datetime | pd.Timestamp) -> set[str]:
    """
    Return the set of active session names for the given UTC time.

    VS.1: Correctly identifies Tokyo/London/NY/Overlap/Off-Hours from server time.
    A timestamp can be in multiple sessions simultaneously.
    """
    if isinstance(utc_time, pd.Timestamp):
        hour = utc_time.hour
    else:
        hour = utc_time.hour

    sessions: set[str] = set()

    if SESSION_TOKYO_START <= hour < SESSION_TOKYO_END:
        sessions.add(SESSION_TOKYO)

    if SESSION_LONDON_START <= hour < SESSION_LONDON_END:
        sessions.add(SESSION_LONDON)

    if SESSION_NY_START <= hour < SESSION_NY_END:
        sessions.add(SESSION_NY)

    if SESSION_OVERLAP_START <= hour < SESSION_OVERLAP_END:
        sessions.add(SESSION_OVERLAP)

    # Off-Hours wraps midnight (21:00–00:00)
    if hour >= SESSION_OFF_HOURS_START or hour < SESSION_OFF_HOURS_END:
        sessions.add(SESSION_OFF_HOURS)

    # If nothing matched (shouldn't happen but guard): treat as Off-Hours
    if not sessions:
        sessions.add(SESSION_OFF_HOURS)

    return sessions


def get_session_tag(utc_time: datetime | pd.Timestamp) -> str:
    """
    Return the primary session name for logging/signal tagging.
    Priority: Overlap > London > NY > Tokyo > Off-Hours
    """
    sessions = get_active_sessions(utc_time)
    for s in (SESSION_OVERLAP, SESSION_LONDON, SESSION_NY, SESSION_TOKYO, SESSION_OFF_HOURS):
        if s in sessions:
            return s
    return SESSION_OFF_HOURS


def is_trend_rider_allowed(pair: str, utc_time: datetime | pd.Timestamp) -> tuple[bool, str]:
    """
    TrendRider hard filter (Phase 3.4 Filter 2):
    - Blocked during Off-Hours for all pairs
    - Blocked during Tokyo-only for ALL pairs (not just EUR/GBP/CHF)
    - Requires London or NY session for entry

    Entry quality analysis showed Tokyo-only has 66.7% SL hit rate vs 55.2% for NY.
    Filter 2 strengthens session requirements to improve entry quality.

    VS.2: TrendRider blocked from EURUSD during Tokyo session (hard filter).

    Returns (allowed, reason_if_blocked).
    """
    sessions = get_active_sessions(utc_time)

    # Block Off-Hours (no major session active)
    if SESSION_OFF_HOURS in sessions and SESSION_LONDON not in sessions and SESSION_NY not in sessions:
        return False, f"SESSION_BLOCKED:TrendRider:Off-Hours:{pair}"

    # Filter 2 (Phase 3.4): Block Tokyo-only for ALL pairs
    # Require at least London or NY session active (not just Tokyo)
    if SESSION_TOKYO in sessions:
        if SESSION_LONDON not in sessions and SESSION_NY not in sessions:
            return False, f"SESSION_BLOCKED:TrendRider:Tokyo-only:{pair}"

    # Require at least one major session (London or NY) active
    if SESSION_LONDON not in sessions and SESSION_NY not in sessions:
        return False, f"SESSION_BLOCKED:TrendRider:No-major-session:{pair}"

    return True, ""


def is_breakout_rider_allowed(utc_time: datetime | pd.Timestamp) -> tuple[bool, str]:
    """
    BreakoutRider hard filter: only active during London Open (07–09) or NY Open (12–14).

    VS.3: BreakoutRider active only during London Open and NY Open windows.

    Returns (allowed, reason_if_blocked).
    """
    if isinstance(utc_time, pd.Timestamp):
        hour = utc_time.hour
    else:
        hour = utc_time.hour

    in_london_open = _LONDON_OPEN_START <= hour < _LONDON_OPEN_END
    in_ny_open = _NY_OPEN_START <= hour < _NY_OPEN_END

    if in_london_open or in_ny_open:
        return True, ""

    return False, f"SESSION_BLOCKED:BreakoutRider:hour={hour} (allowed 07-09,12-14 UTC)"


def is_range_rider_allowed(
    pair: str,
    utc_time: datetime | pd.Timestamp,
    hard_filter: bool = False,
) -> tuple[bool, str]:
    """
    RangeRider soft filter: Tokyo for JPY pairs, Late NY for all pairs.

    VS.4: RangeRider on JPY pairs allowed during Tokyo (soft filter — logs but doesn't block).

    Returns (allowed, reason_if_soft_warning).
    hard_filter=False means log the warning but don't block (soft filter behaviour).
    """
    if isinstance(utc_time, pd.Timestamp):
        hour = utc_time.hour
    else:
        hour = utc_time.hour

    sessions = get_active_sessions(utc_time)
    in_late_ny = _LATE_NY_START <= hour < _LATE_NY_END
    in_tokyo = SESSION_TOKYO in sessions
    is_jpy = pair in _JPY_PAIR_SET

    # Preferred windows: Tokyo for JPY, Late NY for all
    if (in_tokyo and is_jpy) or in_late_ny:
        return True, ""

    # Avoid London/NY Overlap (hard block even for soft filter)
    if SESSION_OVERLAP in sessions:
        reason = f"SESSION_BLOCKED:RangeRider:Overlap:{pair}"
        if hard_filter:
            return False, reason
        log.warning("RangeRider soft session warning: %s", reason)
        return True, reason  # Soft: allow but log

    # Off-hours is fine for RangeRider (mean-reversion suits low-vol)
    if SESSION_OFF_HOURS in sessions:
        return True, ""

    # Outside preferred windows: soft warning
    session_str = ",".join(sorted(sessions))
    reason = f"SESSION_SOFT_WARN:RangeRider:session={session_str}:{pair}"
    log.debug("RangeRider soft session warning: %s", reason)
    return True, reason  # Soft filter — don't block


class SessionFilter:
    """
    Convenience class wrapping per-strategy session checks.
    Used by BrainCore to gate signals before strategy routing.
    """

    def check(
        self,
        strategy_name: str,
        pair: str,
        utc_time: datetime | pd.Timestamp,
    ) -> tuple[bool, str]:
        """
        Check if the strategy is allowed to trade pair at utc_time.

        Returns (allowed, reason_if_blocked).
        Reason is empty string if allowed. SESSION_BLOCKED prefix for hard blocks.
        """
        if strategy_name == "TrendRider":
            return is_trend_rider_allowed(pair, utc_time)
        elif strategy_name == "BreakoutRider":
            return is_breakout_rider_allowed(utc_time)
        elif strategy_name == "RangeRider":
            allowed, reason = is_range_rider_allowed(pair, utc_time)
            if not allowed:
                return False, reason
            # Soft warnings are not blocks — return allowed=True
            return True, ""
        else:
            # Unknown strategy: allow by default
            return True, ""
