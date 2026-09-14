# Notes — Superseded measurements and the exit-ladder re-default

The 6.5-year measurement this bot's numbers used to cite (now superseded — read the Status block above for the current figures) and the 2026-08-06 exit-ladder re-default, including what was tried and rejected and the open Asia-session lead that never shipped. Moved VERBATIM out of `strategies/python/b_leg/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## The 6.5-year measurement — 2026-08-04 — 🔴 **SUPERSEDED, AND KEPT AS THE RECORD OF WHY**

⚠ **EVERY NUMBER IN THIS SECTION IS DEAD. Do not quote it.** It measures the configuration that
existed on 2026-08-04, and **three defaults moved on 2026-08-06** — `bleg_max_days` 1.25 → 4.0,
`exec_trail_pct` 1.0 → 0.05, `exec_time_stop_hrs` 36 → 8 (see the two 2026-08-06 header entries).
Re-measured on 2026-08-09 over the same 155,531 bars, by two independent drivers that agree to the
cent: **99 trades, +17.87R**, free. Charged over the full history: 114 / +17.56R / PF 1.45 /
maxDD **−5.15R**. The drawdown is the real change — it used to be nearly double SOS Fade's and is now
slightly under it.

⚠ **The section stays because the STATISTICAL argument in it is still the right argument**, and it
now points the other way: 99 trades is still not many, and **no jitter audit has ever been run on this
bot**, so +17.87R has no error bar. SOS Fade's equivalent measured a run-to-run spread of sd 15.06R —
larger than B-LEG's entire total. Read the CI reasoning below, substitute today's numbers, and the
honest verdict is *"positive and not yet distinguishable from noise"* rather than *"no edge"*.

🔴 **The lesson is about the DOCS, not the bot.** This file's header recorded the new numbers on
2026-08-06 the same day they were measured. `docs/LIVE_TRADING_PIPELINE.md` → G15 and the root
`CLAUDE.md` went on quoting −0.94R for three days, and those are the two files a decision is read
out of. **The number was corrected where it was produced and not where it was consumed.**

---

That last sentence was finally acted on. **Nothing above this line changes** — parity is still green
and the code is still right. What is new is that the bot has been *replayed*, rather than validated,
over a real window.

```
python backtest/tools/run_report.py --strategy b_leg --start 2020-01-01 --end 2026-08-03
```

**155,453 M15 bars, 50 trades, −0.94R.** No cost layers (the free baseline, comparable to the
Strategy Tester). Win rate 34%, average win +1.65R, average loss −1.01R, expectancy −0.02R/trade,
peak-to-trough **−15.62R**.

| | trades | sum R | mean R | 95% CI on mean R | max DD (R) |
|---|---|---|---|---|---|
| `sos_fade` | 161 | **+135.94** | +0.84 | **+0.29 → +1.40** | −7.99 |
| `b_leg` | 50 | **−0.94** | −0.02 | **−0.40 → +0.37** | −15.62 |

**Read the CI column, not the sum R column.** SOS Fade's interval is entirely positive — 6.5 years of gold
is enough to say its edge is real. B-LEG's straddles zero and is centred on it: its true 6.5-year
total belongs anywhere between −20R and +18R, and no amount of staring at the −0.94 will narrow that.
This is the one place where `CLAUDE.md`'s "sample size arrives at the portfolio level" argument does
**not** apply: that rule says do not reject a strategy for trading rarely, and this is not a rejection
— it is the statement that the measurement cannot yet distinguish this bot from a coin.

⚠ **Everything here is about the SHIPPED DEFAULTS.** `exec_tp1_pct`/`exec_tp2_pct` = 0/0 and
`exec_sl_level` = "1.0" are **pinned to this fork's Pine for parity**, which is a correctness
decision, never a performance one. Lab run `096432c2ad20` ran 30/40. Read the table as "the
parity-pinned configuration has no measured edge", never as "the B-LEG setup does not work".

⚠ **The obvious next move is also the dangerous one.** Optimizing over 50 trades will find a winning
combination whether or not one exists. If it is done: state the out-of-sample split **before** the
grid runs, and expect the honest answer to be "not enough data", because `sos_fade_optimization.md`
Run 12 already showed on the SOS Fade bot that buying trade count by loosening a rule loses money.

⚠ **`--no-regime` was passed** on this run (the regime tag is reporting-only and does not touch a
trade). The "by regime" answer for B-LEG has not been measured and is a genuinely open question — the
2021–2023 losing stretch and the 2024–2026 recovery could be regime or could be noise at n=50.

## The exit-ladder re-default — 2026-08-06

Two defaults moved. Both are FORK PINS in `config.py` and matched defaults in
`strategies/tradingview/b_leg_strategy.pine` + its export; neither is inherited, and neither should be
"reconciled" with the SOS Fade parent, whose own measurements say the opposite in both cases.

| | `exec_trail_pct` | `bleg_max_days` |
|---|---|---|
| was | 1.0 (inherited) | 1.25 (`maxval` 3) |
| now | **0.05** | **4.0** (`maxval` 6) |
| SOS Fade parent | keeps 1.0 — its sweep gives 0.25% → 43.6R vs 109.3R at 1.0 | n/a, B-LEG-only input |

🔴 **EVERY NUMBER IN THIS SECTION PREDATES THE 2026-08-22 STRUCTURE FIX AND NO LONGER DESCRIBES
THIS BOT — and the free-book figure below never reproduced at all.** `f4b0410b` stopped the
structure engine anchoring backwards onto a candle a break had just rejected; on these exact bars
it moves B-LEG **+23.28R → +20.91R** across an unchanged 114 trades. ⚠ **And replaying the
2026-08-06 commit itself gives 114 / +23.28R, not the 112 / +17.64R recorded here** — so that free
figure came from a run whose settings nobody wrote down and **may not be used as a control.** The
usable control is `b_leg_optimization.md` → *The control*, measured on the account this bot trades.
**The RANKINGS in this section still stand — every row moved together — the totals do not.**

**Charged (spread + swap, `vantage_demo`), 186,312 M15 bars, 2018-09-13 → 2026-08-05:**

| | trades | sum R | PF | wins | max DD | IS | OOS |
|---|---|---|---|---|---|---|---|
| old defaults | 59 | −1.73 | 0.94 | 21 | −16.00R | −8.15 | +6.42 |
| **shipped now** | **112** | **+12.02** | **1.23** | 37 | **−8.89R** | **+0.78** | **+11.24** |

Free book at the new defaults: 112 / +17.64R / PF 1.36 / maxDD −6.21R.

**The protocol, because at n≈60 the protocol is most of the evidence.** The split was declared
before any row ran (IS 2018-09-13 → 2022-09-30, OOS after). Every row is a REAL REPLAY of the full
window; IS/OOS are computed by splitting the resulting trade list on entry time, which is safe here
only because it splits the OUTPUT of one identical run and therefore cannot change which trades
exist. Levers were measured ONE AXIS AT A TIME off the shipped baseline, never as a grid — a grid
over 60 trades finds a winner whether or not one exists, and this file said so before the work
started. The two that survived their own axis were then combined and re-checked in both halves.

⚠ **The reason to trust the combination is the FLATNESS, not the peak.** PF is 1.18–1.25 across the
whole 4×3 grid of trail step {0.05, 0.08, 0.10, 0.15} × staleness {3, 4, 5}. Every cell beats the
old PF of 0.94. There is no sharp optimum to have fitted to.

⚠ **It is still not an edge.** 95% CI on mean R = **−0.140 → +0.355**, i.e. the 7.9-year total
belongs anywhere in −16R to +40R. The top 3 trades are 100% of the total and the single best is
+5.07R of it. What genuinely improved is the drawdown, the sample size and the sign of the first
half — all three of which are what a live decision is actually made on, and none of which is proof.

### Rejected, with the reason each was worth trying

- **The minimum-stop guard** (floors 0.10%–0.40% of price, prototyped as a `_place_entries`
  subclass): no effect that survives both halves. The hypothesis was reasonable — this fork's stop
  distances span $2.51 to $49.02 and `qty = risk / dist`, so the tight end buys a position a single
  15m gold bar can traverse whole — and it is simply not where the money goes. ⚠ **The cheap
  estimate disagreed and was wrong in the usual direction**: deleting the refused rows from the
  finished 50-trade list scores a 0.25% floor at **+6R**, the real replay scores **zero**. This
  file's warning about entry-side filters and the one position slot, reproduced on demand.
- **The deeper band edge** (rest at `l_bot`, the 0.618 retrace, instead of `l_top`): PF 2.43,
  maxDD −4.58R, and **28 trades with +15.81 of its +17.25R in the first half**. Fill rate collapses
  112 → 28, which is the real cost and the reason the headline PF is meaningless.
- **Shorts only**: PF 1.58, IS −1.15 / OOS +14.82. A bet on gold's 2023-2026 run wearing a filter.
- **Dropping the SOS Fade priority gate** (`exec_aplus = False`): this file has called it the first tuning
  candidate since 2026-07-24. It adds exactly one trade over 7.9 years and that trade loses.

### Open lead — the Asia-session filter (NOT shipped)

Refusing entries in the Asia session and the late-day window gives **79 trades / +12.32R / PF 1.37
/ maxDD −4.98R**, positive in both halves (IS +2.89 / OOS +9.42) — the best drawdown of anything
measured, on Aaron's stated objective. Two independent samples agree: the original 50-trade baseline
had Asia at −5.0R on 13 trades. The mechanism is plausible (Asia is the thinnest book for gold, and
this fork's tightest stops are the ones a thin-book wick reaches).

**It is not shipped because it is new code, not a default.** Neither `b_leg_strategy.pine` nor
this package has a session filter for the B-LEG arm; adding one is a Pine input + a `cfg_` column +
the Python gate + a parity re-run, in one commit. It is also the most curve-fit-prone thing measured
here — slicing 112 trades by session is exactly the shape that finds a pattern in noise — so it
needs its own out-of-sample statement before it ships, not this one reused.
