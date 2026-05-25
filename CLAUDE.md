# CLAUDE.md — LWG Capital Monorepo
## Standing Instructions for Claude Code

Read this file fully before touching any code. Subsystem-specific rules are in each subsystem's own CLAUDE.md.

---

## Repo Structure

```
trading/
├── algos/          ← Live algo trading suite (XAUUSD, Windows VPS)
└── smart-money/    ← Smart money replication system (Mac-only, under construction)
```

These systems are **fully independent**. Changes to one never affect the other.

---

## System Summaries

### algos/
Live automated trading on PU Prime demo accounts. Three bot instances: gold_main, gold_scalper, gold_fft. Runs on Windows VPS (ForexVPS) via Windows Task Scheduler. Full rules in `algos/CLAUDE.md`.

### smart-money/
Scans and profiles consistent crypto/forex traders for copy trading candidate pool construction. Runs locally on Mac. Not yet in production. No live risk.

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

- Commit `credentials.json`, `users.json`, `.env`, or any `.pkl` model files to main branch
- Touch `algos/` when working on `smart-money/` and vice versa
- Delete `C:\algos` on VPS (old location, kept as rollback until confirmed stable)
