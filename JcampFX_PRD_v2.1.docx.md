  
**PRODUCT REQUIREMENTS DOCUMENT**

**JcampFX**

Regime-Adaptive Multi-Strategy Portfolio Engine

Dynamic Composite Regime Detection (DCRD) | Range Bar Intelligence

*Laptop-First | $500 Start | 5+1 Pair Universe | Modular Brain Architecture*

 **v2.1 — Analyst-Reviewed Revision** 

| Version | 2.1 (Analyst Revised) |
| ----: | :---- |
| **Date** | February 17, 2026 |
| **Author** | Jcamp |
| **Reviewed By** | Forex/EA Analyst |
| **Broker** | FP Markets (ECN) |
| **Platform** | MetaTrader 5 |
| **Start Capital** | $500 USD |

# **Revision Log: v2.0 → v2.1**

The following changes were made based on a professional forex/EA engineering review of v2.0:

| \# | Area | v2.0 Issue | v2.1 Resolution |
| :---- | :---- | :---- | :---- |
| **R1** | Chandelier SL | Fixed 0.5R by tick — eaten by spread | Dynamic: max(0.5R, ATR14) with 15-pip floor majors / 25-pip JPY |
| **R2** | Position Limits | Max 3 at any equity — impossible lots at $500 | Max 2 until equity \> $1,000; skip trade if risk \< 0.8% |
| **R3** | Walk-Forward Data | 6 months / 1 cycle — coin flip | 2+ years tick data; minimum 4 walk-forward cycles |
| **R4** | News Source | Forex Factory API (doesn’t exist) | MQL5 MqlCalendarValue native functions piped via ZMQ |
| **R5** | Strategy Cooldown | 5 losses in 2 calendar days | 5 consecutive losses in last 10 trades (rolling window) |
| **R6** | Weekend Protection | Conditional 80/20 split | Close 100% of all positions 20 min before market close |
| **R7** | Correlation Mgmt | None — 3 USD-correlated trades possible | Max 2 trades sharing same base/quote currency |
| **R8** | Slippage Modeling | Not in backtester | 1.0 pip default slippage on every entry/exit in backtester |
| **R9** | Exit System Timing | Introduced in Phase 4 | Moved to Phase 2 so backtests include full exit logic |
| **R10** | Performance Cycle | 5-calendar-day rolling window | Last-10-trade rolling window per strategy (consistent with cooldown) |
| **R11** | Partial Exit Split | Fixed 70% close at 1.5R | Regime-aware: 60/70/75/80% based on CompositeScore at entry |

# **Table of Contents**

*Update page numbers in Word: Right-click TOC → Update Field.*

1\. Executive Summary

2\. System Architecture & Modular Brain

3\. DCRD – Dynamic Composite Regime Detection

4\. News & Events Awareness Layer

5\. Exit Management System

6\. Dynamic Risk Sizing (1–3%)

7\. Phase 1 – Range Bar Engine & Visualization

8\. Phase 2 – DCRD Brain \+ Strategies \+ Exit System

9\. Phase 3 – Web Backtesting (The Cinema)

10\. Phase 4 – Local Bridge (ZMQ Integration)

11\. Phase 5 – Deployment (VPS & Android)

12\. Risk Management Framework v2.1

13\. Master Validation Checklist

# **1\. Executive Summary**

## **1.1 Product Vision**

JcampFX is a Regime-Adaptive Multi-Strategy Portfolio Engine. It replaces time-based candlestick analysis with Range Bars for noise-free price action, and replaces binary trend/range toggles with the Dynamic Composite Regime Detection (DCRD) — a multi-layer scoring engine producing a continuous 0–100 confidence score across 4H structural, 1H dynamic, and Range Bar intelligence layers.

The modular Brain architecture supports pluggable strategy modules with standardized interfaces, enabling future logic additions and ML-driven dynamic learning without architectural changes.

## **1.2 Key Constraints**

| Constraint | Detail |
| :---- | :---- |
| **Starting Capital** | $500 USD on FP Markets ECN MT5 account |
| **Pair Universe** | EURUSD, GBPUSD, USDJPY, AUDJPY, USDCHF \+ CSM 9-pair grid (Gold unlocks at $2,000) |
| **Infrastructure** | Laptop as Lab (no VPS until Phase 5\) |
| **Data Requirement** | 2+ years tick data for Range Bars \+ 4H/1H candles for DCRD layers |
| **Commission Model** | FP Markets: $7 per standard lot round-trip |
| **Slippage Model** | 1.0 pip default applied to all entries/exits in backtesting |
| **Risk Per Trade** | Dynamic 1–3% based on DCRD confidence \+ last-10-trade rolling performance |
| **Daily Loss Cap** | Maximum 2R total loss per day (hard stop) |
| **Max Concurrent** | 2 positions (until equity \> $1,000, then 3\) |
| **Correlation Limit** | Max 2 trades sharing the same base or quote currency |

## **1.3 Development Timeline**

| Phase | Deliverable | Duration | Gate |
| :---- | :---- | :---- | :---- |
| **Phase 1** | Range Bar Engine \+ Web Chart \+ M15 Overlay | 2 weeks | Visual validation |
| **Phase 2** | DCRD Brain \+ 3 Strategies \+ Exit System \+ News | 4 weeks | Unit tests \+ regime accuracy |
| **Phase 3** | Web Backtester with 2yr data \+ Walk-Forward (4 cycles) | 3 weeks | Profitable after slippage+commission |
| **Phase 4** | ZMQ Bridge \+ Demo Trading \+ Risk Controls | 2 weeks | 1-week demo match |
| **Phase 5** | VPS Deployment \+ Android \+ Signal Service | 1 week | Live execution |

**⚠ REVISED:** *Phase 2 now includes Exit System (was Phase 4). Phase 3 requires 2+ years data and 4 walk-forward cycles (was 6 months / 1 cycle).*

# **2\. System Architecture & Modular Brain**

## **2.1 Laptop Lab Mode (Phases 1–4)**

| Component | Technology | Role | Port |
| :---- | :---- | :---- | :---- |
| **Data Feed** | MT5 Terminal | Tick \+ OHLC \+ Calendar data | N/A |
| **Range Engine** | Python 3.11+ | Tick → Range Bar conversion | N/A |
| **DCRD Engine** | Python | 4H/1H/RB regime scoring (0–100) | N/A |
| **News Layer** | MQL5 Calendar → ZMQ | Native MT5 economic event gating | 5557 |
| **Brain Core** | Python (Modular) | Strategy orchestration \+ correlation filter | N/A |
| **Exit Manager** | Python | Partial exit \+ Dynamic Chandelier SL | N/A |
| **Web Chart** | Plotly / Dash | Range Bars \+ M15 overlay | 8050 |
| **ZMQ Bridge** | pyzmq / MQL5 | Signal transmission | 5555/5556 |
| **Backtester** | backtesting.py | Simulation with slippage \+ commission | N/A |

## **2.2 Modular Brain Architecture**

The Brain is a plugin-based orchestrator. Each strategy is an independent module that registers with the Brain Core, receives regime scores and market data, and returns standardized signal objects.

**Standard Module Interface:**

* analyze(range\_bars, regime\_score, news\_state) → Signal | None

* retrain(performance\_data) → void (future ML hook)

* get\_status() → {active, cooldown\_until, last10\_R, trade\_count}

**Design Principles:**

* New strategies added by dropping a module into /strategies/ — auto-registered without Brain Core changes

* Strategy Registry tracks: allowed regime ranges, active/paused state, rolling performance

* Correlation Filter runs AFTER strategy signals, BEFORE ZMQ dispatch (see Section 12\)

* Performance Tracker feeds rolling last-10-trade R-equity to each module for self-assessment and dynamic risk

**Future Extensibility:**

* Additional strategy modules (SessionBreak, NewsSpike, VolatilityFade)

* Hurst exponent \+ volatility percentile layers in DCRD

* Regime classifier trained on historical trade outcome data (supervised learning)

* Strategy auto-enable/disable based on live performance gradient

## **2.3 Data Flow**

MT5 (Tick \+ 4H/1H \+ Calendar) → Range Engine \+ DCRD Engine (parallel) → News Layer (event gate) → Brain Core (routes to active strategies by CompositeScore) → Correlation Filter (currency exposure check) → Exit Manager (Chandelier \+ partial logic) → ZMQ Bridge → MT5 Hand EA

**⚠ REVISED:** *Correlation Filter added between Brain Core and Exit Manager. News data sourced from MQL5 native calendar via ZMQ port 5557\.*

# **3\. DCRD – Dynamic Composite Regime Detection**

The DCRD produces a Composite Score (0–100) that determines which strategies are active and at what confidence level. No binary triggers — only score zones.

## **3.1 Scoring Formula**

**CompositeScore \= StructuralScore (0–100) \+ ModifierScore (−15 to \+15) \+ RangeBarScore (0–20)**

*Clamped to 0–100*

## **3.2 Layer 1 — 4H Structural Regime Score (0–100)**

Five components, each 0–20 points:

| Component | Max | 20 Points | 10 Points | 0 Points |
| :---- | :---- | :---- | :---- | :---- |
| **ADX Strength** | 20 | ADX \> 25 \+ rising slope | ADX 20–25 | ADX \< 18 |
| **Market Structure** | 20 | ≥3 confirmed HH/HL or LL/LH | Mixed structure | Repeated failure |
| **ATR Expansion** | 20 | ATR\_curr / ATR\_20avg ≥ 1.2 | Ratio 0.9–1.2 | Ratio \< 0.8 |
| **CSM Alignment** | 20 | Base/quote ≥70% across grid | Moderate alignment | Divergent |
| **Trend Persistence** | 20 | ≥70% candles close vs EMA200 | Mixed closure | EMA whipsaw |

## **3.3 Layer 2 — 1H Dynamic Modifier (−15 to \+15)**

| Sub-Component | \+5 | −5 |
| :---- | :---- | :---- |
| **BB Width** | Expanding rapidly | In lowest 20th percentile |
| **ADX Acceleration** | Slope rising strongly | Slope collapsing |
| **CSM Acceleration** | Differential widening | Currency rotation increasing |

## **3.4 Layer 3 — Range Bar Intelligence (0–20)**

| Sub-Component | Max | Scoring |
| :---- | :---- | :---- |
| **RB Speed Score** | 10 | Bars/60min: High \= 10, Normal \= 5, Slow \= 0 |
| **RB Structure Quality** | 10 | Directional bars \+ pullback: Strong \= 10, Mixed \= 5, Alternating \= 0 |

*Recommended Range Sizes: Majors \= 10–15 pips, JPY pairs \= 15–20 pips.*

## **3.5 Regime Mapping**

| Composite Score | Regime | Strategy | Risk Multiplier |
| :---- | :---- | :---- | :---- |
| **70–100** | Trending | TrendRider | 0.8x–1.0x |
| **30–70** | Transitional | BreakoutRider | 0.6x |
| **0–30** | Range | RangeRider | 0.7x |

*R:R is not fixed — final outcomes are path-dependent based on regime-aware partial exit % and Dynamic Chandelier SL on the runner. See Section 5 (Exit Management System) for full exit logic and expected R-multiples by scenario.*

## **3.6 Anti-Flipping Filter**

Regime change ONLY if: Score crosses threshold by ≥15 points AND new regime persists for ≥2 consecutive 4H closes.

## **3.7 DCRD Validation**

| ID | Validation Criteria | Priority | Status |
| :---- | :---- | :---: | :---: |
| **VD.1** | 4H Structural Score 0–100 with all 5 components contributing | **CRITICAL** | ☐ Pending |
| **VD.2** | 1H Modifier stays −15 to \+15, never overrides structural classification | **MUST PASS** | ☐ Pending |
| **VD.3** | Range Bar Intelligence 0–20 independent of structural layer | **MUST PASS** | ☐ Pending |
| **VD.4** | Composite correctly maps: \>70 Trending, 30–70 Transitional, \<30 Range | **CRITICAL** | ☐ Pending |
| **VD.5** | Anti-flipping: ≥15pt cross \+ 2x 4H persistence required for regime change | **CRITICAL** | ☐ Pending |
| **VD.6** | 50 historical sequences classified \>85% accuracy vs manual ground truth | **GATE** | ☐ Pending |
| **VD.7** | CSM pulls from all 9 monitored pairs \+ XAUUSD when unlocked | **MUST PASS** | ☐ Pending |
| **VD.8** | Risk Multiplier applied correctly per regime zone: 0.8x–1.0x Trending, 0.6x Transitional, 0.7x Range (verify 20 samples) | **MUST PASS** | ☐ Pending |

# **4\. News & Events Awareness Layer**

## **4.1 Data Source**

**⚠ REVISED:** *Replaced Forex Factory API (does not exist) with MQL5 native calendar functions.*

* Primary: MQL5 MqlCalendarValue / CalendarValueHistory() functions inside the Hand EA

* Calendar data piped to Python Brain via ZMQ (port 5557\) at startup \+ hourly refresh

* Fallback: MQL5 CalendarCountryById() for currency-specific event filtering

* Data format: {event\_id, name, currency, impact, time\_utc, actual, forecast, previous}

## **4.2 Event Classification & Trade Windows**

| Impact | Examples | Block Window | Action on Open Trades |
| :---- | :---- | :---- | :---- |
| **High (Red)** | NFP, FOMC, CPI, ECB Rate | −30 to \+15 min | Tighten SL to 0.5R |
| **Medium (Orange)** | PMI, Retail Sales, GDP | −15 to \+10 min | No change to open trades |
| **Low (Yellow)** | Housing, Consumer Conf. | No block | Dashboard flag only |

## **4.3 Currency-Specific Gating**

Events only block pairs containing the affected currency. USD NFP blocks EURUSD, GBPUSD, USDJPY, USDCHF, XAUUSD. Does NOT block AUDJPY.

## **4.4 Post-Event Cooling**

15-minute cooling period after high-impact events: only signals with CompositeScore \> 80 are allowed through. This prevents whipsaw entries on the initial spike-and-reversal pattern.

## **4.5 News Validation**

| ID | Validation Criteria | Priority | Status |
| :---- | :---- | :---: | :---: |
| **VN.1** | MQL5 CalendarValueHistory() returns events for current week in correct server timezone | **MUST PASS** | ☐ Pending |
| **VN.2** | Calendar data received by Python via ZMQ port 5557 within 2 seconds of request | **MUST PASS** | ☐ Pending |
| **VN.3** | High-impact events block affected pairs −30 to \+15 min (verify on 5 historical events) | **CRITICAL** | ☐ Pending |
| **VN.4** | Non-affected pairs remain tradeable during events (currency-specific gating) | **MUST PASS** | ☐ Pending |
| **VN.5** | Blocked signals logged with event name, not silently dropped | **MUST PASS** | ☐ Pending |
| **VN.6** | Post-event cooling: 15 min allows only CompositeScore \> 80 signals | **RECOMMENDED** | ☐ Pending |
| **VN.7** | Dashboard shows upcoming events with countdown timers per currency | **RECOMMENDED** | ☐ Pending |

# **5\. Exit Management System**

**⚠ REVISED:** *Moved from Phase 4 to a core system component. Now built in Phase 2 and included in all backtests (Phase 3).*

The Exit Manager handles all post-entry logic: partial profit-taking and dynamic trailing stops designed to survive real-world spread conditions.

## **5.1 Two-Stage Exit Flow**

**Stage 1: Regime-Aware Partial Exit at 1.5R**

**⚠ REVISED:** *Partial close percentage is now DCRD-driven. Higher conviction \= keep more runner. Lower conviction \= lock in more profit.*

When price reaches 1.5R, close a regime-dependent percentage of the position:

| CompositeScore | Regime | Close % | Runner % | Locked Profit | Rationale |
| :---- | :---- | :---- | :---- | :---- | :---- |
| **\> 85** | Deep Trending | 60% | 40% | \+0.90R | High conviction — maximize runner potential |
| **70–85** | Trending | 70% | 30% | \+1.05R | Standard conviction (default) |
| **30–70** | Transitional | 75% | 25% | \+1.125R | Moderate conviction — secure more profit |
| **\< 30** | Range | 80% | 20% | \+1.20R | Mean reversion — minimal runner expectation |

**Stage 2: Dynamic Chandelier SL on Remaining Runner**

**⚠ REVISED:** *Chandelier distance is now dynamic to survive spread spikes. Was fixed 0.5R in v2.0.*

* After partial exit, replace fixed SL with a Chandelier trailing stop

* **Chandelier distance \= max(0.5R, ATR(14) of Range Bar timeframe)**

* **Minimum floor:** 15 pips on majors (EURUSD, GBPUSD, USDCHF) | 25 pips on JPY pairs (USDJPY, AUDJPY)

* Trailing: moves by tick in the profitable direction only (never widens)

* Remaining runner portion runs until Chandelier SL is hit

## **5.2 Why Dynamic Chandelier**

A fixed 0.5R stop on a $500 account (0.01 lots) means approximately 25 pips. FP Markets ECN spread during London close or low-liquidity windows can widen to 1.5–2.0 pips on majors and 3–4 pips on JPY crosses. Combined with slippage, a tight fixed trail gets stopped prematurely on spread spikes, not actual reversals. The ATR-adaptive floor ensures the trail respects current volatility conditions.

## **5.3 Exit Math by Regime**

Showing the two extremes (Deep Trending 60/40 split vs Range 80/20 split) plus full loss:

| Scenario | Deep Trend (60/40) | Transitional (75/25) | Range (80/20) | Full SL |
| :---- | :---- | :---- | :---- | :---- |
| **1.5R, reverses** | \+0.90 \+ 0.40 \= \+1.30R | \+1.125 \+ 0.25 \= \+1.375R | \+1.20 \+ 0.20 \= \+1.40R | N/A |
| **Runs to 3R** | \+0.90 \+ 1.0 \= \+1.90R | \+1.125 \+ 0.63 \= \+1.75R | \+1.20 \+ 0.50 \= \+1.70R | N/A |
| **Runs to 5R** | \+0.90 \+ 1.8 \= \+2.70R | \+1.125 \+ 1.13 \= \+2.25R | \+1.20 \+ 0.90 \= \+2.10R | N/A |
| **Never hits 1.5R** | N/A | N/A | N/A | −1.0R |

*Deep Trending keeps the largest runner (40%), so it benefits most from extended moves. Range keeps only 20% but locks in more upfront. This aligns the exit mechanic with regime conviction.*

## **5.4 Exit Validation**

| ID | Validation Criteria | Priority | Status |
| :---- | :---- | :---: | :---: |
| **VE.1** | Partial exit fires at exactly 1.5R on \> 95% of qualifying trades | **CRITICAL** | ☐ Pending |
| **VE.2** | Regime-aware split: 60% (CS\>85), 70% (CS 70–85), 75% (CS 30–70), 80% (CS\<30) — verify all 4 tiers | **CRITICAL** | ☐ Pending |
| **VE.3** | Chandelier SL \= max(0.5R, ATR14) with floor ≥15 pips majors / ≥25 pips JPY | **CRITICAL** | ☐ Pending |
| **VE.4** | Chandelier moves by tick in profitable direction only (never widens) | **MUST PASS** | ☐ Pending |
| **VE.5** | Runner portion stays open until Chandelier hit (no premature close) | **MUST PASS** | ☐ Pending |
| **VE.6** | Full losers show exactly −1.0R (no partial exit attempted) | **MUST PASS** | ☐ Pending |
| **VE.7** | Regime split uses the CompositeScore at time of entry, not at time of 1.5R hit | **CRITICAL** | ☐ Pending |
| **VE.8** | Backtest: 2-pip spread spike — Chandelier survives vs fixed 0.5R stopped (comparative) | **RECOMMENDED** | ☐ Pending |

# **6\. Dynamic Risk Sizing (1–3%)**

## **6.1 Formula**

**Risk% \= BaseRisk × ConfidenceMultiplier × PerformanceMultiplier**

**Clamped: min 1.0%, max 3.0%. If calculated risk \< 0.8% → SKIP the trade.**

**⚠ REVISED:** *Added 0.8% minimum threshold. Below this, lot size (0.01 min) cannot express the risk accurately on a $500 account.*

## **6.2 Factor 1: DCRD Confidence**

| Condition | Multiplier | Rationale |
| :---- | :---- | :---- |
| **Score \> 85 (deep regime)** | 1.2x | Strong conviction, clear regime |
| **Score 70–85 or \< 15** | 1.0x | Normal confidence |
| **Score 45–55 (mid-transitional)** | 0.8x | Uncertain zone, reduce size |
| **Near boundary (±5 pts of 30 or 70\)** | 0.7x | Regime could flip — minimum exposure |

## **6.3 Factor 2: Last-10-Trade Rolling Performance**

**⚠ REVISED:** *Changed from 5-calendar-day cycle to last-10-trade rolling window. Consistent with cooldown logic and adapts to each strategy’s trade frequency.*

Each strategy tracks the cumulative R-result of its own last 10 completed trades:

| Last 10 Trades R | Multiplier | Rationale |
| :---- | :---- | :---- |
| **≥ \+5R** | 1.3x | Strong edge confirmed — capitalize |
| **\+2R to \+5R** | 1.1x | Positive momentum |
| **0 to \+2R** | 1.0x | Base risk — neutral |
| **−2R to 0** | 0.8x | Slight drawdown — reduce exposure |
| **\< −2R** | 0.6x | Poor streak — protect capital |

Each strategy tracks independently. R thresholds scaled to a 10-trade window (≈2x the old 5-day values) to maintain equivalent sensitivity.

## **6.4 Lot Size Floor Rule**

MT5 minimum lot \= 0.01. On a $500 account at 1% risk, that’s $5 risk per trade. If dynamic multipliers reduce risk below 0.8% ($4), the calculated SL distance requires less than 0.01 lots, making accurate position sizing impossible.

**Rule: if Risk% \< 0.8% after multipliers → skip the trade entirely. Do not round up to 0.01.**

## **6.5 Risk Validation**

| ID | Validation Criteria | Priority | Status |
| :---- | :---- | :---: | :---: |
| **VR.1** | Risk% always 1.0%–3.0% (or trade skipped if \< 0.8%) | **CRITICAL** | ☐ Pending |
| **VR.2** | Confidence multiplier reflects CompositeScore distance from boundaries | **MUST PASS** | ☐ Pending |
| **VR.3** | Last-10-trade multiplier recalculates after every completed trade per strategy | **MUST PASS** | ☐ Pending |
| **VR.4** | Strategies have independent performance tracking | **CRITICAL** | ☐ Pending |
| **VR.5** | Near-boundary trades (±5 pts of 30/70) get 0.7x | **MUST PASS** | ☐ Pending |
| **VR.6** | Trades with \< 0.8% risk are skipped and logged as RISK\_TOO\_LOW | **CRITICAL** | ☐ Pending |
| **VR.7** | Backtest: dynamic risk produces higher Sharpe than fixed 1% over 2 years | **RECOMMENDED** | ☐ Pending |

# **PHASE 1**

## **Range Bar Engine & Visualization**

*Convert raw MT5 tick data into Range Bars, visualize in browser with optional M15 comparison.*

### **7.1 Data Ingestion**

1. Connect Python to FP Markets MT5 via MetaTrader5 package

2. Download 2+ years of tick data for: EURUSD, GBPUSD, USDJPY, AUDJPY, USDCHF

3. Download M15 OHLC candles for the same pairs and period (comparison overlay)

4. Store in Parquet format; implement incremental download

**⚠ REVISED:** *Increased from 6 months to 2+ years. Source Dukascopy free tick data if FP Markets history is insufficient.*

### **7.2 Range Bar Converter**

1. Configurable pip size: 10–15 pips majors, 15–20 JPY pairs

2. Pure price-driven: new bar only on X-pip move from open

3. Store: Open, High, Low, Close, Volume (ticks), Start Time, End Time

4. Handle weekend gaps without false bars

### **7.3 Web Chart**

1. Plotly OHLC rendering in browser with green/red coloring

2. Volume bars (tick count) below chart

3. Pair selector dropdown (5 symbols)

4. Toggle-able M15 comparison overlay, time-aligned with Range Bars

## **7.4 Validation**

| ID | Validation Criteria | Priority | Status |
| :---- | :---- | :---: | :---: |
| **V1.1** | Python retrieves 2+ years tick data \+ M15 OHLC for all 5 pairs | **MUST PASS** | ☐ Pending |
| **V1.2** | Tick data Parquet has correct bid/ask/timestamp columns | **MUST PASS** | ☐ Pending |
| **V1.3** | Range Bars: High–Low \= exactly X pips (within spread tolerance) | **CRITICAL** | ☐ Pending |
| **V1.4** | Bars span different durations (purely price-driven, not time) | **CRITICAL** | ☐ Pending |
| **V1.5** | Browser displays chart visually different from MT5 time chart | **MUST PASS** | ☐ Pending |
| **V1.6** | Weekend gaps handled – no phantom bars | **MUST PASS** | ☐ Pending |
| **V1.7** | M15 overlay toggles and time-aligns correctly | **RECOMMENDED** | ☐ Pending |
| **V1.8** | Unit test: 100 ticks → deterministic N Range Bars | **CRITICAL** | ☐ Pending |

# **PHASE 2**

## **DCRD Brain \+ Strategies \+ Exit System**

*Build the full regime engine, all three strategy modules, exit management, and news integration.*

**⚠ REVISED:** *Exit Management System is now built here (was Phase 4 in v2.0). This ensures Phase 3 backtests include the real exit logic.*

## **8.1 DCRD Implementation**

Implement the full 3-layer DCRD as specified in Section 3\.

## **8.2 Strategy Specifications**

**Strategy A – TrendRider (CompositeScore 70–100)**

* Entry: 2nd Range Bar pull-back in trend direction

* Confirmation: ADX \> 25 \+ 3-bar staircase

* Exit: Regime-aware partial at 1.5R (60–80% per DCRD) \+ Dynamic Chandelier on runner (Section 5\)

**Strategy B – BreakoutRider (CompositeScore 30–70)**

* Entry: RB close outside Keltner during BB compression breakout

* Confirmation: RB speed increasing \+ micro-structure break

* Exit: Regime-aware partial at 1.5R (60–80% per DCRD) \+ Dynamic Chandelier on runner

**Strategy C – RangeRider (CompositeScore 0–30)**

* Entry: Fade at consolidation boundaries

* Confirmation: ≥8 RBs in block \+ width \> 2x RB size

* Exit: Regime-aware partial at 1.5R (60–80% per DCRD) \+ Dynamic Chandelier on runner

## **8.3 Correlation Filter**

**⚠ REVISED:** *New in v2.1. Prevents hidden directional overload from correlated pairs.*

**Rule: Maximum 2 open trades sharing the same base or quote currency.**

Example: If long EURUSD and long GBPUSD are both open (both short USD), no additional USD-pair trade is allowed regardless of strategy signal quality. AUDJPY remains eligible because it shares neither EUR, GBP, nor USD.

* Implemented as a pre-dispatch filter in Brain Core, after strategy signal, before ZMQ send

* Blocked signals logged as CORRELATION\_BLOCKED with currency exposure details

* Dashboard displays current currency exposure grid in real-time

### **8.4 Gold Gate**

if Account\_Equity \< 2000: Allowed\_Pairs.remove("XAUUSD")

## **8.5 Performance Tracker**

* Track TrendRider\_R, BreakoutRider\_R, RangeRider\_R independently

* If strategy R \< 15-trade rolling average → temporarily disable

* Re-enable after 3 positive paper trades

## **8.6 Validation**

| ID | Validation Criteria | Priority | Status |
| :---- | :---- | :---: | :---: |
| **V2.1** | DCRD CompositeScore computed correctly (all 3 layers; output 0–100) | **CRITICAL** | ☐ Pending |
| **V2.2** | TrendRider triggers ONLY when CompositeScore ≥70 | **MUST PASS** | ☐ Pending |
| **V2.3** | BreakoutRider triggers ONLY in 30–70 with BB compression | **MUST PASS** | ☐ Pending |
| **V2.4** | RangeRider: min 8 RBs \+ width \> 2x RB size | **MUST PASS** | ☐ Pending |
| **V2.5** | Gold Gate blocks XAUUSD \< $2,000, allows ≥ $2,000 | **CRITICAL** | ☐ Pending |
| **V2.6** | Max concurrent: 2 positions (until equity \> $1,000, then 3\) | **CRITICAL** | ☐ Pending |
| **V2.7** | Correlation filter: max 2 trades with same base/quote currency enforced | **CRITICAL** | ☐ Pending |
| **V2.8** | Standardized signal: timestamp, pair, direction, entry, SL, TP, strategy, confidence, risk% | **MUST PASS** | ☐ Pending |
| **V2.9** | News layer blocks signals during high-impact windows (MQL5 calendar source) | **CRITICAL** | ☐ Pending |
| **V2.10** | Exit Manager: regime-aware partial (60/70/75/80%) at 1.5R \+ Dynamic Chandelier on runner | **CRITICAL** | ☐ Pending |
| **V2.11** | New strategy module auto-registers from /strategies/ without Brain Core changes | **MUST PASS** | ☐ Pending |
| **V2.12** | Performance tracker disables/re-enables strategies correctly | **MUST PASS** | ☐ Pending |
| **V2.13** | Anti-flipping filter prevents regime oscillation on volatile data | **CRITICAL** | ☐ Pending |
| **V2.14** | Unit tests pass for all 3 strategies independently | **GATE** | ☐ Pending |

# **PHASE 3**

## **Web Backtesting – The "Cinema"**

*Validate on 2+ years historical data with full slippage, commission, and spread modeling. Minimum 4 walk-forward cycles.*

## **9.1 Simulation Engine**

1. backtesting.py with custom Range Bar DataFrame \+ DCRD score timeline

2. Replay 4H/1H alongside Range Bars for historical DCRD computation

3. Simulate all 3 strategies across 2+ years per pair (minimum)

4. Commission: $7/lot round-trip

5. Slippage: 1.0 pip default on every entry AND exit

6. Spread: historical tick-based spread modeling

7. Historical news events replayed (trade blocks during past high-impact events)

8. Walk-forward: 4-month train / 2-month test, minimum 4 complete cycles

**⚠ REVISED:** *Added 1.0 pip slippage modeling. Increased to 2+ years data with 4 walk-forward cycles (was 6 months / 1 cycle).*

## **9.2 Visual Verification**

1. Equity curve with drawdown overlay

2. DCRD CompositeScore timeline with color-coded regime bands

3. Trade markers: entry, exit, partial exit at 1.5R, Chandelier trail path

4. Strategy attribution coloring

5. M15 comparison panel (toggle)

6. Trade log: Date, Pair, Strategy, Regime Score, Entry, Exit, Slippage, PnL, R-Multiple

## **9.3 Hurdle Checks**

* **Net Profit:** Positive after commissions \+ 1.0 pip slippage \+ historical spread

* **Partial Exit:** Regime-aware split (60/70/75/80%) at exactly 1.5R on \> 95% of qualifying trades

* **Chandelier:** Dynamic max(0.5R, ATR14) with pip floors, trailing by tick

* **Daily 2R Cap:** No day exceeds 2R total loss

* **Strategy Cooldown:** 5 consecutive losses in last 10 trades → 24hr pause

* **Correlation:** Never \> 2 trades sharing same base/quote currency

* **Position Limits:** Max 2 concurrent (or 3 if equity \> $1,000) at any backtest point

* **Risk Floor:** No trades taken with \< 0.8% risk (logged as RISK\_TOO\_LOW)

* **News Blocks:** No entries during historical high-impact windows

## **9.4 Validation**

| ID | Validation Criteria | Priority | Status |
| :---- | :---- | :---: | :---: |
| **V3.1** | Equity net positive after $7/lot \+ 1.0 pip slippage \+ spread over 2+ years | **GATE** | ☐ Pending |
| **V3.2** | Max drawdown never exceeds 20% of peak equity | **CRITICAL** | ☐ Pending |
| **V3.3** | 4 walk-forward cycles: each test period within 30% of train period performance | **CRITICAL** | ☐ Pending |
| **V3.4** | Trade markers match signal log (spot-check 20 trades) | **MUST PASS** | ☐ Pending |
| **V3.5** | Regime-aware partial (60/70/75/80%) at 1.5R fires correctly per CompositeScore at entry | **CRITICAL** | ☐ Pending |
| **V3.6** | Dynamic Chandelier trails correctly with ATR adaptation \+ pip floors | **CRITICAL** | ☐ Pending |
| **V3.7** | No day exceeds 2R total loss | **CRITICAL** | ☐ Pending |
| **V3.8** | Strategy cooldown: 5 losses in last 10 trades → 24hr pause enforced | **MUST PASS** | ☐ Pending |
| **V3.9** | Correlation filter: never \> 2 trades same base/quote currency | **MUST PASS** | ☐ Pending |
| **V3.10** | Position cap: 2 concurrent (3 if equity \> $1k) enforced throughout | **MUST PASS** | ☐ Pending |
| **V3.11** | No entries during historical news windows | **MUST PASS** | ☐ Pending |
| **V3.12** | Each strategy individually profitable | **CRITICAL** | ☐ Pending |
| **V3.13** | DCRD regime timeline visible and color-coded | **MUST PASS** | ☐ Pending |
| **V3.14** | Slippage impact report: show PnL with vs without 1-pip slippage | **RECOMMENDED** | ☐ Pending |
| **V3.15** | Sharpe \> 1.0 combined portfolio | **RECOMMENDED** | ☐ Pending |
| **V3.16** | Profit Factor \> 1.5 after all costs | **RECOMMENDED** | ☐ Pending |

## **9.5 Milestone**

**Browser shows upward equity curve over 2+ years with DCRD regime bands, slippage-adjusted results, and 4 walk-forward cycles all positive. This logic has been stress-tested and deserves live capital.**

# **PHASE 4**

## **Local Bridge – ZMQ Integration**

*Connect Brain to Hand EA on laptop. Test all risk controls on demo for 1 week.*

## **10.1 Hand EA (MQL5)**

1. Listen ZMQ tcp://localhost:5555 for trade commands

2. Accept: {Symbol, Action, Lot, SL, TP\_1.5R, ChandelierConfig:{atr\_period:14, min\_pips:15/25}}

3. Handle regime-aware partial close: 60–80% at 1.5R (percentage from signal), activate Dynamic Chandelier on runner

4. Chandelier: max(0.5R, ATR14) with pip floor, trail by tick

5. CLOSE\_ALL within 500ms

6. Report: order ID, fill, slippage, commission, partial details

7. Pipe MQL5 CalendarValueHistory() data to Python via ZMQ port 5557

## **10.2 Daily Protection: 2R Cap**

* **if Daily\_R\_Total ≤ −2.0R → CLOSE\_ALL \+ PAUSE until 00:00 next day**

* R per trade \= risk amount of that individual trade

* Dashboard: real-time daily R meter with −2R threshold

## **10.3 Strategy Cooldown**

**⚠ REVISED:** *Changed from calendar-based (2 days) to trade-count rolling window (last 10 trades).*

* **Rule:** 5 consecutive losses in the strategy’s last 10 trades → pause that strategy for 24 hours

* Other strategies remain active

* Losses from weekend protection closures excluded from count

* After 24hr hold, counter resets and strategy re-enables

*This adapts to trade frequency: high-frequency strategies (BreakoutRider during volatile sessions) and low-frequency strategies (TrendRider in clean trends) are treated fairly regardless of how many calendar days their trades span.*

## **10.4 Weekend Protection**

**⚠ REVISED:** *Simplified to 100% close. At $500 equity, gap risk on 20% runner is not worth the potential upside.*

**Rule: Close 100% of all open positions 20 minutes before Friday market close. No exceptions.**

Rationale: On a $500–$2,000 account trading 0.01 lots, a weekend gap against a 20% runner yields $1–3 upside vs $5–10 downside. The asymmetry doesn’t justify holding. This rule can be revisited when equity exceeds $5,000.

## **10.5 Validation**

| ID | Validation Criteria | Priority | Status |
| :---- | :---- | :---: | :---: |
| **V4.1** | ZMQ connection Python ↔ MQL5 on localhost within 2 seconds | **MUST PASS** | ☐ Pending |
| **V4.2** | Trade commands appear as executed orders in MT5 demo | **CRITICAL** | ☐ Pending |
| **V4.3** | Regime-aware partial (60/70/75/80%) at 1.5R executes correctly per CompositeScore | **CRITICAL** | ☐ Pending |
| **V4.4** | Dynamic Chandelier: max(0.5R, ATR14) \+ pip floor, trails by tick on 30% | **CRITICAL** | ☐ Pending |
| **V4.5** | CLOSE\_ALL within 500ms | **MUST PASS** | ☐ Pending |
| **V4.6** | 2R daily cap triggers correctly at −2R cumulative | **CRITICAL** | ☐ Pending |
| **V4.7** | Cooldown: 5 consecutive losses in last 10 trades pauses only that strategy | **MUST PASS** | ☐ Pending |
| **V4.8** | Weekend: 100% close of all positions 20 min before Friday close | **MUST PASS** | ☐ Pending |
| **V4.9** | Correlation filter: blocks 3rd trade on same currency in live demo | **MUST PASS** | ☐ Pending |
| **V4.10** | MQL5 calendar data arrives at Python via ZMQ 5557 correctly | **MUST PASS** | ☐ Pending |
| **V4.11** | 1-week demo: dashboard matches MT5 history \> 95% | **GATE** | ☐ Pending |
| **V4.12** | Recovers from MT5 disconnect without duplicate orders | **MUST PASS** | ☐ Pending |
| **V4.13** | Latency: signal-to-execution \< 100ms localhost | **RECOMMENDED** | ☐ Pending |

## **10.6 Milestone**

**1-week demo: Python dashboard and MT5 terminal match perfectly. Partial exits at 1.5R, Dynamic Chandelier, 2R cap, correlation filter, and strategy cooldowns all verified in live conditions.**

# **PHASE 5**

## **Deployment – VPS & Android**

*Production infrastructure with mobile monitoring and signal service.*

## **11.1 VPS Migration**

* Transfer Python \+ MT5 \+ DCRD config \+ news cache to NY4 VPS

* Parallel run: laptop \+ VPS 48 hours — identical signals required

* systemd services \+ auto-restart on crash

* Log rotation \+ daily performance email

## **11.2 Android Dashboard**

* Streamlit HTTPS (Let’s Encrypt)

* Display: positions, daily R-meter, equity curve, DCRD per pair, currency exposure grid, upcoming news

* Telegram bot: entries, partials, daily summary, 2R alerts, cooldown notices, correlation blocks

* Emergency kill switch from phone

## **11.3 Signal Service**

* Standardized signal format for subscribers

* 30-second execution-to-delivery delay

* Public performance dashboard with regime history

## **11.4 Validation**

| ID | Validation Criteria | Priority | Status |
| :---- | :---- | :---: | :---: |
| **V5.1** | VPS 48hr without crash or memory leak | **CRITICAL** | ☐ Pending |
| **V5.2** | Parallel: VPS \+ laptop identical signals 48hr | **GATE** | ☐ Pending |
| **V5.3** | Dashboard loads \< 3 sec with real-time DCRD \+ currency exposure | **MUST PASS** | ☐ Pending |
| **V5.4** | Telegram: all trade events \+ daily R \+ correlation blocks | **MUST PASS** | ☐ Pending |
| **V5.5** | Kill switch closes all positions \< 2 sec from phone | **CRITICAL** | ☐ Pending |
| **V5.6** | Auto-restart from VPS reboot | **MUST PASS** | ☐ Pending |
| **V5.7** | First live trade: correct dynamic risk \+ DCRD R:R | **GATE** | ☐ Pending |
| **V5.8** | MQL5 calendar auto-syncs on VPS (hourly refresh) | **MUST PASS** | ☐ Pending |

# **12\. Risk Management Framework v2.1**

| Risk Control | Rule | Enforcement |
| :---- | :---- | :---- |
| **Position Sizing** | Dynamic 1–3% (skip if \< 0.8%) | Python pre-signal calculation |
| **Max Concurrent** | 2 positions (3 if equity \> $1,000) | Brain Core blocks when limit hit |
| **Correlation Limit** | Max 2 trades same base/quote currency | Pre-dispatch filter in Brain |
| **Daily Loss Cap** | 2R total → CLOSE\_ALL \+ PAUSE until midnight | Cumulative R tracker; resets 00:00 |
| **Strategy Cooldown** | 5 consecutive losses in last 10 trades → 24hr hold | Per-strategy rolling window |
| **Max Daily Trades** | 5 new trades per day  | Counter resets 00:00 |
| **Gold Gate** | XAUUSD blocked until equity ≥ $2,000 | Hard-coded pair universe check |
| **Commission** | $7/lot in all calculations | Backtester \+ live PnL |
| **Slippage** | 1.0 pip modeled on all entries/exits | Backtester parameter |
| **Partial Exit** | Regime-aware: 60% (CS\>85), 70% (70–85), 75% (30–70), 80% (\<30) at 1.5R | Exit Manager \+ DCRD score at entry |
| **Chandelier SL** | max(0.5R, ATR14), floor 15/25 pips, trail by tick | Exit Manager \+ Hand EA |
| **Weekend** | 100% close 20 min before Friday close | Friday scheduler |
| **News Gating** | High: −30/+15 min | Medium: −15/+10 min | MQL5 Calendar → ZMQ gate |
| **Post-News Cool** | 15 min: only CompositeScore \> 80 | Brain Core filter |
| **Anti-Flip** | ≥15pt cross \+ 2x 4H persistence | DCRD stability filter |
| **Lot Size Floor** | 0.01 minimum; skip trade if risk \< 0.8% | Pre-signal validation |

# **13\. Master Validation Checklist**

Consolidated tracking. Phase cannot complete until all GATE and CRITICAL items pass.

| Section | Checks | GATE | CRITICAL |
| :---- | :---- | :---- | :---- |
| **DCRD (Sec 3\)** | 8 | 1 | 3 |
| **News Layer (Sec 4\)** | 7 | 0 | 1 |
| **Exit System (Sec 5\)** | 8 | 0 | 4 |
| **Dynamic Risk (Sec 6\)** | 7 | 0 | 3 |
| **Phase 1 (Sec 7\)** | 8 | 0 | 3 |
| **Phase 2 (Sec 8\)** | 14 | 1 | 7 |
| **Phase 3 (Sec 9\)** | 16 | 1 | 6 |
| **Phase 4 (Sec 10\)** | 13 | 1 | 4 |
| **Phase 5 (Sec 11\)** | 8 | 2 | 2 |
| **TOTAL** | 89 | 6 | 33 |

## **Priority Legend**

| Priority | Definition |
| :---- | :---- |
| **GATE** | Hard stop – Cannot proceed without passing |
| **CRITICAL** | Must pass before sign-off; requires root cause analysis |
| **MUST PASS** | Required; can resolve in parallel with next phase |
| **RECOMMENDED** | Best practice; defer if timeline is tight |

*End of Document*  
JcampFX PRD v2.1 — Analyst-Reviewed Revision

*"You are no longer running a trend EA. You are running a Regime-Adaptive Multi-Strategy Portfolio Engine."*