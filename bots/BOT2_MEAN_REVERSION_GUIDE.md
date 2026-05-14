# BOT2_MEAN_REVERSION_GUIDE.md
# Bot 2 — Mean Reversion

**File:** `bots/bot2_mean_reversion.py`
**Style:** Mean reversion — fades price extremes back to average
**Capital allocation:** 20–40% of account (runs alongside Bot 1)
**Trades per day:** 0–4 typical

---

## What It Does

Trades price back toward its average after it stretches too far. When an instrument is overbought or oversold relative to Bollinger Bands, RSI, and VWAP, there is high probability of a snapback. This bot captures that snapback quickly and banks profit before the move reverses.

This is the cash flow layer. While Bot 1 waits for specific kill zone setups, Bot 2 runs 24 hours scanning continuously. It generates consistent wins during ranging conditions when Bot 1 is idle.

---

## When It Trades

Active 24 hours. No session restriction. London and NY setups score higher due to better follow-through. All positions force-close at 21:45 UTC daily regardless.

---

## How It Finds a Trade

All conditions must align simultaneously:

**Bullish (long after oversold):**
1. Price below lower Bollinger Band (2+ std deviations)
2. RSI below 28
3. Price more than 1.5 std deviations below VWAP
4. Rejection candle confirming buyers stepping in

**Bearish (short after overbought):**
1. Price above upper Bollinger Band
2. RSI above 72
3. Price above VWAP by 1.5+ std deviations
4. Rejection candle confirming sellers

Minimum confluence score 4. AI votes approve or block.

---

## How It Manages Trades — 0.01 Lot Safe

Mean reversion moves fast — bank it quickly rather than trailing.

| Stage | Trigger | Action |
|---|---|---|
| 1 | +0.3R profit | Stop to breakeven — very fast |
| 2 | +1R profit | **Full close** — entire trade banked |
| 3 | RSI returns to 40–60 | Full close — mean has been reached |
| 4 | Tight trail (after BE) | 0.3× ATR trail if trade still open |
| Force close | 21:45 UTC daily | All positions closed before market close |
| Force close | Friday 21:45 UTC | Weekend protection |

**Why full close at 1R:** At 0.01 lots you can't split a position. Full close at 1R guarantees profit on every trade that moves in your favour. Mean reversion moves are often done by 1R anyway — the mean has been reached.

---

## Risk Controls

| Parameter | Default | Description |
|---|---|---|
| `breakeven_at_r` | 0.3 | Move SL to entry at 0.3R — very fast |
| `partial_close_r` | 1.0 | Full close at 1R |
| `trail_atr_mult` | 0.3 | Tight trail after breakeven |
| `rsi_neutral_low` | 40 | Early close if RSI returns here |
| `rsi_neutral_high` | 60 | Early close if RSI returns here |
| `risk_pct_bot2` | 2.0% | Per trade risk |
| `max_daily_loss_pct_bot2` | 10% | Daily loss cap |

---

## Regime Behaviour

Inverted vs Bot 1 — they react opposite to the same market conditions.

| Regime | Bot 2 behaviour |
|---|---|
| RANGING | Full size — ideal, price oscillates predictably |
| TRANSITIONING | 75% size |
| TRENDING | 40% size — trends fight reversion |

---

## Tuning Guide

| Problem | Parameter | Change |
|---|---|---|
| Giving back too much | `breakeven_at_r` | Lower to 0.2 |
| Closing too early | `partial_close_r` | Raise to 1.5 |
| Too few signals | `bb_std_entry` | Lower 2.0 → 1.8 |
| Too many bad signals | `bb_std_entry` | Raise 2.0 → 2.2 |
| RSI exit too early | `rsi_neutral_low/high` | Widen to 35/65 |

---

## Log Messages to Watch

```
Scanning | price=4385.20 | regime=RANGING | risk_mult=1.0      ← ideal conditions
No reversion signal — conditions not met                        ← normal, waiting
REVERSION SIGNAL | BULLISH | score=5 | RSI=24.3               ← setup found
AI approved 61%                                                 ← gate passed
T12345678 → BREAKEVEN @ 4385.20 (0.31R)                       ← free trade
T12345678 FULL CLOSE @ 1.0R — banking profit.                  ← money secured
T12345678 EARLY CLOSE — RSI neutral (48.2) | profit=0.8R      ← mean reached
Market closing in 15 min — closing all 2 position(s). [DAILY-CLOSE] ← eod cleanup
```
