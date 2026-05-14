# ALGO_CONTROL_PANEL_GUIDE.md
# algo.py — Interactive Trading Bot Control Panel

**File:** `algo.py` (lives in the root of your algos folder)
**Run from:** Your Mac Terminal — works from anywhere once installed
**Command:** `algo`

---

## What It Does

Single interactive menu that manages all your trading bots across all instruments and accounts. Connects to your VPS over SSH, reads Task Scheduler to discover every running bot automatically, and gives you full control without needing to remember individual commands.

As you add more bots (GBPJPY, crypto, futures), they appear in the menu automatically. Zero configuration changes needed.

---

## Install Once

Run these three commands in your Mac Terminal:

```bash
chmod +x /Users/alwg/algos/algo.py
echo 'alias algo="python3 /Users/alwg/algos/algo.py"' >> ~/.zshrc
source ~/.zshrc
```

After that, just type `algo` from anywhere.

---

## The Menu

```
╔══════════════════════════════════════════════════════╗
║  ALGO CONTROL PANEL    2026-05-14 12:34 UTC          ║
╠══════════════════════════════════════════════════════╣
║  ● FX/XAUUSD/Bot1              RUNNING               ║
║  ● FX/XAUUSD/Bot2              RUNNING               ║
║  ○ FX/XAUUSD/Scalper           STOPPED               ║
╚══════════════════════════════════════════════════════╝

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
| `1` Start all | Runs every task in Task Scheduler — all bots start |
| `2` Stop all | Ends all bot tasks gracefully |
| `3` Emergency stop | Kills all tasks AND kills all python.exe processes. Use when something is very wrong. Open MT5 to verify positions are handled. |
| `4` Manage individual | Select one bot — start, stop, restart, or view its log |
| `5` View bot log | Select a bot and see its last 40 or 100 log lines, colour coded |
| `6` Refresh | Re-query VPS for current status |
| `q` Quit | Exit |

---

## Log Colours

When viewing a bot log through the panel:

| Colour | Meaning |
|---|---|
| Green | Trade filled, signal found, order placed |
| Red | Error or warning |
| Yellow | Warning, daily cap hit, cooldown |
| Cyan | Breakeven, partial close, trailing stop update |
| Gray | Normal scanning activity |

---

## Adding a New Bot

When you add a new instrument or bot to Task Scheduler on the VPS, the control panel discovers it automatically — **as long as the task name follows the naming convention:**

```
MARKET_PAIR_Role

Examples:
  FX_XAUUSD_Bot1
  FX_XAUUSD_Bot2
  FX_XAUUSD_Scalper
  FX_GBPJPY_Bot1
  CRYPTO_BTCUSD_Scalper
  FUTURES_US30_Bot1
```

Prefixes recognised: `FX_`, `CRYPTO_`, `FUTURES_`

**One manual step required** — add the log file path to the `LOG_MAP` dictionary at the top of `algo.py`:

```python
LOG_MAP = {
    "FX_XAUUSD_Bot1":    ("fx", "xauusd_main",    "bot1.log"),
    "FX_XAUUSD_Bot2":    ("fx", "xauusd_main",    "bot2.log"),
    "FX_XAUUSD_Scalper": ("fx", "xauusd_scalper", "bot3.log"),
    # Add new entries here:
    "FX_GBPJPY_Bot1":    ("fx", "gbpjpy_main",    "bot1.log"),
}
```

---

## Configuration

Two settings at the top of `algo.py`:

```python
VPS_HOST = "forexvps"           # Your SSH host alias from ~/.ssh/config
LOG_BASE = "C:\\algos\\markets" # Base log path on VPS (rarely needs changing)
```

---

## Requirements

- SSH key set up for passwordless VPS access (already done)
- `forexvps` host alias in `~/.ssh/config` (already configured)
- Python 3 on your Mac (comes pre-installed on modern Macs)

---

## Troubleshooting

**"SSH connection timed out"**
VPS may be sleeping or unreachable. Check ForexVPS dashboard.

**"No bot tasks found on VPS"**
Task Scheduler tasks don't match naming convention. Check task names start with `FX_`, `CRYPTO_`, or `FUTURES_`.

**Log shows empty or not found**
Task name not in `LOG_MAP` in `algo.py`. Add it following the pattern above.

**Bot shows STOPPED right after starting**
Check the bot's stdout log on the VPS — there may be a Python error. Common causes: config.json missing credentials, MT5 not running, wrong symbol name.
