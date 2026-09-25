# Notes — Exit ladder — dated build and measurement history

Every dated deep-dive behind the exit-ladder lever table — breakeven buffer, scale-in, time stop, costs, and the re-entry-switch flips. Moved VERBATIM out of `strategies/python/sos_fade/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## The exit ladder — every TP/SL lever, and which ones are switchable

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The exit ladder — every TP/SL lever, and which ones are switchable*.

| Stage | What sets it | Switchable? |
|---|---|---|
| **Stop loss** | A fib on the deep side of 0.5, `exec_sl_level` ∈ {0.618, 0.702, 0.786, **0.886**, 1.0, **Custom**}, then `exec_sl_buf_tk` ticks beyond it. **Default 0.886 since 2026-07-27** (the deep edge of the entry band, and what Aaron trades); 1.0 = the leg origin. **"Custom" (2026-08-02) reads `exec_sl_custom` instead** — any ratio in (0, 1.0]. | **0.886 → 1.0 only** (the dropdown values or any Custom ratio between them) — anything shallower is unsupported, see the warning below |
| **TP1 / TP2** | Fibs, chosen AUTOMATICALLY by how deep the entry was. Deep entry → TP1 = 0.5, TP2 = 0.382. Shallow → TP1 = 0.382, TP2 = 0.0 (the swing extreme). | **No** — only the sizes (`exec_tp1_pct` / `exec_tp2_pct`, **both default 0** since 2026-07-27: bank nothing, ride the runner) |
| **TP3 (the runner)** | No target at all. It rides a trailing stop, and it is where the strategy's money is (>100% of net in every window measured). | **Yes** — see below |
| **Stop staging** | Three phases, always on: (0) the full stop → (1) after TP1, breakeven + `exec_be_buf_tk` → (2) after TP2, a floor, then the trail. | **No** |
| **The breakeven buffer** | `exec_be_buf_tk`, default **30 ticks = $0.30**. How far past the entry the stage-1 stop sits. **SWEPT 2026-08-11 and 30 is the optimum — every wider value is worse, monotonically** (60 → −6.17R, 400 → −35.90R). ⚠ **It does NOT cover the swap and cannot be made to**: one night of long swap is $0.796/oz, 2.7× the whole buffer, so ~29% of scratch exits are net losses on every real account — and widening it costs ~5R of total return per 1R of scratch rescued, because the same move that saves a returning trade cuts a running one. **Do not widen it** — Run 17. ⚠ **"Do not make it swap-aware" is AMENDED, not retracted, as of 2026-08-24** — `exec_be_buf_mode` can now express the buffer as a fraction of the trade's own stop, optionally floored at what the trade has cost; it ships `"Ticks"`, so this row still describes the shipped bot. Run 17's ceiling on what a cost-covering stop can recover (+2.11R against 15.06R jitter) is unchanged and still binds. | **Yes, and the FIXED buffer is already at its best value** |

🔴 **THE FORM NOW CASCADES: THE MODE PICKS WHICH CUSHION IS ON SCREEN (2026-08-27).** The tick figure
shows under `Ticks` and the fraction, the cap, the cost margin and the conflict rule show only under
the modes that read them — `_be_buffer` returns on the tick branch before any of the other four is
touched, so under the shipped default they were four settings that could not do anything. ⚠ **This
was not cosmetic. A run launched on the fraction mode at 0.35 put the stage-1 stop $12.92 into
profit instead of $0.30 and closed the 2026-06-04 short at +0.35R where the shipped mode held it to
+4.51R — and nothing on the form said which cushion was in play.** ⚠ **The same rule was applied to
the short-hold variant's five rows and the floating-gap anchor's precedence chain**, both read
straight off the returning branch in `execution.py`.
| **The TP2 floor** | `exec_tp2_stop_mode`: **"TP1 price"** (tight, can scratch the runner on the first pullback) / "Breakeven" (most room) / "One trail step behind" (never below breakeven). | **Yes** — dropdown |
| **The runner trail** | `exec_runner_trail`: "Fixed step" (a `exec_trail_step` grid ratchet anchored on TP2) / "Structure (swing)" (park the stop at the structure engine's last confirmed swing low/high, offset by `exec_struct_trail_buf_tk`) / **"Structure + % ratchet"** (same anchor, then climb one `exec_trail_pct`-of-price step per step of favourable move). | **Yes** — dropdown |
| **The ratchet step** | `exec_trail_pct`, default **1.0**. Only read in "Structure + % ratchet" mode. A PERCENT of price, never dollars — see below. | **Yes** |
| **Early bail-out** | `exec_close_opp_sos` (default OFF) force-closes on an opposite SOS instead of riding to the stop. **Measured INERT** (Run 5): turning it on produced a byte-identical trade list — an opposite SOS never fires before SL/TP has already resolved the position. There is nothing on the other end of this lever. | toggle exists, **does nothing** |
| **Deep-entry stop override** | `exec_sl_deep` (default **OFF**, Pine `execSlDeep`, 2026-08-02). An entry filling AT OR DEEPER THAN 0.786 puts its stop at the leg origin (1.0) instead of `exec_sl_level`; 0.702 and shallower keeps the chosen level. It exists because the entry band and the stop share the 0.886 line, so the band's deep end is priced against a stop it is nearly touching. 🔴 **MEASURED 2026-08-16 (Run 18) and it stays OFF: it costs 24.0R with the secondary live and 23.0R without**, on a full 2×2 over one window (2018-09-14 → 2026-08-14, bar fills) — the shipped cell is the best of the four at +164.4R / 189 trades. The mechanism is Run 11's from the other direction: the targets are fibs and do not move, so a wider stop makes every winner worth fewer R while every loss is still −1R (a 0.786 entry goes from a 0.100 stop to a 0.214 stop, the runner falls 7.86R → 3.67R and the position is less than half the size). ⚠ **It DOES hold a shallower drawdown** (−4.8R vs −5.5R) — expensive, not worthless, if drawdown ever becomes the objective. ⚠ **Its interaction with `exec_secondary` is 1.0R against sd 15.06R**, so the two are separable. This is the first direct measurement of the SHIPPED narrow version; the 2026-08-02 revert `sos_fade_strategy.pine` records was of a WIDER version that also caught 0.702, and the two agree. ⚠ **Its toggle is INERT when `exec_sl_level` is already 1.0** (or Custom = 1.0), because both states then place the same stop; the meta says so with `disable_if` + `disable_note` and the lab takes the row off the screen, matching the Pine's `active = execSlLevel != "1.0"`. ⚠ **Its OFF label is `Stop {exec_sl_level}` — a TOKEN the editor substitutes, never a typed `0.886`**, which would be a second copy of a neighbouring param's value. | **Yes** — toggle |

🔴 **26 params are marked `hidden` in the meta (2026-08-15) — RETIRED FROM THE EDITOR, NOT REMOVED.** Every field is still in `SosFadeConfig`, still at its default, still sent on every run and still settable through the API; only the row is gone, so the editor is the levers still under test rather than every lever that exists. Aaron's call, and his framing is the rule: *"I don't want you to delete the configurations because I might talk to you, and you might be able to toggle it back on super easy."* **Ask and it comes back — one `hidden` flag.** The set: `exec_longs`/`exec_shorts`/`exec_bleg`/`exec_conf_sz`; `exec_arm_div` and the five RSI engine dials; `exec_poi_source`/`exec_ob_deepen`/`exec_fvg_pre_zone`/`exec_fib_overlap`/`exec_fib_deep_edge`; and the whole `Higher-timeframe filter` group. 🔴 **SEVEN MORE landed the same day under a STRICTER bar, and the bar is the part worth keeping.** The first batch above was chosen on "never moved across every stored run", and Aaron rejected that criterion outright: *"we did backtest with and we proved that they're not worthy or have another setting that beats it consistently. Keep that setting and hide the others."* **Never moved is the ABSENCE of the experiment, not its result.** So the seven each name a sweep in `sos_fade_optimization.md`: `exec_close_opp_sos` (Runs 5 AND 6 — *exactly 0 difference*, twice; an opposite SOS never fires before SL or TP has resolved), `exec_tp2_stop_mode` (Run 2's 525-combo grid — TP1 price wins at 70.7R, Breakeven is the harmful one), `exec_struct_trail_buf_tk` (Run 2 — 10→80 ticks moves it 0.4R, *"do not chase it"*), and `exec_fvg_deep_only` + `exec_no_late_day` (Run 12 §3 and §4 — two of the four relax routes, all of which lost money or were noise). 🔴 **`exec_be_buf_tk` WAS in that list on Run 17's evidence and came OUT on 2026-08-27, and the
rule behind that is general: A ROW A `show_if` MAKES CONDITIONAL MUST NOT ALSO BE SETTLED.** Run 17
swept the tick buffer and nothing beat 30, which is the bar for settling — but the buffer MODE has
three values and the shipped one is Ticks, so this figure is what the ladder reads on every live
trade while the two fraction fields it competes with were on screen. **The form was showing the
cushions that were not in force and hiding the one that was.** Between them the two mechanisms hide
a row everywhere: the gate takes it off wherever it cannot matter, `hidden` takes it off wherever it
can. ✅ **THE OTHER FIVE FOLLOWED THE SAME DAY AND THE RULE NOW HAS NO EXCEPTIONS** (Aaron's call):
the fixed-step trail size, the divergence validity window, the two RSI extremes and the
higher-timeframe exhaustion source. ⚠ **Two cost nothing on screen** — their parents are off in
the shipped config, so each appears only in the mode that reads it, which is the point. ⚠ **Three
do** — the divergence veto ships ON and is still refusing setups, so its switch was on screen
while the two numbers it fires on were not. **31 rows → 34.** ⚠ **None of the five had a sweep
behind it** — they were retired on the *never moved lately* criterion Aaron rejected in August,
which is the absence of the experiment rather than its result. ⚠ **The fixed-step trail size is
the one that looks like an exception and is not**: Run 2 settled the trail METHOD, and the method
dropdown is on screen — the step size is a row behind it, so its gate was already doing the
hiding. Pinned with no exceptions by `test_NO_param_is_both_settled_and_conditional`. ⚠ **`exec_sl_buf_tk` is the case that shows the bar biting and it stays VISIBLE**: it WAS in a grid — Run 4 — and Run 4 is marked *INVALID, DO NOT USE THE NUMBERS*, which is worse than untested. ⚠ **The master switches (`exec_arm_sweep`, `exec_aplus`, `aplus_window`), the secondary mechanics and `flat_by_close` have ZERO mentions in the optimization log and therefore stay**, however long they have sat still. ⚠ **`exec_risk_pct` is never hidden on any criterion** — it decides position size on the strategy the LIVE bot runs. ⚠ **The divergence VETO is deliberately NOT in it** — `div_veto` and `exec_respect_veto` are ON and still refusing setups, so the ARM is settled and the behaviour is not; hiding those would take a live rule off the screen. ⚠ **`exec_conf_sz` is not a settled setting but a DEAD one** — declared in `config.py` and referenced only in a comment, so nothing reads it. ⚠ **`exec_req_fvg`, `exec_deep_fib`, `exec_sl_level` and `exec_secondary` stay visible because they have actually been moved on real runs**; a param somebody tunes is a live question whatever it defaults to. ⚠ **Only THREE of the first nineteen carry a sweep** (`exec_poi_source` and `exec_ob_deepen` off Run 15's order-block thread, `exec_htf_exhaust_only` off Run 5's zero-effect pair) — the rest are hidden on Aaron's direct instruction or because they are structural (longs/shorts), which is a legitimate reason and not a measured one. Say which is which rather than letting the next reader assume the whole set was proven. ⚠ **The "never moved" figures behind the first batch came from the 15 `sos_fade` runs then in the lab (19 now), and that is the whole sample** — older rows were deleted, so it means "nobody has touched these lately", never "never in this strategy's history". Mechanism, and the escape that shows a hidden param moved off its default: `command-center/frontend/CLAUDE.md` → `ParamEditor.tsx`.
| **Minimum stop distance** | `exec_min_stop_mode` ∈ {**"Off"**, "% of price", "Fixed $", "x ATR(14)"} + `exec_min_stop_val` (0.10). An ENTRY filter, not an exit lever — it lives in this table only because it is the guard for the `exec_sl_level` hazard two rows up. A setup whose stop lands closer to the entry than the floor places no order and records block code 7. | **Yes** — dropdown + floor; ported 2026-07-30 |
| **Time stop** | `exec_time_stop_mode` ∈ {**"Off"**, "Before TP1 only", "Always"} + `exec_time_stop_hrs` (36.0). Close a position open for that many CALENDAR hours. **"Before TP1 only" fires only at stage 0** — TP1 never touched, so the stop never staged to breakeven; touching TP1 makes a trade immune for the rest of its life. The exit leg books as `L-TIME` / `S-TIME`. Added 2026-08-05; **defaulted ON ("Before TP1 only", 36h) 2026-08-06 — the baseline moved.** | **Yes** — dropdown + hours; see `### The time stop` |
| **Scale-in (ADD size)** | `exec_scale_in` (default **OFF**) + `exec_scale_mode` (**"Trail"**) + `exec_scale_max_adds` (**3**) + `exec_scale_cap_x` (**0.5**). Past TP2, adds to a runner the trail is already protecting, sized so the add's worst case equals the profit the stop already guarantees. **The only ADDITIVE lever here; every other one is protective.** Added 2026-08-16; defaults re-measured 2026-08-18 after the fill model was corrected. **Since 2026-08-19 the adds also carry their own TAKE PROFIT** — `exec_scale_tp_mode` (**"Ride"**, i.e. no target, which is what the measurement says; it shipped for one day on `"Prev week H/L"` and was reversed once the 4.38R gap behind that choice turned out to be 25.64R). ✅ **Five** `cfg_*` columns. ⚠ **The fifth is UNGATED until a fresh export carries `cfg_scale_tp`.** | **Yes** — toggle + mode + two numbers + where the adds bank; see `### Scale-in` |

### The breakeven buffer can be a FRACTION of the stop (`exec_be_buf_mode`, 2026-08-24, ships OFF)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The breakeven buffer can be a FRACTION of the stop (`exec_be_buf_mode`, 2026-08-24, ships OFF)*.

🔴 **The cap is the point, not a safety belt, and it is why the fixed buffer sweep read the way it
did.** A buffer that reaches the rung which staged it closes the trade at the target instead of
protecting a runner. MEASURED on run `5a5e2174d095` (243 trades, ECN costs charged): that happens on
**0 trades at 30 ticks, 24 at 300, 70 at 600** — so a wide fixed buffer stops being a breakeven stop
and becomes an exit, and the widest rungs were losing R for that reason rather than by cutting
winners early. As a fraction: **0.20R never reached the rung on any of the 243; 0.35R did on 5%;
0.50R on 24%.**

⚠ **Aaron's premise was right about his trades and wrong about the typical one.** The median round
trip costs **$0.020/oz** — 6% of the $0.30 buffer — but **66 of 243 trades (27%) cost more than it**,
and **10 of the 46 scratches are genuine losses.** The driver is overnight financing (correlation
**0.727** with hold time), which swings the per-trade cost roughly **250-fold**. That range is the
argument against any fixed distance, and it is the whole argument.

🔴 **THE COST FLOOR IS THE THING RUN 17 SAID NOT TO BUILD, AND ITS CEILING STILL BINDS.** Run 17
rejected a swap-aware stop and asked to be re-read first; it has been. Its mechanism objection
survives — only overnight trades pay financing and those are the runners — and **the cap bounds that
without reversing it.** Its ceiling on what a stage-1 ratchet can recover, **+2.11R over 6.5 years
against 15.06R of run-to-run jitter**, is unchanged. **So the cost half cannot be argued on return;
argue it, if at all, on the 10 losses currently reported as breakevens.** The FRACTION half is a
separate question Run 17 never asked — it swept the buffer's SIZE and never its SHAPE.

⚠ **The conflict case REFUSES to stage.** When accrued cost alone sits past the cap, no price both
covers cost and stays under the rung, so the frozen entry stop is held. Staging anyway is a stop
labelled breakeven that guarantees a loss. A conflicted LONG stays conflicted (the cap is fixed,
cost only grows); a SHORT can recover on the swap credit. Stage 2 is untouched, so the second rung
still lifts the stop and hands it to the trail. `exec_be_cost_conflict = "Clamp to cap"` is the
measurable alternative and is not the recommendation.

🔴 **AND THE CONFLICT NEVER HAPPENS — MEASURED 2026-08-24, THE SETTING IS DEAD CODE.** The two runs
that differ only in `exec_be_cost_conflict` came back **trade for trade identical** (fingerprint
`8088d3411b5e4449`, 246 trades each, matched on entry time, direction, entry, exit and R). Accrued
cost never once grew past 75% of the entry → nearer-rung distance, because on gold at this sizing
costs are small next to that distance. **The branch above has unit tests and has never made a
decision on real bars** — repo rule 9 landing inside a feature, and the tests that cover it
construct the conflict artificially, which is the *fixture more capable than production* shape.
⚠ **Before this build is ever switched on, either prove the branch reachable at a width somebody
would actually use, or delete the setting and hardcode the clamp.** Run 26.

🔴 **SWEPT TEN WAYS 2026-08-24, AND EVERY ONE LOSES — Run 26.** Best variant (cost floor at 0.20R,
margin 0.05R) is **+150.8R against the control's +159.1R**, with a **worse** drawdown (47.91% vs
46.79%). Every rung in the table is below the control on return and above it on drawdown. The
problem being fixed — 10 breakeven exits that are really small losses — is worth **−0.52R over 6.5
years**, so the cheapest complete fix costs ~**16R per 1R rescued**, against Run 17's 5:1 on a
Standard book. ⚠ The 8.3R gap sits inside the strategy's **sd 15.06R** run-to-run spread, so the
best variant is *"not measurably worse"* and never *"better"* — which is not an argument for adding
five settings to a live strategy. ✅ **Two things the sweep vindicated**: the cap works (best single
trade stays **24.6R at all ten settings**, where Run 17's uncapped widening ate the runner), and the
cost floor genuinely beats the plain fraction because it only widens on trades that have SPENT
money, leaving the same-session runners alone (top-five **86.0R, identical to control**, where the
wide plain-fraction rungs clip it to 82.1R). 🔴 **The narrowest rung is the worst value in the
table** — `frac 0.10` produces MORE scratches than the control (51 vs 46) and hands back MORE R,
converting winners into scratches without fixing any scratch. Full tables, run ids and basis:
`sos_fade_optimization.md` → Run 26.

✅ **PARITY GATE GREEN, 2026-08-26 — rule 22 is now SATISFIED for this change.**
`compare_strategy.py "VANTAGE_XAUUSD, 15_6fb2a.csv"` → **exit 0 at warmups 100 / 200 / 500 / 1000 /
2000**, 21,259 bars from 2025-10-01. ⚠ **It proves the SHIPPED path only.** The five new fields have
no Pine counterpart, so the export configures them at their off position and a green says **nothing**
about the fraction or cost modes — the same structural blindness this file already records for the
Custom stop level. ⚠ **And the harness itself warned that the no-gap arm was not exercised**: this
export ran with Require-FVG ON, so neither side entered that fallback branch. A green covers the
bars it walked, never the branch nobody entered.

⚠ **At warmup 0 the gate is RED at bar 16 (`px_s_stage` py=1 pine=0), and that is PRE-EXISTING.**
Confirmed rather than assumed: the identical failure, same bar, same field, same values, reproduces
on the code from BEFORE this change in a throwaway worktree at `1ff36e4^`. Green from **warmup 50**
onward on both. **A pre-existing red is still a red and is not retired by this note** — it is
recorded here so the next reader does not spend the afternoon blaming the breakeven buffer for it.

⚠ **THE SHIPPED PATH IS UNCHANGED.** The control run reproduces the pre-change
baseline `5a5e2174d095` **trade for trade** (fingerprint `13fc4e5f9c7a95fb`, 243 vs 243 — ⚠ the
FIRST version of this fingerprint keyed on `entry_time`, which is not a field in these trade records,
so `.get()` returned `None` for every trade and that component compared nothing to nothing; corrected
to `entry_ms` + `exit_name` on 2026-08-25 and both claims survived. **A comparison built from several
fields degrades SILENTLY — assert the key exists before you fingerprint on it.** Run 26), so tick
mode is byte-identical to before this build. `compare_strategy.py` has NOT run — no decision-stream
export exists on this machine (the CSVs here are trade lists and engine chart data), which is the
"9 of 14 gates could not run" condition the root CLAUDE.md records. ⚠ **Rule 22 is NOT satisfied.**
⚠ **No Pine counterpart either**, so even with an export the gate could never configure a non-default
run of these five fields — the same blindness this file already records for the no-gap arm gate and
the POI source.

**TESTED:** 21 tests in `tests/test_be_buffer.py`, 21 of 21 watched RED by 18 mutations. ⚠ **One was
VACUOUS on its first pass and is recorded rather than quietly replaced** — it asserted the buffer
reads `_sl` rather than "the live stop", and `Execution` has no live-stop attribute, so no mutation
could redden it. **A test that cannot go red is a claim with nothing behind it**, and that one would
have read forever as proof the hazard was considered. Story:
`docs/SOS_FADE_BUILD_NOTES.md` → *The breakeven buffer becomes a FRACTION of the stop*.

### The swing ratchet (`"Structure + % ratchet"`, DEFAULT since 2026-07-28)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The swing ratchet (`"Structure + % ratchet"`, DEFAULT since 2026-07-28)*.

⚠ **Both rows were measured at `exec_tp1_pct = exec_tp2_pct = 1`, NOT at the shipped 0/0** (found
2026-07-28). The A/B is apples-to-apples so the comparison stands, but the absolute figures are not
the shipped configuration: at the true 0/0 default the same window gives **110.65R**, and the 1%+1%
rungs cost 1.4R. Quote 110.65R as "the current bot", not 109.3R — and run `compare_strategy.py` at
0/0 so the parity gate tests what the Pine actually ships.

**⚠ `exec_sl_level` — `"0.886"` (the default since 2026-07-27) and `"1.0"` only. Do NOT sweep or
ship 0.618 / 0.702 / 0.786** (Run 4, 2026-07-26). The entry is a resting limit inside the
**0.5–0.886 fib band**, and all four sub-1.0 levels sit inside that SAME band — so the stop can be
placed at, or past, the entry price. Nothing validates the result.

### Scale-in (`exec_scale_in`, 2026-08-16) — the first ADDITIVE lever this bot has ever had

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *Scale-in (`exec_scale_in`, 2026-08-16) — the first ADDITIVE lever this bot has ever had*.

🔴 **THE TRIGGER IS THE TRAIL (stage 2), NOT A TARGET, and that is what makes it self-regulating.**
At TP2 the stop is only at TP1, so `locked` is small while `price - stop` is large and the affordable
add is a rounding error. Once the trail ratchets up near price the same arithmetic permits a LARGE
add. A trending runner buys size; a stalling one buys nothing, with no extra "is this trade still
good" test.

⚠ **+83R is well outside this strategy's 15.06R run-to-run jitter, so the direction is real** — but
it is one window on one instrument, and the gain is concentrated in the runners that already carry
this book. **It does not widen the edge; it levers the tail that was already there.**

🔴 **THERE IS NO STRUCTURAL TRIGGER IN IT AT ALL, AND THAT IS AN OPEN DESIGN QUESTION rather than an
oversight** (Aaron, 2026-08-16: *"I don't know what market structures I'm looking at to add into"*).
The rule asks only *can I afford this*, never *is this a good place*. Structure enters INDIRECTLY —
the trail is parked on the last confirmed swing, so an add fires roughly when a new HL/LH confirms —
but that is a side effect of the trail's anchor, not a rule anyone chose, and it enters at MARKET on
the bar the trail moves, which is the worst price of the leg where the BASE entry rests a limit in a
discount zone and waits. Adding on a fresh BOS, on a retest of the broken level, or at a limit on
the new leg's retrace are all untested alternatives. **Location has never been varied.**

⚠ **Adds are separate LOTS, not extra `_qty`.** `_exit_portion` prices the whole position off ONE
`_entry`, so growing `_qty` would value added units as if bought at the original entry and invent
profit. Each lot closes pro-rata with the base and pays its own commission and spread.

🔴 **AN ADD THAT HANDS THE WHOLE GUARANTEE BACK CLOSES THE TRADE AT EXACTLY $0.00 — and until
2026-08-18 nothing in the run said an add had ever existed.** That is the affordability rule
landing on its own worst case: `add_qty = locked / per_unit`, so a stop-out at the SAME stop the
lot was sized against cancels to the cent. Run `295a6ff29d21` did it 8 times in 160 trades, and
the reader saw a SHORT entered at 4098.60, exited at 4085.07 — visibly in profit — labelled `Lost`
with a P&L of zero. **Every field that could have explained it describes the BASE lot only**:
`qty`/`size` is the base size, `legs` is the exit ladder, `mfe_usd`/`mae_usd` are excursions on the
base. So `Trade.adds` now records each FILLED lot (`{price, ms, qty}` — `_add_lots`, a report-only
twin of `_adds`, which `_exit_portion` spends on the way out), `backtest/output.py` puts it on the
equity-curve point, and the chart draws an `Add` line per lot. **The P&L identity in `Trade`'s
docstring is now stated in full and it needs every lot** — base leg + each add + costs.

**3 tests in `tests/test_execution.py`, all MUTATION-proven** — the lot is recorded, the P&L
identity closes only when every lot is read, and a trade that never added carries an empty ledger.
Deleting the one `_add_lots.append` line reddens exactly the first two. ⚠ **The exact-flat fixture
needs `exec_scale_cap_x = 2.0`**: at the shipped 0.5 the CAP binds first, the add is smaller than
the offsetting size, and the trade still books a profit — so the $0 outcome belongs to the
UNCAPPED affordability rule, not to scale-in in general.

⚠ **`_add_lots` is in `_POSITION_FIELDS`**, so a restarted live bot restores its own record of what
it bought. ⚠ **The cost of that outcome is real and small: those 8 trades were worth +6.27R
un-scaled, against +154.73R that the same toggle ADDED over the run** (`295a6ff29d21` 295.91R with
scale-in on vs `1f98a36d063c` 141.18R with only that toggle flipped, same window, same params).
**Do not read the $0 trades as an argument against the feature; read them as the guarantee being
paid for.** ⚠ **They are also invisible to a win rate** — a scratch is neither, which is what
`scratch_count` has always been for.

⚠ **`_entry`, `_risk_usd` and `stop_distance` stay anchored to the BASE fill, so R is scale-free and
every row stays comparable to a run with this off.** A scaled trade's "3R" is NOT 3x the capital an
unscaled 3R had at work. It is also why the real implementation reproduced the shadow-ledger harness
to −0.00R, which was predicted to diverge and did not.

⚠ **THE GUARANTEE HOLDS TO THE STOP, NOT THROUGH A GAP.** Price jumping past the stop fills the whole
combined size at the open, and 3x the size loses 3x. Nothing here protects against that.

⚠ **NO ACCOUNT-LEVEL CAP EXISTS.** Net risk-to-stop is ≤ 0 by construction, but margin and
`run_stack`'s risk budget both see the FULL position. `docs/LIVE_TRADING_PIPELINE.md` → G10: the live
allocator is unbuilt, **so this must not go live before it is.**

✅ **VERIFIED TWO WAYS, and the first is the one that matters on a LIVE strategy.** The OFF path is
bit-identical to the costed control measured before the feature existed — 128.26R / 6.03 maxDD / 65
losers / −2.06R worst, all four — so a toggle whose OFF path moved the numbers would have failed.
ON at 2 adds reproduces the harness figure it was decided on (211.59R vs 211.59R, diff −0.00R).

🔴 **NO PARITY GATE HAS RUN.** The Pine side is built (`execScaleIn` / `execScaleAdds` /
`execScaleCapX`, and `pyramiding` raised 0 → 4, which is compile-time and cannot be an input), but
`compare_strategy.py` needs a fresh TradingView export only a human can take, and the export carries
no `cfg_*` column for these three yet. **Until both land, an ON result is a LAB finding** — and per
this file's own standing lesson, a trade-affecting input with no export column is invisible to the
gate BY CONSTRUCTION, so the gate would go green while comparing two different strategies.

### Scale-in gained a MODE — and the first answer was measured on a broken fill (2026-08-18)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *Scale-in gained a MODE — and the first answer was measured on a broken fill (2026-08-18)*.

🔴 **THE 2026-08-17 DEFAULTS WERE WRONG AND ARE REVERSED. Every Run 20 figure is VOID.** That sweep
booked each add at the price its RULE TRIGGERED on, and Pine buys it somewhere else — a market
order fills at the NEXT bar's open, a resting limit fills when price comes back. So the harness
credited `BOS retest` with the retest level itself on every fill, which is exactly the price that
mode has to WAIT for and frequently never gets. **On the corrected fill the ranking INVERTS.**

**THE PARITY GATE IS WHAT CAUGHT IT** — `px_closed_r` at bar 1356, 2025-10-21: py **27.07R** vs
pine **22.03R**, one trade, on the largest runner in the book. Every decision field before it
agreed, and both books were internally consistent. ⚠ **A backtest that prices a fill at the moment
its rule FIRED is measuring a DECISION, not a TRADE, and nothing in the output can show you that.**

🔴 **THE BUG ALSO BROKE THE FEATURE'S ONE GUARANTEE, which is the more serious half.** The
affordability arithmetic is written against the price the add is BOUGHT at; a market order is sized
at one price and filled at another. **MEASURED over the same 182 trades: the market-order add
turned winners of +3.41R and +1.34R into losses of −2.50R and −2.15R, against an un-scaled worst of
−2.06R.** A resting limit closes it — the fill price is known before the order is sent, and price
that GAPS through a buy limit fills BETTER. ⚠ **`Trail` is a market rule by nature and keeps a
small version of the gap: zero breaches at 3 adds, −2.24R and −2.73R at 4.** That is why the add
count ships at 3, and zero observed is not zero possible.

⚠ **`BOS retest` LOSES MONEY outside 2020 at every budget above one add** — down to −14.15R against
not scaling. It is kept as an option because it is implemented, gated and parity-green, **not
because any measurement supports it.**
⚠ **The CAP is the drawdown lever, not the add count.** Same 3 adds: ex-2020 drawdown 10.34 → 17.02
→ 22.99 → 24.56 across 0.5x / 1.0x / 2.0x / 3.0x. Adds are nearly free; SIZE is what hurts.
⚠ **NO CELL BEATS NOT-SCALING'S 2020-FREE ret/DD OF 15.34.** Scaling reliably buys return and
reliably pays in drawdown. This is the cell where that trade is closest to fair and the only one
better than baseline on BOTH axes over the full book. **Quote both halves.**
⚠ **LADDER SHAPE IS NOT MEASURABLE and the intuition behind it is wrong here.** At a fixed 1.5x
total, big-first 199.27R / flat 194.15R / small-first 183.96R — inside the 15.06R jitter. Risk on an
add is measured to the STOP, which trails up behind price, so the LAST add is the cheapest, not the
riskiest; small-first in fact had the lowest drawdown.

⚠ **`exec_scale_mode` REFUSES an unrecognised value** rather than falling back, same standing as
`exec_sl_custom`. ⚠ **`exec_scale_in` is still False, so the OFF path is byte-identical at 128.26R
and no other figure in this file moves** — what changed is what the toggle DOES. **Pin
`mode="Trail", adds=2, cap=1.0` to reproduce Run 19's 211.59R.**

✅ **PARITY GREEN 2026-08-18** — exit 0 on a fresh 20,799-bar export taken at `cfg_scale_in=1 /
cfg_scale_mode=1 / cfg_scale_adds=4 / cfg_scale_cap=2`, i.e. one that genuinely exercises the
feature rather than reading all zeros. **The same gate on the same schema was RED at bar 1356
before the fix**, which is what makes the green worth something.

⚠ **`algos/live/bridge.py` REFUSES `exec_scale_in` outright** — it mirrors one entry limit and one
ratcheting stop and has no path that places a second entry. **This cannot go live until the bridge
learns to place adds AND the account allocator exists** (margin sees the full stacked position even
though risk-to-stop does not).

🔴 **OPEN, and it is the next question worth money: an add has NO TARGET.** It rides the same
trailing stop as the base — but the base earned a runner by being a reversal bought at a discount
after a sweep and a structure shift, and an add has none of that behind it. Banking adds at a
target, structural or otherwise, has never been tested; the liquidity engine already emits previous
day/week levels and session highs and lows and the execution layer reads none of it.

### The adds got a TAKE PROFIT, and the measurement said not to (2026-08-19)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The adds got a TAKE PROFIT, and the measurement said not to (2026-08-19)*.

**It was measured before it was built, and every target lost to riding.** XAUUSD 15m 2018-09-13 →
2026-08-14, PU Prime ECN costs, on `Trail` 3 × 0.5×, 182 trades. 🔴 **These are the RE-MEASURED
numbers, taken after the resting-order fix below — the first set was wrong and is void.**

🔴 **THE ORDERING IS THE FINDING, NOT ANY SINGLE ROW.** That column sorts by how OFTEN the target
fires: weekly levels are far away and rarely bind, H4 levels are near and bind constantly. A
separate control run — banking at a flat multiple of base risk rather than at structure — produced
the same monotonic curve independently (1R **126.76R**, 3R 134.19R, 6R 141.24R), and banking at 1R
came out **below never scaling at all**. Two unrelated target families, one shape: the adds earn on
the few trades that run a long way, and every target truncates exactly those. ⚠ **The control is
untouched by the bug below and still stands** — its target is a fixed price off the base entry, so
there is no level and nothing to mitigate.

🔴 **BANKING BUYS A SMOOTHER RIDE AND PAYS FOR IT OUT OF THE TAIL — the last three columns are the
honest case FOR a target.** Strip the top 20 trades and the ranking inverts on risk-adjusted return:
prev day 14.49 and H4 14.60 against Ride's 11.99, with drawdown falling 10.34 → 7.15. On the
ordinary book a target is genuinely better. It only loses because the extraordinary book is where
this strategy earns, and truncating it costs more than the smoothing is worth.

⚠ **Drawdown on the FULL book barely moves** (7.15–7.51 against Ride's 7.24). Read against the
whole sample, a target is not buying safety.

⚠ **VOID, NEVER RE-MEASURED:** `daily + weekly` 174.35R, `daily + weekly + H4` 161.00R and
`session H/L` 159.39R. All three came off the throwaway harness that carried the live-bar flaw, and
none is a shipped option. Do not quote them; re-measure if they are ever wanted.

⚠ **The worst trade is −2.06R in all 16 configurations, identical.** That is the answer to the
question that prompted the work: the affordability rule already stops an add turning a winner into
a loser, so there is no giveback left for a target to prevent.

✅ **IT SHIPS ON `"Ride"` — settled 2026-08-19 (Aaron), after one day on `"Prev week H/L"`.**
He picked the target deliberately, wanting certain money off the runners rather than the best
expectancy, and **on the number he was given that was a sound trade: a 4.38R gap to `Ride`, INSIDE
this strategy's 15.06R jitter.** "Certainty for no measurable cost" is a reasonable thing to buy.
The 4.38R came from the run with the live-bar bug in it. **The true gap is 25.64R — OUTSIDE the
jitter, and about 13% of total return.** Re-asked on the real number, he reversed within a minute.

🔴 **THE LESSON IS ABOUT THE DECISION, NOT THE DIAL, and it generalises past this input.** A wrong
measurement does not arrive looking wrong. It arrives as a **reasonable-looking number** and quietly
buys a judgement call: nothing about "4.38R" was suspicious — it was small, plausible, and it made a
preference cheap. The defect was two layers away in a mitigation flag, and the ONLY symptom it ever
produced at this level was a default nobody would otherwise have picked. ⚠ **So a judgement call is
only as settled as the measurement under it. When the number moves, go back and re-ask the
question** — do not carry the earlier answer forward as a decision already made. Rule 4 says never
write a guessed number into a doc; this is its neighbour, and it costs more: **a wrong number that
has already been ACTED on leaves a defensible-looking decision behind, and the decision outlives the
correction unless somebody deliberately goes back for it.** ⚠ Session H/L is deliberately not an option:
worst measured, and it would need six more mirrored Pine variables.

🔴 **THE TARGET IS RESTED AT THE BAR'S CLOSE AND FILLS ON THE NEXT BAR (`_add_tp_level`), AND THAT
IS THE WHOLE REASON TWO OF THE FOUR MODES WORK AT ALL.** Resolved from the LIVE bar instead —
which is how this was first built — `"Prev day H/L"` and `"H4 H/L"` banked **ZERO times in eight
years**, returning a figure byte-identical to `Ride`. They were not short of levels: daily resolved
**1,804** valid targets and H4 **2,438**, every one of them standing and beyond the newest add.

⚠ **WEEKLY HID IT COMPLETELY, AND THAT IS THE TRANSFERABLE PART.** A week level dies on a **CLOSE**
through (`BREAK_HIGH` / `BREAK_LOW`), so it survives the spike that fills it and banked normally
throughout. The one family anybody was looking at was the one family immune to the defect — the
default looked healthy while two of its three alternatives were inert. **A feature that works on the
option you are watching tells you nothing about the options you are not.**

⚠ **The fix is not new machinery — it is the one-bar order delay the rest of this file already
honoured.** TradingView places `strategy.exit(..., limit=)` at a bar's close and it is live on the
NEXT bar; the base ladder stages `dec.stop = self._current_stop()` in Phase B for exactly this
reason. The adds were the single path that skipped it. `test_a_target_swept_by_the_filling_bar_still_fills`
pins it, and reverting the fix reddens that test and only that test.

🔴 **BANKING DOES NOT HAND THE ADD SLOT BACK.** Pine's `lAddN` only counts up, and the Python side
zeroes each lot **in place** rather than emptying `_adds`, because the ladder is capped on adds
BOUGHT. Freeing the slot would let a trade add again after banking — "scale in and out repeatedly",
which is a **different strategy** that nothing here has measured. There is a test pinning it.

⚠ **The comparator decodes an absent `cfg_scale_tp` as `"Ride"`, and that is the opposite of how the
four columns beside it are read.** "Absent ⇒ off" is safe for `cfg_scale_in` because that feature
shipped OFF. This one ships **active**, so falling back on the config default would replay every
pre-2026-08-19 export with its adds banking at a weekly level the exported Pine had no code to look
at — and the diff would blame the strategy for the harness's own configuration.

⚠ **UNGATED SO FAR.** `cfg_scale_tp` is new, so no export carries it yet and
`compare_strategy.py` has never checked this path. Rule 22 is not satisfied until a fresh export
lands with the column present and the gate passes on it.

### An add lot is now a TRADE-SHAPED record (2026-08-20)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *An add lot is now a TRADE-SHAPED record (2026-08-20)*.

🔴 **The lot's excursion is measured FROM THE LOT and is not the trade's.** An add is bought later
and further into the move, so it sits through a different part of it — on the fixture the base's
drawdown reaches 103.5 on its entry bar, which happened *before the lot existed*. Copying the
parent's numbers down would report the base's worst price as the add's, and the chart would draw a
`DD` line (the chart's adverse-extreme chip) at a price that lot never saw. MEASURED over 2018-09→2026-08: **110 of 112 lots have
an excursion that differs from their parent's.** The two that match are lots that happened to ride
the same extremes, not evidence of inheritance.

⚠ **Seeded ASYMMETRICALLY on the fill bar, the same rule `_try_entry_fill` follows.** A `Trail` add
is a market order at the bar's open, so the whole bar is genuinely the lot's. A `Limit` add is
reached by price coming to it from the wrong side, so that bar's *favourable* extreme is the
approach into the order — `_widen_add_excursions` skips the fill bar entirely for a limit lot, and
would otherwise hand every one of them a run it never made.

⚠ **`_adds` and `_add_lots` are INDEX-ALIGNED and that is now load-bearing.** The spent list says
which lots are live; the record list says what each did. `_bank_adds` zeroes in place rather than
popping, which is what keeps them aligned — a future edit that pops from either breaks the pairing
**silently and in reporting only**, which is the shape of defect nothing here fails on.

⚠ **`exit_price` is ABSENT, never `0.0`, on a lot nothing closed** — through `backtest/output.py`
and `chart_spec.py` alike. A defaulted zero reports a lot as having exited at price zero, with the
same confidence as a real measurement. Same rule as the bar cache's coverage and the terminal
probe: *never let "not measured" and "measured zero" be the same value.*

⚠ **There is no backfill and there cannot be one** — it would mean replaying the strategy. A run
stored before this carries the three original keys, and the chart's `Scale-in detail` row simply
does not appear for it.

🔴 **The parity gate is GREEN and CANNOT COVER THIS, and saying so is the point.**
`compare_strategy.py` diffs the **decision** stream; every field added here is reporting-only, so a
green run means *my edits to `_exit_portion` and `_bank_adds` did not disturb the decisions* — which
is worth having and is not the same claim. The claim that needed proving was proved directly
instead: full-history replays across four configs, fingerprinted on entry/exit/qty/price/R/costs,
**byte-identical to HEAD**. ⚠ Note the gate's own invocation is `--warmup 1000`; run without it and
it reports a mismatch at bar 16 that is engine cold-start and nothing else.

### 🔴 A TP RUNG WAS SLICING THE ADDS, AND `_finalise_trade` BINNED THE REST (fixed 2026-08-19)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *🔴 A TP RUNG WAS SLICING THE ADDS, AND `_finalise_trade` BINNED THE REST (fixed 2026-08-19)*.

✅ **Exactly two rows came back UNCHANGED, and they are the two that should have.** `0/0` never
slices (the runner closes 100% of the base, so the fraction was always 1.0) and `50/50` never
creates an add at all — the ladder fully closes the position before `_stage` reaches 2, which is
the gate `_maybe_scale_in` requires. Every row that could be wrong was, and no row that could not
be moved. That is the regression check on the fix, not just on the shipped default.

⚠ **`discarded` and `re-run` are two different measurements and only the second one counts.** The
discarded column valued each orphaned lot at the exit bar's CLOSE, while a trade ending on a stop
or a limit would have filled it at that price instead — so it SIZES the defect and does not
reconstruct the run. It is kept because the gap between the two columns is the point: adding it
back to `booked` predicted 172.17R at 25/0 where the re-run measures 174.62R. **A defect this
shape is re-measured, never corrected by arithmetic** — the missing P&L compounds, so it moves
every later trade's size, and win%, sd and drawdown cannot be reconstructed from an aggregate at
all.

⚠ **DIRECTION IS NOT FIXED, and the aggregate hides it.** Only **49 of the 112** dropped lots were
in profit — by COUNT most were underwater. The net came out positive because the winners are far
bigger, which is what lots added into a trend look like. On a single trade the bug can flatter just
as easily: the unit test's fixture drops a LOSING lot, so there the old code read 21,073 against a
true 11,257. **"It understates" was true of the eight-year total and of nothing smaller.**

🔴 **IT COULD NOT FIRE AT THE SHIPPED `0/0`, WHICH IS THE WHOLE REASON IT SURVIVED.** With both
rungs at zero the runner closes 100% of the base, so the pro-rata fraction was always 1.0 and the
two implementations agreed exactly. **The divergence existed only on settings nobody had ever
run** — rule 14, stated as plainly as this repo can state it: a green parity gate says the two
sides AGREE, never that either is RIGHT, and says nothing at all about a branch neither one
entered. ⚠ **The live bot was never exposed** (`exec_tp1_pct = exec_tp2_pct = 0`), and the fix is
byte-identical there: the `(0,0)` row reproduced at **194.15R / 7.24 R-dd / 3,510.4x** after it.

✅ **GATED 2026-08-19 on a purpose-made export, and the COVERAGE is the point rather than the
verdict.** `compare_strategy.py` GREEN on `engines/VANTAGE_XAUUSD, 15_4fef8.csv` (20,899 bars,
2025-10 → 2026-08, `--warmup 1000`) at **`cfg_tp1_pct=50, cfg_scale_in=1, cfg_scale_tp=0`** — Aaron
exported it specifically to reach this path.

🔴 **A GREEN GATE IS WORTH WHAT ITS COVERAGE IS WORTH, AND THAT WAS MEASURED HERE RATHER THAN
ASSUMED.** The run produced **25 trades, 24 add lots, and 11 exits that fired while an add was
live — all 11 closing exactly HALF the base (`frac = 0.5`)**, which is the pro-rata path itself.
Under the old code each of those 11 would have halved its add lots and binned the remainder. So
this run had **11 genuine chances to disagree** and took none.

⚠ **Contrast it with the run the day before**, which was equally GREEN on `49f80` and proved
nothing: that export carried `cfg_tp1_pct=0`, so the runner closed 100% of the base, the fraction
was always 1.0 and neither side ever entered the branch. **Same message, no information.** ⚠ **Do
not read "PARITY OK" as coverage — count the entries into the path you changed.** The probe is four
lines (wrap `_exit_portion`, count exits where `any(lot[1] > 0)` and `qty < _qty`); run it whenever
a gate is asked to vouch for a specific branch.

⚠ **The test is `test_a_tp_rung_does_not_slice_the_adds`, WATCHED RED by mutation** (restore the
pro-rata block → 121.4 vs 100.4 on P&L and on R). It carries no hand-computed constant: it runs the
same price path at `exec_tp1_pct` 0 and 50 where the rung banks at 105 and the stop sits at 105, so
the two runs ARE each other's expected value and only a sliced base can separate them.

### The time stop (`exec_time_stop_mode` / `exec_time_stop_hrs`, 2026-08-05)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The time stop (`exec_time_stop_mode` / `exec_time_stop_hrs`, 2026-08-05)*.

⚠ **Breakeven was the obvious alternative and it is INERT — measured, not assumed.** The entry is
a RESTING LIMIT, so price is sitting at the entry the moment it fills and the next bar's wick
crosses back over it: **161 of 161 trades touch breakeven, median 0.25h — one bar.** By hour 8 the
share of losers that have not returned to breakeven is **0%**. A breakeven-gated time stop fires on
nothing at any usable cutoff, and the sweep confirms it (0 trades cut at every H ≥ 8).

✅ **RE-RUN 2026-08-06 and this table is the corrected one.** It was measured twice over: once
before the one-bar force-close fix, and once before `eq_exempt_fvg` reached the Python side. Both
were real reasons to distrust it and **neither moved it** — every row shifted by ≤0.05R and the
trade counts, the cut counts and the plateau are unchanged. Recorded because "we re-measured and
nothing moved" is a result; a table nobody re-ran after two known-relevant fixes is not.

🔴 **"Always" is the row that justifies the stage gate, and it is not close: +137.94R → +97.32R,
a THIRD of the edge gone.** Same clock, same 36 hours — the only difference is that it also cuts
trades that had already reached TP1. It cuts 26 where the gated version cuts 6, and the 20 extra
are the winners. **The clock is not the lever; the stage gate is.** This is also why nothing below
~16h works: **losers here die FASTER than winners** (median hold — losers 2.0h, winners 17.8h), so
the stop is already the fast exit and the clock can only ever catch the tail that lingers.

✅ **The queue effect did NOT materialise, and that is a measured result rather than an
assumption: the trade count is 159 in EVERY row, including the "Always" run that cut 26 trades.**
This was the live risk on the whole exercise — with one position slot, a trade cut at 36h frees the
slot early and setups no arithmetic can see would have entered in its place, which is exactly how
the minimum-stop guard's cheap estimate got its SIGN wrong (+1.84R estimated, **−1.84R** replayed).
Here the naive re-pricing and the real replay agree on the delta to the cent (+4.23R at 36h),
because the trade list genuinely did not reshuffle. ⚠ **Read that as a fact about THIS window, not
as a general licence to re-price instead of replaying.** The reason it holds is mechanical and
narrow: SOS Fade takes ~2 trades a month, so a slot freed 60 hours early usually contains no setup at
all — and an ENTRY-side change like the min-stop guard frees the slot at the exact moment a setup
exists, which is precisely when a competitor is nearby. **An exit-side lever and an entry-side
filter are not the same risk, and the next lever still gets replayed.**

⚠ **Do not read the +4.23R as edge.** `backtest/tools/jitter_audit.py` measured this strategy's
run-to-run spread at **sd 15.06R**, so +4.23R is a quarter of one standard deviation. **The case
for this lever is the DRAWDOWN — 7.99R → 5.62R at 36h, a 30% reduction, and 5.38R at 30h — and it
rests on 6 trades in 6.5 years.** That is a real improvement in the number a risk budget is set
against, bought for R that is indistinguishable from noise; it is not a profit lever and must not
be sold as one.

⚠ **Calendar hours, weekends included** — the same basis the swap is charged on, and the one a
reader can check against a chart without knowing which hours the market was open. A Friday-to-Monday
hold advances the clock by the whole weekend on a handful of bars, which is deliberate and pinned.

⚠ **`b_leg` INHERITS it, unlike the minimum-stop guard which that fork pins Off.** The lever
lives in the parent's `step()`, which `BLegExecution` delegates to, and both bots share ONE exit
ladder. `strategies/tradingview/b_leg_strategy.pine` got the identical inputs in the same commit so the two
sides cannot drift. **But the 24h–40h plateau was measured on SOS Fade trades only** — a B leg waits for a
LATE retrace by construction, so treat any value there as untested until it is replayed.

⚠ **The Pine inputs are declared next to the exit block, not up in the GRP_EXEC panel**, and that
must not be tidied up: TradingView keys saved input values off DECLARATION ORDER within each type,
and the last `input.float/string/int` in `sos_fade_strategy.pine` is `execBeBandR` (~4050), so declaring
the pair down at the exit block shifts **nothing**. Inserting them beside their siblings at ~483
would silently reset every later string and float input on every chart running the script.

✅ **PARITY VALIDATED 2026-08-06, AND GETTING THERE TOOK THREE EXPORTS AND FOUND A REAL BUG.**

🔴 **The bug it found is a one-bar fill error, and it was in the port from the first line.**
`_close_at(sig, sig.close, ...)` closed the position at the DECIDING bar's close. Pine's
`strategy.close()` is a MARKET order, so it cannot execute on a bar that has already closed — it
fills at the NEXT bar's open. Measured on real bars: Python booked bar 696's close **3651.28**,
Pine booked bar 697's open **3651.23**. The force-close is now held as `_pending_close` and filled
at the next bar's open, ahead of any stop or target, which is the order TradingView executes in.

⚠ **The same defect was already sitting in `exec_close_opp_sos`**, which is the other
`strategy.close()` in the Pine. It defaults OFF and has never appeared in a parity export, so it
was corrected by inference from the time stop's measured evidence rather than by its own. **The
one force-close that is NOT deferred is `flat_by_close`** — it has no `strategy.close()` behind it
(no Pine input exists) and its entire purpose is to be flat before the daily close, so deferring it
to the next open would carry the position overnight and charge the swap it exists to avoid.

🔴 **The second bug was in the HARNESS, and it is the more dangerous shape.** `_py_row` mapped a
force-close to `px_exit_run` by matching `endswith("CLOSE")`, so the new `L-TIME` / `S-TIME` leg
matched nothing and the tool reported `py=None pine=3855.13` — **a manufactured mismatch, in code
that was correct to the cent.** It now selects "any exit that is not a TP rung", so a future leg
name cannot reintroduce it. **A parity tool that must be taught every new leg name will fail this
way, and it fails by accusing the strategy.**

⚠ **A THIRD probe bug is worth recording, because it is this section's own lesson eating itself.**
The script that counts clock exits read `getattr(t, "exit_name", "")` — a field `Trade` does not
have — so it returned `0 closed BY THE CLOCK` for **every** export, including the one where the
clock fired 12 times. The field is `exit_reason`. **The exercise check written to catch
"green on a branch neither side entered" was itself silently answering zero**, and a zero from a
broken counter is indistinguishable from a zero from an unexercised branch. Read the field
directly so a rename raises; never `getattr` with a default in a check whose whole job is to
notice absence.

✅ **THE SWEEP WAS RE-RUN 2026-08-06 AND THE TIME-STOP TABLE IN THE BUILD NOTES IS THE CORRECTED ONE** — every row shifted by
≤0.05R, the trade counts and the plateau are unchanged. It had been stale twice over (the one-bar
force-close fix here, and `eq_exempt_fvg` reaching the Python side the same day) and neither moved
it. Quote the table freely now.

⚠ **Re-export at 4 hours after any change to this lever.** 36 is the shipped value and is
untestable on a normal chart; 4 is the same code path and exercises it dozens of times.

### ✅ CLOSED — the SOS Fade parity failure was the EQ/FVG coupling, not the entry rule (2026-08-06)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *✅ CLOSED — the SOS Fade parity failure was the EQ/FVG coupling, not the entry rule (2026-08-06)*.

🔴 **They were not. `_fib_snap` is line-for-line identical on both sides, and the gap Pine rested
on did not exist in Python at all.** Dumping the live gap list at that bar found Python holding
five gaps and Pine holding a sixth — a bearish gap `[4965.73, 5060.25]` born 143 bars earlier,
which Python had FIFO-evicted and Pine had kept because it sits on an active EQH/EQL.

🔴 **The cause is `eqExemptFvg`, and the shape of it is the lesson.** That input exempts a gap
behind resting liquidity from the FVG cap. It **defaulted ON in `sos_fade_strategy.pine` on 2026-08-03**
(`b1b461b`), while on the Python side `backtest/replay/EngineStack` **built no EQ engine and passed
no levels to the FVG engine at all** — so the coupling could not fire even in principle. The two
implementations were evicting different gaps for three days.

🔴 **And no `cfg_` column carried the input, so the gate could not see it — it diffed two different
strategies and blamed the entry rule.** The Pine's own comment block, eight lines above the input,
still said *"THE EXEMPTION DEFAULTS OFF HERE"* and warned that neither the port nor the export
modelled it. The default was flipped and the warning was not.

✅ **GREEN at warmups 100 / 500 / 1000 / 2000**, and non-vacuously so — that export ran the live
`exec_min_stop_val = 0.08` and the time stop at **4 hours**, which closed **12 of its 26 trades**.
`--eq-exempt off` reproduces the original mismatch at bar 11031 exactly, so the fix is not masking
anything. `compare_bleg.py` exit 0 at 100 / 800 / 2000.

⚠ **The previous diagnosis in this file was WRONG and is recorded as wrong.** It read the failure
as `cfg_min_stop_val` going 0.30 → 0.08 "revealing" a pre-existing entry-rule disagreement. The
0.30 export really is green and every 0.08 export really is red, but that is export TIMING — the
0.30 export was taken before the Pine's default flipped. **Two changes landed within days of each
other and the visible one got the blame.** Forcing the Python floor across 0.0 / 0.05 / 0.08 / 0.10
never moved the diverging bar, which should have been read as *the floor is not involved* rather
than as *the floor is revealing something*.

✅ **MEASURED, and this is the counter-intuitive half: the coupling is heavily exercised and
changes no trade.** Over 155,531 M15 bars (2020-01-01 → 2026-08-03), **155,145 bars hold an active
EQ level, 92,984 hold at least one EXEMPT gap, and 20,546 hold MORE than the cap of 7** (max 12 at
once — the same maximum the Pine commit measured independently). Yet A/B over that window gives
**159 trades / +142.18R / maxDD 5.61R either way, with an identical entry set.** It moves the
RESTING LIMIT on **463 bars (0.30%)** — sometimes creating an edge where there was none — and not
one of those 463 ever became a different fill.

⚠ **So the honest summary is: the feature is real, it is exercised constantly, it changes where the
limit rests, and over 6.5 years it has never changed a trade.** Do not restate that as "it does
nothing" — the exercise counts are what make the second half a measurement rather than an
unentered branch, and this is one window on one instrument.

### The Custom stop level (`exec_sl_custom`, 2026-08-02)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The Custom stop level (`exec_sl_custom`, 2026-08-02)*.

🔴 **Do not go SHALLOWER than 0.886.** A stop shallower than the fill either fails the
positive-distance test (order cancelled, no trade and no tag) or leaves a tiny distance, and the
position size balloons off it. Turn the minimum-stop guard on first.

⚠ **An out-of-range ratio RAISES at construction rather than falling back.** Falling through
would replay a whole backtest against a stop nobody chose and report it as theirs.

⚠ **NO PINE COUNTERPART, so a Custom run is unvalidated.** `sos_fade_strategy.pine`'s `execSlLevel` is an

### The deeper-entry test (`exec_ob_deepen`, 2026-08-09) — REFUTED, and the mechanism is geometry

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The deeper-entry test (`exec_ob_deepen`, 2026-08-09) — REFUTED, and the mechanism is geometry*.

🔴 **The mechanism he named runs BACKWARDS, and it is geometry rather than luck.** TP1 is a FIB, and
on a long it sits ABOVE the entry — so entering deeper puts it FURTHER away, not nearer. **TP1 hit
rate 65.4% → 47.1%.** TP1 is what stages the stop to breakeven, so fewer trades get that protection,
which is the opposite of the theory. The same inversion applies to the deep-entry TP table (a deep
entry takes TP1 = 0.5 where a shallow one takes 0.382), so it compounds.

🔴 **The average LOSS exceeds 1R — −0.98R → −1.37R — which is the minimum-stop hazard arriving by a
new route.** The stop is a median **79% tighter**, which puts it inside ordinary bar noise, so price
runs straight through and the exit stops happening at the stop price. **A risk % is only the real
risk if the exit actually happens at the stop** (`### The minimum-stop guard`); this is that rule
being violated by an ENTRY change rather than by a stop-level change.

⚠ **The freed slot produced ZERO replacement trades, and that is worth recording because this repo
expects the opposite.** The queue effect is real for an ENTRY-side filter (the min-stop guard's cheap
estimate got its SIGN wrong that way), and here it did not fire — this bot takes ~2 trades a month,
so a skipped setup usually has nothing waiting behind it. **A fact about this window, not a licence to
stop replaying.**

⚠ **The strongest form was tested deliberately** — `_deepen` rests on the DEEPEST qualifying block,
not the nearest. A milder version would move less and lose less, i.e. a diluted dose of the same three
mechanisms; the direction is structural.

⚠ **NO PINE COUNTERPART**, so `compare_strategy.py` can never configure it and parity is structurally
unaffected. Ships **OFF**, byte-identical to before, so nothing historical moves. Kept rather than
deleted because it is the instrument this measurement was taken with.

### Bar-mode costs — commission and slippage, charged at last (2026-08-01)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *Bar-mode costs — commission and slippage, charged at last (2026-08-01)*.

⚠ ~~**Swap is NOT charged from the lab's fields.**~~ **Closed 2026-08-02 — see below.**

### Layered costs — spread and swap, and the one that moves trades (2026-08-02)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *Layered costs — spread and swap, and the one that moves trades (2026-08-02)*.

🔴 **EVERY ROW OF THE COST TABLE IN THE BUILD NOTES IS PRICED ON VANTAGE, AND THE BOT TRADES PU PRIME — which costs 23% more.**
Measured 2026-08-06 (`docs/LIVE_TRADING_PIPELINE.md` → G5) off the live terminal's own tick store,
1,893,438 ticks over 3 whole days. On the CURRENT shipped defaults over 155,531 bars, one real
replay per row: free **+142.18R** · Vantage costs **+130.59R** · **PU Prime costs +127.91R**, with
max drawdown 5.61R → 6.83R. **89% of that 2.68R gap is the SPREAD** ($0.32 vs $0.22 — 7.67R vs
5.28R), not the swap, whose worse long leg (−79.60 vs −74.84) is almost exactly cancelled by its
better short credit (+30.25 vs +26.98) on a strategy that trades both sides. **So read this table
as the BACKTEST broker's cost and add ~23% for the live one** — Vantage is pinned here because it
matches the TradingView feed the Pine was written on, which is a parity decision, not a cost one.

🔴 **AND THAT $0.32 IS A FACT ABOUT AN ACCOUNT TIER, NOT ABOUT A BROKER (2026-08-06).** It was
measured on PU Prime's **Standard** account — the one tier priced by a MARKED-UP spread — and
`backtest/fills.py::PROFILES` gave all four PU Prime tiers the same number, so a `puprime_ecn` run
charged ECN's commission ON TOP OF Standard's spread, a combination no real account offers.
✅ The unmeasured tiers carry `SPREAD_UNMEASURED` and **REFUSE**: `_spread()` routes
through `AccountProfile.spread_or_refuse()`, so the refusal fires wherever the profile came from
rather than only on the lab's path. ⚠ **It refuses the SPREAD, not the tier** — a raw tier's
commission and swap are known and still chargeable.
✅ **ECN — the tier this bot actually trades — left that list on 2026-08-14 at `$0.12`** (5 days of
its own ticks; provenance and which tiers still refuse: `backtest/CLAUDE.md`). ⚠ **NO documented
baseline here moves.** The tier RAISED before, so no cost table in the build notes ever charged an ECN spread, and
the `cost_tiers.py` row that quoted $0.12 as `stated` returns an identical 157 trades / +151.39R
now that it is `measured`. ⚠ **`0.0` and "unmeasured" must never
collapse**: 0.0 charges nothing on purpose, and the sentinel is NEGATIVE, so passing it through
would PAY the trader half a spread on every fill. 🔴 **The SWAP on those tiers refuses too, and that
assumption was checked rather than argued**: `XAUUSD.s` and `XAUUSD.crp` are the SAME market on ONE
PU Prime account (median M15 close difference $0.08 over 200 shared bars) carrying **swaps 8.5x
apart — long −79.60 vs −9.35 — with the short CREDIT gone entirely (+30.25 vs +0.04)**. This bot
trades both sides and its whole swap arithmetic rests on that credit nearly cancelling the long
charge, so borrowing another product's swap is not a small approximation. ⚠ **`swap=None` still
means "charge no swap" and stays silent** — only an UNREAD swap refuses. **Which tier to actually
trade is measured and
answered in `docs/BROKER_QUESTIONS.md` — a RAW tier, not Standard, because on this strategy the
spread costs ~20x what the commission does and it costs by killing FILLS** (8 setups of 159 never
fill at $0.32, 3 at $0.08; commission is 0.48R at $1.00/side and 1.67R at $3.50/side over 6.5
years). That is the same limit-order asymmetry the `bid_ask_fills` row in the build notes describes, read as a
decision rather than as a lab curiosity.

⚠ **A small charge is not a small effect.** 12.04R of cost turns $28.3M into $10.1M — **64% of the
final balance for 9% of the R** — because at a fixed % risk a dollar not earned early never
compounds. Always read a cost against the R, never against the net dollars.

⚠ **The last row is HIGHER than the free baseline, and that is not a bug — it is what a
limit-entry strategy does with a spread.** A flat spread charge is the market-order intuition (buy
the ask, sell the bid, lose the spread), and nothing here is a market order: every entry and exit
names a PRICE, so the spread changes WHEN an order fills rather than what it fills at. On a long
the buy limit fills at its own price and the stop sells at its own price — identical cash result,
the limit is simply harder to reach. The cost lands almost entirely on SHORTS, which sell the bid
to get in and buy the ask to get out, so their stops arrive a spread early and their targets a
spread late. On this book that traded 6 marginal entries away and, because there is one position
slot, let 4 different setups through in their place — the queue effect Run 12 already measured.
**So read the flat charge as a conservative UPPER BOUND and `bid_ask_fills` as the real question.**
⚠ It is also the newest and least-validated path here: it is unit-tested per order side and
measured once. Treat a `bid_ask_fills` result as a lab finding until it has been read on a chart.

⚠ **Drawdown got WORSE while profit fell — 57.2% → 60.1%.** A cost does not merely shave the top
off the equity curve, it deepens every losing stretch, so profit and risk move in opposite
directions and both readings are correct. This is the companion to the compounding warning above:
that one says a small charge costs a large fraction of the FINAL BALANCE; this one says it also
costs you drawdown, which is the number a risk budget is actually set against.

⚠ **Trade count cannot move** under spread / commission / swap — they change what a trade was
worth, never whether it happened. Only `bid_ask_fills` moves the trade list. A re-priced run
showing the same trade count as its source is working correctly.

### 🔴 THE RE-ENTRY SWITCH HAS FLIPPED THREE TIMES — ON 2026-08-07, OFF 2026-08-21, ON 2026-08-27

⚠ **It now ships ON, as the RECLAIM, banking all-out at 3.25x** (Aaron, 2026-08-27). What follows
is the 2026-08-21 record of turning it OFF, kept because the reasoning still stands and applies to
a different feature on the same switch: what was turned off then was the GAP re-entry, which had
never earned its place. The reclaim is measured separately — 44 re-entries, +32.50R over 2020-2026.
⚠ **Any figure in this repo quoted as "the shipped book" must name its DATE**, because this switch
has moved the defaults three times.

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *🔴 THE RE-ENTRY NOW SHIPS **OFF** (Aaron's call, 2026-08-21 — reverses 2026-08-07)*.

⚠ **This MOVES every historical figure in this repo that was produced on the defaults**, exactly as
turning it on did in August. A number quoted from before this date may be a 235-trade book. Check
which before comparing anything to it.

⚠ **The once-per-setup CAP stays ON, deliberately.** It only means anything while the re-entry is
enabled, and anyone who switches the re-entry on should get the capped rule with it rather than the
uncapped book by accident. Turning a feature off is not a reason to unpin the rule that governs it.

⚠ **It cannot move `compare_strategy.py`, and that was VERIFIED rather than argued.** The re-entry
needs a fill-clock stream through `run_dual` while the gate replays the export's own single frame, so no
re-entry has ever fired inside it — exit 0 at warmups 100 / 500 / 1000 on
`VANTAGE_XAUUSD, 15_bfe65.csv`, before and after the flip.

⚠ **A pull does NOT move the live bot.** It imports from its frozen `deployed/` snapshot, so this
default reaches an armed bot only through `promote.py`. Until then the live bot keeps whatever it
was promoted with.

### A SHRUNK entry paid its costs on the size it ASKED for (fixed 2026-08-21)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *A SHRUNK entry paid its costs on the size it ASKED for (fixed 2026-08-21)*.

🔴 **The symptom was not a wrong dollar figure — it was the R INVARIANT disagreeing.** R's
denominator followed the shrink and one piece of its numerator did not, so a shrunk trade's R came
back BELOW the same trade run solo. That invariant is the shared account's own test for *"a sizing
change stayed a sizing change"*, and leaving this in place made it cry wolf on every shared run.
⚠ **The tool offers two explanations for a moved R — the cap bit, or a decision changed — and this
was a THIRD it had no name for.** The refusal log showed ZERO refusals, which is what pointed at it.

⚠ **Nothing already recorded moves**, and that was checked rather than assumed: `compare_strategy.py`
is **exit 0 at warmups 100 / 200 / 500 / 1000** on `VANTAGE_XAUUSD, 15_bfe65.csv` (21,052 bars,
2025-10-01 →). ⚠ **That export ran Require-FVG ON, so the no-gap fallback branch was never entered
and the green says nothing about it** — the standing rule that a gate speaks only about code both
sides executed.

⚠ **It is the ONLY charge site that used the requested size.** The TP rungs, the exits and the
scale-in adds all bill against the real position; checked, not assumed.

### Wrong-side stop fills — a KNOWN BACKTEST LIMITATION, not a bug (recorded 2026-08-01)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *Wrong-side stop fills — a KNOWN BACKTEST LIMITATION, not a bug (recorded 2026-08-01)*.

**Deliberately NOT fixed: a "a stop may never be placed through the market" clamp.** It would have
caught the phantom-exit bug on day one, but applied now it would change real trade behaviour and
would have to land in all five Pine files too. That makes it its own change with its own
measurement, not a tidy-up. ⚠ It also matters for **live**: the bridge places the stop with the
broker, so a live fill will land nearer the stop than the backtest's. Expect live to beat the
backtest marginally on exactly these trades — and treat any BIGGER live/backtest gap as a real
problem, not as this.

## The 2026-07-26 exit-lever sync

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The 2026-07-26 exit-lever sync*.

⚠ **Not covered by this run:** it was taken before the minimum-stop guard was ported, at the `"Off"`

⚠ **NOT yet proven: the filter ON, against a real export.** Everything above is unit-tested and

✅ **MEASURED before it was written — two full replays, 186,366 M15 + 2,790,942 M1 bars, at the

🔴 **The honest size of the problem is ONE setup, and the first count of it was misread.** Over the

⚠ **So the case for this is CONSISTENCY, not the measurement.** The history contains no instance of

⚠ **The floor reads `self._atr`, which is the FIFTEEN-minute ATR(14)** — `_update_atr` runs in

✅ 5 new tests in `tests/test_secondary.py`, **3 watched RED** against the restored `dist > 0`. The

⚠ **The same pass found a test my own default flip had made vacuous the day before.**

## Every entry method OWNS its stop rule — the precedence list is gone (2026-08-27)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *Every entry method OWNS its stop rule — the precedence list is gone (2026-08-27)*.

🔴 **MEASURED with `stopwalk.py` on 2026-08-26.** Entry 100.00, stop 98.00, general rule arming at
1R and keeping half. At 2.25R in front the stop was 99.00; at 2.50R it went back out to 98.50.
**A protective stop that RETREATS on a winning trade** — the trade got better and its stop got
worse, putting 0.50 back at risk on a position that had already been made safe. It retreated at
every arm later than 1R (0.10 / 0.50 / 0.90 at keeps of 0.55 / 0.75 / 0.95).

⚠ **A second retreat existed one branch up and is closed in the same change**: a re-entry set to
hold its initial stop until the second target returned the FROZEN entry stop the moment the first
rung was touched — wider than whatever its own protection rule had already set.

⚠ **The rule is not switchable — its VALUE is.** `-1` does not mean "this method has no rule"; it
means "this method's rule is *never move the stop*". Switching an entry method on brings its exit
rules with it and they cannot be detached. That is the model, and it is why there is no "inherit
the shared one" value on any of the four.

✅ **PROVEN A NO-OP AT SHIPPED SETTINGS, trade by trade.** All four pairs ship at `-1` / `0.0`, so
nothing can arm. HEAD (`ecdbd9b1`) and this change were replayed on identical bars, window and
params (XAUUSD.p, 2020-01-01 → 2026-08-23, reclaim trigger, 3.25R target): **200 trades and
141.6497R on both, and zero trades differ.** Same 44 re-entries at 32.50R.

✅ **And proven to CHANGE the thing it was meant to change.** With the old collision switched on
(general 1.0R/keep 0.5, reclaim 2.5R/keep 0.75) the same replay differs on **12 trades**: eleven
reclaims that the primary's rule used to reach now take their own method's rule instead, and one
of them goes −0.5R → **+3.25R** because the borrowed stop had been knocking it out.

⚠ **`_rec_be_armed` is now written but never READ.** It is kept only so a live bot rolled BACK onto
the previous deployment can still restore this version's position record — `restore_position()`
refuses a record with a missing field, and `promote.py` refuses a version that cannot restore the
open position. It is set only on a reclaim, so the older code computes the same stop from it.

⚠ **An UNNAMED re-entry gets no stop movement, and that is a decision rather than a fallthrough.**
Reinstating the primary's pair for the one case the map does not cover would put the precedence
question straight back. It can only ever leave the frozen entry stop in place, never widen one that
has already moved. In production every armed re-entry carries a source (`secondary.py::_src_for`);
the unnamed case is duck-typed test stand-ins.

⚠ **The two new pairs have NEVER been MEASURED ON.** No replay has been run with either positive,
and this file's own numbers above are the reason to distrust the intuition: every protective
setting tested on the primary LOST money, at about three R destroyed per R rescued.

⚠ **Parity is unaffected while they ship off** — nothing can arm, so `compare_strategy.py` sees the
decisions it always did. The moment any of the four goes positive, Python and Pine are trading
different ladders: there is no TradingView side for any of them.

## Target levels and an R-priced first target — added 2026-09-20

- **Three settings, all off by default:** "Target 1 level", "Target 2 level" (pin a fib rung, or Auto for the shipped deep/shallow rule) and "First target, in R" (-1 = off).
- A pinned level behind the entry is not a target, so that trade keeps its Auto level. The strategy counts these fallbacks. ⚠ **The sweep does not surface that count,** so a pinned winner must be re-checked on a single run.
- **Defaults change nothing.** MEASURED 2026-09-21: the grid combo with every new setting at default matched run `ea46142df097` to the cent (244 trades, same net and drawdown).
- Ported to both Pine files and to the gate's input list. ⚠ **The parity gate has NOT run on these branches.** It needs a fresh TradingView export with the new inputs set, and nothing may reach a live bot before it runs.
- Results: `sos_fade_optimization.md` → Run 40.
- **The verdict, MEASURED 2026-09-21 and NOT adopted:** banking half the trade at target 1 and nothing at target 2 is the best of the 9 banking splits on return per drawdown in R — 33.6 (run `8b137a61fcae`, 191.4R over a 5.69R worst drawdown) against 31.8 for the shipped setting (run `ea46142df097`, 234.9R over 7.39R). It buys a quarter off the drawdown for a fifth of the return, which is what a smoother curve costs here. **The shipped default is unchanged** — the parity gate has not run on it. The top three splits sit within 0.4 of each other, so "bank some at target 1" is the finding and 50% exactly is not.

## The give-back guard — added 2026-09-22

**Why.** Aaron, 2026-09-22, after a demo trade on account 700152905 went from over $2,000 up to a
loss: *"this trailing SL is giving too much back"*. MEASURED on run `ea46142df097`: the book keeps
**41% of the profit its trades ever show** (533R of best case, 218R kept). The leak is NOT the
runner trail — trades that reach 5R keep 97% of their peak — it is the band BELOW the trail's
arming point, where nothing protects the trade at all.

**What it is.** Three settings, all off by default (`exec_giveback_arm_r = -1`):

- **arm at (R)** — how far in front the trade must have been, measured on its own high-water mark,
  before the guard starts watching. Priced off the FROZEN entry risk (`_entry` − `_init_stop`).
- **how much of the best it may hand back (%)** — 50 means fire once more than half the peak is gone.
- **what it does** — `Close`, `Hand to the trail` (straight to `_stage = 2`, the runner trail) or
  `Bank half` (sell half of what is still open at the next bar's open, then trail the rest).

⚠ **The two keep-it-open actions fire ONCE per trade (`_gave_back`), and the flag guards the ELIF
CHAIN, not just the action.** A branch that is taken and then does nothing still consumes the bar —
without the flag, a trade whose peak stays above the arming level would swallow the time stop on
every later bar for the rest of its life. `_giveback_has_work()` exists for that, and its test is
mutation-proved: make it return True unconditionally and the test goes red.

⚠ **`Bank half` takes every scale-in add in full**, because it is a market exit and `_exit_portion`
treats the adds the way a stop does. On a laddered trade "half" means half the BASE plus all the
adds. That is the Pine's own rule for a force-close, not a choice made here.

### MEASURED 2026-09-22 — the replays

Full book 2020-01-01 → 2026-09-20, `puprime_ecn` charged, 244 trades, scale-in on.
🔴 **Every row below was re-measured on the CURRENT working tree**, which carries another
session's uncommitted scale-in sizing fix. That fix alone takes the same shipped settings from
234.9R to **218.5R**, so no number here may be compared against a run stored before it.

| setting | total R | worst DD | return / DD |
|---|---|---|---|
| guard off (shipped) | 218.5 | 7.39 | **29.5** |
| arm 1.5R, half back, Close | 161.0 | 5.89 | 27.3 |
| arm 2R, half back, Close | 174.6 | 5.89 | 29.6 |
| arm 2.5R, half back, Close | 208.4 | 5.89 | 35.4 |
| arm 3R, half back, Close | 206.0 | 5.89 | 35.0 |
| arm 3.5R, half back, Close | 204.5 | 5.89 | 34.7 |
| arm 4R, half back, Close | 207.8 | **7.39** | 28.1 |
| arm 2R, half back, Bank half | 178.1 | 6.97 | 25.5 |
| arm 3R, half back, Bank half | 209.9 | 5.89 | 35.6 |
| arm 2.5R, half back, Hand to the trail | 216.7 | 5.89 | 36.8 |
| arm 3R, half back, Hand to the trail | 217.2 | 5.89 | **36.9** |
| arm 3.5R, half back, Hand to the trail | 217.2 | 5.89 | **36.9** |

**The finding: TIGHTEN, never CUT.** At the same arming level the three actions cut exactly the
same drawdown (7.39 → 5.89) and differ only in what they leave on the table — closing gives up
11.2R that tightening keeps. Whatever the guard is doing for the drawdown, it does not need the
trade to be flat to do it.

🔴 **THE ARMING LEVEL IS NOT A PEAK, IT IS A ONE-TRADE BRACKET, AND THAT IS THE REASON THIS
SHIPS OFF.** This line said "a narrow peak at 3R" until the neighbours were replayed; they disprove
it. The real shape is a cliff at BOTH ends with a flat floor between: return/DD is 29.6 at 2R,
then 34.7–35.4 right across 2.5R–3.5R (close) or 36.8–36.9 (tighten), then back to **28.1 at 4R
with the drawdown restored to the shipped 7.39R exactly**.

**The bracket is one trade's high-water mark.** MEASURED: the 2022-06-09 trade peaks at **3.84R**
and closes −0.23R shipped. Arm anywhere below 3.84R and the guard catches it (−0.23R → +1.52R) and
the 2022 drawdown stretch ends early; arm at 4R and it is never touched, so the drawdown is byte-for-byte
the shipped one. The "plateau" is therefore not evidence of robustness — it is the width of the gap
between that one trade's peak and the level below which the guard starts eating runners. A flat
region measured this way is what a single decisive trade looks like from the outside, and it would
move the moment that trade does.

Every protective rule ever measured on this strategy has behaved the same way (see the
partial-banking grid above, and Run 12 in the optimization file): protecting the 1–3R band costs
more upside than it saves, because that give-back is the PRICE of the runners rather than a leak
beside them. The tighten action is the only one that does not pay that price, and it buys nothing
except this one 2022 trade.

⚠ **AND THE WHOLE DRAWDOWN GAIN IS ONE STRETCH.** The shipped 7.39R worst drawdown runs
2022-01-24 → 2022-07-14; with the guard on it ends 2022-03-07 at 5.89R, a level the shipped run
also reaches. At the tighten setting **eight** trades out of 244 move at all, and the one that ends
the stretch early is 2022-06-09 going −0.23R → +1.52R. Read that as *the guard did not hurt*
rather than *the guard found 25%*.

⚠ **It barely moves the thing it was built for.** Capture of best-case profit goes 41.0% → 41.1%
(tighten) or 42.7% (close), and trades that reached 1R and still closed red go 26 → 24. The guard
is close to free at 3R; it is not an answer to the give-back itself.

⚠ **IT ADDS TWO FIELDS TO THE POSITION RECORD** (`_pending_bank`, `_gave_back`), so a bot
promoted onto this version while holding a trade cannot restore a record the previous version
wrote — `restore_position()` refuses an incomplete record by design. `algos/tools/migrate_position_record.py`
covers it without a change, because it reads every default off a freshly constructed deployed
strategy rather than a list typed into the tool.

⚠ **NOT PORTED TO PINE.** There is no TradingView side for any of the three settings, so the moment
the arm goes positive the two implementations are trading different ladders. Parity is unaffected
while it ships off.

## The reversal exit — Aaron's own definition, measured, and it LOSES (2026-09-23)

Aaron, 2026-09-22, after a demo trade that showed over $2,000 and closed red: *"I want to know how
can we confidently tell we are losing momentum, or hit a point of major reversal or the trade is
reversing as soon as possible so we can get out and bank our max profit .... this trailing SL is
giving too much back."* His definition of a reversal, given when asked what to measure: *"as simple
as shift of structure, right? Um, if we're getting a shift of structure and then break of structure
is coming back towards us on lower time frames, that tells me price is reversing"* — and explicitly
NOT on the trade's own chart: *"if we're looking at it on a 15 minute obviously by the time we look
at 15 minutes um, reversal that will be too late so you need to look at a five to one minute."*

**What was built.** `exec_rev_exit` ∈ {Off, Bank half, Tighten to the trail, Close}, armed by
`exec_rev_arm_r` (the R the trade's best must have reached). It fires on a shift of structure
against an open PRIMARY, printed on the FAST frame — the same 5-minute stream the re-entry fills
on, already stepped unconditionally by `DualClock.step_fast`, so no new engine and no new feed.
It prices at the next FAST bar's open, which is the one place a primary is touched off a fast bar.

**MEASURED 2026-09-23. Full replay, 2020-01-01 → 2026-09-20, `XAUUSD.p` M15, `puprime_ecn`
charged, 244 trades. `exec_scale_gate` and the give-back guard PINNED on every row** — the
scale-in gate's default moved while the first queue was in flight, which would have put the
baseline and the treatments on two different scale-in rules (rule 11).

| setting | trades | total R | worst DD | ret/DD | profit kept | trades changed | net on those |
|---|---|---|---|---|---|---|---|
| **off (baseline)** | 244 | **234.5** | **7.39** | **31.7** | **44.0%** | — | — |
| tighten, arm 2R | 243 | 227.0 | 7.39 | 30.7 | 43.6% | 3 | −0.40R |
| tighten, arm 1R | 243 | 222.5 | 7.39 | 30.1 | 43.1% | 6 | −4.90R |
| bank half, arm 2R | 243 | 215.1 | 7.98 | 27.0 | 41.3% | 19 | −12.32R |
| bank half, arm 1R | 243 | 210.1 | 7.98 | 26.3 | 40.7% | 21 | −17.34R |
| close, arm 2R | 243 | 210.5 | 8.35 | 25.2 | 41.7% | 19 | −16.91R |
| close, arm 1R | 243 | 206.1 | 8.35 | 24.7 | 41.3% | 21 | −21.30R |

- 🔴 **EVERY ROW LOSES, ON EVERY MEASURE, AND THE RULE IT WAS BUILT TO FIX GETS WORSE.** The whole
  point was to keep more of the profit a trade shows. Profit kept goes 44.0% DOWN to 40.7–43.6% on
  every single setting. This is not a tuning problem — a rule that reliably kept more profit would
  show it somewhere in this table, and none of them do.
- 🔴 **THE TWO CUTTING ACTIONS MAKE THE DRAWDOWN DEEPER, NOT SHALLOWER** (7.39R → 7.98R banking,
  → 8.35R closing). That is the opposite of the one thing an early exit is supposed to buy, and it
  rules out the usual defence that a lower return bought a smoother curve. It did not.
- 🔴 **THE NET ON EVERY TRADE IT TOUCHES IS NEGATIVE, at every arming level and every action.**
  Not "a few bad ones outweigh the good" — the sum over the changed trades is negative in all six
  rows. The signal is not identifying reversals that matter; it is cutting winners mid-move.
- **WHY, and it is the mechanism rather than a story.** A 5-minute shift of structure against the
  trade is what an ordinary pullback inside a winning swing looks like. It fires on roughly 21 of
  243 trades, and this book's winners are long holds (median hold: winners 17.8h, losers 2.0h), so
  almost every fire lands inside a move the trade was right about.
- ⚠ **TIGHTENING IS THE LEAST BAD, AND THAT IS NOT AN ENDORSEMENT.** At arm 2R it touches 3 trades
  for −0.40R. It is indistinguishable from doing nothing, which is the honest reading of a rule
  that has to be turned down to near-inert before it stops losing money.
- ✅ **IT AGREES WITH THE CHEAP RE-WALK, which is worth recording because the give-back guard did
  NOT.** `backtest/tools/exit_study.py` already had every engine-driven reversal exit losing to
  holding, including both definitions asked for by name. For the give-back cap the replay reversed
  that ranking; here it confirmed it. So the re-walk is not uniformly wrong — it is unreliable,
  and the only way to know which it was is to replay.

**It ships OFF, and off is the measured answer rather than caution.** ✅ **Parity GREEN with it in
the tree** — `tools/compare_strategy.py` on the committed golden (20,220 bars, warm-up 468): exit 0,
19,668 bars compared, Python == Pine on every one. It has no Pine counterpart, so a green gate says
only that switching it off changes nothing, which is exactly the claim being made.

⚠ **WHAT THIS DOES NOT SAY.** It does not say price action cannot time an exit. It says THIS
signal — a fast-frame structure shift against the trade — does not, on this book, at these two
arming levels, as a standalone rule. The level-rejection half of Aaron's definition (*"if we're
hitting that level over and over and over and we print a reversal pattern on there"*) is NOT
measured here: it needs `engines/liquidity/`, which this bot does not currently run, and the
re-walk had it firing on 117 of 129 trades, which is an early exit with a story rather than a
signal. That is the next thing to build if this line is pursued, and it starts from a worse prior
than this one did.

## The level-rejection trigger — the other half of the definition, measured, not adopted (2026-09-23)

Aaron asked for it by name on 2026-09-23 ("test 1 and 3"). **What was built:** a second answer to
"↳ What counts as a reversal" — "Level rejected". It watches only the major levels AHEAD of the
trade (weekly, daily and 4-hour highs and lows, already handed to this bot by the liquidity engine)
and fires when price reaches the same one and closes back off it on "↳ Rejections of the same
level before it acts" separate visits, on the 5-minute frame. Touching bars in a row count as one
visit; a close through the level ends its count. Support holding BEHIND the trade never counts —
that is the difference from the re-walk's screen, which fired on 117 of 129 trades. Unit tests:
`tests/test_reversal_levels.py`.

**MEASURED.** Same basis as the table above (run `ea46142df097`'s params, 2020-01-01 → 2026-09-20,
`puprime_ecn` charged, consistent sizing, 100-lot ceiling). Pinned on every row: scale gate "Stop
improved", give-back guard off, level memory off, no-entry window empty. The re-run of "off" on
today's code (`9fa0f5d9bcaf`) reproduces `e805a5d503a8` exactly.

| action | arm | visits | run | trades | total R | worst DD | R / DD | 2020–22 R | 2023–26 R |
|---|---|---|---|---|---|---|---|---|---|
| **off** | — | — | `e805a5d503a8` | 244 | **234.5** | 7.39 | 31.7 | 68.3 | 166.2 |
| tighten | 1R | 2 | `f291344a0cfb` | 243 | 233.6 | 5.89 | 39.7 | 71.8 | 161.8 |
| tighten | 2R | 2 | `c651c8140b4b` | 243 | 230.1 | 5.89 | 39.1 | 70.5 | 159.6 |
| tighten | 1R | 3 | `4735e6f4d317` | 243 | 229.2 | 7.39 | 31.0 | 69.1 | 160.1 |
| tighten | 1R | 1 | `043969a892ef` | 241 | 157.2 | 5.89 | 26.7 | 38.1 | 119.2 |
| bank half | 1R | 2 | `b23cae3f6ccf` | 243 | 181.6 | 5.89 | 30.8 | 57.2 | 124.4 |
| close | 1R | 2 | `0a8302fb7d3d` | 243 | 111.0 | 5.89 | 18.8 | 33.3 | 77.8 |
| close | 2R | 2 | `77db1c3bb749` | 243 | 117.3 | 5.89 | 19.9 | 34.4 | 82.9 |

- 🔴 **NO SETTING BEATS OFF ON TOTAL R.** Closing and banking half lose 53–123R: they fired 41 times
  and cut the long runners this book is paid by.
- 🔴 **THE BEST ROW'S DRAWDOWN CUT IS THE SAME ONE 2022 TRADE THE GIVE-BACK GUARD CAUGHT.** The
  2022-06-09 trade goes −0.23R → +1.74R and the worst drawdown falls 7.39R → 5.89R. With three
  visits it does not fire on that trade and the drawdown is back to 7.39R. One trade, not a
  property of the rule.
- 🔴 **EVERY TIGHTEN ROW LOSES THE SAME +7.05R TRADE.** Tightening the 2023-03-27 trade ends it
  days early, and the 2023-04-03 re-entry that paid +7.05R never happens. At 1R / 2 visits the
  other 16 changed trades are +6.18R, so the net is −0.9R: the sign rests on two trades.
- 🔴 **ONE VISIT IS AN EARLY EXIT, NOT A SIGNAL.** It cuts the 2020-06-18 trade from +28.9R to +2.5R
  and the 2025-10-21 trade from +24.9R to +0.9R: −77R.
- **Neighbours all fall away from the best row**, both halves of the history included, so there is
  no plateau to stand on.

**Verdict: not adopted.** "What counts as a reversal" stays on "Structure shift", and the reversal
exit stays Off. Both halves of Aaron's definition are now measured, and both lose to holding. The
honest reading is that on this book the trailing stop's give-back is the price of the long
runners, and every exit tried so far that trims give-back also trims them. Parity GREEN with it in
the tree (19,668 bars, warm-up 468); it has no Pine side.
