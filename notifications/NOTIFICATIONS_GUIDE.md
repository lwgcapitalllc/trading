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
| `/stop` | Stop all bots (requires /confirm) |
| `/emergency` | Emergency stop — immediate, no confirm |
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
