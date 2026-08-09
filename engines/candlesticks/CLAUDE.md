# CLAUDE.md — Candlestick Pattern Engine Subsystem

**Purpose:** Turn the bar stream into CANDLESTICK PATTERN EVENTS — fifteen classic single-, two- and
three-bar patterns (Doji, Harami, Engulfing, Piercing Line, Belt Hold, Kicker, Hanging Man,
Morning/Evening Star, Shooting Star, Hammer, Inverted Hammer), each carrying the direction the source
Pine draws it in. The signal is "a bullish engulfing fired on this bar", not the arrow on the chart.
**Scope:** Pattern geometry only. No trading decisions, no structure, no MT5 ops, no UI, no colours,
no alert routing. It is a CONFLUENCE source: something a strategy ANDs into a setup it already has.
**Status:** BUILT + UNIT-TESTED (44 hand-traced tests, green) + ✅ **PINE-PARITY VALIDATED
2026-08-08 (exit 0) ON TWO EXPORTS AT TWO DIFFERENT SETTINGS**, both 20,138-bar
`VANTAGE_XAUUSD, 15m`, the engine configured **from each export's own `cfg_*` columns**:
`15_ce5c6.csv` at the Pine defaults (**trend 5 / doji 0.05**) and `15_ee761.csv` at the settings
actually traded (**trend 117 / doji 0.01** — see `CHART_PRESET`). Green at warmups 0 / 100 / 500 /
2000 on both. ⚠ **Two exports at two settings is what makes the `trend` / `doji_size` plumbing
proven rather than assumed** — a single green says the two sides agree at one configuration, and
`cfg_*` columns exist precisely so that claim can be widened.
✅ **AND THE RUN IS NOT VACUOUS: FOURTEEN OF THE FIFTEEN PATTERNS FIRED**, so the gate entered
almost every branch rather than agreeing about nothing — 302,070 flag comparisons, **zero rule
differences**.
⚠ **THREE BOUNDARY TIES, listed by the tool on every run and NOT swept under a tolerance** — see the
section below. They are float representation, not logic.
⚠ **`bullish_belt` fired ONCE and `hanging_man` ONCE in this window**, so those two are technically
exercised and statistically unproven here. Read them as covered by a single bar each.
**Pine:** ported line-by-line from `indicators/candle_sticks.pine` ("Candlestick Patterns
Identified, update 1-17-26", © repo32, v6 — a third-party indicator Aaron added 2026-08-08). Parity
harness is `indicators/candle_sticks_export.pine`, diffed against this Python by
`tools/compare_candles.py`.
**Last reviewed:** 2026-08-08 — built from scratch. See the notes below; three of them are about the
SOURCE file rather than about this port, and two of those change how the output should be read.

---

## What it detects

Fifteen rules, ported verbatim. `direction` is **the direction the source Pine DRAWS the pattern**,
not a trading opinion — see the callout below. Frequencies are measured, not estimated: one replay of
the full cached XAUUSD M15 history (186,366 bars, 2018-09-14 → 2026-08-07) at the Pine defaults
`trend = 5`, `dojiSize = 0.05`.

| key | Pine var | dir | bars | % of bars |
|---|---|---|---|---|
| `doji` | `doji` | 0 | 9,736 | 5.22% |
| `bearish_harami` | `bearHarami` | − | 11,999 | 6.44% |
| `bullish_harami` | `bullHarami` | + | 11,385 | 6.11% |
| `bearish_engulfing` | `bearEng` | − | 9,769 | 5.24% |
| `bullish_engulfing` | `bullEng` | + | 9,427 | 5.06% |
| `piercing_line` | `piercing` | + | 78 | 0.042% |
| `bullish_belt` | `bullBelt` | + | **19** | 0.010% |
| `bullish_kicker` | `bullKick` | + | 177 | 0.095% |
| `bearish_kicker` | `bearKick` | − | 178 | 0.096% |
| `hanging_man` | `hangingMan` | − | **25** | 0.013% |
| `evening_star` | `eveningStar` | − | 93 | 0.050% |
| `morning_star` | `morningStar` | + | 101 | 0.054% |
| `shooting_star` | `shootingStar` | − | 661 | 0.355% |
| `hammer` | `hammer` | 0 | 16,563 | 8.89% |
| `inverted_hammer` | `invHammer` | 0 | 15,412 | 8.27% |

### 🔴 At the settings actually traded (`CHART_PRESET`, trend 117 / doji 0.01)

Same 186,366-bar replay, the eleven patterns in the preset. **Two findings, and the second is the one
that changes a decision:**

| key | dir | bars | % | vs default |
|---|---|---|---|---|
| `doji` | 0 | 2,014 | 1.08% | **9,736 → 2,014** |
| `bearish_harami` | − | 9,891 | 5.31% | 11,999 → 9,891 |
| `bullish_harami` | + | 8,154 | 4.38% | 11,385 → 8,154 |
| `bearish_engulfing` | − | 9,028 | 4.84% | 9,769 → 9,028 |
| `bullish_engulfing` | + | 7,834 | 4.20% | 9,427 → 7,834 |
| `hanging_man` | − | **19** | 0.010% | 25 → 19 |
| `evening_star` | − | 93 | 0.050% | unchanged |
| `morning_star` | + | 101 | 0.054% | unchanged |
| `shooting_star` | − | 661 | 0.355% | unchanged |
| `hammer` | 0 | 16,563 | 8.89% | unchanged |
| `inverted_hammer` | 0 | 15,412 | 8.27% | unchanged |

🔴 **FIVE OF THE ELEVEN ARE COMPLETELY UNAFFECTED BY BOTH SETTINGS, and that is not a coincidence —
they read neither input.** `hammer`, `invHammer`, `eveningStar`, `morningStar` and `shootingStar`
carry no `open[trend]` gate and no `dojiSize` term, so tuning `trend` from 5 to 117 does nothing to
them whatsoever. **Only six of the eleven respond to the settings at all**: the four harami/engulfing
rules and `hangingMan` (via `trend`), and `doji` (via `dojiSize`). Anyone tuning those two inputs
expecting to sharpen the whole set is tuning six patterns and leaving five alone.

🔴 **`hanging_man` FIRES 19 TIMES IN EIGHT YEARS AT THESE SETTINGS — AND ZERO TIMES IN THE 20,138-BAR
PARITY WINDOW.** It is on the traded list and it is, in practice, dead: 0.010% of bars. Whatever it
is meant to contribute, it contributes it about twice a year. ⚠ **The parity gate is therefore silent
about it at these settings** — the tool says so out loud in its NEVER FIRED line, which is exactly
what that line is for. Its rule is covered by the trend-5 export (1 bar) and by unit tests, and by
nothing else.

⚠ `doji` is the pattern the settings move most — **5.22% → 1.08%**, a 4.8× tightening from
`dojiSize` 0.05 → 0.01. That is the input doing its job, not a discrepancy.

⚠ **Read the table below before choosing which patterns to use, because it splits into two families that
need opposite treatment.** Five patterns fire on **5–9% of all bars** — a "bullish engulfing" arrives
roughly every twenty candles, so on its own it is not a filter, it is barely a coin flip with a name.
The other ten fire between **19 and 661 times in eight years**. `bullish_belt` at 19 and
`hanging_man` at 25 cannot support a measurement at all: they are the B-LEG problem
(`## Trading Philosophy`) in miniature — a sample that small cannot distinguish a real edge from a
small negative one, whatever a backtest reports. **A rare pattern is a reason to widen the window or
drop the pattern, never a reason to trust a small green number.**

⚠ **13,772 bars (7.4%) carry MORE THAN ONE pattern**, and that is correct rather than double-counting:
several rules read the same geometry and differ only in the context they additionally demand. Every
Hanging Man is also a Hammer by construction (identical wick test at 4× vs 3× the body, plus two
lower highs and a trend gate) and the Pine plots both shapes on that bar. **A consumer wanting one
answer per bar picks by direction or by priority; it must not assume only one fires.**

---

## 🔴 Direction is the PINE'S RENDERING, and three patterns are undirected

`indicators/candle_sticks.pine` draws six patterns as a green up-arrow BELOW the bar, six as a red
down-arrow ABOVE it, and **Doji, Hammer and Inverted Hammer as a neutral white cross/diamond**. That
is exactly what `PatternSpec.direction` carries (+1 / −1 / 0), and the engine will not upgrade the
three neutrals.

**Hammer and Inverted Hammer are conventionally read as bullish reversals and this source does not
say so** — and the reason matters. **Neither carries a trend filter at all.** Ten of the fifteen
rules gate on `open[trend] < open` / `> open`; Hammer and Inverted Hammer gate on nothing, so a
"hammer" here can print in an uptrend, a downtrend or a range, and it does — 8.9% of every bar in
eight years. **A hammer with no trend context behind it is a candle shape, not a reversal signal.**

So: a strategy that wants them bullish states that itself, in its own config. The engine will not
decide it, because the moment it did, the engine and the chart would disagree about the same candle —
and this repo has spent a lot of time on the cost of two implementations of one claim.

---

## The two Pine semantics that decide parity

**1. `na` compares FALSE.** Every rule reading `open[trend]`, `high[2]` or `ta.lowest(10)[1]` is
simply false until that history exists. `_has_history()` makes that explicit per rule rather than
letting a missing bar raise or, worse, be read as `0.0` — **a fabricated zero would make
`open[trend] > open` trivially false and `open[trend] < open` trivially true, sprouting every bearish
pattern on the first bars of every chart.** This is the repo's own "never let *no* and *cannot ask*
be the same value" rule, met on a history offset instead of a broker call.

**2. `trend` sizes the history, and it is where the engine's warm-up comes from** — except for
`bullish_belt`, the one rule that needs the DEEPER of `trend` and 10 bars (it reads
`ta.lowest(10)[1]`). Budget `max(trend, 10) + 1` bars of warm-up.

---

## 🔴 Boundary ties: three bars where Pine and Python are BOTH right

The parity run is green with **three mismatching flags in 302,070 comparisons**, and all three are
the same thing. Several rules compare two quantities that come out **exactly equal in decimal** on
real price data, and in every case the tie is what decides the answer:

| bar | rule | comparison | decimal |
|---|---|---|---|
| 2,522 | `doji` | `\|o-c\| <= (h-l)*dojiSize` | **0.26 vs 0.26** |
| 6,844 | `invHammer` | `h-l > 3*\|o-c\|` | **3.96 vs 3.96** |
| 16,764 | `shootingStar` | `h-max(o,c) >= 3*\|o-c\|` | **5.43 vs 5.43** |

Neither side of any of those is representable in binary floating point, so the two implementations
accumulate different last-bit error and land on opposite sides of a rule they are both computing
correctly. Confirmed with `Decimal`, not inferred. It is the same class of thing `engines/vwap/`
already carries a 1e-6 relative tolerance for.

⚠ **It is NOT handled with a tolerance, and that is the design decision worth keeping.** A 0/1 flag
has no "close enough" — a tolerance on the flag would swallow real logic bugs along with these.
`compare_candles.py` instead **CLASSIFIES** each mismatch: it re-runs the rule with every price in
the bar's own history window nudged by ±1e-6, one at a time, and asks whether the answer flips. A
decision a 1e-6 nudge can flip was on the line; a real rule difference is robust to it, because
prices tick in whole cents and every threshold here is built from them.

✅ **The classifier was proven non-vacuous rather than trusted**: two fabricated flag flips injected
at ordinary bars came back as **REAL** with exit 1, while the three genuine ties stayed classified.
⚠ **Ties are printed on a PASS as well as a fail** — burying them behind a green exit code is how a
fact about the export stops being one — and `--strict-ties` fails on them if a future change needs
that. ⚠ **A mismatch that cannot be classified (too little history to replay) counts as REAL**, never
as a tie: the reassuring answer must not be the default.

⚠ **Consequence for a consumer, and it is small but real: on a handful of bars per 20,000 the engine
and the chart will disagree about one flag.** That is unavoidable without reimplementing Pine's exact
float arithmetic, and it is confined to rules whose decision was already a coin-flip. Do not build
anything that depends on a single tie-bar agreeing.

🔴 **AND THE FLOAT TIES ARE THE SMALL HALF — THE FEED IS THE BIG ONE, MEASURED 2026-08-09.** The
ties above are a handful per 20,000 because the harness feeds both sides the SAME prices. A consumer
does not: the command-center chart replays this engine over MT5 cache bars while the reader compares
it against the indicator running on TradingView bars. **Same broker, same symbol, 6 cents apart in
the median close and further within a bar — and 15.9% of every mark disagrees** (600 missed, 515
extra, over 20,053 bars; bearish engulfing 150 of 914). **Read the "handful per 20,000" line above
as a statement about the GATE, never about what a reader will see.** Before promising that a
consumer matches the indicator, ask which tape each one is reading.

### The one named assumption

`ta.lowest(10)[1]` is taken to return `na` — and therefore no belt — until ten bars exist. It sits
inside any sane warm-up so it cannot affect a real parity run, and it is written down because an
assumption nobody wrote down is one nobody checks (this repo's 2026-08-06 lesson about the "~35 days
of 1m" guess, which cost three weeks).

---

## 🔴 The export twin took THREE attempts, and the fix was to stop copying the drawing

`indicators/candle_sticks_export.pine` was refused by TradingView with **RE10140** twice — a runtime
error that is **not in TradingView's published error list at all**, raised with a clean compile and
**no calculation spinner**, i.e. at INITIALIZATION before a bar was processed.

- **Attempt 1** — the parent verbatim + `overlay = false, max_bars_back = 500` on line 11. Both extras
  were mine and both were removed. `max_bars_back` guarded a hazard that does not exist (the
  `open[trend]` offset is on the BUILT-IN `open` series, which carries ~10,000 bars natively) while
  allocating that buffer for **every** series in the script; `overlay = false` was pure cosmetics.
- **Attempt 2** — the parent verbatim, title-only diff. **Still RE10140.** So the deviations were
  never the whole story, and removing them was necessary rather than sufficient.
- **Attempt 3** — the rules only, **all drawing stripped.** 15 `plotshape` calls carrying multi-line
  `text` and 15 `alertcondition` calls are gone; 18 `plot()` columns remain.

⚠ **What attempt 2 ruled out is the useful part.** `fvg_export.pine` runs **40** plot columns on the
same chart without complaint, so the column COUNT was never it. Measured across the sibling harnesses,
this file was the outlier in exactly one way: **`plotshape` 15 / `alertcondition` 15 against 0 / 0 for
every other export in the repo.** It was the only harness that DREW, on a chart already carrying
fifteen scripts.

⚠ **That is the convention this file broke, and the reason it exists is worth restating: an export
harness emits COLUMNS, and nobody ever looks at its chart.** `fvg_export.pine`'s own header says it —
"with ALL drawing removed (no boxes, no directional-visibility filter — those are visuals)". Keeping
the parent's fifteen shapes bought byte-identity, which is a verification convenience, and paid for it
in the only currency the script actually has at runtime.

### 🔴 The verification contract changed with it — `diff` against the parent is now meaningless

This is no longer a byte-identical twin, so the old `head -84 … | diff` check would pass vacuously.
What must hold instead is that the **sixteen logic lines are byte-identical**, and that is one command.
**Run it after any edit to either file:**

```sh
R='^(doji|bearHarami|bullHarami|bearEng|bullEng|piercing|lower|bullBelt|bullKick|bearKick|hangingMan|eveningStar|morningStar|shootingStar|hammer|invHammer) ='
diff <(grep -E "$R" indicators/candle_sticks_export.pine) <(grep -E "$R" indicators/candle_sticks.pine)
```

It must print nothing. **A harness whose rules have drifted from the file it mirrors reports a correct
engine as RED** — `fvg_export.pine` did exactly that on 2026-08-03 with a stale cap rule.

**The standing lesson is about what a copy is for. Byte-identity is a way of PROVING a harness matches
its source; it is not the harness's job, and here it dragged in fifteen drawing calls that had no
reader and — on a loaded chart — a real cost. When a convention exists across every sibling and you
are about to be the exception, the burden is on the exception.**

### The `trend` finding itself, restated honestly

`indicators/candle_sticks.pine` declares `trend = input.int(5, minval = 1, title = "Trend in Bars")`
with **no `maxval`**, and ten rules then read `open[trend]`. ⚠ **This is a much weaker concern than
the first write-up of it claimed**, and the correction matters: `open` is a built-in series with a
large native buffer, so an ordinary value is safe and it would take a `trend` in the thousands to
reach the limit. It is a missing bound worth mentioning before anyone types a big number into that
box — it is **not** the `execVwapSlopeBars` emergency it was first written up as, and treating it as
one is what put the broken `max_bars_back` in the export.

**It is not fixed in the Pine.** That file is a third-party indicator Aaron dropped in; changing its
input declaration is his call, and it does not affect this engine (Python sizes its deque from the
value, so any `trend` works here).

---

## Using it as confluence

```python
from candlesticks import CandlestickEngine, BULLISH

cs = CandlestickEngine()                       # trend=5, doji_size=0.05 — the Pine defaults
ev = cs.update(bar.index, bar.open, bar.high, bar.low, bar.close)

ev.has("bullish_engulfing")                    # this bar
ev.matching(keys=cfg.patterns, direction=BULLISH)   # the confluence read
cs.bars_since("bullish_engulfing")             # 0 = this bar, None = NEVER fired
```

A pattern is a property of ONE bar: it fires and it is over. There is no live list, nothing is
mitigated and nothing expires — deliberately, because a pattern is not a level with a lifecycle. A
window ("within the last 3 bars") is a question about history, so it is asked of the ENGINE
(`bars_since`), never of a bar's events.

⚠ **`bars_since` returns `None` for "never fired", not a large integer.** *Never* and *a long time
ago* are different answers and a sentinel would let a confluence window silently treat one as the
other. Asking a DISABLED pattern raises instead of answering `None`, for the same reason: *not
evaluated* and *did not happen* are different facts and the reassuring one is wrong.

⚠ **An unknown pattern key RAISES** (`spec_for`), it does not match nothing. A config naming
`"bullish_engulphing"` would otherwise switch a confluence silently off, which reads exactly like a
filter that is on and never triggering — this repo's most-repeated failure shape.

⚠ **`patterns=[...]` narrows what is EVALUATED, never what a rule MEANS.** It is also a real cost
lever: the full fifteen replay 186,366 bars in **10.2s** (18k bars/s) and a two-pattern subset in
**1.3s**. Narrow it in a sweep; the parity harness always runs all fifteen.

---

## Rules

**Do**
- Keep every rule byte-faithful to `indicators/candle_sticks.pine`. It is the source of truth. If the
  Pine looks wrong, the fix goes in the Pine and flows here — never the other way round.
- Add a pattern to `PATTERNS` (types.py), a detector in `engine.py`, a `plot()` in
  `candle_sticks_export.pine` and a row in `compare_candles.py`'s `PATTERN_COLUMNS` **in one commit**.
  Two import-time guards and one harness guard already refuse a half-done job — a pattern with no
  detector, a detector with no registry row, and a pattern with no export column are each a rule the
  gate would silently never check.
- Verify the export's sixteen logic lines against the parent with the `grep | diff` command above
  after ANY edit to either file. It is the only check that still means anything now the export is not
  a byte copy, and a drifted harness reports a correct engine as red.
- Keep the export free of drawing. No `plotshape`, no `alertcondition`, no colour inputs — see the
  RE10140 record above, and every sibling harness in `indicators/`.
- Read `compare_candles.py`'s per-pattern HIT COUNTS before believing its exit code. A green run over
  a window where a pattern never fired says nothing about that pattern, and the tool names them.

**Never do**
- Never build a second candlestick-pattern detector anywhere. This is the canonical one.
- Never re-declare Hammer / Inverted Hammer / Doji as bullish or bearish inside this engine. The
  source draws them neutral and gives them no trend context; a consumer states its own reading.
- Never let a missing history bar become `0.0`. See the `na` rule above — it is the difference
  between a rule that cannot fire yet and a rule that always fires.
- Never soften a boundary tie into a tolerance on the flag. A 0/1 column has no "close enough", and
  a tolerance there would swallow real rule differences with the ties. Classify, report, and let the
  reader see the count. ⚠ **AND THE SAME REFUSAL COVERS THE READER, NOT JUST THE
  HARNESS — it was tested on 2026-08-09 and held.** The chart layer's first consumer reported four
  candles that "are obviously bearish engulfings" and were not marked. MEASURED clause by clause
  against `candle_sticks.pine:32`, **three fail `open >= close[1]` by $0.05, $0.06 and $0.01**, and
  the fourth passes the engulf and fails `open[trend] < open`. **On a gapless intraday feed a red
  bar opens within PENNIES of the prior close, so a full-body engulf is decided at the cent** — this
  is the ordinary case here, not an edge one, and a "just a few cents" tolerance would quietly
  redefine the rule for the whole family. The honest answer is the clause breakdown; the indicator
  the reader is comparing against does not draw those candles either.
  ✅ **AND IT IS NOW MEASURED RATHER THAN ARGUED (2026-08-09).** The reader came back with four more
  candles, two of which his indicator DOES draw, so the epsilon was swept against his own `px_*`
  flags over 20,053 bars: engulfings miss/invent go **243 / 190 at epsilon 0**, 143 / 664 at $0.02,
  95 / 822 at $0.05, 65 / 900 at $0.10. **Two cents recovers 100 marks and manufactures 474 — zero
  is the minimum-disagreement setting by a factor of two.** The mechanism is the same sentence read
  forward: because the open sits within a cent or two of the prior close as the ORDINARY case, slack
  does not nudge the rule, it floods it.
  ⚠ **The two genuine misses were caused by the FEED, not by the rule, and no engine change can
  reach them** — the chart draws MT5 bars, the indicator runs on TradingView bars, the two sit 6
  cents apart with larger intra-bar variation, and **15.9% of all marks disagree because of it.**
  A constant offset would flip nothing (every clause compares two prices); it is the variation that
  bites. See `command-center/backend/CLAUDE.md` → *Candlestick reversals*.
- Never treat an unclassifiable mismatch as a tie. Not enough history to replay the bar means the
  question was not answered, and "not answered" must fail, not pass.
