# LWG Capital LLC — Algo Trading Suite
## Claude Context File

---

## What This Project Is

Multi-bot, multi-instrument algorithmic trading system for FX/metals/indices and futures (MNQ).
Built in Python, runs 24/7 on a Windows VPS (ForexVPS, IP: 45.82.164.112).
Controlled from Mac via `algo.py` command-line panel.
Code lives on GitHub. Deploy flow: edit on Mac → git push → ssh pull on VPS → algo restart.

Each bot scans a configurable watchlist every cycle and trades the highest-scoring setup.
Watchlists live inside each bot's config section (`bot_smc_trend.watchlist`, etc.).

---

## The Bots

| Bot | File | Strategy | Watchlist | Account | MT5 Instance |
|-----|------|----------|-----------|---------|--------------|
| SMC Trend | `bot_smc_trend.py` | Judas Swing + FVG, H4 trend filter, M15 | XAUUSD, EURUSD, GBPUSD, XAGUSD, US30 | gold_main #700103491 | PU Prime Terminal |
| Mean Reversion | `bot_mean_reversion.py` | BB + RSI + VWAP, 1R target, fast close | XAUUSD, EURUSD, AUDUSD, USDCAD, EURGBP | gold_main #700103491 | PU Prime Terminal |
| Scalper | `bot_scalper.py` | EMA stack + pullback, M5/M1, 5–20 trades/day | XAUUSD, US30, NAS100, EURUSD, GBPUSD | gold_scalper #700107520 | MT5_Scalper |
| FFT | `bot_fft.py` | Dual Fibonacci confluence, H1+H4 trend | XAUUSD only (Phase 5 gate) | gold_fft #700107749 | MT5_FFT |
| Futures | `bot_futures.py` | SMC_TREND on MNQ via Tradovate API | MNQ only | futures_account1 | N/A (Tradovate) |

SMC Trend and Mean Reversion share one MT5 account and are designed to be uncorrelated — one works trending markets, the other ranging markets.
Scalper is isolated on its own account due to high volatility (+50% / -8% swings possible).
FFT is the lowest risk (1%) — gold-only until 30+ closed trades with solid Calmar (Phase 5 gate).

---

## Shared Components

| File | Role |
|------|------|
| `shared_ai_brain.py` | AI engine (Claude API), trade logger, daily performance logger |
| `shared_calmar.py` | Calmar ratio tracker, morning report |
| `shared_regime.py` | Market regime classifier: TRENDING / TRANSITIONING / RANGING |
| `shared_scanner.py` | Multi-instrument watchlist scanner — `InstrumentScanner` + `SetupCandidate` |
| `shared_risk.py` | Dynamic risk / capacity engine — `RiskEngine` tracks portfolio-level risk budget per bot |
| `mt5_ops.py` | All MT5 operations — symbol-parameterized, single shared instance per bot |
| `bot_utils.py` | Config loader, logging, path resolver |
| `launcher.py` | Universal Task Scheduler launcher |
| `startup_coordinator.py` | Orchestrates bot startup sequence |
| `tradovate.py` | Tradovate API executor for Bot Futures |
| `algo.py` | Mac control panel — start/stop/status/logs/restart |

**Multi-instrument architecture (Phases 1–3):**
- `InstrumentScanner.scan(detect_fn)` iterates the watchlist, calls `detect_fn(symbol) → dict|None` per symbol, ranks by confluence score, returns sorted candidates
- **Phase 2 volatility filter:** before calling detect_fn, the scanner computes `atr_ratio = ATR(5) / ATR(20)` on H1 candles per symbol; symbols below `min_atr_ratio` (default 0.8) are skipped; if the entire watchlist is below the floor and `force_trade=false`, the bot sits out the cycle — configured per bot in config.json
- **Phase 3 dynamic risk engine:** `RiskEngine` tracks `available_risk = daily_budget − used_risk − realized_daily_loss`. `used_risk` is computed from live MT5 SL positions each cycle — trades at breakeven contribute ~0, trades with SL trailing in profit contribute negative (locked gain). Before any new entry, each bot calls `risk_engine.can_enter(open_trades, balance, proposed_risk_pct)` and sizes with `risk_engine.sized_risk_pct()` to cap allocation. Default `daily_budget_pct` equals each bot's existing daily loss cap so day-one behaviour is identical. Phase 4 correlation control and Phase 5 AI gate cap to follow.
- Each bot picks `candidates[0]` (best setup) and enters
- All MT5 methods accept `symbol=None` (defaults to bot's primary symbol)
- `move_sl`, `close_position`, `partial_close` read `pos[0].symbol` from the live MT5 position — instrument-agnostic
- `close_all_positions(symbols=WATCHLIST)` covers all instruments in emergency closes
- Per-trade `symbol`, `atr`, and `lots` stored in trade dict at entry; position management uses them for correct trailing stop distances and risk engine calculations
- Unresolved watchlist symbols: WARNING log + `symbol_errors.log` + bot_state flag → monitor.py alert (once/day/symbol)

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
- **Notifications:** Event-driven — bots self-report startup, algo.py fires on control panel actions, monitor.py detects crashes (Bot Offline/Online ≤1 min) and loop stalls (process up but log stale >5 min → STALLED status). Intentional stops suppressed via `stop_suppress.json`. reporter.py handles daily summaries.
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
│   ├── shared_regime.py
│   ├── shared_scanner.py       ← Multi-instrument scanner (InstrumentScanner)
│   ├── shared_risk.py          ← Dynamic risk engine (RiskEngine) — Phase 3
│   └── mt5_ops.py             ← All MT5 operations, symbol-parameterized
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

- Last completed: **Phase 3 Dynamic Risk / Capacity Engine**
  - New `shared/shared_risk.py` — `RiskEngine` class.
  - `available_risk = daily_budget − used_risk − realized_daily_loss`. `used_risk` computed from live MT5 SL distance each cycle; trades at BE contribute ~0, trades trailing in profit contribute negative (open capacity).
  - All four FX bots now call `risk_engine.can_enter()` before new entries and `risk_engine.sized_risk_pct()` to cap allocation. `lots` added to all trade dicts so the engine can compute per-trade risk without extra MT5 calls.
  - `daily_budget_pct` added to all config sections (defaults to each bot's existing daily loss cap — day-one behavior identical).
  - Phase 4 (correlation control) and Phase 5 (AI gate cap) are the next phases per MULTI_INSTRUMENT_UPGRADE.md.
- Previously: **Phase 2 Volatility Filter** and **Phase 1 Multi-Instrument Scanner**.
- Open questions / decisions pending:
  - `bot_futures.py` — NOT yet audited for reconciliation/P&L bugs or DRY refactor.
  - Scalper: consider whether to raise `peak_drawdown_trigger_pct` above 10%.
