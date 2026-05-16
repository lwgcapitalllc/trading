# Bot 3 — EMA Momentum Scalper
**File:** `bots/bot3_scalper.py` | **Account:** Dedicated scalper account | **MT5:** `C:\MT5_Scalper`

---

## What This Bot Is Built To Do

Bot 3 is an aggressive account-growth engine. It trades momentum on M5 using EMA stack alignment and M1 pullback entries. It runs a dynamic daily profit engine — once it hits its daily target it keeps running with peak protection until either a 10% pullback from the day's peak or a hard ceiling. It compounds position sizes automatically as the account grows. It must run on its own separate account because its risk profile is incompatible with Bot 1 and Bot 2.

---

## Strategy

**EMA Momentum Scalping — M5 Stack + M1 Pullback Entry**

1. M5 EMA stack (9/21/50) must all point in the same direction
2. Price pulls back to the EMA9 on M1 — a genuine retracement, not drift
3. A momentum candle fires in the trend direction (body >= 0.3x ATR)
4. RSI must not be extreme against the trade (no buying above 75, no selling below 25)
5. Enter immediately — scalps require fast execution

**When it trades:** All sessions except 3:00–7:00pm Texas (dead zone) and the previous dead zone start 15:00–19:00 UTC as a secondary check.

**Entry checklist:**
- M5 EMA 9/21/50 all aligned in same direction
- Price within 0.3x ATR of EMA9 on M1 (real pullback)
- Momentum candle body >= 0.3x ATR
- RSI not extreme against trade direction
- AI approves >= 52%

---

## Profitability Goal

- **Daily target:** +10% of account balance
- **Dynamic engine:** After hitting 10%, peak protection activates — bot keeps trading until a 10% pullback from the day's high-water mark
- **Hard ceiling:** +50% in a day — bot stops and locks in gains
- **Compounding tiers:** Risk % increases automatically as account grows

| Balance | Risk per trade |
|---|---|
| $0–$2,000 | 2.0% |
| $2,000–$4,000 | 2.5% |
| $4,000–$7,000 | 3.0% |
| $7,000–$10,000 | 3.5% |
| $10,000+ | 2.0% (resets, compounds again) |

---

## Risk Goal

| Control | Value |
|---|---|
| Daily loss floor | -8% — bot stops for the day |
| Peak protection | 10% pullback from day's peak triggers stop |
| Hard ceiling | +50% — locks in gains |
| Weekly loss cap | 20% |
| No overnight holds | Force-close 19:45 UTC |
| Momentum reversal | Closes immediately if M5 bias flips while in profit |

---

## Trade Management

| Stage | Trigger | Action |
|---|---|---|
| Breakeven | +0.5R | Stop to entry — fast |
| Trail | After BE | 0.4x ATR tight trail |
| Max hold | 20 M1 candles | Force-close — scalps don't drag |
| Momentum flip | M5 bias reverses + in profit | Close immediately |
| Market close | 19:45 UTC | Force-close all |

---

## Dead Zone (3:00–7:00pm Texas)

No new entries. Portfolio-level management every minute:
- Net profitable across all trades → close all immediately
- Individual trade profitable, portfolio negative → move to breakeven
- Losing trade getting worse → close immediately at best price
- Losing trade improving → hold and monitor until 3:45pm TX
- Any trade still open at 3:45pm TX → hard close

---

## AI Brain

Trains at 15 closed trades. Retrains every 5. AUC gate 0.55.
Learns from: EMA stack strength, pullback depth, momentum body size, RSI at entry, daily P&L %, daily trade count.

---

## Tuning

| Problem | Config key | Fix |
|---|---|---|
| Too few signals | `pullback_tolerance` | Raise 0.3 -> 0.5 |
| Too many bad entries | `pullback_tolerance` | Lower 0.3 -> 0.2 |
| Stops hit on noise | `atr_sl_multiplier` | Raise 0.8 -> 1.0 |
| BE too slow | `breakeven_at_r` | Lower 0.5 -> 0.3 |
| Too aggressive | `daily_profit_target_pct` | Lower 10 -> 5 |

---

## Key Log Messages

```
SCALP SIGNAL | BULLISH | price=4388.50 | RSI=52.1 | stack=3/3
AI approved 64% >= 52%
FILLED | bullish 0.02L @ 4388.65
T12345 BE @ 4388.65 (0.5R)
T12345 MOMENTUM FLIP -- closing at 1.2R
DAILY TARGET HIT: +10.3%. Peak protection active. Continuing.
PEAK PROTECTION: pulled back 10% from peak +22%. Locked +12%.
DAILY CEILING HIT: +50.1%. Banking everything.
DEAD ZONE PORTFOLIO CLOSE | Net P&L=+$18.40 | Closing all 3 positions
PROGRESS | $1,000 -> $10,000 (10%) | growth=+0.0% | risk=2.0%
```
