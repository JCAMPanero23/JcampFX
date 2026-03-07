# JcampFX — Regime-Adaptive Multi-Strategy Portfolio Engine

> *"You are no longer running a trend EA. You are running a Regime-Adaptive Multi-Strategy Portfolio Engine."*

[![Status](https://img.shields.io/badge/Status-Phase%201%20Development-blue)]()
[![Platform](https://img.shields.io/badge/Platform-MetaTrader%205-blueviolet)]()
[![Broker](https://img.shields.io/badge/Broker-FP%20Markets%20ECN-green)]()
[![PRD](https://img.shields.io/badge/PRD-v2.1%20Analyst--Reviewed-orange)]()

---

## Overview

JcampFX replaces time-based candlestick analysis with **Range Bars** for noise-free price action, and replaces binary trend/range toggles with the **Dynamic Composite Regime Detection (DCRD)** — a multi-layer scoring engine producing a continuous 0–100 confidence score.

The system routes signals to three independent strategy modules based on the current regime score, applies regime-aware partial exits at 1.5R, and trails the remaining runner with a dynamic Chandelier stop.

**Start capital:** $500 USD | **Broker:** FP Markets ECN MT5 | **Pairs:** EURUSD, GBPUSD, USDJPY, AUDJPY, USDCHF

---

## Architecture

```
MT5 (Tick + 4H/1H + Calendar)
        │
        ├── Range Engine (Python)       → Range Bar conversion
        └── DCRD Engine (Python)        → CompositeScore 0–100
                        │
                News Layer (MQL5 → ZMQ) → Event gating
                        │
                Brain Core (Python)     → Routes signals by CompositeScore
                        │
           Correlation Filter           → Max 2 trades per base/quote currency
                        │
               Exit Manager             → Partial exit at 1.5R + Dynamic Chandelier SL
                        │
             ZMQ Bridge (:5555)         → Hand EA (MQL5)
```

---

## DCRD — Dynamic Composite Regime Detection

The DCRD produces a single **CompositeScore (0–100)** clamped from three independent layers:

```
CompositeScore = StructuralScore (0–100) + ModifierScore (−15 to +15) + RangeBarScore (0–20)
```

| Layer | Weight | Components |
|---|---|---|
| **4H Structural** | 0–100 | ADX Strength, Market Structure, ATR Expansion, CSM Alignment, Trend Persistence |
| **1H Dynamic Modifier** | −15 to +15 | BB Width, ADX Acceleration, CSM Acceleration |
| **Range Bar Intelligence** | 0–20 | RB Speed Score, RB Structure Quality |

### Regime Mapping

| CompositeScore | Regime | Strategy | Risk Multiplier |
|---|---|---|---|
| **70–100** | Trending | TrendRider | 0.8x–1.0x |
| **30–70** | Transitional | BreakoutRider | 0.6x |
| **0–30** | Range | RangeRider | 0.7x |

**Anti-flipping filter:** Regime change requires ≥15pt threshold cross AND 2 consecutive 4H closes in the new regime.

---

## Strategies

### TrendRider `(CompositeScore 70–100)`
- **Entry:** 2nd Range Bar pullback in trend direction
- **Confirmation:** ADX > 25 + 3-bar staircase
- **Exit:** Regime-aware partial at 1.5R + Dynamic Chandelier on runner

### BreakoutRider `(CompositeScore 30–70)`
- **Entry:** RB close outside Keltner during BB compression breakout
- **Confirmation:** RB speed increasing + micro-structure break
- **Exit:** Regime-aware partial at 1.5R + Dynamic Chandelier on runner

### RangeRider `(CompositeScore 0–30)`
- **Entry:** Fade at consolidation boundaries
- **Confirmation:** ≥8 RBs in block + width > 2x RB size
- **Exit:** Regime-aware partial at 1.5R + Dynamic Chandelier on runner

---

## Exit System

All strategies share the same two-stage exit logic. R:R is **not fixed** — outcomes are path-dependent based on regime conviction at entry.

**Stage 1 — Partial Exit at 1.5R** (% set by CompositeScore at entry time):

| CompositeScore | Close % | Runner % | Locked Profit |
|---|---|---|---|
| > 85 (Deep Trending) | 60% | 40% | +0.90R |
| 70–85 (Trending) | 70% | 30% | +1.05R |
| 30–70 (Transitional) | 75% | 25% | +1.125R |
| < 30 (Range) | 80% | 20% | +1.20R |

**Stage 2 — Dynamic Chandelier SL on Runner:**
- Distance = `max(0.5R, ATR(14) of Range Bar timeframe)`
- Floor: 15 pips on majors | 25 pips on JPY pairs
- Trails by tick in profitable direction only, never widens

---

## Risk Management

| Control | Rule |
|---|---|
| **Position Sizing** | Dynamic 1–3% (skip trade if < 0.8%) |
| **Confidence Multiplier** | 0.7x–1.2x based on CompositeScore proximity to regime boundaries |
| **Performance Multiplier** | 0.6x–1.3x based on last-10-trade rolling R per strategy |
| **Max Concurrent** | 2 positions (3 if equity > $1,000) |
| **Correlation Limit** | Max 2 trades sharing same base or quote currency |
| **Daily Loss Cap** | 2R → CLOSE_ALL + PAUSE until midnight |
| **Strategy Cooldown** | 5 consecutive losses in last 10 trades → 24hr pause (per strategy) |
| **Gold Gate** | XAUUSD blocked until equity ≥ $2,000 |
| **Weekend Protection** | 100% close 20 min before Friday market close |
| **News Gating** | High-impact: −30/+15 min block | Medium: −15/+10 min |
| **Post-News Cooling** | 15 min: only CompositeScore > 80 signals pass |
| **Slippage Model** | 1.0 pip on all entries/exits (backtester) |
| **Commission** | $7/lot round-trip (FP Markets ECN) |

---

## Repository Structure

```
JcampFX/
├── JcampFX_PRD_v2.1.docx.md       # Product Requirements Document (source of truth)
├── CLAUDE.md                        # Claude Code project context
├── .gitignore
├── MT5_EAs/
│   ├── Experts/                     # Hand EA + strategy EAs (.mq5)
│   └── Include/
│       └── JcampStrategies/         # Shared MQL5 include files (.mqh)
├── src/                             # Python Brain (DCRD, strategies, exit manager)
├── backtester/                      # Phase 3 backtesting engine (The Cinema)
├── data/                            # Tick data + Range Bar cache (Parquet — gitignored)
└── dashboard/                       # Plotly/Dash web chart
```

**MT5 Symlinks** (auto-sync MQL5 ↔ project on save):

| MT5 Folder | Project Folder |
|---|---|
| `MQL5\Experts\JcampFX\` | `MT5_EAs\Experts\` |
| `MQL5\Include\JcampFXStrategies\` | `MT5_EAs\Include\JcampStrategies\` |

---

## Development Phases

| Phase | Deliverable | Gate |
|---|---|---|
| **1** | Range Bar Engine + Plotly web chart + M15 overlay | Visual validation |
| **2** | DCRD Brain + 3 strategies + Exit System + News layer | Unit tests + regime accuracy ≥85% |
| **3** | Web Backtester — 2yr data, 4 walk-forward cycles (The Cinema) | Net profitable after slippage + commission |
| **4** | ZMQ Bridge + Demo trading + all risk controls live | 1-week demo match ≥95% |
| **5** | VPS deployment + Android dashboard + Telegram bot | Live execution |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Data | MetaTrader5 Python package, Dukascopy tick data, Parquet |
| Range Engine | Python 3.11+ |
| DCRD / Brain | Python (modular plugin architecture) |
| News | MQL5 `CalendarValueHistory()` → ZMQ port 5557 |
| Backtester | `backtesting.py` with custom Range Bar + DCRD timeline |
| Dashboard | Plotly / Dash |
| Signal Bridge | pyzmq (ports 5555/5556) |
| Hand EA | MQL5 on MT5 |
| Broker | FP Markets ECN — $7/lot commission |

---

## Pair Universe

| Pair | Range Bar Size | Status |
|---|---|---|
| EURUSD | 10–15 pips | Active |
| GBPUSD | 10–15 pips | Active |
| USDJPY | 15–20 pips | Active |
| AUDJPY | 15–20 pips | Active |
| USDCHF | 10–15 pips | Active |
| XAUUSD | — | Unlocks at equity ≥ $2,000 |

CSM grid monitors all 9 major pairs for currency strength alignment.

---

## PRD

Full system specification: [`JcampFX_PRD_v2.1.docx.md`](./JcampFX_PRD_v2.1.docx.md)

Includes: DCRD scoring formulas, validation checklists (89 checks / 6 GATE / 33 CRITICAL), exit math by regime, risk framework, and phase-by-phase build gates.
