# Notifications Guide

---

## Components

### monitor.py (SYS_MONITOR — every 1 min)
Watchdog for bot processes. Checks if Python processes are running.
Updates `status` field in `bot_state.json`.
Auto-restarts Telegram bot up to 3 times if it goes down.

**Alerts sent:**
- 🚨 Bot Offline — bot process stopped unexpectedly
- 🟢 Bot Online — bot process came back up
- 🟢 Telegram Bot Restarted — auto-restart succeeded
- 🚨 Critical — Telegram Bot Down — 3 restarts failed

### pnl_tracker.py (SYS_PNLTRACKER — every 1 min)
Pure math P&L engine. Reads trades JSON files only — no MT5 connections.
Writes balance, daily/weekly P&L to `bot_state.json`.

**Alerts sent:**
- 🎯 Daily Goal Hit
- 🛑 Daily Loss Cap Hit
- 🚫 Weekly Loss Cap Hit
- 🔒 Day Locked — fires when a bot sets `day_locked=True` in bot_state (currently: Scalper
  peak protection and daily ceiling). Includes the exact stop reason and `/resume` hint.

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
`pnl_tracker.py` is the only writer for balance/P&L fields.
`monitor.py` is the only writer for status field.
`startup_coordinator.py` is the only writer for started field.
`bot_scalper.py` writes `day_locked`, `lock_reason`, `lock_alerted`, `resume_trading`.
`telegram_bot.py` writes `resume_trading` (via `/resume` command).

### bot_state.json lock fields (Scalper only)

| Field | Written by | Purpose |
|---|---|---|
| `day_locked` | bot_scalper.py | True when peak protection or ceiling lock fires |
| `lock_reason` | bot_scalper.py | Human-readable stop reason for the alert |
| `lock_alerted` | pnl_tracker.py | Dedup flag — alert sent once per lock |
| `resume_trading` | telegram_bot.py | Flag read by bot_scalper wait loop to break lock |
