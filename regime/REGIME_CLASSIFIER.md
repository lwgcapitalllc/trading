# Regime Classifier — Algorithm Reference

Plain-English description of what the classifier does, how it works, and when not to trust it.

---

## What it does

The regime classifier reads recent price data and answers one question: **is the market trending, ranging, or somewhere in between?**

The answer drives two downstream decisions:
- **Live bots** — whether to take entries and at what position size.
- **Backtest lab** — how to segment historical performance (e.g. "this strategy has a 2.1 Sharpe in TRENDING but loses money in RANGING").

---

## Why we have it

A trend-following strategy bleeds in choppy markets. A mean-reversion strategy gets stopped out in strong trends. No single strategy works in all regimes. The classifier makes the current regime explicit so each strategy can act accordingly, rather than trading blind.

---

## Three inputs (signals)

Every classification is the sum of three independent signals, each scored 0, 1, or 2.

### 1. ADX — trend strength

Computed on the shorter-timeframe dataframe (H1 for bots, daily for the lab).

ADX measures how strong the current directional move is, regardless of direction. High ADX means price is making sustained progress in one direction. Low ADX means it is oscillating without follow-through.

We use an EWM-smoothed variant (span=14) rather than Wilder's original rolling-window version. The math is equivalent for stable signals; EWM is less prone to sudden jumps when old bars roll off.

**Score:** ≥ 25 → +2 (trending). 20–24 → +1. < 20 → +0 (ranging).

### 2. ATR ratio — volatility expansion vs. compression

Computed on the longer-timeframe dataframe (H4 for bots, daily for the lab).

ATR ratio = (current 14-period ATR) / (20-period rolling average of that ATR).

A ratio above 1.0 means recent volatility is above its recent average (expanding). Below 1.0 means it is contracting. Trends typically begin after a volatility expansion; tight ranges see ATR compress toward low values.

**Score:** ≥ 1.2 → +2 (expanding). 0.8–1.19 → +1. < 0.8 → +0 (compressing).

### 3. RSI range — directional vs. choppy momentum

Computed on the shorter-timeframe dataframe.

RSI range = max(RSI) − min(RSI) over the last 20 bars, where RSI uses a 14-period window.

When price is trending, RSI reaches extreme values (high or low) and stays there. A wide RSI range means momentum was strongly one-directional over the lookback. When price is choppy, RSI oscillates between moderate values and the range collapses.

**Score:** ≥ 35 → +2 (directional). 20–34 → +1. < 20 → +0 (choppy).

---

## Classification rules

Raw score = sum of three signal scores = 0 to 6.
Normalized score = min(5, round(raw × 5/6)) = 0 to 5.

| Normalized score | Coarse label | Meaning |
|---|---|---|
| 3–5 | TRENDING | Strong directional move. Trend strategies trade full size. |
| 2 | TRANSITIONING | Mixed signals. All strategies trade at half size. |
| 0–1 | RANGING | No trend, no momentum. Trend strategies sit out. |

### Fine-mode only: splitting the RANGING space

When `score_norm ≤ 1` and `mode="fine"`, ATR ratio is checked a second time with tighter bounds to distinguish two distinct types of quiet market:

| Condition | Fine label | Meaning |
|---|---|---|
| score_norm ≤ 1 AND atr_ratio ≥ 1.5 | HIGH_VOLATILITY | Big moves but no momentum — likely stop-hunt or whipsaw territory. |
| score_norm ≤ 1 AND atr_ratio ≤ 0.5 | LOW_VOLATILITY | Compressed and quiet — price coiled, no breakout yet. |
| score_norm ≤ 1, neither above | RANGING | Ordinary sideways chop. |

TRENDING and TRANSITIONING are identical in both modes. Fine mode only adds nuance within the RANGING space.

### Coarse ↔ fine mapping (lossless round-trip)

| Fine label | Coarse equivalent |
|---|---|
| TRENDING | TRENDING |
| TRANSITIONING | TRANSITIONING |
| RANGING | RANGING |
| HIGH_VOLATILITY | RANGING |
| LOW_VOLATILITY | RANGING |

Both HIGH_VOLATILITY and LOW_VOLATILITY collapse to RANGING in coarse mode because both represent "do not trade with directional bias" — the same instruction the bots need.

---

## What UNKNOWN means

The classifier returns `"UNKNOWN"` when:

- The input dataframe has fewer than 34 rows (not enough history for ADX(14) + RSI(14) with a 20-bar lookback window).
- Any signal produces a NaN (missing OHLC data, division edge cases).

UNKNOWN is not an error — it is an explicit "I don't have enough data to classify." The shim that wraps this for the live bots handles UNKNOWN by keeping the last cached regime state.

---

## When not to trust the labels

- **At market open after a gap.** ATR ratio spikes on the first bar; the classification may flip. Give it 1–2 bars to stabilize.
- **Thin holiday markets.** RSI range collapses artificially. The classifier may call RANGING on days that are just low-liquidity, not genuinely sideways.
- **Regime transitions.** By design, TRANSITIONING is the classifier saying "I'm not sure." Treat TRANSITIONING entries as lower-conviction.
- **Short history.** The first 34 bars of any new instrument feed return UNKNOWN. This is correct behavior — don't force a label.

---

## Where the thresholds come from

The coarse thresholds (ADX 25/20, ATR 1.2/0.8, RSI range 35/20) were set during initial bot development and have not been systematically optimized. They are reasonable heuristics for XAUUSD on H1/H4 timeframes.

The fine-mode ATR thresholds (1.5 and 0.5) were set wider than the coarse ATR bands to catch only the most extreme volatility expansions and compressions.

All thresholds live in `thresholds.py`. They are configurable per-call via the `thresholds` parameter but are intentionally not auto-optimized — regime labels are used downstream in trading decisions and should not shift under the user's feet.

---

## Future improvements

- **Instrument-specific thresholds.** ADX and ATR ratio behave differently on NAS100 vs. XAUUSD. A per-instrument threshold config would improve classification accuracy outside gold.
- **Multi-timeframe consistency check.** A regime where H1 and H4 agree is more reliable than one where they conflict. A "confidence" field could surface this.
- **Regime persistence filter.** Prevent rapid label flips by requiring two consecutive identical classifications before committing a change. Reduces noise at transitions.
