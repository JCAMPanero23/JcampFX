# JcampFX Brain cBot — cTrader Migration

This directory contains the cTrader cBot implementation of the JcampFX trading system. The cBot is a direct translation of the MT5 EA (`JcampFX_Brain.mq5`) to C# for cTrader.

## Files

- **JcampFX_Brain.cs** — Main cBot class (robot logic)
- **ZMQBridge.cs** — NetMQ socket wrapper (3 ports)
- **MessageTypes.cs** — JSON DTOs for ZMQ messages
- **README.md** — This file

## Architecture

```
cTrader cBot (C#) ←→ ZMQ Bridge ←→ Python Brain (unchanged)
│
├─ Port 5555 (PUSH): Send ticks, execution reports, heartbeats → Python
├─ Port 5556 (SUB): Receive entry/exit/modify signals ← Python
└─ Port 5557 (PUSH): News events (Phase 5+ placeholder)
```

The Python Brain is **platform-agnostic** — it uses canonical symbol names (e.g., "EURUSD") and expects the EA/cBot to handle broker-specific suffixes locally.

## Installation (cTrader Desktop)

### Step 1: Install NetMQ NuGet Package

**Option A: Automated Installation (Recommended)**

Run the installer script in `D:\JcampFX\cTrader_cBot\`:

```bash
# Windows (PowerShell)
.\install_netmq.bat

# Or run PowerShell script directly
powershell -ExecutionPolicy Bypass -File install_netmq.ps1

# Or Python (if you prefer)
python install_netmq.py
```

This will:
1. Download `nuget.exe` automatically
2. Install NetMQ 4.0.1.13 to `packages/` directory
3. Show you the DLL path to add to cTrader

Then in cTrader:
1. Open **Automate** → **Manage References** → **Add Local File**
2. Navigate to: `D:\JcampFX\cTrader_cBot\packages\NetMQ.4.0.1.13\lib\net47\NetMQ.dll`
3. Click **OK**

**Option B: Manual Installation (via cTrader UI)**

1. Open **cTrader** → **Automate** → **Manage References**
2. Click **Add NuGet Package**
3. Search for `NetMQ` (by NetMQ authors)
4. Install the latest stable version (e.g., `4.0.1.13`)

**IMPORTANT:** NetMQ is a pure .NET implementation of ZMQ. If NetMQ fails to communicate with Python's `pyzmq`, we'll switch to `clrzmq` (native libzmq.dll wrapper) as fallback.

### Step 2: Create New cBot Project

1. Open **cTrader** → **Automate** → **New cBot**
2. Name: `JcampFX_Brain`
3. Replace default code with contents of `JcampFX_Brain.cs`

### Step 3: Add Additional Files

cTrader cBots can reference multiple C# files:

1. Click **Manage References** → **Add Local File**
2. Add `ZMQBridge.cs`
3. Add `MessageTypes.cs`

Alternatively, copy all code into a single file (cTrader supports multi-class files).

### Step 4: Configure Broker Symbol Suffix

Check your FP Markets cTrader account for symbol naming convention:

- **MT5:** Uses `.r` suffix (e.g., `EURUSD.r`)
- **cTrader:** May use `.ct`, `.raw`, or NO suffix (check in Market Watch)

**To check:**
1. Open cTrader → Market Watch
2. Find EURUSD
3. Note the exact symbol name shown

**Update cBot parameter:**
- If symbols are `EURUSD`, `USDJPY`, etc. → Set `BrokerSuffix = ""`
- If symbols are `EURUSD.ct`, `USDJPY.ct`, etc. → Set `BrokerSuffix = ".ct"`

### Step 5: Test Compilation

1. Click **Build** (Ctrl+B)
2. Fix any errors (likely missing `using` statements)
3. Ensure **AccessRights = FullAccess** is set (required for ZMQ)

## Running the cBot

### Step 1: Start Python Brain

```bash
cd D:\JcampFX
python src/live_launcher.py --platform ctrader --demo-mode
```

The Python Brain will listen on ports 5555/5556/5557 for the cBot to connect.

### Step 2: Attach cBot to Chart

1. Open cTrader → Any chart (EURUSD recommended)
2. Drag `JcampFX_Brain` cBot onto chart
3. Configure parameters:
   - **Trading Pairs:** `EURUSD,USDJPY,AUDJPY,USDCHF` (default)
   - **Broker Suffix:** `` (empty if no suffix, `.ct` if suffixed)
   - **Enable Trading:** `true` (or `false` for monitoring only)
   - **Magic Number:** `777001` (default)
4. Click **Start**

### Step 3: Verify Connection

Check cTrader **Log** tab for:
- `[ZMQ] Signal socket connected to tcp://localhost:5555 (PUSH)`
- `[ZMQ] Command socket connected to tcp://localhost:5556 (SUB)`
- `[ZMQ] Bridge started successfully`

Check Python logs for:
- `[INFO] Tick received: EURUSD.ct @ Bid=1.08501 Ask=1.08503`
- `[INFO] ZMQ bridge stats: 1234 ticks received`

If no connection, check:
1. Python Brain is running BEFORE starting cBot
2. Ports 5555/5556/5557 are not blocked by firewall
3. NetMQ installed correctly (check References panel)

## Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| Trading Pairs | `EURUSD,USDJPY,AUDJPY,USDCHF` | Comma-separated list of pairs to monitor |
| Broker Suffix | `` (empty) | Suffix to append to symbol names (e.g., `.ct`) |
| Heartbeat Interval | `30` (seconds) | ZMQ heartbeat frequency |
| Enable Trading | `true` | Allow order execution (false = monitor only) |
| Magic Number | `777001` | Order identification number |
| Slippage (pips) | `2.0` | Maximum slippage allowed |

## Troubleshooting

### Issue: "NetMQ not found" error
**Solution:** Install NetMQ via **Manage References → Add NuGet Package**

### Issue: Tick data not reaching Python
**Solution:**
1. Check Python logs for "ZMQ bridge started"
2. Check cBot log for "Signal socket connected"
3. Verify ports 5555/5556 are not blocked by firewall
4. Restart cBot and Python Brain (start Python FIRST)

### Issue: Orders not executing
**Solution:**
1. Check `Enable Trading = true` in cBot parameters
2. Check Python logs for signal generation
3. Check cBot log for `[COMMAND] Processing: entry`
4. Verify account has sufficient margin

### Issue: Symbol not found error
**Solution:**
1. Check `BrokerSuffix` parameter matches FP Markets naming
2. Verify symbol is available in Market Watch
3. Check for typos in `Trading Pairs` parameter

### Issue: NetMQ communication fails with pyzmq
**Fallback:** Switch to `clrzmq` (native libzmq.dll wrapper):
1. Uninstall NetMQ NuGet package
2. Install `clrzmq` from NuGet
3. Update `using NetMQ;` → `using ZeroMQ;`
4. Adjust socket creation syntax (API differs slightly)

## Next Steps

After successful connection and tick flow validation:
1. **Phase 2:** Implement order execution (entry/exit/modify)
2. **Phase 3:** Build test/dummy trade system (15s full-cycle test)
3. **Phase 4:** Symbol suffix handling (Python brain updates)
4. **Phase 5:** 1-week demo trading validation
5. **Phase 6:** Production deployment

## Validation Checkpoints

**Checkpoint 1 (Phase 1: Foundation):**
- [ ] cBot sends ticks for all 4 pairs
- [ ] Python receives ticks with correct JSON structure
- [ ] Heartbeat every 30 seconds
- [ ] No socket errors for 1 hour continuous run

**Checkpoint 2 (Phase 2: Order Execution):**
- [ ] Entry signal → order executes in cTrader
- [ ] Execution report received in Python within 2s
- [ ] Exit signal → position closes
- [ ] Modify signal → SL/TP updates
- [ ] No JSON parsing errors

See migration plan (`../migration_plan.md`) for full validation criteria.

## Support

For issues or questions:
- Check cTrader log first (detailed error messages)
- Check Python logs (ZMQ bridge status)
- Review migration plan (`../migration_plan.md`)
- Test with dummy trade system (Phase 3)

---

**Status:** Phase 1 Complete (Foundation) ✅
**Next:** Phase 2 (Order Execution Testing)
