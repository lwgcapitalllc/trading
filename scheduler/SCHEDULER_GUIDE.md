# Scheduler Guide
**Folder:** `scheduler/`

All Windows Task Scheduler XML files live here.
One XML per task — bots, reporter, monitor, and telegram bot.

---

## Files

| File | Task Name | Trigger | What It Runs |
|---|---|---|---|
| `bot1_task.xml` | `FX_XAUUSD_Bot1` | At startup | Bot 1 SMC Trend |
| `bot2_task.xml` | `FX_XAUUSD_Bot2` | At startup | Bot 2 Mean Reversion |
| `bot3_task.xml` | `FX_XAUUSD_Scalper` | At startup | Bot 3 EMA Scalper |
| `bot5_task.xml` | `FX_XAUUSD_Bot5_FFT` | At startup | Bot 5 FFT Strategy |
| `reporter_task.xml` | `ALGO_Daily_Reporter` | Daily 21:00 UTC (4pm CDT) | reporter.py |
| `monitor_task.xml` | `ALGO_Monitor` | Every 5 minutes | monitor.py |
| `telegram_bot_task.xml` | `ALGO_Telegram_Bot` | At startup | telegram_bot.py |

---

## Key Settings (all tasks)

All tasks are configured consistently:
- `DisallowStartIfOnBatteries: false` — runs on VPS (no physical battery)
- `StopIfGoingOnBatteries: false` — never stops due to power
- `ExecutionTimeLimit: PT0S` — no time limit (bots run indefinitely)
- `RunLevel: HighestAvailable` — elevated privileges
- `MultipleInstancesPolicy: IgnoreNew` — won't start a second copy if already running
- `WorkingDirectory: C:\algos\bots` — correct working dir for imports

---

## Installing a Task

```powershell
# 1. Copy XML to temp (required encoding step)
Copy-Item C:\algos\scheduler\bot1_task.xml C:\temp\bot1_task.xml

# 2. Install
schtasks /create /tn "FX_XAUUSD_Bot1" /xml "C:\temp\bot1_task.xml" /ru trader /rp "312MXFjt7Q8Zoec"
```

**Install all bot tasks at once:**
```powershell
$tasks = @(
    @{file="bot1_task.xml"; name="FX_XAUUSD_Bot1"},
    @{file="bot2_task.xml"; name="FX_XAUUSD_Bot2"},
    @{file="bot3_task.xml"; name="FX_XAUUSD_Scalper"},
    @{file="bot5_task.xml"; name="FX_XAUUSD_Bot5_FFT"}
)
foreach ($t in $tasks) {
    Copy-Item "C:\algos\scheduler\$($t.file)" "C:\temp\$($t.file)"
    schtasks /create /tn $t.name /xml "C:\temp\$($t.file)" /ru trader /rp "312MXFjt7Q8Zoec"
    Write-Host "Installed: $($t.name)"
}
```

**Install all notification tasks:**
```powershell
$tasks = @(
    @{file="reporter_task.xml";     name="ALGO_Daily_Reporter"},
    @{file="monitor_task.xml";      name="ALGO_Monitor"},
    @{file="telegram_bot_task.xml"; name="ALGO_Telegram_Bot"}
)
foreach ($t in $tasks) {
    Copy-Item "C:\algos\scheduler\$($t.file)" "C:\temp\$($t.file)"
    schtasks /create /tn $t.name /xml "C:\temp\$($t.file)" /ru trader /rp "312MXFjt7Q8Zoec"
    Write-Host "Installed: $($t.name)"
}
```

---

## Verifying Tasks

**List all installed algo tasks:**
```bash
ssh forexvps "schtasks /query /fo TABLE | findstr -i algo"
ssh forexvps "schtasks /query /fo TABLE | findstr -i fx_xauusd"
```

**Check a specific task:**
```bash
ssh forexvps "schtasks /query /fo LIST /tn FX_XAUUSD_Bot1 /v" | grep -E "Status|Power|Start In|Task To Run"
```

Expected output for a healthy task:
```
Task To Run:   C:\...\python.exe C:\algos\bots\launcher.py --bot bot1 ...
Start In:      C:\algos\bots
Power Management: (blank — battery restrictions off)
Status:        Running
```

---

## Manual Task Control

```bash
# Start a task manually
ssh forexvps "schtasks /run /tn FX_XAUUSD_Bot1"

# Stop a task
ssh forexvps "schtasks /end /tn FX_XAUUSD_Bot1"

# Delete a task (to reinstall)
ssh forexvps "schtasks /delete /tn FX_XAUUSD_Bot1 /f"
```

---

## Recreating a Task From Scratch

If a task gets corrupted or needs to be rebuilt, use the XML from this
folder. The XML contains all settings including the correct user SID,
working directory, and power management flags.

```powershell
schtasks /delete /tn "FX_XAUUSD_Bot1" /f
Copy-Item C:\algos\scheduler\bot1_task.xml C:\temp\bot1_task.xml
schtasks /create /tn "FX_XAUUSD_Bot1" /xml "C:\temp\bot1_task.xml" /ru trader /rp "312MXFjt7Q8Zoec"
```

---

## Reporter DST Update (November)

When clocks fall back in November, update `reporter_task.xml`:

Change:
```xml
<StartBoundary>2026-01-01T21:00:00</StartBoundary>
```
To:
```xml
<StartBoundary>2026-01-01T22:00:00</StartBoundary>
```

Then reinstall the task. This keeps the 4pm Texas delivery time accurate
through daylight saving transitions.
