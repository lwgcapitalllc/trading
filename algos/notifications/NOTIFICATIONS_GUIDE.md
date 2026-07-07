# Notifications Guide

---

## Telegram Delivery Model

All notifications — scheduled alerts, command replies, and the startup ping — go to the
**LWG Capital Algos Notifications** group chat (`GROUP_CHAT = "-1003977707258"`).

`ADMIN_CHAT = "429207285"` is kept in all files as a fallback definition but is no longer
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

`shared/notify.py` is *meant* to be the single Telegram helper for all VPS-side components, but today each notification script carries its own inline copy of `send_telegram` (and the token) — nothing imports `notify.py` yet. Refactor the scripts to import it when bots are wired for deploy (Aaron's call, 2026-07-06). Mac-side Telegram calls go through the command-center bots router.

### monitor.py (SYS_MONITOR — every 1 min)
Bot availability and heartbeat monitor. Handles availability alerting and Telegram bot watchdog only.
P&L threshold alerts are exclusively handled by `pnl_tracker.py`.
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

**Alerts sent:**
- 🚨 Bot Offline — unexpected stop (suppressed for intentional stops)
- 🟢 Bot Online — bot came back after a crash (suppressed if stop was intentional)
- ⚠️ Loop Stalled — process alive but heartbeat missing > 5 min. Writes `status = "stalled"` to bot_state.json.
- 🟢 Loop Recovered — heartbeat resumed after a stall. Writes `status = "running"` to bot_state.json.
- 🟢 Telegram Bot Restarted — auto-restart succeeded
- 🚨 Critical — Telegram Bot Down — 3 restarts failed

### pnl_tracker.py (SYS_PNLTRACKER — every 1 min)
P&L engine. Writes balance, daily/weekly P&L to `bot_state.json`. MT5 is the only source of truth.
This is the sole source of P&L threshold alerts — monitor.py does not duplicate these.

**LIVE** (bot `last_write` within 5 minutes):
- Reads `balance`, `daily_start`, `weekly_start` directly from bot_state — MT5-authoritative
  values the bot writes every loop iteration. No trades.json math.

**OFFLINE** (bot stopped or last_write stale):
- Does nothing. Last-known state is preserved as-is. No alerts fired. No values overwritten.

**RESET PENDING** (`reset_requested` flag is True in bot_state):
- Skips alert evaluation for that bot until the bot processes the reset (within 60s).

**Alerts sent:**
- 🎯 Daily Goal Hit
- 🛑 Daily Loss Cap Hit
- 🚫 Weekly Loss Cap Hit
- 🔒 Day Locked — fires when a bot sets `day_locked=True` in bot_state (all 4 bots set
  this on weekly cap; Scalper also sets it on peak protection and daily ceiling).
  Includes the exact stop reason and `/resume` hint.

### reporter.py (SYS_REPORTER — daily 4pm CT)
Sends daily performance summary to all Telegram users.

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
| `/report` | Request performance report |
| `/help` | Command list |
| `/users` | Manage users (admin only) |

---

## Alert Thresholds

| Bot | Daily Goal | Daily Cap | Weekly Cap |
|---|---|---|---|
| SMC Trend | +2% | -10% | -20% |
| Mean Reversion | +2% | -10% | -20% |
| Scalper | +10% | -8% | -20% |
| FFT | +2% | -5% | -15% |

---

## Data Source

All components read from `bot_state.json` — single source of truth.

| Field | Written by | Purpose |
|---|---|---|
| `balance` | bots (every loop) | MT5 account balance — authoritative when bot is live |
| `daily_start` | bots (every loop) | Balance at start of current UTC day |
| `weekly_start` | bots (every loop) | Balance at start of current ISO week |
| `last_week` | bots (startup + week rollover) | ISO week number — used by `load_weekly_start` to detect week boundaries across restarts. Replaces per-bot `*_weekly.json` files. |
| `last_write` | bots (every loop) | UTC ISO timestamp — pnl_tracker uses to detect live mode |
| `heartbeat` | bots (every loop iteration, including during long sleeps) | Unix timestamp — monitor.py checks this to detect a frozen loop; if missing > 5 min, stall alert fires |
| `status` | bots at startup; monitor.py on transitions | "running" / "stalled" / "offline" — monitor.py writes stalled/offline/running-recovery; bots write running at startup |
| `started` | each bot at `run()` start; also startup_coordinator.py | Timestamp bot process launched |
| `day_locked` | all bots | True when weekly cap / peak protection / daily ceiling fires |
| `lock_reason` | all bots | Human-readable stop reason for the lock alert |
| `lock_alerted` | pnl_tracker.py | Dedup flag — alert sent once per lock |
| `resume_trading` | telegram_bot.py | Flag read by bot wait loop to break weekly-cap lock early |
| `reset_requested` | telegram_bot.py `/resetweek` | When True, bot resets weekly_start and daily_start to current MT5 balance on its next loop iteration, then clears the flag. pnl_tracker.py skips alert evaluation while pending. |

Note: `pnl_tracker.py` calls `set_pnl()` which writes display-only balance/P&L fields back
to bot_state for Telegram `/balance` to read. Only runs when the bot is LIVE — it echoes
what the bot already wrote. When offline, bot_state is not touched.

### Weekly start persistence

`weekly_start` is stored exclusively in `bot_state.json`. There are no separate
`*_weekly.json` files. On startup, `load_weekly_start(bot_key, week, balance)` reads
`last_week` from bot_state: if it matches the current ISO week the stored `weekly_start`
is returned; otherwise the current balance is written as the new weekly_start.

**After depositing funds:** send `/resetweek` via Telegram. All running bots pick up the
flag within 60s, reset their in-memory references, and clear all P&L alert flags. No manual
file editing required.
