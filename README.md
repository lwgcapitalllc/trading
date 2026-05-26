# LWG Capital — Trading Operations

## Systems

### algos/
Automated algo trading suite for XAUUSD on PU Prime demo accounts.
Runs on Windows VPS (ForexVPS). Three instances: gold_main, gold_scalper, gold_fft.
See algos/README.md for full documentation.

### smart-money/
Smart money replication system. Scans and profiles the most consistent
crypto and forex traders for copy trading candidate pool construction.
See smart-money/README.md for full documentation.

### command-center/
Local operations platform for both systems above. React + FastAPI app.
Monitors bots via VPS SSH, surfaces Smart Money pipeline output, and
exposes config editing for the pipeline. See command-center/CLAUDE.md
for build status and what still needs to be done.

```bash
cd command-center && ./start.sh
# Frontend: http://localhost:5173
# Backend:  http://localhost:8000/docs
```

## VPS
- Provider: ForexVPS
- OS: Windows
- SSH alias: forexvps
- Deploy path: C:\trading\algos

## Repository
- Main branch: active development
- Backups branch: VPS data backups (orphan branch, never merges to main)
