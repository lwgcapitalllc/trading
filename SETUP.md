# SETUP.md — Algo Suite Deployment Guide

## Architecture

```
algos/
├── .gitignore                       # blocks credentials + runtime files
├── algo.py                          # Mac control panel
├── ALGO_CONTROL_PANEL_GUIDE.md
├── README.md
├── stress_test_suite.py
├── shared/                          # one copy, used by all bots
│   ├── shared_ai_brain.py
│   ├── shared_calmar.py
│   └── shared_regime.py
├── bots/                            # one copy of each bot
│   ├── bot_utils.py
│   ├── launcher.py
│   ├── bot1_smc_trend.py
│   ├── bot2_mean_reversion.py
│   ├── bot3_scalper.py
│   └── [GUIDE files]
└── markets/
    └── fx/
        └── instances/
            ├── xauusd_main/
            │   ├── config.json              ← IN GitHub (no credentials)
            │   ├── credentials.template.json ← IN GitHub (safe template)
            │   └── credentials.json         ← NOT in GitHub (real creds, VPS only)
            └── xauusd_scalper/
                ├── config.json
                ├── credentials.template.json
                └── credentials.json         ← NOT in GitHub
```

---

## Credential Separation — Why and How

**credentials.json is never committed to GitHub.** It contains your MT5 account number, password, and broker server. The `.gitignore` blocks it automatically.

Each instance needs its own `credentials.json` created manually on the VPS:

```json
{
    "login":    700103491,
    "password": "YourActualPassword",
    "server":   "PUPrime-Demo"
}
```

The bot reads `config.json` (from GitHub) and `credentials.json` (local only) and merges them at startup. If `credentials.json` is missing the bot prints clear instructions and exits.

---

## One-Time VPS Setup

### 1. Install Python and dependencies
```
pip install MetaTrader5 pandas numpy pytz scikit-learn joblib
```

### 2. Install Git on VPS
Download from https://git-scm.com/download/win and install with defaults.

### 3. Clone your repo
```
cd C:\
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git algos
cd C:\algos
```

### 4. Create credentials.json for each instance
```
notepad C:\algos\markets\fx\instances\xauusd_main\credentials.json
```
Fill in your real PU Prime details. Save. Repeat for `xauusd_scalper`.

### 5. Configure Task Scheduler tasks
Create three tasks (see names and arguments below). Do this once — they survive reboots.

| Task Name | Arguments |
|---|---|
| `FX_XAUUSD_Bot1` | `C:\algos\bots\launcher.py --bot bot1 --config C:\algos\markets\fx\instances\xauusd_main\config.json` |
| `FX_XAUUSD_Bot2` | `C:\algos\bots\launcher.py --bot bot2 --config C:\algos\markets\fx\instances\xauusd_main\config.json` |
| `FX_XAUUSD_Scalper` | `C:\algos\bots\launcher.py --bot bot3 --config C:\algos\markets\fx\instances\xauusd_scalper\config.json` |

- **Program:** `C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe`
- **Start in:** `C:\algos\bots`
- **Trigger:** At system startup
- **Security:** Run whether logged on or not ✓ | Run with highest privileges ✓

### 6. Start bots
From your Mac terminal:
```bash
algo
```

---

## Daily Deploy Workflow (after initial setup)

```
1. Make changes on Mac
2. git add . && git commit -m "your message" && git push

3. Deploy to VPS:
   ssh forexvps "cd C:\algos && git pull"

4. Restart bots:
   algo  →  Start all
```

Or as a one-liner:
```bash
git push && ssh forexvps "cd C:\\algos && git pull" && algo
```

---

## Adding a New Instrument

1. Create instance folder: `markets/fx/instances/gbpjpy_main/`
2. Copy and edit `config.json` — change `symbol` and tune parameters
3. Copy `credentials.template.json` → rename to `credentials.template.json`
4. Commit and push to GitHub
5. On VPS: `git pull`, then create `credentials.json` in the new instance folder
6. Add Task Scheduler task pointing to the new config
7. Add entry to `LOG_MAP` in `algo.py`
8. The bot appears in `algo` control panel automatically

---

## Mac Setup

```bash
# Install algo control panel command
chmod +x /Users/alwg/algos/algo.py
echo 'alias algo="python3 /Users/alwg/algos/algo.py"' >> ~/.zshrc
echo 'alias algo-emergency="ssh forexvps \"taskkill /F /IM python.exe\" && echo All bots killed"' >> ~/.zshrc
source ~/.zshrc
```

---

## What Lives Where

| File type | Mac | GitHub | VPS |
|---|---|---|---|
| Bot scripts | ✓ | ✓ | ✓ |
| config.json | ✓ | ✓ | ✓ |
| credentials.json | ✗ | ✗ | ✓ only |
| credentials.template.json | ✓ | ✓ | ✓ |
| .gitignore | ✓ | ✓ | ✓ |
| Trade JSON files | ✗ | ✗ | ✓ only |
| Log files | ✗ | ✗ | ✓ only |
| AI model .pkl files | ✗ | ✗ | ✓ only |
| algo.py | ✓ | ✓ | ✗ |
| stress_test_suite.py | ✓ | ✓ | ✗ |
