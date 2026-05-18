# ALGO Control Panel Guide
**File:** `algo.py` — runs on your Mac only
**Command:** `algo`

---

## Install Once

```bash
chmod +x /Users/alwg/algos/algo.py
echo 'alias algo="python3 /Users/alwg/algos/algo.py"' >> ~/.zshrc
source ~/.zshrc
```

---

## The Panel

```
╔════════════════════════════════════════════════════════════════════════════════════╗
║  ALGO CONTROL PANEL  2026-05-17 20:05 UTC    [All]  [Demo]  [Live]               ║
╠════════════════════════════════════════════════════════════════════════════════════╣
║  Trading Bots                                                                      ║
║    Name              Account       Type   Inst     Status     Uptime              ║
║  ●  SMC Trend        #700103491    DEMO   XAUUSD   RUNNING    up 0h 37m           ║
║  ●  Mean Reversion   #700103491    DEMO   XAUUSD   RUNNING    up 0h 37m           ║
║  ●  Scalper          #700107520    DEMO   XAUUSD   RUNNING    up 0h 37m           ║
║  ●  FFT              #700107749    DEMO   XAUUSD   RUNNING    up 0h 36m           ║
║  ○  Futures Acct 1   —             DEMO   MNQ      STOPPED    pending eval        ║
║                                                                                    ║
║  System                                                                            ║
║  ●  Telegram                                        RUNNING    up 0h 41m          ║
║  ◑  Reporter                                        SCHEDULED  daily 4pm CT       ║
║  ◑  Monitor                                         SCHEDULED  every 1 min        ║
╚════════════════════════════════════════════════════════════════════════════════════╝
```

---

## Tabs

The panel has three views switched with `t1`, `t2`, `t3`:

| Input | View | Shows |
|---|---|---|
| `t1` | All | All bots + System section |
| `t2` | Demo | Only bots with `account_type: demo` |
| `t3` | Live | Only bots with `account_type: live` |

When you go live, change `account_type` in the relevant `config.json` to `live`
and that bot automatically appears on the Live tab.

---

## Column Guide

| Column | Source |
|---|---|
| Name | `DISPLAY_NAMES` in algo.py |
| Account | `login` field from `credentials.json` |
| Type | `account_type` field from `config.json` |
| Inst | `instrument` field from `config.json` |
| Status | Actual Python process detection via wmic |
| Uptime | Most recent startup line in bot log file |

---

## Actions

| Option | What it does |
|---|---|
| `1` | Start all bots + SYS_TELEGRAM |
| `2` | Stop all bots |
| `r` | Stop all bots, run SYS_STARTUP coordinator (sequential startup) |
| `3` | Emergency stop — kills everything, restarts SYS_TELEGRAM after |
| `4` | Manage individual bot (start/stop/restart/log) |
| `5` | View bot log (last 40 or 100 lines) |
| `6` | Refresh status |
| `t1/t2/t3` | Switch panel tab |
| `q` | Quit |

---

## Command Line Usage

```bash
algo              # interactive panel
algo restart      # restart all bots + telegram
algo start        # start all bots + telegram
algo stop         # stop all bots
algo status       # print status and exit
```

---

## Status Indicators

| Symbol | Meaning |
|---|---|
| ● green RUNNING | Process confirmed in wmic process list |
| ○ red STOPPED | Process not found |
| ◑ blue SCHEDULED | Runs on a timer, not persistently |

---

## Adding a New Bot

1. Add bot script: `bots/bot_new_strategy.py`
2. Add task: `BOT_NEW_STRATEGY` in `scheduler/new_strategy_task.xml`
3. Add to `LOG_MAP` in algo.py
4. Add to `TASK_BOT_MAP` in algo.py
5. Add to `DISPLAY_NAMES` in algo.py
6. Add to `INSTANCE_CONFIGS` in algo.py (for account/instrument reading)
7. Add to process detection in `get_all_tasks()`
8. Add to `BOT_SCRIPTS` in `bots/launcher.py`
9. Add to `BOTS` dict in `notifications/reporter.py`, `monitor.py`, `telegram_bot.py`

---

## Troubleshooting

**Bot shows STOPPED after starting:**
```bash
ssh forexvps "python C:\algos\bots\launcher.py --bot bot_smc_trend --config C:\algos\markets\fx\instances\gold_main\config.json 2>&1"
```

**Telegram not responding:**
```bash
ssh forexvps "wmic process where \"name='python.exe'\" get commandline 2>nul" | grep telegram
ssh forexvps "schtasks /run /tn SYS_TELEGRAM"
```

**Wrong account showing:**
Check `credentials.json` in each instance folder — `login` must match the MT5 account number.
