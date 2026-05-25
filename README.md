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

## VPS
- Provider: ForexVPS
- OS: Windows
- SSH alias: forexvps
- Deploy path: C:\trading\algos

## Repository
- Main branch: active development
- Backups branch: VPS data backups (orphan branch, never merges to main)
