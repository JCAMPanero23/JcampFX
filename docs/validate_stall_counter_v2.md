# Stall Counter v2.0 Visual Validation Guide

**Before running backtest**, validate the UI changes in Trade Inspector.

---

## Quick Validation Steps

### 1. Launch Dashboard
```bash
python -m dashboard.app
```

### 2. Open Cinema Tab
Navigate to: `http://localhost:8050/cinema`

### 3. Load Previous Run
Select run: `run_20260223_224716` (Phase 3.2.2 baseline with stall counter data)

### 4. Pick a Sample Trade
Click on any trade row to open Trade Inspector

### 5. Visual Checks

#### ✅ Counter Display Format
- **"D"** appears when price is near entry (within ±5 pips)
- **"0" to "8"** shows in OPEN phase (before partial exit)
- **"E0" to "E8"** shows in RUNNER phase (after partial exit)
- **NO parentheses** around counter values
- **NO wrong values** like 80, 60, 40 (should be 8, 6, 4)

#### ✅ M15 Shadow Overlay
- Transparent M15 candlesticks visible in background
- Green/red but very faint (75% transparent)
- Should not obscure Range Bars

#### ✅ Grid Lines
- Grid lines appear **behind** candlesticks
- Subtle reference lines every 10 pips
- Should not obscure price action

#### ✅ Color Coding
- **Green (0-2)**: Safe zone, low risk
- **Orange (3-5)**: Warning zone, medium risk
- **Red (6-8)**: Danger zone, high risk
- **Gray (D)**: Disabled/paused

---

## Example Trades to Check

### Trade with Entry Zone Pause
Look for: Trade that consolidates near entry
- First few bars after entry should show **"D"** (disabled)
- Once price moves >5 pips from entry, counter activates (0, 1, 2...)

### Trade with Partial Exit
Look for: Trade that reached 1.5R
- Before 1.5R partial: counter shows **0-8** (OPEN phase)
- After 1.5R partial: counter shows **E0-E8** (RUNNER phase)

### Trade with Stall Counter Exit
Look for: `close_reason = "STALL_COUNTER_EXIT"`
- Counter should show progression to **8** (or **E8** in RUNNER)
- Exit should occur at counter = 8

---

## Red Flags (Issues to Report)

❌ **Counter shows 80, 60, 40, 20** instead of 8, 6, 4, 2
❌ **Counter shows (0) or (8)** with parentheses
❌ **Grid lines obscure candlesticks** (in foreground)
❌ **No M15 shadow visible** (should see faint candlesticks)
❌ **Counter active at entry** when price within ±5 pips (should be "D")
❌ **No "E" prefix in RUNNER phase** (should be E0-E8)

---

## If Issues Found

1. Take screenshot
2. Save to `Debug/` folder with descriptive name
3. Note trade ID and run ID
4. Report specific issue (see Red Flags above)

---

## If All Checks Pass

✅ Ready to run full 2-year backtest
✅ Proceed with confidence to Phase 3.3 v2.0 test
✅ Compare results to baseline (+$34.94)
