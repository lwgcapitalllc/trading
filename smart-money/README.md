# Smart Money Replication System

Scanner, profiler, and ranker for identifying consistent crypto and forex traders across Hyperliquid, Solana, Ethereum, and Myfxbook/FX Blue. Output is a ranked candidate pool report. No trading — research only.

## Running the pipeline

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

### Simulation tool

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

## Full documentation

See `CLAUDE.md` — stage status, thresholds, file structure, and current state.
