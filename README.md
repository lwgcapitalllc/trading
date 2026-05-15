# Algo Suite — LWG Capital LLC

Multi-bot algorithmic trading system built on MetaTrader 5.
Designed to scale across any instrument by separating shared code from per-instance configuration.

---

## Repository Structure

```
algos/
├── algo.py                          <- Mac control panel (run with: algo)
├── ALGO_CONTROL_PANEL_GUIDE.md
├── README.md
├── SETUP.md
├── stress_test_suite.py             <- run locally for Monte Carlo analysis
│
├── shared/                          <- one copy, used by all bots
│   ├── shared_ai_brain.py           <- AI engine + trade logger + daily logger
│   ├── shared_calmar.py             <- Calmar ratio tracker
│   └── shared_regime.py             <- market regime classifier
│
├── bots/                            <- one copy of each bot, used by all instruments
│   ├── bot_utils.py                 <- config loader + path resolver
│   ├── launcher.py                  <- universal Task Scheduler launcher
│   ├── bot1_smc_trend.py            <- Bot 1: SMC trend following
│   ├── bot2_mean_reversion.py       <- Bot 2: mean reversion
│   ├── bot3_scalper.py              <- Bot 3: EMA momentum scalper
│   ├── BOT1_SMC_TREND_GUIDE.md
│   ├── BOT2_MEAN_REVERSION_GUIDE.md
│   └── BOT3_SCALPER_GUIDE.md
│
└── markets/
    └── fx/
        └── instances/
            ├── xauusd_main/         <- Bot 1 + Bot 2 on XAUUSD
            │   ├── config.json
            │   └── credentials.json <- NOT in GitHub, manual VPS only
            └── xauusd_scalper/      <- Bot 3 on XAUUSD (separate account)
                ├── config.json
                └── credentials.json <- NOT in GitHub, manual VPS only
```

---

## The Three Bots

| Bot | Strategy | Sessions | Risk | Account |
|---|---|---|---|---|
| Bot 1 | SMC Trend — Judas Swing + H4 filter | London + NY kill zones | 2% per trade | Main |
| Bot 2 | Mean Reversion — BB + RSI + VWAP | 24 hours | 2% per trade | Main |
| Bot 3 | EMA Momentum Scalper | All except dead zone | 2–3.5% auto-scaling | Separate |

Bot 1 and Bot 2 share an account — designed to be uncorrelated. Bot 3 must run on its own account due to its aggressive daily profit engine.

---

## AI Brain (v2) — All Bots

| Feature | Value |
|---|---|
| Minimum trades to train | 15 (was 30) |
| AUC quality gate | 0.55 (was 0.52) |
| Retrains every | 5 new closed trades (was 10) |
| Daily performance logger | Records drawdown, trade count, simultaneous positions |
| Re-entry tracking | Logs whether a trade was a re-entry and outcome |
| Drawdown features | daily_trades_so_far, daily_pnl_pct, simultaneous_open |

The AI learns two things over time:
1. Which entry conditions produce winning trades
2. Which day patterns produce drawdowns

After 7+ days of data it can start flagging bad day patterns — e.g. taking trade #6 when already down 4% with 3 positions open has historically led to further losses.

---

## Re-Entry Logic — Bot 1 and Bot 2

If a trade stops at breakeven and the market bias is unchanged, both bots will re-enter once:

- **Bot 1:** Re-enters if H4 trend and sweep direction still match
- **Bot 2:** Re-enters if price is still outside the Bollinger Band

Re-entries are tagged `[RE-ENTRY]` in the log and tracked separately in the AI model. Over time the AI learns whether re-entries outperform original entries.

---

## Market Close Protection — All Bots

All three bots force-close every open position at **19:45 UTC daily** — 15 minutes before the gold market closes at 20:00 UTC (3pm CT Fort Worth).

This triggers:
- On restart if the VPS rebooted during the close window (19:45–21:00 UTC)
- On the normal daily close
- On Fridays (weekend protection — market doesn't reopen until Sunday 22:00 UTC)

**You will never hold overnight or over weekends.**

---

## Shared Components

### shared_ai_brain.py
- `TradeLogger` — logs every trade with 18 features at entry and outcome at close
- `DailyLogger` — records end-of-day metrics (new in v2)
- `AIBrain` — Random Forest classifier, trains at 15 trades, retrains every 5
- `build_features_trend` — feature builder for Bot 1
- `build_features_reversion` — feature builder for Bot 2

### shared_calmar.py
Calmar ratio = annualised return / max drawdown. Prints morning report daily.
- 2.0 = okay | 3.0 = decent | 5.0+ = exceptional

### shared_regime.py
Classifies market every hour: TRENDING / TRANSITIONING / RANGING.
Bot 1 and Bot 2 react opposite ways to the same regime.

---

## Deploy Workflow

```bash
# Make changes on Mac, push to GitHub
git add . && git commit -m "description" && git push

# Deploy to VPS
ssh forexvps "cd C:\algos && git pull origin main"

# Restart bots
algo -> Stop all -> Start all
```

---

## Adding a New Instrument

1. Create `markets/fx/instances/NEW_PAIR_main/config.json`
2. Add `credentials.json` manually on VPS only
3. Add Task Scheduler task: `FX_NEWPAIR_Bot1` pointing to `launcher.py --bot bot1 --config ...`
4. Add entry to `LOG_MAP` and `TASK_BOT_MAP` in `algo.py`
5. The bot appears in `algo` control panel automatically

---

## Game Plan

| Phase | Timing | Condition to advance |
|---|---|---|
| Demo trading | Now -> Day 60 | 15+ closed trades, Calmar >= 2.0 |
| Evaluation | Day 60–90 | Bot1 Calmar >= 2.5, Bot2 Calmar >= 2.0 |
| Small live (50% risk) | Day 90–150 | Calmar holds on live data |
| Full risk | Day 150+ | Live Calmar >= 3.0 for 60+ days |

*Always run on DEMO first. Jason Byers lost $300k skipping this step.*
