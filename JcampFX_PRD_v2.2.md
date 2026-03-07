# JcampFX — Product Requirements Document v2.2

## Regime-Adaptive Multi-Strategy Portfolio Engine

**Dynamic Composite Regime Detection (DCRD) | Range Bar Intelligence | Phantom Liquidity Detection**

*Laptop-First | $500 Start | 5+1 Pair Universe | Modular Brain Architecture*

> **⚠ v2.2 — Analyst-Reviewed + Phantom Liquidity + 20-Pip Migration**

| Field | Detail |
|---|---|
| **Version** | 2.2 |
| **Date** | February 18, 2026 |
| **Author** | Jcamp |
| **Reviewed By** | Forex/EA Analyst Consultant |
| **Broker** | FP Markets (ECN) |
| **Platform** | MetaTrader 5 |
| **Start Capital** | $500 USD |
| **Status** | Phase 1 (Completed), Phase 2–3 (Validation in Progress) |

---

## Revision Log

### v2.0 → v2.1 (Analyst Review)

| # | Area | v2.0 Issue | v2.1 Resolution |
|---|---|---|---|
| R1 | Chandelier SL | Fixed 0.5R by tick — eaten by spread | Dynamic: max(0.5R, ATR14) with 15-pip floor majors / 25-pip JPY |
| R2 | Position Limits | Max 3 at any equity — impossible lots at $500 | Max 2 until equity > $1,000; skip trade if risk < 0.8% |
| R3 | Walk-Forward Data | 6 months / 1 cycle — coin flip | 2+ years tick data; minimum 4 walk-forward cycles |
| R4 | News Source | Forex Factory API (doesn't exist) | MQL5 MqlCalendarValue native functions piped via ZMQ |
| R5 | Strategy Cooldown | 5 losses in 2 calendar days | 5 consecutive losses in last 10 trades (rolling window) |
| R6 | Weekend Protection | Conditional 80/20 split | Close 100% of all positions 20 min before market close |
| R7 | Correlation Mgmt | None — 3 USD-correlated trades possible | Max 2 trades sharing same base/quote currency |
| R8 | Slippage Modeling | Not in backtester | 1.0 pip default slippage on every entry/exit in backtester |
| R9 | Exit System Timing | Introduced in Phase 4 | Moved to Phase 2 so backtests include full exit logic |
| R10 | Performance Cycle | 5-calendar-day rolling window | Last-10-trade rolling window per strategy (consistent with cooldown) |
| R11 | Partial Exit Split | Fixed 70% close at 1.5R | Regime-aware: 60/70/75/80% based on CompositeScore at entry |

### v2.1 → v2.2 (Phantom Liquidity + Analyst Improvements)

| # | Area | v2.1 Issue | v2.2 Resolution |
|---|---|---|---|
| R12 | Range Bar Size | 10-pip bars — 27% edge tax on $500 | 20-pip bars — edge tax drops to ~13.5%, lot granularity improves |
| R13 | Phantom Liquidity | No detection of interpolated bars from price gaps | `is_phantom` flag on all bars created from same tick; `is_gap_adjacent` for first bar in gap sequence |
| R14 | Phantom Exits | Only entries handled phantom bars | Exits on phantom bars filled at actual tick boundary price, not Range Bar close |
| R15 | DCRD Calibration | Thresholds are arbitrary round numbers | Data-driven calibration step using percentile analysis of 2-year dataset |
| R16 | Regime Deterioration | No rule for open trades when regime shifts | Exit parameters frozen at entry; optional force-close if score drops >40 points |
| R17 | BreakoutRider | Entry logic under-specified | Full specification: Keltner(20, 1.5ATR), BB compression <20th percentile, volume confirmation |
| R18 | Session Filtering | No session awareness | Session tags on all signals; per-strategy session filters with recommended active windows |

---

## Table of Contents

1. Executive Summary
2. System Architecture & Modular Brain
3. DCRD – Dynamic Composite Regime Detection
4. DCRD Calibration Methodology *(NEW v2.2)*
5. News & Events Awareness Layer
6. Session Filtering *(NEW v2.2)*
7. 20-Pip Range Bar Migration *(NEW v2.2)*
8. Phantom Liquidity Detection *(NEW v2.2)*
9. Exit Management System
10. Dynamic Risk Sizing (1–3%)
11. Phase 1 – Range Bar Engine & Visualization
12. Phase 2 – DCRD Brain + Strategies + Exit System
13. Phase 3 – Web Backtesting (The Cinema)
14. Phase 4 – Local Bridge (ZMQ Integration)
15. Phase 5 – Deployment (VPS & Android)
16. Risk Management Framework v2.2
17. Master Validation Checklist

---

## 1. Executive Summary

### 1.1 Product Vision

JcampFX is a Regime-Adaptive Multi-Strategy Portfolio Engine. It replaces time-based candlestick analysis with 20-pip Range Bars for noise-free, capital-efficient price action, and replaces binary trend/range toggles with the Dynamic Composite Regime Detection (DCRD) — a multi-layer scoring engine producing a continuous 0–100 confidence score across 4H structural, 1H dynamic, and Range Bar intelligence layers.

The system includes Phantom Liquidity Detection to eliminate backtest bias from price gaps, session-aware signal filtering, and a modular Brain architecture supporting pluggable strategy modules with standardized interfaces.

### 1.2 Key Constraints

| Constraint | Detail |
|---|---|
| **Starting Capital** | $500 USD on FP Markets ECN MT5 account |
| **Pair Universe** | EURUSD, GBPUSD, USDJPY, AUDJPY, USDCHF + CSM 9-pair grid (Gold unlocks at $2,000) |
| **Range Bar Size** | 20 pips (majors), 25–30 pips (JPY pairs) |
| **Infrastructure** | Laptop as Lab (no VPS until Phase 5) |
| **Data Requirement** | 2+ years tick data for Range Bars + 4H/1H candles for DCRD layers |
| **Commission Model** | FP Markets: $7 per standard lot round-trip |
| **Slippage Model** | 1.0 pip default; phantom bars use actual tick boundary price |
| **Edge Tax** | ~13.5% per trade (down from 27% at 10-pip bars) |
| **Risk Per Trade** | Dynamic 1–3% based on DCRD confidence + last-10-trade rolling performance |
| **Daily Loss Cap** | Maximum 2R total loss per day (hard stop) |
| **Max Concurrent** | 2 positions (until equity > $1,000, then 3) |
| **Correlation Limit** | Max 2 trades sharing the same base or quote currency |

### 1.3 Development Timeline

| Phase | Deliverable | Duration | Gate |
|---|---|---|---|
| **Phase 1** | Range Bar Engine (20-pip) + Phantom Detection + Web Chart + M15 Overlay | 2 weeks | Visual validation ✅ |
| **Phase 2** | DCRD Brain + Calibration + 3 Strategies + Exit System + News + Sessions | 4 weeks | Unit tests + regime accuracy |
| **Phase 3** | Web Backtester with 2yr data + Phantom-aware fills + Walk-Forward (4 cycles) | 3 weeks | Profitable after slippage+commission |
| **Phase 4** | ZMQ Bridge + Demo Trading + Risk Controls | 2 weeks | 1-week demo match |
| **Phase 5** | VPS Deployment + Android + Signal Service | 1 week | Live execution |

---

## 2. System Architecture & Modular Brain

### 2.1 Laptop Lab Mode (Phases 1–4)

| Component | Technology | Role | Port |
|---|---|---|---|
| **Data Feed** | MT5 Terminal | Tick + OHLC + Calendar data | N/A |
| **Range Engine** | Python 3.11+ | Tick → 20-pip Range Bar + Phantom flagging | N/A |
| **DCRD Engine** | Python | 4H/1H/RB regime scoring (0–100) | N/A |
| **DCRD Calibrator** | Python (offline) | Percentile-based threshold calibration | N/A |
| **News Layer** | MQL5 Calendar → ZMQ | Native MT5 economic event gating | 5557 |
| **Session Filter** | Python | Session tagging + per-strategy session gating | N/A |
| **Brain Core** | Python (Modular) | Strategy orchestration + correlation filter | N/A |
| **Exit Manager** | Python | Regime-aware partial + Dynamic Chandelier + Regime deterioration | N/A |
| **Web Chart** | Plotly / Dash | Range Bars (organic/phantom coloring) + M15 overlay | 8050 |
| **ZMQ Bridge** | pyzmq / MQL5 | Signal transmission | 5555/5556 |
| **Backtester** | backtesting.py | Phantom-aware simulation with slippage + commission | N/A |

### 2.2 Modular Brain Architecture

The Brain is a plugin-based orchestrator. Each strategy is an independent module with a standardized interface.

**Standard Module Interface:**
- `analyze(range_bars, regime_score, news_state, session_state)` → Signal | None
- `retrain(performance_data)` → void (future ML hook)
- `get_status()` → {active, cooldown_until, last10_R, trade_count, allowed_sessions}

**Design Principles:**
- New strategies added by dropping a module into `/strategies/` — auto-registered without Brain Core changes
- Strategy Registry tracks: allowed regime ranges, active/paused state, rolling performance, session preferences
- Correlation Filter runs AFTER strategy signals, BEFORE ZMQ dispatch
- Performance Tracker feeds rolling last-10-trade R-equity to each module
- Phantom Filter blocks entries triggered on `is_phantom` or `is_gap_adjacent` bars

**Future Extensibility:**
- Additional strategy modules (SessionBreak, NewsSpike, VolatilityFade)
- Hurst exponent + volatility percentile layers in DCRD
- Regime classifier trained on historical trade outcome data (supervised learning)
- Strategy auto-enable/disable based on live performance gradient

### 2.3 Data Flow

```
MT5 (Tick + 4H/1H + Calendar)
    → Range Engine (20-pip bars + is_phantom + is_gap_adjacent flags)
    + DCRD Engine (calibrated thresholds) [parallel]
    → News Layer (event gate)
    → Session Filter (session tag + strategy gating)
    → Brain Core (routes to active strategies by CompositeScore)
    → Phantom Filter (blocks signals on phantom/gap-adjacent bars)
    → Correlation Filter (currency exposure check)
    → Exit Manager (regime-aware partial + Chandelier + deterioration monitor)
    → ZMQ Bridge
    → MT5 Hand EA
```

---

## 3. DCRD – Dynamic Composite Regime Detection

The DCRD produces a Composite Score (0–100) that determines which strategies are active and at what confidence level. No binary triggers — only score zones.

### 3.1 Scoring Formula

```
CompositeScore = StructuralScore (0–100) + ModifierScore (−15 to +15) + RangeBarScore (0–20)
Clamped to 0–100
```

### 3.2 Layer 1 — 4H Structural Regime Score (0–100)

Five components, each 0–20 points. **Thresholds are calibrated using the data-driven methodology in Section 4.**

| Component | Max | 20 Points | 10 Points | 0 Points |
|---|---|---|---|---|
| **ADX Strength** | 20 | ADX > P75 + rising slope | ADX P25–P75 | ADX < P25 |
| **Market Structure** | 20 | ≥3 confirmed HH/HL or LL/LH | Mixed structure | Repeated failure |
| **ATR Expansion** | 20 | ATR ratio > P75 | Ratio P25–P75 | Ratio < P25 |
| **CSM Alignment** | 20 | Base/quote ≥70% across grid | Moderate alignment | Divergent |
| **Trend Persistence** | 20 | ≥70% candles close vs EMA200 | Mixed closure | EMA whipsaw |

> ⚠ **REVISED v2.2:** P25/P75 refer to percentile boundaries derived from the 2-year calibration dataset (see Section 4). Initial values (ADX 18/25, ATR 0.8/1.2) serve as starting estimates only.

### 3.3 Layer 2 — 1H Dynamic Modifier (−15 to +15)

| Sub-Component | +5 | −5 |
|---|---|---|
| **BB Width** | Expanding rapidly | In lowest 20th percentile |
| **ADX Acceleration** | Slope rising strongly | Slope collapsing |
| **CSM Acceleration** | Differential widening | Currency rotation increasing |

### 3.4 Layer 3 — Range Bar Intelligence (0–20)

| Sub-Component | Max | Scoring |
|---|---|---|
| **RB Speed Score** | 10 | Bars/60min: High = 10, Normal = 5, Slow = 0 |
| **RB Structure Quality** | 10 | Directional bars + pullback: Strong = 10, Mixed = 5, Alternating = 0 |

*Range Sizes: Majors = 20 pips, JPY pairs = 25–30 pips (updated from v2.1).*

> ⚠ **REVISED v2.2:** RB Speed Score thresholds must be recalibrated for 20-pip bars. Fewer bars form per hour at 20-pip vs 10-pip. Calibration in Section 4 covers this.

### 3.5 Regime Mapping

| Composite Score | Regime | Strategy | Risk Multiplier |
|---|---|---|---|
| **70–100** | Trending | TrendRider | 0.8x–1.0x |
| **30–70** | Transitional | BreakoutRider | 0.6x |
| **0–30** | Range | RangeRider | 0.7x |

*R:R is path-dependent based on regime-aware partial exit % and Dynamic Chandelier SL on the runner. See Section 9 (Exit Management).*

### 3.6 Anti-Flipping Filter

Regime change ONLY if: Score crosses threshold by ≥15 points AND new regime persists for ≥2 consecutive 4H closes.

### 3.7 Regime Deterioration Rule *(NEW v2.2)*

> ⚠ **NEW:** Addresses what happens to open trades when the regime shifts after entry.

**Core Principle:** Once a trade is open, exit parameters (partial %, Chandelier config) are frozen at entry-time CompositeScore values.

**Optional Force-Close:** If CompositeScore drops more than 40 points from the entry-time score, the runner portion is closed at market. This protects against holding a TrendRider position that entered at CS=78 while the market has shifted to a Range regime (CS=35).

| Condition | Action |
|---|---|
| Score drops ≤40 pts from entry | No change — exit parameters remain frozen |
| Score drops >40 pts from entry | Force-close runner at market; partial exit already locked in |
| Score improves after entry | No change — don't re-open a wider runner |

### 3.8 DCRD Validation

| ID | Validation Criteria | Priority | Status |
|---|---|---|---|
| VD.1 | 4H Structural Score 0–100 with all 5 components contributing | CRITICAL | ☐ Pending |
| VD.2 | 1H Modifier stays −15 to +15, never overrides structural classification | MUST PASS | ☐ Pending |
| VD.3 | Range Bar Intelligence 0–20 independent of structural layer | MUST PASS | ☐ Pending |
| VD.4 | Composite correctly maps: >70 Trending, 30–70 Transitional, <30 Range | CRITICAL | ☐ Pending |
| VD.5 | Anti-flipping: ≥15pt cross + 2x 4H persistence required for regime change | CRITICAL | ☐ Pending |
| VD.6 | 50 historical sequences classified >85% accuracy vs manual ground truth | GATE | ☐ Pending |
| VD.7 | CSM pulls from all 9 monitored pairs + XAUUSD when unlocked | MUST PASS | ☐ Pending |
| VD.8 | Risk Multiplier applied correctly per regime zone (verify 20 samples) | MUST PASS | ☐ Pending |
| VD.9 | Regime deterioration: runner force-closed when score drops >40 pts from entry | CRITICAL | ☐ Pending |
| VD.10 | Exit parameters (partial %, Chandelier config) frozen at entry-time score, never modified by live score changes | MUST PASS | ☐ Pending |

---

## 4. DCRD Calibration Methodology *(NEW v2.2)*

> ⚠ **NEW:** Replaces arbitrary threshold values with data-driven percentile analysis.

### 4.1 The Problem

v2.1 used fixed values (ADX > 25 = "strong", ATR ratio > 1.2 = "expanding") chosen by intuition. These values may not reflect the actual statistical distribution of each indicator across *this specific pair universe at 20-pip Range Bar resolution*. A 20-pip Range Bar on EURUSD produces fundamentally different ADX dynamics than a 10-pip bar — the indicator must be recalibrated.

### 4.2 Calibration Process

Run during Phase 2, before strategy logic is activated.

**Step 1: Generate the Dataset**
1. Compute each DCRD component independently across the full 2+ year dataset for all 5 pairs
2. Store as a time-series: `{timestamp, pair, adx_value, structure_score, atr_ratio, csm_alignment, trend_persistence}`
3. Use 20-pip Range Bar data + 4H/1H candles (matching production configuration)

**Step 2: Analyze Distributions**
For each numeric component (ADX, ATR ratio, BB width, etc.):
1. Plot the distribution (histogram + kernel density)
2. Calculate P25 (25th percentile), P50 (median), P75 (75th percentile)
3. Calculate per-pair and cross-pair distributions

**Step 3: Set Thresholds at Percentile Boundaries**

| Component | 0 Points | 10 Points | 20 Points |
|---|---|---|---|
| **ADX Strength** | < P25 | P25–P75 | > P75 + rising slope |
| **ATR Expansion** | Ratio < P25 | P25–P75 | > P75 |
| **RB Speed** | < P25 bars/hr | P25–P75 | > P75 bars/hr |

Market Structure and Trend Persistence use pattern-based scoring (HH/HL counts, EMA200 closure %) which are inherently data-relative and don't need percentile mapping.

**Step 4: Validate**
1. Apply calibrated thresholds to a held-out 3-month data slice (not used in calibration)
2. Manually label 50 regime sequences on that slice
3. Compare DCRD classification to manual labels → must achieve >85% accuracy

**Step 5: Document**
Store final calibrated values in a `dcrd_config.json` file:
```json
{
  "adx": {"p25": 19.2, "p75": 28.4},
  "atr_ratio": {"p25": 0.85, "p75": 1.25},
  "rb_speed": {"p25": 2.1, "p75": 5.8},
  "calibration_date": "2026-02-18",
  "dataset_range": "2024-01-01 to 2026-01-31",
  "pairs": ["EURUSD", "GBPUSD", "USDJPY", "AUDJPY", "USDCHF"]
}
```

### 4.3 Recalibration Schedule

- **Initial:** During Phase 2 build
- **Quarterly:** Every 3 months, re-run calibration on rolling 2-year window
- **On regime anomaly:** If DCRD accuracy drops below 75% on a monthly review, trigger immediate recalibration

### 4.4 Calibration Validation

| ID | Validation Criteria | Priority | Status |
|---|---|---|---|
| VC.1 | Percentile distributions computed for ADX, ATR ratio, and RB speed across all 5 pairs | CRITICAL | ☐ Pending |
| VC.2 | Calibrated thresholds differ meaningfully from v2.1 fixed values (document delta) | MUST PASS | ☐ Pending |
| VC.3 | Held-out 3-month validation: DCRD accuracy >85% with calibrated thresholds | GATE | ☐ Pending |
| VC.4 | dcrd_config.json generated and loaded by DCRD Engine at startup | MUST PASS | ☐ Pending |
| VC.5 | RB Speed Score thresholds recalibrated for 20-pip bar frequency (not using 10-pip values) | CRITICAL | ☐ Pending |

---

## 5. News & Events Awareness Layer

### 5.1 Data Source

- **Primary:** MQL5 `MqlCalendarValue` / `CalendarValueHistory()` inside Hand EA
- Calendar piped to Python via ZMQ (port 5557) at startup + hourly refresh
- **Fallback:** MQL5 `CalendarCountryById()` for currency-specific filtering
- Format: `{event_id, name, currency, impact, time_utc, actual, forecast, previous}`

### 5.2 Event Classification & Trade Windows

| Impact | Examples | Block Window | Action on Open Trades |
|---|---|---|---|
| **High (Red)** | NFP, FOMC, CPI, ECB Rate | −30 to +15 min | Tighten SL to 0.5R |
| **Medium (Orange)** | PMI, Retail Sales, GDP | −15 to +10 min | No change to open trades |
| **Low (Yellow)** | Housing, Consumer Conf. | No block | Dashboard flag only |

### 5.3 Currency-Specific Gating

Events only block pairs containing the affected currency. USD NFP blocks EURUSD, GBPUSD, USDJPY, USDCHF, XAUUSD. Does NOT block AUDJPY.

### 5.4 Post-Event Cooling

15-minute cooling period after high-impact events: only signals with CompositeScore > 80 allowed. Prevents whipsaw entries on spike-and-reversal patterns.

### 5.5 News Validation

| ID | Validation Criteria | Priority | Status |
|---|---|---|---|
| VN.1 | MQL5 CalendarValueHistory() returns events in correct server timezone | MUST PASS | ☐ Pending |
| VN.2 | Calendar received via ZMQ 5557 within 2 seconds | MUST PASS | ☐ Pending |
| VN.3 | High-impact blocks affected pairs −30 to +15 min (verify 5 historical events) | CRITICAL | ☐ Pending |
| VN.4 | Non-affected pairs remain tradeable (currency-specific gating) | MUST PASS | ☐ Pending |
| VN.5 | Blocked signals logged with event name | MUST PASS | ☐ Pending |
| VN.6 | Post-event cooling: 15 min, only CS > 80 | RECOMMENDED | ☐ Pending |
| VN.7 | Dashboard shows events with countdown timers per currency | RECOMMENDED | ☐ Pending |

---

## 6. Session Filtering *(NEW v2.2)*

> ⚠ **NEW:** Adds session awareness to prevent strategies from trading in low-quality windows.

### 6.1 Rationale

The 5-pair universe spans three major sessions. EURUSD during Asian session is noise. AUDJPY during London open behaves differently than Tokyo. The DCRD's 4H structural score operates on a slower cycle and won't catch intra-session quality shifts.

### 6.2 Session Definitions

| Session | UTC Hours | Primary Pairs | Characteristics |
|---|---|---|---|
| **Tokyo** | 00:00–09:00 | USDJPY, AUDJPY | Range-dominant, low volatility majors |
| **London** | 07:00–16:00 | EURUSD, GBPUSD, USDCHF | Highest volatility, trend initiation |
| **New York** | 12:00–21:00 | All pairs | Continuation or reversal of London moves |
| **London/NY Overlap** | 12:00–16:00 | All pairs | Peak liquidity, strongest trends |
| **Off-Hours** | 21:00–00:00 | None recommended | Low liquidity, wide spreads |

### 6.3 Per-Strategy Session Preferences

Each strategy module declares its preferred active sessions. The Brain Core uses these as soft filters (logged warnings) or hard filters (signal blocked) depending on configuration.

| Strategy | Recommended Sessions | Avoid | Filter Mode |
|---|---|---|---|
| **TrendRider** | London, NY, Overlap | Tokyo (for EUR/GBP/CHF pairs), Off-Hours | Hard filter |
| **BreakoutRider** | London Open (07:00–09:00), NY Open (12:00–14:00) | Off-Hours | Hard filter |
| **RangeRider** | Tokyo (JPY pairs), Late NY (18:00–21:00) | London/NY Overlap | Soft filter (log warning) |

**Implementation:**
- Session state is computed from server time and injected into `analyze()` calls
- Each strategy's `allowed_sessions` field in the registry determines gating behavior
- Blocked signals logged as `SESSION_BLOCKED` with session and pair details
- Dashboard displays current active session with pair-level activity indicator

### 6.4 Session Validation

| ID | Validation Criteria | Priority | Status |
|---|---|---|---|
| VS.1 | Session detection correctly identifies Tokyo/London/NY/Overlap/Off-Hours from server time | MUST PASS | ☐ Pending |
| VS.2 | TrendRider blocked from EURUSD during Tokyo session (hard filter) | MUST PASS | ☐ Pending |
| VS.3 | BreakoutRider active only during London Open and NY Open windows | MUST PASS | ☐ Pending |
| VS.4 | RangeRider on JPY pairs allowed during Tokyo (soft filter logs but doesn't block) | MUST PASS | ☐ Pending |
| VS.5 | Session-blocked signals logged as SESSION_BLOCKED with details | MUST PASS | ☐ Pending |
| VS.6 | Backtest shows win rate comparison: session-filtered vs unfiltered per strategy | RECOMMENDED | ☐ Pending |

---

## 7. 20-Pip Range Bar Migration *(NEW v2.2)*

### 7.1 Rationale: The "Friction vs. Capital" Balance

Operating a $500 account at 10-pips created two structural weaknesses:

- **High Edge Tax:** Total friction (spread + commission + slippage) of ~2.7 pips consumed 27% of the 10-pip gross target
- **Lot Size Inflexibility:** At 10 pips, dynamic risk multipliers frequently pushed lot sizes below the 0.01 minimum, triggering the RISK_TOO_LOW skip rule

### 7.2 Impact of the 20-Pip Change

| Metric | 10-Pip Bars | 20-Pip Bars | Improvement |
|---|---|---|---|
| **Edge Tax** | ~27% | ~13.5% | 2x efficiency gain |
| **Lot @ 1% risk ($5)** | 0.05 lots | 0.025 → 0.02 lots | Still above 0.01 floor |
| **Lot @ 1.5x multiplier** | 0.075 → 0.07 | 0.0375 → 0.03 | Expressible in MT5 |
| **Lot @ 2x multiplier** | 0.10 lots | 0.05 → 0.04 | Expressible in MT5 |
| **Trade frequency** | Higher (more bars/day) | Lower (fewer bars/day) | Less friction, fewer commissions |
| **RISK_TOO_LOW skips** | Frequent at low multipliers | Rare | More signals executed |

### 7.3 Pair-Specific Range Sizes

| Pair | Range Size | Rationale |
|---|---|---|
| EURUSD | 20 pips | Standard major, moderate volatility |
| GBPUSD | 20 pips | Higher volatility but 20 pips still optimal |
| USDCHF | 20 pips | Similar dynamics to EURUSD |
| USDJPY | 25 pips | JPY pairs need wider bars for clean structure |
| AUDJPY | 25–30 pips | Cross-pair volatility requires wider bars |
| XAUUSD | 50–100 pips | When unlocked at $2,000 equity; separate calibration required |

### 7.4 DCRD Re-tuning Required

The 20-pip change affects DCRD Layer 3 (Range Bar Intelligence):
- **RB Speed Score:** Fewer bars form per hour → the "high speed" threshold must be recalibrated (see Section 4)
- **RB Structure Quality:** Consecutive directional bar patterns form differently at 20-pip resolution
- **Chandelier SL floors:** 15-pip floor on majors is now 75% of the bar size — may need adjustment to 10 pips (50% of bar) after backtesting

### 7.5 Migration Validation

| ID | Validation Criteria | Priority | Status |
|---|---|---|---|
| VM.1 | 20-pip granularity allows lot sizes between 0.02 and 0.05 on $500 | MUST PASS | ✅ PASSED |
| VM.2 | Edge tax confirmed at ~13.5% (spread + commission + slippage / 20 pips) | MUST PASS | ✅ PASSED |
| VM.3 | RISK_TOO_LOW skip rate < 5% of signals (down from ~15% at 10-pip) | MUST PASS | ☐ Pending |
| VM.4 | JPY pairs use 25–30 pip bars; verify structure quality at this resolution | MUST PASS | ☐ Pending |
| VM.5 | Chandelier SL floor reassessed: confirm 15-pip floor still appropriate vs 20-pip bar size | RECOMMENDED | ☐ Pending |

---

## 8. Phantom Liquidity Detection *(NEW v2.2)*

### 8.1 The Problem: Mathematical Interpolation

In events like news spikes or market opens, price "teleports" (e.g., jumping from 1.1000 to 1.1050 in one tick). The standard Range Bar algorithm creates "phantom" bars to fill that 50-pip gap. Backtesting on these bars leads to Phantom Profits — trades that execute at prices where no liquidity ever existed.

### 8.2 Bar Classification

| Bar Type | Definition | Color in Cinema | Tradeable |
|---|---|---|---|
| **Organic** | First bar produced by a price movement | Solid Green/Red | ✅ Yes |
| **Phantom** | Any subsequent bar from the same timestamped tick (while-loop continuation) | Gray (Alpha 0.3) | ❌ No — signal blocked |
| **Gap-Adjacent** | The first bar in a gap sequence (price teleported past it) | Orange outline | ⚠ Caution — strategy can optionally avoid |

> ⚠ **NEW v2.2 (Gap-Adjacent):** If price jumps from 1.1000 to 1.1060, the first 20-pip bar (1.1000→1.1020) is organic but un-tradeable at intermediate prices — the market teleported past it. Marking it `is_gap_adjacent=True` lets strategies optionally filter it.

### 8.3 Implementation

```python
@dataclass
class RangeBar:
    # ... existing fields ...
    is_phantom: bool = False       # Bars 2+ from same tick
    is_gap_adjacent: bool = False  # First bar in a multi-bar tick sequence

# Updated Feed Logic
def feed(self, ts: datetime, bid: float, ask: float):
    bars_from_this_tick = 0
    while (self._bar_high - self._bar_open) >= self.bar_size - 1e-10:
        is_phantom = bars_from_this_tick > 0
        bar = self._close_bar_up(ts, is_phantom=is_phantom)
        completed.append(bar)
        self._open_bar(bar.close, ts)
        bars_from_this_tick += 1
    
    # Post-process: if multiple bars created, mark first as gap-adjacent
    if bars_from_this_tick > 1 and len(completed) >= bars_from_this_tick:
        completed[-bars_from_this_tick].is_gap_adjacent = True
```

### 8.4 Entry Rules on Phantom/Gap Bars

| Signal Type | Organic Bar | Gap-Adjacent Bar | Phantom Bar |
|---|---|---|---|
| **Entry Signal** | ✅ Execute normally | ⚠ Strategy decides (configurable) | ❌ Blocked — logged as PHANTOM_BLOCKED |
| **Backtester Fill** | Standard 1.0 pip slippage | Actual tick boundary price | N/A (no entry) |
| **Exit / SL Hit** | Standard fill | Actual tick boundary price | Actual tick boundary price |

### 8.5 Exit Rules on Phantom Bars *(NEW v2.2)*

> ⚠ **NEW:** v2.1 only handled entries on phantom bars. v2.2 also addresses exits.

If a Chandelier SL, 1.5R target, or any stop/target is hit during a phantom bar sequence:
- **Backtester fill price:** Use the actual tick boundary price (the real gap price), not the Range Bar close
- **Live execution:** MT5 will naturally fill at the gap price (this models correctly)
- **Dashboard:** Flag exits on phantom bars with a "GAP EXIT" tag for post-trade analysis

### 8.6 Phantom Validation

| ID | Validation Criteria | Priority | Status |
|---|---|---|---|
| VP.1 | `is_phantom=True` for all bars sharing a tick timestamp (bars 2+) | CRITICAL | ✅ PASSED |
| VP.2 | `is_gap_adjacent=True` for first bar when multiple bars created from one tick | CRITICAL | ☐ Pending |
| VP.3 | Cinema renders phantom bars in Gray (alpha 0.3), gap-adjacent with orange outline | MUST PASS | ☐ Pending |
| VP.4 | No entry signals execute on phantom bars (all blocked and logged) | CRITICAL | ☐ Pending |
| VP.5 | Gap-adjacent filter is configurable per strategy (on/off) | MUST PASS | ☐ Pending |
| VP.6 | Backtester fills exits on phantom bars at actual tick boundary, not RB close | CRITICAL | ☐ Pending |
| VP.7 | Backtest report shows "% of Trades on Phantom Bars" and "% Gap Exits" metrics | MUST PASS | ☐ Pending |
| VP.8 | Comparative backtest: phantom-filtered vs unfiltered equity curves | RECOMMENDED | ☐ Pending |

---

## 9. Exit Management System

The Exit Manager handles all post-entry logic: regime-aware partial profit-taking, dynamic trailing stops, and regime deterioration monitoring.

### 9.1 Two-Stage Exit Flow

#### Stage 1: Regime-Aware Partial Exit at 1.5R

When price reaches 1.5R, close a regime-dependent percentage (locked at entry-time CompositeScore):

| CompositeScore (at entry) | Regime | Close % | Runner % | Locked Profit |
|---|---|---|---|---|
| > 85 | Deep Trending | 60% | 40% | +0.90R |
| 70–85 | Trending | 70% | 30% | +1.05R |
| 30–70 | Transitional | 75% | 25% | +1.125R |
| < 30 | Range | 80% | 20% | +1.20R |

#### Stage 2: Dynamic Chandelier SL on Remaining Runner

- **Chandelier distance = max(0.5R, ATR(14) of Range Bar timeframe)**
- **Minimum floor:** 15 pips on majors | 25 pips on JPY pairs *(reassess after 20-pip migration backtests)*
- Trailing: moves by tick in profitable direction only (never widens)
- Runner runs until Chandelier SL hit
- **Phantom exit handling:** If SL/TP hit on phantom bar, fill at actual tick boundary price (Section 8.5)

### 9.2 Regime Deterioration Monitor

Exit parameters are frozen at entry-time values. However:

| Score Delta from Entry | Action |
|---|---|
| ≤40 point drop | No change — frozen parameters hold |
| >40 point drop | Force-close runner at market; partial profit already secured |

### 9.3 Exit Math by Regime

| Scenario | Deep Trend (60/40) | Transitional (75/25) | Range (80/20) | Full SL |
|---|---|---|---|---|
| **1.5R, reverses** | +0.90 + 0.40 = +1.30R | +1.125 + 0.25 = +1.375R | +1.20 + 0.20 = +1.40R | N/A |
| **Runs to 3R** | +0.90 + 1.0 = +1.90R | +1.125 + 0.63 = +1.75R | +1.20 + 0.50 = +1.70R | N/A |
| **Runs to 5R** | +0.90 + 1.8 = +2.70R | +1.125 + 1.13 = +2.25R | +1.20 + 0.90 = +2.10R | N/A |
| **Never hits 1.5R** | N/A | N/A | N/A | −1.0R |

### 9.4 Exit Validation

| ID | Validation Criteria | Priority | Status |
|---|---|---|---|
| VE.1 | Partial exit fires at exactly 1.5R on > 95% of qualifying trades | CRITICAL | ☐ Pending |
| VE.2 | Regime-aware split: 60% (CS>85), 70% (70–85), 75% (30–70), 80% (<30) — all 4 tiers verified | CRITICAL | ☐ Pending |
| VE.3 | Chandelier SL = max(0.5R, ATR14) with floor ≥15 pips majors / ≥25 pips JPY | CRITICAL | ☐ Pending |
| VE.4 | Chandelier moves by tick in profitable direction only | MUST PASS | ☐ Pending |
| VE.5 | Runner stays open until Chandelier hit (no premature close) | MUST PASS | ☐ Pending |
| VE.6 | Full losers show exactly −1.0R | MUST PASS | ☐ Pending |
| VE.7 | Exit parameters use CompositeScore at entry time, not current | CRITICAL | ☐ Pending |
| VE.8 | Regime deterioration: runner force-closed when score drops >40 pts from entry | CRITICAL | ☐ Pending |
| VE.9 | Exits on phantom bars fill at actual tick boundary price | CRITICAL | ☐ Pending |
| VE.10 | Backtest: Chandelier survives 2-pip spread spike vs fixed 0.5R (comparative) | RECOMMENDED | ☐ Pending |

---

## 10. Dynamic Risk Sizing (1–3%)

### 10.1 Formula

```
Risk% = BaseRisk × ConfidenceMultiplier × PerformanceMultiplier
Clamped: min 1.0%, max 3.0%. If calculated risk < 0.8% → SKIP the trade.
```

### 10.2 Factor 1: DCRD Confidence

| Condition | Multiplier | Rationale |
|---|---|---|
| Score > 85 (deep regime) | 1.2x | Strong conviction |
| Score 70–85 or < 15 | 1.0x | Normal confidence |
| Score 45–55 (mid-transitional) | 0.8x | Uncertain zone |
| Near boundary (±5 pts of 30 or 70) | 0.7x | Regime could flip |

### 10.3 Factor 2: Last-10-Trade Rolling Performance

| Last 10 Trades R | Multiplier | Rationale |
|---|---|---|
| ≥ +5R | 1.3x | Strong edge — capitalize |
| +2R to +5R | 1.1x | Positive momentum |
| 0 to +2R | 1.0x | Neutral |
| −2R to 0 | 0.8x | Reduce exposure |
| < −2R | 0.6x | Protect capital |

Each strategy tracks independently.

### 10.4 Lot Size Floor Rule (Updated for 20-pip)

At 20-pip bars, 1% risk ($5) = 0.025 lots → rounds to 0.02. Dynamic multipliers produce lot sizes that remain expressible in MT5 0.01 increments across most scenarios. The 0.8% skip rule still applies but triggers far less frequently.

**Rule: if Risk% < 0.8% after multipliers → skip the trade. Do not round up to 0.01.**

### 10.5 Risk Validation

| ID | Validation Criteria | Priority | Status |
|---|---|---|---|
| VR.1 | Risk% always 1.0%–3.0% (or skipped if < 0.8%) | CRITICAL | ☐ Pending |
| VR.2 | Confidence multiplier reflects CompositeScore distance | MUST PASS | ☐ Pending |
| VR.3 | Last-10-trade multiplier recalculates after every completed trade per strategy | MUST PASS | ☐ Pending |
| VR.4 | Strategies have independent performance tracking | CRITICAL | ☐ Pending |
| VR.5 | Near-boundary trades (±5 pts) get 0.7x | MUST PASS | ☐ Pending |
| VR.6 | Trades with < 0.8% risk logged as RISK_TOO_LOW and skipped | CRITICAL | ☐ Pending |
| VR.7 | RISK_TOO_LOW skip rate < 5% of signals at 20-pip bars (verify) | MUST PASS | ☐ Pending |
| VR.8 | Backtest: dynamic risk produces higher Sharpe than fixed 1% over 2 years | RECOMMENDED | ☐ Pending |

---

## PHASE 1: Range Bar Engine & Visualization

*Status: ✅ COMPLETED*

### 11.1 Data Ingestion

1. Connect Python to FP Markets MT5 via MetaTrader5 package
2. Download 2+ years tick data for all 5 pairs (Dukascopy fallback if needed)
3. Download M15 OHLC candles for comparison overlay
4. Store in Parquet; incremental download

### 11.2 Range Bar Converter (20-pip)

1. 20-pip bars for majors, 25–30 for JPY pairs
2. Pure price-driven: new bar on X-pip move from open
3. Store: Open, High, Low, Close, Volume (ticks), Start Time, End Time, `is_phantom`, `is_gap_adjacent`
4. Handle weekend gaps without false bars

### 11.3 Web Chart

1. Plotly OHLC with color coding: Organic (green/red), Phantom (gray α0.3), Gap-Adjacent (orange outline)
2. Volume bars below chart
3. Pair selector (5 symbols)
4. Toggle-able M15 comparison overlay

### 11.4 Validation

| ID | Validation Criteria | Priority | Status |
|---|---|---|---|
| V1.1 | 2+ years tick data + M15 OHLC for all 5 pairs | MUST PASS | ✅ |
| V1.2 | Parquet has correct bid/ask/timestamp columns | MUST PASS | ✅ |
| V1.3 | Range Bars: High–Low = exactly 20 pips (within spread tolerance) | CRITICAL | ✅ |
| V1.4 | Bars span different durations (purely price-driven) | CRITICAL | ✅ |
| V1.5 | 20-pip granularity allows lot sizes 0.02–0.05 on $500 | MUST PASS | ✅ |
| V1.6 | `is_phantom=True` for all bars sharing a tick timestamp | CRITICAL | ✅ |
| V1.7 | `is_gap_adjacent=True` for first bar in multi-bar tick sequences | CRITICAL | ☐ Pending |
| V1.8 | Cinema renders: organic solid, phantom gray, gap-adjacent orange outline | MUST PASS | ☐ Pending |
| V1.9 | M15 overlay toggles and time-aligns correctly | RECOMMENDED | ✅ |
| V1.10 | Unit test: 100 ticks → deterministic N Range Bars with correct phantom flags | CRITICAL | ✅ |

---

## PHASE 2: DCRD Brain + Strategies + Exit System

*Status: Validation in Progress*

### 12.1 DCRD Implementation

Implement full 3-layer DCRD with calibrated thresholds (Section 4).

### 12.2 Strategy Specifications

**Strategy A – TrendRider (CompositeScore 70–100)**
- Entry: 2nd Range Bar pull-back in trend direction
- Confirmation: ADX > calibrated P75 + 3-bar staircase
- Exit: Regime-aware partial at 1.5R + Dynamic Chandelier on runner (Section 9)
- Sessions: London, NY, Overlap (hard filter — blocked during Tokyo for EUR/GBP/CHF)

**Strategy B – BreakoutRider (CompositeScore 30–70)**

> ⚠ **REVISED v2.2:** Fully specified entry logic (was under-specified in v2.1).

- Entry: Range Bar closes outside **Keltner Channel (20-period, 1.5× ATR)**
- Confirmation (ALL required):
  1. Bollinger Band width in lowest 20th percentile (compression confirmed)
  2. Range Bar speed increasing (≥2 bars formed in last 30 minutes)
  3. Break of previous micro-structure (prior swing high/low violated)
- Exit: Regime-aware partial at 1.5R + Dynamic Chandelier on runner
- Sessions: London Open (07:00–09:00 UTC), NY Open (12:00–14:00 UTC) — hard filter
- News filter: No entry within high-impact window per Section 5
- Gap filter: No entry on `is_phantom` or `is_gap_adjacent` bars (hard block)

**Strategy C – RangeRider (CompositeScore 0–30)**
- Entry: Fade at consolidation boundaries
- Confirmation: ≥8 Range Bars in block + width > 2× RB size
- Exit: Regime-aware partial at 1.5R + Dynamic Chandelier on runner
- Sessions: Tokyo (JPY pairs), Late NY — soft filter

### 12.3 Correlation Filter

**Rule: Maximum 2 open trades sharing the same base or quote currency.**
- Pre-dispatch filter in Brain Core
- Blocked signals logged as `CORRELATION_BLOCKED`
- Dashboard displays currency exposure grid

### 12.4 Gold Gate

```python
if Account_Equity < 2000: Allowed_Pairs.remove("XAUUSD")
```

### 12.5 Performance Tracker

- Track TrendRider_R, BreakoutRider_R, RangeRider_R independently
- If strategy R < 15-trade rolling average → temporarily disable
- Re-enable after 3 positive paper trades

### 12.6 Validation

| ID | Validation Criteria | Priority | Status |
|---|---|---|---|
| V2.1 | DCRD CompositeScore computed with calibrated thresholds (all 3 layers; 0–100) | CRITICAL | ☐ Pending |
| V2.2 | TrendRider triggers ONLY when CompositeScore ≥70 AND within allowed session | MUST PASS | ☐ Pending |
| V2.3 | BreakoutRider triggers ONLY in 30–70 with BB compression <20th percentile + Keltner break + RB speed increase | CRITICAL | ☐ Pending |
| V2.4 | RangeRider: min 8 RBs + width > 2× RB size | MUST PASS | ☐ Pending |
| V2.5 | Gold Gate blocks XAUUSD < $2,000, allows ≥ $2,000 | CRITICAL | ☐ Pending |
| V2.6 | Max concurrent: 2 positions (3 if equity > $1,000) | CRITICAL | ☐ Pending |
| V2.7 | Correlation filter: max 2 trades same base/quote currency | CRITICAL | ☐ Pending |
| V2.8 | Standardized signal includes: timestamp, pair, direction, entry, SL, TP, strategy, confidence, risk%, session, phantom_status | MUST PASS | ☐ Pending |
| V2.9 | News layer blocks signals during high-impact windows | CRITICAL | ☐ Pending |
| V2.10 | Phantom filter blocks entries on `is_phantom` bars; gap-adjacent configurable per strategy | CRITICAL | ☐ Pending |
| V2.11 | Exit Manager: regime-aware partial + Chandelier + regime deterioration (>40pt force-close) | CRITICAL | ☐ Pending |
| V2.12 | Session filter: TrendRider blocked Tokyo/EUR, BreakoutRider only London/NY Open | MUST PASS | ☐ Pending |
| V2.13 | New strategy module auto-registers from /strategies/ | MUST PASS | ☐ Pending |
| V2.14 | Performance tracker disables/re-enables correctly | MUST PASS | ☐ Pending |
| V2.15 | Anti-flipping filter prevents regime oscillation | CRITICAL | ☐ Pending |
| V2.16 | Unit tests pass for all 3 strategies independently | GATE | ☐ Pending |

---

## PHASE 3: Web Backtesting – The "Cinema"

*Status: Validation in Progress*

### 13.1 Simulation Engine

1. backtesting.py with 20-pip Range Bar DataFrame + DCRD score timeline + phantom flags
2. Replay 4H/1H for historical DCRD computation with calibrated thresholds
3. All 3 strategies across 2+ years per pair
4. Commission: $7/lot round-trip
5. Slippage: 1.0 pip default on organic bars; actual tick boundary on phantom/gap-adjacent
6. Spread: historical tick-based modeling
7. Historical news events replayed with trade blocks
8. Session filtering applied historically
9. Walk-forward: 4-month train / 2-month test, minimum 4 complete cycles

### 13.2 Visual Verification (Cinema)

1. Equity curve with drawdown overlay
2. DCRD CompositeScore timeline with color-coded regime bands
3. Trade markers: entry, exit, partial at 1.5R, Chandelier trail path
4. **Phantom bar rendering:** organic solid, phantom gray, gap-adjacent orange
5. **Regime deterioration markers:** show where >40pt drops triggered force-closes
6. Strategy attribution coloring + session shading
7. M15 comparison panel (toggle)
8. Trade log: Date, Pair, Strategy, Session, Regime Score, Entry, Exit, Slippage, PnL, R-Multiple, Phantom_Flag

### 13.3 Hurdle Checks

- **Net Profit:** Positive after commissions + slippage + spread over 2+ years
- **Partial Exit:** Regime-aware split at 1.5R on > 95% of qualifying trades
- **Chandelier:** Dynamic max(0.5R, ATR14) with pip floors
- **Daily 2R Cap:** No day exceeds 2R total loss
- **Strategy Cooldown:** 5 consecutive losses in last 10 trades → 24hr pause
- **Correlation:** Never > 2 trades same base/quote currency
- **Position Limits:** Max 2 concurrent (3 if equity > $1,000)
- **Risk Floor:** No trades with < 0.8% risk
- **News Blocks:** No entries during historical high-impact windows
- **Phantom Filter:** No entries on phantom bars; gap-adjacent per strategy config
- **Session Filter:** Entries respect per-strategy session preferences
- **Regime Deterioration:** Runner force-closes logged when score drops >40 pts
- **Phantom Metrics:** Report shows "% Phantom Bars", "% Gap Exits", "Phantom-Filtered vs Unfiltered PnL"

### 13.4 Validation

| ID | Validation Criteria | Priority | Status |
|---|---|---|---|
| V3.1 | Equity net positive after $7/lot + slippage + spread over 2+ years | GATE | ☐ Pending |
| V3.2 | Max drawdown < 20% of peak equity | CRITICAL | ☐ Pending |
| V3.3 | 4 walk-forward cycles: each test within 30% of train performance | CRITICAL | ☐ Pending |
| V3.4 | Cinema renders phantom bars gray, gap-adjacent orange | MUST PASS | ☐ Pending |
| V3.5 | Regime-aware partial fires correctly per entry-time CompositeScore | CRITICAL | ☐ Pending |
| V3.6 | Chandelier trails correctly with ATR adaptation + pip floors | CRITICAL | ☐ Pending |
| V3.7 | No day exceeds 2R total loss | CRITICAL | ☐ Pending |
| V3.8 | Cooldown: 5 losses in last 10 trades → 24hr pause | MUST PASS | ☐ Pending |
| V3.9 | Correlation: never > 2 trades same base/quote | MUST PASS | ☐ Pending |
| V3.10 | Position cap enforced throughout | MUST PASS | ☐ Pending |
| V3.11 | No entries during historical news windows | MUST PASS | ☐ Pending |
| V3.12 | No entries on phantom bars; gap-adjacent per config | CRITICAL | ☐ Pending |
| V3.13 | Exits on phantom bars filled at tick boundary price | CRITICAL | ☐ Pending |
| V3.14 | Session filtering applied; backtest shows session-filtered vs unfiltered comparison | MUST PASS | ☐ Pending |
| V3.15 | Regime deterioration force-closes logged and visualized | MUST PASS | ☐ Pending |
| V3.16 | Each strategy individually profitable | CRITICAL | ☐ Pending |
| V3.17 | DCRD regime timeline visible and color-coded | MUST PASS | ☐ Pending |
| V3.18 | Phantom metrics report: % phantom bars, % gap exits, filtered vs unfiltered PnL | MUST PASS | ☐ Pending |
| V3.19 | Slippage impact report: with vs without 1-pip slippage | RECOMMENDED | ☐ Pending |
| V3.20 | Sharpe > 1.0 combined portfolio | RECOMMENDED | ☐ Pending |
| V3.21 | Profit Factor > 1.5 after all costs | RECOMMENDED | ☐ Pending |

**Milestone:** Browser shows upward equity curve over 2+ years with DCRD regime bands, phantom-filtered results, session overlays, and 4 walk-forward cycles positive. This system has been stress-tested across every realistic execution model.

---

## PHASE 4: Local Bridge – ZMQ Integration

### 14.1 Hand EA (MQL5)

1. Listen ZMQ tcp://localhost:5555
2. Accept: `{Symbol, Action, Lot, SL, TP_1.5R, ChandelierConfig:{atr_period:14, min_pips:15/25}, entry_cs:78, session:"london"}`
3. Handle regime-aware partial close: 60–80% at 1.5R, activate Dynamic Chandelier on runner
4. Chandelier: max(0.5R, ATR14) with pip floor, trail by tick
5. CLOSE_ALL within 500ms
6. Report: order ID, fill, slippage, commission, partial details, phantom_flag
7. Pipe MQL5 CalendarValueHistory() to Python via ZMQ port 5557

### 14.2 Daily Protection: 2R Cap

- **if Daily_R_Total ≤ −2.0R → CLOSE_ALL + PAUSE until 00:00 next day**
- R per trade = risk amount of that individual trade
- Dashboard: real-time daily R meter with −2R threshold

### 14.3 Strategy Cooldown

- **Rule:** 5 consecutive losses in strategy's last 10 trades → pause that strategy 24 hours
- Other strategies remain active
- Weekend protection losses excluded from count
- After 24hr hold, counter resets

### 14.4 Weekend Protection

**Rule: Close 100% of all open positions 20 minutes before Friday market close. No exceptions.**

Revisit when equity > $5,000.

### 14.5 Validation

| ID | Validation Criteria | Priority | Status |
|---|---|---|---|
| V4.1 | ZMQ connection within 2 seconds | MUST PASS | ☐ Pending |
| V4.2 | Trade commands execute in MT5 demo | CRITICAL | ☐ Pending |
| V4.3 | Regime-aware partial (60/70/75/80%) executes per entry-time CS | CRITICAL | ☐ Pending |
| V4.4 | Dynamic Chandelier trails correctly in live demo | CRITICAL | ☐ Pending |
| V4.5 | CLOSE_ALL within 500ms | MUST PASS | ☐ Pending |
| V4.6 | 2R daily cap triggers at −2R cumulative | CRITICAL | ☐ Pending |
| V4.7 | Cooldown: 5 losses in last 10 trades pauses strategy | MUST PASS | ☐ Pending |
| V4.8 | Weekend: 100% close 20 min before Friday | MUST PASS | ☐ Pending |
| V4.9 | Correlation filter blocks 3rd same-currency trade | MUST PASS | ☐ Pending |
| V4.10 | MQL5 calendar via ZMQ 5557 | MUST PASS | ☐ Pending |
| V4.11 | Session filter active in demo | MUST PASS | ☐ Pending |
| V4.12 | Regime deterioration force-close triggers in demo | MUST PASS | ☐ Pending |
| V4.13 | 1-week demo: dashboard matches MT5 > 95% | GATE | ☐ Pending |
| V4.14 | Recovers from disconnect without duplicate orders | MUST PASS | ☐ Pending |
| V4.15 | Latency: < 100ms localhost | RECOMMENDED | ☐ Pending |

---

## PHASE 5: Deployment – VPS & Android

### 15.1 VPS Migration

- Transfer all components + `dcrd_config.json` to NY4 VPS
- Parallel run: laptop + VPS 48 hours
- systemd + auto-restart
- Log rotation + daily performance email

### 15.2 Android Dashboard

- Streamlit HTTPS (Let's Encrypt)
- Display: positions, daily R-meter, equity curve, DCRD per pair, currency exposure, upcoming news, active session, phantom bar %
- Telegram: entries, partials, daily summary, 2R alerts, cooldowns, correlation blocks, regime deterioration closes
- Emergency kill switch

### 15.3 Signal Service

- Standardized format for subscribers
- 30-second delay
- Public performance dashboard with regime history

### 15.4 Validation

| ID | Validation Criteria | Priority | Status |
|---|---|---|---|
| V5.1 | VPS 48hr stable | CRITICAL | ☐ Pending |
| V5.2 | Parallel: identical signals 48hr | GATE | ☐ Pending |
| V5.3 | Dashboard < 3 sec with full data | MUST PASS | ☐ Pending |
| V5.4 | Telegram: all events + daily R + regime deterioration alerts | MUST PASS | ☐ Pending |
| V5.5 | Kill switch < 2 sec | CRITICAL | ☐ Pending |
| V5.6 | Auto-restart from reboot | MUST PASS | ☐ Pending |
| V5.7 | First live trade: correct dynamic risk + DCRD + session + phantom check | GATE | ☐ Pending |
| V5.8 | Calendar auto-syncs hourly | MUST PASS | ☐ Pending |
| V5.9 | dcrd_config.json loaded correctly on VPS (verify threshold values match laptop) | MUST PASS | ☐ Pending |

---

## 16. Risk Management Framework v2.2

| Risk Control | Rule | Enforcement |
|---|---|---|
| **Position Sizing** | Dynamic 1–3% (skip if < 0.8%) | Python pre-signal calculation |
| **Max Concurrent** | 2 positions (3 if equity > $1,000) | Brain Core blocks |
| **Correlation Limit** | Max 2 trades same base/quote currency | Pre-dispatch filter |
| **Daily Loss Cap** | 2R total → CLOSE_ALL + PAUSE | Cumulative R tracker; resets 00:00 |
| **Strategy Cooldown** | 5 consecutive losses in last 10 trades → 24hr hold | Per-strategy rolling window |
| **Max Daily Trades** | 5 new trades per day | Counter resets 00:00 |
| **Gold Gate** | XAUUSD blocked until equity ≥ $2,000 | Hard-coded check |
| **Commission** | $7/lot in all calculations | Backtester + live PnL |
| **Slippage** | 1.0 pip organic; tick boundary on phantom/gap | Backtester + live model |
| **Partial Exit** | Regime-aware: 60/70/75/80% at 1.5R (entry-time CS) | Exit Manager + DCRD |
| **Chandelier SL** | max(0.5R, ATR14), floor 15/25 pips, trail by tick | Exit Manager + Hand EA |
| **Regime Deterioration** | >40pt CS drop → force-close runner | Exit Manager monitor |
| **Weekend** | 100% close 20 min before Friday | Friday scheduler |
| **News Gating** | High: −30/+15 min · Medium: −15/+10 min | MQL5 Calendar → ZMQ |
| **Post-News Cool** | 15 min: only CS > 80 | Brain Core filter |
| **Anti-Flip** | ≥15pt cross + 2x 4H persistence | DCRD stability filter |
| **Phantom Filter** | Block entries on phantom bars; flag gap-adjacent | Range Engine + Brain Core |
| **Session Filter** | Per-strategy session gating (hard/soft) | Brain Core + strategy config |
| **Lot Size Floor** | 0.01 min; skip if risk < 0.8% | Pre-signal validation |
| **DCRD Calibration** | Percentile-based; quarterly recalibration | dcrd_config.json |

---

## 17. Master Validation Checklist

| Section | Checks | GATE | CRITICAL |
|---|---|---|---|
| **DCRD (Sec 3)** | 10 | 1 | 4 |
| **DCRD Calibration (Sec 4)** | 5 | 1 | 2 |
| **News Layer (Sec 5)** | 7 | 0 | 1 |
| **Session Filter (Sec 6)** | 6 | 0 | 0 |
| **20-Pip Migration (Sec 7)** | 5 | 0 | 0 |
| **Phantom Detection (Sec 8)** | 8 | 0 | 4 |
| **Exit System (Sec 9)** | 10 | 0 | 6 |
| **Dynamic Risk (Sec 10)** | 8 | 0 | 3 |
| **Phase 1 (Sec 11)** | 10 | 0 | 4 |
| **Phase 2 (Sec 12)** | 16 | 1 | 8 |
| **Phase 3 (Sec 13)** | 21 | 1 | 7 |
| **Phase 4 (Sec 14)** | 15 | 1 | 4 |
| **Phase 5 (Sec 15)** | 9 | 2 | 2 |
| **TOTAL** | **130** | **7** | **45** |

### Priority Legend

| Priority | Definition |
|---|---|
| **GATE** | Hard stop – Cannot proceed without passing |
| **CRITICAL** | Must pass before sign-off; requires root cause analysis |
| **MUST PASS** | Required; can resolve in parallel with next phase |
| **RECOMMENDED** | Best practice; defer if timeline is tight |

---

*JcampFX PRD v2.2 — Analyst-Reviewed + Phantom Liquidity + 20-Pip Migration*

> *"You are no longer running a trend EA. You are running a Regime-Adaptive Multi-Strategy Portfolio Engine."*
