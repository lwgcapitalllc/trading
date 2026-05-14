# Bot 3 — EMA Momentum Scalper

**File:** `bots/bot3_scalper.py`
**Style:** Momentum scalping — fast entries, fast exits, aggressive compounding
**Capital allocation:** Dedicated account — runs separately from Bot 1 and Bot 2
**Trades per day:** 5–20+ depending on session activity

---

## What It Does

Designed to grow a small account aggressively through high-frequency compounding. Enters in the direction of momentum when price pulls back to a key EMA level and a momentum candle confirms continuation. Exits fast, compounds position size as the account grows, and has a dynamic daily engine that keeps trading as long as it is winning.

This bot runs on its own account. Its risk profile is too aggressive to share capital with Bot 1 and Bot 2.

---

## When It Trades

Active all sessions except the dead zone (15:00–19:00 UTC by default — configurable).

Checks for setups every 10 seconds. Most active during London (07:00–10:00 UTC) and NY (12:00–15:00 UTC) when momentum is strongest and spreads are tightest.

---

## How It Finds a Trade

**Direction filter (M5 chart):**
The 3-EMA stack (9, 21, 50) must be aligned. Bullish: EMA9 > EMA21 > EMA50 and price above EMA50. Bearish: EMA9 < EMA21 < EMA50 and price below EMA50. Partial alignment (2/3 conditions) accepted at reduced confidence.

**Entry trigger (M1 chart):**
1. Price pulls back close to the M1 EMA9 (within 0.3× ATR)
2. A momentum candle fires in the trend direction (body ≥ 0.3× ATR)
3. RSI not at an extreme against the trade direction (no buying above 75, no selling below 25)
4. Previous candle touched the EMA9 — confirms an actual pullback occurred
5. AI model votes approve or block

---

## How It Manages Trades

| Milestone | Action |
|---|---|
| +0.5R profit | Stop loss moves to breakeven — very fast |
| After breakeven | Tight trailing stop of 0.4× ATR |
| 20 M1 candles held | Force close — scalps should not drag on |
| M5 bias flips AND in profit | Closes immediately — momentum has shifted |

The momentum reversal detection is what separates this from a basic scalper. If the M5 EMA stack flips against an open position while that position is profitable, the bot exits immediately and banks the profit rather than waiting for the trailing stop.

---

## Dynamic Daily Profit Engine

This is the core of what makes Bot 3 different. The bot does not have a fixed "stop trading at X%" rule. Instead:

**Phase 1 — Free run:**
Trades normally until daily profit reaches the configured target (default 10%).

**Phase 2 — Peak protection activates:**
Once 10% is hit, the bot tracks the highest balance reached that day. It keeps trading. Every new high resets the peak. The bot only stops if profit pulls back 10% from whatever the day's peak was.

**Examples:**
- Hits 10% → keeps going → peaks at 24% → pulls back 3% → still running → pulls back 10% from 24% peak → stops at 14% locked in
- Hits 10% → runs to 38% with no significant pullback → hard ceiling of 50% would apply but realistically the 10% pullback catches it around 35%
- Bad day hits the -8% floor → closes all positions → done for the day

**Hard limits always active:**
| Limit | Value | Behaviour |
|---|---|---|
| Hard ceiling | 50% (5× target) | Monster day — bank it all |
| Peak drawdown trigger | 10% from peak | Locks in accumulated gains |
| Daily loss floor | -8% | Close all, stop for the day |
| Weekly loss cap | 20% | 6hr cooldown then resume |

---

## Compounding Tiers

Position size scales automatically as the account grows. No manual intervention needed.

| Balance range | Risk per trade |
|---|---|
| $0 – $2,000 | 2.0% |
| $2,000 – $4,000 | 2.5% |
| $4,000 – $7,000 | 3.0% |
| $7,000 – $10,000 | 3.5% |
| $10,000+ | 2.0% (resets after goal — keeps compounding at base rate) |

On a $1,000 account at 2% risk, each trade risks $20. When the account reaches $4,000, each trade risks $100. The math compounds — winning phases fund larger positions in the next tier.

---

## News Events

Fully configurable in `config.json` → `bot3_scalper` → `news_events`.

Add events as `[weekday, hour_utc, minute_utc, "label"]` where weekday 0=Monday through 4=Friday.

Options:
- `news_pause_minutes: 30` — pause 30 min before and after (default)
- `news_pause_minutes: 0` — trade through all news events
- `news_widen_sl_multiplier: 2.0` — keep trading but with 2× wider stop loss

---

## AI Learning

After 30 closed trades the model trains on: EMA stack strength, pullback depth, momentum candle body size, RSI at entry, ATR, time of day, day of week, rolling win rate, current daily P&L context, spread, and trade direction. The daily P&L context feature is particularly important — the AI learns whether taking trades when already up 8% on the day has historically been profitable or not.

---

## Log Messages to Watch

```
SCALP SIGNAL | BULLISH | price=2388.50 | RSI=52.1 | stack=3/3   ← strong setup
AI approved 64%                                                    ← gate passed
FILLED | ticket=... | bullish 0.02L @ 2388.65                    ← trade placed
T12345678 BE @ 2388.65 (0.5R)                                    ← breakeven locked
T12345678 MOMENTUM FLIP — closing at 1.2R                        ← smart exit
DAILY TARGET HIT: +10.3%. Peak protection active. Continuing.    ← phase 2 starts
PEAK PROTECTION: pulled back 10% from peak +22%. Locked +12%.   ← day done, gains banked
DAILY CEILING HIT: +50.1%. Banking everything.                   ← extraordinary day
DAILY LOSS FLOOR: -8.0%. Closing all.                           ← protected
PROGRESS | $1,340 → $10,000 (13%) | growth=+34% | risk=2%      ← daily summary
```

---

## Works On

Any liquid instrument traded on MT5 with tight spreads and active sessions. Gold (XAUUSD), major FX pairs, crypto pairs (BTCUSD if your broker offers it), indices. The key requirements are: sufficient intraday volatility for the EMA stack to develop clear bias, and a broker spread under 3–4 points during active sessions. Wide spreads kill scalping strategies.

Tune `atr_sl_multiplier` and `pullback_tolerance` in config per instrument. Instruments with higher volatility (gold, indices) need slightly wider SL multipliers. Tight pairs like EURUSD can use tighter values.
