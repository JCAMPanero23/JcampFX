# JcampFX — Claude Code Context

## Current Status 🎯

**Phase:** 4.1 Complete — cTrader ZMQ Bridge Operational ✅
**Last Completed:** Phase 4.1 — cTrader cBot working, tick flow validated 20+ mins
**Next Session:** Phase 4.2 — Add order execution (entry/exit/modify) to cBot
**Platform:** Dual support (MT5 + cTrader)

**Production Portfolio (Validated):**
- **Pairs:** EURUSD, USDJPY, AUDJPY, USDCHF (4 pairs)
- **Range Bars:** 15 pips (majors), 20 pips (JPY pairs)
- **Starting Equity:** $500
- **Base Risk:** 1.0% per trade
- **2-Year Backtest:** $182.74 profit (36.5% return), 17.4% DD, Sharpe 1.30

## Project Overview
Regime-Adaptive Multi-Strategy Portfolio Engine built on Dynamic Composite Regime Detection (DCRD) with Range Bar Intelligence. Targets a $500 FP Markets ECN account with dual platform support (MT5 + cTrader).

**References:**
- `JcampFX_PRD_v2.2.md` — Single source of truth for all system requirements
- `docs/` — Historical planning and analysis documents

## Repository Structure
```
D:\JcampFX\
├── JcampFX_PRD_v2.2.md          # Product Requirements Document (current)
├── JcampFX_PRD_v2.1.docx.md     # Previous version (archived)
├── docs\
│   ├── next_session_plan.md           # Active development plan (tasks, analysis, decisions)
│   ├── price_level_cooldown_results.md # Phase 3.1.1 Task 1 results
│   ├── config_override_guide.md        # Backtest config override system
│   └── plans\                          # Historical planning documents
├── MT5_EAs\
│   ├── Experts\                   # MQL5 Expert Advisors (symlinked from MT5)
│   └── Include\
│       └── JcampStrategies\       # MQL5 include files (symlinked from MT5)
├── cTrader_cBot\                  # cTrader cBot (C#) — Phase 4.1 ✅
│   ├── JcampFX_Brain_SIMPLE.cs    # Main cBot (working version)
│   ├── ZMQBridge.cs               # NetMQ socket wrapper
│   ├── MessageTypes.cs            # JSON DTOs
│   ├── install_netmq.bat          # Automated NuGet installer
│   └── README.md                  # Installation guide
├── src\                           # Python Brain (DCRD, strategies, exit manager)
├── backtester\                    # Phase 3 backtesting engine
├── data\                          # Tick data + Range Bar cache (Parquet — gitignored)
└── dashboard\                     # Plotly/Dash web chart + Cinema
```

## Git Repository Management

**Current Branch:** `main` (clean history as of 2026-03-07)

**Important Note:** The repository was reorganized during Phase 4.1 to resolve git push timeout issues (HTTP 408 errors). The old `main` branch had 8.1GB of git history due to large tick data files in past commits. We created an orphan branch `ctrader-clean` with no history, then replaced `main` with this clean branch.

**Branch Structure:**
- `main` — Clean history (current work, 265 files, no large data)
- `main-backup` — Old main branch (preserved locally, has full Phase 3 history)
- `feature/*` — Feature branches (unaffected by reorganization)

**What Was Preserved:**
- ✅ All source code files
- ✅ All documentation
- ✅ All Phase 3 backtest results (in baseline_4pair/)
- ✅ cTrader Phase 4.1 implementation

**What Was Removed from Git:**
- ❌ Large tick data files (data/**/*.parquet now gitignored)
- ❌ Old backtest result parquet files (18GB+ in git history)

**Data Backup:** Large data files backed up to Google Drive (not in git)

**Benefits:**
- Fast git operations (clone/push/pull)
- No more HTTP 408 timeout errors
- Clean history going forward
- Old history preserved in `main-backup` (local)

## Platform File Management

### MT5 File Management
EA files are copied directly from `D:\JcampFX\MT5_EAs\Experts\` to MT5 Terminal.

**MT5 Terminal Path:** `C:\Users\Jcamp_Laptop\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\`

**After making changes to EA files:**
```bash
# Copy updated EA to MT5
cp "D:/JcampFX/MT5_EAs/Experts/JcampFX_Brain.mq5" "C:/Users/Jcamp_Laptop/AppData/Roaming/MetaQuotes/Terminal/D0E8209F77C8CF37AD8BF550E51FF075/MQL5/Experts/JcampFX_Brain.mq5"
```

### cTrader cBot Management ✅
cBot files are in `D:\JcampFX\cTrader_cBot\` and imported via cTrader Automate.

**Installation:**
1. Open cTrader → Automate → New cBot
2. Paste combined C# code from `JcampFX_Brain_COMBINED.cs`
3. Add NetMQ reference via Manage References
4. Build and run on chart

**NuGet Packages:**
- NetMQ (pure .NET ZMQ implementation)
- AsyncIO (required for NetMQ)

## Architecture Summary

**Active Pairs (Validated):** EURUSD, USDJPY, AUDJPY, USDCHF

**Core Components:**
- **DCRD Engine:** 4H Structural (0–100) + 1H Dynamic Modifier (−15 to +15) + Range Bar Intelligence (0–20) → CompositeScore (0–100)
- **Range Bars:** 15 pips (EURUSD/USDCHF), 20 pips (USDJPY/AUDJPY)
- **Strategies:** TrendRider (CS 30–100) | RangeRider (CS 0–30) | BreakoutRider (DISABLED)

**Exit System:**
- **Partial Exit:** 1.5R target (60/70/75/80% closed based on CS at entry)
- **Trailing SL:** Primary profit mechanism (tracks Range Bar extremes with 5-pip buffer)
- **2-bar counter-close:** DISABLED (was cutting winners prematurely)
- **Runner Protection:** R >= -0.5 threshold protects near-breakeven/profitable trades from:
  - 2R daily loss cap (only closes trades with R < -0.5)
  - Weekend close (only closes trades with R < -0.5)
- **Regime Deterioration:** Force-close runner if CS drops >40 pts from entry-time score

**Risk Management:**
- **Base Risk:** 1.0% per trade (skip if <0.8%)
- **Max Concurrent:** 5 positions
- **Correlation Filter:** Max 2 trades per currency (base or quote)
- **Price Level Cooldown:** ±20 pips, 4-hour window (prevents revenge trading)

**Infrastructure:**
- **Platforms:** MT5 EA (MQL5) + cTrader cBot (C#) — Python Brain is platform-agnostic
- **News:** MQL5 CalendarValueHistory() → ZMQ port 5557 → Brain gating (MT5 only, cTrader deferred)
- **Session Filter:** Per-strategy hard/soft filters (Tokyo/London/NY/Overlap/Off-Hours)
- **Phantom Detection:** `is_phantom` + `is_gap_adjacent` flags; no entries on phantom bars
- **Bridge:** ZMQ tcp://localhost:5555 (signals) / 5556 (reports) / 5557 (news)
- **Symbol Handling:** Python uses canonical names (EURUSD), EA/cBot handles broker suffixes

## Key Rules (never violate)

**Exit Mechanics:**
- R:R is NOT fixed — exit outcomes are path-dependent via partial exit % + trailing SL runner
- Partial exit % is set by CompositeScore AT ENTRY (not at 1.5R hit time)
- **Runner Protection:** Trades at R >= -0.5 are protected from 2R cap and weekend close
- Daily 2R loss cap → close only trades with current R < -0.5
- Weekend close → close only trades with current R < -0.5
- **2-bar counter-close:** DISABLED (no longer active)

**Entry Gating:**
- Max 2 trades sharing same base or quote currency (correlation filter)
- No entries on `is_phantom` bars (PHANTOM_BLOCKED); gap-adjacent is configurable per strategy
- Price level cooldown: ±20 pips, 4-hour window (prevents revenge trading)

**Technical:**
- Exits on phantom bars fill at actual tick boundary price, not Range Bar close
- DCRD thresholds are data-driven (percentile-based), stored in `dcrd_config.json`
- Active pairs: EURUSD, USDJPY, AUDJPY, USDCHF only (GBPUSD removed after Phase 3.5)

## Phase 3 Backtest Results — Key Milestones

### Baseline (Feb 19, 2026) — v2.2 Complete System
**Run ID:** `run_20260219_190902`

| Net P&L | Sharpe | Max DD | Win Rate | Trades |
|---------|--------|--------|----------|--------|
| **-$218.71** | -2.26 | 48.8% | 36.0% | 292 |

**Key Findings:**
- 65% of trades hit SL before reaching 1.5R partial exit
- Need 40% partial-reach rate for breakeven (had only 34.8%)
- GBPUSD near breakeven, JPY pairs were main drag
- DCRD correctly locked to CS ≥70 (trending) ~89% of time

**Major Implementation (v2.2):**
- TrendRider resumption bar entry (fixes r_dist=0 bug)
- DCRD percentile-based calibration
- Phantom bar detection + tick boundary fills
- Session filters + regime deterioration protection

---

### Phase 3.1.1 (Feb 22, 2026) — Price Level Cooldown
**Run ID:** `run_20260222_083218`

| Net P&L | Sharpe | Max DD | Win Rate | Trades |
|---------|--------|--------|----------|--------|
| **-$130.58** | -1.71 | 37.0% | 38.2% | 165 |

**Implementation:** Per-strategy price level tracking (±20 pips, 4-hour window)

**Results:**
- 40% loss reduction vs baseline (+$88.13)
- 22 revenge trade attempts blocked
- Still not profitable — entry quality improvement needed

---

### Phase 3.5 (Feb 27, 2026) — Range Bar Optimization + Runner Protection
**Final Configuration:** 15-pip bars (majors), 20-pip bars (JPY pairs)

| Net P&L | Sharpe | Max DD | Win Rate | Total R | Trades |
|---------|--------|--------|----------|---------|--------|
| **$267.43** | **1.59** | **20.9%** | **45.0%** | **51.82R** | 298 |

**Key Changes:**
1. **2-bar counter-close:** DISABLED (was cutting 67 profitable runners prematurely)
2. **Runner Protection System:** R >= -0.5 threshold
   - 2R daily cap only closes trades with R < -0.5
   - Weekend close only closes trades with R < -0.5
   - Protected near-breakeven and profitable trades (+$101.50 profit, +61%)
3. **Trailing SL:** Primary exit mechanism (133 exits @ 1.62R avg = $1,682 profit)

**Per-Pair Performance:**
- USDJPY: 127 trades, +$158 (best)
- USDCHF: 23 trades, +$76 (strong)
- AUDJPY: 50 trades, +$50 (good)
- EURUSD: 42 trades, +$33 (good)
- **GBPUSD: 56 trades, -$50 (REMOVE)** ❌

**Gate Status:**
- ✅ Net profit positive: $267.43
- ⚠️ Max DD 20.9% (exceeds 20% gate by 0.9% — accepted due to Sharpe 1.59)
- ✅ Sharpe >1.0: 1.59

---

### Phase 3.6 (Feb 28, 2026) — Portfolio Optimization + Final Validation ✅

**Final Portfolio:** EURUSD, USDJPY, AUDJPY, USDCHF (4 pairs)

| Net P&L | Sharpe | Max DD | Win Rate | Total R | Trades |
|---------|--------|--------|----------|---------|--------|
| **$182.74** | **1.30** | **17.4%** | **45.1%** | **45.61R** | 255 |

**Changes Made:**
1. **GBPUSD removed:** -8.05R over 56 trades (negative contributor)
2. **AUDUSD tested & rejected:** 25% WR, -3.80R over 12 trades
3. **EURGBP deferred:** 53.3% WR, +$17.76 profit BUT breached 20% DD gate at 20.6%

**Walk-Forward Validation (Phase 3.3):**
- 4 cycles of 4-month train + 2-month test
- **ALL 4 OUT-OF-SAMPLE PERIODS PROFITABLE** ✅
- Cumulative Net PnL: $182.53
- Proves system robustness across different market regimes

**Monte Carlo Simulation (Phase 3.4):**
- 10,000 trade sequence permutations
- **100% profitable across all simulations**
- 100% Sharpe >1.0
- Actual DD 17.4% at 33.7th percentile (favorable)
- Median DD: 19.4% (close to gate limit)

**Per-Pair Performance:**
- USDJPY: 131 trades, 44.3% WR, +$58.86 (best)
- USDCHF: 31 trades, 51.6% WR, +$52.11 (strong)
- EURUSD: 42 trades, 45.2% WR, +$38.55 (good)
- AUDJPY: 51 trades, 43.1% WR, +$33.21 (good)

**Exit Performance:**
- TRAILING_SL_HIT: 114 exits (44.7%), +1.63R avg, +$1,307 profit
- SL_HIT: 136 exits (53.3%), -1.02R avg, -$1,104 loss

**Phase 3 Validation Gates - FINAL STATUS:**
- ✅ V3.1: Net profit positive: $182.74
- ✅ V3.2: Max DD <20%: 17.4%
- ✅ V3.3: Walk-forward 4/4 cycles profitable
- ✅ V3.7: No day >2R loss (enforced)
- ✅ V3.12: Each strategy profitable (TrendRider: $170.81, RangeRider: $11.93)
- ✅ V3.15: Sharpe >1.0: 1.30

**ALL MANDATORY GATES PASSED — SYSTEM VALIDATED FOR DEMO TRADING** 🎉

---

## Phase 3 Development — Key Insights (ARCHIVED)

**Journey from -$218 to +$182:**
1. **Baseline (v2.2):** -$218 profit, 48.8% DD — system complete but unprofitable
2. **Price Level Cooldown (3.1.1):** -$130 profit (+40% improvement) — revenge trades eliminated
3. **Range Bar Optimization (3.5):** +$267 profit, 20.9% DD — optimal bar sizes + runner protection
4. **Portfolio Optimization (3.6):** +$182 profit, 17.4% DD — removed GBPUSD, walk-forward validated

**Critical Breakthroughs:**

**1. Runner Protection System (R >= -0.5 threshold)**
- Protecting near-breakeven/profitable trades from forced exits added +$101.50 profit (+61%)
- Only close deep losers (R < -0.5) on 2R cap and weekend close
- Changed 2R daily cap from risk management tool to "deep loser prevention"

**2. Disabling 2-Bar Counter-Close**
- Was prematurely cutting 67 profitable runners at ~2 bars
- Allowed trailing SL to become primary exit mechanism
- Trailing SL: 133 exits @ 1.62R avg = $1,682 profit (63% of total)

**3. Range Bar Size Optimization**
- 15 pips (EURUSD/USDCHF), 20 pips (USDJPY/AUDJPY) = optimal for intraday/swing hybrid
- Too small (10-pip): noise and false signals
- Too large (25-pip): missed opportunities

**4. Price Level Cooldown**
- ±20 pips, 4-hour window prevents "revenge trading"
- Blocked 22 attempts to re-enter failed price levels
- Reduced losses by 40% in initial tests

**5. Portfolio Optimization**
- GBPUSD removed: -8.05R over 56 trades (only losing pair)
- AUDUSD tested: 25% WR, -3.80R (rejected)
- EURGBP deferred: profitable but breached 20% DD gate
- Final 4-pair portfolio: EURUSD, USDJPY, AUDJPY, USDCHF

**Risk Management Validation:**
- Tested 2%, 3%, 5% risk: diminishing returns + exponential DD growth
- **1% base risk is optimal** for $500 account (Sharpe 1.30-1.59)

**Technical Implementation:**
```python
# Runner Protection Logic (2R Cap & Weekend Close):
for trade in account.open_trades:
    current_r = calculate_r_multiple(trade, current_price)
    if current_r >= -0.5:
        continue  # Protect near-breakeven and winners
    account.close_trade(trade)  # Only close deep losers
```

**Files Modified:**
- `backtester/engine.py` — Runner protection logic
- `backtester/monte_carlo.py` — Monte Carlo simulation (NEW)
- `src/price_level_tracker.py` — Price level cooldown (NEW)
- `src/config.py` — Range Bar sizes, active pairs

## Development Phases

| Phase | Focus | Status | Gate | Result |
|-------|-------|--------|------|--------|
| 1 | Range Bar Engine + Web Chart | COMPLETE | Visual validation | ✅ Dashboard operational |
| 2 | DCRD + Strategies + Exit System | COMPLETE | Unit tests | ✅ v2.2 system complete |
| 3 | Web Backtester (2yr validation) | COMPLETE | Net profit positive | ✅ All gates passed |
| 3.1 | Identify loss drivers | COMPLETE | Root cause analysis | ✅ Revenge trades identified |
| 3.1.1 | Price level cooldown | COMPLETE | Eliminate revenge trades | ✅ 40% loss reduction |
| 3.2 | Entry quality improvement | COMPLETE | Runner protection | ✅ +61% profit boost |
| 3.5 | Range Bar optimization | COMPLETE | Exit system overhaul | ✅ $267 profit, Sharpe 1.59 |
| 3.6 | Portfolio optimization | COMPLETE | Final validation | ✅ **$182 profit, 17.4% DD** |
| 3.3 | Walk-forward validation | COMPLETE | 4/4 cycles profitable | ✅ Robustness confirmed |
| 3.4 | Monte Carlo simulation | COMPLETE | Risk assessment | ✅ 100% profitable (10k runs) |
| **4.1** | **cTrader ZMQ Bridge** | **COMPLETE** | **Tick flow validated** | **✅ 20+ mins stable** |
| **4.2** | **Order Execution** | **NEXT** | **Entry/exit/modify** | **🎯 Ready to start** |
| 4.3 | Demo Trading Validation | PENDING | 1-week demo match | — |
| 5 | VPS + Android + Signal Service | PENDING | Live execution | — |

**Phase 4.1 Achievements:**
1. ✅ cTrader cBot created (C# with NetMQ)
2. ✅ ZMQ bridge operational (tick flow validated 20+ minutes)
3. ✅ Python Brain platform-agnostic (canonical symbols)
4. ✅ Test signal generator (decouple from bar close)
5. ✅ Clean git history (orphan branch, 8.1GB → lightweight)
6. ✅ Automated NuGet installers + documentation

**Phase 4.2 Objectives:**
1. Add order execution to cTrader cBot (entry/exit/modify)
2. Test signal generator validation (15s full cycle)
3. News gating via CalendarValueHistory() → ZMQ
4. Demo trading validation (match backtest behavior within tolerance)
5. 1-week live validation before moving to Phase 5

---

## Phase 4 Implementation Roadmap 🎯

**Status:** Ready to start (Phase 3 validation complete)

**Architecture:**
```
MT5 EA (MQL5)                    Python Brain (src/)
    |                                    |
    |--[ZMQ 5555: Signals]------------->|  BrainCore receives signals
    |<-[ZMQ 5556: Reports]--------------|  MT5 receives entry/exit commands
    |--[ZMQ 5557: News Events]--------->|  News gating via CalendarValueHistory()
    |                                    |
    [Tick Data] --> [Range Bar Builder]-->  Cache to Parquet
                    [DCRD Engine]        -->  Calculate CompositeScore
                    [Strategy Logic]     -->  Generate signals
                    [Exit Manager]       -->  Manage open trades
```

**Key Tasks:**

**4.1 — ZMQ Bridge Setup**
- [ ] MT5 EA: ZMQ socket initialization (5555, 5556, 5557)
- [ ] Python Brain: ZMQ listener threads
- [ ] Message protocol design (JSON format)
- [ ] Connection health monitoring + auto-reconnect

**4.2 — Real-Time Range Bar Processing**
- [ ] Tick ingestion from MT5 (all 4 pairs)
- [ ] Range Bar builder (same logic as backtest)
- [ ] Phantom bar detection (weekend gaps)
- [ ] Parquet cache updates (append-only)

**4.3 — Live DCRD Calculation**
- [ ] 4H Structural Layer (ADX, Market Structure, ATR, CSM, Persistence)
- [ ] 1H Dynamic Modifier (pullback detection, momentum)
- [ ] Range Bar Intelligence (speed, volatility)
- [ ] CompositeScore output (0-100)

**4.4 — Strategy Signal Generation**
- [ ] TrendRider: resumption bar entry logic
- [ ] RangeRider: consolidation block detection
- [ ] Entry gating (price level cooldown, correlation, session filters)
- [ ] Signal packaging → ZMQ 5556 → MT5 EA

**4.5 — Exit Management**
- [ ] Partial exit at 1.5R (CS-based percentage)
- [ ] Trailing SL (Range Bar extremes + 5-pip buffer)
- [ ] Runner protection (R >= -0.5 threshold)
- [ ] Regime deterioration monitoring (CS drop >40 pts)
- [ ] 2R daily cap + weekend close (deep losers only)

**4.6 — News Gating**
- [ ] MT5: CalendarValueHistory() → filter high-impact events
- [ ] MT5: Send news events to Python Brain via ZMQ 5557
- [ ] Python Brain: Block entries N minutes before/after news
- [ ] Config: news filter settings (currencies, impact levels)

**4.7 — Demo Trading Validation**
- [ ] FP Markets demo account setup ($500 starting equity)
- [ ] 1-week live validation (match backtest behavior within tolerance)
- [ ] Metrics to track:
  - Trade count vs expected (~12-15/month)
  - Win rate (target: 45%+)
  - Avg R/trade (target: +0.18R)
  - Max DD (monitor: should stay <20%)
  - Signal latency (measure: tick → signal → execution)
- [ ] Compare live vs backtest on same period (overlap test)

**4.8 — Error Handling & Monitoring**
- [ ] MT5 EA: Error logging (connection, execution, data)
- [ ] Python Brain: Exception handling + graceful degradation
- [ ] Heartbeat monitoring (detect disconnects)
- [ ] Trade reconciliation (MT5 vs Brain state sync)

**Gate:** V4.1 — 1-week demo trading matches backtest metrics (within tolerance)

---

## Tech Stack
- **Python:** 3.11+, MetaTrader5 package, backtesting.py, Plotly/Dash, pyzmq
- **Execution Layer:**
  - MT5: MQL5 (JcampFX_Brain.mq5) + pyzmq
  - cTrader: C# (JcampFX_Brain_SIMPLE.cs) + NetMQ ✅
- **Data:** Parquet (tick storage), Dukascopy tick data
- **Broker:** FP Markets ECN (MT5 + cTrader support)
- **Commission:** $7/lot round-trip | Slippage model: 1.0 pip organic / tick boundary on phantom bars
