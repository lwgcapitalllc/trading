# BOT2_MEAN_REVERSION_GUIDE.md
# Bot 2 — Mean Reversion

**File:** `bots/bot2_mean_reversion.py`
**Style:** Mean reversion — fades price extremes back to average
**Capital allocation:** 20–40% of account (runs alongside Bot 1)
**Trades per day:** 0–4 typical

---

## What It Does

Trades price back toward its statistical average after it stretches too far in one direction. When an instrument becomes overbought or oversold relative to its Bollinger Bands, RSI, and VWAP, there is a high probability of a snapback. This bot captures that snapback.

This is the cash flow layer. While Bot 1 waits for specific session setups, Bot 2 runs 24 hours continuously. It generates consistent wins during choppy, ranging conditions when Bot 1 is completely idle. The two bots are naturally uncorrelated.

---

## When It Trades

Active 24 hours. No session restriction.

London (07:00–10:00 UTC) and NY (12:00–15:00 UTC) setups score higher because volume and follow-through are stronger. Low-volume periods will naturally produce fewer signals — the AI and confluence gates filter weak setups out automatically.

---

## How It Finds a Trade

All conditions must align simultaneously:

**Bullish reversion (long after oversold extreme):**
1. Price below lower Bollinger Band (2+ standard deviations)
2. RSI below 28 (oversold)
3. Price more than 1.5 standard deviations below VWAP
4. Rejection candle confirming buyers stepping in

**Bearish reversion (short after overbought extreme):**
1. Price above upper Bollinger Band (2+ standard deviations)
2. RSI above 72 (overbought)
3. Price more than 1.5 standard deviations above VWAP
4. Rejection candle confirming sellers stepping in

Minimum confluence score of 4 required. AI votes approve or block.

---

## How It Manages Trades — Aggressive Profit Protection

Mean reversion moves fast. The bot banks profit quickly rather than waiting.

| Stage | Trigger | Action |
|---|---|---|
| 1 | +0.3R profit | Stop moves to breakeven — trade is now free |
| 2 | +1R profit | 50% of position closes — profit banked in account |
| 3 | After partial close | Remaining 50% trails with tight 0.3× ATR stop |
| 4 | RSI returns to 40–60 | Full position closes — mean has been reached |

**Why this matters:** Mean reversion trades can reverse quickly after hitting the mean. Banking 50% at 1R guarantees profit on every trade that moves in your favour. The trailing stop on the runner captures any extended move. If the trade reverses before RSI reaches neutral, the tight trail stops you out with most of the gain locked in.

---

## Risk Controls

All configured in `config.json` → `bot2_reversion` section.

| Parameter | Default | Description |
|---|---|---|
| `breakeven_at_r` | 0.3 | Move SL to entry when profit hits this R multiple |
| `partial_close_r` | 1.0 | Close 50% of position at this R multiple |
| `partial_close_pct` | 0.50 | Fraction of position to bank at partial close |
| `trail_atr_mult` | 0.3 | ATR multiplier for tight trailing stop after partial |
| `rsi_neutral_low` | 40 | Early close if RSI returns above this |
| `rsi_neutral_high` | 60 | Early close if RSI returns below this |

**Protection limits:**

| Control | Default | Notes |
|---|---|---|
| Risk per trade | 2% | Of current account balance |
| Daily loss cap | 10% | No new entries rest of day |
| Weekly loss cap | 20% | 6hr cooldown then resume |
| Consecutive losses | 3 | 30min → 1hr → 3hr cooldown |

---

## Regime Behaviour

Inverted logic vs Bot 1 — they react to the same regime opposite ways.

| Regime | Bot 2 behaviour |
|---|---|
| RANGING | Full size — ideal, price oscillates predictably |
| TRANSITIONING | 75% size |
| TRENDING | 40% size — strong trends fight reversion |

---

## AI Learning

After 30 closed trades the model trains on: confluence score, ATR, RSI value, Stochastic RSI, Bollinger Band %B position, VWAP deviation, spread, day/hour, rolling win rate, and regime score. Retrains every 10 new trades. Walk-forward validated only.

---

## Tuning Guide

| Problem | Parameter | Adjustment |
|---|---|---|
| Giving back too much profit | `breakeven_at_r` | Lower (e.g. 0.2) |
| Partial close too early | `partial_close_r` | Raise (e.g. 1.5) |
| Runner stopped out on noise | `trail_atr_mult` | Raise (e.g. 0.5) |
| Not enough signals | `bb_std_entry` | Lower (e.g. 1.8) |
| Too many bad signals | `bb_std_entry` | Raise (e.g. 2.2) |
| RSI close too early | `rsi_neutral_low/high` | Widen (e.g. 35/65) |

---

## Log Messages to Watch

```
Scanning | price=2385.20 | regime=RANGING | risk_mult=1.0    ← ideal conditions
No reversion signal — conditions not met                      ← normal, waiting
REVERSION SIGNAL | BULLISH | score=5 | RSI=24.3              ← setup found
AI approved 61%                                               ← gate passed
ENTRY | bullish | lots=0.02 | R:R=2.80                       ← trade placed
T12345678 → BREAKEVEN @ 2385.20 (0.31R)                      ← free trade
T12345678 PARTIAL CLOSE 50% @ 1.0R | Profit banked.          ← money secured
T12345678 TRAIL SL=2386.10 (peak=2386.50)                    ← runner active
T12345678 EARLY CLOSE — RSI neutral (48.2) | profit=1.4R     ← clean exit
```
