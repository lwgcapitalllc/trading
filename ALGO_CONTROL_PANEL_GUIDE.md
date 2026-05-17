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
╔══════════════════════════════════════════════════════════╗
║  ALGO CONTROL PANEL  2026-05-17 09:00 UTC                ║
╠══════════════════════════════════════════════════════════╣
║  ● ALGO/SMC_TREND          RUNNING  up 14h 32m           ║
║  ● ALGO/MEAN_REVERSION      RUNNING  up 14h 31m           ║
║  ● ALGO/SCALPER             RUNNING  up 14h 31m           ║
║  ● ALGO/FFT                 RUNNING  up 2h 15m            ║
║  ● System/TELEGRAM          RUNNING  up 14h 30m           ║
║  ○ Futures/FUTURES_ACCT1    STOPPED                       ║
╚══════════════════════════════════════════════════════════╝

  ACTIONS
  [1] Start all bots
  [2] Stop all bots
  [r] Restart all bots
  [3] Emergency stop everything
  [4] Manage individual bot
  [5] View bot log
  [6] Refresh status
  [q] Quit
```

---

## Actions

| Option | What it does |
|---|---|
| `1` Start all | Launches every bot via Task Scheduler. Polls VPS for up to 10s per bot and shows ✓ RUNNING or ✗ FAILED. Also starts ALGO_TELEGRAM. |
| `2` Stop all | Stops all bots. |
| `r` Restart all | Stops all, kills python.exe, waits 4s, starts all. ALGO_TELEGRAM always restarted too. |
| `3` Emergency stop | Kills all tasks AND all python.exe instantly. ALGO_TELEGRAM restarts automatically after 3s so you can still receive alerts. |
| `4` Manage individual | Select one bot — start, stop, restart, or view log. |
| `5` View log | Select a bot, see last 40 or 100 lines, colour coded. |
| `6` Refresh | Re-query VPS for current status. |
| `q` Quit | Exit. |

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

## How Status Detection Works

The panel checks actual running Python processes via `wmic` — not Task Scheduler state. Task Scheduler launches `launcher.py` which spawns the bot and exits, so the task always shows as stopped even when the bot is running.

The panel bypasses this by checking if `bot_smc_trend.py`, `bot_mean_reversion.py`, `bot_scalper.py`, `bot_fft.py`, `bot_futures.py`, or `telegram_bot.py` appear in the VPS process list.

---

## ALGO_TELEGRAM — Special Handling

The Telegram bot is always managed alongside the trading bots:
- `algo restart` → restarts trading bots + telegram bot
- `algo start` → starts trading bots + telegram bot
- Emergency stop → kills trading bots, then restarts telegram bot after 3s

The `ALGO_MONITOR` task (every 5 min) also watches the telegram bot and auto-restarts it if it goes down. Up to 3 auto-restart attempts before sending a critical alert.

---

## Log Colours

| Colour | Meaning |
|---|---|
| Green | Trade filled, signal found, order placed |
| Red | Error or warning |
| Yellow | Warning, daily cap, cooldown |
| Cyan | Breakeven, partial close, trailing stop |
| Gray | Normal scanning activity |

---

## Adding a New Bot to the Panel

**1. Bot script name must start with `bot_`:**
```
bot_smc_trend.py
bot_scalper.py
bot_my_new_strategy.py
```

**2. Task name must start with `ALGO_`:**
```
ALGO_SMC_TREND
ALGO_SCALPER
ALGO_MY_NEW_STRATEGY
```

**3. Add to `LOG_MAP` in algo.py:**
```python
"ALGO_MY_NEW_STRATEGY": ("fx", "gold_main", "bot_my_new_strategy.log"),
```

**4. Add to `TASK_BOT_MAP` in algo.py:**
```python
"ALGO_MY_NEW_STRATEGY": "my_strategy",
```

**5. Add to process detection in algo.py:**
```python
if "bot_my_new_strategy" in line: running_scripts.add("my_strategy")
```

**6. Add to `BOT_SCRIPTS` in launcher.py:**
```python
"bot_my_new_strategy": "bot_my_new_strategy.py",
```

---

## Troubleshooting

**Bot shows ✗ FAILED TO START**
```bash
ssh forexvps "python C:\algos\bots\bot_smc_trend.py --config C:\algos\markets\fx\instances\gold_main\config.json 2>&1"
```

**All bots show STOPPED after starting**
```bash
ssh forexvps "dir C:\algos\markets\fx\instances\gold_main\credentials.json"
```

**Telegram bot not responding**
```bash
ssh forexvps "wmic process where \"name='python.exe'\" get commandline 2>nul" | grep telegram
ssh forexvps "schtasks /run /tn ALGO_TELEGRAM"
```

**SSH connection timed out**
VPS may be unreachable. Check ForexVPS dashboard at forexvps.net.
