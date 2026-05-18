# Scheduler Guide
**Folder:** `scheduler/`

All Windows Task Scheduler XML files. One XML per task.

---

## Files

| XML File | Task Name | Prefix | Trigger | What It Runs |
|---|---|---|---|---|
| `smc_trend_task.xml` | `BOT_SMC_TREND` | BOT_ | At startup | bot_smc_trend.py |
| `mean_reversion_task.xml` | `BOT_MEAN_REVERSION` | BOT_ | At startup | bot_mean_reversion.py |
| `scalper_task.xml` | `BOT_SCALPER` | BOT_ | At startup | bot_scalper.py |
| `fft_task.xml` | `BOT_FFT` | BOT_ | At startup | bot_fft.py |
| `futures_acct1_task.xml` | `BOT_FUTURES_ACCT1` | BOT_ | At startup | bot_futures.py |
| `startup_coordinator_task.xml` | `SYS_STARTUP` | SYS_ | At boot (+10s delay) | startup_coordinator.py |
| `telegram_task.xml` | `SYS_TELEGRAM` | SYS_ | At startup | start_telegram.py |
| `reporter_task.xml` | `SYS_REPORTER` | SYS_ | Daily 21:00 UTC (4pm CDT) | reporter.py |
| `monitor_task.xml` | `SYS_MONITOR` | SYS_ | Every 1 minute | monitor.py |

**Prefix convention:**
- `BOT_` — trading bots (persistent, run 24/7)
- `SYS_` — system jobs (telegram is persistent, reporter/monitor are scheduled)

---

## Key Settings (all tasks)

All tasks are configured consistently:
- `DisallowStartIfOnBatteries: false` — VPS has no battery
- `StopIfGoingOnBatteries: false` — never stops
- `ExecutionTimeLimit: PT0S` — no time limit (bots run indefinitely)
- `RunLevel: HighestAvailable` — elevated privileges
- `MultipleInstancesPolicy: IgnoreNew` — no duplicate instances
- `WorkingDirectory: C:\algos\bots` — correct for imports

**SYS_TELEGRAM** uses `start_telegram.py` as the launcher — this kills any
existing telegram_bot.py process first to prevent duplicate instances.

**SYS_STARTUP** is the sequential bot startup coordinator. It starts bots
one at a time, waiting for each to confirm MT5 connection before starting
the next. This is the only reliable way to prevent account mixing when
multiple MT5 terminals are running simultaneously. Always use SYS_STARTUP
instead of starting individual BOT_ tasks directly.

---

## Installing All Tasks (fresh setup)

Run in PowerShell on VPS as Administrator:

```powershell
$tasks = @(
    @{file="smc_trend_task.xml";      name="BOT_SMC_TREND"},
    @{file="mean_reversion_task.xml"; name="BOT_MEAN_REVERSION"},
    @{file="scalper_task.xml";        name="BOT_SCALPER"},
    @{file="fft_task.xml";            name="BOT_FFT"},
    @{file="startup_coordinator_task.xml"; name="SYS_STARTUP"},
    @{file="telegram_task.xml";       name="SYS_TELEGRAM"},
    @{file="reporter_task.xml";       name="SYS_REPORTER"},
    @{file="monitor_task.xml";        name="SYS_MONITOR"}
)
foreach ($t in $tasks) {
    Copy-Item "C:\algos\scheduler\$($t.file)" "C:\temp\$($t.file)"
    schtasks /create /tn $t.name /xml "C:\temp\$($t.file)" /ru trader /rp "312MXFjt7Q8Zoec"
    Write-Host "Installed: $($t.name)"
}
```

---

## Verifying Tasks

```bash
# List all algo tasks
ssh forexvps "schtasks /query /fo TABLE | findstr BOT_"
ssh forexvps "schtasks /query /fo TABLE | findstr SYS_"

# Check a specific task
ssh forexvps "schtasks /query /fo LIST /tn BOT_SMC_TREND /v"
```

---

## Manual Task Control

```bash
ssh forexvps "schtasks /run /tn BOT_SMC_TREND"
ssh forexvps "schtasks /end /tn BOT_SMC_TREND"
ssh forexvps "schtasks /delete /tn BOT_SMC_TREND /f"
```

---

## Recreating a Task From Scratch

```powershell
schtasks /delete /tn "BOT_SMC_TREND" /f
Copy-Item C:\algos\scheduler\smc_trend_task.xml C:\temp\smc_trend_task.xml
schtasks /create /tn "BOT_SMC_TREND" /xml "C:\temp\smc_trend_task.xml" /ru trader /rp "312MXFjt7Q8Zoec"
```

---

## Reporter DST Update (November)

When clocks fall back in November, update `reporter_task.xml`:

Change `21:00:00` → `22:00:00` in `<StartBoundary>`, then reinstall:
```powershell
schtasks /delete /tn "SYS_REPORTER" /f
Copy-Item C:\algos\scheduler\reporter_task.xml C:\temp\reporter_task.xml
schtasks /create /tn "SYS_REPORTER" /xml "C:\temp\reporter_task.xml" /ru trader /rp "312MXFjt7Q8Zoec"
```
