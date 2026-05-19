# LWG Capital LLC — Algo Trading Suite
## Claude Context File

> Drop this at the start of any Claude chat or Claude Code session.
> Keep it updated as the project evolves.

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
- **Monitoring:** Telegram bot for alerts, reporter.py for daily summaries, monitor.py for health checks
- **Scheduling:** Windows Task Scheduler via XML task files
- **Backup:** `backup.py` runs twice daily (midnight + noon CT) via SYS_BACKUP. Commits VPS runtime
  data to the `backups` orphan branch via a git worktree at `C:\algos-backup`. Never touches `main`,
  so Mac deploys and VPS backups never conflict. See README § VPS Data Backup for full file list.

---

## Repo Structure

```
algos/
├── algo.py                    ← Mac control panel
├── backup.py                  ← Twice-daily backup to backups branch
├── CONTEXT.md                 ← This file
├── stress_test_suite.py
├── instructions/              ← Standing instructions for Claude Code sessions
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

## What Was Done This Session (2026-05-19)

### Bug 1 — Silent bot hangs (FIXED)
All 4 bots had `input("Type CONFIRM to start:")` behind a `sys.stdin.isatty()` check.
Windows Task Scheduler allocates a real console, so `isatty()` returned `True` and the bots
blocked forever waiting for keyboard input — appearing alive in the process list but never trading.
Fix: removed the prompt entirely. Entry point is now just `run()`.

### Bug 2 — Log close never called (FIXED — most critical)
All 4 bots called `log_entry()` on trade open but **never called `log_close()`** on close.
Result: every trade in `*_trades.json` had `outcome: null`, `pnl_usd: null`, `close_price: null`.
AI brain had zero training data. Telegram `/balance` always showed starting balance.

Fix applied to all 4 bots:
- Added `get_deal_result(ticket)` helper — queries `mt5.history_deals_get()` to get close price
  and P&L for positions closed externally by the broker (SL/TP hit)
- `close_position()` now returns `(success, close_price, pnl_usd)` instead of a plain bool
- `manage_positions()` and `handle_dead_zone()` now accept `logger` and `ai` as parameters
- Every trade removal — SL/TP hit, momentum flip, max hold, dead zone, market close — calls
  `logger.log_close(ticket, cp, pnl)` and `ai.on_trade_closed(ticket, cp, pnl)`
- Fixed `risk_usd=0.0` in all `log_entry()` calls — now passes actual dollar risk amount

### Bug 3 — Log staleness alert added to monitor.py
Monitor now detects "alive but blocked" bots: if process is running but log file hasn't been
written in 90 minutes, sends Telegram alert with last log line. Controlled by `LOG_STALE_MINUTES = 90`.

### Full account reset
- All 4 MT5 accounts reset to $1,000 via broker backoffice (old equity was from a buggy period)
- All VPS tracking files reset: `*_trades.json → []`, `*_equity.json → [{balance:1000}]`,
  `*_weekly.json → {weekly_start:1000}`, `bot_state.json` balances zeroed
- Backup branch cleared of stale pre-reset data; fresh backup committed at 2026-05-19 05:13 UTC
- All 4 bots restarted cleanly. Scalper killed → file wiped → restarted (in that order) to ensure
  it loaded the empty file rather than writing its stale in-memory state back to disk.

### Current VPS state (as of end of session)
- All 4 bots running: `BOT_SMC_TREND`, `BOT_MEAN_REVERSION`, `BOT_SCALPER`, `BOT_FFT`
- Telegram bot running: `SYS_TELEGRAM`
- All `*_trades.json`: 0 entries (clean slate)
- No `.pkl` model files exist (AI never trained — log_close was broken)
- Next closed trade on any bot = first real data point with outcome populated

---

## What I Am Working On (Update This Section Each Session)

_Fill this in at the start of each Claude Code or chat session:_

- Last completed: Full fix + reset described above. All systems clean as of 2026-05-19.
- Currently working on: Live validation — confirm next closed trade appears with `outcome`,
  `pnl_usd`, `close_price` populated in `*_trades.json`.
- Next up: Monitor AI training — once 15 closed trades accumulate per bot, verify first model
  trains and AUC gate passes. Then check Calmar tracking is updating correctly.
- Open questions / decisions pending:
  - `bot_futures.py` — NOT yet audited for the same missing `log_close` bug
  - Consider whether `pnl_tracker.py` needs updating now that trades will have real `pnl_usd` values
