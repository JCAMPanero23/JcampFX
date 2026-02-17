# JcampFX — Claude Code Context

## Project Overview
Regime-Adaptive Multi-Strategy Portfolio Engine built on Dynamic Composite Regime Detection (DCRD) with Range Bar Intelligence. Targets a $500 FP Markets ECN MT5 account.

**Reference:** `JcampFX_PRD_v2.1.docx.md` is the single source of truth for all system requirements.

## Repository Structure
```
D:\JcampFX\
├── JcampFX_PRD_v2.1.docx.md   # Product Requirements Document
├── MT5_EAs\
│   ├── Experts\                 # MQL5 Expert Advisors (symlinked from MT5)
│   └── Include\
│       └── JcampStrategies\     # MQL5 include files (symlinked from MT5)
├── src\                         # Python Brain (DCRD, strategies, exit manager)
├── backtester\                  # Phase 3 backtesting engine
├── data\                        # Tick data + Range Bar cache (Parquet)
└── dashboard\                   # Plotly/Dash web chart + Cinema
```

## Symlinks (do not delete)
| MT5 Path | Project Path |
|---|---|
| `MQL5\Experts\JcampFX\` | `D:\JcampFX\MT5_EAs\Experts\` |
| `MQL5\Include\JcampFXStrategies\` | `D:\JcampFX\MT5_EAs\Include\JcampStrategies\` |

MT5 Terminal: `C:\Users\jcamp\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\`

## Architecture Summary
- **DCRD Engine:** 4H Structural (0–100) + 1H Dynamic Modifier (−15 to +15) + Range Bar Intelligence (0–20) → CompositeScore (0–100)
- **Strategies:** TrendRider (CS 70–100) | BreakoutRider (CS 30–70) | RangeRider (CS 0–30)
- **Exit System:** Partial exit at 1.5R (60/70/75/80% based on CS at entry) + Dynamic Chandelier SL on runner
- **Risk:** Dynamic 1–3% per trade; skip if <0.8%. Max 2 concurrent positions until equity >$1,000
- **News:** MQL5 native CalendarValueHistory() → ZMQ port 5557 → Brain gating
- **Bridge:** ZMQ tcp://localhost:5555 (signals) / 5556 (reports) / 5557 (news)

## Key Rules (never violate)
- R:R is NOT fixed — exit outcomes are path-dependent via partial exit % + Chandelier runner
- Partial exit % is set by CompositeScore AT ENTRY (not at 1.5R hit time)
- Max 2 trades sharing same base or quote currency (correlation filter)
- 100% position close 20 min before Friday market close (no exceptions at this equity level)
- Daily 2R loss cap → CLOSE_ALL + PAUSE until midnight

## Development Phases
| Phase | Focus | Gate |
|---|---|---|
| 1 | Range Bar Engine + Web Chart | Visual validation |
| 2 | DCRD + Strategies + Exit System + News | Unit tests + regime accuracy |
| 3 | Web Backtester (2yr data, 4 walk-forward cycles) | Profitable after costs |
| 4 | ZMQ Bridge + Demo Trading | 1-week demo match |
| 5 | VPS + Android + Signal Service | Live execution |

## Tech Stack
- Python 3.11+, MetaTrader5 package, backtesting.py, Plotly/Dash, pyzmq
- MQL5 (Hand EA), Parquet (tick storage), FP Markets ECN MT5
- Broker commission: $7/lot round-trip | Slippage model: 1.0 pip all entries/exits
