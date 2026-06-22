# Task Scheduler Guide

All tasks run as `trader` user on the VPS.

---

## Task List

| Task | Type | Trigger | Script |
|---|---|---|---|
| SYS_STARTUP | Boot | At startup | `bots/startup_coordinator.py` |
| SYS_TELEGRAM | Boot | At startup | `notifications/start_telegram.py` |
| SYS_MONITOR | Scheduled | Every 1 min | `notifications/monitor.py` |
| SYS_PNLTRACKER | Scheduled | Every 1 min | `notifications/pnl_tracker.py` |
| SYS_REPORTER | Scheduled | Daily 4pm CT | `notifications/reporter.py` |
| BOT_MEAN_REVERSION | **Disabled** | (manual only) | `bots/bot_mean_reversion.py` |

**Important**: BOT_ tasks are disabled. Only `SYS_STARTUP` fires bots.
`SYS_STARTUP` uses `schtasks /run` to start each BOT_ task sequentially.

---

## Why BOT_ Tasks Are Disabled

MT5's Python API cannot reliably select between running terminals via path.
Sequential startup via `SYS_STARTUP` prevents account mixing by starting
one bot at a time and waiting for connection confirmation before the next.

---

## Install All Tasks (PowerShell)

```powershell
$pass = "<vps-trader-password>"
$tasks = @(
    "startup_coordinator_task.xml:SYS_STARTUP",
    "telegram_task.xml:SYS_TELEGRAM",
    "monitor_task.xml:SYS_MONITOR",
    "pnl_tracker_task.xml:SYS_PNLTRACKER",
    "reporter_task.xml:SYS_REPORTER",
    "mean_reversion_task.xml:BOT_MEAN_REVERSION"
)
foreach ($t in $tasks) {
    $parts = $t.Split(":")
    Copy-Item "C:\trading\algos\scheduler\$($parts[0])" "C:\temp\$($parts[0])"
    schtasks /create /tn $parts[1] /xml "C:\temp\$($parts[0])" /ru trader /rp $pass
}
schtasks /change /tn BOT_MEAN_REVERSION /disable
```

---

## Common Commands

```bash
# Check all tasks
ssh forexvps "schtasks /query /fo TABLE | findstr SYS_"
ssh forexvps "schtasks /query /fo TABLE | findstr BOT_"

# Run manually
ssh forexvps "schtasks /run /tn SYS_STARTUP"

# Restart everything
ssh forexvps "del C:\trading\algos\mt5_connect.lock 2>nul && taskkill /f /im python.exe"
sleep 3
ssh forexvps "schtasks /run /tn SYS_STARTUP"
```
