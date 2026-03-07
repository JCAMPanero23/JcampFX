# Phase 4 — ZMQ Bridge + Demo Trading

**Phase:** 4 (Demo Trading Integration)
**Status:** Ready to start (Phase 3 validation complete ✅)
**Gate:** V4.1 — 1-week demo trading matches backtest metrics

---

## Phase 3 Completion Summary ✅

**All Validation Gates Passed:**
- ✅ V3.1: Net profit positive: $182.74 (36.5% return over 2 years)
- ✅ V3.2: Max DD <20%: 17.4%
- ✅ V3.3: Walk-forward 4/4 cycles profitable
- ✅ V3.7: No day >2R loss (enforced via runner protection)
- ✅ V3.12: Each strategy profitable
- ✅ V3.15: Sharpe >1.0: 1.30

**Final Production Configuration:**
- **Pairs:** EURUSD, USDJPY, AUDJPY, USDCHF (4 pairs)
- **Range Bars:** 15 pips (EURUSD/USDCHF), 20 pips (USDJPY/AUDJPY)
- **Starting Equity:** $500
- **Base Risk:** 1.0% per trade
- **Max Concurrent:** 5 positions

**Key Features Validated:**
- Runner protection system (R >= -0.5 threshold)
- Price level cooldown (±20 pips, 4 hours)
- Trailing SL as primary exit mechanism (44.7% of exits, +$1,307 profit)
- Regime deterioration protection (CS drop >40 pts)
- Monte Carlo simulation: 100% profitable across 10,000 permutations

---

## Phase 4 Overview

**Goal:** Build real-time integration between MT5 EA and Python Brain via ZMQ, validate system on demo account

**Architecture:**
```
MT5 EA (MQL5)                    Python Brain (src/)
    |                                    |
    |--[ZMQ 5555: Signals]------------->|  BrainCore receives signals
    |<-[ZMQ 5556: Reports]--------------|  MT5 receives entry/exit commands
    |--[ZMQ 5557: News Events]--------->|  News gating via CalendarValueHistory()
    |                                    |
    [Tick Data] --> [Range Bar Builder] --> Cache to Parquet
                    [DCRD Engine]        --> Calculate CompositeScore
                    [Strategy Logic]     --> Generate signals
                    [Exit Manager]       --> Manage open trades
```

**Success Criteria:**
1. All 4 pairs streaming ticks → Range Bars built in real-time
2. DCRD scores calculated and logged
3. Signals generated and sent to MT5 EA
4. Trades executed on demo account (FP Markets)
5. Exit management working (partial exits, trailing SL, protection rules)
6. 1-week validation: metrics match backtest within tolerance

---

## Session 1: ZMQ Bridge Foundation 🎯

**Priority:** HIGH — Core infrastructure for all future work

### Task 1.1: MT5 EA ZMQ Setup

**Files to create/modify:**
- **NEW:** `MT5_EAs/Include/JcampStrategies/ZMQ_Bridge.mqh` (ZMQ socket wrapper)
- **MODIFY:** `MT5_EAs/Experts/JcampFX_Hand.mq5` (integrate ZMQ)

**Implementation:**
1. **ZMQ Socket Initialization** (OnInit):
   ```mql5
   // ZMQ sockets
   void* zmq_context;
   void* signal_socket;    // PUSH to 5555 (send tick data)
   void* command_socket;   // SUB from 5556 (receive signals)
   void* news_socket;      // PUSH to 5557 (send news events)

   int OnInit() {
       zmq_context = zmq.zmq_ctx_new();

       // Signal socket (tick data → Python)
       signal_socket = zmq.zmq_socket(zmq_context, ZMQ_PUSH);
       zmq.zmq_connect(signal_socket, "tcp://localhost:5555");

       // Command socket (signals ← Python)
       command_socket = zmq.zmq_socket(zmq_context, ZMQ_SUB);
       zmq.zmq_connect(command_socket, "tcp://localhost:5556");
       zmq.zmq_setsockopt(command_socket, ZMQ_SUBSCRIBE, "", 0);

       // News socket (news events → Python)
       news_socket = zmq.zmq_socket(zmq_context, ZMQ_PUSH);
       zmq.zmq_connect(news_socket, "tcp://localhost:5557");

       return INIT_SUCCEEDED;
   }
   ```

2. **Tick Data Broadcasting** (OnTick):
   ```mql5
   void OnTick() {
       for (int i = 0; i < ArraySize(PAIRS); i++) {
           string pair = PAIRS[i];
           MqlTick tick;
           if (SymbolInfoTick(pair, tick)) {
               string msg = StringFormat(
                   "{\"pair\":\"%s\",\"bid\":%.5f,\"ask\":%.5f,\"time\":%d}",
                   pair, tick.bid, tick.ask, (int)tick.time
               );
               zmq.zmq_send(signal_socket, msg, 0);
           }
       }
   }
   ```

3. **Signal Reception** (Timer callback):
   ```mql5
   void CheckForSignals() {
       string msg;
       if (zmq.zmq_recv(command_socket, msg, ZMQ_DONTWAIT) > 0) {
           // Parse JSON signal
           // Execute trade or modify SL/TP
       }
   }
   ```

4. **News Event Broadcasting** (Timer callback):
   ```mql5
   void BroadcastNewsEvents() {
       MqlCalendarValue events[];
       CalendarValueHistory(events, TimeCurrent() - 3600, TimeCurrent() + 86400);

       for (int i = 0; i < ArraySize(events); i++) {
           // Filter high-impact events
           // Send to Python via ZMQ 5557
       }
   }
   ```

**Testing:**
```bash
# Start Python listener first
python -m src.zmq_listener --test-mode

# Launch MT5 EA (should see tick data flowing)
```

---

### Task 1.2: Python Brain ZMQ Listener

**Files to create:**
- **NEW:** `src/zmq_listener.py` (main ZMQ listener)
- **NEW:** `src/zmq_handler.py` (message parsing + routing)

**Implementation:**
1. **ZMQ Socket Setup:**
   ```python
   import zmq

   context = zmq.Context()

   # Receive tick data from MT5
   signal_socket = context.socket(zmq.PULL)
   signal_socket.bind("tcp://localhost:5555")

   # Send signals to MT5
   command_socket = context.socket(zmq.PUB)
   command_socket.bind("tcp://localhost:5556")

   # Receive news events from MT5
   news_socket = context.socket(zmq.PULL)
   news_socket.bind("tcp://localhost:5557")
   ```

2. **Tick Data Ingestion:**
   ```python
   def on_tick_received(msg: dict):
       pair = msg["pair"]
       bid = msg["bid"]
       ask = msg["ask"]
       timestamp = datetime.fromtimestamp(msg["time"])

       # Feed to Range Bar builder
       range_bar_engine.process_tick(pair, bid, ask, timestamp)
   ```

3. **Signal Broadcasting:**
   ```python
   def send_signal(signal: dict):
       # signal = {
       #     "action": "OPEN_LONG",
       #     "pair": "EURUSD",
       #     "entry": 1.0850,
       #     "sl": 1.0820,
       #     "tp": null,  # Managed by Python
       #     "lots": 0.01
       # }
       msg = json.dumps(signal)
       command_socket.send_string(msg)
   ```

**Testing:**
```bash
# Terminal 1: Start Python listener
python -m src.zmq_listener

# Terminal 2: Start MT5 EA
# Should see: "Tick received: EURUSD bid=1.0850 ask=1.0852"
```

---

### Task 1.3: Health Monitoring + Reconnection

**Files to modify:**
- `src/zmq_listener.py` (add heartbeat)
- `MT5_EAs/Experts/JcampFX_Hand.mq5` (add heartbeat)

**Implementation:**
1. **Heartbeat (Python → MT5):**
   ```python
   def heartbeat_loop():
       while True:
           command_socket.send_string('{"heartbeat": true}')
           time.sleep(5)  # Every 5 seconds
   ```

2. **Connection Monitoring (MT5):**
   ```mql5
   datetime last_heartbeat = 0;

   void CheckConnection() {
       if (TimeCurrent() - last_heartbeat > 10) {
           // No heartbeat for 10s → reconnect
           ReconnectZMQ();
       }
   }
   ```

---

## Session 2: Real-Time Range Bar Builder

**Priority:** HIGH — Core data processing pipeline

### Task 2.1: Tick Storage + Range Bar Logic

**Files to create/modify:**
- **NEW:** `src/live_range_bar_engine.py` (real-time builder)
- **MODIFY:** `src/range_bar_builder.py` (extract reusable logic)

**Implementation:**
1. **Tick Ingestion:**
   ```python
   class LiveRangeBarEngine:
       def __init__(self):
           self.active_bars = {}  # pair -> current bar
           self.tick_buffer = []  # For Parquet batch writes

       def process_tick(self, pair: str, bid: float, ask: float, timestamp: datetime):
           mid = (bid + ask) / 2.0

           # Check if current bar is complete
           if self._should_close_bar(pair, mid):
               completed_bar = self._close_bar(pair, mid, timestamp)
               self._cache_to_parquet(completed_bar)
               self._trigger_dcrd_update(pair)

           # Update active bar
           self._update_bar(pair, mid, timestamp)
   ```

2. **Phantom Detection:**
   ```python
   def _check_phantom(self, pair: str, new_tick_time: datetime) -> bool:
       last_tick_time = self.active_bars[pair]["last_tick_time"]
       gap_duration = (new_tick_time - last_tick_time).total_seconds()

       # Weekend gap (Fri close → Mon open)
       if gap_duration > 7200:  # 2 hours
           return True
       return False
   ```

3. **Parquet Caching:**
   ```python
   def _cache_to_parquet(self, bar: dict):
       # Append to data/range_bars/{pair}_RB{size}.parquet
       # Same format as backtest
   ```

**Testing:**
```python
# Run with historical tick data first
engine = LiveRangeBarEngine()
for tick in historical_ticks:
    engine.process_tick(tick["pair"], tick["bid"], tick["ask"], tick["time"])

# Verify Range Bars match backtest output
```

---

## Session 3: Live DCRD Calculation

**Priority:** HIGH — Regime detection for signal generation

### Task 3.1: DCRD Integration

**Files to modify:**
- **MODIFY:** `src/dcrd_calculator.py` (support incremental updates)
- **NEW:** `src/live_dcrd_engine.py` (real-time wrapper)

**Implementation:**
1. **Incremental DCRD Update:**
   ```python
   class LiveDCRDEngine:
       def __init__(self):
           self.dcrd_calc = DCRDCalculator()
           self.cache = {}  # pair -> last N bars for rolling calcs

       def on_bar_close(self, pair: str, new_bar: dict):
           # Update cache with new bar
           self.cache[pair].append(new_bar)

           # Recalculate DCRD (uses last 200 bars for lookback)
           composite_score = self.dcrd_calc.calculate(
               pair=pair,
               bars=self.cache[pair][-200:]
           )

           # Store result
           self.current_scores[pair] = composite_score
   ```

2. **Layer Calculation (same as backtest):**
   - Layer 1 (4H Structural): ADX, Market Structure, ATR, CSM, Persistence
   - Layer 2 (1H Dynamic): Pullback detection, momentum
   - Layer 3 (Range Bar Intelligence): Speed, volatility

**Testing:**
```python
# Compare live DCRD vs backtest DCRD on same data
for bar in historical_bars:
    live_score = live_dcrd.on_bar_close(pair, bar)
    backtest_score = backtest_dcrd[bar["timestamp"]]
    assert abs(live_score - backtest_score) < 0.01
```

---

## Session 4: Strategy Signal Generation

**Priority:** HIGH — Entry/exit decision logic

### Task 4.1: TrendRider Live Integration

**Files to modify:**
- **MODIFY:** `src/strategies/trend_rider.py` (support real-time signals)
- **NEW:** `src/live_strategy_engine.py` (signal coordinator)

**Implementation:**
1. **Signal Generation:**
   ```python
   class LiveStrategyEngine:
       def __init__(self):
           self.trend_rider = TrendRider()
           self.range_rider = RangeRider()
           self.gating = EntryGating()

       def on_bar_close(self, pair: str, bar: dict, composite_score: float):
           # Determine active strategy
           if composite_score >= 30:
               signal = self.trend_rider.generate_signal(pair, bar)
           else:
               signal = self.range_rider.generate_signal(pair, bar)

           # Apply entry gates
           if self.gating.should_block(signal):
               return None

           # Send to MT5
           self._send_to_mt5(signal)
   ```

2. **Entry Gating:**
   - Price level cooldown (±20 pips, 4 hours)
   - Correlation filter (max 2 per currency)
   - Session filter (per-strategy rules)
   - News filter (block during high-impact events)

**Testing:**
```python
# Replay backtest data through live engine
for bar in backtest_bars:
    signal = live_strategy.on_bar_close(pair, bar, composite_score)

    # Verify signal matches backtest
    assert signal == backtest_signals[bar["timestamp"]]
```

---

## Session 5: Exit Management

**Priority:** HIGH — Profit protection + risk control

### Task 5.1: Live Exit Manager

**Files to create:**
- **NEW:** `src/live_exit_manager.py` (real-time exit logic)

**Implementation:**
1. **Partial Exit at 1.5R:**
   ```python
   def check_partial_exit(self, trade: Trade, current_price: float):
       r_multiple = calculate_r_multiple(trade, current_price)

       if r_multiple >= 1.5 and not trade.partial_exited:
           # Determine exit percentage based on entry CS
           exit_pct = self._get_exit_percentage(trade.entry_cs)

           # Send modify signal to MT5
           self._send_partial_exit(trade, exit_pct)
   ```

2. **Trailing SL:**
   ```python
   def update_trailing_sl(self, trade: Trade, new_bar: dict):
       if trade.direction == "LONG":
           new_sl = new_bar["low"] - (5 * point_value)
       else:
           new_sl = new_bar["high"] + (5 * point_value)

       if self._is_better_sl(trade, new_sl):
           self._send_sl_update(trade, new_sl)
   ```

3. **Runner Protection:**
   ```python
   def check_forced_exits(self, trade: Trade, current_price: float):
       r_multiple = calculate_r_multiple(trade, current_price)

       # 2R daily cap or weekend close
       if self._should_force_close(trade):
           if r_multiple >= -0.5:
               return  # Protect near-breakeven/winners

           # Only close deep losers
           self._send_close_signal(trade)
   ```

**Testing:**
```python
# Test partial exit timing
trade = Trade(entry=1.0850, sl=1.0820, direction="LONG")
current_price = 1.0895  # 1.5R hit
exit_manager.check_partial_exit(trade, current_price)

# Verify 60-80% closed (based on CS)
```

---

## Session 6: Demo Trading Validation

**Priority:** CRITICAL — Final validation before live

### Task 6.1: FP Markets Demo Setup

**Steps:**
1. Open FP Markets demo account (MT5 ECN)
2. Fund with $500 virtual equity
3. Connect to demo server: `FusionMarkets-Demo`
4. Verify spread/commission matches backtest assumptions

### Task 6.2: 1-Week Validation

**Metrics to Track:**
| Metric | Target | Tolerance | Status |
|--------|--------|-----------|--------|
| Trade Count | ~12-15/month | ±20% | — |
| Win Rate | 45%+ | ±5 pts | — |
| Avg R/trade | +0.18R | ±0.05R | — |
| Max DD | <20% | — | — |
| Signal Latency | <1s | — | — |

**Daily Checklist:**
- [ ] All 4 pairs streaming ticks
- [ ] Range Bars building correctly
- [ ] DCRD scores logged
- [ ] Signals generated and executed
- [ ] Exits managed (partial + trailing SL)
- [ ] No connection drops or errors

### Task 6.3: Backtest Overlap Test

**Goal:** Run backtest on same week as demo trading, compare results

**Expected Differences:**
- ±1-2 trades (timing variance)
- ±0.05R per trade (slippage/spread)
- Overall trend should match

---

## Risk Considerations

**Technical Risks:**
- ⚠️ ZMQ connection drops → auto-reconnect + state sync required
- ⚠️ Tick data loss → buffering + recovery mechanism
- ⚠️ DCRD calculation lag → ensure real-time performance (<100ms)
- ⚠️ Signal execution delay → measure latency, optimize if needed

**Trading Risks:**
- ⚠️ Demo slippage may differ from backtest assumptions
- ⚠️ Weekend gaps may cause unexpected phantom bars
- ⚠️ News events may trigger more blocks than backtest
- ⚠️ First week may have lower trade count (variance is normal)

**Mitigation:**
- ✅ Start with demo account (no real capital at risk)
- ✅ Monitor all metrics daily (compare to backtest baseline)
- ✅ Keep backtest engine running in parallel (validate assumptions)
- ✅ Have kill switch ready (shut down EA if behavior diverges)

---

## Files to Create/Modify

**New Files:**
- `MT5_EAs/Include/JcampStrategies/ZMQ_Bridge.mqh`
- `src/zmq_listener.py`
- `src/zmq_handler.py`
- `src/live_range_bar_engine.py`
- `src/live_dcrd_engine.py`
- `src/live_strategy_engine.py`
- `src/live_exit_manager.py`

**Modified Files:**
- `MT5_EAs/Experts/JcampFX_Hand.mq5` (integrate ZMQ)
- `src/range_bar_builder.py` (extract reusable logic)
- `src/dcrd_calculator.py` (support incremental updates)
- `src/strategies/trend_rider.py` (real-time signal generation)

---

## Success Criteria

**Phase 4 Gate:** V4.1 — 1-week demo trading matches backtest metrics

**Must Pass:**
- ✅ All 4 pairs streaming ticks → Range Bars built
- ✅ DCRD scores calculated in real-time (<100ms latency)
- ✅ Signals generated and executed on demo account
- ✅ Exit management working (partial exits, trailing SL, protection)
- ✅ Trade count within ±20% of expected (12-15/month)
- ✅ Win rate within ±5 pts of backtest (45%)
- ✅ Avg R/trade within ±0.05R of backtest (+0.18R)
- ✅ No major connection/execution issues

**On Success:** Move to Phase 5 (VPS + Live Trading)
**On Failure:** Debug, optimize, re-validate for another week

---

## Next Steps After Phase 4

**Phase 5 — VPS + Android + Signal Service:**
1. Deploy to VPS (Windows Server, MT5 + Python)
2. Android app for trade monitoring
3. Signal service for subscribers (optional)
4. Live trading with $500 real account (FP Markets ECN)
5. 1-month validation before scaling

**Phase 6 — Scaling + Optimization:**
1. Increase equity to $1,000 - $5,000
2. Add EURGBP (after 10-pip bar optimization)
3. Add alternative exit strategies (ATR-based, time-based)
4. Machine learning for entry quality scoring (optional)
