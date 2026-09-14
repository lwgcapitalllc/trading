# Notes — Re-entry ladder mechanics — dated fixes and measurements

The bar-time leg latch, `Trade.tp_rungs`, the dual-clock merge, the fill clock, the 1m structure engine's contribution, the worst-price bound, the short-hold variant, the ladder-order flip, the two re-entry halves, the reclaim banking level and give-back, and the minimum stop distance. Moved VERBATIM out of `strategies/python/sos_fade/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## 🔴 A BAR NUMBER IS LOCAL TO ONE RUN. THE ONE-TRADE-PER-LEG LATCH NOW KEYS ON TIME (2026-08-26)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *🔴 A BAR NUMBER IS LOCAL TO ONE RUN. THE ONE-TRADE-PER-LEG LATCH NOW KEYS ON TIME (2026-08-26)*.

🔴 **This repo had already written the lesson down, against a different consumer.** `shadow_diff`
joins on bar TIMESTAMP and its docstring says why in as many words: *"the live index counts on
from wherever warm-up stopped and survives restarts."* `strategies/CLAUDE.md` records the same
trap from the B-LEG harness, where 2,409 comparisons failed at one flat offset. **The live path
was still comparing numbers. A lesson recorded against one consumer is not a lesson applied to
the others — go and look at the others.**

✅ **`Execution._same_leg()` decides by TIME whenever both sides have one**, falling back to the
number only for a leg whose time was never seen. `_remember_bar()` keeps a bar-number → bar-time
map for the run, pruned to the recent 20,000 (a bot runs for weeks; an unbounded dict is a leak
with no upside). `_traded_sos_l_ms` / `_traded_sos_s_ms` are PERSISTED — without them a restart
restores a number from the previous numbering and the fix does nothing, which is the same bug one
layer down.

⚠ **The fallback is the OLD behaviour and is wrong across a restart.** It is kept because
refusing to answer would disable the latch outright, which is the same failure with fewer clues.

⚠ **It is a NO-OP in any single continuous run** — one backtest, one Pine chart, one uninterrupted
session — because within a run a number maps to exactly one time. The two answers can only differ
across a RESTART, which exists nowhere but live. **That is why parity is unaffected, and it was
RUN rather than reasoned**: `compare_strategy.py "VANTAGE_XAUUSD, 15_6fb2a.csv"` exit 0 at warmups
100 / 200 / 500 / 1000 / 2000 — the same five the pre-change code passes, and the known
pre-existing red below warmup 50 (bar 16, `px_s_stage`) is unchanged.

⚠ **Adding two fields to `_POSITION_FIELDS` means the next promote with a position OPEN will halt
on the restore** until the record is migrated. That is the designed refusal, and
`algos/tools/migrate_position_record.py` is the repair.

## `Trade.tp_rungs` — the closed record says how much each rung TAKES OFF (2026-08-21)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *`Trade.tp_rungs` — the closed record says how much each rung TAKES OFF (2026-08-21)*.

⚠ **The percentage is resolved for the trade that was actually OPEN, not read off the config.**
A re-entry may bank its own (`exec_sec_tp1_pct`, **0** by default since 2026-09-07) and the reclaim half a different
one again (`exec_rec_tp1_pct`, 100), so it goes through `_tp1_pct()` exactly as the live ladder
does. Reading `cfg.exec_tp1_pct` here would report a primary's percentage for every re-entry.

⚠ **REPORTING ONLY**, the same standing as `mfe_usd` / `tp1` / `tp2` / `fib` — nothing reads it
back, so no decision can move and `compare_strategy.py` diffs the same `px_*` stream.

🔴 **A re-entry's rungs are NOT in distance order, and that is worth knowing beyond the chart.**
Rung 1 is priced off risk (`exec_sec_tp_r`, 1.25R below a short's entry) while rung 2 stays the 15m
fib it was armed on, so **rung 2 can be the NEARER of the two — 23 of the 45 re-entries on run
`687c8df2a523`. The 160 main entries are all correctly ordered, and the Pine's own ladder
(0.5 then 0.382) is too — the flip is created by this Python-only risk-multiple override and
exists nowhere in `sos_fade_strategy.pine`.** ⚠ **A first count published as 182 of 205 was WRONG**
and made this look repo-wide; it measured *nearer* with the sign inverted (corrected
2026-08-21). Distance is measured FROM the entry in the FAVOURABLE direction — on a short the
nearer target is the HIGHER price — and a bare price comparison is backwards on one side.

🔴 **IT WAS FLIPPED, MEASURED, AND REVERTED. DO NOT FLIP IT — IT COSTS MONEY, AND THE READING THAT
SAYS OTHERWISE IS THE INTUITIVE ONE.** MEASURED 2026-08-21 via `run_report`, XAUUSD M15
2018-09-14 → 2026-08-20, matched basis, only the stage ordering differing:

**−4.43R over 7.9 years, and nine winners became scratches.** ⚠ **The reason is that a TRAIL is
STRONGER protection than breakeven, not weaker.** On a flipped trade the first rung price reaches
already arms the trail, which is better than arming plain breakeven — so the "fix" REPLACES the
trail with breakeven at the near price and DELAYS the trail to the far one. Trades that were
banking 0.8–1.2R came off at 0.02–0.06R instead.

⚠ **"It skips the breakeven step" therefore describes something GOOD, and reading it as a defect
is what motivated the flip.** The naming is what is backwards, not the behaviour: the step called
"1" waits on the far price and the step called "2" on the near one, so the bot reaches the better
one first. Aaron's call, 2026-08-21: leave it.

✅ **The question the reordering was mistaken for — arming breakeven EARLIER THAN EITHER RUNG —
has now been MEASURED, and the answer is DON'T (2026-08-25).** `exec_be_arm_r` /
`exec_be_keep_r` generalise the reclaim's arm to every trade: the stop moves once price has gone a
multiple of the trade's own entry risk its way, with no rung touched. Both ship **OFF** and the
`warn` on each says why.

🔴 **Every setting tested LOST money, and the decomposition is the rule, not the totals.** Over
6.6 years on 246 trades (control `32f82feae4ee`, 139.09R): **99.92R** at 1.00R→breakeven,
**71.20R** at 0.75R, **51.55R** at 0.50R; keeping half the risk instead is the least bad and still
loses — **118.99R** at 1.00R, **108.12R** at 0.75R. At 1.00R→breakeven it rescued 17 trades worth
**+17.07R** and destroyed 15 worth **−54.49R**, one of them a **+16.48R** winner cut to +0.35R.

🔴 **The give-back and the outsized winners are the SAME EVENT** — this book is carried by trades
that run, pull back hard THROUGH the entry, and only then go, so any rule that refuses to sit
through the pullback kills those trades first, at about three R destroyed per R rescued.

⚠ **A rising win rate is NOT evidence here**: it went 58.1% → 68.7% at the earliest arm while the
money fell by two thirds. ⚠ **Protection did not reliably buy drawdown either** — keeping half the
risk at 0.75R made the worst drawdown WORSE (60.21% against 53.68%).

⚠ **The defect it was built for is real and is still open**: the stop's ONLY trigger is a rung
TOUCH, so a trade can run a full R in profit and have nothing happen. The 2020-11-04 re-entry did
exactly that (best price 1.016R, nearest rung 1.25R, full loss) and survived in the shipped
configuration only because the flipped ladder put a rung at 0.757R. **A ladder defect was
load-bearing for a stop with no other trigger.**

## 🔴 THE MERGE MOVED OUT OF `run_dual` INTO `dual_clock.DualClock` (2026-09-01)

Story, the five defects it cost and the proof: `docs/LIVE_TRADING_PIPELINE.md` → G18.

🔴 **THERE IS ONE IMPLEMENTATION OF *WHICH BAR IS STEPPED WHEN*, AND BOTH DRIVERS USE IT.**
`run_dual` is now the LAB driver of `DualClock`; the live runner is the other one. The merge order
is the part that is easy to get wrong and impossible to see afterwards — a fast bar stepped
against the wrong 15m context produces an ordinary-looking trade at a slightly wrong price, for
ever, and nothing in any output can show it. **A second copy in `algos/live/` is the shape this
repo has already met twice** (the run-form visibility evaluator against `param_is_reachable`; the
ruff carve-out living in somebody's memory of what they had reverted).

✅ **THE REFACTOR IS A PROVEN NO-OP.** Same window, same params, reclaim trigger:
**188 trades / +125.0949R before and after, 0 rows differing.** ⚠ **The FIRST version of that
check was partly vacuous and is recorded rather than quietly replaced** — it read three of its
nine fields with `getattr(t, name, default)` under names `Trade` does not have (`entry`, `exit`,
`entry_src`), so those three compared nothing to nothing. The field list is DERIVED from the
dataclass now. **This repo already records that failure** (`entry_time` against a record whose
field is `entry_ms`), and it recurred inside the tool written to check a live-path change.

⚠ **`algos/live/` may not know what a re-entry is**, so the live driver asks this strategy two
questions and does as it is told: `fast_feed_minutes()` (does this configuration want a second
stream, and how fast — `None` means *no*, never *cannot have one*) and `make_dual_clock()`. A
strategy implementing neither has one feed, which is every other bot here.

⚠ **`warm_fast_bar` deliberately does NOT arm, price or fill anything.** The primary's warm-up
already replays through the shared emulator and can leave a warm-up position behind; running the
re-entry over the same history would open a second imaginary trade in the ONE position slot and
change what the primary's warm-up saw. What the fast side needs out of history is its own
structure state, and that is all it builds.

⚠ **`reset_fast` throws the arm state machine away with the structure feed.** Its latched legs are
keyed on fast bar NUMBERS, and a rebuilt feed renumbers them — keeping it would leave latches
pointing at bars that no longer exist.

🔴 **A FAST BAR THAT ARRIVES AFTER THE 15m CONTEXT HAS PASSED IT RAISES, AND MUST GO ON RAISING.**
There is no honest way to step it, and absorbing it silently would let a re-entry arm on
information the market had not published. The lab can never trigger it (it pushes every primary
before it steps a fast bar); live it is the late-arrival case and the caller re-warms the fast
side alone.

⚠ **NOTHING ABOUT THE STRATEGY MOVED, AND THE PARITY GATE STILL CANNOT SEE ANY OF IT.**
`compare_strategy.py` replays 15m bars through `.run()`; every re-entry lever lives on the
fill-clock path. **The `run_dual` replay is the only evidence this feature will ever have — call
every number it produces a lab finding, never a parity pass.**

## The re-entry rests its order and LEAVES it — and what the 1m feed is actually for (2026-08-21)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The re-entry rests its order and LEAVES it — and what the 1m feed is actually for (2026-08-21)*.

🔴 **THE RE-DECIDING WAS WORTH 0.02R OVER 7.9 YEARS, AND IT WAS THE ONLY REASON THE ORDER HAD TO BE
RE-ASKED EVERY MINUTE.** MEASURED, matched basis, the only difference in each pair being the switch:

⚠ **The ~11R between the two ROWS is a DIFFERENT thing and is not this switch.** It is fill
PRECISION — a 15m bar fills a resting limit at a worse price than the minute price actually traded
at. **That is a measurement-accuracy question, not a strategy one: live, the broker fills the order
at the price that trades and there is no 15-minute anything.** Read the 15m row as a pessimistic
simulation of the same live behaviour, never as a different rule.

✅ **5 MINUTES IS THE PLACE TO BACKTEST.** Same window, same config, only the fill clock:

⚠ **It freezes the PRICES, not just the armed flag.** The fibs keep extending, so a re-read edge
would slide a still-resting order to a level it was never placed at and the trade's record would
name a price that was never live.

🔴 **THE SNAPSHOT IS CLEARED WHERE A LEG RETIRES (`mark_traded` / `mark_dead`), NOT BY THE READER.**
The first version tried to infer both inside `_rested` by comparing the 15m SOS bar against
`_l_traded` — and those are different keys, because `_traded` holds the LEG id, which under the 1m
trigger is a 1-minute SOS bar and never equals the 15m one. It left a filled order resting and let
a second re-entry straight through the one-per-setup cap. **Three existing tests caught it, which
is the whole argument for a cap having its own tests rather than being 'obviously' enforced.**

⚠ **NOT byte-identical to the old path** — 2 re-entries move and 1 is lost over 7.9 years, so a
stored figure from before this date reproduces only with the switch set False.

## The re-entry's FILL CLOCK is 5 minutes, and it is an accuracy knob (2026-08-21)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The re-entry's FILL CLOCK is 5 minutes, and it is an accuracy knob (2026-08-21)*.

🔴 **IT IS A MEASUREMENT-ACCURACY KNOB, NOT A STRATEGY ONE.** Live, the broker fills a resting
limit at the price that trades — there is no 15-minute anything. A coarser feed fills the order at
a worse price than really traded, so it UNDERSTATES, which is the safe direction. **Never read the
5m default as "the strategy trades on 5m"**: the setup, the entry price and the stop are all 15m.

⚠ **A finer feed also bounds the WINDOW by its own measured history floor**, so 1m is not free
even on a machine that can afford the bars — it costs a day here, and more on a symbol whose 1m
history is shallower.

⚠ **A strategy that does not declare one keeps the old 1m behaviour.** `run_report` reads
`getattr(cfg, "exec_sec_fill_tf_min", 1)` — absent means "this fork has not been measured", not
"coarsen it".

## What the 1-minute STRUCTURE engine contributes at the shipped trigger (2026-08-21)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *What the 1-minute STRUCTURE engine contributes at the shipped trigger (2026-08-21)*.

⚠ **It is NOT inert, and the difference matters.** Its SOS latch still writes `_l_leg` / `_s_leg`,
which is the key `_traded` / `_dead` / `_used` read — so it can still move which setup counts as
already-used. `secondary.py` records a control replay where keying the price rule off the latch
instead of the trigger priced a gap book at a 1-minute retrace, +4 re-entries and +4.9R.

⚠ **Read from the CODE, not from a replay.** Nobody has run the book with the 1m structure engine
suppressed, so "it contributes nothing but bookkeeping" is a reading of the source and not a
measurement. Say which it is before quoting it.

⚠ **Aaron's description of the shipped rule is the right one and the module's own docstring is
stale**: it opens *"1m sniper re-entry … a 1m shift of structure rests a tight limit at a 38.2%
retrace of that 1m leg"*, which describes `"1m shift"` — a trigger that is no longer the default.
The shipped rule is: the first trade reaches breakeven, price comes back into the zone, a fair
value gap is there, and the entry follows the PRIMARY's model around that gap.

## 🔴 The worst price a trade reports is bounded by its STOP — `_widen_hold` (2026-08-22)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *🔴 The worst price a trade reports is bounded by its STOP — `_widen_hold` (2026-08-22)*.

⚠ **It is not an intrabar-ordering guess.** The stop is triggered BY the adverse move, so any
price past the stop necessarily came at or after the fill. Determinate, which is what makes this
fixable at all.

⚠ **The remaining 4 are the ENTRY BAR and are correct.** The stop is not managed until the next
bar — the one-bar order delay every fill model here is built on — so a first-bar excursion past the
stop is real exposure the trade genuinely sat through. Bounding it would report a better worst
price than the trade actually had, which is a lie in the flattering direction.

⚠ **A bar that OPENS past the stop is bounded by the OPEN, not the stop**, because that is where
the stop fills (`_fill_price`) and that fill is real.

⚠ **The FAVOURABLE side is deliberately untouched.** A target is partial — TP1 banks a portion and
the runner stays open — so price past a target is still the trade's move. Only the stop closes
everything.

⚠ **Reporting only, and proven rather than argued.** No decision reads the excursion, so parity
could not move; the gate was run anyway, on three exports, because that is the rule.

## The SHORT-HOLD variant — `exec_short_hold` (2026-08-24, ships OFF)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The SHORT-HOLD variant — `exec_short_hold` (2026-08-24, ships OFF)*.

🔴 **IT IS A SWITCH TO EXPERIMENT WITH, NOT A LEG TO DEPLOY, and the numbers are why.** On the
pool it was built for (order blocks where no gap qualified), matched basis, ECN costs:

**It does exactly what it was designed to do and still earns less.** The scratch problem it was
built to fix is fixed — 33 → 1 — and the drawdown improves; the total halves, because capping a
trade at 2R throws away the tail that was carrying the pool. ⚠ It is also still negative in 2020,
2024 and 2026, the same decay the pool has without it.

🔴 **THE DEPTH CAP SHIPS INERT BECAUSE IT MEASURED NEGATIVE, AND THAT REVERSED THE
RECOMMENDATION THE FIELD WAS BUILT ON.** Entry depth was the strongest split found anywhere in
this work and it replicated three independent ways, including in this bot's own shipped book. Then
it was applied: capping at 0.702 removed 5 trades, 2.1R and made the drawdown slightly worse.
**The split was measured under the fib ladder and the cap was applied under a fixed R target** —
a deep entry has a short stop and the breakeven ratchet takes it out, which stops mattering once
the trade closes at 2R. ⚠ **A finding is scoped to the exit regime it was measured in; carrying
it across an exit change is a new claim and needs its own run.** Nothing was wrong when it was
measured, it was generalised one step too far.

⚠ **Two new BLOCK codes (8, 9) have no Pine counterpart.** `f_blkCode` stops at 7. They are
appended so every existing code keeps its number, they can only fire with the toggle on, and
`BlockedSetup` is reporting-only — which is what makes a new code parity-safe rather than merely
convenient.

⚠ **The variant's hour window is its OWN gate, deliberately not more hours folded into the
final-hour rule.** That rule's label is rendered by the block marker and the Telegram callout as
*"no new entries 16:00-18:00 New York"*, and widening it would leave both of them saying 16:00
about a setup refused at 10:00.

✅ **THE PINE PARITY GATE HAS RUN AND IS GREEN (2026-08-24).** `compare_strategy.py` on
`VANTAGE_XAUUSD, 15_80a5f.csv` — 21,162 bars, 2025-10-01 → 2026-08-24, shipped config
(`cfg_bits` 544375) — **exit 0 at warmups 100 / 500 / 1000 / 2000.** Rule 22 is satisfied for
this change: the Python makes the identical decision to the Pine on every bar.

⚠ **Read what that green run covers, and what it cannot.** It proves parity of the SHIPPED path,
which is the claim that matters here — the variant is off, so the Pine and the Python are running
the same strategy and agree bar for bar. It says nothing about the variant itself, and **no export
ever can**: the Pine has no counterpart to these three rules, so there is nothing on the other side
to diff against. That is a stronger version of the gate's own standing warning about the no-gap
arm gate, which this run also reported as un-exercised. **A green gate is evidence about the
branch it entered and about no other.**

⚠ **Without `--warmup` the gate reports a mismatch at bar 16** (`px_s_stage` py=1 pine=0). That is
engine cold-start and is already recorded further down this file — it is not this change, and it
reproduces on HEAD.

⚠ **All six settings carry a label and a description in `sos_fade.meta.json`**, which is what
puts them on the Command Center's parameter form — a toggle nobody can find is not a toggle. That
file is a CONTRACT the lab reads, not data, and a backend test refuses any tunable parameter with
no description, which is what caught them missing. ⚠ **Position in its `params` array is the order
the form renders in, so APPEND — never re-sort.** Sorting it once here silently reordered all 93
existing settings, and the diff was 1,671 lines that should have been 73.

## 🔴 THE RE-ENTRY LADDER COMES OUT BACKWARDS ON ONE HALF, AND THE FLIP IS PROTECTIVE (2026-08-25)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *🔴 THE RE-ENTRY LADDER COMES OUT BACKWARDS ON ONE HALF, AND THE FLIP IS PROTECTIVE (2026-08-25)*.

🔴 **THE FLIP IS NOT A BEHAVIOUR BUG. IT IS A LABELLING ONE, AND "FIXING" IT COSTS REAL MONEY.**
`_stage_rungs()` already sorts the stop ladder by DISTANCE, so on a flipped trade the nearer rung —
the fib, labelled `TP2` — is what arms BREAKEVEN, and the further one still banks
`exec_sec_tp1_pct`. That is a good ladder: protect early, bank later. Push the second rung away and
you delete the early breakeven trigger. **MEASURED on the re-entry short of 2020-11-04** (entry
1902.97, stop 1912.55354, TP1 1890.99058, TP2 1895.72498, best price 1893.23): price cleared TP2 and
never reached TP1, the stop staged to 1899.61576 and took it for **+0.348R**. With the second rung
floored at 1.5× it moved to 1885.00086, nothing was touched, the stop never staged, and the same
trade ran back to 1912.55354 for **−0.907R**.

⚠ **So `exec_sec_tp2_min_x` exists, is MEASURED, and ships OFF.** Four floors were swept against a
matched control on the basis above. Total R 139.09 (off) / 140.64 / 140.29 / 139.79 / 137.10 at
1.5× / 2× / 2.5× / 3×; the re-entry leg alone improves at every floor and the improvement survives
removing its single best trade. ⚠ **Read none of that as an edge: only 13 of 246 trades changed and
they swung about ±1R each** — the +1.55R is thirteen coin flips. The one durable read is drawdown,
53.68% → 49.02% at 1.5×. ⚠ **3× is not a clean comparison at all** — it drops the book to 237
trades, so it changed which setups were TAKEN.

⚠ **If the naming is to be fixed, sort the LABELS and leave both prices alone.** Everything the
stop ladder does is already distance-ordered; only the chip is out of order.

### The second rung as a CHOSEN distance, not leftover geometry (2026-08-25)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The second rung as a CHOSEN distance, not leftover geometry (2026-08-25)*.

✅ **`exec_sec_tp2_x` REPLACES it with a chosen multiple of the first rung, so the two are ordered
by construction.** ⚠ **It is not the floor above renamed — the difference is DIRECTION.** A floor
lets a distant fib stand and can only push a rung away; this overrides both ways, so it also pulls
IN the rung that ran to 3.66×. Applied BEFORE the floor, so with both on they compose.

⚠ **SHIPS OFF, and the standing rules from its sweep are these three.** ① **The money is noise and
the drawdown is not** — best arm (1.25×) is 142.87R against 139.09R, which is 15 trades swinging ±1R
each, while max drawdown fell at EVERY arm monotonically as the multiple tightened, 53.68% → 47.95%.
Treat it as a drawdown lever, never as a way to make more money. ② **Any arm at 3× or beyond is a
DIFFERENT BOOK, not a comparison** — a re-entry then holds long enough to block the setups behind it
and the trade count drops to 237 and 235; with one position slot an extra hold does not add to the
book, it queues in front of it. ③ 🔴 **Ordering the ladder DELETES the only breakeven trigger some
re-entries have.** 2020-11-04 goes +0.348R → −0.907R at every setting tested, with 2021-02-11 and
2020-12-28 doing the same. **Ordering the targets and protecting those trades are opposing goals**,
and the cheap way to have both is still the one named above: sort the chart LABELS, leave the prices
alone.

🔴 **ONE SWEEP ARM SILENTLY REPLAYED STALE CODE.** The 2.5× arm ran 170s, stored its parameter, and
produced a ladder byte-identical to the control; an identical re-request came out correct. The lab
purges cached strategy modules under one namespace only, and `b_leg` imports this package's
files under their BARE names, which are never purged. **Verify a swept parameter by reading the
stored TRADES, never the KPI row** — the KPI row of a stale replay looks entirely normal.

## 🔴 THE TWO RE-ENTRY HALVES ARE TWO FEATURES, AND ONLY ONE OF THEM EARNS (2026-08-23)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *🔴 THE TWO RE-ENTRY HALVES ARE TWO FEATURES, AND ONLY ONE OF THEM EARNS (2026-08-23)*.

✅ **THE THREE ARE EXACTLY ADDITIVE, AND THAT IS THE STRUCTURAL FINDING.** 139.71 + 30.00 =
169.71; + 8.19 = 177.89. The 159 SOS Fade trades are **identical in all three** — same entry times,
same fills, same R, checked trade by trade. **Neither half displaces an SOS Fade setup or interferes
with the other**, so each is a genuinely independent switch. ⚠ That is a fact about THIS config,
not a property of the design — one position slot means displacement is always possible. **Re-run
the three-way before trusting it after any entry-logic change.**

🔴 **The gap half is one trade away from losing money over six and a half years.** 44 trades,
+8.19R, average +0.186R — and **dropping its single best result leaves −1.92R over 43 trades.**
Its own worst run of losses is **−7.75R, deeper than the whole strategy's −6.41R.** The reclaim
half is the opposite shape: 46 trades, +30.00R, a clean binary of −1R or +3R (19 wins, 27
losses), carried by no single trade.

⚠ **"Adds R" was never the question.** Both halves add R. The gap half adds 8.19R of which none
is repeatable, for 44 extra trades and 0.28R of extra drawdown. **Split a multi-trigger feature
into its triggers and drop the best trade from each — a leg carried by one outlier is a finding,
not a strategy.**

⚠ **It did NOT smooth the drawdown, and the account-drop column is why that reads backwards.**
The worst stretch (2022-01-26 → 2022-11-14) has SOS Fade down 4.13R and the re-entries down another
1.68R on top, with **five occasions where the re-entry lost immediately after the SOS Fade it followed
lost.** In bad conditions the two are ONE position at 1.5× the size — 10% plus 5% on the same
failing setup. The account drop improves 45.6% → 43.3% only because the extra profit compounds
the balance; that is sequencing, never safety. **Read the R drawdown, which got 0.8R worse.**

⚠ **Sample-size caveat, and it cuts against over-reading this too:** 44 trades is thin. The
honest verdict on the gap half is *"it has not shown an edge over this window"*, never *"it does
not work"*.

## Where the reclaim banks: 3.0R → 3.25R, and the 0.25R that costs nothing (2026-08-27)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *Where the reclaim banks: 3.0R → 3.25R, and the 0.25R that costs nothing (2026-08-27)*.

✅ **The move from 3.00R to 3.25R changed NO trade's outcome.** Same 18 winners, same 29 losers —
every winner that reached 3.00R also reached 3.25R and simply carried 0.25R further. **The +4.50R
is not bought from anywhere**, which is what separates this from a tuning nudge that traded one
population of trades for another.

⚠ **THE TARGET TABLE (NOW IN THE BUILD NOTES) WAS MEASURED ON A FROZEN CHECKOUT AND TODAY'S TREE GIVES A DIFFERENT BOOK.**
Work landed on this strategy between the sweep and the default change, and on current code the
same window gives **44 reclaims, not 47**. Do not expect to reproduce 29.50R by replaying today —
quote the table as what it is, a ranking measured on one pinned checkout.

✅ **RE-CONFIRMED ON CURRENT CODE (2026-08-27), with the target resolved from the SETTING rather
than pinned in the run's params:** 3.00R gives 44 reclaims / **28.00R** / 18 winners, and 3.25R
gives 44 reclaims / **32.50R** / 18 winners. **The same 44 trades, the same 18 winners, and zero
outcomes flipped** — 18 × 0.25R = exactly the +4.50R observed. Different absolute numbers, same
structure, same conclusion.

🔴 **THE FIRST ATTEMPT AT THAT CHECK WAS VACUOUS AND PASSED ANYWAY, WHICH IS THE LESSON WORTH
KEEPING.** It replayed a params file that PINNED the target, so both sides read the pinned value
and the default under test was never consulted. Both runs came back byte-identical, and identical
is exactly what a working no-op looks like — **the check could not tell "took effect" from "was
overridden".** To test a DEFAULT, the key has to be ABSENT from the params, not set to the value
you are hoping for. This is the same shape as the lab's basis trap: a request-time value that
overwrites the thing you meant to measure.

🔴 **3.50R ties it at 29.50R and was NOT chosen.** It has one fewer winner, and it sits one 0.25R
step from a cliff where four winners vanish and the leg halves. 3.25R keeps twice that margin for
identical money. ⚠ **The cliff rests on four trades, so its exact position is soft — that it
exists is not**: 3.75R and 4.00R are both down there.

⚠ **This is the OTHER half of the same question the de-risking grid answered**, and the two
answers point the same way: this leg is carried by trades that run, so anything that shortens
them — a nearer target, a tightened stop — costs more than it saves. See *Every entry method owns
its stop rule* above for the stop half.

⚠ **SUPERSEDED THE SAME DAY.** When this was written the re-entry still shipped OFF and only the
default target had moved. Later on 2026-08-27 Aaron turned the re-entry ON as the reclaim, so this
target IS now what the shipped configuration trades — and it is also what the live bot runs.
🔴 **The live bot PINS the old 3.0 in its own instance config** — `algos/markets/fx/instances/
sos_fade_demo/config.json` — so it will NOT pick this up. It is inert there today because
that bot's re-entry fires off the gap, but the moment anyone switches the reclaim on live, the
pinned 3.0 silently wins over this default. **Change it there too, or the measurement never
reaches the bot.**

⚠ **Every losing reclaim in all nine runs came back at exactly −1.0R** (one exception at 4.00R).
The leg is binary, which is what lets each row's total be reconciled from its win count alone —
all nine do, to the cent. That is an independent check on the table rather than a restatement of
it.

## 🔴 THE RECLAIM'S GIVE-BACK — FIVE FIXES REPLAYED, FOUR LOSE, AND THE EXCHANGE RATE SAYS WHY (2026-08-24)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *🔴 THE RECLAIM'S GIVE-BACK — FIVE FIXES REPLAYED, FOUR LOSE, AND THE EXCHANGE RATE SAYS WHY (2026-08-24)*.

🔴 **THE RULE, AND IT GENERALISES TO ANY ALL-OR-NOTHING LEG: WORK OUT THE EXCHANGE RATE BEFORE
BUILDING THE FIX.** A winner here pays 3R and a loser pays 1R, so protecting a loser saves at most
1R while knocking out one winner costs 3R plus what it then loses. **Nothing that touches the stop
or the entry clears one winner per three-to-four saves.** Four separate ideas were built, tested
and replayed before that arithmetic was written down; it would have predicted all four.

⚠ **A WORSE ENTRY IS A WIDER STOP AND A TARGET FURTHER AWAY IN PRICE, because the stop does not
move with it.** Market entry got 2025-08-19 in **12h45m earlier** — exactly what was asked for —
and the risk went **$3.98 → $12.51** with the target moving **3339.42 → 3373.55**. Price topped at
3345.25: **in the move ten hours before the high, and further from the target than before.** The
reclaim's edge IS its tight geometry, so paying up for the entry removes the thing being traded.

⚠ **The one that pays does so by REMOVING trades, not by trading them better.** 8 orders in 6.6
years waited over 12 hours to fill and every one lost; cancelling them is **pure subtraction, with
ZERO new trades appearing in any run** — the freed position slot never let anything in, so there
is no displacement term and the 8.00R is exact. ⚠ **Every cutoff of 6 hours or less LOSES**: the
6–12h band is the best in the whole re-entry book (4 wins from 5). Cutting early is the opposite
trade, not a milder one. ⚠ **It rests on 8 trades** — roughly a 1-in-250 fluke if the pattern is
not real — and is worth ~1.5R a year.

⚠ **A SMALLER LOSING TICKET IS NOT A SAFER ACCOUNT, and this run is the proof.** Account drawdown
is **43.34% in six of the seven** stop-protection runs, i.e. unchanged, because the drawdown is
driven by the SOS Fade book. Halving the re-entry loss moves the number on the ticket and nothing else.

**Three settings landed, all defaulting to the shipped behaviour and all OFF:** the protected-stop
trigger, how far that stop moves, and the resting-order cancel. **Only the cancel is recommended,
at 144 fill-clock bars = 12 hours.** ⚠ **Risk percent was ruled out early — it is a SIZE dial**, so
it changes dollars and account drawdown, never R and never which trades happen.

⚠ **This is the one question that could NOT be answered from stored runs**: a run records when an
order FILLED and never when it was PLACED. Reconstructing the wait by pairing each secondary with
the preceding primary matched on only 32 of 90 exit prices and was discarded before it was quoted.
**Re-run the sweep rather than mining a stored run for it.**

## 🔴 The minimum stop distance permits a stop a normal gap can double (2026-08-23)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *🔴 The minimum stop distance permits a stop a normal gap can double (2026-08-23)*.

⚠ **That is the documented one-bar order delay doing exactly what it is supposed to do** — see
*Wrong-side stop fills* — and it is the SAFE direction for a backtest. **The finding is not the
fill, it is the floor that let the stop be that tight.** The run's minimum stop distance was
0.08% of price; the stop cleared it by six thousandths of a percent, and one ordinary gold gap
then cost twice the risk the position was sized for.

⚠ **Sizing is computed off the stop distance, so a tighter stop buys a BIGGER position.** The
floor is the only thing standing between a near-zero stop distance and an enormous one, and a
floor set just under what the market gaps in a bar is a floor that is not doing its job. ⚠ **One
trade in 249 is not a reason to move it** — it is a reason to measure the floor against the
instrument's typical bar gap rather than picking a round number.
