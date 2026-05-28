# Algo Control Panel Guide

Mac-side terminal dashboard. Run with: `algo`

Setup: add to `~/.zshrc`:
```bash
alias algo="python3 /Users/alwg/trading/algos/algo.py"
```

---

## Panel Layout

```
╔══════════════════════════════════════════════════════════════════════════════════════╗
║  ALGO CONTROL PANEL  2026-05-19 12:00 UTC    [All]  [Demo]  [Live]                  ║
╠══════════════════════════════════════════════════════════════════════════════════════╣
║  Trading Bots                                                                        ║
║    Name             Account      Balance    Status    Info                           ║
║  ● SMC Trend        700103491    $2,759.28  RUNNING   3h 12m  d:+1.6%               ║
║  ● Mean Reversion   700103491    $2,759.28  RUNNING   3h 12m                        ║
║  ● Scalper          700107520    $981.41    RUNNING   3h 11m  d:-0.5%               ║
║  ● FFT              700107749    $1,070.50  RUNNING   3h 10m                        ║
║                                                                                      ║
║  Telegram                                                                            ║
║    Name             Account      Balance    Status    Info                           ║
║  ● Telegram         —            —          RUNNING   3h 12m                        ║
║                                                                                      ║
║  Scheduled Jobs                                                                      ║
║    Name             Account      Balance    Status    Schedule                       ║
║  ◑ Monitor          —            —          SCHEDULED every 1 min                   ║
║  ◑ P&L Tracker      —            —          SCHEDULED every 1 min                   ║
║  ◑ Reporter         —            —          SCHEDULED daily 4pm CT                  ║
╚══════════════════════════════════════════════════════════════════════════════════════╝
```

Columns:
- **Balance** — read from `bot_state.json` for each bot (same source as Telegram `/balance`)
- **Info** — uptime from `bot_state.json → started` field + daily P&L % (green/red)

Auto-refreshes every 60 seconds. Redraws in-place — no top-down flash.

---

## Tabs

| Tab | Key | Shows |
|-----|-----|-------|
| All | `t1` | All bots and system tasks |
| Demo | `t2` | DEMO account bots only |
| Live | `t3` | LIVE account bots only |

---

## Actions

| Key | Action |
|-----|--------|
| `1` | Start all bots |
| `2` | Stop all bots |
| `r` | Restart all bots via SYS_STARTUP coordinator |
| `3` | Emergency stop — kills all Python processes |
| `4` | Manage individual bot |
| `5` | View bot log |
| `6` | Refresh now |
| `t1/t2/t3` | Switch tab: All / Demo / Live |
| `q` | Quit |

---

## How Restart Works

`[r]` does:
1. Stop all bots via Task Scheduler
2. Kill all `python.exe` processes
3. Run `SYS_STARTUP` coordinator
4. Coordinator starts bots one at a time, waits for MT5 connection before next

This prevents MT5 account mixing from simultaneous connections.

---

## Data Sources

All status data is fetched in **one batched SSH call** per refresh (`fetch_vps_snapshot()`).
No sequential SSH calls per-row — the panel renders from a pre-fetched snapshot.

| Field | Source |
|-------|--------|
| Balance | `bot_state.json → balance` |
| Uptime | `bot_state.json → started` (timestamp written by coordinator on startup) |
| Daily P&L % | `bot_state.json → daily_pnl_pct` |
| Account number | `bot_state.json → account` |
| Running status | `wmic process` output (python.exe process list) |

---

## CLI Mode

```bash
algo start    # start all bots
algo stop     # stop all bots
algo restart  # restart all bots
algo status   # print running/stopped status list
```
