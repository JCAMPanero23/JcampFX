"""
JcampFX — Backtester Cost Model (Phase 3, PRD §9.1)

Applies realistic broker costs to every simulated trade:
  - Slippage: 1.0 pip on ALL entries AND exits
  - Commission: $7.00 round-trip per standard lot (FP Markets ECN)

Slippage direction convention:
  Entry  BUY  → price worsens UP   (you pay more)
  Entry  SELL → price worsens DOWN (you sell for less)
  Exit   BUY  → price worsens DOWN (you receive less)
  Exit   SELL → price worsens UP   (you pay more to cover)
"""

from __future__ import annotations

from src.config import COMMISSION_PER_LOT_RT, PIP_SIZE, SLIPPAGE_PIPS


def _pip(pair: str) -> float:
    return PIP_SIZE.get(pair, 0.0001)


def apply_entry_slippage(price: float, direction: str, pair: str) -> float:
    """
    Worsen the entry price by SLIPPAGE_PIPS in the direction that hurts the trader.

    BUY:  you pay more  → price moves UP
    SELL: you sell less → price moves DOWN
    """
    slip = SLIPPAGE_PIPS * _pip(pair)
    if direction.upper() == "BUY":
        return price + slip
    return price - slip


def apply_exit_slippage(price: float, direction: str, pair: str) -> float:
    """
    Worsen the exit price by SLIPPAGE_PIPS in the direction that hurts the trader.

    BUY exit (closing long):  you receive less → price moves DOWN
    SELL exit (closing short): you pay more    → price moves UP
    """
    slip = SLIPPAGE_PIPS * _pip(pair)
    if direction.upper() == "BUY":
        return price - slip
    return price + slip


def round_trip_commission(lot_size: float) -> float:
    """
    Return the full round-trip commission cost in USD.

    Charged once at trade open (covers both entry and exit legs).
    """
    return COMMISSION_PER_LOT_RT * lot_size
