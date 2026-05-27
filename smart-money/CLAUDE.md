# CLAUDE.md — Smart Money Replication System

## What This System Does

Scanner, profiler, and ranker for identifying consistent crypto and forex traders.
Output is a ranked candidate pool report. No trading, no execution — research only.

## How to Run

```bash
cd smart-money

# Full pipeline (pauses at Stage 2 for manual review)
python main.py

# Full pipeline automated (no pause)
python main.py --skip-stage2

# Individual stages (all independently rerunnable)
python run_stage1.py              # Hyperliquid — main data source
python run_stage2.py              # Manual validation helper (read-only)
python run_stage3.py              # Solana + Ethereum (needs API keys)
python run_stage4.py              # Forex (needs API keys)
python run_stage5.py              # Unified final report

# Stage 1 with relaxed win rate (if pool is too small)
python run_stage1.py --win-rate 0.75

# Validate a specific wallet address
python run_stage2.py --address 0xYOUR_WALLET_ADDRESS
```

## Stage Status

| Stage | Status | Notes |
|---|---|---|
| Stage 1 | Fully implemented | Hyperliquid public API — no keys needed |
| Stage 2 | Fully implemented | Read-only validation — no API calls |
| Stage 3 | Scaffold only | Needs DUNE_API_KEY, FLIPSIDE_API_KEY, BIRDEYE_API_KEY |
| Stage 4 | Scaffold only | Needs MYFXBOOK_EMAIL, MYFXBOOK_PASSWORD, FX_BLUE_SESSION |
| Stage 5 | Fully implemented | Reads from DB — requires Stages 1+ to have run |

## Where We Left Off

**Last action (2026-05-27):** Full session of bug fixes and pipeline improvements. Ready for a clean run.

**Next step:** Run pipeline from the UI (BOT profile) — first run will fetch from API (~13-15 min); every re-run same day will be ~30s from cache.

### Config changes made (from original spec)
| Setting | Original | Current | Reason |
|---|---|---|---|
| `min_win_rate` | 80% | 75% (human), 70% (bot) | Pool too thin at 80% |
| `min_active_weeks_per_month` | 3 | 2 | Too restrictive — top traders burst, not steady |
| `requests_per_second` | (via delay) | 2 (human), 3 (bot) | Replaced `rate_limit_delay_seconds` with shared token bucket |
| `fills_cache_hours` | — | 24 | New — skip re-fetching wallets scanned within 24h |

### All bugs found and fixed
1. **Leaderboard endpoint changed** — Hyperliquid deprecated `POST /info` with `type:leaderboard`. Fixed in `scanner/hyperliquid.py`.
2. **HTTP error retry loop** — `if e.response` evaluates False for 4xx. Fixed: `if e.response is not None`.
3. **Pre-filtering** — Was making 37k API calls. Fixed by pre-filtering leaderboard and capping to top 500.
4. **Span gate used window boundaries** — Fixed: now uses `max(close_ts) - min(close_ts)` across actual trades.
5. **Per-worker rate limiting** — N workers × rate = N× actual RPS → mass 429s. Fixed: shared `_SharedRateLimiter` token bucket across all workers. 429 backoff increased from 0.2-0.8s to 5-15s.
6. **Disqualified list accumulated all-time DB records** — Fixed: `current_disqualified` list scoped to current run only.
7. **`KeyError: rate_limit_delay_seconds`** — `run_stage1.py` read removed config key directly. Fixed: `.get()` with fallback.

### Watchlist feature
Wallets that fail only the span gate (short trading history but strong performance) are preserved in `reports/stage1_watchlist_*.json` instead of silently dropped. Sorted by total PnL descending.

## Thresholds

All in `config/config.json`. Edit there — never in code.

| Threshold | Default |
|---|---|
| Min win rate | 75% (per 30-day window) |
| Max drawdown | 20% |
| Min trades | 100 |
| Min wallet age | 90 days |
| Min trading span | 90 days |
| Max hold time | 72 hours |
| Max single trade PnL share | 40% |
| Min active weeks per month | 2 |

## Output Location

All reports land in `smart-money/reports/`:
- `stage1_top20_*.json` — full wallet intelligence profiles
- `stage1_top20_*.csv` — flat CSV for spreadsheet review
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
