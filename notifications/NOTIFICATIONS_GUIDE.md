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
| Start/stop/restart from control panel | `algo.py notify_telegram` after confirmation | Immediate |
| Stop/restart from Telegram command | Result message returned to user via `/confirm` flow | Immediate |
| Bot crashes unexpectedly | `monitor.py` crash detector (every 1 min) | ≤ 1 min |
| Bot comes back online after crash | `monitor.py` (same cycle as crash detection) | ≤ 1 min |
| Telegram bot goes down | `monitor.py` watchdog (every 1 min) | ≤ 1 min |

`shared/notify.py` is the single helper used by all VPS-side components.
`algo.py` (runs on Mac) has an inline `notify_telegram()` using stdlib `urllib`.

### monitor.py (SYS_MONITOR — every 1 min)
Full bot health monitor. Tracks running state, log staleness, P&L caps, and Telegram bot watchdog.
Persists state in `monitor_state.json` across runs.

**Crash alerting with intentional-stop suppression:**
When a bot goes offline, monitor.py checks `C:/algos/stop_suppress.json` before alerting.
If the bot's suppress key is in the file, the stop was intentional — no alert is sent and no
"Bot Online" alert fires when it restarts. The key is consumed on first read (one-shot).

Suppress keys: `fft`, `scalper`, `smc`, `reversion`.

The suppress file is written by:
- `algo.py` — via SSH before stopping from the control panel (`suppress_stop_alert()`)
- `telegram_bot.py` — locally before executing `/stop`, `/restart`, `/emergency` commands

**Alerts sent:**
- 🚨 Bot Offline — unexpected stop (suppressed for intentional stops)
- 🟢 Bot Online — bot came back after a crash (suppressed if stop was intentional)
- ⚠️ Loop Stalled — process alive but log silent > 90 min
- 🎯 Daily Goal Hit
- 🛑 Daily Loss Cap Hit
- 🚫 Weekly Loss Cap Hit
- 🟢 Telegram Bot Restarted — auto-restart succeeded
- 🚨 Critical — Telegram Bot Down — 3 restarts failed

### pnl_tracker.py (SYS_PNLTRACKER — every 1 min)
Dual-mode P&L engine. Writes balance, daily/weekly P&L to `bot_state.json`.

**LIVE mode** (bot `last_write` in bot_state is within 5 minutes):
- Reads `balance`, `daily_start`, `weekly_start` directly from bot_state — these are MT5
  ground-truth values the bot writes every loop iteration.
- No trades.json math. No hardcoded starting balance.

**OFFLINE mode** (bot stopped or last_write stale):
- Falls back to trades.json closed-trade math.
- Uses bot_state `balance` as last-known value when trades.json has no pnl_usd data.

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
| `last_write` | bots (every loop) | UTC ISO timestamp — pnl_tracker uses to detect live mode |
| `status` | telegram_bot.py crash detector | "running" / "offline" |
| `started` | each bot at `run()` start; also startup_coordinator.py | Timestamp bot process launched |
| `day_locked` | all bots | True when weekly cap / peak protection / daily ceiling fires |
| `lock_reason` | all bots | Human-readable stop reason for the lock alert |
| `lock_alerted` | pnl_tracker.py | Dedup flag — alert sent once per lock |
| `resume_trading` | telegram_bot.py | Flag read by bot wait loop to break weekly-cap lock early |

Note: `pnl_tracker.py` calls `set_pnl()` which writes display-only balance/P&L fields back
to bot_state for Telegram `/balance` to read. When the bot is in LIVE mode, this echoes
what the bot already wrote. When OFFLINE, it writes the trades.json-computed estimate.
