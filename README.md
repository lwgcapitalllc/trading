# Algo Suite — Master README

A multi-bot, multi-market algorithmic trading system built on MetaTrader 5.
Designed to scale across any instrument by separating shared code from per-instance configuration.

---

## Repository Structure

```
algos/
│
├── shared/                          # Shared libraries — imported by all bots
│   ├── shared_ai_brain.py           # AI learning engine + trade logger
│   ├── shared_calmar.py             # Calmar ratio tracker
│   └── shared_regime.py            # Market regime classifier
│
├── bots/                            # Bot scripts — one copy, used by all instances
│   ├── bot_utils.py                 # Config loader + path resolver
│   ├── launcher.py                  # Universal Task Scheduler launcher
│   ├── bot1_smc_trend.py            # Bot 1: SMC trend following
│   ├── bot2_mean_reversion.py       # Bot 2: Mean reversion
│   ├── bot3_scalper.py              # Bot 3: EMA momentum scalper
│   ├── README_BOT1.md
│   ├── README_BOT2.md
│   └── README_BOT3.md
│
└── markets/                         # Instance configs — one folder per deployment
    ├── fx/
    │   └── instances/
    │       ├── xauusd_main/         # Bot1 + Bot2 on XAUUSD
    │       │   └── config.json
    │       ├── xauusd_scalper/      # Bot3 on XAUUSD (separate account)
    │       │   └── config.json
    │       └── gbpjpy_main/         # Bot1 + Bot2 
    ├── crypto/
    │   └── instances/               # Future: BTCUSD etc
    └── futures/
        └── instances/               # Future: US30, NAS100 etc
```

---

## The Three Bots

| Bot | Strategy | When it trades | Per-trade risk | Purpose |
|---|---|---|---|---|
| Bot 1 | SMC Trend Following | London + NY kill zones only | 2% | Capital growth on big moves |
| Bot 2 | Mean Reversion | 24 hours | 2% | Cash flow during ranging markets |
| Bot 3 | EMA Scalper | All sessions except dead zone | 2–3.5% (auto-scaling) | Aggressive small account growth |

Bot 1 and Bot 2 run together on the same account — they are designed to be uncorrelated. Bot 3 runs on its own dedicated account due to its aggressive risk profile.

---

## How to Add a New Instrument or Market

1. Create a new folder under the appropriate market: `markets/fx/instances/eurusd_main/`
2. Copy any existing `config.json` into it
3. Edit the config: change `symbol`, adjust ATR parameters and risk levels for the new instrument
4. Add a new Task Scheduler task on the VPS pointing to `launcher.py` with the new `--config` path
5. Add Mac terminal aliases for the new instance

Zero code changes required. The bots read everything from config.

---

## Shared Components

### shared_ai_brain.py
Self-improving Random Forest classifier. Logs every trade with 13–15 features at entry. After 30 closed trades, trains a model using walk-forward validation (TimeSeriesSplit). Refuses to deploy if AUC ≤ 0.52. Retrains every 10 new trades. Each instance has its own model file stored in the instance directory.

### shared_calmar.py
Tracks daily equity and calculates Calmar ratio (annualised return / max drawdown). Jason Byers' #1 metric. Prints a morning report daily. Benchmarks: 2.0 = okay, 3.0 = decent, 5.0+ = generational edge.

### shared_regime.py
Classifies market conditions hourly using ADX(14), ATR ratio, and RSI range. Returns TRENDING / TRANSITIONING / RANGING. Bot 1 and Bot 2 read the same classifier but react opposite ways — Bot 1 is active in trends, Bot 2 is active in ranges.

---

## Running a Bot

On the VPS, each bot is launched via Task Scheduler using `launcher.py`:

```
python bots\launcher.py --bot bot1 --config markets\fx\instances\xauusd_main\config.json
python bots\launcher.py --bot bot2 --config markets\fx\instances\xauusd_main\config.json
python bots\launcher.py --bot bot3 --config markets\fx\instances\xauusd_scalper\config.json
```

From your Mac terminal (after SSH key setup):

```bash
xau-start      # start Bot 1 + Bot 2 (XAUUSD)
xau-stop       # stop Bot 1 + Bot 2
xau-status     # check running status
xau-log1       # view Bot 1 activity log
xau-log2       # view Bot 2 activity log
xau-start3     # start Bot 3 (XAUUSD scalper)
xau-stop3      # stop Bot 3
xau-log3       # view Bot 3 activity log
```

---

## Files Generated at Runtime (per instance)

All written to the instance directory (e.g. `markets/fx/instances/xauusd_main/`):

| File | Contents |
|---|---|
| `bot1.log` | Full Bot 1 activity log |
| `bot2.log` | Full Bot 2 activity log |
| `bot1_trades.json` | Every Bot 1 trade with features and outcomes |
| `bot2_trades.json` | Every Bot 2 trade with features and outcomes |
| `bot1_model.pkl` | Bot 1 trained AI classifier |
| `bot2_model.pkl` | Bot 2 trained AI classifier |
| `bot1_equity.json` | Bot 1 daily equity and Calmar |
| `bot2_equity.json` | Bot 2 daily equity and Calmar |
| `regime_state_BOT1.json` | Last regime reading |
| `regime_state_BOT2.json` | Last regime reading |

---

## Key Configuration Parameters

All parameters live in the instance `config.json`. Nothing is hardcoded in the bot scripts.

| Section | Key parameters |
|---|---|
| `account` | MT5 login, password, server |
| `symbol` | Instrument name exactly as shown in MT5 market watch |
| `risk` | Risk % per trade, min/max lot size |
| `protection` | Daily/weekly loss caps, cooldown times, news events |
| `bot1_trend` | Kill zone hours, confluence threshold, runner trail multipliers |
| `bot2_reversion` | BB period/std, RSI thresholds, VWAP multiplier |
| `bot3_scalper` | EMA periods, daily target, compounding tiers, dead zone hours |
| `regime` | ADX/ATR/RSI thresholds for regime classification |

---

## Jason Byers' Framework — What We Implemented

| Principle | Implementation |
|---|---|
| Two-bot portfolio: trend + reversion | Bot 1 + Bot 2 |
| Regime classifier prevents blowouts | shared_regime.py — governs both bots |
| HMM Monte Carlo stress testing | stress_test_suite.py (run locally) |
| Never trust backtested data | Walk-forward validation only in AI brain |
| Calmar ratio is the only metric | shared_calmar.py — daily tracking |
| Fast trailing stop improves Calmar | Bot 1: breakeven at 1R, dynamic runner trail |
| High Calmar = safe to leverage | Phase 4 of game plan after verified 3.0+ on live |

---

## Game Plan

| Phase | When | Condition to advance |
|---|---|---|
| Demo trading | Now → Day 60–90 | 50+ trades, Calmar ≥ 2.0 |
| Evaluation | Day 60–90 | Bot1 Calmar ≥ 2.5, Bot2 Calmar ≥ 2.0 |
| Small live account (50% risk) | Day 90–150 | Calmar holds on live data |
| Full risk | Day 150+ | Live Calmar ≥ 3.0 for 60+ days |

*Always run on DEMO first. Jason lost $300k skipping this step.*
