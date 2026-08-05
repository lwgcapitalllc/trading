# Notifications Guide

---

## Credentials — where they live (changed 2026-07-30)

**No file in this repo contains a Telegram token, and none may.** The old token was pasted
into six files and committed; it was revoked, and the constants were replaced by a lookup.

`algos/shared/credentials.py` is the single VPS-side resolver. Order: **environment variable**
(`LWG_TELEGRAM_TOKEN` / `LWG_TELEGRAM_CHAT_ID` / `LWG_TELEGRAM_ADMIN_CHAT_ID`), then
**`algos/credentials.json`** — git-ignored, per machine, never travels. Copy
`algos/credentials.template.json` (which is in git and holds only the shape) and fill it in.

The command center resolves the same values from the same FILE via its own
`services/notify.py`, deliberately without importing this module — `command-center/` and
`algos/` are independent by repo rule, so a shared data file is the allowed seam and a shared
import is not.

**Setup on a new machine or after a token rotation:**

```bash
cp algos/credentials.template.json algos/credentials.json
# fill in telegram_token, telegram_chat_id, telegram_admin_chat_id
```

Getting the two chat ids: add the bot to the group and send a message, then read `chat.id`
from `https://api.telegram.org/bot<TOKEN>/getUpdates`. The group id is negative, a personal
id positive.

**Nothing raises when it is missing.** Every sender treats "no credentials" as "drop the
message and say so once". A bot must not refuse to trade because a notification channel is
unset — and it must not crash at 2am for it either.

---

## Telegram Delivery Model

All notifications — scheduled alerts, command replies, and the startup ping — go to the
**LWG Capital Algos Notifications** group chat (`telegram_chat_id`) **by default**. A live bot
can override both the destination and the sender identity in its own instance config; see
*Routing is per bot* below.

`telegram_admin_chat_id` is loaded by every notifier as a fallback definition but is no longer
the send destination for any message.

**Authorization** uses each sender's personal Telegram **user ID** (`message.from.id`), not
the group chat ID. `users.json` lists users by their personal user ID. Anyone in the group
who is not in `users.json` gets "not authorized".

---

## Components

### Notification Architecture — Event-Driven

Bot status notifications are event-driven, not polling-based:

| Event | Source | Latency |
|---|---|---|
| Bot starts (any cause) | Bot calls `notify.send_telegram` at top of `run()` | Immediate |
| Start/stop/restart from command center | command-center bots router sends Telegram notification | Immediate |
| Stop/restart from Telegram command | Result message returned to user via `/confirm` flow | Immediate |
| Bot crashes unexpectedly | `monitor.py` crash detector (every 1 min) | ≤ 1 min |
| Bot comes back online after crash | `monitor.py` (same cycle as crash detection) | ≤ 1 min |
| Telegram bot goes down | `monitor.py` watchdog (every 1 min) | ≤ 1 min |

`shared/notify.py` is the single Telegram helper for VPS-side components. **The token half of the 2026-07-06 refactor note is DONE (2026-07-30)** — no script holds a token any more; every script here resolves its own through `shared/credentials.py`. Mac-side Telegram calls go through the command-center bots router, which delegates to `services/notify.py`.

**Routing is per bot, and the default is shared.** `send_telegram(text, chat_id="", token_key="")`:

- `chat_id` — where this message goes. Empty = the shared group above. A live bot passes its own `telegram_chat_id` from its instance config, so a demo gold bot and a funded FX bot need not share one feed.
- `token_key` — which Telegram bot it appears to come from. It NAMES a key in `credentials.json` (`telegram_token_bleg`), never the token, so an instance config never holds a secret. Empty = the shared bot.

A named token that is missing falls back to the default one and prints the key once. That is deliberate: the wrong sender identity is recoverable, a silently dropped trade alert is not. Expect the send to then fail at Telegram anyway — **a bot can only post to a chat it has been added to** — but it fails loudly with the reason printed, which is the point.

### monitor.py (SYS_MONITOR — every 1 min)
Bot availability and heartbeat monitor. Handles availability alerting and Telegram bot watchdog only.
There are no P&L threshold alerts anywhere any more — see the deleted-jobs note below.
Persists state in `monitor_state.json` across runs.

**Crash alerting with intentional-stop suppression:**
When a bot goes offline, monitor.py checks `C:/trading/algos/stop_suppress.json` before alerting.
If the bot's suppress key is in the file, the stop was intentional — no alert is sent and no
"Bot Online" alert fires when it restarts. The key is consumed on first read (one-shot).

Suppress keys: `fft`, `scalper`, `smc`, `reversion`.

The suppress file is written by:
- command-center bots router — writes `stop_suppress.json` via SSH before stopping a bot
- `telegram_bot.py` — locally before executing `/stop`, `/restart`, `/emergency` commands

**`/restart` full-restart sequence (all bots):**
1. Suppress offline alerts for all bots (`stop_suppress.json`) so the planned stop doesn't trigger false crash alerts.
2. Stop all Task Scheduler task entries (`schtasks /end`) for each bot.
3. Force-kill all bot Python processes by script name via `wmic … call terminate` — `schtasks /end` stops the task entry but does not kill the running process.
4. Poll (max 15s) until all bot processes are confirmed gone.
5. Start the `SYS_STARTUP` coordinator, which starts bots sequentially.

Individual `/restart <bot>` follows the same terminate-then-start pattern for the single bot.

🔴 **THE TELEGRAM BOT WAS NEVER CRASHING — IT WAS BEING KILLED, AND THIS WATCHDOG'S OWN
"restarted" MESSAGE IS WHAT MADE IT LOOK LIKE A CRASH (found 2026-08-04).** Aaron had been
watching it stop and come back for weeks. **Evidence it never faulted: 4,764 Windows Application
events over 14 days, none mentioning python, and no crash event (1000/1001/1026) since 26 July.**
A `taskkill /f` leaves no event behind; a real crash does. Four things were killing it, three now
fixed: the Telegram bot's own `/emergency` command ran `taskkill /f /im python.exe` and **killed
itself** (which is also why its confirmation reply never arrived), the command center's Stop button
did the same, and three docs told you to run it by hand. The fourth was the routine one and was
BY DESIGN: **`startup_coordinator.py` ended by launching `start_telegram.py` unconditionally, and
that script force-kills any running telegram_bot.py before starting a fresh one** — so every
Start/Restart from the Bots page killed the alert channel, and a minute later this watchdog sent
🟢 *Telegram Bot Restarted*. The coordinator now skips a healthy Telegram
(`start_telegram_if_needed`). ⚠ **`SYS_TELEGRAM` deliberately keeps the force-restart** — that
task's job is recovering a bot that is alive but WEDGED, and it is what this watchdog fires below.
**The standing lesson: an alert channel that cries wolf stops being read, and a routine event
dressed as a failure costs exactly as much trust as a missed one.**

**Alerts sent:**
- 🚨 Bot Offline — unexpected stop (suppressed for intentional stops)
- 🟢 Bot Online — bot came back after a crash (suppressed if stop was intentional)
- ⚠️ Loop Stalled — process alive but heartbeat missing > 5 min. Writes `status = "stalled"` to bot_state.json.
- 🟢 Loop Recovered — heartbeat resumed after a stall. Writes `status = "running"` to bot_state.json.
- 🟢 Telegram Bot Restarted — auto-restart succeeded
- 🚨 Critical — Telegram Bot Down — 3 restarts failed

⚠ **The bot's own alerts do NOT come from here** — see *Alerts the RUNNER sends* below. Do not add
a duplicate for one of those: two alerts for one event is how a channel stops being read.

### Alerts the RUNNER sends (algos/live/runner.py) — added 2026-08-04

`monitor.py` watches the bot from OUTSIDE and can only see what a process list and a state file
show. Two conditions are invisible from there and are alerted by the bot itself:

- ⚠️ **Lost its MT5 connection** — the terminal stopped answering this process. Sent **ONCE per
  outage**, not per poll (at a 10s poll that would be 6 messages a minute for as long as it lasts,
  which trains you to ignore the channel).
- ✅ **Reconnected after N min** — the link came back and the engines were re-warmed.

**Why the watchdog cannot raise these.** MetaTrader auto-updates and restarts itself, taking a
running bot's IPC handle with it (measured 2026-08-04: 50 minutes blind across an open session).
The bot stays ALIVE and keeps stamping its heartbeat, so from `monitor.py`'s side it is indistinguishable
from a healthy bot — `wmic` lists it, the heartbeat is fresh, and the stall check correctly does not
fire. Only the process itself can tell, by asking the terminal a question. ⚠ **The heartbeat is
still stamped while blind, deliberately**: dropping it would raise ⚠️ Loop Stalled, which describes a
different failure and would restart a process whose problem is not the process.

`bot_state.json` carries **`mt5_link`** alongside the heartbeat, which is what the Bots page renders
as a `No MT5 link` chip. A blank balance is not a diagnosis — before this field, it was the only
visible symptom anywhere in the system.

### deadman.py (SYS_DEADMAN — every 5 min) — added 2026-08-04

**Every other entry on this page is sent BY the VPS.** The bot's own alerts, the watchdog, the P&L
tracker, the daily report — all of them need the box alive and networked to reach you. So the one
failure this suite could never report is the one where the box or its network dies, because that
produces **silence**, and silence is also what a healthy Sunday produces.

`deadman.py` inverts the direction. It checks the things that must be true and pings an **external**
service only when they all are:

| Checked | Failure reported |
|---|---|
| the process is running | `<bot>: process is not running` |
| the heartbeat is < 5 min old | `<bot>: heartbeat is Ns old (stalled)` |
| `mt5_link` is not `false` | `<bot>: MT5 link is down` |
| `wmic` answered at all | `cannot read the process list` |
| `bot_state.json` is readable | `<bot>: bot_state.json cannot be read` |

The external service expects that ping on a schedule and alerts YOU when it stops. **The alerting
lives off the box, which is the entire point** — a dead VPS, a dead network, a dead Task Scheduler
and a dead Python all produce the same outcome: you find out.

**Two signals, and the difference is deliberate.**

- **ping** — sent only when everything checks out. Missing pings mean *nothing on that box can talk
  to me*, and the receiving end cannot say why, because it does not know.
- **`/fail`** — sent when the script RUNS and finds a problem, with the reasons in the body. The box
  is fine, the fault is named, and you hear at once instead of after the grace period.

Without the second, a dead bot and a dead box would be the same silence.

⚠ **The ping is CONDITIONAL on health and must stay that way.** An unconditional ping proves only
that Task Scheduler is alive — a healthy system and a bot that died an hour ago would send the same
green tick. This is the 2026-08-04 probe lesson from the other side: never trust a POSITIVE result a
broken system can also produce.

⚠ **`mt5_link` is read `is False`, never falsy.** `None` means the bot has not been asked yet (a
fresh start, or a build predating the field) and is not a dead terminal — the same three-state
contract the Bots page and the health strip follow.

⚠ **It never restarts anything.** `monitor.py` owns recovery, and two independent things issuing
starts for one bot is how a book gets doubled.

**Configuration:** `deadman_url` in the git-ignored `algos/credentials.json` (or `LWG_DEADMAN_URL`).
Unset is supported — the script says so and exits 0, because a task that fails every five minutes is
one everybody learns to ignore. `--status` reports whether it is configured; `--dry-run` runs the
checks and sends nothing. ⚠ **The URL is a secret**: anyone holding it can send your pings and keep
the alert green forever, which is worse than no switch, because you would trust it.

✅ **ARMED on the live VPS 2026-08-05** — a healthchecks.io check, 5 min period / 15 min grace,
notifying by **email**, which is deliberately worth writing down: every other alert here arrives on
Telegram, so on the night this one fires it will not be where you are looking.

⚠ **The arming was verified by making it FAIL, and that step is not optional.** `--status`, a healthy
run and a green tick together prove only that the box can reach the service. A real `/fail` ping is
the only thing that proves the service reaches a human, and it is the whole reason this switch is off
the box. **An alarm nobody has heard ring is a configuration, not an alarm.** Repeat the fail-then-
clear pair after any change to the URL, the provider or its notification channel — a rotated URL that
was never rung is indistinguishable from a working one right up until the outage.

Tests: `algos/tests/test_deadman.py` (21), weighted toward the ways a check can wrongly say "fine" —
a bug here is silent by construction, so there is no user report coming.

### pnl_tracker.py and reporter.py — DELETED 2026-08-05
Both are gone, and it is worth saying why rather than leaving a hole here. `pnl_tracker.py`
(SYS_PNLTRACKER, every minute) sent daily-goal / daily-cap / weekly-cap alerts; `reporter.py`
(SYS_REPORTER, 4pm CT) sent a daily performance summary. Both belonged to the four bots deleted
2026-06-22 and had carried an EMPTY registry ever since — `BOT_TRADES = {}` and `BOTS = {}` — so
neither had produced a number in six weeks while both still appeared as switchable jobs.

⚠ **Do not restore either from memory.** Recover the commit hash from `algos/docs/DELETED_CODE.md`
if you want the old shape, then decide deliberately:

- A **daily report** on a strategy taking ~2 trades a month is a message that says "no trades
  today" almost every day, and a channel that is noise on 95% of days is one nobody reads on the
  day it matters. The bot already pings on entry and exit, which is the event worth knowing.
- A **loss cap** is worth having, but it belongs in `algos/live/runner.py`, not here. This one only
  ever sent a Telegram message; nothing refused a trade. **An alert is not a limit** — a cap that
  cannot stop the bot is a cap in name only, and it reads on the Bots page as protection.

### telegram_bot.py (SYS_TELEGRAM — persistent)
Telegram command interface. Reads from `bot_state.json` for all data.

---

## Telegram Commands

| Command | Description |
|---|---|
| `/status` | Live bot status (checks process directly) |
| `/balance` | Current balances and total P&L % |
| `/restart` | Restart all bots (requires /confirm) |
| `/restart scalper` | Restart one bot (requires /confirm) |
| `/stop` | Stop all bots (requires /confirm) |
| `/stop scalper` | Stop one bot (requires /confirm) |
| `/emergency` | Emergency stop — immediate, no confirm |
| `/resume scalper` | Resume a peak-protection-locked bot — no confirm. Clears lock within 60s. Peak protection stays OFF for rest of day. Admin only. |
| `/resetweek` | Reset weekly and daily P&L references to current MT5 balance for all bots. Use after depositing funds. Bots apply within 60s and clear all alert flags. Admin only. |
| `/resetweek smc` | Reset one bot only. |
| `/help` | Command list |
| `/users` | Manage users (admin only) |

---

## Alert Thresholds

None. The table that stood here listed the four bots deleted 2026-06-22, and the job that read it
(`pnl_tracker.py`) was deleted 2026-08-05 along with `shared/thresholds.json`. The live bot's real
risk lever is `strategy_params.exec_risk_pct` in its instance config.

---

## Data Source

All components read from `bot_state.json` — single source of truth.

| Field | Written by | Purpose |
|---|---|---|
| `balance` | bots (every loop) | MT5 account balance — authoritative when bot is live |
| `daily_start` | bots (every loop) | Balance at start of current UTC day |
| `weekly_start` | bots (every loop) | Balance at start of current ISO week |
| `last_week` | bots (startup + week rollover) | ISO week number — used by `load_weekly_start` to detect week boundaries across restarts. Replaces per-bot `*_weekly.json` files. |
| `last_write` | bots (every loop) | UTC ISO timestamp of the last state write |
| `heartbeat` | bots (every loop iteration, including during long sleeps) | Unix timestamp — monitor.py checks this to detect a frozen loop; if missing > 5 min, stall alert fires |
| `status` | bots at startup; monitor.py on transitions | "running" / "stalled" / "offline" — monitor.py writes stalled/offline/running-recovery; bots write running at startup |
| `started` | each bot at `run()` start; also startup_coordinator.py | Timestamp bot process launched |
| `day_locked` | all bots | True when weekly cap / peak protection / daily ceiling fires |
| `lock_reason` | all bots | Human-readable stop reason for the lock alert |
| `resume_trading` | telegram_bot.py | Flag read by bot wait loop to break weekly-cap lock early |
| `reset_requested` | telegram_bot.py `/resetweek` | When True, bot resets weekly_start and daily_start to current MT5 balance on its next loop iteration, then clears the flag. |

⚠ **There are no derived P&L fields in `bot_state.json` any more.** `daily_pnl`, `weekly_pnl`,
`total_pnl_pct`, `peak_balance` and `trades_today` were written by `set_pnl()`, which went with
`pnl_tracker.py` on 2026-08-05. They were removed from the defaults rather than left at `0.0`,
because a fabricated zero and a measured zero must never be the same value — see `shared/bot_state.py`.
`balance` survives and is written by `live/runner.py` on every poll, beside `mt5_link`.

### Weekly start persistence

`weekly_start` is stored exclusively in `bot_state.json`. There are no separate
`*_weekly.json` files. On startup, `load_weekly_start(bot_key, week, balance)` reads
`last_week` from bot_state: if it matches the current ISO week the stored `weekly_start`
is returned; otherwise the current balance is written as the new weekly_start.

**After depositing funds:** send `/resetweek` via Telegram. All running bots pick up the
flag within 60s, reset their in-memory references, and clear all P&L alert flags. No manual
file editing required.
