# MPC D Strategy — spec

**"D" as in dog. The dirty one.** Aaron's name, 2026-08-06.

**Status:** specified from four hand-marked chart examples. Pine `strategy()` built
(`indicators/mpc_d_strategy.pine`) — a full execution layer with %-of-equity sizing and a
TP1/TP2/runner ladder, so it drives the TradingView Strategy Tester and has a Properties tab.
Compiled and **MEASURED once, 2026-08-06** — see *The first measurement* below. **The edge is
statistically indistinguishable from zero (t = 1.00).** Not ported to Python, no parity gate.

⚠ It was written as an `indicator()` first, which is why it had no Properties tab and no
tester. That distinction is the whole difference between a tool that MARKS the sequence and
one that can be scored, and it is worth stating because the file name said `strategy` either
way — the name is not the declaration.

---

## The sequence

A trend gets shaken out against itself and then resumes. The shakeout is what makes the
entry cheap and the resumption is what confirms it.

1. **A trend is established and MATURE.** An SOS opens it, then it prints at least one BOS.
   The BOS is what makes it a trend rather than a single break.
2. **A counter-trend SOS fires.** Price shifts against the trend. This is the shakeout —
   the move that takes out the trend's last protected swing and convinces everyone the
   trend is over.
3. **A with-trend SOS fires.** Price shifts straight back into the original trend.
   **This is the entry.**

The stop sits beyond the extreme the counter leg reached. That extreme is the only price
in the sequence that carries information: if price goes back through it, the shakeout was
a real reversal and the premise is dead.

---

## The thing that is not obvious, and it is the whole implementation

**An SOS strictly alternates direction, by construction.** A bull SOS requires `st.dir == -1`
and sets `st.dir := 1`; the next SOS on that chart can only be a bear one. So "an SOS,
then an SOS the other way" is *always* true and can never be a trigger. Every pair of
consecutive SOS events on any chart satisfies it.

What separates the D sequence from ordinary structure is an **asymmetry in maturity**
between the two legs either side of the counter-SOS:

| leg | test | meaning |
|---|---|---|
| the trend being RETURNED to | printed **≥ `dTrendBosMin`** BOS | it was a real trend, not one break |
| the counter leg in between | printed **≤ `dCtrBosMax`** BOS | it was a shakeout, not a new trend |

Drop either test and it fires on every second SOS on the chart. Those two
numbers are the strategy.

### State machine

Because SOS alternates, the check has to reach **two SOS back** — to the trend that the
*previous* SOS killed:

```
on every BOS that is not an SOS:   dCurBos += 1

on every SOS (direction nDir):
    FIRE if  dTrendDir == nDir                     // returning to the trend from 2 SOS ago
         and dTrendBos >= dTrendBosMin             // that trend was mature
         and dCurBos   <= dCtrBosMax               // this counter leg was not
         and bar_index - dSosBar <= dCtrBarsMax    // and it did not take for ever

    then shift:
        dTrendDir := -nDir        // the direction this SOS just killed
        dTrendBos := dCurBos
        dCurBos   := 0
        dSosBar   := bar_index
```

`dTrendDir` at the moment of the check still holds the value written by the *previous*
SOS, which is exactly the trend two-back. That one-bar-of-state lag is the trick.

---

## The four worked examples

XAUUSD. Prices read off Aaron's screenshots, so treat them as approximate — they are here
to pin the SHAPE, not to be quoted as results.

| # | date | dir | prior trend | counter SOS | counter extreme (stop) | return SOS (entry) | ran to |
|---|---|---|---|---|---|---|---|
| A | Jul 27-28 | SHORT | bear, 2 BOS | bull ~4,048 | high ~4,061 | bear ~4,027 | ~4,010 |
| B | Aug 4-5 | LONG | bull, 2 BOS | bear ~4,072 | low ~4,065 | bull ~4,106 | ~4,137 |
| C | Aug 9 | LONG | bull, 2 BOS | bear ~4,105 | low ~4,098 | bull ~4,118 | ~4,137 |
| D | Aug 8-9 | SHORT | bear, 2 BOS | bull ~4,325 | high ~4,362 | bear ~4,266 | ~4,150 |

All four resolved in the traded direction. The sequence identifies real turns.

### ⚠ The finding that changes the design

**Entering at the return-SOS close, with the stop at the counter-leg extreme, gives
roughly 0.5R to 1.2R on Aaron's own four examples.**

| # | risk (entry → stop) | reward (entry → extreme reached) | ≈R |
|---|---|---|---|
| A | ~34 | ~17 | 0.5 |
| B | ~41 | ~31 | 0.75 |
| C | ~20 | ~19 | 0.95 |
| D | ~96 | ~116 | 1.2 |

Every one of them was directionally right and only one cleared 1R. The reason is
structural, not bad luck: **an SOS confirms at the top of the reclaim leg.** By the time
the break is valid, price has already travelled from the counter extreme back through the
whole leg — so the entry is at the expensive end and the stop is the full leg away.

This is the same problem A+ solves by resting a limit on the fib retrace of the SOS leg
instead of buying the break. The D strategy has the identical shape and probably wants the
identical answer. It therefore ships **both** entry modes:

- **`SOS close`** (default) — marks exactly what Aaron drew, so the tool can be checked
  against the four examples before anything is changed.
- **`Retrace`** — rests the entry at a fib of the reclaim leg (counter extreme → the high
  or low made by the SOS bar). Better price, tighter stop, and it will miss the runs that
  never come back.

Which is right is a MEASUREMENT, not an argument. Do not settle it by reasoning.

### ⚠ The counter leg is not always short

Example C's counter leg ran about 3 hours. Example D's ran about 33 hours and printed its
own higher highs on the way. So:

- `dCtrBarsMax` has to be generous, and it is timeframe-relative — 400 bars is ~4 days on
  15m and ~33 hours on 5m.
- `dCtrBosMax` cannot be 0. Examples A and D both show a counter leg that broke structure
  in its own direction before turning back. Default is 1.

### ⚠ "Sweep" here means a real break, not a wick

The engine's counter-SOS requires a **close** through the protected swing. In every one of
the four examples the counter leg printed a genuine LL or HH that stayed. This is not the
wick-through-and-reclaim event the word "sweep" normally describes, and it is much rarer.
Building the wick version would be a different strategy.

---

## Inputs

**Naming, grouping and tooltips follow `indicators/mpc_strategy.pine`** (Aaron, 2026-08-06):
the sequence gates get their own group with a `d` prefix, exactly as A+ uses `aplus*`, and
everything that decides what a trade *does* lives under **Strategy Execution** with an
`exec` prefix. Five groups, same as that file: `D Setup`, `Strategy Execution`, `D Debug`,
`Result Stats`, `Diagnostic Log`.

⚠ **Declaration order is now frozen.** TradingView keys a chart's saved input values off
declaration order *within each type*, so inserting a string or float above an existing one
silently resets every later input of that type on every chart running the script. Add new
inputs at the end of their type's run.

### D Setup

| input | default | what it decides |
|---|---|---|
| `dTrendBosMin` | 1 | how mature the returning trend must be |
| `dCtrBosMax` | 1 | how much the shakeout may break before it stops being a shakeout |
| `dCtrBarsMax` | 400 | how long the shakeout may last |

### Strategy Execution

| input | default | what it decides |
|---|---|---|
| `execLongs` / `execShorts` | on / on | direction filter, read at the SIGNAL so what is drawn is what is traded |
| `execEntryMode` / `execRetraceFib` / `execLimitBars` | `SOS close` / 0.5 / 20 | entry price and how long a resting limit lives |
| **`execVwapReq` / `execVwapSlope` / `execVwapSlopeBars`** | **off / off / 4** | **the VWAP gate — see *The VWAP entry* below** |
| `execShowVwap` | on | draws the exact line the gate reads |
| `execSlMode` / `execSlPct` / `execSlBufTk` | `Sweep extreme` / 50 / 0 | the stop anchor — see below |
| **`execMinStopMode` / `execMinStopVal`** | **`% of price` / 0.08** | **the minimum-stop guard. See the warning below.** |
| `execSizeMode` / `execRiskPct` / `execFixedQty` | risk % / 1.0 / 1.0 | position sizing |
| `execTp1R` / `execTp2R` / `execTp3R` | 1 / 2 / 3 | targets, in R |
| `execTp1Pct` / `execTp2Pct` | 50 / 25 | how much comes off at each rung |
| `execBeBufTk` | 30 | breakeven buffer, in ticks |
| `execTp2StopMode` | `TP1 price` | the stop floor the instant TP2 is reached |
| `execRunnerTrail` | `Structure + % ratchet` | how the runner is trailed after TP2 |
| `execStructTrailBufTk` / `execTrailPct` / `execTrailStep` | 20 / 1.0 / 5.0 | the three trail settings |
| `execCloseOppSOS` | off | force-close on an SOS against the trade |
| `execTimeStopMode` / `execTimeStopHrs` | `Off` / 36 | the clock exit |
| `execShowConfLabel` / `execLabelWhich` / `execLabelOff` | on / `All` / 6 | the entry callout and its keep filter |
| `execShowPosBox` / `execShowExitLines` / `execShowShakeout` | on / on / on | the position drawing |

### The exit ladder — a PORT, not a lookalike

`f_dRatchet` is `mpc_strategy.pine`'s `f_swingRatchet` unchanged: anchor on the last confirmed
swing ± buffer, then climb one %-of-price step per step of favourable move, falling back to the
bare anchor until the move is a full step past it — so it is never *looser* than the plain
structure trail, only equal or tighter. The staged stop, the three TP2 floor modes, the three
trail methods, the time stop and close-on-opposite-SOS all keep their shapes and defaults.

⚠ **One deliberate divergence, commented at the site.** `mpc_strategy.pine` re-issues every
exit rung unguarded on every bar. That is safe *there* only because it ships both rungs at 0%,
so the rung is skipped entirely and the bug is unreachable at its defaults. This file ships a
real scale-out, so it stops re-issuing a rung once its target has been touched — calling
`strategy.exit` with an id whose order already **filled** places a NEW order rather than
modifying the old one, and a re-issued TP1 would bank another slice of the remainder every bar.

⚠ **`execTp1Pct` / `execTp2Pct` default 50/25 here, not mpc's 0/0.** Riding the whole position
to the runner tested best on the A+ bot over 6.6 years. That is a fact about *that* strategy,
not this one, so it is stated in the tooltip rather than copied as a default.

⚠ **The minimum-stop guard is ON and must stay on while any tight anchor is reachable.** Size
is risk *divided by* stop distance, so a stop that collapses onto the entry does not risk less
— it builds an enormous position. Three of the four anchors here can land arbitrarily close to
the entry (`% of entry-to-sweep` at 5% is a twentieth of the leg). That is the shape that
detonated A+ Run 4 and BOS Run 1 (worst trade −14.33R). It is an entry *filter*: a refused
setup is skipped, never resized. The 0.08 floor is the A+ measurement and has **not** been
measured here.

### D Debug

`showBlockTag` drops a pink **SETUP BLOCKED** tag whenever a with-trend SOS returned to the
right trend — the one structural fact the sequence is built on — and one of your gates refused
it, with the reason and the entry it would have taken in the tooltip. Seven reason codes in
precedence order, so a tag can never blame a downstream gate for an upstream refusal:

1. direction off · 2. trend too young · 3. shakeout became a trend · 4. shakeout stale ·
5. stop too tight · 6. stop on the wrong side of the entry · 7. already in a position

⚠ **"Ready" is `okDir` alone, deliberately.** Every other gate is a *choice*, and those are
precisely what the tag exists to report — folding any of them into readiness would hide the
refusals worth seeing. That is the same rule `mpc_strategy.pine` states at its own block tag.

`execDiagLog` writes one `log.info` line per entry, result and block to the Pine Logs tab.
Off by default: on a long history it is a lot of lines.

## The VWAP entry — added 2026-08-06

Aaron's ask, and it aims straight at the finding above: the with-trend SOS confirms at the top
of the reclaim leg, so waiting for it is *what makes the entry expensive*. Enter earlier —
after the shakeout, on the close back on the pro-trend side of VWAP.

**It is a STATE test, not a cross event, and that is the explicit instruction.** *"If it is
already supported by the VWAP and the VWAP is pro-trend, and it does not have to cross back
over, take those trades."* So a shakeout that dipped under VWAP and reclaimed it, and one that
never lost it, are the **same signal** — both are simply "the close is on the trend's side of
the line". Writing this as a `ta.crossover` would silently refuse every setup of the second
kind, which is half of what was asked for.

### It ships two ways, because they are two different questions

| | what it is | default |
|---|---|---|
| `execEntryMode = "VWAP side"` | the **trigger** — enter on the first qualifying close after the shakeout, never waiting for the SOS | not default |
| `execVwapReq` | a **filter** on whichever mode is selected — refuse a setup whose entry bar is on the wrong side | **off** |

Both off by default, so **the 2026-08-06 baseline stays reproducible**. `execVwapSlope`
additionally requires the line itself to be rising for a long / falling for a short, over
`execVwapSlopeBars` (4 — one hour on 15m, and in **bars**, so it does not transfer between
timeframes).

### 🔴 It is a different trade, not a cheaper D

The with-trend SOS is the *only* evidence in the sequence that the shakeout failed. Dropping
it leaves VWAP-side as the whole confirmation, which is much weaker — this becomes "buy the
dip in a trend, gated on VWAP", closer to a continuation setup than to D. That may well be the
better trade; it is not the same one, and its result must not be quoted as D's.

### The VWAP is the session VWAP, deliberately

`ta.vwap(hlc3)` — the line `mpc_assistant.pine` draws and `engines/vwap/` is the canonical
Python port of. An anchored-at-the-shakeout VWAP would be a **second VWAP implementation**,
which `CLAUDE.md` forbids, and it would not be the line the request was about: *"already
supported by the VWAP"* describes a level that has been sitting under price, which an anchor
placed at the shakeout cannot be. ⚠ **It resets at the trading-day open**, and `dCtrBarsMax`
allows ~33h on 15m, so a sequence can straddle the reset and be judged against a VWAP anchored
after its own shakeout began. That is what the line on the chart does; a filter quietly using a
*different* VWAP from the one being looked at would be the worse failure.

### Four things that had to be got right, and would each have failed quietly

1. **One entry per sequence.** The SOS trigger is self-limiting — an SOS is one bar. A state
   test is true on every bar, so with only `bBusy` stopping it a stopped-out sequence would
   re-enter immediately and keep going until the bar cap expired. `dSeqTaken` latches, released
   only by the next SOS shift.
2. **Skipped on SOS bars.** The unconditional shift has already run by then, so `dTrendDir`
   describes the trend that SOS just *killed* and the leg extremes are reset to that one bar.
3. **The minimum-stop guard stops being optional.** Entering early means entering *close to
   the sweep extreme*, and the stop is anchored at that extreme — so the better the entry, the
   smaller `dist`, and `qty = risk / dist` grows as it shrinks. On the SOS path the whole
   reclaim leg sits in between and the hazard is rare; here it is the normal case. **Do not run
   this mode with `execMinStopMode = "Off"`.**
4. **Direction could no longer be read off `st.bull_sos`.** The block tag and the `B|` log line
   both inferred a candidate's side from the SOS on the same bar — correct only while every
   candidate arrived on one. A VWAP candidate does not, so every candidate of the new mode,
   long or short, would have been drawn and logged as a **short**. `dCandDir` now carries it.

### Block reason 9

`9 = wrong side of VWAP`, **numbered** last and **ranked** fifth (after *stale*, before *stop
too tight*) — the number is a wire format that archived exports decode against and can never be
renumbered, while its position is only which reason gets reported. ⚠ It is raised by the
**filter** only. Under `"VWAP side"` the test is the trigger, so a bar on the wrong side is not
a refused setup — reporting it would write one refusal per bar for the whole window.

### What changed in the export twin

- `cfg_modes`' entry digit went **2-way → 3-way**. It was `SOS close ? 0 : 1`, which sends
  `"VWAP side"` to 1 — so a VWAP run would have been stored and later read as a **Retrace**
  run. 🔴 **This is the `execRunnerTrail` trap of 2026-07-26 exactly: a code that collapses a
  widened dropdown does not fail, it lies. Whenever an option is added to any input, find its
  cfg digit in the same commit.**
- `cfg_bits` gained `execVwapReq·8` + `execVwapSlope·16`; `cfg_vwap_slope_bars` added.
- **`px_vwap`** on every bar, ungated — this is what makes the rule **re-priceable offline**:
  the side test at any candidate and the slope over any lookback can be reconstructed from a
  run taken with the gate switched **off**, so one export answers "would a VWAP filter have
  helped?" instead of needing a second run to ask.
- 🔴 **`f_xCand()` deleted.** It rebuilt candidate direction and leg extremes from
  `st.bull_sos` plus `[1]` lookups, and both halves broke: a VWAP candidate returns direction
  0, which would have **blanked every candidate column for the new mode** — a clean CSV with
  nothing in it — and `[1]` only means "before the shift" on a bar where the shift ran, while
  `dCurBos` can be incremented by a plain BOS on a non-SOS bar. The columns now copy the
  parent's `dCand*` record. **Plot count 48 → 51.**

### Status

**Not compiled, not run, not measured.** Everything above is construction, and the only number
this strategy has is the `SOS close` baseline in *The first measurement*.

## Where the stop goes

The sequence hands over three prices, so every sensible stop is a point on the line between
them. All four modes are inputs; **none of them is known to be right yet.**

| mode | anchor | character |
|---|---|---|
| `Sweep extreme` (default) | the high/low the shakeout reached | the honest invalidation — through it, the shakeout was a real reversal. Widest, so the smallest position and the fewest stop-outs. |
| `Counter-SOS line` | the level the counter-SOS **broke**, which price then reclaimed | tighter, and structurally clean on its own terms: back below it and the reclaim is void. Sits INSIDE the shakeout range, so a wick back into the zone stops you out where the sweep stop holds. |
| `Between the two` | slides on `execSlPct` | 0% = the SOS line, 100% = the sweep extreme. |
| `% of entry-to-sweep` | a fraction of the entry-to-sweep distance | ignores structure entirely. For when the structural stops are simply too wide to size against. |

The counter-SOS line comes from the engine's own `st.bull_bos_high` / `st.bear_bos_low`,
captured at the counter-SOS and read at the entry on the **same one-SOS lag** as
`dTrendDir` — it is never re-derived from prices.

⚠ **A tighter stop is not a better trade.** It buys a bigger position on the same risk
budget and pays for it in stop-outs on setups that later worked. The two effects do not
cancel at a fixed rate, and which one wins is a measurement per instrument and timeframe —
which is exactly why this is four modes and not one hardcoded choice.

⚠ The ordering is well-defined and cannot invert: the counter-SOS bar closed **through** its
level and then went further, so the sweep extreme is always beyond the SOS line, which is
always beyond the entry. `Between the two` therefore interpolates in a known direction.

## What gets drawn

Per **filled** trade — not per signal, because under `Retrace` those are different bars and a
position block starting before the position existed would be drawing a trade nobody was in:

- the **shakeout**, shaded, spanning the counter-SOS to the bar the sequence completed
- the **risk block** in red, entry to stop, which tracks the *live* stop and visibly collapses
  when the breakeven move lands
- three **reward blocks** out to TP1/TP2/TP3, each of which **brightens on the bar its target
  was reached** — so which rungs paid is readable without opening the trade list
- a **callout** at the entry: one line on the chart, and the full breakdown in the tooltip —
  entry, stop, which anchor produced it, all three targets with their R and size, the shakeout
  extreme, the counter-SOS line, and how many bars the shakeout ran

---

## The first measurement — 2026-08-06

**XAUUSD 15m, VANTAGE, 2018-04-05 → 2026-07-26, at the shipped defaults.** Source: the
TradingView Strategy Tester's List of Trades, exported off `mpc_d_strategy_export.pine`.
Two files were taken, identical runs at different sizing (10k @ 10% and 100k @ 1%); R is
scale-free, so the 1% file is the one read. `min = −1.00R` **exactly**, which is what pins
the 1%-risk assumption and makes every figure below reconcilable.

**218 positions.** The trade list carries 468 rows because a scale-out is listed per leg:
125 ladder positions × 3 legs + 93 single-row time-stop closes.

| | |
|---|---|
| total | **+14.03R** (+13.93% on 100k) |
| expectancy | **+0.064R** per trade |
| **t-statistic** | **1.00** |
| 95% CI on mean R | −0.062 … +0.191 |
| 95% CI on the 8.3-year total | **−13.5R … +41.6R** |
| profit factor | 1.181 |
| win / scratch / loss (±0.15R band) | 44.5% / 9.2% / 46.3% |
| avg win / avg loss | +0.94R / −0.76R |
| max drawdown | 9.80R (9.42% of equity) |
| median hold | 107 bars ≈ 27h (winners 130, losers 78) |

### 🔴 The verdict, and it is B-LEG's again

**This is a *nothing*, not a loser.** t = 1.00 is as close to no signal as a number gets, and
the interval spans zero comfortably in both directions. Unlike B-LEG's 50 trades, 218 is a
respectable sample — so this is not "too small to tell", it is a measurement that says the
edge, if any, is smaller than the noise it sits in. Compare A+ over a shorter window: 159
trades / +142.17R / maxDD 5.62R.

### ⚠ Three things the distribution says that the total does not

**1. The ladder caps the tail, and the cap is BINDING.** Max R over 8.3 years is **+2.11**,
and `0.3×1 + 0.3×2 + 0.4×3` = **2.10R** — the exact arithmetic ceiling of the shipped rungs.
16 trades sit on it. So there is no right tail at all: 44.5% winners capped at 2.1R against
full −1R losers. A+ ships its rungs at **0/0** and rides the whole position to the runner
precisely because its money lives in the tail; here TP3 is a lid, and the trail behind it
has never been given anything to do. **Read this before tuning a gate** — the entry has been
blamed for a result the exit ladder bounded.

**2. The time stop is net negative here.** 93 of 218 positions (43%) exit on the 36h clock
for **−5.20R**; the other 125 make +19.23R. That is not proof the clock is wrong — a cut
trade might have gone on to lose more — but on A+ the identical lever bought a 30% drawdown
cut, and here it is eating a third of the gross. It fires at 36.25h, i.e. 36h plus one bar,
which is correct: a force close is a market order and fills at the next bar's open.

**3. Shorts contribute nothing.** Longs +13.28R over 136 positions; shorts **+0.75R over 82**.

### ⚠ The configuration is INFERRED, not proven

These were **List of Trades** exports. `mpc_d_strategy_export.pine` emits 22 `cfg_*` columns
for exactly this reason — a run must carry its own configuration — and a trade list carries
none of them. The R ceiling of 2.11, the −1.00R floor and the 36.25h clock together pin
risk 1%, TP 1/2/3R at 30/30/40, and the time stop at "Before TP1 only" / 36h, all of which
are the shipped defaults. **They do not pin the three gates** (`dTrendBosMin`,
`dCtrBosMax`, `dCtrBarsMax`), and nothing in the trade list can. Take the **chart-data**
export next; the twin exists for this.

### What to measure next, in this order

Each is one re-export, and the first two are cheap and independently large:

1. **`execTp3R = 0` and `execTp1Pct = execTp2Pct = 0`** — remove the lid, ride to the trail.
   The tail is the one thing this run proves does not exist yet.
2. **`execTimeStopMode = "Off"`** — price the clock properly instead of reading its net.
3. **`execEntryMode = "Retrace"`** — never measured at all, and it is the lever the spec was
   written expecting to matter.
4. Only then the gates, and only from a chart-data export that states them.

⚠ **Do not read any of these as a sequence of improvements.** With sd 0.952R over 218 trades,
a change worth less than about ±13R is inside the noise — the same trap the A+ jitter audit
recorded at sd 15.06R. A lever has to move the result a long way to have moved it at all.

---

## Open, and deliberately not decided yet

1. **Which entry mode pays.** See the finding above. Needs a real replay, not a read.
2. **Whether the counter extreme is the right stop at all.** It is the honest
   invalidation, but on example D it is $96 wide. A structure-based or ATR stop inside the
   reclaim leg may be the better trade at the cost of being stopped out of setups that
   later work.
3. **Overlap with A+ and B-LEG.** All three read the same `engines/market_structure/`
   stream on the same instrument. A+ fades an SOS; D buys the SOS *after* a fake one. They
   can fire on the same swing. `backtest/tools/overlap_audit.py` is the tool and it must be
   re-run before D goes anywhere near a live account — see `CLAUDE.md` → the overlap audit
   and G10/G11 in `docs/LIVE_TRADING_PIPELINE.md`.
4. **Timeframe.** The four examples span at least two chart timeframes. The bar-denominated
   gates (`dCtrBarsMax`) will not transfer between them unchanged.

## Build order, if it goes further

Pine indicator (done) → eyeball against the four examples → `strategy()` version for the
Strategy Tester → Python package under `strategies/python/mpc_d/` reusing the shared exit
ladder → parity gate. Nothing here is validated until a `compare_*.py` run exits 0 on a
real TradingView export.

⚠ **`exec_min_stop_mode` on from bar one** if this ever becomes a sized strategy. A retrace
entry with the stop inside the same band collapses the stop distance and `qty = risk / dist`
balloons. It has bitten twice already (A+ Run 4, BOS Run 1).
