# Bot 2 — Mean Reversion
**File:** `bots/bot_mean_reversion.py` | **Account:** Main (shared with Bot 1) | **MT5:** `C:\Program Files\PU Prime MT5 Terminal`

---

## What This Bot Is Built To Do

Bot 2 trades price snapping back to its statistical average after extreme overextension. When gold stretches too far from its mean — confirmed by Bollinger Bands, RSI, and VWAP simultaneously — the probability of a snapback is high. This bot captures that move quickly and banks profit at 1R. It runs 24 hours and generates consistent smaller wins, complementing Bot 1 which is session-specific.

---

## Strategy

**Mean Reversion — Bollinger Band + RSI + VWAP Confluence**

A signal fires when all three confirm the same overextension:
- Price outside Bollinger Band (2+ standard deviations)
- RSI below 28 (oversold) or above 72 (overbought)
- Price deviated from VWAP by 1.5+ standard deviations
- Rejection candle confirms buyers/sellers stepping in

**When it trades:** 24 hours, every day. Dead zone 3–7pm Texas.

**Entry checklist — all must be true:**
- Price outside Bollinger Band (2+ std dev)
- RSI confirms overbought/oversold
- VWAP deviation confirms overextension
- Rejection candle present
- Confluence score >= 4
- AI approves >= 55%

---

## Profitability Goal

- **Target per trade:** 1R (tight, fast, consistent)
- **Philosophy:** Many small wins compound faster than few large wins at this account size
- **Early close:** Closes if RSI returns to neutral (50 area) — mean has been reached, no reason to hold
- **Cash flow layer:** Designed to generate consistent daily P&L while Bot 1 waits for high-quality setups

---

## Risk Goal

| Control | Value |
|---|---|
| Risk per trade | 2% of balance |
| Breakeven | +0.3R — very fast protection |
| Full close | +1R — always banks profit |
| Daily loss cap | 10% — no new entries |
| Weekly loss cap | 20% — 6hr cooldown |
| No overnight holds | Force-close 19:45 UTC |

---

## Trade Management

| Stage | Trigger | Action |
|---|---|---|
| Breakeven | +0.3R | Stop to entry — very fast |
| Full close | +1R | Entire position closes |
| Early close | RSI returns to neutral | Mean reached — exit |
| Tight trail | After BE, before 1R | 0.3x ATR trail |
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
Learns from: confluence score, RSI value, BB position, VWAP deviation, daily P&L %, simultaneous positions, regime score.

---

## Regime Behaviour

Bot 2 is the INVERSE of Bot 1 — it thrives when Bot 1 struggles:

| Regime | Response |
|---|---|
| RANGING | Full size — ideal, price oscillates predictably |
| TRANSITIONING | 75% size |
| TRENDING | 40% size — trends fight reversion |

---

## Tuning

| Problem | Config key | Fix |
|---|---|---|
| Giving back profits | `breakeven_at_r` | Lower to 0.2 |
| Closing too early | `partial_close_r` | Raise to 1.5 |
| Too few signals | `bb_std_entry` | Lower 2.0 -> 1.8 |
| Too many bad signals | `bb_std_entry` | Raise 2.0 -> 2.2 |

---

## Key Log Messages

```
REVERSION SIGNAL | BULLISH | score=5 | RSI=24.3
AI approved 61% >= 55%
ENTRY | bullish | lots=0.02 | entry=4385.20 SL=4380.00 TP=4400.00
T12345 -> BREAKEVEN @ 4385.20 (0.31R)
T12345 FULL CLOSE @ 1.0R -- banking profit.
T12345 EARLY CLOSE -- RSI neutral (48.2) | profit=0.8R
DEAD ZONE PORTFOLIO CLOSE | Net P&L=+$22.10 | Closing all 1 position
New day 2026-05-16 | $2,759.28 | AI: Trained | AUC=0.58 | WR(10)=60%
```
