# BOT3_SCALPER_GUIDE.md
# Bot 3 — EMA Momentum Scalper

**File:** `bots/bot3_scalper.py`
**Strategy:** EMA stack direction + M1 pullback entry
**Direction:** With momentum — closes immediately if momentum flips
**Trades per day:** 5–20+ depending on session
**Account:** Dedicated separate account — never shared with Bot 1 or Bot 2

---

## What It Does

Grows a small account aggressively through high-frequency compounding. Enters when the M5 EMA stack (9/21/50) shows clear directional bias and price pulls back to the EMA9 on M1, then fires a momentum candle. Exits fast. Scales position size automatically as account grows.

Must run on its own dedicated MT5 account. Its aggressive profile would contaminate daily loss tracking for Bot 1 and Bot 2 if shared.

---

## When It Trades

All sessions except the dead zone (15:00–19:00 UTC, configurable). Checks every 10 seconds. All positions force-close at 19:45 UTC daily.

---

## Entry Logic — All Must Be True

**Direction filter (M5):**
- EMA 9/21/50 all aligned in same direction
- Price above EMA50 (bullish) or below EMA50 (bearish)
- Partial alignment (2/3) accepted at reduced confidence

**Entry trigger (M1):**
1. Price within 0.3× ATR of EMA9 (genuine pullback)
2. Momentum candle body ≥ 0.3× ATR in trend direction
3. RSI not extreme against trade (not buying above 75, not selling below 25)
4. Previous candle touched EMA9 — confirms actual pullback, not drift
5. AI approves ≥ 52%

---

## Trade Management

| Stage | Trigger | Action |
|---|---|---|
| Breakeven | +0.5R profit | Stop to entry — very fast |
| Trailing | After BE | 0.4× ATR tight trail |
| Max hold | 20 M1 candles | Force close — scalps don't drag |
| Momentum flip | M5 bias reverses AND in profit | Close immediately |
| Market close | 19:45 UTC daily | All positions force-closed |
| Weekend | Friday 19:45 UTC | All positions force-closed |

**Momentum reversal detection:** If the M5 EMA stack flips against the open position while in profit, the bot exits immediately and banks the profit. This is the key difference from a basic scalper.

---

## Dynamic Daily Profit Engine

| Phase | Condition | Behaviour |
|---|---|---|
| Free run | Until +10% daily target hit | Trades normally |
| Peak protection | After +10% hit | Tracks peak balance, keeps trading |
| Stop | 10% pullback from day's peak | Locks in accumulated gains |
| Hard ceiling | +50% (5x target) | Banks everything, done for day |
| Hard floor | -8% loss | Closes all, done for day |

**Example:** Hits +10% -> keeps running -> peaks at +28% -> pulls back 10% from 28% peak -> stops at +18% locked in.

---

## Compounding Tiers (auto-adjusts)

| Balance | Risk per trade |
|---|---|
| $0 - $2,000 | 2.0% |
| $2,000 - $4,000 | 2.5% |
| $4,000 - $7,000 | 3.0% |
| $7,000 - $10,000 | 3.5% |
| $10,000+ | 2.0% (resets, keeps compounding) |

---

## News Events

Configured in `config.json` -> `bot3_scalper` -> `news_events`.
Format: `[weekday, hour_utc, minute_utc, "label"]`

Options:
- `news_pause_minutes: 30` — pause 30 min around event (default)
- `news_pause_minutes: 0` — trade through all news
- `news_widen_sl_multiplier: 2.0` — keep trading with 2x wider stop

---

## AI Brain (v2)

| Parameter | Value |
|---|---|
| Min trades to train | 15 |
| AUC gate | 0.55 |
| Retrains every | 5 trades |

**Features the AI learns from:**
- EMA stack strength, pullback depth, momentum body size
- RSI at entry, ATR, time of day, day of week
- Rolling win rate, spread
- `daily_trades_so_far`, `daily_pnl_pct`, `simultaneous_open`

The `daily_pnl_pct` feature is especially important — the AI learns whether taking trades when already up 15% on the day has historically been profitable.

---

## Risk Controls

| Control | Value |
|---|---|
| Risk per trade | 2.0–3.5% (auto by tier) |
| Daily target | +10% |
| Peak protection | 10% pullback from peak |
| Hard ceiling | +50% |
| Daily loss floor | -8% |
| Weekly loss cap | 20% |
| Market close | 19:45 UTC force-close |

---

## Tuning Guide

| Problem | Parameter | Adjustment |
|---|---|---|
| Too few signals | `pullback_tolerance` | Raise 0.3 -> 0.5 |
| Too many bad entries | `pullback_tolerance` | Lower 0.3 -> 0.2 |
| Stops hit on noise | `atr_sl_multiplier` | Raise 0.8 -> 1.0 |
| BE too slow | `breakeven_at_r` | Lower 0.5 -> 0.3 |
| Too aggressive daily | `daily_profit_target_pct` | Lower 10 -> 5 |

---

## Log Messages to Watch

```
SCALP SIGNAL | BULLISH | price=4388.50 | RSI=52.1 | stack=3/3       ← strong setup
AI approved 64% >= 52%                                               ← gate passed
FILLED | ticket=... | bullish 0.02L @ 4388.65                       ← trade placed
T12345678 BE @ 4388.65 (0.5R)                                       ← breakeven
T12345678 MOMENTUM FLIP -- closing at 1.2R                          ← smart exit
DAILY TARGET HIT: +10.3%. Peak protection active. Continuing.       ← phase 2
PEAK PROTECTION: pulled back 10% from peak +22%. Locked +12%.      ← day done
DAILY CEILING HIT: +50.1%. Banking everything.                      ← great day
PROGRESS | $1,340 -> $10,000 (13%) | growth=+34% | risk=2%         ← daily summary
Market closing in 15 min [DAILY-CLOSE] -- closing all 4 scalps.    ← eod cleanup
```
