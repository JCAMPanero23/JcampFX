# Step-by-Step: After NetMQ Installation

## Where You Are Now ✅
- NetMQ.dll installed in `packages\NetMQ.4.0.1.13\lib\net47\`
- NetMQ reference added to cTrader (in Manage References)

## What's Next (5 minutes)

### Step 1: Create New cBot (1 min)

1. In cTrader → **Automate** tab
2. Click **New** button (top left toolbar)
3. Select **cBot** (not Indicator)
4. Name: `JcampFX_Brain`
5. Click **Create**

**You should see:**
- Code editor opens with default template code
- About 20-30 lines starting with `using System;`
- A class called `JcampFX_Brain` with `OnStart()`, `OnTick()`, `OnStop()` methods

### Step 2: Use Combined File (2 min)

**IMPORTANT:** We've created a combined file for you that merges all 3 files into one!

1. Open `D:\JcampFX\cTrader_cBot\JcampFX_Brain_COMBINED.cs` in **Notepad**
   - Right-click file → Open with → Notepad
   - Or double-click if Notepad is default

2. In Notepad:
   - Press **Ctrl+A** (select all)
   - Press **Ctrl+C** (copy)

3. In cTrader code editor:
   - Press **Ctrl+A** (select all default code)
   - Press **Delete** (remove it)
   - Press **Ctrl+V** (paste our code)

**You should now see:**
- Code starting with `using System;`
- Then `using NetMQ;` and `using NetMQ.Sockets;`
- Then `namespace JcampFX { ... }`
- Three classes: `MessageTypes`, `ZMQBridge`, `JcampFX_Brain`

### Step 3: Verify NetMQ Reference (1 min)

1. In cTrader → Click **Manage References** (top toolbar)
2. **Check:** References panel shows `NetMQ 4.0.1.13`

**If NetMQ is NOT listed:**
1. Click **Add Local File**
2. Navigate to: `D:\JcampFX\cTrader_cBot\packages\NetMQ.4.0.1.13\lib\net47\NetMQ.dll`
3. Click **Open**

### Step 4: Build (1 min)

1. Click **Build** button (or press **Ctrl+B**)
2. Wait for compilation (5-10 seconds)

**Expected result:**
- Build succeeds ✅
- Output shows: "Build completed successfully"
- No red errors in output panel

**If you see errors:**
- Check Step 3 (NetMQ reference must be added)
- Check code was pasted correctly (should have `using NetMQ;` at top)

### Step 5: Configure Parameters (1 min)

Before running, check your symbol suffix:

1. In cTrader → **Market Watch** panel
2. Find **EURUSD** in the list
3. Note exact name:
   - If `EURUSD` → Suffix is **empty** (use `""`)
   - If `EURUSD.ct` → Suffix is **`.ct`**
   - If `EURUSD.raw` → Suffix is **`.raw`**

**Remember this!** You'll need it when starting the cBot.

---

## Troubleshooting

### Build Error: "NetMQ not found"
**Solution:**
1. Click **Manage References**
2. Verify `NetMQ 4.0.1.13` is listed
3. If not, add it via **Add Local File** → Navigate to DLL path

### Build Error: "using NetMQ could not be found"
**Same as above** - NetMQ reference not added correctly

### Build Error: Syntax errors in code
**Solution:**
1. Delete ALL code in cTrader editor
2. Re-copy from `JcampFX_Brain_COMBINED.cs`
3. Make sure you copied the ENTIRE file (Ctrl+A in Notepad)

### Code looks wrong / incomplete
**Solution:**
- Open `JcampFX_Brain_COMBINED.cs` in Notepad
- Scroll to bottom - should end with a closing brace `}`
- File should be ~38 KB, ~984 lines
- If smaller, file may be incomplete - re-run `python combine_files.py`

---

## What You Should Have Now

✅ NetMQ reference added to cTrader
✅ New cBot created named `JcampFX_Brain`
✅ All code pasted from `JcampFX_Brain_COMBINED.cs`
✅ Build succeeds with no errors
✅ Symbol suffix noted (e.g., empty or `.ct`)

---

## Next: Test the cBot

See **QUICK_START.md** Step 4 for testing with Python Brain.

**Quick preview:**

1. Start Python Brain:
   ```bash
   cd D:\JcampFX
   python src/zmq_bridge.py
   ```

2. In cTrader:
   - Drag `JcampFX_Brain` cBot onto EURUSD chart
   - Set `Broker Suffix` parameter (from Step 5 above)
   - Set `Enable Trading` = **false** (monitoring only)
   - Click **Start**

3. Check logs:
   - cTrader log: Should show "Bridge started successfully"
   - Python terminal: Should show "Tick received: EURUSD..."

**If both show tick flow → SUCCESS!** ✅

---

## Files Reference

- `JcampFX_Brain_COMBINED.cs` — **Use this!** All 3 files merged into one
- `JcampFX_Brain.cs` — Original (reference only)
- `ZMQBridge.cs` — Original (reference only)
- `MessageTypes.cs` — Original (reference only)

**You only need the COMBINED file for cTrader.**

---

## Quick Command Reference

```bash
# Create combined file (if needed)
cd D:\JcampFX\cTrader_cBot
python combine_files.py

# Test Python ZMQ bridge
cd D:\JcampFX
python src/zmq_bridge.py
```

---

**You're at:** Create cBot + paste code + build
**Next step:** Test with Python Brain (5 minutes)
