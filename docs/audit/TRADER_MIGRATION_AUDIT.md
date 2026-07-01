# Trader Migration Audit — Administrator → trader

> **Stale entries flagged 2026-06-22.** Several files referenced below were deleted in the
> suite cutdown and no longer exist — ignore their rows when running this audit:
> - Scheduler XMLs `smc_trend_task.xml`, `scalper_task.xml`, `fft_task.xml`,
>   `mean_reversion_task.xml`, and `backup_task.xml`. All four first-attempt bots (SMC Trend,
>   Scalper, FFT, and Mean Reversion) were deleted — Mean Reversion was also removed 2026-06-22,
>   so its task XML is gone too — along with the VPS data-backup feature.
> - The backup scripts `scripts/backup.py` and `scripts/nt8_backup.py` (the `backups` orphan
>   branch and twice-daily backup task are gone), so the `nt8_backup.py` class (b) fallback note
>   and the "Restore Data from Backup" / profile-note steps no longer apply.
> - `algos/docs/SETUP.md` — deleted in commit `f5d56db` (before the bot-suite cutdown), and
>   nothing replaced its install-prereq content. **Step 2b** (SETUP.md prerequisites edit) and
>   **Step 3** (profile note to add to SETUP.md) below target a file that no longer exists — they
>   are kept here only as a record of the intended guidance in case a new setup guide is written.
>
> The remaining Administrator→trader actions (Python path, `backtest_config.json`, `setup_agent_task.py`,
> `bots.py`, `test_integration.py`, the surviving scheduler XMLs, and the bootstrap scripts) still stand.

**Context:** This VPS was provisioned with only a `trader` login (a local admin account).
Over time, software installed to default "current user" locations that landed under the
built-in Administrator profile by accident — Python is at
`C:\Users\Administrator\AppData\...`, and NinjaTrader's data folder is under
`C:\Users\Administrator\Documents\NinjaTrader 8`. The intended design is for everything
to run under `trader`. We are NOT moving anything on the live VPS. We are making the
repo, scripts, and docs assume `trader` as the single profile so the next rebuild/migration
places everything under trader cleanly.

---

## Inventory — every "Administrator" hit in the repo, classified

### Class (a) — Run-as account or profile path that should become `trader`

| File | Line | Current value | Action |
|---|---|---|---|
| `algos/docs/SETUP.md` | 10 | `C:\Users\Administrator\AppData\Local\Programs\Python\Python311\` | Change prereq guidance to install Python all-users at `C:\Python311` |
| `algos/nt8/backtest_config.json` | 3 | `"vps_user": "Administrator"` | → `"trader"` |
| `algos/nt8/setup_agent_task.py` | 10 | docstring: `Administrator logs in via RDP` | → `trader logs in via RDP` |
| `algos/nt8/setup_agent_task.py` | 58 | comment: `fires when Administrator logs in` | → `trader logs in` |
| `algos/nt8/setup_agent_task.py` | 61 | comment: `Omit /ru so it defaults to current user (Administrator)` | Add explicit `/ru trader` to the schtasks command instead of omitting /ru |
| `algos/scheduler/backup_task.xml` | 37 | `C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe` | → `C:\Python311\python.exe` |
| `algos/scheduler/fft_task.xml` | 32 | same Administrator python path | → `C:\Python311\python.exe` |
| `algos/scheduler/mean_reversion_task.xml` | 32 | same | → `C:\Python311\python.exe` |
| `algos/scheduler/monitor_task.xml` | 32 | same | → `C:\Python311\python.exe` |
| `algos/scheduler/pnl_tracker_task.xml` | 32 | same | → `C:\Python311\python.exe` |
| `algos/scheduler/reporter_task.xml` | 30 | same | → `C:\Python311\python.exe` |
| `algos/scheduler/scalper_task.xml` | 32 | same | → `C:\Python311\python.exe` |
| `algos/scheduler/smc_trend_task.xml` | 32 | same | → `C:\Python311\python.exe` |
| `algos/scheduler/startup_coordinator_task.xml` | 28 | same | → `C:\Python311\python.exe` |
| `algos/scheduler/telegram_task.xml` | 26 | same | → `C:\Python311\python.exe` |
| `command-center/backend/routers/bots.py` | 603 | `_PYTHON_EXE = r"C:\Users\Administrator\AppData\...\python.exe"` | → `C:\Python311\python.exe` |
| `command-center/backend/tests/test_integration.py` | 136 | `r"C:/Users/Administrator/Documents/NinjaTrader 8/..."` | → `C:/Users/trader/Documents/NinjaTrader 8/...` |

---

### Class (b) — Intentional resolver fallback (keep both, trader already first — no reorder needed)

| File | Lines | What it does | Status |
|---|---|---|---|
| `algos/scripts/nt8_backup.py` | 67–69 | `CANDIDATE_USER_DIRS` — trader path index 0, Administrator path index 1 | **Already correct order.** No change. |
| `scripts/bootstrap_ninjatrader.ps1` | 103–104 | `$candidates` array — trader first, Administrator second | **Already correct order.** No change. |
| `scripts/bootstrap_ninjatrader.ps1` | 131–133 | `Resolve-Python` fallback — `$env:LOCALAPPDATA` before Administrator path | Add `C:\Python311` as the first candidate before `$env:LOCALAPPDATA` so all-users install wins |
| `scripts/bootstrap_vps.ps1` | 196–205 | `Resolve-Python` — checks `C:\Python311` first, then current user, then Administrator last | **Already correct order.** No change. |

---

### Class (c) — Unrelated — Windows security API, UAC prose, or architectural comment — leave alone

| File | Line | Hit | Why leave alone |
|---|---|---|---|
| `scripts/bootstrap_ninjatrader.ps1` | 125 | `[Security.Principal.WindowsBuiltInRole]::Administrator` | .NET enum value for admin-elevation check — not a profile reference |
| `scripts/bootstrap_vps.ps1` | 182 | `[Security.Principal.WindowsBuiltInRole]::Administrator` | Same |
| `algos/docs/SETUP.md` | 133 | `Run in PowerShell as Administrator:` | Means "elevated shell" (Windows UAC), not the Administrator account |
| `algos/nt8/run_all.py` | 127 | `Administrator's interactive RDP session` | Explains the SSH→Task Scheduler bridge (architectural why); will be naturally accurate once trader is the RDP login |

---

## Step 2 — Edits to make (approved scope)

### 2a — All 10 scheduler XMLs
**Find** (in the `<Command>` element of every XML under `algos/scheduler/`):
```
C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe
```
**Replace with:**
```
C:\Python311\python.exe
```
All 10 files are identical in this regard.

---

### 2b — algos/docs/SETUP.md prerequisites
**Current (line 10):**
```
- Python 3.11 installed at `C:\Users\Administrator\AppData\Local\Programs\Python\Python311\`
```
**Replace with:**
```
- Python 3.11 installed **for all users** at `C:\Python311\` — use the silent all-users
  installer so Python is profile-independent:
      py311.exe /quiet InstallAllUsers=1 PrependPath=1 TargetDir=C:\Python311
  (Do NOT install to a per-user AppData path — that ties the system to one Windows account.)
```

---

### 2c — backtest_config.json
**Current (line 3):**
```json
"vps_user": "Administrator",
```
**Replace with:**
```json
"vps_user": "trader",
```

---

### 2d — setup_agent_task.py
Three changes:

1. **Docstring (line 10):** `Administrator logs in via RDP` → `trader logs in via RDP`

2. **Comment (line 58):** `# /sc onlogon  — fires when Administrator logs in` → `trader logs in`

3. **Comment + schtasks command (lines 61–66):** Remove "Omit /ru" comment and add `/ru trader`
to the `task_cmd` string. Current:
```python
    # /sc onlogon  — fires when Administrator logs in
    # /rl HIGHEST  — run with highest privileges
    # /f           — overwrite if task already exists
    # Omit /ru so it defaults to current user (Administrator)
    print(f"\nRegistering Task Scheduler task '{TASK_NAME}'...")
    task_cmd = (
        f"schtasks /create /tn {TASK_NAME} "
        f"/tr \"python {AGENT_WIN}\" "
        f"/sc onlogon /rl HIGHEST /f"
    )
```
Replace with:
```python
    # /sc onlogon  — fires when trader logs in via RDP
    # /ru trader   — run as the trader account (the VPS's single operating account)
    # /rl HIGHEST  — run with highest privileges
    # /f           — overwrite if task already exists
    print(f"\nRegistering Task Scheduler task '{TASK_NAME}'...")
    task_cmd = (
        f"schtasks /create /tn {TASK_NAME} "
        f"/tr \"python {AGENT_WIN}\" "
        f"/sc onlogon /ru trader /rl HIGHEST /f"
    )
```

---

### 2e — command-center/backend/routers/bots.py
**Current (line 603):**
```python
_PYTHON_EXE  = r"C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe"
```
**Replace with:**
```python
_PYTHON_EXE  = r"C:\Python311\python.exe"
```

---

### 2f — command-center/backend/tests/test_integration.py
**Current (lines 135–137):**
```python
    CS_PATH = (
        r"C:/Users/Administrator/Documents/NinjaTrader 8"
        r"/bin/Custom/Strategies/ORB_LucidFlex.cs"
    )
```
**Replace with:**
```python
    CS_PATH = (
        r"C:/Users/trader/Documents/NinjaTrader 8"
        r"/bin/Custom/Strategies/ORB_LucidFlex.cs"
    )
```

---

### 2g — scripts/bootstrap_ninjatrader.ps1 — Resolve-Python
**Current (lines 128–136):**
```powershell
function Resolve-Python {
    if ($PythonExe -and (Test-Path $PythonExe)) { return $PythonExe }
    $c = Get-Command python -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    foreach ($p in @("$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
                     'C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe')) {
        if (Test-Path $p) { return $p }
    }
    return $null
}
```
**Replace with:**
```powershell
function Resolve-Python {
    if ($PythonExe -and (Test-Path $PythonExe)) { return $PythonExe }
    # Prefer a profile-independent (all-users) install — the target layout going forward.
    foreach ($shared in @('C:\Python311\python.exe', 'C:\Program Files\Python311\python.exe')) {
        if (Test-Path $shared) { return $shared }
    }
    $c = Get-Command python -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    # Per-user fallbacks: trader's profile first, then Administrator (legacy).
    foreach ($p in @("$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
                     'C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe')) {
        if (Test-Path $p) { return $p }
    }
    return $null
}
```

---

## Step 3 — Profile note to add to algos/docs/SETUP.md

Add this paragraph in the "Restore Data from Backup" section (§5), just before the restore
code block, under a `### Profile note` subheading:

```
### Profile note

The live VPS currently has Python and NinjaTrader's user-data folder under the built-in
`Administrator` profile by historical accident — Python landed at
`C:\Users\Administrator\AppData\Local\Programs\Python\Python311\` and NT8's workspace/
template/log data is at `C:\Users\Administrator\Documents\NinjaTrader 8`. This is harmless
while the system is running (the `trader` account is a local admin, so it can read and
execute both locations). A rebuild done as `trader` — following these scripts — will install
Python to `C:\Python311` (all-users, profile-independent) and NT8's user data will live
under `C:\Users\trader\Documents\NinjaTrader 8`. The `Administrator` path is kept as a
legacy fallback in the NT8 user-dir resolvers (`nt8_backup.py` and
`bootstrap_ninjatrader.ps1`) so the backup system continues to work on the current VPS
without any changes.
```

---

## Step 4 — Final verification grep (run after all edits)

```bash
grep -rni "Users\\\\Administrator\|Users/Administrator" \
  algos/docs algos/markets algos/scheduler command-center scripts \
  --include="*.py" --include="*.md" --include="*.ps1" --include="*.xml" --include="*.json"
```

Expected remaining hits after edits:
- `algos/scripts/nt8_backup.py` — intentional class (b) fallback
- `scripts/bootstrap_ninjatrader.ps1` — intentional class (b) fallback (in both `$candidates` and `Resolve-Python`)
- `scripts/bootstrap_vps.ps1` — intentional class (b) last-resort fallback in `Resolve-Python`
- This audit doc itself

Any other hit is a miss that needs fixing.
