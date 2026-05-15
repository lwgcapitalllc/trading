# ALGO_CONTROL_PANEL_GUIDE.md
# algo.py — Interactive Trading Bot Control Panel

**File:** `algo.py` (root of your algos folder, runs on your Mac only)
**Command:** `algo`

---

## Install Once

```bash
chmod +x /Users/alwg/algos/algo.py
echo 'alias algo="python3 /Users/alwg/algos/algo.py"' >> ~/.zshrc
echo 'alias algo-emergency="ssh forexvps \"taskkill /F /IM python.exe\" && echo All bots killed"' >> ~/.zshrc
source ~/.zshrc
```

---

## The Menu

```
╔══════════════════════════════════════════════════════════╗
║  ALGO CONTROL PANEL  2026-05-14 21:00 UTC                ║
╠══════════════════════════════════════════════════════════╣
║  ● FX/XAUUSD/Bot1              RUNNING  up 2h 14m        ║
║  ● FX/XAUUSD/Bot2              RUNNING  up 2h 14m        ║
║  ○ FX/XAUUSD/Scalper           STOPPED                   ║
╚══════════════════════════════════════════════════════════╝

  ACTIONS
  [1] Start all bots
  [2] Stop all bots
  [3] Emergency stop everything
  [4] Manage individual bot
  [5] View bot log
  [6] Refresh status
  [q] Quit
```

---

## Options Explained

| Option | What it does |
|---|---|
| `1` Start all | Launches every bot. Polls VPS for up to 8 seconds per bot and shows ✓ RUNNING or ✗ FAILED for each. Panel updates automatically. |
| `2` Stop all | Kills all bots. Confirms each one stopped within 8 seconds. |
| `3` Emergency stop | Kills all tasks AND all python.exe processes instantly. Open MT5 to verify no positions left open. |
| `4` Manage individual | Select one bot — start, stop, restart, or view its log. Every action confirms the result before returning. |
| `5` View log | Select a bot, see last 40 or 100 lines, colour coded. |
| `6` Refresh | Re-query VPS for current status. |
| `q` Quit | Exit. |

---

## How Status Detection Works

The panel checks for actual running Python processes on the VPS using `wmic` — not Task Scheduler task state. This matters because:

- Task Scheduler launches `launcher.py` which spawns the bot and exits immediately
- Task Scheduler therefore always shows the task as stopped even when the bot is running fine
- The panel bypasses this by checking if `bot1_smc_trend.py`, `bot2_mean_reversion.py`, or `bot3_scalper.py` appear in the VPS process list directly

**Start confirmation flow:** fires the Task Scheduler task → polls process list every 1 second → up to 8 seconds → shows ✓ RUNNING or ✗ FAILED TO START.

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

## Adding a New Bot

When you add a new instrument or bot to Task Scheduler on the VPS, two steps:

**1. Task name must follow the convention:**
```
MARKET_PAIR_Role
Examples:
  FX_XAUUSD_Bot1
  FX_GBPJPY_Bot2
  CRYPTO_BTCUSD_Scalper
```
Prefixes recognised: `FX_`, `CRYPTO_`, `FUTURES_`

**2. Add to LOG_MAP in algo.py:**
```python
LOG_MAP = {
    "FX_XAUUSD_Bot1":    ("fx", "xauusd_main",    "bot1.log"),
    "FX_XAUUSD_Bot2":    ("fx", "xauusd_main",    "bot2.log"),
    "FX_XAUUSD_Scalper": ("fx", "xauusd_scalper", "bot3.log"),
    # Add new entries here:
    "FX_GBPJPY_Bot1":    ("fx", "gbpjpy_main",    "bot1.log"),
}
```

**3. Add to TASK_BOT_MAP in algo.py:**
```python
TASK_BOT_MAP = {
    "FX_XAUUSD_Bot1":    "bot1",
    "FX_XAUUSD_Bot2":    "bot2",
    "FX_XAUUSD_Scalper": "bot3",
    # Add new entries here:
    "FX_GBPJPY_Bot1":    "bot1",
}
```

---

## Troubleshooting

**Bot shows ✗ FAILED TO START**
Run directly to see the error:
```bash
ssh forexvps "python C:\algos\bots\bot1_smc_trend.py --config C:\algos\markets\fx\instances\xauusd_main\config.json 2>&1"
```

**All bots show STOPPED after starting**
Check if credentials.json exists on VPS:
```bash
ssh forexvps "dir C:\algos\markets\fx\instances\xauusd_main\credentials.json"
```

**SSH connection timed out**
VPS may be unreachable. Check ForexVPS dashboard.
