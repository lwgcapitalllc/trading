# Algo Control Panel Guide

Mac-side terminal dashboard. Run with: `algo`

Setup: add to `~/.zshrc`:
```bash
alias algo="python3 /Users/alwg/algos/algo.py"
```

---

## Panel Layout

```
╔══════════════════════════════════════════════════════════════════════════════════╗
║  ALGO CONTROL PANEL  2026-05-18 04:00 UTC    [All]  [Demo]  [Live]              ║
╠══════════════════════════════════════════════════════════════════════════════════╣
║  Trading Bots                                                                    ║
║    Name             Account      Type  Inst    Status    Uptime                  ║
║  ● SMC Trend        700103491    DEMO  XAUUSD  RUNNING   3m                      ║
║  ● Mean Reversion   700103491    DEMO  XAUUSD  RUNNING   3m                      ║
║  ● Scalper          700107520    DEMO  XAUUSD  RUNNING   2m                      ║
║  ● FFT              700107749    DEMO  XAUUSD  RUNNING   2m                      ║
║                                                                                  ║
║  Scheduled Jobs                                                                  ║
║    Name             Account      Type  Inst    Status    Schedule                ║
║  ◑ Monitor          —            —     —       SCHEDULED every 1 min             ║
║  ◑ P&L Tracker      —            —     —       SCHEDULED every 1 min             ║
║  ◑ Reporter         —            —     —       SCHEDULED daily 4pm CT            ║
╚══════════════════════════════════════════════════════════════════════════════════╝
```

**Uptime** reads from `bot_state.json` → `started` field (written by coordinator).

---

## Actions

| Key | Action |
|---|---|
| `1` | Start all bots |
| `2` | Stop all bots |
| `r` | Restart all bots via SYS_STARTUP coordinator |
| `3` | Emergency stop — kills all Python processes |
| `4` | Manage individual bot |
| `5` | View bot log |
| `6` | Refresh |
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
