# The 20-day momentum filter — a reusable entry check

**Purpose:** How to test, on any strategy here, whether its trades do better WITH or AGAINST the
bigger move — and how not to fool yourself doing it.
**Status:** A technique, measured once (realign, 2026-09-16): it smoothed the curve but failed the
both-halves test, so it was not shipped. **Not built into any bot
or engine.** First measurement: `strategies/python/realign/realign_optimization.md` → Run 12.

---

## What it is

**Momentum, also called rate of change,** is the plainest trend measure there is:

> 20-day momentum = today's close ÷ the close 20 trading days ago − 1

Above zero, the market is up over the last month; below zero, it is down. There is no average and
no volatility in it — it is not ATR (which measures how far price moves, not which way) and not a
moving average (which smooths, and lags differently).

**As a filter it asks one question per trade:** does this trade point the SAME way as the last 20
days, or AGAINST them?

- Classic trend-following uses it FORWARDS: only take trades with the move.
- Realign measured best using it BACKWARDS: refuse trades with the move, keep those against it.

**Which way round is right is a measurement for each strategy, never an assumption.**

## Rules for computing it — each one prevents a fake result

- **Use only days that have CLOSED before the trade's trading day.** Today's close is not known at
  entry; using it is look-ahead and makes any filter look good.
- **Build the days on the broker's 17:00 New York roll**, the same day boundary the sessions and
  liquidity engines use — not midnight UTC.
- **Too little history → let the trade through.** Refusing on missing data is a silent filter
  nobody chose (root rule 1: "no" and "cannot ask" are different values).

## How to test it on a strategy — the order matters

1. **Tag, don't filter.** Write every trade's momentum sign next to its R. Group by "with" /
   "against", split the history in two, and also sum each group with its single best trade
   removed. A group that only works in one half, or only because of one trade, is a story.
2. **Replay, never delete rows.** With one position slot, a refused setup frees the slot for a
   different trade. Crossing trades off a list gives a number no bot would ever produce. Patch the
   strategy's entry placement and re-run the backtest.
3. **Check the neighbours.** Re-run at other lookbacks (realign used 5, 10, 20, 40, 60). An effect
   that exists only at one length is a fitted number; one that holds across lengths is real.
4. **Pass both halves, and the best-trade removal.** The same bar every filter here must clear.
5. **Look at the fresh data separately.** Any history not used while choosing is the only honest
   test — say how many trades it holds.
6. **Judge on the combined account,** not the bot alone — the aim is a smoother total curve.
7. **Ship only with its Pine input, export twin and a green parity gate.** Momentum needs only daily
   closes, so it CAN be gated (a market-condition label from `engines/regime/` cannot).

## What realign showed (full tables in its Run 12)

- Refusing trades with the 20-day move cut the worst drawdown from 14.5R to about 5R, and that held
  at every lookback from 10 to 60 days.
- It cost total profit at every lookback (54R → 48.5R at 20 days, less elsewhere), because the
  2023+ trend paid the aligned trades.
- The reading: a strategy that enters a short-term trend on a pullback does best when that short
  trend runs against the monthly move — a pullback inside the bigger picture.

## Where to try it next

Any bot whose record shows the "profitable direction flips with the trend" pattern — SOS Fade and
the extreme leg are the obvious candidates. Expect either direction, or nothing.
