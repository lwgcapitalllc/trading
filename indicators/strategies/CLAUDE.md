# CLAUDE.md — indicators/strategies/

**Purpose:** The Pine `strategy()` sources — the files that place orders in the TradingView
Strategy Tester, plus their instrumented `_export` twins.
**Scope:** This file owns everything true of a STRATEGY Pine file: the numbered input-panel
contract, the trade annotations, and the colour palette. It does NOT cover the `indicator()`
sources those strategies were cut from — that is `indicators/engines/CLAUDE.md` — and it does
not cover the Python ports, which own their own CLAUDE.md under `strategies/python/`.
**Last reviewed:** 2026-08-15 — **`mpc_m15_playbook_strategy.pine` is now
`smc_session_sweep_strategy.pine`, and `../engines/mpc_m15_playbook.pine` was DELETED** (Aaron,
2026-08-15; see *The session sweep strategy* below). Before that it was brought onto the panel
contract and the palette, then had two drawing bugs found on a chart. Full narrative in
`../docs/INDICATORS_BUILD_NOTES.md`. The `active =`
declaration-order check this file has been asking for since 2026-08-12 now exists and has been
run on all twelve files. 2026-08-13: split out of `indicators/CLAUDE.md` when the Pine sources
were divided into `strategies/` and `engines/`; the rules below moved verbatim.


## `mpc_recovery_strategy.pine` — the A+ book plus a LOSS RECOVERY leg (new 2026-08-19)

**A FORK of `mpc_strategy.pine`, not an edit to it, and the reason is mechanical.** A recovery
trade is open AT THE SAME TIME as a primary. That file's bookkeeping assumes one position:
`strategy.position_size == 0` means *"the trade closed"* at **13 arming gates** and at the
WIN/LOSS grader (`closedR`), while `strategy.netprofit`, `strategy.position_avg_price` and
`math.abs(strategy.position_size)` are all TOTALS feeding `openRiskUsd` — the divisor every trade
is graded in. Open a second position there and **the primary silently stops grading its own
trades**; nothing errors and no plot changes shape. Forking is also what this directory already
does for variants (`mpc_b_leg_strategy.pine`, `mpc_bos_strategy.pine`).

⚠ **NOT COMPILED.** Written against the Pine v6 reference and never run on a chart. Expect syntax
fixes on first paste. **Nothing here has been verified by anything.**

### What differs from `mpc_strategy.pine` — 294 changed lines, every one marked `[REC]`

| | |
|---|---|
| `pyramiding` 5 → 8 | primary + 4 adds already fills 5; the recovery needs its own slot |
| `f_isRec` / `f_primarySize` / `f_primaryEntryPx` / `f_recSize` / `f_recEntryPx` | a recovery order is any entry id starting `Rec`; every global that was a TOTAL now has a primary-only twin |
| `posPrimary` replaces `strategy.position_size` | **30 sites** below the helpers, including all 13 arming gates, both open-transition detectors, the position box and the scale-in blocks |
| `primaryNet` replaces `strategy.netprofit` | in `netAtEntry` and `closedR`, so the two legs cannot credit each other |
| `f_primaryEntryPx()` replaces `strategy.position_avg_price` | it would blend the recovery's fill into `lEntry`/`sEntry` and therefore into `openRiskUsd` |
| group **11** inputs | `recEnabled` (**default OFF**), size %, both-directions, lock-at / lock-to, trail, day cap, scratch band |

🔴 **THE FIRST PASTE FAILED ON `CE10095: "G9" is already defined`, and the cause is worth keeping.**
The recovery group was numbered 9 because the panel contract's own table lists 9 as *Drawing: Fibs*
and this file has no fibs — so 9 read as free. It was not: `mpc_strategy.pine` declares **both**
`G9 = "9 · Drawing: fibs"` and `G10 = "10 · Drawing: sessions"`, and the new declaration was
inserted directly above the existing one. ⚠ **The contract's numbering is the ADDRESS, not an
inventory of what a given file uses** — read the file's own `var string G*` block before claiming a
number. The recovery group is **G11 / "11 · Loss recovery"**; renumbering the two drawing groups
instead would have moved every existing input to a new group in anyone's saved chart settings.
✅ Checked afterwards rather than assumed: all 24 new identifiers (`f_isRec`, `posPrimary`,
`primaryNet`, `f_recSize`, every `rec*`) are absent from `mpc_strategy.pine`, and
`indicators/tools/check_active_order.py` passes.

✅ **That acceptance test PASSED on 2026-08-19** — identical book with `recEnabled` off, so all
30 `posPrimary` substitutions are right.

🔴 **THE SECOND PASTE — recovery ON — DIED MID-RUN ON A DRAWING CALL, AND A HALT IS NOT A DRAWING
BUG.** `Error on bar 70887: Bar index value of the 'left' argument (58907) in 'box.new()' is too
far from the current bar index.` TradingView refuses a `bar_index` anchor past ~10,000 bars and
**stops the script there**, so the trade list silently ENDS at that bar — the numbers under it are
a partial run that looks like a finished one. ⚠ **Read a Pine "Caution!" as a truncated result,
never as a cosmetic complaint.**

The anchor was `PosBox.entryBar`, reached by elimination: with the defaults, sessions and the
sniper zone draw nothing and every FVG box anchors at `bar_index - 1`, so the position box owns the
only `box.new` in the file whose left edge can travel. Two fixes landed together, and the second is
the real one:

| | fix |
|---|---|
| `POSBOX_ORIGIN_CAP = 9000` | every left anchor is clamped, the same guard and the same reason as `EQ_ORIGIN_CAP`. A trade longer than the cap draws from the cap. Cosmetic loss; the alternative is the script dying. |
| the STRANDED HANDLE | a primary can close and reopen on ONE bar — a stop and a resting limit filling together. Neither *flat now* nor *flat last bar* held, so **neither** the open branch nor the close branch fired: the box handle and `entryBar` stayed pinned to a dead trade, and each further same-bar flip pushed the anchor further back. `pbFlip` now makes a flip an explicit close **then** open, in that order. |
| `f_isRec` in the fill loop | a recovery exit was being banked against the PRIMARY's `p.t1`, so a recovery closing in profit painted the primary green — the same blend `f_primarySize` exists to prevent. |

⚠ **The stranded handle is a LATENT BUG IN `mpc_strategy.pine` TOO** — it is the shared drawing
code, not anything the recovery leg added; the recovery leg only perturbed the run into reaching
it. It has not been fixed there, because that file is LIVE-adjacent and the change deserves its own
pass. ⚠ **The ordering inside `f_posBox` is now bank → close → open → grow, and that order is
load-bearing**: with open running first, a same-bar exit was banked as a fill on the trade that had
just replaced it.

🔴 **AND THEN THE ANSWER TO THAT CHECK CHANGED WHAT THIS FILE IS FOR. TRADINGVIEW CANNOT RUN THE
RECOVERY RULE, AND ITS P&L IS NOT THE RULE'S P&L.** A Pine strategy holds **one net position** and
has no hedge mode: an entry opposite the open position REVERSES it. So when a recovery is open and
the primary enters the other way, Pine closes the recovery to make room. ⚠ **The direction of the
damage is the opposite of what it sounds like — the PRIMARY is never blocked; the RECOVERY is the
leg that dies**, cut at the primary's entry price instead of at its own stop or trail. That was the
first thing asked and the first thing checked.

MEASURED on Aaron's Sept-2025 → Aug-2026 M15 chart, from the two chart-data exports in `engines/`
(`VANTAGE_XAUUSD, 15_09390.csv` recovery off, `…_adf26.csv` on): **25 primary entries on identical
bars in both runs** (7 long, 18 short — the leg disturbs nothing), **8 recovery trades**, and **5
of the 8 meet an opposite primary entry — two of them inside 2 days, against a 4-day median hold.**

🔴 **The design error was mine and it was an ASSUMPTION, not a slip: this file's header asserted the
two legs could be open at once, and nobody checked the platform before the work was commissioned.**
The Python twin runs the recovery as its own independent book (`LossRecoveryEngine.run()` takes the
bars and the loss list and never asks whether the primary is in a trade), which is why its numbers
are better and why they are the ones to quote. ⚠ **MT5 does NOT have this limit** — separate OS
processes, separate magic numbers — so the Python model is the one that matches the live path.
**TradingView is the odd one out, not the reference.**

⚠ **A multi-year chart also cannot SHOW you an old trade.** Pine caps labels, lines and boxes at
500 each and deletes the oldest, so over ~20,000 bars of structure annotation everything older than
a few weeks is gone — primary trades included. Two consequences, both acted on 2026-08-19: the
recovery's entry markers and its stop are now **plots**, which are not drawings and are never
collected, so they survive across all history; and the reliable way to inspect any old trade is the
Strategy Tester's **List of Trades** tab, where clicking a row makes TradingView mark that trade
itself at no cost to the drawing budget.

🔴 **THE RECOVERY LEG IS DRAWN BY THE SAME CODE AS THE PRIMARY, NOT BY A PARALLEL COPY (2026-08-19,
Aaron: *"I want it to show just like how we show winning and losing trades... nothing should be
different"*).** `f_posBox` now takes the leg's size, its own running closed P&L and an `isRec` flag,
and is CALLED TWICE. Same bands, same drawdown shading, same entry triangles, same by-result
recolouring on close. ⚠ **The two legs are told apart by the LABEL'S HEAD TEXT (`▲ RECOVERY LONG`),
not by a different marker** — the same convention a B-Leg trade already follows. The recovery's
`t1` is its **lock price**, because "did it get back to +1R" is the question TP1 asks on a primary.

🔴 **THAT REWRITE ALSO CHANGED THE PRIMARY'S CHART, AND THE BUG IT FIXED WAS ALWAYS THERE: A WINNER
THAT NEVER CLEARED TP1 PAINTED AS A FLAT ORANGE LINE — i.e. it read as a SCRATCH.** Nothing banks a
band unless an exit price clears `p.t1`, and with `execTp1Pct`/`execTp2Pct` both at 0 (the shipped
default) the only exit is the runner stop, so any trade the trail caught below TP1 was drawn as
though it made nothing. It now paints green to its real exit. ⚠ **Expect the primary's chart to look
different after this even though no trade changed** — the drawing was wrong, not the book.

⚠ **A multi-year chart still cannot SHOW you an old trade, and giving the recovery the full
treatment means it INHERITS that.** Pine caps labels, lines and boxes at 500 each and deletes the
oldest, so over ~20,000 bars everything older than a few weeks is gone — primary trades included.
Two ways through it, and they are the answer to *"I'm not seeing any trades on the chart"*: the
Strategy Tester's **List of Trades** tab, where clicking a row makes TradingView mark that trade
itself at no cost to the budget; and turning OFF the drawing hogs (external structure, missed
setups, blocked-trade tags), which is what is consuming the 500. **The recovery's STOP is the one
exception and is deliberately a `plot`** — plots are not drawings and are never collected, so it is
the only thing that still shows where an old recovery locked and how far the trail carried it.

🔴 **THE FIRST THING TO CHECK ON A CHART, BEFORE ANY RECOVERY NUMBER IS BELIEVED: with
`recEnabled` OFF this file must reproduce `mpc_strategy.pine`'s book EXACTLY** — same trade count,
same net, same list. If it does not, one of those 30 substitutions is wrong and every recovery
figure is measured on a primary that is no longer the primary.

### The rule itself

Loss → wait for the opposing external CHoCH → market in (fills next open) → stop at the far end of
the break leg → **at +1R move the stop TO +1R** → trail each new confirmed swing → no target →
30-day backstop. Sized at 25% of a normal trade.

⚠ **`st.asl` / `st.ash` ARE the new swing's price on the bar `st.new_swing_low` / `new_swing_high`
fires** — that is how the trail reads a level without a second engine.

### Known divergences from the Python twin, to settle at parity time

1. **Overlapping recoveries.** `loss_recovery` in Python processes each loss independently, so two
   recovery trades CAN overlap. Pine has one `Rec` entry id, so a second loss while one is open is
   dropped. Count how often that happens before treating the two as equivalent.
2. **Fill model.** Python enters at the next bar's OPEN explicitly; Pine gets that from
   `process_orders_on_close = false`. Same intent, and it needs to be confirmed rather than assumed.
3. **`recWant` never expires**, matching Python. An arm with no CHoCH yet is a visible state, not
   a trade that fires late on stale intent.

**Everything measured about this rule, including that it does NOT reduce drawdown and does NOT
smooth the equity curve, is in `strategies/python/loss_recovery/CLAUDE.md`.** Read that before
quoting any figure off this chart.


🔴 **THE RULE THIS FORK DRAWS WAS SEARCHED ON 2026-08-19 AND NOTHING CHANGED — so the fork's
inputs are still the measured ones.** Nine stop placements and six exit ladders were replayed over
A+'s 62 real losses on 186,910 M15 bars, both legs costed. The shipped rule (break-leg stop, lock
+1R at +1R, trail confirmed swings) won. ⚠ **The one challenger that beat it on the headline — a
stop on the CHoCH BAR's own extreme, +24.4R against +16.2R on a 7x tighter stop — goes to −7.4R
once its five best trades are deleted, and holds for four bars.** ⚠ **Aaron's own idea (rest the
stop on the LOSING trade's entry) is 2.4x tighter and resolves in 43 bars instead of 294, exactly
as predicted, and loses 14R** — the primary's entry is a price the market has just been trading
around, so the stop sits in fresh congestion; median MFE falls 1.01R → 0.89R, which a 2.4x smaller
R should have RAISED. Full grid: `strategies/python/mpc_sos_fade/mpc_sos_fade_optimization.md` →
Run 24; the rule itself: `strategies/python/loss_recovery/CLAUDE.md`.
## The tied-extreme structure fix (2026-08-20) — all ELEVEN strategy files

Every `strategy(` file here embeds its own copy of the market-structure state machine, and all
eleven carried the same defect: when two bars print an identical extreme, the post-break rescan
anchors on the LATER one while the label sits on the EARLIER one, so the swing gets a second
permanent label. **The mechanism, the measurements and the reasoning live in ONE place —
`engines/market_structure/CLAUDE.md` -> *The 2026-08-20 tied-extreme fix*. Do not restate them
here.**

What matters for THIS directory:

🔴 **`mpc_recovery_strategy.pine` DEMONSTRATED THE HAZARD WHILE THE FIX WAS BEING WRITTEN.** It
was forked from `mpc_strategy.pine` on 2026-08-19 — one day before the fix — on the other machine,
so it arrived carrying the defect and had to be patched on the way in. **A fork-per-strategy layout
means a bug fixed in sixteen files can walk back in through a seventeenth that was cut from the
pre-fix source, and nothing fails when it does.** ⚠ **Before calling a cross-cutting fix done,
re-run the sweep AFTER pulling** — `grep -rl 'lowest_val' --include='*.pine' .` and count guards.

⚠ **NO STRATEGY'S TRADE BEHAVIOUR CHANGES, and that was measured rather than argued.** The guard
moves bar INDICES, never prices. Every consumer of those indices in these ten files was traced:
label positions, `mid_x`, and `_snS` — the Sniper Zone box's left edge. All drawing. **And the
one path that COULD have moved a price was checked and did not**: the guard also shifts
`last_conf_*_loc`, which bounds the opposite side's rescan window, so a wider window could in
principle find a new extreme. Replayed over 186,759 M15 and 400,000 M1 bars: **identical break
counts and ZERO break-leg price differences.** The bars the window gains sit inside the swing
base, between the two tied extremes, so their highs cannot beat an extreme already scanned.

⚠ **The `_export` twins were changed in the same pass, deliberately.** A strategy and its export
must stay byte-identical in logic or the export stops describing the strategy — and here the
export is the only way the gate can ever see this code.

🔴 **NONE OF THE TEN IS COMPILE-VERIFIED OR PARITY-GATED FOR THIS CHANGE.** `mpc_assistant.pine`
was pasted into TradingView and confirmed by Aaron; these ten were not, and no `compare_*.py`
has run on any of them. **Paste before trusting.**

---

## What lives here, and the one thing that decides it

A file is in this folder if its declaration is `strategy(`, and in `../engines/` if it is
`indicator()`. That is the whole rule, and it is mechanical on purpose. **Check the declaration,
never the filename**: `structure_engine.pine` reads like a strategy component and is an indicator,
and `smc_session_sweep_strategy.pine` had an `indicator()` twin next door under a near-identical
name until that twin was deleted on 2026-08-15.

⚠ **Every file here is half of a parity gate.** The `_export` twin is the instrumented copy a
`compare_*.py` diffs against its Python port, and it has to move with its parent — a change to
`mpc_strategy.pine` that does not land in `mpc_strategy_export.pine` makes the gate green about
a file nobody trades. `mpc_realign_strategy.pine` has **no twin at all**, which is why every
REALIGN number in this repo is a lab finding.

---

## 🔴 THE PROSE LIVES IN `docs/`, NOT IN THE PINE (2026-08-16, Aaron's call)

**A Pine file here is CODE. Its explanation lives in `docs/<family>.md`, and the Pine carries
a one-line pointer.** These files are 130–320 KB each and **a third of every byte was prose**,
so reading one to answer a question about its entry logic spent a quarter of a context window
on commentary that was not the question — sessions ran out of tokens inside a single file.

| | |
|---|---|
| where prose goes | `indicators/strategies/docs/<family>.md` |
| what stays in the Pine | line 1 licence, `//@version`, **1–2 line comments**, the anchors |
| the anchor | `// [doc N] <title>  -> docs/<family>.md` |
| finding one | grep the md for `## [N]` |

**One doc per FAMILY, shared by the parent and its `_export` twin.** The pair carried
near-identical prose; a doc per file would be two copies drifting apart — the exact failure
*parents ROUTE, children EXPLAIN* exists to stop. An entry in only one of the pair says so.

**3+ consecutive comment lines moved; 1–2 line comments stayed.** Those are inline labels on
the line they describe — 12% of the bytes, and moving them costs the Pine its legibility.

⚠ **DELETING AN ANCHOR IS NOT A TIDY-UP.** The anchor is what tells the next reader an
explanation EXISTS and where. A block whose anchor is gone is prose nobody will find again —
worse than the inline comment it replaced, which was at least in the way. Move a code block,
move its anchor.

⚠ **New prose goes in the md, not back into the Pine**, or the files grow back to what
they were. Over two lines and explaining rather than labelling ⇒ a new `## [N]` plus an anchor.

⚠ **Trailing comments were deliberately left** — 1.2% of the bytes, and stripping them means
parsing `//` out of lines that also hold string literals containing `//`. All of the win was
in the full-line blocks and none of the risk was.

⚠ **The safety argument is a byte-identity DIFF, not "comments cannot change behaviour."**
That second claim is true and is exactly the confident reasoning rule 22 exists so nobody has
to trust it. ⚠ **No parity gate was re-run — that is a gap, not a pass**: the gates need a
fresh TradingView export only a human can take, so this is proof about the SOURCE, not a run.
Numbers, method and the three tests that read these files: `../docs/INDICATORS_BUILD_NOTES.md`.

---

## 🔴 TOOLTIPS ARE PLAIN ENGLISH AND ONE OR TWO SENTENCES (2026-08-16, Aaron's call)

**A tooltip says what the setting DOES, in words a person can read at a glance.** They had grown
into paragraphs of measured history, parity warnings and rationale — hover one and you could not
tell what the toggle was for. All 663 were rewritten on 2026-08-16; numbers and method are in
`../docs/INDICATORS_BUILD_NOTES.md`.

**The rule for writing one:**

| do | do not |
|---|---|
| say what it does, and what Off does | recite what a sweep measured |
| name the unit and what 0 means | warn about parity with another file |
| one or two short sentences | explain why the default was chosen |

⚠ **The evidence did not go in the bin — it moved.** Measured results, the reason a default is
what it is, and every ⚠ about a sibling file belong in `docs/<family>.md` or the spec, which is
where a reader looking for *why* is already going. A tooltip is for a reader looking for *what*.

🔴 **A TOOLTIP IS HALF OF A CONTRACT — CHANGING ONE ALONE BREAKS A TEST.** The Pine tooltip and
the lab panel's `desc` in `strategies/python/<bot>/<bot>.meta.json` are ONE explanation, and
`test_bleg.py::test_the_meta_descs_are_the_pine_tooltips_verbatim` asserts four of them match
byte for byte. **It went RED on this pass, which is the test working** — 90 `desc` fields across
the three meta files were resynced in the same commit. Change a tooltip, change its `desc`.

⚠ **`label.new()` tooltips were deliberately NOT touched** — nine of them, the chart hovers like
TRADE BLOCKED that carry a live reason and a price. They are diagnostics, not settings, and
shortening them would delete the only record of why a setup was refused.

---

## THE INPUT PANEL CONTRACT — where a new toggle goes

**Aaron's standing rule, 2026-08-12.** Every strategy Pine here uses the SAME numbered
groups in the SAME order, so section 5 is Entry whichever file you open. A strategy that
has no fibs simply has no `9 · Drawing: Fibs` group — **the numbering does not close up**,
because the number is the address.

| # | group | what lives here |
|---|---|---|
| 1 | Confirmation Table | the JARVIS panel's own switches |
| 2 | Market Structure | swing/BOS/SOS drawing and labels |
| 3 | What trades | longs/shorts, risk %, sizing mode |
| 4 | What arms it | the trigger — sweep, divergence, band tap, confirmation candle |
| 5 | Entry | where the limit rests, and **everything that decides which zones exist** |
| 6 | Stop & targets | SL anchor, TP rungs, trail, time stop, breakeven |
| 7 | Filters | things that REFUSE a setup — HTF bias, final hour, minimum stop |
| 8 | Chart annotations | blocked / missed / position boxes / entry triangles |
| 9 | Drawing: Fibs | draw-only, ONE toggle, default OFF |
| 10 | Drawing: Sessions | draw-only, ONE toggle, default OFF |
| 11 | Drawing: Liquidity | draw-only |
| 12 | Debug | the last resort, and nothing a reader tunes on |

### Section 2 is FIXED — four toggles, same order, same defaults, every file

Aaron, 2026-08-12: *"On all of my strategies, the market structure should be the exact same…
There should always be four toggles… the only thing that should be on by default is show
external structure, nothing else."*

```
Show External Structure            ON
Show Internal Structure            off
Show Historic Internal Structure   off
Show Swing Point Labels            off
```

🔴 **`mpc_d_strategy.pine` HAD TWO OF THE FOUR, AND THE MISSING PAIR WAS A MISSING ENGINE
RATHER THAN A MISSING INPUT.** That file embeds only the EXTERNAL half of
`structure_engine.pine`, so there was nothing for an internal toggle to switch. Adding the
two checkboxes alone would have shipped exactly the hazard the deleted `REQUIRED` toggles
were: a control that looks like it does something. **The internal engine is ported in
instead** — 452 lines, taken from `structure_engine.pine` rather than from a sibling
STRATEGY, because the strategies' copy also seeds the External Fib (`i_confirmed_*`) and D
has no fibs. ✅ **Proven the right source rather than assumed: the two blocks were diffed
comment-free, and the only difference is those four fib-anchor writes plus `IFIB_GREY` and
`extBreakThisBar`.** ⚠ **It draws and decides nothing** — D reads no internal swing, so this
is annotation only and cannot move a trade. ⚠ `showSwingLabels` also shipped **ON** in D
against every sibling's off.

🟢 **`mpc_h4_sweep_strategy.pine` GOT THE SECTION TOO (Aaron's call, 2026-08-12), AND IT IS
THE ONE FILE WHERE THE ENGINE DECIDES NOTHING.** That file had no structure engine at all —
it trades an H4 liquidity sweep confirmed by a candlestick pattern, consuming no swing, no BOS
and no SOS — so honouring "the exact same" there meant porting ~1,000 lines of engine purely to
draw with. It was recorded as an open decision rather than skipped, and answered *do it*.

**Lifted from `mpc_d_strategy.pine`, not from `structure_engine.pine`**, on purpose: D's copy is
the STANDARDISED one (external half + the fib-free internal port above), so taking it means all
five files share one block rather than four sharing one and H4 sharing a fifth. 880 → 1,921
lines. ✅ **Checked mechanically rather than by eye — zero duplicate top-level declarations and
zero name collisions with H4's own identifiers** (`st`, `ph`, `pl`, `bullColor`, `majorLength`,
`f_swingCol`, every `i_*`), and the block was confirmed self-contained first by grepping it for
`exec*` / `d[A-Z]*` references, which returned nothing.

⚠ **It draws and decides nothing, and the file says so at the block AND at the section.** Flip
any of the four toggles and H4's trade list is unchanged. **The comment names the condition that
would end that**: if a future rule in this file starts reading `st`, it stops being a drawing
block and the toggles stop being free — say so at the rule, because nothing else will.

⚠ **The compile-token cost is real and unmeasured.** H4 more than doubled; only a paste can say
whether it clears CE10117. If it does not, this block is the first thing to cut, and cutting it
costs a chart annotation rather than a trade.

### Trade longs / Trade shorts — every file, both ON

🔴 **`mpc_h4_sweep_strategy.pine` had NEITHER.** Added, and the wiring is the interesting
half: a refused side is **block code 5, numbered last and ranked FIRST** (a code is a wire
format `px_blk` carries into exports already on disk, so an existing number can never be
renumbered — only its place in the chain moves).

⚠ **A DISABLED SIDE DOES NOT CONSUME THE H4 WINDOW, unlike every other refusal in that
file, and the asymmetry is deliberate.** H4 allows one setup per H4 window and burns it on
any trigger, refused or not — which is right for a stop-too-tight refusal (about that
setup) and wrong for a direction switch (about every trade on that side). Burning it would
have removed LONGS that happened to share a window with a short, so "longs only" would not
have been the long book. **That is the trap this repo keeps meeting: a filter that quietly
changes the population it was not aimed at.**

### The confirmation table

Present and **default OFF** where the strategy reads one — `mpc_strategy.pine` and
`mpc_b_leg_strategy.pine`. **Absent from BOS, D and H4 by Aaron's own instruction**, because
none of them has a table for it to show; already the case in all three, so nothing was
removed.

---

### A `strategy()` ARGUMENT CANNOT BE AN INPUT — raise it permanently and gate it in code

**2026-08-16, `mpc_strategy.pine` + its export twin.** The scale-in toggle (`execScaleIn`, default
OFF) needs `pyramiding > 0` to place a second entry on an open position. `strategy()` is evaluated
**once at compile time**, so `pyramiding` can never read an input — the only options are to raise it
permanently or not to have the feature. It is **0 → 4** in both files (the base entry plus
`execScaleAdds`, whose `maxval` is 3).

🔴 **A RAISED CEILING IS SAFE ONLY IF SOMETHING ELSE REFUSES THE STACK, AND THAT WAS CHECKED RATHER
THAN ASSUMED.** All four `strategy.entry` calls that OPEN a trade in that file (two A+, two B-LEG)
are gated on `strategy.position_size == 0`, so the base entry cannot stack on itself whatever
`pyramiding` says; the only other entries are the `L-ADD*` / `S-ADD*` ids, each gated on
`execScaleIn`. **With the toggle off the file trades exactly as before** — verified on the Python
side as a bit-identical OFF path, which is the half a paste cannot show you.

⚠ **`strategy.exit` and `strategy.close` MATCH ONE ENTRY ID.** A pyramided position is N entries, so
`from_entry = "Long"` protects the base and nothing else — every add needs its own exit AND its own
close on each force-close path, or an add sits in the book with no stop while the base leaves on an
opposite SOS. That is a naked pyramid against fresh opposite structure, and it is the worst state
this class of feature can produce.

⚠ **The three inputs are appended after the LAST input in the file and carry `group = G6`.** The
group decides which panel BOX they display in; DECLARATION ORDER decides which saved chart value
they inherit. Putting them beside the other stop settings would have re-keyed every later bool, int
and float on Aaron's live chart. Prose: `docs/mpc_strategy.md` → `## [174]`–`## [178]`.

⚠ **NOT COMPILED, and there is no `cfg_*` column for any of the three**, so `compare_strategy.py`
cannot configure a scale-in run — the gate would go green while comparing two different strategies.
Measured result and the open design question (the add trigger is arithmetic only — no BOS, no
retest): `strategies/python/mpc_sos_fade/mpc_sos_fade_optimization.md` → Run 19.

---

### The adds got a TAKE PROFIT, and it is the one default here set AGAINST its measurement (2026-08-19)

`execScaleTpMode` ∈ {`"Ride"`, `"Prev week H/L"`, `"Prev day H/L"`, `"H4 H/L"`}, default
**`"Ride"`** — i.e. no target, which is what the measurement says. Until now the scale-in lots had no exit of their own — they rode `lStop` with
the base trade and closed pro-rata with its ladder.

**It rides the EXISTING per-add exits rather than adding new orders**, which is what keeps the
change small:

```
strategy.exit("L-AX1", from_entry = "L-ADD1", stop = lStop, limit = lAddTp)
```

One extra argument makes each add a proper OCO bracket — stop or target, whichever price reaches
first. **A `na` limit is no limit**, so `"Ride"` leaves all eight of those calls byte-identical to
what they were.

`lAddTp` / `sAddTp` require the level to be **unmitigated** (`not w_hMit` / `not d_hMit` /
`not h4HighSwept` — a swept level is not somewhere to aim at, it is a price we are past) **and**
beyond `lAddLastPx`, the price the newest add was bought at, so every lot it closes is closed in
profit. `lAddLastPx` is latched from `strategy.opentrades.entry_price()` on the bar the add fills.

⚠ **The NEWEST add, not the worst-priced one.** In `Trail` mode adds fill at successively higher
prices because the ratchet only moves one way, so the two are the same level — and Pine can name the
newest fill without keeping a running extreme. Measured equal on the full book rather than argued.

🔴 **`lAddN` IS NOT DECREMENTED WHEN THE ADDS BANK.** The ladder is capped on adds BOUGHT, so
handing the slot back would let a trade add again after banking — "scale in and out repeatedly",
a different strategy that nothing has measured. The Python mirror zeroes its lots in place rather
than emptying its list, for exactly this reason, and has a test pinning it.

🔴 **EVERY TARGET LOST TO RIDING, AND IT SHIPS ON ONE ANYWAY.** Ride **194.15R**, prev week
168.51R, prev day 157.57R, H4 146.09R — an ordering that tracks how OFTEN the target fires (0, 16,
25 and 47 banks), reproduced independently by a flat-risk-multiple control. ✅ **It shipped for ONE DAY on
`"Prev week H/L"` and was reversed to `"Ride"` on 2026-08-19 (Aaron).** He picked the target
deliberately, wanting certain money off the runners, and on the number he was given — a 4.38R gap,
INSIDE this strategy's 15.06R jitter — that was a sound trade. That number came from the run with
the live-bar bug in it; **the true gap is 25.64R, OUTSIDE the jitter**, and on the real figure he
reversed within a minute. ⚠ **A wrong measurement does not arrive looking wrong — it arrives as a
reasonable-looking number and quietly buys a judgement call, and the decision outlives the
correction unless somebody goes back for it.** Full numbers:
`strategies/python/mpc_sos_fade/CLAUDE.md` → *The adds got a TAKE PROFIT*.

🔴 **THE `limit` MUST BE COMPUTED AT THE BAR'S CLOSE, NOT RE-RESOLVED AS PRICE TOUCHES IT.** Pine
gets this right for free — `strategy.exit(..., limit=)` rests an order that is live on the NEXT bar
— and the Python mirror did not, which made `"Prev day H/L"` and `"H4 H/L"` bank **zero times in
eight years** while resolving 1,804 and 2,438 valid targets. Day and H4 levels die on a **WICK**,
the engine steps before the strategy sees the bar, so the level was already mitigated on the exact
bar the order would have filled. ⚠ **Week levels die on a CLOSE through, so weekly was immune and
the defect was invisible on the only mode anybody was watching.**

⚠ **A FIFTH `cfg_*` COLUMN LANDED WITH IT** (`cfg_scale_tp`), for the reason the four before it
exist: a trade-affecting input with no column is invisible to `compare_strategy.py` **by
construction** — the gate does not go quiet, it goes WRONG. ⚠ **The comparator decodes ABSENT as
`"Ride"`, which is the opposite of how `cfg_scale_in` is read.** "Absent ⇒ off" is safe there
because that feature shipped OFF; this one ships ACTIVE, so a config-default fallback would replay
every older export with its adds banking at a weekly level the exported Pine never looked at.

🔴 **NOT GATED YET.** No export carries `cfg_scale_tp`, so `compare_strategy.py` has never checked
this path. Rule 22 is unsatisfied until a fresh export lands with the column and the gate passes.

### The scale-in gained a MODE, and the export gained the columns it should have had first

**2026-08-17.** `execScaleMode` ∈ {`Trail`, `BOS retest`}, defaulting **`BOS retest`**;
`execScaleAdds` 2 → 4 (maxval 3 → 4) and `execScaleCapX` 1.0 → 2.0. `pyramiding` 4 → **5** (base
entry + 4 adds), which is still compile-time and still cannot be an input. `L-ADD4`/`S-ADD4` carry
their own `strategy.exit` AND their own `strategy.close` on both force-close paths — `from_entry`
matches ONE id, so a missed close leaves a naked pyramid against fresh opposite structure.

🔴 **THE FOUR `cfg_*` COLUMNS ARE THE POINT OF THIS PASS, NOT THE MODE.** The feature shipped on
2026-08-16 with NO export column at all, so `compare_strategy.py` could not configure a scale-in run
— and a trade-affecting input with no column does not make the gate quiet, it makes it **WRONG**,
diffing two different strategies and blaming whichever code the symptom lands in. Three prior
instances: `execRunnerTrail` (2026-07-26), `cfg_min_stop` (2026-07-30), `eqExemptFvg` (2026-08-06,
three days and a misdiagnosis). All four inputs are carried, not just the on/off switch.
⚠ **`cfg_scale_adds` / `cfg_scale_cap` are plotted RAW, never packed** — any pack has to round, and
a silently rounded cap mis-sizes every add.

⚠ **The new `input.string` is appended AFTER the last input of any type.** The file's last
`input.string` is ~line 95, so nothing already saved is re-keyed and no chart needs a settings
reset. ✅ `check_active_order.py` passes on all twelve strategy files; the export twin re-diffs to
exactly line 5's title.

### The add is a RESTING LIMIT now, and the market order it replaced broke the guarantee

🔴 **2026-08-18. The 2026-08-17 defaults above are REVERSED and Run 20 is VOID.** The add was
issued as a plain `strategy.entry(qty = ...)` — **a market order, which TradingView fills at the
NEXT bar's open** — while the Python booked it at the price its rule triggered on. The parity gate
caught it on `px_closed_r` at bar 1356 (2025-10-21): py **27.07R** vs pine **22.03R**, one trade,
the largest runner in the book, every decision field before it agreeing.

**What changed in both Pine files:**

| | before | after |
|---|---|---|
| `BOS retest` | detected the touch, fired a MARKET order | `strategy.entry(..., limit = _lim)` — a real resting limit |
| `Trail` | market (correct, it has no level to rest at) | unchanged |
| `lAddN` | incremented at PLACEMENT | incremented on the **FILL**, detected by `strategy.position_size` growing |
| `L-AX*` / `S-AX*` | gated on `lAddN >= n` | placed **unconditionally**, so a limit filling mid-bar is never unprotected |
| stale orders | — | **`strategy.cancel` on every add id once flat** ([doc 182]) |

🔴 **A LIMIT ORDER OUTLIVES THE POSITION THAT PLACED IT**, which is why the cancel block is a
positive check on being flat rather than a hook on each exit path — this strategy closes on a stop,
three ladder rungs, an opposite SOS and a time stop, and an ignore-list of exits is one new exit
away from being wrong.

🔴 **The order TYPE was the guarantee.** The affordability rule sizes an add against the price it is
BOUGHT at; a market order is sized at one price and filled at another. **MEASURED: as a market
order the adds turned winners of +3.41R and +1.34R into losses of −2.50R and −2.15R, against an
un-scaled worst of −2.06R over the same 182 trades.** A resting limit closes it — the fill price is
known before the order is sent, and price that gaps through a buy limit fills BETTER.

**Defaults now: `execScaleMode` `"Trail"`, `execScaleAdds` **3**, `execScaleCapX` **0.5**.** ⚠ The
add count is 3 rather than 4 for a SAFETY reason — `Trail` is a market rule by nature and still
carries a small trigger-to-fill gap, measuring zero breaches at 3 and −2.24R/−2.73R at 4. ⚠
`execScaleAdds` keeps `maxval = 4` and `pyramiding` stays 5, so the ceiling is unchanged and only
the default moved.

✅ **PARITY GREEN, exit 0** on a fresh 20,799-bar export taken at `cfg_scale_in=1 /
cfg_scale_mode=1 / cfg_scale_adds=4 / cfg_scale_cap=2` — one that genuinely exercises the feature
rather than reading all zeros. **The same gate on the same schema was RED before the fix**, which is
what makes the green worth something. Full grid and the void banner:
`strategies/python/mpc_sos_fade/mpc_sos_fade_optimization.md` → Run 21.

---

## PHASE 1 — the trade annotations, and the one piece that CANNOT be ported

The other half of the standardisation: *"as I move to strategies, nothing seems different other
than the logic of the strategy."* Same blocked marker, same missed callout, same position box,
same entry triangles, on every file.

| annotation | A+ | B-LEG | BOS | D | H4 | M15 |
|---|---|---|---|---|---|---|
| position box / result bands | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ **new** |
| entry callout, recoloured on close | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ **new** |
| **entry triangles** | ✅ | ✅ | ✅ | ✅ **new** | ✅ | ✅ **new** |
| **blocked-setup tag (pink)** | ✅ | ✅ | ✅ | ✅ | ✅ **new** | ✅ |
| missed-setup callout (2-of-3) | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |

**D gained the entry triangles.** `plotshape` is a GLOBAL-SCOPE call, so it cannot live inside
the fill block and the fill edge is written out at top level instead — the SAME test the fill
block uses, so a triangle can never appear on a bar the tracker did not treat as a fill. Gated
on `execShowPosBox` like A+, because the triangles are part of the position drawing.
⚠ **They are not redundant with the boxes**: a scratch paints a risk block a few pixels tall and
reads as no trade at all, which is exactly when you need to see where it opened.

**H4 gained the blocked-setup tag.** It has carried the refusal CODES since its export twin
landed and had nothing on the chart that drew them. It reads `hTrigCode` — already written at
decision time — and re-derives nothing, so the tag and the export's `px_blk` cannot tell
different stories.

🔴 **The side had to be RECORDED rather than inferred, and `mpc_d_strategy.pine` already paid for
learning that.** D's tag read direction off the SOS on the same bar, correct only while every
candidate arrived on one — and the moment a second entry mode existed, every candidate drew as a
SHORT. Here the equivalent shortcut is reading `trigShort`, a per-bar local: right today, silent
the day a refusal is reported from anywhere but those two blocks. `hTrigDir` is written beside
`hTrigCode` instead.

⚠ **No dedupe, and that is not an omission.** A trigger fires at most once per H4 window
(`firedWindow`), so one refusal is already one bar. A+ needs its `sosBar + code` key because a
setup there can stay refused for twenty consecutive bars. ⚠ **`hTrigBar == bar_index` is what
scopes it** — the four `hTrig*` fields are `var` and keep the last trigger's values for ever.

### 🔴 The missed-setup callout is NOT portable to BOS, D or H4, and this file already said so

A+'s callout scores a **2-of-3 confluence sequence** — arm (sweep or divergence), SOS, then the
retrace zone — and reports which one was missing. **`mpc_bos_strategy.pine` DELETED those four
inputs on 2026-07-31 with the reason written down**: *"The BOS arm is a break of structure, so
there is no sweep→SOS clock to bound and no 2-of-3 sequence to score."* The same is true of D (a
three-SOS sequence with no partial state) and of H4 (a sweep window plus a confirmation candle —
two facts, not three).

**So this is a DESIGN decision per strategy, not a port**, and inventing one would have shipped a
callout naming confluences those files do not have — the exact mistake the B-LEG block tag was
built to avoid (*"a shared annotation is shared at the DISPLAY, never at the reasons"*).

⚠ **And the cost is not symmetric.** `mpc_bos_strategy.pine` has hit **CE10117 twice**, is the
largest file here at 4,384 lines, and its export sits at **60 of Pine's 64 plots**. Adding ~90
statements of `MissW` machinery to it, unverified, immediately before a five-file paste is the
wrong trade — a file that will not compile is worse than a file missing one annotation.

**What each would need, so the decision is a decision rather than a blank:**
- **BOS** — a break armed a leg, the limit rested, and price never reached it (or the leg died
  first). One state, not three: the honest callout is *"armed, never filled"* plus the reason.
- **D** — the shakeout completed and the with-trend SOS never came, or came stale. `dCandDir`
  and the three `dCand*` gate values are already recorded for every candidate, so the data is
  there; only the drawing is missing.
- **H4** — a sweep window opened and no confirmation candle fired in it. Cheapest of the three,
  and the one whose absence is least visible, since `firedWindow` already bounds it.

### The rule that decides the section

**Ask what it CHANGES, never what it is ABOUT.** A setting goes in 3-7 if it can move a
trade, and in 8-12 if it can only move a pixel. This is the whole contract, and it was
chosen over the obvious alternative (group everything named "FVG" into an FVG group)
deliberately.

🔴 **THE FAIR VALUE GAP GROUP IS WHY.** In `mpc_strategy.pine` it reads as a drawing group
and it is not: `Show FVG (REQUIRED — feeds entries)`, both `FVG Min Gap` floors, the
middle-bar close test, `Max Active FVGs` and `keep until broken` **all change WHICH GAPS
EXIST, and therefore which entries fire** — six of its seven inputs. `eqExemptFvg` does the
identical thing from inside `Liquidity Levels`. Grouping by name would have demoted six
trade-deciding knobs to the bottom of the panel alongside the fib colours, and nothing
would have errored. **They belong in `5 · Entry`, with the entry rules that consume them.**

⚠ **The converse is equally load-bearing: a group named for an OBJECT invites settings that
merely mention that object.** "Fair Value Gaps" attracted the entry rules' detection
constants and a liquidity exemption because they all say FVG. Naming a group for a JOB —
"Entry" — gives a new toggle exactly one honest home.

### Collapsing, and why it is the same edit as grouping

⚠ **Do not regroup a file and collapse it in two passes.** 76 of A+'s 156 inputs are fib,
session and liquidity sub-settings Aaron has said he will never configure; each family
collapses to ONE draw toggle with the rest hardcoded at today's values. Moving them into
new groups and then deleting them is the risky work done twice, on the panel that decides
what he trades. **One pass per file: collapse, then group what survives.** A+ goes
156 → about 75.

⚠ **Collapse means HIDE THE SUB-SETTINGS, never remove the on/off.** Aaron, 2026-08-12:
*"I don't even need to see the time frame or the colors of the sessions. It could just be
one button that says show sessions… I'll never configure them."* Both draw toggles default
**OFF**.

### 🔴 The trap that makes this dangerous rather than cosmetic

**Two of the "show X" toggles are not display toggles at all, and their own titles say so:**

```
Show External Fib (REQUIRED — SL/TP/entry levels)
Show All Liquidity Levels (REQUIRED — arms sweeps)
```

`showFibo` gates the block that computes `fiboP1..fiboP7` — every entry, stop and target
price in the file. Default that OFF as part of a drawing group and **the bot silently stops
trading.** Each therefore SPLITS in two: the calculation is hardcoded permanently on and
stops being an input at all, and the new draw toggle guards only the drawing. Verified
before relying on it — the fib block is pure arithmetic for its first ~80 lines and draws
through per-level flags further down, so the seam is clean.

⚠ **`marketStructureOnly` ("Hide Everything Except Market Structure") is the same hazard by
another route** — it force-disables `showFibo` and `showFVG`, so ticking it stops the bot
trading. It becomes a DRAWING switch, which is what its name already claims.

⚠ **`showDiv` (`Track RSI divergence`) looks like a third one and must NOT be hardcoded** —
it is packed into `cfg_bits` bit 1024 in the export, so removing it breaks
`compare_strategy.py`. It stays an input and is hoisted into `4 · What arms it`.

### The Pine mechanics this collides with

⚠ **Reordering `input.*` declarations RESETS saved chart values** — TradingView keys them
off declaration order within each type. This pass therefore costs exactly ONE
"Reset settings to defaults", which is only safe because the file DEFAULTS are what Aaron
runs. **That is what `indicators/docs/PINE_INPUT_DEFAULTS.md` is for**: it snapshots every
input's type, per-type ordinal, group, title and default BEFORE the pass, so the reorder is
proven cosmetic by re-dumping and diffing rather than argued to be.

⚠ **Group ORDER is the order each group's FIRST input is declared**, so controlling the
panel means controlling declaration order — retagging `group =` alone cannot do it. The
answer is one consolidated input block near the top of the file, which the execution inputs
already use (2026-07-28). Moving a declaration EARLIER is always safe; moving it LATER than
its first read is a compile error.

⚠ **An input referenced by another input's `active =` must stay declared before it.**

🔴 **THE REORDER BROKE THAT RULE IN `mpc_bos_strategy.pine` AND IT ONLY SHOWED UP ON THE PASTE
(`CE10272: Undeclared identifier "bosUseFvg"`, 2026-08-12).** `bosEntryFib` carries
`active = not (bosUseFvg and execReqFVG)` and the collapse landed it ABOVE both of them. Fixed by
moving `bosEntryFib` BELOW the whole gap block — which is where it reads better anyway, since its own
title is *"Fallback entry level"* and it is the fallback FROM that block. ⚠ **The same defect was in
`mpc_bos_strategy_export.pine`**, because the twin is a copy: **a compile error in a parent is a
compile error in its export, and only the parent gets pasted.** ✅ **The move shifts NO saved value
and needs no extra reset** — proven rather than assumed: the four inputs it crossed are all `bool`
and it is a `string`, so every per-type ordinal, default and title is identical to before the fix.

✅ **THE CHECK NOW EXISTS AND HAS BEEN RUN — `indicators/tools/check_active_order.py`, 2026-08-14.**
For each `active =`, every identifier in it must be declared at a lower line number than the input
carrying it. **All twelve files in this folder pass.** Run it after any panel edit; it found the
export twin above, which nobody would have pasted until much later.

⚠ **Its first two versions BOTH reported four false failures, and the shape of them is the
warning.** Version one ran the `active =` expression on past its own argument and swallowed the
next one, so `step = 0.05` read as a dependency on an identifier called `step` — which a local
variable 4,900 lines away happened to be. Version two stopped at the argument boundary and still
failed, because `active = execRunnerTrail != "Fixed step"` puts the word inside a STRING. **A
checker that flags the four biggest files while passing the small ones is one you conclude is
broken and stop running** — and the second reading would have been right for the wrong reason,
since the files really were clean. Strings are stripped before identifiers are extracted now.
✅ **Watched RED by mutation rather than trusted**: swapping `execShowPosBox` and its own
`active =` dependant in a throwaway copy reddens exactly that pair and nothing else.

### 🔴 "Trades on chart" CANNOT be defaulted from code, and it is the one thing on the Style tab that matters here

Aaron, 2026-08-12: *"Under the styles tab, I don't ever want trades on charts enabled. It should
always be unchecked. Can you make that a default button on everything, please?"*

**It cannot be done in Pine, and this is recorded rather than re-litigated because it looks like
it should be possible.** Checked against TradingView's own reference and the Strategies FAQ:
`strategy()` has no argument for it, and the FAQ says outright that trade-marker visibility is a
chart-side UI setting with no Pine equivalent. `display = display.none` works on a `plot`; the
trade markers are not a plot — TradingView draws them itself from the order log, and there is no
way to place an order without one.

**So this is a per-chart-instance UI action, and the good news is it is nearly a one-time one.**
The setting lives with the script INSTANCE on the chart, not with the source, so:

- Saving edited code in the Pine Editor updates the instance in place and the unticked box
  **survives**. Ordinary iteration does not undo it.
- It comes back ON only when the script is added to a chart FRESH, or when you hit
  **"Reset settings to defaults"**.

⚠ **Which is exactly what the 2026-08-12 panel reorder costs, once, on every one of these files** —
so untick it in the SAME visit as the reset, or the next paste is the one that surprises you.

**It applies to all six strategy files, `smc_session_sweep_strategy.pine` included**, even though
that file was out of scope for the panel pass.

⚠ **The reason it matters is not tidiness — it is DOUBLE-DRAWING.** Every strategy here already
draws its own trade: the position box with its result bands, the entry triangles, the TP tags and
the result label. `execShowPosBox`'s own tooltip says it *"replaces TradingView's built-in trade
markers"*, and it only replaces them if the built-in ones are off. Leaving both on puts two
different renderings of one trade on the same candles, at two different exit prices whenever a
partial filled.

---

## THE ANNOTATION PALETTE — one result, one colour, `mpc_strategy.pine` is the standard

Aaron, 2026-08-12: *"the colors of the labels that show if a trade had won or lost, if it broke
even, if it was blocked, what was the max drawdown, where the price went, the long and short
positions — all those colors are not consistent across all the pines. They should be the same
colors. Use MPC, the A+ strategy as a standard."*

**Every colour a TRADE is drawn in is copied from `mpc_strategy.pine`. Change a value by changing
it there first and copying it down** — never by picking one in a fork.

| slot | colour | where |
|---|---|---|
| WIN | `#26A69A` @12 label, @0 leader | closed winner's callout |
| LOSS | `#EF5350` @12 / @0 | closed loser |
| **BREAKEVEN** | `#FF9800` @12 / @0 | inside the ± band — **orange, never yellow** |
| OPEN | `#787B86` @12 / @0 | result not known yet |
| risk / adverse excursion | `#EF5350` @88 | how far it went against you — behind everything |
| reward, by rung | `#26A69A` @55 / @70 / @82 | TP1 / TP2 / TP3 — the gradient IS the legend |
| entry markers | `#26A69A` @0 / `#EF5350` @0 | long / short triangles, solid |
| TP tags + their lines | `#26A69A` @40 | one colour for all three |
| blocked setup | `#FF2E9A` @12 / @0 | pink |
| label text | `#101014` @0 | dark on every bright fill |

### 🔴 A+ carries TWO palettes and that is what the forks got wrong

The one real finding of the pass. A+ has a **TABLE** palette (`#00E676` / `#FF5252` / `#ffde59` —
the JARVIS status panel's bull / bear / armed text) and a **POSITION** palette (`#26A69A` /
`#EF5350` / `#FF9800` — every trade drawing). They are different greens and different reds on
purpose.

**`mpc_d_strategy.pine` applied the TABLE palette to its TRADES.** A D winner drew in the green
A+ uses for a table row and never in the green A+ uses for a winner; its breakeven was
`#ffde59`, which is A+'s *"Armed"* highlight. Nothing was wrong with either palette — the file
was reading the wrong one, and both are still there. Its state panel keeps the table colours,
which is where they belong.

⚠ **`mpc_h4_sweep_strategy.pine` had NO colour constants at all** — every value was a hex literal
at its use site, which is exactly why it drifted without anyone being able to see that it had.
The hues were mostly already A+'s; the **transparencies** were not, so the same green read as a
different shade per file. It has a named block now.

⚠ **Three deliberate behaviour corrections came with it, all label-only.** D coloured its open
callout by DIRECTION (A+ paints it grey — the result is not known yet, and direction is already
in the label text and the triangle); D never recoloured its leader LINE on close, so a grey line
ran into a green label; and D used white label text where every other file uses `#101014`.

🔴 **H4 had NO breakeven state, so a +0.02R scratch drew as a full WIN and a −0.02R scratch as a
full LOSS** — the two loudest colours on the chart for a trade that made nothing. It grades
against a band now. ⚠ **The band is a CONSTANT (`H4_BE_BAND = 0.15`), not an input**, because
adding an input resets every saved value on the chart and it has never been tuned here; A+
exposes it as `execBeBandR`. Promote it when the rest of H4's annotations are brought up.

### ⚠ The one collision, left OPEN rather than silently resolved

**A+ itself uses `#FF9800` for two different things: BREAKEVEN and the missed-setup callout.**
H4 then uses the same orange for its trigger line and label. They are different objects in
different places, so it is not wrong — but on a chart showing both, orange has two meanings.
Recorded rather than fixed, because resolving it means changing A+, which changes the standard
and every chart running it. **Aaron's call, not a tidy-up.**

### What is NOT in this pass

Colours only. **D still draws no entry triangles and H4 still has no blocked-setup tag or
missed-setup callout** — those are missing ANNOTATIONS, not wrong colours, and they belong with
the Phase-1 annotation work. A palette pass that invented them would have hidden how much of the
annotation set is still absent.

⚠ **Nothing here touches an input, so no saved chart value moves and no panel order changes** —
this is safe to paste onto a chart already carrying the panel rebuild.

---

## The session sweep gets an EXPORT TWIN, stage 3 of six (2026-08-17)

`smc_session_sweep_strategy_export.pine` — the parent byte-for-byte, plus one appended block of
59 transparent `editable = false` plots. It draws nothing and trades identically; the series exist
only to leave the chart through *Export chart data*. Built because Aaron asked for a Python port
and a sweep, and **`docs/STRATEGY_WORKFLOW.md` stages 3 and 4 did not exist for this file** — the
two CSVs already on disk are TRADE LISTS, which is the right idea and the wrong artifact: the gate
compares per-bar DECISIONS, not fills.

🔴 **PINE ALLOWS 64 PLOTS PER SCRIPT AND THE PARENT ALREADY SPENDS 2. The first draft was 70 and
would not have compiled** — a ceiling you meet on Aaron's screen, one paste cycle later, not here.
**What got cut is the rule worth keeping: only things that can MOVE A TRADE are exported.** The
comparison-timeframe stream (`cmpDir`, `cmpShifts`, `sosCmpTf`), the SOS marker price and the
confirmation LEVEL are annotation — a parity failure over any of them would be a failure over a
chart drawing. Everything DERIVABLE went too: position size is quantity × direction, the leg id is
the `newLeg` bit counted up. Small integer inputs are packed two to a plot, safe because each
field's `minval`/`maxval` bounds it below its neighbour's multiplier.

🔴 **THE REFUSED SIDE IS EXPORTED, NOT JUST THE TAKEN ONE** (`px_ent_l`/`px_ent_s`, `px_blk_l`/
`px_blk_s`, both zone pairs, both distances). **A port that agrees on the trades and disagrees on
the refusals will diverge the first time an input moves — which is exactly when a sweep is
running.** Gating on fills alone would pass a port that is wrong everywhere the shipped config
happens not to go.

⚠ **A STRING CANNOT CROSS A CSV**, so the session and hour windows are exported as the DECISION
they produced (`inAsia`, `inWinLdn`, … packed into `px_state`) rather than as their text. That is
the better half of the trade: the port is gated on what the window DID, not on whether it parses
`"0200-0500"` the same way, so a timezone bug shows up as a disagreeing bit instead of hiding
behind two strings that match.

⚠ **`*_shifts` IS A COUNTER AND THE TWIN EXPORTS IT AS ONE.** A boolean read back through
`request.security` stays true, so "it JUST shifted" is only recoverable by comparing the count with
its own previous bar. A port that exports or consumes a flag confirms on every bar after the first.

⚠ **THE TWIN IS A SEPARATE TRADINGVIEW SCRIPT AND STARTS AT THE FILE'S DEFAULTS, not at whatever
is saved on Aaron's chart.** That is why every trade-moving input is in the CSV: the harness reads
`cfg_*` and states the config it was gated at rather than assuming one. ⚠ `execFixedQty` is
deliberately absent — a sweep never leaves "Risk % of equity", and `cfg_enum1` carries the MODE, so
a CSV taken in Fixed-contracts mode is DETECTABLE and can be refused rather than silently gated on
a size the harness cannot see.

## The sweep-reclaim strategy was BUILT AND ABANDONED on the same day (2026-08-17)

`smc_sweep_reclaim_strategy.pine` — sweep the previous session's level, close back through it
within three candles on a candle whose body agrees, target the session's other end. 347 lines,
16 inputs, no `request.security`. **Deleted the day it was written, at Aaron's call, and recorded
here so nobody proposes it a third time.**

**Why it was killed, in his words:** *"it does not have much confirmation to know we're ready to
change direction after the sweep. A pattern is not enough. Misleading candle patterns could print
at highs all day long and simply blow past the sweep levels."*

🔴 **THE OBJECTION IS THE ARGUMENT FOR THE SHIFT OF STRUCTURE, AND THAT IS THE FINDING WORTH
KEEPING.** "A candle body is not enough evidence that direction has changed after a sweep" is
precisely the job `pbRequireConf` does in `smc_session_sweep_strategy.pine`. The idea was not a
dead end — it was a rediscovery of why the course's rule exists. ⚠ **It was abandoned on an
impression, never compiled and never run**, which is the same move that kept the +180% alive: the
chart looked good so it was believed, then another chart looked bad so it was not. Neither was a
number. Say so if it comes back.

⚠ **Two things in it are worth stealing rather than rebuilding.** The **leverage refusal** — an
input in units of "times my account" instead of a percent-of-price stop floor, refusing rather than
shrinking — and the **three-candle window** on a reclaim. Both are described in this file's git
history at the commit that deleted them.

## The session sweep strategy — the rules the 2026-08-14/15 pass left behind

**`smc_session_sweep_strategy.pine`, called `mpc_m15_playbook_strategy.pine` until 2026-08-15.**
The old name named the timeframe the DIRECTION is read on, said nothing about the setup, and wore
the `mpc_` prefix of a Pine family this file was never part of — it came from a video note, not
from `mpc_assistant.pine`. Its `indicator()` twin, `../engines/mpc_m15_playbook.pine`, was deleted
in the same pass: 270 KB of dashboard that placed no orders, so the Strategy Tester could never
score it. ⚠ **That deleted file is where this strategy's structure-engine block was lifted from
byte-for-byte**, so its provenance now points at `engines/market_structure/` — the canonical
implementation and the only other copy. ⚠ **The old names are deliberately left standing in
`HISTORY.md` and the build notes**: a diary entry records what a file was called when the thing
happened, and rewriting it makes the record false.

**Full narrative: `../docs/INDICATORS_BUILD_NOTES.md` → *the playbook joins the contract*.** What
is here is the instruction; that file is the evidence. Six rules, each learned by something on a
chart being wrong in a way nothing errored about.

### 🔴 THE SHIPPED DEFAULTS ARE AARON'S CHART, NOT A MEASUREMENT (2026-08-17)

**Six defaults were changed to whatever Aaron had dialled in on his own chart, at his request:
confirmation OFF, first target 3.5R, 80% banked there, 4% risk per trade, minimum stop floor 0.07%,
sessions drawn.** The gap requirement stays ON (`pbPoiTf = "5"`). Table and the reasoning per line:
`../docs/SMC_SESSION_SWEEP_SPEC.md` → *The shipped defaults*.

✅ **ONE OF THEM NOW IS: the minimum stop became `Fixed $` `4.00` on 2026-08-17 and it was
MEASURED.** The target was the average LOSER, which is −1.27R over 214 positions where a stop that
works gives −1.00R — and that 0.27R of overshoot is more than half the whole edge (break-even 26.1%
against an actual 29.9%). **All 150 losers bucketed by stop width: everything under $4 averages
−1.43R and holds every loss worse than −3R in six years; everything above averages ≈−1.1R whatever
you do.** So $4 is the bend in the curve and a wider floor buys only fewer trades. ⚠ **The MODE
changed too and that is half the fix** — `% of price` is not a constant, and 0.07% was $1.19 at gold
1,700 against $2.80 at 4,000, i.e. loosest exactly where it was needed most. ⚠ **It is a FILTER on a
finished export, not a re-run**: with one position slot a refusal frees the slot, so a real backtest
can take trades this cannot see. **The bias only runs one way — the ~9R it appears to cost is an
upper bound** — and the per-trade ratios are sound while the total-R figures are the approximation.
⚠ **IT DOES NOT FIX THE LEVERAGE.** At 4% risk on gold at 3,500 a $4 stop is still **35x**; the
floor and the risk percent set leverage together, and 20x would need risk near 2.3%. Full table:
`../../docs/SMC_SESSION_SWEEP_SPEC.md` → *The minimum stop is $4*.

🔴 **THE OTHER FIVE ARE STILL NOT BACKED BY A RUN, and the reason to write that here is that a default is
indistinguishable from a finding once it is in the file.** The previous set was equally unmeasured
and read for two days as if the course had produced it — 5R was the course's number and 50% was
nobody's. **A default is a CLAIM about what is best, made by whoever typed it last.** These are
Aaron's live settings and they are the ones to reproduce when he reports a number; they are not a
result and must never be quoted as one.

⚠ **Three of the six move RISK, not display, and they compound: 4% per trade with a 0.07% stop
floor sizes larger on a tighter stop than the old 1% / 0.03% pair did in both directions at once.**
The floor is the only thing between the position sizer and a stop a few ticks wide.

⚠ **Changing a default is what re-opens the cascade audit** — see *A CASCADE AUDIT* below for the
`showSosMark` gate this reversed one day after it was written.

### 🔴 The TOOLTIPS are for Aaron, not for the next engineer (2026-08-16)

**Aaron: *"all the tooltip explanations are way too long and way too technical. I can't read that."***
Every tooltip on this file's 44 inputs was rewritten short and plain. They had grown into the same
thing the comments had been — measured numbers, dates, file paths, incident history — except a
tooltip renders in a small hover box on a settings panel, which is the worst possible place to put
any of it.

**The rule: a tooltip answers "what does this do and which way should I move it", in one or two
sentences, in words a non-programmer uses.** No file paths, no dates, no variable names, no bar
counts, no "block code 9". The evidence and the incidents live in this doc; the tooltip is the
label on the dial.

⚠ **This is the same lesson as the comment strip, one layer up: the content was not wrong, the
PLACE was.** Deleting it would have been the mistake; it moved.

⚠ **`showSetups` was also renamed** — it read *"Draw the zone, stop and targets"*, which named a
thing (a "zone") that appears nowhere else in the UI and did not say the drawing belongs to trades
that actually happened. It is now *"Show the gap the order sat in, plus entry, stop and targets"*.
**Renaming a title is safe for saved settings; only insertion and reordering are not.**

### 🔴 The file's comments were STRIPPED 2026-08-16 — this doc is now the only copy

**Aaron: *"realistically I will never read these comments. Unless they're for AI, they're
useless."*** 674 of 1,722 lines were explanation — **45% of the file, 111 KB → 61 KB** — and every
byte of it loaded on every read, in a file that gets read constantly while a chart is being tuned.
All full-line comments below the header are gone. **Tooltips stayed**: those render in TradingView,
so they are the half he actually reads.

⚠ **This makes the doc load-bearing rather than supplementary.** Several facts below are now
unrecoverable from the code — the code is correct and silent about why. Before changing this file,
read the sections here.

⚠ **How it was done, because doing it by hand is how a Pine file breaks.** A script stripped
full-line comments only, after first proving that **no `if`/`else`/function body would be left
empty** — a comment that is the sole member of a block is load-bearing whitespace, and removing it
is a compile error, or worse, a silently re-parented statement. Inline trailing comments were
removed only on lines with no string literal on them. The script is disposable; the CHECK is the
part to repeat.

### The facts that used to live only in the header

**STATUS.** ✅ Compiles — confirmed by Aaron 2026-08-16, on the build carrying the three course
rules, the provenance panel and the rebuilt overlay. ⚠ **That is a fact about that paste only.**
There is no local Pine compiler, so every edit since is unverified; `check_active_order.py` is the
only thing that runs here. 🔴 **NOT MEASURED — no run has been taken at these defaults.** No export
twin, no Python port, so **no `compare_*.py` covers this file at all.**

**The confirmation timeframe is read through a COUNTER, not a flag, and that is not a style
choice.** `request.security` runs the structure engine on every bar of the requested timeframe and
hands back only the value as at the LAST of them. A shift flag is set on the bar that shifted and
cleared at the top of the next, so sampling it once per chart bar reads the fifth 1-minute bar and
misses four out of five shifts. A counter accumulates inside the chart bar and is diffed against the
previous one. ⚠ **The flag goes stale-FALSE through the security call, not stale-true** — an earlier
comment had that backwards, so the code was right for a reason its own note got wrong. ⚠ Residual
cost: the shift is known at the chart bar's CLOSE — up to one chart bar late, never early.

**The drawing budget is TradingView's 500-per-type and nothing here caps itself.** Aaron, 2026-08-15:
*"don't cap it at all."* ⚠ TradingView evicts per OBJECT TYPE, oldest first, with no idea which
drawing an object belonged to — so at the far-left edge a setup dissolves in pieces, its box gone
while its stop line remains. That is the edge running out, not a bug. ⚠ **The families compete**:
sessions draw 3 boxes a day whatever happens, trades 4 each. **Count trades in the Strategy Tester's
list, never off the chart.**

**The session windows are hardcoded and DST-aware** — each session's own city clock, identical in
every Pine file here since 2026-07-31. They DECIDE trades (the pool is read from them), so they are
not inputs, and a change to one belongs in every file carrying the block.

**The point of interest is GAP-ONLY.** The course says "order block OR fair value gap"; only the gap
is modelled, so this file takes strictly fewer setups than he does. ⚠ **TradingView loads limited
1-minute history** — with confirmation on, the far end of a long backtest may see no 1m structure
and simply take no trades there. Check the trade list's FIRST date against the chart's.

### 🔴 Three rules added from the course, 2026-08-16 — and none of them is measured yet

Six runs of this file over 2023-01 → 2026-08 on XAUUSD gave a win rate that never left
**16.7-20.1%**, profit factors **0.85-1.15**, worst drawdowns **24-59%**, and **zero breakeven
trades in 1,961 trades**. The course the model came from
(`education/smc/05-my-full-trading-strategy/`, the data review in transcript 25 — ⚠ its
`summaries/25-*.md` is an empty `to-summarize` stub, the numbers are in the transcript) reports
his own book over 2.5 years: **230 trades, 62 wins, 126 losses, 42 BREAKEVEN**, ~6.2 average
reward-to-risk, worst drawdown **6%**.

🔴 **The setup was never the problem — London-sweeps-Asia is his most traded AND most profitable
play, and it is the one this file implements.** What was missing was rules he has and this file
did not. Three are now in, each behind its own switch, all defaulted ON:

| input | what it does | his number |
|---|---|---|
| `execBeOnShift` | stop to breakeven when the confirmation timeframe shifts against an open trade | 18% of his trades end flat; ours ended 0% flat |
| `execUseWindows` | trade three one-hour windows a session instead of all nine hours | London 2-5am NY, New York 7-10am NY |
| `execTp1Mode` = `Fixed R` | first target at a fixed 5R instead of the nearest liquidity level | his winners average 6.8x, ours 4.7x |

⚠ **ALL THREE ARE HYPOTHESES. Nothing has been run.** They are switches precisely so each can be
turned off and re-measured alone — flipping all three and reading one number says nothing about
which one did the work, and this repo has a rule about exactly that.

⚠ **The breakeven rule implements only the MECHANICAL half of his.** He also requires no reason
left for price to return (no unfilled zone behind it), which is discretionary and is not modelled.
So it fires MORE often than he does: expect scratches he would not have taken and runners cut
early. **Known bias, one direction** — read the breakeven count against his 18% before concluding
the rule failed.

🔴 **Both windows have an INERT first hour, and it is a fact about this file rather than a bug to
chase.** The London session opens 08:00 London = **03:00 New York**, so his 2-3am hour is outside
every session here and dies on block code 3 before the clock is consulted — his 2am hour is the
**Frankfurt** open, and Frankfurt is a session this file does not model. Same shape on the other
side: the New York session window starts 08:00, so his 7-8am hour is refused too. **Effective
windows are 3-5am and 8-10am.** Widening the session windows to match would change what the POOL
is measured over, which is a real change and not a tidy-up.

⚠ **A resting limit is CANCELLED when its window closes** (`cWin`, ungated by `execCancelFlip`).
Without that the window would be decorative — an order placed at 04:55 could fill at 08:30 — and
the trade list would not be comparable to an hour-by-hour read of it.

⚠ **Refusals on the clock are block code 11, chosen instead of renumbering 4-10.** The ladder ORDER
decides which refusal wins; the number is only a label, and renumbering would silently change what
every tag and screenshot already taken means. ⚠ **Code 11 is deliberately NOT tagged on the chart**
— the window is shut for most of every session, so a pink label per leg would drown the five
refusals that mean something. Read its cost off the trade list, windows on against windows off.

⚠ **Under `Fixed R` the first target always exists, so block code 9 can never fire** and the trade
count rises for that reason alone. ⚠ **When no liquidity level sits beyond the fixed target the
WHOLE position exits there** — the runner is lost, deliberately, because the alternative is
inventing a second number nothing measured.

⚠ **INPUTS WERE INSERTED, NOT APPENDED, so every saved chart preset for this script is void.**
TradingView keys saved values off declaration order per type. The panel-order contract and
TradingView's persistence are in genuine conflict here and the contract won, because a panel
nobody can read is the defect this file already has an incident about. Re-set the panel on the
next paste; do not trust a preset from before 2026-08-16.

**Four course rules still NOT modelled**, and two of them gate his best setups: order blocks as
entry objects (this file is gap-only), point-of-interest quality grading, the news blackout, and
six of his eight named setups — including *NY continuation from the London POI* (**63% win rate**)
and *NY sweep of the Lull* (**55%**), both of which need session concepts this file has no idea
exist.

### 🔴 The trade overlay is the Command Center's shape, rebuilt in Pine (2026-08-16)

Aaron, off a side-by-side screenshot of `command-center/`'s trade tracker: *"no borders on
anything… one shade of green for where we took profit, a lighter shade where price ran further and
we didn't… a solid line showing where the entry was and a different one showing where we exited…
I want it exactly like this."* Six pieces, and each one answers a question:

| piece | what it answers |
|---|---|
| entry → **deepest**, red | how far it went against you |
| entry → **furthest**, LIGHT green | how far it ever went your way |
| entry → **exit**, DARK green | the part you actually captured |
| entry line, grey solid | where you got in |
| exit line, result-coloured | where you got out |
| SL line, red dashed | the risk you took it on |

🔴 **DRAW ORDER IS LOAD-BEARING.** The favourable band (`pRan`) is created at the FILL and the
captured band (`pGot`) at the CLOSE, so the later box paints over the earlier one. The captured
band is a SUBSET of the favourable band on any winner, and that layering is the only thing
producing the light-green sliver between the exit and the furthest — *"price ran further but we
didn't take any profit."* Swap them and the whole move reads as captured.

🔴 **ARM and FILL are different bars, and that decides what a drawing may span.** The gap, the entry
and the stop are true from the moment the LIMIT is placed, so they start at the arm bar. A TARGET is
not — nothing aims at it until there is a position — and it was drawn from the arm bar too, so on any
order that rested a while the target line stuck out to the left of the trade block. Aaron: *"it's
overlaying to the left of where the trade traded."* Now clipped to the fill. ⚠ **On a market entry
arm and fill coincide and the clip is a no-op, which is exactly why it survived**: the defect only
exists on the resting-limit path.

⚠ **The swept-level line is GONE** (Aaron, 2026-08-16: *"I want that whole line gone"*). It ran from
the sweep bar across to the setup, so it reached back into the previous session and was the longest
object on any chart — **a line that long reads as a level being respected, not as a one-off event
that already happened.** The pool plot draws that price live for the session hunting it, which is the
honest version. `sweepHi/LoBar` and `sweepHi/LoLvl` went with it: nothing else read them.

🔴 **A `plot()` of a level that JUMPS needs an explicit `na` on the jump bar.** `style_linebr` only
breaks on `na`, and London runs straight into New York with no gap — `rawSess` goes 1 → 2 on adjacent
bars — while the pool underneath jumps from Asia's high to London's. The plot joined them with a
steep diagonal, and **a diagonal on a price chart reads as a trend line**. `newLeg ? na` is the fix
and it costs one bar of the new session's line, which is the right trade: a one-bar gap is legible,
a connector between two unrelated levels asserts something false.

🔴 **Inserting a block ABOVE a trailing, more-indented fragment RE-PARENTS that fragment, and Pine
has no brace to disagree with.** The close-bar stretch was inserted directly above the three lines
that make the setup's stop line follow the staged breakeven, which swallowed them into a branch
gated on `justClosed` — where the position is by definition FLAT, so the guard was never true.
Nothing errored; **the stop line simply froze at the original stop.** ⚠ After inserting into an
indented Pine block, check what now sits UNDER it, not just what you wrote.

🔴 **The right edge of every piece is set in ONE place, on the close bar, and getting that wrong is
what a split drawing looks like.** The live-extend block is gated on `strategy.position_size != 0`,
and on the bar a trade CLOSES the position is already flat — so it does not run, and `pRan`/`pDD`
stopped one bar short while `pGot` and all four lines were born on that bar and ran to it. The
symptom Aaron saw was a light-green margin down the side of the dark box that read as a second,
wider zone. ⚠ **Standing: a drawing assembled from pieces created on DIFFERENT bars has to have its
extents set in one place, or the pieces disagree about where the trade ended.**

⚠ **The SL line reads the ORIGINAL stop, never the live one.** The live stop moves to breakeven, so
drawing it shows a trade at a reward:risk it never had. That is why `posStop0` exists.

⚠ **No borders anywhere, and no direction arrow.** The old build bordered the result box and the
border was the loudest thing on the chart — it read as a level rather than as the edge of a fill.
Direction is carried by the geometry: green above the entry is a long, green below it is a short.

🔴 **The result label anchors at the FURTHEST price and points outward.** It used to hang 1.5 ATR
off the ENTRY, which on any trade that travelled put it in the middle of the move — Aaron: *"this
should be off of the bars. It should never be on top of the bars."* Anchoring at the extreme the
trade reached is what guarantees nothing is beyond it to cover.

⚠ **The gap zone is GREY and BORDERLESS, copied from `mpc_strategy.pine:225`** (`color.new(color.gray,
80)`, `border_color = color(na)`, bull and bear identical) rather than chosen here. Aaron, 2026-08-16:
*"no border, make it grey, same as my other fair value gaps."* **It is deliberately not
direction-coloured**: a gap is a price RANGE the limit rests inside, and the trade block drawn on top
of it already says which way the trade went — a green-bordered box under a green trade block is two
claims about one thing. A pulled setup fades one step (`FVG_DEAD`) and takes the ✕; there is no
border left to recolour, which is why the fade carries it.

🔴 **Every label sits behind `execShowLabels` and it SHIPS OFF.** Aaron asked for the pills, saw
them, and said *"take off the labels — I can use the colour code to determine that."* The zones and
lines do carry the picture alone. ⚠ **What that costs is stated on the input rather than left to be
found: colour can say won/lost/breakeven and it cannot say 4.46R**, so with labels off there is no
per-trade R on the chart at all and no hover. On for reading individual trades, off for reading the
shape of a run. ⚠ It is also the entire label budget — six a trade against Pine's 500-label ceiling
is ~80 trades, and blocked-setup tags compete for the same 500, so OFF is what lets the chart run
back as far as it does. **Count trades in the Strategy Tester's list, never off the chart.**

### 🔴 MISSED and BLOCKED are different things, and one pink tag said both

**Aaron, on a refusal whose gap sat twenty dollars from price: *"it was never blocked, it was
missed… you could have said two out of three — the session was swept but the fair value gap was too
far."*** Every refusal from the zone onward wore one pink **SETUP BLOCKED** tag, which reads as the
strategy turning away a trade it could have taken. In codes 6-9 there was never a trade to turn
away: the model's own fourth step did not happen.

| tag | codes | means |
|---|---|---|
| **orange `3/4 MISSED`** | 6-9 | direction, sweep and confirmation ALL landed; the point of interest failed |
| **pink `BLOCKED`** | 10 | all four confluences were there and OUR one-position rule refused it |

🔴 **THE TICK-LIST IS READ FROM THE INPUTS AND ITS FIRST VERSION WAS HARDCODED.** It shipped
printing a fixed *"3 of 4 · ✓ Confirmation — the 1-minute changed character"* — on charts with
lower-timeframe confirmation switched **off**. Aaron, within minutes: *"how could it have met the
1-minute confirmation if I have it off? That tells me the annotations are not reading my inputs."*
He was right, and the same line hardcoded *15-minute* for a direction timeframe that is also an
input. Now: the denominator is 4 or 3 depending on `pbRequireConf`, the confirmation row reads **NOT
REQUIRED** when it is off, and every timeframe named is the one actually set.

⚠ **`mpc_strategy.pine` had already solved this and the pattern was not carried over** — its
2-of-3 callout takes every gate as a PARAMETER from the caller precisely so *"the callout always
describes the strategy you are actually running"*. **A confluence tick-list is a CLAIM about the
config, so it has to be built from the config.** A hardcoded one is worse than no tick-list: it
reads as a diagnostic and is a decoration, and it will be believed over the settings panel.

🔴 **THE SCORE ITSELF WAS STILL ASSERTED, AND THAT COST A ROUND.** `cfMet` was
`str.tostring(isMiss ? cfTot - 1 : cfTot)` — pure arithmetic off the gate code, reading none of
`dirDir`, `sweptHi/Lo` or `confShort/Long`. The reasoning was sound (the ladder cannot reach a
point-of-interest refusal without the earlier steps passing) and the OUTPUT was therefore correct,
which is exactly why it survived. It failed the moment Aaron asked a question of it: a 3/4 MISSED
tag claimed *"✓ Confirmation"* while the confirmation MARKER was absent from the chart, and there
was **no way to tell which one was lying, because only one of them was measuring anything.**

✅ **Every tick is now read from the live flag** (`okDir`/`okSwp`/`okConf`), the count is their sum,
and a failed step prints ✗ rather than being omitted. The confirmation line also prints the price it
broke at, so it ties to the cyan SOS line by number and not by eye. ⚠ **This will now DISAGREE with
the ladder if the ladder is ever wrong — which is the point.** A tick list derived from the thing it
is supposed to check can only ever agree with it.

**The standing lesson, and this file has now hit it three times: a derived diagnostic is not a
diagnostic.** It cannot catch the bug it sits next to, and its confidence is indistinguishable from
evidence. The cost is a few extra reads of variables already in scope.

🔴 **Code 8's wording named the CONSEQUENCE and hid the CAUSE.** *"The stop is too tight"* is what
happens; *the gap is too thin* is why. Aaron read the old text as the strategy refusing a good
trade, and it cost a full round of explanation. ⚠ **When a gate refuses on a derived quantity, say
what it was derived FROM** — the stop distance is downstream of the gap height, and only the gap
height is something you can look at on the chart.

⚠ **Pink is now the only refusal you can buy back by changing a setting**, which is what pink should
have meant all along. ⚠ **Colours are `mpc_strategy.pine`'s and mean the same there** — orange
2-of-3 callout, pink TRADE BLOCKED — so one glance reads the same on either chart. ⚠ **That orange
is also this file's BREAKEVEN colour**, an overlap A+ has too; it is tolerable only because the two
never share an object (breakeven orange is always a filled trade band, missed orange is always a tag
with no trade under it). **Do not use it for a third thing.**

### A refusal is DRAWN now, not just tooltipped (`showBlockDraw`, 2026-08-16)

**Aaron, reading a *"the stop is too tight"* tag: *"if it was a fair value gap, still draw the fair
value gap so I could visually see it, and draw where the stop loss would have been."*** The tag
carried the reason and the would-be entry price in a tooltip, and that made the guard unauditable by
eye — you had to take *too tight* on trust. A blocked setup now draws the **same three objects a
taken setup draws**: the gap as the identical grey borderless box, the entry it would have rested
at, and the stop it would have carried. The tooltip also prints the stop distance next to the floor
that refused it.

### The shift of structure is MARKED now, and a second timeframe is marked beside it (`showSosMark`, 2026-08-16)

**Aaron: *"if we do take the one minute shift of structure, give me an indicator on the chart exactly
where that happens… and add the equivalent on a five minute shift. I just want to see if five minute
works better than one minute."*** The confirmation step was the one part of the model with no mark on
the chart at all — every other step draws something — so *"the small timeframe turned"* was a claim
with nothing to check it against.

🔴 **THE FIRST BUILD MARKED EVERY SHIFT AND WAS USELESS FOR EXACTLY THAT REASON.** Aaron:
*"I only want to see the confirmation shift where there was either a missed trade, a blocked trade,
or a successfully taken trade. I don't want to see any other shifts in between."* A structure engine
on a 1-minute chart shifts constantly, so marking them all buries the handful that mattered under
hundreds that did not — **a marker that fires on everything carries no information, and it is worse
than none, because the chart now LOOKS annotated.** Same failure shape as the editor guard that
warned on every large file.

**So the marker is drawn RETROSPECTIVELY, at the moment the setup resolves.** The shift that
confirmed a setup is recorded when it happens (`cfBar`/`cfDir`/`cfPx`, set inside the same branch
that latches `confShort`/`confLong`, so it is by construction the shift the gate consumed, never a
re-derivation). Nothing is drawn then. The marker is placed back at that bar only once the setup
becomes one of the three things worth looking at — `justFilled`, or the MISSED/BLOCKED tag firing.
⚠ **A setup whose order was pulled before filling gets no marker**, by decision: it is not one of
the three cases named.

🔴 **AN ARROW BESIDE THE BAR WAS ALSO WRONG, AND THE REASON IS THE ONE THAT MAKES THIS FEATURE WORTH
HAVING.** Aaron: *"if we have a wick, I don't know which part of the wick the shift of structure
happened at. Show me a horizontal line right where it happened."* An arrow says WHEN. On a long
wick the question is WHERE — and a shift of structure has an exact price: **the swing level the
close broke through.** So `f_pbStruct` now returns that level as a third value (`bull_bos_high` on a
bull shift, `bear_bos_low` on a bear one, read straight from the engine's own fields), and the
marker is a **horizontal line at that price** with an `SOS <tf>m` label on its right end. Solid
cyan for the confirmation timeframe, dashed purple for the comparison one.

⚠ **`dirLvl` is destructured and unused** — the direction call shares the function, so it returns
the level too. Pine warns; it does not error.

⚠ **The price is recorded at the shift bar, not looked up later.** Drawing at a past `bar_index`
with `low[bar_index - cfBar]` would be a dynamic history offset — the class of bug that throws
*"beyond the historical buffer's limit"* at runtime and only on some charts. Storing the price when
the bar is current costs one float and cannot fail.

🔴 **A HORIZONTAL LINE ANSWERS "AT WHAT PRICE" AND SAYS NOTHING ABOUT "ON WHICH CANDLE".** Aaron,
on the next screenshot: *"the line runs across ten fifteen-minute candles. I don't know which one
the shift was on."* Its left end IS the bar, but a reader does not measure a line's endpoint — they
see a band. **The two questions need two marks.** The marker is now three objects: the flat line at
the broken price running right, a **thick vertical stub on the shift bar itself**, and the label
anchored to that stub with a pointer style (`label.style_label_up` on a bull shift,
`_down` on a bear one) so it points at exactly one candle. The label also carries the price, so the
candle and the level are both readable without hovering.

⚠ **The stub is drawn AWAY from the break** — below the level on a bull shift, above on a bear one —
because the candles right after a break sit on the other side and the marker would be buried in
them.

⚠ **The LINE is the level; the BAR is when we learned about it.** `request.security` reports on the
chart bar where the higher timeframe's bar closed, so the break happened somewhere inside that bar.
The price is exact, the x-position is *the bar the strategy could act on* — which is the honest one
for a strategy chart, and would be the wrong one for a study of the engine.

**The comparison timeframe** (`sosCmpTf`, default 5, `"Off"` available) marks the FIRST time it
turned the sweep's way in that session leg — the earliest that timeframe could have confirmed.
⚠ **It is MARKING ONLY and feeds nothing** — no gate, no arm, no order — which is what makes it
usable as a comparison: it shows what a different confirmation timeframe would have said on the same
bars, without changing the bars. ⚠ **It is not a verdict.** It says where and when the other
timeframe turned, not whether turning there was better; that is a backtest.

🔴 **AND IT ONLY EVER DREW ON TAKEN TRADES, BECAUSE THE RECORDING SAT INSIDE THE CONFIRMING
BRANCH.** Aaron: *"you only show it on trades we actually took. I want it on missed and blocked
too."* `cfBar`/`cfPx` were assigned in the same `if` that latches `confShort`/`confLong` — the
branch that fires only when a shift genuinely confirms. **With `pbRequireConf` OFF, step 5 passes on
the sweep alone (`confOkLong = sweptLo`), so a leg can reach a MISSED or BLOCKED refusal having
never entered that branch: nothing recorded, nothing to draw, and no error.** The same hole opens
under `"At the zone"`, where `placeOk` needs `armTouched` and a missed setup never touches the zone.

✅ **Recording is now SPLIT from confirming.** Every confirmation-timeframe shift on the swept side
is recorded, whatever the toggles say; a separate `cfUsed` flag records whether that shift was the
one the gate consumed. ⚠ **The flag is not bookkeeping — it is what keeps the tooltip honest.** The
same cyan line now means two different things, and it says which: *"this is the shift that confirmed
the setup"* when `cfUsed`, and *"it did NOT confirm anything — you have confirmation switched off,
or the setup was refused before it mattered"* when not. **A marker that looked identical in both
cases would be the label-vs-code failure this file keeps recording, drawn instead of written.**

⚠ **When no shift happened on that side at all there is still nothing to draw**, and that is
correct rather than a gap — there is no price to put a line at.

⚠ **The comparison draws NOTHING when it is set to the same timeframe as the confirmation.** Both
lines would sit on one price and the purple one — drawn second — would hide the cyan. That is not
hypothetical: a screenshot showing a lone purple `SOS 1m` and *"where is the confirmation
indicator?"* is what found it. The suppression is named in the input's own tooltip, because a
drawing that silently does not appear is the failure it is meant to prevent.

⚠ **One line plus one label per marker, and the budget is why the toggle DEFAULTS OFF.** The labels
share the 500-per-type ceiling with the MISSED/BLOCKED tags, the cancel ✕ and the trade labels, and
eviction is per-type and silent.

⚠ **Both inputs are appended AFTER the last existing input of their own type** (the bool after
`pbShowSess`, the string after `execMinStopMode`) even though both display in group 8. Group is a
display label; TradingView keys saved values off declaration order within each type, and the two are
unrelated.

⚠ **It adds a fifth `request.security` call.** The comparison timeframe is resolved to the
confirmation timeframe when it is `"Off"` so the call always has a valid argument, and the drawing is
gated instead — the call cost is paid either way.

⚠ **With confirmation switched off there is no confirming shift and no cyan triangle**, which is
correct rather than broken. The purple comparison one still draws.

### 🔴 A GATE NAME IS NOT AN EXPLANATION — "too thin" read as "we got there and it was too thin"

**Aaron, third round on the same tag: *"it says the gap is too thin. But price never got to it. All
this time I was thinking we got to one and it was too thin. Your messages have to be very clear on
exactly what happened."*** The gate name was accurate and the SENTENCE it formed was not. Nothing
says a refusal happened BEFORE any order existed, so a reader supplies the missing half — that price
arrived, then something went wrong there. It never arrived. No order was ever placed.

**The tooltip is now a story with an ending, not a gate name plus loose numbers.** It reads: what
lined up, then `WHY THERE WAS NO TRADE`, then a `THE GAP` block with the gap's location, height,
distance from price and the stop maths.

⚠ **The reason strings are now SENTENCES with full stops, not fragments.** A fragment gets read as
the end of whatever sentence the reader started, and they do not all start the same one.

🔴 **AND THE FIRST FIX WAS STILL NOT PRECISE — it appended "no order was ever placed" to a reason
that still LED with "the gap is too thin".** Aaron, immediately: *"It should say why there was no
trade. Point of interest was never met. That's it. Nothing more… only if we met it, and it was too
thin, and I could see that."* A disclaimer under a wrong headline does not fix the headline.

✅ **So the tag now KNOWS whether price ever traded into that gap, rather than inferring it.**
`f_poiScan` returns the selected zone's own tap flag alongside its prices (`poiBullTap`/`poiBearTap`,
`armTouched` on the at-the-zone path). `WHY THERE WAS NO TRADE` is then one line, chosen from the
FACT rather than from the gate: no zone at all → *"There was no gap on this side of price."*; a zone
price never entered → *"Price never reached the gap. The point of interest was never met."*; a zone
price DID enter → the real gate sentence, which now opens *"Price reached the gap, but…"*.

⚠ **With `pbPoiUntouched` ON — the shipped default — a tapped zone is excluded from selection, so
the tag can only ever say "price never reached the gap".** That is not the message being lazy; it is
the setting. The thin/target reasons become reachable only when untouched-only is turned off.

⚠ **Code 7 (too far) is deliberately EXEMPT from the tap test and always states its own reason.**
It is a filter the reader switched on, and by construction its gap is far away — routing it through
"price never reached it" would hide the filter that actually did the refusing.

⚠ **The stop maths is kept, one line, and it is worded as a HYPOTHETICAL when the zone was never
entered** (*"Had price reached it: entry …, stop …, your floor is …"*). It is the only way to see
whether a gap really was too thin, which is what Aaron asked for two rounds earlier — but it lives
under `THE GAP`, never under `WHY`, because a fact and a cause are different things.

**The standing lesson, and it is the sharper form of the section below: a first-refusal-wins ladder
tells you which CHECK refused, and a reader is asking what HAPPENED. Those coincide only when the
check ran on something real. When it ran on a hypothetical — an order that was never placed at a
price never traded — the gate name is the wrong sentence no matter how much you append to it.**

### 🔴 A DISABLED GATE MAKES THE NEXT ONE LIE — the "too thin" that was really "too far"

**Aaron, on a 2/3 MISSED tag: *"it says the gap is too thin. But we haven't even touched the gap
yet — how could that be valid?"*** He was reading a refusal on a gap **twenty dollars below price**,
reported as a thinness problem. Both facts were true. The ORDER was wrong.

**The ladder checks "too far" (code 7) BEFORE "too thin" (code 8) — and code 7 ships DISABLED**
(`pbPoiMaxAtr = 0`, no limit). So the first thing wrong with that setup was never evaluated, the
second thing was, and the tag named the second. 🔴 **A first-refusal-wins ladder reports the first
gate that FIRES, which is not the first gate that MATTERS when an earlier one is switched off.**
Every such ladder in this repo has the same shape.

**The fix is not to reorder the ladder** — the order is right, and code 8 genuinely did refuse it.
The fix is that **the tooltip now always prints the distance to the gap, in dollars and in ATR, and
says so explicitly when the distance filter is off.** A refusal reason is a summary; the geometry
next to it is what stops the summary being mistaken for the whole story.

⚠ **The setting that would refuse these honestly already exists** — *Maximum distance to the zone (x
ATR14)*, group 7 — and it is **0 = off** out of the box. Nothing is measured about what it should
be. A gap that far away is one the model offers and price rarely reaches, so it costs setups to no
purpose; that is a hypothesis, not a finding, and it needs a run each way.

🔴 **A REFUSED GAP GETS A BORDER; A TAKEN ONE DOES NOT, AND THAT IS NOT AN INCONSISTENCY.** Aaron,
looking at a *"gap too thin"* tag: *"I need to see a gap to know that it's too thin. If I can't see
it, the annotation doesn't add up."* The box was being drawn correctly the whole time — **a
one-dollar box on a chart at 4360 is under a pixel tall, and a borderless box of sub-pixel height
renders as literally nothing.** A border renders as a line at any height, so the thing the tag is
talking about is now always visible at its true size. ⚠ **The borderless rule it appears to break
exists for a DIFFERENT case**: a gap under a trade block, where the border would read as a second
claim about the same thing. A refusal has no trade block over it, so there is no conflict.

🔴 **THE LEADER LINE RUNS TO THE GAP, NOT TO THE CANDLE, AND THE FIRST FIX GOT THIS BACKWARDS.**
Aaron, after the border landed: *"I still can't see it. Look at the chart. I can't see it
literally."* A bordered box IS drawn — but the tag sits 1.5 ATR off the bar, the gap can be twenty
dollars the other way, and the line between them stopped at the candle. So the tag pointed at
nothing and the box was a grey line lost among the session shading. **The leader now ends on the
gap's near edge**, so following it always arrives somewhere. ⚠ **This does NOT reintroduce the
scale blow-up** — that came from padding the LABEL past the zone, and the label is still anchored to
the bar. The leader only spans a range the box already forced onto the scale.

⚠ **The tooltip also prints the gap's HEIGHT and both edges.** A line tells you where; only a number
tells you how thin, and "measure it by eye at this zoom" was never a real instruction.

🔴 **The stop is PINK and dashed, never the red a real stop gets.** Nothing was ever working there.
A red line says a trade existed, and a chart full of red lines at prices no order was ever placed at
is how a refusal gets read back as a loss.

**The tag itself moved OFF the candles.** It was anchored at the bar's high/low, which put it over
the very candles you are trying to read — Aaron: *"it's literally on top of the candle."* It is now
parked 1.5 ATR clear of the BAR with a dotted leader back to the candle.

🔴 **The pad is measured off the BAR ALONE, and the first version measured it off the ZONE too.**
That reads as the safer choice — a stop below the bar would otherwise be drawn through the label —
and it **blew up the price scale**. The zone is the nearest *untouched* gap, which after a long
one-way move can be twenty dollars from price; padding past it put the label another 1.5 ATR beyond
that, TradingView auto-scaled to include it, and the candles were squashed into the top fifth of the
chart. Aaron: *"the gap is off the chart now."* ⚠ **A label positioned relative to a value with no
bound on it inherits that lack of bound.** Anchor to the bar — it is the one thing on screen that
cannot run away. Same reason the leader now points at the candle rather than at the would-be entry
price.

⚠ **A far-off gap box is NOT the bug and must not be "fixed" by clamping it.** It is the honest
answer to why nothing traded, and the setting that refuses those already exists — *Maximum distance
to the zone (x ATR14)* in group 7, which ships at 0 = off.

⚠ **Costs 3 more drawings per tag against the 500-per-type ceiling**, so the chart goes back less
far with it on. ⚠ **Block code 6 has no zone at all** (that IS its refusal), so it draws the leader
and nothing else — guarded on the zone being non-`na` rather than assumed present.

⚠ **Inserting this bool shifted `pbShowSess` by one declaration slot**, so *Show sessions* resets on
every saved chart. Both are draw-only; it was accepted rather than missed. It is the last bool in
the file, which is why the damage stopped at one.

### 🔴 "BLOCKED" beside a running trade reads as a bug, and the reason string was three reasons at once

**Aaron, on a pink BLOCKED tag sitting under a trade that was clearly open: *"I don't understand
what was blocked. I'm in a trade."*** He is describing the tag correctly and it still told him
nothing. Code 10's string was *"You were already in a trade, already had an order waiting, or had
already traded this session"* — **a list of the three things `busy` is made of, offered because the
code did not know which one fired.** It does know: `strategy.position_size`, `pendDir` and `tookLeg`
are all in scope at the tag, and they are mutually distinguishable.

✅ **Four sentences now, picked from live state, and each one names the SECOND setup explicitly** —
that is the missing noun. The tag is not about the trade you can see; it is about another setup that
appeared while that trade held the only slot. ⚠ **The cross-session case is separated out**
(`position_size != 0 and not tookLeg` — a trade from an EARLIER session leg still running), because
that is a genuinely different fact about the strategy and gets read as the same one.

🔴 **AND THE PLAN WAS NESTED INSIDE THE GAP BLOCK, SO A SETUP WITH NO GAP SHOWED NO PRICES AT ALL.**
`tipGeom` was concatenated onto `tipGap`, which is `""` when there is no zone — invisible for every
`pbPoiTf = "Off"` refusal, i.e. exactly the mode added the same day. It is its own `THE TRADE THAT
DID NOT HAPPEN` section now. ⚠ **A string built by appending to a conditionally-empty string
inherits that condition**, and nothing errors — the section simply is not there.

### 🔴 The gap can be switched OFF entirely — `pbPoiTf = "Off"` (2026-08-16)

**Aaron: *"I want an option where I don't require a point of interest. I'd still require the shift of
structure confirmation."*** The course's third step is the gap; this drops it. Sweep, then the
confirmation timeframe turns, then **enter at market on that bar**, stop behind the sweep extreme.

🔴 **IT IS AN OPTION ON THE EXISTING DROPDOWN, NOT A NEW INPUT, AND THAT WAS THE DESIGN CONSTRAINT
RATHER THAN A TIDINESS PREFERENCE.** A new `input.bool` has to be appended after the LAST bool in
the file to avoid resetting saved values — which would have put "do I need a gap?" at the bottom of
the panel, three groups away from the gap settings it governs. **Widening an existing dropdown moves
nothing, resets nothing, and lands the control exactly where it belongs.** ⚠ **Reach for this before
reaching for a new input**: ask whether an existing control of the right type already sits in the
right place. ⚠ It also let `pbPoiUntouched` be gated on it, which a bottom-of-file input could never
have done — `active =` may only name inputs declared above.

⚠ **`"Off"` is not a timeframe**, so the scan's `request.security` resolves it to `"5"` and the
result is discarded by the flag instead. The call cost is paid either way.

🔴 **`poiOff` REQUIRES CONFIRMATION AND SILENTLY STAYS OFF WITHOUT IT** (`pbPoiTf == "Off" and
pbRequireConf`). With both switched off nothing is left but the sweep, which is a different and much
looser strategy that nobody asked for. ⚠ **The refusal is the safe direction but it IS silent** —
the dropdown's own tooltip is the only place it is stated, because a greyed-out `active =` is a
display hint and does not stop the value being read.

**What changes downstream, and every one of these was a place the gap was assumed to exist:**
the entry becomes `close` and the order goes in at MARKET rather than as a resting limit; the stop
comes from the sweep extreme alone (`execStopFrom` is bypassed — there is no gap edge to choose
between); gate 6 stops asking "is there a gap" and asks "is there a sweep extreme to stop behind";
the grey zone box is skipped, so the setup drawing's update passes now key off the ENTRY LINE rather
than the box; and the tag's tick list drops to 3 steps with the point-of-interest row reading
*"not required"*.

⚠ **The minimum-stop floor becomes the load-bearing guard in this mode.** A sweep extreme one tick
from the entry is a huge position, and there is no gap height standing between the two any more.

⚠ **NOT MEASURED.** This is a different entry model — market fill at the turn instead of a limit in
a gap — so it pays the spread and gets no retrace. Run it against the shipped default before
believing anything about it.

### 🔴 A CASCADE AUDIT, and the three inputs that stayed editable while doing nothing (2026-08-16)

**Aaron: *"why is 'mark the shift of structure' still editable when I have confirmation off? Is
there anything else we are not disabling correctly from a cascading perspective?"*** The question is
worth more than the one input that prompted it. **An input with no `active =` is a PROMISE that it
does something**, and three here were breaking it — silently, because a control that changes nothing
looks identical to one that works.

| input | inert when | why |
|---|---|---|
| `execZoneEntry` | `"At the zone (enter at market)"` | the entry is `close`, so where the limit rests in the gap is never read |
| `execTpFallbackR` | `execTp1Mode == "Fixed R"` | a fixed-R target is never `na`, so the `na(t1)` fallback is unreachable |
| `pbPoiMaxAtr` | `"At the zone"` | its own gate is guarded by `not confAtZone` |
| ~~`showSosMark`~~ | ~~confirmation off~~ | **REVERSED 2026-08-17 — see below** |

⚠ **`execCancelBars` and `execCancelFlip` were CHECKED AND DELIBERATELY LEFT UNGATED.** They look
inert at market — no resting limit — but Pine fills a market entry on the NEXT bar's open, so the
order is pending for one bar and the session/window cancels can genuinely fire on it. **A control
that acts once is not a control that acts never.**

🔴 **THAT `showSosMark` GATE WAS WRONG AND WAS REVERSED ONE DAY LATER (2026-08-17), AND THE
REVERSAL IS THE LESSON.** The trade-off was named honestly at the time — gating it made the
confirmation-off mode unreachable from the panel — and the name was allowed to win anyway. Then
`pbRequireConf` shipped defaulting **OFF**, and the control that answers *"what would requiring
confirmation have cost me?"* was greyed out for every user on the default settings, at exactly the
moment it was most useful. **A cascade gate is a claim about which settings are worth reaching, and
it goes stale the instant a DEFAULT moves.** The input is now ungated and renamed *"Mark the shift
of structure next to a setup"*, which is true in both modes. ⚠ **Re-read every `active =` in a file
whenever you change a default in it** — nothing fails, nothing goes red, the control just quietly
stops being available.

🔴 **THE SAME AUDIT MISSED A GATE POINTING THE OTHER WAY: `pbConfTf` WAS GREYED WHILE THREE THINGS
STILL READ IT.** Turning confirmation off does not stop the confirmation timeframe being consumed —
`execBeOnShift` (breakeven when the small timeframe turns against the trade), `execCancelFlip`
(pull a resting order on an opposite shift) and `showSosMark` all read `newConfShift`, which is
derived from `pbConfTf` with no reference to `pbRequireConf`. So the panel greyed a live control and
the user had no way to change a timeframe that was still deciding where their stop went. Now
ungated, with the three consumers named in its tooltip. ⚠ **An audit that only asks "is this input
inert?" finds half the defects. Ask the other direction too: "is anything still READING an input I
have greyed?"** The first shape is a dead control; the second is a lie about what the strategy is
doing, and it is the worse of the two.

⚠ `pbConfWhen` was re-checked in the same pass and its gate is CORRECT — it is read only inside
`confAtZone = pbRequireConf and ...`, so confirmation off makes it genuinely inert.

⚠ **The grouping was done by CHANGING `group =` STRINGS, never by moving declarations.** A new
`GS` group pulls the four confirmation inputs and the two marker inputs together, and TradingView
places a group where its FIRST input is declared — so it lands second without a single `input.*`
call changing position. **Moving the declarations would have reset every later input of that type
on Aaron's charts; changing a group string resets nothing.** That is the only safe way to reorganise
this panel and it should be the default move.

### 🔴 This file's panel is ordered by PROVENANCE, and it is the only one here that is

**Aaron, 2026-08-16: *"rearrange the inputs into things that came from him 100% and things that
came from us… so I could see them logically."*** Groups **1-4 are HIS MODEL**, groups **5-10 are
OURS**. The other five strategy files keep the house contract that groups by what a setting
CHANGES; this one does not, and the exception is deliberate rather than drift.

**Why it was worth breaking the contract.** This file is a PORT of somebody else's documented
model, and its six flat backtests were explained almost entirely by rules of his we had not built
and rules of ours he does not have. Grouping by function hid exactly that — his 5R target and our
minimum-stop guard sat in one box called *Stop & targets*, so nothing on the panel said one was the
model and the other was our own scar tissue. ⚠ **Do NOT propagate this layout to the other files.**
They are not ports of an outside model and the provenance split would mean nothing there.

⚠ **Group 6, *choices his method leaves open*, is where to look first when a result disagrees with
his book.** Every input in it is a number standing in for a decision he makes by eye and never
states. ⚠ **Groups 8-10 cannot move a trade** — if a result differs, it is in 5, 6 or 7.

### 🔴 What invalidates the trade — the gap, or the sweep? (`execStopFrom`, 2026-08-16)

**Aaron: *"I don't think the size of a fair value gap should ever matter. If we had a shift of
structure and that gap was one dollar, I don't care — put the stop behind the low of the session
that swept."*** He is describing a different theory of invalidation, and he is right that it is a
theory rather than a fact, so it is a switch and **neither setting has been measured.**

| setting | stop sits past | consequence |
|---|---|---|
| **The gap** (default, and what this file always did) | the far edge of the entry zone | a $1 gap gives a $1 stop; thin gaps get refused by the minimum-stop floor |
| **The sweep extreme** | the high (short) / low (long) the session made taking the pool | gap size stops mattering; stops widen a lot |

🔴 **It takes the FURTHER of the two, never the sweep alone.** A gap that extends past the sweep
extreme would otherwise put the stop INSIDE the entry zone, where price simply filling the gap you
entered on takes you out. That case is rare and silent, which is exactly why it is handled here
rather than left to be discovered in a trade list.

🔴 **THE TARGETS MOVE WITH IT, and this is the thing that will mislead a comparison.** Under Fixed R
the first target is 5× the stop distance — so a $10 stop aims fifty dollars away where a $1 stop
aimed five. **Switching this changes the entry, the size, the target and the refusal rate at once**,
so a single before/after number tells you almost nothing about which effect did the work. Read the R
distribution and the trade count, not the net.

⚠ **The sweep extreme is the RUNNING extreme of the leg**, snapshotted when the limit is armed —
not the single bar that first crossed the pool. A session that keeps pushing moves the level, which
is the honest reading of "the session's low" and also means an order armed late carries a wider stop
than one armed early.

### 🔴 The minimum-stop floor: 0.08% → 0.03%, and why it is not zero

**The guard came from THIS REPO, not from the course** — it is in all ten strategy files here, and
it is scar tissue from a sizing bug that once put a 54-lot order on a $2,000 account. **He does the
opposite**: *"you'll see tight stops when there's no room, but there's no wiggle room."* A tight
stop is how a 6.8x average winner happens at all, so the guard could only ever delete his best
trades.

🔴 **It is LOWERED, not removed, and the rule generalises past this file: a floor on stop distance
is a proxy for a COST, so it must be set from the measured cost and not from a round number.** The
runs bill no spread and no commission; Vantage's measured XAUUSD spread is **$0.22**
(`backtest/fills.py`). That is 6% of a median stop here, 22% of a $1 stop, over half of a $0.40 one
— **so the tightest setups are exactly the ones a zero-cost backtest flatters most.** 0.03% ≈ $1 of
gold today: his stops get through, the unpayable ones still do not. ⚠ **Turn the spread on in the
tester before reading the trades this gains you**, or you are scoring against a book that never
paid to enter. ⚠ **What the floor COST is unmeasurable from a trade list** — a refused setup never
appears in one. Numbers behind all of this: `../../docs/SMC_SESSION_SWEEP_SPEC.md`.

**1 · A drawing on a strategy chart is a CLAIM, and a claim about a PLAN must be withdrawn when
the plan does not happen.** Reward bands are painted at the fill, entry → target, because that is
what the trade is aiming at. Nothing removed them on the close, so a −1R stop-out left a
full-height green band running to a price nothing went near — the chart said won, the result said
−1R. On the close the target bands are deleted, the body band is repainted entry → the REAL exit,
and the red band is clipped to the worst price the trade actually SAW rather than the stop it never
reached. ⚠ `mpc_strategy.pine` already carried this in writing (*"every band comes from the
strategy's own closed-trade log… never a fib level it merely aimed at"*) and the palette pass
copied its COLOURS without copying the rule.

**2 · A setup that never filled must not look like one that traded.** Most armed setups die — the
session rolls, the direction flips, price never returns. Each used to leave a full-colour drawing
identical to a real trade's, so a long setup that never happened sat beside a short that did.
Cancelled setups fade to grey and take a `✕`. An armed setup draws no text at all; the `✕` is the
only text a setup ever gets, because it is the only case with nothing else to speak for it.

**3 · A label naming a precondition that every drawn setup already satisfies is noise.** Each setup
carried `London sweep` / `Asia sweep`, overlapping the result label — and a setup here cannot arm
without a sweep, so the words restated the drawing's own existence. Replaced by the thing the label
alluded to: **a dashed double-width line at the price actually taken, from the bar it was taken
on.** The precondition is noise; the level it fired on is information.

**4 · A self-imposed cap that truncates history is indistinguishable from a bug.** Session boxes
were capped at 30 — three a day, so ten trading days — and simply stopped mid-chart. Nothing here
evicts anything now; TradingView's own 500-object ceiling is the only limit, and it drops the
oldest object of a type. ⚠ That trades whole-drawing eviction for per-object, so the far-left edge
can dissolve in pieces. ⚠ The families compete for that 500: **count trades in the Strategy
Tester's list, never off the chart.**

**5 · Never put two numbering systems on one panel.** Group headings carry the contract's numbers;
input titles carried the video's five step numbers. Reading down, the panel counted 4, 1, 2, 3, 5,
4, 6 and a strictly ordered model looked like it had none. ⚠ The tension is real and general: **the
contract groups by what a setting CHANGES, and a sequential model's steps do not map onto that
one-to-one.** Both orderings are right. Carry the group NUMBER and the step NAME — never both
numbers. Worth checking on any strategy here whose rules are a named sequence.

**6 · If a limit bounds what a reader can SEE, say so where it is seen.** Both affected tooltips
state their own limit. A cap discovered on the chart reads as a defect; a cap stated in the panel
reads as a boundary.

### 🔴 The ORDER of steps 3 and 4 is an OPEN QUESTION, and it is now a switch

Aaron, 2026-08-15: *"Why would I look for the gap after a one-minute shift? Shouldn't I look for
the point of interest first, and then once price is in it, look for the shift?"* He is describing
the standard SMC sequence, and **the objection is a good one on the mechanics**: under the video's
listed order the lower timeframe turns AGAINST the move and price then has to push FURTHER to reach
the resting limit.

`pbConfWhen` ships **Before the zone** (the video's listed order — shift, then rest a limit) with
**At the zone** as the alternative (freeze the zone at the sweep, price must travel into it, only a
shift that happens *inside* it counts, entry at MARKET).

⚠ **Neither branch is the "correct" one and the file says so at the input.** `education/learned/`'s
note is a transcript of what he SAID, and **its own header records that frame selection largely
missed the chart walkthrough** — so the five steps' ORDER is established and the MECHANICS are not.
**The honest move was a switch and a measurement, not a rewrite in either direction.**

⚠ **AT-THE-ZONE has to FREEZE the zone and could not reuse the live scan**, and the reason is the
kind that produces zero trades with nothing to debug: a gap price has traded into is marked
touched, so with untouched-only on **the scan drops the zone at the exact moment price arrives in
it** — the condition you are waiting for destroys the thing you are waiting on. `armDir` is stored
beside the frozen zone so a direction flip mid-session cannot hand a bear zone to a long.

⚠ **Two gates change meaning in that mode and both were adjusted rather than left to misfire**: the
"limit must rest on the far side of the market" test (block 6) is about a RESTING order and does
not apply to a market entry, and "maximum distance to the zone" is meaningless once price is inside
it. ⚠ **That one gate hides TWO waits that need opposite responses** — *price never reached the zone*
(a market fact) against *it got there and no shift came* (a rule fact). The state panel used to split
them and **the panel was removed 2026-08-16**, so nothing reports the difference now. Read it off the
chart, or put the panel back.

🔴 **THE MOVE THAT ALMOST SHIPPED A COMPILE ERROR IS THE REUSABLE PART.** The new block was written
into the LOCATION section, where the rest of the sweep state lives — and it reads the zone scan,
which is defined further down the file. Pine resolves top-down, so that is `CE10272`, and it would
only have appeared on the paste. **It was caught by a mechanical check, not by reading**: for every
top-level global, assert its first textual use is not before its declaration line. 185 globals, run
in seconds, and it is the same defect class `check_active_order.py` exists for arriving through a
different door. ⚠ **Run both after any block move in a Pine file.** The organising instinct — put
new state with the state it belongs to — is exactly what puts a read above its write.

### What this file does NOT have, and why

⚠ **`1 · Confirmation table`** — no JARVIS table, same as BOS, D and H4.
⚠ **`9 · Drawing: fibs`** — no fibs.
⚠ **`12 · Debug`** — held one per-event Pine Logs line; cut on Aaron's call. What it reported is on
the chart already, from the same state.
🔴 **`2 · Market structure` — the one place "the same four toggles everywhere" cannot be honoured
by porting.** Every other file runs its engine on the CHART frame, so drawing it is free; H4 ported
~1,000 lines in on that basis. This one runs the engine inside `request.security` on the 15m and
1m, and **Pine cannot draw from in there.** A chart-frame copy would paint the 5m's swings while
the strategy trades the 15m's — a chart that disagrees with the file under it, which is worse than
no drawing. The honest fix is a FEATURE (return the swing prices through the security call and draw
those), not a port. **Open — Aaron's call.**

⚠ **The six session strings are hardcoded, not inputs, and that is the exception to the collapse
rule rather than an example of it** — they DECIDE trades (the sweep pool is read off them). It is
safe only because every Pine file here has carried the identical DST-aware values since
2026-07-31, so a divergence would be a bug and not a setting. **A change to them belongs in every
file that carries the block.**

---

## DELETED 2026-08-15 — the D strategy, and the lessons that outlive the file

`mpc_d_strategy.pine`, `mpc_d_strategy_export.pine` and `docs/MPC_D_STRATEGY_SPEC.md` were
removed at Aaron's instruction. Recover any of them from git history.

**Two reasons, and the second is the one worth recording.**

1. **It never earned its place.** `docs/STRATEGY_WORKFLOW.md` had it at stage 3 of 6 with the
   verdict already written: its one measurement was *indistinguishable from zero*, and nothing
   had moved on it since 2026-08-06.
2. 🔴 **Its VOCABULARY was colliding.** D described its middle leg as a "shakeout"
   (`dCtrBosMax` = "how much the shakeout may break before it stops being a shakeout"), and the
   Retail Shake Out (RSO) model now owns that word. **Two setups sharing one term in one repo is
   how a rule gets read backwards** — the same failure this file's palette and side-recording
   sections were both written about. One word, one meaning.

⚠ **Deleting the file does NOT delete what it taught, and three of its lessons are load-bearing
elsewhere in this repo.** They are kept in place deliberately:

- **The margin trap.** D's own tooltip said "10 BUSTS THE ACCOUNT". `mpc_realign_strategy.pine`
  then had to learn it again from an empty Strategy Tester report — see its entry below.
- **The palette rule.** D applied the TABLE palette to its TRADES, so a winner drew in the wrong
  colour. That is why `## THE ANNOTATION PALETTE` exists.
- **Record the side, never infer it.** `mpc_h4_sweep_strategy.pine` carries the block D paid for,
  lifted byte-for-byte, and it stands on its own now.

Every comment that pointed at the file was retargeted rather than left dangling.

## Key paths & entry points

- `indicators/strategies/mpc_strategy.pine` — Aaron's brother's "MPC-JARVIS" backtest script: the same engine as `mpc_assistant.pine`, converted from `indicator()` to `strategy()` and given an execution layer at the end (A+ sequence entries, fib TP ladder, %-risk sizing). [Detail](../docs/INDICATORS_BUILD_NOTES.md#indicatorsmpcstrategypine)
- `indicators/strategies/smc_session_sweep_strategy.pine` — **the five-step session-sweep model from the 2026-08-11 video note, as a `strategy()`** (built 2026-08-11 as `mpc_m15_playbook_strategy.pine`; brought onto the panel contract and the palette 2026-08-14; renamed 2026-08-15 — see the section above). ⚠ **NEVER COMPILED, never run, no number of any kind exists for it.** No export twin, no Python port, no `compare_*.py`. ⚠ **Section `2 · Market structure` is deliberately absent** and the reason is a real constraint rather than a skip — its engine lives inside `request.security`, so nothing can draw from it. [Detail](../docs/INDICATORS_BUILD_NOTES.md#indicatorssmcsessionsweepstrategypine)
- `indicators/strategies/mpc_h4_sweep_strategy_export.pine` — **the H4 sweep's decision-stream twin (2026-08-12).** `mpc_h4_sweep_strategy.pine` + one appended block, body byte-identical apart from line 166's title; **43 `plot(` columns** (42 here + the parent's own Trend EMA). [Detail](../docs/INDICATORS_BUILD_NOTES.md#indicatorsmpch4sweepstrategyexportpine)
- `indicators/strategies/mpc_b_leg_strategy.pine` — a FORK of `mpc_strategy.pine` that trades ONLY the B LEG (the SOS whose retrace arrived late), split out 2026-07-24 to run PARALLEL to the A+ bot. [Detail](../docs/INDICATORS_BUILD_NOTES.md#indicatorsmpcblegstrategypine)

- `indicators/strategies/mpc_realign_strategy.pine` — **the REALIGN strategy (built 2026-08-13).** A standalone `strategy()`, NOT a fork of `mpc_strategy.pine`: it embeds `mpc_assistant.pine`'s `MTFStruct` block verbatim (lines 1462-1808) and runs it twice through `request.security`, once on the 15m external frame and once on the chart frame. Trades a **false break** — bullish 15m trend, a bearish SOS that is a structural liquidity grab, then a lower-frame internal realignment back with-trend — entering at market on the realignment, **before** the external SOS that later confirms it. Python port: `strategies/python/mpc_realign/` (its own CLAUDE.md); spec: `docs/MPC_REALIGN_SPEC.md`. **COMPILES and has been RUN** (XAUUSD 5m, 2020-2026: 143 trades / +41.35% / PF 1.617 / maxDD 17.79% / win 30.77%). ⚠ **NO export twin and NO `compare_realign.py`** — the Pine and the Python agree on total R and have never been diffed bar for bar. ⚠ **It does NOT yet follow the numbered-input-panel contract at the top of this file** (`a8fa395`, 2026-08-12) — it predates it by a day. Aligning it is a reorder, so it needs the same "Reset settings to defaults" treatment every other file needed. 🔴 **TWO MARGIN TRAPS, ONE OF WHICH REPORTS NOTHING AT ALL.** Pine's DEFAULT margin is 100% (full cash), and this strategy sizes by `risk ÷ stop distance` — ~$500k notional on a $10k account — so **every order was silently refused and the Strategy Tester showed an empty report with no error anywhere.** Setting `margin = 0` "fixed" it and was worse: unbounded leverage gave **−98.10% / PF 0.193** with the account dead in the first months of an 8-year run. Now `margin_long/short = 0.2` (500x, matching every other strategy file here) with `riskPct` defaulted **10 → 1.0**. **This repo had already recorded the identical lesson in `mpc_d_strategy.pine`'s own tooltip — "10 BUSTS THE ACCOUNT" — and it had to be learnt again from the Strategy Tester rather than from the file one directory over.** ⚠ **The runner trail anchors on the EXTERNAL frame's confirmed swings (`hConfLo`/`hConfHi`), not the chart frame's** — the first build used the chart frame, which is a different, tighter trail on a strategy whose whole thesis is a 15m structure.
- `indicators/strategies/mpc_realign_strategy_export.pine` — **DOES NOT EXIST YET.** It is stage 3 of `docs/STRATEGY_WORKFLOW.md` and the prerequisite for `compare_realign.py`. Until it does, every REALIGN number in this repo is a lab finding.

---
