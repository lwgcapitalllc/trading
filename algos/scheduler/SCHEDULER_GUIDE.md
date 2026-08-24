# Task Scheduler Guide

All tasks run as `trader` user on the VPS.

---

## Task List

| Task | Type | Trigger | Script |
|---|---|---|---|
| SYS_STARTUP | Boot | At startup | `bots/startup_coordinator.py` |
| SYS_TELEGRAM | Boot | At startup | `notifications/start_telegram.py` |
| SYS_MONITOR | Scheduled | Every 1 min | `notifications/monitor.py` |
| SYS_DEADMAN | Scheduled | Every 5 min | `notifications/deadman.py` |
| SYS_LOGBACKUP | Scheduled | Daily 00:30 | `tools/log_backup.py` |
| SYS_LOGREVIEW | Scheduled | Hourly | `notifications/log_review.py` |
| SYS_LEDGERSYNC | Scheduled | Hourly, :20 | `tools/ledger_sync.py --local --alert-on-failure` |

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

## `SYS_DEADMAN` — the one alert that does not come from this box

Every other task in this list reports FROM the VPS. So does the bot, and so does Telegram. That
means a dead box, a dead network or a dead Task Scheduler produces **silence**, and silence is also
what a healthy Sunday produces. Nothing in this suite could tell those apart until 2026-08-04.

`deadman.py` inverts it. It checks that each registered bot is running, stamping a fresh heartbeat,
and holding a live MT5 link — and pings an **external** service only when all of that is true. That
service expects the ping on a schedule and alerts you when it stops. The alerting lives off the box,
so it survives the box.

⚠ **The ping is CONDITIONAL on health, and that is the whole design.** A task that pings
unconditionally proves only that Task Scheduler is alive: a healthy system and a bot that died an
hour ago would send the identical green tick. That is the same broken-probe shape that let a dead
MT5 link read as a quiet market — stated the other way round. Never trust a positive result a
broken system can also produce.

⚠ **It sends a second, different signal on a detected problem** (`<url>/fail`, with the reasons in
the body), so a bot failure alerts immediately and by name while a box failure alerts on timeout.
Without that, both would be the same silence and the script would be throwing away a distinction it
is standing right next to.

⚠ **It never restarts anything.** `SYS_MONITOR` owns recovery. Two independent things issuing starts
for one bot is how you get two copies on one account — see the `SYS_STARTUP` section above.

⚠ **It is a separate task from `SYS_MONITOR` deliberately.** The watchdog is the bigger program and
the likelier to break; a dead-man's switch sharing its process shares its failure modes and stops
being an independent check.

**Setup — one step, and it is the only part that is not in git.** Create a free check at
healthchecks.io (period 5 minutes, grace 15), then put its ping URL in the git-ignored
`algos/credentials.json` as `deadman_url`. Point that check's notification at Telegram or email.
Until it is set the task runs, reports honestly, and sends nothing:

```bash
ssh forexvps "C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe C:\trading\algos\notifications\deadman.py --status"
ssh forexvps "C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe C:\trading\algos\notifications\deadman.py --dry-run"
```

**An unconfigured switch is a supported state, not an error.** A scheduled task that fails every
five minutes is a task everyone learns to ignore — and then the real failure is ignored with it.

⚠ **The URL is a SECRET.** Anyone holding it can send your pings for you and hold the alert
permanently green, which is worse than having no switch, because you would believe in it.

---

## Install All Tasks (PowerShell)

```powershell
$tasks = @(
    "startup_coordinator_task.xml:SYS_STARTUP",
    "telegram_task.xml:SYS_TELEGRAM",
    "monitor_task.xml:SYS_MONITOR",
    "deadman_task.xml:SYS_DEADMAN",
    "logbackup_task.xml:SYS_LOGBACKUP",
    "logreview_task.xml:SYS_LOGREVIEW",
    "ledgersync_task.xml:SYS_LEDGERSYNC"
)
foreach ($t in $tasks) {
    $parts = $t.Split(":")
    Copy-Item "C:\trading\algos\scheduler\$($parts[0])" "C:\temp\$($parts[0])"
    schtasks /create /tn $parts[1] /xml "C:\temp\$($parts[0])" /f
}
```

⚠ **This list and the table above were BOTH stale until 2026-08-24** — `SYS_LOGBACKUP` was in
the snippet and missing from the table, and `SYS_LOGREVIEW` was in neither, while both had been
running on the box for weeks. A roster is a CLAIM about what a rebuilt box comes back with, and
the one thing a stale roster cannot do is tell you what it left out. **`scripts/bootstrap_vps.ps1`
is what actually registers them; this file is a copy for a human, so check it against that list
rather than against the box.**

🔴 **`SYS_LEDGERSYNC` is the only task here that needs a SECRET, and a rebuild does not restore
it.** `github_token` lives in `algos/credentials.json`, which is git-ignored. Without it the task
still runs, still commits, and simply never pushes — so the record stops leaving the box while
every green tick stays green. Put the token back as part of the rebuild.

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
