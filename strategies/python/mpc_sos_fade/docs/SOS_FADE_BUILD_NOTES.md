# MPC SOS Fade Build Notes

**Status:** ARCHIVE - relocated history, deliberately. Implementation-level history and
war-story detail moved OUT of `strategies/python/mpc_sos_fade/CLAUDE.md` on 2026-08-12 so that file could stay standing rules
and current status. **Nothing here was deleted from the record** - same pattern as
`command-center/docs/BACKEND_BUILD_NOTES.md`.

⚠ **The Pine strategy sources moved on 2026-09-02: `indicators/strategies/` → `strategies/tradingview/`.**
The entries below are left exactly as they were written, so read any older `indicators/strategies/…`
path as `strategies/tradingview/…`. A diary edited to match today stops being a record of what
happened. Why they moved and what else changed with them: `docs/TRADINGVIEW_STRATEGY_MOVE_PLAN.md`.


**Why it moved.** `strategies/python/mpc_sos_fade/CLAUDE.md` had grown to 207,701 bytes, most of it dated narrative,
and every byte loaded into context whenever anyone worked in this area. Worse than the size:
the diary sat in 2 paragraph(s), the largest **58,936 bytes on a
SINGLE LINE** - not readable by a person at all. A rule nobody can find is not a rule.

**What is here.** The entries below, verbatim and unedited, newest first. Any RULE they taught
stays behind in `strategies/python/mpc_sos_fade/CLAUDE.md`; this is the evidence, not the instruction.

---

**Last reviewed:** 2026-08-12 (latest) — ⚠ **THE PINE PANEL WAS REBUILT AND FIVE INPUTS WERE DELETED FROM IT; NOTHING HERE MOVES, AND THE ONE THING THAT DID IS A COMMENT.** `indicators/strategies/mpc_strategy.pine`'s inputs went 156 → 67 under one numbered panel, and five "REQUIRED" drawing checkboxes that actually gated CALCULATION are gone — `showFibo`, `showFVG`, `i_showLiquidity`, `eqShow` and `marketStructureOnly` are permanent now. **None of them ever had a config field here**, because they were Pine drawing toggles and this port has no drawing, so no default, no `cfg_` column and no parity behaviour changes — **the only trace in this package was `show_div`'s comment, which qualified it with "`marketStructureOnly` off", a condition that no longer exists.** Corrected. ⚠ **`showDivInput` SURVIVED as an input and `show_div` still mirrors it** — it is the one of the five that Aaron kept, because the divergence engine is a real confluence source rather than a drawing. ⚠ **Every input TITLE is unchanged**, which is what keeps `mpc_sos_fade.meta.json`'s byte-identical-label contract intact; the panel pass diffed all five files on type, default and title and the only new entry anywhere is a new `drawFibs` drawing toggle. ⚠ **Re-export before quoting a parity run** — `compare_strategy.py` has not been re-run against a CSV off the rebuilt file. Earlier: 2026-08-11 — 🔴 **THE "BREAKEVEN" EXIT IS NOT BREAKEVEN ON ANY REAL ACCOUNT, AND EVERY WAY OF FIXING IT COSTS FIVE TIMES WHAT IT RESCUES.** Aaron's theory: `exec_be_buf_tk` is 30 ticks = **$0.30** and the measured PU Prime Standard spread is **$0.32**, so the buffer the strategy calls breakeven is smaller than the spread on the account the live bot is on — *"make sure we are truly breaking even and not just running negative thinking we're breaking even."* ✅ **CONFIRMED: the scratch cohort goes from +1.44R free to −0.56R on Standard / −0.94R Prime / −0.71R ECN, with 12 of 41 outright losses on every real tier.** A free-book run reports it as a small gain, which is where the false flat came from. 🔴 **BUT THE SPREAD NEVER TOUCHES THESE TRADES AND THE PREMISE IS THE ONE THING THAT IS WRONG — the gross move per unit is $0.298–$0.300 on every tier INCLUDING the free control.** Every entry here is a limit that fills at the price it names and every stop fills at the price it names, so a spread changes WHICH trades happen and not what a scratch nets (the same asymmetry `## Layered costs` records). **What it pays is SWAP, and it is the LONGS**: Standard scratches are **long −0.052R with 12 of 23 negative against short +0.036R with 0 of 18** — gold charges longs −79.60/lot/night and PAYS shorts +30.25, and a scratch by definition HUNG AROUND. **Aaron had the cause right and the cost wrong.** ⚠ **The scale is what kills a fixed buffer: one night of long swap is $0.796 per ounce, 2.7× the whole $0.30 buffer, and a Wednesday roll is $2.39 — EIGHT times it.** Over the 35 longs that paid any swap the stop would have had to move a median **$1.59**, 5.3× the buffer. 🔴 **SWEEPING THE BUFFER SOLVES THE COHORT AND WRECKS THE BOOK, monotonically: 30 ticks → +141.87R with scratches at −0.56R; 400 ticks → +105.97R with scratches at +30.80R.** That is **~5R of total return lost per 1R of scratch rescued** — a stop further into profit protects the trades that were coming back AND cuts the trades that were running, and the runner is where the money is (Run 8: >100% of net in every window). **30 is already the best value in the table and nothing needs changing.** 🔴 **THE DYNAMIC VERSION AARON PROPOSED — ratchet the stop by the swap charged at each rollover — IS WORSE THAN THE FIXED ONE, NOT BETTER, AND THAT IS THE COUNTER-INTUITIVE HALF.** Only positions held OVERNIGHT pay swap, and those are the runners, so a swap-driven ratchet aims precisely at the trades the sweep says to leave alone while doing nothing to the half of the book that closes same day (median nights held **0**). **Ceiling on what it could ever recover is +2.11R against sd 15.06R — and it is an UPPER BOUND, the same arithmetic that got its sign wrong on the minimum-stop guard. NOT BUILT.** ⚠ **The other half of the theory — losses compounding past 10% — is real and tiny: total excess is 1.0–1.7R over 6.5 years, and the one trade worse than −1.98R is a GAP through the stop that costs $0.00 in fees and is present on the free book too.** 🔴 **Standard's losers carry a swap CREDIT (+$71.92 mean) rather than a charge**, because losers here die fast (median 2.0h) and are short-heavy — **so the swap-on-losers half does not hold at all**; Prime and ECN put every loser past −1R purely on COMMISSION, which no stop move can recover. 🔴 **AND THE LONGS EARN THEIR SWAP, so nothing may cut them: +0.917R per trade after paying 8.93R of it, against shorts' +0.802R.** Any direction-split time stop or longs-only flat-by-close is cutting the better side — the same result `## Deliberate deviations` records for `flat_by_close`, which inverts the long side entirely to save 6.4R. ✅ **VERDICT: no strategy change. The bleed is ~1R over 6.5 years and every fix measured costs more than the bleed. The thing that actually helps needs no strategy change at all — switch to PU Prime ECN, worth +9.5R against Standard, five times the entire scratch problem.** Full record, both sweep tables and what was NOT measured: `mpc_sos_fade_optimization.md` → **Run 17**. **The standing lesson is about a premise that is arithmetically true and describes a cost you do not pay: "$0.30 cannot cover a $0.32 spread" is correct and irrelevant, because a resting limit never pays the spread — and chasing it would have led straight to widening the buffer, which is the single most expensive change available in this table. Before fixing a cost, check the strategy actually incurs it.** Earlier: ⚠ **`Signals` GAINED FOUR REPORTING-ONLY FIELDS AND NOTHING IN THIS BOT READS THEM.** `bull_bos_high_ms` / `bull_bos_low_ms` / `bear_bos_high_ms` / `bear_bos_low_ms` are the TIMES of the break-leg endpoints this file has carried the PRICES of since the B-LEG split — read straight off `st.bull_bos_h_loc` and friends, which the canonical structure engine has published since it was written. They exist for `mpc_bleg`, which prices its whole trade off a fib on that leg and could not say where the leg BEGAN, so the lab's chart had no x-span to draw one across. ⚠ **Same standing as `fibo_ash_ms`/`fibo_asl_ms` beside them, and the same two rules: TIMES rather than bar INDICES** (an index is relative to the window that produced it, and this repo has already been bitten diffing a Pine `bar_index` across two windows) **and `None` when this run's window cannot date the anchor**, never a substituted bar. ✅ **Proven cosmetic by MEASUREMENT rather than argued: a full-history replay reproduces this bot's documented baseline to four decimals — 159 trades / +142.1774R over 155,531 M15 bars — and `compare_strategy.py` is exit 0 at warmup 1000.** ⚠ **The A+ ladder is untouched and `_freeze_fib` is still the only thing that writes one here**; the fork records its own, off its own leg, in its own package. Earlier: 2026-08-10 (latest) — 🟢 **THE STRATEGY DETAIL PAGE READS LIKE A PAGE.** Aaron: *"the amount of text in there is so overwhelming… it says more than it does. It gives examples of past runs and all kind of craziness."* Every `desc` in `mpc_sos_fade.meta.json`, plus `edge` and `steps`, is rewritten SHORT and PLAIN: what the setting does, what each choice means, and the one fact that changes the decision. **No trade counts, no R figures, no dates, no file references** — `exec_poi_source` alone went 2,128 characters to 232. ⚠ **Nothing was deleted, only moved: every measurement cut was CHECKED to be recorded here or in `mpc_sos_fade_optimization.md` first**, and that check found three figures whose only copy was the tooltip. ⚠ **A desc is byte-identical to its Pine tooltip, so `mpc_strategy.pine` and its export changed in the same commit** — only the strings; every input's name, type, title, default and order is unchanged against HEAD, so no chart resets. ⚠ **The safety sentences STAY** — a stop that collapses onto the entry buys a huge position, deeper is the safe direction, lab-only settings say so — because those are the facts that change what somebody does. ✅ Driven end to end: scanned through the running backend and read in a real browser, no console errors; 333 strategy tests and 931 backend tests green (1 pre-existing failure). Earlier: 2026-08-10 (latest, second entry) — 🟢 **PARITY GREEN ON `execNoGapArm`, AND THE RUN WAS NOT VACUOUS — CHECKED RATHER THAN ASSUMED.** Aaron took TWO exports off `mpc_strategy_export.pine`, both with **`execReqFVG` OFF** (`cfg_bits` 544359, bit 16 clear) so the fallback branch is actually entered, one at `cfg_nogap_arm` **1** and one at **0**. `compare_strategy.py` is **exit 0 on both, at warmups 100 / 500 / 1000 / 2000 / 3000**, over **20,230 M15 bars (2025-09-30 → 2026-08-10)**. 🔴 **The non-vacuity check is the half that matters, because this is precisely where the minimum-stop guard went wrong on 2026-08-04.** The two exports were diffed against EACH OTHER before either green was believed: they differ on **4,237 bars of `px_edge`, 675 of `px_dec_bits`, 124 of `px_stop`, 45 of `px_block`, and 10 actual `px_entry_price` fills**, with `px_closed_r` differing on 23. **So the Pine really is steering a different run off that dropdown, and the Python reproduced BOTH streams bar for bar** — which is the thing a single green could never have said. ✅ **And the direction agrees with the 6.5-year measurement on an independent engine and a mostly-forward window: gated 31 trades / +12.16R against Any's 39 / +6.77R** — 8 fewer trades, more R, on TradingView's own tester rather than ours. ⚠ **It is 31 trades in ten months, so read it as a CONSISTENCY check on the rule, never as a second measurement of the edge.** ⚠ **`warn_unexercised()` correctly stayed silent on both** (gap requirement off, column present), which is the other direction of that guard and is what stops it becoming noise. Earlier the same day: 🟢 **`exec_nogap_arm` HAS A PINE SIDE NOW, AND THE HARNESS WILL TELL YOU WHEN IT COULD NOT TEST IT.** `execNoGapArm` is in `mpc_strategy.pine` and its export mirror, the export plots `cfg_nogap_arm` (Any?0 : Sweep + RSI div?1), and `compare_strategy.py` decodes it — **absent column ⇒ "Any", read as a fact about what the PINE did before the gate existed, never as the Python default** (a test pins that it must not fall back on the base config). 🔴 **The Pine's fallback block HAD TO MOVE**: `sosL_swp` / `sosL_div` are computed ~30 lines after the entry ladder that needs them, so the five-line `if not execReqFVG and fibsReady` block now sits just after the retro-link snapshot. **Nothing between the two points reads `longEdge` / `shortEdge`** — checked, the next read is 140 lines on — so at the default the move is behaviour-neutral. ⚠ **The input is declared beside `execLabelOff`, deliberately not beside `execReqFVG`**, because TradingView keys saved values off declaration order per type and this file has 37 strings; it shifts exactly ONE (`execTimeStopMode`). **After pasting the new build, check the Time stop input still reads "Before TP1 only" / 36 hours.** 🔴 **`warn_unexercised()` is new and is the point of the pass as much as the input is: it prints a warning whenever the export ran `execReqFVG` ON, because then NEITHER side enters the fallback branch and exit 0 is evidence about nothing.** That is the minimum-stop guard's 2026-08-04 trap pre-empted — a lever shipped live on a green run whose export had raised its block code zero times in 21,897 bars. **A useful export for this lever must be taken with the gap requirement OFF, once at `cfg_nogap_arm` 0 and once at 1.** ✅ 6 new harness tests (333 strategy green), a round trip driven at BOTH arm modes, and **measured non-vacuity: the two modes price a different entry edge on 59 of 960 synth bars** — with the honest other half recorded beside it, that both still close the same 6 trades there, so the trade-level evidence stays the 155,531-bar replay and not the synth frame. ✅ **PARITY-VALIDATED the same day on two real exports — see the top of this entry.** Until `compare_strategy.py` exits 0 on a real CSV taken with `execReqFVG` off, a gated result remains a LAB FINDING and no live bot may run one. **The standing lesson is about where a test's own blind spot lives: this harness would have gone green on the very first export Aaron takes, because the shipped default never enters the branch — and green would have read as validation. A gate has to be able to say "I did not test that".** Earlier the same day: 🟢 **THE NO-FVG SETUPS ARE WORTH TAKING AFTER ALL, BUT ONLY THE HALF THAT ALSO CARRIED AN RSI DIVERGENCE — AND THE POINT OF THE PASS IS THAT THE SCOREBOARD WAS WRONG BEFORE THE RULE WAS.** Aaron: *"I don't even care about max drawdown... there's periods in my chart where there's no trades, so the chart jumps a lot. I need more frequent trades."* Every previous run scored these setups on R and drawdown, which is the wrong question for that, and Run 12 had closed the file on them in 2026-07 on exactly those grounds. `exec_nogap_arm` ∈ {**"Any"**, "Sweep + RSI div"} is new in `config.py`, read ONLY when `exec_req_fvg` is False, so **at the shipped defaults it is INERT and no historical figure moves**. 🔴 **THE SPLIT IS THE FINDING AND IT IS CLEAN IN A WAY NOTHING ELSE TRIED WAS.** The fallback takes 173 setups the shipped bot refuses; **the 78 whose SOS carried BOTH a liquidity sweep and an RSI divergence made +35.47R, and the 95 carrying only a sweep made +0.71R — an average of +0.007R per trade, i.e. exactly nothing.** Eight other splits were run on the same 173 and every one came back flat — direction, entry hour, weekday, leg size, stop distance, year, and the DAILY-sweep confluence Aaron proposed (36 trades, +7.34R, 33.3% win against the rest's 34.4%, and −1.61R with its best trade removed). ✅ **MEASURED, 155,531 M15 bars (2020-01-01 → 2026-08-03), one real replay per row, `exec_secondary` off:** shipped **159 / +142.18R / maxDD 5.61R** · fallback "Any" **315 / +149.55R / 12.70R** · fallback gated **230 / +155.89R / 9.54R**. ✅ **AND THE SHIPPED FIELD REPRODUCES ALL THREE BOOKS TO THE CENT** — every figure above was first measured with a scratch subclass that swapped `_entry_edges` at runtime, which is a SECOND implementation of the rule, so the real config field was driven through the real strategy and demanded the same 159 / 315 / 230 and the same R. **Two implementations agreeing is not one being right; that check is the difference.** 🔴 **COSTS ARE WHAT SEPARATE THE TWO SETTINGS, AND WITHOUT THEM THE WRONG ONE LOOKS FINE.** The lever works by trading 45% more, so it pays 45% more spread and commission. Charged at the decided live account (**PU Prime ECN**, commission $1.00/side/lot, gold swap −79.60/+30.25, spread 0.12 **STATED not measured** — `fills.py` still refuses that tier's spread and this is an explicit override): **159 / +132.23R · 315 / +134.78R · 230 / +144.78R.** So "Any" adds 156 trades to earn **+2.55R** once charged, and on Vantage's fully-measured profile it goes **NEGATIVE** against the shipped book (−0.17R) while the gated version holds +11.32R. ⚠ **Cost per trade is 0.048R for the gated book against 0.063R for the shipped one** — the added trades are CHEAPER to run, because they rest at the 0.618 with a wider stop, so a fixed spread is a smaller fraction of a bigger 1R. ✅ **JITTERED ±$0.05/bar over 8 seeds it beat the shipped book on 8 of 8 individually and was never negative** (min +116.06R, mean +147.23R, sd 17.46R), with **+66 to +75 extra trades on every seed** and the worst drought landing on **exactly 54.5 days on all eight**. ⚠ **READ THE R AS "NOT WORSE", NEVER AS THE GAIN: +13.71R sits inside this strategy's own run-to-run spread of 15.06R.** **The measured gain is FREQUENCY, and it is a count rather than a return, so noise cannot manufacture it** — median gap between trades **9.5 → 7.3 days**, worst drought **99.7 → 54.5 days**, calendar months with no trade at all **8 of 80 → 4**. ⚠ **It is bought with drawdown — 5.61R → 9.54R free, 6.03R → 11.12R charged — which Aaron has explicitly accepted, and which must be restated rather than buried.** ⚠ **Per year it is positive in ALL SEVEN and beats the shipped book in five**; the two it loses are 2024 (−0.98R, noise) and **2025 (−19.12R, and almost all of it is one +16.49R October short a fallback trade was holding the slot in front of)** — the one-position-slot queue cost, arriving for the third time in this file. ⚠ **The monthly R spread does NOT improve (sd 5.10 → 5.65)**: it fills the calendar, it does not flatten the curve, and saying otherwise would answer a question Aaron did not ask. 🔴 **THE GATE READS THE RAW ARM FLAGS (`sos_*_swp` / `sos_*_div`), DELIBERATELY NOT THE TOGGLE-FILTERED ONES.** `exec_arm_div` is OFF at the shipped defaults, so a gate reading the filtered pair would refuse **every** setup while the page said the lever was on — enabled and doing the opposite of its job. It asks what the market did at the SOS, not which triggers the operator chose to act on, so it is independent of the two arm toggles and is **not** a way of saying "arm on both". ⚠ **`_entry_edges` now takes `seq` and it is REQUIRED with no default**, because a `None` default would make *the sequence was not passed* and *the confluence was not there* the same value at the one line that decides whether a trade happens. 🔴 **That signature change found a live defect in a sibling: `mpc_bos.BosExecution` overrides `_entry_edges` and would have died with a `TypeError` on its first bar** — caught by its own parity test, not by reading. `mpc_bleg` PINS the new field to the inert value. ✅ **14 new tests, ALL proven by MUTATION rather than by a fail-watch** (the feature does not exist at HEAD, so red there is uninformative): neutering the gate reds 4, making it read the enable toggles reds 3, giving the short side the long flags reds exactly 1, dropping the config refusal reds 2, and giving `seq` a default reds the signature test. 326 strategy tests green. ⚠ **PYTHON-ONLY — there is no `execNoGapArm` input in either A+ Pine, so `compare_strategy.py` can never configure a non-default run, a result taken with one is a LAB FINDING, and no live bot may use it.** Parity is structurally unaffected: the default is the pre-existing branch byte-for-byte, and an export that ran `execReqFVG` off decodes to "Any", which is what the Pine does. ⚠ **`exec_ob_deepen` had shipped on 2026-08-09 with NO meta entry**, so `test_every_tunable_param_is_documented` has been RED on main since — a param with no `desc` renders as `—` on the strategy page. Documented in this pass. **The standing lesson is about the scoreboard rather than the rule: these setups were measured three times and refused three times, on R and on drawdown, and the population never changed — what changed was being asked for trade FREQUENCY, which nothing had ever computed. Before concluding a thing is worthless, check you have measured the quantity somebody actually wants.** Earlier: 2026-08-09 — 🔴 **ORDER BLOCKS ARE CLOSED — SEVEN ANGLES, TWO TIMEFRAMES — AND THE LAST TEST REFUTED THE TIDY EXPLANATION THAT HAD BEEN OFFERED FOR THE OTHER SIX.** Aaron: *"I'm so convinced that there's something there with order blocks, and I can't figure out what it is."* Every angle tried until now asked ONE question in six costumes — *where do I put my limit order* — so each let a block ARM a setup the gap rule never armed, measured a larger and different population, and paid the one-slot displacement cost (`Either`'s 178 added trades were **+33.08R POSITIVE** and the book still came out worst, because it displaced 45 real ones). ✅ **`backtest/tools/ob_confluence.py` asks the one question that CANNOT be punished by the position slot: a pure QUALITY split of the 159 trades already taken.** It adds no trade, removes none and moves no entry price — it splits the shipped book by whether the gap the limit actually rested on had a same-direction block under it, which is a risk-SIZING question and therefore Aaron's standing requirement (*"some trades are just way higher quality"*). **MEASURED, 155,531 M15 bars, control reproduced to the cent (159 / +142.18R): 81 on-block at +0.763R average against 78 plain at +1.031R — a difference of 0.47x its own standard error, i.e. NOTHING.** The undirected reading is **byte-identical** (same 81/78 split, same R), so requiring the block to point the same way as the gap decides nothing either. 🔴 **THE 4-HOUR RUN IS THE ONE THAT MATTERS, BECAUSE IT KILLED MY OWN EXPLANATION.** The story offered for the six null results was that an M15 block is WALLPAPER — a live one exists on **99.9% of bars** — so it cannot separate anything. That story predicts a rarer block should separate better. It does not: 4H blocks tag **16 of the 159 trades rather than 81 — five times rarer at the entry — and the separation gets WORSE (0.08x the noise)**, with the on-block group's whole +15.68R being ONE trade (+16.49R; the other 15 make **−0.81R** between them). **Scarcity was never the problem.** The statement the data actually supports is duller and narrower: **an order block carries no information about how these trades turn out.** ✅ **The tag is PINNED to `Execution._entry_edges` rather than re-derived beside it** — naming the winning gap means re-running the selection, and a second implementation of a rule is this repo's signature defect, so the replica must reproduce the real edge to the float on EVERY bar and REFUSES the run otherwise (zero mismatches over 155,531 bars). ⚠ **Higher-timeframe blocks are read with a hard no-lookahead rule** — a snapshot is admitted only once its own coarse bar has CLOSED — because getting that wrong manufactures an edge out of nothing. ✅ **`backtest/tools/tf_sweep.py` — the same strategy on four bar sizes, same 6.5 years: 15m 159 trades / +142.18R / avg +0.894R (the control, reproduced) · 30m 106 / +94.70R / avg +0.893R · 1H 37 / −6.61R · 4H 9 / −3.99R.** The edge does not merely weaken above 30m, it INVERTS. 🔴 **The 30m row read as the day's one positive result for about an hour, and `backtest/tools/tf_overlap.py` refuted it.** Against the A+/B-LEG pair as the yardstick: **37.0% of A+'s in-market time is shared (against 0.5%), 95% of it SAME-direction (against 1 bar of 49), 39 same-direction entries within four hours with the closest 0 MINUTES apart (against ZERO), and monthly R correlation +0.613 against +0.172.** It is not a second strategy, it is this bot through a coarser lens — and stacking it would concentrate risk on the same swings rather than spread it. ⚠ **It is no good as a REPLACEMENT either**: the same average R, fewer trades, and drawdown 5.61R → 10.07R. ⚠ **`overlap_audit.py` could not answer this** — it works in bar INDICES over ONE frame, and an index means a different amount of time on each side of a timeframe pair, so the new tool measures everything on the trades' own `entry_ms`/`exit_ms` clock. ⚠ **The two refuted levers are KEPT and DEFAULTED OFF at Aaron's call** (*"lets keep the levers incase we need them in the future but they are off"*) — `exec_poi_source = "Order block (no FVG)"` and `exec_ob_deepen = False`. **The standing lesson is about EXPLANATIONS rather than results: six null results were handed one tidy story that fitted every number, and the seventh test refuted the story while agreeing with all of them. A story that fits the evidence is not evidence — the thing worth running is the test that could break it, and here that test cost one flag.** Earlier the same day: 🔴 **THE ORDER-BLOCK BOT WAS BUILT, RUN AS A REAL SECOND LEG, AND IT HAS NO EDGE — AND THE TWO DEFECTS FOUND ON THE WAY ARE WORTH MORE THAN THE VERDICT.** The plan was a separate fork (`mpc_ob_fade`); Aaron challenged it — *"are you a thousand percent sure there should be its own strategy and its own bot and not just a toggle… I will hate that we segregate this when they should have been the same strategy"* — and he was right. It ships as `exec_poi_source = "Order block (no FVG)"`, a MODE of this package run as a second LEG on one shared account, because the entry rules, the exit ladder and the sequence are identical and only the zone differs; a fork would have been a second copy of everything that is already right. His standing requirement decided it: *"all my strategies, I wanna be able to tune how much risk they can take because some trades are just way higher quality"* — two legs each carry their own `exec_risk_pct` where a toggle inside one bot could only ever have one. ✅ **MEASURED, `backtest/portfolio/run_stack`, 155,807 M15 bars, $10,000, 10% cap: the block leg SOLO is 133 trades / +0.02R / maxDD 21.81R / 20.3% win, closing $10,000 → $4,638.** Stacked, the pair posts **+142.19R against the FVG leg's own +142.18R alone**, with drawdown 5.61R → 10.30R and the closing balance $54.7M → $25.4M. **Zero contention and zero displacement — the shared account moved no decision, so this is a clean measurement of the population and not of the plumbing.** 🔴 **DEFECT 1 WAS FOUND BY AARON REFUSING A NUMBER, NOT BY A TEST.** He would not accept 103 candidate setups becoming 181 trades, and named the mechanism himself: *"is the zone creating its own fair value gap? Because I know that's a real thing."* It was. The stand-down asked *is a gap here NOW*, per bar, where the 103 counted setups that DIED with no gap — so price ran into the zone, CREATED a gap, and both legs traded the same idea. **MEASURED: 60 of 181 setups (33%) traded by BOTH legs, 44 with the FVG leg first.** `_sync_gap_latch` makes it a LATCH keyed on the SOS bar — per setup, cleared by a new break — and shared setups fell 60 → 14, all 14 OB-first, which is structurally unpreventable because the gap does not exist yet when the block leg fills. 🔴 **DEFECT 2 IS IN THE SHARED ACCOUNT AND AFFECTS EVERY STACK, NOT JUST THIS ONE.** A leg asked for $4,385.98 of risk against a room of a fraction of a cent, and `_open` scaled its qty by `granted/desired` ≈ 1e-6 — **a position of no size that occupied the leg's ONE slot from November 2020 to August 2026: 18 trades instead of 181, with nothing logged as refused.** Fixed in `backtest/portfolio/account.py` (`_MIN_GRANT_USD`); full record in `backtest/CLAUDE.md`. ⚠ **It had never fired before because the first shared run's contention log was EMPTY** — this is the first stack anyone has run with a budget tight enough to produce a partial grant. 🔴 **DEFECT 3 WAS MINE AND IT IS THE transferable one: my first verification of defect 1 compared entry TIMES and reported the two legs clean.** Two legs on one account cannot hold a position at the same moment by construction, so a time comparison can only ever come back clean — the unit is the SETUP `(side, SOS bar)`, and asking the wrong question produced a confident pass over 60 double-traded setups. **Before believing a "no overlap" result, check that the thing being compared is the thing that can overlap.** ⚠ **The verdict is about the POPULATION and not about the seam**: with nothing refused and nothing displaced, +0.02R over 133 trades is the order-block setup measured on its own slot with every excuse removed — which is exactly what the fork was going to be built to find out, at a fraction of the cost. ⚠ **`docs/MPC_OB_FADE_SPEC.md` described the fork and was DELETED in the same commit** — a spec left lying around is a signpost pointing the next reader at work the data already closed. The record of what was tried is `mpc_sos_fade_optimization.md`, in this folder. Earlier the same day: 🟢 **THE ORDER-BLOCK OPTION LEFT THE PINE AND STAYED IN THE PYTHON, AND THE SPLIT IS THE DECISION.** With the question below answered, `mpc_strategy.pine` and its export mirror are RESTORED to `2580f5b` — `execPoiSource`, the ported OB engine, `f_gapOnOb`, the POI seam and the `cfg_poi_source` plot are gone, and the ~230-line internal fib that was cut to make room for them is back. **The order-block setup is being built as its own bot (`mpc_ob_fade`) with its own position slot instead**, because 82% of the loss below is DISPLACEMENT rather than the added trades themselves. ⚠ **`exec_poi_source` STAYS HERE and that is not an oversight**: this package is the shared base `mpc_bleg`, `mpc_bos` and the new fork all build on, and `signals.pois_for` is the ONE place the zone rules live — deleting it would mean a second copy for the fork, which is the failure mode this whole seam exists to prevent. 🔴 **The cost of that choice, stated rather than left to be discovered: only `"FVG"` now has a Pine input behind it, so `compare_strategy.py` can never configure another mode and every non-FVG result is a LAB finding by construction.** That is the `exec_sl_custom` standing exactly — a Python-first lever — and the lab row now carries a `(lab only)` suffix, the `exec_conf_sz` precedent. The harness's `cfg_poi_source` decode is KEPT: an absent column reads `"FVG"`, which is the correct answer for every export on disk and every export anyone will take. ⚠ **Nothing here moves a trade** — `"FVG"` is the shipped default and reproduces 159 trades / +142.18R unchanged; 198 tests green. ⚠ **The two forks are mutually exclusive BY CONSTRUCTION once the new bot ships**: A+ is pinned to gaps and `mpc_ob_fade` fires only where there is NO gap in the zone, so the pair can never take the same setup — which is the property the A+/B-LEG overlap audit had to be run to establish, and here it falls out of the rule. Earlier the same day: 🔴 **THE ORDER-BLOCK QUESTION IS ANSWERED, AND THE ANSWER IS NOT THE ONE THE THREE BAD RUNS IMPLIED: blocks are a roughly ZERO-expectancy population that loses money by CROWDING OUT the winners.** Aaron asked how many opportunities sit outside the winning trades — specifically, of the setups that were otherwise complete and died only because no gap was in the zone, how many had an order block in 0.618-0.786. ✅ **MEASURED (`backtest/tools/ob_opportunity.py`, 155,807 M15 bars, 2020-01-01 → 2026-08-06, the shipped FVG book with the OB engine tracking but never trading and the run ASSERTED to reproduce 159 trades / +142.18R): 179 "No FVG in zone" misses, 130 of them (73%) with a same-direction block in 0.618-0.786 and 152 (85%) in the shipped 0.5-0.886 band.** ⚠ **130 against 159 real trades is not a filtered subset, it is nearly the same book again** — the count lands within twenty of "Either"'s measured 292, which is the cross-check that this bucket IS the order-block book rather than a better corner of it. ✅ **THE PER-TRADE DECOMPOSITION IS WHAT SETTLES IT, and it closes to the cent: UNTOUCHED 130 (+110.07R, byte-identical) · REPRICED 0 · DISPLACED 29 (+32.11R, gone) · NEW 146 (−7.16R) = −39.27R** (`FVG first` 276 trades / +102.90R / maxDD 9.62R against the baseline's 159 / +142.18R / 5.61R). 🔴 **The 146 added trades average −0.049R — indistinguishable from zero — while 82% of the loss is 29 baseline trades that never happened, and ONE of them (2025-10-21 short, +16.49R) is 42% of the total damage.** **"Either" makes it undeniable: its 178 new trades were +33.08R, POSITIVE, and it is still the WORST book (+85.77R), because it displaced 45 baseline trades.** ⚠ **So do not read the three bad runs as "order blocks are bad setups" — read them as this bot having ONE position slot and a fat-tailed return distribution, so any marginal entry is a bet against its own tail.** The lever is CONCURRENCY (`backtest/portfolio/run_stack`, a second slot), not the band and not the precedence order — narrowing 0.5-0.886 to 0.618-0.786 removes only 22 of 152 candidates. This is Run 12's queue effect reached from a new direction, and it is now measured twice on two different loosenings. ✅ **`REPRICED 0` is the cleanest proof available that the "FVG first" precedence does exactly what it says**: every gap-priced entry is identical to the baseline, so that book is baseline + extras − displacement and nothing else. Earlier the same day: 🟢 **`exec_poi_source` GAINED A PRECEDENCE MODE: "FVG first".** Aaron, off a curve he did not like: *"could I add, like, a precedence order? If there is fair value gaps, take those preferentially over order blocks. Only if there's no fair value gaps, then take the order blocks. If a fair value gap and an order block overlap, that's the most preferred fair value gap to take."* Built on both sides in one commit — `signals.pois_for` and `mpc_strategy.pine`'s POI seam. **`pois_for` now returns 5-tuples, `(top, bottom, is_bullish, born, RANK)`**, and `Execution._entry_edges` takes the best rank that has a QUALIFYING zone, letting nearest-first decide only WITHIN a rank: `POI_RANK_FVG_ON_OB` (2) > `POI_RANK_FVG` (1) > `POI_RANK_OB` (0). ⚠ **The ranks are compared AFTER the eligibility gates, and that ordering is load-bearing** — a gap the deep-only or pre-zone gate refuses must not suppress a block the entry may legitimately use, and it cannot, because it never enters the comparison. Ranking before gating would turn a REFUSED gap into a veto on the fallback. ⚠ **Every other mode returns ONE flat tier**, so all candidates tie and the loop collapses to the original max/min. ✅ **PROVEN BY REPLAY, not argued: "FVG", "Order block" and "Either" each reproduce their HEAD trade list to a matching SHA-256** over entry time, direction, entry price, exit price, R and exit reason on the same frame. 🔴 **IT IS NOT "FVG" WITH A SAFETY NET, AND THE NAME INVITES EXACTLY THAT MISREADING.** A leg whose only zone is a block still trades, so this takes **strictly more setups than "FVG"** — and that fallback tier is precisely the population already measured as bad (order blocks alone 267 trades / +75.93R against FVG's 159 / +142.18R; requiring a block was worse than requiring nothing). **Expect the trade count to rise toward "Either" and the quality of the added trades to be the order-block quality.** ⚠ **"Either" and "FVG first" hold the SAME zones and differ only in which one prices the entry**, so a difference between them is entirely an ENTRY-PRICE effect — which makes that pair the run that finally separates the two things the first order-block measurement could not: which setups qualify versus where the limit rests. **Run that pair, not FVG-vs-FVG-first.** ⚠ **The confirming block must point the SAME WAY as the gap, and Aaron's words did not settle it.** A bearish supply block on a bullish gap is the opposite of confirmation, and ranking that gap TOP would promote the worst candidate on the leg. **This is a judgement recorded as a judgement**; one predicate in `pois_for` and one in `mpc_strategy.pine`, and they must be flipped TOGETHER or the parity gate goes red. ⚠ **Overlap is INCLUSIVE at the edges**, matching every other band test here (`bot <= p2 and top >= p6`); a `>` on one side against a `>=` on the other is a divergence no unit test on either side would show. ✅ **The export code was APPENDED as 3** (`cfg_poi_source` = FVG 0 / Order block 1 / Either 2 / FVG first 3) and `compare_strategy.py` decodes it — **codes are a WIRE FORMAT, never renumbered**, because an export on disk carries the number and re-pointing one is silent: the file still reads and now claims a mode it never ran. ⚠ **NOT PARITY-VALIDATED — no export has ever been taken on a non-FVG run**, so a "FVG first" result is a LAB finding and no live bot may run one. ⚠ **The Pine is also NOT COMPILED**; it was over the token cap yesterday (CE10117) and this adds ~30 lines back. ✅ **9 new tests (287 strategy green), and the load-bearing ones are MUTATION-PROVEN rather than merely green**: the two entry-loop tests go red against the un-ranked loop, the same-direction test goes red when the direction predicate is dropped, and the inclusive-overlap test goes red when `>=` becomes `>`. ⚠ **The round-trip test's non-vacuity was MEASURED against "Either" specifically, not against the default** — both price an edge on the same 833 of 960 synth bars (the union is identical by construction) and rest a DIFFERENT limit on 111 of them, so the ranking really is steering the stream. Comparing it to "FVG" would have proved the union differs, which was never in doubt. **The standing lesson is about what a mode NAME promises: "FVG first" reads like a filter with gaps preferred, and it is a RANKING over a UNION — so it can only ever trade MORE than the mode it is named after.** Earlier the same day: 🟢 **THE SHARED-ACCOUNT SEAM REACHES THIS BOT'S CONSTRUCTOR NOW.** `Execution` has taken an injected `account` since 2026-07-17 and NOTHING could pass it one — the strategy built its `Execution` without the kwarg, so every run got a `SoloAccount` (no cap, always full size). `__init__` takes `account=None, leg="strat"` and threads both through, so this bot can be one leg of a stack sharing ONE balance and ONE risk budget (`backtest/portfolio/run_stack`). ⚠ **Omitting it is byte-identical to before** — Execution still builds its own `SoloAccount`, which is what keeps every parity result and every measured baseline valid. ⚠ **`leg` MUST be distinct per leg**: the account holds one open position per key, so two legs both called `"strat"` would overwrite each other's reservation and the cap would silently under-count the open risk while reporting itself enforced; `run_stack` refuses duplicate names for exactly that reason. ✅ **MEASURED on a real two-leg run (155,807 M15 bars, $10,000, 10% cap): this bot posts 159 trades / +142.18R shared, identical to solo** — R is normalised to the trade's own risk, so a shared balance changes the DOLLARS and no decision. 🔴 **And nothing was ever blocked in 6.5 years, because this bot touches breakeven on 161 of 161 trades at a median of ONE BAR** — the account reserves risk to the CURRENT stop, so its room is released almost immediately and the second leg is never refused. Full record: `backtest/CLAUDE.md` → *The shared-account run*. Earlier the same day: 🔴 **ORDER BLOCKS CAN BE TRADED INSTEAD OF FAIR VALUE GAPS NOW, AND THE RAW ANSWER IS THAT THEY ARE MUCH WORSE.** Aaron: *"build an option to trade off of order blocks instead of fair value gaps so I could toggle between them... I just wanna see raw what order blocks return."* `exec_poi_source` in {**"FVG"**, "Order block", "Either"} decides which zones count as the point of interest in the 0.5-0.886 band. **MEASURED, one real replay each, 155,807 M15 bars (2020-01-01 -> 2026-08-06): FVG 159 trades / +142.18R / maxDD 5.61R / +0.894 per trade - Order block 267 / +75.93R / 11.11R / +0.284 - Either 292 / +85.77R / 10.51R / +0.294.** Order blocks give **68% more trades for half the R and double the drawdown**, and R per trade falls to a third. WARNING **Requiring an order block is worse than requiring NOTHING** - dropping the gap requirement entirely gives 315 trades / +149.55R, so this is not a filter that is merely weak, it is one that actively selects worse setups than no filter does. WARNING **The run changes TWO things at once and this data cannot separate them**: which setups qualify, AND where the limit rests (a block's edges price the entry through `_fib_snap` exactly as a gap's do). Attributing the loss to selection rather than to entry pricing needs a further run. **The design is the part worth keeping: an order block is adapted into the gap's own `(top, bottom, is_bullish, born)` shape and both consumers read ONE seam (`signals.pois_for`)** - so a block is judged by the same deep-only filter, the same pre-zone gate and the same four entry rules, and "order blocks obey the same rules as a gap" is true by construction rather than by two implementations agreeing. WARNING **`born` is the block's `created_index`, NOT its origin candle** - the anchor can be ~10 bars older than the bar the engine can first report it on, and the pre-zone gate asks whether the zone was ALREADY THERE when price arrived; answering with the anchor would be look-ahead wearing a reasonable field name. WARNING **Asking for blocks on a stack built without the engine REFUSES (`PoiSourceUnavailable`) rather than returning `[]`** - an empty list would trade exactly like a Require-FVG run that found no gap, i.e. a silently different strategy reporting itself as the one you configured. `Signals.obs_available` is the only thing separating *found none* from *never asked*. WARNING **`stack_config()` is a per-INSTANCE layer over the static `engine_config()`**, which stays a description of the Pine's constants because the parity harness and `mpc_bleg` both call it off the class; a caller that drives `step()` with its own stack must apply it too, and gets a refusal rather than a silent degrade if it does not. **THE PINE SIDE LANDED THE SAME DAY, so the line that used to sit here - "PYTHON-ONLY, no Pine counterpart, compare_strategy.py can NEVER check a non-default run" - is now FALSE and has been corrected in place rather than left to be read as current.** `mpc_strategy.pine` and its export mirror carry `execPoiSource`, the OB engine is ported into both, and the export plots **`cfg_poi_source`** which `compare_strategy.py` decodes (absent column => "FVG", a FACT about every older export because the input shipped defaulting to FVG on the day it was added - deliberately NOT the `cfg_eq_exempt` hole). WARNING **The gate has still not RUN on a non-FVG export**, so an order-block result remains a LAB finding until it does, and no live bot may run one before then. What IS proven is the transcription: the ported OB block was mechanically diffed against `mpc_assistant.pine` line by line and is identical apart from one added field, and `engines/order_blocks/` is itself Pine-parity-validated against that same source - so the chain chart-to-bot is argued, not measured, and the missing link is one fresh export. **The default is proven untouched by replay, not by argument** - `exec_poi_source="FVG"` reproduces 159 trades / +142.18R / maxDD 5.61R exactly, and `pois_for` returns `sig.fvgs` unchanged. WARNING **The parity gate itself was NOT re-run: the only export on disk predates the `cfg_eq_exempt` column and the tool correctly refuses it.** Re-run on the next fresh export. 13 new tests, weighted toward the silent failures - a typo'd source falling back to gaps, an order-block run on a blind stack, and an export with no `cfg_poi_source` column decoding as anything but FVG. WARNING **The two round-trip tests were checked for VACUITY rather than assumed non-vacuous**: over the 960-bar synth frame the three sources price an entry edge on **824 / 404 / 833** bars, so the column really is steering a different decision stream and the harness reproduces it exactly. A green round trip across three modes that all produced the same run would have proven nothing. Earlier: 2026-08-07 - 🟢 **THE MINIMUM-STOP FLOOR NOW REACHES THE 1-MINUTE RE-ENTRY, AND MEASURING IT FIRST IS WHAT KEPT THE CLAIM HONEST.** Aaron asked what the guard saves him from before agreeing to add it. **The answer is one setup in 7.9 years.** `_secondary_pending` asked only `dist > 0` while `_place_entries` had enforced the floor since 2026-07-30, and `exec_min_stop_mode` ships `"% of price"` **0.08, not `"Off"`** — so this was live in a default run. It matters MORE on this path than the 15m one: `qty = risk / dist`, and a 1-minute leg is a shorter leg. ✅ **MEASURED, two full replays over 186,366 M15 + 2,790,942 M1 bars, the instrumented control reproducing the shipped book exactly: 188 trades / +165.46R / ddR 5.53 → 188 / +165.42R / ddR 5.53, all 180 primaries identical.** −0.04R, and the refused trade did not vanish — a later re-entry took the freed slot 47 minutes on, which is why this was replayed and not subtracted (the same guard's cheap estimate on the 15m path got its SIGN wrong). 🔴 **The first count was MISREAD and the correction is the transferable part: 90 of 1,956 secondary limits rested under the floor, and all 90 are the SAME limit re-placed every 1m bar — one setup resting 90 minutes, at one ratio, 0.9848 of the floor.** A resting order is re-placed per bar, so counting placements counts BARS, not risk. Exactly one under-floor secondary has ever filled (2024-12-02 20:08, $2.08 against a $2.11 floor). ⚠ **So the case for this is CONSISTENCY, not the measurement** — the history holds no instance of the hazard, only one rule enforced in one of the two places it applies, and an absence over 8 years is not evidence it cannot happen. ✅ 5 new tests, **3 watched RED** against the restored `dist > 0`; the 2 that pass at HEAD are kept and labelled. 196 strategy + 348 backtest green. ⚠ **The same pass found a test yesterday's default flip had made VACUOUS: `test_run_dual_primary_is_identical_to_run_when_secondary_off` built `SosFadeConfig()` under a comment reading "defaults False" — it ships True now, so the test had become a run of the secondary path, and it still PASSED because its synthetic 1m stream never arms one.** Pinned explicitly. **The standing lesson: flipping a default silently re-points every test that relied on it, and the ones that keep PASSING are the ones you will not find — when you change a default, grep the suite for bare constructions of that config.** Earlier the same day: 🟢 **THE 1-MINUTE RE-ENTRY IS ON BY DEFAULT NOW, CAPPED AT ONE PER PRIMARY, AND THE MEASUREMENT THAT SAYS IT DOES NOT EARN ITS PLACE STILL STANDS.** Aaron read two `SEC` chips on one 2024-12 screen and asked whether one primary could hand out several re-entries. **It could** — the latch retired the 1-MINUTE leg, and 2024-12-02 took two off one 15m break (SOS bar 7893, 1m legs 120399 and 120499, the second filling two minutes after the first closed). `exec_sec_once_per_setup` (default ON) retires the 15m SOS bar on a fill instead, which is one-to-one with the primary. ✅ **MEASURED, one real replay each over 186,366 M15 + 2,745,711 M1 bars: uncapped 190 trades / +165.46R / maxDD 6.53R · capped 188 / +165.46R / maxDD 5.53R**, zero primaries moved. It fires on **two setups in 7.9 years**. 🔴 **The identical total is a COINCIDENCE** — the two removed trades are exactly −1.000R and +1.000R and cancel — **so do not read it as "capping is free"**; the real gain is the drawdown, because the −1R sat inside the worst losing stretch. ⚠ **`exec_secondary` DEFAULTED ON at Aaron's request against the standing verdict, which is recorded as overridden rather than reversed: eight re-entries in 7.9 years, April 2023 is still all of it, and the book's average excluding that trade is 0.739R against the baseline's 0.777R. PIN IT OFF to reproduce any older figure in this file.** 🔴 **The default made a structural gap load-bearing: `run_dual` has ONE caller, so the optimizer, sweeps and pooled sensitivity have no 1m stream and now REFUSE rather than ranking a primary-only book against a baseline that has re-entries; and `mpc_bleg` had to pin it False, where an inherited True would have killed every B-LEG lab run on a NotImplementedError.** ✅ 6 new tests — **the cap watched RED against HEAD, and the three that could not be (they pin rules that predate it) proven by MUTATION**: a lifetime latch, a merged stop-out latch, and a stop-out rule gated on the preference each turn one red. 191 strategy + 341 backtest green. **The standing lesson is about defaults reaching further than the feature: turning this on did not just change a number, it made two unrelated code paths wrong — one silently (the sweep) and one loudly (the fork) — because a default is read by every caller, including the ones that cannot honour it.** Earlier: 2026-08-06 — ✅ **THE A+ PARITY GATE IS GREEN AGAIN, AND THE THREE-DAY RED WAS NEVER THE ENTRY RULE.** `compare_strategy.py` failed at bar 11031 with Python resting at fib 0.702 (4990.02) and Pine on a gap edge (4965.73) — which reads exactly like the two sides taking different branches of the entry model. 🔴 **`_fib_snap` is line-for-line identical on both sides; the gap Pine rested on did not exist in Python at all.** Dumping the live gap list found Pine holding a sixth gap, bearish `[4965.73, 5060.25]` born 143 bars earlier, which Python had FIFO-evicted and Pine had kept because it sits on an active EQH/EQL. 🔴 **The cause is `eqExemptFvg`, which DEFAULTED ON in `mpc_strategy.pine` on 2026-08-03 (`b1b461b`) while `backtest/replay/EngineStack` built no EQ engine and passed no levels to the FVG engine at all** — the coupling could not fire on the Python side even in principle. 🔴 **And no `cfg_` column carried the input, so the gate diffed two different strategies and blamed whichever code the symptom landed in.** The Pine's own comment block eight lines above the input still read *"THE EXEMPTION DEFAULTS OFF HERE"* and warned that neither the port nor the export modelled it: the default was flipped and the warning was not. **Fixed in four places in one commit** — the stack builds an `EqualHighsLowsEngine` and feeds its levels to the FVG cap; the FVG engine's cap now counts ORDINARY gaps only (it was still on the self-cancelling SWAP rule the Pine fixed on 2026-08-03); this bot pins `eq_exempt_fvg=True` and `mpc_bleg` pins it False; and both export Pines plot **`cfg_eq_exempt`**, which the harnesses configure from. ✅ **GREEN at warmups 100 / 500 / 1000 / 2000, and NON-VACUOUSLY** — that export ran the live `exec_min_stop_val = 0.08` and the time stop at **4 hours**, which closed **12 of its 26 trades**, so the clock lever is parity-validated too; `--eq-exempt off` reproduces the original bar-11031 mismatch exactly, so the fix masks nothing. `compare_bleg.py` exit 0 at 100 / 800 / 2000. ⚠ **The previous diagnosis in this file was WRONG and is kept, labelled wrong**: it blamed `cfg_min_stop_val` going 0.30 → 0.08. The 0.30 export really is green and every 0.08 export really is red, but that is export TIMING — **two changes landed days apart and the visible one got the blame.** Forcing the Python floor across 0.0 / 0.05 / 0.08 / 0.10 never moved the diverging bar, which should have been read as *the floor is not involved*. ✅ **The coupling is heavily EXERCISED and changes no trade, and both halves had to be measured:** over 155,531 M15 bars, 155,145 hold an active EQ level, **92,984 hold an EXEMPT gap and 20,546 hold MORE than the cap of 7** (max 12 at once — the same maximum the Pine commit measured independently), yet A/B gives **159 trades / +142.18R / maxDD 5.61R either way with an identical entry set**. It moves the RESTING LIMIT on **463 bars (0.30%)**, sometimes creating an edge where there was none, and not one became a different fill. ⚠ **Do not restate that as "it does nothing"** — the exercise counts are what make it a measurement rather than an unentered branch, and it is one window on one instrument. ✅ **The time-stop sweep was RE-RUN and the table is corrected** — it was stale twice over (the one-bar force-close fix and this coupling) and **neither moved it**: every row shifted by ≤0.05R, trade counts, cut counts and the 24h–40h plateau unchanged, so 36h stands. ✅ 6 new tests **watched RED against the un-wired stack, the un-pinned bot, the old swap cap rule and the dropped B-LEG override**; a 7th pins the harness REFUSAL and is labelled as unfailable-before-the-fix (the refusal did not exist to fail). 197 strategy + FVG-engine tests green. **The standing lesson is this repo's own in its sharpest form yet: a trade-affecting input with no export column is invisible to the parity gate BY CONSTRUCTION — and the gate does not go quiet, it goes WRONG, accusing whichever code the symptom happens to land in.** `execRunnerTrail` (2026-07-26) and `cfg_min_stop` (2026-07-30) were the same shape and cost nothing because they were caught immediately. This one cost three days and a misdiagnosis, and the missing column was for an input somebody had ALREADY written the warning about. **A comment saying "this defaults OFF" is not a guard; the column is the guard.** Earlier: 2026-08-06 — 🔴 **THE MINIMUM-STOP GUARD IS ON BY DEFAULT NOW — `"% of price"` 0.08 — AND THE SHIPPED BASELINE MOVED WITH IT.** Aaron's call, and it changes the number every other line in this file is measured against: **183 trades / +134.75R → 181 / +136.75R** over 7.9 years. `exec_min_stop_mode` had been `"Off"` since it was ported precisely so no historical result moved; **that protection is now spent, deliberately.** A run replayed at defaults from today refuses setups an older run took, so every A+ figure measured at `"Off"` describes a different configuration — **pin the mode explicitly when reproducing one.** **MEASURED: 23 configs over 186,220 M15 bars (2018-09-13 → 2026-08-04), ONE REAL REPLAY EACH.** `% of price` 0.05 → 183 tr / +134.75R (refuses nothing) · **0.08 → 181 / +136.75R (+2.00)** · 0.10 → 176 / +132.92R (−1.84) · 0.15 → 165 / +109.47R (−25.28) · 0.30 → 130 / +87.10R (−47.65) · 0.50 → 93 / +35.84R (−98.92); `Fixed $` 1.25 → 180 / +137.75R (+3.00), $5 → −25.34R, $25 → −114.00R; `x ATR(14)` 0.30/0.35 → +0.00, 0.50 → −4.72R, 1.0 → −9.29R. ⚠ **Every row is a REPLAY, not the baseline with rows deleted** — one position slot means a refused setup frees the slot and the trade list reshuffles downstream (the queue effect Run 12 measured), so no arithmetic over a finished trade list can produce these. The naive "delete the refused trades" answer for 0.10 is **+1.84R**; the real one is **−1.84R**, i.e. the right sign is the opposite of the cheap estimate. ⚠ **A small floor GAINS R, mechanically rather than luckily: the three tightest stops in 7.9 years — $1.03, $1.06, $1.18 — were all full −1.00R losers.** Fixed $1.25 refuses exactly those three and gains exactly +3.00R. The distribution says why they are outliers: median stop distance is **$8.88**, 25th percentile $4.59, and the tightest ever is 0.0581% of price. ⚠ **DO NOT read +2R as an edge.** `backtest/tools/jitter_audit.py` measured this strategy's run-to-run spread at **sd 15.06R**, so 0.05 through 0.08 are statistically indistinguishable from zero and from each other. **0.08 is chosen as the HIGHEST value that does not start costing — the most protection for nothing. A SAFETY choice, not a profit one**, which is the same standing this guard has had since Run 7. ⚠ 🔴 **`"x ATR(14)"` IS THE WRONG TOOL FOR THIS HAZARD, and it was measured rather than assumed — this overturns the intuitive answer.** ATR looked best on cost alone (three free rungs where the other modes had one) and it adapts to volatility, which sounds right. But at 0.35 and 0.40 **it never refuses the $1.03 stop at all**, because that bar was quiet and $1.03 was not tight *relative to ATR*. The hazard is `qty = risk / stop_distance` — **pure price units, with volatility nowhere in it** — so ATR blocks a different set of trades from the one at risk. It buys cheapness, not safety. ⚠ **Parity is proven with the filter FIRING but at 0.30, not at 0.08**: `compare_strategy.py` is exit 0 at warmups 100 / 500 / 1000 / 2000 on a 21,899-bar export where block code 7 was raised **213 times** (49 long, 164 short). Same code path, same `px * val / 100` floor, same refusal, same code — only the constant differs. **State it that way; do not claim 0.08 was itself diffed.** ⚠ **The FIRST export that day was also green and proved nothing** — it ran `"Fixed $"` 0.10 (a ten-cent floor on a $4,000 instrument) and raised code 7 **zero times in 21,897 bars**. **A green parity run cannot say anything about a branch neither side entered; before trusting a gate on a feature, check the feature was EXERCISED** — here a one-line block-code histogram over the export. Changed in lockstep: `config.py`, `indicators/strategies/mpc_strategy.pine` + its export mirror (defaults AND tooltips), `mpc_sos_fade.meta.json` (desc stays byte-identical to the tooltip), `algos/live/instance.template.json`, and the live bot's own instance config. `mpc_bleg` PINS `"Off"` and is unmoved — `compare_bleg.py` exit 0 confirms it. 157 strategy + 297 backtest tests green. Earlier: 2026-08-04 — 🔴 **RULE 3 IS A KNIFE EDGE, AND THE FIRST LIVE SHADOW DIFF MEASURED IT: FOUR CENTS OF FEED DIFFERENCE MOVED A RESTING ENTRY BY $10.12.** `exec_fib_nearest` rests on whichever of the two bracketing fib levels is NEARER the floating gap edge. That is a **discontinuous** choice, and until today nothing had measured how sharp the discontinuity is. `algos/tools/shadow_diff.py` compared the live bot's decision stream to a lab replay of the same 148 bars, and found `long_edge` diverging by **$10.08 on 25 consecutive bars** (2026-07-31 14:30-20:30, one leg). ✅ **The cause was ISOLATED, not inferred: both prices are rungs on the SAME ladder.** At that bar the ladder reads 0.618 = **4041.958** and 0.702 = **4031.841**, with identical anchors (ash 4116.39 / asl 3995.95) and an identical stage on both sides. The live bot rested at 0.618; the lab rested at 0.702. Same leg, same geometry, **different rung** — the two feeds differ by 4-5 cents (Vantage above PU Prime, systematically), and that was enough to flip which level was 'nearer'. ⚠ **It is a different TRADE, not a different price.** With the stop at 0.886 (4009.68) the two entries are a **$32.28 stop and a $22.16 stop — 46% apart**. The nominal 1R is identical, so nothing in an R-denominated backtest moves; **position SIZE, fill probability and the distance price has to travel all move materially.** **The consequence to carry: this bot's backtested FILL RATE is not transferable across brokers at the margin, and this is the mechanism.** Every number in this file was measured on Vantage; the live account is PU Prime. ⚠ **A CONSTANT price offset cannot cause this** — every level and every gap shifts together, so the geometry is unchanged. It is the small VARIATION in the offset (0.04 on some bars, 0.05 on others) that moves a gap edge against a fixed rung. **So do not test it by shifting the series; test it by jittering it.** ⚠ **How OFTEN the rung flips is UNMEASURED.** One leg in a 148-bar sample proves the mechanism and says nothing about the frequency. The honest test is a jitter replay over the full 6.5 years counting how many trades change; until that runs, treat the trade LIST as broker-specific even though the R is not. ✅ **Nothing was affected in the observed window** — no trade was taken, `l_stage` never exceeded 1 on either side, no stop was ever set. This is a measured sensitivity, not an incident, and rule 3 is not being questioned: it was measured at **165 trades / +126.68R → 161 / +135.94R** and that stands. ⚠ **This does not contradict the parity gates.** `compare_strategy.py` feeds ONE price series to both implementations, so it can never see this — it proves Pine and Python agree, which they do. **A green parity run says the two implementations agree, never that the result is robust to the data.** That is a third face of this repo's standing lesson. Earlier: **this bot can be charged the SPREAD and the OVERNIGHT SWAP now**,

Earlier: 2026-07-31 — 🔴 **THE BOT WAS RELYING ON AN ENGINE DEFAULT IT NEVER PINNED.** `engine_config()` pinned `fvg_max_count` and `fvg_require_close` but not **`fvg_threshold_pct`** — the minimum-gap floor, which decides which FVGs exist and therefore which entry edges exist at all. It was inheriting `backtest/replay/stack.py`'s `0.1`, which matches `mpc_strategy.pine`'s 15m floor **by coincidence, not by decision** (that shared default was flagged as "stale, harmless, every real consumer pins its own" — half of which was false). Proven load-bearing by removing it: `compare_strategy.py` failed on the FIRST compared bar. Now pinned explicitly, `stack.py` carries the engine default again, and the pin test asserts all four. **No number moves** — `compare_strategy.py --warmup 100` still exit 0 on the 2026-07-29 export, 529 tests green. See `## Engine-construction pins`. **The rule this sharpens:** *an engine input the decision stream does not export is a silent parity trap* already existed — what was missing is that it applies to an input a bot FORGOT to pin, not only to one whose default changed. Also this session: the session windows underneath this bot (`SessionEngine`, reached via `EngineStack`, feeding `recent_ssl`/`recent_bsl`) were re-synced to the mpc paste; this bot's Pine has had the new windows since 2026-07-12, so the Python had been running the OLD ones against it — parity stayed green through the change. Earlier: 2026-07-30 — **the MINIMUM-STOP GUARD is ported, closing the one known Pine↔Python

---

## The combined re-entry value (2026-08-21) — the two control replays that caught it

Moved out of `CLAUDE.md` under the doc-size rule. The RULES both of these produced live there, in
*Reclaim Entry*; this is the evidence behind them.


**Neither failure was found by a test.** The suite was green, the parity gate was green, and the
only thing that caught either was re-running the UNCHANGED configuration on the changed code and
finding it had moved.

**1. Which rule prices a side is the CONFIGURED TRIGGER's, never whichever block latched last.**
Section 3's 1-minute latch runs under EVERY trigger, including the two that have no 1m leg to price
off — that is shipped behaviour, because the latch moves `_l_leg`, which `_traded` / `_dead` /
`_used` all read. Keying the entry price off which block latched therefore let a 1m structure event
price a GAP book at a 38.2% retrace of a 1-minute leg. **The shipped book silently gained 4
re-entries and 4.9R.** Under the combined value the trigger cannot resolve it alone, so ownership
falls to **which precondition is open** — which is well-defined precisely because the gates are
disjoint. ⚠ **Do NOT gate section 3 behind a trigger test to "tidy" this.** It was tried twice; the
first attempt is the 4-re-entry drift above and the second is the next rule.

**2. A fix belongs in the half that has the problem.** The reclaim must not arm off a latch some
other block wrote — but guarding it at the GAP LATCH, by requiring the gap half's own precondition
there, **cost the gap half 7 of its 54 re-entries whenever the reclaim was switched on** (a latch
arriving later shifts the one-per-setup bookkeeping). The combined book was then not the two halves;
it was a third thing resembling both. The guard belongs in `_leg_ok`, where the reclaim asks its own
question — *has price actually come back through the level* (`_l_rec`) — instead of *did something
latch this side*. ⚠ **The general shape: when a shared structure needs protecting, protect it at the
READER that has the requirement, not at every WRITER.** Guarding the writers means every other
reader pays.

✅ **And rule 2 found a real defect rather than only restoring additivity.** Reading `_l_rec`
directly removed one reclaim re-entry that had armed at the deep edge **without price ever
reclaiming** — a 1-minute structure event had latched the side and the old test could not tell the
difference. Worth **+1.0R** (53 re-entries / +19.0R, from 54 / +18.0R). ⚠ **Every reclaim figure
quoted before 2026-08-21 evening is the pre-fix book** — 156.9R, not 157.9R.

**The verification, in full.** 350 strategy tests green (24 new); **11 rules each watched RED by a
named mutation**, each reddening only the tests that name it. Two mutations reddened NOTHING first
time and both were test defects rather than harness noise — one test never looked at the bar where
the rule bites, and another sat behind a zone gate that blocked the mutated path for an unrelated
reason. ⚠ A third reddened nothing CORRECTLY (swapping two mutually-exclusive branches) and is kept
as the disjointness proof rather than deleted. ⚠ The harness itself had to be fixed twice: a killed
run left a mutation on disk and poisoned seven later verdicts, and an unasserted `replace` silently
dropped two mutations so it reported nine confident verdicts about eleven rules. **Both are the same
shape as the defects it was hunting — a check that cannot tell its own damage from the code's.**


---

## The short-hold variant (2026-08-24)

**The question.** Aaron: *"I'm looking for more intraday trades where I don't have to worry about
swap because our trade captures some R and gets out."* The runner is built to hold; he wanted a
second way of trading the same setups that banks a small, fixed number of R and closes.

**Where it started.** `miss_audit.py` counts the setups that reach the 0.5-0.886 band with every
confluence present and no fair-value gap to rest a limit on: **178** over 2020-01-01 → 2026-08-06.
The question was what those 178 were worth under a short-hold rule.

### What the reconstruction said, and how far wrong it was

`backtest/tools/nogap_scalp_audit.py` prices entries off fib geometry instead of running the order
layer, so a whole stop × target × breakeven × ladder grid is affordable. Its bar-walk was
validated against the engine's own answers first — the excursion it computes reproduces
`Trade.mfe_price` on all 158 A+ trades to 0.0000R, and two mutations were watched red (crediting
the fill bar's high to a buy limit; letting the stop fire on the fill bar, which killed a trade
the engine ran 316 bars for +9.98R).

The grid's verdict on the raw pool was unambiguous and negative: every fixed target from 0.5R to
2R loses at every stop level, and the first positive cell needs 2.5R. Median best excursion 0.54R
against the A+ book's 1.40R; 84% stopped out against 61%. **At 5R the two pools are identical
(16.4% vs 15.2%) — the gap buys the first two R and nothing past it, which is exactly the region a
short hold lives in.**

Two filters then made it look tradeable: an order block in the zone (92 of 146, reaching 1R 44.6%
against 25.9% for the 54 with nothing) and excluding 10:00-12:00 New York. The best cell read
**102 trades, +32.7R**.

🔴 **That +32.7R did not survive the order layer. The real replay of the same idea made −6.6R.**
Three pieces of the reconstructed rule were not settings — the limit at the 0.5, the fixed R
target and the hour window — and the fourth difference was the pool: the block leg stands down on
any setup a gap ever qualified for, so it is not the same 178. **A reconstruction that is
validated on its excursion arithmetic is still not validated on its conclusion.**

### The order-block leg, which existed all along

The best surviving idea turned out to be a shipped setting nobody had run: the point-of-interest
source that rests on an order block only where a gap setup would not have traded. Replayed against
the shipped bot on an identical basis (`backtest/tools/ob_leg_replay.py`):

| | trades | total R | R/trade | worst DD | med hold |
|---|---|---|---|---|---|
| A+ shipped | 158 | +130.8 | +0.828 | −6.0R | 7.0h |
| block leg, shipped entry model | 134 | −6.6 | −0.049 | −23.2R | 2.5h |
| block leg, best config found | 109 | +22.5 | +0.207 | −13.7R | 2.0h |

⚠ **One lever in that search did nothing and it was not the lever failing.** The shallow-snap
setting sits behind the "nearest fib either side" setting, which ships on and overrides it, so
switching it on alone produced a byte-identical run. **A lever behind another lever reads exactly
like a lever that does nothing.**

⚠ **The +22.5R is not stable.** +34.6R over 2020-2023 and −12.0R over 2024-2026.

### Does it fill the main leg's drawdowns? No.

`backtest/tools/drawdown_fill.py` asks the question total R cannot: does a second leg put equity on
the board while the first is bleeding. The timing looks ideal — monthly correlation **−0.09**, and
+23.3R of its +22.5R lands in the 32 months A+ was down. It still does not help:

| | end | worst drawdown | days under water |
|---|---|---|---|
| A+ alone | 2590x | −50% | 1813 |
| + the leg at 1% | 3155x | −51% | 1971 |
| + the leg at 2.5% | 3871x | −56% | 1920 |

**At every weight the account spends MORE time under water, not less.** It is leverage, not a
hedge — an uncorrelated edge too small and too lumpy to fill a hole. ⚠ The one genuinely useful
result is the −0.09 itself: this repo lists "are two legs off one structure stream independent?"
as an open question, and over 76 months these two are.

### What was built, and what it measured

Three rules behind `exec_short_hold`, all defaulted so the shipped path is untouched. On the pool
it was built for: **104 trades, +10.4R, +0.100R a trade, −10.2R worst drawdown, and scratches down
from 33 to 1.** It does exactly what it was designed to do and still earns less than leaving the
pool on the A+ exits, because capping at 2R discards the tail that was carrying it. Sweeping the
target: 1.5R → +3.6R, 2R → +10.4R, 3R → +12.6R.

🔴 **The depth cap ships INERT because applying it lost money, reversing the recommendation the
field was built on.** Capping at 0.702 removed 5 trades and 2.1R. The split it came from was
measured under the fib ladder; the cap was applied under a fixed R target, and a deep entry's
short stop only matters while a breakeven ratchet can take it out. **A finding is scoped to the
exit regime it was measured in.**

### The tests, and the three that could not go red

36 tests, six mutations. Three killed their target immediately. **Three did not, and each was a
different way of writing a test that cannot fail:**

* *the target does not creep as the stop trails* — structurally impossible, the value is computed
  once at open and never recomputed. **Deleted rather than left passing.**
* *the variant never touches a re-entry* — passed against a build with the guard removed, because
  the re-entry's own branch runs next and overwrote the leak. **A test whose subject is masked by
  the following statement is testing that statement.** Rewritten with the re-entry on its fib rung.
* *the hour window does not borrow the final-hour label* — passed while only reading a lookup
  table it could not affect. Rewritten to drive the real gate.

### Two defects found on the way

🔴 **The Weekly and Daily bias requirements are DEAD.** Both read a field that is declared on the
signals dataclass with an empty-string default and assigned nowhere in the repo. Driven rather
than only grepped, over 2022-2023: "Ignore" 48 trades, "Must not oppose" 48 (a silent no-op),
"Must agree" **0**, "Must oppose" **0**. **It is an off-switch dressed as a filter** — and the two
settings that look like the safe ones are the two that stop the bot entirely.

⚠ **An audit reported "no order block in the zone on any of the 146 setups" and it was a false
zero** — the block engine is only built into the stack when the point-of-interest setting asks for
something other than gaps, so at shipped settings `obs_available` is False on all 155,807 bars. A
registry nobody populated answers confidently and wrongly, and the answer looked like a finding.
Fixed with a second replay whose only output is where the blocks were.

### Higher-timeframe trend filters were tested and do not help

15m, 1h, 4h, daily and weekly, structure engine on each, read off the last bar that had CLOSED
before the fill. Daily alignment is the best single split (48.1% reach 1R with it, 36.2% against)
and it still does not survive stacking: 102 trades/+32.7R → 48 trades/+10.9R, i.e. the win rate
rises and the return per trade falls. ⚠ **The 15-minute row is a tautology** — every setup is
"with the trend" because the shift of strength IS the 15-minute flip.

### The parity gate, run afterwards (2026-08-24)

The change was committed with the gate unrun — the exports on this machine were TRADE LISTS, not
the decision-stream export `compare_strategy.py` reads, and the commit message said so rather than
implying otherwise. Aaron exported the twin the same evening.

**Green.** `VANTAGE_XAUUSD, 15_80a5f.csv`, 21,162 bars, 2025-10-01 → 2026-08-24, shipped config
(`cfg_bits` 544375): **exit 0 at warmups 100 / 500 / 1000 / 2000.**

⚠ **What it does NOT cover, and this is the part worth keeping.** It proves the SHIPPED path is
bar-for-bar identical to the Pine — which is exactly the claim the change makes, since the variant
ships off. It proves nothing about the variant, and **no export ever can**, because the Pine has no
counterpart to those three rules and a diff needs two sides. The gate said the same thing about the
no-gap arm gate in the same run, unprompted. **A green gate is evidence about the branch it
entered.** The variant's own evidence is the replay table above, not this.

---

# The breakeven buffer becomes a FRACTION of the stop (2026-08-24)

**Aaron, on run `6e029942cb29`:** *"that thirty buffer … I don't think that would even cover
somebody trades cost. So in essence, I will be losing those trades. They won't be breakeven … we
need something that could really help capture traits and move traits out of breakeven. Like, even
capture something, a little bit of profit."*

## What was measured first, on the control run `5a5e2174d095`

XAUUSD.p M15, 2020-01-01 → 2026-08-23, PU Prime ECN costs charged, 243 trades. Every figure below
is recomputed from that run's own trade list, not read off a stored KPI.

| | |
|---|---|
| scratches (0.15R band) | 46 — **10 of them net losses** |
| round-trip cost per ounce | median **$0.020**, p90 $1.493, max $5.592 |
| trades costing more than the $0.30 buffer | **66 of 243 (27%)** |
| cost vs hold time | correlation **0.727** |
| median cost, held under a day | $0.020 · 1–3 days $0.82 · 3–7 days **$1.704** |
| first target distance from entry | median **1.098R**, minimum **0.310R** |

**Aaron's premise is right about the trades he was looking at and wrong about the typical one.**
Spread and commission are not the problem — the median round trip is 6% of the buffer. Overnight
financing is, and it swings the per-trade cost roughly **250-fold**, which is why no single fixed
distance can sit above it.

## The second finding, which the buffer sweep had hidden

The ten-rung sweep run the day before showed R falling as the buffer widened (159.1R at 30 ticks →
136.5R at 600). Counting how often the staged stop lands **at or past the rung that staged it**
explains it:

| fixed buffer | trades where the stop reaches the rung |
|---|---|
| $0.30 (shipped) | 0 of 243 |
| $1.50 | 5 (2%) |
| $2.00 | 10 (4%) |
| $3.00 | **24 (10%)** |
| $6.00 | **70 (29%)** |

Past that line the stop is not protecting the trade, it is closing it at a fixed small profit on the
next bar. **So a wide fixed buffer stops being a breakeven stop and becomes an exit**, and the
$3.00 rung recommended off the sweep's headline was already doing it on a tenth of the book.

As a fraction of the trade's own risk instead: **0.20R never once reached the rung across all 243
trades; 0.35R did on 5%; 0.50R on 24%.** That is where the default and the validation ceiling come
from.

## What was built

Five settings on `SosFadeConfig`, all defaulting to the shipped behaviour, so the OFF path is the
tick buffer unchanged. The mode picks one of three answers; the other four are read only when it is
not `"Ticks"`.

```
buffer = clamp_to_cap( max( fraction × frozen entry risk,
                            accrued cost + margin × frozen entry risk ) )
cap    = exec_be_cap_pct % of the entry → nearer-rung distance
```

`_accrued_cost_price` converts `_costs_usd` (plus the exit side's commission and half-spread, which
have not been charged yet) into a price distance on the size still open. It skips the spread under
modelled bid/ask fills, mirroring `_charge_spread`'s own early return — the cost is in the fill
prices there, and counting it would bill it twice in a different currency.

**The conflict case is a REFUSAL, not a clamp.** On a trade whose accrued financing alone is past
the cap there is no price that both covers cost and stays under the rung; `_be_buffer` returns
`None` and `_current_stop` holds the frozen entry stop. Staging anyway would be a stop labelled
breakeven that guarantees a loss, which is the defect the whole change exists to remove.
`exec_be_cost_conflict = "Clamp to cap"` is the measurable alternative and is not recommended.

⚠ **A conflicted LONG stays conflicted for the rest of its life** — the cap is fixed and accrued
cost only grows. A short can recover, because gold's swap is a credit to the short side. Stage 2 is
untouched either way, so the second rung still lifts the stop and hands it to the trail.

## 🔴 Run 17 said DO NOT BUILD THE SWAP-AWARE VERSION, and this is the re-read it asked for

Run 17 (2026-08-11) rejected a stop that moves at each rollover by the swap just charged, and closed
with *"NOT BUILT. Do not build it without re-reading this row."* Read, and both halves of it still
stand:

- **Its mechanism objection applies here too.** Only overnight positions pay financing, and the
  overnight positions are the runners — so a cost floor moves the stop on exactly the trades the
  buffer sweep says to leave alone. **The cap is the difference**: Run 17's version had nothing
  stopping the stop reaching the target, and this one cannot pass `exec_be_cap_pct` of the way
  there. That bounds the damage; it does not reverse the direction.
- **Its ceiling still binds.** Run 17 put the most a stage-1 ratchet could recover at **+2.11R over
  6.5 years**, against this strategy's **15.06R** run-to-run jitter. Nothing measured since moves
  that. **The cost-covering half cannot be justified on return** and should be argued, if at all,
  on the 10 genuine losses being mislabelled as breakevens.
- **What is genuinely new is the FRACTION half**, which Run 17 never asked about: it swept the
  buffer's SIZE and never its SHAPE, so every row in its table is one distance applied to trades
  whose first target sits anywhere from 0.310R to well past 1R away.

⚠ **Read the fraction half and the cost half as two separate questions.** They ship under one mode
each precisely so a sweep can separate them.

## What has NOT been done

✅ **The sweep was done the same day — ten rungs, and every one loses. See Run 26 in
`mpc_sos_fade_optimization.md` for the full tables, run ids and basis.** Headline: best variant
**+150.8R against the control's +159.1R** with a worse drawdown (47.91% vs 46.79%); no rung beat
doing nothing on either column. The 8.3R gap is inside the strategy's **sd 15.06R** run-to-run
spread, so the best case is *"not measurably worse"* rather than *"better"*.

🔴 **And the sweep found a dead branch in this very build.** The two runs differing only in
`exec_be_cost_conflict` are **trade for trade identical** (`8088d3411b5e4449`, 246 trades). The
accrued cost never reached the cap on any trade in 6.5 years, so that setting has never made a
decision on real bars — its tests construct the conflict artificially. **A branch proven by tests
alone is exactly what rule 9 is about, and building a setting before sweeping it is how you end up
shipping one.**

⚠ **Mid-sweep this session asserted a monotonic drawdown on four points and the fifth falsified it**
(`frac 0.35` at 53.96% is worse than the wider `frac 0.50` at 49.74%). Total R *is* strictly
monotonic across the plain-fraction ladder; drawdown is uniformly worse than control but noisily
ordered. **Declaring a trend before the ladder is full is the error, not the trend itself.**

✅ **PARITY GATE RAN AND PASSED, 2026-08-26.** Aaron supplied the decision-stream export the same
week; `compare_strategy.py "VANTAGE_XAUUSD, 15_6fb2a.csv"` gives **exit 0 at warmups 100 / 200 /
500 / 1000 / 2000** over 21,259 bars from 2025-10-01. **Rule 22 is satisfied for this change.**

⚠ **A pre-existing red sits below the warm-up boundary and is NOT this change.** At warmup 0 the
gate fails at bar 16 (`px_s_stage` py=1 pine=0); green from warmup 50 on. The identical failure —
same bar, field and values — reproduces on the code from before this change, run in a throwaway
worktree at `1ff36e4^`. **Recorded rather than retired**: it is somebody's open question, just
provably not the breakeven buffer's.

⚠ **The green covers the shipped path only, and the harness said so itself.** The five new fields
have no Pine counterpart, so the export runs them at their off position — nothing here tests the
fraction or cost modes. The harness separately warned that the no-gap arm branch was never entered,
because this export ran with Require-FVG ON.

⚠ **No Pine counterpart**, so even with an export the gate could never configure a non-default run
of these five fields — the Python-only-field hazard this file already records for the no-gap arm
gate and the POI source.

**TESTED:** 21 new tests in `tests/test_be_buffer.py`, **21 of 21 watched RED** by 18 mutations
(harness: `mutate.py`, scratchpad). 466 strategy tests green.

### 🔴 One of the 21 was VACUOUS on its first pass, and the reason generalises

`test_fraction_mode_measures_risk_off_the_frozen_stop_not_the_live_one` asserted that the buffer
reads `_sl` rather than "the live stop". **No mutation could redden it, because `Execution` has no
live-stop attribute** — the bug it described is not one the code can express, so the test was
describing a system we do not have. It was replaced by one pinning a source the code CAN reach
(`_max_fav`), which dies when a mutation points the risk at it.

**A test that cannot go red is not a weak test, it is a claim with nothing behind it** — and this
one would have read, forever, as proof that a hazard had been considered.

---

## The stop that never moved, and the sweep that said leave it alone (2026-08-25)

**Aaron, reading the 2020-11-04 re-entry short:** *"so wait we were up so much money and we just
leave SL at its original SL? that is dumb."*

He was right about the mechanism and wrong about the fix, and both halves are worth keeping.

### The defect he found is real

**The stop's ONLY trigger is a rung TOUCH.** `_advance_stage` moves the stage when price reaches
a ladder rung; nothing else moves it. So a trade can run a long way in profit, turn around, and
pay the full loss with the stop still sitting where it started.

MEASURED on the 2020-11-04 re-entry short (run `ed21fca08a91`): best price **1.016R in profit**,
nearest rung at **1.25R**, stop never left `1912.55354`, full loss.

⚠ **It survived in the shipped configuration only by accident.** The flipped ladder that session
started out investigating put a rung at 0.757R on that trade, and that rung is the only reason it
banked anything at all. **A ladder defect was load-bearing for a stop that had no other trigger.**

### The fix generalises the reclaim's arm to every trade

Two settings, both off by default. The first says how far the trade must go, as a multiple of its
own entry risk, before the stop moves at all. The second says how far the stop then moves — all
the way to breakeven, or leaving a share of the risk in the market.

Design points that are decisions rather than details:

- **Latched.** `_max_fav` is RESTORED state, and a stop that can un-ratchet is a trade that can
  lose after it was protected. The flag is in `_POSITION_FIELDS`.
- **Read against the FROZEN entry stop** (`_sl` at entry), so the trigger cannot creep upward as
  the stop ratchets. ⚠ Unlike `exec_rec_be_r`, this is NOT equivalent to reading the managed stop:
  the reclaim's only ever runs with the latch clear, while this one shares its trade with the rung
  ladder and a staged stop can already have moved.
- **Applied LAST in `_current_stop()`.** Every branch above it is a stop a touched rung has already
  staged, and each of those is at least as tight. Reaching the new branch means nothing has fired.
- **It can only TIGHTEN.** The keep fraction is clamped below 1.0, so the armed stop always lands
  strictly between the entry and the entry stop.

### 🔴 AND THE SWEEP SAYS DO NOT SWITCH IT ON

Six arms, one basis (XAUUSD.p M15, 2020-01-01 → 2026-08-23, PU Prime ECN with bid/ask fills,
commission and swap, commission 1.0/side, consistent sizing). Control is run `32f82feae4ee`.

| arm | run | total R | max DD % | PF | win % | scratches |
|---|---|---|---|---|---|---|
| **control (off)** | `32f82feae4ee` | **139.09** | **53.68** | 2.439 | 58.1 | 9 |
| 0.50R → breakeven | `0642367749d3` | 51.55 | 46.27 | 1.359 | 68.7 | 27 |
| 0.75R → breakeven | `59392c124e84` | 71.20 | 50.93 | 1.647 | 64.2 | 14 |
| 1.00R → breakeven | `d0374d7c31cd` | 99.92 | 49.06 | 2.047 | 63.3 | 11 |
| 0.75R → keep 0.5R | `5e63ae5398ec` | 108.12 | 60.21 | 2.089 | 52.2 | 8 |
| 1.00R → keep 0.5R | `f3e8bc41db50` | 118.99 | 55.50 | 2.300 | 54.7 | 8 |

**Not one arm beat the control, and the ranking is monotonic in how little it interferes.** The
best arm is also the one closest to doing nothing.

**The decomposition is the finding, not the totals.** Against the control, trade by trade:

| arm | trades rescued | trades destroyed | net | worst single case |
|---|---|---|---|---|
| 1.00R → breakeven | 17, **+17.07R** | 15, **−54.49R** | −37.42R | +16.48R → +0.35R |
| 1.00R → keep 0.5R | 15, **+6.80R** | 8, **−26.44R** | −19.64R | +5.47R → −0.50R |

🔴 **The give-back and the outsized winners are the SAME EVENT.** This book is carried by trades
that run, pull back hard THROUGH the entry, and only then go. Any rule that refuses to sit through
that pullback kills those trades first, at roughly three R destroyed per R rescued. The
2020-11-04 trade Aaron was angry about *is* in the rescued 17 — worth +1.35R, bought for 54.49R.

⚠ **Win rate rose from 58.1% to 68.7% at the earliest arm while the money fell by two thirds.**
That is the fingerprint of cutting winners, and it is why a win-rate improvement must never be
read as evidence on its own here.

⚠ **Protection did not even buy drawdown reliably.** The keep-half arm at 0.75R made drawdown
WORSE than control (60.21% against 53.68%). Only the arms that gutted the profit reduced it.

**Both settings are SHIPPED OFF and kept deliberately, with these numbers in their `desc` and a
`warn` on each**, so the next person to have this idea reads the answer instead of re-running it.

### The target floor is a separate dead end, kept the same way

`exec_sec_tp2_min_x` came out of the same session — a re-entry's two targets are priced by
different rulers (a multiple of the trade's own risk, and the frozen 15m fib), so nothing keeps
them in order and the second can land nearer than the first.

MEASURED over 6.5 years: control 139.09R against 140.64R / 140.29R / 139.79R / 137.10R at floors
of 1.5× / 2.0× / 2.5× / 3.0×. **Only 13 of 246 trades changed, each swinging about ±1R — noise.**

🔴 **And it is ACTIVELY harmful on the trade that started all this.** Pushing the second target out
on 2020-11-04 took that trade from **+0.348R to −0.907R**, because the flipped rung was the only
breakeven trigger it ever reached. **The flip is protective.** Shipped off.

**TESTED:** 13 new tests in `tests/test_excursion_arm.py`, all 13 watched RED by mutation. The map
was RUN, not reasoned:

| mutation | tests killed |
|---|---|
| arming never fires | 8 |
| arming ignores the trigger level | 2 |
| the armed stop is never applied | 6 |
| the keep fraction is ignored, always breakeven | 4 |
| a partial move takes the breakeven buffer too | 4 |
| the trigger is read off the MANAGED stop | 1 |
| it ships ON | 2 |
| the branch is lifted ABOVE the staged stops | 1 |

⚠ **Two mutations silently failed to apply on the first pass** — the anchor string appeared twice —
and produced blank rows that read exactly like "no test covers this". They were re-run with unique
context and an explicit edit-failed guard. **A mutation harness needs to prove it EDITED, or its
silence is indistinguishable from a passing test.**

### ⚠ Two process failures worth more than the result

🔴 **A sweep arm ran for 170 seconds, stored the right setting, completed normally, and replayed
the CONTROL's code.** `services/strategy_import.purge_strategy_modules()` drops
`strategies.python.*` from `sys.modules`, but sibling strategies do `sys.path.insert` then import
by BARE name — and those copies are never purged. **It was caught only by reading each arm's
stored ladder, not its headline numbers.** Every arm above therefore carries a trade-by-trade
comparison against the control, and the driver refuses to report an arm whose book is identical.
**Open — the stale-module hole is not fixed.**

🔴 **The backend destroyed two runs mid-flight and the second attempt looked identical to a
strategy that produced nothing.** `lab_db.reset_stale_runs()` runs at every startup and marks
EVERY `running` row `failed_crashed`, so any reload during a run kills it. Under `uvicorn --reload`
that is not a rare event. The run only completed on the third attempt, with a watcher recording the
server's process identity every ten seconds. ⚠ **The reaper is right to fire — the alternative is a
row stuck `running` forever — but a long sweep under a reloading server is not a safe place to
measure.**


## The second rung as a chosen distance (2026-08-25)


Aaron, reading the 2020-11-04 chart: *"I just want to find a better TP2 other than the 15-minute
level it was armed on — I don't even know what this means. TP2 should always come after TP1."*

**He is right about what it means, and the answer is that for a re-entry it means nothing
deliberate.** The second rung is a retracement level of the swing the ORIGINAL setup formed on —
a fixed price on the chart, fixed when the setup appeared. A primary enters where that ladder
expects and the rung is a real target: MEASURED on run `f3e8bc41db50`, 75 primaries took the start
of the move and 80 took the 38.2% mark, and **all 155 were correctly ordered**. A re-entry enters
somewhere else entirely, so the distance left to that same price is an accident of where it got
filled. MEASURED over the same run's 90 re-entries: the second rung lands between **0.27× and
3.66× the first rung's distance, median 1.47×, with 25 of 90 INSIDE the first rung.**

✅ **So `exec_sec_tp2_x` REPLACES it with a chosen multiple of the first rung.** The two are then
ordered by construction on every re-entry. ⚠ **It is not the floor above under a new name, and the
difference is direction**: a floor lets a distant fib stand and can only push a rung away, while
this overrides in BOTH directions — it also pulls IN the rung that ran to 3.66×, which is the half
a floor can never reach. Applied BEFORE the floor, so with both on they compose.

MEASURED 2026-08-25 on the basis above. Control `34ffef240698` reproduced the earlier control to
the penny with the field off, which is how the sweep knows the new field is inert when unset.

| multiple | total R | max DD | trades | |
|---|---|---|---|---|
| off | 139.09 | 53.68% | 246 | control |
| 1.10× | 142.83 | 47.95% | 246 | 15 moved |
| **1.25×** | **142.87** | **47.95%** | 246 | 15 moved — best |
| 1.50× | 141.09 | 49.02% | 246 | 14 moved |
| 2.00× | 140.29 | 50.67% | 246 | 16 moved |
| 2.50× | 139.79 | 51.11% | 246 | 17 moved |
| 3.00× | 137.10 | 51.11% | 237 | book DIVERGES |
| 4.00× | 136.55 | 52.85% | 235 | book DIVERGES |

🔴 **THE LAST TWO ROWS ARE A DIFFERENT BOOK AND MUST NOT BE READ AS A TRADE-FOR-TRADE COMPARISON.**
At 3× a re-entry on 2020-09-28 (trade 18) holds long enough to block the setups behind it, and every
entry after that point differs — 9 and 11 fewer trades. **With one position slot an extra hold does
not ADD to the book, it QUEUES in front of it**, which is the same effect this repo already
measured when loosening the entry filter. The 1.1×–2.5× rows all keep the same 246 entries and were
checked entry-by-entry, so those are clean.

⚠ **THE MONEY IS NOISE AND THE DRAWDOWN IS NOT — same verdict as the floor, reached independently.**
+3.78R over 6.5 years off 15 trades swinging ±1R each is fifteen coin flips. What does not look like
a coin flip is that **every arm tested cut max drawdown, monotonically as the multiple tightened,
53.68% → 47.95%** — and the floor sweep found the same direction on a different mechanism. Read this
as a drawdown lever, never as a way to make more money.

🔴 **AND IT COSTS THE TRADE THAT PROMPTED IT, AT EVERY SETTING TESTED.** 2020-11-04 goes
**+0.348R → −0.907R**, identical at 1.1× through 2.5×, joined by 2021-02-11 and 2020-12-28. The
mechanism is the one the floor already exposed: on a flipped re-entry the too-close rung is the ONLY
thing that ever arms breakeven, so ordering the ladder deletes that trade's only protection.
**Ordering the targets and protecting those trades are opposing goals, not one job** — the cheap way
to have both is still the one named above: sort the chart LABELS and leave the prices alone.

**Ships OFF.** TESTED: 15 tests in `tests/test_sec_tp2_level.py`, 6 mutations run and all killed —
the rule never firing, reading the raw fib instead of the replaced first rung, ignoring direction,
being applied after the floor instead of before, shipping ON, and the validation accepting anything.

---

## The dead-market floor (2026-08-26)

Rules live in `strategies/python/mpc_sos_fade/CLAUDE.md` → *The DEAD-MARKET floor*. This is what
happened and what it was measured on.

**Where the question came from.** Aaron asked for a smoother equity curve, having read that the
strategy showed far more open profit than it kept. Of 245 trades on run `c868358c5177`, **86 never
reached +0.5R and cost 67.6R between them.** Cutting that population by stop width, by hour of day
and by entry kind each looked good in aggregate and refused trades that carry the return. The one
cut that survived a per-year check was the volatility at the fill.

**The driver.** Lab runs are slow, so the sweep ran through a scratchpad driver reusing the lab's
own `_resolve` / `_build_config` / `_cost_profile` / `BarSource` / `build_strategy` / `run_dual`.
It was validated before anything it produced was believed: it reproduced lab run `5c35fc4081bf`
exactly — 245 trades, 119.0R, $4,855,242.72.

**Full replay, 2020-01-01 → 2026-08-23, one replay per row:**

| floor | trades | total R | ending balance | max DD | ulcer | wins |
|---|---|---|---|---|---|---|
| off | 245 | +119.0 | $4,855,242.72 | 55.5% | 20.8% | 134 |
| 0.08 | 240 | +127.9 | $9,769,875.84 | 47.9% | 17.2% | 136 |
| 0.09 | 235 | +111.5 | $9,920,480.96 | — | — | 132 |
| 0.10 | 227 | +114.4 | $4,915,629.94 | 41.5% | 18.6% | 126 |

0.09's drawdown is blank because it was only ever measured under the ordering bug below and was
never re-run. **0.09 books LESS R than 0.08 and MORE money**, which is rule 6 demonstrating itself.

🔴 **The first drawdown pass was wrong, and it took a deliberate look to notice.** The equity path
was sorted by `exit_index`. The trade list mixes two bar clocks — a 15m setup carries a 15m index,
a re-entry carries a fill-clock one — so the maximum index was 468,057 against roughly 155,000 15m
bars, and a 2026 setup sorted ahead of a 2021 re-entry. The tell was that number, not the output:
**the sum is order-independent, so the ending balance and the R total came out identical either
way.** It reported 51.5% at 0.08 where the truth is 47.9%. The sweep now refuses when any exit
timestamp is unpopulated rather than falling back to the index.

**The near-miss on the breakout-structure bot.** The gate was hung inside `_stop_clears_floor`
because two entry paths call it. `mpc_bos` overrides `_place_entries`, which read as *it cannot
reach this* — and it calls the shared floor check from inside its own placer
(`mpc_bos/execution.py:401`). Its own suite passed while silently acquiring a volatility filter
nobody had decided to give it. All three forks pin it off.

**What the 0.08 was not.** Aaron said *"set it to zero point zero eight, that's what I've been
using forever."* The 0.08 he has used forever is the **minimum stop distance** — a different
setting, already 0.08 as "% of price" on both sides for weeks, untouched here. Both are expressed
as a percent of price, which is exactly how the two get confused. It shipped at 0.08 for part of
the day and went back to 0.0 (off) once the switch existed on both sides.

**TESTED:** 10 in `tests/test_dead_market.py`. **71 pre-existing tests went red when the default
moved and none was a defect** — those fixtures feed two to four bars, so the ATR never seeds and
the gate refuses by design. They were fixed by having each declare `exec_min_atr_pct=0.0`, not by
teaching a fixture to fake an ATR.


---

# Moved out of `CLAUDE.md` on 2026-08-27

Dated RUN and BUILD write-ups, moved VERBATIM to keep the strategy's CLAUDE.md
readable. The standing RULES from each stayed behind there. Nothing was edited.


### The Custom stop level (`exec_sl_custom`, 2026-08-02)

Aaron's ask: *"let me enter a fib level as a stop loss outside of the predefined ones, as long as it
falls between 0 and 1 — 0.90 instead of 0.886."* The five-value dropdown had no answer, and a stop
is a PRICE, not a member of a set. `exec_sl_level = "Custom"` reads `exec_sl_custom` (a ratio in
(0, 1.0], default **0.886**) instead of a fiboP*.

**Where the price comes from.** `Signals` has carried `fibo_ash` / `fibo_asl` — the leg anchors the
fiboP* were built from — since `e2140c3`, with a comment naming this feature as the one consumer.
`_sl_anchor` feeds them to the canonical `engines.fibonacci.geometry.fib_level()`, the same helper
and the same IEEE-754 path the fib engine used, so **Custom 0.886 is bit-identical to picking
"0.886"** and switching the mode alone moves nothing. That equality is a test
(`test_custom_at_a_dropdown_value_is_the_SAME_price_to_the_last_bit`), on a bear leg too.

**Which half of the range this opens, and which half it must not.** 0.886 → 1.0 is the safe half and
the reason it exists: deeper stop, smaller position, more room before the setup is wrong — and it is
exactly the gap the ladder never covered. **Shallower than 0.886 walks straight back into Run 4's
hazard**, now reachable at any ratio rather than only at three: a stop shallower than the fill either
fails `dist > 0` (the order is cancelled, no trade and no tag) or leaves a tiny `dist`, and
`qty = risk / dist` balloons the position. Turn `exec_min_stop_mode` on first.

**An out-of-range ratio raises at construction, it does not fall back.** `SosFadeConfig.__post_init__`
refuses anything outside (0, 1.0] when — and only when — the mode reads it. The tempting alternative
was `_sl_anchor`'s existing shape (an unrecognised level falls through to fib 1.0), and that is the
wrong answer for a number a human typed: it would replay a whole backtest against a stop nobody
chose and report it as theirs. Validating only under `"Custom"` is deliberate too — the optimizer may
sweep `exec_sl_custom` behind a fixed mode, which is a wasted grid but not an error.

⚠ **NO PINE COUNTERPART, so a Custom run is unvalidated.** `mpc_strategy.pine`'s `execSlLevel` is an
`input.string` with five options; `compare_strategy.py` decodes `cfg_strcodes` into those five and
can therefore never configure a Custom run, which is also why parity is structurally unaffected by
this change. **A Custom result is a LAB finding, not a validated one** — port the input to the Pine
(a new `input.float` + a `cfg_` column + a `_SL_LEVEL` branch) before trading one. Note this is the
first lever in the exit ladder to be Python-first; every other one landed in the Pine first.

**In the lab:** the Stop level dropdown gains a "Custom" option and a numeric field appears under it
(`show_if`), the same pattern `exec_min_stop_mode` → `exec_min_stop_val` already uses. Because it is
a numeric field it is also a real **numeric optimizer axis** — sweep 0.88 → 1.00 step 0.01 and the
grid walks it, which a list of five strings never could.

**Why 0.886 is nonetheless the shipped default.** It is what Aaron trades, the 2026-07-27 parity
run went GREEN at it, and Run 6 rode it over the broker's whole intraday history (188 trades,
107.7R, 293x, −54.9% maxDD) with no degenerate stop. That is 0.886 being the SHALLOWEST point the
entry limit can itself rest at — the stop is just past the deep edge of the band, so the collapse
mode needs the entry to fill at almost exactly 0.886. **It is evidence of absence, not a
guarantee:** both defects below are still OPEN at this level, so treat a sudden outsized loss as
this hazard until proven otherwise, and turn the Pine's "Minimum stop distance" on for live use.

**The guard is now PORTED (2026-07-30) — it was the one known Pine↔Python divergence on the A+
pair, and it is closed.** `exec_min_stop_mode` / `exec_min_stop_val` in `config.py` (defaults `"Off"`
/ 0.10, matching the Pine), the floor applied at order placement in `_place_entries`, block reason
**code 7** ("Stop too tight") so a setup refused on PRICE is countable in the lab's Blocked layer
like every toggle refusal, and `cfg_min_stop` / `cfg_min_stop_val` columns in a regenerated
`mpc_strategy_export.pine` that `compare_strategy.py` decodes. See `### The minimum-stop guard`.

The four modes match the Pine exactly: `"Off"` (floor 0.0 — inert, so every historical result is
unmoved), `"% of price"` (self-scaling, the one Run 7 recommends at 0.10), `"Fixed $"`, and
`"x ATR(14)"` — the ATR being Pine's `ta.rma(ta.tr(true), 14)`, updated on every bar at the top of
`step()` rather than inside the entry branch, because a `ta.*` call that skips bars returns a
different number. **Turn it on for live trading**; leave it Off to reproduce a past run.

Measured consequence at `0.786` + 20 ticks
over full history: stop distance collapses to **$0.20** on 15m gold, `qty = risk / stop_distance`
builds a **39,033 oz (~$78M notional)** position, one bar takes **18× the intended risk**, and
equity ends at **−$63,726** — after which the bot stops trading entirely. Two defects behind it,
both still OPEN and both live-trading hazards:
1. No validation that the chosen SL fib is on the correct side of the entry, or a sane distance
   from it. Assume `mpc_strategy.pine` has the same exposure (same dropdown) until checked.
2. **No minimum stop distance.** `execution.py:329` sizes correctly —
   `qty = (equity * exec_risk_pct / 100) / dist` — so risk IS dynamic and a wider stop DOES give a
   smaller lot. The formula is not the bug. What it assumes is: `exec_risk_pct` is only the real
   risk **if the exit actually happens at the stop price**. That holds when the stop is wider than
   a typical bar (which `"1.0"` = leg origin always is) and fails completely when it is narrower —
   price gaps straight through and the realised loss is unbounded. At a $0.20 stop on 15m gold the
   nominal 10% risk was realised as **~180% in one bar**. So the guard needed is a floor on
   `dist` (e.g. ≥ some ATR multiple), NOT a change to the sizing math. A position/margin cap is
   worth adding as a second backstop, but it treats the symptom.

**This bot has no R:R dial.** Targets are fibs and the stop is a fib, so the risk-reward ratio is
an OUTPUT of leg geometry, never an input — no combination of existing parameters can express
"risk 1 to make 3". Answering that question needs an ATR-based stop distance + fixed-R targets,
which is new code here AND in the Pine. See Run 4's writeup for the two proposed routes.

**Every sweep of these levers is logged in `mpc_sos_fade_optimization.md`** — one entry per run,
with the full grid, per-year and per-half R, and whether it was adopted. Read it before tuning
anything here so a question already answered is not re-measured. ⚠ **Count them with
`grep -c '^# Run ' mpc_sos_fade_optimization.md`, never off this line** — it read "twelve" while
eighteen were filed. Only
1–7 are enumerated below (they are the exit-ladder work this section owns); 8–12 live in the log and
are summarised in the paragraph after the list. **Run 1 is ADOPTED (2026-07-27)** and **Run 8 is
SHIPPED (2026-07-28)**; every other run is measured and unadopted — Runs 1–3 on the same
185,530 M15 bars / 187 trades, Runs 6–7 on the full 185,668-bar history at 188 trades:

1. **TP split** (21 combos) — monotonic; best is `exec_tp1_pct=0, exec_tp2_pct=0` (100% on the
   runner) at 70.7R vs 47.9R for the shipped 30/40 split. **ADOPTED 2026-07-27 as the default**, in
   lockstep across `config.py` and both A+ Pine files. The tick-mode re-run this entry originally
   asked for was overtaken by better evidence: Aaron's own TradingView chart had been running the
   rungs at 1% each (the closest the input would take to 0) for the whole 2020-2026 Deep Backtest,
   so the setting has a real 162-trade out-of-sample record, not just a bar-mode sweep. Adopting it
   also FIXED a live hazard — see the `qty_percent = 0` guard note in `## The exit ladder`.
2. **The whole ladder** (525 combos) — re-confirms (1), and finds **both dropdowns are already at
   their best value**: structure trail beats every fixed step (best fixed = 62.5R), the trail
   buffer is nearly irrelevant (0.4R across 10→80 ticks), and `exec_tp2_stop_mode="One trail step
   behind"` is actively harmful (caps out at 42.3R). The TP split is the only lever with real
   variance: ~−2R per 10% moved off the runner.
3. **Stop TIMING** (35 combos, research-only dials — both moments are hardcoded in Python AND
   Pine) — **the shipped timing wins; nothing to adopt.** Delaying breakeven grows the average
   winner 3.7x (0.80R → 2.96R) but total R falls 25% and drawdown grows 3.5x, monotonically bad.
   **This settles the open question below about whether stop→BE on TP1 caps runners: it does not.**
   It converts full losses to scratches (avg loss −0.73R with it, −0.99R without) and that is worth
   more than the upside it forgoes. The biggest winner was +15.03R in all 35 combos — the trade
   that makes the money never traded against its stop, so this lever cannot reach it.
4. **Stop PLACEMENT** (40 combos) — **INVALID, discard the numbers.** Four of the five
   `exec_sl_level` values put the stop on top of the entry; equity ended at −$63,726. See the ⚠
   warning above — it is this run's writeup.
5. **"How do I cut the losers quicker?"** (2022+ cache, 118 trades) — **there is nothing to cut
   quicker with.** Both early-exit toggles measured at exactly zero effect (`exec_close_opp_sos`
   and `exec_htf_exhaust_only` each produced byte-identical trade lists), and a time stop would
   cut the WINNERS (all net comes from trades held past 20 bars). The diagnosis is the value:
   **every loss is a trade that never touched TP1**, and TP1 sits ~0.45R away while the stop sits
   1R away, so a losing trade dies a median 0.34R short of the level that would have staged it to
   breakeven. That makes this a stop-DISTANCE problem, not a stop-timing one. Re-running
   `exec_sl_level` on a clean window scored **59.3R at 0.786 vs 33.6R shipped at the same
   drawdown** — but 8 of its 108 trades reproduced Run 4's sub-$2-stop hazard, so it stays
   unadoptable. ~~The minimum-stop-distance guard is worth a measured ~+26R.~~ **That ~+26R figure
   is WRONG — superseded by Run 7**, which replayed the guard properly instead of filtering rows out
   of a finished trade list.
6. **"Cut trades early / block the losing pattern"** (2026-07-27; 8 years, per-bar R paths, ~40 cut
   variants + 10 entry blocks) — **the question is CLOSED, do not build it.** No loser runs straight
   to its stop (min MFE **+0.09R**, median +0.51R) and winners sit underwater just as deep (median
   MAE −0.36R), so the two populations are indistinguishable while the trade is live. Every cut
   family loses money. The −54.9% drawdown is a **losing streak at 10% risk**, not give-back —
   **risk % is the only lever that moves it.**
7. **The minimum-stop guard, measured properly** (2026-07-27; 17 real replays, three independent
   definitions: fixed $, % of price, ×ATR) — **it PASSES, at a MILD threshold only, as a SAFETY
   rule.** All three definitions agree: light (blocks 3–6 of 188 trades) = **+0.7 to +2.7R**;
   medium/heavy = **−12 to −39R**. Best is **`pct 0.1`** — the stop must be ≥ 0.1% of price
   (self-scaling, one line in Pine): 182 trades, **+2.5R**, blocks the −1.98R trade, and leaves
   2021/2024/2025/2026 **byte-identical**. Two cautions: the +2.5R is **noise-level** (ship it to
   close the hazard, not for the money — read sumR, never the ragged x-multiple), and it does
   **NOT** fix drawdown (−54.9% → −54.3%). **Not adopted — awaiting Aaron's go.** The follow-up it
   unblocks: re-run Run 5's `exec_sl_level` sweep with the guard installed, to see whether 0.786
   becomes adoptable.

**Runs 8–12, in one line each** (full write-ups in the log; do not re-measure any of them):
**8** the runner-exit space — **SHIPPED**, `"Structure + % ratchet"` at 1.0%, run-capture 43% → 53%
on the same 164 trades at identical % drawdown; every tightening family lost 60–90%. · **9** banking
at the extension fibs — **REJECTED in every form** (109.3R → 69.1R as rungs, 56.1R as a stop floor,
106.3R as deep rungs); 11 trades past −0.618 carry 106R of the 109R, so any fixed ceiling caps
exactly what pays. · **10** cutting by the SHAPE of the path — in/out-of-profit is **not** a loss
signal (32% base rate), the 0.886 fib cut fires zero times and 0.786 costs −27.0R; only a "no +0.15R
by bar 3 → close" stall cut is mildly positive (+4.8R) and it does not move drawdown. · **11** the
`exec_sl_level` sweep re-run WITH Run 7's guard — **`exec_sl_level` is settled at "0.886"**; 0.786 is
105.2R unguarded / 49.0R guarded, and 0.702/0.618 detonate. The one improvement is `0.886 + pct 0.1`
(112.0R, maxDD 54.3%, worst trade −1.98R → −1.00R), which independently confirms Run 7. · **12** *can
this strategy trade MORE?* — **no, not from inside the entry rule.** Dropping the FVG requirement,
sizing those extras smaller, deepening the entry and loosening which gaps qualify are all negative
or noise (see the ⚠ block in `## The missed-setup watch`), and the final-hour rule costs ~0.4R over
6.5 years so it stays on. **Trade count is a PORTFOLIO property here** — with one position slot every
marginal setup displaces a real one, and sizing UP trades already trusted beats adding new ones
(shipped book at `exec_risk_pct=12.5` = 832x @ 64.2% DD vs 426x @ 64.9% for the loosened book).


## The 2026-07-26 exit-lever sync

`mpc_strategy.pine` gained a structure-based runner trail, a TP2 stop-floor dropdown, an SL fib
dropdown and three setup toggles. Ported here, with the Pine's defaults adopted verbatim:

- **New config fields** — `exec_runner_trail` (**"Structure (swing)"**), `exec_struct_trail_buf_tk`
  (20), `exec_tp2_stop_mode` ("TP1 price"), `exec_aplus` (True), `exec_bleg` (False here, True in
  `BLegConfig`), `exec_fvg_50` (False). `exec_sl_level` already existed.
- **`signals.py`** — `Signals` gained `last_conf_high` / `last_conf_low`, passed straight through
  from the structure snapshot. Only `_advance_stage` reads them, and only past TP2.
- **`execution.py`** — `_trail()` gained the structure branch; the stage-2 floor moved out of
  `_current_stop()` into `_stage2_floor()`. Both anchors are snapshotted at the bar's CLOSE, the
  same one-bar delay `_max_fav` already had, because the stop placed at bar N's close is what bar
  N+1 trades against. Reading the live swing instead would silently make the trail clairvoyant.
- **`exec_fvg_50` is NOT ported** (same standing as `exec_conf_sz`) — `compare_strategy.py` refuses
  an export taken with it on. `exec_bleg` on is refused too: those trades belong to `mpc_bleg`.

### PARITY GREEN 2026-07-29 (exit 0) — the ratchet build, at the shipped rungs

`compare_strategy.py "VANTAGE_XAUUSD, 15_7b2f3.csv" --warmup 100` → **exit 0**. 21,494 bars,
2025-08-31 → 2026-07-29. Green at warmup 200, 500, 1000 and 2000 too.

This clears the 2026-07-28 stale warning. Two things make it the run that was actually needed:

1. **It carries the ratchet through the export.** `cfg_exitmode = 20` — the tens digit is the trail
   method, and it went 2-way → 3-way when `"Structure + % ratchet"` landed. Plus `cfg_trail_pct = 1`.
   An export taken before that change would decode the ratchet as the plain structure trail and go
   green while silently comparing two different exit ladders.
2. **It was taken at `cfg_tp1_pct = cfg_tp2_pct = 0`** — what the bot actually ships. The previous
   green run and the 109.3R ratchet headline were both at 1%/1%, which is not the shipped config.

26 trades graded, **sum 30.29R** over the ~11 months. Note this is the TradingView window, not the
6.6-year MT5 window the 110.65R baseline and the extension-fib work were measured on — the two
numbers are not comparable and neither supersedes the other.

⚠ **Not covered by this run:** it was taken before the minimum-stop guard was ported, at the `"Off"`
default where the gate is inert. It therefore still describes the CURRENT build exactly (see below —
Off is byte-identical on both sides), but it says nothing about the filter itself.

### The minimum-stop guard (ported 2026-07-30) — and what is NOT yet proven

The parent Pine had `execMinStopMode` / `execMinStopVal` and the Python did not. That was the one
known Pine↔Python divergence on this pair, and it was the dangerous kind: the export carried no
column for it, so `compare_strategy.py` would have gone GREEN while the Pine refused setups the
Python took. Closed in one pass:

| where | what changed |
|---|---|
| `config.py` | `exec_min_stop_mode` (default `"Off"`) + `exec_min_stop_val` (0.10) |
| `execution.py` | `_update_atr` (Pine `ta.atr(14)`), `_min_stop_floor`, `_stop_clears_floor` / `_stop_is_tight`; the floor gates both `_pend_long` and `_pend_short`; block reason **code 7** |
| `mpc_strategy_export.pine` | REGENERATED off the parent (body now byte-identical again apart from line 29's title) + `cfg_min_stop` / `cfg_min_stop_val` plots |
| `compare_strategy.py` | `_MIN_STOP` decode; **absent column ⇒ `"Off"`**, never the Python default |
| `mpc_sos_fade.meta.json` | both fields, with `show_if` on the mode (which needed `show_if` to accept a LIST of values — one enum, three ON states) |
| `mpc_bleg/config.py` | `exec_min_stop_mode` PINNED `"Off"` — that fork overrides `_place_entries`, so the floor never runs there and its Pine has no such input |

**At `"Off"` the two sides are byte-identical to what they were**, which is why the 2026-07-29 green
above still describes this build: the floor is 0.0, so `dist > 0 and dist >= 0.0` is the old
`dist > 0`, and code 7 cannot fire. 11 new tests pin that, both floor definitions, the ATR against
Wilder by hand, the precedence of code 7 behind a toggle refusal, and the decode.

⚠ **NOT yet proven: the filter ON, against a real export.** Everything above is unit-tested and
round-tripped through a synthetic export, which proves the two halves of OUR code agree — never that
they agree with TradingView (that is exactly the limit the B-LEG harness bug demonstrated). Before
trusting a run made with the guard on: re-paste `mpc_strategy_export.pine`, export at the mode you
intend to use, and re-run `compare_strategy.py` to exit 0.

#### The guard reaches the 1-MINUTE path too (2026-08-07)

The table above says the floor gates `_pend_long` and `_pend_short`. Those are the **15m** orders.
`_secondary_pending` — the fast-feed sniper's resting limit — asked only `dist > 0`, so from the day the
re-entry was built the shipped floor did not reach it. `exec_min_stop_mode` has been
`"% of price"` **0.08 since 2026-08-04**, not `"Off"`, so this was a live gap in a default run
rather than one waiting to be switched on.

It matters more on this path than on the 15m one, not less: `qty = risk / dist`, and a 1-minute
leg is a **shorter leg**, so its stop distance is smaller by construction.

✅ **MEASURED before it was written — two full replays, 186,366 M15 + 2,790,942 M1 bars, at the
shipped defaults.** The instrumented control reproduced the shipped book exactly (188 trades /
+165.46R / ddR 5.53 / 8 secondaries), which is what makes the delta attributable:

| | trades | R | ddR | maxDD | secondaries |
|---|---|---|---|---|---|
| control | 188 | +165.46R | 5.53 | 45.26% | 8 |
| floor on the 1m path | 188 | +165.42R | 5.53 | 45.26% | 8 |

**−0.04R over 7.9 years. All 180 primaries identical.** The refused trade did not vanish — a later
re-entry on the same setup took the freed slot 47 minutes on (+0.099R where the refused one made
+0.144R). That is the queue effect again, and it is why this was replayed rather than subtracted:
the same guard's cheap estimate on the 15m path got its **sign** wrong (+1.84R estimated, −1.84R
replayed).

🔴 **The honest size of the problem is ONE setup, and the first count of it was misread.** Over the
whole history **1,956 secondary limits were placed and 90 rested under the floor** — but a resting
limit is re-placed on every fill-clock bar, and all 90 are the **same limit at the same ratio (0.9848 of
the floor), one setup resting for 90 minutes.** Reading them as 90 near-misses would have been a
count of bars dressed up as a count of risk. Exactly one under-floor secondary has ever FILLED
(2024-12-02 20:08, a $2.08 stop against a $2.11 floor — 1.5% short).

⚠ **So the case for this is CONSISTENCY, not the measurement.** The history contains no instance of
the hazard the floor exists for; what it contains is one rule enforced in one of the two places it
applies. The sizing hazard on a shift leg is structural and unpriced either way — an absence over 8
years is not evidence it cannot happen, and the $0.36-stop re-entry that motivated the question
existed until `exec_sec_once_per_setup` removed it the day before.

⚠ **The floor reads `self._atr`, which is the FIFTEEN-minute ATR(14)** — `_update_atr` runs in
`step`, never in `step_secondary`. That is the right reading (the setup is a 15m setup and the risk
is budgeted against it) and it only matters under `"x ATR(14)"`; the shipped `"% of price"` mode is
a pure function of the entry price.

✅ 5 new tests in `tests/test_secondary.py`, **3 watched RED** against the restored `dist > 0`. The
2 that pass at HEAD are kept and LABELLED — they pin the direction the old rule already got right,
which is the direction a later "simplification" would restore. 196 strategy + 348 backtest green.

⚠ **The same pass found a test my own default flip had made vacuous the day before.**
`test_run_dual_primary_is_identical_to_run_when_secondary_off` built its config with
`SosFadeConfig()` and a comment reading *"exec_secondary defaults False"*. It ships **True** since
2026-08-07, so the test had quietly become a run of the secondary path — and it still PASSED,
because the synthetic fill-clock stream it feeds never arms one. It pins `exec_secondary=False` explicitly
now. **The lesson generalises past this file: flipping a default silently re-points every test that
relied on it, and the ones that keep passing are the ones you will not find.** When you change a
default, grep the suite for bare constructions of that config.

### PARITY GREEN 2026-07-26 (exit 0) — and the bug the run caught

`compare_strategy.py "VANTAGE_XAUUSD, 15_e8beb.csv" --warmup 100` → **exit 0**, bar-for-bar identical
on 21,130 of 21,230 bars (20,730 15m bars, 2025-09-01 → 2026-07-25). The export starts mid-history, so
the ~100-bar warmup is genuine engine cold start, not a mask: every warmup from 100 up is green and the
first mismatch at warmup 0 is bar 16.

The first run came back with ONE mismatch, and it was a real bug, not noise:

> `bar 20315 2026-07-12 23:00:00 px_edge: py=4100.94376 pine=None`

Python computed a short entry edge on a bar where the Pine had none. The fib matched to the decimal
(`dbg_fib_p2`/`p6`/`ash`/`asl` all identical), so it was an **FVG lifetime** difference: Python held a
bearish gap created on the first bar after the weekend gap that the Pine never created at all.

**Root cause — an unpinned engine input.** `mpc_strategy.pine` HARDCODES the middle-bar close-cleared
check in its FVG detection (`close[1] > high[2]` / `close[1] < low[2]`, lines 1686/1688). The
`fair_value_gaps` engine has that as the OPTIONAL `require_close` flag, defaulting **False** (it mirrors
`mpc_assistant.pine`, where it IS an input and IS off). Nothing exported it, so nothing caught it — the
engine happily created gaps whose middle candle never cleared the void.

Fixed by making it explicit rather than implicit: `EngineConfig` gained `fvg_require_close` (default
False, so no other consumer moves) and `MpcSosFadeStrategy.engine_config()` pins it **True**, alongside
the `fvg_max_count=7` and `show_internal=False` pins that were already there for exactly this reason.
`test_engine_config_pins_every_input_the_pine_moved_off_its_default` locks all three.

**The lesson is the class of bug, not the flag.** An engine input the decision stream does not export
is invisible to the parity check until a fresh export happens to disagree — and this one had been wrong
since the FVG engine made the gate optional on 2026-07-18. Any time an engine's default changes, check
every `engine_config()` that replays a Pine which does NOT share that default.

**What the new export columns immediately paid for:** they revealed the Pine was running
`execTp1Pct = 20` / `execTp2Pct = 20`, not the 30/40 defaults. Before this change no column carried
them, so the bot would have silently replayed 30/40 against a 20/20 Pine and the diff would have been
blamed on logic.

**The export had a real hole while this was in flight.** `execRunnerTrail` defaulted to Structure in
the Pine on 2026-07-25, but no `cfg_*` column carried it, so `compare_strategy.py` configured the
bot to the fixed-step fallback and diffed two different strategies. Any parity result from that
window is drift, not a bug. `mpc_strategy_export.pine` now carries `cfg_bits` bits 16384 /
32768 / 65536 (`execAplus` / `execBLeg` / `execFvg50`), `cfg_exitmode` (both exit dropdowns), and
one raw column each for the six exit numerics + the scratch band. An export WITHOUT `cfg_exitmode`
is pre-2026-07-26 and `compare_strategy.py` prints a loud warning rather than guessing.


### The 2026-07-22 re-sync (the export was 7 days stale)

`mpc_strategy_export.pine` was last regenerated 2026-07-15 and had drifted on three trade-affecting
Pine changes, so any diff it produced was July-15 drift, not a bug. Regenerated from
`mpc_strategy.pine` @ `361f007`:

1. **The veto is now SOS-aware** (Pine `longVetoA`/`shortVetoA`, ~3701). A divergence printing AFTER
   the SOS no longer vetoes its own setup — once stage 2 is live the setup is waiting on a retrace,
   and an opposing divergence formed during that retrace IS the pullback. Only one already live at
   or before the SOS bar still blocks. Extreme RSI keeps blocking LIVE. **Ported here**: the veto
   moved out of `SignalAdapter.update()` (which has no sequence state) into `signals.sos_aware_veto()`,
   which `execution.py` and `secondary.py` both call. `Signals` now carries the veto PARTS
   (`veto_on`, `veto_rsi_ob`, `veto_rsi_os`) instead of the finished `long_veto`/`short_veto`.
   The old, stricter rule is why a lab run can miss a long TradingView took.
2. **`execConfSZ`** — "Allow Sniper Zone as entry confirmation", a second accepted entry
   confirmation alongside the FVG. **NOT ported.** `config.exec_conf_sz` exists (default False) and
   the export packs it as `cfg_bits` bit 4096, so `compare_strategy.py` REFUSES an export taken with
   it on rather than diffing against logic this bot lacks. Port = read `BarState.sniper`'s
   0.5-0.618 pocket as an entry edge on any leg with no qualifying FVG.
3. **CONT trades removed** from the Pine — the export used to carry `contL_ok`/`contS_ok`.
4. **`execDeepFib`** (Method 3, added 2026-07-23) — "Floating gap → nearest fib shallower" (titled
   "Entry: deep gap enters on nearest fib (not gap edge)" until the 2026-08-02 label sync).
   A qualifying FVG whose NEAR edge (long = gap top, short = gap bottom) sits deeper than
   0.618 rests its limit at the nearest fib just SHALLOWER (0.618/0.702/0.786) — the level price
   reaches first — instead of chasing a gap edge price may never tap. **PORTED here**: `config.exec_deep_fib`
   (default **True** as of 2026-07-23 — see the prime-combo defaults note below), `execution._deep_fib_edge()`
   + the override in `_entry_edges()`, the export packs it as `cfg_bits` bit 8192, and `compare_strategy.py`
   reads it (no refusal — it is fully ported). ONLY the near edge's position decides it; what the gap body
   crosses is irrelevant (an earlier "body contains a level" gate was WRONG and dropped exactly the deep
   multi-level gaps this targets).

**Prime-combo defaults (2026-07-23).** Aaron's TradingView-tested "prime" settings are now the shipped
defaults in BOTH Pine files and `config.py`, in lockstep so `compare_strategy.py` parity holds:
`exec_arm_sweep` False→**True**, `exec_arm_div` True→**False** (arm on liquidity sweeps, not divergence),
`exec_fvg_deep_only` False→**True**, `exec_deep_fib` (new) → **True**. `exec_req_fvg` stays True. Combo
result on Aaron's Strategy Tester: ≈+237% / PF 6.2 / 85% win / 13% max DD over ~2yr gold at 84 trades.
This SUPERSEDES the old divergence-armed default — the "2-year run" analysis further down was measured
under that old default and predates Method 3 + deep-only; keep it as the historical baseline only.

**Slippage pinned to 0 in the Pine (2026-07-23).** Both `mpc_strategy.pine` and `mpc_strategy_export.pine`
now declare `slippage = 0` in the `strategy()` call, so the TradingView Properties tab defaults to zero
instead of Aaron's old 25-tick setting. Reason: for HONEST parity the Pine's `fill_model="bar"` (zero
costs) must line up with a TV run that also charges nothing, so `compare_strategy.py` and a hand
trade-diff compare like-for-like. Real costs belong in the LAB's `fill_model="tick"` run (real bid/ask +
spread + slippage + commission + swap), not smeared as a flat 25-tick charge on every TV fill. The
breakeven buffer (`execBeBufTk`, default 30) is a STRATEGY input and is unchanged — it is signal logic,
not a cost. So the old note that TV's number is "slightly PESSIMISTIC because TV charges 25 ticks" no
longer applies to a fresh export: at slippage 0 the TV bar-mode number and our bar-mode number are the
honest apples-to-apples pair; the tick-mode lab run is the real tradeable number.

**When the Pine changes:** brother re-pastes `mpc_strategy.pine` → regenerate `mpc_strategy_export.pine`
(re-copy + re-append the parity block) → re-export → re-run until exit 0. A new trade-affecting input =
a new `config.py` field + a new `cfg_*` plot + a new `compare_strategy._TOGGLE_COLS` entry.

**One-shot sync check:** `backtest/tools/verify_parity.py <export.csv> [more.csv ...]` runs EVERY parity
check (all nine engines + this strategy) whose columns are present in the CSV(s) and prints one
GREEN/RED/SKIP table with auto-detected cold-start warmup. It is the "is everything in sync?" command
to run after any re-paste; it reports drift, it does not fix it (a real logic change is still a hand
port). Engines are the foundation — sync them first (`/audit-engines`), then this strategy.


## The 2026-07-16 year run — what the numbers actually say

365d, 15m, XAUUSD.s, `exec_risk_pct=10`, $10k start. Both fill models, same 22 trades:

| | bar (Pine guess, no costs) | tick (real bid/ask + costs) |
|---|---|---|
| net | $11,525.41 (115.25%) | **$11,374.78 (113.75%)** |
| PF | 4.426 | 4.228 |
| win% | 72.73% | 72.73% |

Real fills cost 1.3%; **0 bars fell back to the guess**, so every fill is a real tick. TradingView's
110.19% on the same setup is slightly PESSIMISTIC, not optimistic — TV charges a flat 25 ticks of
slippage on every fill, and the real broker is better than that (the entry is a resting limit, which
never slips; only stops pay).

**TradingView's 66 trades = our 22.** Each `strategy.exit` leg (TP1/TP2/runner) is a separate closed
trade in TV's stats: 22 × 3 = 66 exactly, and the filtered 16 winners × 3 = 48 exactly. Net / return /
drawdown mean the same thing in both; **profit factor and average-trade do NOT** — splitting one
winner into three legs changes the ratio (TV 4.155 vs the real 4.426). Don't compare those two.

**The distribution is the real story** (`|R| < 0.25` = scratch):

| outcome | n | $ pnl | % of net | avg R |
|---|---|---|---|---|
| reached the runner (TP1+TP2 banked) | 8 | +12,510 | **110%** | 1.19 |
| TP1 only, rest stopped at BE | 8 | +2,389 | 21% | 0.19 |
| never reached TP1 | 6 | −3,524 | −31% | −0.42 |

The 72.73% win rate is arithmetically right and analytically misleading: **10 of the 22 trades are
near-scratch** (together +$749), six of the eight "TP1 only" winners made under $300, only 2 trades
lost a full R (the stop→BE rule converts most losses to scratches), and the **top 3 trades are 57% of
net**. The edge is the runner. Treat the win rate as a byproduct of the BE stop, not as the edge.

### The 2-year run (2024-07-16 → 2026-07-16, tick mode) — the shape HOLDS

> **⚠️ Pre-combo baseline (superseded 2026-07-23).** Everything in this subsection was measured under
> the OLD default (divergence-armed, gap-edge entry, no deep-only). The shipped default is now the
> deep-entry combo (sweep-arm + deep-only + deep-fib → ≈+237%/PF6.2/85%/13%DD at 84 trades). The
> numbers below still stand as the divergence-only baseline, but they are no longer the default's
> results. Read them as history, not as what the bot does out of the box today.

40 trades, net **$21,536.60** on $10k. The distribution is the same story with a bigger sample:

| outcome | n | $ pnl | % of net | avg R |
|---|---|---|---|---|
| reached the runner | 15 | +26,565 | **123%** | 1.13 |
| TP1 only | 12 | +4,032 | 19% | 0.16 |
| never reached TP1 | 13 | −9,060 | −42% | −0.45 |

What the second year of data changed, and what it didn't:
- **Win rate fell 72.73% → 67.5%** (27/40) and losers went 6→13 — the 1-year window was the kinder half.
- **Concentration improved**: top 3 = 45% of net (was 57%) — still above the framework's <60% floor
  but no longer resting on three trades.
- **Still 17 of 40 near-scratch**, and still exactly the runner carrying everything (123% of net).
- **Full-R losses scale with the sample** (2 → 5), i.e. the stop→BE rule keeps converting most losses
  to scratches; that behaviour is stable, not a one-year artifact.
- **The ~83% short skew (33 shorts / 7 longs) is EXPLAINED as of 2026-07-16 — it is not a bug.**
  The port is parity-green, so the Pine skews identically. Measured per-side over the same 2yr
  window (48,246 bars, gold +75%):
  - **Root cause — the arm-source filter.** The sequence arms on a sweep OR a divergence, but
    `exec_arm_sweep` defaults **False**: only DIVERGENCE-armed setups may enter. Bearish
    divergences outnumber bullish **142:73 (66%)** in an uptrend — price keeps making higher
    highs on weakening RSI, while bullish divergences need lower lows a bull market rarely gives.
    The skew is inherited almost entirely from that 2:1. Sweeps, by contrast, are near-symmetric
    (1,505 S / 1,308 L), and the raw structure is *dead even* — external SOS is **125/125**. So
    nothing upstream of the arm filter is asymmetric.
  - **Amplified by fib geometry.** Episodes reaching Stage 4 READY: **37 L vs 67 S**. After a bull
    SOS a long waits for a retrace to 0.5/0.618 — in a strong uptrend the pullback is too shallow
    to reach it (51 long episodes die at peak stage 2, vs 25 short), while the deep counter-trend
    rallies a short setup needs arrive reliably.
  - **The default filter is the profitable subset, and it is a strict SUBSET.** Every
    divergence-armed trade is also sweep-armed, so `both` is bit-identical to `sweep only`.
    Arm source → trades / short% / net / PF (bar mode, 2yr, no costs):
    divergence-only (OLD default) 40 / 82.5% / +190% / **3.27** · sweep-only (= both) 79 / 69.6% /
    +144% / **1.87**. Enabling sweeps adds 39 trades that lose money net and drags PF down ~43%.
  - **Longs are not broken, just rare** — 7 trades, **86% win**, profitable (+21% of capital).
    Nothing is blocking longs incorrectly; there simply are few bullish divergences up here.
  - **What to actually worry about is concentration, not the count.** Shorts carry **89% of net**.
    Every HTF bias filter is `Ignore` (`exec_htf_weekly`/`exec_htf_daily`), so this is an
    unfiltered counter-trend fade that shorted a +75% bull market and won at 70%. That is the
    claim needing a second regime to confirm — the direction split itself is now accounted for.

Open threads (Aaron is on the edge work as of 2026-07-16): ~~whether stop→BE on TP1 caps runners~~
(**ANSWERED 2026-07-26, Run 3 in `mpc_sos_fade_optimization.md`: it does not — it pays for itself**); and
why 15m is reportedly the only winning timeframe (a real edge usually survives on neighbouring
timeframes — if 5m and 30m lose, suspect luck). 40 trades is still a thin sample; treat the KPIs as
directional, not settled. (Superseded note: an earlier version warned "do not flip `exec_arm_sweep` — it
breaks parity". That was wrong on the mechanism — parity is driven by the export's `cfg_bits`, not the
default — and moot now: the default flipped to sweep-arm on 2026-07-23, in lockstep across both Pine
files and `config.py`, so parity holds. Flip toggles freely per run; just keep the two Pine files and
`config.py` defaults identical when you change a DEFAULT.)


---

# The explanations, moved out of `CLAUDE.md` on 2026-08-27

`CLAUDE.md` next to the code now carries the RULES and routes here; this file carries
the evidence behind them — the prose, the tables, the run numbers. Everything below was
moved VERBATIM and nothing was edited. Headings mirror the ones in `CLAUDE.md`.


## `mpc_sos_fade.meta.json` — labels and descs are SHARED WITH THE PINE (2026-08-02)

Every `label` in the meta file is byte-identical to that input's title in
`strategies/tradingview/mpc_strategy.pine`, minus Pine's leading `   ↳ ` indent marker. Every `desc` is that
input's tooltip **verbatim**. One parameter, one name, one explanation, two UIs.

**Change a label or a desc and change the Pine in the same commit.** Otherwise the lab and
TradingView start teaching different things about the same setting, which is exactly how the
old `exec_deep_fib` row came to be labelled "nearest fib ABOVE" — true for a long, wrong for a
short, and contradicting its own Pine tooltip four inches away.

The ONE allowed deviation is a suffix stating something true only of THIS runner: `exec_conf_sz`
reads "Allow Sniper Zone as entry confirmation **(not supported)**" in the lab, because the
Sniper-Zone entry is Pine-only and turning it on changes nothing on a lab run.

Verify with a diff, not by eye — the check is mechanical: pull every `input.*` title out of the
Pine, join on the field name, and compare. As of 2026-08-02 that is **42 of 43 shared params
identical** and **43 of 43 descs identical**.

---

**Last reviewed:** 2026-08-12 - the dated build narrative that used to sit here moved VERBATIM to `strategies/python/mpc_sos_fade/docs/SOS_FADE_BUILD_NOTES.md`. **Nothing was deleted.** It was 60,467 bytes in 2 paragraph(s), the largest 58,936 bytes on a single line, loaded in full every time anyone opened this area. Rules stay here; the evidence is one file away.



## 🔴 A BAR NUMBER IS LOCAL TO ONE RUN. THE ONE-TRADE-PER-LEG LATCH NOW KEYS ON TIME (2026-08-26)

**The bot re-entered a setup it had been scratched out of three seconds earlier.** Same fib leg,
same stop 4686.32356, same targets 4640.22772 / 4605.29, 0.53 lots. The latch that exists to stop
exactly that stored the shift bar's **NUMBER** — and a live bot renumbers every bar each time it
re-warms its history on restart. The restored latch held 5059; the same leg was now numbered
4953; no match; through it went.

**Tests: 8 in `tests/test_leg_latch_across_restart.py`, two mutations watched RED** — comparing
numbers only reddens the restart case; dropping the two persisted fields reddens the other.



## The name (renamed 2026-07-16 — was `mpc_aplus` / `MpcAplusStrategy`)

`MPC` = Mental Peak Consulting (Aaron's brother's company) and prefixes every strategy in the
house. The suffix names the **narrative** the strategy trades off the shared `engines/` — here:
a **shift of structure (SOS)**, faded. The old name described the *grade filter* it happens to
use, not what it does, and "A+" would collide the moment a second MPC bot also traded A+ setups.

**"A+" is still correct vocabulary and is deliberately kept** wherever it names the brother's own
Pine concept — the A+/B/C/D grade dropdown, the "A+ SETUP SEQUENCE" block this ports, and the
`aplus_window` config field (which mirrors the Pine input "Max time: sweep → SOS (minutes)" and is
a lab param-grid key). Renaming those would break the line-for-line traceability to the Pine, and
`aplus_window` is also an optimizer grid key. The Pine files themselves are NEVER renamed: they are
the brother's source and the parity reference.



## Sizing — this bot sizes ITSELF

`LAB_STRATEGY` declares `self_sizing: True`, so the command-center lab does NOT run its dynamic
sizing engine over this bot's trades. `exec_risk_pct` (Pine default **10%** per trade) IS the risk
knob: it is a normal strategy param, so it is editable in the Run modal and sweepable in the
optimizer grid — that is the "manual %" for this strategy, and the SIZING MODE control is hidden
because there is nothing for it to decide. Pair a run with the **Unconstrained (No Limits)**
ruleset to see the raw behaviour with no halts and no drawdown floor cutting a day short.

**Input range (2026-07-27):** the Pine input's `maxval` was raised **10 → 100** across all four
strategy Pine files at Aaron's request — the old 10 was an arbitrary UI cap, not a safety rule, and
`exec_risk_pct` in `config.py` never had one. The DEFAULT is still 10 on both sides, so no run
changes. Two things the raised ceiling exposes and neither side checks: the `margin_long/short =
0.2` pin means TradingView rejects (or partially fills) an entry whose notional exceeds 5x equity —
silently, as a missing trade rather than an error — and the **no-minimum-stop-distance hazard**
below scales linearly with the risk %, so a degenerate stop that realised ~180% of equity at
`exec_risk_pct = 10` realises the same multiple of whatever is typed here.



## `live_setups()` — what this bot is WATCHING, for the pre-trade signals channel (2026-08-13)

The `backtest/setups.py` contract, implemented here. `Execution._setup_context` freezes each
side's live watch every bar; `live_setups()` assembles it with the CURRENT resting order;
`drain_setups()` is what the live runner calls. Messages and volume:
`docs/LIVE_SETUP_ALERTS.md`.

**Three confluences, reported with the strategy's own words**: Arm (`Sweep · Day High`), Shift of
structure, Retrace zone (`0.5-0.886 tagged, FVG live`). Plus the tradeable ZONE (`fibo_p2` →
`fibo_p6`) and the stop projected off the deep edge through `_sl_anchor`, so `exec_sl_level` /
`exec_sl_custom` / `exec_sl_deep` resolve exactly as they would for a real order.



## The restart seam — `snapshot_position()` / `restore_position()` (2026-08-10)

`Execution` can write its whole open-trade state down and put it back. **It exists for
`algos/live/` and nothing in a backtest calls it** — the full design, and every refusal around
it, is in `algos/live/position_state.py`.

**Why it had to live here rather than in the live package.** A restart rebuilds this object EMPTY
from a warm-up replay, so the live bridge used to HALT on any position the broker already held and
the trade sat unmanaged until somebody looked — its broker stop stood, but nothing ratcheted it and
the time stop never fired. Putting the state back means writing ~30 private fields, and the live
package reaching across a subsystem boundary to set them would be a second, silent copy of what an
open trade IS. One method here is the honest seam, the same standing as the `account` / `leg` pair
above.



## The portfolio-account seam (2026-07-17)

`Execution.__init__` takes an injected `account` (default `SoloAccount`) and a `leg` name — the seam
for stacking this bot with others on ONE shared account (`backtest/portfolio/`). What changed:
`self.equity` now reads `account.balance` (the shared balance the bot sizes against); the leg-local
`_equity_realized` is kept for R. The fill gate in `_open_position` calls `account.request_fill`,
which **scales** the bot's own desired qty to the shared room (solo → full size); partial exits and
costs `book_pnl` onto the shared balance; the full close frees the reservation; each bar reports the
live stop via `update_stop`. **Parity is unchanged:** a `SoloAccount` grants full size always, so
`compare_strategy.py` stays exit 0 — re-verified on the 20,076-bar export after the seam landed. The
account scales the bot's qty rather than recomputing it precisely so parity holds (the bot sizes off
the limit price at placement, not the fill). Do not route qty computation through the account.



## What it is (one paragraph)

A counter-trend reversal that fades exhaustion at HTF liquidity. Three-stage A+ sequence: **Arm**
(liquidity sweep by default, or an RSI divergence) → **SOS** (a same-side external structure break in
the trade direction, inside a staleness window) → **Zone+FVG** (price retraces into the 0.5–0.886 fib
band and a live FVG overlaps it; default requires the gap fully past 0.5). Entry is a resting limit — a
deep gap re-prices to the nearest shallower fib (Method 3), else the FVG's near edge, clamped into the
band; stop = fib 1.0 (leg origin) + buffer; exit = the fib TP ladder (30/40/runner) with stop→BE on
TP1, stop→TP1 on TP2, and a ratcheting trail on the runner. Full rules: `docs/MPC_SOS_FADE_SPEC.md`.



## The five modules (the data flow)

```
BarState  --SignalAdapter-->  Signals  --SosFadeSequence-->  SeqState  --Execution-->  Decision
(backtest.replay)             (Pine-named inputs)          (A+ stages)               (orders + fills + R)
```

- **`config.py`** — `SosFadeConfig`: every trade-affecting Pine input toggle, same name + default
  (**toggle parity is a hard requirement**). Instrument facts (mintick, point value, close time) are
  Layer-B injections, also here. Cosmetic Pine inputs (debug labels, boxes, table styling) are
  deliberately absent — they don't touch a trade decision.
- **`signals.py`** — `SignalAdapter`: turns a replay `BarState` into the exact Pine-named globals the
  A+ block reads. Two reconstructions are non-trivial and must stay faithful:
  1. `recentSSL` / `recentBSL` — the most-recent swept pool per side, from ten per-source slots
     (H4 / Day / Asia / London / NY high & low) resolved by latest sweep bar, sessions suppressed
     once Day is filled. Rebuilt from the liquidity engine's `mitigated` / `evicted` events.
  2. `bullDivActive` / `longVeto` — recomputed WITH the structure-break staleness (`lastExtBreakBar`)
     the standalone RSI engine can't see. **Do NOT use the RSI engine's convenience `bull_active`** —
     it omits the stale check and would diverge from the Pine.
- **`sequence.py`** — `SosFadeSequence`: the Stage 1→4 state machine, retro-link (a late-confirming
  divergence adopting an SOS that already fired), sequence death (opposite SOS / TP3 / invalidation /
  continuation BOS), and the arm-source snapshot (which Stage-1 source was live at the SOS).
- **`execution.py`** — `Execution`: entry edge → resting limit → TP1/TP2/runner ladder → staged stop
  + ratchet → %-risk sizing → graded R, on a small broker emulator (`_Broker`-style) that reproduces
  the two TradingView fill assumptions logic parity depends on:
  1. **calc-on-close, one-bar delay** — an order placed at a bar's close is active only next bar (a
     resting limit never fills the bar it was placed; an exit never fills the bar the entry filled).
     **This is also a KNOWN BACKTEST LIMITATION, not a defect — see `### Wrong-side stop fills`
     below before reporting it as one.**
  2. **intrabar path** — when a bar covers both a TP and the stop, the open's proximity to the
     extremes decides which fills first (open nearer high ⇒ price travels open→high→low→close ⇒
     targets first; nearer low ⇒ stop first). **This is the single most parity-sensitive assumption
     — it is a GUESS until `compare_strategy.py` is exit 0.**
  Each closed `Trade` also carries **reporting-only excursion** — `mfe_usd` (favorable: the most it
  ever showed in profit) and `mae_usd` (adverse: the deepest it sat against us), tracked across the
  whole hold on bar high/low (`_ext_high`/`_ext_low`) and converted to USD at close. NO decision
  reads them, so they are parity-safe (`compare_strategy.py` diffs the `px_*` decision stream, not
  `Trade`); they flow through `backtest/output.py` to the lab's equity-chart excursion overlay.
  `Execution` also records **blocked setups** (`BlockedSetup`, `execution.blocks`) — a port of the
  Pine's pink `TRADE BLOCKED` tag (`mpc_strategy.pine` 4025-4086): a setup price and the engine had
  READY (SOS in, fib agreeing, an entry edge to rest on, flat, this leg untraded) that one of the
  strategy's OWN toggles refused. Same six reason codes in the same PRECEDENCE (`f_blkCode`: 1
  direction off · 2 arm source off · 3 final hour · 4 divergence/extreme veto · 5 HTF breakout · 6
  HTF bias), the same hover text as `f_blkWhy`, and the Pine's `sosBar*10 + code` dedupe generalised
  to the reason SET — one record per setup per distinct COMBINATION, so a setup blocked for twenty
  bars is one record but a set that changes is a genuinely different refusal.
  **ONE DELIBERATE DEVIATION:** the Pine reports only the FIRST blocker (a chart tag has room for one
  line); we record EVERY rule refusing the setup, because the lab filters by reason and "blocked by
  the veto" has to stay true when the final hour was also blocking. Precedence survives as the ORDER,
  so `codes[0]` (exposed as `.code`) is exactly what `f_blkCode` would have returned alone — a
  per-reason count taken off the primary still reconciles with TradingView.
  **Reporting-only and parity-safe**, exactly like the excursion fields:
  nothing reads a record back, so no decision can move and `compare_strategy.py` diffs the same
  `px_*` stream as before. The recording hangs off `_place_entries` (reading gates `_armed`
  computed, never recomputing them), which is why `mpc_bleg` gets none — it overrides that method,
  and those codes describe why an *A+* setup was refused. Surfaced on the lab price chart's Blocked
  layer; the full path is in `command-center/backend/CLAUDE.md` → *Blocked setups*.
  `Execution` also records **missed setups** (`MissedSetup`, `execution.misses`) — the OTHER half of
  "why didn't this trade", and a port of the Pine's orange 2-of-3 callout (`f_w23Arm` / `f_w23`,
  `mpc_strategy.pine` 3064-3194 + 4022-4023). See *The missed-setup watch* below.
- **`strategy.py`** — `MpcSosFadeStrategy`: the driver. `run(df, warmup=…)` replays a canonical frame
  end-to-end; `step(bar_state)` does one bar. Collects `.decisions` (the per-bar stream) and
  `.execution.trades`.
- **`secondary.py`** — the fast-feed sniper re-entry (below). `Structure1m` (fill-clock structure feed, port of Pine
  `f_struct1m`) + `SecondaryArm` (the latch/arm, port of Pine `f_secArm`). Consumed by `run_dual`.



## The missed-setup watch (2026-07-27) — the setups that died, not the ones that were refused

A **block** and a **miss** answer the same question one step apart in a setup's life, and mixing
them up makes both useless. A block is a trade the strategy had FULLY READY and one of its own
toggles refused. A miss never got that far: it reached 2 or 3 of the three confluences and then
DIED. Neither places an order, so neither is in any trade list, any equity curve, or any broker
report — the only place either is countable is here.

The three confluences, and what "met" means (Pine `f_w23`):

| # | Confluence | Met when |
|---|---|---|
| 1 | **ARM** | a liquidity sweep or an RSI divergence armed Stage 1 — and the source that fired is one you have ENABLED |
| 2 | **SOS** | always: it is why the watch is open at all |
| 3 | **ZONE** | price tagged the 0.5-0.886 band AND (with Require-FVG on) a gap was live in it while price was there |

**Exactly one thing is ever missing**, which is why `MissedSetup` carries a single `code` where
`BlockedSetup` carries a list. At 2 of 3 it is the arm or the zone (codes 1-3); at 3 of 3 every
confluence was there and the entry still never happened, so the record names the ENTRY-side reason
instead, in the Pine's precedence: veto → final hour → HTF → "the limit rested and price never
touched it" (codes 4-7). `reasons` is still exposed as a one-item LIST purely so a miss and a block
read identically all the way downstream.



## The RETRACE a miss was waiting on (`zone_time_ms` / `zone_turn_ms`, 2026-08-08)

`MissedSetup` therefore carries the retrace itself: `zone_time_ms` (the first bar of the visit) and
`zone_turn_ms` (its most adverse bar). Both `None` when price never reached the band.

**Three deliberate deviations from the Pine, all reporting-side:**

1. **Every miss is recorded; nothing is filtered at write time.** The Pine has three view filters
   (`debugShow23`, `debug23Filter`, `debugShow23Disarmed`) plus a `debugDays` recency window because
   TradingView caps a chart at 500 labels. The lab has neither problem, and a miss filtered away at
   write time can never be counted later. The chart filters BY REASON instead, which is strictly
   more expressive than the Pine's three presets.
2. **`near` replaces those presets.** Each record carries the Pine's own near-miss test
   (`metN == 3 or (zone reached and zone not met)`). The chart derives its DEFAULT view from it —
   see `command-center/backend/CLAUDE.md` → *Missed setups* — so the layer opens on the Pine's
   default and one click widens it, which the Pine's radio buttons cannot do.
3. **A setup that filled this bar closes as TRADED immediately.** The Pine assigns `tradedSosL`
   further down its script than it reads it, so on the fill bar it still reads the previous value.
   Both end with no callout; ours gets there a bar sooner, and it is the correct answer on the one
   bar where they differ (a trade that opened and closed inside the same bar, which the Pine would
   have booked as a miss).

**Where it runs, and why not where the blocks run.** `_record_misses` is called from `step()`,
between the fills and the placement — the same slot the Pine calls `f_w23` from. It CANNOT hang off
`_place_entries` like the block recorder does: a setup keeps accumulating state while a position
from the other side is open, and that path never runs then. That is also why `_bar_gates` was
extracted from `_armed` (the final-hour / HTF / bias gates are needed on every bar, not only when
flat) and why `mpc_bleg` needs the explicit `_records_misses = False` opt-out rather than getting
the exclusion for free.

**Two additions this needed elsewhere, both parity-neutral.** `SeqState` gained `l_arm_src` /
`s_arm_src` (Pine `armHolderL`/`armHolderS`) — the source holding the Stage-1 slot, which is the one
thing the live `sos_*_swp`/`sos_*_div` flags cannot tell you once the execution layer has filtered
them through the toggles, and without it a "your arm source is off" reason could not say WHICH one.
`build_results` gained `missed_setups`.

**Measured on the shipped window** (XAUUSD M15, 2025-03-04 → 2026-07-27, 33,041 bars, defaults):
46 trades, 80 blocks, **93 misses** — 50 "No retrace" (none near), 35 "No FVG in zone" (all near),
4 "Never filled", 4 "Final hour". So the chart opens on 43 markers and the routine 50 are one click
away.



## Secondary (1m sniper) re-entry — `exec_secondary` (built 2026-07-19, committed `c962601`)

The re-entry Aaron prototyped in Pine, built as the *exact* version here (Pine can only
sample the fill-clock engine once per 15m bar — its own tooltip says "the exact version is the Python port").
**Full rules + design: `docs/MPC_SOS_FADE_SECONDARY.md`.** One paragraph: after the **primary** 15m
A+ trade on a leg has traded and gone flat, while the 15m div + SOS are still live and price is back
in the 0.618-0.886 zone, a **Structure shift** in the trade direction rests a limit at a 38.2%
retrace of that tight shift leg (stop = shift leg origin; TP1/TP2 = 15m 0.5/0.382; runner = TP3). One
re-entry per shift leg; a re-entry is never the first trade on a leg.

  | retrace | trades | total R | avg R/trade | sec | sec R | its best | other 9+ | W/L |
  |---|---|---|---|---|---|---|---|---|
  | **0.000** (on the SOS) | 192 | +154.38 | +0.804 | 12 | +14.48 | +16.51 | −2.03 | 3/3 |
  | 0.236 | 190 | +159.92 | +0.842 | 10 | +20.02 | +21.91 | −1.90 | 2/3 |
  | **0.382** (shipped) | 190 | +165.46 | +0.871 | 10 | +25.56 | +27.33 | −1.76 | 2/3 |
  | 0.500 | 189 | +170.07 | +0.900 | 9 | +30.17 | +34.01 | −3.84 | 1/4 |



## Reclaim Entry, and the combined value that runs it beside the gap

**Added 2026-08-21.** Two new values for `exec_sec_trigger`: **`Reclaim Entry`** and
**`FVG in zone + Reclaim Entry`**, which runs it alongside the shipped gap trigger.

The reclaim exists because of a geometry fact this file already records: **the `1.0` sits a median
0.43R past the `0.886`**, so a primary stopped at the `0.886` that then turns can be re-entered AT
the `0.886` with the stop at the `1.0` — the level that genuinely kills the leg — for roughly 0.43x
the original risk. It waits for a fill-clock bar to trade back THROUGH the `0.886` (never the
stop-out bar's own wick — `_l_seen`/`_s_seen` require a later bar), rests the entry at that level,
and voids for the setup if the `1.0` prints first.



## The numbers — `run_dual` over 187,102 M15 / 2,801,964 M1 bars, 2018-09-14 → 2026-08-18

One account, one position slot, `fill_model='bar'`, no costs.

| book | trades | re-ent | R | re-ent R | x at 10% | worst dd | risk / x at a −50% ceiling |
|---|---|---|---|---|---|---|---|
| no re-entry | 181 | 0 | 138.9 | — | 3,582 | −45.6% | 11.00% / 7,188 |
| after-breakeven only (**ships today**) | 235 | 54 | 152.0 | +13.1 | 5,490 | −53.5% | 8.50% / 2,981 |
| after-a-loss only (the reclaim) | 234 | 53 | 157.9 | +19.0 | 7,225 | −46.3% | 11.00% / 15,509 |
| **both** | 288 | 107 | **171.0** | **+32.1** | **11,072** | −49.0% | 10.25% / **17,142** |

**It all ships OFF.** `exec_sec_trigger` still defaults to the gap alone, and the shipped path is
byte-identical: the control book reproduces 235 trades / 54 re-entries / 152.0R / +13.1R exactly.



## 🔴 Two control replays, two rules — the story is in the build notes, the rules are here

**Neither failure was found by a test.** The suite was green, the parity gate was green, and the
only thing that caught either was re-running the UNCHANGED configuration on the changed code and
finding it had moved. Full narrative and the numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The
combined re-entry value*.

**2. A fix belongs in the half that has the problem — protect at the READER with the requirement,
never at every WRITER.** The reclaim must not arm off a latch another block wrote, but guarding it
at the GAP LATCH **cost the gap half 7 of its 54 re-entries whenever the reclaim was switched on**,
so the combined book stopped being the two halves. The guard belongs in `_leg_ok`, where the reclaim
asks its own question — *has price come back through the level* (`_l_rec`) — rather than *did
something latch this side*.



## The re-entry settings, split three ways in the editor (2026-08-21)

Aaron, looking at a single flat list of them: *"which one of them is applicable to Reclaim Entry?
I have nothing to do with any of these items."* He was right about nine of them. The block is now
three groups in `mpc_sos_fade.meta.json`, and the rows that cannot matter are **greyed with the
reason on them** (`disable_if` / `disable_note`) rather than hidden — the reader has to be able to
see which state a dead setting is stuck in.

| group | what is in it | when its rows are greyed |
|---|---|---|
| `Secondary re-entries` | the switch, the trigger, and everything BOTH halves read | never |
| `↳ Reclaim Entry only` | its precondition, stop, first target, bank % | trigger is `Structure shift` or `FVG in zone` |
| `↳ FVG / Structure shift only` | the four the reclaim replaces one-for-one, plus the retrace | trigger is `Reclaim Entry` |



## A re-entry records WHAT THE TRADE BEFORE IT DID, and that is a second question (2026-08-21)

`SecArm.l_after` / `s_after` → `_Pending.after` → `Trade.after`: **"breakeven" | "stopped" |
"closed" | None**, reporting-only, read by nothing that arms, prices or sizes. The price chart tags
a re-entry `BE+` or `SL+` off it — Aaron's ask, looking at a chart with both triggers on and 107
re-entries all wearing one `SEC`.

**TESTED:** 6 new tests in `tests/test_secondary.py` (+4 in `command-center/backend`); 8 mutations
written, 8 killed. **PARITY:** unchanged and re-run green — nothing here is read by a decision.



## Nothing in the re-entry layer says "1 minute" any more (2026-08-21)

The fill clock became a setting the same day (5 minutes by default — table and reasoning at
`exec_sec_fill_tf_min` in `config.py`). Aaron, on landing it: *"Make it transparent everywhere.
Anything that says one minute shouldn't be so."*

**Two dropdown VALUES were renamed**, because a value naming a timeframe the code no longer uses
is worse than stale — it is a wrong answer printed on the page.

| was | is |
|---|---|
| `1m shift` (a re-entry trigger) | **`Structure shift`** |
| `1m leg` (a re-entry stop anchor) | **`Shift leg`** |



## The exit ladder — every TP/SL lever, and which ones are switchable

The register of how this bot (and `mpc_bleg`, which reuses the whole ladder) decides where the
stop and the targets sit. Keep it current: a new exit lever in the Pine lands here, in `config.py`,
in `mpc_strategy_export.pine`, and in `compare_strategy.py` in ONE commit.

The floor and the trail compose: past TP2 the stop is the floor, and the trail may only tighten
it further, never loosen it. With Structure selected and no confirmed swing yet, the trail is
absent and the floor alone holds the stop.

**The TP rungs default to 0/0 (2026-07-27) — and 0 does NOT disable the target.** The rung SIZE and
the target PRICE are separate things. At 0 no size leaves at TP1/TP2, but `_advance_stage` still
watches those prices, so touching TP1 still stages the stop to breakeven and touching TP2 still
installs the floor and hands the runner to the trail. The whole position then exits as one runner leg.
This is the shipped behaviour because it is what Run 1 measured as best AND what Aaron actually trades.
`test_zero_pct_rungs_bank_nothing_but_still_stage_the_stop` locks both halves of that.
Python needs no special case (`_remaining_brackets` computes p1 = p2 = 0 and emits neither bracket);
**the Pine does** — `strategy.exit(qty_percent = 0)` closes the WHOLE position, so both Pine files skip
the call when the rung is 0. If you ever port a new rung, port that guard with it.

**`mpc_bleg` overrides TP1, TP2 and the SL** with its own band prices (SL = band origin, TP1 =
the broken swing extreme, TP2 = the expansion extreme). Everything from the staging down —
floor, trail, both dropdowns — is this table, inherited unchanged.

**Aaron's brother's tested best combo (the shipped default 2026-07-26):** Structure trail +
buffer 20 ticks + TP2 floor = TP1 price.



## The breakeven buffer can be a FRACTION of the stop (`exec_be_buf_mode`, 2026-08-24, ships OFF)

Three modes. `"Ticks"` is the shipped one and reads `exec_be_buf_tk` alone — **one fixed distance on
every trade, whatever that trade is risking.** `"Fraction of stop"` takes `exec_be_buf_r` of the
FROZEN entry risk instead. `"Fraction of stop + cost"` floors that at what the trade has actually
cost plus `exec_be_cost_margin_r`, which is the only mode that can promise a staged exit is not a
loss. Both non-tick modes are capped at `exec_be_cap_pct` of the entry → nearer-rung distance.



## The swing ratchet (`"Structure + % ratchet"`, DEFAULT since 2026-07-28)

**The problem it fixes.** The plain structure trail PARKS the stop at the last confirmed swing.
That swing is a LAGGING anchor: in a strong leg it ends up a long way behind, and the gap between
it and the high IS the runner's give-back. Measured over 6.6y / 164 trades (XAUUSD 15m, SL 0.886):
the strategy banked **27.5% of the total profit it ever showed open**, and on the 78 trades that
ran ≥$10 of gold it captured $2,283 of the $5,300 they moved — **57% handed back**.

**What it does.** Same anchor (`last_conf_swing ± exec_struct_trail_buf_tk`), but from there the
stop climbs one `exec_trail_pct`-of-price step for every step of favourable move. It falls back to
the bare anchor until the move is one full step past it, so it is **never LOOSER than the plain
structure trail — only equal or tighter** (`test_swing_ratchet_is_never_looser_than_the_plain_structure_trail`).

**Measured, vs the plain structure trail** (same 6.6y window, same 164 trades, same entries):

| | order-free edge | net | run actually banked | max DD |
|---|---|---|---|---|
| Structure (swing) | 107.6R | $2.82M | **43%** | 54.7% |
| Structure + 1% ratchet | 109.3R | $3.81M | **53%** | 54.7% |

**Read this honestly.** The EDGE is unchanged — +1.7R over 164 trades is noise, and 1.5% (106.3R)
/ 2.5% (110.4R) bounce either side of it, which is the signature of randomness rather than an
optimum. What is real is the 10-point jump in how much of each run survives to the close, and it
costs nothing: **percentage drawdown is IDENTICAL (54.7%, same day)** — the bigger DOLLAR drawdown
in an early write-up was a compounding-account artifact, not a risk increase. Only 11 exits change:
8 better (+13.2R), 3 worse (−11.5R), and ONE trade (2025-10-21, +25.23R → +16.27R) is nearly the
whole downside.

**Why PERCENT and not dollars.** Gold ran 1,500 → 3,400 across the test window, so no fixed $ step
is right at both ends ($20 is a 1.3% trail at 1,500 and 0.6% at 3,400). The dollar version tops out
at **100.4R vs the percent version's 109.3R** for exactly that reason, and it only ever climbs
toward the plain structure trail as the step widens — in dollars this dial cannot beat what it
replaced. Do not "simplify" it back to a $ step.

**Do NOT add a hard take-profit on top of it.** Tested (2026-07-28): a target is either too loose to
fire (40R was byte-identical to no target — no trade in 6.6y ever reached it) or tight enough to cut
the tail that IS the profit (15R → 86.4R, a fifth of the edge gone). The 25R row looks best on the
table and is three lucky trades — only 3 of 164 ever reached 25R peak. There is no useful middle.

**Extension fibs (NEGATIVE fibs past 0.0) — measured 2026-07-28, REJECTED in every form.** This is
the most natural-looking idea on the list and the one Aaron trades by hand, so it gets its own record
rather than a line in the list below. Past the 0.0 fib the runner has no target at all, so the
proposal was to bank at the standard extensions the way a discretionary trader would.

*As TAKE-PROFIT rungs, shallow* (0.0 / −0.272 / −0.414 / −0.618, all off at −0.618 — Aaron's hand
rule): **109.3R → 69.1R**, a third of the edge gone. Every one of 14 allocations lost, and the
ranking was perfectly monotonic in how much was banked — the limit of "bank less" is the shipped
runner. Best of them (50% at −0.618 only) still only reached 92.4R.

*As a STOP FLOOR* (bank nothing, but ratchet the stop up the extension ladder one rung behind price):
**worse than the targets — 109.3R → 56.1R at best**, roughly half the strategy. A fib level is a
FIXED price and does not breathe; the structure trail moves with the market and survives an ordinary
retrace, a horizontal line does not. The 23.5R trade became 10.5R, cut on a pullback six legs before
it actually finished. Same lesson as every other tightening experiment above.

*As DEEP rungs* (−1 / −2 / −3 / −4 / −6 — take nothing until the trade is already a monster, then
trim): far better than the shallow version and still not an improvement. Aaron's −1:10% / −4:50% /
−6:rest ladder = **106.3R**. The only rows that beat the baseline sit at −6, and **exactly ONE trade
in 6.6 years ever reached −6** (−6 take 100% = 112.2R, i.e. +1.55R over the true 110.65R baseline,
from a single 2020 trade). That is a description of July 2020, not a rule.

**The pattern, and why there is no ceiling to find.** Rule cost tracks how OFTEN the rule fires:
−1 touches 8 trades and costs 7–14R, −4 touches 2 and costs 1–3R, −6 touches 1 and costs nothing.
Every candidate converges on the baseline from below as it stops doing anything. There is no depth
at which banking becomes profitable — there is only a depth at which it becomes harmless.

**The shape of the book, which is the real reason.** Of 164 trades only **29 ever reach the 0.0 fib**,
11 reach −0.618, 8 reach −1, 2 reach −4, 1 reaches −6. Those **11 trades past −0.618 make 106R of the
109R total**. The two biggest ran to −4.77 and −6.74 and the trail paid −3.69 and −5.68. Any fixed
ceiling is applied to every trade, so it necessarily caps the handful that carry the strategy. Eight
trades DO run past 0.0 and hand the whole extension back (they exit at the 0.382 floor) — that leak
is real, but it is worth 5.7R and the cheapest rule that plugs it costs 17R.

**Four other exit ideas measured and REJECTED the same day, so they are not re-tried:** tightening
the trail in any form (fixed step $2–$40, chandelier 2–8×ATR, giveback caps 25–50%) costs 60–90% of
net; banking at the TP rungs (25/25, 33/33, 50/0) costs 60%; "stay loose then clamp once it is a
monster" (>3R/5R/8R/15R → a tight trail) costs 20–45%; and exiting on an opposing RSI divergence past
TP2 costs 77% — only 18 of 164 trades ever print one, the six biggest give-back trades print ZERO,
and where it does fire it fires 2–4 times so you can only ever act on the earliest and worst one.



## Scale-in (`exec_scale_in`, 2026-08-16) — the first ADDITIVE lever this bot has ever had

**Every exit family swept here before this one was PROTECTIVE** (Run 8 alone killed ~50 tightening
variants, Run 9 rejected banking in every form). This one adds SIZE to a runner the trail is already
protecting, and a grep for pyramid/scale-in across the repo returned nothing before it.

**The rule, and it is a SIZING rule rather than a timing one:**

```
locked   = (stop - entry) * base_qty     profit the stop already guarantees
per_unit = (price - stop)                what one extra unit risks to that SAME stop
add_qty  = min(locked / per_unit, base_qty * exec_scale_cap_x)
```

Stop out right after adding and the two cancel — the base banks `locked`, the add gives back at most
`locked`. **An add can shrink a winner; it cannot manufacture a loser.** The guarantee is arranged in
advance by SIZE, never detected in real time.

**MEASURED 2026-08-16 (Run 19) — XAUUSD 15m, 2018-09-13 → 2026-08-14, PU Prime ECN costs charged:
off 182 trades / +128.26R / 6.03R maxDD / 65 losers, and 2 adds at cap 1.0x gives +211.59R (+65%) /
8.72R maxDD / 67 losers with the WORST TRADE UNCHANGED at −2.06R.** Return-per-drawdown 21.27 →
24.26. **Dropping the affordability test and adding a flat 1x instead costs 8–13 extra losing
trades — that difference is what the `locked / per_unit` line buys.** Full grid, the free-of-costs
pair whose losers are bit-identical, and the two families that closed NEGATIVE the same day (ATR
stop distance, regime filtering): `mpc_sos_fade_optimization.md` → Run 19.



## Scale-in gained a MODE — and the first answer was measured on a broken fill (2026-08-18)

`exec_scale_mode` ∈ {`"Trail"`, `"BOS retest"`}. **Trail** adds at MARKET on the bar the trail
ratchets. **BOS retest** waits for the next confirmed break of structure our way and RESTS A LIMIT
at the level that break cleared. The SIZE rule is untouched by either; only the moment and the
price move.

🟢 **SHIPPED 2026-08-18 after a 32-cell re-run: `exec_scale_mode="Trail"`, `exec_scale_max_adds=3`,
`exec_scale_cap_x=0.5`.** Scored on the 2020-FREE book, because 2020 is ~1/3 of the all-period
figure and scaling roughly TRIPLES its contribution:

| | ALL R | dd | ret/DD | EX20 R | ret/DD |
|---|---|---|---|---|---|
| no scaling | 128.26 | 6.03 | 21.27 | 92.51 | 15.34 |
| **Trail 3 × 0.5x** | **194.15** | **7.24** | **26.81** | **124.05** | 11.99 |
| BOS retest 4 × 2.0x | 180.44 | 9.20 | 19.61 | 80.90 | 8.79 |

Full grid, the ladder-shape test and the void banner: `mpc_sos_fade_optimization.md` → Run 21.



## The adds got a TAKE PROFIT, and the measurement said not to (2026-08-19)

`exec_scale_tp_mode` ∈ {`"Ride"`, `"Prev week H/L"`, `"Prev day H/L"`, `"H4 H/L"`}. Until now the
scale-in lots had **no exit of their own**: they closed pro-rata whenever the base ladder banked a
rung, and otherwise rode the base trade's trailing stop. Aaron's question was the right one to ask —
an add is bought late and high, with almost none of the base entry's cushion, so a pullback ought to
hand back what it just made.

| where the adds bank | total | maxDD | banks | worst | excl. top 20 | its dd | ret/dd |
|---|---|---|---|---|---|---|---|
| scale-in OFF (shipped) | 128.26R | 6.03 | — | −2.06 | 92.51R | 6.03 | 15.34 |
| **Ride** (no target) | **194.15R** | 7.24 | 0 | −2.06 | 124.05R | 10.34 | 11.99 |
| Prev week H/L | 168.51R | 7.24 | 16 | −2.06 | 114.12R | 9.73 | 11.73 |
| Prev day H/L | 157.57R | 7.51 | 25 | −2.06 | 111.91R | 7.72 | **14.49** |
| H4 H/L | 146.09R | 7.15 | 47 | −2.06 | 104.38R | 7.15 | **14.60** |

**How it works, and the two things that are load-bearing.** The target is the nearest level of the
chosen family that (a) price has **not already taken** — a swept level is not somewhere to aim at,
it is a price we are past — and (b) sits **beyond the newest add**, so every lot it closes is closed
in profit. On the Pine side it rides the existing per-add `strategy.exit` as a `limit`, which makes
each add a proper OCO bracket; a `na` limit is no limit, so `"Ride"` leaves those calls
byte-identical.

The cause is an interaction, which is why neither the tests nor the numbers caught it. A daily or H4
level dies on a **WICK** (`SWEEP_HIGH` / `SWEEP_LOW`), and `stack.step(bar)` runs **before** the
strategy sees that bar — so on the exact bar price reached the level, the engine had already flagged
it mitigated and the target evaluated to `None`. **The order vanished precisely on the bar it would
have filled**, every single time, for eight years.



## An add lot is now a TRADE-SHAPED record (2026-08-20)

**Aaron's ask:** see a scale-in add on the Command Center price chart the way any trade is seen —
how far it ran, what its drawdown was, where it got exited — and be able to toggle it.

**It was a data problem, not a chart one.** The record was `{price, ms, qty}`, so the only true
statement the panel could make was *a lot was bought here* — one dotted `Add` line. Every question
worth asking had no answer anywhere in the pipeline. Each lot now carries its own excursion and its
own exit: `{price, ms, qty, mfe_price, mae_price, exit_price, exit_ms, exit_reason, pnl_usd}`.

**TESTED:** 3 new strategy tests, each watched RED by its own mutation and each reddening only
itself — inheriting the parent's window (reddens the excursion test at the parent's 103.5), dropping
the `_close_add_record` call (reddens the exit test on a `KeyError`), returning `dict(lot)` from
`_add_record` (reddens the bookkeeping test). Plus 3 backend tests on the passthrough.

**MEASURED, full history, `Trail` 3 × 0.5× at rungs 50/25:** 66 trades with adds, 112 lots; **0**
lots missing an exit, **0** whose window fails to bracket its own entry and exit, **0** whose
stamped P&L disagrees with its own entry→exit arithmetic, and **0** trades where base + lots + costs
fails to reconcile to `pnl_usd` to the cent.



## 🔴 A TP RUNG WAS SLICING THE ADDS, AND `_finalise_trade` BINNED THE REST (fixed 2026-08-19)

**Found while verifying the TP1/TP2 sweep, not by a test.** `_exit_portion` closed the scale-in
lots **pro-rata** with the base: a rung taking 50% of the base took 50% of every add. Then
`_finalise_trade` ends with `self._adds = []`, so the unclosed remainder vanished **with its P&L
never booked**. The trade's R was short by whatever those lots were worth.

**MEASURED, XAUUSD 15m 2018-09-13 → 2026-08-14, PU Prime ECN, `Trail` 3 × 0.5×:** every affected
configuration dropped **exactly 112 add lots**, worth up to **42.46R — 32% of the result** at
`exec_tp1_pct = 50, exec_tp2_pct = 25`.

| tp1 / tp2 | booked (buggy) | discarded | re-run (fixed) | understated by |
|---|---|---|---|---|
| 0 / 0 | 194.15R | 0.00R | **194.15R** | — |
| 0 / 25 | 163.59R | — | **180.19R** | 9% |
| 25 / 0 | 158.02R | 14.15R | **174.62R** | 10% |
| 25 / 25 | 127.45R | 28.31R | **160.65R** | 21% |
| 50 / 0 | 121.89R | 28.31R | **155.09R** | 21% |
| 33 / 33 | 106.11R | 37.37R | **149.93R** | 29% |
| 50 / 25 | 91.32R | 42.46R | **141.12R** | 35% |
| 50 / 50 | 61.26R | 0.00R | **61.26R** | — |

**The ranking survives the fix and Ride still wins**, but the penalty is smaller than the buggy
table implied: `exec_tp1_pct = 50` costs 39R against Ride, not the 72R it was reading.

**The fix is Pine's rule, not a repair of the pro-rata one.** `L-TP1`/`L-TP2` are
`from_entry = "Long"`, so a rung can only ever close the BASE entry; each add carries its own
`L-AX1..4` exit at the same stop and dies with it. So: **a TP rung leaves the adds alone; a stop, a
force-close, or whichever fill closes the last of the base takes them in FULL.** The `final` clause
is why the second half is there — if `exec_tp1_pct + exec_tp2_pct == 100` a *limit* is what closes
the base, and the adds must still go with it. Nothing may outlive the trade that owns it.



## The time stop (`exec_time_stop_mode` / `exec_time_stop_hrs`, 2026-08-05)

Aaron's ask, and it started from the right question rather than from a rule: *"what number could we
draw a line at and say if a trade is dancing around by this hour, cut it, to minimise our
drawdown."* The lever exists; **the evidence for the number does not yet, and that distinction is
the whole of this section.**

**What it does.** `exec_time_stop_mode = "Before TP1 only"` closes a position that has been open
`exec_time_stop_hrs` calendar hours **and is still at stage 0** — TP1 never touched. `"Always"`
drops the stage gate and closes on the clock alone. `"Off"` closes nothing. **"Before TP1 only" at 36h became the DEFAULT
on 2026-08-06 (Aaron's call), so the baseline moved — 159 trades / +137.94R / maxDD 7.99R →
159 / +142.17R / maxDD 5.62R. Pin `exec_time_stop_mode="Off"` when reproducing any run measured
before that date.** The exit leg books as `L-TIME` / `S-TIME` so it is countable in the lab
rather than hiding inside the ordinary force-close bucket.

**Why the milestone is TP1 and not something else.** Over the 161-trade window
(2020-01-01 → 2026-08-03, run `75ccc776d10c`) the TP1 line splits the book perfectly:
**105 trades reached TP1 and not one of them lost; all 56 that never reached it lost.** That is
structural, not a coincidence — touching TP1 stages the stop to breakeven, so a trade past that
line cannot take a full loss. The clock is therefore only ever asked about trades still at risk.

**MEASURED BY REAL REPLAY — 155,440 M15 bars (2020-01-01 → 2026-08-03), one full replay per row,
at today's shipped defaults** (which include `exec_min_stop_mode = "% of price"` 0.08, so the
baseline is **159 trades / +137.94R**, not the 161 / +135.94R of the pre-guard run `75ccc776d10c`):

| cut at | mode | trades | total R | max DD (R) | cut by the clock |
|---|---|---|---|---|---|
| — | **Off (shipped)** | 159 | **+137.94** | **7.99** | 0 |
| 24h | Before TP1 only | 159 | +140.22 | 5.54 | 10 |
| 30h | Before TP1 only | 159 | +142.05 | **5.37** | 7 |
| **36h** | **Before TP1 only** | 159 | **+142.18** | 5.61 | 6 |
| 40h | Before TP1 only | 159 | +142.59 | 5.60 | 6 |
| 48h | Before TP1 only | 159 | +140.10 | 7.34 | 4 |
| 36h | **Always** | 159 | **+97.27** | 5.91 | 26 |

**24h–40h is a PLATEAU, not a peak, and that is the only reason 36 is defensible.** Roughly the
same R and the same drawdown across a 16-hour band describes the trade population rather than
fitting it; 36 sits mid-plateau deliberately.

**Where it lives.** `_time_stop_due()` in `execution.py`, fired from the same Phase-B `elif` chain
as `exec_close_opp_sos` and `flat_by_close`, so the three force-close paths keep one precedence.
The clock is `sig.time_ms - self._entry_ms`, i.e. from the FILL — a limit can rest for days, and
charging that waiting time against the trade's life would close positions that had barely opened
(`test_the_clock_runs_from_the_FILL_not_from_the_bar_the_limit_was_PLACED`). `_stage == 0` is the
existing state rather than a new flag, because stage 1 IS "price touched TP1"; deriving it a second
way would be a second claim about one event.

- **Round 1, mode Off** — worthless by construction, exactly as this section had warned.
- **Round 2, mode ON at 36h** — `compare_bleg.py` exit 0, and it proved NOTHING: the clock fired
  **zero times**. At 36h the lever fires ~6 times in 6.5 years, so no export a human takes will
  reach it.
- **Round 3, mode ON at 4h** — the clock fires constantly, and the gate went **RED on its first
  exercised bar.**

**After both fixes:**

| gate | result | clock exits in the window |
|---|---|---|
| `compare_bleg.py` | **exit 0** | 1 |
| `compare_strategy.py` | clean to bar 11031 | **6** (2 long, 4 short) |

Bar 11031 is the pre-existing minimum-stop divergence recorded above, unrelated to this lever and
red before it existed. Every clock exit before it matches Pine bar-for-bar and price-for-price.



## ✅ CLOSED — the A+ parity failure was the EQ/FVG coupling, not the entry rule (2026-08-06)

**The symptom**, on a 21,999-bar `VANTAGE_XAUUSD, 15m` export, at every warmup 100 / 500 / 1000 /
2000:

```
bar 11031  2026-02-18 14:30  px_edge:  py=4990.02  pine=4965.73
```

Same fib leg on both sides (`dbg_fib_ash` 5052.77 / `dbg_fib_asl` 4842.20), same stage, same
`px_dec_bits`. Python rested at **fib 0.702 exactly**; Pine at **0.5866 of the leg**, which is not
a rung, so Pine was resting on a GAP EDGE. It reads exactly like the two sides taking different
branches of the entry model.

**Fixed in four places, all in one commit:** `EngineStack` builds an `EqualHighsLowsEngine` and
feeds its levels to the FVG cap; the FVG engine's cap counts **ordinary gaps only** (it was still
on the self-cancelling SWAP rule the Pine fixed on 2026-08-03); `mpc_sos_fade` pins
`eq_exempt_fvg=True` and `mpc_bleg` pins it False (that fork's Pine keeps it off); and both export
Pines plot **`cfg_eq_exempt`**, which the harnesses now configure from.

**The standing lesson is one this repo keeps meeting from new directions, and this is its sharpest
form: a trade-affecting input with no export column is invisible to the parity gate BY
CONSTRUCTION — and the gate does not go quiet, it goes WRONG, accusing whichever code the symptom
happens to land in.** `execRunnerTrail` (2026-07-26) and `cfg_min_stop` (2026-07-30) were the same
shape and were both caught before they cost anything. This one was caught after three days and a
misdiagnosis, because the missing column was for an input somebody else had already written a
warning about. **A comment saying "this defaults OFF" is not a guard; the column is the guard.**



## The Custom stop level (`exec_sl_custom`, 2026-08-02)

A ratio in (0, 1.0] used as the stop instead of one of the five dropdown levels; default
**0.886**, which is bit-identical to picking the dropdown's own 0.886 — so switching the mode
alone moves nothing. How the price is derived, the lab UI, the optimizer axis, and why 0.886 is
the shipped default: See `docs/SOS_FADE_BUILD_NOTES.md` → *The Custom stop level*.



## The deeper-entry test (`exec_ob_deepen`, 2026-08-09) — REFUTED, and the mechanism is geometry

Aaron's theory, and it is a good one: **31% of the scratches and almost all of the losers could have
filled at an order block DEEPER than where they actually entered** (measured first — a deeper
same-direction block existed on 113 of 159 trades, and price reached it on 4 of 40 winners, 11 of 36
scratches and **35 of 37 losers**). A deeper fill has a TIGHTER stop, so the same price path is worth
more R — *"would I have less losers? and potentially slightly more return on the scratches."*

**Filling almost only on losers is bad only if the loser stays a loser**, which is why this needed a
REPLAY and not arithmetic over the finished list.

**MEASURED, two full replays, 155,807 M15 bars (2020-01-01 → 2026-08-06):**

| | trades | won | scratch | **lost** | hit TP1 | total R | maxDD |
|---|---|---|---|---|---|---|---|
| baseline | 159 | 63 | 44 | **52** | 104 (65.4%) | **+142.18R** | 5.61R |
| deepened | 102 | 35 | 15 | **52** | 48 (47.1%) | +73.41R | 15.20R |

**Both of his questions come back NO**: losers stay at exactly **52** and their R goes **−50.86 →
−71.30**; scratches **44 → 15**, their R +1.54 → +0.72.

Per-trade accounting, matched on the setup `(side, SOS bar)`:

```
never filled at the deeper price    57   (+44.61R given up)   ← the adverse selection, priced
entry unchanged (no deeper block)   47
re-priced and BETTER                16   (+25.70R)
re-priced and WORSE                 39   (−49.85R)
setups the baseline never traded     0   (+0.00R)             ← the freed slot bought nothing
```



## Bar-mode costs — commission and slippage, charged at last (2026-08-01)

Bar mode charging ZERO costs is the parity requirement (deviation 3 above). Bar mode being
*incapable* of charging any is not, and the two were confused: the command-center lab collected
`commission_per_side` and `slippage_ticks` on every run, stored them, displayed them, and
`python_runner` read neither — so every lab run of this bot was frictionless while reporting a
cost profile it had not applied. The tell was 52 of one run's 54 losers each losing **exactly
10.00%** of prior equity.

`MpcSosFadeStrategy(..., cost_profile=<AccountProfile>)` now passes a profile straight through to
`Execution` in bar mode. **Omit it and every path is byte-identical to what it was**, which is
what keeps `compare_strategy.py` a valid gate — and the harness never passes one, so parity is
untouched by construction. `mpc_bleg` inherits the kwarg.

Two units, both deliberate, and both would look plausible if wrong:

- **Commission is per LOT per side** — a lot being 100 oz. Charged on the entry and on every
  ladder rung, through the existing `_charge_commission`, which means it lands inside the trade's
  own P&L and R rather than beside them.
- **Slippage is charged on MARKET exits only** (`_charge_slippage`, `_exit_portion(market=...)`).
  A stop is a market order and pays; the entry limit and the TP rungs are RESTING LIMITS, which
  fill at their price or better or not at all, so charging them would price a cost that does not
  exist. It is also skipped entirely in **tick mode**, where the fill price already contains the
  real slippage off the tape — charging an estimate on top would book it twice.



## Layered costs — spread and swap, and the one that moves trades (2026-08-02)

Aaron's ask: *"you know the spread… the only thing we don't know is slippage."* Correct, and bar
mode was pricing neither the spread nor the swap. Both are now chargeable, from a broker profile
rather than a typed number, behind independent switches that are **all OFF by default** — the
baseline run stays frictionless so it stays comparable to the TradingView Strategy Tester, and
every cost is something you deliberately turned on. Lab contract: `python_runner.COST_LAYERS`.

**Swap needed almost nothing** — `_charge_swap` has run on every bar in bar mode since A2 and was
dead only because the lab passed `swap=None`. It matters here more than on most strategies: this
runner is designed to hold overnight (deviation 1) and gold swap is **−74.84 points/lot/night**
long on the Vantage demo.

**The spread is measured, and the number this repo had was the wrong broker's.** `$0.33` is PU
Prime's (688k ticks). Vantage — the broker every backtest here replays — measures **$0.22**
(median, over 1,494,459 cached ticks spanning 2025-08 → 2026-07; p90 0.27, p99 0.31). Using 0.33
would have overstated every backtest cost by 50%.

**MEASURED over 155,431 M15 bars, 2020-01-01 → 2026-07-31, at the shipped defaults:**

| run | trades | sum R | final equity | charged |
|---|---|---|---|---|
| free (the shipped baseline) | 161 | 135.94R | $28.26M | $0 |
| + spread as a cost | 161 | 130.27R | $16.27M | −$266,948 |
| + spread + swap | 161 | 123.90R | $10.09M | −$333,110 |
| **bid/ask fills + swap** | **159** | **141.93R** | **$29.48M** | −$361,835 |

Two things to take from that table, and the second is the one worth remembering.

Everything else is unchanged and deliberately so: **omit the profile and every path is
byte-identical** (the free row above reproduces the documented 161 / +135.94R exactly), the
harness never passes one, and `compare_strategy.py` is still **exit 0**.

**A cost turns marginal winners into real losers, and the win rate is where it shows up
(measured 2026-08-03).** On the 3-year run `432aff31f374` (73 trades, Aug 2023 → Aug 2026),
charging spread + swap took the win rate from **65.8% to 60.3%** — because **four trades flipped
side**: +$12 → −$26, +$68 → −$133, +$207 → −$1,315 and +$376 → −$2,331. All four were scratches
that only looked like wins because the run was frictionless, and the last two are not small.



## 🔴 THE RE-ENTRY NOW SHIPS **OFF** (Aaron's call, 2026-08-21 — reverses 2026-08-07)

**Every optional entry path is now OFF by default: the re-entry, loss recovery, scale-in and
B-Leg. The shipped book is the PRIMARY book.** MEASURED over 2018-09-14 → 2026-08-14: **181 trades
on the new defaults, against 235 with the re-entry on.**

---



## A SHRUNK entry paid its costs on the size it ASKED for (fixed 2026-08-21)

**Only reachable when a second leg competes for one budget**, so it was invisible for as long as it
existed. On a solo account the granted size ALWAYS equals the requested size, so both readings agree
and no stored run, no live trade and no parity export can tell them apart.

**The defect.** When the shared account shrinks an entry to fit the budget, the position, its risk
and its R yardstick all follow the GRANT — but the entry commission and half-spread were billed on
`pend.qty`, the size the leg merely asked for. Those costs are booked inside the trade's own P&L on
purpose, so the overcharge landed inside its R.

**MEASURED, 186,910 M15 bars 2018-09-14 → 2026-08-14, `puprime_ecn`:** 25 shrunk trades, every one
negative, **−0.0954R** total. Predicted error (shrink factor × entry cost ÷ risk) matched the
observed to five decimal places on **all 25**, and no other trade moved. Fixed: bill both on
`granted`. A+ shared then reads **+127.11R against +127.11R solo** — exact.

---



## Wrong-side stop fills — a KNOWN BACKTEST LIMITATION, not a bug (recorded 2026-08-01)

**Read this before reporting "the exit price matches no stop and no target" again.** That symptom
was the phantom-exit bug (`indicators/docs/BUG_exit_fill_price_mismatch.md`, fixed 2026-08-01), but with
that fixed there is a *legitimate* residue that produces a similar-looking exit, and it will keep
appearing on the chart forever.

**The shape.** Price runs up, tags TP1, the ladder stages the stop to breakeven — and then price
closes back through breakeven **inside the same bar**. The stop only becomes live on the NEXT bar
(assumption 1 above, `calc_on_every_tick = false` / `process_orders_on_close = false`). By then it
is already behind the market, so the emulator converts it to a market order and fills at that bar's
**open**, not at the stop price.

**Why it is not a defect.** Being OUT is correct — price genuinely went through the stop. What is
imprecise is the exit PRICE, and only because a bar-replay backtest looks at orders once per bar
while a real broker watches every tick and would have filled at or near the stop. Three consequences
worth holding onto:

- It makes the backtest look **slightly worse than reality**, which is the safe direction to be
  wrong. Do not "fix" it to make numbers look better.
- **Pine and Python behave identically**, so **parity is unaffected** — `compare_strategy.py` and
  `compare_bleg.py` stay valid, and neither will ever flag it.
- It is a **bar-mode** property. `fill_model="tick"` resolves the stop against real ticks and will
  legitimately disagree here; that is the improvement, not drift (see `backtest/CLAUDE.md` → A2).



## The 2026-07-26 exit-lever sync

The run write-up and the parity record that followed it moved to
`docs/SOS_FADE_BUILD_NOTES.md` → *The 2026-07-26 exit-lever sync*. The standing rules stay here:



## Deliberate deviations from the Pine (per the framework)

**Other rules rescued from that same moved narrative (60,467 bytes, largest paragraph 58,936 bytes on ONE line):**
- **Block codes are a WIRE FORMAT — never renumbered.** `leg` must stay distinct per leg.
- **An absent column means "Any"** — read it as a fact about what the Pine did *before the gate existed*, never as the Python default.
- **Read a within-noise R as "not worse", never as the gain.** This strategy's run-to-run spread is 15.06R, so anything under that is a consistency check on a rule, not a second measurement of the edge. Where a pass genuinely gained, it gained FREQUENCY — a count, which noise cannot manufacture — and it was bought with drawdown that must be restated every time the gain is quoted.

All OFF for the parity check (to match the Pine); each is a real-run choice:
1. **Flat-by-close** — force-flat + no new entries N minutes before the daily close (`flat_by_close`).
   **Default False, and RE-MEASURED 2026-08-03 over the full 6.5 years: leave it that way, and the
   margin is not close.** Aaron asked the natural question — *"I don't like swaps, what if we just
   close before the market closes?"* — so it was replayed four ways over the same 155,453 M15 bars
   at run `75ccc776d10c`'s params:

   | | trades | R | final balance |
   |---|---|---|---|
   | hold overnight, free | 161 | **135.94** | $28,258,768 |
   | hold overnight, spread+swap | 161 | 123.90 | $10,090,716 |
   | flat before close, free | 161 | **59.82** | $411,314 |
   | flat before close, spread+swap | 161 | 54.18 | $236,057 |



## Engine-construction pins (`MpcSosFadeStrategy.engine_config`)

**FOUR** engine inputs are NOT in the decision stream, so the bot pins them to the Pine STRATEGY's own
input defaults rather than the shared engine defaults — miss any one and the fib the bot reads drifts.
`test_engine_config_pins_every_input_the_pine_moved_off_its_default` asserts all four.
1. **`fvg_max_count=7`** — `mpc_strategy.pine` sets Max Active FVGs to 7 (the FVG engine default is 8);
   a smaller cap evicts the oldest gap one bar sooner and drops an entry edge Pine still holds.
2. **`fvg_threshold_pct=0.1`** *(added 2026-07-31 — it had NEVER been pinned)*. The minimum-gap floor.
   `mpc_strategy.pine` splits it by timeframe (`fvgThreshLTF` 0.0 below 15m / `fvgThreshHTF` **0.1** at
   15m and up, lines 116-118) and this bot trades 15m. `mpc_assistant.pine` uses **0.04** at 15m and
   the ENGINE default mirrors the indicator, so the two Pines genuinely disagree and no shared default
   can be right for both. **The bot worked for months by coincidence**: `backtest/replay/stack.py`
   happened to carry 0.1 as its own default. That default was itself stale relative to the engine, so
   anyone reconciling it would have silently moved this bot's trades with no test failing. Proven
   load-bearing by removing it — `compare_strategy.py` failed on the first compared bar
   (`px_edge` py=3478.99 vs pine=3475.43). `stack.py` now carries the engine default (0.0) and this
   pin carries the strategy's, which is the right way round.
3. **`fvg_require_close=True`** — `mpc_strategy.pine` HARDCODES the middle-bar close-cleared check
   while the engine defaults it OFF (mirroring the indicator). Caught 2026-07-26 as the single
   mismatch on a fresh export; full story in `### PARITY GREEN 2026-07-26`.
4. **`show_internal=False`** — the Pine's "Show Internal Structure" input defaults OFF, and Pine gates
   the ENTIRE internal block behind it (`internalActive = showInternal`), so `i_confirmed_*` is never
   set and the **Structure fib never adopts a more-extreme internal swing** as its anchor. The
   `market_structure` engine ALWAYS computes internal structure, so the `EngineStack` must be told to
   suppress the internal-derived snapshot fields (it blanks `i_confirmed_*` + `ifib_seed_*` when this
   is off). This is a real "a drawing toggle changes trade logic" coupling in the Pine — do not drop it.



## The three parity fixes (2026-07-16) — read before touching signals/fib

The port went green after fixing three faithful-translation gaps; each is a class of bug to watch for:
1. **Internal-swing adoption** (the `show_internal` pin above) — the engine's always-on internal
   structure fed the fib an anchor the Pine strategy never had (internal display off).
2. **Sweep double-count at the daily/session rollover** — Pine records a sweep on `d_lMit and not
   d_lMit[1]` (a bar-to-bar edge of a persistent VARIABLE). When a daily/session/H4 level rolls at
   18:00 and is re-taken on its own creation bar, `d_lMit[1]` (the old level, already swept) is still
   true, so no edge fires. The engine models levels (create / mitigate / EVICT) and the naive
   reconstruction latched on every `mitigated` event, re-recording the rollover sweep — which made a
   stale sweep look fresh and armed a trade Pine didn't. `signals.py` now reconstructs the Pine
   variable: reset on `created`, set on `mitigated`, **left alone on `evicted`**, edge vs the prior bar.
3. **The forming last bar** — TradingView exports the final (still-forming) bar's plotted series as
   NaN. `compare_strategy.py` now marks that bar `_px_present=False` and skips it, instead of reading
   `fillna(0)` as a real "stage 0" and flagging a phantom mismatch.



## The parity gate — `tools/compare_strategy.py` + `/audit-strategy`

The standing regression harness (same pattern as the engines' `compare_*.py`). `mpc_strategy_export.pine`
(in `indicators/`) = `mpc_strategy.pine` + an appended block that plots the per-bar decision stream
(`px_*`) and every toggle (`cfg_*`). Export it to CSV on a 5m XAUUSD chart; `compare_strategy.py` reads
the toggles, configures the bot identically, replays the same bars, and diffs the decision stream. Exit
0 = bar-for-bar identical. On a mismatch it names the first diverging bar + field. Run it via
`/audit-strategy`, or:
```
command-center/backend/.venv/bin/python strategies/python/mpc_sos_fade/tools/compare_strategy.py <export.csv> --warmup N
```



## The 2026-07-22 re-sync (the export was 7 days stale)

A dated gate record carrying no standing rule. See `docs/SOS_FADE_BUILD_NOTES.md` → *The 2026-07-22 re-sync*.



## LOGIC parity vs RESULT parity — two different tools, two different questions

`compare_strategy.py` answers "is our CODE the Pine's code?" — it replays TradingView's OWN bars and
diffs the per-bar `px_*` decision stream, so the data feed is out of the equation. That is the gate.

`tools/compare_trades.py` answers a different question: "why does a LAB RUN's finished trade list
differ from what I got in the TradingView Strategy Tester?" It pairs the two trade lists by entry TIME
(not price — different brokers legitimately differ by cents on the same bar) and reports matched /
TV-only / ours-only. **It is a diagnosis tool, not a parity gate** — a diff here is usually the DATA
FEED, not the code (proven 2026-07-22: run `f455b21faabe` came in ~110% vs TradingView's 142%; the whole
gap was two longs Vantage's wick swept a level our PU-Prime feed's wick fell ~10 cents short of, so the
sweep never armed. `compare_strategy.py` was green on TradingView's bars, i.e. our code took both those
longs on Vantage data — the lab missed them purely on the feed). Two counting conventions also confuse
the comparison and are NOT bugs: TradingView counts each TP rung as its own "trade" (41 positions × 3
rungs = 123) and its max-DD % is vs peak equity where ours is vs starting capital. Usage:
`compare_trades.py <tv_trades.csv> <run_id>` — `--tz` defaults to `Etc/GMT+4` (the Vantage XAUUSD chart
is a FIXED UTC-4, no US DST); it prints a hint if the median pairing offset says otherwise.



## This bot's LOSSES are another package's population — `strategies/python/loss_recovery/`

**The rule, its measurements and every caveat live in that package's own CLAUDE.md.** What belongs
here is only what a reader of THIS file needs: the recovery leg adds **+4.1R on top of +129.0R
(~3%)**, it does **not** reduce max drawdown (48.3% against 48.8%) and does not smooth the curve —
and the 2026-08-19 search of nine stop placements and six exit ladders **adopted nothing**, so the
shipped rule is unchanged and no number in this file moves. Full grid: `mpc_sos_fade_optimization.md`
→ Run 24.



## 🔴 The gate REFUSES an export from a chart faster than 15m (2026-08-23)

**The bot pins the gap filter to 15-minute values; the Pine reads them off the CHART.**
`mpc_strategy.pine` runs a minimum-gap floor of 0.0 below 15m and 0.1 at 15m and above, and
drops the middle-bar-close test below 15m. `strategy.py::engine_config` hardcodes the 15m
pair, deliberately and with its reason already written down there. **So on a sub-15m export
the two sides are configured differently before a single bar is replayed.**



## Tests

```
command-center/backend/.venv/bin/python -m pytest strategies/python/mpc_sos_fade/tests/ -q
```
Offline, no network, no TradingView. `test_sequence.py` (state machine on the real engine stack +
hand-checked Pine rules), `test_execution.py` (fills / ladder / stop-out / sizing, hand-checked),
`test_strategy_driver.py` (end-to-end), `test_compare_strategy.py` (the parity tool round-trips its
own output). These prove the plumbing; the Pine diff is the live gate.



## The B-LEG bot reuses this one — three parity-safe additions (2026-07-24, do NOT revert)

`strategies/python/mpc_bleg/` (the standalone B-LEG bot) reuses this package's engine + A+ sequence +
fill machinery, so it needed three ADDITIVE, decision-neutral changes here. All three are safe (this
bot's offline tests stay green) and must not be reverted:

1. **`signals.py`** — `Signals` gained `bull_bos_high/low` + `bear_bos_high/low` (the break-leg
   endpoints the B-LEG band-freeze reads). Nothing in the A+ path reads them.
2. **`sequence.py`** — `SeqState` gained `bleg_arm_l`/`bleg_arm_s`, computed at the EXACT Pine point:
   after the opposite-SOS death, BEFORE the continuation-BOS death clears `l_sos_bar` and before the
   half/618 latch update. The B leg arms off state that `update()` has already cleared by the time it
   returns, so the sequence has to expose it here.
3. **`execution.py`** — the A+ arm decision was extracted from `_place_entries` into `_armed()` (a pure
   refactor) so the B-LEG subclass can reuse the "A+ has priority" gate. No behaviour change.

Full context in `strategies/python/mpc_bleg/CLAUDE.md`.



## `Trade.tp_rungs` — the closed record says how much each rung TAKES OFF (2026-08-21)

`Trade.tp1` / `tp2` say only WHERE a rung sits. At the shipped `exec_tp1_pct = exec_tp2_pct = 0`
nothing is ever sold at either one — the position rides the runner and the rungs only stage the
stop — so a chart reading two prices off a closed trade drew two profit targets that had no orders
behind them, on every trade of every run. `tp_rungs` carries the same two rungs as
`(price, banks_pct)` pairs beside the prices. Full finding, and the two `TP1` chips on one trade
that started it: `command-center/backend/CLAUDE.md` → *The exit ladder*.

`_advance_stage` tests rung 1 before rung 2, so on a flipped trade the stop goes straight from
stage 0 to stage 2 without ever arming breakeven.

| | total | trades moved | breakeven scratches |
|---|---|---|---|
| as it ships (rungs in the strategy's own order) | **+151.99R** | — | 45 |
| stage 1 at the NEARER rung, stage 2 at the further | +147.57R | 17 (11 worse, 6 better) | **54** |

Arm-by-arm table, the mutation map, and the two process failures that nearly published a wrong
number: `docs/SOS_FADE_BUILD_NOTES.md` → *The stop that never moved*.
Tests: `tests/test_excursion_arm.py` (13, all watched RED by mutation).



## Every entry method OWNS its stop rule — the precedence list is gone (2026-08-27)

**The stop used to be resolved by walking a list of rules and taking the first that matched, and
that list had a defect.** The reclaim's own protection sat ABOVE the general one, so on a reclaim
that the general rule had already tightened, the reclaim's rule would fire later and hand back a
**looser** stop.

**Aaron, 2026-08-27:** *"For all my different entry types, they should have their own take profit
and stop loss rules. They shouldn't be, like, a list of stop loss rules, and now I need to go
figure out which one has precedence over the other."*

**So there is now exactly ONE rule per entry method.** `_protect_rule()` returns the pair belonging
to the method that opened the trade — keyed on `_entry_src`, the value `secondary.py` stamps on the
arm — and nothing else is consulted. **A retreat is unreachable rather than merely unobserved,
because there is no second rule to override the first.**

| entry method | its pair |
|---|---|
| the normal entry | `exec_be_arm_r` / `exec_be_keep_r` — the PRIMARY's now, not everyone's |
| re-entry off a reclaim | `exec_rec_be_r` / `exec_rec_be_keep_r` |
| re-entry off a gap in the zone | `exec_gap_be_r` / `exec_gap_be_keep_r` (new) |
| re-entry off a structure shift | `exec_shift_be_r` / `exec_shift_be_keep_r` (new) |

Tests: `tests/test_stop_rule_per_method.py` (37; 18 watched RED against HEAD in a detached
worktree, and the file's docstring records the four mutations that re-prove them).

Tests: `tests/test_execution.py` (2, both watched RED against HEAD).



## The re-entry rests its order and LEAVES it — and what the 1m feed is actually for (2026-08-21)

`exec_sec_rest_and_leave`, ON by default. Once the side arms, the order stays where it was placed
at the price it was placed at, until the setup that placed it dies (a new break of structure), the
leg is traded or goes dead, or a position opens. Before this the arm was recomputed from scratch
every bar, so any one of a dozen gates closing pulled the resting order back off the book.

| fill clock | re-decided every bar | rested and left |
|---|---|---|
| 1m | 235 trades, +147.57R | 234 trades, +147.56R |
| 15m | 234 trades, +136.38R | 233 trades, +136.36R |

| fill clock | bars loaded | trades | total |
|---|---|---|---|
| 1m | 2,804,720 | 234 | +147.56R |
| **5m** | **561,795** | **234** | **+145.61R** |
| 15m | 187,286 | 233 | +136.36R |

One fifth of the data for 1.3% of accuracy, against 7.6% at 15m.



## The re-entry's FILL CLOCK is 5 minutes, and it is an accuracy knob (2026-08-21)

`exec_sec_fill_tf_min`, default **5**. The primary always replays on 15m; this is the second feed
`run_dual` walks alongside it, and it is what the re-entry's resting order is filled against.
**The strategy OWNS this number** — `backtest/tools/run_report.py` reads it off the config, and
`command-center` keeps a copy in `run_feeds.EXTRA_FEEDS` that a test refuses to let drift.

MEASURED 2026-08-21, XAUUSD 2018-09-14 → 2026-08-20, matched basis, only the fill clock differing:

| fill clock | bars loaded | trades | total |
|---|---|---|---|
| 1m | 2,804,720 | 234 | +147.56R |
| **5m** | **561,795** | **234** | **+145.61R** |
| 15m | 187,286 | 233 | +136.36R |

One fifth of the data for 1.3% of accuracy, against 7.6% at 15m. It was hardcoded `1` in both
runners for as long as they existed, so every run anybody made paid 2.8M bars for that 1.3%.



## What the 1-minute STRUCTURE engine contributes at the shipped trigger (2026-08-21)

`Structure1m` runs on every bar of the second feed under **every** trigger, including the ones
that use no 1m leg — `secondary.py` step 3 says so in its own comment. At the shipped
`exec_sec_trigger = "FVG in zone"` it **prices nothing**: the entry is the primary's own resting
price (`_edge` → `poi`), the stop is `sig.fibo_p6`, a 15m fib (`_stop_anchor` never touches `m1`
for that mode), and `exec_sec_req_m1_dir` is OFF so `m1.direction` is ignored.



## 🔴 The worst price a trade reports is bounded by its STOP — `_widen_hold` (2026-08-22)

The hold's high/low is widened with each bar BEFORE that bar's exits resolve, so it used to take
the bar's whole range. On the bar that stops the trade out, the far end of that range is price
**after the position is flat**, and it was being recorded as the trade's own drawdown.

**MEASURED on run `976aff9ec279` (206 trades) before the fix: 77 of 77 trades that exited at their
stop recorded a worst price beyond it** — median 0.18R past, worst 4.41R. One short lost exactly
1.0R and reported **2.22R of adverse excursion**; its chart drew a drawdown marker, and its own
win/loss chip, a full 1.2R **above** its `SL` line. That is what made Aaron ask.

**MEASURED after, same window replayed 2020-01-01 → 2026-08-22, 156,811 bars, 160 trades:**
worst-price-past-the-stop **54 → 4**, 59 trades' deepest price corrected and their adverse dollars
with them, and **every trade's R byte-identical** — total +141.177388543R both sides, 0 trades
moved, 0 favourable extremes moved. `compare_strategy.py` **exit 0 on three exports** at warmup
1000 (`bfe65`, `4fef8`, `49f80`), before and after.

**Tests:** `tests/test_excursion_bounds.py` (7), watched RED by five mutations — removing the
bound, ignoring a gapped open, replacing the running extreme instead of bounding it, clamping the
favourable side too, and comparing a shifted bar against an unshifted stop.



## The SHORT-HOLD variant — `exec_short_hold` (2026-08-24, ships OFF)

A second way of trading the SAME setups: close at a fixed R instead of banking a little and
riding the rest. Three rules behind one toggle — refuse an entry deeper than a fib, close the
whole position at a multiple of risk, and refuse a New York hour window.

**With the toggle off the run is byte-identical** — 158 trades, +130.8R over 2020-01-01 →
2026-08-06 on the ECN tier, diffed on every decision field of every trade rather than on the
count and the total, because a run that RESHUFFLES which setups it took agrees on both of those.

| | trades | total R | R/trade | worst DD | scratches |
|---|---|---|---|---|---|
| A+ shipped | 158 | +130.8 | +0.828 | −6.0R | 32 |
| the pool, A+ exits | 109 | +22.5 | +0.207 | −13.7R | 33 |
| the pool + this variant | 104 | **+10.4** | +0.100 | −10.2R | **1** |

Full build story, every configuration replayed, the three tests that could not go red and what
was done about them: `docs/SOS_FADE_BUILD_NOTES.md` → *The short-hold variant*.



## Do / Never

- **Do** port any change to `mpc_strategy.pine`'s A+ block or execution layer here line-for-line, then
  re-run `compare_strategy.py`. Keep the Pine the source of truth — never edit it to match the Python.
- **Do** read engine OUTPUT only (`backtest.replay` `BarState`) — never reach into an engine's internals.
- **Never** build a second copy of any engine here — this consumes the canonical `engines/`.
- **Never** trust a backtest number until `compare_strategy.py` is exit 0 on a fresh export.
- **Never** commit a real TradingView export or backtest cache into git.
- **Never** revert the three B-LEG parity-safe additions above without also updating `mpc_bleg/`.



## References

- Spec: `docs/MPC_SOS_FADE_SPEC.md`; build plan + order: `docs/MPC_SOS_FADE_BUILD_PLAN.md`.
- Pine source of truth: `strategies/tradingview/mpc_strategy.pine` (A+ block ~3708-3972, execution ~4112-4735).
- Upstream runner: `backtest/CLAUDE.md`; engines: `engines/*/CLAUDE.md`.

---



## 🔴 THE RE-ENTRY LADDER COMES OUT BACKWARDS ON ONE HALF, AND THE FLIP IS PROTECTIVE (2026-08-25)

**The two rungs are priced by two different rulers.** The first is a multiple of the trade's OWN
risk (`exec_sec_tp_r`, 1.25R); the second stays the frozen 15m fib. The first therefore MOVES with
the fill price and the second does not, so how close you get filled decides whether they come out
in order. MEASURED on run `ed21fca08a91` (XAUUSD.p M15, 2020-01-01 → 2026-08-23, PU Prime ECN
costs), 91 re-entries:

| half | n | flipped | second rung, as a multiple of the first |
|---|---|---|---|
| after a STOPPED primary (reclaim) | 47 | **0** | 1.474 – 2.263 |
| after a BREAKEVEN primary (gap) | 44 | **27 (61%)** | 0.268 – 3.662 |

The gap half stops at the deep fib — a WIDE stop — so 1.25× that width routinely overshoots the fib
target. The reclaim half enters at its level with a stop a median 0.43R away, so its rung lands
short of the fib every time. **Only the gap half can flip, and it flips more often than not.**



## The second rung as a CHOSEN distance, not leftover geometry (2026-08-25)

**For a re-entry the second rung means nothing deliberate, and that is the finding.** It is a
retracement level of the swing the ORIGINAL setup formed on — a price fixed on the chart when the
setup appeared. A primary enters where that ladder expects, so the rung is a real target and all
155 primaries on run `f3e8bc41db50` were correctly ordered. A re-entry enters somewhere else, so
what is left to that same price is an accident of the fill: MEASURED across 90 re-entries it lands
between **0.27× and 3.66× the first rung's distance, median 1.47×, with 25 of 90 INSIDE the first
rung.**

TESTED: 15 tests in `tests/test_sec_tp2_level.py`, 6 mutations run and all killed. Full sweep table,
the run ids and the entry-by-entry divergence check: `docs/SOS_FADE_BUILD_NOTES.md`.



## 🔴 THE TWO RE-ENTRY HALVES ARE TWO FEATURES, AND ONLY ONE OF THEM EARNS (2026-08-23)

The combined trigger runs **two independent re-entries** and the run report adds them together,
which is how one of them hid inside the other's result for as long as it existed. They ask
different questions of the primary: the **gap** half needs the A+ to have scratched at breakeven,
the **reclaim** half needs it to have been STOPPED. Each trade records which.

MEASURED 2026-08-23 — XAUUSD M15, 2020-01-01 → 2026-08-23, no cost layers, 10% per trade
compounding, three runs off ONE run's own row with a single field changed, driven through
`services/python_runner._execute` so the only difference is the flag:

| | trades | total | worst run of losses | account drop |
|---|---|---|---|---|
| A+ alone | 159 | +139.71R | −5.61R | −45.6% |
| A+ + reclaim (after a stop) | 205 | **+169.71R** | −6.13R | −43.9% |
| A+ + both | 249 | +177.89R | −6.41R | −43.3% |



## Where the reclaim banks: 3.0R → 3.25R, and the 0.25R that costs nothing (2026-08-27)

**MEASURED on the live bot's own stance** — every stop rule at never-move, the whole position off
at the target, no runner — over **47 reclaims**, XAUUSD.p M15+M5, 2020-01-01 → 2026-08-23, nine
targets replayed on one frozen checkout so no code moved between them:

| bank at | total | winners |
|---|---|---|
| 2.00R | 13.00R | 20 |
| 2.25R | 14.75R | 19 |
| 2.50R | 19.50R | 19 |
| 2.75R | 24.25R | 19 |
| 3.00R | 25.00R | 18 |
| **3.25R** | **29.50R** | **18** |
| 3.50R | 29.50R | 17 |
| 3.75R | 14.75R | 13 |
| 4.00R | 13.95R | 12 |



## 🔴 THE RECLAIM'S GIVE-BACK — FIVE FIXES REPLAYED, FOUR LOSE, AND THE EXCHANGE RATE SAYS WHY (2026-08-24)

The reclaim half banks 100% at its target and its stop does not move until that target is
touched, so every trade is **+3.25R or −1R** with nothing in between (the target was 3.0R until
2026-08-27 — see *Where the reclaim banks* below). Aaron's 2025-08-19 reclaim ran **+2.98R**,
missed by **7.5 cents**, and paid the full loss. Five ways of fixing that were
replayed on the shipped basis. **Full grids, per-band splits and the run ids:
`mpc_sos_fade_optimization.md` → the 2026-08-24 run.**

| idea | reclaim book | vs shipped |
|---|---|---|
| bank earlier (target 1.25R) | +10.25R | −19.75R |
| move the stop to breakeven | +23.77R | −6.23R |
| enter at market, not on the retest | +23.11R | −6.89R |
| halve the stop zone at halfway | +29.00R | −1.00R |
| **expire the resting order after 12h** | **+38.00R** | **+8.00R** |



## 🔴 The minimum stop distance permits a stop a normal gap can double (2026-08-23)

MEASURED in the same run: one trade lost **−1.98R on a 1R stop**. Its stop was **$1.83 wide,
0.093% of price**, and price gapped **$1.80** straight through it, filling at the next bar's open.



## Loss recovery — the toggle, and the one property it must never break

**Added 2026-08-20.** `exec_recovery` turns on a counter-trade after this bot loses. The RULE is
not here — it lives in `strategies/python/loss_recovery/`, defined against a `LossEvent` protocol
so any strategy can drive it, and that file owns every measurement. This section is the WIRING
only: `recovery.py` (the adapter), the seven `exec_recovery_*` inputs, and the `finalize` hook.



## 🔴 The toggle's warning text was WRONG in the direction that flatters the rule (rewritten 2026-08-21)

The `desc` on `exec_recovery` in `mpc_sos_fade.meta.json` opened *"THIS SWITCH DOES NOT MODEL ONE
ACCOUNT"* and quoted **+3.8% against +44.8% on one real balance**. Three things were wrong with it,
and the third is the one that mattered.

MEASURED end to end on XAUUSD M15 2018-09-14 → 2026-08-14 at `puprime_ecn`: 181 A+ trades
unchanged, 65 recovery trades added, median recovery risk $2,050 against A+'s $10,127. **All 65
reach the chart's full profit-depth view; none falls back to the plain box.**



## The DEAD-MARKET floor — `exec_min_atr_pct` (2026-08-26, ON at 0.08)

A second entry filter beside the minimum stop distance, asking a **different question**: not *is
the leg long enough to size against* but *is the market moving at all*. A dead market throws up
wide stops as happily as tight ones, so the stop floor does not catch this and never could. Full
measurement, the driver it was taken with and the two near-misses: `docs/SOS_FADE_BUILD_NOTES.md`
→ *The dead-market floor*.

| export | floor on the chart | verdict | setups the floor REFUSED |
|---|---|---|---|
| `…15_b5eda.csv` | 0.08 (shipped) | exit 0 | **0** |
| `…15_3ce38.csv` | 0.30 (driving) | exit 0 | **21 of 26** |

Both 21,355 bars, 2025-10-01 → 2026-08-26, green at warmups 100 / 500 / 1000 / 2000, both
carrying `cfg_min_atr` so the harness configured the floor from the chart rather than from a
default. On the second, Python and Pine agree bar-for-bar **while the floor is refusing four out
of five setups** — 9 trades / +10.64R against the control's 26 / +29.06R on the same bars.



## 🔴 The leg latch's bar-time map was re-sorting 20,000 keys EVERY BAR (fixed 2026-08-26)

The map that made the one-trade-per-leg latch survive a restart (above) is capped at 20,000
entries. Its prune called `sorted(self._bar_ms)` to find the one key to delete — and once the cap
is reached that runs on **every single bar for the rest of the run**.

**MEASURED under cProfile on a 23,539-bar year: 3,539 sorts were 8.0s of a 52.6s replay — 15%,
and the largest single cost in the whole profile.** Measured end to end on 62,468 bars, both
algorithms in ONE process with only the branch differing: **189.76s → 81.25s, the whole replay
2.34x faster.** The 6.6-year window pays that prune 135,807 times.

**TESTED:** 16 in `tests/test_bar_ms_prune.py`, two mutations watched RED — pruning the newest
instead of the oldest reddens 9, dropping the order latch reddens 3. The key-set claim is
asserted against a re-implementation of the ORIGINAL algorithm rather than against a hand-typed
constant, so it cannot re-freeze my own reading of it.

