# CLAUDE.md — indicators/strategies/

**Purpose:** The Pine `strategy()` sources — the files that place orders in the TradingView
Strategy Tester, plus their instrumented `_export` twins.
**Scope:** This file owns everything true of a STRATEGY Pine file: the numbered input-panel
contract, the trade annotations, and the colour palette. It does NOT cover the `indicator()`
sources those strategies were cut from — that is `indicators/engines/CLAUDE.md` — and it does
not cover the Python ports, which own their own CLAUDE.md under `strategies/python/`.
**Last reviewed:** 2026-08-15 — `mpc_m15_playbook_strategy.pine` was brought onto the panel
contract and the palette, then had two drawing bugs found on a chart (see *The playbook strategy* below; full narrative in `../docs/INDICATORS_BUILD_NOTES.md`). The `active =`
declaration-order check this file has been asking for since 2026-08-12 now exists and has been
run on all twelve files. 2026-08-13: split out of `indicators/CLAUDE.md` when the Pine sources
were divided into `strategies/` and `engines/`; the rules below moved verbatim.

## What lives here, and the one thing that decides it

A file is in this folder if its declaration is `strategy(`, and in `../engines/` if it is
`indicator()`. That is the whole rule, and it is mechanical on purpose — `mpc_m15_playbook.pine`
is an `indicator()` and sits next door, while `mpc_m15_playbook_strategy.pine` is a `strategy()`
and sits here. **Check the declaration, never the filename**: `structure_engine.pine` reads like
a strategy component and is an indicator.

⚠ **Every file here is half of a parity gate.** The `_export` twin is the instrumented copy a
`compare_*.py` diffs against its Python port, and it has to move with its parent — a change to
`mpc_strategy.pine` that does not land in `mpc_strategy_export.pine` makes the gate green about
a file nobody trades. `mpc_realign_strategy.pine` has **no twin at all**, which is why every
REALIGN number in this repo is a lab finding.

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

**It applies to all six strategy files, `mpc_m15_playbook_strategy.pine` included**, even though
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

## The playbook strategy — the rules the 2026-08-14/15 pass left behind

**Full narrative: `../docs/INDICATORS_BUILD_NOTES.md` → *the playbook joins the contract*.** What
is here is the instruction; that file is the evidence. Six rules, each learned by something on a
chart being wrong in a way nothing errored about.

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
it. ⚠ **The state panel splits the one gate into two waits** — *waiting on the zone* (a market fact)
against *waiting* (a rule fact) — because they need opposite responses.

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

## Key paths & entry points

- `indicators/strategies/mpc_strategy.pine` — Aaron's brother's "MPC-JARVIS" backtest script: the same engine as `mpc_assistant.pine`, converted from `indicator()` to `strategy()` and given an execution layer at the end (A+ sequence entries, fib TP ladder, %-risk sizing). [Detail](../docs/INDICATORS_BUILD_NOTES.md#indicatorsmpcstrategypine)
- `indicators/strategies/mpc_d_strategy.pine` — **the D strategy ("D as in dog, the dirty one", Aaron 2026-08-06).** [Detail](../docs/INDICATORS_BUILD_NOTES.md#indicatorsmpcdstrategypine)
- `indicators/strategies/mpc_d_strategy_export.pine` — **the D strategy's decision-stream twin (2026-08-06).** `mpc_d_strategy.pine` + one appended block, body byte-identical apart from line 60's title; 48 transparent `plot()` columns. [Detail](../docs/INDICATORS_BUILD_NOTES.md#indicatorsmpcdstrategyexportpine)
- `indicators/strategies/mpc_m15_playbook_strategy.pine` — **the five-step session-sweep model from the 2026-08-11 video note, as a `strategy()`** (built 2026-08-11; brought onto the panel contract and the palette 2026-08-14 — see the section above). ⚠ **NEVER COMPILED, never run, no number of any kind exists for it.** No export twin, no Python port, no `compare_*.py`. ⚠ **Section `2 · Market structure` is deliberately absent** and the reason is a real constraint rather than a skip — its engine lives inside `request.security`, so nothing can draw from it. [Detail](../docs/INDICATORS_BUILD_NOTES.md#indicatorsmpcm15playbookstrategypine)
- `indicators/strategies/mpc_h4_sweep_strategy_export.pine` — **the H4 sweep's decision-stream twin (2026-08-12).** `mpc_h4_sweep_strategy.pine` + one appended block, body byte-identical apart from line 166's title; **43 `plot(` columns** (42 here + the parent's own Trend EMA). [Detail](../docs/INDICATORS_BUILD_NOTES.md#indicatorsmpch4sweepstrategyexportpine)
- `indicators/strategies/mpc_b_leg_strategy.pine` — a FORK of `mpc_strategy.pine` that trades ONLY the B LEG (the SOS whose retrace arrived late), split out 2026-07-24 to run PARALLEL to the A+ bot. [Detail](../docs/INDICATORS_BUILD_NOTES.md#indicatorsmpcblegstrategypine)

- `indicators/strategies/mpc_realign_strategy.pine` — **the REALIGN strategy (built 2026-08-13).** A standalone `strategy()`, NOT a fork of `mpc_strategy.pine`: it embeds `mpc_assistant.pine`'s `MTFStruct` block verbatim (lines 1462-1808) and runs it twice through `request.security`, once on the 15m external frame and once on the chart frame. Trades a **false break** — bullish 15m trend, a bearish SOS that is a structural liquidity grab, then a lower-frame internal realignment back with-trend — entering at market on the realignment, **before** the external SOS that later confirms it. Python port: `strategies/python/mpc_realign/` (its own CLAUDE.md); spec: `docs/MPC_REALIGN_SPEC.md`. **COMPILES and has been RUN** (XAUUSD 5m, 2020-2026: 143 trades / +41.35% / PF 1.617 / maxDD 17.79% / win 30.77%). ⚠ **NO export twin and NO `compare_realign.py`** — the Pine and the Python agree on total R and have never been diffed bar for bar. ⚠ **It does NOT yet follow the numbered-input-panel contract at the top of this file** (`a8fa395`, 2026-08-12) — it predates it by a day. Aligning it is a reorder, so it needs the same "Reset settings to defaults" treatment every other file needed. 🔴 **TWO MARGIN TRAPS, ONE OF WHICH REPORTS NOTHING AT ALL.** Pine's DEFAULT margin is 100% (full cash), and this strategy sizes by `risk ÷ stop distance` — ~$500k notional on a $10k account — so **every order was silently refused and the Strategy Tester showed an empty report with no error anywhere.** Setting `margin = 0` "fixed" it and was worse: unbounded leverage gave **−98.10% / PF 0.193** with the account dead in the first months of an 8-year run. Now `margin_long/short = 0.2` (500x, matching every other strategy file here) with `riskPct` defaulted **10 → 1.0**. **This repo had already recorded the identical lesson in `mpc_d_strategy.pine`'s own tooltip — "10 BUSTS THE ACCOUNT" — and it had to be learnt again from the Strategy Tester rather than from the file one directory over.** ⚠ **The runner trail anchors on the EXTERNAL frame's confirmed swings (`hConfLo`/`hConfHi`), not the chart frame's** — the first build used the chart frame, which is a different, tighter trail on a strategy whose whole thesis is a 15m structure.
- `indicators/strategies/mpc_realign_strategy_export.pine` — **DOES NOT EXIST YET.** It is stage 3 of `docs/STRATEGY_WORKFLOW.md` and the prerequisite for `compare_realign.py`. Until it does, every REALIGN number in this repo is a lab finding.

---
