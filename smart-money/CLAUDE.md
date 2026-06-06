# CLAUDE.md — Smart Money Replication System

**Last reviewed:** 2026-06-01

## What This System Does

Scanner, profiler, and ranker for identifying consistent crypto and forex traders.
Output is a ranked candidate pool report. No trading, no execution — research only.

## How to Run

```bash
cd smart-money

# Full pipeline — both default + bot profiles (RECOMMENDED — catches all trader types)
python3 main.py --all-profiles --skip-stage2

# Full pipeline — default profile only (consistent long-term traders)
python3 main.py --skip-stage2

# Stage 1 only — both profiles (catches consistent traders + short-burst high-ROI bots)
python3 run_stage1.py --all-profiles

# Stage 1 only — bot profile (14-60 day wallets, 70% WR, active bots)
python3 run_stage1.py --profile bot

# Stage 1 only — default profile (consistent human-scale traders)
python3 run_stage1.py

# Individual stages (all independently rerunnable)
python3 run_stage2.py              # Manual validation helper (read-only)
python3 run_stage3.py              # Solana + Ethereum (needs API keys)
python3 run_stage4.py              # Forex (needs API keys)
python3 run_stage5.py              # Unified final report

# Stage 1 with relaxed win rate (if pool is too small)
python3 run_stage1.py --win-rate 0.75

# Stage 1 dry run — skip API calls entirely, re-profile wallets already in DB
python3 run_stage1.py --dry-run

# Validate a specific wallet address
python3 run_stage2.py --address 0xYOUR_WALLET_ADDRESS
```

## Stage Status

| Stage | Status | Notes |
|---|---|---|
| Stage 1 | Fully implemented | Hyperliquid public API — no keys needed |
| Stage 2 | Fully implemented | Read-only validation — no API calls |
| Stage 3 | Scaffold only | Needs DUNE_API_KEY, FLIPSIDE_API_KEY, BIRDEYE_API_KEY |
| Stage 4 | Scaffold only | Needs MYFXBOOK_EMAIL, MYFXBOOK_PASSWORD, FX_BLUE_SESSION |
| Stage 5 | Fully implemented | Reads from DB — requires Stages 1+ to have run |

## Simulation Tool

`simulate_configs.py` re-runs qualification logic against all trades in the DB. No API calls.
Two grid profiles: default (3,780 combos, ~5s) and bot (~15k combos, ~10s, also varies
max_hold_hours and max_trade_conc).

```bash
python3 simulate_configs.py                        # default profile, top 40 configs
python3 simulate_configs.py --profile bot          # bot-specific grid
python3 simulate_configs.py --min-qualify 5        # only show configs with ≥5 qualifiers
python3 simulate_configs.py --detail               # list individual wallets for best config
python3 simulate_configs.py --export               # write reports/sim_results.{json,csv}
python3 simulate_configs.py --apply-best           # patch config.json with best config found
python3 simulate_configs.py --profile bot --apply-best  # patch bot.json instead
```


## Copy Trading Roadmap

Full automation plan is documented in `COPY_TRADING_ROADMAP.md`. Summary:

| Phase | What | Status |
|---|---|---|
| 1 | Config tuning + fresh scan | **Ready now** |
| 2 | Daily automated scan + Telegram alerts on status change | Not started |
| 3 | Live WebSocket mirroring — copy trades in real time | Not started |
| 4 | Vault copy integration (deposit into trader's Hyperliquid vault) | Not started |
| 5 | Risk framework (per-trader allocation, daily loss limits) | Designed, not built |

## Thresholds

All in `config/config.json` (default) or `config/templates/bot.json` / `config/templates/human.json`. Edit there — never in code.

| Threshold | Default | Bot | Human |
|---|---|---|---|
| Min win rate (per 30-day window) | **55%** | **70%** | 60% |
| Min overall win rate (all trades) | **50%** | **45%** | 55% |
| Max inactive days | **30** | **30** | 30 |
| Max drawdown | **30%** | **35%** | 25% |
| Min trades | 100 | 100 | 100 |
| Min wallet age | 90 days | **14 days** | 90 days |
| Min trading span | 90 days | **14 days** | 90 days |
| Max hold time | 72 hours | **48 hours** | 72 hours |
| Max single trade PnL share | 40% | **disabled** | 40% |
| Min active weeks per month | 2 | **1** | 2 |
| Data coverage flag threshold | 10% | 10% | 10% |
| Leaderboard candidates scanned | 3000 | **3000** | 3000 |

**Bot profile key differences:** wallet age + span gate at 14 days (catches sprint bots active
as little as 2 weeks); 70% per-window win rate floor (grid-searched: ~21 active traders in the
old DB — strict by design, algo accounts should be consistently profitable); drawdown 35%
(slightly more headroom for volatile systems, still a hard safety guard); hold time 48h
(scalpers and short-term algos); leaderboard depth 3000 (high-ROI bots can be mid-tier in
dollar PnL).

## Output Location

All reports land in `smart-money/reports/`:
- `stage1_top{N}_*.json` — full wallet intelligence profiles (N = qualifying candidate count)
- `stage1_top{N}_*.csv` — flat CSV for spreadsheet review
- `stage1_summary_*.md` — human-readable summary
- `stage1_disqualified_*.json` — full disqualification log
- `stage5_final_report_*.json` — unified pool final report
- `stage5_summary_*.md` — final markdown summary

## Database

SQLite at `data/smart_money.db`. Schema: wallets, trades, monthly_windows, disqualified, scores, run_log, **fills_cache**.
Reruns are idempotent — each run overwrites prior results for the same wallet.
`fills_cache` stores raw API fills per wallet with a `fetched_at` timestamp. TTL controlled by `hyperliquid.fills_cache_hours` (default 24h). Re-runs within TTL skip all API calls.

## File Structure

```
smart-money/
├── config/config.json          ← All thresholds
├── database.py                 ← SQLite layer (shared by all stages)
├── run_logger.py               ← Pipeline logging utility
├── run_progress.py             ← Atomic progress.json writer (polled by command-center)
├── main.py                     ← Full pipeline orchestrator
├── run_stage1.py               ← Stage 1 entrypoint
├── run_stage2.py               ← Stage 2 validation helper
├── run_stage3.py               ← Stage 3 entrypoint
├── run_stage4.py               ← Stage 4 entrypoint
├── run_stage5.py               ← Stage 5 entrypoint
├── scanner/
│   ├── hyperliquid.py          ← API client + leaderboard scanner
│   ├── solana.py               ← Dune + Flipside + Birdeye (scaffold)
│   └── ethereum.py             ← GMX + dYdX + DeBank (scaffold)
├── profiler/
│   ├── hyperliquid_profiler.py ← Fill matching + balance reconstruction
│   ├── filters.py              ← Monthly windows + all qualification filters
│   ├── scorer.py               ← Composite 1–100 scoring model
│   └── reporter.py             ← Wallet intelligence report + exports
├── forex/
│   ├── myfxbook.py             ← Myfxbook API (scaffold)
│   └── fx_blue.py              ← FX Blue (scaffold)
├── ranking/
│   └── unified_pool.py         ← Stage 5 unified merge + final report
├── data/
│   ├── smart_money.db          ← SQLite database
│   └── smart_money.log         ← Full pipeline run log
└── reports/                    ← All output files
```

## Never Do

- Touch `algos/` while working here — fully separate system
- Make API calls from Stage 2 (it is read-only by design)
- Commit `MYFXBOOK_PASSWORD`, `BIRDEYE_API_KEY`, or any API keys to git
- Hardcode any threshold — it goes in `config/config.json`
