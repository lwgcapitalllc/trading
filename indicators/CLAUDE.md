# CLAUDE.md — indicators/

**Purpose:** The Pine Script INDICATOR sources — the charting engines the 13 canonical Python
engines were ported from, the from-scratch `smc_engine_v2` rebuild, and the instrumented `_export`
twins that are half of every ENGINE parity gate.
🔴 **The `strategy()` half LEFT ON 2026-09-02 AND IS NOT IN THIS TREE ANY MORE.** Those files are
strategy source for the TradingView runner platform, so they now sit beside the MT5, NinjaTrader
and Python strategies at [`strategies/tradingview/`](../strategies/tradingview/CLAUDE.md) — the
numbered input-panel contract, the trade annotations, the colour palette and the per-family prose
rule all travelled with them, along with `docs/` and `tools/`. Why, and what else moved:
`docs/TRADINGVIEW_STRATEGY_MOVE_PLAN.md`.
**Scope:** This file ROUTES and keeps the dated build narrative. The RULES live in
[`engines/CLAUDE.md`](engines/CLAUDE.md), next to the code they describe. It does not cover any
Python port — those live under `engines/` and `strategies/python/`, each owning its own CLAUDE.md.
**Last reviewed:** 2026-09-02 — the `strategy()` half moved out to `strategies/tradingview/`.
2026-08-15: `tools/check_active_order.py` landed (see above). 2026-08-13: the 28 `.pine` files were
split into `strategies/` and `engines/` on their declaration, and the rules that applied to only
one half moved into that half's CLAUDE.md.

## The split — where a `.pine` file goes, and the one thing that decides it

**The Pine DECLARATION decides it, not the filename.** A file declaring `indicator()` goes in
`engines/`, here; a file declaring `strategy(` goes in `strategies/tradingview/` and is NOT in
this tree at all. Nothing else is consulted, which is the point — `structure_engine.pine` reads
like a strategy component and is an indicator. ⚠ **`m15_playbook.pine` / `m15_playbook_strategy.pine` used to be the
textbook example of this — a near-identical pair split across both folders on the declaration
alone. On 2026-08-15 the indicator was DELETED and the strategy renamed to
`smc_session_sweep_strategy.pine`**; the note that says why is in
[`engines/CLAUDE.md`](engines/CLAUDE.md). Several paragraphs below still name the deleted file in
the present tense, deliberately — each records a decision applied across many files that is still
binding on the survivors.

| folder | declaration | count | owns |
|---|---|---|---|
| [`strategies/tradingview/`](../strategies/tradingview/CLAUDE.md) — **not here since 2026-09-02** | `strategy(` | 16 | the numbered input-panel contract, the trade annotations, the colour palette, and the `docs/<family>.md` prose rule |
| [`engines/`](engines/CLAUDE.md) | `indicator()` | 17 | the `mpc_jarvis` extraction track, the `smc_engine_v2` rebuild and its detection rules, and the third-party reference files |

⚠ **Count both with `ls`, never off this table** — the `strategy(` column read 12 for weeks while
there were 16, and the row above is the third place in this repo that number has been wrong.

⚠ **Ask the folder, then read that folder's CLAUDE.md — not this one.** A fact lives in exactly
ONE CLAUDE.md, the one next to the code. This file keeping its own copy of the panel contract is
how three files in this repo came to disagree about whether a bot was live.

⚠ **`CLAUDE.md` is the only file left at this level, and that is structural rather than tidy** —
the commit hook finds a changed file's OWNING doc by walking up from its folder, so this file has
to sit above `engines/` to be the thing it falls back to. ⚠ **It kept that job when the strategy
half left**, because `docs/` and `tools/` still sit here and both need an owner.

## `tools/` — the panel checks, run by hand

**`check_active_order.py` (2026-08-15).** An input's `active =` may only name inputs declared
ABOVE it; Pine resolves top-down and a violation is `CE10272`, which **only appears on the paste**.
`bos_strategy.pine` shipped exactly that in the 2026-08-12 panel reorder, and its export twin
carried the same defect because a twin is a copy. Run it after ANY panel edit:

```bash
python3 indicators/tools/check_active_order.py strategies/tradingview/*.pine
```

**All FOURTEEN gated strategy files pass, re-run 2026-09-02 at the new paths** (it read twelve on 2026-08-15 and two more have landed since). ⚠ **The two files under `strategies/tradingview/research/` are deliberately outside that glob** — they carry no numbered panel, so the check has nothing to say about them. ⚠ **Its first two versions each reported four
false failures and the shape of that is the warning, not a footnote.** Version one ran the
`active =` expression past its own argument and swallowed the next one, so `step = 0.05` read as a
dependency on an identifier called `step` — which a local 4,900 lines away happened to be. Version
two stopped at the argument boundary and still failed, because `active = execRunnerTrail != "Fixed
step"` puts the word inside a STRING. **A checker that flags the four biggest files while passing
the small ones is one you conclude is broken and stop running**, and version two would have been
"right" for entirely the wrong reason since those files really were clean. Strings are stripped
before identifiers are extracted now. ✅ **Watched RED by mutation rather than trusted** — swapping
an input with its own `active =` dependant in a throwaway copy reddens exactly that pair and
nothing else. ⚠ **It is a PROMPT, not enforcement**: nothing runs it for you, and it reads Pine
with regular expressions rather than parsing it, so a novel formatting of `active =` could slip
past. It is a cheap check for a defect that otherwise costs a round trip to TradingView.

**`check_scope.py` (2026-08-25).** Asserts that every `_`-prefixed identifier read inside a
function or method body is a parameter of it or assigned in it. Pine calls the failure `CE10272`
and **it only appears on the paste**, so a file can look finished in the repo for days.

```bash
python3 indicators/tools/check_scope.py strategies/tradingview/*.pine
```

**All thirteen strategy files pass as of 2026-08-25.** It exists because
`extreme_leg_strategy.pine` builds its higher-timeframe engine by GENERATING a second copy of
the chart-frame one, swapping the bar globals for passed-in values — and two helper methods got
the swap without getting the parameter. ⚠ **It is deliberately narrow: the underscore prefix is
this repo's convention for a value handed IN to a derived engine instance, so the check covers the
whole class that generator can produce and nothing else.** Finding an undeclared identifier with
no underscore needs Pine's own builtin list, which we do not have — **so its silence is one
specific question answered, not a clean bill of health.** ✅ Watched RED by mutation rather than
trusted, on the exact line the first paste failed at. ⚠ **It is a PROMPT, not enforcement**, same
as its neighbour.

🔴 **`check_flat_reset.py` (2026-08-25). This one is here because a strategy blew an account on its
first run.** Orders are processed on the bar's close, which happens AFTER the script has finished
running for that bar — so on the bar an entry is placed, `strategy.position_size` still reads flat
everywhere below it. `extreme_leg_strategy.pine` cleared its stop and target under a bare flat
test, which therefore fired on the entry bar and wiped both three lines after the entry set them.
**The bracket then went out empty, and because a new entry needs a flat book the position could
never close: one unprotected trade held to the end of the chart.** The check flags any value an
entry block sets and a bare flat test clears.

```bash
python3 indicators/tools/check_flat_reset.py strategies/tradingview/*.pine
```

**All thirteen strategy files pass as of 2026-08-25.** ✅ Watched RED against the exact file that
blew the account, naming both cleared values at their own lines. ⚠ **It knows this one shape and
nothing else — it cannot tell you a bracket is correct**, only that this specific way of destroying
one is absent. ⚠ **Nothing else in this repo tests whether a position is protected.** A Python
study measures in R with the stop assumed live, so an absent stop is not a shape it can express;
that lives only in the Pine file. ⚠ **It is a PROMPT, not enforcement.**

**Everything else that is prose lives in [`docs/`](docs/):** `PINE_INPUT_DEFAULTS.md`,
`BUG_exit_fill_price_mismatch.md`, `MARKET_STRUCTURE_GLOSSARY.md`, `STRUCTURE_OS_BUILD.md` and
`INDICATORS_BUILD_NOTES.md`. They were NOT split across the two children: each describes both
halves, and splitting them would have made two half-true copies.

⚠ **Not to be confused with [`strategies/tradingview/docs/`](../strategies/tradingview/CLAUDE.md),
which is a different thing with a different job:** one `<family>.md` per strategy holding the
commentary that used to sit inline in that Pine, anchored from the source by `// [doc N]`. Prose
ABOUT a strategy file goes there; prose about the indicators subsystem goes here. ⚠ **That folder
left this tree on 2026-09-02 with the strategies it describes** — it used to be `strategies/docs/`
one level down from here.

---


## The build narrative

Everything below this line is the dated story of how these files got here — what a pass found,
what it measured, and what it cost. It is kept rather than summarised, because a rule with no
incident behind it reads as arbitrary and gets "tidied up" by the next reader.

⚠ **An earlier drain (2026-08-12) moved 129,018 bytes of narrative VERBATIM to
`indicators/docs/INDICATORS_BUILD_NOTES.md` and nothing was deleted; the entries below
accumulated after it.** They are the next thing to drain, and this file is still ~100 KB —
over the 40 KB ceiling the editor guard watches. Draining is deliberately SILENT to that
guard, so nothing will remind you.

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

## 2026-08-07 — PDH/PDL WIN A TIE AGAINST A SESSION HIGH/LOW AT THE SAME PRICE

Aaron: when the previous day's low IS the New York session low, the chart printed `PDL` and
`NY L` stacked on one line. **Drawing only — labels. No line, level, sweep, arm or trade moves.**

**The nudge was already working, which is why this reads as a different bug than it is.**
`f_liqLabels()` spaces colliding labels apart by `lblOff`, so two labels at one price were not
overlapping — they were being *separated*, into two names for a level only one of them needs to
name. The complaint is duplication, not collision.

**Fix:** a session H/L label whose price matches the active PDH/PDL is hidden (`textcolor` na, the
same mechanism a mitigated level already uses) **and left out of the nudge**, so the collision pass
does not space the survivors around an invisible label. Daily wins; the session label comes back the
moment the daily one does not exist — hence the test reads `d_hLbl`/`d_lLbl`, not just the prices
(a mitigated PDH is deleted on the next new day, and then there is nothing to defer to).

⚠ **The tolerance is ONE TICK and that is not a fudge factor.** Both numbers are maxima over the
same bar highs, so a real duplicate is EXACT; a level a few ticks away is a DIFFERENT level and the
existing nudge is the right answer for it. A visual-gap tolerance would start hiding real levels.

⚠ **Scope is deliberately PDH/PDL vs the three session levels only.** PWH/PWL and the H4 sweep can
also coincide with a session level and are untouched — a priority ORDER across all four tiers is a
bigger decision than the one asked for, and the JARVIS `recentBSL`/`recentSSL` block already has its
own (contradicted) ordering recorded above.

### 🔴 …and the same block was reserving space for labels nobody could see

Aaron, same day: "Ldn L" sat at a different distance from its line than its neighbours, and **H4 H
and H4 L were at different distances from their own two lines.** One cause explains both, and it is
not the creation offsets — every label is born at `price + lblOff` (highs) or `price - lblOff`
(lows), verified line by line across all eight files. It is the nudge.

**A MITIGATED daily/weekly/session level is hidden by blanking its textcolor, and the label OBJECT
survives.** The collision pass guarded only on `not na(<lbl>)`, so an invisible label was still
pushed into `liq_y`, still took a slot, and still shoved every visible label above it up by a full
`lblOff` — **with nothing on screen to explain the gap.** That is precisely "this tag's offset is
wrong": the label it was making room for cannot be seen.

⚠ **It explains the H4 pair too, and that is the tell.** H4 is the one tier that is never hidden —
a swept H4 stays on the chart in grey — so H4 H and H4 L both keep their space. What moved them
apart was a hidden Asia/Ldn level sitting under ONE of them and not the other.

**Fix:** the visibility term is added to each of the ten daily/weekly/session guards.
⚠ **The two families need DIFFERENT terms and this is not cosmetic.** `mpc_jarvis.pine` and
`m15_playbook.pine` hide a mitigated label only when `showMitLiq` is off, so their test is
`(not mit or showMitLiq)`; the strategy family's `f_liqMitigate` blanks the textcolor on `newMit`
**unconditionally**, so `i_showMitigated` does not resurrect the label there and the test is plain
`not mit`. Using the assistant's form in the strategies would keep reserving the slot the day
anyone flips that flag.
⚠ **H4 and PWC are deliberately NOT filtered** — both stay visible, so both genuinely need space.

⚠ **What is NOT changed, and is the remaining reason two visible tags can differ: the nudge is
one-directional.** It walks bottom-up and only ever pushes UP, so in a real cluster the lowest label
keeps its natural offset and everything above it drifts. That is the feature doing its job; it is
only misleading when it is spacing around a ghost, which is what this fixes.

**The standing lesson is small and general: hiding a drawing by making it transparent leaves an
object that every layout pass downstream still counts.** The chart said one thing and the geometry
was computed from another.

### 🟢 Mitigated levels are drawn again — and the dedupe was deferring to an invisible label

Aaron: "I also want the mitigated dotted lines for the sessions that break by a candle. I had it
before and it's gone." **`showMitLiq` false → TRUE in `mpc_jarvis.pine`.** It had been the
`Show Mitigated Liquidity Lines` input (default OFF) and the Chart Tools lock-down froze it at its
default as a constant — **which locked in the answer nobody had asked for.** A broken level now
freezes at the break bar, goes dotted and grey, and keeps a greyed label.

⚠ **ONE flag, THREE tiers.** PDH/PDL and PWH/PWL keep their broken levels too, not only the
sessions — which is exactly what the old input did (its tooltip named all three), so this restores
the behaviour rather than widening it. Split per tier if the daily and weekly read as clutter.
⚠ **Nothing accumulates** — each tier deletes and redraws its own line when its pool rolls, so
there is at most one broken level per tier. What changes is LIFETIME: the new-day wipe is skipped
while this is on, so a broken level survives to its own tier's next roll (a swept PWH most of a
week) instead of being cleared at NY midnight.

🔴 **Checking it exposed a hole in the PDH/PDL dedupe shipped hours earlier, and it is the SAME
defect as the reserved-slot one, from the other side.** `liqDupH` tested only `not na(d_hLbl)` — but
a mitigated PDH is INVISIBLE while its label object lives on until the next new-day wipe. So a
swept, invisible PDH went on suppressing a perfectly visible session tag at the same price, and the
level lost its name with nothing on screen holding the place. **Fixed in all eight files**: the
dedupe now defers only to a daily label that is actually drawn. ⚠ **The term differs by family for
the same reason the slot filter does** — `(not mit or showMitLiq)` in the indicator pair, plain
`not mit` in the strategies.

⚠ **The strategy family is deliberately NOT switched on.** Its `i_showMitigated` has always been a
hardcoded `false` — nothing was lost there, so nothing is being restored — and its
`f_liqMitigate` still blanks a mitigated label **unconditionally**, which is the pre-2026 version:
flipping the flag there would draw a faint unlabelled stub, the exact complaint the indicator's own
comment records fixing. Port that label branch first if it is ever wanted.
⚠ **`m15_playbook.pine` still has the real INPUT** (default off) and was left alone — it is a
control, not a lock, so it can just be ticked.

---

**All three changes applied to all eight files that carry the block** (the `showMitLiq` flip is the
indicator only), identical text:
`sos_fade_strategy.pine`,
`b_leg_strategy.pine`, `bos_strategy.pine`, their three exports, `mpc_jarvis.pine` and
`m15_playbook.pine`. ✅ **The three export mirrors were re-diffed after the edit and still
differ from their parents by exactly the `strategy()` title line plus their appended parity block.**
⚠ **NOT COMPILED** — no local Pine compiler, and these files have hit CE10117 twice; the change adds
three locals and six two-branch `if`s inside an existing function, so **zero new main-body
statements** (CE10295 unaffected) but not zero tokens. ⚠ **No input was added, renamed or reordered,
so no "Reset settings to defaults" is needed.**

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

## 2026-08-06 — 🟢 THE VWAP WENT INTO THE BOS STRATEGY INSTEAD, BECAUSE THE MEASUREMENT SAID D'S TRIGGER HAS NO EDGE

Aaron asked which combination of the two continuation strategies to pursue — `bos_strategy.pine`
(fibs + FVG) or `d_strategy.pine` (structure + fake shift + VWAP) — and asked for diagnostics
rather than an opinion. **Neither has a Python port, so neither could be swept.** The question
underneath it did not need one: replay the canonical `market_structure` + `vwap` engines over the
cached bars, find the bar each trigger would actually be IN on, and ask whether price reaches +2R
before −1R. No sizing, no ladder, no costs. **186,384 true-M15 XAUUSD bars, 2018-09-13 → 2026-08-07.**

🔴 **THE CONTROL IS THE LOAD-BEARING PART AND IT IS WHY THE ANSWER IS TRUSTWORTHY.** Gold went
1,200 → 4,300 across this window, so a long-side "edge" is free and any harness without a control
will find one. Every set is scored against **random entries matched on direction AND stop distance**.
The control lands on **33.3% with expectancy 0.000** — exactly the theoretical breakeven at 2R — so
the harness is measurably unbiased before any result is read off it.

| trigger | n | win rate | vs control | expectancy |
|---|---|---|---|---|
| **CONT** — with-trend BOS → 0.5 retrace | 778 | 37.5% | **+4.4% (+2.5σ)** | +0.125R |
| **D** — counter-SOS → VWAP reclaim | 833 | 33.1% | −0.4% (−0.3σ) | −0.007R |
| D — VWAP side only, no reclaim | 838 | 33.5% | −0.0% (−0.0σ) | +0.004R |

🔴 **D's trigger measures as RANDOM** — not losing, indistinguishable from a coin flip on 833 events
across eight years. ⚠ **And the reclaim latch built for it that same afternoon is worth nothing:**
−0.4% with it, −0.0% without. It is neither the problem nor the fix. ⚠ **At longer targets D goes
significantly NEGATIVE** (−2.8%, −2.1σ at 4R), which is the sharper statement: its entries catch
moves that die, so it is not merely edgeless, it is anti-selected for runners.

⚠ **The mechanical reason is the stop, and it is structural rather than tunable.** Median stop:
**CONT $3.43, D $7.24.** D's stop must sit beyond the whole shakeout extreme, so it is 2.1× wider —
same R buys half the position and needs price to travel twice as far.

✅ **VWAP IS A REAL FILTER, AND IT BELONGS ON CONT.** Pro-trend side: **39.9%, +6.8% (+2.8σ)**, median
stop **1.11 ATR**. Wrong side: 34.9%, +2.0% (+0.8σ), stop 1.80 ATR. It roughly doubles the trigger's
edge and cuts the stop 38% — **and the stop is the half that matters more**, because a tighter stop is
more size per unit of risk and is a mechanical gain rather than a statistical one.

🔴 **THE FIRST RUN OF THAT NUMBER WAS +15.9% AT +5.0σ AND IT WAS LOOK-AHEAD.** VWAP side was read off
the close of the bar the limit *fills* on, which selects bars that recovered by their close. Reading
the PREVIOUS closed bar halved it to +6.8%. **The transferable lesson is that the bug's symptom was
being too good, not erroring** — a filter evaluated on the same bar it acts on is look-ahead until
proven otherwise, and the flattering number is the one that survives a careless review.

✅ **Both robustness checks were run rather than skipped.** Across R targets the edge is +5.0% / +6.5%
/ +6.8% / +6.5% / +4.7% at 1R / 1.5R / 2R / 3R / 4R — stable, so not an artefact of the 2R choice —
and expectancy GROWS with distance (+0.094R → +0.257R at 3R), which is what a runner ladder is for.
By year, 7 of 9 positive; 2021 worst (−5.6%), 2022 and 2025 strongest. No single year carries it.

**What was then built:** `bosVwapReq` (F10) in `bos_strategy.pine` — a pro-trend-side gate,
default ON, ANDed into `longArmed`/`shortArmed`, with block code 7 so a refusal shows on the pink
Blocked tag and in the diag log. Full write-up in `docs/BOS_SPEC.md` §4b.

⚠ **A STATE, not a cross**, per Aaron's standing call — and re-read on every bar the limit rests, so
price closing back through VWAP *pulls* a resting order. A one-shot check at arming time would let a
setup fill hours later on the wrong side of the very line that qualified it.

⚠ **`na` VWAP returns FALSE, never true** — "cannot ask" and "no" must not be the same value, and for
a gate about to place money the safe answer is refusal. Costs at most one bar a day.

⚠ **IT IS A DROPDOWN, NOT A CHECKBOX, AND THAT IS THE INTERESTING CONSTRAINT.** TradingView keys saved
input values off declaration order *within each type*. The last `input.bool` in that file sits ~800
lines BELOW the use site, so a bool could not be appended (Pine needs declaration first) and inserting
one would have shifted `execDiagLog` and silently reset it on every chart. **There is no `input.string`
after that point, so a string shifts nothing.** Verified by scanning last-declaration-line per type
before and after. **The paste is safe on a tuned chart and needs no "Reset settings to defaults".**
Generalise it: when a new input must be READ early but must not DISTURB saved values, pick the type
whose last declaration precedes your insertion point.

⚠ **F10, not F9 — and the collision was nearly shipped.** `docs/BOS_SPEC.md` §4 already used F9
for staleness (`bosMaxDays`), while the Pine's inline comments only went up to F8, so "F9" looked
free from inside the file. Caught by reading the spec's table rather than the code's comments. **A
gate's number is a shared label across two documents; free in one is not free.**

⚠ **VWAP had been REMOVED from this file 2026-07-25 under `CE10117` (101,484 > 100,256 tokens)**, and
what came back is deliberately only the VALUE plus one `plot()` — not the settings block, colours and
styles that were cut. The old VWAP spent tokens DRAWING something nothing read; this one is read by
the arming condition. **If CE10117 returns, delete the `plot()` first and the gate last.**

⚠ **NO SLOPE TEST.** `d_strategy.pine` carries `execVwapSlope`/`execVwapSlopeBars`; only the SIDE
test was measured. Adding an unmeasured lever beside a measured one is how the measured one stops
being trustworthy.

⚠ **NOT COMPILED, and the measurement is on a SKELETON.** The probe replayed a plain with-trend BOS →
0.5 retrace → 0.886 stop — **not** this file's FVG-priced entry, the Sniper Zone, F1–F9 or the real
exit ladder. **+6.8% is a strong prior for the filter, never this strategy's own number.** The next
measurement is whether the FVG requirement adds to that edge or merely cuts the sample.

**The standing lesson is about what a diagnostic is FOR.** The request was "which combination should I
use", and the honest answer needed no strategy port at all — the canonical engines plus a control were
enough to say that one trigger has edge, the other does not, and the tool being brought to the table
belongs on the first one. ⚠ **The control is what made it an answer rather than an opinion**: without
it, D's 33.1% and CONT's 37.5% are both just numbers, and gold's own drift would have made the
long-side halves of BOTH look like edges. **Before believing any trigger study in this repo, find the
control — and if there isn't one, the study is a description of gold, not of the trigger.**

---

## 2026-08-06 — `d_strategy.pine`, and why "an SOS then an opposite SOS" is not a signal

Aaron specified a new setup from four hand-marked charts (two long, two short) and named it the
**D strategy** — "D as in dog, the dirty one". The sequence: a MATURE trend, then a counter-trend
SOS that shakes it out, then a with-trend SOS that resumes it. The third SOS is the entry; the
stop sits beyond the extreme the shakeout reached. Full spec + the four worked examples:
`docs/D_STRATEGY_SPEC.md`.

🔴 **The load-bearing finding is that the obvious implementation cannot work, and it fails
silently by firing constantly rather than by erroring.** **An SOS strictly ALTERNATES direction
by construction** — `is_choch = st.dir == -1` gates a bull SOS and the break then sets `dir := 1`,
so the next SOS on that chart can only be a bear one. "An SOS, then an SOS the other way" is
therefore **always true**: every consecutive pair on every chart satisfies it, so coding the
sequence as literally described marks every second SOS and looks like a working indicator.

What actually separates the D sequence from ordinary structure is an **asymmetry in maturity**
across the counter-SOS: the trend being RETURNED to must have printed `>= dMinTrendBos` BOS (it
was a trend), and the counter leg in between must have printed `<= dMaxCtrBos` BOS (it was a
shakeout, not a new trend). Those two integers ARE the strategy; everything else is drawing.
Implementing it needs state reaching **two SOS back**, which is why `dTrendDir`/`dTrendBos` are
read BEFORE the shift that overwrites them — at that instant they still describe the trend the
*previous* SOS killed.

⚠ **Measured on Aaron's own four examples, entering at the return-SOS CLOSE with the stop at the
counter extreme gives roughly 0.5R / 0.75R / 0.95R / 1.2R.** All four were directionally right
and only one cleared 1R. The cause is structural rather than bad luck: **an SOS confirms at the
TOP of the reclaim leg**, so the entry is at the expensive end and the stop is the whole leg away
— the same problem SOS Fade solves by resting a limit on the retrace instead of buying the break. A
`Retrace` entry mode is therefore shipped alongside, but `SOS close` is the DEFAULT so the tool
can be checked against the four reference setups before the entry is changed. Which one pays is
a measurement, not an argument.

⚠ **`dMaxCtrBos` is deliberately not 0.** Two of the four examples show a counter leg that broke
structure in its own direction before turning back — example D's ran ~33 hours and printed its
own higher highs — so a zero would refuse half the setups it was written from. ⚠ **`dMaxCtrBars`
is in BARS and does not transfer between timeframes**; the four reference charts span at least
two. ⚠ **"Sweep" here means a real CLOSE through the protected swing**, not a wick-and-reclaim —
the engine's SOS requires it, and every example prints a genuine LL/HH that stays. The wick
version would be a different strategy.

Two Pine details worth carrying: the drawing uses a **fixed stride** of 5 lines + 1 box + 1 label
per setup, with disabled TPs and a hidden box created TRANSPARENT rather than skipped, because a
variable stride splits a setup across an eviction and leaves orphaned levels on the chart with
nothing to explain them; and the alert is `alert.freq_once_per_bar_close` because the engine's
break test reads the LIVE close, so an SOS can appear and vanish intrabar.

🔴 **It shipped as an `indicator()` and had to be converted to a `strategy()` the same day** —
found by Aaron asking why there were no Properties to test. An indicator has no Properties tab
and no Strategy Tester, so the thing could mark the sequence and could not be SCORED, which is
the only reason it exists. ⚠ **The file was named `d_strategy.pine` throughout: the name is
not the declaration, and nothing in the repo checks that the two agree.** The conversion brought
a real execution layer — %-of-equity sizing, a TP1/TP2/runner ladder, breakeven-at-TP1, and a
cancel path for a resting Retrace order (stale, invalidated before the fill, or superseded by a
newer SOS). Three traps this repo has already recorded were guarded on the way in rather than
discovered again: **a `qty_percent = 0` rung is SKIPPED, never issued** (Pine reads 0 as
"unspecified" and closes the WHOLE position), **a rung stops being issued once touched**
(re-calling `strategy.exit` with a FILLED id places a NEW order rather than modifying it, so a
re-issued TP1 banks another slice every bar), and **the fill bar may not stage its own stop**
(BUG_exit_fill_price_mismatch — a resting limit is reached from the wrong side, so the fill
bar's favourable extreme is the approach to the order, not a move the trade made).

**The stop is FOUR anchors, not one** (Aaron's ask the same day, and the reason is that none of
them is known to be right). The sequence hands over three prices, so every sensible stop is a
point on the line between them: the **sweep extreme** (the honest invalidation, widest), the
**counter-SOS line** — the level the counter-SOS BROKE and price then reclaimed, which is
tighter and sits INSIDE the shakeout so a wick back in stops you out — a **percentage between
the two**, and a plain **percentage of the entry-to-sweep distance** for when the structural
stops are too wide to size against. The SOS line is the engine's own `st.bull_bos_high` /
`st.bear_bos_low`, captured at the counter-SOS and read at the entry on the SAME one-SOS lag as
`dTrendDir`, never re-derived from prices. ⚠ **A tighter stop is not a better trade** — it buys
a bigger position on the same risk budget and pays in stop-outs on setups that later worked, and
the two do not cancel at a fixed rate. ⚠ The ordering cannot invert: the counter-SOS bar closed
THROUGH its level and then went further, so sweep is always beyond SOS line is always beyond
entry, which is what makes the interpolation well-defined.

**The drawing is per FILLED TRADE, not per signal** — under `Retrace` those are different bars,
and a position block starting before the position existed would be drawing a trade nobody was
in. Each one gets the shaded shakeout, a red risk block that tracks the LIVE stop (so it
visibly collapses when breakeven lands), three reward blocks that **brighten on the bar their
target was reached**, and an entry callout whose TOOLTIP carries the whole breakdown — stop,
which anchor produced it, all three targets with R and size, the shakeout extreme, the SOS line,
and how many bars the shakeout ran. ⚠ **The drawing updates are na-guarded and guarded
SEPARATELY from the exits**: a drawing call on an `na` id is a runtime error that takes the
script down, and an order that stopped being issued because a BOX could not be drawn would turn
a chart bug into a trading bug.

**RESTYLED TO `sos_fade_strategy.pine`'s CONVENTIONS the same day** (Aaron: *"follow the mpc strategy
styling for all inputs and debugging annotations and take profits too"*). Same five input groups
— `D Setup` for the sequence gates (as SOS Fade uses `SOS Fade Setup`), `Strategy Execution` for everything
that decides what a trade DOES, plus `D Debug`, `Result Stats` and `Diagnostic Log`. Same
`d`-prefix / `exec`-prefix split, same `"   ↳ "` sub-input with `active =` on its parent, same
tooltip rule: what it does, ON vs OFF, and the one fact that changes the decision — never a
measurement essay, those live here. ⚠ **Declaration order is now FROZEN** for the same reason
that file records at its own time-stop pair: TradingView keys saved input values off declaration
order WITHIN EACH TYPE, so inserting a string or float above an existing one silently resets
every later input of that type on every chart running the script.

**The exit ladder is a PORT, not a lookalike.** `f_dRatchet` is `f_swingRatchet` unchanged, and
the staged stop, the three TP2 floor modes, the three trail methods, the time stop and
close-on-opposite-SOS all keep their shapes and defaults. 🔴 **One deliberate divergence, and it
is the interesting one: `sos_fade_strategy.pine` re-issues every exit rung unguarded on every bar,
which is safe THERE only because it ships both rungs at 0% — the rung is then skipped entirely
and the bug is unreachable at its defaults.** Calling `strategy.exit` with an id whose order
already FILLED places a NEW order rather than modifying it, so a re-issued TP1 banks another
slice of the remainder every bar. This file ships a real 50/25 scale-out, so it guards. ⚠ The
generalisation is worth more than the fix: **a latent bug held off by a DEFAULT is not fixed, and
copying the code without copying the default is how it gets discovered.** ⚠ `execTp1Pct`/
`execTp2Pct` are 50/25 here rather than mpc's 0/0 — riding the whole position to the runner
tested best on the SOS Fade bot over 6.6 years, which is a fact about THAT strategy, so it is stated in
the tooltip rather than copied as a default. ✅ **`execMinStopMode` is now present and ON at
`% of price` 0.08**, which the first build did not have at all: three of the four stop anchors
can land arbitrarily close to the entry, and `qty = risk / dist` is what detonated SOS Fade Run 4 and
BOS Run 1.

**The debug layer follows the same file too**: a pink `SETUP BLOCKED` tag with seven reason codes
in PRECEDENCE order (so a tag can never blame a downstream gate for an upstream refusal), bounded
by `debugDays`; an entry callout that recolours by result and appends the trade's R, with a
`keep for which results` filter; a `Result Stats` breakeven band, because the breakeven buffer
books a few cents and the Strategy Tester therefore files every scratch as a winner; and
`execDiagLog` writing one `log.info` per entry, result and block. ⚠ **"Ready" for the block tag
is `okDir` ALONE** — the one structural fact the sequence is built on. Every other gate is a
CHOICE and those are precisely what the tag exists to report; folding any of them into readiness
would hide the refusals worth seeing, which is the same rule stated at that file's own block tag.

**Status: not compiled, not measured, no Python port, no parity harness.** The state panel
reports the GATES rather than just the outcome, so a quiet market can be told apart from a gate
set too tight — those need opposite responses.

### 2026-08-06 (later still) — 🔴 THE VWAP ENTRY HAD NO RECLAIM IN IT, SO IT WAS NEVER THE SETUP ON THE CHART

Aaron pasted the D strategy with `execEntryMode = "VWAP side"` shipped as the default (set the
previous day) and read the trades off a real chart: *"they were not accurate… I specifically sent
you an image of the type of setups I would like to have, that pro trend."*

**He is right, and the file had it BOTH ways in writing.** `execEntryMode`'s own tooltip promises
*"enter on the first close **back** on the trend's own side of VWAP"* — and the word *back* was
doing all the work with none of the code behind it. Meanwhile `execVwapReq`'s tooltip states the
truth outright: *"It does NOT need price to have crossed back; a shakeout that never lost VWAP
passes on the same terms as one that reclaimed it."* That sentence was written about the FILTER
and was equally true of the ENTRY MODE, where it is not a caveat but the whole trade.
⚠ **So the two tooltips CONTRADICTED each other, fifty lines apart, and the wrong one was the
one describing the shipped default.** This is the repo's label-vs-code refrain arriving with the
label present in duplicate: one claim was aspiration, one was a confession, and nothing checked
either against the line that decides.

🔴 **`f_dVwapOk()` is a pure STATE test — `close > dVwap` for a long — and nothing anywhere
tracked whether price had ever been on the WRONG side.** So the sequence was:

1. Bull trend, bearish counter-SOS prints the shakeout.
2. On a 15m chart price is very often STILL ABOVE VWAP when that SOS confirms.
3. `f_dVwapOk(1)` is therefore already true on the very next bar, and the trade opens THERE.

No pullback, no basing, no reclaim — an entry at the top of the shakeout with the stop down at the
sweep extreme. ⚠ **And it is worse than one bad bar: the block gets a FREE LOOK EVERY BAR for
`dCtrBarsMax` (133 bars ≈ 33 hours on 15m), so a trade could also open a day and a half later on
an unrelated bar that happened to close on the right side of the line.** That is the second half
of "I don't know why some of those trades would take on".

**The setup in Aaron's image is a ROUND TRIP**: bullish structure → bearish SOS printing the LL →
price falls and BASES ON VWAP → closes back ABOVE it → that reclaim is the entry, stop behind the
counter-trend shift. Two events, on two different bars.

✅ **Fixed with `execVwapReclaim` (new, defaults ON) + a `dVwapLost` latch.** Price must close on
the wrong side of VWAP after the counter-SOS before a close back across it can be an entry.

⚠ **A LATCH, NOT `ta.crossover`, and the distinction is load-bearing.** A crossover is true on
exactly one bar, so any other gate refusing that bar — a stop too tight, a position still open —
would lose the setup permanently. The latch remembers the line was lost and lets the entry fire on
the first bar every gate agrees. This is also why Aaron's earlier "make it a STATE, not an event"
instruction is not contradicted: the SIDE test is still a state; what was added is a memory.

⚠ **The latch updates AFTER the SOS shift, deliberately**, so on an SOS bar it reads the direction
that bar just established rather than the one it killed — which is what lets the shakeout's own
SOS candle count as the start of losing VWAP, usually exactly where it starts. It is also tracked
UNCONDITIONALLY, whatever the switch is set to: a latch that only runs while its own switch is on
cannot be switched on mid-chart without lying about the bars it never watched.

⚠ **The new input is declared AFTER THE LAST `input.bool` IN THE FILE and must stay there.**
TradingView keys saved values off declaration order within each type, so a bool inserted beside its
siblings in `GRP_EXEC` would silently reset every later bool on every chart running the script.
✅ **Verified mechanically: all 45 HEAD inputs diff identical in type, order and title; exactly one
appended.** No "Reset settings to defaults" needed.

✅ The state panel stops merging two different states — `Waiting for price to lose VWAP` (the
pullback has not happened) vs `Waiting on VWAP reclaim` (it has, and price has not come back), and
the VWAP row now reads **`reclaimed`** rather than `pro-trend` once both halves are in. The old
wording let the panel look armed when it had nothing to enter on.

✅ Export twin REGENERATED from the parent rather than hand-edited, then re-verified: body
byte-identical except line 72's title, 51 plot columns.

🔴 **NOT COMPILED, NOT RUN, NOT MEASURED.** ⚠ **Two things to check before blaming the rule again,
and neither is a defect:** `dCtrBarsMax = 133` is **PINNED FOR 15m** (it is ~33h there and ~5.5
DAYS on 1H — running this on another timeframe measures a different strategy), and
`dTrendBosMin = 1` accepts a "trend" that printed a single continuation, which is far looser than
the multi-leg run in the reference image; **2 is the honest value for that picture** and is a
tuning decision, not a fix, so it was left alone.

**The standing lesson is one this repo has met from the label side and meets here from the
BEHAVIOUR side: a correct, specific warning was sitting in a tooltip fifty lines from the code it
described, attached to the wrong control.** It documented the filter and was fatal to the entry
mode, and nobody read it as being about the entry mode — including the person who wrote it. When a
caveat explains why something is *acceptable* for one consumer, check every other consumer before
the same sentence becomes the bug report.

### 2026-08-06 (later) — VWAP, and the four quiet failures adding it exposed

Aaron asked for an EARLIER entry: after the shakeout, take the trade when the close is back on
the pro-trend side of VWAP, without waiting for the with-trend SOS — plus, explicitly, *"if it
is already supported by the VWAP and it does not have to cross back over, take those trades."*
**So it is a STATE test, not a cross event**: a shakeout that reclaimed VWAP and one that never
lost it are the same signal, and a `ta.crossover` would have silently refused half of what was
asked for. Shipped two ways because they are two questions — `execEntryMode = "VWAP side"` (the
trigger) and `execVwapReq` (a filter on any mode), **both off by default so the morning's
baseline stays reproducible**, with `execVwapSlope` / `execVwapSlopeBars` as the sub-gate and
`execShowVwap` drawing the exact line the rule reads. It is **`ta.vwap(hlc3)`, the session
VWAP** — an anchored-at-the-shakeout variant would be a second VWAP implementation, which this
repo forbids, and would not be the line "already supported by" describes.

🔴 **It is a DIFFERENT TRADE, not a cheaper D, and that has to be said in the results**: the
with-trend SOS is the only evidence the shakeout failed, and this drops it.

**Four things would each have failed quietly, and three of them are this file's own recorded
traps arriving from a new direction.** (1) **Direction could no longer be read off
`st.bull_sos`** — the block tag and the `B|` log line both inferred a candidate's side from the
SOS on the same bar, correct only while every candidate arrived on one, so **every VWAP
candidate, long or short, would have drawn and logged as a SHORT**; `dCandDir` now carries it.
(2) 🔴 **`cfg_modes`' entry digit was 2-way** (`SOS close ? 0 : 1`), so `"VWAP side"` decoded as
**Retrace** — a stored run described as a different entry model, with total confidence. **This
is the `execRunnerTrail` trap of 2026-07-26 exactly: a code that collapses a widened dropdown
does not fail, it lies. Whenever an option is added to any input, find its cfg digit in the same
commit.** (3) 🔴 **The export's `f_xCand()` rebuilt candidate direction from `st.bull_sos`**, so
it returned 0 on every VWAP candidate and **would have blanked px_cand_dir, px_ctr_ext,
px_rcl_ext, px_sos_lvl and all three px_gate_\* columns for the whole mode** — a clean CSV with
nothing in it, the failure an export is least able to report. It is **deleted, not repaired**:
the parent already records `dCand*` for every candidate at decision time, so there was never a
second claim worth maintaining, only one that could disagree. Its `[1]` lookups were wrong for a
second reason too — `[1]` means "before the shift" only on a bar where the shift RAN, and
`dCurBos` can be incremented by a plain BOS on a non-SOS bar. (4) **A state test re-fires**: the
SOS trigger is self-limiting because an SOS is one bar, but a state is true on every bar, so with
only `bBusy` stopping it a stopped-out sequence would re-enter immediately and keep going until
the bar cap expired — `dSeqTaken` latches, released only by the next SOS shift.

⚠ **The minimum-stop guard stops being optional in this mode.** Entering early means entering
close to the sweep extreme and the stop is anchored at that extreme, so the better the entry the
smaller `dist`, and `qty = risk / dist` grows as it shrinks. On the SOS path the whole reclaim
leg sits in between and the hazard is rare; here it is the normal case. ⚠ **The new inputs are
declared at the END of the file, after `execDiagLog`, and must not be tidied into `GRP_EXEC`** —
the last input of every type sits at or before it, so this shifts nothing and **no "Reset
settings to defaults" is needed**; moving them up would silently reset every later bool and int
on Aaron's charts. ⚠ **VWAP resets at the trading-day open** and `dCtrBarsMax` allows ~33h on
15m, so a sequence can straddle the reset — that is what the chart's line does, and a filter
quietly reading a different VWAP would be the worse failure. ⚠ **`ta.vwap` needs volume** and
raises rather than returning `na` on a symbol without it. ✅ The export was **regenerated by its
own recipe**, body re-diffed to exactly line 60's title, **plot count 48 → 51** (`px_vwap`
ungated on every bar — which is what makes the rule re-priceable offline from a run taken with
the gate OFF — plus `cfg_vwap_slope_bars`, plus the parent's new visible VWAP plot). Block reason
**9** added, numbered last and ranked fifth, raised by the filter only. **NOT COMPILED, NOT RUN,
NOT MEASURED.** Full write-up: `docs/D_STRATEGY_SPEC.md` → *The VWAP entry*.

### 2026-08-06 (later still) — the sweep was already there, and a chart said the EXIT is the problem

🔴 **THE COUNTER-SOS *IS* THE LIQUIDITY SWEEP, AND SETTLING THAT DELETED A 500-LINE FEATURE
BEFORE IT WAS WRITTEN.** Aaron describes D as *"a liquidity sweep and a fake break of
structure"*, and the near-miss was reading that as two conditions: a liquidity-pool port
(previous day/week high-low, H4, session high-low, EQH/EQL) lifted out of `sos_fade_strategy.pine`
to gate the shakeout on having *taken* something. **It is one event, not two.** The
counter-SOS closes through the trend's last protected swing — the HL in an uptrend, the LH in
a downtrend — and a protected swing is exactly where the stops rest. The break and the sweep
are the same bar. ⚠ **A pool test would have been a SECOND claim about one event**, and the
two disagree constantly: a shakeout can break the trend's HL without reaching the previous
day's low, and that is still the setup — so the gate would have refused real trades while
looking like a quality filter. ⚠ **`dSosLvl` is therefore the swept level itself**, captured
from the engine's own `st.bull_bos_high`/`st.bear_bos_low`, which is what makes the
`Counter-SOS line` stop anchor mean *"back above the liquidity that was taken"*. ⚠ **D needs
no liquidity engine and must not grow one** — this file embeds only `structure_engine.pine`.

🔴 **A REAL DEFECT WAS FOUND BY READING THE NEVER-RUN VWAP CODE, AND IT IS LATENT AT THE
DEFAULT AND LIVE THE MOMENT YOU TUNE.** `dVwapSlope` is `dVwap - dVwap[execVwapSlopeBars]` — a
history offset taken from an **INPUT**, not a literal. Pine sizes each series' history buffer
from the offsets it observes on the first bars, so at the shipped 4 it sizes for 4, and raising
the slope input toward its own declared `maxval` of **200** throws *"the requested historical
offset is beyond the historical buffer's limit"* **at runtime**. ✅ Fixed with
**`max_bars_back = 300`** on the `strategy()` call in BOTH files, covering the whole declared
range; the export twin took the identical edit and its body re-diffed to **exactly line 68's
title**. ⚠ **It is not cosmetic — do not drop it on a future regen.** **The standing lesson is
the repo's own from a new angle: a `maxval` is a promise that the whole range works, and here
only the default did.** Anywhere an input feeds a `[]` offset, the buffer has to cover `maxval`,
not the default.

🟢 **AARON MARKED A LIVE EXAMPLE AND IT VALIDATED THE ENTRY WHILE CONDEMNING THE EXIT.**
XAUUSD 19→23 Aug: bullish structure, a bear SOS printing the **LL at ~3,996** (the shakeout),
price basing along VWAP for a dozen-plus bars, then a **close back above it at ~4,012**, stop
behind the LL, run to **4,166**. ✅ **The tool already expresses it exactly** — `execEntryMode
= "VWAP side"` with the shipped `execSlMode = "Sweep extreme"`; nothing needed building. 🔴
**But 1R is $16, the full run is 9.62R, and the shipped ladder caps it at 2.10R** — TP1/TP2/TP3
land at 4,028 / 4,044 / 4,060 and **all three fill on 21 Aug**, so the 4,060 → 4,166 leg never
happens. **7.53R left on the table on the one trade the strategy exists to catch.** That is the
`0.3×1 + 0.3×2 + 0.4×3` arithmetic ceiling the 8.3-year run already found BINDING (max R
**+2.11**, 16 trades on it); the chart supplies the size of the miss. ⚠ **So "catch the entire
run" is an EXIT change, not an entry one, and it is the answer SOS Fade already reached** — that bot
ships both rungs at **0/0** and rides to the runner trail because its money lives in the tail.
D pairs a continuation premise with a scale-out exit. ⚠ **Do not read 9.62R as achievable**: a
structure trail exits on the turn, not the high, so 5–7R is the honest expectation.

🟢 **THE DEFAULTS WERE THEN MOVED TO THAT CONFIGURATION (Aaron's request, same day), SO A FRESH
PASTE *IS* THE RUN.** Four values in BOTH files: `execEntryMode` **"SOS close" → "VWAP side"**,
`execTp3R` **3.0 → 0**, `execTp1Pct` **30 → 0**, `execTp2Pct` **30 → 0**. `execSlMode` was
already `Sweep extreme` — the stop Aaron drew — and the trail, risk %, min-stop and time stop
are untouched. ⚠ **THE BASELINE THEREFORE MOVED: pin `"SOS close"` with 30/30/40 and TP3 = 3.0
to reproduce the 218-trade / +14.03R run.** ⚠ **VALUES AND TOOLTIP STRINGS ONLY — no input was
added, removed or reordered, verified mechanically** (the 45 `input.*` declarations diff
byte-identical to HEAD on type, order and title), so TradingView's saved-value keying is
untouched and **no "Reset settings to defaults" is needed**; the flip side is that an EXISTING
chart keeps whatever is already set, so confirm on the panel rather than assuming. ⚠ **The
export twin took every edit and re-diffed to exactly line 72's title**, plot count still 51.
🔴 **Three comments and four tooltips had to move with them, and that is not tidying** — the
header asserted *"the default stays SOS close"*, and the rung comment said *"these ship as a
real scale-out"*. Both were about to become the exact `eqExemptFvg` failure this file records
from three days earlier: a correct, specific warning left standing directly above the line that
invalidated it. ⚠ **`execTp1R`/`execTp2R` must stay above 0** — at 0% size the TP *prices* are
still what stages the stop to breakeven and hands the runner to the trail. ⚠ **The
`qty_percent = 0` guard is now LOAD-BEARING rather than latent**: it was unreachable while the
rungs shipped at 30, and it is the only thing between this default and `strategy.exit` closing
the WHOLE position at TP1. **That is the lesson the same section already carries from the other
direction — a latent bug held off by a default is not fixed — met here as its mirror: changing
a default is what ARMS the guard, so check what the old value was hiding.**

⚠ **One hazard is NAMED and NOT FIXED, and it must be read out of the trade list.** The VWAP
entry fires on the first qualifying bar after the counter-SOS and nothing requires the shakeout
to have DEVELOPED — so if price is already on the pro-trend side of the session VWAP one bar
after the break, the entry fires with `ctrExt` a bar or two old. That is the smallest stop this
strategy can make and `qty = risk / dist` makes it the largest position. Aaron's example based
for a dozen-plus bars, so it did not bite. The only guard is `execMinStopMode` at 0.08% —
**$3.20 on $4,000 gold, measured on SOS Fade and never here.** Check for any trade whose 1R is under
about $5; the fix would be a minimum shakeout length, not a bigger floor.

### 2026-08-06 (later still) — the JARVIS REV row stuck on TAKE PROFIT after a 0.5 entry

🔴 **A short entered at 0.5 banked TP3 and the row never cleared — it sat on `TAKE PROFIT SHORT ·
TP3 · close the rest` indefinitely.** `mpc_jarvis.pine` only; nothing here reaches a trade.

**Two flags describe one event and only one of them survives a shallow entry.** The SOS Fade leg's
completion death reads the DRAWN FIB's `fibo7Touched`, and that flag is gated — the fib block
checks its three TP levels inside `if fibo618EverReached`. An EARLY 0.5 entry never reaches
0.618, so on that leg `fibo618EverReached` stays false, `fibo7Touched` can NEVER be set, and the
completion death is **unreachable**. The leg then survives until an opposite SOS or a
continuation BOS happens along, which can be hours. Meanwhile the SOS Fade engine's own `aplusX_tp0`
fires perfectly well on that same leg, because its gate is `aplusX_618[1] or aplusX_half[1]` —
half is enough. **The row knew the trade was finished and the death did not.**

✅ Fixed by adding `or aplusL_tp0` / `or aplusS_tp0` to the two death conditions. `aplusX_tp0`
**is** TP3 — it is set on price reaching `fiboP7`, the 0.0 leg origin, the level the drawn fib
labels TP3 — so it is the identical death read from the side that can see it. `fibo7Touched` is
KEPT: it still fires first on a deep entry (the fib block runs earlier in the bar) and it covers
a leg that returned to 0.0 without the engine banking the rungs in order.

⚠ **This is the SAME defect `f_rev15` was fixed for on 2026-08-04, from the opposite side.** That
pass found the 15m security engine missing the win death that the chart-side engine had, and
recorded the chart side as complete. It was not — it was complete only for a deep entry. **A
death condition that has been checked on one entry tier has been checked on one entry tier.**

⚠ It kills one bar LATE (the death block runs before the TP tracking that sets the latch) — the
same lag `f_rev15` already accepts for its own `or S_tp0`, and left the same way rather than
adding a second clear site that can drift from this one. ⚠ It cannot arm a B leg (`bLegArmL/S`
require the continuation-BOS branch plus `not aplusX_half and not aplusX_618`). ⚠ RE-ENTRY after
TP1/TP2 is unaffected — only `tp0` kills, and after TP3 the row's own instruction is "close the
rest", so there is nothing left to re-enter.

⚠ **The death ALERT had to move with it or the fix would have shipped a new wrong message**: the
chain's last branch fires on any drop out of the SOS stages, so a leg now retiring on a WIN would
have announced `SETUP DEAD - died at stage 4 of 4`. It reads `_alDone` (`aplusX_tp0[1]`, at `[1]`
because the death cleared the latches earlier the same bar) and says `COMPLETE - TP3 banked, leg
closed` instead. **A new death is a new alert, whatever the alert block looks like it says.**

⚠ **NOT COMPILED** — there is no local Pine compiler and this file has hit CE10117; the change is
two boolean terms, one local and one ternary, so it is small but not free. No input was added,
renamed or reordered, so **no "Reset settings to defaults" is needed.** ⚠ No parity harness can
see this: the SOS Fade sequence tracker exists only in `mpc_jarvis.pine` and `sos_fade_strategy.pine`. ✅
**Checked rather than assumed — `sos_fade_strategy.pine` and `b_leg_strategy.pine` carry ZERO
references to `aplusL_tp0`/`aplusS_tp0` and have no TAKE PROFIT row**: their restored table is the
EXT/INT structure pair only, so the stuck row cannot occur there and neither file was touched.

---

## 2026-07-31 — the harness pass: four exports validated, one file deleted, session windows finally forked back together

**`mpc_jarvis_v2.pine` DELETED** (Aaron's call). It was a 2,084-line lean `indicator()`
build superseded by `sos_fade_strategy_export.pine`. Last committed at **`825592a`** — recover from there,
never from memory. All doc references removed in the same pass.

**The session windows were forked and nobody had noticed.** `sos_fade_strategy.pine` has carried the
DST-aware windows since **2026-07-12** (`317dbef`) — two weeks BEFORE `mpc_jarvis.pine` got them
(`b25789d`, 07-26) — but `b_leg_strategy.pine` and `b_leg_strategy_export.pine` never did, so
the SOS Fade and B-LEG forks disagreed about when a session opens. That breaks this file's own standing
rule: an engine-block change in the parent flows to the fork line-for-line.

| | old (fixed offset) | new (own city, DST-aware) |
|---|---|---|
| Tokyo  | `2000-0500` GMT-4 | `0900-1800` **Asia/Tokyo** |
| London | `0400-1300` GMT-4 | `0800-1700` **Europe/London** |
| New York | `0900-1800` GMT-4 | `0800-1700` **America/New_York** |

**It is trade-affecting in principle, not cosmetic** — session H/L feed `recentBSL`/`recentSSL`
(`sos_fade_strategy.pine:3121-3126`), which is what `execArmSweep` arms SOS Fade on, and that toggle is ON in the
shipped prime combo. The path is narrow (`showSessH = liq_dh == ""` makes session levels a FALLBACK
used only when no day level exists) but narrow is not none. **Measured, not assumed: neither bot
moves** — `compare_strategy.py --warmup 100` and `compare_bleg.py --warmup 100` both still exit 0.

**Then proven on a FRESH export, which is the run that actually tests the fix.** The paragraph above
was measured against the 2026-07-29 B-LEG export, taken off the Pine *before* its windows changed — a
green there says the Python side is self-consistent, not that the sync is right.
`compare_bleg.py "VANTAGE_XAUUSD, 15_cabec.csv" --warmup 800` → **exit 0**, 6,329 bars,
2026-04-27 → 2026-07-31. **The window matters more than the bar count here:** it sits entirely inside
BST/EDT, which is the half of the year where the new city-clock windows and the old fixed GMT-4 ones
genuinely disagree (New York `0800-1700` America/New_York = 12:00–21:00 UTC under EDT, an hour earlier
than the old `0900-1800` GMT-4). A stale Python side would have disagreed with Pine on every session
boundary in this export. `svp_export.pine` was re-exported in the same pass and `compare_svp.py
--warmup 317` exits 0 on 12,117 bars, so the "re-expression, not a behaviour change" claim about Asia
is now measured too.

⚠ **Compile status after that pass, stated exactly.** `b_leg_strategy_export.pine` and
`svp_export.pine` both compiled — Aaron exported from them, which is stronger evidence than a paste.
`b_leg_strategy.pine` is body-identical to its export apart from the line-40 title, so it is
covered by construction. **`m15_playbook.pine` was never pasted after its windows were edited
and now never will be — it was DELETED on 2026-08-15** (Aaron's call; the note is in
`engines/CLAUDE.md`). ⚠ **It was described here as his BROTHER'S work in progress**, so the six
edited session strings in it were never compiled by anyone and that question closes unanswered
rather than resolved. The surviving files carrying the same block are listed below.

Synced in `b_leg_strategy.pine`, `b_leg_strategy_export.pine` and `m15_playbook.pine`
(each file's own `display = display.none` preserved — only the six values changed; the third of
those was deleted 2026-08-15).
⚠ **That deleted file's NY window had been `0900-1700`**, unlike every other file's `0900-1800` — a
pre-existing difference of unknown origin, folded into the common `0800-1700` by the sync. It was
his BROTHER's in-progress file and the question of whether that hour was deliberate was never put
to him; the file is gone, so the question is now moot rather than answered. `svp_export.pine` was re-stated too, purely for
consistency: `"2000-0500" GMT-4` and `"0900-1800" Asia/Tokyo` are the SAME 00:00-09:00 UTC window all
year, which is exactly why `engines/session_volume_profile/` needed no code change.

**Do this as a line-targeted edit, never a global string replace.** In these files the OLD Tokyo value
(`"2000-0500"`) and the OLD New York value (`"0900-1800"`) collide with the NEW Tokyo value, so a naive
substitution rewrites Tokyo and then immediately overwrites it again when the New York rule runs.
Anchor every edit on its `*_SESSION_GROUP`.

### `fvg_export.pine` — two holes that would each have produced a MISLEADING green

1. **It plotted 6 array slots against a cap of 8**, so gaps 7 and 8 were live in Pine and invisible to
   the diff — every earlier FVG "exit 0" covered the oldest six only. Now 10 slots, `fvgMaxCount`
   capped at 10 to match, and `compare_fvg.py` REFUSES an export whose `cfg_fvg_maxcount` exceeds the
   plotted slots rather than reporting partial coverage.
2. **Its minimum-gap floor was one flat number** while mpc's is timeframe-split
   (`mpc_jarvis.pine:410-412`: `0.0` below 900s, `0.04` at 15m+). Exported on 15m the old build
   would still have gone GREEN — both sides read the setting from `cfg_fvg_thresh` — while running a
   DIFFERENT rule from the indicator it mirrors. It now carries `fvgThreshLTF`/`fvgThreshHTF` and the
   same `timeframe.in_seconds() < 900` ternary; `cfg_fvg_thresh` plots the EFFECTIVE value, so the
   comparator needed no change. Proven both ways: the 15m export read back **0.04**, the 5m **0.0**.

### The four harnesses, validated on two grand exports

`sessions_export.pine`, `liquidity_export.pine`, `ob_export.pine` and `fvg_export.pine` were put on
ONE chart and exported together — 146 columns, **no column-name collisions between the four**, so all
four comparators run off a single CSV. Both runs exit 0 on every check:

| export | bars | window | note |
|---|---|---|---|
| `VANTAGE_XAUUSD, 15m` | 21,691 | 2025-09-01 → 2026-07-31 | spans **four DST changeovers** — the real test of the window re-sync |
| `VANTAGE_XAUUSD, 5m` | 13,186 | 2026-05-27 → 2026-07-31 | covers the NY opening range, which is a ≤5m feature |

**Take the DST-spanning export on the COARSER timeframe.** TradingView caps an export near 20k bars,
so 15m spans a changeover and 5m may not — the opposite of the instinct to always export fine.
`sessions_export.pine` is the one harness that needs both: everything in it is timeframe-agnostic
except the NY opening range, which reads a 5-minute `request.security`. `compare_sessions.py` now
measures the export's bar interval, warns before running, and takes `--skip-nyr` (printing a **NOT
CHECKED** line on success as well as failure).

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

---

## The 2026-07-12 structure re-sync (`choch_lock` removed from the break decision)

Aaron's brother found a missing higher high on XAUUSD 15m (17 Jun 2026, the ~4382 spike) and had it fixed on TradingView. The fix landed in `mpc_jarvis.pine` and was propagated through the entire chain. **Both symptoms were one bug:** a bullish SOS set `choch_lock`, so the next bearish break was not treated as a CHoCH — it printed as a **BOS instead of an SOS**, and since the bear-break fallback classifies the old high with `old_is_hh = is_choch ? true : (…)`, losing the CHoCH also lost the forced `true`, so the **HH never printed**.

Four changes, now byte-identical across all six Pine copies of the engine (`mpc_jarvis.pine`, `structure_engine.pine`, `structure_engine_export.pine`, `ob_export.pine`, `fib_export.pine`, `sos_fade_strategy.pine`):

1. bull break — `is_choch = st.dir == -1` (the `and not st.choch_lock` gate is gone)
2. bear break — `is_choch = st.dir == 1` (same)
3. bull-break SOS — the promoted pullback low prints **ASL**, not HL/LL
4. bear-break SOS — the promoted pullback high prints **ASH**, not HH/LH

…and in both break paths the confirmed-swing map (`last_conf_high` / `last_conf_low`) is now written only `if not is_choch`. On a fast reversal the promoted extreme is only the new ACTIVE swing; the NEXT break in that direction classifies it. That guard is what stops a lower high overwriting a genuine higher high.

`choch_lock` is now **inert** — still declared, set and released, but never read. Leave it alone. It is dead in `mpc_jarvis.pine` too, and these files are kept byte-identical to it; deleting it would make the next Pine diff lie.

**Parity re-confirmed 2026-07-12 on ONE combined export.** `ob_export.pine` + `fib_export.pine` were put on a single `VANTAGE_XAUUSD, 5m` chart and exported as one CSV (9,270 bars). `structure_engine_export.pine` was **not needed on the chart** — `ob_export.pine` already carries all 23 of its `px_*` columns (strict superset), and `fib_export.pine` collides with neither, so all three compare tools (which resolve columns by name and ignore extras) ran off that single file: `compare_tradingview.py --warmup 365`, `compare_ob.py --warmup 548`, `compare_fib.py --warmup 368` — all exit 0. Warm-up differs per engine because each needs a different depth of history before it catches up with the state Pine already had at row 0.

---

## The 2026-07-12 SOS Fade divergence retro-link

An RSI divergence pivot only confirms `divPivotLen` (5) bars **after** the extreme it marks. On a fast V-reversal the SOS fires inside that lag, so by the time the divergence arms Stage 1 the SOS is already in the past — and Stage 2 only looks forward. The setup stuck at 1/3 forever, and in `sos_fade_strategy.pine` that meant a divergence-armed setup could never place a trade.

Fix: remember the last bull/bear SOS bar, and when a divergence arms, adopt an SOS that already fired **at or after** the divergence's pivot bar, provided it is still inside the staleness window. The sequence really did run div → SOS; we just learned about the div late.

This lives ONLY in the two files that carry the SOS Fade sequence — `mpc_jarvis.pine` and `sos_fade_strategy.pine`. The structure engine, the three export builds and every Python engine have no SOS Fade block, so nothing else needed it and no parity harness was affected (no re-run required).

**The two SOS Fade blocks are NOT byte-identical, and that is expected.** Only `process()` is held byte-identical between the two files. `mpc_jarvis.pine`'s SOS Fade block has since moved on: its staleness window is measured in **minutes** (`aplusWindow * 60000`), arming is gated behind `aplusL_canArm`, and it has a session-gap detector. `sos_fade_strategy.pine` is an earlier generation — the window is in **bars** — so the retro-link there compares bar numbers, not timestamps. The strategy also needed a second change: its execution layer snapshots the arm source (`sosL_swp` / `sosL_div`) *on the SOS bar*, which never runs for a retro-linked SOS, so that snapshot is taken at retro-link time instead, measured against the SOS bar. Without it the table would show 2/3 but no trade would fire.

---

## 2026-07-22 — `sos_fade_strategy.pine` readability pass + compile-budget cuts

The trade annotations were rebuilt so a chart can be read without decoding text, and two features were deleted to get back under Pine's compiled-token cap.

**Removed to buy tokens (CE10117: 100543 > 100256).**
- **Kill Zones & NY Range** — the whole input group, the `security` call, the boxes/plotshapes and the today-deletion logic. Both were cosmetic, default OFF, and read by nothing in the execution layer. They still live in `mpc_jarvis.pine` if the drawing is ever wanted back. `nyHour` was KEPT — `lateDayBlock` reads it.
- **`debugMarkNoFvg`'s on-chart labels** — they duplicated the missed-setup callout, which already names FVG as the missing confluence. The COUNTERS (`missedNoFvgL/S`) stay; the diagnostic log still reports every one.

**Trade drawing, rebuilt.** A trade scales out in up to three pieces, so one box can never describe it. On close it now paints as stacked bands, each the slice of price one piece was actually paid for: entry→TP1 fill, TP1→TP2, TP2→runner, in three depths of the SAME green. A faded red band behind them shows how far price went against the trade first. A trade that banked nothing is one red band; one that came back to entry is a lone orange line. Every band comes from `strategy.closedtrades.exit_price()` — the real fill, never a fib level it merely aimed at. TP1/TP2/TP3 tags all anchor at the same x (the trade's right edge + 4) so they stack in one column instead of scattering across the candles.

**Result colours, not direction colours.** Aaron reversed an earlier call: the trade label is GREY while the trade is open (the result is not known yet), then green won / red lost / orange breakeven on close. Direction stays readable via the ▲/▼ arrow, the word LONG/SHORT, and the entry triangle. Breakeven is graded against `execBeBandR`, the same band the diagnostic log uses.

**Two new inputs.** `execLabelWhich` filters which results KEEP their label (All / Wins only / Losses only / Losses + breakevens / None) — the review view is losses + breakevens. `execLabelOff` sets the label's distance from price in ATRs. That second one exists because **Pine has no tooltip-positioning API**: TradingView anchors a tooltip to its label, so pushing the label further out is the only way to stop the tooltip covering the candles. Also note **tooltips exist only on `label`, never on `box`** — a result rectangle can never be hovered, which is why the annotation is a label with a leader line rather than text on the box.

**A regression worth remembering.** Trade labels were briefly gated behind `debugDays` (the missed-setup recency window), which silently deleted every trade label older than 3 days. `debugDays` now applies ONLY to the missed-setup callouts — every real trade always gets its label, however old.

### Pine gotchas this pass exposed

- **`to` cannot be a parameter name.** It is the `for i = 0 to n` keyword. Using it makes the parser reject the whole declaration and blame the FIRST parameter (`CE10156: Syntax error at input "x1"`), which points nowhere near the real cause. `from` is fine on its own but was renamed alongside it.
- **A function's last statement is its return value, and every branch of it must share a type.** `f_posBox`'s closing `if / else if / else` creates a box / a box / a line, which is `CE10235`. Fixed by putting a trailing `int _pbDone = 0` after the chain so the drawing is no longer the return expression — remove that line and the script stops compiling.
- Both of these are the same family as the existing `CE10295` workaround (wrap a big block in a function so the main body pays for one statement).

## 2026-07-23 — `sos_fade_strategy.pine` Method 3 (deep-fib entry) + prime-combo defaults

**New GRP_EXEC input `execDeepFib`** ("Entry: deep gap enters on nearest fib (not gap edge)"). It fixes a class of missed trades: when a qualifying FVG floats DEEP in the retrace, the limit used to rest at the gap's own edge, so price often stalled at a shallower fib and turned back before the edge was ever tapped. With it on, a gap whose NEAR edge (long = gap top `_gT`, short = gap bottom `_gB`) sits deeper than 0.618 re-prices to the nearest fib just SHALLOWER — 0.618/0.702/0.786 — the level price reaches first. A gap on a fib level, or shallower than 0.618, is unchanged. Logic: helper `f_deepFibEdge()` before the Entry EDGE block, called inside the FVG loop. **ONLY the near edge's position decides it** — an earlier "gap body contains a level" gate was WRONG (it dropped exactly the deep multi-level gaps this targets) and was removed.

**Defaults flipped to Aaron's "prime" combo** — the settings he hard-tests in TradingView, now the shipped defaults across the strategy Pine, the export Pine, and the Python bot: `execArmSweep` OFF→**ON**, `execArmDiv` ON→**OFF** (arm on liquidity sweeps, not divergence), `execFvgDeepOnly` OFF→**ON**, `execDeepFib` (new) → **ON**. `execReqFVG` stays ON. This combo measured ≈+237% / PF 6.2 / 85% win / 13% max DD over ~2 years of gold at 84 trades (Aaron's TradingView Strategy Tester). NOTE: this changes the Strategy Tester baseline — the OLD divergence-armed numbers no longer reproduce without flipping the toggles back.

**Ported to the Python bot the same day** — `strategies/python/sos_fade/` (config `exec_deep_fib` + the four flipped defaults in `config.py`, `execution._deep_fib_edge()`, export `cfg_bits` bit 8192, `compare_strategy.py` reads it, meta.json panel entry + updated `edge`/`steps`, 4 unit tests). Parity re-run pending a fresh TradingView export.

**Slippage pinned to 0 in the `strategy()` call.** Both `sos_fade_strategy.pine` and `sos_fade_strategy_export.pine` now declare `slippage = 0` (the two `tradingview/` research strategies too), so the Strategy Tester Properties tab defaults to zero instead of Aaron's carried-over 25-tick setting. TV slippage is a broker-emulator COST, not signal logic — a flat per-fill charge that is neither honest (a resting limit never slips) nor comparable to the zero-cost Python `fill_model="bar"` run. Real costs go in the lab's tick fill model. The breakeven buffer (`execBeBufTk`, default 30) is a strategy INPUT and is unchanged. This does not touch the decision-stream (`px_*`/`cfg_*`) columns, so `compare_strategy.py` parity is unaffected.

---

## 2026-07-24 — the B-LEG fork + 500x leverage pin

**New file `strategies/tradingview/b_leg_strategy.pine`** — the B LEG split out as its own strategy (see the Key-paths entry above for what it is, how it differs from the parent, and the lean-out). Standing rule for it: any change to the parent's engine or SOS Fade block flows in line-for-line; any B-LEG change flows to the Python port in `strategies/python/b_leg/`.

**500x leverage pinned in the `strategy()` call** to match Aaron's demo account. `sos_fade_strategy.pine`, `sos_fade_strategy_export.pine` and `b_leg_strategy.pine` now carry `margin_long = 0.2, margin_short = 0.2` (margin % = 100 / leverage → 500x = 0.2%), and the two `tradingview/` research strategies (`ny_orb.pine`, `london_breakout.pine`) got the same. Like `slippage = 0`, this only sets the Strategy Tester Properties defaults so a fresh paste reproduces Aaron's account — it is not signal logic and does not touch the `px_*`/`cfg_*` decision stream, so `compare_strategy.py` parity is unaffected.

---

## 2026-07-25 — blocked-trade marker (`sos_fade_strategy.pine` + `sos_fade_strategy_export.pine`)

A setup refused by one of the strategy's own toggles used to be **invisible everywhere**: no order is
placed, so nothing is drawn, no row reaches the trade list, and the Strategy Tester cannot know it
existed. That made it impossible to judge whether a blocking rule protects the account or costs it.

**New in both SOS Fade files.** A pink `▲/▼ TRADE BLOCKED` label with the reason in its hover tooltip and a
dotted leader down to the price the limit would have rested at. Input `showBlockTag` ("Mark blocked
trades on chart (pink)", group `SOS Fade Debug`, default ON). Cosmetic only — it reads state and places no
orders.

**Six reasons, reported by PRECEDENCE** (`f_blkCode` returns the first rule that would refuse the
order, so a tag never blames a downstream gate for an upstream refusal): 1 direction off · 2 arm
source off · 3 final hour · 4 divergence/extreme veto · 5 HTF breakout · 6 HTF bias.

**"Ready" deliberately omits every toggle gate** — those are the blockers being reported. It asserts
only what price and the engine decide: SOS in, `fibo_dir` agrees, an entry edge exists, flat, this leg
not already traded.

**Deduped on `sosBar * 10 + code`**, so a setup blocked for twenty bars is one tag — but a *changed*
reason (veto clears, final hour then blocks) is a genuinely different refusal and gets its own tag.

**The `[BLOCK]` log now reads the same `lBlkCode` / `sBlkCode`**, so the log and the tag can never
disagree about why a trade did not happen. This also *shrank* the diag block (the old `lReadyBase` /
`lBlkVeto` / `lBlkLate` trio is gone) and widened its coverage from two reasons to all six.

**Export gets `px_block`** = `longCode + shortCode·10`, non-zero on **every** bar the block holds
(not deduped like the tag), so an offline reader can measure how long each refusal lasted as well as
count them.

**It broke the token cap, and three subsystems paid for it (CE10117: 101484 > 100256).** Removed from
`sos_fade_strategy.pine` — **Order Blocks** (input group, `OrderBlock` type, `manageOBs`/`extendOBs`, and
all four creation blocks: external bull/bear + internal bull/bear), **VWAP** (input group,
`ta.vwap(hlc3)`, the `plot`), and the **Session Volume Profile / MV line** (input group + the whole
Asia-POC block). 4935 → 4700 lines.

All three were cosmetic, defaulted OFF, and read by **nothing** in the execution layer — verified by
grep before deleting (zero references to any of them after the `STRATEGY EXECUTION` header, and zero
orphaned identifiers after: `showOBs`, `obBodyOnly`, `maxActiveOB`, `colBull/BearOB`, `showBull/BearOB`,
`manageOBs`, `extendOBs`, `vwapValue`, `vwapColor`, `vwapWidth`, `showVwap`, `hlc3`, `SVP_SESSION`,
`SVP_TZ`, `inSVP`, `svpRows`, `svpHistory`, `svpPOCCol`, `svp_poc*`, `GRP_OB/VWAP/SVP`). The B-LEG
fork dropped the same three on 2026-07-24 for the same reason, so this is precedent, not a new call.
They live on in `mpc_jarvis.pine` if the drawing is ever wanted back.

**`process()` is untouched**, so the byte-identical rule still holds and no parity harness is affected.

**`sos_fade_strategy_export.pine` got the identical cuts** (4778 → 4540 lines) — its pre-cut line numbers
matched the parent's exactly, so the same eight ranges applied verbatim. In the export the three were
doubly pointless: nobody reads its chart, it exists only to emit the columns, and none of the three fed
any of them. **All 25 `px_*` / `cfg_*` / `dbg_*` columns verified present afterward**, including the
new `px_block`, so `compare_strategy.py` is unaffected.

**If CE10117 returns anyway**, trim in this order: shorten the six `f_blkWhy` strings, then drop codes
1 and 2 (a disabled direction or arm source is a setting you already know about, unlike the four that
depend on price).

---

## 2026-07-26 — orphaned-SVP compile fix + `sos_fade_strategy_export.pine` regenerated

**The compile error.** Aaron's brother edited `sos_fade_strategy.pine` directly on TradingView and pushed
it. His copy deleted the Session Volume Profile **inputs** (`showSVP`, `svpRows`, `svpHistory`,
`svpPOCCol`, `GRP_SVP`) but left the entire 108-line SVP computation block behind, so the script failed
with `CE10272: Undeclared identifier "showSVP"` at the first line that read one. Removed the orphaned
block (the MV / Asia-POC line; cosmetic, read by nothing in the execution layer). 4668 → 4560 lines.
Order Blocks and VWAP were cut cleanly in his copy — verified by grep, no orphans left.

**Lesson for the next TradingView round-trip:** when a feature is cut on the TV side, grep for its
identifiers before trusting the paste. A deleted input group with its consumer still in place compiles
locally in nobody's head and fails on the first line that reads it. The 2026-07-25 entry above lists
the exact identifier set for all three cosmetic subsystems — use it as the checklist.

**`sos_fade_strategy_export.pine` regenerated** (4540 → 4610 lines) by its own documented procedure: the
parent's body up to the `DIAGNOSTIC LOG` header, plus the appended `PARITY EXPORT` block, then restore
`strategy("SOS Fade Strategy Export"` on line 29. That title is now the **ONLY** difference from the
parent — verified by `diff` over the shared range, zero other lines. The export had drifted five
trade-affecting changes behind (the whole **B LEG** setup + its three inputs and the `execAplus` term
in `longArmed`; **`execFvg50`**; **`execRunnerTrail` + `execStructTrailBufTk`**, the structure-swing
runner trail that is now the DEFAULT; **`execTp2StopMode`**; and the removed fixed-R:R lever) and still
carried the JARVIS confirmation table the parent dropped 2026-07-24. All 25 `px_*` / `cfg_*` / `dbg_*`
columns verified present afterward.

**Two things deliberately NOT done, both flagged in the export's own header:**
- **`cfg_bits` still packs 14 booleans.** `execAplus`, `execBLeg` and `execFvg50` have no bit, and
  `execRunnerTrail` / `execStructTrailBufTk` / `execTp2StopMode` have no column. At their **defaults**
  this costs parity nothing (`execBLeg` and `execFvg50` are OFF, and the `sos_fade` Python bot has
  no B leg — that lives in `b_leg`). Tune any of them and the column must be added here AND in
  `compare_strategy.py` before a diff means anything.
- **`execFvgDeepest` (the deepest-gap-on-a-fib entry toggle) is GONE and has to be rebuilt from
  scratch if wanted.** Built repo-side 2026-07-25 across both Pine files, `sos_fade`
  (`config.py` / `execution._pick_edge` / 6 unit tests / meta.json panel / `cfg_bits` bit 16384) and
  never committed — then wiped: the brother's TradingView copy overwrote the Pine, and the working-tree
  revert that followed discarded the Python. Nothing of it survives. What it did: when TWO OR MORE
  FVGs qualify in the entry band, ignore the shallow ones and rest the limit at the DEEPEST gap whose
  body holds a fib entry level (0.618/0.702/0.786/0.886), at that gap's own near edge — instead of the
  historical rule of taking the gap price reaches FIRST. Method 3 was deliberately NOT applied on that
  path (re-pricing a gap that already holds a level drags the limit back to the shallow side and undoes
  the choice). Measured over 8 years of gold 15m: 188 trades / +39.0R → 180 / +44.5R, better in 6 of 9
  years — a real fix on the specific trade Aaron raised (a −1.00R stop-out became a +0.10R scratch) but
  only modestly above the ~3R noise floor in aggregate. **The lesson is the process, not the feature:
  commit repo-side Pine work before the next TradingView round-trip, or it dies.**

---

## 2026-07-26 — the exit levers ported to the B-leg fork + the export's config columns completed

Aaron's brother's 2026-07-25 paste added a new **exit** family to `sos_fade_strategy.pine`. This pass
brought `b_leg_strategy.pine` and both Python bots up to it, and closed the export hole it left.

**What was new in the parent** (all in `GRP_EXEC`):
- `execRunnerTrail` — "Fixed step" / **"Structure (swing)"**, the DEFAULT. Past TP2 the runner
  trails the structure engine's last confirmed swing (`st.last_conf_low` / `st.last_conf_high`)
  instead of the `execTrailStep` grid ratchet.
- `execStructTrailBufTk` — 20 ticks below/above that swing, so a wick doesn't clip the runner.
- `execTp2StopMode` — "TP1 price" (default) / "Breakeven" / "One trail step behind": the stop FLOOR
  the instant TP2 fills, before the trail engages. The trail may tighten past it, never loosen it.
- `execSlLevel` — the stop's fib, 0.618 … **1.0** (default = the leg origin, i.e. unchanged).
- `execAplus` — trade SOS Fade setups at all, so the B leg can be read in isolation.

The brother's tooltip names the tested best combo: **Structure trail + buffer 20 + floor = TP1 price**.

**Ported into `b_leg_strategy.pine`:** `execRunnerTrail`, `execStructTrailBufTk`,
`execTp2StopMode` and the `lStage2Floor` / `sStage2Floor` + structure-trail exit block, line-for-line
off the parent. Plus `execAplus`, relabelled **"SOS Fade has priority (stand the B-leg down)"** — in this
fork SOS Fade never places an order, so the flag doesn't disable an entry path, it drops the priority gate.
That gate has been the file's own first-listed tuning candidate since 2026-07-24 and is now a toggle.

**Deliberately NOT ported to the B-leg fork**, with reasons, so nobody "fixes" it later:
- `execSlLevel` — the B leg's stop is its frozen band's origin, not a fib on the SOS Fade leg. The dropdown
  has nothing to select there.
- The pink blocked-trade markers. Their codes answer "why was this **SOS Fade** setup refused". In a fork
  where SOS Fade never trades, those tags read as the opposite of what they mean. A B-LEG block tag needs
  its own code set — new design work, not a port.

**The export hole this closed — the important part.** `execRunnerTrail` shipped defaulting to
Structure on 2026-07-25, but `sos_fade_strategy_export.pine` carried no column for it. So
`compare_strategy.py` configured the Python bot to the fixed-step fallback and diffed a
structure-trailed Pine against a grid-trailed Python: a mismatch that is pure drift, reported as if
it were a bug. **A default that changes behaviour is exactly as dangerous as a new input, and it
hides better.** The export now carries `cfg_bits` bits 16384 / 32768 / 65536 (`execAplus` /
`execBLeg` / `execFvg50`), `cfg_exitmode` (both exit dropdowns packed), and one RAW column each for
`execStructTrailBufTk` / `execTrailStep` / `execTp1Pct` / `execTp2Pct` / `execBeBufTk` /
`execSlBufTk` / `execBeBandR`. Those six are plotted raw rather than packed on purpose: any pack
that fits them in one float64 has to round, and a silently rounded buffer mis-configures the bot —
the exact failure the block exists to prevent. `compare_strategy.py` warns loudly on an export with
no `cfg_exitmode` (i.e. taken before this change) instead of guessing.

**VALIDATED the same day — and the new columns paid for themselves immediately.** A fresh 21,230-bar
`VANTAGE_XAUUSD, 15m` export off the updated export Pine ran `compare_strategy.py --warmup 100` to
**exit 0**. Two things only the new columns could have told us:
1. The Pine was running `execTp1Pct = 20` / `execTp2Pct = 20`, NOT the 30/40 shipped defaults. With no
   column for them the bot would have replayed 30/40 and the diff would have been blamed on logic.
2. The first run's single mismatch (`px_edge` on one bar) was a genuine bug — an unpinned FVG engine
   input. `sos_fade_strategy.pine` HARDCODES the middle-bar close-cleared check (lines 1686/1688) while the
   `fair_value_gaps` engine defaults `require_close` OFF, so Python created gaps the Pine never did.
   Fixed on the Python side (`EngineConfig.fvg_require_close`, pinned True by the bot). **Never fix
   this class of gap by editing the Pine** — it is the source of truth; the pin belongs in the port.

`b_leg_strategy.pine` compiles (confirmed on TradingView), and its parity harness was built the
same day: **`strategies/tradingview/b_leg_strategy_export.pine`** = that file with the body byte-identical
(only the line-40 `strategy()` title differs) + an appended PARITY EXPORT block, diffed by
`strategies/python/b_leg/tools/compare_bleg.py` and registered in `backtest/tools/verify_parity.py`.
It plots the B-LEG arm (NOT `longArmed` — SOS Fade never places an order in this fork), the band's 0.5 edge,
the band-derived TP1/TP2, and the tracker's own `bl_*` state, which is the column set that matters:
every new B-LEG rule lives in the tracker, and a band-maths bug shows as a wrong price many bars before
it becomes a wrong trade. **Ran GREEN (exit 0) on its first real export the same day** — 21,231 bars, ~90 distinct frozen bands and 5 graded trades diffed. That run also found a bug in the HARNESS (entry direction read off `Fill.qty`'s sign instead of the signed `Fill.dir`), which the offline round-trip test could never catch because its encoder shared the same mistake — a round trip proves the two halves agree, never that either is right.
`cfg_strcodes`' SL slot is pinned to the "1.0" code because this fork has no `execSlLevel` (its stop is
the band ORIGIN), which keeps ONE `cfg_*` decoder serving both exports. Regeneration split point is in
the export's own header.

---

## 2026-07-27 — TP1/TP2 default 30/40 → 0/0, and the `qty_percent = 0` trap

`execTp1Pct` / `execTp2Pct` now default **0** in both `sos_fade_strategy.pine` and
`sos_fade_strategy_export.pine` (and `exec_tp1_pct`/`exec_tp2_pct` in `config.py`, in lockstep). 0 = bank
NOTHING at the targets; the whole position rides to the runner. This is what Aaron has actually been
trading — his saved chart carried 1% on both rungs, which is the closest the input would take — and it
is what `sos_fade_optimization.md` Run 1 measured as best (0/0 = 70.7R vs 47.9R at 30/40,
monotonic across all 21 combos).

**The trap, and why the code needed a guard, not just a new default.** `strategy.exit()` treats
`qty_percent = 0` as UNSPECIFIED and falls back to closing the **whole position** at that limit — so
setting the input to 0 would have banked everything at TP1, the exact opposite of what it reads as.
This is why 0 appeared not to work. Both files now SKIP the call entirely when the rung is 0:

```pine
if execTp1Pct > 0
    strategy.exit("L-TP1", from_entry = "Long", qty_percent = execTp1Pct, limit = lTP1, stop = lStop)
```

leaving the runner leg as the only exit, which is what 0% means. The TP **prices** still drive the
staged stop (`lStage`/`sStage`) whatever the rung sizes are — touching TP1 still lifts the stop to
breakeven, touching TP2 still hands the runner to the trail. The Python needs no guard:
`_remaining_brackets` computes p1 = p2 = 0 and emits neither bracket. `minval` on both inputs was
already 0; the failure was at runtime, not in the input.

**Parity RE-VALIDATED GREEN (exit 0) 2026-07-27** on a fresh 21,320-bar `VANTAGE_XAUUSD, 15m` export
taken at the settings Aaron trades — SL fib **0.886**, TP1 0%, TP2 0%, structure trail. First run of
the 0/0 exit path against the Pine, so the guard is verified by the decision stream, not just by the
script compiling.

**A note on reading TradingView's trade list, learned the same day.** The Strategy Tester counts each
exit RUNG as its own "trade": a 486-row list over 2020-2026 was 162 positions × 3 rungs. Group by entry
timestamp before comparing anything to a Python run's trade count. The rung SIZES in that export are
also how the 1%/1%/98% split was caught — the sizes are in the CSV and they are ground truth about what
the chart was configured to do, which the code's defaults are not.

---

## Guides & references

- `indicators/docs/STRUCTURE_OS_BUILD.md` — full build log: settings-panel parity, architecture (two engines/one shared type), design decisions, open questions, and per-stage validation status against the original TradingView indicator.
- `docs/market_structure_engine_spec.md` — plain-language spec of the detection rules (swing points, HH/HL/LH/LL, BOS/CHoCH, internal engine) derived from the TradingView indicator's public description.
