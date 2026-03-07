"""
JcampFX — DCRD (Dynamic Composite Regime Detection) package.

Public API:
    from src.dcrd import DCRDEngine
    engine = DCRDEngine()
    score, regime = engine.score(ohlc_4h, ohlc_1h, range_bars, csm_data, pair)
"""

from src.dcrd.dcrd_engine import DCRDEngine

__all__ = ["DCRDEngine"]
