# LWG Capital — Algo Trading Suite

Automated trading system for XAUUSD (Gold) on PU Prime demo accounts.
Runs on a Windows VPS (ForexVPS). Managed from Mac via SSH alias `forexvps`.

---

## Accounts

| Instance | Account | Bot(s) | Balance |
|---|---|---|---|
| gold_main | #700103491 | SMC Trend + Mean Reversion | $2,759.28 |
| gold_scalper | #700107520 | Scalper | $981.41 |
| gold_fft | #700107749 | FFT | $1,070.50 |

Starting balance for all accounts: **$1,000**

---

## Repository Structure

```
algos/
├── README.md
├── docs/
│   ├── ARCHITECTURE.md              ← Multi-instrument system design (Phases 1–5)
│   ├── SETUP.md                     ← VPS setup and restore guide
│   ├── BOT_SMC_TREND_GUIDE.md
│   ├── BOT_MEAN_REVERSION_GUIDE.md
│   ├── BOT_SCALPER_GUIDE.md
│   └── BOT_FFT_GUIDE.md
├── scripts/
│   ├── backup.py                    ← Twice-daily backup to GitHub (backups branch)
│   ├── nt8_backup.py                ← NT8 user-folder backup extension (called by backup.py)
│   ├── deploy.py                    ← File staging tool
│   └── cleanup_vps.bat
├── bots/
│   ├── bot_smc_trend.py
│   ├── bot_mean_reversion.py
│   ├── bot_scalper.py
│   ├── bot_fft.py
│   ├── bot_utils.py
│   └── startup_coordinator.py       ← Sequential startup (single entry point)
├── shared/
│   ├── bot_state.py                 ← Single source of truth (read/write)
│   ├── mt5_ops.py                   ← All MT5 operations (BotMT5 class + free functions)
│   ├── notify.py                    ← Telegram notification helpers
│   ├── shared_ai_brain.py           ← Trade logging + AI brain
│   ├── shared_calmar.py             ← Calmar ratio tracker
│   ├── shared_regime.py             ← Market regime detection
│   ├── shared_risk.py               ← Dynamic risk / capacity engine (RiskEngine)
│   ├── shared_scanner.py            ← Multi-instrument scanner (InstrumentScanner, LearningPhaseGate)
│   ├── structure_engine.py          ← BOS/SOS/retracement event detection (used by FFT)
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
└── markets/
    ├── fx/instances/
    │   ├── gold_main/
    │   │   ├── config.json
    │   │   ├── bot_state.json       ← Live state (balance, P&L, status)
    │   │   ├── smc_trend_trades.json
    │   │   └── mean_reversion_trades.json
    │   ├── gold_scalper/
    │   │   ├── config.json
    │   │   ├── bot_state.json
    │   │   └── scalper_trades.json
    │   └── gold_fft/
    │       ├── config.json
    │       ├── bot_state.json
    │       └── fft_trades.json
    ├── futures/lucid_flex/
    │   └── tools/                   ← NinjaScript strategy source files moved to strategies/ninjatrader/
    │       ├── vps_agent.py         ← HTTP agent running on VPS (NT8 control)
    │       ├── vps_backtest_runner.py ← pywinauto NT8 Strategy Analyzer automation
    │       ├── setup_agent_task.py  ← Registers LucidFlexAgent Task Scheduler entry
    │       ├── deploy.py            ← Deploys .cs strategies to NT8 user folder
    │       ├── run_all.py           ← Batch backtest runner
    │       ├── analyze.py           ← Backtest result analyzer
    │       └── backtest_config.json ← Default backtest parameters
    └── crypto/instances/            ← Reserved (empty)
```

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

## VPS Data Backup

Critical VPS-only files are backed up to GitHub twice daily (midnight + noon CT) via `SYS_BACKUP`.

**What is backed up:** `bot_state.json`, `*_trades.json` (AI training data),
`*_model.pkl` + `*_model_scaler.pkl` (trained AI models), `*_equity.json`,
`*_daily.json`, `*_weekly.json`, `*_stdout.log`, `users.json`;
NT8 user folder: `nt8/bin/Custom` (custom NinjaScript), `nt8/workspaces`,
`nt8/templates`, `nt8/strategyanalyzerlogs` (backtest result XMLs)

**Where:** The `backups` orphan branch of this repo (separate from `main`).
Backup commits never land on `main`, so Mac development and VPS backups never conflict.

**On VPS:** `scripts/backup.py` uses a git worktree at `C:\trading-backup` pointing to the
`backups` branch. The `main` branch working tree at `C:\trading\algos` is never touched
by backup operations.

To restore after VPS rebuild — see `docs/SETUP.md` § Restore Data from Backup.

---

## MT5 Instances (VPS)

| Terminal | Path | Account |
|---|---|---|
| MT5 Main | `C:\Program Files\PU Prime MT5 Terminal\terminal64.exe` | #700103491 |
| MT5 Scalper | `C:\MT5_Scalper\terminal64.exe` | #700107520 |
| MT5 FFT | `C:\MT5_FFT\terminal64.exe` | #700107749 |

**Critical**: Each terminal must have ONLY its own account logged in.
If extra accounts appear in Navigator → Accounts → right-click → Remove.

---

## Telegram Bot

- Token: managed in `algos/shared/notify.py` — never commit to docs
- Commands: `/status`, `/balance`, `/restart`, `/stop`, `/emergency`, `/help`
