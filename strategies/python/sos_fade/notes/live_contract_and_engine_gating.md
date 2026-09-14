# Notes — Live contract, exit pricing and engine gating (2026-09-09/10)

`full_exit_price()`, the single implementation behind the first rung's price, the two engines this bot no longer runs, and the parity gate's truncation, missing-column and fresh-export fixes. Moved VERBATIM out of `strategies/python/sos_fade/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## Closing a trade because a PERSON asked — `request_close()` (2026-09-02)

**A seam, not a shipped feature.** It gives this strategy the one thing it had no way to be
told: get out of this trade now. Nothing calls it yet — the runner and the bridge wiring are
unbuilt — so **rule 9 applies in full: nobody has run this end to end.**

🔴 **THE INSTRUCTION GOES TO THE STRATEGY, NOT THE BROKER, AND THAT IS THE WHOLE DESIGN.**
Closing by hand at the terminal leaves the emulator holding a position the account no longer
has, and the bridge HALTS on the next bar — correctly, because from outside that is
indistinguishable from a position vanishing for a reason nobody can name. A partial close by
hand is worse: nothing notices at all, and every later size is computed against a book that
does not exist.

⚠ **It closes nothing itself.** It latches a value; the exit happens on the next bar through
`_pending_close`, the same path the time stop and the opposite-break close already use — same
one-bar delay, same fill model, same record. A private exit path here would be a second
implementation of what this file already does, and the one nobody's tests cover.

🔴 **The record's tag is `L-CMD` / `S-CMD`, NOT `CLOSE`, and that was caught by reading
`_close_at` rather than by a test.** Only the TAG reaches the trade record — the reason
argument is discarded — and the opposite-break close already uses `CLOSE`. Sharing it would
make *a person asked for this* and *structure broke against us* the same value, which is this
repo's oldest defect shape and would quietly corrupt any later study of why trades ended.
⚠ **So `reason` is for the CALLER's record**, and belongs in the decision ledger where a
sentence fits.

⚠ **Asking while FLAT refuses rather than latching.** A request that waited would fire on
whatever the strategy opened next — a trade the person asking had no opinion about. The `False`
is what lets a caller say *nothing to close* instead of reporting a close that never happened.

⚠ **Deliberately NOT in `_POSITION_FIELDS`.** The request's home is the file the runner
watches, and a restart re-reads it, so there is one source of truth rather than two that can
disagree. Persisting it would also make every existing position record incomplete, which the
promote gap-check reads as a migration. **And a latched close surviving a restart is the
`stop.request` hazard exactly** — a stale instruction outliving the moment somebody meant it.
Losing it on a restart is visible and cheap: the position is still open, so you ask again.

🔴 **A GREEN PARITY GATE PROVES THIS IS INERT, NEVER THAT IT WORKS**, and the two are being
stated apart on purpose. The Pine has no such lever and `compare_strategy.py` never enters the
branch, so rule 14 applies in its exact stated form: the gate says nothing about a branch
neither side entered. **PARITY: `compare_strategy.py "VANTAGE_XAUUSD, 15_2a817.csv"` exit 0 at
warmups 100 / 200 / 500 / 1000, before AND after the change** (21,766 bars, 2025-10-01 →
2026-09-02, full history — the truncation detector measured 0 missing warmup bars).
⚠ **At warmup 0 it diverges at bar 16 and that is cold start, not a regression** — the same
shape every export here shows, gone well before 100 and still gone at 1000.

**Tests: 6 in `tests/test_commanded_close.py`.** Five go red against HEAD only as
*AttributeError*, which proves little for a new method — **so each is pinned by MUTATION**:
sharing the `CLOSE` tag, demoting the branch below the time stop, latching when flat, and
firing with nobody asking each redden their own named test. ⚠ **The sixth passes at HEAD by
design** — it is the inertness control the parity gate leans on, and it reddens under the
fire-with-nobody-asking mutation.

## `full_exit_price()` — where this bot closes the WHOLE position (2026-09-09)

Part of the live contract (`strategies/python/live_contract.py` → `EXECUTION_ATTRS`). The bridge
hands the answer to the broker, so a target fills AT its price instead of at market on the next bar
close — up to a whole 15-minute bar of drift from the price the backtest booked.

🔴 **THE RULE LIVES HERE BECAUSE ONLY THIS FILE CAN ANSWER IT.** Which share the first rung takes
depends on what KIND of trade is open: a re-entry after a stop-out banks **100** and one into a gap
banks **0** on the live bot. `algos/live/` holds no trading logic and its `bank_ladders` mirrors
that rule for the STARTUP refusal only — it cannot answer for an OPEN trade. A copy over there
would be a second implementation free to drift from the one that books the fills.

⚠ **`None` for a rung that leaves a RUNNER.** A venue take-profit closes the entire position, so a
price there would bank size this strategy is still managing. The bridge reconciles those at market.

⚠ **`None` while FLAT — and that guard is LOAD-BEARING, not defensive.** `_finalise_trade` does not
clear `_tp1` (assigned only in the constructor and at the entry fill), so a strategy that has traded
and gone flat still carries its last trade's target. Without the guard that stale price would be
handed to the broker for whatever opens next.

⚠ **Off `_tp1`, never `_stage_rungs()`.** That method orders the two rungs by DISTANCE for the stop
ladder and explicitly does not move where profit banks, so reading the reordered pair would name a
price this strategy does not bank at.

**Tests: 6 in `tests/test_full_exit_price.py`, 3 mutations RUN and every one red.**
🔴 **The FLAT test was VACUOUS on its first pass and the fixture was the fault.** It asserted `None`
on a fresh object, where `_tp1` is 0.0 — so *flat* and *no price* were the same assertion and the
mutation deleting the guard survived it. **The scale-of-1 trap: check that a test's inputs can
distinguish the behaviours it names.** It now carries a stale target and asserts it does.

✅ **PARITY GREEN after the change** — `compare_strategy.py` on `VANTAGE_XAUUSD, 15_53f52.csv`,
**19,542 bars, exit 0 at `--warmup 500`**, identical to its pre-change baseline. ⚠ **The gate is
structurally blind to this method** — nothing in the decision stream reads it, and the Pine has no
counterpart. A green run says the decisions did not move, nothing more.

## The first rung's price has ONE implementation, and the live bridge asks it too (2026-09-09)

**`_first_rung` and `_tp1_pct_for` are the rule; `_open_position`, `full_exit_price` and
`planned_full_exit_price` are its callers.** The arithmetic used to be written out inline at the
fill and nowhere else.

🔴 **THE ALTERNATIVE WAS A SECOND COPY IN `algos/live/`, WHICH IS THE SHAPE THIS REPO KEEPS PAYING
FOR.** The live bridge needs the whole-position target for an order it is about to SEND, so the
target reaches the broker in the same message as the stop instead of a bar later. That answer is
this strategy's to give — which trade kind banks what is a trading rule, and the live layer holds
none — so the seam is a question asked of the strategy rather than a branch copied into the bridge.

🔴 **THE PLANNED ANSWER IS AN ESTIMATE AND ITS ONE-WAY SAFETY IS THE ARGUMENT FOR SENDING IT.** The
rung is priced off the FILL. A limit fills at its price **or better**; a better fill is a **smaller**
risk; a smaller risk puts the rung **nearer**. So the estimate is always at or BEYOND where this
strategy banks, the strategy's own trigger fires first, and the broker's target is never reached
early. ⚠ **For a SHORT, *nearer* means HIGHER** — the direction an eyeball check gets backwards, and
the reason both directions carry their own test.

⚠ **A MARKET re-entry (`exec_rec_entry_mode = "Market"`) answers `None` rather than estimating.**
Its fill can land either side of the arming price, so the property above does not hold. **The live
bot rests a limit for its reclaim, so this refusal costs it nothing today.**

⚠ **The order carries its own `kind` now.** Deriving it from `src` is wrong: `None` is both a
primary and a re-entry whose trigger never named itself. The fill path is TOLD the kind; the
planned answer is asked before there is a trade to read it off.

⚠ **PARITY UNAFFECTED, MEASURED RATHER THAN ARGUED.** `compare_strategy.py` on
`VANTAGE_XAUUSD, 15_53f52.csv` (20,056 rows) is **exit 0 at warmups 500 and 1000 (19,542 / 19,042
bars)** and diverges at bar 293 at warmups 100 / 200 — and a HEAD worktree gives the **byte-identical
ladder**, so the shallow-warm-up divergence is a pre-existing cold start and not this change.
🔴 **`export_truncation()` returned 0 on an export carrying 12 `dbg_` columns, so the harness could
not name its own warm-up floor and the ladder is what settled it.** That is rule 1 inside the gate:
*not truncated* and *cannot measure it* are the same value. ✅ **FIXED 2026-09-10 — it returns
`None` for *cannot measure* and the gate SAYS SO before it prints a verdict.** See below.

⚠ **6 new tests, every one watched RED by mutation** — including one rewritten after a mutation
survived it: the first version asserted `None` on a config whose shared percentage was also 0, so
*read the primary's rule* and *read the secondary's and fall through* were the same assertion. **A
test whose inputs cannot separate the behaviours it names is green and worthless.**

## Two engines this bot never reads are no longer RUN (2026-09-10)

`engine_config()` now also declares `internal=False, sessions=False`. **`SignalAdapter.update` is
the whole of what this strategy sees of the engine stack** — the snapshot, the structure fib, the
sniper zone, the macro fib, the gaps, the RSI divergence and the liquidity levels. It has never
read the internal fib or the sessions engine, and both were stepped on every bar of every replay,
optimizer combo and sweep this bot has ever run.

⚠ **`show_internal=False` was already blanking the snapshot fields the internal fib seeds from, so
that engine's output was doubly dead.** The two are still separate facts: one is a Pine input about
what the STRUCTURE engine exposes, the other is whether a downstream engine is asked at all.

✅ **PROVEN RESULT-IDENTICAL, not argued.** The live two-bot stack replayed twice in one process —
every engine on, then gated — over 2020-01-01 → 2026-09-06: **361 trades either way, identical on
every field of every record**, 277.5s → 182.6s. Per-engine on 190,159 M5 bars, the seven this bot
reads cost 81.8% of the full stack.

🔴 **THIS SAID "PARITY GREEN" AND THE GATE HAD COMPARED NOTHING.** `engines/VANTAGE_XAUUSD,
15_e98ec.csv` is an export of the GAP engine's harness, not this bot's twin: no decision column, so
the diff skipped every field and printed `PARITY OK — 19636 bars compared`. **No SOS Fade strategy
export is on this machine, so this change has NO parity evidence** — the A/B above only says the
gated stack books what the ungated one does, never that either agrees with the Pine. A real run is
the strong check here (a wrongly gated engine moves a decision). The gate now refuses that file.

⚠ **A switch is a CLAIM about what this package reads, and the guard is
`backtest/tests/test_replay_engine_gates.py`** — it parses every module here and fails by name if
one starts reading a gated engine. **The failure it prevents is silent**: a gated engine hands back
`None`, and `None` read as *nothing happened this bar* is a bot refusing every setup with nothing
anywhere saying so. Rules and the measurement: `backtest/CLAUDE.md` → *An engine a strategy never
READS is never RUN*.

⚠ **It needs a PROMOTE to reach the live bot**, like everything else in this package — and it
changes no decision there either, only how long a warm-up takes.


## The gate says "cannot measure truncation" instead of "not truncated" (2026-09-10)

`export_truncation()` returns `Optional[int]`: **`None` = the export carries no bar-index column,
so there is no way to tell; `0` = measured, and complete; `>0` = measured, and this many warm-up
bars are missing.** The command prints the `None` case out loud before any verdict.

🔴 **`0` MEANT BOTH THINGS, AND *CANNOT MEASURE* IS WHAT AN ORDINARY EXPORT ACTUALLY IS.** Every
column the reading needs is a `dbg_*` diagnostic, present only when the diagnostic block is
exported — so on a normal export the old code returned 0, the caller printed nothing, and the
harness reported *this file is complete* about a file it had never inspected. **Rule 1, inside the
gate**, which is the one place it is most expensive: a `PARITY OK` rests on `--warmup` being past
whatever Pine warmed on, and this is the only thing that can say what that floor is.

🔴 **IT WAS CAUGHT BY A REAL LADDER, NOT BY A TEST.** The 2026-09-09 run on
`VANTAGE_XAUUSD, 15_53f52.csv` diverged at bar 293 at warm-ups 100 and 200 and was green at 500 and
1000 — and the file carried twelve `dbg_` columns while this function answered 0. **The floor had to
be found by trying warm-ups until the diff went green**, which is exactly the work this function
exists to remove.

🔴 **A SECOND DEFECT WAS FOUND WHILE FIXING THE FIRST, AND IT FAILS IN THE DANGEROUS DIRECTION.**
The presence test asked for ONE column and the measurement then summed over THREE, so an export
carrying a subset passed the test and was measured off that subset — reporting a gap SMALLER than
the file really has. **A gap read too small is what lets a cold engine be diffed and the result
called parity.** The list is now named once and both halves walk it.

⚠ **`None` rather than a raise.** The harness has something honest to say and no reason to stop:
exports with no diagnostic block diff perfectly well, they simply cannot vouch for their own
warm-up floor. Refusing them would take the gate away from every export on this machine.

**TESTED:** 6 in `tests/test_compare_strategy.py` — a measured zero still reads zero, a measured
gap reads the gap, no column and other-`dbg_`-columns-only both read `None`, the subset case, and
one asserting each of the three columns is enough on its own so the two lists cannot drift.

## 🔴 The gate REFUSES an export missing a column it compares (2026-09-10)

`missing_columns_refusal()`, called by `run_parity` before the replay: **an export lacking ANY column
the diff reads exits 2** — none of them reads *not an export of the twin*, some of them are named.
🔴 **The diff skipped every column an export lacked, so a file that was not the twin passed** (the
paragraph above), and a PARTIAL export passed the same way over whatever was left. ⚠ **Refused, not
narrowed** — `compare_bos.py`'s policy; today's twin plots every compared column, so an older export
is re-exported, never read around. The loop's skips are DELETED, so no dead branch reads as covered.
⚠ **Shared, not copied**: B-LEG's and the extreme leg's gates call it too. ⚠ **Its one way to backfire
is a diff column the Pine never plots** — every real export refused — so a test reads the twin's own
plot titles (`plot_titles()`, which follows a call wrapped across lines). ⚠ **Rule 13 on the
encoder**: its one column no real export carries is `cfg_poi_source` (the Pine input was reverted),
so the zone-source round trips test plumbing, not parity; a test names it as the only exemption.
**Tests:** 13 here, 24 in B-LEG's file, 2 in the extreme leg's; **18 mutations run, all red.**
Story: `HISTORY.md` → *A parity gate passed a file that was not its twin*.

## Its gap pins follow ITS Pine, and the engine default now happens to agree (2026-09-10)

The gap engine's default cap moved 8 → 7 to match the indicator, so this bot's pin of 7 now equals
the default — and the indicator's own 15m floor and close test now equal this bot's pins too. **The
pins stay.** They mirror `sos_fade_strategy.pine`, and two Pines agreeing today is a coincidence
the next indicator edit can undo in silence. `engine_config()`'s docstring said the engine default
was 6 and the indicator's 15m floor 0.04; both corrected. Comment-only; no value moved here.

## The gate ran on a fresh export, and that export is now COMMITTED (2026-09-10)

`compare_strategy.py` exits 0 on a fresh export of `sos_fade_strategy_export.pine` with **adding to
winners ON at the shipped sub-settings** — 20,220 M15 bars, 2025-11-02 → 2026-09-10 — on **every
one of 19,668 bars from a MEASURED warm-up of 468** (all 98 mismatches before it are the short-side
arm stage, state the chart carries in from before the export began). 8 trades close in the window,
+12.62R on the chart; **5 of them added, 13 adds in all, and the gate SEES them**: with adds forced
off in the Python it goes RED at the first trade that added (+2.40R against the chart's +2.59R).
✅ **Committed at `exports/golden/` — step 15 runs it on every clone**, and its manifest NAMES the
gate, because `tools/` holds two compare scripts. It REPLACED the same day's adds-OFF export
(8 trades, +10.63R): the live bot adds, and the OFF path stays covered by the B-LEG and BOS
goldens, which run this execution code with it off.
⚠ **Read what it RAN before quoting it.** The B leg, divergence arming and the no-gap fallback
were OFF, so it says NOTHING about them — nor about the re-entries, which are Python-only. Its
dead-market floor was 0.3 against the bot's 0.08.
