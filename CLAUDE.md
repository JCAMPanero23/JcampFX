# JcampFX — Claude Code Context

## Project Overview
Regime-Adaptive Multi-Strategy Portfolio Engine built on Dynamic Composite Regime Detection (DCRD) with Range Bar Intelligence. Targets a $500 FP Markets ECN MT5 account.

**Reference:** `JcampFX_PRD_v2.2.md` is the single source of truth for all system requirements.

## Repository Structure
```
D:\JcampFX\
├── JcampFX_PRD_v2.2.md          # Product Requirements Document (current)
├── JcampFX_PRD_v2.1.docx.md     # Previous version (archived)
├── MT5_EAs\
│   ├── Experts\                   # MQL5 Expert Advisors (symlinked from MT5)
│   └── Include\
│       └── JcampStrategies\       # MQL5 include files (symlinked from MT5)
├── src\                           # Python Brain (DCRD, strategies, exit manager)
├── backtester\                    # Phase 3 backtesting engine
├── data\                          # Tick data + Range Bar cache (Parquet)
└── dashboard\                     # Plotly/Dash web chart + Cinema
```

## Symlinks (do not delete)
| MT5 Path | Project Path |
|---|---|
| `MQL5\Experts\JcampFX\` | `D:\JcampFX\MT5_EAs\Experts\` |
| `MQL5\Include\JcampFXStrategies\` | `D:\JcampFX\MT5_EAs\Include\JcampStrategies\` |

MT5 Terminal: `C:\Users\jcamp\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\`

## Architecture Summary
- **DCRD Engine:** 4H Structural (0–100) + 1H Dynamic Modifier (−15 to +15) + Range Bar Intelligence (0–20) → CompositeScore (0–100)
- **Range Bars:** 20 pips (majors), 25–30 pips (JPY pairs) — upgraded from 10-pip in v2.2
- **Strategies:** TrendRider (CS 70–100) | BreakoutRider (CS 30–70) | RangeRider (CS 0–30)
- **Exit System:** Partial exit at 1.5R (60/70/75/80% based on CS at entry) + Dynamic Chandelier SL on runner
- **Regime Deterioration:** Force-close runner if CS drops >40 pts from entry-time score
- **Risk:** Dynamic 1–3% per trade; skip if <0.8%. Max 2 concurrent positions until equity >$1,000
- **News:** MQL5 native CalendarValueHistory() → ZMQ port 5557 → Brain gating
- **Session Filter:** Per-strategy hard/soft filters (Tokyo/London/NY/Overlap/Off-Hours)
- **Phantom Detection:** `is_phantom` + `is_gap_adjacent` flags on all Range Bars; no entries on phantom bars
- **Bridge:** ZMQ tcp://localhost:5555 (signals) / 5556 (reports) / 5557 (news)

## Key Rules (never violate)
- R:R is NOT fixed — exit outcomes are path-dependent via partial exit % + Chandelier runner
- Partial exit % is set by CompositeScore AT ENTRY (not at 1.5R hit time)
- Max 2 trades sharing same base or quote currency (correlation filter)
- 100% position close 20 min before Friday market close (no exceptions at this equity level)
- Daily 2R loss cap → CLOSE_ALL + PAUSE until midnight
- No entries on `is_phantom` bars (PHANTOM_BLOCKED); gap-adjacent is configurable per strategy
- Exits on phantom bars fill at actual tick boundary price, not Range Bar close
- DCRD thresholds are data-driven (percentile-based), stored in `dcrd_config.json`

## Phase 3 Backtest Results (Feb 19, 2026 — First Clean Run)

**Run ID:** `run_20260219_150916` | **Data:** 10-pip Range Bars + DCRD fallback CS=50

| Metric | Value | Gate |
|---|---|---|
| Net P&L | **+$44.96** | V3.1 PASS |
| Sharpe Ratio | 0.60 | V3.20 FAIL (target >1.0) |
| Max Drawdown | 17.1% | V3.2 PASS (<20%) |
| Win Rate | 39.9% | — |
| Profit Factor | 1.07 | V3.21 FAIL (target >1.5) |
| Trades | 188 | — |

**Notes:**
- Results used DCRD fallback score (50.0) — no 4H/1H OHLC calibration applied yet
- All trades in BreakoutRider regime (CS=50 → transitional zone)
- Bugs fixed before this run: cross-pair price poisoning on 2R_CAP/WEEKEND_CLOSE closes + lot size cap (MAX_LOT=5.0)
- V2.2 upgrade (20-pip bars + phantom detection + session filter + regime deterioration) expected to meaningfully improve Sharpe and Profit Factor

## PRD v2.1 → v2.2 Upgrade Scope (Next Session)

The following are **new requirements** from PRD v2.2 not yet implemented:

| ID | Feature | Priority |
|---|---|---|
| R12 | **20-pip Range Bar migration** (from 10-pip) — re-download tick data, rebuild RB cache | CRITICAL |
| R13 | **Phantom Liquidity Detection** — `is_gap_adjacent` flag (VP.2); `is_phantom` exists (VP.1 ✅) | CRITICAL |
| R14 | **Phantom exit fills** at actual tick boundary price (VP.6) | CRITICAL |
| R15 | **DCRD Calibration** — percentile-based ADX/ATR/RB-speed thresholds → `dcrd_config.json` (VC.1–VC.5) | GATE |
| R16 | **Regime Deterioration** — force-close runner if CS drops >40 pts from entry (VD.9, VE.8) | CRITICAL |
| R17 | **BreakoutRider full spec** — Keltner(20, 1.5×ATR) + BB compression <P20 + RB speed ≥2 bars/30min (V2.3) | CRITICAL |
| R18 | **Session Filtering** — Tokyo/London/NY/Overlap per-strategy hard/soft filters (VS.1–VS.6) | MUST PASS |

**Recommended implementation order:**
1. R12 — 20-pip migration (foundational: everything else calibrates off this)
2. R13+R14 — Phantom gap-adjacent + phantom exit fills
3. R15 — DCRD calibration pipeline + `dcrd_config.json`
4. R16 — Regime deterioration in ExitManager + BacktestEngine
5. R17 — BreakoutRider entry spec upgrade
6. R18 — Session filter module + Brain Core integration
7. Re-run Phase 3 backtest → target V3.1 PASS with calibrated DCRD

## Development Phases
| Phase | Focus | Status | Gate |
|---|---|---|---|
| 1 | Range Bar Engine + Web Chart | COMPLETE | Visual validation ✅ |
| 2 | DCRD + Strategies + Exit System + News | COMPLETE (v2.1) | Unit tests ✅ |
| 3 | Web Backtester (2yr data, 4 walk-forward cycles) | IN PROGRESS | Profitable after costs |
| 4 | ZMQ Bridge + Demo Trading | PENDING | 1-week demo match |
| 5 | VPS + Android + Signal Service | PENDING | Live execution |

## Tech Stack
- Python 3.11+, MetaTrader5 package, backtesting.py, Plotly/Dash, pyzmq
- MQL5 (Hand EA), Parquet (tick storage), FP Markets ECN MT5
- Broker commission: $7/lot round-trip | Slippage model: 1.0 pip organic / tick boundary on phantom bars
