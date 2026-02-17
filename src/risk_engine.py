"""
JcampFX — Dynamic Risk Engine (Phase 2, PRD §6)

Computes the dynamic risk percentage (1–3%) for each trade signal.

Formula (PRD §6.1):
    Risk% = BaseRisk × ConfidenceMultiplier × PerformanceMultiplier
    Clamped: min 1.0%, max 3.0%
    If Risk% < 0.8% → SKIP the trade (RISK_TOO_LOW)

Confidence Multiplier (PRD §6.2):
    CS > 85  → 1.2x  (deep regime)
    CS 70–85 or CS < 15 → 1.0x
    CS 45–55 → 0.8x  (mid-transitional uncertainty)
    Within ±5 pts of 30 or 70 boundary → 0.7x  (regime could flip)

Performance Multiplier (PRD §6.3):
    Provided by PerformanceTracker.get_performance_multiplier()

Lot Size Calculation:
    lot_size = (account_equity × risk_pct) / (sl_pips × pip_value)
    Minimum 0.01 lots (MT5 floor)

Validation:
    VR.1 — Risk% always 1.0%–3.0% (or skipped if < 0.8%)
    VR.2 — Confidence multiplier reflects CS distance from boundaries
    VR.5 — Near-boundary trades (±5 pts of 30/70) get 0.7x
    VR.6 — Trades with < 0.8% risk are skipped and logged as RISK_TOO_LOW
"""

from __future__ import annotations

import logging
import math

from src.config import (
    BASE_RISK_PCT,
    MAX_RISK_PCT,
    MIN_LOT,
    MIN_RISK_PCT,
    PIP_SIZE,
    STRATEGY_BREAKOUTRIDER_MIN_CS,
    STRATEGY_TRENDRIDER_MIN_CS,
)

log = logging.getLogger(__name__)

# Near-boundary zone width in points (±5 of 30 or 70)
NEAR_BOUNDARY_WIDTH = 5.0


# ---------------------------------------------------------------------------
# Confidence multiplier (PRD §6.2)
# ---------------------------------------------------------------------------

def get_confidence_multiplier(composite_score: float) -> float:
    """
    Map DCRD CompositeScore to a confidence multiplier.

    VR.5: ±5 points from 30 or 70 boundary → 0.7x (minimum exposure)
    """
    cs = float(composite_score)

    # Near-boundary check (highest priority — VR.5)
    for boundary in (STRATEGY_BREAKOUTRIDER_MIN_CS, STRATEGY_TRENDRIDER_MIN_CS):
        if abs(cs - boundary) <= NEAR_BOUNDARY_WIDTH:
            return 0.7

    # Deep regime (very strong conviction)
    if cs > 85:
        return 1.2

    # Mid-transitional uncertainty zone
    if 45 <= cs <= 55:
        return 0.8

    # Deep range (extreme low — also uncertain)
    if cs < 15:
        return 1.0  # PRD says same as 70–85 for CS < 15

    # Standard zones: 70–85, 15–45 (excl mid-transitional), 55–70 (excl near-boundary)
    return 1.0


# ---------------------------------------------------------------------------
# Risk calculation
# ---------------------------------------------------------------------------

def calculate_risk_pct(
    composite_score: float,
    performance_multiplier: float,
    base_risk: float = BASE_RISK_PCT,
) -> float:
    """
    Compute the final risk percentage.

    Returns the clamped value in [MIN_RISK_PCT, MAX_RISK_PCT] range.
    If the computed value falls below MIN_RISK_PCT (0.8%), the caller
    should call should_skip() — this function still returns the raw clamped value.

    VR.1: clamped to [1.0%, 3.0%] after multipliers, but skipped if < 0.8%
    """
    confidence_mult = get_confidence_multiplier(composite_score)
    raw = base_risk * confidence_mult * performance_multiplier

    # Clamp to [1%, 3%]
    clamped = max(BASE_RISK_PCT, min(MAX_RISK_PCT, raw))
    return round(clamped, 6)


def should_skip(risk_pct: float) -> bool:
    """
    Return True if the trade should be skipped due to insufficient risk precision.

    PRD §6.4: if Risk% < 0.8% after multipliers → skip (RISK_TOO_LOW).
    This prevents lot sizes below 0.01 minimum.

    VR.6: caller must log the skip as RISK_TOO_LOW.
    """
    return risk_pct < MIN_RISK_PCT


# ---------------------------------------------------------------------------
# Lot size calculation
# ---------------------------------------------------------------------------

def calculate_lot_size(
    risk_pct: float,
    account_equity: float,
    sl_pips: float,
    pair: str,
    pip_value_per_lot: float | None = None,
) -> float:
    """
    Calculate lot size from risk parameters.

    Parameters
    ----------
    risk_pct           : Final risk percentage (e.g. 0.01 for 1%)
    account_equity     : Current account equity in USD
    sl_pips            : Stop-loss distance in pips
    pair               : Canonical pair name (for pip size lookup)
    pip_value_per_lot  : USD value of 1 pip per standard lot.
                         If None, uses a default approximation:
                         - USD quote pairs (EURUSD, GBPUSD): ~$10/pip/lot
                         - JPY quote pairs (USDJPY, AUDJPY): ~$6.67/pip/lot @ 150
                         - CHF quote pair (USDCHF): ~$10/pip/lot

    Returns
    -------
    Lot size rounded down to 2 decimal places, minimum 0.01.
    """
    if sl_pips <= 0:
        log.warning("calculate_lot_size: sl_pips=%s — returning MIN_LOT", sl_pips)
        return MIN_LOT

    risk_amount = account_equity * risk_pct

    if pip_value_per_lot is None:
        pip_value_per_lot = _default_pip_value(pair)

    raw_lots = risk_amount / (sl_pips * pip_value_per_lot)

    # Round DOWN to 2 decimal places (never exceed intended risk)
    lots = math.floor(raw_lots * 100) / 100
    return max(MIN_LOT, lots)


def _default_pip_value(pair: str) -> float:
    """
    Approximate pip value per standard lot in USD.

    Accurate estimates are pair-dependent and require current exchange rates.
    Phase 4 (live) will pass the real pip value from MT5.
    For backtesting and Phase 2 unit tests, these approximations are sufficient.
    """
    from src.config import JPY_PAIRS
    if pair in JPY_PAIRS:
        return 6.67   # ~$6.67/pip/lot at USD/JPY ~150
    if pair == "USDCHF":
        return 9.10   # ~$9.10/pip/lot at USD/CHF ~1.10
    if pair == "XAUUSD":
        return 10.0   # Gold: $1/pip but in our context 1 pip = $0.01 * 100 lots
    return 10.0       # USD-quoted pairs: $10/pip/standard lot (EURUSD, GBPUSD)


# ---------------------------------------------------------------------------
# Convenience: full risk package
# ---------------------------------------------------------------------------

def compute_trade_risk(
    composite_score: float,
    performance_multiplier: float,
    account_equity: float,
    sl_pips: float,
    pair: str,
    pip_value_per_lot: float | None = None,
) -> dict:
    """
    One-call helper returning all risk parameters for a trade.

    Returns
    -------
    {
        "risk_pct":          float,   # Final risk %, clamped
        "lot_size":          float,   # Calculated lots (MIN_LOT floor)
        "skip":              bool,    # True if risk_pct < MIN_RISK_PCT
        "skip_reason":       str|None,
        "confidence_mult":   float,
        "performance_mult":  float,
    }
    """
    confidence_mult = get_confidence_multiplier(composite_score)
    risk_pct = calculate_risk_pct(composite_score, performance_multiplier)
    skip = should_skip(risk_pct)
    skip_reason = None

    if skip:
        log.info(
            "RISK_TOO_LOW: pair=%s CS=%.1f conf_mult=%.2f perf_mult=%.2f risk=%.4f%% < %.1f%%",
            pair, composite_score, confidence_mult, performance_multiplier,
            risk_pct * 100, MIN_RISK_PCT * 100,
        )
        skip_reason = "RISK_TOO_LOW"
        lots = 0.0
    else:
        lots = calculate_lot_size(risk_pct, account_equity, sl_pips, pair, pip_value_per_lot)

    return {
        "risk_pct": risk_pct,
        "lot_size": lots,
        "skip": skip,
        "skip_reason": skip_reason,
        "confidence_mult": confidence_mult,
        "performance_mult": performance_multiplier,
    }
