# Notes — BOS strategy — build, defaults and the false-break defect

The build of `bos_strategy.pine` off the shared engine block, its default flips vs SOS Fade, the timeframe-split FVG floor it shares with SOS Fade, and the false-break-counted-as-a-strategy defect and its sign bug. Moved VERBATIM out of `indicators/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## 2026-08-13 — 🟢 A FALSE BREAK BECAME A STRATEGY, AND THE TOOL THAT COUNTED IT GOT THE SHORT SIDE'S SIGN WRONG

Aaron, off four of his own chart screenshots: a bullish external trend on the 15m, then *"a bearish
shift of structure — a false break, a structural liquidity grab"*, then on the 5m the internal
structure turning bearish and back bullish to **realign**, and the trade taken there — *"immediately
at the internal shift"* — with the stop behind the last bearish internal shift and the target the
pre-deviation external high. It **front-runs** the external bullish SOS that later confirms it.

Built end to end in one pass: a counting tool, a spec, a Python package and the Pine. Full record in
`strategies/python/realign/CLAUDE.md` and `docs/REALIGN_SPEC.md`; the parts that generalise
past this strategy are below.

🔴 **"INTERNAL STRUCTURE" HAS TWO DEFENSIBLE READINGS AND THEY GIVE OPPOSITE ANSWERS.** The engine
publishes `ExternalEvents` (the swing structure a chart draws) and `InternalEvents` (the
sub-structure within it) per frame. Aaron's *"internal structure on the 5m"* is the **5m's EXTERNAL
stream** — internal *relative to the 15m* — and not the engine's `InternalEvents`, which is one
level below what he is pointing at. That is not pedantry: **`InternalEvents` resets on any external
break of its own frame, and the false break IS such an event, so on 81% of candidates that stream
was blank at the moment the setup armed.** Reading it there measures a different, mostly-empty
setup rather than a weaker version of this one.

🔴 **THE TRIGGER SCAN AND THE REPLAY DISAGREED IN SIGN, AND THE SCAN IS NOT BROKEN.**
`backtest/tools/internal_realign_scan.py` scored shorts-on-`internal` at **+9.6% over a matched
control (+2.1σ)** — its strongest row. A real replay through the exit ladder gives **−13.26R against
+20.22R** on the other stream. The scan scores every setup **independently, at a fixed target, with
no exit ladder, no staged stop and no position slot**, and that short edge lived entirely in the tail
(+0.1σ at 1R, +2.1σ at 4R) — **the real ladder banks at the structural target, so the edge it
measured is one the strategy never collects.** ⚠ **Take counts from a trigger scan; take the
direction of anything exit-sensitive from a replay.**

🔴 **THIS ENTRY ORIGINALLY SAID "THE SEQUENCE AARON DREW IS THE WORST OF THE THREE FILTERS". IT IS
NOT, AND THE CORRECTION IS THE SAME LESSON AS THE PARAGRAPH ABOVE IT.** That claim was the trigger
scan's, written down one paragraph after the warning never to let the scan decide an exit-sensitive
question. **Replayed over 467,352 M5 bars, FREE, the strict sequence is the BEST of the three on
average R (+0.294 vs +0.279), profit factor (1.977 vs 1.658) and drawdown (4.15R vs 12.15R) at
once.** It loses the ranking only once **costs are charged** — it gives up **40% of its average R**
against the loose rule's **21%**, and the order flips. The loose rule still ships, on the two
figures that survive charging: 5x the total R (+35.81R vs +7.33R) and more R per unit of drawdown
(2.31 vs 1.66). ⚠ **The mechanism is a hypothesis, not a finding** — probably tighter stops paying a
fixed spread — and it is one replay away. **Twice now this scan's ordering has failed to survive a
replay, the first time in SIGN; treat its rankings as trigger quality and nothing else.**

⚠ **The lower frame was swept rather than assumed: 5m carries the edge, 3m is break-even, 1m is
negative and its stops sit inside gold's spread floor.** A single-engine M15 run gives **9 setups in
5.6 years** — the two-frame build is not a refinement, it is the difference between having a
strategy to measure and not having one.

⚠ **The strategy is SINGLE-FRAME on purpose and builds its own 15m bars** (`htf.py`, and
`request.security` on the Pine side), because **`backtest.optimizer.run_sweep` refuses dual-frame
strategies** — a `run_dual` build is locked out of the optimizer, every sweep and the stress test.
The correctness condition is that an HTF bar is published only once its last chart bar has CLOSED;
publishing a forming one is lookahead of the flattering kind and nothing errors.

✅ **Cross-checked rather than asserted: Python 162 trades / +35.81R charged (+45.14R free),
TradingView 143 / +41.35% / PF 1.617. Total R agrees within noise.** ✅ **THE WIN-RATE DIFFERENCE IS
NOW LARGELY CLOSED, AND ITS CAUSE WAS THE COMPARISON RATHER THAN EITHER IMPLEMENTATION** — this
entry reported "30.77% vs 44%" and blamed scratch classification, but **44% is the FREE book while
the R beside it is the CHARGED one.** The charged book wins **33.3%** against the tester's 30.77%.
Costs move this strategy's win rate 11 points because it enters at MARKET and pays the spread both
ways, unlike every other bot here. 🔴 **The DRAWDOWN difference is still open** (Pine ≈19.5R against
15.52R; the candidate is TradingView filling a gapped stop at the next OPEN where the bar model
fills at the stop price, which would make Python optimistic) — **a signature is not a measurement,
and the parity gate is what settles it.** ⚠ **A charged figure of +37.67R quoted on the first pass
does NOT reproduce and the reason is not known**: the free figure reproduces to the cent, `32b633f`
was checked and touched no execution code, and **the original run's command was never recorded**,
which is the only reason it cannot be settled.

⚠ **NOTHING HERE IS PARITY-VALIDATED.** No export twin, no real CSV, no `compare_realign.py` —
stages 3, 4 and 6 of `docs/STRATEGY_WORKFLOW.md` are outstanding, and stage 4 is the one only a
human can do.

**The standing lesson is about what a counting tool can and cannot answer: `internal_realign_scan.py`
did its job perfectly — it found the pattern, counted it on both sides and compared it against a
control — and it was still wrong about which way to trade one of them, because scoring a trigger at
a fixed target and running it through a staged exit ladder are different experiments. A prior over
triggers is evidence that a pattern carries information. It is not evidence about a strategy, and
when the two disagree the replay wins.**

---

## 2026-08-07 — 🟢 `bos_strategy.pine` COMPILES, AND ITS DEFAULTS MOVED OFF THE SPEC BECAUSE THE FVG ENTRY IS THE LOSING HALF

Aaron pasted the file, it compiled (the `CE10117` risk from putting VWAP back did not materialise),
and he asked for the parameters to be optimized into something profitable. **That exact request had
already been run and failed** — `strategies/python/bos/` swept **82 configurations on 2026-07-31
and found profit factor below 1.0 in every one**, then was deleted on 2026-08-04 as an unvalidated
port. So the grid was not re-searched. What was asked instead is what had CHANGED, and one thing
had: the session VWAP filter added the day before, which was in none of those runs.

⚠ **That is the reusable move, not the result: before optimizing anything in this repo, find out
whether it has been optimized already and what the answer was.** The old log survives at `1946f8b^`
and it reframed the whole task — Run 3 had concluded *"every input the strategy has describes the
SETUP... what separated winners from losers was the state of the MARKET, which no existing input
can express."* VWAP is exactly that missing axis, which is why it was worth one more sweep.

✅ **The result — 564 configurations, 186,384 true-M15 bars, scored +2R-before-−1R against a control
matched on direction AND stop distance:** a **fib 0.786 entry with the leg-origin stop and VWAP on**
measures **+14.5% over control (+4.1σ, n=201, PF 1.76, positive in 9 of 9 years)**, where **what
shipped before measured +2.8% at 1.7σ — not distinguishable from random.**

🔴 **The headline is that `bosUseFvg` now defaults OFF, and the FVG entry was the SPEC'S CORE IDEA.**
Entry depth turned out to be a bigger lever than the filter. **Two independent measurements, seven
days and two implementations apart, agree**: the deleted Python sweep found the FVG entry was *"98
trades for −15.1R with no tail at all"* while the rest of the book broke even, and this run found a
plain deep fib beats it four-fold. **The gap decides WHERE the limit rests, and it rests too shallow
for a continuation trade.** ⚠ It does NOT vindicate Run 1's proposed fix, which was to go SHALLOWER
still (the Sniper-Zone pocket) — Run 2 had already withdrawn that, and the measured answer is deeper.

🔴 **THE TOP ROW OF THE SWEEP WAS DISCARDED AND THAT IS THE PART WORTH CARRYING.** Ranked on
expectancy alone the winner was a 0.786 entry against an **0.886 stop at +0.563R**. Its **median stop
is $0.74**, so at a $0.22 spread **30% of R is gone before the trade starts**, and the deepest tenth
rest stops under **$0.31** — untradeable. The leg-origin stop's median is $1.73 (12.7% of R). **Net
of the spread the ranking INVERTS**, +0.265R against +0.276R. ⚠ **Standing rule: rank on expectancy
NET of the spread, never on expectancy** — on this strategy the two orderings disagree at the top and
the gross one picks the configuration you cannot trade. It is also the collapsing-stop hazard the SOS Fade
file already records, arriving by a third route: there it inflated sum-R through position sizing,
here it inflates win rate through an unpayable stop.

⚠ **The strongest evidence is a direction check, not a significance figure: shorts +17.7% beat longs
+12.3%.** Gold tripled across this window, so a drift artefact shows up as longs carrying everything
— and Run 3 had flagged its own longs-vs-shorts slice as confounded and unusable for that reason.
This one points the other way, which is what a real effect looks like on a trending instrument.

⚠ **VWAP was tested PAIRED across the whole grid rather than read off the winners: 276 matched
on/off pairs, better in 210, median ΔexpR +0.054.** A filter judged only from the top of a sorted
list is judged on the rows it was selected into.

⚠ **564 configurations is real multiple-comparison exposure and is stated as such in the log.** The
defences are the 9-of-9 years, a half-split on time (the test that killed Run 3's volatility rule and
Run 4's regime labels), the direction check, the smooth degradation across every switch, and the
paired VWAP test. Decent; not proof.

⚠ **THE MEASUREMENT IS A SKELETON, NOT THE STRATEGY.** `backtest/tools/trigger_edge.py` drives the
canonical engines with a plain fib limit and a flat +2R/−1R score. It models none of the file's
30/30/20 TP ladder, staged stop or runner. **Direction transfers, magnitude does not** — `+0.276R per
trade` must never be quoted as this strategy's expectancy. ⚠ **Aaron confirmed the Strategy Tester
agrees, DIRECTIONALLY ONLY: the three numbers were not recorded, so no figure in this repo describes
a real TradingView run at these settings.** ⚠ **And there is still no `compare_bos.py`** — the last
port was deleted for exactly that gap.

Full record, grid and caveats: `docs/BOS_OPTIMIZATION.md` → Run 5. ⚠ **`docs/BOS_SPEC.md`
§4/§5 now describe the ORIGINAL DESIGN rather than the shipped behaviour**, and its Status block says
so — a spec that silently stops matching the file is worse than no spec.

**The standing lesson is about what "optimize the parameters" can and cannot buy.** The parameter
search had already been run exhaustively and lost; what changed the answer was adding a variable that
was not in the parameter set at all. ⚠ **And the second half matters as much: the winning row of a
564-config sort was the one to throw away.** A sweep hands you the configuration that scored best
under the metric you happened to write down — here that metric ignored the spread, and the spread is
30% of the winner's R. **Before believing a sweep's top row, price it.**

---

## 2026-07-31 — `bos_strategy.pine` defaults now ENCODE the spec, not the bare baseline

**Aaron's spec, stated 2026-07-31:** SOS opens the regime → a BOS with **clean displacement** → that
break **leaves an FVG** → price retraces into **0.5-0.886** and taps the gap. The **Sniper Zone is
optional** (it may price a leg that had no qualifying gap; it is never waited for). The **daily does
NOT have to agree** — no HTF bias gate.

**Four defaults flipped to carry it:** `bosUseFvg` OFF→**ON**, `execReqFVG` OFF→**ON**,
`bosMinDispAtr` 0.0→**0.5**, and `execConfSZ2` stays ON (that is what makes the zone an optional
stand-in rather than a requirement). `execHtfWeekly`/`execHtfDaily` stay **"Ignore"** by explicit
decision, now written on the daily tooltip so nobody "fixes" it later.

**Why the old defaults were not the target.** The file shipped with every filter and every entry
confirmation OFF so the run measured the raw BOS idea. That is a MEASUREMENT baseline. The standing
direction for this strategy is **quality over quantity — the confluences ARE the quality lever**, and
frequency comes from stacking SOS Fade, B-LEG and this one on one account, never from loosening this one.
Reading the old defaults as "keep it loose, it takes more trades" inverts the intent. The filters that
are still open questions (F1/F3/F4/F5/F6/F8) stay OFF, to be turned on one at a time and judged on
expectancy and drawdown — **not on how many trades survive.**

**⚠ 0.5 ATR is the spec expressed as a number, NOT a measured optimum.** No run has been taken at any
displacement value. Sweep 0.25 / 0.5 / 1.0 and set it from results. Same warning on its tooltip.

**⚠ EVERY NUMBER IN THIS FILE'S HEADER DESCRIBES THE OLD DEFAULTS.** The 365-day / 13-trade / −2.65%
figure and the F4 design-conflict finding were measured on the previous configuration and say nothing
about this one. The header keeps them, labelled as the previous baseline.

**No logic changed — inputs, defaults and comments only.** `bosEntryFib` is now INERT at the shipped
defaults (with a gap required, the plain-fib fallback at the bottom of the entry ladder is never
reached); its tooltip says so. The entry ZONE is not set by that dropdown — the gap edge is clamped to
0.5 at the shallow end and a gap outside 0.5-0.886 is refused, which is where the band comes from.
**Not compiled on TradingView yet** (no local Pine compiler), and there is still no export Pine, no
`compare_bos.py` and no Python port — so nothing here is parity-checked.

---

## 2026-07-29 — the FVG floor is now SPLIT BY TIMEFRAME (SOS Fade, its export, and BOS)

**The bug Aaron found.** `mpc_jarvis.pine` draws fair value gaps on a 5m chart
that `sos_fade_strategy.pine` does not. Cause: the assistant's minimum-gap floor is
timeframe-aware and the strategy's was one flat number.

```pine
// mpc_jarvis.pine:149-151
float fvgThreshLTF = 0.0
float fvgThreshHTF = 0.04
float fvgThreshPct = timeframe.in_seconds() < 900 ? fvgThreshLTF : fvgThreshHTF
```

The strategy had `input.float(0.1, "FVG Min Gap (% of price)")` — 0.1% at every
timeframe. **A %-of-price floor does not scale down.** 0.1% of gold at $3,300 is
$3.30 of gap, which is wider than most WHOLE 5m bars, so a single flat floor
silently erased nearly every low-timeframe gap. A second, smaller difference
stacked on it: the assistant has `fvgRequireClose = false` everywhere, while the
strategy HARDCODED the middle-bar close-cleared test on.

**What landed.** Both are now split at the same 900-second boundary, in
`sos_fade_strategy.pine`, `sos_fade_strategy_export.pine` and `bos_strategy.pine`:

| | below 15m | 15m and above |
|---|---|---|
| min gap | `fvgThreshLTF`, default **0.0** | `fvgThreshHTF`, default **0.1** |
| middle-bar close test | forced **off** | `fvgReqCloseHTF`, default **on** |

**15m and above is bit-identical to before, deliberately.** The HTF floor stays
0.1 and is NOT set to the assistant's 0.04, and the close test stays on. SOS Fade is
traded on 15m, so its baseline, its 188-trade history and the `sos_fade`
parity pin (`EngineConfig.fvg_require_close = True`) must not move. Matching the
assistant at 15m too is a one-number change if it is ever wanted — but it is a
different decision, with a re-validation attached, and it was not made here.

**Consequence to carry.** These are new trade-affecting inputs and
`sos_fade_strategy_export.pine` has no `cfg_*` column for either. At their defaults on
15m that costs parity nothing (behaviour is unchanged), but **a parity run taken
on a sub-15m chart, or with either input tuned, is meaningless until the columns
land here and in `compare_strategy.py`.** Same trap as `execRunnerTrail` in the
2026-07-26 entry: a default that changes behaviour is as dangerous as a new
input, and it hides better.

**NOT applied to `b_leg_strategy.pine` / `b_leg_strategy_export.pine`.**
They carry the identical FVG block and are now the only strategy files without
the split. The standing "engine changes flow line-for-line to the fork" rule says
they should get it; it was left out only because the request scoped SOS Fade and BOS.

**Pre-existing drift found while checking this, NOT caused by it.**
`sos_fade_strategy_export.pine` is missing `execMinStopMode` / `execMinStopVal`
entirely — the min-stop lever landed in the parent (`7603444`) and never reached
the export. That breaks the export's own "the title is the ONLY difference" rule.
A parity run replays the bot with a floor the export cannot describe; harmless
while the mode is "Off" (the default), wrong the moment it is not.

---

## 2026-07-29 — `bos_strategy.pine`, the third strategy off the shared engine

**New file `strategies/tradingview/bos_strategy.pine`** (3875 lines), built to `docs/BOS_SPEC.md`. It
trades the CONTINUATION: an SOS sets a regime, and every BOS after it in that direction is a fresh
leg whose retrace is bought/sold. SOS Fade fades the shift; this rides what the shift started.

**How it was assembled.** Engine block = **lines 1-3028 of `sos_fade_strategy.pine`, byte-identical**
(everything through the liquidity `recentSSL`/`recentBSL` block), then the watermark, then a new
execution layer. **Not copied:** the SOS Fade SEQUENCE tracker, the B-LEG tracker, the missed-setup callout
and its `MissW` machinery — nothing here reads them, and the compile-token budget in this family has
already hit CE10117 and CE10295 twice. Net effect vs the parent: ~510 lines of tracker out, ~250 of
execution in. Regenerate with `head -3028 sos_fade_strategy.pine`, the parent's watermark block, then this
file's execution layer.

**Two default flips vs the SOS Fade, both named in the spec:** `execConfSZ` OFF→**ON** (the Sniper Zone is
entry method 3 here) and `execFvg50` OFF→**ON**. Note `execConfSZ` also gates `_snTrack`, and
`_snBullBOS`/`_snBearBOS` sit behind `showFibo` — so **"Show External Fib" is still trade-critical**
in this file even though the fib LEVELS are no longer read off it (see below).

**The levels are computed, not read.** The entry band, stop and targets come from `f_lvl(ext, org, v)`
over the anchor leg's own extreme/origin — identical arithmetic to the engine's `fiboP*`, just
anchored per-setup. `bosFibAnchor` picks the EXPANSION leg (default — `fibo_ash`/`fibo_asl`, the drawn
External fib's own anchors, so the band moves until the pullback confirms) or the frozen BREAK leg
(`bos_high`/`bos_low`). This is what makes the "Break leg" option possible at all; the SOS Fade could only
ever price off the one drawn fib.

**Three deviations from the spec, all flagged in the file header and in the spec's new §10a.** The
important one: **`fibo7Touched` is re-implemented per-anchor.** The engine's latch is keyed to the fib
ORIGIN, which does not change across a run of breaks, so break #1's round trip would have killed
breaks #2 and #3 on their arm bar — every continuation after the first would be untradeable. The Pine
tracks the anchor's own 0.5 tap and its own return to 0.0 instead. The other two: the divergence
CLOSE fires on a confirmed divergence only (not extreme RSI — that is the normal state of a healthy
long, and closing on it flattens the runner on every winner), and `execMinStopMode`/`execMinStopVal`
are carried over from the SOS Fade though §8 does not list them (default Off, so the baseline is unmoved).

**Not yet compiled on TradingView and not yet backtested.** There is no local Pine compiler; the file
is statically checked only (no identifier collisions with the engine block, every referenced engine
symbol present, no duplicate declarations or input titles). **No number in this repo describes this
strategy yet** — §10 steps 2-4 (baseline + the F1→F4→SL-model sweeps, the export Pine +
`compare_bos.py`, the Python port under `strategies/python/bos/`) are all open.

**Standing rule, same as the B-LEG fork:** any change to the engine block flows in line-for-line from
`sos_fade_strategy.pine`; any BOS execution change flows to the Python port once it exists.
