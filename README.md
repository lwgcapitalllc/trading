# LWG Capital LLC — Algo Trading Suite

Multi-bot algorithmic trading system built on MetaTrader 5.
Designed to scale across instruments and prop firm accounts.

---

## The Bots — At a Glance

| | Bot 1 | Bot 2 | Bot 3 | Bot 5 |
|---|---|---|---|---|
| **Name** | SMC Trend | Mean Reversion | EMA Scalper | FFT |
| **Strategy** | Judas Swing + FVG | BB + RSI + VWAP | EMA stack + pullback | Dual Fibonacci confluence |
| **Direction** | With H4 trend only | Against overextension | With momentum | With H1+H4 trend |
| **Timeframe** | M15 entry | Any (24hr) | M5 stack, M1 entry | M15 entry |
| **Sessions** | London + NY kill zones | 24 hours | All except dead zone | Any trending session |
| **Trades/day** | 0–3 | 0–4 | 5–20+ | 0–3 |
| **Target R:R** | 3:1+ (runner system) | 1:1 fast | Dynamic daily engine | 2:1 to 5:1 |
| **Risk/trade** | 2% | 2% | 2–3.5% (auto-scaling) | 1% |
| **Daily cap** | 10% loss | 10% loss | -8% floor | 5% loss |
| **Account** | Main (with Bot 2) | Main (with Bot 1) | Separate | Separate |
| **MT5** | PU Prime Terminal | PU Prime Terminal | MT5_Scalper | MT5_FFT |

---

## How They Work Together

**Bot 1 and Bot 2 are designed to be uncorrelated.** When markets are trending, Bot 1 is active and Bot 2 reduces size. When markets are ranging, Bot 2 is busy and Bot 1 sits idle. They share one account and complement each other across market conditions.

**Bot 3 is completely independent.** It runs on its own account with its own aggressive compounding logic. Its daily profit engine means one great day can significantly move the account.

**Bot 5 is the proprietary edge.** The FFT dual-fib strategy is the most selective — it only fires when two independent Fibonacci tools agree on the same price zone. Fewer trades, higher quality. Will be refined over time as more chart examples are provided.

---

## Key Differences Explained

**Why does Bot 2 close at 1R when Bot 1 targets 3R?**
Mean reversion moves are fast and often complete within minutes. Holding for 3R on a reversion trade risks giving back the move. Bot 2 banks 1R reliably, many times. Bot 1 holds for 3R because trend continuation moves can run far beyond the initial target — the runner system captures this.

**Why does Bot 3 have its own account?**
Bot 3 can make +50% in a day. It can also hit the -8% floor. This volatility would destroy the daily loss cap tracking on Bot 1 and Bot 2's shared account. Separation keeps risk clean.

**Why is Bot 5 risk only 1% when others are 2%?**
The FFT strategy is unproven in live trading — it has no trade history yet. Lower risk while the AI is learning. Once it has 30+ trades and a solid Calmar ratio, risk can be raised to 2%.

**Why different AI thresholds (Bot 1/2: 55% vs Bot 3/5: 52%)?**
Bot 1 and 2 have stricter entry rules — the AI needs more confidence to approve. Bot 3 and 5 are newer with less data — a lower threshold means the AI starts influencing decisions sooner while still learning.

---

## Dead Zone (All Bots)

**No new entries 3:00pm–7:00pm Texas time** (CDT/CST, DST-aware automatically).

During this window all bots run portfolio-level management:
- Net profitable across all open trades → close everything, lock profit
- Profitable individual trade, portfolio negative → move to breakeven
- Losing trade getting worse → close immediately
- Losing trade improving → hold until 3:45pm TX then hard close

---

## Infrastructure

**VPS:** ForexVPS (IP: 45.82.164.112) — Windows Server, 24/7
**Control:** `algo` command on Mac — starts, stops, restarts, shows status and uptime
**Deploy:** `git push` on Mac → `ssh forexvps "git pull"` → `algo restart`
**Monitoring:** `algo status` shows all bots, uptime, running state

**MT5 instances:**
| Directory | Account | Bots |
|---|---|---|
| `C:\Program Files\PU Prime MT5 Terminal` | Main (#700103491) | Bot 1 + Bot 2 |
| `C:\MT5_Scalper` | Scalper (#700107520) | Bot 3 |
| `C:\MT5_FFT` | FFT (#700107749) | Bot 5 |

---

## Shared Components

| File | Purpose |
|---|---|
| `shared/shared_ai_brain.py` | AI engine, trade logger, daily performance logger |
| `shared/shared_calmar.py` | Calmar ratio tracker (prints morning report daily) |
| `shared/shared_regime.py` | Market regime classifier (TRENDING/TRANSITIONING/RANGING) |
| `bots/bot_utils.py` | Config loader, logging setup, path resolver |
| `bots/launcher.py` | Universal Task Scheduler launcher for all bots |
| `algo.py` | Mac control panel — start/stop/status/logs |

---

## Repository Structure

```
algos/
├── algo.py                           <- Mac control panel
├── README.md
├── stress_test_suite.py
├── shared/
│   ├── shared_ai_brain.py
│   ├── shared_calmar.py
│   └── shared_regime.py
├── bots/
│   ├── bot_utils.py
│   ├── launcher.py
│   ├── bot1_smc_trend.py
│   ├── bot2_mean_reversion.py
│   ├── bot3_scalper.py
│   ├── bot5_fft.py
│   ├── BOT1_SMC_TREND_GUIDE.md
│   ├── BOT2_MEAN_REVERSION_GUIDE.md
│   ├── BOT3_SCALPER_GUIDE.md
│   └── BOT5_FFT_GUIDE.md
├── executors/
│   └── tradovate.py                  <- Tradovate API (Bot 4 futures)
└── markets/
    ├── fx/instances/
    │   ├── xauusd_main/              <- Bot 1 + Bot 2
    │   ├── xauusd_scalper/           <- Bot 3
    │   └── xauusd_fft/               <- Bot 5
    └── futures/instances/
        └── lucid_account1/           <- Bot 4 (pending Lucid evaluation)
```

---

## Game Plan

| Phase | Timing | Condition to advance |
|---|---|---|
| Demo trading | Now — Day 60 | 15+ closed trades per bot, Calmar >= 2.0 |
| Evaluation | Day 60–90 | Bot 1 Calmar >= 2.5, Bot 2 Calmar >= 2.0 |
| Small live (50% risk) | Day 90–150 | Calmar holds on live data |
| Full risk | Day 150+ | Live Calmar >= 3.0 for 60+ days |
| Prop firms (Lucid) | Parallel | Buy LucidFlex $100K eval, run Bot 4 |

**Calmar targets:** 2.0 = okay | 3.0 = decent | 5.0+ = exceptional

*Always run on DEMO first. Never optimize to past results — that is overfitting.*
