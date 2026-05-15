# BOT2_MEAN_REVERSION_GUIDE.md
# Bot 2 — Mean Reversion

**File:** `bots/bot2_mean_reversion.py`
**Strategy:** Fade overextended price back to statistical average
**Direction:** Against the overextension — confirms with RSI, BB, VWAP
**Trades per day:** 0–4 typical
**Account:** Main account — runs alongside Bot 1

---

## What It Does

Trades price back toward its average after it stretches too far. When an instrument is overbought or oversold relative to Bollinger Bands, RSI, and VWAP simultaneously, the snapback probability is high. This bot captures that snapback quickly and banks profit at 1R — it does not hold for extended moves.

This is the cash flow layer. Bot 1 is active during kill zones only. Bot 2 runs 24 hours and generates consistent wins during ranging conditions when Bot 1 is idle. They are intentionally uncorrelated.

---

## When It Trades

Active 24 hours. All positions force-close at 19:45 UTC daily (market close window).

---

## Entry Logic — All Must Be True

**Bullish (long after oversold):**
1. Price below lower Bollinger Band (2+ std deviations)
2. RSI below 28
3. Price below VWAP by 1.5+ std deviations
4. Rejection candle confirming buyers

**Bearish (short after overbought):**
1. Price above upper Bollinger Band
2. RSI above 72
3. Price above VWAP by 1.5+ std deviations
4. Rejection candle confirming sellers

Minimum confluence score 4. AI must approve ≥ 55%.

---

## Trade Management — 0.01 Lot Safe

Mean reversion moves fast — bank profit immediately rather than trailing.

| Stage | Trigger | Action |
|---|---|---|
| Breakeven | +0.3R profit | Stop to entry — very fast |
| Full close | +1R profit | Entire position closes — profit banked |
| Early close | RSI returns to 40–60 | Mean reached — close immediately |
| Tight trail | After BE, before 1R | 0.3× ATR trail |
| Market close | 19:45 UTC daily | All positions force-closed |
| Weekend | Friday 19:45 UTC | All positions force-closed |

**Why full close at 1R:** At 0.01 lots you cannot split a position. Full close at 1R guarantees profit on every winning trade. Mean reversion moves are typically done by 1R — price has returned to the mean.

---

## Re-Entry After Breakeven Stop

If a trade stops at breakeven and price is still at the extreme (still outside BB), the bot re-enters once:

1. Trade stops at BE → direction stored as re-entry opportunity
2. Next valid signal in the same direction → re-enters with `[RE-ENTRY]` tag
3. AI learns whether re-entries outperform original entries
4. Maximum one re-entry per original setup

---

## AI Brain (v2)

Same improvements as Bot 1:

| Parameter | Value | Change |
|---|---|---|
| Min trades to train | 15 | Was 30 |
| AUC gate | 0.55 | Was 0.52 |
| Retrains every | 5 trades | Was 10 |

**New features the AI learns from:**
- `daily_trades_so_far` — trades placed so far today
- `daily_pnl_pct` — current day P&L at entry
- `simultaneous_open` — open positions at entry
- `is_reentry` — whether this is a re-entry

**Daily performance logger** records end-of-day metrics. The AI learns which day conditions and market regimes produce drawdowns.

---

## Risk Controls

| Control | Value | Notes |
|---|---|---|
| Risk per trade | 2% | Of current balance |
| Breakeven at | 0.3R | Very fast — protects every winner |
| Full close at | 1R | Profit always banked |
| Daily loss cap | 10% | No new entries |
| Weekly loss cap | 20% | 6hr cooldown |
| Market close | 19:45 UTC | Force-closes all |

---

## Regime Behaviour

Inverted logic vs Bot 1:

| Regime | Bot 2 response |
|---|---|
| RANGING | Full size — ideal, price oscillates predictably |
| TRANSITIONING | 75% size |
| TRENDING | 40% size — trends fight reversion |

---

## Tuning Guide

| Problem | Parameter in config.json | Adjustment |
|---|---|---|
| Giving back profits | `breakeven_at_r` | Lower to 0.2 |
| Closing too early | `partial_close_r` | Raise to 1.5 |
| Too few signals | `bb_std_entry` | Lower 2.0 → 1.8 |
| Too many bad signals | `bb_std_entry` | Raise 2.0 → 2.2 |
| RSI exit too early | `rsi_neutral_low/high` | Widen to 35/65 |

---

## Log Messages to Watch

```
Scanning | price=4385.20 | regime=RANGING | risk_mult=1.0            ← ideal conditions
REVERSION SIGNAL | BULLISH | score=5 | RSI=24.3                      ← setup found
AI approved 61% >= 55%                                                ← gate passed
AI not yet trained (6/15 trades). Rules-based. 9 more needed.        ← learning
ENTRY | bullish | lots=0.02 | entry=4385.20 SL=4380.00 TP=4400.00    ← trade placed
ENTRY | bullish | ... [RE-ENTRY]                                       ← re-entry
T12345678 -> BREAKEVEN @ 4385.20 (0.31R)                             ← free trade
T12345678 FULL CLOSE @ 1.0R -- banking profit.                        ← secured
T12345678 EARLY CLOSE -- RSI neutral (48.2) | profit=0.8R            ← mean reached
Market closing in 15 min [DAILY-CLOSE] -- closing all 1 positions.   ← eod protection
New day 2026-05-15 | $1,234.56 | AI: Trained | AUC=0.58 | WR(10)=60% ← morning report
```
