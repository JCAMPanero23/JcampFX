"""
JcampFX — Exit Management System (Phase 2, PRD §5)

Handles all post-entry exit logic:
  Stage 1: Regime-aware partial exit at 1.5R
  Stage 2: Dynamic Chandelier SL on remaining runner

REVISED (v2.1): Moved from Phase 4 to Phase 2 so backtests use real exit logic.

Partial Exit Tiers (PRD §5.1):
    CompositeScore > 85  → close 60%, keep 40% runner
    CompositeScore 70–85 → close 70%, keep 30% runner
    CompositeScore 30–70 → close 75%, keep 25% runner
    CompositeScore < 30  → close 80%, keep 20% runner

Dynamic Chandelier SL (PRD §5.1):
    chandelier_distance = max(0.5R, ATR(14))
    Floor: 15 pips majors (EURUSD, GBPUSD, USDCHF) | 25 pips JPY (USDJPY, AUDJPY)
    Trails only in profitable direction (never widens)

Key rule (VE.7): partial exit % uses CompositeScore AT ENTRY (frozen), not at 1.5R hit time.

Validation:
    VE.1 — Partial exit fires at exactly 1.5R
    VE.2 — Regime-aware split: all 4 tiers correct
    VE.3 — Chandelier = max(0.5R, ATR14) with pip floors
    VE.4 — Chandelier moves only in profitable direction (never widens)
    VE.5 — Runner stays open until Chandelier hit
    VE.6 — Full losers show exactly −1.0R
    VE.7 — CS at entry frozen, not at 1.5R hit time
"""

from __future__ import annotations

import logging

from src.config import (
    CHANDELIER_FLOOR_JPY,
    CHANDELIER_FLOOR_MAJORS,
    JPY_PAIRS,
    PARTIAL_EXIT_R,
    PARTIAL_EXIT_TIERS,
    PIP_SIZE,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Partial exit logic
# ---------------------------------------------------------------------------

def get_partial_exit_pct(composite_score_at_entry: float) -> float:
    """
    Return the fraction of the position to close at 1.5R.

    PRD §5.1 (VE.2): uses CompositeScore frozen at entry time.
    Tiers (first match wins, inclusive lower bounds):
        CS > 85        → 60% — Deep Trending (keep 40% runner)
        CS ≥ 70 ≤ 85  → 70% — Trending (keep 30% runner)
        CS ≥ 30 < 70   → 75% — Transitional (keep 25% runner)
        CS < 30        → 80% — Range (keep 20% runner)
    """
    cs = float(composite_score_at_entry)
    if cs > 85:
        return 0.60
    if cs >= 70:
        return 0.70
    if cs >= 30:
        return 0.75
    return 0.80


def calculate_1_5r_price(entry: float, sl: float, direction: str) -> float:
    """
    Calculate the price at which Stage 1 partial exit fires (1.5R).

    VE.1: partial exit fires at exactly 1.5R from entry.
    """
    r_distance = abs(entry - sl)
    target = PARTIAL_EXIT_R * r_distance
    if direction.upper() == "BUY":
        return entry + target
    return entry - target


def is_at_1_5r(current_price: float, entry: float, sl: float, direction: str) -> bool:
    """
    Return True when price has reached or exceeded the 1.5R level.
    Used in backtesting tick-by-tick simulation.

    A small epsilon (1e-9) handles floating-point rounding at the exact target price.
    """
    target = calculate_1_5r_price(entry, sl, direction)
    _eps = 1e-9
    if direction.upper() == "BUY":
        return current_price >= target - _eps
    return current_price <= target + _eps


# ---------------------------------------------------------------------------
# Chandelier Stop-Loss
# ---------------------------------------------------------------------------

def _chandelier_floor_pips(pair: str) -> int:
    """Return the minimum pip floor for the Chandelier SL."""
    return CHANDELIER_FLOOR_JPY if pair in JPY_PAIRS else CHANDELIER_FLOOR_MAJORS


def _pip_size(pair: str) -> float:
    return PIP_SIZE.get(pair, 0.0001)


def _initial_r_distance_pips(entry: float, sl: float, pair: str) -> float:
    """Return the initial R-distance (entry to SL) in pips."""
    pip = _pip_size(pair)
    return abs(entry - sl) / pip


def initial_chandelier_sl(
    entry: float,
    sl: float,
    direction: str,
    atr14: float,
    pair: str,
) -> float:
    """
    Calculate the initial Chandelier SL price after the partial exit fires.

    chandelier_distance = max(0.5R, ATR14)  in price terms (not pips)
    Minimum floor: 15/25 pips converted to price terms.

    VE.3: distance = max(0.5R, ATR14) with pip floor.

    Parameters
    ----------
    entry     : Entry price
    sl        : Original stop-loss price (used to compute 0.5R)
    direction : "BUY" or "SELL"
    atr14     : ATR(14) value in price terms (from Range Bar timeframe)
    pair      : Canonical pair name (for pip floor selection)
    """
    r_distance = abs(entry - sl)          # 1R in price terms
    half_r = 0.5 * r_distance             # 0.5R in price terms

    pip = _pip_size(pair)
    floor_pips = _chandelier_floor_pips(pair)
    floor_price = floor_pips * pip         # minimum floor in price terms

    chandelier_distance = max(half_r, atr14, floor_price)

    # At the point of partial exit (1.5R), price = entry + 1.5R (for BUY)
    partial_exit_price = calculate_1_5r_price(entry, sl, direction)

    if direction.upper() == "BUY":
        return partial_exit_price - chandelier_distance
    return partial_exit_price + chandelier_distance


def update_chandelier(
    new_extreme: float,
    current_sl: float,
    direction: str,
    atr14: float,
    initial_r_pips: float,
    pair: str,
) -> float:
    """
    Update the Chandelier SL on each new tick/bar in the runner phase.

    The Chandelier moves ONLY in the profitable direction and never widens.
    VE.4: trail by tick in profitable direction only.

    Parameters
    ----------
    new_extreme    : New high (BUY) or new low (SELL) since last update
    current_sl     : Current Chandelier SL price
    direction      : "BUY" or "SELL"
    atr14          : Current ATR(14) in price terms
    initial_r_pips : Original R-distance in pips (for 0.5R calculation)
    pair           : Canonical pair name

    Returns
    -------
    Updated SL (never farther from price than current_sl).
    """
    pip = _pip_size(pair)
    half_r_price = 0.5 * initial_r_pips * pip

    floor_pips = _chandelier_floor_pips(pair)
    floor_price = floor_pips * pip

    chandelier_distance = max(half_r_price, atr14, floor_price)

    if direction.upper() == "BUY":
        proposed_sl = new_extreme - chandelier_distance
        # Never move SL backwards (never below current_sl for a BUY)
        return max(current_sl, proposed_sl)
    else:
        proposed_sl = new_extreme + chandelier_distance
        # For SELL: SL moves down, never above current_sl
        return min(current_sl, proposed_sl)


def is_chandelier_hit(current_price: float, chandelier_sl: float, direction: str) -> bool:
    """
    Return True when price crosses the Chandelier SL (runner close trigger).
    VE.5: runner stays open until this fires.
    """
    if direction.upper() == "BUY":
        return current_price <= chandelier_sl
    return current_price >= chandelier_sl


# ---------------------------------------------------------------------------
# R-multiple calculation helpers (for performance tracker and backtester)
# ---------------------------------------------------------------------------

def calculate_r_multiple(
    entry: float,
    exit_price: float,
    sl: float,
    direction: str,
) -> float:
    """
    Calculate the R-multiple for a trade leg.

    R = (exit - entry) / (entry - sl)   for BUY
    R = (entry - exit) / (sl - entry)   for SELL

    VE.6: full losers → exactly −1.0R (when exit = original SL).
    """
    r_distance = abs(entry - sl)
    if r_distance <= 0:
        return 0.0

    if direction.upper() == "BUY":
        return (exit_price - entry) / r_distance
    return (entry - exit_price) / r_distance


def expected_locked_profit_r(partial_pct: float) -> float:
    """
    Return the R-value locked in by the partial exit at 1.5R.
    partial_pct = fraction of position closed at 1.5R (e.g. 0.70)
    Returns partial_pct × 1.5R
    """
    return partial_pct * PARTIAL_EXIT_R
