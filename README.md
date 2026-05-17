# LWG Capital LLC — Algo Trading Suite

Multi-bot algorithmic trading system built on MetaTrader 5.
Designed to scale across instruments and prop firm accounts.

---

## Documentation

**Bot guides:**
- [Bot SMC Trend — SMC Trend Following](bots/BOT_SMC_TREND_GUIDE.md)
- [Bot Mean Reversion — Mean Reversion](bots/BOT_MEAN_REVERSION_GUIDE.md)
- [Bot Scalper — EMA Scalper](bots/BOT_SCALPER_GUIDE.md)
- [Bot FFT — FFT Strategy](bots/BOT_FFT_GUIDE.md)

**System guides:**
- [Notifications — Telegram reporter, monitor, commands](notifications/NOTIFICATIONS_GUIDE.md)
- [Scheduler — Task Scheduler setup and management](scheduler/SCHEDULER_GUIDE.md)

---

## The Bots — At a Glance

| | SMC Trend | Mean Reversion | Scalper | FFT |
|---|---|---|---|---|
| **Strategy** | Judas Swing + FVG | BB + RSI + VWAP | EMA stack + pullback | Dual Fibonacci confluence |
| **Direction** | With H4 trend only | Against overextension | With momentum | With H1+H4 trend |
| **Timeframe** | M15 entry | Any (24hr) | M5 stack, M1 entry | M15 entry |
| **Sessions** | London + NY kill zones | 24 hours | All except dead zone | Any trending session |
| **Trades/day** | 0–3 | 0–4 | 5–20+ | 0–3 |
| **Target R:R** | 3:1+ (runner system) | 1:1 fast | Dynamic daily engine | 2:1 to 5:1 |
| **Risk/trade** | 2% | 2% | 2–3.5% (auto-scaling) | 1% |
| **Daily cap** | 10% loss | 10% loss | -8% floor | 5% loss |
| **Account** | gold_main (shared) | gold_main (shared) | gold_scalper | gold_fft |
| **MT5** | #700103491 | #700103491 | #700107520 | #700107749 |

---

## How They Work Together

**Bot SMC Trend and Bot Mean Reversion are designed to be uncorrelated.**

They share one MT5 account (#700103491) and one equity file (`gold_main_equity.json`). Their balance and account growth are always identical. Individual trade performance (win rate, profit factor, Calmar) is tracked separately per bot. When markets are trending, Bot SMC Trend is active and Bot Mean Reversion reduces size. When markets are ranging, Bot Mean Reversion is busy and Bot SMC Trend sits idle. They share one account and complement each other across market conditions.

**Bot Scalper is completely independent.** It runs on its own account with its own aggressive compounding logic. Its daily profit engine means one great day can significantly move the account.

**Bot FFT is the proprietary edge.** The FFT dual-fib strategy is the most selective — it only fires when two independent Fibonacci tools agree on the same price zone. Fewer trades, higher quality. Will be refined over time as more chart examples are provided.

---

## Key Differences Explained

**Why does Mean Reversion close at 1R when SMC Trend targets 3R?**
Mean reversion moves are fast and often complete within minutes. Holding for 3R on a reversion trade risks giving back the move. Mean Reversion banks 1R reliably, many times. SMC Trend holds for 3R because trend continuation moves can run far beyond the initial target — the runner system captures this.

**Why does Scalper have its own account?**
Scalper can make +50% in a day. It can also hit the -8% floor. This volatility would destroy the daily loss cap tracking on the shared gold_main account. Separation keeps risk clean.

**Why is FFT risk only 1% when others are 2%?**
The FFT strategy is unproven in live trading — it has no trade history yet. Lower risk while the AI is learning. Once it has 30+ trades and a solid Calmar ratio, risk can be raised to 2%.

**Why different AI thresholds (SMC/Reversion: 55% vs Scalper/FFT: 52%)?**
Bot 1 and 2 have stricter entry rules — the AI needs more confidence to approve. Scalper and FFT are newer with less data — a lower threshold means the AI starts influencing decisions sooner while still learning.

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
**Deploy:** Edit on Mac → `python3 deploy.py` → `git push` → `ssh forexvps "cd C:\algos && git pull"` → `algo restart`
**Monitoring:** `algo status` shows all bots, uptime, running state

**MT5 instances:**
| Directory | Account | Bots |
|---|---|---|
| `C:\Program Files\PU Prime MT5 Terminal` | #700103491 | Bot SMC Trend + Bot Mean Reversion |
| `C:\MT5_Scalper` | #700107520 | Bot Scalper |
| `C:\MT5_FFT` | #700107749 | Bot FFT |

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
│   ├── bot_smc_trend.py
│   ├── bot_mean_reversion.py
│   ├── bot_scalper.py
│   ├── bot_fft.py
│   ├── BOT_SMC_TREND_GUIDE.md
│   ├── BOT_MEAN_REVERSION_GUIDE.md
│   ├── BOT_SCALPER_GUIDE.md
│   └── BOT_FFT_GUIDE.md
├── executors/
│   └── tradovate.py                  <- Tradovate API (Bot Futures)
└── markets/
    ├── fx/instances/
    │   ├── gold_main/              <- Bot 1 + Bot 2
    │   ├── gold_scalper/           <- Bot 3
    │   └── gold_fft/               <- Bot 5
    └── futures/instances/
        └── futures_account1/           <- Bot 4 (pending Lucid evaluation)
```

---

## Game Plan

| Phase | Timing | Condition to advance |
|---|---|---|
| Demo trading | Now — Day 60 | 15+ closed trades per bot, Calmar >= 2.0 |
| Evaluation | Day 60–90 | SMC Trend Calmar >= 2.5, Mean Reversion Calmar >= 2.0 |
| Small live (50% risk) | Day 90–150 | Calmar holds on live data |
| Full risk | Day 150+ | Live Calmar >= 3.0 for 60+ days |
| Prop firms (Lucid) | Parallel | Buy LucidFlex $100K eval, run Bot Futures |

**Calmar targets:** 2.0 = okay | 3.0 = decent | 5.0+ = exceptional

*Always run on DEMO first. Never optimize to past results — that is overfitting.*
