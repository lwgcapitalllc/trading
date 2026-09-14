# Notes — extreme_leg_strategy.pine — the run into the shift of structure

The full write-up of `extreme_leg_strategy.pine`, the leg that trades the run into a shift of structure. Moved VERBATIM out of `strategies/tradingview/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## `extreme_leg_strategy.pine` — the run INTO the shift of structure (new 2026-08-24)

The counterpart to SOS Fade: that bot waits for the shift and fades the retracement, this one takes the
move that CREATES the shift — extreme up to the swing whose break IS the shift. **Prose, defaults
and the numbers behind them: `docs/extreme_leg_strategy.md`. The study that produced the rules
is `../../docs/PRE_SOS_LEG_STUDY.md`.** Only what is true of THIS directory lives here.

✅ **COMPILES AND RUNS** (2026-08-25). It is 1,443 lines carrying two copies of the external state
machine; the token ceiling was the risk and it cleared. ⚠ Its first run blew the account — the
defect and the standing rule it produced are in the 🔴 block further down this file.

🔴 **TUNED 2026-08-25, and the rule worth carrying to the next strategy: SWEEP WITH THE POSITION
SLOT ON.** An exit that ends sooner hands the slot back, so it is worth more than its average
outcome says — scored one-trade-at-a-time the winning exit here looks marginal, and with one
position it is the largest gain available. Two defaults moved as a result. Numbers, the
risk-percent table and the interaction that killed the most promising change:
`docs/extreme_leg_strategy.md`.

🔴 **THEN SEARCHED EXHAUSTIVELY ON 2026-09-01 — 509,000 configurations across five searches — AND
NOT ONE BEAT THE SHIPPED SETTINGS.** That is the finding, and it is the outcome a search is least
likely to produce and most likely to be doubted, so it goes first. **The 15-minute chart with a
5-minute trigger also won the timeframe question outright**, against thirteen other pairings and
against a 30-minute chart RE-TUNED from scratch over its own 252,000 (its best: +35.9R against
+83.3R). ⚠ **A faster trigger buys frequency and nothing else** — the 1-minute version fires 270
times a year and loses money, which is the direct answer to "can this pay me every day".
🔴 **THE FINE PASS NAMED A WINNER AND IT WAS REJECTED, WHICH IS THE TRANSFERABLE PART.** A 15-minute
change to the sweep window scored 4% better; its neighbours across single steps run 74 / 87 / 83 /
75 / 77 / 74, so the axis moves 10R between adjacent values and the "winner" is a coin landing well.
**Print the neighbours of anything a search hands you — a real setting sits on a hill, and a hill
and a spike are indistinguishable from the top.**
✅ **ONE INPUT ADDED: the calendar refusal, defaulting to ON.** Friday setups were free — 40 over
eight years returning +1.1R between them while supplying 25 of the losses — so refusing them leaves
the money unchanged and cuts the worst run from 9.7R to 7.9R. ⚠ **It reads the day in UTC**, because
that is how it was measured and a chart opened elsewhere would otherwise refuse different bars,
silently and only for part of the day.
🔴 **THE BIGGER WIN CANNOT BE BUILT IN PINE AND THAT IS WORTH KNOWING BEFORE SOMEBODY TRIES.**
Refusing a transitioning market takes the worst run to 5.9R and the 5%-risk drawdown from 33.5% to
26.4% — but `engines/regime/` has no Pine source by construction, so putting it here means a second
implementation of a canonical engine in another language with no parity gate. That is a project.
Every number, the four dead ends, and the risk table: `docs/extreme_leg_strategy.md`.

🔴 **ITS THREE SESSION WINDOWS WERE READ ON THE WRONG CLOCK FOR AS LONG AS THE FILE EXISTED
(found and fixed 2026-09-01), AND THE LESSON IS ABOUT AN ABSENT ARGUMENT RATHER THAN A WRONG ONE.**
It built its session highs and lows from three fixed strings with **no timezone**, and a session
string with no timezone resolves in the SYMBOL'S EXCHANGE clock — New York for gold, daylight
saving and all. So every window sat 4–5 hours later than its own name: two of the three tracked no
real session at all, and the one labelled "London" WAS the New York session under a wrong name.
MEASURED over 38,747 M15 bars — the old "London" high and low equalled the house New York session's
on **100.0%** of bars, while the other eight pairings agreed on 0.0–8.0%. ✅ Each window now names
its own city, which is what `../../indicators/engines/mpc_jarvis.pine` — the file this was ported from — has
always passed, and what `engines/sessions/` carries.
⚠ **Nothing failed, nothing repainted, and the chart looked right the whole time**: a session box
in the wrong place still looks like a session box. The only symptom was a strategy arming on levels
its own documentation did not describe.
⚠ **It CHANGES WHAT THIS TRADES**, and the direction was decided by the house standard and by the
parent file, never by which clock made more money. **Do not re-optimise around it** — picking a
session clock for its P&L is picking a result and calling it a rule.
⚠ **The generalisation, and it is the one to carry: an omitted argument is a DEFAULT you did not
choose.** A wrong timezone gets noticed because somebody typed it. A missing one inherits whatever
the platform decides, silently, and the platform's choice here depends on the SYMBOL — so the same
file is wrong by a different number of hours on a different instrument.

✅ **IT HAS AN EXPORT TWIN SINCE 2026-09-01, AND THE TWIN IS GENERATED RATHER THAN MAINTAINED.**
`tools/build_extreme_leg.py` now writes both files from ONE body: the strategy, and
`extreme_leg_strategy_export.pine`, which is the same body with a different title and 62
`plot()` columns appended. The build asserts the two bodies are byte-identical apart from that, and
asserts the column count against Pine's 64-plot ceiling. **It was the only generated twin here
until 2026-09-10**, when the shared builder took over all six (see the top of this file). ⚠ **Edit
the generator or `export_blocks/extreme_leg_strategy.pine`, never either `.pine`.**

🔴 **THIS FILE TOOK EVERY LIQUIDITY LEVEL ON A WICK, AND ITS OWN PARENT DOES NOT (found by the
first real parity run, 2026-09-02, fixed the same day).** The sweep tracker used `high > level` /
`low < level` for all four families. `engines/liquidity/` — 100% parity-validated against
`indicators/engines/mpc_jarvis.pine` — takes a **WEEKLY** level only on a **CLOSE** through it
and the daily and lower families on a wick (`engine.py:228`, citing `mpc_jarvis.pine` line
1427). **The house engine and the parent indicator agreed with each other; this strategy file was
the odd one out.** The tracker now takes a close-through flag, passed only for weekly.

✅ **CONFIRMED GREEN THE SAME DAY.** A second export off the regenerated twin — same window, same
shape — compared 20,327 bars and the gate exited 0. **That is what confirms the fix; the argument
for it only decided which half to change.**

⚠ **MEASURED, and it is why the gate was worth building rather than reasoning about**: over 20,319
compared bars the weekly family differed on **ten bars** and every other family agreed on **all**
of them. All seven diverged columns cascaded from those ten. ⚠ **The direction was decided by the
house standard, not by which rule made more money** — the same call as the session-clock fix the
day before, and the same instruction follows: **do not re-optimise around it.** ⚠ **No Python
baseline moves** — that side already followed the engine; only the chart changed.

✅ **THE SAME RUN CONFIRMED THE SESSION-CLOCK FIX.** That was made on 2026-09-01 against a
cross-map with no export to check it. The session families now agree on every one of the 20,319
compared bars. **A fix argued from a cross-map and a fix proven by an export are not the same
thing, and this is the export.**

✅ **ONE DEAD INPUT REMOVED IN THE SAME PASS.** "Enter on the change-of-character close" appeared
exactly once in 1,443 lines — its own declaration — and nothing read it. Its tooltip promised that
turning it off would wait for the next 15-minute close; turning it off did nothing at all. It was
DELETED rather than wired, because the branch it promised was measured and is worth 8R less
(+75.1R against +83.3R over the same bars). ⚠ **Rule 7 found it in ten seconds and only because
somebody went looking** — a control that does nothing costs nothing to ship and is indistinguishable
from one that works.

🔴 **IT IS THE FIRST FILE HERE WHOSE SECOND ENGINE INSTANCE IS GENERATED RATHER THAN FORKED.**
`tools/derive_htf_structure.py` regenerates the 15-minute copy from the block in
`h4_sweep_strategy.pine` — renaming the type and method, swapping the four bar globals for
passed-in values — and `tools/build_extreme_leg.py` assembles the file around it. **This directory's
own worst failure mode is the reason**: eleven files each carry a private fork of one state machine,
so a bug fixed in sixteen places walked back in through a seventeenth cut from pre-fix source, and
nothing failed when it did. A generated copy makes a divergence a diff. ⚠ **The script asserts the
exact substitution counts (12 `high`, 15 `low`, 9 `close`, 2 `open`, 4 pivot-bar reads) and refuses
to write on any other number** — a silent under-match is a state machine reading the wrong
timeframe's bar with nothing on the chart to show for it. **Do not relax that check; re-count and
update it in the same edit.** ⚠ **Re-run BOTH scripts after any cross-cutting structure fix**, or
this file keeps the old engine while its source gets the new one.

🔴 **THOSE COUNTS WERE 16 / 19 / 9 / 2 / 44 FOR ONE DAY AND THE ENGINE THEY BUILT RAN ON TWO
CLOCKS AT ONCE (2026-08-25).** The first generator swapped the bar index too, and everything
downstream of it: every swing LOCATION became a higher-timeframe count while every loop bound and
lookback stayed a chart-bar count. The post-break rescan then searched a window a third of the
length it meant to, and the bootstrap scan could reach past the start of history. **Neither half
errors, goes red, or shows on a chart — a swing simply anchors in the wrong place.**

✅ **The rule that resolves it, and it generalises to any aggregated-bar engine here: THE EXTREME
OF A SPAN OF AGGREGATED BARS IS THE EXTREME OF THE CHART BARS UNDER IT.** A 15-minute bar's low
IS the lowest of its three 5-minute lows, so "the lowest low between these two points" returns the
same PRICE whichever series you scan. So the scans, the loop bounds and every stored location stay
on the CHART's clock and stay consistent with each other, and only the per-bar DECISIONS — is this
bar inside the last one, did this close break the swing — take the aggregated values. That is
exactly the bare reads, which is why the counts dropped: an indexed read (`low[i]`) is history on
the chart's own series and is deliberately left alone. ⚠ **One consequence to know rather than
discover: the rescan's 1490-bar runaway guard is now 1490 CHART bars, about 496 higher-timeframe
ones.** It is a guard, not a rule, and no swing here spans that far.

🔴 **IT SURFACED AS ONE COMPILE ERROR ON AARON'S PASTE (`CE10272`, `_bi` undeclared), AND THE
COMPILE ERROR WAS THE HARMLESS HALF.** Two helper methods got the rename without getting the
parameter, so Pine refused them; the two-clock defect underneath compiled perfectly and would
have run. ✅ **The narrow half is now checked mechanically — `indicators/tools/check_scope.py`,
which asserts every `_`-prefixed read inside a function body is a parameter of it or assigned in
it.** All 13 strategy files pass; watched RED by mutation on the exact line Aaron reported. ⚠ **It
cannot see the two-clock half at all**, and nothing can — that one is caught by reading, or by the
export twin this file still does not have.

🔴 **IT THEN COMPILED, AND ITS FIRST RUN BLEW THE ACCOUNT (2026-08-25). The compile error and the
two-clock defect were both cheaper than this.** Orders here process on the bar's CLOSE, which is
after the script has finished running for that bar — so on the bar an entry is placed, the book
still reads flat everywhere below it. This file cleared its stop and target under a bare flat test,
which fired on the entry bar and wiped both three lines after the entry set them. **The bracket
went out empty on the next bar, and because a new entry needs a flat book the position could never
close: one unprotected trade, held to the end of the chart.**

**The standing rule for every strategy in this directory: after a `strategy.entry` call, a bare
`strategy.position_size == 0` is a LIE for the rest of that bar.** Any block that reads the flat
book below an entry needs a per-bar just-entered flag in its guard. `h4_sweep_strategy.pine`
has carried that pair since it was written; the derivation of this file dropped it.

⚠ **Sizing is what turned a wrong trade into a dead account, and it is worth saying separately.**
Every trade risks a fixed percentage of equity, so a tight stop buys a large position — MEASURED
over the 486 signals the shipped configuration produces, the median stop is $6.98 and the 1st
percentile $1.26, which on a $10,000 account at 1% risk is 14 and 79 ounces, $47k and $262k of
notional. **Correct sizes for a trade that has a stop. The account, for one that does not.**

🔴 **No Python study can catch this class.** A study measures in R with the stop assumed live, so
an absent stop is not a shape it can express — and a parity gate would not have caught it either,
since both sides would agree. **Whether a position is protected is decided only in the Pine file.**
✅ `indicators/tools/check_flat_reset.py` now refuses this one shape mechanically; watched RED
against the exact file that blew the account, and all 13 strategy files pass.

⚠ **It ships TWO of Section 2's four toggles, and that is an open decision rather than an
oversight.** There is no internal engine here, so the other two would be controls that look like
they do something — the hazard the contract's own note names. Porting it in would be a THIRD state
machine in one uncompiled file, purely to draw with. **If it compiles with room to spare, port the
internal engine and make the section standard.**

⚠ **No `_export` twin, so no parity gate can ever run on it** — the same hole
`realign_strategy.pine` has, and it means every number this file produces is a lab finding
until a twin exists.
