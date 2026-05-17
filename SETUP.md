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
├── ALGO_CONTROL_PANEL_GUIDE.md      ← Panel usage guide
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
│   ├── telegram_bot.py
│   ├── start_telegram.py            ← Single-instance launcher for SYS_TELEGRAM
│   ├── users.template.json          ← Template for users.json (never commit users.json)
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
    │   ├── gold_main/               ← SMC Trend + Mean Reversion (#700103491)
    │   ├── gold_scalper/            ← Scalper (#700107520)
    │   └── gold_fft/                ← FFT (#700107749)
    └── futures/instances/
        └── futures_account1/        ← Futures bot (pending Lucid evaluation)
```

---

## What Lives Where

| File type | Mac | GitHub | VPS |
|---|---|---|---|
| Bot scripts | ✓ | ✓ | ✓ |
| config.json | ✓ | ✓ | ✓ |
| credentials.json | ✗ | ✗ | ✓ only |
| users.json | ✗ | ✗ | ✓ only |
| credentials.template.json | ✓ | ✓ | ✓ |
| users.template.json | ✓ | ✓ | ✓ |
| Trade JSON / log / pkl files | ✗ | ✗ | ✓ only |
| algo.py | ✓ | ✓ | ✗ |
| deploy.py | ✓ | ✓ | ✗ |

---

## Credential Separation

**credentials.json and users.json are never committed to GitHub.** The `.gitignore` blocks both.

Each instance needs its own `credentials.json` created manually on the VPS:

```json
{
    "login":    700103491,
    "password": "YourPassword",
    "server":   "PUPrime-Demo"
}
```

The bot merges `config.json` (from GitHub) + `credentials.json` (VPS only) at startup.

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

**4. Create users.json (Telegram access control):**
```
echo {"users":{"429207205":{"name":"Jason","role":"admin","added":"2026-05-17"}}} > C:\algos\users.json
```
Manage users at any time via: `algo` → `[4] Manage individual bot` → `Telegram` → `[u] Manage users`

**5. Install Task Scheduler tasks (PowerShell on VPS):**

See `scheduler/SCHEDULER_GUIDE.md` for full install commands.

**6. Start everything:**
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
ssh forexvps "taskkill /f /im python.exe"
ssh forexvps "schtasks /run /tn BOT_SMC_TREND && schtasks /run /tn BOT_MEAN_REVERSION && schtasks /run /tn BOT_SCALPER && schtasks /run /tn BOT_FFT && schtasks /run /tn SYS_TELEGRAM"
```

---

## Deploying New Files from Claude

When downloading updated files from Claude, place them directly at their correct path under `/Users/alwg/algos/` then commit:

```bash
cd /Users/alwg/algos
git add .
git commit -m "your message"
git push
ssh forexvps "cd C:\algos && git pull origin main"
```

Alternatively, drop files flat into `algos/files/` and run `python3 deploy.py` to auto-route them.

---

## Task Scheduler Task Names

| Task | Prefix | Purpose |
|---|---|---|
| `BOT_SMC_TREND` | BOT_ | Bot SMC Trend |
| `BOT_MEAN_REVERSION` | BOT_ | Bot Mean Reversion |
| `BOT_SCALPER` | BOT_ | Bot Scalper |
| `BOT_FFT` | BOT_ | Bot FFT |
| `BOT_FUTURES_ACCT1` | BOT_ | Bot Futures Account 1 |
| `SYS_TELEGRAM` | SYS_ | Telegram command bot (24/7) |
| `SYS_REPORTER` | SYS_ | Daily summary at 4pm Texas |
| `SYS_MONITOR` | SYS_ | Health checker every 1 minute |

```bash
# List all tasks
ssh forexvps "schtasks /query /fo TABLE | findstr BOT_"
ssh forexvps "schtasks /query /fo TABLE | findstr SYS_"
```

---

## Adding a New Instrument

1. Create instance folder: `markets/fx/instances/gbpjpy_main/`
2. Copy and edit `config.json` — set `instrument`, `account_type`, symbol, parameters
3. Copy `credentials.template.json` into new folder, fill in VPS only
4. Add new task XML to `scheduler/`
5. Add entry to `LOG_MAP`, `TASK_BOT_MAP`, `DISPLAY_NAMES`, `INSTANCE_CONFIGS` in `algo.py`
6. Add to `BOTS` dict in `reporter.py`, `monitor.py`, `telegram_bot.py`
7. Commit, push, pull on VPS, install task, start bot
