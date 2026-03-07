# NetMQ Package Installation Guide

Three ways to install NetMQ for cTrader cBot development.

## Method 1: Automated Script (Recommended) ⭐

**Advantages:**
- Fastest method (1 command)
- Works offline after first download
- No manual clicking in cTrader UI
- Reproducible (can script in CI/CD)

**Steps:**

1. Open terminal in `D:\JcampFX\cTrader_cBot\`

2. Run installer (choose one):
   ```bash
   # Windows Batch (double-click or run in cmd)
   install_netmq.bat

   # PowerShell (if batch doesn't work)
   powershell -ExecutionPolicy Bypass -File install_netmq.ps1

   # Python (cross-platform)
   python install_netmq.py
   ```

3. Wait for installation (downloads nuget.exe + NetMQ package)

4. Script will show DLL path like:
   ```
   packages\NetMQ.4.0.1.13\lib\net47\NetMQ.dll
   ```

5. Open cTrader → **Automate** → **Manage References** → **Add Local File**

6. Navigate to the DLL path shown by script

7. Click **OK**

**Verify:** References panel shows `NetMQ 4.0.1.13`

---

## Method 2: Manual via cTrader UI

**Advantages:**
- No command line required
- Visual confirmation at each step
- cTrader handles download automatically

**Steps:**

1. Open **cTrader** → **Automate** tab

2. Click **Manage References** (top toolbar)

3. Click **Add NuGet Package**

4. Search: `NetMQ`

5. Select: `NetMQ` by NetMQ (version 4.0.1.13 or latest)

6. Click **Install**

7. Wait for download (cTrader shows progress)

8. Click **OK**

**Verify:** References panel shows `NetMQ 4.0.1.13`

---

## Method 3: Manual Download + Local Reference

**Advantages:**
- Most control over package version
- Works when cTrader NuGet integration has issues
- Can use same DLL for multiple cBots

**Steps:**

1. Download nuget.exe:
   ```
   https://dist.nuget.org/win-x86-commandline/latest/nuget.exe
   ```

2. Open terminal in download location

3. Run:
   ```bash
   nuget.exe install NetMQ -Version 4.0.1.13 -OutputDirectory packages
   ```

4. Find DLL at:
   ```
   packages\NetMQ.4.0.1.13\lib\net47\NetMQ.dll
   ```

5. Open cTrader → **Automate** → **Manage References** → **Add Local File**

6. Navigate to DLL path

7. Click **OK**

**Verify:** References panel shows `NetMQ 4.0.1.13`

---

## Troubleshooting

### Issue: "nuget.exe is not recognized"
**Solution:** Use Method 1 (automated script) — it downloads nuget.exe automatically

### Issue: "NetMQ package not found"
**Solution:**
1. Check internet connection
2. Try Method 2 (cTrader UI handles NuGet automatically)
3. If behind corporate proxy, configure nuget:
   ```bash
   nuget.exe config -set http_proxy=http://proxy.company.com:8080
   ```

### Issue: "Cannot find NetMQ.dll after installation"
**Solution:**
1. Check `packages\` directory for folder like `NetMQ.4.0.1.13`
2. Look inside: `lib\net47\NetMQ.dll`
3. If missing, delete `packages\` folder and re-run installer

### Issue: "cTrader says 'Reference already exists'"
**Solution:**
1. Click **Manage References** in cTrader
2. Find `NetMQ` in list
3. Click **Remove**
4. Re-add using any method above

### Issue: Script fails with "Execution Policy" error (PowerShell)
**Solution:**
```powershell
# Run PowerShell as Administrator, then:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Or run with bypass flag:
powershell -ExecutionPolicy Bypass -File install_netmq.ps1
```

### Issue: Python script fails to download nuget.exe
**Solution:**
1. Download nuget.exe manually from https://dist.nuget.org/win-x86-commandline/latest/nuget.exe
2. Place in `D:\JcampFX\cTrader_cBot\` directory
3. Re-run Python script

---

## Verification Checklist

After installation, verify:

- [ ] **Manage References** panel shows `NetMQ 4.0.1.13`
- [ ] cBot compiles without errors
- [ ] No "using NetMQ not found" errors
- [ ] Build output shows no missing assembly warnings

**Test Compilation:**

1. Create new cBot in cTrader
2. Add at top:
   ```csharp
   using NetMQ;
   using NetMQ.Sockets;
   ```
3. Click **Build** (Ctrl+B)
4. Should compile with no errors

If successful: ✅ NetMQ installed correctly!

---

## Advanced: Global Package Installation

To make NetMQ available to ALL cBots (not just one):

1. Copy DLL to cTrader global packages:
   ```
   %USERPROFILE%\Documents\cAlgo\Sources\Packages\NetMQ.4.0.1.13\
   ```

2. Create folder structure:
   ```
   NetMQ.4.0.1.13\
   └── lib\
       └── net47\
           └── NetMQ.dll
   ```

3. Restart cTrader

4. NetMQ will now appear in **Manage References** for all cBots

---

## Package Details

**Package:** NetMQ
**Version:** 4.0.1.13 (recommended for stability)
**Authors:** NetMQ
**License:** LGPL-3.0
**Dependencies:** System.Text.Json (included in .NET)
**Target Framework:** .NET Framework 4.7+ (cTrader compatible)

**Why NetMQ?**
- Pure .NET implementation (no native DLLs)
- Easy to deploy (single DLL)
- Active maintenance (updated 2023)
- Compatible with Python's pyzmq

**Fallback:** If NetMQ communication fails with Python, switch to `clrzmq` (native libzmq wrapper).

---

## Next Steps

After successful installation:

1. ✅ NetMQ installed
2. → Create cBot project (see README.md)
3. → Add JcampFX_Brain.cs code
4. → Test compilation
5. → Test ZMQ connection with Python

See **QUICK_START.md** for complete setup guide.
