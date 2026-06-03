# CLAUDE.md — LWG Capital Monorepo

**Purpose:** Standing instructions for Claude Code across all subsystems.
**Scope:** This covers repo-wide rules, VPS workflow, and branch conventions. It does NOT cover subsystem internals — each subsystem has its own CLAUDE.md.
**Status:** Active — four subsystems in various stages of production.
**Last reviewed:** 2026-06-02

---

## Repo Structure

```
trading/
├── algos/           ← Live algo trading suite (XAUUSD, Windows VPS)
├── smart-money/     ← Smart money replication system (Mac-only, active)
├── command-center/  ← Local operations platform (React + FastAPI)
├── regime/          ← Shared market regime classifier (bots + backtest lab)
└── docs/            ← Cross-subsystem reference docs and audit tools
```

`algos/`, `smart-money/`, and `command-center/` are fully independent from each other. `regime/` is a shared library imported by `algos/` (via shim) and `command-center/` (directly).

---

## System Summaries

### algos/
Live automated trading on PU Prime demo accounts. Three bot instances: gold_main, gold_scalper, gold_fft. Runs on Windows VPS (ForexVPS) via Windows Task Scheduler. Full rules in `algos/CLAUDE.md`.

### smart-money/
Scans and profiles consistent crypto/forex traders for copy trading candidate pool construction. Runs locally on Mac. Stages 1–2 and 5 live; Stages 3–4 need API keys. Full rules in `smart-money/CLAUDE.md`.

### command-center/
React + FastAPI local operations platform. Monitors bots via SSH, surfaces Smart Money pipeline output, runs and evaluates NinjaTrader backtests. Full rules in `command-center/CLAUDE.md`.

### regime/
Shared market regime classifier. Imported by the live bots (via `algos/shared/shared_regime.py` thin shim) and by the command-center backtest lab. Two modes: coarse (3 labels — what the bots use) and fine (5 labels — what the lab uses). Full rules in `regime/CLAUDE.md`. Algorithm documented in `regime/REGIME_CLASSIFIER.md`.

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

VPS paths: `C:\trading\algos\` (main), `C:\trading-backup\` (backups worktree)

---

## Branches

- `main` — active development, all code changes go here
- `backups` — orphan branch, VPS runtime data only, never merges to main

---

## Never Do

- Commit `credentials.json`, `users.json`, `.env`, any `.pkl` model files, or API tokens/keys to main branch
- Touch `algos/` when working on `smart-money/` or `command-center/` and vice versa
- Build a second regime classifier in `command-center/` or anywhere else — `regime/classifier.py` is the canonical implementation; all consumers import from there
