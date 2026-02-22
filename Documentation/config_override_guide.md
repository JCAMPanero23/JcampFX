# Config Override System — Quick Start Guide

## Overview

The config override system lets you test different settings without modifying `src/config.py`. Perfect for backtesting experiments!

## Quick Start

### 1. Apply the Threshold Adjustment Test (CS 85/40/40)

```bash
# Apply preset for threshold testing
python config_manager.py preset threshold-85-40-40

# Verify overrides are active
python config_manager.py show
```

**Output:**
```
Active overrides (3):
  STRATEGY_BREAKOUTRIDER_MIN_CS  = 40
  STRATEGY_RANGERIDER_MAX_CS     = 40
  STRATEGY_TRENDRIDER_MIN_CS     = 85
```

### 2. Run Backtest with Overrides

**IMPORTANT:** The backtest runner must use `config_override` to load settings.

```bash
# Run backtest (will automatically use overrides if config_overrides.json exists)
python -m backtester.run_backtest --start 2025-01-01 --end 2025-12-31
```

The backtest will use:
- TRENDING: CS ≥85 (was 70)
- TRANSITIONAL: CS 40-85 (was 30-70)
- RANGING: CS <40 (was <30)

### 3. Compare Results

Compare backtest results with and without overrides:

**Baseline (CS 70/30/30):**
```bash
python config_manager.py reset  # Use defaults
python -m backtester.run_backtest --start 2025-01-01 --end 2025-12-31
# Note the run_id (e.g., run_20260222_120000)
```

**Test (CS 85/40/40):**
```bash
python config_manager.py preset threshold-85-40-40
python -m backtester.run_backtest --start 2025-01-01 --end 2025-12-31
# Note the run_id (e.g., run_20260222_123000)
```

**Compare in Dashboard:**
- Load both runs in the Cinema tab
- Compare: Trade count by strategy, Win rate, PnL

### 4. Reset to Defaults

```bash
# Delete all overrides
python config_manager.py reset
```

## Available Presets

### 1. `threshold-85-40-40` (Recommended First Test)
Shift more time to Transitional regime for BreakoutRider.
```bash
python config_manager.py preset threshold-85-40-40
```

**Changes:**
- STRATEGY_TRENDRIDER_MIN_CS = 85 (was 70)
- STRATEGY_BREAKOUTRIDER_MIN_CS = 40 (was 30)
- STRATEGY_RANGERIDER_MAX_CS = 40 (was 30)

**Expected Impact:**
- BreakoutRider gets 2.6x more regime time (22.3% → 58.5%)
- TrendRider becomes more selective (77.7% → 41.4%)

### 2. `threshold-default`
Revert to original PRD thresholds (CS 70/30/30).
```bash
python config_manager.py preset threshold-default
```

### 3. `high-risk`
Test with 2% base risk per trade.
```bash
python config_manager.py preset high-risk
```

### 4. `low-risk`
Test with 0.5% base risk per trade.
```bash
python config_manager.py preset low-risk
```

## Manual Override Commands

### Set Individual Override
```bash
python config_manager.py set STRATEGY_TRENDRIDER_MIN_CS 85
python config_manager.py set BASE_RISK_PCT 0.015
```

### View Current Overrides
```bash
python config_manager.py show
```

### List All Presets
```bash
python config_manager.py list-presets
```

### Reset All Overrides
```bash
python config_manager.py reset
```

## Advanced: Save Overrides as Defaults

**DANGER:** This modifies `src/config.py`!

```bash
# Save current overrides as new defaults
python config_manager.py save-as-defaults

# Restore from backup (if needed)
python config_manager.py restore-backup
```

**When to Use:**
- After extensive testing confirms new settings are superior
- You want to commit the new thresholds to the codebase
- Creates backup at `config_defaults_backup.json` first

## Files

- **config_overrides.json** — Active overrides (git-ignored)
- **config_defaults_backup.json** — Backup created by save-as-defaults (git-ignored)
- **src/config.py** — Default settings (committed to git)
- **src/config_override.py** — Override system implementation
- **config_manager.py** — CLI tool

## Integration with Backtester

**TODO:** Update `backtester/run_backtest.py` to use `config_override.get_config()` instead of importing `src.config` directly.

**Example:**
```python
# OLD (hardcoded defaults)
from src.config import STRATEGY_TRENDRIDER_MIN_CS

# NEW (supports overrides)
from src.config_override import get_config
cfg = get_config()
trendrider_min_cs = cfg.STRATEGY_TRENDRIDER_MIN_CS
```

## Workflow Summary

**Step 1: Test Threshold Adjustment**
```bash
python config_manager.py preset threshold-85-40-40
python -m backtester.run_backtest --start 2025-01-01 --end 2025-12-31
```

**Step 2: Analyze Results**
- Load run in dashboard
- Check strategy distribution
- Compare PnL vs baseline

**Step 3: Decision**
- If better → `python config_manager.py save-as-defaults`
- If worse → `python config_manager.py reset`
- If unclear → test on different date range

## Next Session Plan

See `Documentation/next_session_plan.md` for detailed task breakdown.

**Priority:**
1. Test threshold adjustment (CS 85/40/40) on 2024 and 2025 data
2. If successful, save as defaults
3. If unsuccessful, proceed with Price Level Cooldown (Task 1)
