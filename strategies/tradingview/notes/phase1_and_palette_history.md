# Notes — Trade annotations and the colour palette — build history

The dated build history behind the trade-annotation standardisation (Phase 1) and the shared colour palette: why the missed-setup callout cannot port to every file, the grouping/collapsing rule, the Pine mechanics that collide with it, why 'Trades on chart' cannot be defaulted from code, why SOS Fade carries two palettes, and the one open collision. Moved VERBATIM out of `strategies/tradingview/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

### 🔴 The missed-setup callout is NOT portable to BOS, D or H4, and this file already said so

SOS Fade's callout scores a **2-of-3 confluence sequence** — arm (sweep or divergence), SOS, then the
retrace zone — and reports which one was missing. **`bos_strategy.pine` DELETED those four
inputs on 2026-07-31 with the reason written down**: *"The BOS arm is a break of structure, so
there is no sweep→SOS clock to bound and no 2-of-3 sequence to score."* The same is true of D (a
three-SOS sequence with no partial state) and of H4 (a sweep window plus a confirmation candle —
two facts, not three).

**So this is a DESIGN decision per strategy, not a port**, and inventing one would have shipped a
callout naming confluences those files do not have — the exact mistake the B-LEG block tag was
built to avoid (*"a shared annotation is shared at the DISPLAY, never at the reasons"*).

⚠ **And the cost is not symmetric.** `bos_strategy.pine` has hit **CE10117 twice**, is the
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

🔴 **THE FAIR VALUE GAP GROUP IS WHY.** In `sos_fade_strategy.pine` it reads as a drawing group
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

⚠ **Do not regroup a file and collapse it in two passes.** 76 of SOS Fade's 156 inputs are fib,
session and liquidity sub-settings Aaron has said he will never configure; each family
collapses to ONE draw toggle with the rest hardcoded at today's values. Moving them into
new groups and then deleting them is the risky work done twice, on the panel that decides
what he trades. **One pass per file: collapse, then group what survives.** SOS Fade goes
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

🔴 **THE REORDER BROKE THAT RULE IN `bos_strategy.pine` AND IT ONLY SHOWED UP ON THE PASTE
(`CE10272: Undeclared identifier "bosUseFvg"`, 2026-08-12).** `bosEntryFib` carries
`active = not (bosUseFvg and execReqFVG)` and the collapse landed it ABOVE both of them. Fixed by
moving `bosEntryFib` BELOW the whole gap block — which is where it reads better anyway, since its own
title is *"Fallback entry level"* and it is the fallback FROM that block. ⚠ **The same defect was in
`bos_strategy_export.pine`**, because the twin is a copy: **a compile error in a parent is a
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

### 🔴 SOS Fade carries TWO palettes and that is what the forks got wrong

The one real finding of the pass. SOS Fade has a **TABLE** palette (`#00E676` / `#FF5252` / `#ffde59` —
the JARVIS status panel's bull / bear / armed text) and a **POSITION** palette (`#26A69A` /
`#EF5350` / `#FF9800` — every trade drawing). They are different greens and different reds on
purpose.

**`d_strategy.pine` applied the TABLE palette to its TRADES.** A D winner drew in the green
SOS Fade uses for a table row and never in the green SOS Fade uses for a winner; its breakeven was
`#ffde59`, which is SOS Fade's *"Armed"* highlight. Nothing was wrong with either palette — the file
was reading the wrong one, and both are still there. Its state panel keeps the table colours,
which is where they belong.

⚠ **`h4_sweep_strategy.pine` had NO colour constants at all** — every value was a hex literal
at its use site, which is exactly why it drifted without anyone being able to see that it had.
The hues were mostly already SOS Fade's; the **transparencies** were not, so the same green read as a
different shade per file. It has a named block now.

⚠ **Three deliberate behaviour corrections came with it, all label-only.** D coloured its open
callout by DIRECTION (SOS Fade paints it grey — the result is not known yet, and direction is already
in the label text and the triangle); D never recoloured its leader LINE on close, so a grey line
ran into a green label; and D used white label text where every other file uses `#101014`.

🔴 **H4 had NO breakeven state, so a +0.02R scratch drew as a full WIN and a −0.02R scratch as a
full LOSS** — the two loudest colours on the chart for a trade that made nothing. It grades
against a band now. ⚠ **The band is a CONSTANT (`H4_BE_BAND = 0.15`), not an input**, because
adding an input resets every saved value on the chart and it has never been tuned here; SOS Fade
exposes it as `execBeBandR`. Promote it when the rest of H4's annotations are brought up.

### ⚠ The one collision, left OPEN rather than silently resolved

**SOS Fade itself uses `#FF9800` for two different things: BREAKEVEN and the missed-setup callout.**
H4 then uses the same orange for its trigger line and label. They are different objects in
different places, so it is not wrong — but on a chart showing both, orange has two meanings.
Recorded rather than fixed, because resolving it means changing SOS Fade, which changes the standard
and every chart running it. **Aaron's call, not a tidy-up.**

### What is NOT in this pass

Colours only. **D still draws no entry triangles and H4 still has no blocked-setup tag or
missed-setup callout** — those are missing ANNOTATIONS, not wrong colours, and they belong with
the Phase-1 annotation work. A palette pass that invented them would have hidden how much of the
annotation set is still absent.

⚠ **Nothing here touches an input, so no saved chart value moves and no panel order changes** —
this is safe to paste onto a chart already carrying the panel rebuild.
