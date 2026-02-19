"""
JcampFX — DCRD Calibration Script (v2.2, PRD §4)

Generates data-driven percentile thresholds for the DCRD engine.

PRD §4.2 — Calibration Process:
  Step 1: Compute DCRD component values across the full 2+ year dataset
  Step 2: Analyze distributions (P25, P75)
  Step 3: Store thresholds in dcrd_config.json
  Step 4: DCRD layers load thresholds at startup instead of using hardcoded values

Validation:
  VC.1 — Percentile distributions computed for ADX, ATR ratio, and RB speed
  VC.2 — Calibrated thresholds differ meaningfully from v2.1 fixed values
  VC.4 — dcrd_config.json generated and loadable by DCRD Engine at startup
  VC.5 — RB Speed thresholds recalibrated for 20-pip bar frequency
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _atr(ohlc: pd.DataFrame, period: int = 14) -> pd.Series:
    high = ohlc["high"]
    low = ohlc["low"]
    prev_close = ohlc["close"].shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def _adx(ohlc: pd.DataFrame, period: int = 14) -> pd.Series:
    high = ohlc["high"]
    low = ohlc["low"]
    prev_high = high.shift(1)
    prev_low = low.shift(1)
    prev_close = ohlc["close"].shift(1)

    dm_plus = (high - prev_high).clip(lower=0)
    dm_minus = (prev_low - low).clip(lower=0)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    atr = tr.ewm(span=period, adjust=False).mean()
    di_plus = 100 * dm_plus.ewm(span=period, adjust=False).mean() / (atr + 1e-9)
    di_minus = 100 * dm_minus.ewm(span=period, adjust=False).mean() / (atr + 1e-9)
    dx = 100 * (di_plus - di_minus).abs() / (di_plus + di_minus + 1e-9)
    return dx.ewm(span=period, adjust=False).mean()


def compute_adx_distribution(ohlc_4h: pd.DataFrame) -> dict[str, float]:
    """
    Compute P25/P75 for ADX(14) on 4H OHLC.
    Used by structural_score Layer 1 (ADX Strength component).
    """
    if len(ohlc_4h) < 100:
        return {"p25": 18.0, "p75": 25.0}  # v2.1 defaults

    adx_series = _adx(ohlc_4h, period=14).dropna()
    if len(adx_series) < 50:
        return {"p25": 18.0, "p75": 25.0}

    return {
        "p25": float(np.percentile(adx_series, 25)),
        "p75": float(np.percentile(adx_series, 75)),
    }


def compute_atr_ratio_distribution(ohlc_4h: pd.DataFrame) -> dict[str, float]:
    """
    Compute P25/P75 for ATR ratio (current ATR / 20-bar rolling ATR mean).
    Used by structural_score Layer 1 (ATR Expansion component).
    """
    if len(ohlc_4h) < 50:
        return {"p25": 0.85, "p75": 1.25}  # v2.1 defaults

    atr_series = _atr(ohlc_4h, period=14).dropna()
    if len(atr_series) < 30:
        return {"p25": 0.85, "p75": 1.25}

    rolling_avg = atr_series.rolling(20).mean()
    ratio = (atr_series / (rolling_avg + 1e-9)).dropna()

    return {
        "p25": float(np.percentile(ratio, 25)),
        "p75": float(np.percentile(ratio, 75)),
    }


def compute_bb_width_distribution(ohlc_1h: pd.DataFrame, period: int = 20) -> dict[str, float]:
    """
    Compute P20/P80 for BB Width on 1H OHLC.
    Used by dynamic_modifier Layer 2 (BB Width sub-component).
    """
    if len(ohlc_1h) < period + 50:
        return {"p20": 0.002, "p80": 0.008}  # safe defaults

    mid = ohlc_1h["close"].rolling(period).mean()
    sigma = ohlc_1h["close"].rolling(period).std()
    bb_width = (2 * 2.0 * sigma) / (mid + 1e-9)
    bb_width = bb_width.dropna()

    return {
        "p20": float(np.percentile(bb_width, 20)),
        "p80": float(np.percentile(bb_width, 80)),
    }


def compute_rb_speed_distribution(range_bars: pd.DataFrame) -> dict[str, float]:
    """
    Compute P25/P75 for Range Bar speed (bars per 60-minute window).
    Recalibrated for 20-pip bars (VC.5): fewer bars/hour expected vs 10-pip.

    Falls back to safe defaults if insufficient data.
    """
    if len(range_bars) < 100 or "start_time" not in range_bars.columns:
        # v2.2 defaults for 20-pip bars (approx. half the frequency of 10-pip)
        return {"p25": 1.0, "p75": 3.0}

    start_times = pd.to_datetime(range_bars["start_time"], utc=True)
    end_times = pd.to_datetime(range_bars["end_time"], utc=True)

    # Sample speed at each bar: count bars that ENDED in the past 60 min
    speeds: list[float] = []
    window_td = pd.Timedelta(minutes=60)

    # Sample every 10th bar for efficiency
    sample_indices = range(60, len(range_bars), 10)
    for i in sample_indices:
        ref_time = end_times.iloc[i]
        cutoff = ref_time - window_td
        count = (end_times.iloc[:i] >= cutoff).sum()
        speeds.append(float(count))

    if len(speeds) < 10:
        return {"p25": 1.0, "p75": 3.0}

    return {
        "p25": float(np.percentile(speeds, 25)),
        "p75": float(np.percentile(speeds, 75)),
    }


def calibrate(
    pairs: list[str],
    data_dir: str = "data",
    output_path: Optional[str] = None,
    holdout_months: int = 3,
) -> dict:
    """
    Run the full DCRD calibration process across all pairs.

    PRD §4.2: Computes distributions across the full 2-year dataset (excluding
    the holdout period which is used for accuracy validation).

    Parameters
    ----------
    pairs          : Canonical pair names (e.g. ["EURUSD", "GBPUSD", ...])
    data_dir       : Root data directory
    output_path    : Override output path for dcrd_config.json
    holdout_months : Last N months excluded from calibration (held for validation)

    Returns
    -------
    dict: calibration config (also written to dcrd_config.json)
    """
    from src.config import DCRD_CONFIG_PATH, DATA_OHLC_4H_DIR, DATA_OHLC_1H_DIR, DATA_RANGE_BARS_DIR, RANGE_BAR_PIPS

    data_path = PROJECT_ROOT / data_dir
    out = output_path or str(PROJECT_ROOT / DCRD_CONFIG_PATH)

    adx_all: list[float] = []
    atr_ratio_all: list[float] = []
    bb_width_all: list[float] = []
    rb_speed_all_per_pair: list[dict] = []

    holdout_cutoff = pd.Timestamp.utcnow() - pd.DateOffset(months=holdout_months)

    for pair in pairs:
        log.info("Calibrating %s ...", pair)

        # Load 4H OHLC
        ohlc_4h_path = data_path / "ohlc_4h" / f"{pair}_H4.parquet"
        if not ohlc_4h_path.exists():
            log.warning("Missing 4H OHLC for %s — skipping", pair)
            continue

        ohlc_4h = pd.read_parquet(ohlc_4h_path)
        ohlc_4h["time"] = pd.to_datetime(ohlc_4h["time"], utc=True)
        # Exclude holdout period
        ohlc_4h = ohlc_4h[ohlc_4h["time"] < holdout_cutoff].reset_index(drop=True)

        if len(ohlc_4h) < 100:
            log.warning("%s: insufficient 4H data (%d rows) — skipping", pair, len(ohlc_4h))
            continue

        # ADX distribution
        adx_series = _adx(ohlc_4h, period=14).dropna()
        adx_all.extend(adx_series.tolist())

        # ATR ratio distribution
        atr_series = _atr(ohlc_4h, period=14).dropna()
        rolling_avg = atr_series.rolling(20).mean()
        ratio = (atr_series / (rolling_avg + 1e-9)).dropna()
        atr_ratio_all.extend(ratio.tolist())

        # 1H OHLC for BB width
        ohlc_1h_path = data_path / "ohlc_1h" / f"{pair}_H1.parquet"
        if ohlc_1h_path.exists():
            ohlc_1h = pd.read_parquet(ohlc_1h_path)
            ohlc_1h["time"] = pd.to_datetime(ohlc_1h["time"], utc=True)
            ohlc_1h = ohlc_1h[ohlc_1h["time"] < holdout_cutoff].reset_index(drop=True)
            bb_dist = compute_bb_width_distribution(ohlc_1h)
            bb_width_all.extend([bb_dist["p20"], bb_dist["p80"]])  # rough accumulation

        # Range Bar speed
        pips = RANGE_BAR_PIPS.get(pair, 20)
        rb_path = data_path / "range_bars" / f"{pair}_RB{pips}.parquet"
        if rb_path.exists():
            rb_df = pd.read_parquet(rb_path)
            rb_df["end_time"] = pd.to_datetime(rb_df["end_time"], utc=True)
            rb_df = rb_df[rb_df["end_time"] < holdout_cutoff].reset_index(drop=True)
            speed_dist = compute_rb_speed_distribution(rb_df)
            rb_speed_all_per_pair.append(speed_dist)
        else:
            log.warning("%s: Range Bar cache not found (RB%d) — speed not calibrated", pair, pips)

    # Aggregate across all pairs
    if not adx_all:
        log.warning("No data for calibration — using v2.1 defaults")
        adx_result = {"p25": 18.0, "p75": 25.0}
        atr_result = {"p25": 0.85, "p75": 1.25}
        rb_result = {"p25": 1.0, "p75": 3.0}
        bb_result = {"p20": 0.002, "p80": 0.008}
    else:
        adx_result = {
            "p25": float(np.percentile(adx_all, 25)),
            "p75": float(np.percentile(adx_all, 75)),
        }
        atr_result = {
            "p25": float(np.percentile(atr_ratio_all, 25)),
            "p75": float(np.percentile(atr_ratio_all, 75)),
        }
        # BB width: average the per-pair percentiles
        if bb_width_all:
            bb_result = {
                "p20": float(np.mean([x for i, x in enumerate(bb_width_all) if i % 2 == 0])),
                "p80": float(np.mean([x for i, x in enumerate(bb_width_all) if i % 2 == 1])),
            }
        else:
            bb_result = {"p20": 0.002, "p80": 0.008}

        # RB speed: average across pairs
        if rb_speed_all_per_pair:
            rb_result = {
                "p25": float(np.mean([d["p25"] for d in rb_speed_all_per_pair])),
                "p75": float(np.mean([d["p75"] for d in rb_speed_all_per_pair])),
            }
        else:
            rb_result = {"p25": 1.0, "p75": 3.0}

    # Log comparison vs v2.1 hardcoded values
    log.info("ADX: P25=%.2f (was 18.0), P75=%.2f (was 25.0)", adx_result["p25"], adx_result["p75"])
    log.info("ATR ratio: P25=%.3f (was 0.85), P75=%.3f (was 1.25)", atr_result["p25"], atr_result["p75"])
    log.info("RB speed: P25=%.2f bars/hr, P75=%.2f bars/hr (20-pip calibrated)", rb_result["p25"], rb_result["p75"])
    log.info("BB width: P20=%.5f, P80=%.5f", bb_result["p20"], bb_result["p80"])

    config = {
        "adx": adx_result,
        "atr_ratio": atr_result,
        "rb_speed": rb_result,
        "bb_width": bb_result,
        "adx_slope_threshold": 0.2,    # ADX slope > +0.2/bar → acceleration (Layer 2)
        "csm_widen_pct": 10.0,          # Currency differential widening % for +5 (Layer 2)
        "csm_narrow_pct": 30.0,         # Currency rotation narrowing % for -5 (Layer 2)
        "calibration_date": str(pd.Timestamp.utcnow().date()),
        "dataset_range": f"up to {holdout_cutoff.date()} (excluding {holdout_months}-month holdout)",
        "pairs": pairs,
        "version": "2.2",
    }

    # Write to file
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(config, f, indent=2)
    log.info("DCRD calibration complete — written to %s", out)

    return config


def load_config(path: Optional[str] = None) -> dict:
    """
    Load dcrd_config.json. Returns hardcoded v2.1 defaults if file not found.

    VC.4: dcrd_config.json loaded by DCRD Engine at startup.
    """
    from src.config import DCRD_CONFIG_PATH

    config_path = Path(path or PROJECT_ROOT / DCRD_CONFIG_PATH)

    if not config_path.exists():
        log.warning(
            "dcrd_config.json not found at %s — using v2.1 hardcoded defaults. "
            "Run: python -m src.dcrd.calibrate to generate it.",
            config_path,
        )
        return _default_config()

    try:
        with open(config_path) as f:
            config = json.load(f)
        log.info("Loaded DCRD config from %s (version %s)", config_path, config.get("version", "?"))
        return config
    except Exception as exc:
        log.error("Failed to load dcrd_config.json: %s — using defaults", exc)
        return _default_config()


def _default_config() -> dict:
    """v2.1 hardcoded defaults — used when dcrd_config.json is unavailable."""
    return {
        "adx": {"p25": 18.0, "p75": 25.0},
        "atr_ratio": {"p25": 0.85, "p75": 1.25},
        "rb_speed": {"p25": 1.0, "p75": 3.0},
        "bb_width": {"p20": 0.002, "p80": 0.008},
        "adx_slope_threshold": 0.2,
        "csm_widen_pct": 10.0,
        "csm_narrow_pct": 30.0,
        "version": "default",
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    from src.config import PAIRS

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="JcampFX DCRD Calibration (PRD §4)")
    parser.add_argument("--pairs", nargs="+", default=list(PAIRS), help="Pairs to calibrate on")
    parser.add_argument("--data-dir", default="data", help="Root data directory")
    parser.add_argument("--output", default=None, help="Override output path for dcrd_config.json")
    parser.add_argument("--holdout-months", type=int, default=3, help="Months to exclude (holdout)")
    args = parser.parse_args()

    result = calibrate(
        pairs=args.pairs,
        data_dir=args.data_dir,
        output_path=args.output,
        holdout_months=args.holdout_months,
    )
    print(json.dumps(result, indent=2))
