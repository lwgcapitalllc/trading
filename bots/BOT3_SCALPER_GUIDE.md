# BOT3_SCALPER_GUIDE.md
# Bot 3 — EMA Momentum Scalper

**File:** `bots/bot3_scalper.py`
**Style:** Momentum scalping — fast entries, fast exits, aggressive compounding
**Capital allocation:** Dedicated separate account — never shared with Bot 1 or Bot 2
**Trades per day:** 5–20+ depending on session activity

---

## What It Does

Grows a small account aggressively through high-frequency compounding. Enters in the direction of momentum when price pulls back to a key EMA and a momentum candle confirms continuation. Exits fast, compounds position size as the account grows, and has a dynamic daily engine that keeps trading as long as it is winning.

**Must run on its own dedicated account.** Its aggressive profile would contaminate daily loss tracking for Bot 1 and Bot 2 if shared.

---

## When It Trades

All sessions except dead zone (15:00–19:00 UTC configurable). Checks every 10 seconds. Most active during London and NY. All positions force-close at 21:45 UTC daily.

---

## How It Finds a Trade

**Direction filter (M5):** EMA 9/21/50 stack aligned. Bullish: 9>21>50 and price above 50. Bearish: 9<21<50 and price below 50.

**Entry trigger (M1):**
1. Price pulls back close to M1 EMA9 (within 0.3× ATR)
2. Momentum candle fires in trend direction (body ≥ 0.3× ATR)
3. RSI not extreme against trade (no buying above 75, no selling below 25)
4. Previous candle touched EMA9 — confirms actual pullback
5. AI approves

---

## How It Manages Trades

| Stage | Trigger | Action |
|---|---|---|
| 1 | +0.5R profit | Stop to breakeven — very fast |
| 2 | After breakeven | Tight trail 0.4× ATR |
| 3 | 20 M1 candles held | Force close — scalps don't drag |
| 4 | M5 bias flips AND in profit | Close immediately — momentum gone |
| Force close | 21:45 UTC daily | All positions closed |
| Force close | Friday 21:45 UTC | Weekend protection |

---

## Dynamic Daily Profit Engine

| Phase | Trigger | What happens |
|---|---|---|
| Free run | Until +10% | Trades normally |
| Peak protection | After +10% hit | Tracks day's peak balance, keeps trading |
| Stop | 10% pullback from peak | Locks in accumulated gains |
| Hard ceiling | +50% (5× target) | Banks everything, done for day |
| Hard floor | -8% loss | Closes all, stops for the day |

Example: hits +10% → keeps running → peaks at +28% → gives back 10% of that → stops at +18% locked in.

---

## Compounding Tiers

Auto-adjusts as account grows — no manual changes needed.

| Balance | Risk per trade |
|---|---|
| $0 – $2,000 | 2.0% |
| $2,000 – $4,000 | 2.5% |
| $4,000 – $7,000 | 3.0% |
| $7,000 – $10,000 | 3.5% |
| $10,000+ | 2.0% (resets, keeps compounding) |

---

## News Events

Configured in `config.json` → `bot3_scalper` → `news_events`. Format: `[weekday, hour_utc, minute_utc, "label"]`. Set `news_pause_minutes: 0` to trade through all news. Set `news_widen_sl_multiplier: 2.0` to trade with doubled stop loss during news instead of pausing.

---

## Tuning Guide

| Problem | Parameter | Change |
|---|---|---|
| Too few signals | `pullback_tolerance` | Raise 0.3 → 0.5 |
| Too many bad entries | `pullback_tolerance` | Lower 0.3 → 0.2 |
| Stops hit on noise | `atr_sl_multiplier` | Raise 0.8 → 1.0 |
| Breakeven too slow | `breakeven_at_r` | Lower 0.5 → 0.3 |
| Daily target too aggressive | `daily_profit_target_pct` | Lower 10 → 5 |

---

## Log Messages to Watch

```
SCALP SIGNAL | BULLISH | price=4388.50 | RSI=52.1 | stack=3/3   ← strong setup
AI approved 64%                                                   ← gate passed
FILLED | ticket=... | bullish 0.02L @ 4388.65                   ← trade placed
T12345678 BE @ 4388.65 (0.5R)                                   ← breakeven locked
T12345678 MOMENTUM FLIP — closing at 1.2R                       ← smart exit
DAILY TARGET HIT: +10.3%. Peak protection active.               ← phase 2 starts
PEAK PROTECTION: pulled back 10% from peak +22%. Locked +12%.  ← gains banked
DAILY CEILING HIT: +50.1%. Banking everything.                  ← extraordinary day
PROGRESS | $1,340 → $10,000 (13%) | growth=+34% | risk=2%      ← daily summary
Market closing in 15 min — closing all 4 position(s). [WEEKEND-CLOSE] ← friday cleanup
```
