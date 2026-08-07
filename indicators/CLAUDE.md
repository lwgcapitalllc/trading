# CLAUDE.md — indicators/

**Purpose:** From-scratch Pine Script rebuild of the "Structure OS / SMC Engine" market-structure indicator (swing highs/lows, HH/HL/LH/LL, BOS, CHoCH), replicating a private TradingView indicator's behavior using a pullback-only detection method.
**Scope:** This covers Pine Script indicator development and the market-structure detection engine only. It does NOT cover trading strategy logic, risk management, or any live/backtest execution — this is a charting indicator, not a bot.
**Status:** Under construction — Stage 2b (break-gated swing structure + BOS/CHoCH) is ~95% validated against the original; Stage 3 (internal structure) and Stage 4 (multi-symbol/timeframe comparison) not started. Blocked on chart validation by Aaron before Stage 3 begins.
**Last reviewed:** 2026-08-06 (latest) — 🟢 **`execTimeStopHrs` 36 → 8 IN THE B-LEG PAIR, AND THE A+ PAIR DELIBERATELY KEEPS 36.** Both tooltips rewritten with the fork's own measured figures. Charged over 186,312 M15 bars, one axis per row: **8h → 114 trades / +17.56R / PF 1.45 / maxDD 5.15R** against 36h → 112 / +12.02R / 8.89R and Off → 111 / +6.50R / 12.01R. **The two forks measured the same lever on their own trades and got different plateaus — A+ 24h–40h, B-LEG 4h–12h — so this is a fork, not drift, and "reconciling" them would move every B-LEG exit to a number measured on a different strategy.** ⚠ **A DEFAULT and two tooltips only — no input added, renamed or reordered** — so TradingView's saved-value keying is untouched and **no "Reset settings to defaults" is needed**; the flip side is that an existing chart keeps whatever is already set, so confirm on the panel rather than assuming 8 is live. ⚠ **`execTimeStopMode` stays "Before TP1 only" on BOTH files and the `lStage == 0` / `sStage == 0` term must not be tidied out of `lTimeUp`/`sTimeUp`** — it is what makes the clock cut no winners, and a test now greps both Pine files for it. ⚠ **NOT COMPILED and NOT PARITY-RE-VALIDATED**; `compare_bleg.py` reads `cfg_time_stop_hrs` off the export, so an export taken before today decodes 36 and proves nothing about 8, and the clock has still never fired inside a parity window. Full measurement, the exit-stage map, and the four "let the winner run" levers that were tried and all LOST money: `strategies/python/mpc_bleg/CLAUDE.md`. Earlier the same day: 🔴 **`eqExemptFvg` WAS DEFAULTED ON IN THE A+ PAIR WITH NO EXPORT COLUMN AND NO PYTHON PORT, AND IT COST THREE DAYS OF A RED PARITY GATE.** `b1b461b` (2026-08-03) flipped that input `false → true` in `mpc_strategy.pine` and `mpc_strategy_export.pine` — deliberately, with a real measurement behind the rule change — **while the comment block eight lines above it still read "⚠ THE EXEMPTION DEFAULTS OFF HERE" and went on to name the exact consequences: "it changes which gaps exist, so it changes which entries fire… backtest/replay/EngineStack does not wire them yet, and no cfg_ column carries this input into the export builds."** Every word of that warning was correct and it was left standing over the flipped default. 🔴 **So the Pine and the live Python bot evicted different gaps for three days**: at bar 11031 of a 21,999-bar export Pine rested a limit on a liquidity-pinned gap edge (4965.73) that Python had FIFO-dropped, and `compare_strategy.py` reported it as an entry-RULE mismatch — the entry rule being identical on both sides. **Both export Pines now plot `cfg_eq_exempt`** and the harnesses configure the Python engine from it; an export with no such column is **REFUSED**, not defaulted, because the input predates its column by three days so neither answer is a fact about the file. ⚠ **The detection constants are deliberately NOT exported** — `eqPivotLen` / `eqAtrMult` / `eqMax` are hardcoded (2 / 0.1 / 6) precisely so the indicator and the strategy cannot draw different levels; export them the day either side makes one an input, not before. ⚠ **`mpc_b_leg_strategy_export.pine` got the column too even though that fork ships the input `false`** — both sides read 0 today, which is exactly what turns *two defaults that happen to line up* into a measured agreement. 🔴 **`fvg_export.pine` was found carrying the SELF-CANCELLING cap rule the indicator fixed in the same `b1b461b`** — it counted every gap while its drop scan skipped the exempt ones — so the harness that validates `engines/fair_value_gaps/` had gone stale against both the Pine it mirrors and the engine it checks, and the next export would have reported a correct engine as red. Fixed here. ⚠ **NOT COMPILED** — there is no local Pine compiler, and both A+ files sit near CE10117; the three edits are one `plot()` each plus one counting loop in `fvg_export.pine`, so they are small but not free. ⚠ **A new `plot()` is appended at the END of each export's PARITY block, so no `input.*` order moved and no saved chart setting shifts** — no "Reset settings to defaults" is needed for this paste. ✅ `compare_strategy.py` exit 0 at warmups 100 / 500 / 1000 / 2000 on the existing export with `--eq-exempt on`, and `--eq-exempt off` reproduces the original mismatch exactly. **The standing lesson is about where a warning lives: the comment was right, specific, and directly above the line that invalidated it — and a comment cannot fail a build. The export COLUMN is the guard; prose is not.** Earlier the same day: 🟢 **TWO B-LEG DEFAULTS MOVED, AND ONE OF THEM WAS A `maxval` RATHER THAN A NUMBER.** `mpc_b_leg_strategy.pine` and its export mirror: **`execTrailPct` 1.0 → 0.05** and **`bLegMaxDays` 1.25 → 4.0 with `maxval` 3 → 6**. Both tooltips rewritten with the measured figures. 🔴 **The `maxval` is the finding: 4–5 days measures best and the input could not express it, so the old 1.25 was never a tuned value — it was a cap nobody had checked.** Charged over 186,312 M15 bars: 1.25 → 59 trades / +7.29R · 3.0 → 92 / +10.56R · 4.0 → 112 / +12.02R · 5.0 → 118 / +13.76R, degrading past 5. **A `minval`/`maxval` is a claim about where the useful range ends, and it is exactly as unmeasured as any other constant until somebody sweeps past it.** 🔴 **`execTrailPct` was inert on this fork for its whole life, for a UNIT reason rather than a tuning one:** it is a percent of PRICE, and a B leg's whole 1R is 0.13%–1.25% of price, so at 1.0 one trail step is bigger than the entire trade and `f_swingRatchet` can never climb above the stage-2 floor. That floor is `TP1 price`, and a B leg's TP1 is exactly 1R from the entry by construction (`2*edge − inv` against a stop at `inv`) — so the runner banked precisely +1.00R and handed back the rest, on nine of fifty measured trades, one of them after running +6.82R. ⚠ **`mpc_strategy.pine` KEEPS `execTrailPct` at 1.0 and must not be "reconciled"** — the A+ sweep gives 0.25% → 43.6R against 109.3R at 1.0, i.e. the opposite conclusion, because an A+ stop is a fib fraction of a leg on a ladder whose rungs are also fib levels. **Same input name, same tooltip, different right answer either side of the fork.** ⚠ **DEFAULTS and one `maxval` only — no input was added, renamed or reordered**, so TradingView's saved-value keying is untouched and **no "Reset settings to defaults" is needed**. The flip side is that **an existing chart keeps whatever Aaron already has set**: a changed default reaches a fresh paste and nothing else, so confirm on the panel rather than assuming the new values are live. ⚠ **`bLegMaxDays` 4.0 is inside the NEW `maxval` and outside the old one** — a default outside its own input's range is a config the Pine cannot express, which would put `compare_bleg.py` red on the first export at shipped settings; a test now reads both Pine files and asserts the default sits inside `[minval, maxval]` and equals the Python config. ⚠ **The export mirror took the identical edit and was re-diffed: lines 1–4763 are byte-identical to the parent apart from line 40's title**, verified by an actual diff after an earlier check passed vacuously on two empty files (the split marker grep matched nothing and both `sed` ranges errored to empty — *a diff of nothing against nothing is green*). ⚠ **NOT COMPILED and NOT PARITY-RE-VALIDATED.** Parity is structurally unaffected because `compare_bleg.py` configures Python FROM `cfg_trail_pct` / `cfg_bleg_days`, **but a green run on an export taken before today decodes the OLD values and says nothing about these** — the same "green on a branch neither side entered" trap the min-stop guard hit. Full measurement, the four rejected levers and the unshipped Asia-session lead: `strategies/python/mpc_bleg/CLAUDE.md` → *The exit-ladder re-default*. Earlier the same day: 2026-08-06 — 🟢 **A TIME STOP LANDED IN ALL FOUR STRATEGY FILES, AND THE PINE MECHANIC IS WHERE THE INPUTS ARE DECLARED.** `execTimeStopMode` ∈ {**"Off"**, "Before TP1 only", "Always"} + `execTimeStopHrs` (36.0) in `mpc_strategy.pine`, `mpc_b_leg_strategy.pine` and both export mirrors, closing a long or short that has been open that many calendar hours **and still at stage 0** (TP1 never touched — `"Always"` drops that gate). **Defaulted ON ("Before TP1 only", 36h) on 2026-08-06 in all four Pine files, so a chart re-pasted after that date trades differently.** 🔴 **The stage gate is the whole lever and the Python replay measured how much: same 36-hour clock, `Before TP1 only` = +142.17R against `Always` = +97.32R on a +137.94R baseline — a THIRD of the edge, because `Always` cuts 26 trades where the gated version cuts 6 and the 20 extra are winners.** Do not "simplify" the `lStage == 0` term out of `lTimeUp`. ⚠ **THE INPUTS ARE DECLARED NEXT TO THE EXIT BLOCK (~4960), NOT UP IN THE GRP_EXEC PANEL WITH THEIR SIBLINGS, AND THAT MUST NOT BE "TIDIED UP".** TradingView keys a chart's saved input values off **declaration order within each type**, so inserting a string and a float at ~483 would shift every later string/float and silently reset them on every chart Aaron runs this on — the exact hazard this file warns about after the 2026-08-05 `mpc_assistant.pine` insert. The last `input.float/string/int` in the file is `execBeBandR` (~4050), so declaring the pair down at the exit block shifts **nothing at all**; `group = GRP_EXEC` still files them under Strategy Execution, only their position within that group moves. **So no "Reset settings to defaults" is needed for this change** — which is the whole reason it was done this way. ⚠ **`lEntryTime` / `sEntryTime` are new state**, assigned at the fill beside `lEntry`, because the clock has to run from the FILL — a resting limit can wait days. ⚠ **The close is `else if` after `execCloseOppSOS`**, mirroring the Python's `elif` chain exactly, so the three force-close paths keep ONE precedence on both sides. ⚠ **Both export mirrors were REGENERATED off their parents** by the documented splits and re-diffed: **exactly the line-32 / line-40 title differs**, nothing else. They carry two new columns, `cfg_time_stop` (`Off?0 : Before TP1 only?1 : Always?2`) and `cfg_time_stop_hrs` raw — deliberately NOT folded into `cfg_exitmode`, which is the two ladder DROPDOWNS. **Absent column ⇒ Off in the decoder, never the Python default**, so archived exports still replay correctly. ⚠ **NOT COMPILED — there is no local Pine compiler — and NOT parity-validated.** `mpc_strategy.pine` has hit CE10117 twice; this adds two inputs, two `var int`s, two bool expressions and two `strategy.close` branches, so it is small but not free. **A parity run taken at the Off default would prove nothing about this lever** — export with the mode ON and check the trade list actually contains `time stop` closes, the same "was the feature EXERCISED" check the min-stop guard needed the same week. Earlier the same day: **THE 1m SHOWS ITS FAIR VALUE GAPS AGAIN, THE CAP STOPPED THROWING AWAY THE ONES THE TRADE IS TAKEN FROM, AND THERE IS A NEW BIAS TOGGLE.** Three changes, `mpc_assistant.pine` ONLY, and the reason they stop there is the same one every time: each of them decides WHICH GAPS EXIST, so porting any of them to `mpc_strategy.pine` moves entry edges, moves trades, and puts `compare_strategy.py` red. **(1) `f_fvg1mZone()` IS DELETED.** It ran on the 1m chart alone and blanked every gap outside the External Fib's entry band — so an out-of-band gap was hidden, and, because the band came FROM the fib, **a 1m chart with no aligned REV setup showed no gaps AT ALL**, which is most of the session. That gate needs `rStage >= 3` plus a 1m SOS in the 15m's direction confirming after the 15m SOS closed; the bar for drawing a gap was far higher than "is there a gap here". The 1m now draws on exactly the same rules as every other timeframe. ⚠ **Deleted, not made inert** — this file sits at Pine's compile-token cap (CE10117), so a dead branch is not free. ⚠ **`mpc_m15_playbook.pine` still has its own copy at ~3457 and was deliberately left alone.** **(2) THE ENTRY-ZONE GAPS ARE NOW EXEMPT FROM `fvgMaxCount`.** The complaint was the cap working exactly as written: after a bearish SOS price drops and prints gap after gap on the way down, the FIFO drops from the FRONT, and **the oldest gaps on a retrace setup are the ones UP IN THE ENTRY ZONE — the only gaps the trade is ever taken from.** The chart was discarding the levels being watched to make room for levels below price that nothing reads. A gap overlapping the live fib's **0.382–0.886** band **on the trade's own side** no longer counts against the cap and is never chosen for eviction; it rides on top exactly as an EQ-backed gap does. ⚠ **Both loops — the COUNT and the DROP SCAN — apply the same exemption**, which is the whole lesson of the 2026-08-03 EQ fix: a protected gap that still holds a slot evicts an ordinary one in its place, and the exemption becomes self-cancelling. ⚠ **0.382, not 0.5**, is the shallow edge — one rung shallower than the bot's own entry zone, so a gap sitting just above 0.5 survives to be looked at. ⚠ **Direction-matched**: on a bearish leg only bearish gaps are pinned, because the A+ entry rule cannot read the others either. **(3) A NEW `↳ Trend-Aligned FVGs Only` TOGGLE (default OFF) under Fair Value Gaps.** Separate from the shared `Trend-Aligned Zones Only`, and it reads a **DIFFERENT DIRECTION** — that is the load-bearing half. The shared filter reads `st.dir`, the CHART's own structure, which on a 1m chart flips several times inside one 15m leg, so a short's gaps would appear and vanish while the setup never changed. This one reads the **DRAWN FIB's** direction, so it holds for the life of the leg the trade is on. ⚠ **ABSOLUTE — no EQ exemption**, unlike the shared filter: "only gaps with bias" has to mean only gaps with bias. The EQ exemption still protects a counter-side gap from the CAP; this just refuses to draw it. ⚠ Applies to gaps only; order blocks are untouched. **THE PINE MECHANIC WORTH CARRYING:** `fiboP1`/`fiboP6`/`fibo_dir` are declared ~800 lines BELOW the FVG cap, and Pine needs a declaration before its use — so the band and the direction are **PUBLISHED DOWNWARD** into globals declared beside their consumer (`fvgZoneLo`/`fvgZoneHi`/`fvgZoneDir`/`fvgBiasDir`), read one bar late. **The lag is deliberate and is safe only because of WHAT reads it: the cap decides which gap to THROW AWAY, never which one to trade.** ⚠ `fvgZoneDir` is zeroed once the leg completes so a finished setup stops pinning gaps; `fvgBiasDir` is the RAW direction and is NOT zeroed, because the bias filter must keep working after TP3. **Two globals because they answer two questions** — sharing one would tie the filter's life to the cap exemption's. ✅ **COMPILED IN TRADINGVIEW BY AARON, 2026-08-05.** There is no local Pine compiler, so a paste is the only compile gate this file has, and it is the one that mattered here: a new `input.bool` title is a string literal and a malformed one is a compile error, so this proves the toggle and the four published globals parse. ⚠ **It proves the file BUILDS, not that the three rules are right** — the cap exemption, the deletion and the bias filter are all read off a chart, and none of them has a parity harness (they exist only in this file, by design). ⚠ **A new input was inserted mid-list, which shifts every later input's saved value** — TradingView keys saved values off declaration order — so click **"Reset settings to defaults"** once, or the Chart Tools switches read one position out. Earlier the same day: 🔴 **`execMinStopMode` NOW DEFAULTS ON (`"% of price"`, `execMinStopVal` 0.10 → **0.08**) IN BOTH A+ FILES.** Aaron's call after a 23-config sweep over 186,220 M15 bars: the A+ baseline moves **183 trades / +134.75R → 181 / +136.75R**, 0.10 costs 1.84R, 0.15 costs 25R, 0.30 costs 48R. The guard refuses a setup whose stop lands closer to the entry than the floor, because `qty = risk / stop_distance` means a collapsing stop builds a huge position rather than risking less. Both tooltips were rewritten with the measured numbers, `execMinStopVal`'s `step` went 0.05 → 0.01 (0.08 is not reachable in 0.05 steps), and `mpc_strategy_export.pine` took the identical edit so its body stays byte-identical to its parent apart from the title line and the diagnostic-log block. ⚠ **A DEFAULT changed, not an input's order or its title** — TradingView keys a chart's saved input values off declaration order, so **an existing chart keeps whatever Aaron already had set** and only a fresh chart gets 0.08. Do not read the new default as having reached his charts; confirm on the panel. ⚠ **`x ATR(14)` was measured and is the WRONG mode for this guard**, which is the counter-intuitive half: it is the only mode that adapts to volatility and it was the cheapest on R, but at 0.35 and 0.40 it **never refuses the tightest stop in the whole history** ($1.03), because that bar was quiet so $1.03 was not tight *relative to ATR*. The hazard is in price units and volatility does not enter it. The tooltip now says so, since the dropdown otherwise invites exactly that choice. ⚠ **Parity re-run GREEN with the filter FIRING** — `compare_strategy.py` exit 0 at warmups 100 / 500 / 1000 / 2000 on a 21,899-bar export at `"% of price"` 0.30 where **block code 7 was raised 213 times**; an earlier export the same day was green at `"Fixed $"` 0.10 and raised code 7 **zero times in 21,897 bars**, i.e. green on a branch neither side entered. **Before trusting a gate on a Pine feature, check the feature was EXERCISED in the export** — a block-code histogram is the whole check. `mpc_b_leg_strategy.pine` has no such input and is untouched; `compare_bleg.py` exit 0. Earlier: 2026-08-04 — **THE JARVIS TABLE GAINED A GROUP COLUMN, THE EQ LEVELS CHANGED WHAT "TAKEN" MEANS, AND THE 1m STOPPED TRACKING A FINISHED SETUP.** Four Pine changes across `mpc_assistant.pine` and the A+ strategy pair, and the line between them is the one worth carrying: **detection is FORKED on purpose, appearance is SYNCED.**

🔴 **The one real defect: `f_rev15` had three ways to die and the chart-side A+ engine has four.** The missing one is the one that fires on a WIN — `fibo7Touched`, price back at the leg origin. So on the 15m chart the REV row read `Pass` the moment TP3 printed, while the **1m chart kept the same leg alive at stage 4 saying TAKE PROFIT** until an opposite SOS or a continuation BOS happened along, which can be hours. Two charts, two answers, one setup. Worse than a stale row: the RE-ENTRY round trip clears the TP latches when price returns to 0.618, so a finished trade could hand the 1m a fresh AWAIT and ask for a 1m SOS on a leg the 15m had closed the book on. Fixed with `or L_tp0` / `or S_tp0` on the two death conditions — `L_tp0` **is** TP3, since `p0` is `L_high`, the leg origin, the same 0.0 the drawn fib labels TP3. ⚠ **It kills one bar LATE**: the death block runs before the fib block that sets the latch, where the 15m side kills on the bar itself. Left as is — every other value this engine ships crosses the security boundary a bar late in the same way. ⚠ **It retires the whole 1m stack together, not just the row** — `rStage` falling below 3 drops `_m15Retraced`, which is what `fiboShowAligned`, the 1m External Fib, the 1m Sniper Zone and the 1m ENTRY row all hang off. ⚠ **Nothing on the 15m moves**: every consumer of `rStage`/`rTp50`/`rDeepCode`/`rZoneLo` sits behind `_fibOneMin`, `_sn1m`, `revOn1m` or the non-15m branch of the table, checked one by one; `f_rev15` exists only in `mpc_assistant.pine` and `mpc_m15_playbook.pine`, so **no bot and no parity gate can see this.**

**A WICK TAKES AN EQ LEVEL — in the indicator ONLY, and the fork is the point.** The test was `close > lvl`, so a candle that speared clean through an EQH and closed back under it left the line drawn. A close test is the wrong QUESTION for this object: an EQH is not resistance being "broken", it is a **pool of resting stops**, price reaches those stops with its WICK, and whether the candle closed back below describes what happened AFTER the liquidity was taken. Same correction the order blocks got on 2026-07-31, for the same reason. It also makes the deletion STABLE on the live bar — a bar's high only ever grows, where the old close test could delete a level intrabar and put it back on the next tick. Its three dials went back to constants the same day after a few hours on the panel (**sensitivity 0.1 → 0.25, count 6 → 14, extension 50 → gone**), the third time this file has run that expose-measure-lock loop. ⚠ **`mpc_strategy.pine` and `mpc_strategy_export.pine` were deliberately NOT synced on any of that**, and `engines/equal_highs_lows/` still reads a close too. **`eqAtrMult` and `eqMax` change WHICH GAPS EXIST through `eqExemptFvg`, so they change which entries fire** — and `backtest/replay/EngineStack` does not wire `eq_levels` into the FVG engine at all, so Python cannot see an EQ level even in principle. Porting them would move trades AND put `compare_strategy.py` red. **The indicator is a display consumer here; the bot is not.**

**What the strategy pair DID get is appearance, and only appearance.** The EQ line is solid instead of dotted and **ends at the live candle** rather than running `i_lineExtend` bars past it (a pool is not a forecast), and its tag anchors with `style_label_left` + an invisible box instead of `style_none` — `style_none` centres text ON the anchor, so half the glyph sat above the level and read as a tag floating over the line. Plus the **four-column JARVIS table**: GROUP · row · STATUS · INFO, with `SETUP` / `BIAS` / `LIQ` / `STR` printed once on each group's first row. ⚠ **The group tag cannot be latched inside the row helper** — Pine lets a function READ a global but never WRITE one (**CE10088**, the error `ob_export.pine` hit on 2026-07-31) — so the CALLER owns the once-only rule; rows that always print hardcode their tag, LIQ and the EXT/INT pair use a local latch. The LIQ rows needed a real fix rather than a copy: `"LIQ BSL", "BSL", …` rendered as `LIQ | BSL | BSL | Day High`, the same word twice, so STATUS now says **"Swept"** (what happened) and the pool name moved to the row label. Status cells are tinted `color.new(vc, 87)` — **derived from the colour the row already chose, never looked up off the status TEXT**, because these statuses are not a fixed vocabulary and the one a lookup missed would silently render untinted. Palette: charcoal body, black-only header, cyan on the JARVIS cell alone, muted-slate INFO, 1px blue frame replacing the 2px yellow. ⚠ **Panel inputs changed their option lists** — four corners instead of nine, no "Huge" — so **click "Reset settings to defaults" once after pasting**, and note the `=>` switch fallback matters MORE in the strategy than in the indicator because **"Top Center" was the strategy's shipped default**, so every saved chart holds a string the panel no longer offers. ✅ **Cosmetic and earned rather than asserted on the strategy side**: the table reads state and writes none back, `showConfTable` still defaults FALSE there, all **38** `px_*`/`cfg_*`/`dbg_*` columns are still present, and **the export was REGENERATED off the parent by its documented split so the shared body is byte-identical except the line-32 title** (verified by diff, both files carry the identical four-hunk EQ diff). ⚠ **NOT COMPILED — there is no local Pine compiler — and `mpc_strategy.pine` has hit CE10117 twice.** The fourth column adds one `table.cell` per row inside the row helper, so no new main-body statements (CE10295 unaffected), but it does add compile tokens; if CE10117 returns, this block is the first thing to cut again. **The standing lesson is a new one and it is about WHERE a rule may be shared: two files can agree on how a thing LOOKS and still have to disagree about what it IS, and the boundary is whether the rule reaches a trade. An indicator may lead; a bot moves only with its Python port and its parity gate.** Earlier: 2026-08-02 — **ONE NAME AND ONE EXPLANATION PER PARAMETER, SHARED BY THE PINE AND THE LAB.** The two panels had drifted into separate vocabularies for the same settings — the Pine said "Entry: floating gap enters on the nearest fib SHALLOWER than it" where the lab said "Floating gap → nearest fib ABOVE", and the lab's version was **wrong for shorts** (shallower is above on a long and BELOW on a short). A script diffed all 51 lab params against their Pine input titles: **6 matched, 37 differed**. They now all match — **42 of 43 shared params are byte-identical**, and every lab `desc` is that input's Pine tooltip verbatim (43 of 43), so the two UIs cannot teach different things. The one deliberate deviation is `exec_conf_sz`, whose lab label carries a `(not supported)` suffix because the Sniper-Zone entry is Pine-only. Same pass, at Aaron's request: **every execution and divergence tooltip was rewritten short.** They had grown into forensic essays — the `execFvgPreZone` tooltip alone ran ~1,400 characters of measurement narrative. The rule now is what it does, what ON vs OFF means, and the one fact that changes the decision; **the long write-ups live in CLAUDE.md, which is where a reader can actually find them again.** Both A+ Pine files shrank ~6,000 characters and the B-LEG pair ~3,600, so this RELIEVES the CE10117 token pressure rather than adding to it. 10 settings that had no tooltip at all (Trade longs/shorts, Risk % per trade, the stop buffer) got one. ⚠ **Titles only — never a plot title, never a default, never the ORDER of an `input.*` call**, because TradingView keys saved chart settings off declaration order: a rename carries Aaron's saved values, a reorder loses them. Verified after the fact: **35 of 35 execution defaults unchanged**, both export mirrors still byte-identical to their parents except the line-32 `strategy()` title, 363 strategy tests + 337 backend tests green, and **BOTH parity gates exit 0 at warmups 100 / 500 / 1000 / 2000** on fresh 21,715-bar `VANTAGE_XAUUSD, 15m` exports taken off the RENAMED files — `compare_strategy.py` (`cfg_bits` 544375) and `compare_bleg.py` (`cfg_bits` 61047). Those exports are also the compile proof: a Pine input title is a string literal, so the only way this change could break anything is a mangled quote, and a mangled quote is a compile error rather than a silent behaviour change. Block reasons were safe to reword because `f_blkWhy` maps an int CODE to display text — the parity stream carries the code (`f_blkCode`), never the sentence. ⚠ **`mpc_bos_strategy.pine` was only partly synced on purpose**: its divergence group and Trade longs/shorts were aligned, but its entry inputs ("...and require one (no gap = no trade)") describe a genuinely different setup and were left alone. **Earlier the same day: the A+ panel's shipped defaults were set from Aaron's own screenshot, and the export now CARRIES the entry model.** `execFvgPreZone` was briefly defaulted ON earlier the same day and is **reverted to OFF** — the full-panel screenshot he sent is the authority, and it shows the box unticked. Every other visible toggle already matched. `mpc_strategy_export.pine` was regenerated off the parent (body diff back to exactly the line-32 title) and its `cfg_bits` extended with the five 2026-08-02 toggles — **`execFibOverlap` 131072 · `execFibDeepEdge` 262144 · `execFibNearest` 524288 · `execFvgPreZone` 1048576 · `execSlDeep` 2097152** — because without them a parity run configures the Python bot to a DIFFERENT entry model and reports the difference as a logic bug, the exact `execRunnerTrail` trap of 2026-07-26. ⚠ **Bit 65536 stays RETIRED and the new bits start at 131072**; an export taken before today has all five clear, which decodes to Method 3 with the gate off — i.e. the build it came from, so archived exports still replay correctly. **The whole model is now ported to `strategies/python/mpc_sos_fade/`** (see its CLAUDE.md), and the two sides' 23 execution-input defaults were diffed **programmatically, not by eye**: 0 mismatches. ✅ **BOTH FILES COMPILE AND A+ PARITY IS GREEN** — Aaron pasted them and exported the same day, which is stronger evidence than a paste alone: `compare_strategy.py "VANTAGE_XAUUSD, 15_cfa13.csv"` → **exit 0 at warmups 100 / 200 / 500 / 1000 / 2000**, 21,702 bars, 2025-08-31 → 2026-08-02. The export's `cfg_bits` read **544375 with bit 524288 SET**, which is the proof the new plot line compiled AND that the Pine was actually running rule 3 — a green taken with every new bit clear would have validated nothing about this change. ✅ **THE CONFIRMATION TABLE IS RESTORED IN `mpc_strategy.pine`, COMPILED, AND PROVEN TRADE-NEUTRAL.** It had been dead since 2026-07-24: `f_drawTable` was cut for compile tokens and the three inputs survived, so ticking the box drew nothing (it defaults OFF, which is why it went unnoticed — what Aaron had been reading in bar replay was `mpc_assistant.pine`'s copy, or the B-LEG fork's). Aaron uses it for bar replay and asked for it back, so it was **RECOVERED FROM `b25789d~1`, never rewritten from memory** — this file's OWN table, not the near-identical fork in `mpc_b_leg_strategy.pine`. Restored in three places: the JARVIS colours, the `ext_struct`/`int_struct`(+`_bar`/`_valid`) slots with `jarvisTable` + `f_jRow3`, and the 92-line `f_drawTable` with its single main-body call — which also revives the orphaned `f_tablePosition`/`f_tableSize`. The SNIPER-ZONE slot was deliberately NOT restored: the table never read `sz_status`/`sniperZoneActive`, so it was dead weight even before the cut. Budget came from the ~207 lines freed earlier the same day. ✅ **PROVEN COSMETIC BY MEASUREMENT, NOT BY ARGUMENT** — a second export was taken off the rebuilt Pine at the identical config (`cfg_bits` 544375 both times) and the two exports' `px_*` decision streams were diffed cell-by-cell over their **21,702 shared bars: 21,701 byte-identical**, the only differences being the four columns on the FIRST export's still-forming last bar (NaN then, real values now — the documented TradingView artifact `compare_strategy.py` already skips). Not one fill, exit, stage, block or R moved. Parity re-run on the new export: **exit 0**. ⚠ **If CE10117 returns, this block is the first thing to cut again** — the file has hit that cap twice. Earlier the same day: **28 unused toggles deleted from `mpc_strategy.pine`, and the export regenerated behind it.** Aaron asked which settings he genuinely never touches; the audit found 157 inputs, and he approved cutting four things. Gone: the whole **Cycle Fib** input group (27 inputs — master toggle, line extension, draw-up-to-timeframe cap, and a show/colour/style trio for each of eight levels) together with its drawing block, its two style helpers, its eight line+label handles, the eight touched-flags that only coloured them, `MACRO_GREY`, `macroFibAllowed` and `macro_visible`; and **`execFvg50`** ("Entry (least favorable): FVG must touch the 0.5 line") with its fallback loop. 157 → **129 inputs**, 207 lines lighter, which is real headroom in a file that has hit CE10117 twice and sits near CE10295. ⚠ **THE CYCLE FIB'S TRACKING STAYS AND IS LOAD-BEARING — only the DRAWING went.** `macro_origin` / `macro_extreme` are the A+ sequence's HTF POI (`poiLongNow` / `poiShortNow`) and the B-LEG log line's premium/discount zone; both gate on `macro_origin_locked` alone and never read `macro_visible`, which is why that latch could go with the lines. Every value the execution layer reads is byte-identical, so **no trade moves** — the removals are cosmetic-only by the same grep test the Kill Zones / VWAP / Order Blocks / SVP cuts used, re-run here (zero references to any deleted identifier). **`mpc_strategy_export.pine` was REGENERATED off the parent in the same pass** by its own documented split (`sed -n '1,4682p'` + the appended PARITY block), because a deleted input with its consumer still in place is precisely the `CE10272` failure of 2026-07-26 — the export's `cfg_bits` plot still read `execFvg50`. Body diff vs the parent is again **exactly the line-32 title**, and all 25 `px_*` / `cfg_*` / `dbg_*` columns verified present. ⚠ **`cfg_bits` bit 65536 is RETIRED, NOT FREE** — it carried `execFvg50`, now always reads 0, and `compare_strategy.py` still refuses an ARCHIVED export that has it set (read straight off the bit now, not through a config field). **Do not reuse 65536 for a new toggle**: an old export would decode the new flag as whatever `execFvg50` was. Python side cleaned in lockstep — `exec_fvg_50` removed from `config.py`, from the lab panel (`meta.json`), and from both harness encoders. **129 strategy tests green.** ⚠ **NOT compiled** — there is no local Pine compiler, so both files still need pasting into TradingView, and **"Reset settings to defaults" must be clicked once** (TV maps saved input values by POSITION, and 28 inputs were removed from the middle of the panel). ⚠ **`mpc_b_leg_strategy.pine` and its export STILL carry `execFvg50` and the full Cycle Fib group** — deliberately out of scope (Aaron's request named the A+ file), so this is a KNOWN fork, not an oversight. ⚠ **The three "Confirmation Table" inputs are still there and still DEAD** — `showConfTable` / `tablePositionInput` / `tableSizeInput` read by nothing since the table was deleted 2026-07-24, plus the orphaned `f_tablePosition` / `f_tableSize` helpers. Aaron says he USES that table for replays; the working one is in `mpc_assistant.pine` (default ON), so **ticking the box on the strategy draws nothing**. Decide before deleting: drop the three dead inputs, or rebuild the table here at a real token cost. Earlier: 2026-08-01 — 🔴 **THE PHANTOM-EXIT BUG IS FIXED, AND IT WAS IN EVERY STRATEGY FILE.** `BUG_exit_fill_price_mismatch.md` (open since 2026-07-14, "all three legs at one price one bar after entry") was never a TradingView fill artifact — it was **the FILL BAR being allowed to stage the stop**. A resting limit is reached by price coming to it from the wrong side (a buy limit fills on the way DOWN, a sell limit on the way UP), so the entry bar's *favourable* extreme is the approach to the order, not a move the trade made. The staging block read it anyway, `sStage` went to 1 on the fill bar, the stop went to `sEntry - beBuf` — **below** the entry for a short, i.e. already through the market — and TradingView market-closed every leg at the next bar's open. Confirmed on real Vantage bars for the reference trade (entry bar 2025-09-09 06:30 UTC: low **3637.80**, ten dollars below the 3647.91 fill, all of it pre-fill; `sTP1` was 3645.21) and reproduced against the real Python `Execution` class. **Fixed in all five strategy Pine files** (`mpc_strategy`, `mpc_strategy_export`, `mpc_b_leg_strategy`, `mpc_b_leg_strategy_export`, `mpc_bos_strategy`) — the staging block is gated `and strategy.position_size[1] > 0` (mirror `< 0` for shorts), i.e. "we were ALREADY in the position last bar, so this is not the fill bar", and `lMaxFav`/`sMaxFav` now seed from `lEntry`/`sEntry` instead of the bar's extreme. **Four changed lines per file and ZERO new main-body statements** — that is deliberate: this family already sits near Pine's CE10295 statement cap, which is why the gate is a bare `position_size[1]` condition and not the `lJustFilled`/`sJustFilled` helper bools it started as. **Also fixed in `strategies/python/mpc_sos_fade/execution.py`**, which `mpc_bleg` reuses. Both export pairs re-diffed against their parents: still the line-29/40 title only. **Measured on lab run `d2ab68f9e884`** (165 trades, 6.5y): **all 165 entries unchanged**, 30 results changed, 18 better / 12 worse, **+101.68R → +112.43R**, win rate 63.6% → 67.3%; the four biggest gains are trades the bug killed at breakeven that were really +3.90R / +2.98R / +2.86R / +1.87R. ⚠ **The fix is not free and max drawdown was NOT measured** — 12 trades that used to scratch now take a full −1R. ✅ **BOTH PARITY GATES RE-VALIDATED THE SAME DAY on FULL-HISTORY post-fix exports** — `compare_strategy.py` (`15_fd236.csv`) and `compare_bleg.py` (`15_1b2f3.csv`), both **21,691 bars, 2025-08-31 → 2026-07-31, exit 0 at warmups 100/200/500/1000/2000**, no truncation warning on either. **The fingerprint is measurably gone:** on the entry bar, is `px_stop` already at breakeven instead of the real SL? A+ before = **4 of 26** entries; A+ after = **0 of 27**; B-LEG **0 of 5**. All four affected candles sit inside the new window, so each reads before/after on the same bar — 2025-10-02 died in 1 bar at −0.120R and now runs **47 bars to +0.008R**; 2025-12-02 went −0.860R → **−1.000R**; 2026-05-11 went +0.008R (1 bar) → **−1.000R** (3 bars); 2026-07-20 is **unchanged** at +0.859R (wrong stop, never hit). **Three of four get worse or stay flat — the fix is right anyway**, because the exit price now corresponds to an order the strategy actually placed. An earlier PARTIAL pair the same day (`15_88f5a`/`15_21332`, ~6,340 warmup bars missing) was also green, and it exposed a real harness asymmetry that was fixed: `compare_strategy.py` HARD REFUSED any truncated export while `compare_bleg.py` has always replayed until the engine converges. It now warns and requires `--warmup >= the missing bars`; `--debug-arm` still refuses, because it diffs the chart-relative `dbg_*` bar indices. 534 tests green. **The standing lesson: a green parity run says the two implementations AGREE, never that either is right** — this bug was faithfully ported, so the harness was green for its entire life. ⚠ **Recorded the same day, and it is NOT this bug and NOT a defect — a backtest LIMITATION that will keep appearing on the chart forever.** With the staging fixed, a stop can still legitimately end up on the wrong side of the market: price tags TP1, the stop stages to breakeven, then price closes back through it INSIDE THE SAME BAR. The stop only goes live NEXT bar (`calc_on_every_tick = false`), so by then it is behind the market and TradingView market-closes at that bar's OPEN rather than at the stop. Being OUT is CORRECT — price genuinely went through the stop — it is only the exit PRICE that is imprecise, because a bar-replay tester checks orders once per bar while a real broker watches every tick and would have filled at the stop. **It errs in the safe direction (the backtest looks slightly worse than reality) and it behaves identically in Pine and Python, so parity is unaffected** — no `compare_*.py` will ever flag it. A "never place a stop through the market" clamp was considered and deliberately NOT added: it would change real behaviour and would have to land in all five Pine files, so it is its own change with its own measurement. Canonical write-up: `strategies/python/mpc_sos_fade/CLAUDE.md` → `### Wrong-side stop fills`. Earlier: 2026-07-31 — **the harness pass: four export builds validated on two real grand exports, `mpc_jarvis_v2.pine` DELETED, and the session windows forked back together.** `ob_export.pine` was REBUILT (1148 → ~300 lines — it no longer embeds the structure engine, killing this folder's worst maintenance trap) and needed a real Pine fix to compile at all: **`CE10088 — a function may READ a global but never WRITE one`**, which the export-only counters were doing inside `extendOBs` and `f_obAdd`. `fvg_export.pine` had two holes that would each have produced a misleading GREEN (6 plotted slots against a cap of 8; a flat gap floor where mpc's is timeframe-split). `mpc_b_leg_strategy.pine` + its export had **never received the DST-aware session windows** the A+ parent has carried since 2026-07-12 — a real fork, and trade-affecting in principle because session H/L feed the sweep that arms A+; both bots re-verified GREEN after the sync, and then **on a FRESH B-LEG export off the synced Pine** (`--warmup 800`, exit 0, 6,329 bars over a window sitting entirely inside BST/EDT — the half of the year where the new windows and the old ones actually disagree, so this is the run that tests the fix rather than the Python side's self-consistency). `mpc_m15_playbook.pine` and `svp_export.pine` synced too, and `compare_svp.py` re-run green (12,117 bars). Of the four edited files, three were exported from, which proves them; `mpc_m15_playbook.pine` is uncompiled and **that is fine — Aaron's call, 2026-07-31: it is his brother's work in progress, not ready, and not a validation item for this repo.** Full record in the 2026-07-31 harness-pass section below, including the line-targeted-edit warning (the old Tokyo and New York values collide, so a global string replace corrupts them) and **the harness bug the first PARTIAL export exposed: `bl_*_bar` carries Pine's chart-relative `bar_index`, so `compare_bleg.py` was comparing two different coordinate systems and had only ever been right by the accident of full-history exports.** Earlier: 2026-07-30 — **`mpc_strategy_export.pine` REGENERATED off the parent, closing the last surviving drift.** It had no `execMinStopMode`/`execMinStopVal`, so the moment that filter was switched on the export stopped describing the strategy and `compare_strategy.py` would have reported GREEN while diffing a config it could not read. The regen followed the file's own documented procedure (`sed -n '1,4581p' mpc_strategy.pine` + the appended PARITY EXPORT block, then restore the line-29 title) and **`diff` over the shared range is now exactly one line — that title**. Two new columns carry the filter: `cfg_min_stop` (`Off?0 : % of price?1 : Fixed $?2 : x ATR(14)?3`) and `cfg_min_stop_val` (raw float, same reason the exit numerics are raw — a packed float that rounds mis-configures the bot silently). Deliberately NOT folded into `cfg_exitmode`: that column is the two EXIT dropdowns, and this is an ENTRY filter. The Python side was ported in the same pass (`strategies/python/mpc_sos_fade/CLAUDE.md` → `### The minimum-stop guard`), including block reason **code 7**, which the parent already emitted and nothing downstream could see. ⚠ **The filter is still unproven ON against a real export** — every green in this file was taken at the `"Off"` default, where the gate is inert and both sides are byte-identical to their previous build. Re-paste and re-export before trusting a run made with it on. ⚠ `mpc_b_leg_strategy.pine` still has no min-stop input at all (deliberate — a B leg's stop is its band ORIGIN, a full band from the entry, so the hazard is structurally absent); its Python fork pins the mode `"Off"` to keep that honest. Earlier: 2026-07-29 — **`aplusWindow`'s `maxval` raised 4320 → 20160 (14 days) in the A+ pair only** (`mpc_strategy.pine`, `mpc_strategy_export.pine`). The bug it fixes is worth knowing because the pattern can recur on any input: **the old ceiling EQUALLED the default**, so the field could only ever be lowered, and TradingView silently CLAMPS a typed value to `maxval` as you type — entering 4800 left the box showing a truncated number with no error, which reads as a broken input rather than a cap. Default is unchanged at 4320, so **no backtest and no parity run moves**, and the Python side (`aplus_window`) never had a cap so nothing there needed changing. **The export was raised in lockstep** — it must be able to carry any value the parent can produce, or a parity export taken at a longer window would silently be clamped to a different strategy. ⚠ `mpc_b_leg_strategy.pine` + its export and `mpc_bos_strategy.pine` / `mpc_m15_playbook.pine` still cap at 4320 (same default-equals-ceiling trap); raise them the same way if that window is ever swept there. Earlier the same day: **both strategy pairs re-validated GREEN, and both parents compile in TradingView.** `mpc_strategy.pine` and `mpc_b_leg_strategy.pine` were pasted in and compiled clean (the CE10117 token-cap worry did not materialise — no tooltip trimming needed). Fresh exports off `mpc_strategy_export.pine` (21,494 bars) and `mpc_b_leg_strategy_export.pine` (21,493 bars), both 2025-08-31 → 2026-07-29: `compare_strategy.py --warmup 100` → exit 0, `compare_bleg.py --warmup 100` → exit 0, and both hold at warmup 200/500/1000/2000. The A+ export carried `cfg_tp1_pct = cfg_tp2_pct = 0`, `cfg_exitmode = 20` (the 3-way trail digit decoding as the ratchet) and `cfg_trail_pct = 1` — i.e. the ratchet plumbing is proven through the export, not just present in it. **Every "STALE" warning below is CLEARED.** ⚠ **The one drift that survived that pass** — `mpc_strategy_export.pine` lacking `execMinStopMode`/`execMinStopVal` — **was closed 2026-07-30** (see the entry above). Those green runs were taken at the `"Off"` default where the gate is inert, so they still describe the current build exactly, and they still say nothing about the filter itself. Earlier: 2026-07-28 — **the swing ratchet landed in the A+ pair FIRST** (`mpc_strategy.pine` + `_export`), which is what the B-LEG entry below then caught up to: `execRunnerTrail` gained `"Structure + % ratchet"` and **now defaults to it**, with `f_swingRatchet()` and the `execTrailPct` child input (1.0%). It fixes the runner's give-back — the plain structure trail parks the stop at a LAGGING swing, so a strong leg hands back the gap between that swing and the high (measured 57% on the trades that ran ≥$10 of gold); the ratchet climbs one %-of-price step per step of favourable move and is never LOOSER than the plain trail, only equal or tighter. Export side: `cfg_exitmode`'s tens digit went 2-way → **3-way** and `cfg_trail_pct` was added — without both, the comparator would diff a ratcheted Pine against a non-ratcheted Python and report pure drift as a bug. ⚠ **The A+ export is now STALE: the 2026-07-27 GREEN parity run predates the ratchet, so it validates nothing about this build.** Re-run `compare_strategy.py` on a fresh export before trusting any A+ number from it — and run it at `execTp1Pct = execTp2Pct = 0` (the shipped rungs), because the 109.3R figure quoted for the ratchet was measured at 1%/1%; the true 0/0 baseline is **110.65R**. ⚠ **Pre-existing drift, NOT introduced by the ratchet:** `mpc_strategy_export.pine` lacks `execMinStopMode`/`execMinStopVal`, which the parent has. Inert at the `"Off"` default (the floor is 0.0, so the gate is always true) so parity holds today — but the moment minimum-stop-distance is switched on, the export stops describing the strategy and any parity result from it is meaningless. Close it before using that filter. Extension-fib take-profits on top of the ratchet were measured and REJECTED the same day; the full record is in `strategies/python/mpc_sos_fade/CLAUDE.md` → `### The swing ratchet`, and the short version is that 11 trades past the −0.618 extension carry 106R of the 109R, so any fixed ceiling caps exactly what pays. Earlier the same day — **the B-LEG pair now runs the SAME exit ladder as the A+ pair** (`mpc_b_leg_strategy.pine` + `_export`). Three changes, all ported line-for-line from `mpc_strategy.pine`: (1) `execTp1Pct`/`execTp2Pct` defaulted **30/40 → 0/0** — bank nothing, ride the whole position to the runner; (2) the **`qty_percent = 0` guard** — `strategy.exit()` reads 0 as "unspecified" and closes the WHOLE position at that limit, so a 0 rung is now SKIPPED rather than placed. That is why typing 0 previously blew the trade out at TP1 instead of banking nothing, and it is a real hazard, not a cosmetic default; (3) `execRunnerTrail` gained the third option **"Structure + % ratchet"** and now DEFAULTS to it, with `f_swingRatchet()` and the new `execTrailPct` child input (1.0%, greyed unless that method is selected). ⚠ **All three MOVE B-LEG results** — the rungs, the 0-guard and the trail default each change what a runner banks; nothing here is cosmetic. ⚠ **The 43% → 53% run-capture measurement behind the ratchet default was taken on the A+ file's own trades, NEVER on B legs** — it is inherited so the two forks share ONE ladder, not because it is a proven B-LEG result; sweep it before treating it as tuned. Export side: `cfg_exitmode`'s tens digit went from a 2-way to the A+'s **3-way** code (it used to collapse everything non-fixed to 1, which would have decoded the ratchet as the plain structure trail), and `cfg_trail_pct` was added. Python side, same commit: `mpc_bleg/config.py` DROPPED its `exec_runner_trail` pin (it existed only because this Pine lagged the parent), and `mpc_bleg.meta.json` gained the third choice + the `exec_trail_pct` row. The B-LEG exec-input gap vs A+ is now **three** levers, not four (`execSlLevel`, `execMinStopMode`, `execMinStopVal`). 98 Python tests green. **Not yet re-validated against a fresh export — `compare_bleg.py` must be re-run before any B-LEG number from this build is trusted.** Earlier the same day: **every Strategy Execution input in all FOUR strategy Pine files now lives in ONE consolidated block near the top of the file** (`mpc_strategy`, `mpc_strategy_export`, `mpc_b_leg_strategy`, `mpc_b_leg_strategy_export` — search `STRATEGY EXECUTION INPUTS`). All four carry the SAME eight sections in the SAME order; the B-LEG pair simply has fewer levers (no `execSlLevel`, no `execMinStopMode`/`execMinStopVal` — `execTrailPct` was in this list until the exit-ladder port later the same day), so its block is the A+ block minus those three. Ordered the way a trade happens (what trades → what arms it → where the limit rests → what can refuse it → size and stop → targets → runner → drawing), with each dependent input prefixed `↳` and carrying `active = <its parent>` so it greys out when irrelevant. **The block had to MOVE, not just be reordered:** panel order is declaration order, and two inputs (`execConfSZ`, `bLegMaxDays`) are read by engine code ~3,000 lines above the old block, so Pine forced them to be declared early — which stranded them at the TOP of the Execution panel, above "Trade Longs". **NO logic changed** — same inputs, same defaults, same reads; only declaration order, label text and `active =` gates. ⚠ **Reordering inputs resets saved TradingView settings** (TV maps them by position), so re-paste and click "Reset settings to defaults" once — cheap now that the defaults equal what Aaron trades. Three traps found while doing it, all now documented in the block's own header comment: (1) `execTrailStep` has TWO masters — `Fixed step` mode AND the `One trail step behind` TP2 floor — so it is deliberately NOT greyed by the trail method; (2) the three FVG entry rules still price an entry with `execReqFVG` OFF (that toggle only ADDS a 0.618 fib fallback), so they are siblings, not children; (3) `execMinStopMode` is an ENTRY filter and has nothing to do with the runner trail — the two never interact. **Standing rule: a new execution input goes in that block, in its section, with `active =` if anything can make it irrelevant.** `active` needs a pure INPUT bool, so never reassign one of these with `:=`. Earlier: 2026-07-27 — `execSlLevel` defaulted **"1.0" → "0.886"** in both A+ Pine files (`mpc_strategy`, `mpc_strategy_export`) to match `config.py` and what Aaron trades; the B-LEG pair deliberately keeps "1.0" (its Python fork pins the same). This MOVES the stop, so it changes every A+ trade's size and R — it is not cosmetic. Parity is unaffected: the export emits the level in `cfg_strcodes` and `compare_strategy.py` configures Python from that, so the harness never reads either side's default. Earlier the same day: `execRiskPct`'s `maxval` raised **10 → 100** in all four strategy Pine files (`mpc_strategy`, `mpc_strategy_export`, `mpc_b_leg_strategy`, `mpc_b_leg_strategy_export`); default stays 10, sizing math untouched, so no backtest moves. The old 10 was a UI cap only — the Python `exec_risk_pct` never had one. Note the `margin_long/short = 0.2` pin (500x) still bounds notional at 5x equity, so a high risk % on a tight stop can be rejected or partially filled by the tester with no error. Earlier the same day: `execTp1Pct`/`execTp2Pct` defaulted 30/40 → **0/0** in both A+ Pine files, with the `qty_percent = 0` guard that makes 0 mean "bank nothing" instead of "bank everything"; parity re-validated GREEN on a 21,320-bar export at SL 0.886 + 0/0 (see the 2026-07-27 entry). Earlier: 2026-07-26 — the new exit levers (structure runner trail, TP2 stop floor, SL fib dropdown, `execAplus`) ported into `mpc_b_leg_strategy.pine`, and `mpc_strategy_export.pine` given a column for every trade-affecting input (see the second 2026-07-26 entry). Earlier the same day: orphaned-SVP compile fix in `mpc_strategy.pine` + the export regenerated off it. Earlier: 2026-07-12 — the whole structure chain was re-synced to the `choch_lock` removal in `mpc_assistant.pine` and re-validated at 100% Pine parity (see the "2026-07-12 structure re-sync" note below), and the A+ divergence retro-link landed in both A+-carrying files (see the note after it).

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
- `indicators/mpc_strategy.pine` — Aaron's brother's "MPC-JARVIS" backtest script: the same engine as `mpc_assistant.pine`, converted from `indicator()` to `strategy()` and given an execution layer at the end (A+ sequence entries, fib TP ladder, %-risk sizing). Its `process()` state machine is byte-identical to `mpc_assistant.pine`'s — verified by diff, keep it that way. **Sync direction reversed 2026-07-21: the REPO is now the source of truth** — Aaron pastes this file up to TradingView and his brother picks it up, so repo-side edits stick. (It used to flow the other way, which is why older notes warn about TradingView edits silently reverting fixes.) There is no local Pine compiler: validation is pasting into TradingView, checking it compiles, and confirming the Strategy Tester numbers are unchanged.
- `indicators/mpc_d_strategy.pine` — **the D strategy ("D as in dog, the dirty one", Aaron 2026-08-06).** A standalone `strategy()`, NOT a fork of `mpc_strategy.pine`: it embeds `structure_engine.pine`'s external block byte-for-byte (lines 27-591, minus the two internal-structure inputs) and adds one state machine plus an execution layer on top. Trades the sequence *mature trend → counter-trend SOS (the shakeout) → with-trend SOS (the entry)*, with %-of-equity sizing, a TP1/TP2/runner ladder and breakeven-at-TP1; also draws the levels and shades the shakeout. Spec, worked examples and the open questions: `docs/MPC_D_STRATEGY_SPEC.md`. ⚠ **It shipped as an `indicator()` first and had to be converted** — an indicator has no Properties tab and no Strategy Tester, so it could not be scored at all. **The file NAME said `strategy` the whole time; the name is not the declaration.** **COMPILES and has been RUN** (Aaron, 2026-08-06, XAUUSD 5m, ~11.5 months). Still no Python port and no parity harness. ⚠ **The DEFAULTS were changed 2026-08-06 to the configuration that measurement run actually used** — `initial_capital` 10,000 → **100,000**, `execRiskPct` 1.0 → **10**, `execTp1Pct` 50 → **30**, `execTp2Pct` 25 → **30**, `execTimeStopMode` "Off" → **"Before TP1 only"** (36h). Reason: the shipped defaults described a run nobody had made, so a fresh paste could not reproduce the only numbers this strategy has. **The time-stop mode was DEDUCED, not asked for** — trade 33 sat open 7 days uncut with a peak of 1.71R, and trade 36 ran 37 hours, both past TP1, which only "Before TP1 only" allows. ⚠ **Values only — no input was added, removed or reordered**, so TradingView's saved-settings keying is untouched and no existing chart resets. ⚠ **The baseline therefore MOVED: 37 positions / +8.31R / PF 1.69 / 56.8% win / max DD 3.53R over 2025-08-11 → 2026-07-29** — pin the old values to reproduce anything from before. 🔴 **`execRiskPct` was then dropped 10 → 1.0 the same day, because 10 BUSTS THE ACCOUNT on real history.** The first full-history run (2020-01-01 → 2026-08-05, 5m) died with `Invalid qty value (-0.1) in the strategy.entry() call` — **that is not a compile error, it is equity going NEGATIVE**, and `qty = equity × risk% ÷ dist` goes negative with it. ⚠ **A non-positive qty does not skip the order, it ABORTS THE SCRIPT** — so the Strategy Tester showed no report at all and the blow-up that caused it was invisible; the only symptom was a banner about qty. Now reported as **block code 8**, first in the precedence chain, plus a `q > 0` guard at the entry, so the run completes and the run of 8s marks the exact bar it died. **The mechanism is the min-stop floor meeting old prices: 0.08% is $3.20 at $4,000 gold but $1.20 at 2020 gold, so `100,000 × 0.10 ÷ 1.20` = 8,333 oz = $12.5M notional on a $100k account, which margin 0.2% permits — one weekend gap ends it.** ⚠ **R is scale-free, so a MEASUREMENT run at 1% gives identical R, drawdown-in-R and profit factor while surviving to the end. Size the account after you know the R distribution, never before.** **The standing lesson: a sizing rule that divides by a distance has no floor of its own — the floor has to come from the distance, and a %-of-price floor silently loosens as you walk backwards through history.** 🔴 **THE SAME RUN THEN EXPOSED A WORSE ONE — THE STRATEGY FROZE DEAD ON 2020-05-07 AND STAYED FROZEN FOR THE REMAINING SIX YEARS OF AN EIGHT-YEAR BACKTEST.** The trade list's last row is a long opened 2020-05-07 12:30 and still `Open` at 2026-08-06 — **147,518 bars**, and the run's headline +81% was that one position's unrealised profit. **The cause is BLOCK ORDER.** The CLOSE block sat at the very bottom of the file, after the setup block. On a **same-bar flip** — a position closing and the next sequence firing on the SAME bar — `if dFired` set the new trade up first (`tDir := 1`, entry placed), and then the CLOSE block, correctly seeing `position_size == 0`, scored the old trade and finished with **`tDir := 0`**, wiping the direction of a trade that had just been placed. From the next bar the FILL block and the entire exit block are both gated on `tDir != 0`, **so neither ever ran again**: the position sat open with no stop, no targets and no time stop, `bBusy` was permanently true, and every later setup was refused with code 7. ✅ **Fixed by moving the CLOSE block ABOVE `if dFired`**, which is also required for a second reason — `if dFired` overwrites `tRiskUsd` and `tNpAt`, the exact values the R grade divides by, so running after it scored the closing trade against the NEW trade's risk. ⚠ **It fired ONCE in eight years.** Exactly one same-bar flip in the entire history, and that single occurrence cost 6 of the 8 years. **The standing lesson is about probability and blast radius: a path taken on 1 bar in 200,000 is still a path, and the relative ORDER of two blocks that both touch one state machine is not a detail.** ⚠ **And note how it was caught — not by reading the code, not by a compile error, not by the Strategy Tester (which reported a healthy +81%), but by one row in a trade list saying a position had been open for six years.** The suite here has no way to catch this; the export's `px_blk` run-of-7s would have shown it too. **Read the tail of the trade list before you read anything else.**
- `indicators/mpc_d_strategy_export.pine` — **the D strategy's decision-stream twin (2026-08-06).** `mpc_d_strategy.pine` + one appended block, body byte-identical apart from line 60's title; 48 transparent `plot()` columns. Regenerate with `cp` + the line-60 `sed` + re-append, never by hand-patching. **It exists because the Strategy Tester's trade list records FILLS and nothing else** — it cannot say what the gates refused, how far a trade ran before handing the move back, or what a different stop anchor would have priced, and those are the only three questions this strategy is being tuned on. ⚠ **`px_ctr_ext` / `px_rcl_ext` are RECONSTRUCTED, and that is called out in the file**: the parent updates the leg extremes earlier on the same bar and the unconditional shift then destroys them, so the block re-derives the parent's own two-line rule. Everything else at decision time (`dTrendBos` / `dCurBos` / `dSosBar` / `dSosLvl`) is written ONLY by that shift, so its `[1]` value *is* what the gate read — exact. **The reconstruction is kept checkable rather than trusted**: `px_fire_ctr_hi/lo` and `px_fire_sos_lvl` carry the parent's authoritative values on fired bars, and on any fired bar the two must agree. ⚠ **`px_mfe_r` / `px_mae_r` exclude the fill bar**, the same rule as the parent's `tMaxFav` (BUG_exit_fill_price_mismatch) — a resting limit is reached from the wrong side, so the fill bar's extreme is not a move the trade made. ⚠ **`px_stage` is tracked in the export, not read from `tStage`**, because the parent zeroes `tStage` on the close bar and the close bar is exactly where the final stage matters. ⚠ **Every int-in-a-ternary-against-`na` is built as a float LOCAL first** — Pine does not reliably type that shape and it fails at paste time; four columns had to be rewritten this way. ⚠ **Transparent colour, never `display.none`** — TradingView drops `display.none` series from the CSV, the trap every engine export here records. **The payoff to remember: with `px_ctr_ext`, `px_rcl_ext`, `px_sos_lvl` and `px_cand_entry` on every candidate the strategy ever saw, both stop anchors and any retrace level can be re-priced OFFLINE from one export — so one run answers a sweep instead of one configuration.**
- `indicators/mpc_b_leg_strategy.pine` — a FORK of `mpc_strategy.pine` that trades ONLY the B LEG (the SOS whose retrace arrived late), split out 2026-07-24 to run PARALLEL to the A+ bot. The ONLY logic change vs the parent is the execution layer: the two A+ `strategy.entry` blocks are replaced with cancel-only stand-down (`longArmed`/`shortArmed` are still computed so the "A+ has priority" gate on the B leg is preserved), and the B LEG is the sole entry type. The whole engine + A+ sequence tracker above the execution block stays byte-identical to `mpc_strategy.pine` — do not let it drift. **Leaned out 2026-07-24** (4871 → 4573 lines): the code that went dead when A+ entries were disabled (`f_conf`, `f_slAnchor`, the `execSlLevel` input, `longDeep`/`shortDeep`, `longEdgeSz`/`shortEdgeSz`) plus three self-contained cosmetic subsystems the B leg never reads and that default OFF (VWAP, Session Volume Profile/MV, Order Blocks) were removed. Python port lives in `strategies/python/mpc_bleg/` (its own CLAUDE.md). Same no-local-compiler rule: validate by pasting into TradingView. **No Pine↔Python parity harness yet** — a `mpc_b_leg_strategy_export.pine` + `compare_bleg.py` are the follow-up.

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
