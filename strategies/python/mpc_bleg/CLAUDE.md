# CLAUDE.md — strategies/python/mpc_bleg/ (the MPC B-LEG bot)

**Purpose:** The B-LEG setup as a standalone Python strategy — a port of
`indicators/mpc_b_leg_strategy.pine` (Aaron's brother's B-LEG fork of MPC-JARVIS). The
B LEG is the SOS whose retrace arrived LATE: an A+ reversal dies at 2/3 on a continuation
BOS before it retraces, the Sniper-Zone band (0.382–0.5) of that break is frozen, and a
resting limit at the 0.5 edge waits for the late return.
**Scope:** This bot only — its tracker, order layer, config, tests. It does NOT own the
engines (`engines/`), the replay runner (`backtest/`), or the A+ machinery it reuses
(`strategies/python/mpc_sos_fade/`).
**Status:** Built + unit-tested (19 tests green) + **Pine-parity GREEN (exit 0), re-validated 2026-07-31**
on a fresh 6,329-bar `VANTAGE_XAUUSD, 15m` export off the session-window build — bar-for-bar
identical decision stream. The harness is `tools/compare_bleg.py` +
`indicators/mpc_b_leg_strategy_export.pine`, registered in `verify_parity.py`.
⚠ **STILL NO ESTABLISHED EDGE, but the defaults MOVED THREE TIMES on 2026-08-06 and the old numbers
no longer describe this bot.** The shipped configuration is now **114 trades / +17.56R / PF 1.45 /
maxDD −5.15R over 7.9 years with spread and swap charged** (free book: +23.28R / PF 1.65 / maxDD
−4.19R), against the pre-change **59 / −1.73R / PF 0.94 / maxDD −16.00R** on the same bars and the
same charges. Both halves of the history are positive now (IS +3.14 / OOS +14.42) where the old
defaults lost 8R in the first. **The 95% CI on mean R is −0.068 → +0.376 and still contains zero**
— the 7.9-year total belongs anywhere in **−7.7R to +42.8R** — so read this as "the measurement
moved up and narrowed", never as "it works". Three defaults carry it and each was measured on its
own axis: `exec_trail_pct` 1.0 → 0.05, `bleg_max_days` 1.25 → 4.0, `exec_time_stop_hrs` 36 → 8.
See "The exit-ladder re-default".
**Last reviewed:** 2026-08-09 — 🟢 **THE SHARED-ACCOUNT SEAM REACHES THIS BOT'S CONSTRUCTOR NOW.** `Execution` has taken an injected `account` since 2026-07-17 and NOTHING could pass it one — the strategy built its `Execution` without the kwarg, so every run got a `SoloAccount` (no cap, always full size). `__init__` takes `account=None, leg="strat"` and threads both through, so this bot can be one leg of a stack sharing ONE balance and ONE risk budget (`backtest/portfolio/run_stack`). ⚠ **Omitting it is byte-identical to before** — Execution still builds its own `SoloAccount`, which is what keeps every parity result and every measured baseline valid. ⚠ **`leg` MUST be distinct per leg**: the account holds one open position per key, so two legs both called `"strat"` would overwrite each other's reservation and the cap would silently under-count the open risk while reporting itself enforced; `run_stack` refuses duplicate names for exactly that reason. ✅ **MEASURED on a real two-leg run (155,807 M15 bars, $10,000, 10% cap): this bot posts 159 trades / +142.18R shared, identical to solo** — R is normalised to the trade's own risk, so a shared balance changes the DOLLARS and no decision. 🔴 **And nothing was ever blocked in 6.5 years, because this bot touches breakeven on 161 of 161 trades at a median of ONE BAR** — the account reserves risk to the CURRENT stop, so its room is released almost immediately and the second leg is never refused. Full record: `backtest/CLAUDE.md` → *The shared-account run*. Earlier: 2026-08-07 — ⚠ **THIS FORK NOW PINS `exec_secondary` OFF, AND THE PIN IS THE DIFFERENCE BETWEEN THIS BOT RUNNING AND NOT RUNNING.** The parent defaulted the 1-minute sniper re-entry **ON** on 2026-08-07. It is an A+ feature end to end — it re-enters a 15m A+ leg whose PRIMARY reached breakeven, and in this fork **A+ never places an order**, so there is no primary to follow and `MpcBLegStrategy.run_dual` raises outright. 🔴 **Inheriting it would not have changed a trade here, it would have KILLED every B-LEG lab run**: `python_runner` reads `exec_secondary` off the config to decide whether to load a 1m feed and call `run_dual`, so an inherited `True` reaches that `NotImplementedError` on every run. ⚠ **Same class as the `exec_min_stop_mode` pin — a parent default this fork's code cannot honour — but the failure mode is the opposite one.** That pin guards against a guard being silently CLAIMED; this one guards against a hard crash, and the only reason it was caught before shipping is that it is loud. **The quiet ones are the pins to re-check when a parent default moves.** Pinned by `test_the_fork_pins_the_secondary_OFF`, watched red, which also asserts the PARENT still ships it on — so if that is ever reverted the pin is flagged as redundant rather than left standing as decoration. No B-LEG number moves. Earlier: 2026-08-06 — 🟢 **ASKED TO MAKE THE WINNERS WIN MORE, AND THE MEASUREMENT SAYS THE WINNERS ARE ALREADY FINE — IT IS THE DEAD TRADES THAT COST THE MONEY.** Two questions, both answered by real replay over 186,312 M15 bars with spread and swap charged, one axis moved per row, the IS/OOS split declared before any row ran. ✅ **SHIPPED: `exec_time_stop_hrs` 36 → 8** (pinned in `config.py`, both Pine files, the meta). Charged: **114 trades / +17.56R / PF 1.45 / maxDD −5.15R** against 112 / +12.02R / PF 1.23 / −8.89R at 36. 🔴 **THE HEADLINE FINDING IS A NEGATIVE ONE, AND IT IS THE ONE WORTH CARRYING.** The exit-stage map over the 112 trades reads: **stage 0** (never touched TP1) 63 trades, −48.12R banked on 24.61R shown · **stage 1** (touched +1R, stop at breakeven, never reached TP2) 18 trades, **−1.38R banked on 31.23R shown** · **stage 2** (runner trail live) 31 trades, **+61.52R banked on 73.31R shown, 84% kept**. Stage 1 looks like a 32R hole sitting in plain sight. **Every way of closing it LOST MONEY:** trailing from stage 1 → +1.92R · flooring at +1R → +4.09R · floor at +0.5R → +0.67R · TP2 pulled to 60% → +1.10R · TP2 pushed to 180% → −4.82R. ⚠ **The tell is the BEST-TRADE column, not the total: every one of those cut the best trade from +5.07R to under +4.4R.** The breakeven-until-TP2 gap is not a defect — it is the thing that lets the stage-2 cohort get to stage 2 at all, and protecting a runner earlier saves the 18 by killing the 31. **Do not "fix" stage 1.** ⚠ **So the 8-hour clock is NOT a "winners win more" change and must not be described as one.** It fires only at stage 0, so it cuts no winner by construction; the gain is dead trades ending sooner and the single position slot freeing up. Capture (R banked ÷ R ever shown) 9.3% → 15.1% almost entirely by shrinking the denominator. ⚠ **8 is defensible because 4–12 is a PLATEAU on drawdown, not because it is the peak on R**: 4h −5.19 · 6h −5.13 · 8h −5.15 · 12h −6.03 · 18h −8.10 · 36h −8.89. **Read the drawdown. +5.5R over 114 trades in 7.9 years is inside a noise band this bot has never had measured** — the A+ jitter audit put THAT bot's run-to-run spread at sd 15.06R and no equivalent has been run here. ⚠ **The A+ fork KEEPS 36 and the two must not be reconciled**: both plateaus are real and measured on their own trades. Only the HOURS fork; `exec_time_stop_mode` stays "Before TP1 only" on both. 🔴 **Q2 — killing an untapped band on an opposite SOS — was measured and is CATASTROPHIC: 112 trades → 8, +12.02R → −0.09R.** The mechanism is structural rather than tuning: **an SOS strictly ALTERNATES direction by construction** (a bull SOS requires `dir == -1` and sets it to 1), so after a bear SOS freezes a short band an opposite SOS is GUARANTEED to arrive — and it is usually the retrace the band is waiting for. `bleg.py`'s own comment said exactly that; it is now measured. **The watch window stops mattering entirely** — 5, 6 and 8 days all return the identical 8 trades, because the kill fires long before the staleness clock can. ⚠ **This is what closes out the 2026-07-21 short Aaron spotted on the chart** (a band frozen 16 July, armed 17 July, filled 21 July into a market that had turned bullish, stopped for −1R): it is a genuine B leg, it is the price of the 4-day watch, and there is no cheap filter for it. **A frozen band only checks `fibo_dir` when it ARMS, never when it fills.** ✅ Also measured and rejected: closing on an opposite SOS is a wash (+12.52R, but best trade +5.07 → +3.87), scaling out at TP1 costs money (+8.75R), the stage-2 floor mode is now INERT (all three modes identical to the cent — the 0.05 ratchet always sits above every floor), and the breakeven buffer is already at its best value. ✅ 3 new tests, **all watched RED against the exact state each guards** (the inherited 36 in config, the old Pine default, the stage gate deleted from `lTimeUp`, and a drifted meta desc — four defects, four reds); 491 strategy + backtest green. ✅ **The shipped config was proven by RUNNING it: a plain default run now reproduces +17.56R / PF 1.45 / maxDD −5.15R to the cent.** ⚠ **NOT PARITY-RE-VALIDATED** — only a default moved and `compare_bleg.py` configures Python FROM `cfg_time_stop_hrs`, so parity is structurally unaffected, **but an export taken before today decodes 36 and would say nothing about 8**, and the clock has still never fired inside a parity window. Re-export. **The standing lesson is about where to look when a strategy underperforms its own excursion: the obvious reading of "73.9R shown, −0.9R captured" is that the runner is leaking, and here the runner was the one part working — it kept 84% of everything it was handed. The leak was upstream, in trades that never became winners at all and sat in the single position slot while they died.** Before tuning an exit, split the excursion by the stage the trade reached; a give-back number aggregated over winners and losers together points at the wrong half of the ladder. Earlier the same day: ✅ **THIS FORK PINS THE EQ/FVG COUPLING OFF, AND THAT PIN IS WHY `compare_bleg.py` STAYED GREEN THROUGH THE A+ GATE'S THREE-DAY RED.** `eqExemptFvg` — a fair value gap sitting on an active EQH/EQL surviving the FVG cap — **defaults `true` in `mpc_strategy.pine` and `false` in `mpc_b_leg_strategy.pine`**, a genuine fork rather than drift. The Python side modelled the coupling nowhere until today, so the A+ bot silently disagreed with its own Pine while this one silently agreed with its own. ⚠ **Wiring it up would have BROKEN this fork by inheritance**: `MpcBLegStrategy` takes `engine_config()` from its parent, so pinning the parent ON would have configured this bot to a gap set its Pine never held. `engine_config()` is overridden here as a **one-field `dataclasses.replace`**, never a second copy of the parent's pins — a hand-written config would go stale the moment the parent pins a new engine input, in the quiet direction where nothing fails. Both halves are pinned by `tests/test_bleg_fork_pins.py`: one test asserts the deliberate difference, the other asserts **field-by-field equality on everything else**. ⚠ **Same shape as the `exec_min_stop_mode = "Off"` pin, and the same standing rule: delete the override only in the commit that ports the input into this fork's Pine, then re-run the gate.** ✅ `mpc_b_leg_strategy_export.pine` now plots **`cfg_eq_exempt`** too, and that is the part worth defending — both sides read 0 today, so the column looks redundant, and it is exactly what turns *two defaults that happen to line up* into a MEASURED agreement. ✅ `compare_bleg.py` **exit 0 at warmups 100 / 800 / 2000** on the 2026-08-06 21,999-bar export after the change. ⚠ **Its clock still fired ZERO times in that window**, so the time-stop caveat below is unchanged — re-export at 4 hours. Earlier the same day: 2026-08-06 — 🟢 **THIS BOT WAS NOT LOSING ON ITS ENTRIES. IT WAS HANDING BACK ITS RUNS, AND THE CAUSE WAS A UNIT MISMATCH RATHER THAN A TUNING ERROR.** Aaron asked for the most optimised result on profit factor, winners and drawdown. **Measured first, tuned second, and the diagnosis is the deliverable: across the 50 baseline trades the sum of maximum favourable excursion is 73.9R and the strategy captured −0.9R.** 🔴 **Nine of those 50 exited at EXACTLY +1.00R — one after running +6.82R — and the exactness is the clue.** On a B leg `TP1 = 2*edge − inv` while the stop is `inv`, so **TP1 is precisely 1R from the entry BY CONSTRUCTION**, and the inherited `exec_tp2_stop_mode = "TP1 price"` makes the stage-2 floor that same price. The floor therefore caps the runner at its own first target. 🔴 **The trail is supposed to climb past that floor and structurally cannot: `exec_trail_pct` is a percent OF PRICE, and a B leg's whole 1R is 0.13%–1.25% of price** (measured — stop distances $2.51 to $49.02), so at the inherited 1.0 one trail step is routinely larger than the entire risk and `f_swingRatchet` never lifts off the floor. **The ratchet was inert on this fork for its whole life.** ✅ **TWO DEFAULTS CHANGED, each measured on its own axis before they were combined, with the out-of-sample split declared BEFORE any row ran** (IS 2018-09-13 → 2022-09-30, OOS 2022-10-01 → 2026-08-05; 186,312 M15 bars; one real replay per row): **`exec_trail_pct` 1.0 → 0.05** and **`bleg_max_days` 1.25 → 4.0**. Charged, the combination is **112 trades / +12.02R / PF 1.23 / maxDD −8.89R / IS +0.78 / OOS +11.24** against the old **59 / −1.73R / PF 0.94 / maxDD −16.00R / IS −8.15 / OOS +6.42**. ⚠ **`bleg_max_days` is the more interesting of the two, because the old value was never tuned at all — the Pine input's `maxval = 3` was what mattered, and the best region sits OUTSIDE it.** Charged: 1.25 → 59 tr / +7.29R · 3.0 → 92 / +10.56R · **4.0 → 112 / +12.02R** · 5.0 → 118 / +13.76R · 7.0 → 121 / +8.62R. **The cap was raised 3 → 6 in the same commit; a `maxval` is a claim about where the useful range ends and this one had never been measured.** 4.0 is chosen for the LOWEST drawdown on the plateau and the only clearly positive in-sample half, not for the highest total. ⚠ **THE SURFACE IS FLAT AND THAT IS THE POINT: PF is 1.18–1.25 across the entire 4×3 grid of trail step × staleness.** A flat surface is what a real plateau looks like; a sharp peak would have been the curve-fit this file's own warning predicts at n≈60. ⚠ **The plateau genuinely continues below `exec_trail_pct` 0.05, and that lower half is a BAR-GRANULARITY artefact rather than a market fact** — a $2 step and a $0.25 step exit on the same 15m bar, which is why 0.03 / 0.02 / 0.01 all returned the identical figure to the cent. Do not read that flatness as headroom; 0.05 is also the Pine input's own `minval`. 🔴 **FOUR THINGS WERE MEASURED AND REJECTED, and they are recorded because each looked right.** (1) **The minimum-stop guard does nothing here.** The hypothesis was that this fork's tight stops are the losers, as they were on A+ — it is wrong: every floor from 0.10% to 0.40% is within noise and none improves both halves. ⚠ **And the cheap estimate said otherwise — deleting the refused rows from the finished trade list scored a 0.25% floor at +6R where the real replay scores zero — which is this repo's own entry-side-filter trap reproducing exactly.** (2) **The deeper 0.618 band edge looks spectacular at PF 2.43 / maxDD −4.58R and is a 28-trade mirage**: +15.81 of its +17.25R is in the first half, and the fill rate collapses 112 → 28. (3) **Shorts-only is the same mirage in the other half** (PF 1.58, IS −1.15 / OOS +14.82). (4) **Dropping the A+ priority gate — this file's own documented "first tuning candidate" since 2026-07-24 — adds one trade and that trade loses.** ⚠ **A fifth result is a genuine open lead rather than a rejection: dropping Asia-session and late-day entries gives 79 trades / +12.32R / PF 1.37 / maxDD −4.98R, positive in both halves** (IS +2.89 / OOS +9.42), and the original 50-trade baseline independently showed Asia at −5.0R on 13 trades. **It is NOT shipped — there is no such input on either side, so it is new code in the Pine and here, not a default change.** ⚠ **The time stop inherited on 2026-08-06 behaves OPPOSITE to A+ on this fork: `"Always"` at 36h beats `"Before TP1 only"` (+6.08R vs +1.38R free)**, because a B leg's TP1 *is* 1R, so the stage gate that protects A+ winners here just exempts trades that already made their money. Left at the inherited default deliberately — it is a one-flag change with no Pine divergence, and it has not been re-measured since the two defaults moved. ⚠ **NOT PARITY-RE-VALIDATED.** Only DEFAULTS and one `maxval` changed, and `compare_bleg.py` configures the Python side FROM the export's `cfg_trail_pct` / `cfg_bleg_days`, so parity is structurally unaffected — **but a green run on an export taken before today decodes the OLD values and would say nothing about these**, which is the "green on a branch neither side entered" trap. Re-export and re-run. ⚠ **Aaron's saved charts keep their own values.** TradingView stores a chart's input values, so changing a Pine DEFAULT does not move a chart already running the script — the new defaults reach a fresh paste or a "Reset settings to defaults", and nothing else. ✅ **The shipped config was PROVEN BY RUNNING IT, not by reading the diff: a plain default run reproduces 112 / +12.02R / PF 1.23 / maxDD −8.89R to the cent, and pinning 1.0 / 1.25 reproduces the old 59 / −1.73R.** ✅ 3 new tests, all watched RED against the exact state each guards (the old config defaults, the old Pine default + `maxval`, and the un-synced meta desc); 182 strategy + 297 backtest + 696 backend green. **The standing lesson is about UNITS, not about tuning, and it generalises past this fork: `exec_trail_pct` was inherited from a parent where a percent of price is the right size for the trade, into a fork where it is roughly ten times the trade's whole risk. Both files read the same field name and the same tooltip, and nothing anywhere was wrong — the number simply meant something different on the other side of the fork.** Before inheriting a threshold, check what it is a fraction OF, and whether that quantity has the same magnitude in the child. Earlier the same day: 🟢 **THE TIME STOP IS INHERITED HERE, AND THAT IS THE OPPOSITE CALL FROM THE MINIMUM-STOP GUARD.** `exec_time_stop_mode` ∈ {"Off", "Before TP1 only", "Always"} + `exec_time_stop_hrs` (36.0) landed in the parent, and this fork picks it up for free — the lever lives in `Execution.step()`'s force-close chain, which `BLegExecution` delegates to, and **both bots share ONE exit ladder**. `indicators/mpc_b_leg_strategy.pine` got the identical inputs in the same commit so the two sides cannot drift, and its export carries `cfg_time_stop` / `cfg_time_stop_hrs`. **Defaulted ON ("Before TP1 only", 36h) on 2026-08-06, inherited from the parent — so B-LEG results measured before that date no longer reproduce at defaults.** ✅ `compare_bleg.py` **exit 0 with the lever ON** (21,999 bars, 2026-08-06) 🔴 **but the clock fired ZERO times in that window — 0 of 5 trades — so the green says nothing about this lever.** Re-export at 4 hours to exercise it. ⚠ **Why inherited rather than PINNED off, unlike `exec_min_stop_mode`:** that guard runs inside `_place_entries`, which this fork overrides, so it could never fire here and a pin kept the config honest. This one runs in `step()` and genuinely applies, and the B leg's own Pine now has the input to be parity-checked against — the two conditions the min-stop pin was missing. ⚠ **The 24h–40h plateau behind the 36 default was measured on A+ TRADES ONLY.** A B leg waits for a LATE retrace by construction, so the hold-time distribution that makes 36 defensible over there says nothing about here — **treat any value on this fork as untested until it is replayed**, and note that at 50 trades a sweep will find a winner whether or not one exists (the same warning this file already carries about optimizing anything here). ⚠ Pinned by `test_the_bleg_fork_inherits_the_time_stop`, which asserts the fork has not grown its own `step()`. Earlier: 2026-08-04 — 🔴 **RE-MEASURED OVER 6.5 YEARS POST-PHANTOM-EXIT-FIX, AND IT MAKES NOTHING.** ⚠ **This is a CONFIRMATION, not a discovery, and the fact that it needed confirming is the finding.** `backtest/archive/2026-07-29_xauusd_15m_full_history/README.md` already stated **58 trades / +3.5R over 7.9 years** and, in its own words, "B-LEG is roughly flat over 7.9 years and is the one that most needs the analysis". That snapshot predates the 2026-08-01 phantom-exit fix and was on the repo's own re-baseline list, so it needed re-running — but the verdict was on disk, in a committed file, and nothing had been decided off it. The current number: **50 trades, −0.94R over 155,453 M15 bars (2020-01-01 → 2026-08-03)**, at the shipped defaults, zero cost layers. 34% win rate, **+1.65R average win against a −1.01R average loss**, expectancy **−0.02R per trade**. ⚠ **The right read is NOT "it loses" — it is that 50 trades cannot distinguish a small edge from a small negative one.** The 95% CI on its mean R is **−0.40 to +0.37**, i.e. its 6.5-year total belongs anywhere in **−20R to +18R**. Run the identical window through A+ and the CI is **+0.29 to +1.40**, entirely positive on 161 trades. That contrast is the finding: one bot has an edge that survives error bars and this one has an absence of one. ⚠ **The SHAPE is worse than the total, and it is the part that matters for a live decision**: peak-to-trough **−15.62R** on the way to finishing at −0.94R — nearly DOUBLE A+'s −7.99R over the same bars, for none of the return. By year: 2020 +1.5, 2021 −6.0, 2022 −3.9, 2023 −4.8, 2024 +0.3, 2025 +3.0, 2026 +8.9 (4 trades). A first half that loses and a second half that recovers is exactly what noise looks like at n=50, so do not read a regime story into it without measuring one. ⚠ **THIS IS A STATEMENT ABOUT THE DEFAULTS, NOT ABOUT THE SETUP.** `exec_tp1_pct`/`exec_tp2_pct` are 0/0 (full runner) and `exec_sl_level` is "1.0", both PINNED to this fork's own Pine for parity rather than chosen — lab run `096432c2ad20` ran 30/40. This bot has never been optimized over a long window. ⚠ **What today actually adds over the archive is the ERROR BARS and the DRAWDOWN SHAPE.** "Roughly flat" reads as a strategy waiting for its moment; **flat with a ±19R interval and a −15.62R peak-to-trough** reads as a measurement that has not begun, and only the second one is a basis for saying no. A number without its uncertainty is a number nobody can act on, which is why it sat in a README for a week. ⚠ **And optimizing it is its own hazard**: 50 trades is few enough that a grid will find a winner whatever the truth is, which is the definition of curve-fitting. Any tuning pass here needs an out-of-sample split stated BEFORE the grid runs, not after. ✅ **The good news from the same run, and it is genuine**: the A+/B-LEG **overlap audit finally ran and this bot PASSED it comfortably** — 27 shared bars in 155,453, one same-direction entry cluster in 6.5 years, monthly R correlation +0.155. The "different legs of the move" design intent is measured and true. It just does not matter yet. Tool: `backtest/tools/overlap_audit.py`; write-up in `docs/LIVE_TRADING_PIPELINE.md` → G14/G15. **Consequence: this bot is NOT a candidate for bot #2 today**, and the thing standing in its way is no longer the allocator or the overlap question — both of those moved out of the road today — but the absence of anything to deploy. Earlier: **this bot's lab labels and descriptions are now shared with
`indicators/mpc_b_leg_strategy.pine`.** All 11 params in `mpc_bleg.meta.json` carry that input's
Pine title byte-for-byte and its tooltip verbatim as the `desc`; change one and change the Pine in
the same commit. Two of them are deliberately the FORK's own wording, not the A+ parent's —
`exec_aplus` is "A+ has priority (stand the B-leg down)" because in this file A+ never places an
order, and `exec_sl_buf_tk` says "beyond fib 1.0" because that is where this bot's stop always
sits. Nothing behavioural moved: the only Python edits were two comment strings in `config.py`.
✅ **`compare_bleg.py` re-run GREEN the same day** on a fresh 21,715-bar `VANTAGE_XAUUSD, 15m` export
(2025-08-31 → 2026-08-02, `cfg_bits` 61047 — `execBLeg` ON, `execAplus` priority ON, `execDeepFib`
ON, matching this fork's pins) — **exit 0 at warmups 100 / 500 / 1000 / 2000**. Earlier the same day: **the parent's new A+ entry model is PINNED OFF here, and
unlike the minimum-stop guard it is NOT inert.** `mpc_sos_fade` gained rules 1-3 (`exec_fib_overlap` /
`exec_fib_deep_edge` / `exec_fib_nearest`), the pre-zone gate (`exec_fvg_pre_zone`) and the
deep-entry stop (`exec_sl_deep`), and flipped `exec_deep_fib` **True → False**.
`mpc_b_leg_strategy.pine` has none of those inputs and still ships `execDeepFib = true`, so
`BLegConfig` pins all six. **Why the pins are load-bearing rather than tidiness:** this fork
overrides `_place_entries` but **NOT `_entry_edges`**, and the A+ edges it produces are passed to
`_armed()` — the "A+ has priority, stand the B leg down" gate. A different A+ entry edge therefore
changes which bars the B leg is allowed to trade on, so inheriting the parent's new defaults would
have moved B-LEG trades with no Pine change behind it. The pins keep this fork byte-identical to its
own Pine; nothing in this package's code changed and the parity run below still stands. Un-pin only
in the same commit that ports the model into `mpc_b_leg_strategy.pine`, then re-run `compare_bleg.py`.
⚠ One additive change did reach here: `Signals.fvgs` is now a 4-tuple carrying each gap's born bar,
and `Signals` gained `fibo_half_bar`. Both are read only by the pinned-off gate, so no B-LEG decision
moves. Earlier: 2026-08-01 — 🔴 **THIS BOT INHERITED THE PHANTOM-EXIT BUG AND IS FIXED WITH THE
A+ — it reuses `mpc_sos_fade/execution.py`, so the fix arrived here without a line changing in this
folder.** `indicators/BUG_exit_fill_price_mismatch.md`: the FILL BAR was allowed to stage the stop,
which put the stop through the market on a trade that had gone nowhere and market-closed every leg
at the next bar's open. Fixed on both sides, including `mpc_b_leg_strategy.pine` and its export.
✅ **`compare_bleg.py` exit 0** on a FULL-HISTORY post-fix export (`VANTAGE_XAUUSD, 15_1b2f3.csv`,
**21,691 bars**, 2025-08-31 → 2026-07-31) at warmups 100 / 200 / 500 / 1000 / 2000, no truncation
warning. Fingerprint scan: **0 of 5 entries** have a stop staged on the fill bar.
⚠ **The B-LEG fork has ZERO affected entries in any window measured, before OR after** — its TP1 is
the broken swing extreme, far further from the entry than the A+ ladder's next fib, so its fill bar
rarely reaches it. **That is exposure, not proof:** the fix here is verified by construction (the
code is literally the A+'s) and by parity, never by a caught case. If a B-LEG trade ever shows the
symptom, treat it as new. ⚠ **Every B-LEG number measured before today was measured through the
bug** — the trade counts are thin enough that one changed result moves the whole picture. ⚠ **NOT a
recurrence of this bug, and it will keep appearing:** a stop staged legitimately at TP1 on a later
bar can still be behind the market when it goes live next bar, and then fills at that bar's open.
That is a backtest limitation, identical in Pine and Python, parity-neutral, and erring in the safe
direction — see `strategies/python/mpc_sos_fade/CLAUDE.md` → `### Wrong-side stop fills`.
Earlier: 2026-07-31 — **the session-window fork is CLOSED and proven, and the harness had a
latent hole that a partial chart export walked straight into.** `mpc_b_leg_strategy.pine` had never
received the DST-aware session windows its A+ parent has carried since 2026-07-12; both were synced
and `compare_bleg.py` re-run on a fresh export → **exit 0 at `--warmup 800`**, green at 1200 / 2000 /
3000. **What makes this run the right one for that fix:** the window is 2026-04-27 → 2026-07-31,
which sits ENTIRELY inside BST/EDT — the half of the year where the new city-clock windows and the
old fixed GMT-4 windows actually disagree (New York `0800-1700` America/New_York is 12:00–21:00 UTC
under EDT, an hour earlier than the old `0900-1800` GMT-4). A stale Python side would have disagreed
with Pine on every session boundary in this export, so green here is a real result rather than a
window where the two happen to coincide. **The harness hole:** `bl_l_bar`/`bl_s_bar` carry Pine's
`bar_index`, which counts from the first bar the CHART loaded, while the Python tracker counts from
the export's first ROW. Every previous export was the whole loaded history, so the two origins
coincided and nobody noticed the assumption. This one starts 15,362 bars in, and all 2,409 armed-bar
comparisons failed at exactly that constant — the logic was identical the whole time. `compare_bleg.py`
now MEASURES the origin (the modal `pine - python` difference) instead of assuming zero, and the
normalisation is deliberately majority-based so a genuine drift in WHICH bar armed is a minority
offset and still fails; `test_partial_chart_export_still_parity` and
`test_offset_normalisation_still_catches_a_real_armed_bar_drift` pin both halves. **Generalise it:
any parity column holding a Pine BAR INDEX is export-window-relative, and a harness that compares one
raw is only correct by the accident of a full-history export.** 19 tests green.
Earlier: 2026-07-30 — **the parent's new MINIMUM-STOP guard is PINNED OFF here, and is inert
on this path.** `mpc_sos_fade` gained `exec_min_stop_mode` / `exec_min_stop_val` (refuse a setup whose
stop lands too close to the entry — `qty = risk / stop_distance`, so a collapsing stop buys an enormous
position). It does not reach this fork: the floor is enforced in the parent's `_place_entries`, which
`BLegExecution` overrides, and `mpc_b_leg_strategy.pine` has no matching input to be parity-checked
against. `BLegConfig` pins the mode to `"Off"` so a future parent default change cannot silently claim a
guard this fork never runs. The hazard is also structurally absent here — a B leg's stop is the band
ORIGIN, always a full band away from the 0.5 entry edge, never a fib that can land on top of it. Porting
it = the Pine input + the floor check in this fork's `_place_entries` + a `cfg_min_stop` export column, in
one commit, then re-run `compare_bleg.py`. Nothing else changed and the parity run below still stands.
Earlier: 2026-07-29 — **the stale export is CLEARED: `compare_bleg.py` re-run GREEN on the
ratchet build.** `compare_bleg.py "VANTAGE_XAUUSD, 15_ab202.csv" --warmup 100` → exit 0, 21,493 bars,
2025-08-31 → 2026-07-29, still green at warmup 200/500/1000/2000. The export decoded
`cfg_exitmode = 20` (the new 3-way trail digit reading as "Structure + % ratchet"), `cfg_trail_pct = 1`
and `cfg_tp1_pct = cfg_tp2_pct = 0` — so the ladder changes below are proven through the export, not
merely present in it. `mpc_b_leg_strategy.pine` also compiles clean in TradingView. The ratchet's
43% → 53% run-capture caveat below still stands: parity proves the two sides AGREE, never that the
setting is right for B legs. Earlier: 2026-07-28 — **`mpc_b_leg_strategy.pine` caught up to the A+ exit ladder**, so this
package's two divergence pins are gone: `exec_runner_trail` is INHERITED again ("Structure + % ratchet",
with `exec_trail_pct` alongside it) and the TP rungs sit at the inherited 0/0. The Pine also gained the
`qty_percent = 0` guard — without it a 0 rung closed the WHOLE position at TP1, which is why typing 0
"blew up" there. Nothing changed in this package's CODE (the ladder has always lived in the parent's
`Execution`); what changed is that the config no longer has to lie to stay parity-green. ⚠ **The export
is now STALE and every B-LEG number from this build is unvalidated until `compare_bleg.py` is re-run**
— `cfg_exitmode`'s trail digit went 2-way → 3-way and `cfg_trail_pct` is new, so an OLD export decodes
the ratchet as the plain structure trail. ⚠ The ratchet's 43% → 53% run-capture result was measured on
**A+ trades only**; it is inherited for one-ladder consistency, not as a proven B-LEG result. Earlier:
2026-07-27 — the A+ blocked-setup AND missed-setup markers stay non-ported here, both now pinned by a test (the miss watch needed an explicit opt-out). Earlier: 2026-07-26 — the exit levers landed, the Pine-parity harness was built, and it came back GREEN on the first real export (see "The parity gate").

## Why it exists (the split, 2026-07-24)

The B LEG lived inside `mpc_strategy.pine` as a second setup type (`execBLeg`, default OFF).
Turned ON alongside A+ it made significantly more money, and Aaron wants to run it PARALLEL
to the A+ bot on the shared account (the portfolio-stacking seam he built). Decision:
**abstract it into its own strategy that shares the READ layer** (the engine stack + the A+
sequence tracker) and owns its OWN entry/stop/TP — because he intends to tune those
independently, which is the textbook signal to split. The coupling is only on the A+
sequence STATE (a clean read dependency, like depending on an engine), never on the A+ entry
logic. See the Pine file's header for the same reasoning.

## What it reuses vs what is new

It is deliberately ~90% the A+ bot. The fill / TP-ladder / stop-staging / %-risk-sizing /
R-grading machinery is direction- and setup-agnostic, so it is REUSED wholesale:

- **Reused from `mpc_sos_fade`:** `SignalAdapter` → `Signals`, `SosFadeSequence` → `SeqState`
  (the whole A+ engine + sequence), and `Execution` (the broker emulator + exit ladder).
- **New here:**
  - `bleg.py` `BLegTracker` → `BLegState` — the band-freeze / target-track / arm / tap /
    death state machine (Pine 3683-3758). Standalone; reads `Signals` + the `bleg_arm_*`
    flags off `SeqState`.
  - `execution.py` `BLegExecution(Execution)` — a thin subclass: `step(sig, seq, bleg)`
    stashes the `BLegState`; `_place_entries` is the ONLY override — A+ entries disabled,
    B-LEG limit rested at the band's 0.5 edge (SL beyond the leg origin, TP1 = broken swing
    extreme `2·edge−inv`, TP2 = expansion extreme `tgt`, TP3 runner). Everything from
    `_open_position` onward is the parent's.
  - `config.py` `BLegConfig(SosFadeConfig)` — a strict superset, adds only `bleg_max_days`.
  - `strategy.py` `MpcBLegStrategy(MpcSosFadeStrategy)` — inherits `_fill_model` +
    `engine_config` (the SAME `fvg_max_count=7` + `show_internal=False` pins — the B-LEG reads
    the same structure/fib engines), overrides `__init__`/`run`/`step` to splice the tracker.
    `run_dual` is disabled (no 1m secondary).

## The "A+ has priority" gate (kept for baseline; first tuning candidate)

`BLegExecution._place_entries` still computes the A+ `longArmed`/`shortArmed` via the parent's
`_armed()` and stands the B-LEG down on a side where A+ is armed — faithful to the Pine fork.
A+ never PLACES an order (the fork's whole point), it just holds the priority. When stacked
with the real A+ bot on one account the account layer re-does this arbitration, so **dropping
this gate is the first thing to try when tuning** (Aaron's own note in the Pine tooltip). Run
SOLO, the bot fires MORE B-legs than the parent did with `execBLeg` on, because no A+ position
occupies the account — that is correct and expected, not drift.

## Three parity-safe additions to `mpc_sos_fade` (do not revert)

The reuse needed three ADDITIVE, decision-neutral changes there (all re-verified: the A+'s
55 offline tests stay green):

1. **`signals.py`** — `Signals` gained `bull_bos_high/low` + `bear_bos_high/low` (the break-
   leg endpoints the band-freeze reads). Nothing in the A+ path reads them.
2. **`sequence.py`** — `SeqState` gained `bleg_arm_l`/`bleg_arm_s`, computed at the EXACT Pine
   point (Pine 3661): after the opposite-SOS death, BEFORE the continuation-BOS death clears
   `l_sos_bar` and BEFORE the half/618 latch update. This is the whole reason the sequence had
   to expose them — by the time `update()` returns, the state the B-LEG arms off is gone.
3. **`execution.py`** — the A+ arm decision was extracted from `_place_entries` into `_armed()`
   (a pure refactor) so the B-LEG subclass can reuse the priority gate. No behaviour change.

## The exit ladder is inherited (2026-07-26)

The structure runner trail, the TP2 stop-floor dropdown and the two setup toggles were ported into
`mpc_sos_fade`, and this bot picks up ALL of them for free — `BLegConfig` subclasses `SosFadeConfig`
and `BLegExecution` subclasses `Execution`, and the exit ladder lives entirely in the parent. The
full register is `mpc_sos_fade/CLAUDE.md` → `## The exit ladder`. What is specific here:

- **`exec_bleg` is re-defaulted to True.** `mpc_b_leg_strategy.pine` ships `execBLeg = true` (the
  A+ file ships it false), so `BLegConfig` overrides the inherited default to match. It gates the
  B-LEG arm in `_place_entries`; OFF the bot trades nothing, which is its only real use.
- **`exec_aplus` controls the PRIORITY GATE here, not entries.** A+ never places an order in this
  fork, so `exec_aplus=False` doesn't disable an entry path — it drops the "A+ stands the B leg
  down" gate entirely. That is the tuning experiment this file's own notes have called for since
  2026-07-24, now a one-flag run instead of a code edit. The same input was added to
  `indicators/mpc_b_leg_strategy.pine` under the label "A+ has priority (stand the B-leg down)".
- **This bot OVERRIDES TP1 / TP2 / SL** with its band prices (SL = band origin, TP1 = the broken
  swing extreme, TP2 = the expansion extreme). Everything from the stop staging down — the floor,
  the trail, both dropdowns — is the parent's, unchanged.
- **`exec_min_stop_mode` is PINNED `"Off"` (2026-07-30) and is INERT here.** The parent's
  minimum-stop guard runs inside `_place_entries`, which this fork overrides, so the floor is never
  applied on this path — and there is no `execMinStopMode` in `mpc_b_leg_strategy.pine` to be
  parity-checked against. The pin exists so a future parent default change cannot make this config
  claim a guard the code does not run. Structurally the hazard is absent too: a B leg's stop is the
  band ORIGIN, a full band away from the 0.5 entry edge, so it cannot collapse onto the entry the
  way a fib stop can. Porting it is three edits in one commit (Pine input, floor check in this
  fork's `_place_entries`, `cfg_min_stop` export column) followed by `compare_bleg.py`.

`indicators/mpc_b_leg_strategy.pine` was ported in the same pass and now matches: `execRunnerTrail`,
`execStructTrailBufTk`, `execTp2StopMode`, `execAplus`, and the `lStage2Floor` / structure-trail
exit block copied line-for-line from `mpc_strategy.pine`. **Completed 2026-07-28** — that Pine had
fallen a lever behind: it lacked the `"Structure + % ratchet"` trail method (+ `f_swingRatchet` and
`execTrailPct`), still defaulted the TP rungs 30/40, and still called `strategy.exit()` on a 0% rung.
All three were ported, so the two forks are back on ONE ladder with nothing pinned around a gap. **Not ported, deliberately:** `execSlLevel`
(the SL fib dropdown) is meaningless here because the B leg's stop is its band origin, not a fib; and
the pink blocked-trade markers, whose codes describe why an **A+** setup was refused — in this fork
A+ never trades, so those tags would report the opposite of what a reader would assume. A B-LEG
block tag would need its own code set, which is new design work, not a port.

**That non-port now also holds on the PYTHON side (2026-07-27).** `mpc_sos_fade`'s `Execution` gained
`blocks` (the same six codes, feeding the lab price chart's Blocked layer). This fork records none by
CONSTRUCTION: the recording hangs off the parent's `_place_entries`, which `BLegExecution` overrides.
`test_this_fork_records_no_blocked_setups` pins it, so restoring the parent's entry path here can't
quietly switch on tags that would mean the opposite of what they say.

**Same call for the MISSED-setup markers (2026-07-27), but this one is NOT free.** The parent's miss
watch scores how far an **A+** setup got before it died (2 of 3 / 3 of 3) — meaningless in a fork
where A+ never places an order. Unlike the blocks it runs from `step()`, which this fork delegates
straight to the parent, so it takes an explicit class-level opt-out: `BLegExecution._records_misses
= False`. `test_this_fork_records_no_missed_setups` pins it — a flag is far easier to flip by
accident than an overridden method. A B-LEG version of either marker needs its own code set (what
would "2 of 3" even mean for a frozen band?), which is new design work, not a port.

## Sizing — sizes ITSELF

`LAB_STRATEGY` declares `self_sizing: True` (like the A+ bot): `qty = equity·exec_risk_pct /
stop_distance`, so the lab's dynamic sizing engine leaves it alone and `exec_risk_pct` is the
risk knob. Registered as class `MpcBLegStrategy` (distinct from `MpcSosFadeStrategy`), so both
register and run side by side — the parallel-stack use case.

## The parity gate — `tools/compare_bleg.py` + `mpc_b_leg_strategy_export.pine` (built 2026-07-26)

BUILT, plumbing-tested, **awaiting its first real export**. `indicators/mpc_b_leg_strategy_export.pine`
= `mpc_b_leg_strategy.pine` (body byte-identical, only the line-40 `strategy()` title differs) + an
appended PARITY EXPORT block. Export it from a 15m XAUUSD chart, then:

```
command-center/backend/.venv/bin/python strategies/python/mpc_bleg/tools/compare_bleg.py <export.csv> --warmup N
```

Exit 0 = bar-for-bar identical. It is also registered in `backtest/tools/verify_parity.py`, so the
one-shot "is everything in sync?" run covers the B leg now.

**What it diffs, and why it is NOT a flag on `compare_strategy.py`.** The two bots diff DIFFERENT
fields. In this fork A+ never places an order, so:
- `px_dec_bits`' arm bits are the **B-LEG** arm (`bLegLongArm`/`bLegShortArm`), not `longArmed`.
  Diffing `longArmed` here would test a decision that never happens.
- `px_edge` is the frozen band's 0.5 edge, not an FVG edge.
- `px_tp1`/`px_tp2` are their own columns because the B leg derives its ladder from the band
  (TP1 = 2·edge − origin, TP2 = the expansion extreme) instead of reading fib levels.
- `px_stages` IS still diffed: the B leg arms off the A+ sequence's death, so an A+ stage drift is
  where a B-LEG mismatch usually ORIGINATES. It turns "a trade differs" into "the upstream moved".

What IS shared — the packed `cfg_*` decoding — is imported, not duplicated: both export Pines plot
`cfg_*` with one identical scheme on purpose, and `compare_strategy.config_from_export` now returns
the caller's config CLASS, so passing a `BLegConfig` gets one back with `bleg_max_days` intact.
`allow_bleg=True` is needed because the A+ decoder (correctly) REFUSES an export with `execBLeg` on,
and this fork's export always ships it on.

**The `bl_*` columns are the point.** They carry the TRACKER's own state — `bl_bits` (on/tap per
side), `bl_bars` (the armed bar per side, packed as bar+1 so 0 = none), and the four band prices per
side (top / bot / inv / tgt). Every new B-LEG rule lives in the tracker (band freeze, deepest-band
migration, target track, tap, staleness death), and a bug there shows as a wrong band price MANY bars
before it becomes a wrong trade. Without them a mismatch says "a trade differs" and nothing about why.

**Two things that are NOT in the export, deliberately:**
- `execSlLevel` — the fork has no such input (the B-LEG stop is its band ORIGIN, not a fib on the A+
  leg). `cfg_strcodes`' SL slot is pinned to the "1.0" code so the shared decoder reads
  `exec_sl_level = "1.0"` — correct-and-unused here, and one decoder keeps serving both exports.
- The Diagnostic Log block, dropped in the export copy to stay under Pine's token cap (CE10117),
  exactly as the A+ export does.

**Regenerate it whenever `mpc_b_leg_strategy.pine` changes** — the split point is exact and is
recorded in the export's own header (`sed -n '1,4486p'`, then re-append the block and restore the
line-40 title). A new trade-affecting input = a new `config.py` field + a new `cfg_*` plot + a new
read in `compare_bleg.config_from_export`, in the SAME commit as the Pine change.

Offline guard: `tests/test_compare_bleg.py` (8 tests) round-trips the tool — run the bot, serialise
its own decisions + tracker state into an export-shaped CSV using the Pine's packing, feed it back,
require exit 0 — then plants a `bl_l_top` mismatch and a `px_dec_bits` mismatch and requires the tool
to catch each at the right bar. The encoder there is written from the Pine's plot expressions rather
than from the tool's decoder, so it also catches the two drifting apart. It uses 30 synthetic days,
not 10: on 10 no leg ever ARMS, so the `bl_*` diff would prove nothing.

Two of those eight cover the **partial-export** case added 2026-07-31 — one re-packs `bl_bars` as
if the chart held 15,362 bars before the export's first row and requires exit 0, the other shifts
all but ONE armed bar and requires that odd one to still be caught. They are a pair on purpose:
the first alone would pass just as happily if the tool had stopped diffing the bar index at all.

### PARITY GREEN 2026-07-31 (exit 0) — the session-window build

`compare_bleg.py "VANTAGE_XAUUSD, 15_cabec.csv" --warmup 800` → **exit 0**. 6,329 bars,
2026-04-27 → 2026-07-31. Green at warmup 1200, 2000 and 3000 too, so nothing late is hiding
behind the skip.

**Why the warm-up is 800 and not 100.** This export is a partial chart — it starts 15,362 bars
into the loaded history, so Pine walks in already holding a frozen band that the Python side has
never seen. It has to wait for a whole fresh band to form. That is cold start in the ordinary
sense, just a longer one than a from-bar-zero export needs; the same run at `--warmup 400` fails
only on `bl_s_top`-style band prices Pine carried in, never on a decision.

**What it proves that the 21k-bar 2026-07-29 run could not.** The window is entirely inside
BST/EDT, which is exactly where the new city-clock session windows differ from the old fixed
GMT-4 ones. `mpc_b_leg_strategy.pine` had been a genuine fork on those windows; a Python side
still on the old offsets would have disagreed with Pine on every session boundary here. Config
decoded off the export: `cfg_exitmode = 20` (the ratchet trail), `cfg_trail_pct = 1`,
`cfg_tp1_pct = cfg_tp2_pct = 0`, `cfg_bleg_days = 1.25`, risk 10%, `aplus_window = 4320`.

Exercised: 605 / 695 bars with a live long / short leg, 2,063 bars armed, **2 entries, 2 trades
graded, sum 5.73R**. The usual caveat applies harder than ever on a 3-month window — that trade
count proves the two implementations agree and says nothing about the edge.

**It also found the harness bug described in "Last reviewed"** — the raw `bar_index` comparison.
Worth restating as a rule: a round trip proves the two halves agree, and a full-history export
hides an origin assumption, so **the first PARTIAL export is its own kind of gate.**

### PARITY GREEN 2026-07-29 (exit 0) — the ratchet build

`compare_bleg.py "VANTAGE_XAUUSD, 15_ab202.csv" --warmup 100` → **exit 0**. 21,493 bars,
2025-08-31 → 2026-07-29. Green at warmup 200, 500, 1000 and 2000 as well, same cold-start
picture as the first run.

This is the run that clears the 2026-07-28 stale-export warning. What makes it non-vacuous is
what the export DECODED, not just the bar count: `cfg_exitmode = 20`, `cfg_trail_pct = 1`,
`cfg_tp1_pct = cfg_tp2_pct = 0`. The tens digit of `cfg_exitmode` is the trail method, and it
went 2-way → 3-way when the ratchet landed. An OLD export would have decoded the ratchet as
the plain structure trail and gone green while comparing two different exit ladders — this one
carries the third code, so the Python side really was configured to the ratchet.

5 trades graded, **sum 10.91R** over the window. That trade count is the same warning as ever:
enough to prove the two implementations agree, nowhere near enough to tune against.

### PARITY GREEN 2026-07-26 (exit 0) — first real export

`compare_bleg.py "VANTAGE_XAUUSD, 15_9b74a.csv" --warmup 100` → **exit 0**. 21,231 bars,
2025-08-31 → 2026-07-24. Green at every warmup from 100 to 2000, so the ~100-bar skip is genuine
engine cold start, not a mask.

**The run was not vacuous** — it exercised the machinery this harness exists to check:

| what | count |
|---|---|
| bars with a live long / short leg | 2,195 / 1,010 |
| bars tapped (long / short) | 568 / 141 |
| bars ARMED (long / short) | 2,024 / 862 |
| entries taken (long / short) | 2 / 3 |
| trades closed and graded in R | 5 |
| distinct frozen band prices diffed | 48 long / 45 short |

So the band freeze, the deepest-band migration, the target track, the tap and the staleness death
were all diffed against Pine across ~90 distinct bands — not just the 5 bars that became trades.
That breadth is the whole reason the `bl_*` columns exist.

**The first run found a bug — in the HARNESS, not the port.** `bar 680 px_entry_dir: py=1 pine=-1`.
`_py_row` derived the trade direction from `Fill.qty`'s sign, but `qty` is NOT signed in this
codebase — `Fill.dir` is. Every short read as a long. Fixed to read `Fill.dir`.

**Why the round-trip test could never have caught it:** the test's encoder had the identical wrong
derivation, so encoder and decoder agreed and the round trip passed. A round trip only proves the
two halves are consistent with each other, never that either is right. That is the structural limit
of the technique, and it is why a real export is the gate.
`test_entry_direction_comes_from_fill_dir_not_qty_sign` now asserts against the FIELD rather than
against a round trip — the only way a shared-mistake bug like that gets caught offline. Apply the
same shape to any future packed column whose value is DERIVED rather than copied.

**Config decoded off the export** (all of it correct): `bleg_max_days` 1.25, A+-priority ON,
`execBLeg` ON, Structure trail, TP2 floor = TP1 price, TP1/TP2 30/40%, risk 10%.

Backtest numbers are now validated logic, not directional guesses — with the standing caveat that
**5 trades is far too thin a sample to tune against.** Parity says the code is right; it says nothing
about whether the edge is real.

## The 6.5-year measurement — 2026-08-04

That last sentence was finally acted on. **Nothing above this line changes** — parity is still green
and the code is still right. What is new is that the bot has been *replayed*, rather than validated,
over a real window.

```
python backtest/tools/run_report.py --strategy mpc_bleg --start 2020-01-01 --end 2026-08-03
```

**155,453 M15 bars, 50 trades, −0.94R.** No cost layers (the free baseline, comparable to the
Strategy Tester). Win rate 34%, average win +1.65R, average loss −1.01R, expectancy −0.02R/trade,
peak-to-trough **−15.62R**.

| | trades | sum R | mean R | 95% CI on mean R | max DD (R) |
|---|---|---|---|---|---|
| `mpc_sos_fade` | 161 | **+135.94** | +0.84 | **+0.29 → +1.40** | −7.99 |
| `mpc_bleg` | 50 | **−0.94** | −0.02 | **−0.40 → +0.37** | −15.62 |

**Read the CI column, not the sum R column.** A+'s interval is entirely positive — 6.5 years of gold
is enough to say its edge is real. B-LEG's straddles zero and is centred on it: its true 6.5-year
total belongs anywhere between −20R and +18R, and no amount of staring at the −0.94 will narrow that.
This is the one place where `CLAUDE.md`'s "sample size arrives at the portfolio level" argument does
**not** apply: that rule says do not reject a strategy for trading rarely, and this is not a rejection
— it is the statement that the measurement cannot yet distinguish this bot from a coin.

⚠ **Everything here is about the SHIPPED DEFAULTS.** `exec_tp1_pct`/`exec_tp2_pct` = 0/0 and
`exec_sl_level` = "1.0" are **pinned to this fork's Pine for parity**, which is a correctness
decision, never a performance one. Lab run `096432c2ad20` ran 30/40. Read the table as "the
parity-pinned configuration has no measured edge", never as "the B-LEG setup does not work".

⚠ **The obvious next move is also the dangerous one.** Optimizing over 50 trades will find a winning
combination whether or not one exists. If it is done: state the out-of-sample split **before** the
grid runs, and expect the honest answer to be "not enough data", because `mpc_sos_fade_optimization.md`
Run 12 already showed on the A+ bot that buying trade count by loosening a rule loses money.

⚠ **`--no-regime` was passed** on this run (the regime tag is reporting-only and does not touch a
trade). The "by regime" answer for B-LEG has not been measured and is a genuinely open question — the
2021–2023 losing stretch and the 2024–2026 recovery could be regime or could be noise at n=50.

## The exit-ladder re-default — 2026-08-06

Two defaults moved. Both are FORK PINS in `config.py` and matched defaults in
`indicators/mpc_b_leg_strategy.pine` + its export; neither is inherited, and neither should be
"reconciled" with the A+ parent, whose own measurements say the opposite in both cases.

| | `exec_trail_pct` | `bleg_max_days` |
|---|---|---|
| was | 1.0 (inherited) | 1.25 (`maxval` 3) |
| now | **0.05** | **4.0** (`maxval` 6) |
| A+ parent | keeps 1.0 — its sweep gives 0.25% → 43.6R vs 109.3R at 1.0 | n/a, B-LEG-only input |

**Charged (spread + swap, `vantage_demo`), 186,312 M15 bars, 2018-09-13 → 2026-08-05:**

| | trades | sum R | PF | wins | max DD | IS | OOS |
|---|---|---|---|---|---|---|---|
| old defaults | 59 | −1.73 | 0.94 | 21 | −16.00R | −8.15 | +6.42 |
| **shipped now** | **112** | **+12.02** | **1.23** | 37 | **−8.89R** | **+0.78** | **+11.24** |

Free book at the new defaults: 112 / +17.64R / PF 1.36 / maxDD −6.21R.

**The protocol, because at n≈60 the protocol is most of the evidence.** The split was declared
before any row ran (IS 2018-09-13 → 2022-09-30, OOS after). Every row is a REAL REPLAY of the full
window; IS/OOS are computed by splitting the resulting trade list on entry time, which is safe here
only because it splits the OUTPUT of one identical run and therefore cannot change which trades
exist. Levers were measured ONE AXIS AT A TIME off the shipped baseline, never as a grid — a grid
over 60 trades finds a winner whether or not one exists, and this file said so before the work
started. The two that survived their own axis were then combined and re-checked in both halves.

⚠ **The reason to trust the combination is the FLATNESS, not the peak.** PF is 1.18–1.25 across the
whole 4×3 grid of trail step {0.05, 0.08, 0.10, 0.15} × staleness {3, 4, 5}. Every cell beats the
old PF of 0.94. There is no sharp optimum to have fitted to.

⚠ **It is still not an edge.** 95% CI on mean R = **−0.140 → +0.355**, i.e. the 7.9-year total
belongs anywhere in −16R to +40R. The top 3 trades are 100% of the total and the single best is
+5.07R of it. What genuinely improved is the drawdown, the sample size and the sign of the first
half — all three of which are what a live decision is actually made on, and none of which is proof.

### Rejected, with the reason each was worth trying

- **The minimum-stop guard** (floors 0.10%–0.40% of price, prototyped as a `_place_entries`
  subclass): no effect that survives both halves. The hypothesis was reasonable — this fork's stop
  distances span $2.51 to $49.02 and `qty = risk / dist`, so the tight end buys a position a single
  15m gold bar can traverse whole — and it is simply not where the money goes. ⚠ **The cheap
  estimate disagreed and was wrong in the usual direction**: deleting the refused rows from the
  finished 50-trade list scores a 0.25% floor at **+6R**, the real replay scores **zero**. This
  file's warning about entry-side filters and the one position slot, reproduced on demand.
- **The deeper band edge** (rest at `l_bot`, the 0.618 retrace, instead of `l_top`): PF 2.43,
  maxDD −4.58R, and **28 trades with +15.81 of its +17.25R in the first half**. Fill rate collapses
  112 → 28, which is the real cost and the reason the headline PF is meaningless.
- **Shorts only**: PF 1.58, IS −1.15 / OOS +14.82. A bet on gold's 2023-2026 run wearing a filter.
- **Dropping the A+ priority gate** (`exec_aplus = False`): this file has called it the first tuning
  candidate since 2026-07-24. It adds exactly one trade over 7.9 years and that trade loses.

### Open lead — the Asia-session filter (NOT shipped)

Refusing entries in the Asia session and the late-day window gives **79 trades / +12.32R / PF 1.37
/ maxDD −4.98R**, positive in both halves (IS +2.89 / OOS +9.42) — the best drawdown of anything
measured, on Aaron's stated objective. Two independent samples agree: the original 50-trade baseline
had Asia at −5.0R on 13 trades. The mechanism is plausible (Asia is the thinnest book for gold, and
this fork's tightest stops are the ones a thin-book wick reaches).

**It is not shipped because it is new code, not a default.** Neither `mpc_b_leg_strategy.pine` nor
this package has a session filter for the B-LEG arm; adding one is a Pine input + a `cfg_` column +
the Python gate + a parity re-run, in one commit. It is also the most curve-fit-prone thing measured
here — slicing 112 trades by session is exactly the shape that finds a pattern in noise — so it
needs its own out-of-sample statement before it ships, not this one reused.

## Tests

```
command-center/backend/.venv/bin/python -m pytest strategies/python/mpc_bleg/tests/ -q
```
Offline. Hand-traced `BLegTracker` (band maths, arm, tap, staleness + invalidation death,
deepest-band migration, BLEG_MAX conversion) + end-to-end driver run + longs/shorts-off.

## Do / Never

- **Do** port any change to `mpc_b_leg_strategy.pine`'s B-LEG block or execution here
  line-for-line, and any change to its A+ engine into `mpc_sos_fade` first.
- **Do** keep `BLegConfig` a superset of `SosFadeConfig` — a new A+ toggle should flow in for free.
- **Never** build a second copy of any engine or of the A+ sequence here — reuse `mpc_sos_fade`.
- **Never** trust a backtest number until a `compare_bleg.py` is green on a fresh export.

## References

- Pine source of truth: `indicators/mpc_b_leg_strategy.pine` (B-LEG block ~3683-3758,
  execution ~4429-4506).
- The A+ bot it reuses: `strategies/python/mpc_sos_fade/CLAUDE.md`.
- Upstream runner: `backtest/CLAUDE.md`; engines: `engines/*/CLAUDE.md`.
