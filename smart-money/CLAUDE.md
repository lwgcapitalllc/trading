# CLAUDE.md — Smart Money Replication System

## What This System Does

Scanner, profiler, and ranker for identifying consistent crypto and forex traders.
Output is a ranked candidate pool report. No trading, no execution — research only.

## How to Run

```bash
cd smart-money

# Full pipeline — both default + bot profiles (RECOMMENDED — catches all trader types)
python main.py --all-profiles --skip-stage2

# Full pipeline — default profile only (consistent long-term traders)
python main.py --skip-stage2

# Stage 1 only — both profiles (catches consistent traders + short-burst high-ROI bots)
python run_stage1.py --all-profiles

# Stage 1 only — bot profile (30-60 day wallets, 1000%+ ROI, active bots)
python run_stage1.py --profile bot

# Stage 1 only — default profile (consistent human-scale traders)
python run_stage1.py

# Individual stages (all independently rerunnable)
python run_stage2.py              # Manual validation helper (read-only)
python run_stage3.py              # Solana + Ethereum (needs API keys)
python run_stage4.py              # Forex (needs API keys)
python run_stage5.py              # Unified final report

# Stage 1 with relaxed win rate (if pool is too small)
python run_stage1.py --win-rate 0.75

# Stage 1 dry run — skip API calls entirely, re-profile wallets already in DB
python run_stage1.py --dry-run

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

## Simulation Tool

`simulate_configs.py` re-runs qualification logic across 3,780 config combinations against
all trades already in the DB. No API calls. Completes in ~5 seconds.

```bash
python simulate_configs.py                 # top 40 configs by qualifier count
python simulate_configs.py --min-qualify 5 # only show configs with ≥5 qualifiers
python simulate_configs.py --detail        # list individual wallets for the best config
python simulate_configs.py --export        # write reports/sim_results.{json,csv}
python simulate_configs.py --apply-best    # patch config.json with the best config found
```

### What the simulation revealed (2026-05-27 run, 814 wallets)

| Finding | Detail |
|---|---|
| Max possible qualified traders (any config) | **23** |
| Current config → qualifiers | **1** (too restrictive) |
| Biggest single filter killing candidates | `max_drawdown=20%` removes 53% of remaining wallets |
| Second biggest | `strike_sys` (per-window win rate) removes 25% |
| Net losers on Hyperliquid | 51% of active wallets — net negative PnL |
| Wallets active within 30 days with 100+ trades | ~330 |

### Recommended config update

These settings yield ~15–20 qualified traders while still filtering noise:

| Setting | Current | → Use | Reason |
|---|---|---|---|
| `min_win_rate` (per window) | 75% | **55%** | 75% → 5 wallets; 55% → 18–22 |
| `min_overall_win_rate` | 55% | **50%** | Still meaningful; 55% is too high for this leaderboard |
| `max_inactive_days` | 60 | **30** | Copy trading needs active traders, not last-year stars |
| `max_drawdown` | 20% | **30%** | 20% cuts 53% of otherwise-good wallets; crypto is volatile |
| `min_trades` | 100 | 100 | Keep |
| `min_span_days` | 90 | 90 | Keep |

After changing config.json, clear the cache and re-scan:
```bash
# Via dashboard: Smart Money → Clear cache button
# Then: run pipeline (human profile)
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

## Where We Left Off

**Last action (2026-05-27, session 4):** Added `--all-profiles` flag to run both default
and bot profiles in one command. Updated bot profile: span gate 30d, wallet age 30d,
win rate floor 55%, max_inactive_days 30, leaderboard depth 3000. Clarified that short-burst
high-ROI bots (30–60 day active wallets) are wanted and supported — they must just not blow
their accounts (drawdown guard stays at 30%).

**Immediate next step:**
1. Clear fills cache: `python -c "import database; database.clear_fills_cache()"`
2. Run both profiles: `python run_stage1.py --all-profiles`
   - Pass 1 (default): consistent long-term traders (~13–15 min)
   - Pass 2 (bot): short-burst high-ROI bots (~13–15 min, shares leaderboard fetch)
3. Review all qualified wallets in dashboard (both profiles write to same DB)

### Quality fixes added (2026-05-27, session 2)

After reviewing the first run results (7 qualified wallets, all now failing the new filters), three structural problems were found and fixed:

**1. Recency filter** (`qualification.max_inactive_days`)
- Wallets must have a trade within the last N days or they are disqualified.
- Solves: one-time-wonder accounts (made all their money in one month in 2024, dormant since) were ranking at the top because their single-month metrics looked perfect.
- Bot: 45d | Human: 60d | Default: 60d

**2. Overall win rate floor** (`qualification.min_overall_win_rate`)
- Aggregate win rate across all matched trades must meet a hard minimum.
- Solves: high R/R "sniper" strategies (6.9% and 19.2% win rates) were passing qualification because the per-window strike system only disqualifies on *consecutive* bad months — their bad months were always separated by one recovery month.
- Bot: 50% | Human: 60% | Default: 55%

**3. Data coverage flag** (`hyperliquid.min_data_coverage_pct`)
- Computes `captured_pnl / leaderboard_all_time_pnl` for each wallet. If below threshold, adds a yellow flag and logs a warning with the dollar gap.
- Solves: the Hyperliquid fills API only returns a recent slice of history for most wallets (e.g. wallet with $1.65M all-time PnL had only $12.7k captured = 0.8% coverage). All metrics for that wallet are based on unrepresentative data.
- Does NOT disqualify — just flags. The recency filter handles the main consequence.
- Threshold: 10% (all profiles)
- Surfaced in `flags.data_coverage_pct` in JSON, CSV, and `candidates.json`.

**Validation:** All 7 wallets from the 2026-05-27 run now correctly fail:
- Ranks 1–5: inactive 85–330 days (recency filter)
- Ranks 6–7: 6.9% and 19.2% overall win rate (win rate floor)

### Config changes made (from original spec)
| Setting | Original | Current | Reason |
|---|---|---|---|
| `min_win_rate` | 80% | 75% (human), 70% (bot) | Pool too thin at 80% |
| `min_overall_win_rate` | — | 55% (default), 50% (bot), 60% (human) | New — blocks low-win-rate sniper strategies |
| `max_inactive_days` | — | 60d (default/human), 45d (bot) | New — blocks dormant accounts |
| `min_data_coverage_pct` | — | 10% (all) | New — yellow flag when fills API coverage is thin |
| `min_active_weeks_per_month` | 3 | 2 | Too restrictive — top traders burst, not steady |
| `requests_per_second` | (via delay) | 2 (human), 3 (bot) | Replaced `rate_limit_delay_seconds` with shared token bucket |
| `fills_cache_hours` | — | 24 | New — skip re-fetching wallets scanned within 24h |

### All bugs found and fixed (session 1)
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

All in `config/config.json` (default) or `config/templates/bot.json` / `config/templates/human.json`. Edit there — never in code.

| Threshold | Default | Bot | Human |
|---|---|---|---|
| Min win rate (per 30-day window) | **55%** | **55%** | 60% |
| Min overall win rate (all trades) | **50%** | **45%** | 55% |
| Max inactive days | **30** | **30** | 30 |
| Max drawdown | **30%** | 30% | 25% |
| Min trades | 100 | 100 | 100 |
| Min wallet age | 90 days | **30 days** | 90 days |
| Min trading span | 90 days | **30 days** | 90 days |
| Max hold time | 72 hours | **24 hours** | 72 hours |
| Max single trade PnL share | 40% | **disabled** | 40% |
| Min active weeks per month | 2 | **1** | 2 |
| Data coverage flag threshold | 10% | 10% | 10% |
| Leaderboard candidates scanned | 3000 | **3000** | 3000 |

**Bot profile key differences:** wallet age + span gate dropped to 30 days (catches 30–60 day sprint bots); hold time 24h max (scalpers/algos); win rate lowered to 55% (trend-following bots have high R:R not high win %); drawdown stays at 30% (the only hard safety guard); leaderboard depth widened to 3000 (high-ROI bots can be mid-tier in dollar PnL).

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
