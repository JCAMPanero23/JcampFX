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

## Phase 3 Backtest Results — Evolution Log

### Run 1 (Feb 19, 2026) — Pre-v2.2, DCRD fallback, 10-pip bars
**Run ID:** `run_20260219_150916`
| Net P&L | Sharpe | Max DD | Win Rate | PF | Trades |
|---|---|---|---|---|---|
| **+$44.96** ✅ | 0.60 | 17.1% | 39.9% | 1.07 | 188 |
- DCRD fallback CS=50 → all BreakoutRider regime (no real DCRD)
- 10-pip Range Bars. Phase 3 gate V3.1 technically PASS but not meaningful.

---

### Run 2 (Feb 19, 2026) — v2.2 complete, 20-pip bars, calibrated DCRD, resumption entry
**Run ID:** `run_20260219_190902`
| Net P&L | Sharpe | Max DD | Win Rate | PF | Trades |
|---|---|---|---|---|---|
| **-$218.71** ❌ | -2.26 | 48.8% | 36.0% | 0.76 | 292 |

**v2.2 code changes applied before this run:**
- R12: 20-pip Range Bars (EURUSD/GBPUSD/USDCHF), 25-pip (USDJPY/AUDJPY)
- R13+R14: `is_gap_adjacent` flag + phantom exit fills at tick boundary price
- R15: DCRD percentile-based calibration → `dcrd_config.json`
- R16: Regime deterioration (force-close runner if CS drops >40 pts from entry CS)
- R17: BreakoutRider full spec — Keltner(20,1.5×ATR) + BB compression P20 + RB speed ≥2/30min
- R18: Session filter module (Tokyo/London/NY hard/soft per strategy)
- **TrendRider: resumption bar entry** — enter on first trend-direction bar AFTER pullback (not AT pullback close). SL = pullback bar's structural extreme. Eliminates r_dist=0 bug.
- **BreakoutRider: BB compression on Range Bar closes** (not 1H OHLC — temporal mismatch fix)
- **Backtester: performance tracker integration** — closed trades feed R-multiples to BrainCore

**Trade breakdown by pair:**
| Pair | Trades | WR | Total R | PnL |
|---|---|---|---|---|
| USDJPY | 136 | 38% | -17.67R | -$124 |
| AUDJPY | 48 | 33% | -7.93R | -$39 |
| USDCHF | 27 | 30% | -6.91R | -$36 |
| EURUSD | 29 | 38% | -1.74R | -$12 |
| GBPUSD | 50 | 38% | -3.32R | +$2 |

**Root cause analysis:**
- **65.2% of trades (189/290) hit SL before partial exit fires** — avg -0.982R
- **34.8% of trades reach 1.5R partial exit** — avg +1.466R total
- Breakeven requires ~40% partial-reach rate (E[R] = 0.40×1.47 + 0.60×(-0.98) = 0)
- Gap from breakeven: 5.2 percentage points on partial-reach rate
- Monthly WR variance is extreme: May-24=86%, Aug-24=59% vs Oct-24=17%, Jul-25=0%
- **USDJPY overweight**: 47% of all trades but same WR as EURUSD/GBPUSD — concentration risk
- **DCRD locks to CS≥70 (TrendRider) ~89% of time** → BreakoutRider only 2 trades in 2 years

**Close reason breakdown (TrendRider):**
| Reason | Count | Notes |
|---|---|---|
| SL_HIT | 176 | 61% — full loss before partial exit |
| CHANDELIER_HIT | 100 | 34% — triggered after partial or as runner stop |
| 2R_CAP | 9 | daily loss cap fired |
| WEEKEND_CLOSE | 5 | Friday close rule |

---

### Run 3 (Feb 19, 2026) — ADX slope filter added (5-bar staircase)
| Net P&L | Win Rate | Total R | Trades |
|---|---|---|---|
| **-$199** ❌ | 35.0% | -34.12R | 180 |
- ADX slope filter reduced trade count 38% (292→180) but WR dropped slightly (36%→35%)
- Per-trade loss WORSE: -0.19R vs -0.136R → slope filter selected LOWER quality signals
- **Conclusion**: ADX slope (rising ADX) does not predict partial-reach rate improvement

---

## TrendRider Debugging Experiments Summary

| Config | Trades | WR | Total R | PnL | Notes |
|---|---|---|---|---|---|
| 1-bar pullback entry (SL bug) | 2 | — | — | — | r_dist=0 bug, SL==entry |
| Resumption bar, staircase=5 | 292 | 36% | -39.6R | -$219 | Baseline v2.2 |
| Resumption bar, staircase=3 | 430 | 34% | -81.2R | -$323 | 3-bar = too noisy |
| Resumption bar, staircase=5, ADX slope | 180 | 35% | -34.1R | -$199 | Fewer trades, same WR |

**What we know:**
- Resumption bar entry is correct (eliminates r_dist=0 bug, natural SL placement)
- 5-bar staircase is the right level (3-bar too noisy, no staircase untested)
- ADX slope filter is NOT predictive of entry quality
- The 34-36% partial-reach rate is a STRUCTURAL property of the current entry pattern
- EURUSD/GBPUSD near breakeven; USDJPY/AUDJPY/USDCHF are the main drag

**What we DON'T know yet (next session — backtest playback):**
- WHY Oct-24 (17% WR) and Jul-25 (0% WR) were catastrophically bad
- What the Range Bars looked like at entry during losing months vs winning months
- Whether staircase is detecting TRUE trending or just ranging bounce patterns
- Whether USDJPY's 136 trades are in genuinely trending conditions or false positives
- What the DCRD composite score looked like bar-by-bar during bad months

---

## Next Session Plan: Backtest Playback / Debug Visualizer

Build a **Cinema-style bar-by-bar playback** that lets us inspect what the backtest engine saw at each signal:

**Proposed `backtester/playback.py`** (or extend the Cinema tab in dashboard):
1. Load a backtest run's trades.parquet + range bar data for a given pair
2. For each trade, show:
   - The 20 Range Bars leading up to entry (with staircase highlighted)
   - Entry bar, pullback bar, resumption bar (color-coded)
   - DCRD composite score at entry time
   - ADX value at entry time
   - Whether trade was a win (reached 1.5R) or loss (SL hit)
3. Filter view: show only LOSING trades in specific bad months (Oct-24, Jul-25)
4. Let us visually inspect whether staircase pattern looks like a real trend or a false signal

**Key questions to answer visually:**
- Do losing trades have "weaker" staircase patterns than winning trades?
- Are losing trades entering near obvious support/resistance levels?
- Is the pullback bar unusually large (deeper pullback = trend might be reversing)?
- Are winning months characterized by a particular DCRD score range?

**Implementation priority:**
1. Add a `generate_signal_snapshots()` function to extract per-trade context (20-bar window, CS, ADX)
2. Export as JSON/CSV for the Cinema dashboard tab to render
3. Add a "Trade Inspector" view in the dashboard: click a trade → see its bar context

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
