# SwingRider GBPJPY -- Convex Amplifier Module (v1.0)

## Overview

SwingRider is an **independent convex trading module** designed
specifically for **GBPJPY**.\
Its purpose is to capture **large volatility expansions and long trend
legs** that the main intraday/range strategies cannot fully exploit.

Key design principles: - Low trade frequency - Large R-multiples -
Independence from other strategies - Convex profit profile

------------------------------------------------------------------------

# System Identity

  Parameter          Value
  ------------------ ----------------------------------
  Pair               GBPJPY
  Strategy Role      Convex Profit Amplifier
  Timeframe Bias     Daily
  Entry Trigger      H4
  Max Positions      1
  Risk per Trade     0.7%
  Partial Exit       40% at +2R
  Runner             60%
  Trailing Stop      Daily Chandelier
  Additional Logic   Volatility Expansion Accelerator

------------------------------------------------------------------------

# Regime Filter (Daily)

### Long Conditions

-   Price above **EMA 50**
-   EMA 50 slope upward
-   Market structure forms **Higher High + Higher Low**

### Short Conditions

-   Price below **EMA 50**
-   EMA 50 slope downward
-   Market structure forms **Lower Low + Lower High**

This filter ensures trades follow higher timeframe momentum.

------------------------------------------------------------------------

# Weekly Pivot Bias Filter

SwingRider uses pivots only as **bias filters**, not exit targets.

### Long trades

Price must be **above Weekly Pivot (WP)**

### Short trades

Price must be **below Weekly Pivot (WP)**

No pivot levels are used for profit taking.

------------------------------------------------------------------------

# Setup Phase (Daily Pullback)

After a new structural high/low:

Wait for: - **2--5 candle pullback** - Pullback does **not break
previous structure** - At least one candle with **rejection wick**

This creates compression before expansion.

------------------------------------------------------------------------

# Entry Trigger (H4)

Enter when either condition occurs:

1.  **H4 close above pullback high** (breakout trigger)
2.  **Bullish/Bearish engulfing candle** at pullback zone

Entries occur only at **candle close**.

------------------------------------------------------------------------

# Initial Stop Loss

Stop loss location:

Pullback swing low/high\
± **0.5 × ATR(14)**

Typical GBPJPY stop range:

**200--350 pips**

This is intentional for swing convexity.

------------------------------------------------------------------------

# Partial Profit Logic

At **+2R**:

-   Close **40% position**
-   Move stop to **BE + 0.2R**

Remaining **60% becomes convex runner**.

------------------------------------------------------------------------

# Runner Management

Runner uses **Daily Chandelier Exit**.

  Parameter          Value
  ------------------ ----------------------
  ATR Period         22
  Multiplier         3
  Update Frequency   Once per daily close

No counter-bar exits or intraday trailing.

------------------------------------------------------------------------

# Volatility Expansion Accelerator

When volatility explodes, the trailing stop tightens automatically.

### Activation Conditions

ATR Expansion:

ATR(14) \> **1.5 × 20-day ATR average**

AND

Range Expansion:

Daily range \> **1.8 × 20-day average range**

------------------------------------------------------------------------

### Accelerator Behavior

Chandelier Multiplier changes:

Normal condition:

ATR × **3.0**

Volatility Expansion:

ATR × **2.2**

When expansion ends, multiplier returns to **3.0**.

This protects profits during explosive moves.

------------------------------------------------------------------------

# Hard Invalidation Rules

Trade is closed early only if:

-   Market forms **opposite structure break**
-   Price closes **through EMA50 with strong momentum**

Otherwise, the **Chandelier Exit controls the trade**.

------------------------------------------------------------------------

# Expected Statistical Profile

Over a multi-year sample:

  Metric            Expectation
  ----------------- -------------
  Trades per year   6--15
  Win Rate          35--45%
  Average Win       3R--7R
  Largest Winners   8R--12R
  Losing Streaks    3--5 trades

Convex strategies rely on **few large winners**.

------------------------------------------------------------------------

# Backtesting Methodology

## Data Range

Recommended testing window:

**2018--2025**

This period includes:

-   Strong trends
-   Volatility shocks
-   Slow markets

------------------------------------------------------------------------

## Data Source

Data does **not need to be FP Markets** for structural testing.

Acceptable sources:

-   Dukascopy
-   TrueFX
-   MT5 history center

Broker data differences are negligible for **multi-day swing trades**.

------------------------------------------------------------------------

# Testing Structure

## Phase 1 -- In-Sample (2018--2022)

Tune only:

-   ATR multiplier
-   Volatility thresholds
-   Partial percentage

Avoid heavy optimization.

------------------------------------------------------------------------

## Phase 2 -- Out-of-Sample (2023--2025)

No parameter changes allowed.

Evaluate:

-   Profit stability
-   Drawdown behavior
-   Largest R trades

------------------------------------------------------------------------

# Monte Carlo Validation

After collecting trade list:

Run Monte Carlo simulations to measure:

-   Worst-case equity path
-   Probability of deep drawdowns
-   Loss streak distribution

Convex systems typically show **uneven equity curves**.

This is normal.

------------------------------------------------------------------------

# Portfolio Integration

SwingRider operates independently.

  Feature               Behavior
  --------------------- --------------------
  Pair                  GBPJPY
  Position Slot         +1 additional slot

------------------------------------------------------------------------

# Convexity Objective

System success is measured by:

Percentage of profit from **top 3 trades**.

Target:

**25--40% of total profits from top 3 trades**

If profits are evenly distributed, convexity is weak.

------------------------------------------------------------------------

# Final Philosophy

This module exists to capture **rare but powerful trend expansions**.

Rules are intentionally simple to avoid overfitting.

Key principles:

-   Patience
-   Large stop distances
-   Let runners run
-   Do not interfere with convex trades
