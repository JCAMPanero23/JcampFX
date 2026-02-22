# Pair Prioritization & Signal Selection

**Status:** ⚠️ NO EXPLICIT PRIORITIZATION SYSTEM IMPLEMENTED
**Last Updated:** February 22, 2026

---

## Current System: First-Come-First-Served

### How Pairs Are Processed

**Backtester (Event-Driven):**
- Uses priority queue (`heapq`) sorted by Range Bar `end_time`
- Pairs processed in **chronological order** (whichever bar completes first)
- No explicit pair ranking or prioritization

**Processing Flow:**
```python
# backtester/engine.py
heap = []
for pair in pairs:
    for bar in range_bars:
        heapq.heappush(heap, (bar.end_time, pair, bar))

while heap:
    end_time, pair, bar = heapq.heappop(heap)  # Pop earliest bar
    signal = brain.process(pair, ...)          # Process in time order
    if signal and not signal.is_blocked:
        open_trade(signal)
```

**Result:** If EURUSD bar completes at 12:00:00 and GBPUSD at 12:00:01, EURUSD is processed first.

---

## Current Gating System

The system has **filtering gates** (what NOT to trade) but NO **prioritization logic** (what to trade FIRST):

### Gate Order (brain_core.py)

1. **Gold Gate** - Block XAUUSD if equity < $2,000
2. **Max Concurrent** - Block if already at 2 positions (or 3 if equity > $1,000)
3. **Max Daily Trades** - Block if already opened 5 trades today
4. **Daily Loss Cap** - Block all if lost -2R today
5. **News Gating** - Block during high-impact news events
6. **Post-Event Cooling** - Block low CS signals for 15min after news
7. **Phantom Bar** - Block entries on phantom Range Bars
8. **Strategy Selection** - Route to TrendRider/BreakoutRider/RangeRider by CS
9. **Session Filter** - Block per-strategy session rules (Tokyo/London/NY)
10. **Strategy Cooldown** - Block strategy after 5 consecutive losses
11. **Price Level Cooldown** - Block re-entry within ±20 pips of recent loss (v2.2)
12. **Correlation Filter** - Block if already 2 trades with same currency
13. **Risk Engine** - Skip if risk < 0.8%

**Gap:** If multiple pairs pass all gates simultaneously, there's NO logic to choose which one to take.

---

## What Happens When Multiple Signals Appear?

### Scenario: 2 Signals, 1 Slot Available

**Example:**
```
Time: 12:00:00 UTC
Open Positions: 1 (max 2 allowed)
Signals generated:
  - EURUSD: CS=85, TrendRider, 2.5% risk, entry=1.0900
  - GBPUSD: CS=90, TrendRider, 2.8% risk, entry=1.2500
```

**Current Behavior:**
- Whichever pair's Range Bar completed FIRST is processed first
- If EURUSD bar end_time = 11:59:58, it gets the slot
- GBPUSD bar end_time = 12:00:02, blocked by max concurrent gate
- **No consideration of:** CS level, risk %, pair strength, or strategy confidence

**Result:** First-come-first-served, NOT best-signal-first.

---

## Implicit Prioritization Factors

While there's no explicit ranking, some factors **indirectly** affect which pairs trade more:

### 1. Range Bar Speed
- Faster-forming pairs (high momentum) generate signals more frequently
- Example: If USDJPY forms 4 bars/hour vs USDCHF 1 bar/hour, USDJPY gets 4x more signal opportunities

### 2. DCRD Score Distribution
- Pairs that stay in TRENDING regime (CS ≥70) longer get more TrendRider signals
- Historical data (2024-2025): USDJPY stayed CS ≥70 for 77.7% of time → 47% of all trades

### 3. Session Filter
- TrendRider blocks Tokyo/Off-Hours sessions for EURUSD/GBPUSD/USDCHF
- JPY pairs (USDJPY/AUDJPY) allowed during Tokyo → more opportunities

### 4. Correlation Filter
- First pair to generate signal "locks" its base/quote currencies
- Subsequent pairs with same currency are blocked
- Example: EURUSD opens → GBPUSD blocked (shares USD), EURGBP blocked (shares EUR and GBP)

**Problem:** These are side effects, not intentional design. No guarantee the "best" signal is selected.

---

## Potential Prioritization Systems

### Option 1: CompositeScore Ranking (Simplest)

**Logic:** Higher CS = stronger regime conviction → prioritize higher CS signals

**Implementation:**
```python
# Collect all valid signals in current bar
signals = []
for pair in pairs:
    sig = brain.process(pair, ...)
    if sig and not sig.is_blocked:
        signals.append((sig.composite_score, sig))

# Sort by CS descending, take top N
signals.sort(reverse=True, key=lambda x: x[0])
for _, sig in signals[:available_slots]:
    open_trade(sig)
```

**Pros:**
- Simple, aligns with DCRD philosophy (trust the score)
- CS already reflects regime strength across all 3 layers

**Cons:**
- Doesn't consider pair diversity (might overweight single pair)
- Doesn't account for recent performance or drawdown

---

### Option 2: Risk-Adjusted Return Ranking

**Logic:** Prioritize signals with best recent risk-adjusted performance

**Implementation:**
```python
# Track 20-trade Sharpe ratio per pair
pair_sharpe = {
    "EURUSD": 0.8,
    "GBPUSD": 1.2,  # ← Best recent performance
    "USDJPY": 0.3,
}

# Score signals by CS × Sharpe
signals = []
for pair in pairs:
    sig = brain.process(pair, ...)
    if sig and not sig.is_blocked:
        score = sig.composite_score * pair_sharpe[pair]
        signals.append((score, sig))

signals.sort(reverse=True, key=lambda x: x[0])
```

**Pros:**
- Adapts to recent market conditions (rewards what's working)
- Reduces exposure to underperforming pairs

**Cons:**
- Requires tracking per-pair performance
- May create feedback loop (winners keep winning, losers starved)

---

### Option 3: Diversification Weighting

**Logic:** Ensure max 1 trade per currency at entry time

**Implementation:**
```python
# Filter signals to ensure no currency overlap
used_currencies = set()
selected_signals = []

for sig in sorted_signals:  # Pre-sorted by CS or other metric
    pair = sig.pair
    base, quote = pair[:3], pair[3:]

    if base not in used_currencies and quote not in used_currencies:
        selected_signals.append(sig)
        used_currencies.add(base)
        used_currencies.add(quote)

        if len(selected_signals) >= available_slots:
            break
```

**Pros:**
- Maximum diversification (no currency appears twice)
- Reduces correlation risk

**Cons:**
- Very restrictive (max 3 concurrent trades across 5 pairs = only 3 currencies active)
- May reject high-CS signals to enforce diversity

---

### Option 4: Hybrid: CS + Recent Performance + Diversity

**Logic:** Multi-factor ranking with configurable weights

**Implementation:**
```python
def score_signal(sig, pair_stats, existing_positions):
    cs_score = sig.composite_score / 100.0              # 0–1
    sharpe_score = pair_stats[sig.pair].sharpe / 2.0    # normalize

    # Diversity penalty: -0.2 if currency already in use
    base, quote = sig.pair[:3], sig.pair[3:]
    diversity_penalty = 0.0
    for pos in existing_positions:
        if base in pos.pair or quote in pos.pair:
            diversity_penalty = 0.2
            break

    # Weighted combination
    total_score = (
        0.5 * cs_score +           # 50% weight on DCRD confidence
        0.3 * sharpe_score +        # 30% weight on recent performance
        -diversity_penalty          # Penalty for currency overlap
    )
    return total_score

# Rank and select
signals_with_scores = [(score_signal(s), s) for s in valid_signals]
signals_with_scores.sort(reverse=True, key=lambda x: x[0])
```

**Pros:**
- Balances multiple factors
- Configurable (adjust weights based on testing)

**Cons:**
- More complex
- Harder to validate (many parameters)

---

## Recommendation

### Short-Term (Phase 3.1.1–3.2)
**Status Quo is acceptable** for now because:
- Current system trades only 165 trades over 2 years (avg 1 signal every 4.4 days)
- Max concurrent = 2 means collision is rare
- Price Level Cooldown (v2.2) already prevents rapid re-entries

### Medium-Term (Phase 3.3+)
Implement **Option 1: CompositeScore Ranking** if:
- Multiple signals appear frequently at same timestamp
- Analysis shows we're missing high-CS signals due to max concurrent gate
- Walk-forward validation requires more selective entry logic

**Implementation Location:**
- `backtester/engine.py::run()` — collect signals per timestamp, sort before opening
- `src/brain_core.py` — add `get_signal_priority_score()` method

---

## Current Workarounds

The system **indirectly** handles prioritization via:

1. **Time-based processing** (heapq ensures fairest allocation)
2. **Correlation filter** (prevents overexposure to single currency)
3. **Strategy cooldown** (disables underperforming strategies)
4. **Price level cooldown** (blocks revenge trades)

**Analysis Needed:**
- Review backtest logs: How often do 2+ signals appear at exact same timestamp?
- Check if high-CS signals are being blocked by lower-CS signals that arrived first
- If collision rate < 5%, prioritization may not be worth the complexity

---

## Files to Modify (If Implementing)

| Component | File | Changes |
|---|---|---|
| Signal Collection | `backtester/engine.py` | Buffer signals per timestamp, sort before opening |
| Priority Scoring | `src/brain_core.py` | Add `signal_priority_score()` method |
| Pair Stats Tracking | `src/performance_tracker.py` | Track per-pair Sharpe, win rate, recent R |
| Config | `src/config.py` | Add priority weights, enable/disable flag |

---

## Test Cases

If prioritization is implemented, validate:

**TC1: Same Timestamp, Different CS**
- EURUSD signal CS=85, GBPUSD signal CS=95, 1 slot available
- Expected: GBPUSD taken (higher CS)

**TC2: Same Timestamp, Currency Overlap**
- EURUSD signal, GBPUSD signal (both share USD), 1 slot available
- Expected: Higher CS taken, or diversification rule applied

**TC3: Sequential Timestamps**
- EURUSD at 12:00:00, GBPUSD at 12:00:05, 1 slot available
- Expected: EURUSD taken (arrived first, no prioritization needed)

---

**Status:** No prioritization implemented (first-come-first-served)
**Next Steps:** Monitor backtest logs for signal collision frequency before implementing
