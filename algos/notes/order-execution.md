# Notes — Order execution — the bridge's entries, exits, banking and market orders

Dated build stories and incidents for how the live bridge places, banks, closes and resizes orders: exec_scale_in refusal, close-on-demand, banking part of a position, partial_close clamping, the second bar feed, plus the lifted broker-call/resize/exit/market-order/pending-order stories from Shared MT5 Architecture and the exec_sl_deep story from the preamble. Moved VERBATIM out of `algos/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

### `exec_sl_deep` ON (2026-08-15) — two rules, both live-path

🔴 **It COSTS 23R and is WORSE at matched drawdown — it is a deliberate trade of return for a
smaller ride, never an improvement.** +140.0R → **+117.0R**, max DD 5.61R → **4.73R** (45.6% →
41.1% at `exec_risk_pct` 10); re-levered to equal drawdown it returns 3,830x against 4,868x.
**Stated here because a reader meeting +117.0R against a +140.0R history otherwise reads a
regression.** Aaron's call, evidence and every warning in the `_exec_sl_deep` block of
`markets/fx/instances/sos_fade_demo/config.json`; the measurement is in
`docs/ALGOS_BUILD_NOTES.md` → *Which stop-outs a wider stop rescues*.

🔴 **A param change to a NON-reloadable field is REFUSED by the running bot, with a Telegram
message, and that refusal is the guard working.** `RUNTIME_RELOADABLE` is `{"exec_risk_pct"}`
alone, so the VPS `git pull` leaves this on disk and **the bot keeps trading the old rule until it
is RESTARTED.** ⚠ A param change needs **no `promote.py`** — the frozen snapshot covers code, and
the source-hash pin is re-checked on the restart regardless. `b_leg_demo` is registered and **BENCHED** (`account: null`) pending a fresh `compare_bleg.py` parity run at its moved defaults. **`extreme_leg_demo` is registered and BENCHED too since 2026-09-03** — it satisfies the live contract and loads, and what is left is an ORDERING step rather than a build: the sibling drops to 5% before this one is assigned, never after. ⚠ **Its frame is M5 and on M15 it runs, logs cleanly and never fires.** ⚠ **Count the bots with `ls algos/markets/fx/instances`, never from this line.** The four first-attempt bots were deleted 2026-06-22 to rebuild backtest-first; the pipeline that got the first Python strategy live is `docs/LIVE_TRADING_PIPELINE.md`.







This file is auto-loaded by Claude Code at the start of every session. Read it fully before touching any code.

---


**Last reviewed:** 2026-08-12 - the dated build narrative that used to sit here moved VERBATIM to `algos/docs/ALGOS_BUILD_NOTES.md`. **Nothing was deleted.** It was 91,060 bytes in 7 paragraph(s), the largest 36,137 bytes on a single line, loaded in full every time anyone opened this area. Rules stay here; the evidence is one file away.

## 🔴 The bridge REFUSES `exec_scale_in` (2026-08-17)

`assert_supported()` gained a fourth refusal. **`OrderBridge` mirrors ONE entry limit and one
ratcheting stop — it has no path that places a second entry**, and `exec_scale_in` adds size to a
winning position. Left unrefused the bot would have traded the base position, placed no adds, and
reported nothing: the backtest would show a scaled book and the account an unscaled one, with
nothing explaining the gap. That is the exact divergence this function exists to prevent.
⚠ **This paragraph cited partial take-profits and the re-entry as fellow refusals until
2026-09-02; both are mirrored now and neither is refused.** Scale-in still is, and it needs the
account-level allocator as well as an add path — margin sees the full stacked position even where
risk-to-stop does not.

✅ **Watched both ways rather than assumed** — scale-in ON is refused with a message naming the
cause, and the SHIPPED config still starts. A guard that refuses everything is not a guard.

⚠ **The refusal is not the whole fix and must not be read as one.** Making this live needs the add
path in the bridge AND the account-level allocator (`docs/LIVE_TRADING_PIPELINE.md` → G10): risk to
the shared stop is <= 0 by construction, but **margin sees the full stacked position**, and at the
shipped 4 adds x 2.0x cap that is several times the base size.



## ✅ A trade can be CLOSED ON DEMAND (2026-09-02) — and the instruction goes to the STRATEGY

**Three pieces, and the order they run in is the design.** A file in the instance directory
(`close.request`) → the runner hands it to the strategy → the strategy exits on its next bar
through the path every other market exit uses → the bridge closes the broker position to match.

🔴 **CLOSING BY HAND AT THE TERMINAL IS WHAT THIS REPLACES, AND IT HALTS THE BOT.** The strategy
goes on believing it holds a position the account no longer has, and the bridge stops on the next
bar — correctly, because from outside that is indistinguishable from a position vanishing for a
reason nobody can name. **A partial close by hand is worse: nothing notices at all**, and every
size computed afterwards is against a book that does not exist.

⚠ **It closes ONE trade and does not stop the bot** — that is why it is a second file rather than
a flag on `stop.request`. Afterwards the bot goes on looking for its next setup. Somebody wanting
both asks for both.

⚠ **The strategy is told, never the broker.** `algos/live/` holds no trading logic, so the
instruction changes what the strategy BELIEVES and the bridge mirrors that — the same rule that
keeps a live result comparable to a backtest. The exit is booked, alerted and recorded exactly
like a time stop, one-bar delay included.

🔴 **THE BROKER SIDE RUNS BEFORE THE ORDINARY CLOSE OBSERVER, NOT AFTER.** `_close_on_command`
brings the account into line FIRST, and `_observe_close` then books the trade the way it books
every other exit. Reversed, one kind of exit would need its own booking path — the second
implementation this package exists to avoid.

⚠ **A REFUSED close is left to halt the bot, deliberately.** The two ledgers really have parted,
and carrying on would compute every later decision against a trade that is still open. **Retrying
here would be a recovery tool repeating the fault it is recovering from** — the rule
`close_orphans.py` already records.

⚠ **The verdict is re-read off the ACCOUNT, never off a return code**, same as everywhere else on
this path.

🔴 **The trade is recorded under `L-CMD` / `S-CMD`, not `CLOSE`, and that was caught by READING
`_close_at` rather than by a test.** Only the tag survives into the record — the reason argument
is discarded — and the opposite-break close already uses `CLOSE`. Sharing it would make *a person
asked for this* and *structure broke against us* the same value, which is this repo's oldest
defect shape and would quietly corrupt any later study of why trades ended.

⚠ **The request file is CLEARED AT STARTUP**, the `stop.request` lesson applied before it could
bite: left behind by a crash or an aborted SSH call it would otherwise flatten the FIRST trade of
every later run, seconds after it opened. The file may only ever mean *somebody asked while this
process was alive*. ⚠ **And it is consumed whatever the answer**, including *nothing to close* —
a request surviving its own answer would fire again on the next bar, and on the trade after that.

⚠ **Asking while FLAT is reported, not latched.** A waiting request would fire on whatever the
bot opened next, which is a trade nobody had an opinion about.

⚠ **Three new ledger events, all DECISIONS** (`close_requested`, `commanded_close`,
`commanded_close_failed`) — each answers *why did this trade end*, which is that stream's
question. `close_requested` is written even when nothing was open, so an instruction that did
nothing is still answerable later.

🔴 **NOBODY HAS RUN THIS AGAINST A REAL BROKER. Treat the first one as a FIRST RUN** — rule 9.
The strategy half is gated (`compare_strategy.py` exit 0 at warmups 100/200/500/1000 on the
2026-09-02 export, before AND after), but **a green gate proves the lever is INERT in a parity
run, never that it works** — rule 14, a branch neither side enters.

**Tests: 4 in `test_live_bridge.py`, 7 in `test_close_request.py`, 6 in the strategy's own
`test_commanded_close.py`.** ⚠ **The bridge's two controls pass without the feature and are
pinned by MUTATION** — firing on any exit fill, and ignoring the dry run, each redden their own
named test. ⚠ **One mutation was written, measured to be a NO-OP and replaced**: it guarded on a
field the test always sets, so it changed nothing and would have been reported as proof of a
test that was never exercised. ⚠ **The fake broker learned to REFUSE a close**, because the
failure branch halts a live bot and is the one most worth being able to produce.

## The live runner's SECOND bar feed — G18 stage 1 (2026-09-01). Stages 2-4 still open

🔴 **`exec_secondary` on a live bot STILL REFUSES AT STARTUP**, and the message that used to say
*"a 1-minute bar stream"* was WRONG — the fill clock has been FIVE minutes by default since
2026-08-21 and is configurable either way. It is corrected as of 2026-09-01 and now names the
setting. ⚠ **A refusal that names the wrong feed is worse than a vague one: it sends the next
reader to build the wrong thing, confidently.** The setting was turned on for
`sos_fade_demo` on 2026-08-28 (Aaron's call) and the bot **would not start** — down until the
setting was put back. **The re-entry is a LAB-ONLY feature on the live side today**, whatever the
strategy's defaults say.

⚠ **Nothing before startup catches it, and that is the trap.** The config CONSTRUCTS fine, and
`promote.py` reported *"verified: the snapshot imports and builds with the promoted parameters"* —
because importing and building is not running. The refusal lives in the runner, so the first thing
that tests it is the restart, by which point the bot is down.
⚠ **A promote's "verified" line means IMPORTS AND BUILDS, never RUNS.** Read it that way.

✅ **CLOSED 2026-09-01 — the preview now asks the question the RESTART asks.** `promote.py`'s
verify subprocess ships the startup FACTS on its existing `@@` line and the parent applies the
rules, which it can because it already has `algos/live/` importable while the staged snapshot has
no `algos/` tree at all. ⚠ **Every config field travels, not the handful a rule reads today** — a
rule that grows a field would otherwise take its `getattr` default and be wrong in the direction
of saying yes. ⚠ **It returns NON-ZERO on a dry run**, deliberately unlike the open-position
warning beside it: the Command Center's verdict is the exit code, so a check that only prints
renders green. ⚠ **A snapshot shipping no startup facts prints "NOT CHECKED" rather than passing**
— rule 1, one level up: *was not asked* and *nothing wrong* must not read the same. ⚠ **Both feed
refusals moved into `feed.fast_feed_timeframe` and the RUNNER calls it too** — a copy in the
promote tool would have drifted the first time either moved. Tests drive the real `verify()`
subprocess against a real staged snapshot, because a hand-written payload would only prove the
parser reads my own dict.

## 🔴 The bridge could not bank at a price, and only two of the six rungs were refused (2026-09-01)

**`assert_supported` read `exec_tp1_pct`/`exec_tp2_pct` and nothing else — which is the LAST branch
of `execution.Execution._tp1_pct`.** Three branches above it were invisible to it and all three
default to banking **100%**. **The bridge has no exit path of any kind**: its only order calls are
`place_pending_limit`, `modify_pending`, `cancel_pending` and `move_sl`, so every exit reaches the
broker as a stop move and any rung that takes size off at a PRICE simply never happens.

🔴 **ONE OF THEM WAS REACHABLE ON THE ARMED BOT TODAY.** `exec_short_hold` is a single boolean;
turning it on replaces the primary's first rung with `exec_sh_tp1_pct`, default **100** — the whole
position off at the R target. Nothing refused it, so the bot would have **STARTED** and ridden
every trade past a target its own backtest closed at. **Watched RED with DID NOT RAISE**, which is
the strongest red available and the reason this is written as an incident rather than a hardening.

⚠ **The other two matter for G18 stage 2**: the re-entry banks 100% under the reclaim trigger
(`exec_rec_tp1_pct`) and 50% under the gap trigger (`exec_sec_tp1_pct`, the live bot's stated
value). **So stage 2 is not "place one more order"** — the entry can be placed and the scale-out
would still have nowhere to go. Either the bridge learns to bank, or the re-entry's banking goes to
zero and the `+32.50R` is re-measured without it.

## ✅ The bridge can BANK part of a position (2026-09-01) — and still cannot close the last of it

**`_sync_partials` is the exit path this bridge never had.** Its only order calls were place /
modify / cancel a resting limit and move a stop, so every exit reached the broker as a stop move
and any rung taking size off AT A PRICE simply never happened.

🔴 **IT IS A RECONCILIATION, NOT AN EVENT, AND THAT IS THE WHOLE DESIGN.** It does not watch for a
rung being touched; it asks *how much should be open* and closes the difference. A partial missed
by a restart, a dropped link or a skipped bar is taken on the next sync, and one already done is a
no-op. An event-driven version has to remember what it has done, and this bridge's history is a
list of things that went wrong with exactly that state.

🔴 **WHAT IT STILL CANNOT DO IS CLOSE THE LAST OF A POSITION AT A PRICE**, so the refusal narrowed
rather than lifted: `full_exit_at_price` now refuses a ladder whose rungs SUM to 100 and allows one
that leaves a runner. ⚠ **SUMMED, not per field** — 50 + 50 also reaches zero, and a check reading
`== 100` on one rung waves it through. Two shipped configurations are still refused and both are
worth naming: `exec_short_hold` (its rung defaults to 100) and the RECLAIM re-entry
(`exec_rec_tp1_pct` = 100) — **which is the setting that MEASURED BEST for that trigger**, so the
reclaim waits on a full-exit path while the gap trigger does not.

⚠ **IT FILLS AT MARKET ON A CLOSED PRIMARY BAR; THE LAB FILLS AT THE RUNG PRICE.** A permanent
divergence, not a bug to tune away — `sync` runs once per closed 15m bar, so a rung touched
mid-bar banks at whatever the market is when the bar shuts. Named on every `partial_banked` record
(`fill="market_on_bar_close"`) so a shadow diff attributes it rather than rediscovering it.

⚠ **A configuration that banks nothing never enters the path, and that is load-bearing.** The
shipped bot runs 0/0, so there is no size to take off; without the gate the first version alerted
*cannot read the intended size* on 18 existing tests whose doubles quite reasonably have no `_qty`.
**An always-on reconciliation against a book nobody is scaling is noise, and noise is how a real
partial failure gets scrolled past.**

⚠ **It only ever CLOSES.** A broker holding LESS than the strategy expects is a disagreement about
the book and belongs to the halt machinery; re-opening size here would be the bridge inventing a
trade. ⚠ **`None` from the size read is not zero** — zero would mean bank the whole position, which
is a full exit, the most destructive misreading available here.

⚠ **It reads `_qty`/`_filled_qty` off the emulator**, the same private coupling the bridge already
has with `_pend_long` and `_pos_dir`. A public seam on `Execution` is the better shape and was
deliberately NOT taken: that is a strategy file, and rule 22 says a changed strategy does not ship
until its parity gate has actually RUN on a real export — a decision to make with an export in
hand, not while wiring a bridge.

🔴 **NO LIVE PARTIAL HAS EVER EXECUTED.** Twelve offline tests and seven mutations; the broker call
under it had zero callers before today. Rule 9 stands: watch the first one.

✅ **`price_triggered_banks` MIRRORS `_tp1_pct` branch for branch and must be re-read against it
when that changes.** It returns a LIST of `(field, percent)` rather than a bool, so the refusal
names the fields — *"partial take-profits are on"* sends nobody anywhere. ⚠ **`exec_sec_tp2_x` is
deliberately NOT listed**: it moves where the second rung sits, while how much comes off there is
`exec_tp2_pct` alone. ⚠ **`assert_supported` still raises on the FIRST problem**, so the preview's
list carries at most one bridge refusal — written down because the list shape suggests otherwise.
Six mutations, each reddening its own named test, none surviving.

🔴 **AND THAT CHECK OVER-REFUSED, BECAUSE IT ADDED UP PERCENTAGES BELONGING TO DIFFERENT TRADES
(fixed 2026-09-02).** It summed every rung the config banks and asked whether the total reached
100. But **a primary and a re-entry are different positions and their percentages never meet** —
so a primary banking 40% beside a gap re-entry banking 60% read as a full exit that neither one
performs, and the refusal named two fields belonging to two trades that are never on the same
rung. **A refusal that names the wrong setting is worse than a vague one: the reader changes
something that was already fine, and is refused again.**

✅ **`bank_ladders` groups the rungs into the ladders ONE position can actually walk**, and the
full-exit check sums each ladder against itself. Four ladders exist and at most three are live at
once: the primary (short-hold's rung or the shared one, plus the shared second rung), and the
re-entry's own — one under a reclaim trigger, one under a gap. ⚠ **The shared second rung sits in
EVERY ladder and is not double-counted**, because a ladder is only ever summed against itself.
⚠ **The flat list is still right for the other question** — *does anything bank at a price at
all* — and is now DERIVED from the ladders, so there is one source of truth rather than two lists
free to drift.

⚠ **Both halves of the rule are load-bearing and each was wrong at some point.** A check reading
`== 100` on a single field waves 50 + 50 on one position straight through; a check summing across
ladders refuses configurations that are fine. **Two tests, one per direction, and each reddens
under the mutation that breaks its own half.**

⚠ **The refusal returns the FIRST offending ladder rather than all of them**, so the message names
one thing to change — `assert_supported` raises on the first problem anyway, and a list of four
fields across two trades is the shape that sends a reader to the wrong setting.

⚠ **No verdict changed for anything shipped** — the live bot banks nothing, the reclaim at 100 is
still refused, and the gap at 50 is still allowed. What changed is the message, and a false
refusal nobody had hit yet.


## 🔴 `partial_close` had never run once, and it CLAMPED UP to the broker minimum (2026-09-01)

**Building the exit path started by reading the one broker call that takes size off a live
position — and repo-wide it had ZERO callers.** Every line of it had been written, reviewed and
shipped against nothing. Rule 9, in its purest form: a feature nobody has RUN is not a feature.
Treat the first live partial as a FIRST RUN, not as a regression risk.

🔴 **Its last sizing line was `max(volume_min, min(lots, held))`, which is rule 17 inverted.** A
slice below the broker's minimum — or one that ROUNDED TO ZERO against the volume step — silently
closed `volume_min` instead, **and returned True.** Watched RED: asking for 0.003 lots against a
0.01 minimum reported SUCCESS while closing 0.01. Banking size the backtest keeps is not the
trade the strategy is holding, and the two books part company on the next bar with nothing saying
why. **It refuses now, naming the number**, and the caller is left with an over-sized position it
KNOWS about rather than a quietly different one.

⚠ **`positions_get` returning None means the terminal could not be ASKED, not that the position
is gone** — the old `if not pos: return False` read the two the same way. That is the identical
defect `cancel_pending` was fixed for on 2026-08-25, sitting one method below it the whole time.
**When you fix a rule-1 hole, grep the file for the same call.**

⚠ **The verdict is re-read off the POSITION, never off the retcode.** A DONE code says the
request was accepted; the position's volume says what is actually open. A move by the WRONG
amount — a race with the stop, a partial fill, another hand on the account — is `UNKNOWN`, never
success, because the bridge reconciles against that number.

🔴 **AND THE REWRITE SHIPPED ITS OWN BUG, FOUND HOURS LATER: THE GUARD REFUSED A FULL EXIT
EVERYWHERE EXCEPT IN THE CODE.** It read `want > held`, which refuses only a size LARGER than the
position — so a request for EXACTLY the held volume passed every check, reached the wire, emptied
the position and returned True while logging *"PARTIAL CLOSE"*. PROVEN by running it: 1.00 lots
asked against 1.00 held → `True`, position 1.00 → 0.00.

⚠ **Two documents asserted the refusal and neither was the code.** `partial_close`'s own message
said *"Closing what is there would be a FULL exit, which is a different decision"* on a branch that
never fired for that case, and `bridge.full_exit_at_price`'s docstring repeated it. **A doc and a
comment agreeing with each other is not evidence** — they agreed with each other and neither agreed
with the line above them.

⚠ **The test beside it looked like coverage and was not.** It asserted 2.00 against 1.00 held — a
size LARGER, never the BOUNDARY. **The one value that mattered was the one nobody wrote down**, and
the test's own name said *is_REFUSED_because_that_is_a_full_exit*, which is exactly the case it did
not exercise.

⚠ **It was LATENT rather than live-reachable, and that was luck rather than design.** The only
caller is `_sync_partials`, gated behind a ladder that `assert_supported` permits only when the
rungs sum to under 100 — so the requested slice was always strictly less than the position. **The
guard was the last line of defence and it was wrong; an upstream check happened to stand in for
it.** Fixed to `>=`, boundary tested, and closing the last of a position is now a differently
NAMED call (`close_position`) so it cannot be reached by an off-by-one in a comparison.

⚠ **The tests carry their own fake terminal rather than reusing `test_mt5_ops_pending.py`'s.**
That one returns every position whatever ticket you ask for and can NEVER return `None`, so it
cannot express the case under test — a fixture that cannot fail the way production fails would
have passed the bug (rule 13).
⚠ **The same limitation is why `compare_strategy.py` can never gate the re-entry** (single frame,
no fill clock) and why `b_leg` and `bos` pin it off. Three places had already recorded this
shape; the live runner was the fourth and nobody had asked it.

✅ **THE SECOND FEED EXISTS SINCE 2026-09-01 AND PLACES NOTHING — G18 stage 1.** The runner opens
a second `BarFeed` on the re-entry's fill clock, warms it, and steps the re-entry through the SAME
object the lab drives (`dual_clock.DualClock`, which `run_dual` was refactored onto in the same
change). A would-be fill is written to the decision ledger as `secondary_shadow_fill`; no order is
sent. **`assert_supported` refused the config outright at the time and was not to be softened
until the bridge could place a second entry** — that was stage 2, and it was the bigger half.
⚠ **Both have since happened; the refusal is gone as of 2026-09-02** — see *The re-entry can be
switched on* below. Full record, the five defects the merge cost and the proof:
`docs/LIVE_TRADING_PIPELINE.md` → G18.

🔴 **STAGE 1 CANNOT BE RUN ON A LIVE BOT, AND THE PLAN THAT SAID IT COULD IS CORRECTED.** The
primary and the re-entry share ONE position slot in the same `Execution`. A "shadow" re-entry does
not sit beside the book — it FILLS in the emulator and takes that slot, and the bridge then finds
*the strategy believes it is in a position but MT5 has none* and **HALTS**. So there is no
observe-it-live step: **stage 2 and stage 3 both land before anything runs on a bot.** Nothing is
lost — the claim is about the MERGE, and that is proved better offline against `run_dual` on the
same bars than by watching a log.

🔴 **THE PRIMARY IS NEVER HELD UP BY THAT FEED, AND EVERY DECISION IN IT FOLLOWS FROM THAT.** A
15m bar is stepped the MOMENT it closes; a fast bar arriving after that has missed its slot and is
REFUSED rather than stepped against a context from its own future. ⚠ **The fast pump has its own
exception handler for the same reason** — unguarded, anything raising in it fell through to the
loop's handler and the primary bars were never read at all, so a fault in the re-entry's feed
would have stopped the bot managing a live trade. Found by a test going red, not by reading.

⚠ **A bot with the re-entry OFF keeps the primary path it has always had, byte for byte** — it
gets a `_SingleFeedClock` that holds no ordering rule at all. Turning the re-entry on is the
change that moves a live bot onto the merged path, once, on purpose, with its own proof.

🔴 **THE MERGE RULE HAS EXACTLY ONE IMPLEMENTATION AND IT LIVES IN THE STRATEGY, NOT HERE.**
`algos/live/` holds no trading logic — that is what keeps a live result comparable to a backtest
result — so this package asks a strategy two questions (`fast_feed_minutes`, `make_dual_clock`)
and does as it is told. **A copy of *which bar steps when* in this package is the defect shape
this repo has already met twice**, and a wrong merge produces an ordinary-looking trade at a
slightly wrong price with nothing in any output able to show it.

⚠ **A fill clock MT5 has no timeframe for is REFUSED, never rounded** (`timeframe_for_minutes`),
and so is one that is not FASTER than the stream the strategy trades. A 7-minute clock silently
served as 5m is a strategy replayed on a stream nobody chose.

⚠ **The 3.25x reclaim target IS stated in the config and is correct**, but inert while the
re-entry is off.

🔴 **Neither setting is runtime-reloadable, so this needed a RESTART — only `exec_risk_pct` applies
to a running bot.** A config pull alone leaves the bot trading the old rules while the file on disk
says otherwise, and the bot reports the difference as *blocked* rather than applying it.

⚠ **An instance config PIN beats the strategy default, silently and permanently.** This bot pinned
the old 3.0 target, so the default moving to 3.25 did not reach it — the pin had to be edited too.
Check the pin before assuming a default change reaches a bot.

⚠ **It is a LAB finding on the live box.** The Pine has no reclaim at all, so `compare_strategy.py`
can never gate it — measured, not assumed: the harness exercised **0** re-entries. The evidence is
a `run_dual` replay (44 re-entries, +32.50R, 2020-2026), not a parity pass.

### 🔴 A broker call has THREE outcomes, not two (2026-08-25)

**One limit order became five positions, and the whole cause is a missing third value.** Retcode
10012 is TIMEOUT: the reply never arrived, so the broker may well have acted. It arrived at the
caller as the same `(None, None)` a rejection produces, the retry loop could not tell them apart,
and the same limit was re-sent on five consecutive bars. All five copies filled at 4661.50 within
69 milliseconds. Full story and the terminal-journal evidence: `docs/ALGOS_BUILD_NOTES.md`.

**`shared/broker_result.UNKNOWN` is that third value.** Its own dependency-free module on purpose
— defining it inside `mt5_ops.py` and importing it into `bridge.py` pulled the broker module into
the bridge's import graph, reordered `sys.path`, made a different `fleet_halt` win, and broke
three unrelated test modules with a circular-import error naming neither file. It is **falsy**, so
an old `if ticket:` site degrades to the conservative reading rather than crashing; anything that
must act on the difference tests `is UNKNOWN`.

**The five rules this leaves, and each one is a place the old code was wrong:**

1. **A send that does not confirm must ASK THE BROKER before reporting failure.**
   `place_pending_limit` snapshots the order book, sends, and on any non-DONE result diffs the
   book against that snapshot. A ticket that is there now and was not before is ours. ⚠ **An
   unreadable snapshot is UNKNOWN even if the follow-up read succeeds** — without the baseline an
   order already resting cannot be told from one that just landed. ⚠ **Two new tickets is also
   UNKNOWN, not a pick**: adopting one would leave the other resting and unowned, which is the
   state being fixed.
2. **A cancel that is not CONFIRMED must never be followed by a replacement.** `_drop_rest`
   returns False and KEEPS the record, so the next bar retries the cancel instead of placing a
   second order beside the first. 🔴 **This one needs no timeout at all** — an ordinary rejected
   cancel was enough, because `_sync_slot` discarded the answer and cleared its record anyway.
3. **The order book is swept EVERY BAR for orders we have no record of** (`_observe_orphans`),
   not only at startup. Four orphans sat resting for five hours through twenty bars and the first
   thing that noticed was the position-count halt, after they had all filled. ⚠ **It cancels
   rather than adopting**: adoption needs a decision about which strategy intent an order belongs
   to, and getting that wrong silently attaches a live order to the wrong side. ⚠ **An unreadable
   book cancels nothing and clears nothing** — fail closed.
4. **The account risk cap excludes our own orders by TICKET, never by MAGIC.** The exclusion
   carried an unstated premise — *anything under our magic is something we placed and are about
   to replace* — and four orders we had no record of were under our magic too, so five copies of a
   10% order read as an empty account. **A premise like that belongs written next to the exclusion
   it justifies**: this one was documented, reasoned and correct on the day it was written, and
   nothing announced the day it stopped being true.

5. **A resting order is keyed by what it is FOR, not by which side it is on** (2026-09-02).
   `_rest`, `_unresolved`, `_refused` and `_refusal_alerted` are keyed by `(intent, side)` —
   `PRIMARY_LONG`, `SECONDARY_SHORT` and the other two — and `_sync_slot` reconciles exactly one
   of them. 🔴 **The re-entry arms while the bot is FLAT, which is precisely when the primary is
   offering its own limit, so the two want a resting order on the same side at the same moment.**
   Keyed by side alone the second placement overwrites the first's record — and rule 3 above then
   cancels the order nobody remembers, within a bar, while the strategy still believes it is
   there. ⚠ **The side is part of the key rather than read off the pending order**: it costs one
   slot that is never used and buys the property that every lookup here finds its slot from the
   two things the caller always knows. ⚠ **The intent reaches the ledger as `intent`, never
   `kind`** — `ledger._write` stamps every record with a `kind` of its own, so that name collides
   one layer down; MEASURED, not reasoned, when writing it as `kind` killed six tests on the fake
   ledger's signature.

### 🔴 A refused order records WHICH guard refused it (2026-09-06)

**The order layer refuses for seven unrelated reasons and every one returned the same
`(None, None)`**, so `bridge._place` could record only THAT an order was refused — no code, no
sentence. The reason existed, correctly worded, in a log line that rotates; **the decision record —
the copy `ledger_sync.py` pushes off the box, and the only artefact that outlives the week — could
not answer the question it exists to answer.**

⚠ **This was NARROW and the narrowness is why it survived.** The SIZING refusal beside it
(`_record_refusal`) has carried a code, a detail, the wanted size and an alert since it was written.
Only the PLACEMENT refusal was mute, so a grep for `order_refused` found rich records and the gap
sat in the other branch.

**`mt5_ops.BotMT5.last_refusal` carries it out**: cleared at the top of BOTH placement functions,
set by `_refuse` at each guard, read by the bridge. ⚠ **Cleared on ENTRY, or a stale reason from an
earlier bar is read as this bar's** — a confidently wrong sentence in the one record that survives,
which is worse than the blank field it replaces.

⚠ **`None` at the bridge is recorded as `code="unrecorded"` with a detail NAMING the gap, never as
a blank field.** Rule 1: *no reason given* and *nobody captured one* must not read alike — the first
is a gap in `mt5_ops.py` worth finding, and a blank hides it for as long as it exists.

⚠ **The codes are NAMED CONSTANTS, never literals** (`ORDER_REFUSAL_CODES`). A mistyped literal is
a brand-new code no reader and no query has heard of and nothing fails; a mistyped name does not
import. **Deliberately not a validating assert** — a guard that can crash a live bot over a typo in
its own error path is worse than the gap it closes.

⚠ **Only the genuine refusal branch sets it.** An UNKNOWN outcome and an ADOPTED order must leave
none: one means *we could not find out* and the other *it worked*, and a reason-for-refusal under
either is a sentence flatly contradicting the record beside it.

⚠ **`at_market` travels with the record**, because the two placement paths share codes — a size
below the venue minimum is `below_min_lot` on both — and a count that cannot tell them apart answers
a different question from the one its name asks.

⚠ **The two ends of the broker's stop distance get DIFFERENT codes.** A strategy hitting the
entry-to-stop one every time has a stop too tight for this venue; one hitting the market-to-entry
one is arming too close to price. A shared code cannot show either.

✅ **9 tests in `test_live_bridge.py` and 16 in `test_mt5_ops_pending.py`; 18 mutations RUN and every
one red**, including a control that a SUCCESSFUL placement records no refusal at all — a suite whose
every case asserts a refusal certifies a bridge that refuses everything, which this repo has already
shipped once.

⚠ **NOTHING HERE HAS RUN AGAINST A BROKER. Rule 9** — the codes are produced by a faked terminal,
and the first real one is still the first one.

### 🔴 An oversized position is RESIZED now, and the resize does NOT happen here (2026-09-02)

**A strategy asking for more lots than the venue accepts trades the maximum instead of skipping
the setup** (Aaron's call). Default ceiling **100 lots**, every bot. ⚠ **This reverses half of
root rule 17 and only half** — below the broker minimum and unaffordable-on-margin still mean NO
TRADE, and `order_sizing.plan_order` still refuses an over-max ORDER.

🔴 **THE RESIZE IS IN THE STRATEGY'S OWN SIZING, NEVER IN THE ORDER, AND THAT DISTINCTION IS THE
WHOLE SAFETY PROPERTY.** `backtest/portfolio/account.py` caps the quantity the emulator books, so
the position it holds and the order this bridge sends are the same size. Clamping the ORDER
instead is what rule 17 was written about: the emulator would hold 742 lots against a broker
holding 100, the two grade different R, and `_agrees` halts the bot on a divergence the safety
feature created. **Clamping at the DECISION is coherent; clamping at the ORDER is not.**

**`bridge._reconcile_lot_ceiling` is this package's whole share of it** — it holds the emulator's
ceiling at `min(what we configured, what this broker accepts)`, read off the symbol spec that
`_plan` already fetches. Without it a configured ceiling ABOVE the venue's is not a ceiling: the
strategy sizes to 100, the broker refuses at 50, and `plan_order` is left refusing an order nobody
could place.

⚠ **It only ever LOWERS, and it re-reads the CONFIGURED value each time.** Aaron does not want to
trade past his own ceiling whatever a broker permits, so a venue offering 200 does not raise it —
and ratcheting off the live value would let one bad read pin the ceiling low for the whole session,
which is rule 16 inverted.

⚠ **A missing or non-positive volume band is CANNOT ASK, not NO LIMIT and not ZERO** (rule 1). Zero
refuses every order for the rest of the session; infinite hands the broker a size it rejects. The
configured ceiling simply stands.

⚠ **Both numbers are LOTS and nothing converts on this path.** Introducing a contract-size
multiply here would be the 2026-08-07 units bug arriving by a new route — the conversion belongs in
the account seam, which is the only place that knows the strategy sizes in units.

⚠ **`plan_order`'s over-max refusal now firing means the ceiling never reached the strategy** — a
configured maximum above the venue's, or a bot whose sizing does not go through the account seam.
Its message says so and names the number to lower.

⚠ **NOTHING HERE HAS RUN AGAINST A BROKER.** Rule 9. And the live bot cannot reach it until a
promote: the frozen snapshot carries `backtest/`, so the account seam's ceiling arrives with the
strategy, while this reconciliation is `algos/` and arrives on a `git pull` plus a restart.
**MEASURED: the live SOS Fade config does not touch the ceiling until the balance passes ~$927,000**, so
this changes nothing about what that bot trades today.

**Tests: 6 in `tests/test_live_bridge.py`, each watched RED under its own mutation** — the venue
raising our ceiling, the assignment removed, an unreadable band taken at face value, the ratchet,
a deliberately-uncapped run having one switched on, and a strategy with no account seam raising
inside order planning. ⚠ **They use the REAL `SoloAccount`, not a stub with a `max_lots`
attribute** — a stub accepts any number the code writes, including ones the real object rejects,
which is the fixture-more-capable-than-production trap this file already records twice.

### Exits — which ones the BRIDGE has to execute (2026-09-02)

**`_mirror_strategy_exit` closes the broker position when the strategy has exited a trade the
broker cannot.** The strategy exits in its own book and stamps a tag on the exit fill;
`BRIDGE_OWNED_EXITS` is the allow-list of tags this bridge must act on: `-CMD`, `-TIME`, `-TP1`,
`-TP2`.

🔴 **The list is what the BROKER cannot do for itself.** A stop is already an order sitting at the
broker, so a stop-out needs nothing from here. Everything on the list is a decision the strategy
made against a closed bar — a target that took the whole position, an operator's instruction, the
clock running out — and the broker has never heard of any of them.

🔴 **THIS IS THE FULL-EXIT-AT-A-PRICE PATH, and it is why a ladder banking 100% is no longer
refused at startup.** `_sync_partials` reconciles the broker DOWN to the size the strategy still
wants, and that cannot express zero: a rung taking the last of a position finalises the trade in
the same step, so by the time the bridge looks the strategy is simply flat and there is no
intended size to reconcile towards. The two are complementary — **a bank that leaves a runner is
a reconciliation, and a bank that ends the trade is an exit.**

🔴 **THE STRATEGY MUST BE FLAT, and that test is what separates the two.** A rung banking 50% and
riding the rest emits *exactly the same* `-TP1` exit fill as one taking the lot. Acting on the tag
alone would market-close the whole position and delete a runner the strategy is still managing —
turning every scale-out into a full exit, silently.

🔴 **IT ALSO CLOSED A HOLE THAT WAS LIVE.** The time stop is ON for the armed bot (36 hours,
before-breakeven only) and nothing mirrored it: the strategy would have exited in its own book,
the broker would have kept the position, and the bridge would have halted on the next bar with
the trade still open and nothing ratcheting its stop. Only the operator's own close was ever
wired. ⚠ MEASURED: the committed decision record holds two exits, both by stop, so it never
fired — the exposure was real and had not yet been reached.

⚠ **`-CLOSE` is ABSENT because it is AMBIGUOUS, not because it is safe.** `execution._close_at`
defaults to that tag, so an ordinary stop-out and the opposite-structure force-close both arrive
stamped `L-CLOSE` and nothing in the fill tells them apart. **So `exec_close_opp_sos` is REFUSED
at startup instead** — mirroring would market-close on top of a filling stop, ignoring would halt
the bot, and an unsupported thing that says so beats either guess. It comes off the refusal list
when that exit gets its own tag.

⚠ **Adding an exit leg to the strategy means adding it here.** This is an allow-list, so a new tag
defaults to *not mirrored*: the bot exits in its own book, the broker keeps the position, and the
bridge halts. Loud rather than silent — which is why the allow-list is the safe direction — but
still a halt somebody has to come and read.

⚠ **`full_exit_at_price` was DELETED rather than left behind.** Its whole subject was *the bridge
cannot do this*, and a function whose docstring describes behaviour the code no longer has is
worse than no function: the next reader takes it for a live rule. The property underneath it —
that rungs sum within ONE ladder and never across two — still matters to
`price_triggered_banks`, so the tests now assert it against `bank_ladders` directly.

⚠ **None of this has run against a broker.** Rule 9 applies to the first one.

🔴 **THE FLAT TEST WAS ALSO READING A REVERSAL AS A BANK, AND MIS-MANAGING A LIVE POSITION IN
SILENCE (found and closed 2026-09-03).** A bar that closes one trade and opens another leaves the
emulator holding a position, so the paragraph above sent it down the bank path: the broker kept the
OLD position, `_observe_close` saw it still there and booked nothing, `_agrees` compares PRESENCE
and was content — and `_sync_stop` then ratcheted that position's stop to the NEW trade's, which
belongs to the other direction. **Nothing in any log said so, because every layer's own check
passed.** ⚠ **It reaches the LIVE bot**: a bar that closes a trade and fills the emulator's next
limit lands here identically. ✅ **The distinguishing fact is an ENTRY fill on the same decision** —
one position slot means one can only exist beside an exit fill if the old trade ended.

⚠ **It HALTS rather than reversing in one bar, and that is a decision.** MEASURED over 470,995 M5
bars of the extreme leg: 113 closes, 113 opens, **zero sharing a bar**. Building a reversal path
would ship a branch to a live bot that nothing has ever run (rule 9); the halt is the honest answer
to a case nobody has built, and it is what this state produced anyway for a resting bot one bar
later, once its new limit filled and two positions appeared.

⚠ **The halt needed its own exit from `sync`, and leaving that out is what would have made it
useless.** Every other halt on this path comes FROM `_agrees`, which stops the bar by returning
False; one raised earlier falls straight through to `_sync_stop` and does the very thing it just
refused. **A refusal that does not stop the work is not a refusal.**

### Opening at MARKET — `_mirror_strategy_entry` (2026-09-03)

**The mirror image of the exit path, for a strategy that enters at market on a bar's close.** Such
a strategy fills inside its own emulator DURING the step, so by the time this bridge looks there is
nothing left to place ahead of the fill: the position exists on one side and not the other, and the
bridge's job is to catch the broker up. **Before this, such a bot halted on its first setup** — the
order-placing branch requires the emulator to be FLAT and was never reached.

🔴 **IT RUNS ONLY FOR A STRATEGY THAT DECLARED IT ENTERS AT MARKET, AND THAT GATE IS THE WHOLE
SAFETY PROPERTY.** *Emulator in a position, broker flat, an entry fill on this bar's decision* is
byte for byte the state a RESTING strategy shows when its limit filled in one book and not the
other — the 2026-08-07 fault, where the bot must stop. **Nothing observable separates the two**, so
the bridge reads the strategy's own declaration (`entry_style`) instead of guessing. An undeclared
strategy defaults to the HALTING answer; `verify_live_ready` refuses an unrecognised value at
startup so that default stays a backstop. Contract: `strategies/CLAUDE.md`.

🔴 **THE SIZE STILL COMES FROM `_plan`, NEVER FROM THE EMULATOR'S QUANTITY.** That is the one seam
converting strategy units into lots against the BROKER's balance, its volume band and the account's
remaining risk — none of which the emulator can see. A strategy sizing off its own compounded
equity is the 221x incident, and a second sizing path on the live route is how it comes back.

🔴 **A MARKET ORDER'S STOP GOES OUT WITH THE ORDER AND THERE IS NO SECOND CHANCE**, which is why
the intent's coherence is checked here rather than left to the broker. A resting limit sits for
hours with a whole reconcile loop in which to notice a bad stop; this one fills on arrival. Four
refusals, each its own code: an unreadable price, an unreadable size, **an unreadable stop (`None`,
rule 1) and an ABSENT one (`0.0`, which reaches the terminal as *no stop at all* — the two must not
collapse)**, and a stop on the wrong side, which would fill and stop out in the same instant.
⚠ **The wrong-side test is deliberately NOT in the shared sizing seam** — putting it there changes
what the live bot does today and needs its own measurement. **The limit path keeps that hole**; it
is loud there, because the broker rejects the order and a refusal is recorded.

⚠ **A refused order leaves the two books parted ON PURPOSE, and `_agrees` halts naming the
refusal.** The emulator has ALREADY booked the trade, so shrinking the order would leave the two
holding trades that grade different R (rule 17), and un-booking the emulator's side would be this
layer editing the strategy's book. The shrink that avoids most of these happens one layer earlier,
in the strategy's own sizing, before the fill.

⚠ **It acts on an entry fill from THIS bar only, and a failed placement does not retry.** A
position opened on an earlier bar is not latency — it is a divergence that has already survived a
reconcile, and placing it now would buy at today's price a trade priced yesterday.

⚠ **Nothing is adopted here.** It returns a RE-READ position list and `_observe_open` books, alerts
and saves exactly as it does for a limit fill — one adoption path, so two code paths can never
disagree about one trade. WARMING and HALTED place nothing.

🔴 **THE FILL CLOCK REFUSES A MARKET STRATEGY OUTRIGHT.** The mirror is wired on the primary clock
only, so a second stream would reach the same disagreement with no path to open it and halt with
the resting bot's message, blaming a limit that was never placed. Unreachable today; it is a halt
rather than a silent return because a bot running two clocks with one of them inert is the worst of
both.

⚠ **None of this has run against a broker.** Rule 9 applies to the first one.

**Tests: 18 in `algos/tests/test_live_bridge.py`, 17 mutations watched RED on their own named
test.** 🔴 **One was VACUOUS on its first pass and is recorded rather than quietly replaced** — the
stale-position test asserted *no order and a halt*, and mirroring a stale position produces both
(it fails on an unreadable price and records a refusal). It now asserts that **nothing was
attempted**: no refusal row, and a halt reason that does not blame a price the strategy was never
asked for.

### The venue lot ceiling is reconciled BEFORE the strategy sizes, not only before an order (2026-09-03)

`_reconcile_lot_ceiling` used to run inside `_plan`, i.e. only when the bridge was about to PLACE
an order. **A bot whose first action is a FILL rather than a placement never reached it**, so its
first trade sized against the configured ceiling instead of `min(configured, venue)` — and a venue
band tighter than the configured one meant a refused order and a halt on trade one. It now also
runs in `refresh_account_room`, which the runner calls before every step: the same seam, at the one
moment that can still change the outcome. ⚠ **A resting bot had a milder version of the same gap**
on its first armed bar. ⚠ **It only ever LOWERS and re-reads the configured value each time, so
this computes the same number more often — what changed is WHEN it is applied.** ⚠ **A spec the
terminal cannot answer leaves the configured ceiling alone** (rule 1): not *no limit*, not zero.

### ✅ The bridge can OPEN AT MARKET, and the flag that asked for it finally has a consumer (2026-09-03)

**`_place` branches on `pend.market`.** Until now its only placement call was
`place_pending_limit`, so **a strategy that enters at market could not be a live bot at all** —
which is what blocked `extreme_leg`.

🔴 **THE FLAG EXISTED AND NOTHING READ IT.** `_Pending.market` has meant *do not wait for price,
fill at the next open* since the re-entry landed; the EMULATOR honours it
(`sos_fade/execution.py`) and **no file under `algos/live/` referenced it — grepped, not
assumed.** So a strategy could mark an entry as market and this bridge would quietly rest a limit
at a price that may never come back: two books, different trades, nothing raised. **Rule 7 with
the consuming line simply missing.**

⚠ **It was NOT live-reachable, and that was luck rather than design.** The only setting that sets
it is the reclaim entry mode, which the live bot has on `Retest` with the feature off — both
CHECKED in its config. **Latent, not active.**

🔴 **BOTH BROKER CALLS RETURN `(ticket, price)` AND THE TWO PRICES MEAN OPPOSITE THINGS.**
`place_order` returns where it FILLED; `place_pending_limit` returns the price it is RESTING AT,
which has not been reached. The first version unpacked the second element for both, recording an
unfilled order as filled at a price nobody traded. **An identical shape carrying two meanings is
what made it invisible** — and it was caught by its own test rather than by reading.

🔴 **A MARKET FILL IS NOT RECORDED IN `_rest`, and that is the whole bookkeeping difference.**
`_rest` means *an order of ours is waiting at the venue*. A market order has already filled, so
recording it there would make `_observe_vanished` read a live position as an order that
disappeared, and `_cancel_all_rest` would try to cancel a position.

⚠ **Nothing adopts the position at the placement site either.** `_observe_open` adopts whatever it
finds on the next reconcile and remains the ONE adoption path — a second one is how two code paths
start disagreeing about the same trade. The position is not unprotected meanwhile: its stop went
to the broker WITH the order, the same guarantee the limit path relies on (D4).

⚠ **BOTH branches are handed `lots` from `_plan`.** Nothing on this path re-derives a size, so the
2026-08-07 single-seam rule holds for the market route too — pinned by a test asserting the two
routes produce an IDENTICAL lot count from identical inputs.

⚠ **`tp=0.0`, like the limit path.** Every strategy here manages its own targets; a broker-side TP
would close a position the emulator still holds.

✅ **`mt5_ops.place_order` gained the volume guard its sibling already had** — an ASYMMETRY rather
than a decision, invisible for as long as nothing called the market form. It REFUSES below the
minimum and never rounds UP (rule 17); rounding 0.004 up to a 0.01 minimum is 2.5x the authorised
risk. Its log lines now name the volume SENT rather than the one requested (rule 3).

⚠ **NOTHING HERE HAS RUN AGAINST A BROKER. Rule 9** — and `place_order` itself had ZERO production
callers before today, so treat the first market entry as a FIRST RUN, not a regression risk.

⚠ **It reaches the running bot by `git pull` plus a RESTART** (`algos/` is not in the frozen
snapshot). The live bot cannot reach the new branch — its config cannot set the flag — so this is
additive for it, which is why it may land while it trades.

**Tests: 9 in `test_live_bridge.py`, 3 in `test_mt5_ops_pending.py`; 8 mutations watched RED.**
🔴 **One "surviving" mutation was the HARNESS, not the test** — its `-k` filter did not select the
target, so the test never ran and the report read exactly like a vacuous test. **A mutation run
that does not assert its target was SELECTED can report a false survivor**, which sends you to
weaken a test that was working.

### The pending-order layer (added 2026-07-30) — four MT5 behaviours to know

`place_pending_limit` / `modify_pending` / `cancel_pending` / `cancel_all_pending` /
`get_pending_orders` / `get_open_positions` / `normalize_volume` / `min_stop_distance`.
Added because the file could only send MARKET orders and the strategies enter on a resting
limit. Each is a broker quirk that fails silently rather than loudly:

- **`MODIFY` silently ignores `volume`.** MT5 accepts the request, reports success, and leaves the
  size unchanged. A size change — which happens on almost every bar, because size is a % of moving
  equity — must be CANCEL + re-place, never a modify.
- **`SYMBOL_TRADE_STOPS_LEVEL` is checked twice**, market→limit *and* limit→stop. A limit that is
  legal against the market but whose stop sits inside the band is rejected at fill time, not at
  placement, which looks like a random missing trade hours later.
- **`normalize_volume` rounds DOWN and returns 0.0 below `volume_min`.** Rounding a sub-minimum size
  UP to the broker minimum would silently trade more risk than the strategy asked for; refusing is
  the honest answer.
- **Every read is MAGIC-filtered.** `get_pending_orders`/`get_open_positions` see only this bot's
  orders, so two bots on one account cannot cancel each other and a hand-placed trade is invisible
  to the reconciler.

**Never treat MT5's `time` field as UTC.** It is the BROKER SERVER's local time, and it arrives as a
plain epoch int with nothing to mark it. `get_candles` converts through `broker_clock.py`
(measured offsets, not assumed). Before the fix on 2026-07-30 every bar was 2–3 hours out behind a
perfectly valid-looking timestamp — which moves every session boundary a strategy trades off, with
no error anywhere. Verify a new broker with `compare_feeds.py`; do not assume the offset.

## 🔴 The fill clock halted both SOS Fade bots on their OWN limit (2026-09-17)

**What happened.** 01:36 UTC, the primary short limit (T364105022 live, T379558872 demo) filled at
4316.98. At 01:40 a 5-minute and a 15-minute bar closed together; the fill clock runs FIRST (the
merge rule), the strategy had not yet closed the 15-minute bar that fills its limit, so the
position read as unknown: `Could not snapshot … called while flat`, then `HALTED: MT5 holds a
position the strategy does not know about`. Both trades were left with only the broker stop. Every
primary fill on a bot with the re-entry switched on would have done this.

**The fix (`bridge._primary_fill_awaiting_its_bar`).** The fill clock leaves a broker position
alone when its TICKET and SIDE match the primary limit this bridge rested, pulls every other
resting order, and lets the 15-minute `sync` adopt it the ordinary way. A position matching nothing
still halts; an emulator that does not fill on its bar still halts in `sync`. The restart record is
never attempted while the strategy is flat (`_save_position`).

**Re-adopt by replay (`bridge._adopt_by_replay`).** A broker position with no restart record no
longer halts at `adopt_broker_state`: after the warm-up, if the replay holds the same side, entry
and stop (one point) and remaining lots (within 0.005) with no scale-in lots, it is adopted and a
record written; any difference halts naming each one. ⚠ The replay sizes on its own drifting
equity, so it refuses more often than it adopts — the safe direction.

**MEASURED 2026-09-17 02:15 UTC** (frozen a6481ce3 code, real instance params, 5,000 demo-feed
M15 bars): tonight's two trades would NOT be adopted. Replay: short @ 4316.98, stage 2, stop
already moved to 4301.37 (TP1 touched 01:56, TP2 4285.76 at 02:09), a scale-in lot at 4287.45,
0.132 / 0.203 lots open against the broker's 0.14 / 0.22. Stop, size and scale-in all differ.

**Also.** The re-entry gap alert no longer fires for gold's daily break — `BarFeed.bars_since_last`
counts bars the broker actually printed (the re-warm still runs; cannot-ask still alerts). The
hourly review reads the PROCESS list before calling a missing health record a fault, so a bot
stopped with a stale `running` status no longer raises it daily (`log_review.running_keys`).
Extreme Leg has no second bar stream, so it never reaches the fill clock.
