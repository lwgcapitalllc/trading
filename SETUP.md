# SETUP.md — LWG Capital Algo Suite

Complete setup guide for a fresh VPS or new developer.

---

## Repository Structure

```
algos/
├── algo.py                          ← Mac control panel (alias: algo)
├── deploy.py                        ← Deployment helper script
├── README.md                        ← Master docs + bot comparison
├── SETUP.md                         ← This file
├── stress_test_suite.py             ← Local HMM Monte Carlo stress tests
│
├── bots/                            ← All trading bot scripts + guides
│   ├── bot_smc_trend.py
│   ├── bot_mean_reversion.py
│   ├── bot_scalper.py
│   ├── bot_fft.py
│   ├── bot_futures.py
│   ├── bot_utils.py
│   ├── launcher.py
│   ├── BOT_SMC_TREND_GUIDE.md
│   ├── BOT_MEAN_REVERSION_GUIDE.md
│   ├── BOT_SCALPER_GUIDE.md
│   ├── BOT_FFT_GUIDE.md
│   └── BOT_FUTURES_GUIDE.md
│
├── shared/                          ← Shared components (all bots import these)
│   ├── shared_ai_brain.py
│   ├── shared_calmar.py
│   └── shared_regime.py
│
├── executors/                       ← Broker API connectors
│   └── tradovate.py
│
├── notifications/                   ← Telegram reporter, monitor, command bot
│   ├── reporter.py
│   ├── monitor.py
│   ├── start_telegram.py → telegram_bot.py
│   └── NOTIFICATIONS_GUIDE.md
│
├── scheduler/                       ← Task Scheduler XMLs (one per task)
│   ├── smc_trend_task.xml
│   ├── mean_reversion_task.xml
│   ├── scalper_task.xml
│   ├── fft_task.xml
│   ├── futures_acct1_task.xml
│   ├── telegram_task.xml
│   ├── reporter_task.xml
│   ├── monitor_task.xml
│   └── SCHEDULER_GUIDE.md
│
└── markets/                         ← Per-instance configs (no credentials)
    ├── fx/instances/
    │   ├── gold_main/               ← SMC Trend + Mean Reversion
    │   ├── gold_scalper/            ← Scalper
    │   └── gold_fft/                ← FFT
    └── futures/instances/
        └── futures_account1/        ← Futures bot
```

---

## What Lives Where

| File type | Mac | GitHub | VPS |
|---|---|---|---|
| Bot scripts | ✓ | ✓ | ✓ |
| config.json | ✓ | ✓ | ✓ |
| credentials.json | ✗ | ✗ | ✓ only |
| credentials.template.json | ✓ | ✓ | ✓ |
| Trade JSON / log / pkl files | ✗ | ✗ | ✓ only |
| algo.py | ✓ | ✓ | ✗ |
| deploy.py | ✓ | ✓ | ✗ |

---

## Credential Separation

**credentials.json is never committed to GitHub.** The `.gitignore` blocks it.

Each instance needs its own `credentials.json` created manually on the VPS:

```json
{
    "login":    700103491,
    "password": "YourPassword",
    "server":   "PUPrime-Demo"
}
```

The bot merges `config.json` (from GitHub) + `credentials.json` (VPS only) at startup. If missing, it prints clear instructions and exits.

---

## One-Time VPS Setup

**1. Install Python dependencies:**
```
pip install MetaTrader5 pandas numpy pytz scikit-learn joblib requests
```

**2. Clone the repo:**
```
cd C:\
git clone https://github.com/lwgcapitalllc/algos.git algos
cd C:\algos
```

**3. Create credentials.json for each instance:**
```
notepad C:\algos\markets\fx\instances\gold_main\credentials.json
notepad C:\algos\markets\fx\instances\gold_scalper\credentials.json
notepad C:\algos\markets\fx\instances\gold_fft\credentials.json
```

**4. Install Task Scheduler tasks (PowerShell on VPS):**

See `scheduler/SCHEDULER_GUIDE.md` for the full install commands.
All tasks use the `ALGO_` prefix. Install via XML files in `scheduler/`.

**5. Start everything:**
```bash
algo restart
```

---

## Mac Setup (one-time)

```bash
chmod +x /Users/alwg/algos/algo.py
echo 'alias algo="python3 /Users/alwg/algos/algo.py"' >> ~/.zshrc
source ~/.zshrc
```

---

## Daily Deploy Workflow

```bash
# 1. Make changes on Mac
# 2. Commit and push
git add . && git commit -m "your message" && git push

# 3. Pull on VPS and restart
ssh forexvps "cd C:\algos && git pull origin main"
algo restart
```

---

## Deploying New Files

When downloading updated files from Claude, place them all flat into `algos/files/` then run:

```bash
cd /Users/alwg/algos
python3 deploy.py
```

This moves every file to its correct location, removes old files, and cleans up.

---

## Task Scheduler Task Names

All tasks use the `ALGO_` prefix for easy grouping:

| Task | Purpose |
|---|---|
| `BOT_SMC_TREND` | Bot SMC Trend |
| `BOT_MEAN_REVERSION` | Bot Mean Reversion |
| `BOT_SCALPER` | Bot Scalper |
| `BOT_FFT` | Bot FFT |
| `BOT_FUTURES_ACCT1` | Bot Futures Account 1 |
| `SYS_TELEGRAM` | Telegram command bot (24/7) |
| `SYS_REPORTER` | Daily summary at 4pm Texas |
| `SYS_MONITOR` | Health checker every 1 minute |

Find all: `schtasks /query /fo TABLE | findstr ALGO`

---

## Adding a New Instrument

1. Create instance folder: `markets/fx/instances/gbpjpy_main/`
2. Copy and edit `config.json` — change symbol and tune parameters
3. Copy `credentials.template.json` into new folder
4. Add new task XML to `scheduler/`
5. Add entry to `LOG_MAP` and `TASK_BOT_MAP` in `algo.py`
6. Add to `MANIFEST` in `deploy.py`
7. Commit, push, pull on VPS, install task, start bot
