# CLAUDE.md — indicators/

**Purpose:** From-scratch Pine Script rebuild of the "Structure OS / SMC Engine" market-structure indicator (swing highs/lows, HH/HL/LH/LL, BOS, CHoCH), replicating a private TradingView indicator's behavior using a pullback-only detection method.
**Scope:** This covers Pine Script indicator development and the market-structure detection engine only. It does NOT cover trading strategy logic, risk management, or any live/backtest execution — this is a charting indicator, not a bot.
**Status:** Under construction — Stage 2b (break-gated swing structure + BOS/CHoCH) is ~95% validated against the original; Stage 3 (internal structure) and Stage 4 (multi-symbol/timeframe comparison) not started. Blocked on chart validation by Aaron before Stage 3 begins.
**Last reviewed:** 2026-08-12 (latest) — 🟢 **EVERY TRADE ANNOTATION IN EVERY STRATEGY IS NOW PAINTED IN A+'s COLOURS, AND THE CAUSE OF THE DRIFT WAS THAT A+ CARRIES TWO PALETTES.** Aaron: *"all those colors are not consistent across all the pines. They should be the same colors. Use MPC, the A+ strategy as a standard."* 🔴 **`mpc_d_strategy.pine` WAS READING THE WRONG ONE OF THE TWO.** A+ has a **TABLE** palette (`#00E676` / `#FF5252` / `#ffde59` — the JARVIS panel's bull / bear / armed text) and a **POSITION** palette (`#26A69A` / `#EF5350` / `#FF9800` — every trade drawing), and D applied the TABLE one to its TRADES: **a D winner drew in the green A+ uses for a table ROW, and its breakeven was `#ffde59`, which is A+'s "Armed" highlight.** Neither palette was wrong; the file was reading the wrong one, and both are still there — D's state panel keeps the table colours, which is where they belong. ⚠ **`mpc_h4_sweep_strategy.pine` had NO colour constants AT ALL** — every value was a hex literal at its use site, which is precisely why it drifted with nobody able to see that it had; the hues were mostly already A+'s and the **TRANSPARENCIES** were not, so one green read as a different shade per file. 🔴 **AND H4 HAD NO BREAKEVEN STATE, so a +0.02R scratch drew as a full WIN and a −0.02R scratch as a full LOSS** — the two loudest colours on the chart for a trade that made nothing. It grades against a band now; ⚠ **the band is a CONSTANT and deliberately not an input**, because an input resets every saved chart value and it has never been tuned here. ⚠ **Three label-only behaviour corrections came with it**: D coloured its open callout by DIRECTION where A+ paints it GREY (the result is not known yet, and direction is already in the text and the triangle), D never recoloured its leader LINE on close so a grey line ran into a green label, and D used white label text where every other file uses `#101014`. ✅ **VERIFIED MECHANICALLY, not by eye: all five files now carry the same five annotation hues, every declared colour constant is referenced (no typos, no dead ones), and both rebuilt export twins are a one-line body diff with D's `px_*`/`cfg_*` column set IDENTICAL to HEAD and H4's still at 43.** ⚠ **NOTHING HERE TOUCHES AN INPUT** — no saved value moves and no panel order changes, so it is safe to paste onto a chart already carrying the panel rebuild. ⚠ **The one COLLISION is left open rather than silently resolved: A+ itself uses `#FF9800` for BOTH breakeven and the missed-setup callout**, and H4 then uses the same orange for its trigger — resolving it means changing the standard and every chart running it, which is Aaron's call. ⚠ **Colours ONLY: D still draws no entry triangles and H4 still has no blocked or missed callout** — those are missing ANNOTATIONS rather than wrong colours and stay with the Phase-1 work, because a palette pass that invented them would have hidden how much of the set is still absent. Full contract below → *THE ANNOTATION PALETTE*. Same day — ⚠ **AND ONE THING AARON ASKED FOR CANNOT BE DONE IN PINE AT ALL: "Trades on chart" on the Style tab has no `strategy()` argument, confirmed against TradingView's reference AND its Strategies FAQ, which says outright that trade-marker visibility is chart-side UI with no Pine equivalent.** `display = display.none` works on a `plot`; the markers are not a plot — TradingView draws them off the order log and no order can be placed without one. **The setting lives with the script INSTANCE, so it survives ordinary code saves and comes back ON only on a fresh add or a "Reset settings to defaults"** — which is exactly what the panel reorder below costs, once, on every file. **Untick it in the same visit as the reset.** ⚠ **It matters because of DOUBLE-DRAWING, not tidiness**: every strategy here already draws its own position box, entry triangles, TP tags and result label, and `execShowPosBox`'s own tooltip says it *replaces* the built-in markers — which it only does if they are off. Applies to all six strategy files, `mpc_m15_playbook_strategy.pine` included. Full note below → *"Trades on chart" CANNOT be defaulted from code*. Same day — 🟢 **ALL FIVE STRATEGY PINE FILES NOW SHARE ONE NUMBERED INPUT PANEL, AND THE NUMBER IS THE ADDRESS.** The panel contract below, applied everywhere. **Totals: A+ 156 → 67 · B-LEG 173 → 56 · BOS 176 → 62 · D 49 → 48 · H4 sweep 47 → 48.** Sections present per file — `A+ 1-10 · B-LEG 1-10 · BOS 2-10 · D 2-8 · H4 3-8` — **and the numbering never closes up**, so `5 · Entry` is section 5 whichever file you open and a strategy with no fibs simply has no `9`. ✅ **PROVEN COSMETIC PER FILE RATHER THAN ARGUED**: every file's inputs were dumped before and after and diffed on type, default and title, and **the only entry that is new or changed in any of the five is `drawFibs`, the one input deliberately added** (D and H4 have none at all). ✅ **All five export twins rebuilt and re-verified — title-only body diff, plot counts 46 / 43 / 60 / 51 / 43, and every `px_*`/`cfg_*` column set IDENTICAL to HEAD.** ✅ **The regenerator now reports `parent-only 0` for ALL FIVE**, which is the diagnostic-log deletion showing up as a structural fact: every export is a pure append at last. 🔴 **FIVE INPUTS WERE DELETED FROM EACH OF THE THREE BIG FILES BECAUSE THEY COULD SILENTLY STOP THE BOT TRADING, AND THAT IS THE FINDING OF THE WHOLE PASS.** `Show External Fib (REQUIRED — SL/TP/entry levels)`, `Show FVG (REQUIRED — feeds entries)`, `Show All Liquidity Levels (REQUIRED — arms sweeps)`, the EQ-levels toggle and `Hide Everything Except Market Structure` each read as a drawing checkbox and each gates a CALCULATION — `showFibo` guards the block computing `fiboP1..fiboP7`, `showFVG` guards gap creation and **the gap boxes ARE the entry's storage**, `eqShow` guards the levels `eqExemptFvg` reads. **Ticking "Hide Everything Except Market Structure" stopped the bot trading, with nothing anywhere reporting it.** All are permanent calculation now; the DRAWING they hid is the new `drawFibs` (default OFF) and the existing `showSessions`. ⚠ **`showDivInput` looks like a sixth and was deliberately KEPT — it is `cfg_bits` bit 1024 and deleting it breaks `compare_strategy.py`.** ⚠ **THE FVG SETTINGS LIVE IN `5 · Entry` IN EVERY FILE**, because the gap floors, the close test, the cap, keep-until-broken and `eqExemptFvg` all change WHICH GAPS EXIST and therefore which entries fire. 🔴 **`fvgThreshPct` WAS BRIEFLY HARDCODED IN B-LEG AND WAS PUT BACK, which is the near-miss worth recording**: that fork never got A+'s timeframe split, so its gap floor has a DIFFERENT NAME, fell outside the keep-list written from A+'s vocabulary, and was collapsed to a constant like a colour. It was caught by reading the group's survivors rather than by any check. **A per-file keep-list written from a sibling's names will silently miss whatever that sibling renamed.** ⚠ **SIX STALE DECLARATION-SLOT COMMENTS WERE REWRITTEN, NOT DELETED** — each said its inputs must never be moved into the exec panel because they were the file's last string/float/bool and moving them would reset saved values. Every one was correct when written and became the exact `eqExemptFvg` failure this file already records: a specific, confident warning standing directly above the line that invalidated it. ⚠ **52 orphaned `GRP_*` / `*_SESSION_GROUP` constants were deleted across the five**, which RELIEVES the CE10117 token pressure A+ has hit twice. ⚠ **`mpc_assistant.pine`, `mpc_m15_playbook.pine` and `mpc_m15_playbook_strategy.pine` are UNTOUCHED and still carry the hazard inputs** — the first two are read-only reference, the third Aaron explicitly scoped out. ⚠ **NOTHING HERE IS COMPILED AND NO PARITY GATE HAS BEEN RE-RUN.** ⚠ **EVERY ONE OF THESE PASTES NEEDS ONE "Reset settings to defaults"** — the known, accepted price of the reorder, safe only because the file DEFAULTS are what Aaron trades. **The standing lesson is about what a group NAME does to the settings that land in it: "Fair Value Gaps" was a group named for an OBJECT, so it collected anything that mentioned a gap — six trade-deciding knobs — while reading to every human as decoration. Name a group for the JOB it does and a new toggle has exactly one honest home.** Earlier the same day: 🟢 **`mpc_strategy.pine`'s PANEL IS REBUILT END TO END: 156 INPUTS → 66, IN TEN NUMBERED SECTIONS, AND EVERY SURVIVOR KEEPS ITS TYPE, DEFAULT AND TITLE.** The full panel contract below, applied to the template file. **90 inputs became constants at exactly the value the file shipped, 5 were DELETED as hazards, the diagnostic log went entirely (102 lines), and the 66 that remain live in ONE consolidated block right under the `strategy()` call.** ✅ **PROVEN COSMETIC RATHER THAN ARGUED, three times over**: the input dump was taken before the pass and after, and the only line in the "after" set that is new or changed is **`drawFibs`, the one input deliberately added** — everything else diffs one-directional. ✅ **The export mirror is a title-only diff, 46 `plot(` columns, and its `px_*`/`cfg_*` set is IDENTICAL to HEAD.** ✅ **The regenerator now reports `parent-only 0` for this file, which is the diagnostic log's deletion showing up as a structural fact rather than a claim** — the export is a pure append at last. 🔴 **FIVE INPUTS WERE DELETED BECAUSE THEY COULD SILENTLY STOP THE BOT TRADING, AND THAT IS THE FINDING OF THE WHOLE PASS.** `Show External Fib (REQUIRED — SL/TP/entry levels)`, `Show FVG (REQUIRED — feeds entries)`, `Show All Liquidity Levels (REQUIRED — arms sweeps)`, the EQ-levels toggle, and `Hide Everything Except Market Structure` — **each reads as a drawing checkbox and each gates a CALCULATION.** `showFibo` guards the block that computes `fiboP1..fiboP7`, i.e. every entry, stop and target price in the file; `showFVG` guards gap creation, and the gap boxes ARE the storage, so the entry has nothing to rest on without them; `eqShow` guards the levels `eqExemptFvg` reads. **Ticking "Hide Everything Except Market Structure" stopped the bot trading, with nothing anywhere reporting it.** All five are permanent calculation now and are not inputs at all; the DRAWING they used to hide is switched by the new `drawFibs` (default OFF) and the existing `showSessions`. ⚠ **`showDivInput` LOOKS like a sixth and was deliberately KEPT** — it is packed into `cfg_bits` bit 1024, so deleting it would break `compare_strategy.py`. It sits in `4 · What arms it`. ⚠ **THE FVG SETTINGS ARE IN `5 · Entry`, NOT IN AN FVG GROUP, AND THAT IS THE CONTRACT'S WHOLE POINT** — both min-gap floors, the close test, the max-active cap, keep-until-broken and `eqExemptFvg` all change WHICH GAPS EXIST and therefore which entries fire. Grouping by name would have demoted six trade-deciding knobs to the bottom beside the fib colours. ⚠ **Two stale comments were rewritten rather than left standing**: the time-stop note said its inputs must never be moved up to the exec panel because they were the file's last string and float — correct for its day, and now the exact `eqExemptFvg` failure this file already records, a specific warning sitting directly above the line that invalidated it. ⚠ **16 orphaned `GRP_*` / `*_SESSION_GROUP` constants were deleted with it**, which RELIEVES the CE10117 token pressure this file has hit twice. ⚠ **NOT COMPILED, and `compare_strategy.py` has NOT been re-run.** ⚠ **THIS PASTE NEEDS ONE "Reset settings to defaults"** — that is the known, accepted price of the reorder, and it is only safe because the file DEFAULTS are what Aaron trades. ⚠ **`mpc_b_leg_strategy.pine`, `mpc_bos_strategy.pine`, `mpc_d_strategy.pine` and `mpc_h4_sweep_strategy.pine` are NOT yet regrouped** — the METHOD is proven on the hardest file, so each remaining one is a repeat of the same three verified steps. 🔴 **Corrected 2026-08-12: this sentence used to name `harden.py` and `regroup.py` as tooling that was "written and proven". NEITHER SCRIPT HAS EVER EXISTED** — not on disk, not in any commit, not on any branch (`git log --all` finds nothing). The regroup was done by hand. **So the four remaining files are hand work, not a script run**, and anyone who budgeted them off this sentence budgeted them wrong. The transferable part is rule 7 in a doc rather than in code: *naming* a script is a claim that it exists, and a plausible filename is the easiest thing in the world to write and the last thing anyone checks. Earlier the same day: 🟢 **A+'s PANEL IS HALF THE SIZE: 156 INPUTS → 71, AND NOT ONE SURVIVOR MOVED.** The collapse half of the panel contract below. 85 fib, session, liquidity, colour and RSI sub-settings stopped being inputs and became constants **at exactly the value the file already shipped** — Aaron, 2026-08-12: *"I don't even need to see the time frame or the colors of the sessions… I'll never configure them."* ✅ **PROVEN COSMETIC RATHER THAN ARGUED, which is the whole point of snapshotting the defaults first**: `PINE_INPUT_DEFAULTS.md` was dumped before the pass and re-dumped after, and the diff is **one-directional — 85 lines removed, ZERO lines added or changed.** Every surviving input keeps its type, its default and its title to the character. ⚠ **The tool READS each default out of its own `input.*` call rather than being handed a list**, and REFUSES a var it cannot parse instead of guessing — a skipped input stays visibly on the panel, where a silently wrong constant would not be visible at all. ⚠ **`active = <hardcoded var>` was checked and there are none**, so no surviving input greys off a constant. ✅ **The export mirror was REBUILT off the collapsed parent and re-verified: body diff is exactly line 32's title, 46 `plot(` columns, and the `px_*`/`cfg_*` set diffs IDENTICAL to HEAD** — nothing the parity gate reads moved. All five twins still round-trip byte-identical. ⚠ **THE PANEL IS COLLAPSED AND NOT YET REGROUPED** — the 71 survivors still sit in their old groups, so `Strategy Execution` still holds 44 and the six FVG entry rules are still filed under a drawing-sounding name. The numbered sections, and the three `REQUIRED`-toggle SPLITS that must happen with them, are the next pass. ⚠ **NOT COMPILED, and the parity gate has NOT been re-run.** Earlier the same day: 🟢 **THE B-LEG FORK DRAWS BLOCKED TRADES NOW, AND ITS CODE SET IS ITS OWN.** Aaron is standardising every strategy Pine against `mpc_strategy.pine` so that "nothing seems different other than the logic of the strategy" — same blocked marker, same missed callout, same position box, same entry triangles, on all of them. This is step one: `mpc_b_leg_strategy.pine` had every annotation except the pink `TRADE BLOCKED` tag. 🔴 **IT COULD NOT BE A PORT, AND THIS FILE ALREADY SAID SO ON 2026-07-26** — *"their codes answer why an A+ setup was refused; in a fork where A+ never trades those tags read as the opposite of what they mean"*. A+'s six codes name the arm source, the divergence veto and the two HTF filters, and **not one of them can refuse a B leg** — the arm condition here gates on `execBLeg`, direction, the A+ priority stand-down, the final hour and the band's own geometry, which is what the comment above it already states in words. The new set is those five, in PRECEDENCE order so a tag can never blame a downstream gate: **1 B-leg entries off · 2 direction off · 3 A+ has priority · 4 final hour · 5 the band prices no ladder.** ⚠ **What is shared is the DISPLAY, and that is the whole point of the standardisation** — same pink, same text, same tooltip shape, same one-tag-per-setup-per-reason dedupe keyed on the band's own bar. The chart reads identically across the two files; only the sentences differ, because the refusals differ. **Do not "reconcile" the two code sets.** 🔴 **CODE 5 IS THE ONE WORTH HAVING AND IT WAS COMPLETELY INVISIBLE.** The band's ladder test — stop beyond the entry, TP1 past it, TP2 no nearer than TP1 — lived inline inside `if bLegLongArm` and its `else` branch just cancelled the order, so a band that prices nothing produced no order, no trade-list row and nothing on the chart. **It is also the only one of the five that is about the SETUP rather than a switch you already know you flipped**, i.e. the only refusal a reader could not have worked out from their own inputs. ✅ **The test is HOISTED and the ENTRY BLOCK NOW READS IT** (`bLegL_ok` / `bLegS_ok`) rather than the tag re-deriving it — one expression, two readers, so the tag and the order cannot disagree. ⚠ **Proven behaviour-identical rather than asserted**: `bLegL_slD` / `bLegL_t1` are the original `slDist` / `lTP1` expressions character for character, and the added `not na(...)` guards are trivially true inside a block already gated on `bLegLongArm`, which requires all three prices non-`na`. ⚠ **THE NEW `input.bool` SHIFTS EXACTLY ONE SAVED SLOT AND THAT IS THE MINIMUM AVAILABLE.** TradingView keys saved values off declaration order within each type; Pine needs the declaration before the read and the read has to sit at the marker, so `execDiagLog` — the only later bool, and the one the diagnostic-log deletion is about to remove anyway — moves one place. **Check "Log every trade to Pine Logs" once after pasting.** Nothing else shifts. ✅ **The export mirror was REBUILT off the updated parent and re-verified three ways: body diff is exactly line 40's title, 43 `plot(` columns, and the `px_*`/`cfg_*` column set diffs IDENTICAL to HEAD** — so nothing the parity gate reads moved. ⚠ **The regenerator's cut moved 4817 → 4913, which is the +96 lines, and all five twins still round-trip byte-identical.** ⚠ **NOT COMPILED, and `compare_bleg.py` has NOT been re-run** — the tag is cosmetic and the hoist is proven equivalent by inspection, but neither is a paste and neither is a real export. **The standing lesson is one this file wrote down two weeks early and is worth re-reading: a shared annotation is shared at the DISPLAY, never at the reasons. Two strategies can and should look identical to a reader while refusing trades for entirely different causes — and the moment you copy one file's reason codes into another, the chart starts confidently naming gates that file does not have.** Earlier: 2026-08-11 — 🟢 **THE M15 PLAYBOOK CAN BE SCORED NOW: `mpc_m15_playbook_strategy.pine` IS THE FIVE-STEP MODEL FROM THE VIDEO NOTE, WITH AN EXECUTION LAYER.** Aaron: *"I don't know what my brother was thinking, but this MPC m15 playbook pine is not a strategy… fix it to be a strategy. I wanna see if this actually really wins."* `mpc_m15_playbook.pine` is an `indicator()` — 4,886 lines of structure, sessions, gaps, order blocks and a confirmation table, placing no orders — so the Strategy Tester could not score it and the model had never been measured. The new file is **NOT a conversion of it**: it is a lean 1,015-line `strategy()` carrying only what the five rules need, and the playbook is left intact so the pair can sit on one chart — the indicator draws, the strategy trades. The rules are from `education/learned/2026-08-11-smc-strategy-too-simple-to-ignore-1150-trades.md`: 15m structure direction → the current session sweeps the PREVIOUS session's high/low (London takes Asia's, NY takes London's) → a 1m change of character agreeing with the 15m → a limit into the nearest UNTOUCHED 5m fair value gap → TP1 previous day's extreme, TP2 previous week's. ✅ **The 15m and 1m structure engines are LIFTED BYTE-FOR-BYTE from the playbook's own drawing-free `MTFStruct` block**, which is the same state machine as `engines/market_structure/` — a second swing map is exactly how a strategy starts trading a different market from the one being read. 🔴 **THE CONFIRMATION HAD TO BE A COUNTER, NOT A FLAG, AND THAT IS THE TRANSFERABLE HALF: a change of character is an EDGE, and an edge read back through `request.security` arrives as a LEVEL that stays true.** The engine returns how many shifts it has seen and the strategy diffs it against its own previous bar; nothing else can tell *it just shifted* from *it shifted at some point*. ⚠ **The pool is FROZEN at the session open, never read live** — Asia/London and London/NY overlap, so "the previous session's high" is ambiguous while both run, and a level that moves under the setup watching it is not a level. NY wins the overlap. 🔴 **The proximal edge cannot be written without the direction** — it is the BOTTOM of a zone above price and the TOP of one below — and the first draft had one rule for both, which rests every long at the far edge of its own gap. ⚠ **A limit must rest on the far side of the market or it is a market order wearing a limit's name**: if the zone is no longer beyond price when the sequence completes, the setup is REFUSED (block code 6) rather than sent. ⚠ **Targets are ordered by DISTANCE, not by name** — whether the previous day's low is nearer than the previous week's is a fact about the week — and a target on the wrong side of the entry, or nearer than `execMinRr`, is replaced by `execTpFallbackR` or refuses the setup. ⚠ **ONLY THE FAIR-VALUE-GAP HALF OF STEP 4 IS MODELLED.** The video says "order block OR fair value gap", so this takes strictly FEWER setups than he does, and a low trade count is partly that. Adding blocks means a second OB implementation inside `request.security`, which this repo forbids. ⚠ **Three of this repo's recorded traps were guarded on the way in rather than rediscovered**: the fill bar may not stage its own stop, a `qty_percent` rung is only issued while unfilled, and a `0` rung is skipped. 🔴 **NOT COMPILED, NOT RUN, NOT MEASURED, NO PYTHON PORT, NO PARITY HARNESS — and there is no control**, so read nothing off it until it is scored against random entries matched on direction and stop distance; gold tripled across any window this will run on, so a long-side result is free. ⚠ **TradingView loads limited 1-minute history, so with the confirmation ON the far end of a long backtest may take no trades at all** — read the trade list's FIRST date against the chart's, and never read the tester's window header as what arrived. ⚠ **The lab cannot sweep this as built**: it reads THREE bar streams and `run_sweep` replays one frame, `run_dual` two. Spec, decisions and open work: `docs/MPC_M15_PLAYBOOK_SPEC.md`. **The standing lesson is about what the word "strategy" was doing in a filename: the file said playbook, the header said `indicator(`, and the thing nobody could do with it was the only thing it existed for — the same shape `mpc_d_strategy.pine` hit on 2026-08-06, where the NAME said strategy and the DECLARATION did not.** Earlier: 2026-08-10 (latest) — 🟢 **EVERY EXECUTION TOOLTIP IN THE THREE STRATEGY PINE FILES IS SHORT AND PLAIN NOW.** Aaron on the lab's strategy detail page: *"the amount of text in there is so overwhelming… it gives examples of past runs and all kind of craziness."* A `desc` in a `<pkg>.meta.json` is byte-identical to that input's TOOLTIP, so the page could not be fixed on its own — **99 tooltips were rewritten across all six files** (both A+, both B-LEG, both BOS) to *what it does, what each choice means, and the one fact that changes the decision*, with the measurement dumps, trade counts, R figures and dates removed. 🔴 **22 of them were STALE COPIES in the B-LEG pair** — that fork inherits the A+ arm/entry/exit inputs and its meta deliberately does not list them, so rewriting `mpc_strategy.pine` alone would have left ONE setting reading two different ways on two of Aaron's charts. ⚠ **Only tooltip STRINGS moved, and it is proven rather than asserted:** every `input.*` call in all six files was parsed at HEAD and at the working tree and compared with the tooltip masked out — **name, type, title, default and declaration order identical, 114 / 113 / 122 / 121 / 126 / 126 inputs** — so **no saved chart settings reset** and nothing behavioural moved. ⚠ **NOT COMPILED.** A tooltip is a string literal, so a mangled one is a compile error and never a silent behaviour change, but the paste is still unverified on TradingView. ⚠ **Parity is structurally unaffected** (no parity column carries a tooltip) and both export mirrors took the identical edits, so they stay mirrors. Earlier: 2026-08-10 (latest) — 🟢 **PARITY GREEN ON `execNoGapArm`, AND THE RUN WAS NOT VACUOUS — CHECKED RATHER THAN ASSUMED.** Aaron took TWO exports off `mpc_strategy_export.pine`, both with **`execReqFVG` OFF** (`cfg_bits` 544359, bit 16 clear) so the fallback branch is actually entered, one at `cfg_nogap_arm` **1** and one at **0**. `compare_strategy.py` is **exit 0 on both, at warmups 100 / 500 / 1000 / 2000 / 3000**, over **20,230 M15 bars (2025-09-30 → 2026-08-10)**. 🔴 **The non-vacuity check is the half that matters, because this is precisely where the minimum-stop guard went wrong on 2026-08-04.** The two exports were diffed against EACH OTHER before either green was believed: they differ on **4,237 bars of `px_edge`, 675 of `px_dec_bits`, 124 of `px_stop`, 45 of `px_block`, and 10 actual `px_entry_price` fills**, with `px_closed_r` differing on 23. **So the Pine really is steering a different run off that dropdown, and the Python reproduced BOTH streams bar for bar** — which is the thing a single green could never have said. ✅ **And the direction agrees with the 6.5-year measurement on an independent engine and a mostly-forward window: gated 31 trades / +12.16R against Any's 39 / +6.77R** — 8 fewer trades, more R, on TradingView's own tester rather than ours. ⚠ **It is 31 trades in ten months, so read it as a CONSISTENCY check on the rule, never as a second measurement of the edge.** ⚠ **`warn_unexercised()` correctly stayed silent on both** (gap requirement off, column present), which is the other direction of that guard and is what stops it becoming noise. Earlier the same day: 🟢 **`execNoGapArm` LANDS IN BOTH A+ PINE FILES, AND WHERE IT IS DECLARED IS MOST OF THE WORK.** It gates the no-FVG FALLBACK entry — with `execReqFVG` off, only rest a limit at the 0.618 if the SOS carried BOTH a liquidity sweep and an RSI divergence — after the Python side measured the split at 155,531 M15 bars: the 78 setups with both sources made **+35.47R** and the 95 with a sweep alone made **+0.71R**, an average of +0.007R. Default **"Any"** = the original fallback exactly, so no historical result moves. 🔴 **THE FALLBACK BLOCK HAD TO MOVE, AND THE REASON IS PURE PINE SEQUENCING: `sosL_swp` / `sosL_div` are not computed until ~30 lines AFTER the entry ladder that needed them.** The five-line `if not execReqFVG and fibsReady` block is now declared just after the retro-link snapshot, with a marker left at its old site. **Checked rather than assumed: NOTHING between the two points reads `longEdge` / `shortEdge`** — the next read is `longArmed`, 140 lines further on — so at the default the move is behaviour-neutral. ⚠ **The INPUT is declared beside `execLabelOff` in the DRAWING sub-block, NOT beside `execReqFVG` where it belongs semantically, and it must not be tidied.** TradingView keys a chart's saved values off DECLARATION ORDER within each type; this file has **37 `input.string`s** and `execReqFVG`'s neighbourhood is the 32nd, so declaring it there would shift five later strings. Declared where it is, it is the LAST string before the code that reads it and shifts **exactly one** — `execTimeStopMode`. ⚠ **So after pasting this build, check the Time stop input still reads "Before TP1 only" / 36 hours.** That is the whole cost, it is stated rather than discovered, and it is the minimum available: any placement usable at the ladder shifts at least one input, and a `bool` would have shifted two. ✅ **The export mirror carries `cfg_nogap_arm` (Any?0 : Sweep + RSI div?1)** as its own column rather than a `cfg_bits` bit — it is a dropdown, and packing a third state into a bit is how a decoder starts guessing — and both files remain byte-identical outside line 32 and the export's own plot block. ✅ **`compare_strategy.py` decodes it, and an ABSENT column reads "Any" as a FACT ABOUT THE PINE** (before the gate, the fallback took every no-gap setup) rather than as the Python default, which it also happens to equal today; a test pins that it must not fall back on the base config. 🔴 **AND THE HARNESS NOW SAYS OUT LOUD WHEN IT COULD NOT TEST THIS.** `warn_unexercised()` prints a warning whenever the export ran `execReqFVG` **ON**, because then neither side ever enters the fallback branch and a green run is evidence about nothing — **this is the minimum-stop guard's 2026-08-04 trap pre-empted**, where a setting shipped live on an exit-0 run whose export had raised its block code zero times in 21,897 bars. **To actually test this lever the export must be taken with `execReqFVG` OFF — once at `cfg_nogap_arm` 0 and once at 1.** ✅ 6 new harness tests (333 strategy green), including a round trip driven at BOTH arm modes; **measured non-vacuity: the two modes price a different entry edge on 59 of 960 synth bars** — and the honest other half is recorded with it, that both still close the same 6 trades on that frame, so the trade-level evidence is the real replay and not the synth. ✅ **COMPILED AND PARITY-VALIDATED the same day — see the top of this entry.** The Python side is committed and green either way; nothing here is trustworthy until `compare_strategy.py` exits 0 on a real CSV taken with the gap requirement off. **The standing lesson is one this file keeps re-learning from a new direction: a Pine input's DECLARATION POSITION is part of its contract with every chart it is already saved on, and the correct place to declare it is almost never the place it reads best.** Earlier: 2026-08-09 (latest) — 🟢 **THE ORDER-BLOCK OPTION IS OUT OF `mpc_strategy.pine` AGAIN, AND THE INTERNAL FIB CAME BACK WITH IT.** The three commits that put it there (`cc0ecec` the engine + `execPoiSource`, `de21388` the internal-fib cut that paid for it, `7f54d46` the "FVG first" ranking) are REVERTED on both A+ Pine files, which are restored to `2580f5b`. **The question they existed to answer is answered and the answer is no**: order blocks on A+ measure 267 trades / +75.93R against the gap rule's 159 / +142.18R, "FVG first" 276 / +102.90R, and **82% of that loss is 29 baseline trades DISPLACED rather than the trades added** — a bot with ONE position slot bets against its own tail every time it takes a marginal setup. **So the setup becomes its own bot (`mpc_ob_fade`) with its own slot, not a mode of this one**, and the loser's code does not sit in the live A+ file. ✅ **The removal is a RESTORE from git, never a hand edit**, which is what makes it safe rather than merely tidy: `execPoiSource` was declared as the LAST `input.string` and `execTimeStopMode` had been MOVED up to accommodate it, so putting the file back puts the mode back in its original slot — and since none of the three commits was ever compiled or pasted, **the restored file is byte-identical to what is on Aaron's charts today. Nothing to re-paste, no saved input resets, no compile risk.** ✅ **The token debt is repaid**: the OB engine pushed this file to CE10117 (102,086 against a 100,256 cap) and the ~230-line internal FIB was cut to make room; both are undone together, so the file is back under the cap with the fib drawing restored. ⚠ **The PYTHON side deliberately KEEPS `exec_poi_source`** — `strategies/python/mpc_sos_fade/` is the shared base `mpc_bleg`, `mpc_bos` and the new fork all build on, and `signals.pois_for` is the one place the zone rules live; a second copy for the fork is the thing this repo forbids. **The consequence is stated rather than left implicit: only `"FVG"` now has a Pine input behind it, so `compare_strategy.py` can never check another mode and any non-FVG result is a LAB finding.** The lab row carries a `(lab only)` suffix for exactly that reason (the `exec_conf_sz` precedent), and the harness's `cfg_poi_source` decode stays — an absent column reads `"FVG"`, which is the right answer for every export ever taken and every export to come. **The standing lesson is about where a lever belongs rather than whether it works: as a TOGGLE this made one bot take more setups and they competed with its own winners for one slot; as its own BOT the same rule is additive, and nothing about the rule changed between those two readings.** Earlier the same day: 🟢 **THE ZONE DROPDOWN GAINED A PRECEDENCE MODE: "FVG first".** Aaron, off a curve he did not like: *"could I add, like, a precedence order? If there is fair value gaps, take those preferentially over order blocks. Only if there's no fair value gaps, then take the order blocks. If a fair value gap and an order block overlap, that's the most preferred fair value gap to take."* `execPoiSource` is now ∈ {**"FVG"**, "Order block", "Either", "FVG first"}. 🔴 **REVERTED — this paragraph describes a design that no longer exists in any Pine file, and it is kept only because the same file elsewhere records the revert (`execPoiSource`, the ported OB engine, `f_gapOnOb`, the POI seam and the `cfg_poi_source` plot were all RESTORED to `2580f5b`). Read what follows as history, not as behaviour.** ⚠ **Verified 2026-08-12: `execPoiSource` appears in ZERO `.pine` files, and `poiRank` appears nowhere in the repo except this doc.** ⚠ **And the revert was NOT symmetric — `execPoiSource` is still a live field in `strategies/python/mpc_sos_fade/config.py`, so the Python side carries an input the Pine does not have. A field the export cannot carry is a field the parity gate can never check; that asymmetry is unresolved and is worth a look before the next A+ measurement.** The original entry read: **The mode is a RANKING, not a filter** — the POI seam carries a `poiRank` alongside the four fields it already had, and the entry-edge loop takes the best rank that has a QUALIFYING zone, letting nearest-first decide only WITHIN a rank: **2** a gap an order block sits on · **1** a plain gap · **0** a block. ⚠ **Every other mode pushes rank 0 for everything**, so all candidates tie and the loop collapses to the original max/min — which is what keeps the three measured modes byte-identical rather than merely intended to be, and it is **PROVEN BY REPLAY**: all three reproduce their HEAD trade lists to a matching SHA over the same frame. ⚠ **IT IS NOT "FVG" WITH A SAFETY NET, and the trade count will say so** — a leg whose only zone is a block still trades, so this takes strictly MORE setups than "FVG" does, and that fallback tier is exactly the population that measured badly (order blocks alone: 267 trades / +75.93R against FVG's 159 / +142.18R; requiring a block was worse than requiring nothing). **Read the mode as "gaps preferred, blocks as fallback", never as "gaps, confirmed by blocks".** ⚠ **The confirming block must point the SAME WAY as the gap, and that is a judgement Aaron's words did not settle**: a bearish supply block on a bullish gap is the opposite of confirmation, and ranking that gap TOP would promote the worst candidate on the leg. One predicate here and one in `signals.pois_for`, **and they must be flipped together or the parity gate goes red**. ⚠ **`f_gapOnOb` overlap is INCLUSIVE at the edges**, matching every other band test in the file (`_gB <= fiboP2 and _gT >= fiboP6`); a `>` here against a `>=` in Python is a divergence no unit test on either side would show, so it is pinned by a mutation-proven test. ✅ **The new option was APPENDED to the `options` list and the export code APPENDED as 3** — `cfg_poi_source = FVG?0 : Order block?1 : Either?2 : FVG first?3`. **Codes are a WIRE FORMAT**: an export already on disk carries the number, so renumbering one is silent — the file still reads and now claims a mode it never ran. Adding an option to an `input.string` shifts no saved-value slot, unlike adding an input. ⚠ **NOT COMPILED AND NOT PARITY-VALIDATED.** `cfg_poi_source` is plotted and `compare_strategy.py` decodes 3, but no export has ever been taken on a non-FVG run, so **a green gate at the default would prove nothing about this lever** — the "green on a branch neither side entered" trap. ⚠ **And this file was over the compile-token cap yesterday** (CE10117, 102,086 against 100,256), fixed by cutting the internal fib; this pass adds ~30 lines back. If it refuses again, the next cuts in order are the six `f_blkWhy` strings, then the Sessions drawing block. **The standing lesson is about what a mode NAME promises: "FVG first" reads like a filter with gaps preferred, and it is a RANKING over a union — so it can only ever trade MORE than the mode it is named after, which is the opposite of what a reader expects from the word "first".** Earlier the same day: 🟢 **THE A+ STRATEGY CAN TRADE ORDER BLOCKS INSTEAD OF FAIR VALUE GAPS, ON THE CHART, WITH ONE DROPDOWN — AND THE HARD PART WAS NOT THE ENGINE.** Aaron: *"I asked you to build this option into mpc_strategy.pine where I could toggle between fair value gaps or order blocks. Both entry models the exact same way... Right now what you're doing is all in theory, and I need to see it and interact myself."* `execPoiSource` ∈ {**"FVG"**, "Order block", "Either"} is in `mpc_strategy.pine` and its export mirror, with the 2026-07-31 turn-anchored OB engine ported in from `mpc_assistant.pine` (the strategy files had dropped order blocks entirely on 2026-07-24/25, so there was nothing to switch on). ✅ **THE PORT'S FAITHFULNESS WAS PROVEN MECHANICALLY, NOT BY READING IT** — a script stripped comments and diffed every executable line of the ported block against its source: **111 vs 114 lines, and the only differences are two whitespace changes, one added constructor argument, and the `extendOBs` call that lives elsewhere in the parent.** `f_obAdd`, the push source and the turn source are line-for-line identical. That matters because `engines/order_blocks/` is the Pine-parity-validated port of the SAME source and the Python bot reads it, so a transcription slip here is how the chart and the bot start disagreeing about one candle. 🔴 **THE REAL DEFECT-IN-WAITING WAS THE INPUT SLOT, AND IT IS THE `execTimeStop` NOTE BITING FROM THE OTHER END.** TradingView keys saved input values off DECLARATION ORDER within each type, and `execTimeStopMode` had been parked at ~line 5020 for exactly that reason — it was the LAST `input.string` in the file. The new input has to be readable ~2,500 lines earlier, so appending it was impossible and inserting it would have silently reset the time stop on every chart running this script. ✅ **Fixed by MOVING `execTimeStopMode` up beside the new input and declaring the new one AFTER it** — the mode keeps the string slot it has always held, the new input becomes the new last one, and **pasting this build resets NOTHING.** ⚠ **`execTimeStopHrs` deliberately stays at the old site** because it is a FLOAT and `execBeBandR` is a later float; moving the pair together would have shifted that one instead. **The pair is split across the file on purpose and must not be tidied.** ✅ **One SEAM, not two code paths**: both consumers of a zone — the confluence flag and the entry-edge loop — now read one set of `poi*` arrays, mirroring `signals.pois_for()` in the Python. That is what makes *an order block obeys the same rules as a gap* true by construction rather than by two blocks of code agreeing. ⚠ **The pre-date gate reads the block's `born` field (written `bornBar` here until 2026-08-12 — no such identifier exists; the real one is `born`, in both `mpc_assistant.pine` and `engines/order_blocks/types.py`) — the bar it was ADDED on, never its anchor candle**, which can be ~10 bars older. Gating on the anchor would let a block price an entry before it was knowable: look-ahead of the quiet kind that raises nothing and backtests beautifully. It matches `created_index` in the engine, whose `origin_index` is deliberately the field NOT used. ⚠ **Blocks are drawn ONLY while the entry can trade them**, so what is on the chart is the set the entry reads — no second switch to drift out of sync. ⚠ **NOT COMPILED AND NOT PARITY-VALIDATED.** The export plots `cfg_poi_source` and `compare_strategy.py` decodes it (absent ⇒ FVG, which is a FACT here because the input shipped defaulting to FVG on day one — the `cfg_eq_exempt` hole pre-empted rather than repeated), but no export has been taken, **and a green run at the FVG default would prove nothing about this lever** — the *green on a branch neither side entered* trap this file already records twice. 🔴 **IT DID NOT COMPILE, AND THE FIX WAS NOT THE ONE THIS ENTRY PREDICTED.** The first paste returned **CE10117: 102,086 tokens against a cap of 100,256** — so the warning was right that it would break and wrong about what to do: it said *"the OB block is the thing to shrink"*, and shrinking the OB block would have meant giving back the feature Aaron asked for. ✅ **The INTERNAL FIB was cut instead — ~230 lines of real code, 5,504 → 5,274 lines** — on the same test every earlier cut in this file was made on (Kill Zones, VWAP, Order Blocks, SVP, the Cycle Fib drawing): **purely cosmetic, defaulted OFF, and read by NOTHING in the execution layer, verified by grep rather than assumed.** ⚠ **THE INTERNAL STRUCTURE ENGINE STAYS AND THAT DISTINCTION IS THE WHOLE OF IT** — `i_confirmed_low_price` / `i_confirmed_high_price` are written by the internal SWING detection and adopted as the External Fib's anchors whenever they are more extreme, so they set `fiboP1..fiboP10`, i.e. every entry, stop and target in the file. Cutting the fib and cutting the structure look like the same edit from the outside and one of them would have moved every trade. ⚠ **Its 18 GRP_IFIB inputs are LEFT DECLARED and GREYED (`active = false`), not deleted** — that group holds 8 colours and 8 strings, so removing them would shift every later input of those types and silently reset them, `execPoiSource` and the time stop included. Same call, same reason, as the Cycle Fib's two parked inputs. The master toggle is retitled so ticking it cannot read as a bug (a TITLE is safe; TradingView keys on declaration ORDER, not text). ✅ **The export mirror was REGENERATED off the trimmed parent and re-verified: exactly the line-32 title differs, 46 `plot(` columns, and the `cfg_*` set diffs identical to HEAD** — so nothing the parity gate reads moved. ⚠ **STILL NOT COMPILED at the time of writing** — the cut is sized by judgement, not measured, because only TradingView can count these tokens. **The standing lesson is about which feature pays for a new one: the file was over budget, and the cheapest thing to delete was not the thing just added — it was the oldest cosmetic block nobody had switched on.** ⚠ **The measured answer is that order blocks are much worse** — 267 trades / +75.93R / maxDD 11.11R against FVG's 159 / +142.18R / 5.61R, and worse than requiring NOTHING (315 / +149.55R); see `strategies/python/mpc_sos_fade/CLAUDE.md`. **The standing lesson is about where the risk in a port actually sits: the engine was 250 lines of someone else's proven logic and transcribing it was mechanical, while the one change that could have quietly damaged every chart Aaron runs was deciding which LINE to declare a dropdown on.** Earlier: 2026-08-08 — 🟢 **A THIRD-PARTY CANDLESTICK INDICATOR ARRIVED, GOT AN ENGINE AND AN EXPORT HARNESS, AND THE GATE IS GREEN: `compare_candles.py` exit 0 on a 20,138-bar `VANTAGE_XAUUSD, 15m` export at warmups 0 / 100 / 500 / 2000, 14 of 15 patterns fired, 302,070 flag comparisons, ZERO rule differences.** ⚠ **Three BOUNDARY TIES survive and are reported on every run rather than tolerated away** — `doji`, `invHammer` and `shootingStar` each compare quantities that are **exactly equal in decimal** on those bars (0.26 vs 0.26 · 3.96 vs 3.96 · 5.43 vs 5.43, confirmed with `Decimal`), neither side representable in binary float, so both implementations are right and land opposite. **A tolerance was refused on principle: a 0/1 flag has no "close enough" and would have swallowed real bugs**, so the harness CLASSIFIES each mismatch by re-running it with every price in the bar's window nudged ±1e-6 — a decision a nudge can flip was on the line, a rule difference is not. ✅ **Proven non-vacuous by injecting two fabricated flips, which came back REAL with exit 1.** Full detail below and in `engines/candlesticks/CLAUDE.md`. The build history that got there: 🟢 **A THIRD-PARTY CANDLESTICK INDICATOR ARRIVED AND IT NOW HAS AN ENGINE, AN EXPORT TWIN AND A GATE.** Aaron added `indicators/candle_sticks.pine` (© repo32, v6 — fifteen classic patterns, flat file, no state machine) and asked for a generic engine to use as confluence in strategies. `engines/candlesticks/` is built (42 hand-traced tests, all fifteen patterns firing at least once over 186,366 real M15 bars) and `indicators/candle_sticks_export.pine` is its parity twin — **the parent VERBATIM apart from line 11, verified mechanically** (`head -84 candle_sticks_export.pine | diff - candle_sticks.pine` prints exactly that one pair), plus 18 appended `plot()` columns. 🔴 **`compare_candles.py` HAS NEVER RUN — no TradingView CSV exists — so nothing here is parity-validated and the engine is deliberately uncommitted**, per this repo's standing rule that unit tests pin logic and do not prove parity. 🔴 **THAT EXPORT TOOK THREE ATTEMPTS. TRADINGVIEW REFUSED THE FIRST TWO WITH `RE10140`, AN ERROR THAT IS NOT IN ITS PUBLISHED LIST AT ALL, AND THE FIX WAS TO STOP COPYING THE DRAWING.** **Attempt 1** was the parent verbatim plus two deviations of mine on line 11 (`overlay = false`, `max_bars_back = 500`). The code could not be looked up, but Aaron supplied the decisive fact himself: *"usually I would see the little spinner compiling but not this time."* **A clean compile with no calculation spinner means it died at INITIALIZATION, before a bar was processed** — which points at what a script sets up, not at any of the fifteen rules. Both extras were deleted, neither having survived being asked what it was for: `max_bars_back` guarded a hazard that does not exist (the `open[trend]` offset is on the **BUILT-IN `open` series, which carries ~10,000 bars natively**) while allocating that buffer for EVERY series in the script, and `overlay = false` was pure cosmetics on a file nobody reads. 🔴 **ATTEMPT 2 — the parent verbatim, a title-only diff — STILL FAILED, and that is the finding.** Removing my deviations was necessary and not sufficient, so the cause was in the part I had faithfully copied. ✅ **MEASURED rather than reasoned, across the sibling harnesses: `plotshape` 15 / `alertcondition` 15 in this file against 0 / 0 in `fvg_export.pine`, `ob_export.pine`, `sessions_export.pine` and `rsi_div_export.pine`.** It was **the only export in this repo that DREW**, on a chart already carrying fifteen scripts — and `fvg_export.pine` runs **40** plot columns on that same chart without complaint, so the column COUNT was never it. **Attempt 3 strips the drawing** and is the rules only, which is what every sibling has always been: *"with ALL drawing removed — those are visuals"*, in `fvg_export.pine`'s own header. ⚠ **THE VERIFICATION CONTRACT HAD TO CHANGE WITH IT, AND THE OLD ONE WOULD NOW PASS VACUOUSLY** — the file is no longer a byte copy, so `diff` against the parent proves nothing; what is checked instead is that the SIXTEEN LOGIC LINES are byte-identical, in one `grep | diff` recorded in both this file's Key-paths entry and the export's own header. **A harness whose rules have drifted reports a correct engine as red — `fvg_export.pine` did exactly that on 2026-08-03.** ⚠ **The `trend` finding is DOWNGRADED and that correction matters more than the original claim**: it is a missing `maxval` worth mentioning before somebody types a big number, **not** the `execVwapSlopeBars` emergency the first write-up called it — and reading it as one is precisely what put the useless `max_bars_back` pin in attempt 1. **The standing lesson is about what byte-identity is FOR: it is a way of PROVING a harness matches its source, not the harness's job — and here chasing it dragged fifteen drawing calls with no reader into the one file whose entire purpose is to emit columns. When every sibling follows a convention and you are about to be the exception, the burden is on the exception.** ⚠ **The gate's exit code is not the whole answer and the tool says so out loud**: it prints a per-pattern hit count on BOTH sides and names every pattern that fired zero times, because "agreed on 20,000 bars" and "neither side ever entered this branch" are indistinguishable from an exit code — the min-stop guard's green-on-an-unentered-branch trap, designed out rather than rediscovered. ⚠ **Two patterns are measured at 19 and 25 occurrences in EIGHT YEARS** (`bullBelt`, `hangingMan`), so a real export may well go green having exercised neither; that is a fact to read off the histogram, not a reason to distrust the run. 🔴 **One transcription near-miss, caught by a test rather than by reading: `bullEng` reads `close[1] >= open`, not `<=`.** The intuitive direction still passes on plenty of real bars, so the rule would have looked like it worked; the engine had it right and the FIXTURE was built from the misreading, which is the honest version of the same mistake. Both directions are now pinned by their own test. **The standing lesson is about which half of a port you check: the code was faithful and the test fixture was not, so the failure pointed at the innocent half — and it was only findable because each fixture was hand-derived from the source expression rather than recorded from the engine's own output.** Full detail: `engines/candlesticks/CLAUDE.md`. Earlier: 2026-08-07 — 🔴 **THE FIRST REAL BOS EXPORT ARRIVED AND THE GATE REFUSED IT: NO VOLUME COLUMN, BECAUSE "TRADINGVIEW EXPORTS VOLUME" WAS NEVER TRUE.** Aaron took the CSV off the freshly-fixed export Pine (7,154 bars, all 60 decision + config columns present) and `compare_bos.py` refused before comparing a single bar — correctly. F10, the session-VWAP filter, is ON by default and needs the bar's volume, and the export carried none. 🔴 **The cause is a claim written into `compare_bos.py`'s own docstring as a fact: "TradingView exports it".** It does not. **"Export chart data" ships a Volume column only if the Volume STUDY is on the reader's chart** — so it is a statement about somebody's chart layout, not about the export format. ✅ **MEASURED rather than assumed: across ~40 real exports in `engines/`, exactly ONE carries volume, and it is the one whose Pine plots it** (`vwap_export.pine`). ✅ **Fixed at the source — `mpc_bos_strategy_export.pine` now plots `px_volume` itself (59 → 60 plots, four under Pine's cap of 64), which is the convention `vwap_export.pine` and `svp_export.pine` have carried since they were written.** This fork simply failed to inherit it, the same shape as the four config pins from the port two commits earlier. ⚠ **Adding a `plot()` shifts NOTHING on a tuned chart** — TradingView keys saved values off `input.*` declaration order, and a plot is not an input, so this paste needs no "Reset settings to defaults". 🔴 **The comparator had a SECOND, quieter defect in the same line, and it would have refused a correct export too: it looked for `volume` and nothing else, so even an export taken with the Volume study on would have been rejected, because TradingView capitalises it.** It now resolves `px_volume` → `volume` → `Volume`, exactly as `compare_vwap.py` and `compare_svp.py` already do, **and treats a column with nothing under it as no column** — a header over NaNs is not a measurement, and feeding it to the VWAP engine would answer F10's question with a number nobody took. ⚠ **The test FIXTURE is what hid it, in the direction this repo keeps recording: it wrote a `volume` column that no real BOS export has ever carried, so the guard was written against a name production does not produce and the suite was green about a file shape that cannot exist.** ✅ **4 new assertions, all proven non-vacuous — 3 watched RED against HEAD (`_volume_col` absent) and the empty-column one by MUTATION.** 54 mpc_bos tests green; the export's own two structural checks re-run (one-line diff against the parent, `grep -c '^plot('` now **60** — the previous entry's "59" was correct for its day and is superseded). ✅ **CLOSED THE SAME DAY: Aaron re-exported off the fixed Pine and `compare_bos.py` went GREEN** — 6,300 bars, no divergence, warmups 900 / 1000 / 2000 / 3000. So `mpc_bos_strategy_export.pine` is COMPILED, loads, and its 60-column decision stream is now proven to describe the same decisions the Python makes. ⚠ **Its own header still warns that `px_sz_top` / `px_sz_bot` are absent, and that warning is now load-bearing**: the green run had `bosUseFvg` OFF, so the Sniper Zone branch is unverified and cannot be verified until those two plots come back. **The standing lesson is the repo's own signpost rule pointed at a dependency rather than at a number: "the platform gives you X" is a claim, it earns the same evidence as any other, and this one was checkable in one `head -1` across the exports already on disk. When a tool depends on an input arriving from somebody else's system, plot it yourself rather than trusting that it comes for free.** Earlier the same day: 🔴 **`mpc_bos_strategy_export.pine` WOULD NOT LOAD: IT HAD TWO `strategy()` DECLARATIONS, AND THE SECOND ONE HAD EATEN A LINE OF THE FILE.** Aaron pasted it and got **CE10243 — "Scripts must contain one declaration statement… Your script has 2"**. The export was regenerated at some point by INSERTING its own `strategy("MPC BOS Strategy Export", …)` line rather than RETITLING the parent's, so line 131 sat in the middle of the header comment block and the parent's original declaration was still live at line 142. ✅ **Fixed by deleting the inserted line and retitling the real one, which is what this file family's regeneration recipe says to do in the first place** — "restore the line-N title", never "add a title". 🔴 **The insertion had also OVERWRITTEN a comment line** (`// no longer read off it — the entry band, stop and targets are computed from`), so the surviving sentence read *"The fib LEVELS themselves are the structure engine's own anchors"* — the opposite of the truth, since this fork computes its levels itself. **A stray line that lands in a comment block does not announce itself; it silently rewrites the paragraph it lands in.** ⚠ **Only the second half was visible from the error.** CE10243 names the duplicate declaration and says nothing about the mangled comment — that came out of the diff, which is the reason the check below is a diff and not a grep for `strategy(`. ✅ **VERIFIED THE WAY THIS FILE FAMILY DEMANDS, not by eye: `head -4389 <export> | diff - <parent>` is now exactly ONE line, the title**, and `grep -c '^plot('` returns **59**, the count the export's own header requires. **Both checks were already written down in that header and neither had been run on this file.** ⚠ **NOT COMPILED — the fix is verified structurally, and a paste is still the only compile gate this repo has.** **The standing lesson is about a recipe that is followed halfway: the export's header states the regeneration procedure precisely (`cp` the parent, `sed` the title line, append the parity block), and doing the title step as an INSERT instead of a SUBSTITUTION produced a file that was wrong in two places — one loud and one silent. When a recipe says "replace line N", a diff against the source is the only proof it was replaced.** Earlier the same day: 🔴 **THE SAME DAY'S OPTIMISATION WAS FALSIFIED BY ONE STRATEGY TESTER RUN, AND THE CHEAP CHECK WAS ONE PASTE AWAY THE WHOLE TIME.** Aaron pasted the new defaults into TradingView. On the SAME symbol, timeframe and window, with the config confirmed identical by the Pine's own `[CFG]` echo, **`bos_sweep.py` says 20 trades / 80% win / PF 2.97 / +102.5% and the Strategy Tester says 24 trades / 66.67% win / PF 1.043 / +5.01%.** The Tester is the ground truth. 🔴 **Every NUMBER in the pass below is therefore withdrawn** — the 65.4x at a matched drawdown budget, the 32-of-40 paired jitter, the 28-of-40 both-halves, the ATR plateau figures and Run 6's R totals all came out of that model and **none may be quoted.** ⚠ **It does NOT automatically make the shipped defaults wrong, and that distinction has to be held**: Run 7 compared two configurations measured by the SAME model, so a shared bias could cancel and leave the RANKING intact — or not. **Unknown is what it gets recorded as.** The defaults stay as shipped, LABELLED UNVALIDATED, until the model-free A/B is run (revert only `bosSlModel` → "Fib 1.0 (leg origin)" and `execMinStopMode` → "Off", read the four numbers against `24 / +5.01% / PF 1.043 / 34.11% DD`). ✅ **The disagreement is LOCALISED and that is the useful half: entries roughly agree (20 vs 24 over ten months), exits do not.** The model averages +0.73R per win against a −1.02R loss while the Tester's 66.67% win rate at PF 1.043 implies winners about HALF the size of losers — so the model extracts materially more from its winners than the Pine does, and the fault is in the exit ladder (staged stop, structure trail, or how the position leaves at TP3). 🔴 **THE SECOND FINDING IS THE ONE THAT GENERALISES AND IT IS THIS REPO'S OLDEST DEFECT ARRIVING FROM A VENDOR UI: the Strategy Tester header read "Mar 8, 2018 — Aug 7, 2026 DEEP" and the strategy received bars from 2025-09-30.** Ten months, not eight years — the `[CFG]` line is stamped `2025-09-30T18:00:00` because it fires on `barstate.isfirst`, and the chart is capped at ~20,000 bars, **exactly the size of the export CSV taken the same day, same first bar to the minute.** That header states what TradingView will let you ASK for; nothing on the panel says what ARRIVED, and every statistic beside it describes ten months while looking like it describes eight years. **Never read what you requested as what you received** — the hardcoded history floor did it at the start of a window, `run_report.py` did it by defaulting, the bar cache did it by recording its requested range, and now a vendor panel does it in the one place nobody thought to check. ⚠ **Ten months cannot settle this either way: PF 1.043 over 24 trades is indistinguishable from noise in both directions.** A 1H chart reaches ~2.5 years on the same bar budget. ⚠ **`compare_bos.py` and `strategies/python/mpc_bos/` are now BLOCKING rather than optional** — the export exists (20,079 bars, pre-Run-7 config) and until that gate is green no Python measurement of this strategy means anything. **The standing lesson is sharper than "a feature nobody has run is not a feature": Run 7 CARRIED its own caveat — "NOT PARITY-VALIDATED, read as a strong prior" — and the caveat was correct and was still not enough, because a table of numbers reads as a finding no matter what sentence sits under it. A measurement nobody has checked against the thing it measures is not a measurement. Run the ground truth FIRST, then optimise.** The withdrawn pass, kept for its method and its reasoning rather than its numbers: 🔴 **THE BOS STRATEGY'S STOP MODEL WAS THE WHOLE GAME, AND R HAD BEEN FLATTERING THE OLD ONE FOR ITS ENTIRE LIFE.** Aaron asked for the most profitable `mpc_bos_strategy.pine` obtainable, computed rather than argued. **~35,000 configurations over 186,384 true-M15 bars (2018-09-13 → 2026-08-07)** via the new `backtest/tools/bos_sweep.py`. **Three defaults moved: `bosSlModel` "Fib 1.0 (leg origin)" → "ATR", `bosSlAtr` 1.5 → 1.3, `execMinStopMode` "Off" → "% of price"** (its 0.10 value was already the default). 🔴 **The finding is not a tuned number, it is that `Fib 1.0` makes the stop A FRACTION OF THE LEG — at a 0.786 entry it risks 0.214 of it — so a small leg produces a tiny stop MECHANICALLY, and since R = profit / stop, a tiny stop inflates every R in the book without one extra dollar being made.** Measured on the old default: **median stop $1.58, tightest tenth $0.64**, where the $0.22 spread is **34% of R** and a 15-minute bar's low cannot say whether the stop was touched at all — inside one bar price crosses that spread constantly. ⚠ **The first leaderboard this sweep produced was ENTIRELY such configurations: every top-15 row had a median stop of $0.74 and read +250R to +450R.** They are a measurement artefact wearing a strategy's clothes, and the trap was already written into `bosEntryFib`'s own tooltip — which is the uncomfortable half, because it was recorded and still nearly shipped. **Ranking on R alone cannot see it; the tool now prints the tightest-tenth stop beside every row and refuses the ones a bar cannot resolve.** ✅ **The ATR stop does not care how big the leg was: median $3.89, tightest tenth $2.06.** ✅ **Compared at a MATCHED 25% DRAWDOWN BUDGET — the only fair way to rank a 55-trade book against a 600-trade one, since summing R treats a 25R drawdown as three times worse than an 8R one when at 10% risk it is the difference between giving back 30% and giving back 93% — the new default measures 65.4x against the old 23.0x, on 161 trades against 168.** ⚠ **The sumR column goes DOWN (+107.5R → +54.4R) and that is NOT a loss: a wider stop makes each R a bigger dollar amount, so the same money is fewer R. Never read a stop-model change off the R total.** ✅ **PROVEN BY PAIRED JITTER RATHER THAN BY A MEDIAN, and the pairing is what settled it.** Unpaired, the two were TIED (42.8x vs 42.3x) — because the real price series happens to be unlucky for one and lucky for the other, which is exactly the kind of thing a single backtest cannot tell you. Scoring BOTH configurations on **the SAME jittered series, 40 replays at ±$0.05 per bar with the engines re-run**: **the new default wins 32 of 40, and clears 4x on BOTH halves of the history in 28 of 40 against the old default's 4 of 40.** ✅ **The half-split says the search transfers rather than fits**: configurations chosen on 2018-2022 score **+0.243 expR** on 2022-2026 against a survivor average of **+0.123**; chosen on the later half, **+0.566** on the earlier against **+0.096**. ✅ **1.3 sits on a PLATEAU, not a peak** — 1.2 → 60.9x, 1.3 → 65.4x, 1.4 → 47.4x, 1.5 → 55.2x — and that is the only reason a single ATR multiple is defensible. ⚠ **The weakest number is stated rather than buried: the matched random control clears at only p = 0.04.** The ATR geometry is 75% win-rate by construction, so random entries with the same geometry also score positively and the trigger's contribution is diluted — **and the OLD fib default measures a STRONGER control edge (2.5σ) on the very same 168 entries**, which is a fact about the exit geometry, not about the trigger. Both are true and neither cancels the other. ✅ **Positive in 9 of 9 years**, longest losing streak 3, top 5 trades 28% of the total. ✅ **Re-confirmed and NOT changed**: `bosUseFvg` off, entry 0.786, `bosWhich` "All", `bosMinDispAtr` 0, and the TP rungs at 0/0/100 (Run 6, measured the same day: 30/30/20 gives +58.2R against 0/0/100's +107.5R, and the staged stop is unaffected because the TP **prices** drive it whatever the rung **sizes** are). ⚠ **VWAP is the most load-bearing filter in the file and it is not close — off, the book goes to 533 trades at PF 1.23 and its second half is 1.0x, i.e. it stopped working.** ⚠ **`max_days`, `min_leg`, `late`, `per_regime` and the runner trail all measured as NO-OPS at these settings and `min_disp` above 0 actively costs — they are not tuned values and nothing rides on them.** ⚠ **`mpc_bos_strategy_export.pine` was re-synced in the same pass and differs from its parent by exactly ONE line (the `strategy()` title), verified line-by-line** — an export taken at defaults must describe the configuration you trade. ⚠ **NOT PARITY-VALIDATED: `compare_bos.py` still does not exist**, so all of this is a claim about a MODEL of the strategy — one that reproduces its structure engine, VWAP engine, entry model, staged stop, TP ladder and single position slot, and has never been diffed against the Pine's own decision stream. **Read it as a strong prior, not a validated result.** ⚠ **No TradingView Strategy Tester figure describes these defaults either.** ⚠ **Changing a default does not move a chart you have saved settings on** — TradingView keeps saved input values, so "Reset settings to defaults" is needed to pick these up; only DEFAULTS and TOOLTIPS were touched, no input was renamed, reordered or retyped, so nothing else on your charts shifts. **The standing lesson is about the unit rather than the strategy: R is a RATIO, and every ratio can be improved by shrinking its denominator instead of growing its numerator. A stop model is precisely the knob that moves the denominator, so ranking stop models on R measures the wrong thing by construction — and it fails in the most seductive direction available, by handing you the biggest number on the page.** Earlier: 2026-08-06 — 🟢 **THE CYCLE FIB NOW PRICES THE WHOLE TREND, IN BOTH DIRECTIONS, AND THE THING THAT NEARLY SANK IT WAS THE DEFINITION OF THE WORD "CYCLE".** Aaron asked for a counter-trend fib on the ENTIRE move rather than the per-leg External Fib: a trend runs HH/HL/HH/HL and the reversal off it retraces the WHOLE thing, so the 0.618/0.702 worth watching is pulled from the trend's origin to its extreme. `mpc_assistant.pine` ONLY — the drawing block was deleted from `mpc_strategy.pine` on 2026-08-02 and nothing here reaches a trade. 🔴 **The old build could not do it and it is worth being exact about why: `f_cycleState` locked on `mtf.bull_sos` and NOTHING ELSE, so half of "every trend" — every down-cycle — had no ladder at all, and the one it did draw was read off a ONE-MINUTE `request.security` (`macroCycleTf = 1`), so a 15m chart drew a 1m-scale cycle bearing no relation to the BOS/SOS labelled beside it.** Its own comments still said "5m" long after that constant went to 1 — **a block nobody could check against the chart is a block nobody was reading.** Both are gone; the cycle is now the chart's own `st`, and deleting the security call paid for the bear side. 🔴 **THE SWEPT H4 HIGH COULD NEVER REACH THE JARVIS LIQ ROW, AND THE SAME DEFECT WAS SITTING IN ALL FOUR LIQUIDITY TIERS.** Aaron reported the H4 high not showing as swept on the table. **Two bugs, both on the roll bar, and they compound.** **(1) H4 was the ONE tier whose record reset ran BELOW the sweep-activation block.** The comment above the daily and session resets states the rule explicitly — *"Placed BEFORE the sweep-activation block so a sweep firing on the very same refresh bar still registers"* — and H4 did it the other way round, so a sweep registering on the first bar of a new H4 candle was written and then wiped in the same bar. **(2) `flag and not flag[1]` cannot survive a same-bar reset.** Every tier zeroes its sweep flag when the pool rolls and then re-runs its mitigation check on that SAME bar, so the flag goes false → true within one bar while `flag[1]` still holds the previous bar's `true` — the rising edge never fires. ✅ **DRIVEN, not reasoned: on a rising market that rolls into each new H4 candle already above the previous candle's high, the old rule prints "nothing" on EVERY BAR of the sequence** — which is exactly the report. The guard is now `liq_* == ""` — *swept, and not yet written down* — which asks the question actually meant and cannot be defeated by a same-bar reset. ⚠ **Applied to all ten activations, not just H4.** The bug is identical in the daily, Asia, London and NY tiers; it goes unnoticed there for a structural reason worth keeping — **H4 rolls six times a day and a trend very often rolls into a new candle already swept, while the daily and session pools roll once each and rarely open already swept.** The rarest instance of a bug is not a different bug. ⚠ **`recentBSL`/`recentSSL` resolve by `bar_index` with strict `>` in the order H4 → Day → Asia → Ldn → NY, so a TIE goes to H4 — the opposite of the "NY > London > Asia > Daily > H4" priority its own comment claims.** Left alone deliberately: it was never reachable before this fix, so changing it in the same pass would mix a behaviour change into a repair. **The standing lesson is that the rule was written down correctly, in a comment, directly above three tiers that obey it and one that does not — a comment cannot enforce an ordering, and the tier that broke it is the one that fires often enough for a human to notice.** ⛔ **THE CYCLE FIB IS COMMENTED OUT AS OF 2026-08-06, AT THE END OF THE SAME DAY IT WAS REWRITTEN** (Aaron: nothing reads it and the anchoring rule needs refining). **Four blocks are disabled and must come back TOGETHER** — the level colour/style constants (~734-772), `MACRO_GREY`, `f_macroLineStyle`/`f_macroLabel`, and the engine + drawing block, which carries a banner listing all four. ⚠ **THE TWO INPUTS ARE LEFT DECLARED AND GREYED (`active = false`), NOT DELETED.** TradingView keys a chart's saved values off DECLARATION ORDER WITHIN EACH TYPE, so removing a bool and an int from the middle of the panel silently resets every later bool and int on every chart running the script — **input count verified unchanged at 30, so no "Reset settings to defaults" is needed.** A greyed input that would do nothing if ticked is also the honest rendering; leaving it live-looking is how a dead feature gets reported as a bug six weeks later. ⚠ **COMMENTED, NOT LEFT INERT BEHIND A FLAG, and that is the cheap direction here**: Pine comments cost ZERO compile tokens, so this RELIEVES the CE10117 pressure this file has hit twice — **3,790 → 3,595 real code lines** — where a live-but-unused branch would have cost the same as before. ⚠ **Verified before cutting: all 54 references sit in ONE contiguous region and nothing outside it reads `macro_origin` / `macro_extreme` / `macro_dir`. That is NOT true of `mpc_strategy.pine`, where those two ARE the A+ sequence's HTF POI (`poiLongNow`/`poiShortNow`) — do not copy this cut across.** ⚠ **What it was when parked, so the refinement does not restart from zero:** a cycle is delimited by SOS events and the origin re-locks on every SOS; the two alternatives were both tried and both wrong (see below); the v3 rule reproduces Aaron's hand-drawn fib in SIMULATION and **was never read on a chart, so it is unvalidated**; and the open question is whether the 0.0 should be the raw wick extreme or the confirmed swing high — his hand-drawn 0 sat ~$25 below the visible high. 🟢 **THE CYCLE FIB NOW PRICES THE WHOLE TREND, IN BOTH DIRECTIONS.** Aaron asked for a counter-trend fib on the ENTIRE move rather than the per-leg External Fib: a trend runs HH/HL/HH/HL and the reversal off it retraces the WHOLE thing, so the 0.618/0.702 worth watching is pulled from the trend's origin to its extreme. `mpc_assistant.pine` ONLY — the drawing block was deleted from `mpc_strategy.pine` on 2026-08-02 and nothing here reaches a trade. 🔴 **The old build could not do it and it is worth being exact about why: `f_cycleState` locked on `mtf.bull_sos` and NOTHING ELSE, so every down-cycle had no ladder at all, and the one it did draw was read off a ONE-MINUTE `request.security` (`macroCycleTf = 1`), so a 15m chart drew a 1m-scale cycle bearing no relation to the BOS/SOS labelled beside it.** Its own comments still said "5m" long after that constant went to 1 — **a block nobody could check against the chart is a block nobody was reading.** Both are gone; the cycle is now the chart's own `st`, and deleting the security call paid for the bear side. 🔴 **THE DEFINITION OF THE WORD "CYCLE" WAS GOT WRONG TWICE, IN OPPOSITE DIRECTIONS, AND ONLY THE CHART SETTLED IT.** **(1) "The run between two SOS" — TOO SMALL.** A healthy trend CONTAINS SOS events (the shakeout `mpc_d_strategy.pine` exists to trade is exactly one), so the with-trend SOS that RESUMES a trend is a counter-trend SOS against the pullback — **transcribed to Python and driven on Aaron's own July sequence, it birthed a fresh ladder ON THE PULLBACK and overwrote the one being watched, ONE BAR before that ladder was due to retire.** The feature deleted its own output, silently, in the only case it exists for. ⚠ **A maturity gate did NOT fix it and looked like it had** — an ordinary pullback prints its own BOS, so it passes any `cycBos >= n` test. **(2) Origin-locked — TOO BIG, and this one SHIPPED.** The second build ended a cycle only when price closed back THROUGH its origin, reasoning that a move is not over until it is fully retraced. Sound, and **unbounded**: gold has never traded back through its 2020 low, so the origin sat on an ancient low, the extreme climbed to the all-time high, and the ladder spanned the entire loaded history. Aaron pasted it and said *"way too big… not sticking to the market structure I'm seeing on my chart"* — **one paste found what an afternoon of reading had not.** ✅ **(3) The rule that holds: a trend is ONE UNINTERRUPTED RUN of HH/HL, which is exactly what an SOS delimits, so the origin RE-LOCKS on every SOS** — and the pullback is stopped from superseding by a LIVE-LADDER LOCK (`macro_dir == 0`) rather than by a maturity gate. ✅ **Checked against his own hand-drawn fib rather than against an argument: the rule reproduces 1.0 = 3942.79 and 0.0 = 4202.55, and its 0.618 lands on 4042.02 — the price printed on his chart.** ⚠ **The live lock needs THREE deaths or it wedges**: resolved (zone → SOS → BOS), voided (closed past the 1.0), and **exceeded (closed past the 0.0)** — without the third, a shallow dip followed by a run to new highs leaves a ladder up for ever and no later reversal can draw one. **Lifecycle:** drawn only AFTER the reversal (Aaron's call — while the trend runs the extreme is still moving and every level under it would slide). ⚠ **"An SOS from the zone" cannot mean an SOS INSIDE the zone** — an SOS confirms above the zone by construction, breaking a swing the retracement left behind — so it is latched as *reached the zone, then an SOS followed*. ⚠ **The BOS test must exclude the SOS bar** (`st.bull_bos and not st.bull_sos`): the engine raises `bull_bos` on every bull break INCLUDING a bull SOS, so unguarded the SOS counts as its own confirmation and the ladder dies one step early, every time — the same guard `dCurBos` needs. ⚠ **Step order is the mechanism**: extend → BIRTH → re-seed → count, because birth must read the cycle the SOS just ENDED; swapping birth and re-seed prices the ladder off the move only just starting. ⚠ **The geometry is ONE formula for both directions** (`extreme - dir * range * ratio`, range ABSOLUTE), in the tracking block and the drawing block alike, because a per-direction branch is what lets a short's ladder quietly drift from a long's. ⚠ **`MACRO_MIN_TREND_BOS` is HARDCODED, not an input** — TradingView keys saved input values off declaration order within each type, so a new int here would shift every later int in this file. ⚠ **IT DRAWS ON 5m–30m ONLY, AND THE 1m EXCLUSION IS A DELIBERATE DIVERGENCE FROM THE EXTERNAL FIB** (Aaron, 2026-08-06: *"i dont want the fib on the one min… unless its tracking a 1m sos entry for the REV setup"*). `_fibTfOk` hides fibs below 5m but EXEMPTS the 1m, and that exemption is not a general "1m is fine" — the 1m is the ENTRY VIEW and the External Fib's SOS-leg fib IS the entry map there, which is exactly why it carries the further `fiboShowAligned` gate (a 1m SOS aligned with the 15m, after the REV setup has retraced). **The Cycle Fib answers the opposite question — where a multi-day trend retraces to — so it can never satisfy that condition and has no business on the entry view.** Copying the exemption across would put a ladder spanning days on the chart used to time a single entry. It appeared there in the first place only because flipping the default ON exposed a timeframe gate (`<= macroMaxTfMin`) that had never had a FLOOR, having lived its whole life switched off. ⚠ **A toggle that draws nothing on some timeframes has to say so in its own tooltip**, or the panel reads as broken. ⚠ **`showMacroFibInput` flipped back to `true`**; the 2026-07-31 reason for switching it off (eight permanent lines interleaving with the External Fib's eight) is spent now the ladder is on screen only during a retracement. **A changed default reaches a FRESH paste and nothing else** — no input was added, removed or reordered, so **no "Reset settings to defaults" is needed**. ✅ **Cost measured rather than assumed: a handful of real code lines** (the insertions are almost all comment), one `request.security` call REMOVED, `MTFStruct` still has two live consumers so nothing was orphaned — which matters in a file that has hit CE10117. ⚠ **NOT COMPILED, and the v3 rule has NOT yet been read on a chart.** There is no local Pine compiler and this feature has no parity harness by design (it exists only in this file). **The standing lesson is that this feature turned entirely on one undefined word. "Cycle", "trend" and "the run between two SOS" were being used as if they were the same thing, and each wrong definition was individually defensible in prose — one too small, one too big, neither visible in the source. What settled it was not an argument: it was transcribing the state machine and running it, and then a human pasting it onto a chart. ⚠ The sharper half is the ORDER those two happened in — the simulation caught the too-small rule and then passed the too-big one, because a simulation only ever answers the question its fixture asks, and no fixture here spanned six years. **A synthetic driver proves the logic does what you told it; only the real chart says whether what you told it was the thing wanted.** "cycle", "trend" and "the run between two SOS" were being used as if they were one thing, and the bug was invisible in the source and obvious the moment the state machine was driven. When a feature turns on a word, define the word first — then run it.** Earlier the same day: 🟢 **`execTimeStopHrs` 36 → 8 IN THE B-LEG PAIR, AND THE A+ PAIR DELIBERATELY KEEPS 36.** Both tooltips rewritten with the fork's own measured figures. Charged over 186,312 M15 bars, one axis per row: **8h → 114 trades / +17.56R / PF 1.45 / maxDD 5.15R** against 36h → 112 / +12.02R / 8.89R and Off → 111 / +6.50R / 12.01R. **The two forks measured the same lever on their own trades and got different plateaus — A+ 24h–40h, B-LEG 4h–12h — so this is a fork, not drift, and "reconciling" them would move every B-LEG exit to a number measured on a different strategy.** ⚠ **A DEFAULT and two tooltips only — no input added, renamed or reordered** — so TradingView's saved-value keying is untouched and **no "Reset settings to defaults" is needed**; the flip side is that an existing chart keeps whatever is already set, so confirm on the panel rather than assuming 8 is live. ⚠ **`execTimeStopMode` stays "Before TP1 only" on BOTH files and the `lStage == 0` / `sStage == 0` term must not be tidied out of `lTimeUp`/`sTimeUp`** — it is what makes the clock cut no winners, and a test now greps both Pine files for it. ⚠ **NOT COMPILED and NOT PARITY-RE-VALIDATED**; `compare_bleg.py` reads `cfg_time_stop_hrs` off the export, so an export taken before today decodes 36 and proves nothing about 8, and the clock has still never fired inside a parity window. Full measurement, the exit-stage map, and the four "let the winner run" levers that were tried and all LOST money: `strategies/python/mpc_bleg/CLAUDE.md`. Earlier the same day: 🔴 **`eqExemptFvg` WAS DEFAULTED ON IN THE A+ PAIR WITH NO EXPORT COLUMN AND NO PYTHON PORT, AND IT COST THREE DAYS OF A RED PARITY GATE.** `b1b461b` (2026-08-03) flipped that input `false → true` in `mpc_strategy.pine` and `mpc_strategy_export.pine` — deliberately, with a real measurement behind the rule change — **while the comment block eight lines above it still read "⚠ THE EXEMPTION DEFAULTS OFF HERE" and went on to name the exact consequences: "it changes which gaps exist, so it changes which entries fire… backtest/replay/EngineStack does not wire them yet, and no cfg_ column carries this input into the export builds."** Every word of that warning was correct and it was left standing over the flipped default. 🔴 **So the Pine and the live Python bot evicted different gaps for three days**: at bar 11031 of a 21,999-bar export Pine rested a limit on a liquidity-pinned gap edge (4965.73) that Python had FIFO-dropped, and `compare_strategy.py` reported it as an entry-RULE mismatch — the entry rule being identical on both sides. **Both export Pines now plot `cfg_eq_exempt`** and the harnesses configure the Python engine from it; an export with no such column is **REFUSED**, not defaulted, because the input predates its column by three days so neither answer is a fact about the file. ⚠ **The detection constants are deliberately NOT exported** — `eqPivotLen` / `eqAtrMult` / `eqMax` are hardcoded (2 / 0.1 / 6) precisely so the indicator and the strategy cannot draw different levels; export them the day either side makes one an input, not before. ⚠ **`mpc_b_leg_strategy_export.pine` got the column too even though that fork ships the input `false`** — both sides read 0 today, which is exactly what turns *two defaults that happen to line up* into a measured agreement. 🔴 **`fvg_export.pine` was found carrying the SELF-CANCELLING cap rule the indicator fixed in the same `b1b461b`** — it counted every gap while its drop scan skipped the exempt ones — so the harness that validates `engines/fair_value_gaps/` had gone stale against both the Pine it mirrors and the engine it checks, and the next export would have reported a correct engine as red. Fixed here. ⚠ **NOT COMPILED** — there is no local Pine compiler, and both A+ files sit near CE10117; the three edits are one `plot()` each plus one counting loop in `fvg_export.pine`, so they are small but not free. ⚠ **A new `plot()` is appended at the END of each export's PARITY block, so no `input.*` order moved and no saved chart setting shifts** — no "Reset settings to defaults" is needed for this paste. ✅ `compare_strategy.py` exit 0 at warmups 100 / 500 / 1000 / 2000 on the existing export with `--eq-exempt on`, and `--eq-exempt off` reproduces the original mismatch exactly. **The standing lesson is about where a warning lives: the comment was right, specific, and directly above the line that invalidated it — and a comment cannot fail a build. The export COLUMN is the guard; prose is not.** Earlier the same day: 🟢 **TWO B-LEG DEFAULTS MOVED, AND ONE OF THEM WAS A `maxval` RATHER THAN A NUMBER.** `mpc_b_leg_strategy.pine` and its export mirror: **`execTrailPct` 1.0 → 0.05** and **`bLegMaxDays` 1.25 → 4.0 with `maxval` 3 → 6**. Both tooltips rewritten with the measured figures. 🔴 **The `maxval` is the finding: 4–5 days measures best and the input could not express it, so the old 1.25 was never a tuned value — it was a cap nobody had checked.** Charged over 186,312 M15 bars: 1.25 → 59 trades / +7.29R · 3.0 → 92 / +10.56R · 4.0 → 112 / +12.02R · 5.0 → 118 / +13.76R, degrading past 5. **A `minval`/`maxval` is a claim about where the useful range ends, and it is exactly as unmeasured as any other constant until somebody sweeps past it.** 🔴 **`execTrailPct` was inert on this fork for its whole life, for a UNIT reason rather than a tuning one:** it is a percent of PRICE, and a B leg's whole 1R is 0.13%–1.25% of price, so at 1.0 one trail step is bigger than the entire trade and `f_swingRatchet` can never climb above the stage-2 floor. That floor is `TP1 price`, and a B leg's TP1 is exactly 1R from the entry by construction (`2*edge − inv` against a stop at `inv`) — so the runner banked precisely +1.00R and handed back the rest, on nine of fifty measured trades, one of them after running +6.82R. ⚠ **`mpc_strategy.pine` KEEPS `execTrailPct` at 1.0 and must not be "reconciled"** — the A+ sweep gives 0.25% → 43.6R against 109.3R at 1.0, i.e. the opposite conclusion, because an A+ stop is a fib fraction of a leg on a ladder whose rungs are also fib levels. **Same input name, same tooltip, different right answer either side of the fork.** ⚠ **DEFAULTS and one `maxval` only — no input was added, renamed or reordered**, so TradingView's saved-value keying is untouched and **no "Reset settings to defaults" is needed**. The flip side is that **an existing chart keeps whatever Aaron already has set**: a changed default reaches a fresh paste and nothing else, so confirm on the panel rather than assuming the new values are live. ⚠ **`bLegMaxDays` 4.0 is inside the NEW `maxval` and outside the old one** — a default outside its own input's range is a config the Pine cannot express, which would put `compare_bleg.py` red on the first export at shipped settings; a test now reads both Pine files and asserts the default sits inside `[minval, maxval]` and equals the Python config. ⚠ **The export mirror took the identical edit and was re-diffed: lines 1–4763 are byte-identical to the parent apart from line 40's title**, verified by an actual diff after an earlier check passed vacuously on two empty files (the split marker grep matched nothing and both `sed` ranges errored to empty — *a diff of nothing against nothing is green*). ⚠ **NOT COMPILED and NOT PARITY-RE-VALIDATED.** Parity is structurally unaffected because `compare_bleg.py` configures Python FROM `cfg_trail_pct` / `cfg_bleg_days`, **but a green run on an export taken before today decodes the OLD values and says nothing about these** — the same "green on a branch neither side entered" trap the min-stop guard hit. Full measurement, the four rejected levers and the unshipped Asia-session lead: `strategies/python/mpc_bleg/CLAUDE.md` → *The exit-ladder re-default*. Earlier the same day: 2026-08-06 — 🟢 **A TIME STOP LANDED IN ALL FOUR STRATEGY FILES, AND THE PINE MECHANIC IS WHERE THE INPUTS ARE DECLARED.** `execTimeStopMode` ∈ {**"Off"**, "Before TP1 only", "Always"} + `execTimeStopHrs` (36.0) in `mpc_strategy.pine`, `mpc_b_leg_strategy.pine` and both export mirrors, closing a long or short that has been open that many calendar hours **and still at stage 0** (TP1 never touched — `"Always"` drops that gate). **Defaulted ON ("Before TP1 only", 36h) on 2026-08-06 in all four Pine files, so a chart re-pasted after that date trades differently.** 🔴 **The stage gate is the whole lever and the Python replay measured how much: same 36-hour clock, `Before TP1 only` = +142.17R against `Always` = +97.32R on a +137.94R baseline — a THIRD of the edge, because `Always` cuts 26 trades where the gated version cuts 6 and the 20 extra are winners.** Do not "simplify" the `lStage == 0` term out of `lTimeUp`. ⚠ **THE INPUTS ARE DECLARED NEXT TO THE EXIT BLOCK (~4960), NOT UP IN THE GRP_EXEC PANEL WITH THEIR SIBLINGS, AND THAT MUST NOT BE "TIDIED UP".** TradingView keys a chart's saved input values off **declaration order within each type**, so inserting a string and a float at ~483 would shift every later string/float and silently reset them on every chart Aaron runs this on — the exact hazard this file warns about after the 2026-08-05 `mpc_assistant.pine` insert. The last `input.float/string/int` in the file is `execBeBandR` (~4050), so declaring the pair down at the exit block shifts **nothing at all**; `group = GRP_EXEC` still files them under Strategy Execution, only their position within that group moves. **So no "Reset settings to defaults" is needed for this change** — which is the whole reason it was done this way. ⚠ **`lEntryTime` / `sEntryTime` are new state**, assigned at the fill beside `lEntry`, because the clock has to run from the FILL — a resting limit can wait days. ⚠ **The close is `else if` after `execCloseOppSOS`**, mirroring the Python's `elif` chain exactly, so the three force-close paths keep ONE precedence on both sides. ⚠ **Both export mirrors were REGENERATED off their parents** by the documented splits and re-diffed: **exactly the line-32 / line-40 title differs**, nothing else. They carry two new columns, `cfg_time_stop` (`Off?0 : Before TP1 only?1 : Always?2`) and `cfg_time_stop_hrs` raw — deliberately NOT folded into `cfg_exitmode`, which is the two ladder DROPDOWNS. **Absent column ⇒ Off in the decoder, never the Python default**, so archived exports still replay correctly. ⚠ **NOT COMPILED — there is no local Pine compiler — and NOT parity-validated.** `mpc_strategy.pine` has hit CE10117 twice; this adds two inputs, two `var int`s, two bool expressions and two `strategy.close` branches, so it is small but not free. **A parity run taken at the Off default would prove nothing about this lever** — export with the mode ON and check the trade list actually contains `time stop` closes, the same "was the feature EXERCISED" check the min-stop guard needed the same week. Earlier the same day: **THE 1m SHOWS ITS FAIR VALUE GAPS AGAIN, THE CAP STOPPED THROWING AWAY THE ONES THE TRADE IS TAKEN FROM, AND THERE IS A NEW BIAS TOGGLE.** Three changes, `mpc_assistant.pine` ONLY, and the reason they stop there is the same one every time: each of them decides WHICH GAPS EXIST, so porting any of them to `mpc_strategy.pine` moves entry edges, moves trades, and puts `compare_strategy.py` red. **(1) `f_fvg1mZone()` IS DELETED.** It ran on the 1m chart alone and blanked every gap outside the External Fib's entry band — so an out-of-band gap was hidden, and, because the band came FROM the fib, **a 1m chart with no aligned REV setup showed no gaps AT ALL**, which is most of the session. That gate needs `rStage >= 3` plus a 1m SOS in the 15m's direction confirming after the 15m SOS closed; the bar for drawing a gap was far higher than "is there a gap here". The 1m now draws on exactly the same rules as every other timeframe. ⚠ **Deleted, not made inert** — this file sits at Pine's compile-token cap (CE10117), so a dead branch is not free. ⚠ **`mpc_m15_playbook.pine` still has its own copy at ~3457 and was deliberately left alone.** **(2) THE ENTRY-ZONE GAPS ARE NOW EXEMPT FROM `fvgMaxCount`.** The complaint was the cap working exactly as written: after a bearish SOS price drops and prints gap after gap on the way down, the FIFO drops from the FRONT, and **the oldest gaps on a retrace setup are the ones UP IN THE ENTRY ZONE — the only gaps the trade is ever taken from.** The chart was discarding the levels being watched to make room for levels below price that nothing reads. A gap overlapping the live fib's **0.382–0.886** band **on the trade's own side** no longer counts against the cap and is never chosen for eviction; it rides on top exactly as an EQ-backed gap does. ⚠ **Both loops — the COUNT and the DROP SCAN — apply the same exemption**, which is the whole lesson of the 2026-08-03 EQ fix: a protected gap that still holds a slot evicts an ordinary one in its place, and the exemption becomes self-cancelling. ⚠ **0.382, not 0.5**, is the shallow edge — one rung shallower than the bot's own entry zone, so a gap sitting just above 0.5 survives to be looked at. ⚠ **Direction-matched**: on a bearish leg only bearish gaps are pinned, because the A+ entry rule cannot read the others either. **(3) A NEW `↳ Trend-Aligned FVGs Only` TOGGLE (default OFF) under Fair Value Gaps.** Separate from the shared `Trend-Aligned Zones Only`, and it reads a **DIFFERENT DIRECTION** — that is the load-bearing half. The shared filter reads `st.dir`, the CHART's own structure, which on a 1m chart flips several times inside one 15m leg, so a short's gaps would appear and vanish while the setup never changed. This one reads the **DRAWN FIB's** direction, so it holds for the life of the leg the trade is on. ⚠ **ABSOLUTE — no EQ exemption**, unlike the shared filter: "only gaps with bias" has to mean only gaps with bias. The EQ exemption still protects a counter-side gap from the CAP; this just refuses to draw it. ⚠ Applies to gaps only; order blocks are untouched. **THE PINE MECHANIC WORTH CARRYING:** `fiboP1`/`fiboP6`/`fibo_dir` are declared ~800 lines BELOW the FVG cap, and Pine needs a declaration before its use — so the band and the direction are **PUBLISHED DOWNWARD** into globals declared beside their consumer (`fvgZoneLo`/`fvgZoneHi`/`fvgZoneDir`/`fvgBiasDir`), read one bar late. **The lag is deliberate and is safe only because of WHAT reads it: the cap decides which gap to THROW AWAY, never which one to trade.** ⚠ `fvgZoneDir` is zeroed once the leg completes so a finished setup stops pinning gaps; `fvgBiasDir` is the RAW direction and is NOT zeroed, because the bias filter must keep working after TP3. **Two globals because they answer two questions** — sharing one would tie the filter's life to the cap exemption's. ✅ **COMPILED IN TRADINGVIEW BY AARON, 2026-08-05.** There is no local Pine compiler, so a paste is the only compile gate this file has, and it is the one that mattered here: a new `input.bool` title is a string literal and a malformed one is a compile error, so this proves the toggle and the four published globals parse. ⚠ **It proves the file BUILDS, not that the three rules are right** — the cap exemption, the deletion and the bias filter are all read off a chart, and none of them has a parity harness (they exist only in this file, by design). ⚠ **A new input was inserted mid-list, which shifts every later input's saved value** — TradingView keys saved values off declaration order — so click **"Reset settings to defaults"** once, or the Chart Tools switches read one position out. Earlier the same day: 🔴 **`execMinStopMode` NOW DEFAULTS ON (`"% of price"`, `execMinStopVal` 0.10 → **0.08**) IN BOTH A+ FILES.** Aaron's call after a 23-config sweep over 186,220 M15 bars: the A+ baseline moves **183 trades / +134.75R → 181 / +136.75R**, 0.10 costs 1.84R, 0.15 costs 25R, 0.30 costs 48R. The guard refuses a setup whose stop lands closer to the entry than the floor, because `qty = risk / stop_distance` means a collapsing stop builds a huge position rather than risking less. Both tooltips were rewritten with the measured numbers, `execMinStopVal`'s `step` went 0.05 → 0.01 (0.08 is not reachable in 0.05 steps), and `mpc_strategy_export.pine` took the identical edit so its body stays byte-identical to its parent apart from the title line and the diagnostic-log block. ⚠ **A DEFAULT changed, not an input's order or its title** — TradingView keys a chart's saved input values off declaration order, so **an existing chart keeps whatever Aaron already had set** and only a fresh chart gets 0.08. Do not read the new default as having reached his charts; confirm on the panel. ⚠ **`x ATR(14)` was measured and is the WRONG mode for this guard**, which is the counter-intuitive half: it is the only mode that adapts to volatility and it was the cheapest on R, but at 0.35 and 0.40 it **never refuses the tightest stop in the whole history** ($1.03), because that bar was quiet so $1.03 was not tight *relative to ATR*. The hazard is in price units and volatility does not enter it. The tooltip now says so, since the dropdown otherwise invites exactly that choice. ⚠ **Parity re-run GREEN with the filter FIRING** — `compare_strategy.py` exit 0 at warmups 100 / 500 / 1000 / 2000 on a 21,899-bar export at `"% of price"` 0.30 where **block code 7 was raised 213 times**; an earlier export the same day was green at `"Fixed $"` 0.10 and raised code 7 **zero times in 21,897 bars**, i.e. green on a branch neither side entered. **Before trusting a gate on a Pine feature, check the feature was EXERCISED in the export** — a block-code histogram is the whole check. `mpc_b_leg_strategy.pine` has no such input and is untouched; `compare_bleg.py` exit 0. Earlier: 2026-08-04 — **THE JARVIS TABLE GAINED A GROUP COLUMN, THE EQ LEVELS CHANGED WHAT "TAKEN" MEANS, AND THE 1m STOPPED TRACKING A FINISHED SETUP.** Four Pine changes across `mpc_assistant.pine` and the A+ strategy pair, and the line between them is the one worth carrying: **detection is FORKED on purpose, appearance is SYNCED.**

🔴 **The one real defect: `f_rev15` had three ways to die and the chart-side A+ engine has four.** The missing one is the one that fires on a WIN — `fibo7Touched`, price back at the leg origin. So on the 15m chart the REV row read `Pass` the moment TP3 printed, while the **1m chart kept the same leg alive at stage 4 saying TAKE PROFIT** until an opposite SOS or a continuation BOS happened along, which can be hours. Two charts, two answers, one setup. Worse than a stale row: the RE-ENTRY round trip clears the TP latches when price returns to 0.618, so a finished trade could hand the 1m a fresh AWAIT and ask for a 1m SOS on a leg the 15m had closed the book on. Fixed with `or L_tp0` / `or S_tp0` on the two death conditions — `L_tp0` **is** TP3, since `p0` is `L_high`, the leg origin, the same 0.0 the drawn fib labels TP3. ⚠ **It kills one bar LATE**: the death block runs before the fib block that sets the latch, where the 15m side kills on the bar itself. Left as is — every other value this engine ships crosses the security boundary a bar late in the same way. ⚠ **It retires the whole 1m stack together, not just the row** — `rStage` falling below 3 drops `_m15Retraced`, which is what `fiboShowAligned`, the 1m External Fib, the 1m Sniper Zone and the 1m ENTRY row all hang off. ⚠ **Nothing on the 15m moves**: every consumer of `rStage`/`rTp50`/`rDeepCode`/`rZoneLo` sits behind `_fibOneMin`, `_sn1m`, `revOn1m` or the non-15m branch of the table, checked one by one; `f_rev15` exists only in `mpc_assistant.pine` and `mpc_m15_playbook.pine`, so **no bot and no parity gate can see this.**

**A WICK TAKES AN EQ LEVEL — in the indicator ONLY, and the fork is the point.** The test was `close > lvl`, so a candle that speared clean through an EQH and closed back under it left the line drawn. A close test is the wrong QUESTION for this object: an EQH is not resistance being "broken", it is a **pool of resting stops**, price reaches those stops with its WICK, and whether the candle closed back below describes what happened AFTER the liquidity was taken. Same correction the order blocks got on 2026-07-31, for the same reason. It also makes the deletion STABLE on the live bar — a bar's high only ever grows, where the old close test could delete a level intrabar and put it back on the next tick. Its three dials went back to constants the same day after a few hours on the panel (**sensitivity 0.1 → 0.25, count 6 → 14, extension 50 → gone**), the third time this file has run that expose-measure-lock loop. ⚠ **`mpc_strategy.pine` and `mpc_strategy_export.pine` were deliberately NOT synced on any of that**, and `engines/equal_highs_lows/` still reads a close too. **`eqAtrMult` and `eqMax` change WHICH GAPS EXIST through `eqExemptFvg`, so they change which entries fire** — and `backtest/replay/EngineStack` does not wire `eq_levels` into the FVG engine at all, so Python cannot see an EQ level even in principle. Porting them would move trades AND put `compare_strategy.py` red. **The indicator is a display consumer here; the bot is not.**

**What the strategy pair DID get is appearance, and only appearance.** The EQ line is solid instead of dotted and **ends at the live candle** rather than running `i_lineExtend` bars past it (a pool is not a forecast), and its tag anchors with `style_label_left` + an invisible box instead of `style_none` — `style_none` centres text ON the anchor, so half the glyph sat above the level and read as a tag floating over the line. Plus the **four-column JARVIS table**: GROUP · row · STATUS · INFO, with `SETUP` / `BIAS` / `LIQ` / `STR` printed once on each group's first row. ⚠ **The group tag cannot be latched inside the row helper** — Pine lets a function READ a global but never WRITE one (**CE10088**, the error `ob_export.pine` hit on 2026-07-31) — so the CALLER owns the once-only rule; rows that always print hardcode their tag, LIQ and the EXT/INT pair use a local latch. The LIQ rows needed a real fix rather than a copy: `"LIQ BSL", "BSL", …` rendered as `LIQ | BSL | BSL | Day High`, the same word twice, so STATUS now says **"Swept"** (what happened) and the pool name moved to the row label. Status cells are tinted `color.new(vc, 87)` — **derived from the colour the row already chose, never looked up off the status TEXT**, because these statuses are not a fixed vocabulary and the one a lookup missed would silently render untinted. Palette: charcoal body, black-only header, cyan on the JARVIS cell alone, muted-slate INFO, 1px blue frame replacing the 2px yellow. ⚠ **Panel inputs changed their option lists** — four corners instead of nine, no "Huge" — so **click "Reset settings to defaults" once after pasting**, and note the `=>` switch fallback matters MORE in the strategy than in the indicator because **"Top Center" was the strategy's shipped default**, so every saved chart holds a string the panel no longer offers. ✅ **Cosmetic and earned rather than asserted on the strategy side**: the table reads state and writes none back, `showConfTable` still defaults FALSE there, all **38** `px_*`/`cfg_*`/`dbg_*` columns are still present, and **the export was REGENERATED off the parent by its documented split so the shared body is byte-identical except the line-32 title** (verified by diff, both files carry the identical four-hunk EQ diff). ⚠ **NOT COMPILED — there is no local Pine compiler — and `mpc_strategy.pine` has hit CE10117 twice.** The fourth column adds one `table.cell` per row inside the row helper, so no new main-body statements (CE10295 unaffected), but it does add compile tokens; if CE10117 returns, this block is the first thing to cut again. **The standing lesson is a new one and it is about WHERE a rule may be shared: two files can agree on how a thing LOOKS and still have to disagree about what it IS, and the boundary is whether the rule reaches a trade. An indicator may lead; a bot moves only with its Python port and its parity gate.** Earlier: 2026-08-02 — **ONE NAME AND ONE EXPLANATION PER PARAMETER, SHARED BY THE PINE AND THE LAB.** The two panels had drifted into separate vocabularies for the same settings — the Pine said "Entry: floating gap enters on the nearest fib SHALLOWER than it" where the lab said "Floating gap → nearest fib ABOVE", and the lab's version was **wrong for shorts** (shallower is above on a long and BELOW on a short). A script diffed all 51 lab params against their Pine input titles: **6 matched, 37 differed**. They now all match — **42 of 43 shared params are byte-identical**, and every lab `desc` is that input's Pine tooltip verbatim (43 of 43), so the two UIs cannot teach different things. The one deliberate deviation is `exec_conf_sz`, whose lab label carries a `(not supported)` suffix because the Sniper-Zone entry is Pine-only. Same pass, at Aaron's request: **every execution and divergence tooltip was rewritten short.** They had grown into forensic essays — the `execFvgPreZone` tooltip alone ran ~1,400 characters of measurement narrative. The rule now is what it does, what ON vs OFF means, and the one fact that changes the decision; **the long write-ups live in CLAUDE.md, which is where a reader can actually find them again.** Both A+ Pine files shrank ~6,000 characters and the B-LEG pair ~3,600, so this RELIEVES the CE10117 token pressure rather than adding to it. 10 settings that had no tooltip at all (Trade longs/shorts, Risk % per trade, the stop buffer) got one. ⚠ **Titles only — never a plot title, never a default, never the ORDER of an `input.*` call**, because TradingView keys saved chart settings off declaration order: a rename carries Aaron's saved values, a reorder loses them. Verified after the fact: **35 of 35 execution defaults unchanged**, both export mirrors still byte-identical to their parents except the line-32 `strategy()` title, 363 strategy tests + 337 backend tests green, and **BOTH parity gates exit 0 at warmups 100 / 500 / 1000 / 2000** on fresh 21,715-bar `VANTAGE_XAUUSD, 15m` exports taken off the RENAMED files — `compare_strategy.py` (`cfg_bits` 544375) and `compare_bleg.py` (`cfg_bits` 61047). Those exports are also the compile proof: a Pine input title is a string literal, so the only way this change could break anything is a mangled quote, and a mangled quote is a compile error rather than a silent behaviour change. Block reasons were safe to reword because `f_blkWhy` maps an int CODE to display text — the parity stream carries the code (`f_blkCode`), never the sentence. ⚠ **`mpc_bos_strategy.pine` was only partly synced on purpose**: its divergence group and Trade longs/shorts were aligned, but its entry inputs ("...and require one (no gap = no trade)") describe a genuinely different setup and were left alone. **Earlier the same day: the A+ panel's shipped defaults were set from Aaron's own screenshot, and the export now CARRIES the entry model.** `execFvgPreZone` was briefly defaulted ON earlier the same day and is **reverted to OFF** — the full-panel screenshot he sent is the authority, and it shows the box unticked. Every other visible toggle already matched. `mpc_strategy_export.pine` was regenerated off the parent (body diff back to exactly the line-32 title) and its `cfg_bits` extended with the five 2026-08-02 toggles — **`execFibOverlap` 131072 · `execFibDeepEdge` 262144 · `execFibNearest` 524288 · `execFvgPreZone` 1048576 · `execSlDeep` 2097152** — because without them a parity run configures the Python bot to a DIFFERENT entry model and reports the difference as a logic bug, the exact `execRunnerTrail` trap of 2026-07-26. ⚠ **Bit 65536 stays RETIRED and the new bits start at 131072**; an export taken before today has all five clear, which decodes to Method 3 with the gate off — i.e. the build it came from, so archived exports still replay correctly. **The whole model is now ported to `strategies/python/mpc_sos_fade/`** (see its CLAUDE.md), and the two sides' 23 execution-input defaults were diffed **programmatically, not by eye**: 0 mismatches. ✅ **BOTH FILES COMPILE AND A+ PARITY IS GREEN** — Aaron pasted them and exported the same day, which is stronger evidence than a paste alone: `compare_strategy.py "VANTAGE_XAUUSD, 15_cfa13.csv"` → **exit 0 at warmups 100 / 200 / 500 / 1000 / 2000**, 21,702 bars, 2025-08-31 → 2026-08-02. The export's `cfg_bits` read **544375 with bit 524288 SET**, which is the proof the new plot line compiled AND that the Pine was actually running rule 3 — a green taken with every new bit clear would have validated nothing about this change. ✅ **THE CONFIRMATION TABLE IS RESTORED IN `mpc_strategy.pine`, COMPILED, AND PROVEN TRADE-NEUTRAL.** It had been dead since 2026-07-24: `f_drawTable` was cut for compile tokens and the three inputs survived, so ticking the box drew nothing (it defaults OFF, which is why it went unnoticed — what Aaron had been reading in bar replay was `mpc_assistant.pine`'s copy, or the B-LEG fork's). Aaron uses it for bar replay and asked for it back, so it was **RECOVERED FROM `b25789d~1`, never rewritten from memory** — this file's OWN table, not the near-identical fork in `mpc_b_leg_strategy.pine`. Restored in three places: the JARVIS colours, the `ext_struct`/`int_struct`(+`_bar`/`_valid`) slots with `jarvisTable` + `f_jRow3`, and the 92-line `f_drawTable` with its single main-body call — which also revives the orphaned `f_tablePosition`/`f_tableSize`. The SNIPER-ZONE slot was deliberately NOT restored: the table never read `sz_status`/`sniperZoneActive`, so it was dead weight even before the cut. Budget came from the ~207 lines freed earlier the same day. ✅ **PROVEN COSMETIC BY MEASUREMENT, NOT BY ARGUMENT** — a second export was taken off the rebuilt Pine at the identical config (`cfg_bits` 544375 both times) and the two exports' `px_*` decision streams were diffed cell-by-cell over their **21,702 shared bars: 21,701 byte-identical**, the only differences being the four columns on the FIRST export's still-forming last bar (NaN then, real values now — the documented TradingView artifact `compare_strategy.py` already skips). Not one fill, exit, stage, block or R moved. Parity re-run on the new export: **exit 0**. ⚠ **If CE10117 returns, this block is the first thing to cut again** — the file has hit that cap twice. Earlier the same day: **28 unused toggles deleted from `mpc_strategy.pine`, and the export regenerated behind it.** Aaron asked which settings he genuinely never touches; the audit found 157 inputs, and he approved cutting four things. Gone: the whole **Cycle Fib** input group (27 inputs — master toggle, line extension, draw-up-to-timeframe cap, and a show/colour/style trio for each of eight levels) together with its drawing block, its two style helpers, its eight line+label handles, the eight touched-flags that only coloured them, `MACRO_GREY`, `macroFibAllowed` and `macro_visible`; and **`execFvg50`** ("Entry (least favorable): FVG must touch the 0.5 line") with its fallback loop. 157 → **129 inputs**, 207 lines lighter, which is real headroom in a file that has hit CE10117 twice and sits near CE10295. ⚠ **THE CYCLE FIB'S TRACKING STAYS AND IS LOAD-BEARING — only the DRAWING went.** `macro_origin` / `macro_extreme` are the A+ sequence's HTF POI (`poiLongNow` / `poiShortNow`) and the B-LEG log line's premium/discount zone; both gate on `macro_origin_locked` alone and never read `macro_visible`, which is why that latch could go with the lines. Every value the execution layer reads is byte-identical, so **no trade moves** — the removals are cosmetic-only by the same grep test the Kill Zones / VWAP / Order Blocks / SVP cuts used, re-run here (zero references to any deleted identifier). **`mpc_strategy_export.pine` was REGENERATED off the parent in the same pass** by its own documented split (`sed -n '1,4682p'` + the appended PARITY block), because a deleted input with its consumer still in place is precisely the `CE10272` failure of 2026-07-26 — the export's `cfg_bits` plot still read `execFvg50`. Body diff vs the parent is again **exactly the line-32 title**, and all 25 `px_*` / `cfg_*` / `dbg_*` columns verified present. ⚠ **`cfg_bits` bit 65536 is RETIRED, NOT FREE** — it carried `execFvg50`, now always reads 0, and `compare_strategy.py` still refuses an ARCHIVED export that has it set (read straight off the bit now, not through a config field). **Do not reuse 65536 for a new toggle**: an old export would decode the new flag as whatever `execFvg50` was. Python side cleaned in lockstep — `exec_fvg_50` removed from `config.py`, from the lab panel (`meta.json`), and from both harness encoders. **129 strategy tests green.** ⚠ **NOT compiled** — there is no local Pine compiler, so both files still need pasting into TradingView, and **"Reset settings to defaults" must be clicked once** (TV maps saved input values by POSITION, and 28 inputs were removed from the middle of the panel). ⚠ **`mpc_b_leg_strategy.pine` and its export STILL carry `execFvg50` and the full Cycle Fib group** — deliberately out of scope (Aaron's request named the A+ file), so this is a KNOWN fork, not an oversight. ⚠ **The three "Confirmation Table" inputs are still there and still DEAD** — `showConfTable` / `tablePositionInput` / `tableSizeInput` read by nothing since the table was deleted 2026-07-24, plus the orphaned `f_tablePosition` / `f_tableSize` helpers. Aaron says he USES that table for replays; the working one is in `mpc_assistant.pine` (default ON), so **ticking the box on the strategy draws nothing**. Decide before deleting: drop the three dead inputs, or rebuild the table here at a real token cost. Earlier: 2026-08-01 — 🔴 **THE PHANTOM-EXIT BUG IS FIXED, AND IT WAS IN EVERY STRATEGY FILE.** `BUG_exit_fill_price_mismatch.md` (open since 2026-07-14, "all three legs at one price one bar after entry") was never a TradingView fill artifact — it was **the FILL BAR being allowed to stage the stop**. A resting limit is reached by price coming to it from the wrong side (a buy limit fills on the way DOWN, a sell limit on the way UP), so the entry bar's *favourable* extreme is the approach to the order, not a move the trade made. The staging block read it anyway, `sStage` went to 1 on the fill bar, the stop went to `sEntry - beBuf` — **below** the entry for a short, i.e. already through the market — and TradingView market-closed every leg at the next bar's open. Confirmed on real Vantage bars for the reference trade (entry bar 2025-09-09 06:30 UTC: low **3637.80**, ten dollars below the 3647.91 fill, all of it pre-fill; `sTP1` was 3645.21) and reproduced against the real Python `Execution` class. **Fixed in all five strategy Pine files** (`mpc_strategy`, `mpc_strategy_export`, `mpc_b_leg_strategy`, `mpc_b_leg_strategy_export`, `mpc_bos_strategy`) — the staging block is gated `and strategy.position_size[1] > 0` (mirror `< 0` for shorts), i.e. "we were ALREADY in the position last bar, so this is not the fill bar", and `lMaxFav`/`sMaxFav` now seed from `lEntry`/`sEntry` instead of the bar's extreme. **Four changed lines per file and ZERO new main-body statements** — that is deliberate: this family already sits near Pine's CE10295 statement cap, which is why the gate is a bare `position_size[1]` condition and not the `lJustFilled`/`sJustFilled` helper bools it started as. **Also fixed in `strategies/python/mpc_sos_fade/execution.py`**, which `mpc_bleg` reuses. Both export pairs re-diffed against their parents: still the line-29/40 title only. **Measured on lab run `d2ab68f9e884`** (165 trades, 6.5y): **all 165 entries unchanged**, 30 results changed, 18 better / 12 worse, **+101.68R → +112.43R**, win rate 63.6% → 67.3%; the four biggest gains are trades the bug killed at breakeven that were really +3.90R / +2.98R / +2.86R / +1.87R. ⚠ **The fix is not free and max drawdown was NOT measured** — 12 trades that used to scratch now take a full −1R. ✅ **BOTH PARITY GATES RE-VALIDATED THE SAME DAY on FULL-HISTORY post-fix exports** — `compare_strategy.py` (`15_fd236.csv`) and `compare_bleg.py` (`15_1b2f3.csv`), both **21,691 bars, 2025-08-31 → 2026-07-31, exit 0 at warmups 100/200/500/1000/2000**, no truncation warning on either. **The fingerprint is measurably gone:** on the entry bar, is `px_stop` already at breakeven instead of the real SL? A+ before = **4 of 26** entries; A+ after = **0 of 27**; B-LEG **0 of 5**. All four affected candles sit inside the new window, so each reads before/after on the same bar — 2025-10-02 died in 1 bar at −0.120R and now runs **47 bars to +0.008R**; 2025-12-02 went −0.860R → **−1.000R**; 2026-05-11 went +0.008R (1 bar) → **−1.000R** (3 bars); 2026-07-20 is **unchanged** at +0.859R (wrong stop, never hit). **Three of four get worse or stay flat — the fix is right anyway**, because the exit price now corresponds to an order the strategy actually placed. An earlier PARTIAL pair the same day (`15_88f5a`/`15_21332`, ~6,340 warmup bars missing) was also green, and it exposed a real harness asymmetry that was fixed: `compare_strategy.py` HARD REFUSED any truncated export while `compare_bleg.py` has always replayed until the engine converges. It now warns and requires `--warmup >= the missing bars`; `--debug-arm` still refuses, because it diffs the chart-relative `dbg_*` bar indices. 534 tests green. **The standing lesson: a green parity run says the two implementations AGREE, never that either is right** — this bug was faithfully ported, so the harness was green for its entire life. ⚠ **Recorded the same day, and it is NOT this bug and NOT a defect — a backtest LIMITATION that will keep appearing on the chart forever.** With the staging fixed, a stop can still legitimately end up on the wrong side of the market: price tags TP1, the stop stages to breakeven, then price closes back through it INSIDE THE SAME BAR. The stop only goes live NEXT bar (`calc_on_every_tick = false`), so by then it is behind the market and TradingView market-closes at that bar's OPEN rather than at the stop. Being OUT is CORRECT — price genuinely went through the stop — it is only the exit PRICE that is imprecise, because a bar-replay tester checks orders once per bar while a real broker watches every tick and would have filled at the stop. **It errs in the safe direction (the backtest looks slightly worse than reality) and it behaves identically in Pine and Python, so parity is unaffected** — no `compare_*.py` will ever flag it. A "never place a stop through the market" clamp was considered and deliberately NOT added: it would change real behaviour and would have to land in all five Pine files, so it is its own change with its own measurement. Canonical write-up: `strategies/python/mpc_sos_fade/CLAUDE.md` → `### Wrong-side stop fills`. Earlier: 2026-07-31 — **the harness pass: four export builds validated on two real grand exports, `mpc_jarvis_v2.pine` DELETED, and the session windows forked back together.** `ob_export.pine` was REBUILT (1148 → ~300 lines — it no longer embeds the structure engine, killing this folder's worst maintenance trap) and needed a real Pine fix to compile at all: **`CE10088 — a function may READ a global but never WRITE one`**, which the export-only counters were doing inside `extendOBs` and `f_obAdd`. `fvg_export.pine` had two holes that would each have produced a misleading GREEN (6 plotted slots against a cap of 8; a flat gap floor where mpc's is timeframe-split). `mpc_b_leg_strategy.pine` + its export had **never received the DST-aware session windows** the A+ parent has carried since 2026-07-12 — a real fork, and trade-affecting in principle because session H/L feed the sweep that arms A+; both bots re-verified GREEN after the sync, and then **on a FRESH B-LEG export off the synced Pine** (`--warmup 800`, exit 0, 6,329 bars over a window sitting entirely inside BST/EDT — the half of the year where the new windows and the old ones actually disagree, so this is the run that tests the fix rather than the Python side's self-consistency). `mpc_m15_playbook.pine` and `svp_export.pine` synced too, and `compare_svp.py` re-run green (12,117 bars). Of the four edited files, three were exported from, which proves them; `mpc_m15_playbook.pine` is uncompiled and **that is fine — Aaron's call, 2026-07-31: it is his brother's work in progress, not ready, and not a validation item for this repo.** Full record in the 2026-07-31 harness-pass section below, including the line-targeted-edit warning (the old Tokyo and New York values collide, so a global string replace corrupts them) and **the harness bug the first PARTIAL export exposed: `bl_*_bar` carries Pine's chart-relative `bar_index`, so `compare_bleg.py` was comparing two different coordinate systems and had only ever been right by the accident of full-history exports.** Earlier: 2026-07-30 — **`mpc_strategy_export.pine` REGENERATED off the parent, closing the last surviving drift.** It had no `execMinStopMode`/`execMinStopVal`, so the moment that filter was switched on the export stopped describing the strategy and `compare_strategy.py` would have reported GREEN while diffing a config it could not read. The regen followed the file's own documented procedure (`sed -n '1,4581p' mpc_strategy.pine` + the appended PARITY EXPORT block, then restore the line-29 title) and **`diff` over the shared range is now exactly one line — that title**. Two new columns carry the filter: `cfg_min_stop` (`Off?0 : % of price?1 : Fixed $?2 : x ATR(14)?3`) and `cfg_min_stop_val` (raw float, same reason the exit numerics are raw — a packed float that rounds mis-configures the bot silently). Deliberately NOT folded into `cfg_exitmode`: that column is the two EXIT dropdowns, and this is an ENTRY filter. The Python side was ported in the same pass (`strategies/python/mpc_sos_fade/CLAUDE.md` → `### The minimum-stop guard`), including block reason **code 7**, which the parent already emitted and nothing downstream could see. ⚠ **The filter is still unproven ON against a real export** — every green in this file was taken at the `"Off"` default, where the gate is inert and both sides are byte-identical to their previous build. Re-paste and re-export before trusting a run made with it on. ⚠ `mpc_b_leg_strategy.pine` still has no min-stop input at all (deliberate — a B leg's stop is its band ORIGIN, a full band from the entry, so the hazard is structurally absent); its Python fork pins the mode `"Off"` to keep that honest. Earlier: 2026-07-29 — **`aplusWindow`'s `maxval` raised 4320 → 20160 (14 days) in the A+ pair only** (`mpc_strategy.pine`, `mpc_strategy_export.pine`). The bug it fixes is worth knowing because the pattern can recur on any input: **the old ceiling EQUALLED the default**, so the field could only ever be lowered, and TradingView silently CLAMPS a typed value to `maxval` as you type — entering 4800 left the box showing a truncated number with no error, which reads as a broken input rather than a cap. Default is unchanged at 4320, so **no backtest and no parity run moves**, and the Python side (`aplus_window`) never had a cap so nothing there needed changing. **The export was raised in lockstep** — it must be able to carry any value the parent can produce, or a parity export taken at a longer window would silently be clamped to a different strategy. ⚠ `mpc_b_leg_strategy.pine` + its export and `mpc_bos_strategy.pine` / `mpc_m15_playbook.pine` still cap at 4320 (same default-equals-ceiling trap); raise them the same way if that window is ever swept there. Earlier the same day: **both strategy pairs re-validated GREEN, and both parents compile in TradingView.** `mpc_strategy.pine` and `mpc_b_leg_strategy.pine` were pasted in and compiled clean (the CE10117 token-cap worry did not materialise — no tooltip trimming needed). Fresh exports off `mpc_strategy_export.pine` (21,494 bars) and `mpc_b_leg_strategy_export.pine` (21,493 bars), both 2025-08-31 → 2026-07-29: `compare_strategy.py --warmup 100` → exit 0, `compare_bleg.py --warmup 100` → exit 0, and both hold at warmup 200/500/1000/2000. The A+ export carried `cfg_tp1_pct = cfg_tp2_pct = 0`, `cfg_exitmode = 20` (the 3-way trail digit decoding as the ratchet) and `cfg_trail_pct = 1` — i.e. the ratchet plumbing is proven through the export, not just present in it. **Every "STALE" warning below is CLEARED.** ⚠ **The one drift that survived that pass** — `mpc_strategy_export.pine` lacking `execMinStopMode`/`execMinStopVal` — **was closed 2026-07-30** (see the entry above). Those green runs were taken at the `"Off"` default where the gate is inert, so they still describe the current build exactly, and they still say nothing about the filter itself. Earlier: 2026-07-28 — **the swing ratchet landed in the A+ pair FIRST** (`mpc_strategy.pine` + `_export`), which is what the B-LEG entry below then caught up to: `execRunnerTrail` gained `"Structure + % ratchet"` and **now defaults to it**, with `f_swingRatchet()` and the `execTrailPct` child input (1.0%). It fixes the runner's give-back — the plain structure trail parks the stop at a LAGGING swing, so a strong leg hands back the gap between that swing and the high (measured 57% on the trades that ran ≥$10 of gold); the ratchet climbs one %-of-price step per step of favourable move and is never LOOSER than the plain trail, only equal or tighter. Export side: `cfg_exitmode`'s tens digit went 2-way → **3-way** and `cfg_trail_pct` was added — without both, the comparator would diff a ratcheted Pine against a non-ratcheted Python and report pure drift as a bug. ⚠ **The A+ export is now STALE: the 2026-07-27 GREEN parity run predates the ratchet, so it validates nothing about this build.** Re-run `compare_strategy.py` on a fresh export before trusting any A+ number from it — and run it at `execTp1Pct = execTp2Pct = 0` (the shipped rungs), because the 109.3R figure quoted for the ratchet was measured at 1%/1%; the true 0/0 baseline is **110.65R**. ⚠ **Pre-existing drift, NOT introduced by the ratchet:** `mpc_strategy_export.pine` lacks `execMinStopMode`/`execMinStopVal`, which the parent has. Inert at the `"Off"` default (the floor is 0.0, so the gate is always true) so parity holds today — but the moment minimum-stop-distance is switched on, the export stops describing the strategy and any parity result from it is meaningless. Close it before using that filter. Extension-fib take-profits on top of the ratchet were measured and REJECTED the same day; the full record is in `strategies/python/mpc_sos_fade/CLAUDE.md` → `### The swing ratchet`, and the short version is that 11 trades past the −0.618 extension carry 106R of the 109R, so any fixed ceiling caps exactly what pays. Earlier the same day — **the B-LEG pair now runs the SAME exit ladder as the A+ pair** (`mpc_b_leg_strategy.pine` + `_export`). Three changes, all ported line-for-line from `mpc_strategy.pine`: (1) `execTp1Pct`/`execTp2Pct` defaulted **30/40 → 0/0** — bank nothing, ride the whole position to the runner; (2) the **`qty_percent = 0` guard** — `strategy.exit()` reads 0 as "unspecified" and closes the WHOLE position at that limit, so a 0 rung is now SKIPPED rather than placed. That is why typing 0 previously blew the trade out at TP1 instead of banking nothing, and it is a real hazard, not a cosmetic default; (3) `execRunnerTrail` gained the third option **"Structure + % ratchet"** and now DEFAULTS to it, with `f_swingRatchet()` and the new `execTrailPct` child input (1.0%, greyed unless that method is selected). ⚠ **All three MOVE B-LEG results** — the rungs, the 0-guard and the trail default each change what a runner banks; nothing here is cosmetic. ⚠ **The 43% → 53% run-capture measurement behind the ratchet default was taken on the A+ file's own trades, NEVER on B legs** — it is inherited so the two forks share ONE ladder, not because it is a proven B-LEG result; sweep it before treating it as tuned. Export side: `cfg_exitmode`'s tens digit went from a 2-way to the A+'s **3-way** code (it used to collapse everything non-fixed to 1, which would have decoded the ratchet as the plain structure trail), and `cfg_trail_pct` was added. Python side, same commit: `mpc_bleg/config.py` DROPPED its `exec_runner_trail` pin (it existed only because this Pine lagged the parent), and `mpc_bleg.meta.json` gained the third choice + the `exec_trail_pct` row. The B-LEG exec-input gap vs A+ is now **three** levers, not four (`execSlLevel`, `execMinStopMode`, `execMinStopVal`). 98 Python tests green. **Not yet re-validated against a fresh export — `compare_bleg.py` must be re-run before any B-LEG number from this build is trusted.** Earlier the same day: **every Strategy Execution input in all FOUR strategy Pine files now lives in ONE consolidated block near the top of the file** (`mpc_strategy`, `mpc_strategy_export`, `mpc_b_leg_strategy`, `mpc_b_leg_strategy_export` — search `STRATEGY EXECUTION INPUTS`). All four carry the SAME eight sections in the SAME order; the B-LEG pair simply has fewer levers (no `execSlLevel`, no `execMinStopMode`/`execMinStopVal` — `execTrailPct` was in this list until the exit-ladder port later the same day), so its block is the A+ block minus those three. Ordered the way a trade happens (what trades → what arms it → where the limit rests → what can refuse it → size and stop → targets → runner → drawing), with each dependent input prefixed `↳` and carrying `active = <its parent>` so it greys out when irrelevant. **The block had to MOVE, not just be reordered:** panel order is declaration order, and two inputs (`execConfSZ`, `bLegMaxDays`) are read by engine code ~3,000 lines above the old block, so Pine forced them to be declared early — which stranded them at the TOP of the Execution panel, above "Trade Longs". **NO logic changed** — same inputs, same defaults, same reads; only declaration order, label text and `active =` gates. ⚠ **Reordering inputs resets saved TradingView settings** (TV maps them by position), so re-paste and click "Reset settings to defaults" once — cheap now that the defaults equal what Aaron trades. Three traps found while doing it, all now documented in the block's own header comment: (1) `execTrailStep` has TWO masters — `Fixed step` mode AND the `One trail step behind` TP2 floor — so it is deliberately NOT greyed by the trail method; (2) the three FVG entry rules still price an entry with `execReqFVG` OFF (that toggle only ADDS a 0.618 fib fallback), so they are siblings, not children; (3) `execMinStopMode` is an ENTRY filter and has nothing to do with the runner trail — the two never interact. **Standing rule: a new execution input goes in that block, in its section, with `active =` if anything can make it irrelevant.** `active` needs a pure INPUT bool, so never reassign one of these with `:=`. Earlier: 2026-07-27 — `execSlLevel` defaulted **"1.0" → "0.886"** in both A+ Pine files (`mpc_strategy`, `mpc_strategy_export`) to match `config.py` and what Aaron trades; the B-LEG pair deliberately keeps "1.0" (its Python fork pins the same). This MOVES the stop, so it changes every A+ trade's size and R — it is not cosmetic. Parity is unaffected: the export emits the level in `cfg_strcodes` and `compare_strategy.py` configures Python from that, so the harness never reads either side's default. Earlier the same day: `execRiskPct`'s `maxval` raised **10 → 100** in all four strategy Pine files (`mpc_strategy`, `mpc_strategy_export`, `mpc_b_leg_strategy`, `mpc_b_leg_strategy_export`); default stays 10, sizing math untouched, so no backtest moves. The old 10 was a UI cap only — the Python `exec_risk_pct` never had one. Note the `margin_long/short = 0.2` pin (500x) still bounds notional at 5x equity, so a high risk % on a tight stop can be rejected or partially filled by the tester with no error. Earlier the same day: `execTp1Pct`/`execTp2Pct` defaulted 30/40 → **0/0** in both A+ Pine files, with the `qty_percent = 0` guard that makes 0 mean "bank nothing" instead of "bank everything"; parity re-validated GREEN on a 21,320-bar export at SL 0.886 + 0/0 (see the 2026-07-27 entry). Earlier: 2026-07-26 — the new exit levers (structure runner trail, TP2 stop floor, SL fib dropdown, `execAplus`) ported into `mpc_b_leg_strategy.pine`, and `mpc_strategy_export.pine` given a column for every trade-affecting input (see the second 2026-07-26 entry). Earlier the same day: orphaned-SVP compile fix in `mpc_strategy.pine` + the export regenerated off it. Earlier: 2026-07-12 — the whole structure chain was re-synced to the `choch_lock` removal in `mpc_assistant.pine` and re-validated at 100% Pine parity (see the "2026-07-12 structure re-sync" note below), and the A+ divergence retro-link landed in both A+-carrying files (see the note after it).

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

| annotation | A+ | B-LEG | BOS | D | H4 |
|---|---|---|---|---|---|
| position box / result bands | ✅ | ✅ | ✅ | ✅ | ✅ |
| entry callout, recoloured on close | ✅ | ✅ | ✅ | ✅ | ✅ |
| **entry triangles** | ✅ | ✅ | ✅ | ✅ **new** | ✅ |
| **blocked-setup tag (pink)** | ✅ | ✅ | ✅ | ✅ | ✅ **new** |
| missed-setup callout (2-of-3) | ✅ | ✅ | ❌ | ❌ | ❌ |

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
runs. **That is what `indicators/PINE_INPUT_DEFAULTS.md` is for**: it snapshots every
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

⚠ **The check is cheap and none of the five files was run through it.** For each `active =`, every
identifier in it must be declared at a lower line number than the input carrying it — a ten-line
script over `indicators/*.pine`. Run it after any panel edit; it found the export twin here, which
nobody would have pasted until much later.

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

## Key paths & entry points

- `indicators/smc_engine_v2.pine` — the current pullback-only rewrite (v6 Pine Script), overlay indicator named "SMC Engine"
- `indicators/STRUCTURE_OS_BUILD.md` — cross-session handoff doc: architecture, design decisions, validation findings, build-stage status. Read this first when resuming work.
- `docs/market_structure_engine_spec.md` — the source-of-truth rules spec, written from the TradingView overview page. `STRUCTURE_OS_BUILD.md` treats this as priority-1 source of truth.
- `indicators/mpc_assistant.pine` — a full-featured SMC indicator (structure + order blocks + sessions + kill zones + VWAP + liquidity levels + fibonacci + SVP) that Aaron sourced separately. Its market-structure logic is pivot-seeded (`ta.pivothigh`/`ta.pivotlow`) rather than pullback-only, which breaks the rule below — but it matches the original "Structure OS" indicator at ~99.99% parity. Treat it as read-only reference; don't merge its approach into `smc_engine_v2.pine`.
- `indicators/structure_engine.pine` — a straight extraction of *only* the market-structure logic (external ASH/ASL/BOS/CHoCH/HH/HL/LH/LL + internal iSH/iSL/iBOS/iSOS) from `mpc_assistant.pine`, with every other feature (OBs, sessions, kill zones, VWAP, liquidity, fibo, SVP) stripped out. Same pivot-seeded approach as `mpc_assistant.pine`, so same exception to the no-pivot rule below. Chart-validated by Aaron; now ported to Python as the canonical `engines/market_structure/` subsystem (imported by `algos/` bots). **Re-synced 2026-07-11 so its drawing/visibility layer is byte-for-byte identical to `mpc_assistant.pine`'s structure block** — same "Market Structure" input group (Structure Label Size, Show External / Internal / Historic-Internal Structure, Show Swing Point Labels), same `f_swingCol`/`f_structSize` gating, same historic-internal wiping, so every label and line overlaps the MPC assistant exactly. The re-sync touched only drawing/visibility — the state machine is unchanged, so `engines/market_structure/` and `structure_engine_export.pine`'s plot columns are unaffected and need no re-validation.
- `indicators/fib_export.pine` — instrumented build for the FIB parity check: the external **and internal** structure engine (copied from `structure_engine_export.pine`, plus the mpc capture lines the fibs need — `i_confirmed_*` and the `iFib_*` seed anchors) + the Structure, Sniper, Macro AND Internal fib blocks lifted from `mpc_assistant.pine` (compute + state machines; drawing removed) + `px_fib_*`, `px_sniper_*`, `px_macro_*` and `px_ifib_*` `plot()` columns. Used to export a CSV that `engines/fibonacci/tools/compare_fib.py` diffs Python-vs-real-Pine. **Re-synced 2026-07-09** (TP3 reset-latch dropped + extend-changed guard added on Structure+Internal, Macro first-bar seed) and re-validated at 100% on a fresh `VANTAGE_XAUUSD, 5m` export (13,759 bars, `--warmup 3154`, exit 0 — Structure+Sniper+Macro+Internal). Do not let any part drift from its source (`structure_engine.pine` / `mpc_assistant.pine`).
- `indicators/structure_engine_export.pine` — instrumented copy of `structure_engine.pine` (logic byte-for-byte identical; adds `plot()` output columns, including the eight break-leg columns `px_bull_bos_high/low` + `px_bull_bos_h_ago/l_ago` and bear mirror added 2026-07-02). Used only to export a CSV from TradingView for the Python↔Pine parity check in `engines/market_structure/tools/compare_tradingview.py`. That check passes at 100% on the `OANDA_XAUUSD, 15m` export (21,729 bars, exit 0) and was re-confirmed on a fresh `VANTAGE_XAUUSD, 15m` export (9,721 bars, `--warmup 227`, exit 0) after the break-leg columns were added. Do not trade off it or let its logic drift from `structure_engine.pine`.
- `indicators/ob_export.pine` — instrumented build for the ORDER-BLOCK parity check. **REBUILT 2026-07-31 (1148 → ~300 lines): it no longer embeds the structure engine at all.** Every order block used to be born on a BOS/SOS/iBOS/iSOS, so this file had to carry a byte-for-byte copy of the structure engine and be re-synced whenever that changed — its single biggest maintenance trap (it silently went stale twice). The mpc rework commented out all four structure creation sites, so blocks now come from `ta.pivot(2,2)` TURNS alone and the structure engine is simply gone from here. Invisible boxes are KEPT (`color(na)`) because `extendOBs` reads `box.get_left` for its age check, which is what lets the port stay byte-identical instead of paraphrased. Carries nine `cfg_ob_*` columns so `compare_ob.py` configures the Python engine FROM the export, plus 10 array slots per side. **Pine-parity GREEN 2026-07-31** (21,691-bar 15m export, `--warmup 798`, exit 0; and 13,186-bar 5m, `--warmup 326`). ⚠ **It did not compile on the first paste** — `CE10088: cannot modify global variable in function`. Pine lets a function READ a global but never WRITE one, and the export-only counters were being incremented inside `extendOBs` AND `f_obAdd`. `extendOBs` now RETURNS its mitigation count and the creation counters are bumped at `f_obAdd`'s call sites. **Remember this shape for any future harness: per-bar instrumentation counters cannot live inside a Pine function.**
- `indicators/candle_sticks.pine` — **a THIRD-PARTY indicator, added 2026-08-08** ("Candlestick Patterns Identified, update 1-17-26", © repo32, MPL-2.0, v6). Fifteen classic candlestick patterns as fifteen flat boolean expressions plus their `plotshape` calls and `alertcondition`s — no state machine, no arrays, nothing carried bar to bar except the history each rule reads back through. It is the SOURCE OF TRUTH for `engines/candlesticks/`; if a rule looks wrong, the fix goes here and flows to the port, never the other way. ⚠ **Treat it as read-only unless Aaron says otherwise** — it is somebody else's file, and the one defect found in it (an unbounded `trend` input feeding the history offset `open[trend]`, which throws at RUNTIME on a large value) is recorded rather than patched. ⚠ **Ten of the fifteen rules carry a trend-context gate (`open[trend] < open` / `> open`) and HAMMER, INVERTED HAMMER and DOJI carry none at all**, which is why the port emits those three as direction-NEUTRAL and why they fire on ~9% of every bar. Do not "improve" that in the port.
- `indicators/candle_sticks_export.pine` — the parity harness for `engines/candlesticks/`. **An INSTRUMENTED COPY OF THE RULES ONLY, with all drawing removed** (no `plotshape`, no `alertcondition`, no colour inputs) — the same shape as `fvg_export.pine` / `ob_export.pine` / every other harness here — carrying the parent's two real inputs, its sixteen logic lines byte-identical, and 18 `plot()` columns: one 0/1 flag per pattern, `px_lower` as the single `bullBelt` diagnostic, and `cfg_trend` / `cfg_doji_size` so `engines/candlesticks/tools/compare_candles.py` configures the Python FROM the file rather than from a guess. 🔴 **IT TOOK THREE ATTEMPTS: TradingView refused the first two with `RE10140`, an UNDOCUMENTED runtime error** raised with a clean compile and **no calculation spinner** — i.e. at INITIALIZATION, before a bar was processed. Attempt 1 was the parent verbatim plus two deviations of mine on line 11 (`overlay = false`, `max_bars_back = 500`); both were removed and **attempt 2, a title-only diff, still failed**, which is what ruled the deviations out as the whole story. What was left is the one way this file differed from every sibling harness: **`plotshape` 15 / `alertcondition` 15 against 0 / 0 everywhere else** — it was the only export that DREW, on a chart already carrying fifteen scripts. `fvg_export.pine` runs **40** plot columns on that same chart, so the column count was never it. ⚠ **THE VERIFICATION CONTRACT CHANGED WITH IT and the old one would now pass vacuously**: this is not a byte copy, so `diff` against the parent proves nothing. Run this after ANY edit to either file — it must print nothing: `R='^(doji|bearHarami|bullHarami|bearEng|bullEng|piercing|lower|bullBelt|bullKick|bearKick|hangingMan|eveningStar|morningStar|shootingStar|hammer|invHammer) ='` then `diff <(grep -E "$R" candle_sticks_export.pine) <(grep -E "$R" candle_sticks.pine)`. ✅ **COMPILED, LOADED AND EXPORTED FROM 2026-08-08** — attempt 3 runs clean, and `compare_candles.py` is **exit 0** on its 20,138-bar CSV (`engines/candlesticks/exports/VANTAGE_XAUUSD, 15_ce5c6.csv`) at warmups 0 / 100 / 500 / 2000, with 14 of the 15 patterns fired. **So the drawing really was the problem** — the file is otherwise unchanged in every rule.
- `indicators/mpc_strategy.pine` — Aaron's brother's "MPC-JARVIS" backtest script: the same engine as `mpc_assistant.pine`, converted from `indicator()` to `strategy()` and given an execution layer at the end (A+ sequence entries, fib TP ladder, %-risk sizing). Its `process()` state machine is byte-identical to `mpc_assistant.pine`'s — verified by diff, keep it that way. **Sync direction reversed 2026-07-21: the REPO is now the source of truth** — Aaron pastes this file up to TradingView and his brother picks it up, so repo-side edits stick. (It used to flow the other way, which is why older notes warn about TradingView edits silently reverting fixes.) There is no local Pine compiler: validation is pasting into TradingView, checking it compiles, and confirming the Strategy Tester numbers are unchanged.
- `indicators/mpc_d_strategy.pine` — **the D strategy ("D as in dog, the dirty one", Aaron 2026-08-06).** A standalone `strategy()`, NOT a fork of `mpc_strategy.pine`: it embeds `structure_engine.pine`'s external block byte-for-byte (lines 27-591, minus the two internal-structure inputs) and adds one state machine plus an execution layer on top. Trades the sequence *mature trend → counter-trend SOS (the shakeout) → with-trend SOS (the entry)*, with %-of-equity sizing, a TP1/TP2/runner ladder and breakeven-at-TP1; also draws the levels and shades the shakeout. Spec, worked examples and the open questions: `docs/MPC_D_STRATEGY_SPEC.md`. ⚠ **It shipped as an `indicator()` first and had to be converted** — an indicator has no Properties tab and no Strategy Tester, so it could not be scored at all. **The file NAME said `strategy` the whole time; the name is not the declaration.** **COMPILES and has been RUN** (Aaron, 2026-08-06, XAUUSD 5m, ~11.5 months). Still no Python port and no parity harness. ⚠ **The DEFAULTS were changed 2026-08-06 to the configuration that measurement run actually used** — `initial_capital` 10,000 → **100,000**, `execRiskPct` 1.0 → **10**, `execTp1Pct` 50 → **30**, `execTp2Pct` 25 → **30**, `execTimeStopMode` "Off" → **"Before TP1 only"** (36h). Reason: the shipped defaults described a run nobody had made, so a fresh paste could not reproduce the only numbers this strategy has. **The time-stop mode was DEDUCED, not asked for** — trade 33 sat open 7 days uncut with a peak of 1.71R, and trade 36 ran 37 hours, both past TP1, which only "Before TP1 only" allows. ⚠ **Values only — no input was added, removed or reordered**, so TradingView's saved-settings keying is untouched and no existing chart resets. ⚠ **The baseline therefore MOVED: 37 positions / +8.31R / PF 1.69 / 56.8% win / max DD 3.53R over 2025-08-11 → 2026-07-29** — pin the old values to reproduce anything from before. 🔴 **`execRiskPct` was then dropped 10 → 1.0 the same day, because 10 BUSTS THE ACCOUNT on real history.** The first full-history run (2020-01-01 → 2026-08-05, 5m) died with `Invalid qty value (-0.1) in the strategy.entry() call` — **that is not a compile error, it is equity going NEGATIVE**, and `qty = equity × risk% ÷ dist` goes negative with it. ⚠ **A non-positive qty does not skip the order, it ABORTS THE SCRIPT** — so the Strategy Tester showed no report at all and the blow-up that caused it was invisible; the only symptom was a banner about qty. Now reported as **block code 8**, first in the precedence chain, plus a `q > 0` guard at the entry, so the run completes and the run of 8s marks the exact bar it died. **The mechanism is the min-stop floor meeting old prices: 0.08% is $3.20 at $4,000 gold but $1.20 at 2020 gold, so `100,000 × 0.10 ÷ 1.20` = 8,333 oz = $12.5M notional on a $100k account, which margin 0.2% permits — one weekend gap ends it.** ⚠ **R is scale-free, so a MEASUREMENT run at 1% gives identical R, drawdown-in-R and profit factor while surviving to the end. Size the account after you know the R distribution, never before.** **The standing lesson: a sizing rule that divides by a distance has no floor of its own — the floor has to come from the distance, and a %-of-price floor silently loosens as you walk backwards through history.** 🔴 **THE SAME RUN THEN EXPOSED A WORSE ONE — THE STRATEGY FROZE DEAD ON 2020-05-07 AND STAYED FROZEN FOR THE REMAINING SIX YEARS OF AN EIGHT-YEAR BACKTEST.** The trade list's last row is a long opened 2020-05-07 12:30 and still `Open` at 2026-08-06 — **147,518 bars**, and the run's headline +81% was that one position's unrealised profit. **The cause is BLOCK ORDER.** The CLOSE block sat at the very bottom of the file, after the setup block. On a **same-bar flip** — a position closing and the next sequence firing on the SAME bar — `if dFired` set the new trade up first (`tDir := 1`, entry placed), and then the CLOSE block, correctly seeing `position_size == 0`, scored the old trade and finished with **`tDir := 0`**, wiping the direction of a trade that had just been placed. From the next bar the FILL block and the entire exit block are both gated on `tDir != 0`, **so neither ever ran again**: the position sat open with no stop, no targets and no time stop, `bBusy` was permanently true, and every later setup was refused with code 7. ✅ **Fixed by moving the CLOSE block ABOVE `if dFired`**, which is also required for a second reason — `if dFired` overwrites `tRiskUsd` and `tNpAt`, the exact values the R grade divides by, so running after it scored the closing trade against the NEW trade's risk. ⚠ **It fired ONCE in eight years.** Exactly one same-bar flip in the entire history, and that single occurrence cost 6 of the 8 years. **The standing lesson is about probability and blast radius: a path taken on 1 bar in 200,000 is still a path, and the relative ORDER of two blocks that both touch one state machine is not a detail.** ⚠ **And note how it was caught — not by reading the code, not by a compile error, not by the Strategy Tester (which reported a healthy +81%), but by one row in a trade list saying a position had been open for six years.** The suite here has no way to catch this; the export's `px_blk` run-of-7s would have shown it too. **Read the tail of the trade list before you read anything else.**
- `indicators/mpc_d_strategy_export.pine` — **the D strategy's decision-stream twin (2026-08-06).** `mpc_d_strategy.pine` + one appended block, body byte-identical apart from line 60's title; 48 transparent `plot()` columns. Regenerate with `cp` + the line-60 `sed` + re-append, never by hand-patching. **It exists because the Strategy Tester's trade list records FILLS and nothing else** — it cannot say what the gates refused, how far a trade ran before handing the move back, or what a different stop anchor would have priced, and those are the only three questions this strategy is being tuned on. ⚠ **`px_ctr_ext` / `px_rcl_ext` are RECONSTRUCTED, and that is called out in the file**: the parent updates the leg extremes earlier on the same bar and the unconditional shift then destroys them, so the block re-derives the parent's own two-line rule. Everything else at decision time (`dTrendBos` / `dCurBos` / `dSosBar` / `dSosLvl`) is written ONLY by that shift, so its `[1]` value *is* what the gate read — exact. **The reconstruction is kept checkable rather than trusted**: `px_fire_ctr_hi/lo` and `px_fire_sos_lvl` carry the parent's authoritative values on fired bars, and on any fired bar the two must agree. ⚠ **`px_mfe_r` / `px_mae_r` exclude the fill bar**, the same rule as the parent's `tMaxFav` (BUG_exit_fill_price_mismatch) — a resting limit is reached from the wrong side, so the fill bar's extreme is not a move the trade made. ⚠ **`px_stage` is tracked in the export, not read from `tStage`**, because the parent zeroes `tStage` on the close bar and the close bar is exactly where the final stage matters. ⚠ **Every int-in-a-ternary-against-`na` is built as a float LOCAL first** — Pine does not reliably type that shape and it fails at paste time; four columns had to be rewritten this way. ⚠ **Transparent colour, never `display.none`** — TradingView drops `display.none` series from the CSV, the trap every engine export here records. **The payoff to remember: with `px_ctr_ext`, `px_rcl_ext`, `px_sos_lvl` and `px_cand_entry` on every candidate the strategy ever saw, both stop anchors and any retrace level can be re-priced OFFLINE from one export — so one run answers a sweep instead of one configuration.**
- `indicators/mpc_m15_playbook_strategy.pine` — **the five-step session-sweep model from the 2026-08-11 video note, as a `strategy()`** (built 2026-08-11). Direction from `pbDirTf` (15m) structure, location from the previous session's swept high/low, confirmation from a `pbConfTf` (1m) change of character, entry a limit into the nearest untouched `pbPoiTf` (5m) fair value gap, targets the previous day's and previous week's extremes. Its `MTFStruct` engine is byte-identical to `mpc_m15_playbook.pine`'s — keep it that way. **It is NOT a fork of `mpc_strategy.pine`** and shares none of its execution layer. ⚠ **`mpc_m15_playbook.pine` itself is untouched and stays an indicator** — Aaron's brother's dashboard, and the drawing companion to this file. ⚠ **Unvalidated in every sense: not compiled, never run, no measurement, no export twin, no Python port, no `compare_*.py`.** Full spec and the decisions the video does not make: `docs/MPC_M15_PLAYBOOK_SPEC.md`.
- `indicators/mpc_h4_sweep_strategy_export.pine` — **the H4 sweep's decision-stream twin (2026-08-12).** `mpc_h4_sweep_strategy.pine` + one appended block, body byte-identical apart from line 166's title; **43 `plot(` columns** (42 here + the parent's own Trend EMA). Regenerate with `cp` + the line-166 `sed` + re-append, never by hand-patching — the recipe and the count check are in the file's own header. ⚠ **It contradicts the parent's own 2026-08-05 SCOPE paragraph, which says "ONE FILE. No export mirror"** — that was written when this was a one-file question and Aaron asked for the twin on 2026-08-12 so the H4 sweep gets the same treatment as every other strategy here. **There is still NO Python port and NO `compare_h4.py`; this export is the PREREQUISITE for one, not a substitute.** 🔴 **THE PARENT NEEDED A WRITE-ONLY ADDITION AND THAT IS THE REUSABLE PART.** `okMin` / `okTrig` / `emaOk*` are LOCALS inside the two trigger blocks, so the reason a trigger was refused was computed and thrown away on every bar — the export would have had to recompute it, i.e. carry a SECOND implementation of the gate that can disagree with the gate. Four `var`s (`hTrigCode` / `hTrigBar` / `hTrigPx` / `hTrigStop`) are now written at decision time and **read by nothing in the parent**, so the export COPIES the refusal. ⚠ **`px_blk` is 0 for a TAKEN trigger and `na` on a bar with no trigger — filter on `px_seq` bit 8, never on `px_blk > 0`**, or every taken trade vanishes from the count. ⚠ **`px_cand_entry` / `px_cand_stop` are set for a REFUSED trigger exactly as for a taken one**, which is what lets a refusal be re-priced offline rather than merely counted: with `px_cc_line` beside them, one export sweeps `maxTrigPct` and both stop modes instead of describing one configuration. ⚠ **`px_volume` is plotted HERE on purpose** — "TradingView exports volume" is false, the CSV carries it only if the Volume STUDY is on the reader's chart (the 2026-08-07 BOS lesson). ⚠ **`px_mfe_r` / `px_mae_r` EXCLUDE the fill bar**, the same rule as the parent's `tMaxFav` (BUG_exit_fill_price_mismatch) — and on this strategy they are the whole argument, because it ships a runner with no target and the only way to judge the trail is how much of the favourable excursion it handed back. ⚠ **`px_stage` is read STRAIGHT off `tStage`, unlike `mpc_d_strategy_export.pine` which tracks its own copy** — safe only because this parent resets its stage at the next ENTRY rather than on the close bar. Check which shape a parent has before copying that shortcut. 🔴 **THREE INPUTS CANNOT BE EXPORTED AT ALL AND THAT HOLE IS NAMED RATHER THAN PAPERED OVER: `tfLiq`, `tfConf` and `emaTf` are `input.timeframe` STRINGS and `plot()` takes only a number.** A reader must record them by hand alongside the CSV — and they are the part of the configuration that changes what the strategy IS, since an H4/15m run and an H1/5m run are different studies. ⚠ **NOT COMPILED** — no local Pine compiler; verified structurally (one-line diff against the parent, 43 plots, every referenced identifier present in the parent, round-trip byte-identical through `export_regen.py`).
- `indicators/mpc_b_leg_strategy.pine` — a FORK of `mpc_strategy.pine` that trades ONLY the B LEG (the SOS whose retrace arrived late), split out 2026-07-24 to run PARALLEL to the A+ bot. The ONLY logic change vs the parent is the execution layer: the two A+ `strategy.entry` blocks are replaced with cancel-only stand-down (`longArmed`/`shortArmed` are still computed so the "A+ has priority" gate on the B leg is preserved), and the B LEG is the sole entry type. The whole engine + A+ sequence tracker above the execution block stays byte-identical to `mpc_strategy.pine` — do not let it drift. **Leaned out 2026-07-24** (4871 → 4573 lines): the code that went dead when A+ entries were disabled (`f_conf`, `f_slAnchor`, the `execSlLevel` input, `longDeep`/`shortDeep`, `longEdgeSz`/`shortEdgeSz`) plus three self-contained cosmetic subsystems the B leg never reads and that default OFF (VWAP, Session Volume Profile/MV, Order Blocks) were removed. Python port lives in `strategies/python/mpc_bleg/` (its own CLAUDE.md). Same no-local-compiler rule: validate by pasting into TradingView. **No Pine↔Python parity harness yet** — a `mpc_b_leg_strategy_export.pine` + `compare_bleg.py` are the follow-up.

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
⚠ **The two families need DIFFERENT terms and this is not cosmetic.** `mpc_assistant.pine` and
`mpc_m15_playbook.pine` hide a mitigated label only when `showMitLiq` is off, so their test is
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
before and it's gone." **`showMitLiq` false → TRUE in `mpc_assistant.pine`.** It had been the
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
⚠ **`mpc_m15_playbook.pine` still has the real INPUT** (default off) and was left alone — it is a
control, not a lock, so it can just be ticked.

---

**All three changes applied to all eight files that carry the block** (the `showMitLiq` flip is the
indicator only), identical text:
`mpc_strategy.pine`,
`mpc_b_leg_strategy.pine`, `mpc_bos_strategy.pine`, their three exports, `mpc_assistant.pine` and
`mpc_m15_playbook.pine`. ✅ **The three export mirrors were re-diffed after the edit and still
differ from their parents by exactly the `strategy()` title line plus their appended parity block.**
⚠ **NOT COMPILED** — no local Pine compiler, and these files have hit CE10117 twice; the change adds
three locals and six two-branch `if`s inside an existing function, so **zero new main-body
statements** (CE10295 unaffected) but not zero tokens. ⚠ **No input was added, renamed or reordered,
so no "Reset settings to defaults" is needed.**

---

## 2026-08-07 — 🟢 `mpc_bos_strategy.pine` COMPILES, AND ITS DEFAULTS MOVED OFF THE SPEC BECAUSE THE FVG ENTRY IS THE LOSING HALF

Aaron pasted the file, it compiled (the `CE10117` risk from putting VWAP back did not materialise),
and he asked for the parameters to be optimized into something profitable. **That exact request had
already been run and failed** — `strategies/python/mpc_bos/` swept **82 configurations on 2026-07-31
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
the gross one picks the configuration you cannot trade. It is also the collapsing-stop hazard the A+
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

Full record, grid and caveats: `docs/MPC_BOS_OPTIMIZATION.md` → Run 5. ⚠ **`docs/MPC_BOS_SPEC.md`
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

Aaron asked which combination of the two continuation strategies to pursue — `mpc_bos_strategy.pine`
(fibs + FVG) or `mpc_d_strategy.pine` (structure + fake shift + VWAP) — and asked for diagnostics
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

**What was then built:** `bosVwapReq` (F10) in `mpc_bos_strategy.pine` — a pro-trend-side gate,
default ON, ANDed into `longArmed`/`shortArmed`, with block code 7 so a refusal shows on the pink
Blocked tag and in the diag log. Full write-up in `docs/MPC_BOS_SPEC.md` §4b.

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

⚠ **F10, not F9 — and the collision was nearly shipped.** `docs/MPC_BOS_SPEC.md` §4 already used F9
for staleness (`bosMaxDays`), while the Pine's inline comments only went up to F8, so "F9" looked
free from inside the file. Caught by reading the spec's table rather than the code's comments. **A
gate's number is a shared label across two documents; free in one is not free.**

⚠ **VWAP had been REMOVED from this file 2026-07-25 under `CE10117` (101,484 > 100,256 tokens)**, and
what came back is deliberately only the VALUE plus one `plot()` — not the settings block, colours and
styles that were cut. The old VWAP spent tokens DRAWING something nothing read; this one is read by
the arming condition. **If CE10117 returns, delete the `plot()` first and the gate last.**

⚠ **NO SLOPE TEST.** `mpc_d_strategy.pine` carries `execVwapSlope`/`execVwapSlopeBars`; only the SIDE
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

## 2026-08-06 — `mpc_d_strategy.pine`, and why "an SOS then an opposite SOS" is not a signal

Aaron specified a new setup from four hand-marked charts (two long, two short) and named it the
**D strategy** — "D as in dog, the dirty one". The sequence: a MATURE trend, then a counter-trend
SOS that shakes it out, then a with-trend SOS that resumes it. The third SOS is the entry; the
stop sits beyond the extreme the shakeout reached. Full spec + the four worked examples:
`docs/MPC_D_STRATEGY_SPEC.md`.

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
— the same problem A+ solves by resting a limit on the retrace instead of buying the break. A
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
the only reason it exists. ⚠ **The file was named `mpc_d_strategy.pine` throughout: the name is
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

**RESTYLED TO `mpc_strategy.pine`'s CONVENTIONS the same day** (Aaron: *"follow the mpc strategy
styling for all inputs and debugging annotations and take profits too"*). Same five input groups
— `D Setup` for the sequence gates (as A+ uses `A+ Setup`), `Strategy Execution` for everything
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
is the interesting one: `mpc_strategy.pine` re-issues every exit rung unguarded on every bar,
which is safe THERE only because it ships both rungs at 0% — the rung is then skipped entirely
and the bug is unreachable at its defaults.** Calling `strategy.exit` with an id whose order
already FILLED places a NEW order rather than modifying it, so a re-issued TP1 banks another
slice of the remainder every bar. This file ships a real 50/25 scale-out, so it guards. ⚠ The
generalisation is worth more than the fix: **a latent bug held off by a DEFAULT is not fixed, and
copying the code without copying the default is how it gets discovered.** ⚠ `execTp1Pct`/
`execTp2Pct` are 50/25 here rather than mpc's 0/0 — riding the whole position to the runner
tested best on the A+ bot over 6.6 years, which is a fact about THAT strategy, so it is stated in
the tooltip rather than copied as a default. ✅ **`execMinStopMode` is now present and ON at
`% of price` 0.08**, which the first build did not have at all: three of the four stop anchors
can land arbitrarily close to the entry, and `qty = risk / dist` is what detonated A+ Run 4 and
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
NOT MEASURED.** Full write-up: `docs/MPC_D_STRATEGY_SPEC.md` → *The VWAP entry*.

### 2026-08-06 (later still) — the sweep was already there, and a chart said the EXIT is the problem

🔴 **THE COUNTER-SOS *IS* THE LIQUIDITY SWEEP, AND SETTLING THAT DELETED A 500-LINE FEATURE
BEFORE IT WAS WRITTEN.** Aaron describes D as *"a liquidity sweep and a fake break of
structure"*, and the near-miss was reading that as two conditions: a liquidity-pool port
(previous day/week high-low, H4, session high-low, EQH/EQL) lifted out of `mpc_strategy.pine`
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
run" is an EXIT change, not an entry one, and it is the answer A+ already reached** — that bot
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
**$3.20 on $4,000 gold, measured on A+ and never here.** Check for any trade whose 1R is under
about $5; the fix would be a minimum shakeout length, not a bigger floor.

### 2026-08-06 (later still) — the JARVIS REV row stuck on TAKE PROFIT after a 0.5 entry

🔴 **A short entered at 0.5 banked TP3 and the row never cleared — it sat on `TAKE PROFIT SHORT ·
TP3 · close the rest` indefinitely.** `mpc_assistant.pine` only; nothing here reaches a trade.

**Two flags describe one event and only one of them survives a shallow entry.** The A+ leg's
completion death reads the DRAWN FIB's `fibo7Touched`, and that flag is gated — the fib block
checks its three TP levels inside `if fibo618EverReached`. An EARLY 0.5 entry never reaches
0.618, so on that leg `fibo618EverReached` stays false, `fibo7Touched` can NEVER be set, and the
completion death is **unreachable**. The leg then survives until an opposite SOS or a
continuation BOS happens along, which can be hours. Meanwhile the A+ engine's own `aplusX_tp0`
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
see this: the A+ sequence tracker exists only in `mpc_assistant.pine` and `mpc_strategy.pine`. ✅
**Checked rather than assumed — `mpc_strategy.pine` and `mpc_b_leg_strategy.pine` carry ZERO
references to `aplusL_tp0`/`aplusS_tp0` and have no TAKE PROFIT row**: their restored table is the
EXT/INT structure pair only, so the stuck row cannot occur there and neither file was touched.

---

## 2026-07-31 — the harness pass: four exports validated, one file deleted, session windows finally forked back together

**`indicators/mpc_jarvis_v2.pine` DELETED** (Aaron's call). It was a 2,084-line lean `indicator()`
build superseded by `mpc_strategy_export.pine`. Last committed at **`825592a`** — recover from there,
never from memory. All doc references removed in the same pass.

**The session windows were forked and nobody had noticed.** `mpc_strategy.pine` has carried the
DST-aware windows since **2026-07-12** (`317dbef`) — two weeks BEFORE `mpc_assistant.pine` got them
(`b25789d`, 07-26) — but `mpc_b_leg_strategy.pine` and `mpc_b_leg_strategy_export.pine` never did, so
the A+ and B-LEG forks disagreed about when a session opens. That breaks this file's own standing
rule: an engine-block change in the parent flows to the fork line-for-line.

| | old (fixed offset) | new (own city, DST-aware) |
|---|---|---|
| Tokyo  | `2000-0500` GMT-4 | `0900-1800` **Asia/Tokyo** |
| London | `0400-1300` GMT-4 | `0800-1700` **Europe/London** |
| New York | `0900-1800` GMT-4 | `0800-1700` **America/New_York** |

**It is trade-affecting in principle, not cosmetic** — session H/L feed `recentBSL`/`recentSSL`
(`mpc_strategy.pine:3121-3126`), which is what `execArmSweep` arms A+ on, and that toggle is ON in the
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

⚠ **Compile status after that pass, stated exactly.** `mpc_b_leg_strategy_export.pine` and
`svp_export.pine` both compiled — Aaron exported from them, which is stronger evidence than a paste.
`mpc_b_leg_strategy.pine` is body-identical to its export apart from the line-40 title, so it is
covered by construction. **`mpc_m15_playbook.pine` has never been pasted since its windows were
edited, and is deliberately left that way** — Aaron's call, 2026-07-31: it is his BROTHER's work in
progress, not ready and not part of this repo's validated set. Do not raise it as an open validation
item. The changes there were value-only, so if he does compile it and something breaks, it is one of
the six session strings.

Synced in `mpc_b_leg_strategy.pine`, `mpc_b_leg_strategy_export.pine` and `mpc_m15_playbook.pine`
(each file's own `display = display.none` preserved — only the six values changed).
⚠ **`mpc_m15_playbook.pine`'s NY window was `0900-1700`**, unlike every other file's `0900-1800` — a
pre-existing difference of unknown origin, now folded into the common `0800-1700`. Nothing replays
that file, but it is his BROTHER's in-progress file, so if that hour was deliberate it is his to
judge — mention it to him rather than assume the sync was right. `svp_export.pine` was re-stated too, purely for
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
   (`mpc_assistant.pine:410-412`: `0.0` below 900s, `0.04` at 15m+). Exported on 15m the old build
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

## 2026-07-31 — `mpc_bos_strategy.pine` defaults now ENCODE the spec, not the bare baseline

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
frequency comes from stacking A+, B-LEG and this one on one account, never from loosening this one.
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

## 2026-07-29 — the FVG floor is now SPLIT BY TIMEFRAME (A+, its export, and BOS)

**The bug Aaron found.** `mpc_assistant.pine` draws fair value gaps on a 5m chart
that `mpc_strategy.pine` does not. Cause: the assistant's minimum-gap floor is
timeframe-aware and the strategy's was one flat number.

```pine
// mpc_assistant.pine:149-151
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
`mpc_strategy.pine`, `mpc_strategy_export.pine` and `mpc_bos_strategy.pine`:

| | below 15m | 15m and above |
|---|---|---|
| min gap | `fvgThreshLTF`, default **0.0** | `fvgThreshHTF`, default **0.1** |
| middle-bar close test | forced **off** | `fvgReqCloseHTF`, default **on** |

**15m and above is bit-identical to before, deliberately.** The HTF floor stays
0.1 and is NOT set to the assistant's 0.04, and the close test stays on. A+ is
traded on 15m, so its baseline, its 188-trade history and the `mpc_sos_fade`
parity pin (`EngineConfig.fvg_require_close = True`) must not move. Matching the
assistant at 15m too is a one-number change if it is ever wanted — but it is a
different decision, with a re-validation attached, and it was not made here.

**Consequence to carry.** These are new trade-affecting inputs and
`mpc_strategy_export.pine` has no `cfg_*` column for either. At their defaults on
15m that costs parity nothing (behaviour is unchanged), but **a parity run taken
on a sub-15m chart, or with either input tuned, is meaningless until the columns
land here and in `compare_strategy.py`.** Same trap as `execRunnerTrail` in the
2026-07-26 entry: a default that changes behaviour is as dangerous as a new
input, and it hides better.

**NOT applied to `mpc_b_leg_strategy.pine` / `mpc_b_leg_strategy_export.pine`.**
They carry the identical FVG block and are now the only strategy files without
the split. The standing "engine changes flow line-for-line to the fork" rule says
they should get it; it was left out only because the request scoped A+ and BOS.

**Pre-existing drift found while checking this, NOT caused by it.**
`mpc_strategy_export.pine` is missing `execMinStopMode` / `execMinStopVal`
entirely — the min-stop lever landed in the parent (`7603444`) and never reached
the export. That breaks the export's own "the title is the ONLY difference" rule.
A parity run replays the bot with a floor the export cannot describe; harmless
while the mode is "Off" (the default), wrong the moment it is not.

---

## 2026-07-29 — `mpc_bos_strategy.pine`, the third strategy off the shared engine

**New file `indicators/mpc_bos_strategy.pine`** (3875 lines), built to `docs/MPC_BOS_SPEC.md`. It
trades the CONTINUATION: an SOS sets a regime, and every BOS after it in that direction is a fresh
leg whose retrace is bought/sold. A+ fades the shift; this rides what the shift started.

**How it was assembled.** Engine block = **lines 1-3028 of `mpc_strategy.pine`, byte-identical**
(everything through the liquidity `recentSSL`/`recentBSL` block), then the watermark, then a new
execution layer. **Not copied:** the A+ SEQUENCE tracker, the B-LEG tracker, the missed-setup callout
and its `MissW` machinery — nothing here reads them, and the compile-token budget in this family has
already hit CE10117 and CE10295 twice. Net effect vs the parent: ~510 lines of tracker out, ~250 of
execution in. Regenerate with `head -3028 mpc_strategy.pine`, the parent's watermark block, then this
file's execution layer.

**Two default flips vs the A+, both named in the spec:** `execConfSZ` OFF→**ON** (the Sniper Zone is
entry method 3 here) and `execFvg50` OFF→**ON**. Note `execConfSZ` also gates `_snTrack`, and
`_snBullBOS`/`_snBearBOS` sit behind `showFibo` — so **"Show External Fib" is still trade-critical**
in this file even though the fib LEVELS are no longer read off it (see below).

**The levels are computed, not read.** The entry band, stop and targets come from `f_lvl(ext, org, v)`
over the anchor leg's own extreme/origin — identical arithmetic to the engine's `fiboP*`, just
anchored per-setup. `bosFibAnchor` picks the EXPANSION leg (default — `fibo_ash`/`fibo_asl`, the drawn
External fib's own anchors, so the band moves until the pullback confirms) or the frozen BREAK leg
(`bos_high`/`bos_low`). This is what makes the "Break leg" option possible at all; the A+ could only
ever price off the one drawn fib.

**Three deviations from the spec, all flagged in the file header and in the spec's new §10a.** The
important one: **`fibo7Touched` is re-implemented per-anchor.** The engine's latch is keyed to the fib
ORIGIN, which does not change across a run of breaks, so break #1's round trip would have killed
breaks #2 and #3 on their arm bar — every continuation after the first would be untradeable. The Pine
tracks the anchor's own 0.5 tap and its own return to 0.0 instead. The other two: the divergence
CLOSE fires on a confirmed divergence only (not extreme RSI — that is the normal state of a healthy
long, and closing on it flattens the runner on every winner), and `execMinStopMode`/`execMinStopVal`
are carried over from the A+ though §8 does not list them (default Off, so the baseline is unmoved).

**Not yet compiled on TradingView and not yet backtested.** There is no local Pine compiler; the file
is statically checked only (no identifier collisions with the engine block, every referenced engine
symbol present, no duplicate declarations or input titles). **No number in this repo describes this
strategy yet** — §10 steps 2-4 (baseline + the F1→F4→SL-model sweeps, the export Pine +
`compare_bos.py`, the Python port under `strategies/python/mpc_bos/`) are all open.

**Standing rule, same as the B-LEG fork:** any change to the engine block flows in line-for-line from
`mpc_strategy.pine`; any BOS execution change flows to the Python port once it exists.

---

## The 2026-07-12 structure re-sync (`choch_lock` removed from the break decision)

Aaron's brother found a missing higher high on XAUUSD 15m (17 Jun 2026, the ~4382 spike) and had it fixed on TradingView. The fix landed in `mpc_assistant.pine` and was propagated through the entire chain. **Both symptoms were one bug:** a bullish SOS set `choch_lock`, so the next bearish break was not treated as a CHoCH — it printed as a **BOS instead of an SOS**, and since the bear-break fallback classifies the old high with `old_is_hh = is_choch ? true : (…)`, losing the CHoCH also lost the forced `true`, so the **HH never printed**.

Four changes, now byte-identical across all six Pine copies of the engine (`mpc_assistant.pine`, `structure_engine.pine`, `structure_engine_export.pine`, `ob_export.pine`, `fib_export.pine`, `mpc_strategy.pine`):

1. bull break — `is_choch = st.dir == -1` (the `and not st.choch_lock` gate is gone)
2. bear break — `is_choch = st.dir == 1` (same)
3. bull-break SOS — the promoted pullback low prints **ASL**, not HL/LL
4. bear-break SOS — the promoted pullback high prints **ASH**, not HH/LH

…and in both break paths the confirmed-swing map (`last_conf_high` / `last_conf_low`) is now written only `if not is_choch`. On a fast reversal the promoted extreme is only the new ACTIVE swing; the NEXT break in that direction classifies it. That guard is what stops a lower high overwriting a genuine higher high.

`choch_lock` is now **inert** — still declared, set and released, but never read. Leave it alone. It is dead in `mpc_assistant.pine` too, and these files are kept byte-identical to it; deleting it would make the next Pine diff lie.

**Parity re-confirmed 2026-07-12 on ONE combined export.** `ob_export.pine` + `fib_export.pine` were put on a single `VANTAGE_XAUUSD, 5m` chart and exported as one CSV (9,270 bars). `structure_engine_export.pine` was **not needed on the chart** — `ob_export.pine` already carries all 23 of its `px_*` columns (strict superset), and `fib_export.pine` collides with neither, so all three compare tools (which resolve columns by name and ignore extras) ran off that single file: `compare_tradingview.py --warmup 365`, `compare_ob.py --warmup 548`, `compare_fib.py --warmup 368` — all exit 0. Warm-up differs per engine because each needs a different depth of history before it catches up with the state Pine already had at row 0.

---

## The 2026-07-12 A+ divergence retro-link

An RSI divergence pivot only confirms `divPivotLen` (5) bars **after** the extreme it marks. On a fast V-reversal the SOS fires inside that lag, so by the time the divergence arms Stage 1 the SOS is already in the past — and Stage 2 only looks forward. The setup stuck at 1/3 forever, and in `mpc_strategy.pine` that meant a divergence-armed setup could never place a trade.

Fix: remember the last bull/bear SOS bar, and when a divergence arms, adopt an SOS that already fired **at or after** the divergence's pivot bar, provided it is still inside the staleness window. The sequence really did run div → SOS; we just learned about the div late.

This lives ONLY in the two files that carry the A+ sequence — `mpc_assistant.pine` and `mpc_strategy.pine`. The structure engine, the three export builds and every Python engine have no A+ block, so nothing else needed it and no parity harness was affected (no re-run required).

**The two A+ blocks are NOT byte-identical, and that is expected.** Only `process()` is held byte-identical between the two files. `mpc_assistant.pine`'s A+ block has since moved on: its staleness window is measured in **minutes** (`aplusWindow * 60000`), arming is gated behind `aplusL_canArm`, and it has a session-gap detector. `mpc_strategy.pine` is an earlier generation — the window is in **bars** — so the retro-link there compares bar numbers, not timestamps. The strategy also needed a second change: its execution layer snapshots the arm source (`sosL_swp` / `sosL_div`) *on the SOS bar*, which never runs for a retro-linked SOS, so that snapshot is taken at retro-link time instead, measured against the SOS bar. Without it the table would show 2/3 but no trade would fire.

---

## 2026-07-22 — `mpc_strategy.pine` readability pass + compile-budget cuts

The trade annotations were rebuilt so a chart can be read without decoding text, and two features were deleted to get back under Pine's compiled-token cap.

**Removed to buy tokens (CE10117: 100543 > 100256).**
- **Kill Zones & NY Range** — the whole input group, the `security` call, the boxes/plotshapes and the today-deletion logic. Both were cosmetic, default OFF, and read by nothing in the execution layer. They still live in `mpc_assistant.pine` if the drawing is ever wanted back. `nyHour` was KEPT — `lateDayBlock` reads it.
- **`debugMarkNoFvg`'s on-chart labels** — they duplicated the missed-setup callout, which already names FVG as the missing confluence. The COUNTERS (`missedNoFvgL/S`) stay; the diagnostic log still reports every one.

**Trade drawing, rebuilt.** A trade scales out in up to three pieces, so one box can never describe it. On close it now paints as stacked bands, each the slice of price one piece was actually paid for: entry→TP1 fill, TP1→TP2, TP2→runner, in three depths of the SAME green. A faded red band behind them shows how far price went against the trade first. A trade that banked nothing is one red band; one that came back to entry is a lone orange line. Every band comes from `strategy.closedtrades.exit_price()` — the real fill, never a fib level it merely aimed at. TP1/TP2/TP3 tags all anchor at the same x (the trade's right edge + 4) so they stack in one column instead of scattering across the candles.

**Result colours, not direction colours.** Aaron reversed an earlier call: the trade label is GREY while the trade is open (the result is not known yet), then green won / red lost / orange breakeven on close. Direction stays readable via the ▲/▼ arrow, the word LONG/SHORT, and the entry triangle. Breakeven is graded against `execBeBandR`, the same band the diagnostic log uses.

**Two new inputs.** `execLabelWhich` filters which results KEEP their label (All / Wins only / Losses only / Losses + breakevens / None) — the review view is losses + breakevens. `execLabelOff` sets the label's distance from price in ATRs. That second one exists because **Pine has no tooltip-positioning API**: TradingView anchors a tooltip to its label, so pushing the label further out is the only way to stop the tooltip covering the candles. Also note **tooltips exist only on `label`, never on `box`** — a result rectangle can never be hovered, which is why the annotation is a label with a leader line rather than text on the box.

**A regression worth remembering.** Trade labels were briefly gated behind `debugDays` (the missed-setup recency window), which silently deleted every trade label older than 3 days. `debugDays` now applies ONLY to the missed-setup callouts — every real trade always gets its label, however old.

### Pine gotchas this pass exposed

- **`to` cannot be a parameter name.** It is the `for i = 0 to n` keyword. Using it makes the parser reject the whole declaration and blame the FIRST parameter (`CE10156: Syntax error at input "x1"`), which points nowhere near the real cause. `from` is fine on its own but was renamed alongside it.
- **A function's last statement is its return value, and every branch of it must share a type.** `f_posBox`'s closing `if / else if / else` creates a box / a box / a line, which is `CE10235`. Fixed by putting a trailing `int _pbDone = 0` after the chain so the drawing is no longer the return expression — remove that line and the script stops compiling.
- Both of these are the same family as the existing `CE10295` workaround (wrap a big block in a function so the main body pays for one statement).

## 2026-07-23 — `mpc_strategy.pine` Method 3 (deep-fib entry) + prime-combo defaults

**New GRP_EXEC input `execDeepFib`** ("Entry: deep gap enters on nearest fib (not gap edge)"). It fixes a class of missed trades: when a qualifying FVG floats DEEP in the retrace, the limit used to rest at the gap's own edge, so price often stalled at a shallower fib and turned back before the edge was ever tapped. With it on, a gap whose NEAR edge (long = gap top `_gT`, short = gap bottom `_gB`) sits deeper than 0.618 re-prices to the nearest fib just SHALLOWER — 0.618/0.702/0.786 — the level price reaches first. A gap on a fib level, or shallower than 0.618, is unchanged. Logic: helper `f_deepFibEdge()` before the Entry EDGE block, called inside the FVG loop. **ONLY the near edge's position decides it** — an earlier "gap body contains a level" gate was WRONG (it dropped exactly the deep multi-level gaps this targets) and was removed.

**Defaults flipped to Aaron's "prime" combo** — the settings he hard-tests in TradingView, now the shipped defaults across the strategy Pine, the export Pine, and the Python bot: `execArmSweep` OFF→**ON**, `execArmDiv` ON→**OFF** (arm on liquidity sweeps, not divergence), `execFvgDeepOnly` OFF→**ON**, `execDeepFib` (new) → **ON**. `execReqFVG` stays ON. This combo measured ≈+237% / PF 6.2 / 85% win / 13% max DD over ~2 years of gold at 84 trades (Aaron's TradingView Strategy Tester). NOTE: this changes the Strategy Tester baseline — the OLD divergence-armed numbers no longer reproduce without flipping the toggles back.

**Ported to the Python bot the same day** — `strategies/python/mpc_sos_fade/` (config `exec_deep_fib` + the four flipped defaults in `config.py`, `execution._deep_fib_edge()`, export `cfg_bits` bit 8192, `compare_strategy.py` reads it, meta.json panel entry + updated `edge`/`steps`, 4 unit tests). Parity re-run pending a fresh TradingView export.

**Slippage pinned to 0 in the `strategy()` call.** Both `mpc_strategy.pine` and `mpc_strategy_export.pine` now declare `slippage = 0` (the two `tradingview/` research strategies too), so the Strategy Tester Properties tab defaults to zero instead of Aaron's carried-over 25-tick setting. TV slippage is a broker-emulator COST, not signal logic — a flat per-fill charge that is neither honest (a resting limit never slips) nor comparable to the zero-cost Python `fill_model="bar"` run. Real costs go in the lab's tick fill model. The breakeven buffer (`execBeBufTk`, default 30) is a strategy INPUT and is unchanged. This does not touch the decision-stream (`px_*`/`cfg_*`) columns, so `compare_strategy.py` parity is unaffected.

---

## 2026-07-24 — the B-LEG fork + 500x leverage pin

**New file `indicators/mpc_b_leg_strategy.pine`** — the B LEG split out as its own strategy (see the Key-paths entry above for what it is, how it differs from the parent, and the lean-out). Standing rule for it: any change to the parent's engine or A+ block flows in line-for-line; any B-LEG change flows to the Python port in `strategies/python/mpc_bleg/`.

**500x leverage pinned in the `strategy()` call** to match Aaron's demo account. `mpc_strategy.pine`, `mpc_strategy_export.pine` and `mpc_b_leg_strategy.pine` now carry `margin_long = 0.2, margin_short = 0.2` (margin % = 100 / leverage → 500x = 0.2%), and the two `tradingview/` research strategies (`ny_orb.pine`, `london_breakout.pine`) got the same. Like `slippage = 0`, this only sets the Strategy Tester Properties defaults so a fresh paste reproduces Aaron's account — it is not signal logic and does not touch the `px_*`/`cfg_*` decision stream, so `compare_strategy.py` parity is unaffected.

---

## 2026-07-25 — blocked-trade marker (`mpc_strategy.pine` + `mpc_strategy_export.pine`)

A setup refused by one of the strategy's own toggles used to be **invisible everywhere**: no order is
placed, so nothing is drawn, no row reaches the trade list, and the Strategy Tester cannot know it
existed. That made it impossible to judge whether a blocking rule protects the account or costs it.

**New in both A+ files.** A pink `▲/▼ TRADE BLOCKED` label with the reason in its hover tooltip and a
dotted leader down to the price the limit would have rested at. Input `showBlockTag` ("Mark blocked
trades on chart (pink)", group `A+ Debug`, default ON). Cosmetic only — it reads state and places no
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
`mpc_strategy.pine` — **Order Blocks** (input group, `OrderBlock` type, `manageOBs`/`extendOBs`, and
all four creation blocks: external bull/bear + internal bull/bear), **VWAP** (input group,
`ta.vwap(hlc3)`, the `plot`), and the **Session Volume Profile / MV line** (input group + the whole
Asia-POC block). 4935 → 4700 lines.

All three were cosmetic, defaulted OFF, and read by **nothing** in the execution layer — verified by
grep before deleting (zero references to any of them after the `STRATEGY EXECUTION` header, and zero
orphaned identifiers after: `showOBs`, `obBodyOnly`, `maxActiveOB`, `colBull/BearOB`, `showBull/BearOB`,
`manageOBs`, `extendOBs`, `vwapValue`, `vwapColor`, `vwapWidth`, `showVwap`, `hlc3`, `SVP_SESSION`,
`SVP_TZ`, `inSVP`, `svpRows`, `svpHistory`, `svpPOCCol`, `svp_poc*`, `GRP_OB/VWAP/SVP`). The B-LEG
fork dropped the same three on 2026-07-24 for the same reason, so this is precedent, not a new call.
They live on in `mpc_assistant.pine` if the drawing is ever wanted back.

**`process()` is untouched**, so the byte-identical rule still holds and no parity harness is affected.

**`mpc_strategy_export.pine` got the identical cuts** (4778 → 4540 lines) — its pre-cut line numbers
matched the parent's exactly, so the same eight ranges applied verbatim. In the export the three were
doubly pointless: nobody reads its chart, it exists only to emit the columns, and none of the three fed
any of them. **All 25 `px_*` / `cfg_*` / `dbg_*` columns verified present afterward**, including the
new `px_block`, so `compare_strategy.py` is unaffected.

**If CE10117 returns anyway**, trim in this order: shorten the six `f_blkWhy` strings, then drop codes
1 and 2 (a disabled direction or arm source is a setting you already know about, unlike the four that
depend on price).

---

## 2026-07-26 — orphaned-SVP compile fix + `mpc_strategy_export.pine` regenerated

**The compile error.** Aaron's brother edited `mpc_strategy.pine` directly on TradingView and pushed
it. His copy deleted the Session Volume Profile **inputs** (`showSVP`, `svpRows`, `svpHistory`,
`svpPOCCol`, `GRP_SVP`) but left the entire 108-line SVP computation block behind, so the script failed
with `CE10272: Undeclared identifier "showSVP"` at the first line that read one. Removed the orphaned
block (the MV / Asia-POC line; cosmetic, read by nothing in the execution layer). 4668 → 4560 lines.
Order Blocks and VWAP were cut cleanly in his copy — verified by grep, no orphans left.

**Lesson for the next TradingView round-trip:** when a feature is cut on the TV side, grep for its
identifiers before trusting the paste. A deleted input group with its consumer still in place compiles
locally in nobody's head and fails on the first line that reads it. The 2026-07-25 entry above lists
the exact identifier set for all three cosmetic subsystems — use it as the checklist.

**`mpc_strategy_export.pine` regenerated** (4540 → 4610 lines) by its own documented procedure: the
parent's body up to the `DIAGNOSTIC LOG` header, plus the appended `PARITY EXPORT` block, then restore
`strategy("MPC A+ Strategy Export"` on line 29. That title is now the **ONLY** difference from the
parent — verified by `diff` over the shared range, zero other lines. The export had drifted five
trade-affecting changes behind (the whole **B LEG** setup + its three inputs and the `execAplus` term
in `longArmed`; **`execFvg50`**; **`execRunnerTrail` + `execStructTrailBufTk`**, the structure-swing
runner trail that is now the DEFAULT; **`execTp2StopMode`**; and the removed fixed-R:R lever) and still
carried the JARVIS confirmation table the parent dropped 2026-07-24. All 25 `px_*` / `cfg_*` / `dbg_*`
columns verified present afterward.

**Two things deliberately NOT done, both flagged in the export's own header:**
- **`cfg_bits` still packs 14 booleans.** `execAplus`, `execBLeg` and `execFvg50` have no bit, and
  `execRunnerTrail` / `execStructTrailBufTk` / `execTp2StopMode` have no column. At their **defaults**
  this costs parity nothing (`execBLeg` and `execFvg50` are OFF, and the `mpc_sos_fade` Python bot has
  no B leg — that lives in `mpc_bleg`). Tune any of them and the column must be added here AND in
  `compare_strategy.py` before a diff means anything.
- **`execFvgDeepest` (the deepest-gap-on-a-fib entry toggle) is GONE and has to be rebuilt from
  scratch if wanted.** Built repo-side 2026-07-25 across both Pine files, `mpc_sos_fade`
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

Aaron's brother's 2026-07-25 paste added a new **exit** family to `mpc_strategy.pine`. This pass
brought `mpc_b_leg_strategy.pine` and both Python bots up to it, and closed the export hole it left.

**What was new in the parent** (all in `GRP_EXEC`):
- `execRunnerTrail` — "Fixed step" / **"Structure (swing)"**, the DEFAULT. Past TP2 the runner
  trails the structure engine's last confirmed swing (`st.last_conf_low` / `st.last_conf_high`)
  instead of the `execTrailStep` grid ratchet.
- `execStructTrailBufTk` — 20 ticks below/above that swing, so a wick doesn't clip the runner.
- `execTp2StopMode` — "TP1 price" (default) / "Breakeven" / "One trail step behind": the stop FLOOR
  the instant TP2 fills, before the trail engages. The trail may tighten past it, never loosen it.
- `execSlLevel` — the stop's fib, 0.618 … **1.0** (default = the leg origin, i.e. unchanged).
- `execAplus` — trade A+ setups at all, so the B leg can be read in isolation.

The brother's tooltip names the tested best combo: **Structure trail + buffer 20 + floor = TP1 price**.

**Ported into `mpc_b_leg_strategy.pine`:** `execRunnerTrail`, `execStructTrailBufTk`,
`execTp2StopMode` and the `lStage2Floor` / `sStage2Floor` + structure-trail exit block, line-for-line
off the parent. Plus `execAplus`, relabelled **"A+ has priority (stand the B-leg down)"** — in this
fork A+ never places an order, so the flag doesn't disable an entry path, it drops the priority gate.
That gate has been the file's own first-listed tuning candidate since 2026-07-24 and is now a toggle.

**Deliberately NOT ported to the B-leg fork**, with reasons, so nobody "fixes" it later:
- `execSlLevel` — the B leg's stop is its frozen band's origin, not a fib on the A+ leg. The dropdown
  has nothing to select there.
- The pink blocked-trade markers. Their codes answer "why was this **A+** setup refused". In a fork
  where A+ never trades, those tags read as the opposite of what they mean. A B-LEG block tag needs
  its own code set — new design work, not a port.

**The export hole this closed — the important part.** `execRunnerTrail` shipped defaulting to
Structure on 2026-07-25, but `mpc_strategy_export.pine` carried no column for it. So
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
   input. `mpc_strategy.pine` HARDCODES the middle-bar close-cleared check (lines 1686/1688) while the
   `fair_value_gaps` engine defaults `require_close` OFF, so Python created gaps the Pine never did.
   Fixed on the Python side (`EngineConfig.fvg_require_close`, pinned True by the bot). **Never fix
   this class of gap by editing the Pine** — it is the source of truth; the pin belongs in the port.

`mpc_b_leg_strategy.pine` compiles (confirmed on TradingView), and its parity harness was built the
same day: **`indicators/mpc_b_leg_strategy_export.pine`** = that file with the body byte-identical
(only the line-40 `strategy()` title differs) + an appended PARITY EXPORT block, diffed by
`strategies/python/mpc_bleg/tools/compare_bleg.py` and registered in `backtest/tools/verify_parity.py`.
It plots the B-LEG arm (NOT `longArmed` — A+ never places an order in this fork), the band's 0.5 edge,
the band-derived TP1/TP2, and the tracker's own `bl_*` state, which is the column set that matters:
every new B-LEG rule lives in the tracker, and a band-maths bug shows as a wrong price many bars before
it becomes a wrong trade. **Ran GREEN (exit 0) on its first real export the same day** — 21,231 bars, ~90 distinct frozen bands and 5 graded trades diffed. That run also found a bug in the HARNESS (entry direction read off `Fill.qty`'s sign instead of the signed `Fill.dir`), which the offline round-trip test could never catch because its encoder shared the same mistake — a round trip proves the two halves agree, never that either is right.
`cfg_strcodes`' SL slot is pinned to the "1.0" code because this fork has no `execSlLevel` (its stop is
the band ORIGIN), which keeps ONE `cfg_*` decoder serving both exports. Regeneration split point is in
the export's own header.

---

## 2026-07-27 — TP1/TP2 default 30/40 → 0/0, and the `qty_percent = 0` trap

`execTp1Pct` / `execTp2Pct` now default **0** in both `mpc_strategy.pine` and
`mpc_strategy_export.pine` (and `exec_tp1_pct`/`exec_tp2_pct` in `config.py`, in lockstep). 0 = bank
NOTHING at the targets; the whole position rides to the runner. This is what Aaron has actually been
trading — his saved chart carried 1% on both rungs, which is the closest the input would take — and it
is what `mpc_sos_fade_optimization.md` Run 1 measured as best (0/0 = 70.7R vs 47.9R at 30/40,
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

## Standing instructions

**Do**
- Confirm swings only by the 3-candle pullback method: a swing high needs 3 consecutive candles each closing below the previous candle's low; a swing low needs 3 consecutive candles each closing above the previous candle's high.
- Reset the pullback count to zero at a new extreme if price prints a new high (while seeking a high) or new low (while seeking a low) before the count reaches 3.
- Keep detection to a single fixed constant (3). No numeric tuning inputs for detection.
- Reuse the same shared pullback-tracker type (`type PB`) for both the swing (external) engine and the internal engine — instantiate it twice, don't fork the logic.
- Gate new swing structure on a body-close break of the current trading range (BOS/CHoCH), per the corrected Stage 2b architecture — do not let swings form freely inside the range.
- Update `STRUCTURE_OS_BUILD.md` status/changelog as each stage is validated on a real chart.

**Never do**
- Do not use `ta.pivothigh` / `ta.pivotlow` or any fixed-lookback-window pivot method to detect swings in `smc_engine_v2.pine` (the from-scratch rebuild). This does not apply to `mpc_assistant.pine` / `structure_engine.pine`, which are a separate, intentionally pivot-seeded track — see Key paths above.
- Do not add numeric/tunable inputs for the detection logic itself — it must stay a zero-parameter mechanical rule.
- Do not fork the shared `PB` pullback-tracker type into two separate code paths for swing vs. internal — if the two ever need to diverge, branch inside `PB` with a flag instead.
- Do not build or validate Stage 2/3 logic on top of an unvalidated swing map — the swing detector is the foundation; get it confirmed against the real chart first.
- Do not treat a wick-only touch of a range boundary as a break — only a candle body close beyond the boundary counts (BOS/CHoCH).

---

## Guides & references

- `indicators/STRUCTURE_OS_BUILD.md` — full build log: settings-panel parity, architecture (two engines/one shared type), design decisions, open questions, and per-stage validation status against the original TradingView indicator.
- `docs/market_structure_engine_spec.md` — plain-language spec of the detection rules (swing points, HH/HL/LH/LL, BOS/CHoCH, internal engine) derived from the TradingView indicator's public description.
