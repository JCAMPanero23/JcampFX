# cTrader Quick Start Guide

**Goal:** Get cBot sending ticks to Python in 15 minutes.

## Prerequisites

- [ ] cTrader Desktop installed
- [ ] FP Markets cTrader demo account ($500 starting equity)
- [ ] Python 3.11+ with pyzmq installed (`pip install pyzmq`)

## Step 1: Check Symbol Suffix (2 min)

1. Open **cTrader** → **Market Watch**
2. Find **EURUSD** in the list
3. Note the EXACT symbol name shown

**Examples:**
- If you see `EURUSD` → No suffix (use `BrokerSuffix = ""`)
- If you see `EURUSD.ct` → Suffix is `.ct` (use `BrokerSuffix = ".ct"`)
- If you see `EURUSD.raw` → Suffix is `.raw` (use `BrokerSuffix = ".raw"`)

**Write down the suffix:** _______________

## Step 2: Install NetMQ Package (2 min)

**Option A: Automated (Recommended)**

Open terminal in `D:\JcampFX\cTrader_cBot\`:

```bash
# Run installer (choose one):
.\install_netmq.bat          # Windows batch
python install_netmq.py      # Python script
```

Then in cTrader:
1. **Automate** → **Manage References** → **Add Local File**
2. Navigate to: `packages\NetMQ.4.0.1.13\lib\net47\NetMQ.dll`
3. Click **OK**

**Option B: Manual (via cTrader UI)**

1. Open **cTrader** → **Automate** tab
2. Click **Manage References** (top toolbar)
3. Click **Add NuGet Package**
4. Search: `NetMQ`
5. Install: `NetMQ` by NetMQ (latest stable, e.g., 4.0.1.13)
6. Click **OK**

**Verify:** References panel shows `NetMQ` package

## Step 3: Create cBot Project (5 min)

### Option A: Single File (Easiest)

1. Open **cTrader** → **Automate** → **New cBot**
2. Name: `JcampFX_Brain`
3. Delete all default code
4. Copy ENTIRE contents of `D:\JcampFX\cTrader_cBot\JcampFX_Brain.cs`
5. Copy ENTIRE contents of `D:\JcampFX\cTrader_cBot\ZMQBridge.cs` (append to same file)
6. Copy ENTIRE contents of `D:\JcampFX\cTrader_cBot\MessageTypes.cs` (append to same file)
7. Remove duplicate `using` statements at top (keep only one set)
8. Remove duplicate `namespace JcampFX { ... }` wrapper (keep only one)
9. Click **Build** (Ctrl+B)

### Option B: Multi-File (Cleaner)

1. Open **cTrader** → **Automate** → **New cBot**
2. Name: `JcampFX_Brain`
3. Replace code with `D:\JcampFX\cTrader_cBot\JcampFX_Brain.cs`
4. Click **Manage References** → **Add Local File**
5. Add `D:\JcampFX\cTrader_cBot\ZMQBridge.cs`
6. Add `D:\JcampFX\cTrader_cBot\MessageTypes.cs`
7. Click **Build** (Ctrl+B)

**Verify:** Build succeeds with no errors

## Step 4: Start Python Brain (2 min)

Open terminal in `D:\JcampFX`:

```bash
# Option 1: Use existing live_launcher (if available)
python src/live_launcher.py --platform ctrader --demo-mode

# Option 2: Use minimal ZMQ bridge (if live_launcher not ready)
python src/zmq_bridge.py
```

**Expected output:**
```
[INFO] ZMQ bridge started
[INFO] Signal socket bound to port 5555 (PULL)
[INFO] Command socket bound to port 5556 (PUB)
[INFO] News socket bound to port 5557 (PULL)
```

**Keep this terminal open!**

## Step 5: Start cBot (3 min)

1. Open **cTrader** → Any chart (EURUSD recommended)
2. **Automate** tab → Find `JcampFX_Brain` cBot
3. Drag cBot onto chart
4. Configure parameters:
   - **Trading Pairs:** `EURUSD,USDJPY,AUDJPY,USDCHF` (default)
   - **Broker Suffix:** (use value from Step 1)
   - **Enable Trading:** `false` (monitoring only for now)
   - **Magic Number:** `777001` (default)
5. Click **Start**

**Check cTrader Log tab:**
```
[INFO] Monitoring 4 pairs: EURUSD, USDJPY, AUDJPY, USDCHF
[INFO] Loaded symbol: EURUSD → EURUSD (Digits=5, PipSize=0.0001)
[ZMQ] Signal socket connected to tcp://localhost:5555 (PUSH)
[ZMQ] Command socket connected to tcp://localhost:5556 (SUB)
[SUCCESS] JcampFX Brain cBot initialized
```

**Check Python terminal:**
```
[INFO] Tick received: EURUSD @ Bid=1.08501 Ask=1.08503
[INFO] Tick received: USDJPY @ Bid=149.123 Ask=149.125
[INFO] ZMQ bridge stats: 1234 ticks received
```

## Troubleshooting

### Issue: "NetMQ not found"
**Solution:** Repeat Step 2, ensure NetMQ installed via NuGet

### Issue: "Failed to connect signal socket"
**Solution:**
1. Check Python Brain is running BEFORE starting cBot
2. Restart Python Brain
3. Restart cBot

### Issue: "Symbol not found: EURUSD.ct"
**Solution:**
1. Check `BrokerSuffix` parameter matches Step 1
2. Verify symbol in Market Watch
3. Try `BrokerSuffix = ""` (empty) if unsure

### Issue: No ticks in Python
**Solution:**
1. Check cBot log shows "Signal socket connected"
2. Check Python shows "Signal socket bound to port 5555"
3. Disable firewall temporarily (test only)
4. Restart both Python and cBot

### Issue: Build errors in cBot
**Solution:**
1. Ensure NetMQ package installed
2. Check for missing `using` statements:
   ```csharp
   using System;
   using System.Text.Json;
   using NetMQ;
   using NetMQ.Sockets;
   using cAlgo.API;
   ```
3. Verify namespace is `namespace JcampFX`

## Validation Checkpoint 1

After 5 minutes of running:

- [ ] cBot shows "Bridge started successfully" in log
- [ ] Python shows tick data flowing (multiple pairs)
- [ ] Heartbeat message every 30 seconds in Python log
- [ ] No errors in either cBot or Python logs

**If all checkboxes checked:** ✅ Phase 1 Complete! Move to Phase 2 (test_trade.py)

**If any issues:** See troubleshooting above or check `cTrader_cBot/README.md`

## Next Steps

### Test Order Execution (Phase 2)

```bash
# Full cycle test (entry → modify → exit in 15s)
python test_trade.py --pair EURUSD --direction BUY --mode full_cycle
```

**Before running:**
1. Change cBot parameter: `Enable Trading = true`
2. Verify demo account has $500+ balance
3. Keep Python Brain running

### Expected Result
```
[TEST] Firing full_cycle test signal...
[TEST] Sending entry: EURUSD BUY @ 1.08503 SL=1.08003 Ticket=90000
✅ Entry signal sent successfully
[TEST] Waiting 5s before modifying SL...
[TEST] Modifying SL to breakeven: Ticket 90000 SL=1.08503
✅ Modify signal sent successfully
[TEST] Waiting 5s before exit...
[TEST] Closing position: Ticket 90000
✅ Exit signal sent successfully
[TEST] Full cycle complete: Ticket 90000
```

**Validation Checkpoint 2:**
- [ ] Order appears in cTrader (Positions tab)
- [ ] SL updates to breakeven after 5s
- [ ] Position closes after 15s total
- [ ] Execution report received in Python
- [ ] No errors

---

**Time to complete:** ~15 minutes
**Status:** Phase 1 Foundation
**Next:** Phase 2 Order Execution Testing
