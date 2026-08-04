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

**No BOT_ tasks currently exist** — all four first-attempt bots were deleted 2026-06-22.
When a new bot is deployed it gets a disabled `BOT_<NAME>` task; `SYS_STARTUP` uses
`schtasks /run` to start each BOT_ task sequentially. The SYS_* support tasks above stand
on their own.

---

## Why BOT_ Tasks Are Disabled

MT5's Python API cannot reliably select between running terminals via path.
Sequential startup via `SYS_STARTUP` prevents account mixing by starting
one bot at a time and waiting for connection confirmation before the next.

---

## `SYS_STARTUP` is IDEMPOTENT as of 2026-08-04 — it was not before

Running it used to start a second copy of everything already running, because the coordinator
launched each bot in `STARTUP_SEQUENCE` unconditionally and then launched `start_telegram.py`,
whose first act is to force-kill any running Telegram bot. So firing this task on a healthy box:

- left **TWO** `runner.py --bot <key>` processes — one account, one magic number, one strategy,
  both sizing a full position off the same setup, from a state neither could see; and
- **killed and rebuilt the Telegram bot**, after which SYS_MONITOR sent 🟢 *Telegram Bot
  Restarted* a minute later. That message is why a routine event read as a crash for weeks.

**Both were MEASURED on the live box on 2026-08-04, not reasoned about** — the duplicate bot was
found by running this task to verify the Telegram fix.

It is now safe to fire at any time: a running bot is skipped, a healthy Telegram is left alone,
and anything genuinely down is started. `runner.py` carries its own refusal as a backstop for
the paths this task does not own (the command center, the watchdog, a typed command).

⚠ **`SYS_TELEGRAM` deliberately still force-restarts.** That task's job is recovering a Telegram
bot that is alive but WEDGED, which is a state no "is it running" check can see.

---

## Install All Tasks (PowerShell)

```powershell
$tasks = @(
    "startup_coordinator_task.xml:SYS_STARTUP",
    "telegram_task.xml:SYS_TELEGRAM",
    "monitor_task.xml:SYS_MONITOR",
    "pnl_tracker_task.xml:SYS_PNLTRACKER",
    "reporter_task.xml:SYS_REPORTER"
)
foreach ($t in $tasks) {
    $parts = $t.Split(":")
    Copy-Item "C:\trading\algos\scheduler\$($parts[0])" "C:\temp\$($parts[0])"
    schtasks /create /tn $parts[1] /xml "C:\temp\$($parts[0])" /f
}
```

### No password — and never add one back

These tasks run as **SYSTEM** (`S-1-5-18` / `ServiceAccount` in each XML). Do **not** pass
`/ru trader /rp $pass`: it overrides the XML's principal and stores a password copy on every task.

That is not hypothetical. This guide told you to do exactly that, and when the VPS provider rotated
the `trader`/Administrator password around **30 May 2026**, all five tasks stopped launching —
**silently**. `schtasks /run` kept returning SUCCESS, the tasks kept reading `Ready`, and only
`Last Run Time` betrayed it by never advancing. Crash alerts were dead for two months and
`SYS_STARTUP` would not have restarted a single bot after a reboot. Found 2026-07-31.

**Verifying a task actually runs takes one command, and the exit code is not it:**

```powershell
schtasks /query /tn SYS_STARTUP /fo list /v | findstr /C:"Last Run Time"
```

When a new bot is added, install its `BOT_<NAME>` task the same way and disable it
(`schtasks /change /tn BOT_<NAME> /disable`) so only `SYS_STARTUP` fires it.

---

## Common Commands

```bash
# Check all tasks
ssh forexvps "schtasks /query /fo TABLE | findstr SYS_"
ssh forexvps "schtasks /query /fo TABLE | findstr BOT_"

# Run manually
ssh forexvps "schtasks /run /tn SYS_STARTUP"

# Stop ONE bot (never `taskkill /f /im python.exe` — that also kills the Telegram bot and
# both backtest agents, and is what left the live bot dead for three days on 2026-07-31)
ssh forexvps "wmic process where \"name='python.exe' and commandline like '%--bot mpc_sos_fade_demo%'\" call terminate"

# Restart everything
ssh forexvps "del C:\trading\algos\mt5_connect.lock 2>nul"
ssh forexvps "schtasks /run /tn SYS_STARTUP"
```

Note SYS_MONITOR restarts a dead bot by itself within ~60s (up to 3 tries), so a stop that is
not meant to stick will be undone. A deliberate stop from the Bots page or Telegram writes a
suppress key that the watchdog honours.
