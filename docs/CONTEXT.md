# LWG Capital LLC — Algo Trading Suite
## Claude Context File

---

## What This Project Is

Multi-bot algorithmic trading system for gold (XAUUSD) and futures (MNQ).
Built in Python, runs 24/7 on a Windows VPS (ForexVPS, IP: 45.82.164.112).
Controlled from Mac via `algo.py` command-line panel.
Code lives on GitHub. Deploy flow: edit on Mac → git push → ssh pull on VPS → algo restart.

---

## The Bots

| Bot | File | Strategy | Account | MT5 Instance |
|-----|------|----------|---------|--------------|
| SMC Trend | `bot_smc_trend.py` | Judas Swing + FVG, H4 trend filter, M15 entry | gold_main #700103491 | PU Prime Terminal |
| Mean Reversion | `bot_mean_reversion.py` | BB + RSI + VWAP, 1R target, fast close | gold_main #700103491 | PU Prime Terminal |
| Scalper | `bot_scalper.py` | EMA stack + pullback, M5/M1, 5–20 trades/day | gold_scalper #700107520 | MT5_Scalper |
| FFT | `bot_fft.py` | Dual Fibonacci confluence, H1+H4 trend | gold_fft #700107749 | MT5_FFT |
| Futures | `bot_futures.py` | SMC_TREND on MNQ via Tradovate API | futures_account1 | N/A (Tradovate) |

SMC Trend and Mean Reversion share one MT5 account and are designed to be uncorrelated — one works trending markets, the other ranging markets.
Scalper is isolated on its own account due to high volatility (+50% / -8% swings possible).
FFT is the lowest risk (1%) — unproven in live trading, still learning.

---

## Shared Components

| File | Role |
|------|------|
| `shared_ai_brain.py` | AI engine (Claude API), trade logger, daily performance logger |
| `shared_calmar.py` | Calmar ratio tracker, morning report |
| `shared_regime.py` | Market regime classifier: TRENDING / TRANSITIONING / RANGING |
| `bot_utils.py` | Config loader, logging, path resolver |
| `launcher.py` | Universal Task Scheduler launcher |
| `startup_coordinator.py` | Orchestrates bot startup sequence |
| `tradovate.py` | Tradovate API executor for Bot Futures |
| `algo.py` | Mac control panel — start/stop/status/logs/restart |

---

## Risk Rules (All Bots)

- SMC Trend: 2% risk, 3:1 target, 10% daily loss cap
- Mean Reversion: 2% risk, 1:1 target, 10% daily loss cap
- Scalper: 2–3.5% risk (auto-scaling), -8% floor
- FFT: 1% risk, 2:1–5:1 target, 5% daily loss cap
- Futures (MNQ): 1% risk, max 4 contracts, 3% daily loss cap

**Dead Zone (all bots): No new entries 3:00pm–7:00pm Texas time.**
During dead zone: net profit → close all. Individual profit + portfolio negative → breakeven. Losing worsening → close immediately.

---

## AI Thresholds

- SMC Trend + Mean Reversion: min_ai_probability = 0.55 (stricter, more history)
- Scalper + FFT: min_ai_probability = 0.52 (newer, learning phase)

---

## Infrastructure

- **VPS:** ForexVPS Windows Server, 24/7
- **Mac control:** `python algo.py start|stop|restart|status`
- **Deploy:** `git push` on Mac → `ssh forexvps "cd C:\algos && git pull"` → `algo restart`
- **Notifications:** Event-driven — bots self-report startup, algo.py fires on control panel actions, monitor.py detects crashes and fires Bot Offline/Online alerts (≤1 min). Intentional stops suppressed via `stop_suppress.json`. reporter.py handles daily summaries.
- **Scheduling:** Windows Task Scheduler via XML task files
- **Backup:** `scripts/backup.py` runs twice daily (midnight + noon CT) via SYS_BACKUP. Commits VPS runtime
  data to the `backups` orphan branch via a git worktree at `C:\algos-backup`. Never touches `main`,
  so Mac deploys and VPS backups never conflict. See README § VPS Data Backup for full file list.

---

## Repo Structure

```
algos/
├── algo.py                    ← Mac control panel
├── CLAUDE.md                  ← Auto-loaded Claude Code instructions (quant rules + doc rules)
├── README.md
├── docs/
│   ├── CONTEXT.md             ← This file
│   ├── SETUP.md               ← VPS setup and restore guide
│   ├── ALGO_CONTROL_PANEL_GUIDE.md
│   └── CLAUDE_CODE_SETUP.md
├── scripts/
│   ├── backup.py              ← Twice-daily backup to backups branch
│   ├── deploy.py              ← File staging tool
│   ├── stress_test_suite.py   ← Monte Carlo stress tests (run locally)
│   └── cleanup_vps.bat
├── .claude/
│   ├── settings.local.json
│   └── commands/              ← Custom slash commands: /session-start /quant-review
├── shared/
│   ├── shared_ai_brain.py
│   ├── shared_calmar.py
│   └── shared_regime.py
├── bots/
│   ├── bot_utils.py
│   ├── launcher.py
│   ├── startup_coordinator.py
│   ├── bot_smc_trend.py
│   ├── bot_mean_reversion.py
│   ├── bot_scalper.py
│   ├── bot_fft.py
│   └── bot_futures.py
├── executors/
│   └── tradovate.py
└── markets/
    ├── fx/instances/
    │   ├── gold_main/
    │   ├── gold_scalper/
    │   └── gold_fft/
    └── futures/instances/
        └── futures_account1/
```

Note: VPS runtime data (`*_trades.json`, `bot_state.json`, `*.pkl`, etc.) is gitignored
on `main` and backed up to the separate `backups` branch by `backup.py`.

---

## Current Phase

Demo trading. Targets to advance:
- 15+ closed trades per bot
- Calmar >= 2.0 to continue demo
- Calmar >= 2.5 (SMC Trend) / 2.0 (Mean Reversion) to begin prop firm evaluation
- FFT risk stays at 1% until 30+ trades with solid Calmar

Calmar benchmarks: 2.0 = okay | 3.0 = decent | 5.0+ = exceptional

---

## Coding Conventions

- Python throughout
- Each bot is self-contained in its own file
- Shared logic lives in shared/ — never duplicate in bot files
- Config driven via config.json per instance
- All logging via bot_utils.py logger setup
- Never optimize to past data — overfitting is the enemy

---

## What I Am Working On

- Last completed: Refactored bot control in `algo.py`. `stop_bot()` encapsulates
  `schtasks /end` + `wmic terminate` + `wait_for_process_death` — used by both stop
  and restart, no duplication. `wait_for_state()` replaces five copies of the
  VPS-snapshot polling loop. Crash alerting moved to `monitor.py` with intentional-stop
  suppression via `stop_suppress.json`; duplicate crash detector removed from
  `telegram_bot.py`.
- Open questions / decisions pending:
  - `bot_futures.py` — NOT yet audited for reconciliation/P&L bugs or DRY refactor.
  - Scalper: consider whether to raise `peak_drawdown_trigger_pct` above 10%.
