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

**Last action:** Stage 1 has been run once. Pool was too thin (1 qualified wallet). Config has been updated and bugs fixed. Ready to rerun Stage 1.

**Next step:** `python3 run_stage1.py` — expect ~17 min runtime.

### Config changes made (from original spec)
| Setting | Original | Current | Reason |
|---|---|---|---|
| `min_win_rate` | 80% | 75% | Pool too thin at 80% — top PnL earners are high-leverage, not consistent win-rate traders |
| `min_wallet_age_days` | 90 | 120 | Require 4 months of history |
| `lookback.minimum_days` | 90 | 120 | Require 4 months of active trading span (separate from wallet age) |

### Bugs found and fixed in Stage 1
1. **Leaderboard endpoint changed** — Hyperliquid deprecated `POST /info` with `type:leaderboard`. Now uses `GET https://stats-data.hyperliquid.xyz/Mainnet/leaderboard` with different response schema. Fixed in `scanner/hyperliquid.py`.
2. **HTTP error retry loop** — `if e.response` evaluates False for 4xx responses, so all HTTP errors retried 3x instead of failing fast. Fixed: `if e.response is not None`.
3. **Pre-filtering** — Original code made 37k fills API calls (one per leaderboard entry). Fixed by pre-filtering leaderboard by allTime PnL ≥ $10k and account value ≥ $1k, then capping to top 500. Runtime: ~17 min.
4. **Span gate missing** — Age check (`min_wallet_age_days`) measured wallet creation date, not trading history length. A wallet 4 months old but trading for only 22 days passed. Fixed: added `lookback.minimum_days` span gate in `profiler/filters.py:QualificationGate.evaluate`.

### Watchlist feature
Wallets that fail only the span gate (short trading history but strong performance) are preserved in `reports/stage1_watchlist_*.json` instead of silently dropped. Sorted by total PnL descending. First run had 1 watchlist candidate: `0x2d23b731...` — 2612% growth, 72.5% WR, 22-day span.

## Thresholds

All in `config/config.json`. Edit there — never in code.

| Threshold | Default |
|---|---|
| Min win rate | 80% (per 30-day window) |
| Max drawdown | 20% |
| Min trades | 100 |
| Min wallet age | 90 days |
| Max hold time | 72 hours |
| Max single trade PnL share | 40% |
| Min active weeks per month | 3 |

## Output Location

All reports land in `smart-money/reports/`:
- `stage1_top20_*.json` — full wallet intelligence profiles
- `stage1_top20_*.csv` — flat CSV for spreadsheet review
- `stage1_summary_*.md` — human-readable summary
- `stage1_disqualified_*.json` — full disqualification log
- `stage5_final_report_*.json` — unified pool final report
- `stage5_summary_*.md` — final markdown summary

## Database

SQLite at `data/smart_money.db`. Schema: wallets, trades, monthly_windows, disqualified, scores, run_log.
Reruns are idempotent — each run overwrites prior results for the same wallet.

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
