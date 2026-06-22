## Communication Rules — Non-Negotiable

- Plain English only. Short sentences.
- Never use bullet points to explain a simple thing.
- No preamble. No "Great question." No "Sure, I can help with that."
- Spawn subagents for routine tasks. Work sequentially unless the task explicitly requires parallel execution.


# CLAUDE.md — LWG Capital Monorepo

**Purpose:** Standing instructions for Claude Code across all subsystems.
**Scope:** This covers repo-wide rules, VPS workflow, and branch conventions. It does NOT cover subsystem internals — each subsystem has its own CLAUDE.md.
**Status:** Active — six subsystems in various stages of production.
**Last reviewed:** 2026-06-12

---

## Repo Structure

```
trading/
├── algos/           ← Live algo trading suite (XAUUSD, Windows VPS)
├── smart-money/     ← Smart money replication system (Mac-only, active)
├── command-center/  ← Local operations platform (React + FastAPI)
├── regime/          ← Shared market regime classifier (bots + backtest lab)
├── strategies/      ← Generic trading strategy source files, organized by runner platform
├── scripts/         ← Cross-subsystem VPS recovery and bootstrap scripts
└── docs/            ← Cross-subsystem reference docs and audit tools
```

`algos/`, `smart-money/`, and `command-center/` are fully independent from each other. `regime/` is a shared library imported by `algos/` (via shim) and `command-center/` (directly). `strategies/` is consumed by `command-center/` (scanner + deploy) and deployed to the VPS (NT8 strategy folder).

---

## System Summaries

### algos/
Automated trading on PU Prime demo accounts (Windows VPS via Task Scheduler). No live bots currently — the four first-attempt bots (SMC Trend, Scalper, FFT, Mean Reversion) were deleted 2026-06-22 to rebuild the suite backtest-first per `docs/BOT_DEVELOPMENT_METHOD.md`. Deployment learnings (MT5 connection, configs, scheduler, liveness layer) are preserved in `algos/docs/BOT_DEPLOYMENT_INFRA.md`. Full rules in `algos/CLAUDE.md`.

### smart-money/
Scans and profiles consistent crypto/forex traders for copy trading candidate pool construction. Runs locally on Mac. Stages 1–2 and 5 live; Stages 3–4 need API keys. Full rules in `smart-money/CLAUDE.md`.

### command-center/
React + FastAPI local operations platform. Monitors bots via SSH, surfaces Smart Money pipeline output, runs and evaluates NinjaTrader and MT5 backtests. Full rules in `command-center/CLAUDE.md`.

### regime/
Shared market regime classifier. Imported by the live bots (via `algos/shared/shared_regime.py` thin shim) and by the command-center backtest lab. Single output set: 5 labels (TRENDING, TRANSITIONING, RANGING, HIGH_VOLATILITY, LOW_VOLATILITY). Each bot owns its own `REGIME_RISK_TABLE` mapping labels to trade decisions. Full rules in `regime/CLAUDE.md`. Algorithm documented in `regime/REGIME_CLASSIFIER.md`.

### strategies/
Generic trading strategy source files, organized by runner platform. `strategies/ninjatrader/` holds the only live NinjaScript strategy, `ORB.cs` (VWAP_MR and Momentum were deleted 2026-06-21 — they baked risk management into the strategy, against the gated-layer rules). The command center scanner reads from here to register strategies in the database; the Deploy button uploads files to the VPS (NT8 or MT5 folder by extension). `strategies/mt5/` holds one MQL5 strategy: `LondonBreakout.mq5` (instrument-agnostic Asian-range → London breakout). `strategies/tradovate/` is a placeholder. Full rules in `strategies/CLAUDE.md`.

### scripts/
Cross-subsystem VPS bootstrap and full-recovery scripts (`bootstrap_vps.ps1` for the MT5/algos side, `bootstrap_ninjatrader.ps1` for the NT8 side). Idempotent, run on a wiped or new VPS. Full run order in `scripts/README.md`.

---

## VPS Deploy Workflow

```bash
# Push changes
git add . && git commit -m "..." && git push

# Pull on VPS and restart bots
ssh forexvps "cd C:\trading && git pull origin main"
ssh forexvps "del C:\trading\algos\mt5_connect.lock 2>nul && taskkill /f /im python.exe"
sleep 3
ssh forexvps "schtasks /run /tn SYS_STARTUP"
sleep 60
ssh forexvps "wmic process where \"name='python.exe'\" get commandline 2>nul"
```

VPS path: `C:\trading\algos\` (main)

---

## Branches

- `main` — active development, all code changes go here

---

## Never Do

- Commit `credentials.json`, `users.json`, `.env`, any `.pkl` model files, or API tokens/keys
- Touch `algos/` when working on `smart-money/` or `command-center/` and vice versa
- Build a second regime classifier in `command-center/` or anywhere else — `regime/classifier.py` is the canonical implementation; all consumers import from there
