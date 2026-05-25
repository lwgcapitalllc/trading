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
├── algo.py                          ← Mac control panel (run: algo)
├── README.md
├── docs/
│   ├── CONTEXT.md                   ← Full project context
│   ├── SETUP.md                     ← VPS setup and restore guide
│   ├── ALGO_CONTROL_PANEL_GUIDE.md
│   └── CLAUDE_CODE_SETUP.md
├── scripts/
│   ├── backup.py                    ← Twice-daily backup to GitHub (backups branch)
│   ├── deploy.py                    ← File staging tool
│   ├── stress_test_suite.py         ← Monte Carlo stress tests (run locally)
│   └── cleanup_vps.bat
├── bots/
│   ├── bot_smc_trend.py
│   ├── bot_mean_reversion.py
│   ├── bot_scalper.py
│   ├── bot_fft.py
│   ├── bot_utils.py
│   ├── startup_coordinator.py       ← Sequential startup (single entry point)
│   └── BOT_*_GUIDE.md
├── shared/
│   ├── bot_state.py                 ← Single source of truth (read/write)
│   ├── shared_ai_brain.py           ← Trade logging + AI brain
│   ├── shared_calmar.py             ← Calmar ratio tracker
│   └── shared_regime.py             ← Market regime detection
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
    └── fx/instances/
        ├── gold_main/
        │   ├── config.json
        │   ├── bot_state.json       ← Live state (balance, P&L, status)
        │   ├── smc_trend_trades.json
        │   └── mean_reversion_trades.json
        ├── gold_scalper/
        │   ├── config.json
        │   ├── bot_state.json
        │   └── scalper_trades.json
        └── gold_fft/
            ├── config.json
            ├── bot_state.json
            └── fft_trades.json
```

---

## Single Source of Truth

`bot_state.json` in each instance directory is the **only** file every
component reads from. Nothing else is authoritative.

| Field | Set by | Read by |
|---|---|---|
| `started` | startup_coordinator | algo.py, telegram /status |
| `status` | monitor.py | telegram /status |
| `balance`, P&L fields | pnl_tracker.py | telegram /balance, reporter |
| `day_locked` | pnl_tracker.py | monitor alerts |

---

## Deploy Workflow

```bash
# Edit on Mac
git add . && git commit -m "..." && git push
ssh forexvps "cd C:\lwg-capital\algos && git pull origin main"

# Restart bots (coordinator starts them sequentially)
ssh forexvps "del C:\lwg-capital\algos\mt5_connect.lock 2>nul && taskkill /f /im python.exe"
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
`*_daily.json`, `*_weekly.json`, `*_stdout.log`, `users.json`

**Where:** The `backups` orphan branch of this repo (separate from `main`).
Backup commits never land on `main`, so Mac development and VPS backups never conflict.

**On VPS:** `scripts/backup.py` uses a git worktree at `C:\lwg-capital-backup` pointing to the
`backups` branch. The `main` branch working tree at `C:\lwg-capital\algos` is never touched
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

- Token: `8888123776:AAFuWpPoKnHSmGwxNxRB9Qo61kDSk7w0YD8`
- Admin: Aaron (@cryptobetta, chat ID: `429207285`)
- Commands: `/status`, `/balance`, `/restart`, `/stop`, `/emergency`, `/help`
