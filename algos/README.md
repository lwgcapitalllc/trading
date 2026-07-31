# LWG Capital — Algo Trading Suite

Automated trading system for XAUUSD (Gold) on PU Prime demo accounts.
Runs on a Windows VPS (ForexVPS). Managed from Mac via SSH alias `forexvps`.

---

## Bots

There are currently **no live bots**. All four first-attempt bots — SMC Trend, Scalper, FFT, and Mean Reversion — were deleted 2026-06-22 to rebuild the suite backtest-first.

New bots follow the S.Y.S.T.E.M. process in `../docs/BOT_DEVELOPMENT_METHOD.md` (repo root). The reusable deployment plumbing (MT5 connection, per-instance configs, Task Scheduler, liveness layer) is documented in `docs/BOT_DEPLOYMENT_INFRA.md`.

---

## Repository Structure

```
algos/
├── README.md
├── docs/
│   ├── ARCHITECTURE.md              ← Multi-instrument system design (Phases 1–5)
│   └── BOT_DEPLOYMENT_INFRA.md      ← Reusable deploy plumbing (MT5, configs, scheduler, liveness)
├── bots/
│   ├── bot_utils.py                 ← Config loader, logging, path resolver
│   ├── launcher.py                  ← Universal Task Scheduler launcher
│   └── startup_coordinator.py       ← Sequential startup (single entry point)
├── shared/
│   ├── bot_state.py                 ← Single source of truth (read/write)
│   ├── mt5_ops.py                   ← All MT5 operations (BotMT5 class + free functions)
│   ├── notify.py                    ← Telegram sender (per-bot chat + identity)
│   ├── credentials.py               ← The one place secrets resolve (env → credentials.json)
│   ├── shared_regime.py             ← Market regime detection
│   ├── structure_engine.py          ← BOS/SOS/retracement event detection
│   └── thresholds.json              ← Risk cap overrides (written by command-center deploy)
├── notifications/
│   ├── monitor.py                   ← Process watchdog (every 1 min)
│   ├── pnl_tracker.py               ← P&L engine (every 1 min)
│   ├── reporter.py                  ← Daily 4pm CT report
│   ├── telegram_bot.py              ← Telegram command bot
│   ├── start_telegram.py            ← Telegram launcher
│   └── NOTIFICATIONS_GUIDE.md
├── scheduler/
│   ├── *_task.xml                   ← Task Scheduler definitions
│   └── SCHEDULER_GUIDE.md
├── nt8/                            ← NT8 backtest toolchain (top-level)
│   ├── nt8_agent.py                ← HTTP agent running on VPS (NT8 control)
│   ├── nt8_backtest_runner.py      ← pywinauto NT8 Strategy Analyzer automation
│   ├── nt8_compile_runner.py       ← pywinauto NinjaScript Editor compile subprocess
│   ├── deploy.py                   ← Deploys .cs strategies to NT8 user folder
│   ├── run_all.py                  ← Batch backtest runner
│   ├── analyze.py                  ← Backtest result analyzer
│   ├── setup_agent_task.py         ← Registers NT8Agent Task Scheduler entry
│   ├── debug_sa_display.py         ← Manual SA display diagnostic
│   ├── test_bt_switch.py           ← Manual backtest-mode-switch diagnostic
│   └── backtest_config.json        ← Default backtest parameters
└── markets/
    ├── fx/
    │   └── tools/
    │       └── mt5_agent.py        ← MT5 HTTP agent (VPS, port 8766)
    └── crypto/instances/           ← Reserved (empty)
```

Per-bot instance directories (`markets/<market>/instances/<name>/` with `config.json` + `bot_state.json`) are created when a new bot is deployed — see `docs/BOT_DEPLOYMENT_INFRA.md`. None exist today.

---

## Single Source of Truth

`bot_state.json` in each instance directory is the **only** file every
component reads from. Nothing else is authoritative.

| Field | Set by | Read by |
|---|---|---|
| `started` | startup_coordinator + each bot at `run()` start | command-center, telegram /status |
| `status` | monitor.py | telegram /status |
| `balance`, P&L fields | pnl_tracker.py | telegram /balance, reporter |
| `day_locked` | pnl_tracker.py | monitor alerts |

---

## Deploy Workflow

```bash
# Edit on Mac
git add . && git commit -m "..." && git push
ssh forexvps "cd C:\trading && git pull origin main"

# Restart bots (coordinator starts them sequentially)
ssh forexvps "del C:\trading\algos\mt5_connect.lock 2>nul && taskkill /f /im python.exe"
sleep 3
ssh forexvps "schtasks /run /tn SYS_STARTUP"
sleep 60
ssh forexvps "wmic process where \"name='python.exe'\" get commandline 2>nul"
```

---

## MT5 Instances (VPS)

No bot instances are configured today. When a validated strategy is wired to live demo, each instance maps to one MT5 terminal — see `docs/BOT_DEPLOYMENT_INFRA.md`.

**Critical**: Each terminal must have ONLY its own account logged in.
If extra accounts appear in Navigator → Accounts → right-click → Remove.

---

## Telegram Bot

- Token: managed in `algos/shared/notify.py` — never commit to docs
- Commands: `/status`, `/balance`, `/restart`, `/stop`, `/emergency`, `/help`
