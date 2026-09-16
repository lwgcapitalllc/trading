# CLAUDE.md — strategies/tradingview/

**Purpose:** The Pine `strategy()` sources — the files that place orders in the TradingView
Strategy Tester, plus their instrumented `_export` twins.
**Scope:** This file owns everything true of a STRATEGY Pine file: the numbered input-panel
contract, the trade annotations, and the colour palette. It does NOT cover the `indicator()`
sources those strategies were cut from — that is `indicators/engines/CLAUDE.md` — and it does
not cover the Python ports, which own their own CLAUDE.md under `strategies/python/`.
🔴 **THIS FOLDER MOVED ON 2026-09-02, AND SO DID THIS FILE.** It was
`indicators/strategies/CLAUDE.md`. A Pine `strategy()` file is strategy source for the TradingView
runner platform, so these files now sit beside the MT5, NinjaTrader and Python strategies rather
than under `indicators/`, which is organised by language. The `indicator()` engines they were cut
from did NOT move and are still `indicators/engines/`. Full survey, and the four things that were
not a text substitution: `../../docs/TRADINGVIEW_STRATEGY_MOVE_PLAN.md`.

⚠ **`research/` next door is a DIFFERENT KIND OF FILE and none of the rules below apply to it.**
Two hand-tested Pine ideas with no panel contract, no export twin, no parity gate and no Python
port. A new strategy starts there and moves up here when it earns a twin. ⚠ **Read the folder, not
the filename** — this is the same mistake the declaration rule already exists to stop.

## 🔴 The export twins are GENERATED — edit the parent or its block, never the twin (2026-09-10)

`<name>_export.pine` = `<name>.pine` with " Export" on its title + `export_blocks/<name>.pine`, all
six built by `tools/build_export_twins.py` and checked by **step 18** of `scripts/run_all_tests.sh`
(`--check` regenerates and diffs). 🔴 **Five of the six were kept BY HAND until then**, and a twin
that drifts proves parity against a file nobody trades while its gate stays green. ⚠ The first
build was byte-identical on five; the session sweep's twin had kept its parent's title and now
follows the one rule (one line, no column moves). ⚠ A `_export.pine` with no block file is REFUSED
as a hand-kept copy, and a twin over Pine's 64-plot cap is refused before it can fail on paste.
⚠ `tools/build_extreme_leg.py` still writes the extreme leg's parent, then calls the shared builder.

⚠ **Every `../` link in this file was repointed in that move and each was checked to resolve.** The
one exception is `m15_playbook.pine`, which is dead on purpose — the file was deleted on
2026-08-15 and the sentence around the link says so.

**Last reviewed:** 2026-09-02 — moved here from `indicators/strategies/`; nothing in any `.pine`
changed and the three panel checks were re-run green on all fourteen at the new paths.
2026-08-15: **`m15_playbook_strategy.pine` is now `smc_session_sweep_strategy.pine`, and
`../../indicators/engines/m15_playbook.pine` was DELETED** (Aaron, 2026-08-15; see *The session
sweep strategy* below). Before that it was brought onto the panel contract and the palette, then
had two drawing bugs found on a chart. Full narrative in
`../../indicators/docs/INDICATORS_BUILD_NOTES.md`. The `active =` declaration-order check this file
has been asking for since 2026-08-12 now exists and has been run on all fourteen files.
2026-08-13: split out of `indicators/CLAUDE.md` when the Pine sources were divided into
`strategies/` and `engines/`; the rules below moved verbatim.


## What lives here, and the one thing that decides it

A file is in this folder if its declaration is `strategy(`, and in `../../indicators/engines/` if it is
`indicator()`. That is the whole rule, and it is mechanical on purpose. **Check the declaration,
never the filename**: `structure_engine.pine` reads like a strategy component and is an indicator,
and `smc_session_sweep_strategy.pine` had an `indicator()` twin next door under a near-identical
name until that twin was deleted on 2026-08-15.

⚠ **Every file here is half of a parity gate.** The `_export` twin is the instrumented copy a
`compare_*.py` diffs against its Python port, and it has to move with its parent — a change to
`sos_fade_strategy.pine` that does not land in `sos_fade_strategy_export.pine` makes the gate green about
a file nobody trades. `realign_strategy.pine` gained its twin on 2026-09-16; its
`compare_realign.py` exists and has never been RUN, so every REALIGN number is still a lab finding.

---

## 🔴 THE PROSE LIVES IN `docs/`, NOT IN THE PINE (2026-08-16, Aaron's call)

**A Pine file here is CODE. Its explanation lives in `docs/<family>.md`, and the Pine carries
a one-line pointer.** These files are 130–320 KB each and **a third of every byte was prose**,
so reading one to answer a question about its entry logic spent a quarter of a context window
on commentary that was not the question — sessions ran out of tokens inside a single file.

| | |
|---|---|
| where prose goes | `strategies/tradingview/docs/<family>.md` |
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
Numbers, method and the three tests that read these files: `../../indicators/docs/INDICATORS_BUILD_NOTES.md`.

---

## 🔴 TOOLTIPS ARE PLAIN ENGLISH AND ONE OR TWO SENTENCES (2026-08-16, Aaron's call)

**A tooltip says what the setting DOES, in words a person can read at a glance.** They had grown
into paragraphs of measured history, parity warnings and rationale — hover one and you could not
tell what the toggle was for. All 663 were rewritten on 2026-08-16; numbers and method are in
`../../indicators/docs/INDICATORS_BUILD_NOTES.md`.

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

## PHASE 1 — the trade annotations, and the one piece that CANNOT be ported

The other half of the standardisation: *"as I move to strategies, nothing seems different other
than the logic of the strategy."* Same blocked marker, same missed callout, same position box,
same entry triangles, on every file.

| annotation | SOS Fade | B-LEG | BOS | D | H4 | M15 |
|---|---|---|---|---|---|---|
| position box / result bands | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ **new** |
| entry callout, recoloured on close | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ **new** |
| **entry triangles** | ✅ | ✅ | ✅ | ✅ **new** | ✅ | ✅ **new** |
| **blocked-setup tag (pink)** | ✅ | ✅ | ✅ | ✅ | ✅ **new** | ✅ |
| missed-setup callout (2-of-3) | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |

**D gained the entry triangles.** `plotshape` is a GLOBAL-SCOPE call, so it cannot live inside
the fill block and the fill edge is written out at top level instead — the SAME test the fill
block uses, so a triangle can never appear on a bar the tracker did not treat as a fill. Gated
on `execShowPosBox` like SOS Fade, because the triangles are part of the position drawing.
⚠ **They are not redundant with the boxes**: a scratch paints a risk block a few pixels tall and
reads as no trade at all, which is exactly when you need to see where it opened.

**H4 gained the blocked-setup tag.** It has carried the refusal CODES since its export twin
landed and had nothing on the chart that drew them. It reads `hTrigCode` — already written at
decision time — and re-derives nothing, so the tag and the export's `px_blk` cannot tell
different stories.

🔴 **The side had to be RECORDED rather than inferred, and `d_strategy.pine` already paid for
learning that.** D's tag read direction off the SOS on the same bar, correct only while every
candidate arrived on one — and the moment a second entry mode existed, every candidate drew as a
SHORT. Here the equivalent shortcut is reading `trigShort`, a per-bar local: right today, silent
the day a refusal is reported from anywhere but those two blocks. `hTrigDir` is written beside
`hTrigCode` instead.

⚠ **No dedupe, and that is not an omission.** A trigger fires at most once per H4 window
(`firedWindow`), so one refusal is already one bar. SOS Fade needs its `sosBar + code` key because a
setup there can stay refused for twenty consecutive bars. ⚠ **`hTrigBar == bar_index` is what
scopes it** — the four `hTrig*` fields are `var` and keep the last trigger's values for ever.

## 🔴 THE CONVENTIONS ARE CHECKED NOW, BECAUSE WRITING THEM DOWN DID NOT HOLD (2026-09-16)

**Aaron, 2026-09-16:** *"all pine strategies and export must have these conventions. I believe I
stated this before and I did an audit and now we back to here."* He had. He did. And `realign`
was still built, measured six times and taken to the edge of a parity gate with **no position
box, no result callout, no entry triangles, no refusal tag and ad-hoc input groups.**

**A convention enforced by remembering to read this file is not enforced.** `scripts/check_pine_conventions.py`
now audits every `*_strategy.pine` here for the numbered panel, the six annotations and the three
standard RESULT colours, and it is **meant to fail the build the same way `check_pine_blocks.py`
does for the engine copies.**

🔴 **IT IS NOT WIRED INTO `scripts/run_all_tests.sh` YET, AND THIS SECTION SAID IT WAS FOR A DAY.**
The two files in the table below still fail it, so wiring it would land a red build on everyone —
run it by hand (`python3 scripts/check_pine_conventions.py`) until they are fixed, and wire it
then. ⚠ **A doc claiming a check runs when it does not is worse than no doc**: it is exactly the
"a label is a CLAIM about code somewhere else" failure in rule 7, committed by the very file
written to stop a convention from drifting.

⚠ **A DIFFERENT Pine check DID land, inside step 14** — `indicators/tools/check_continuation.py`,
green on all 43 Pine files, so it cost nobody a red build. A wrapped expression indented a
multiple of four is read by Pine as a new block and the line above it is reported as ending
unfinished; `realign_strategy.pine` refused to compile on exactly that on 2026-09-16, and because
a twin is GENERATED the identical break arrived in both halves of the parity gate. Any
non-multiple of four works.

What the first credible run found, beyond realign:

| file | what was missing |
|---|---|
| `extreme_leg_strategy.pine` | **no trade drawing of any kind** — it draws structure and never draws a trade |
| `smc_session_sweep_strategy.pine` | a position box, but **no BREAKEVEN grading** (a scratch drew as a win or a loss) and no entry triangles |

⚠ **The palette rule is checked by PRESENCE of the three result colours, never by absence of
others.** "No hex outside the palette" cannot be decided by text — these files legitimately colour
sessions, gaps, the confirmation panel and the B-LEG overlay — and the first version of the script
reported **all seven files as broken**. A check with false positives gets ignored, which is the
exact failure it exists to prevent. Same reason it resolves `G1`-style group CONSTANTS instead of
reading literal `group = "…"` strings: matching only literals called a compliant panel "no
numbered groups at all".

⚠ **An exemption is a decision with a name on it** (`_EXEMPT` in the script), never a quiet skip.
`recovery_strategy.pine` is the only one: it is a sizing rule, draws no trade of its own, and has
no twin by design.

⚠ **Bringing a file onto the panel contract REORDERS its inputs, which resets saved values on any
chart already running it.** Do it BEFORE an export is taken, not after, and say that *"Reset
settings to defaults"* is needed once. `realign` was brought on this way on 2026-09-16, deliberately
ahead of its first CSV.

⚠ **Nothing here compiles Pine.** The check proves a layer is PRESENT, not that it draws correctly.
A file can satisfy every rule and still be wrong on a chart.

## THE ANNOTATION PALETTE — one result, one colour, `sos_fade_strategy.pine` is the standard

Aaron, 2026-08-12: *"the colors of the labels that show if a trade had won or lost, if it broke
even, if it was blocked, what was the max drawdown, where the price went, the long and short
positions — all those colors are not consistent across all the pines. They should be the same
colors. Use MPC, the SOS Fade strategy as a standard."*

**Every colour a TRADE is drawn in is copied from `sos_fade_strategy.pine`. Change a value by changing
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

## Key paths & entry points

- `strategies/tradingview/sos_fade_strategy.pine` — Aaron's brother's "MPC-JARVIS" backtest script: the same engine as `mpc_jarvis.pine`, converted from `indicator()` to `strategy()` and given an execution layer at the end (SOS Fade sequence entries, fib TP ladder, %-risk sizing). [Detail](../../indicators/docs/INDICATORS_BUILD_NOTES.md#indicatorsmpcstrategypine)
- `strategies/tradingview/smc_session_sweep_strategy.pine` — **the five-step session-sweep model from the 2026-08-11 video note, as a `strategy()`** (built 2026-08-11 as `m15_playbook_strategy.pine`; brought onto the panel contract and the palette 2026-08-14; renamed 2026-08-15 — see the section above). ⚠ **NEVER COMPILED, never run, no number of any kind exists for it.** No export twin, no Python port, no `compare_*.py`. ⚠ **Section `2 · Market structure` is deliberately absent** and the reason is a real constraint rather than a skip — its engine lives inside `request.security`, so nothing can draw from it. [Detail](../../indicators/docs/INDICATORS_BUILD_NOTES.md#indicatorssmcsessionsweepstrategypine)
- `strategies/tradingview/h4_sweep_strategy_export.pine` — **the H4 sweep's decision-stream twin (2026-08-12).** `h4_sweep_strategy.pine` + one appended block, body byte-identical apart from line 166's title; **43 `plot(` columns** (42 here + the parent's own Trend EMA). [Detail](../../indicators/docs/INDICATORS_BUILD_NOTES.md#indicatorsmpch4sweepstrategyexportpine)
- `strategies/tradingview/b_leg_strategy.pine` — a FORK of `sos_fade_strategy.pine` that trades ONLY the B LEG (the SOS whose retrace arrived late), split out 2026-07-24 to run PARALLEL to the SOS Fade bot. [Detail](../../indicators/docs/INDICATORS_BUILD_NOTES.md#indicatorsmpcblegstrategypine)

- `strategies/tradingview/realign_strategy.pine` — **the REALIGN strategy (built 2026-08-13).** A standalone `strategy()`, NOT a fork of `sos_fade_strategy.pine`: it embeds `mpc_jarvis.pine`'s `MTFStruct` block verbatim (lines 1462-1808) and runs it twice through `request.security`, once on the 15m external frame and once on the chart frame. Trades a **false break** — bullish 15m trend, a bearish SOS that is a structural liquidity grab, then a lower-frame internal realignment back with-trend — entering at market on the realignment, **before** the external SOS that later confirms it. Python port: `strategies/python/realign/` (its own CLAUDE.md); spec: `docs/REALIGN_SPEC.md`. **COMPILES and has been RUN** (XAUUSD 5m, 2020-2026: 143 trades / +41.35% / PF 1.617 / maxDD 17.79% / win 30.77%). ✅ **Export twin built 2026-09-16** (`export_blocks/realign_strategy.pine`, generated like the other six); `compare_realign.py` and a real CSV are still outstanding, so the Pine and the Python have still never been diffed bar for bar. 🔴 **AND THE FIRST THING THAT SURFACED IS A REAL DIVERGENCE, FOUND BY READING RATHER THAN BY THE GATE: this file trails the EXTERNAL frame's confirmed swings and the Python port has always trailed the CHART frame's.** The line's own comment said "the chart frame's" — describing the PORT, not this file — which is almost certainly how it happened. Worth ±60R in the port, and the trail IS the exit here since nothing banks at a target. The comment is fixed and the frame is now the `trailFrame` input, exported in `cfg_enum1`, so a CSV states which one it ran. ⚠ **Both frames' swings are exported** (`px_htf_conf*` and `px_cht_conf*`) so the gate can say *wrong frame* rather than *numbers differ*. ⚠ **It does NOT yet follow the numbered-input-panel contract at the top of this file** (`a8fa395`, 2026-08-12) — it predates it by a day. ⚠ **The four inputs added 2026-09-16 (retest entry, flat-before-close, trail frame) are APPENDED AFTER THE LAST EXISTING INPUT OF EACH TYPE**, not filed into their groups, and that is deliberate: TradingView keys a saved chart's values off declaration order WITHIN A TYPE, so inserting one higher up silently resets every later input of that type on every chart already running this script. The panel reads slightly out of order as the price of not doing that. Aligning it is a reorder, so it needs the same "Reset settings to defaults" treatment every other file needed. 🔴 **TWO MARGIN TRAPS, ONE OF WHICH REPORTS NOTHING AT ALL.** Pine's DEFAULT margin is 100% (full cash), and this strategy sizes by `risk ÷ stop distance` — ~$500k notional on a $10k account — so **every order was silently refused and the Strategy Tester showed an empty report with no error anywhere.** Setting `margin = 0` "fixed" it and was worse: unbounded leverage gave **−98.10% / PF 0.193** with the account dead in the first months of an 8-year run. Now `margin_long/short = 0.2` (500x, matching every other strategy file here) with `riskPct` defaulted **10 → 1.0**. **This repo had already recorded the identical lesson in `d_strategy.pine`'s own tooltip — "10 BUSTS THE ACCOUNT" — and it had to be learnt again from the Strategy Tester rather than from the file one directory over.** ⚠ **The runner trail anchors on the EXTERNAL frame's confirmed swings (`hConfLo`/`hConfHi`), not the chart frame's** — the first build used the chart frame, which is a different, tighter trail on a strategy whose whole thesis is a 15m structure.
- `strategies/tradingview/realign_strategy_export.pine` — **DOES NOT EXIST YET.** It is stage 3 of `docs/STRATEGY_WORKFLOW.md` and the prerequisite for `compare_realign.py`. Until it does, every REALIGN number in this repo is a lab finding.

---

## The notes — read the matching file BEFORE touching its code

🔴 **This file was 152 KB on 2026-09-13 and loaded in full every time anyone opened
a file in this folder.** Everything outside the rules above moved VERBATIM into
`notes/` — nothing reworded, nothing dropped.

**How to write here from now on:** a rule gets ONE line under its topic below; its story and
evidence go in that topic's notes file. A notes file satisfies the commit hook's doc check.

⚠ **An old pointer to a section of this file still resolves** — every moved heading is
listed below under the notes file that now holds it.

### `notes/recovery_strategy.md` — recovery_strategy.pine — the SOS Fade book plus a loss-recovery leg

**Read before touching:** `recovery_strategy.pine`, or checking whether a `sos_fade_strategy.pine` change needs to be mirrored into it.
Most-cited code: `sos_fade_strategy.pine`, `recovery_strategy.pine`, `b_leg_strategy.pine`, `bos_strategy.pine`.

- `recovery_strategy.pine` — the SOS Fade book plus a LOSS RECOVERY leg (new 2026-08-19)

### `notes/extreme_leg_strategy.md` — extreme_leg_strategy.pine — the run into the shift of structure

**Read before touching:** `extreme_leg_strategy.pine` or comparing it against its Python port.
Most-cited code: `mpc_jarvis.pine`, `extreme_leg_strategy.pine`, `h4_sweep_strategy.pine`, `extreme_leg_strategy_export.pine`, `realign_strategy.pine`.

- `extreme_leg_strategy.pine` — the run INTO the shift of structure (new 2026-08-24)

### `notes/cross_cutting_pine_fixes.md` — Cross-cutting Pine bugs — one fix, many copied files

**Read before touching:** changing any rule that is copy-pasted across strategy files, or investigating why a parity gate stayed green while two Pine files disagreed.
Most-cited code: `mpc_jarvis.pine`, `sos_fade_strategy.pine`, `b_leg_strategy.pine`, `bos_strategy.pine`, `recovery_strategy.pine`.

- 🔴 Four files carried a superseded gap cap, dormant, for five weeks (2026-09-10)
- The equal-level wick fix (2026-09-09) — all SEVEN files here, and nothing noticed for a month
- The refused-wick structure fix (2026-08-21) — every strategy file and its export twin
- The tied-extreme structure fix (2026-08-20) — all ELEVEN strategy files

### `notes/input_panel_history.md` — The input panel contract — build history

**Read before touching:** adding a new toggle to a strategy's input panel, or changing anything about the scale-in adds.
Most-cited code: `structure_engine.pine`, `d_strategy.pine`, `h4_sweep_strategy.pine`, `sos_fade_strategy.pine`, `b_leg_strategy.pine`.


### `notes/phase1_and_palette_history.md` — Trade annotations and the colour palette — build history

**Read before touching:** changing a trade annotation, a chart colour, or the Style-tab defaults on any strategy file.
Most-cited code: `bos_strategy.pine`, `sos_fade_strategy.pine`, `bos_strategy_export.pine`, `smc_session_sweep_strategy.pine`, `d_strategy.pine`, `h4_sweep_strategy.pine`.


### `notes/session_sweep_strategy.md` — The session-sweep strategy

**Read before touching:** `smc_session_sweep_strategy.pine` or its export twin.
Most-cited code: `sos_fade_strategy.pine`, `smc_session_sweep_strategy.pine`, `smc_session_sweep_strategy_export.pine`, `smc_sweep_reclaim_strategy.pine`, `m15_playbook_strategy.pine`, `mpc_jarvis.pine`.

- The session sweep gets an EXPORT TWIN, stage 3 of six (2026-08-17)
- The sweep-reclaim strategy was BUILT AND ABANDONED on the same day (2026-08-17)
- The session sweep strategy — the rules the 2026-08-14/15 pass left behind

### `notes/misc_dated_changes.md` — Other dated changes — deleted files and per-file defaults

**Read before touching:** looking for why `d_strategy.pine` no longer exists, or checking a recent default change on `sos_fade_strategy.pine`.
Most-cited code: `sos_fade_strategy.pine`, `d_strategy.pine`, `d_strategy_export.pine`, `realign_strategy.pine`, `h4_sweep_strategy.pine`, `recovery_strategy.pine`.

- DELETED 2026-08-15 — the D strategy, and the lessons that outlive the file
- `execMinAtrPct` — the dead-market floor (2026-08-26, ON at 0.08)
- SOS Fade's risk per trade defaults to 5 (2026-09-13)
