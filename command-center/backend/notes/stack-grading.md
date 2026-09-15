# Notes — Grading and stress-testing stacks, and promoting their settings

Stack stress tests, walk-forward and sensitivity over a stack, the sensitivity pool, copying graded settings onto bots, demo to live. Moved VERBATIM out of `command-center/backend/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## A stress test's settings can be copied onto a DEMO bot (2026-09-06)

`services/bot_settings_import.py` + two endpoints on `routers/bots.py`
(`GET`/`POST /bots/{bot}/settings-from-stress-test/{id}`). Aaron's pipeline is **backtest → stress
test → demo → live**, and this is the third hop. Before it, the only way to move settings from a
good result onto a bot was hand-editing that bot's instance config and restarting.

🔴 **ONE PLANNER, CALLED BY BOTH VERBS, AND THAT IS THE ENTIRE VALUE OF THE FEATURE.** The preview
and the apply build the list from the same call; the apply writes exactly `plan.changes`. Two code
paths that each assemble a list are two lists that can drift — invisibly, because nothing compares
them — and the reader has then approved a list describing something else. A test drives both verbs
and asserts the plans match.

🔴 **THE SOURCE IS A STRESS TEST, NOT A BACKTEST (Aaron's call).** A backtest is one path through
history. The stress test is what asks whether that result survives being shaken — reshuffled trade
order, held-out windows, and each setting nudged. **A knife-edge setting backtests beautifully and
cannot be told from a robust one by its equity curve.** ⚠ **It costs nothing in fidelity**: a stress
test carries no settings of its own, it reads its parent run's and perturbs COPIES into child runs,
so a button on either page writes identical values.

🔴 **DEMO ONLY, and that is what makes demo→live a real stage rather than the same button with two
labels.** It reads `BotReg.account_type`, which has no default and is validated — a fact about the
bot, not a naming convention. A live bot is refused (409) with the reason.

⚠ **A RUNNING bot is refused, for `set_bot_account`'s reason**: the bot read its config at startup,
so the write cannot reach the live process and the page would show settings it is not trading.

⚠ **It never reports the change as in effect.** `restart_required` is always True — exactly one
setting reaches a running bot without a restart and this writes many.

⚠ **`_only_declared` is IMPORTED from `bot_accounts`, never re-implemented.** It carries the
2026-09-04 incident where a bot was written a setting its strategy does not declare and refused to
start on every attempt. A dropped setting is NAMED, never silent.

⚠ **`_stress_test_was_graded` reads `grade`/`grade_reasons`.** `grade is None` after grading ran is
a first-class outcome (a ruleset stating no drawdown limit), so *not graded* must never render as
*passed* — nor as *failed*. ⚠ **There is no `graded_at` column**; an earlier draft read one.

⚠ **A weak grade, a symbol mismatch and a timeframe mismatch all WARN and none of them BLOCKS**
(Aaron's call). Blocking a low grade puts a legitimately good low-trade config out of reach, which
fights this repo's stated design intent. A timeframe that cannot be compared says so rather than
reporting a match.

⚠ **`untouched` is reported**: settings the bot pins that the run never mentions keep their values,
so the bot does NOT end up identical to the run. A page that cannot say that shows a partial copy
as a complete one.

⚠ **A no-op apply writes nothing, commits nothing and returns `applied: false`** — reporting
success there would claim a write that did not happen, and an empty commit is noise in a log two
people read.

**Tests:** `tests/test_bot_settings_import.py` (27). ⚠ **A fail-watch against HEAD is VACUOUS** —
the module did not exist — so non-vacuity is by **MUTATION: 20 written, 20 RUN, 20 killed.** Two
survived first and both are recorded in the file's own docstring: one was the HARNESS mutating the
wrong endpoint (`if _bot_is_running(bot_key):` appears twice in that router, and a first-occurrence
replace hit the account move), and one was a fixture whose bot and run carried the same key set, so
*write the plan* and *merge the run's dict* produced identical output. **A mutation that lands
somewhere else is not a surviving mutation, and it reads exactly like one.**

## A STACK can be graded — the combined book, and the target that had nowhere to point (2026-09-06)

Aaron's pipeline is **backtest → stress test → demo → live**, and he runs stacks: *"it doesn't
matter if it's a single strategy or a stack of two or more strategies … nothing should run on its
own and then come at numbers at the end. It should try to test it as though this is the whole
strategy set that's been run on the account."* Everything below is the first two steps of making
that true. The pieces still missing are named at the end.

### 🔴 The shared account's own book was computed on every run and thrown away

`portfolio_runner._persist` kept each leg's trades, each leg's SOLO control, and the contention
log — and reduced the ACCOUNT's own trade stream to two scalars, `combined_trades` and
`combined_r`. **So the one thing a shared stack exists to produce did not survive to disk**, and
nothing downstream could grade a stack because there was nothing to grade. It is now written
through the SAME `build_results` every other book in this app goes through
(`combined_equity_curve.json`, `combined_daily_pnl.json`, `combined_kpis` on the summary), read
back by `portfolio_runner.combined_book`.

⚠ **`run.trades` arrives grouped BY LEG, not in time order** — every leg A trade, then every leg B
trade. `build_equity_curve` sorts on exit time itself, which is the ONLY reason handing it that
list is safe. **Do not pass it to anything that walks it as given.**

⚠ **A second curve builder here would be a second answer to *what did this account do*.** The
equity contract — one point per closed trade, in exit order, anchored on the opening balance — is
what the stress tester, the grader and the chart all read.

⚠ **`combined_curve_agrees` is a CHECK the artefact makes rather than a number it reports.** The
curve is walked from the opening balance over the trades; the account tracked its balance live.
A disagreement means the account applied something no trade carries — a defect in the seam, not a
rounding difference. Same idea as `neutral` beside it.

⚠ **`combined_book` returning `([], [])` means NOT STORED, never *this account made nothing*.** A
screen has no shared account for a book to belong to, and every stack replayed before this date has
none either. **There is no backfill** — recovering it means replaying the stack.

⚠ **`_stack_point_value` REFUSES legs that disagree on contract size** rather than taking whichever
leg was last. A stack is one instrument, so disagreement means the account's book would be priced
at one leg's contract while carrying the other leg's trades.

### 🔴 `stress_tests.run_id` was NOT NULL, so a stack had nowhere to point

A stress test grades a RESULT, and a result is now either a single strategy's run or a whole stack
on one shared account. The row carries `run_id` **or** `stack_id`, and **the database enforces
exactly one** (`CHECK ((run_id IS NULL) <> (stack_id IS NULL))`).

🔴 **Pointing a stack's test at its FIRST LEG would have satisfied the foreign key** and named one
strategy as the subject of a portfolio result — a field that reads as answered and is not. That is
the shape rule 1 keeps catching, in a column rather than in a probe.

⚠ **`_migrate_stress_tests_gradable_target` READS ITS COLUMN LIST OFF THE TABLE, never types it.**
This file already records what typing it costs: the `optimizations` rebuild above lists its columns
by hand and silently DROPPED the ones somebody forgot, on every fresh database. Every column on
`stress_tests` past `error_message` arrived by a later migration, so a hand-written list here would
have rotted the same way. Only `run_id`'s NOT NULL is lifted; every other constraint and default is
carried across exactly as the table states it.

🔴 **The stack INDEX may not live in the main schema script.** That script also runs against a
database whose `stress_tests` predates the column — `CREATE TABLE IF NOT EXISTS` does not alter an
existing table — and an index on a missing column kills the whole script and **every migration
below it**. It is asserted in the migration instead, on the rebuild path AND on the
already-migrated early return, or a fresh database would never get it.

⚠ **Both paths were checked, and this section is the reason:** a schema change declared in only one
of them works perfectly on the machine that ran the migration and is broken on every fresh clone.

**Tests:** `tests/test_gradable_target.py` (9) + 6 in `tests/test_shared_stack.py`. ⚠ **A
fail-watch is vacuous for a column that did not exist**, so non-vacuity is by **MUTATION: 12
written, 12 RUN, 12 killed** — the CHECK removed from each of the two paths in turn, the rebuild
lifting every NOT NULL, the column list hardcoded, the index dropped from the early return, the
curve's exit-order sort, the balance cross-check pinned true, the contract-size refusal, the
canonical Sharpe, and the book not written at all.

🔴 **THE FIRST FIXTURE HERE WAS THINNER THAN ANY REAL MACHINE, AND IT READ AS A BUG IN THE CODE
UNDER TEST.** A hand-written *old* `stress_tests` omitted columns a later migration in `init_db`
needs, so that migration raised and the failure pointed at the rebuild. `_downgrade` now DERIVES
the old shape from the table that is actually there. **A fixture less capable than production
describes a system you do not have** — and here it accused the right code of the fixture's fault.

### What is NOT built yet, so nobody reads this as finished

✅ **ALL FOUR OF THESE LANDED, 2026-09-06 → 2026-09-07, and the list is kept as a record of the
order rather than as open work.** A stress test can be created against a stack (`services/
gradable.py`); walk-forward replays the whole stack per window; sensitivity replays it per shift;
and a graded stack's settings copy onto its bots. ⚠ **Read the sections below for the rules — this
list is history, not status.**

## A STACK can now be stress tested — `services/gradable.py` (2026-09-06)

The reshuffle half of the plan. Everything downstream of a stress test used to read a
`backtest_runs` row directly, so a stack — which has no such row of its own — could not be graded.

🔴 **ONE resolver answers *what am I grading*, and BOTH the endpoint and the background task ask
it.** The endpoint asks to decide a status code; the task asks to decide what to read. Two places
answering that independently is precisely how a pre-flight and a run came to disagree about which
bar feeds a backtest loads (`run_feeds.py`, written for that defect one layer down). Here the cost
would be a test refused on one side and started on the other, or graded against a window it never
replayed.

⚠ **The task resolves off the ROW, never off an id handed to it.** The row is the record of what
was requested; a task told separately can grade something the row does not name.

⚠ **`NotGradable` carries its own HTTP status.** Only the resolver knows whether it just decided
*no such stack* (404) or *this stack is a screen* (400), and a router inferring it would report one
as the other.

⚠ **A SCREEN is refused, by name.** There every leg traded its own full account with nothing able
to block anything, so the combined figure is N standalone runs added up — an UPPER BOUND. Grading
it would put a letter on a result no account can produce, which is worse than refusing **because it
looks like an answer**.

⚠ **A stack with no combined book is refused with the FIX in the sentence** (*re-run the stack*),
never reported as an empty result — which reads as an account that never traded. Every stack
replayed before 2026-09-06 is that stack, and there is no backfill.

⚠ **The runner is READ OFF THE LEGS, not asserted.** A stack is python-only by construction; the
day that stops being true this refuses rather than filing an MT5 leg under the python platform
lock. Legs that disagree are refused.

⚠ **Each leg carries ITS OWN frame**, since a leg has named one since 2026-09-03. Reading the
stack's fallback for every leg describes a leg on a timeframe it was never replayed on.

🔴 **WALK-FORWARD AND SENSITIVITY ARE REFUSED FOR A STACK, and that refusal is the feature.**
Neither is built for one, and both would replay a SINGLE LEG and report the answer as the whole
account's. The endpoint refuses up front; both phase functions refuse again as a backstop **and say
the true reason** — falling through to their existing *"Source run not found"* would send the
reader looking for a run nobody deleted.

⚠ **The trade floor counts the COMBINED book, and that is Aaron's design rather than a loophole.**
Sample size arrives at the PORTFOLIO level, so two legs that each trade too rarely to grade alone
clear the 100 floor together — one account's real trade history, not a trade count bought by
loosening a filter.

⚠ **The Telegram grade alert is named off the TARGET.** A stack has no run row, and naming it after
its first leg would credit one strategy with a whole account's grade.

⚠ **`_apply_grid_sensitivity_if_available` refuses a stack BY NAME rather than relying on
`get_run(None)` returning None** — which it does, measured. A branch that is correct by accident is
one the next edit breaks in silence.

⚠ **This endpoint deliberately does NOT call `refuse_if_needs_source`**, and the AST sweep in
`test_recovery_leg_wiring.py` flagged it the moment the code read a strategy id. It is the decision
`_source_guard.py` already records — a stress test acts on a result that ALREADY EXISTS, and no run
of a parentless rule can be created once every creation path refuses one. **For a stack the guard
would be actively wrong**: a stack may legitimately hold a loss-recovery leg, which is the case that
leg was built for. The endpoint reads the strategy off the resolved target instead of looking it up
again — one read of one fact, which is what stopped the sweep matching.

⚠ **`StressTest.run_id` is Optional and `stack_id` is DECLARED.** A stack row carries `run_id =
None`, and a required field would make the whole row unserialisable — a 500 on the list endpoint,
not a missing field. An undeclared `stack_id` would be dropped in silence, the trap `entry_ms`,
`exit_ms`, `favorable`/`adverse` and `r` each hit on this same model.

**Tests:** `tests/test_gradable_resolver.py` (16). ⚠ **A fail-watch is vacuous — the module did not
exist — so non-vacuity is by MUTATION: 13 written, 13 RUN, 13 killed.**

🔴 **TWO SURVIVED FIRST AND BOTH WERE THE TESTS, NOT THE HARNESS.** One asserted only that the
resolver RAISED when neither target was named — and with the guard weakened, naming neither falls
through to `_from_run("")`, which raises the same class saying *Run not found*. **A refusal for the
wrong reason passes a test that only asks whether it refused.** The other seeded legs with no
equity curve of their own, so *resolve the account's book* and *resolve the first leg's book*
returned the identical path and the swap could not be detected — **a fixture whose two behaviours
cannot produce different output is not testing the thing it names**, the same shape as the
settings-import fixture four sections up.

### What is still missing

✅ **Walk-forward** (2026-09-06), ✅ **sensitivity** (2026-09-07) and ✅ **the settings copy onto
bots** (2026-09-07) all landed — see their own sections below.

## Walk-forward over a STACK — the whole stack per window, on a fresh account (2026-09-06)

`stress_tester._run_stack_walk_forward` + `portfolio_runner.replay_window`. Dispatched from
`run_walk_forward_task` before anything resolves a source run, because a stack does not have one.

🔴 **EVERY LEG RUNS TOGETHER IN EVERY WINDOW, with the risk budget live.** Replaying the legs
separately and adding their windows up would drop contention in the one place the answer is meant
to be hardest, and would not be a portfolio result at all.

🔴 **EVERY WINDOW STARTS FROM THE SAME OPENING BALANCE (Aaron's call).** `account_size` is not
carried forward, so a late window is not flattered by everything the account made before it, and
the in-sample / out-of-sample halves of one window stay directly comparable — the only comparison
this phase draws. A compounded balance makes the last window's dollars enormous and the comparison
meaningless, which is why every figure downstream is read in risk multiples and percentages.

⚠ **It spawns NO child runs.** A stack replays in this process, so a window is a function call
rather than a job on a terminal — no platform to hold, nothing to poll, and a window that raises is
caught here and recorded as a failed period exactly as a failed child backtest is.

🔴 **`_build_and_run` was SPLIT OUT of `_execute` for this, and it persists nothing and knows no
`stack_id`.** Every window is a throwaway measurement; writing one would overwrite the stack's own
book with three months of its history. Progress and cancellation arrive as CALLBACKS — a function
that reached for `_set_progress(stack_id, …)` itself could not be reused without inventing a stack
id for a window that is not a stack.

⚠ **A window replays with the SOLO CONTROLS OFF.** They answer *what would this leg have made
alone*, which is a question about the launched stack — so a window costs one replay instead of
`1 + N`.

🔴 **`_finish_walk_forward` is SHARED by the single-run and stack paths, never copied.** Every
exclusion rule in it is a judgement about when `1 - OOS/IS` means anything, both paths write the
same `walk_forward_degradation`, and both are read against the same grading thresholds — so a
second copy would let a stack be scored under a rule a run is not. Same argument that made
sensitivity's two paths share a metric.

⚠ **A failed half leaves its keys ABSENT, which is the single-run path's own convention** — the
scorer reads them with `.get()`, so absent excludes the window from the average. What must never
happen is a real `0.0`, which passes through as a measurement and draws a bar on the chart for a
period nothing was measured on.

✅ **A STACK HOLDING A DEPENDENT LEG REPLAYS SINCE 2026-09-07, and until then it was refused at
the request.** `LegSpec.source` — the leg whose closed trades a loss-recovery rule arms off — was
passed at launch and never written down, so a window replay would have rebuilt that leg with
nothing to arm off: an EMPTY book landing in the summary looking exactly like a rule that found no
setups, on a whole account graded one leg short. It is stored on the member row now; the rules are
in *A dependent leg's parent is stored* below. ⚠ **A stack launched BEFORE that column is still
refused**, because it has the dependency and cannot state it.

⚠ **SENSITIVITY is still refused for a stack**, and for a different reason: a shift has no way to
name WHICH LEG's setting it is nudging, so it would perturb one strategy and report the answer as
the whole account's.

**Tests:** `tests/test_gradable_resolver.py` (23 now). ⚠ **Non-vacuity by MUTATION: 9 written, 9
RUN, 9 killed** — the dispatch removed, only the first leg replayed, the balance carried forward,
a raising window killing the phase, the cancellation check dropped, every-window-failed reported
clean, the dependent-leg refusal dropped, sensitivity allowed, and walk-forward refused again.

🔴 **ONE SURVIVED FIRST AND IT WAS THE HARNESS.** `summary.append(window_data)` appears in BOTH
walk-forward paths and the single-run one comes first in the file, so a first-occurrence replace
mutated the wrong function — **a mutation that lands somewhere else is not a surviving mutation,
and it reads exactly like one.** This is the second time in two days that trap has been hit here
(the settings-import harness mutated the wrong endpoint the same way). **Anchor a mutation on
something unique to the function you mean.**

⚠ **A fixture bug also read as a code failure**: the window book generated `2024-01-40`. Same shape
as the thin `stress_tests` fixture two sections up — **when a new test fails, check the fixture
before the code.**

---

## Sensitivity over a STACK — one setting nudged, the WHOLE stack replayed (2026-09-07)

`services/stress_tester.py` → `_run_stack_sensitivity`, `stack_sensitivity_plan`,
`stack_shift_applied`, `stack_sensitivity_preview`, `_finish_sensitivity`.

**The last of the three deep phases to stop being single-strategy.** Monte Carlo and grading
already read the combined book; walk-forward learned to replay the whole stack per window on
2026-09-06; sensitivity was refused for a stack until this change, with the honest reason that a
shift could not say which leg's setting it was nudging.

🔴 **NUDGING ONE SETTING AND REPLAYING THE ENTIRE STACK IS WHAT MAKES THE ANSWER A PORTFOLIO
ANSWER.** The other legs are in there competing for the same risk budget for the whole replay, so
the profit factor that comes back is the ACCOUNT's under that nudge — not the leg's. Perturbing a
leg on its own and adding the answers up measures a strategy and labels it a stack, which is
exactly what Aaron ruled out: *"nothing should run on its own and then come at numbers at the
end."*

🔴 **THE STACK'S OWN SETTINGS ARE SPENT FIRST — the account risk budget, the starting balance,
then the smallest position it will still take.** Those three are the only settings that belong to
the ACCOUNT rather than to a strategy, so they are the ones a portfolio answer is actually about.
After them the legs' settings take TURNS: a flat pass in leg order spends the whole budget on the
first leg when it carries twenty settings and the second carries three, and then reports the
account as though the second leg had no settings at all.

🔴 **THE BASELINE IS REPLAYED HERE, THROUGH THE SAME FUNCTION, rather than read off the stack's
stored combined book.** Degradation divides a shifted profit factor by the baseline's, so a
baseline measured on a different code path reports the path difference as a setting's fragility —
this repo's signature defect, and the reason every child run already carries its parent's
measurement fields. The stored book is *close*, and close is what makes it dangerous. It costs one
extra replay and removes the whole class of error.

⚠ **EVERY SHIFT IS A FULL STACK REPLAY AND THEY RUN ONE AT A TIME.** A single strategy's shifts fan
across every core through the optimizer's sweep; a stack cannot use that path — it replays several
legs on one merged clock in this process — so the cost is one whole replay per shift, serial.
`_STACK_SENS_MAX_REPLAYS` is **60**, about the same wait the single-run phase shipped with before
it was parallelised (MEASURED there: 69s per 6.6-year M15 replay). **It is a CAP, not a target, and
what it drops is NAMED** — in the coverage record, and in a warning on the trigger response so the
reader can drop a leg and re-run before spending the hour rather than after.

⚠ **The budget is spent a SETTING at a time, never a shift at a time**, and it STOPS rather than
skipping ahead to a cheaper setting. Half a setting's shifts would put a max degradation on the
record measured over a probe nobody chose; squeezing in a later setting would quietly reorder the
priority the plan exists to enforce, with nothing on screen to show it happened.

✅ **`_finish_sensitivity` is SHARED by the single-run path and the stack path, never copied** —
same move as `_finish_walk_forward` the day before. Both write `sensitivity_max_degradation` and
are read against the same grading thresholds, so a second copy would let a stack be scored under a
rule a single run is not.

✅ **`sensitivity_shifts` is now the one shift list, read by both paths and by the time estimate.**
It was a COUNT in one place and a literal list in another, held together by a comment reading
*"Matches SHIFTS below"* — a claim about code somewhere else rather than a mechanism (rule 7).
⚠ **A stack is probed with the SAME shifts as a single run, and that is not a free choice**: the
±25% pair is usually the one that produces the maximum, so probing a stack with ±10% only to buy
back replays would make every stack grade EASIER than every run, on one letter scale, silently.

⚠ **No child runs are spawned, and none should be** — a stack replay is a function call in this
process, not a job on a terminal, and manufacturing a run row would put a backtest in the Runs
lineage that nobody launched. ✅ **The BOOK is stored instead since 2026-09-07**, so a shift can be
opened without inventing a row: *A stack shift keeps its own book* below.

✅ **A stack holding a loss-recovery leg is sensitivity-testable since 2026-09-07**, through the
same rebuild walk-forward uses — both phases share `gradable.rebuild_legs`, so neither can accept a
stack the other refuses. ⚠ **A stack launched before the parent was stored is still refused**: every
shift would otherwise be measured on an account quietly one strategy short.

⚠ **Two legs of the same strategy are refused**, because a shift is recorded under
`<strategy>.<setting>` and the second would overwrite the first in silence. The replay itself
already requires unique leg names so the app cannot build one today — it is asked here because the
day it can, the failure is invisible.

⚠ **The estimate is built by RUNNING THE PLANNER**, not by multiplying a param count by a shift
count, so the modal cannot quote an experiment other than the one about to run. The per-replay
figure comes from the legs' OWN measured durations added together and is labelled a floor — the
shared replay also carries the risk budget, the contention log and a merged clock the solo runs
never had.

🔴 **ONE TEST HERE WAS WRITTEN, PASSED, AND COULD NOT HAVE FAILED — caught by asking what its
mutation would do BEFORE running it, which is the only reason it is not still green and worthless.**
It asserted that a stack setting the stack never recorded stays out of the PLAN. It does — whether
the missing value is left as `None` (refused as non-numeric) or substituted with 0 (dropped as a
no-op). **Two behaviours that cannot produce different output are not two behaviours, and a test
that cannot tell them apart is describing a system where the thing under test does nothing.** Same
shape as the period-window cases written against a scale of exactly 1. It now asserts the setting is
absent from the COVERAGE RECORD as well, where the substitution shows up as
`account_size +10% (=0.0)` — a setting reading as probed and flat when it was never set at all — and
the mutation kills it.

---

## Grading judges the COMBINED ACCOUNT, and a stack's test is a first-class row (2026-09-07)

Aaron: *"For grading, it's the combined account. You're not taking strategies, you're not running
them separately and treating them as such."*

✅ **`compute_grade` already did, and that was CHECKED rather than assumed.** It reads only the
stress-test row's own Monte Carlo fields plus the walk-forward and sensitivity summaries — and for
a stack all three are the combined account's: Monte Carlo runs on the combined equity curve the
resolver hands it, walk-forward replays the whole stack per window, sensitivity replays the whole
stack per nudge. There is no per-leg input to that function and there never was.

🔴 **WHAT WAS BROKEN WAS EVERYTHING AROUND IT, AND BOTH DEFECTS WERE MEASURED RATHER THAN READ.**
Two queries joined `backtest_runs` on `run_id` to reach a stress test's strategy and runner — and a
stack-targeted row does not carry one, so an INNER JOIN dropped it in silence:

```
list_stress_tests()          -> ['st_run']                      # the stack's test, missing entirely
running_stress_test_markets  -> {futures: False, forex: False}  # with a stack test RUNNING
```

**The second is the severe one.** `POST /stress-tests/run` refuses when a market is locked, so with
the lock silently open a second stress test could start beside a running stack one — on one box
driving one terminal. **A lock derived by joining through a nullable key is a lock that quietly
opens for whatever that key cannot reach.**

✅ **Two columns on the row fix both, and each is written at CREATION off the resolved target.**
`stress_tests.runner` is the platform this test HOLDS; `stress_tests.target_label` is what it is
grading, in words.

- ⚠ **`runner` on the row is more correct than the join was, for a single run too.** It records the
  platform the test was STARTED on, which a re-scanned strategy row cannot move under a live test.
  The join is kept as the fallback for rows written before the column, so a test in flight across
  the upgrade still locks.
- ⚠ **`target_label` is the LAST fallback in the list query**, so a single run keeps its LIVE
  strategy name and a rename still shows through. A stack has no live name to read — its name is
  its legs joined — and that string is built once in `services/gradable.py` and stored, never
  rebuilt in SQL.
- ⚠ **A stack's `strategy_id` stays NULL in the list, deliberately.** A stack is not a strategy,
  and filling it with a leg's id names one strategy as the subject of an account's result — the
  same thing the nullable `run_id` exists to prevent one layer down.
- ⚠ **A stack contributes no run id to the lock's id list — it has none — but it DOES set its
  market.** The list is what the page points at to name the blocking run; the booleans are the
  lock, and they must not depend on that list being non-empty.
- ⚠ **Both columns are declared in the migration list AND in the `stress_tests` CREATE TABLE**, per
  this file's standing note. The rebuild migration derives its column list from the table, so it
  carries them without being told.
- ⚠ **The cancel endpoint reads the platform off the row too.** Looking it up through the run meant
  a stack — which has none — resolved to NinjaTrader.
- 🔴 **The LIST never selected `st.stack_id` (fixed 2026-09-10)** — declared on the model, assigned
  by nothing, so every row reached the browser saying `null`. It is selected now, and
  `GET /stress-tests?stack_id=` filters on it (symmetric with `run_id`, newest first), because the
  stack's stress-test window reads it to default to the ruleset that stack was last graded against.
  3 tests in `test_stack_stress_visibility.py`, 4 mutations run, 4 killed.

✅ **`best_grades_by_strategy` EXCLUDES a stack explicitly, and that exclusion is a forward guard
rather than a fix.** A stack's grade judges a whole strategy set sharing one balance and one risk
budget; hanging that letter on one leg claims evidence about that strategy which nothing measured.
🔴 **The right answer already came out — by accident.** A stack row's `run_id` is NULL, so the
inner join dropped it. **The next person to widen that query to a LEFT JOIN, or to reach for the
stack's legs, gets no warning from an accident**, so the rule is now written and tested.

⚠ **The standing lesson is about DERIVED identity, and it is the third time this file has recorded
it.** When a row gains a second way of being addressed, every query that reached its old address by
a join has to be asked whether it can still find it — and the ones that cannot will answer
confidently, with a shorter list and an open lock.

**Tests:** `tests/test_stack_stress_visibility.py` (10). ⚠ **Non-vacuity by MUTATION: 10 written,
10 RUN, 10 killed.** Eight were also watched RED against HEAD; the two that were not are labelled
forward guards in their own docstrings — the grade exclusion (right by accident at HEAD) and the
null run-id in the lock list.

---

## A graded STACK's settings, onto the bots that run its legs (2026-09-07)

`services/stack_settings_import.py` + two endpoints on `routers/bots.py`
(`GET`/`POST /bots/stack-settings-from-stress-test/{id}`). The demo hop of Aaron's pipeline, for
the thing he actually runs: *"it doesn't matter if it's a single strategy or a stack of two or
more strategies."* Before this, the single-bot control moved one strategy to one bot and a stack
had to be hand-assembled bot by bot.

🔴 **ALL OR NOTHING, and that is the whole feature rather than a safety flourish.** A
shared-account stack is a measurement of several strategies competing for ONE balance and ONE
risk budget. Writing three of its four legs produces a strategy set nobody has measured — **and
it reads as a completed copy, because every bot it did reach is correct.** A plan is either
`blocked` with a sentence or it is complete; there is no partial plan to apply.

🔴 **THE PER-LEG WORK IS `bot_settings_import.plan_import`, CALLED ONCE PER LEG AND NEVER
RE-IMPLEMENTED.** A second copy of *which settings move* is a second answer, and the copy is the
one that goes stale. What this module adds is the half a per-bot planner cannot see:

- every leg must land on a **DEMO** bot, and they must all be on the **same broker account** —
  two bots on two accounts is not the stack that was replayed, and the contention behind every
  number in it does not exist there;
- the account's **RISK BUDGET is written too**, because the stack's own figures were produced
  under it. ⚠ **To every bot on the account, not just the legs**: the ceiling is stored per bot
  and the account's cap is whatever its bots agree on, so one left behind leaves the account with
  two of them — the state `bot_accounts` refuses to report a cap for at all;
- after everything is written the per-trade shares must still FIT under that budget
  (`share_overflow`), or the bots quietly stop being the bots that were measured. ⚠ Since
  2026-09-15 that refuses only an unreadable share or ONE bot above the whole budget; shares that
  add up past it are a warning (`accounts-risk.md` → *Shares may add up past the cap*).

🔴 **THE SHARE CHECK READS THE PROPOSED SHARES, NEVER TODAY'S.** Checking the current state
passes every write that CREATES the problem and refuses every write that FIXES it — the same rule
`bot_accounts` already records for a bot being moved onto an account. ⚠ **A bot on the account
that is not a leg keeps its own share and still counts**: it spends the budget whether or not the
stack mentions it. It is WARNED about rather than refused — benching it is the reader's call —
but its share is in the sum.

⚠ **An unreadable config refuses the whole copy, and it is checked FIRST for a reason found by
test.** An unreadable config states no strategy package, so the leg's own bot silently fails to
MATCH and the refusal came back as *"no registered bot runs extreme_leg"* — sending the reader to
register a bot that already exists. It cannot be narrowed to the legs either: an unreadable bot
may be a stranger sharing the account, and then its share and its ceiling are both unknown.

⚠ **A leg is matched on the bot's own `strategy_package`**, which IS the lab's strategy id for a
python package — never on a key-name convention. `sos_fade` → `sos_fade_demo` is a rule living in
a string, and it breaks the first time a bot is named differently or a second bot runs one
strategy. Two matches REFUSE rather than picking one.

⚠ **`stack_risk_cap_pct = None` writes NOTHING to the ceiling and says so.** `None` means the
stack recorded no budget, not that it recorded an absence of one; clearing a live account's
ceiling because a stored figure was missing is the opposite of what an absent value means.

⚠ **Every warning is LOUD and none refuses** — an ungraded test, a weak grade, a symbol or
timeframe mismatch — and each leg's own warnings are NAMED with the bot they belong to. Rolled
into one list a reader cannot tell which of four bots is on the wrong chart.

⚠ **Every file goes into ONE commit**, and the writes are staged before any of them lands. A
stack is a set of bots measured together; two commits is two states of the fleet, and the one in
between was never measured.

⚠ **`_running_bot_keys` is ONE round trip for the fleet**, not `_bot_is_running` per bot — the
fan-out shape this backend has already paid for twice. **An unreadable process list answers EVERY
bot**, which is the opposite of the single-bot helper's fallback and right for the opposite
reason: there the caller escalates to a kill, here it WRITES, and refusing to write is
recoverable while writing under a running bot leaves a page describing settings nothing trades.

⚠ **The route resolves the stack through `gradable.resolve`, the same call the stress test itself
was started through**, so it cannot accept a target that one refuses — a SCREEN in particular,
where every leg traded its own full account and nothing could block anything.

⚠ **It does NOT deploy code and does NOT restart**, and `restart_required` is always True.

**Tests:** `tests/test_stack_settings_import.py` (27). ⚠ **A fail-watch against HEAD is VACUOUS**
— none of it existed — so non-vacuity is by MUTATION.

🔴 **TWO OF THE FAILURES DURING THE BUILD WERE THE FIXTURE, NOT THE CODE, AND BOTH WERE THE SAME
MISTAKE: an account the stack itself could not have been replayed on.** 5% legs under an 8%
ceiling is over-subscribed, so every apply was correctly refused — a premise that quietly turned
two tests into a third copy of the share check. **When a new test fails, check the fixture before
the code**; this file has now hit it twice, as has `test_gradable_resolver.py`.

⚠ **Two endpoint tests were STRENGTHENED after asking what their mutation would do.** Comparing
the preview's response to the apply's passes against an apply that plans correctly and then
WRITES something else — both build their response from their own plan — so it now asserts what
landed in each config. And counting commits passes against one commit staging a single bot, so it
now asserts the commit carries every written file.

🔴 **ONE MUTATION SURVIVED, AND IT WAS THE TEST ASKING TOO LITTLE.** With the stack-level demo
check narrowed to the first leg, a live bot falls through to the per-leg planner — which refuses
it too — and the test's assertion (the message names the bot and the word *demo*) was satisfied
by that second refusal. **A refusal for a different reason passes a test that only asks whether
it refused**, which is the trap `test_gradable_resolver.py` recorded on its own exactly-one-target
case a day earlier. The per-leg planner IS the intended backstop and stays; what the test pins now
is that the STACK-level check gets there first, so the reader is told the whole set is barred
rather than reading it as one leg's problem.

---

## DEMO → LIVE: the whole proven set, or none of it (2026-09-07)

`services/go_live.py` + two endpoints on `routers/bots.py` (`POST /bots/go-live/preview`,
`POST /bots/go-live`). The last hop of Aaron's pipeline, and the only write in this app that puts
a strategy on real money.

🔴 **ALL OR NOTHING, for the reason the stack settings copy is.** A strategy set is a measurement
of several strategies competing for ONE balance and ONE risk budget. Two of three bots on the live
account is a set nobody has ever run — **and it reads as a finished promotion, because every bot it
did move is correct.**

🔴 **THERE IS NO MINIMUM DEMO RECORD, AND THAT IS A DECISION** (Aaron, 2026-09-06: *"There's no
minimum to go from demo to live. That's discretionary."*). So the plan REPORTS what each bot did on
demo — closed trades, realised R, wins and losses, and the span of the record — and refuses on none
of it. ⚠ **A bot with no ledger reads *no record reached this machine*, never *zero trades***;
`bot_earnings` already refuses to collapse those two and this may not undo it one layer up. The
warning for such a bot says NO DEMO EVIDENCE in as many words, because the alternative is a set
going live on a sibling's record.

**What it refuses on is the ACCOUNT, not the evidence:**

- 🔴 **The destination's REGISTRY entry has to say `live`.** Going "live" onto a demo account is a
  no-op wearing the word, and the account registry is the one place that states what an account IS
  — not the account number, and not the bot's name. It must also be registered at all (nothing
  else knows its server, its terminal or its symbol suffix) and have a terminal logged into it.
- **Every bot has to be on ONE demo account today**, which is the set that was proven together.
- 🔴 **A bot LEFT BEHIND on that demo account is REFUSED, not warned.** The whole claim being
  promoted is that these strategies were measured competing for one balance; a leg that stays
  behind means the thing that ran on demo is not the thing going live. It is the only check here
  that fires on a bot nobody asked to move.
- **Nothing may be RUNNING.** A bot reads its config at startup, so a moved config on a running bot
  means the page shows a live account while the process trades the demo one.
- **The shares still have to fit** under the budget the set arrives with.

🔴 **THE RISK BUDGET IS CARRIED, NOT RE-DERIVED, and this is the trap the module exists for.**
`bot_accounts.assign_plan` writes `account_risk_cap_pct = None` for the FIRST bot on an account —
correct for one bot joining an empty account, and catastrophic for a set: moved one at a time,
**every member looks like the first**, so a proven set lands on a live account UNCAPPED. The budget
is written explicitly here, on every bot, and `assign_plan`'s own *"starts UNCAPPED"* note is
dropped when it is — a note contradicting the fields beside it is worse than no note.

⚠ **A populated destination's budget WINS.** A live account already carrying bots has a ceiling
those bots agreed on, and arrivals adopt it; the alternative is the set rewriting a ceiling on an
account it has never traded, and `live_config._assert_account_cap_agrees` then refuses every bot
there at its next restart. Bots on the destination that DISAGREE, or one whose config cannot be
read, refuse the promotion outright — there is nothing safe to adopt.

⚠ **An arriving bot keeps its OWN per-trade share.** This moves an account, not a setting: a
promotion that quietly re-sized the strategies would be promoting something other than what was
proven. If the shares do not fit, that is a refusal to read, not a number to adjust.

🔴 **A TYPED CONFIRMATION THAT NAMES THE ACCOUNT.** `confirmation_phrase` returns `GO LIVE
<account>`, compared exactly. A fixed word like CONFIRM is a reflex — typed the same way whichever
preview is on screen, so it proves the button was pressed and nothing else. An account number can
only be typed by somebody reading THIS preview, so a confirmation pasted from a different one
fails. ⚠ **The plan is rebuilt from live state on the apply**, so the phrase is compared against
what is true now, not against a constant.

⚠ **The password check is a DEFINITE no only.** `_accounts_with_a_password()` answers `None` when
the VPS could not be asked, and refusing on that sends the reader to re-enter a credential that is
already there. It lives in the router because it needs the box; the planner is pure.

⚠ **Every file goes into ONE commit**, staged before any of them lands, and the promotion is
ANNOUNCED on Telegram. This is the one event on this box where a config write changes whose money
is at risk, and the person who did not press the button is the one who most needs to know.

⚠ **Nothing is started.** Every bot in the set is stopped (a running one is refused) and stays
stopped; `restart_required` is always True. It does NOT deploy code either — that stays a separate
deliberate step.

🔴 **Warnings carry only what needs a decision, and name bots as the page does (2026-09-10).** The
screen read as a wall — every bot's record restated, a bookkeeping line per skipped setting, and
bot KEYS in every sentence. So: a traded bot's record travels on its MOVE and is not repeated; *no
record* and *could not be read* stay; every sentence uses the display name. ⚠ **`AssignPlan` now
splits `notes` (a hazard) from `info` (bookkeeping — a setting the strategy does not declare)**, and
`info` is deliberately NOT carried onto a move. 🔴 **The single-bot move serves both APART since
2026-09-11** (`notes` and `info` on `PATCH /bots/{bot}/account`): joined, the bookkeeping reached the
Bots page as a yellow warning naming a config field on every add. The page raises `notes` only.
⚠ **When nothing is unusual the list is EMPTY** — pinned by
`test_a_CLEAN_promotion_carries_NO_warnings`, because a warning on every promotion is one nobody reads.

### 🔴 The demo/live label is DERIVED now, or step 8 would have made the fleet lie

`_account_type_of` resolves a bot's account type from the account its config names (and the account
its process last reported), looked up in the account registry, with `BotReg.account_type` as the
FALLBACK.

**`BotReg.account_type` is a hardcoded Python fact, and the moment a bot can be MOVED onto a live
account from this app that hardcode becomes a second answer that drifts** — in the one direction
the registry's own comment names as dangerous. A promoted bot would have gone on rendering as demo:
no amber tint, absent from the *"N of these are LIVE accounts"* warning on every fleet dialog, wrong
in the demo/live filter and in the Overview's live-bot count. **Worse, both settings imports refuse
anything but a demo bot — so a stale label turns the one guard there that protects real money into
a comment.**

⚠ **LIVE WINS when the config and the running process disagree, and the disagreement is a real
state rather than a fault.** Between the promotion write and the restart, both are true of
something. The tint's job is to say this bot touches real money, so it goes amber the moment ANY
evidence says live and only goes back when nothing does. Under-reporting live is the failure this
may never have.

⚠ **An unreadable account registry, or an account nobody registered, falls back to the hardcode** —
never to `"demo"`. Cannot ask is not an answer, and here the reassuring answer is the dangerous one.
A benched bot keeps the hardcode too, which is right: a bot on no account has no account to derive
a kind from.

⚠ **`_registered_kinds()` is read ONCE per snapshot**, not once per bot — two rows in one response
may never disagree about what kind of account a number is.

🔴 **`test_bot_registry.py` ALREADY ASSERTED THIS FIELD AND COULD NOT HAVE CAUGHT THE REGRESSION.**
It compares each row to `reg.account_type`, and every registered bot is demo-registered on a demo
account — so derived and hardcoded give the same answer there and the test passes either way. Two
fallback tests written here had the identical flaw and were caught by mutation: against a
demo-registered bot, *"fell back to the hardcode"* and *"answered demo"* are the same assertion.
Both now use a bot registered LIVE, where the two differ. **Check that a test's inputs can
distinguish the behaviours it names** — third time in a week.

**Tests:** `tests/test_go_live.py` (49). ⚠ **A fail-watch against HEAD is VACUOUS** — the module did
not exist — so non-vacuity is by **MUTATION: 52 written, 52 RUN, 52 killed.**

🔴 **One survivor, and it was the assertion depending on ITERATION ORDER.** The no-terminal case
asserted the refusal did not start with one named bot key — but the moves are sorted, so the
per-bot backstop refused a DIFFERENT bot first and the assertion passed under the mutation. It now
checks against every key in the set. ⚠ **This is the third time this month a test has been
satisfied by a refusal for the wrong reason**; the fix is always the same shape — assert WHICH rule
refused, not merely that something did.

⚠ **A reformat invalidated one mutation's patch string and it reported as a survivor.** Re-run the
harness after `ruff format`, and treat a BADPATCH as an unrun mutation rather than a passing one.

---

## A dependent leg's parent is STORED, so the stack can be replayed (2026-09-07)

`stack_members.source` — the strategy id whose closed trades a dependent leg arms off — written
by `routers/stacks.py` at launch, read back by `gradable.rebuild_legs`.

🔴 **IT WAS PASSED AT LAUNCH AND WRITTEN DOWN NOWHERE, so a stack holding a loss-recovery leg
could be replayed by nobody and was refused walk-forward AND sensitivity outright** — the two
phases that make a stack's grade mean anything. Rebuilding without it produces a leg that arms off
nothing and returns an EMPTY book, which lands in the summary looking exactly like a rule that
found no setups: a whole account graded on a strategy set quietly one leg short. **Refusing named a
real gap; replaying would have hidden it** — which is why the refusal was the right interim answer
and why the fix is a column rather than a guess from leg order.

⚠ **NULL IS NOT READ AS *INDEPENDENT*; THE STRATEGY IS ASKED WHETHER IT NEEDS A PARENT.** Every
ordinary leg stores NULL, and so does every leg written before the column existed — so the column
alone cannot tell an independent leg from an unrecorded dependency, and reading it that way would
replay exactly the stacks the refusal exists for. `requires_source` on the strategy row can tell
them apart, and it is the same flag every endpoint that starts a job already refuses on.

⚠ **A stack launched before 2026-09-07 is STILL REFUSED, and the refusal names the fix** (re-run
the stack). There is no backfill: the parent was never recorded, and inferring it from leg order
is the guess this column exists to remove.

⚠ **The parent must be a leg of THIS stack, checked at rebuild time.** `run_stack` refuses a
dangling source too — but that refusal arrives minutes into a replay and names the simulator; this
one arrives before the phase starts and names the stack.

⚠ **`source` is ABSENT from an ordinary leg's rebuilt dict rather than `None`.** The runner reads
it with `.get()`, so both mean the same thing, and stating it once is one fewer way for the two to
disagree.

⚠ **The column is declared in the migration list AND in the `stack_members` CREATE TABLE**, per
this file's standing note — a column added to only one works perfectly on the machine that ran the
migration and is missing on every fresh clone. Both paths were checked.

🔴 **THE COLUMN IS ONLY WORTH HAVING IF THE THING THAT CREATES A STACK WRITES IT** (rule 7). A
rebuild reading a column nobody fills refuses every stack for ever, which looks exactly like the
bug it replaced — so the launch's write is pinned by its own test, driven through the real endpoint
rather than the helper.

⚠ **Both phases share `gradable.rebuild_legs`**, so neither can accept a stack the other refuses.
That is the same reason `_finish_walk_forward` and `_finish_sensitivity` are shared: a second copy
would let one phase run under a rule the other does not.

**Tests:** 6 more in `tests/test_gradable_resolver.py` (44). ⚠ **Non-vacuity by MUTATION: 9
written, 9 RUN, 9 killed** — the parent dropped from the rebuilt leg, emitted unconditionally, the
membership check dropped, the blanket refusal restored, the refusal dropped entirely, the refusal
keyed on the NULL column instead of the strategy flag, the router's write dropped, the write
thrown away in `add_stack_member`, and the column dropped from the leg query.

⚠ **TWO EXISTING TESTS HAD THEIR SUBJECT NARROWED AND THEIR DOCSTRINGS SAY SO.** They pinned *any*
dependent leg being refused; they now pin the PRE-COLUMN stack being refused, which is the half
that survives. **A test whose premise quietly changes meaning while staying green is a test that
has stopped guarding what its name claims** — the same trap this file records for the fixture
premises two sections up.

---

## A stack shift keeps its own BOOK, so it can be opened without inventing a row (2026-09-07)

`stress_tester.write_shift_book` / `read_shift_book` / `stack_shift_slug`, served by
`GET /stress-tests/{id}/shift-book/{slug}`.

🔴 **A SINGLE RUN'S SHIFT IS A BACKTEST AND GETS A ROW; A STACK'S SHIFT IS A FUNCTION CALL AND
MUST NOT.** The single-run path creates a child `backtest_runs` row per shift, which is what the
page navigates into. A stack shift replays in this process — there is no job, no terminal and
nothing to poll — and giving it a run row would put a backtest in the Runs lineage that nobody
launched, **naming one strategy as the subject of an account's result**, which is exactly what the
nullable `run_id` on the stress test exists to prevent. So the BOOK is stored and the row stays
absent.

🔴 **`book` IS A SEPARATE FIELD FROM `run_id` ON THE SHIFT RECORD.** `run_id` means *there is a lab
run row you can navigate to*; `book` means *a stored account book you can read*. A stack shift has
the second and never the first, and folding them into one field would make a page that follows
`run_id` request a run that does not exist.

⚠ **The slug is recorded ONLY when the write landed.** A slug whose book is not on disk is a link
that opens nothing, and *cannot open* would then be indistinguishable from *was never stored*.

⚠ **The writer NEVER raises and never fails the phase.** A shift's score comes off the KPIs in
memory; the file is a convenience for the reader, and a phase that died because a drill-down could
not be written would have traded a measurement for a link. Its return value is what the caller
reads, so the failure is not silent to the code that matters.

🔴 **THE BASELINE IS STORED TOO, and it is not decoration.** Every shift's number is a RATIO
against it, so a reader opening a shift with nothing to compare it to holds half a measurement —
and it is the baseline THIS phase replayed, not the stack's own stored book, which was measured on
a different code path. Its slug is `__baseline__`, double-underscored so a setting genuinely named
`baseline` cannot overwrite the thing every shift is scored against.

⚠ **The books live UNDER THE STRESS TEST'S OWN DIRECTORY**, which is what makes them disposable:
the delete endpoint already rmtrees that directory, so they go with the test they describe. A
directory of their own would need its own cleanup, and the one nobody writes is the one that grows
— this app has already had to clear an orphaned-directory backlog once.

⚠ **404 means NOT STORED** — a phase predating this, a write that failed, or a slug naming nothing
— and it is deliberately not an empty book. An account that traded nothing and a book nobody kept
are different answers.

⚠ **A corrupt half returns the readable half.** The KPIs are what the reader came for and an
unreadable curve should not withhold them; the missing half reads as absent, never as measured
empty.

🔴 **A DEFECT OF MINE WAS FOUND BY LOOKING AT THE FILES, NOT BY READING THE CODE, AND ITS DOCSTRING
CLAIMED THE OPPOSITE.** `stack_shift_slug` ended with `.strip("_")`, which deleted the underscore
the substitution had just put there in place of the `%` — so `+25%` and `+25` both became
`account_size__+25` and the second shift's book would have silently overwritten the first's.
MEASURED: the two returned the identical string. **No shift label today lacks a `%`, so it could
not fire** — and the comment positively asserted the collision was impossible, which is the shape
this file already records twice: *a comment asserting a safety net that is not there is worse than
no comment, because the next reader stops looking.* A leading underscore is still stripped; that
one cannot encode anything.

⚠ **AND THE TEST SUITE WAS WRITING INTO THE REAL `reports/lab`.** The sensitivity fixture never
redirected the results directory — harmless while the phase wrote nothing, and the moment it wrote
books every run of that file left folders in the live reports tree. **Found the same way**, by
listing the directory. The fixture redirects it now, and the stray folder was read before it was
deleted and confirmed to hold only the fixture's own stub values with no stress-test row naming it.

**Tests:** 11 more in `tests/test_gradable_resolver.py` (55). ⚠ **Non-vacuity by MUTATION: 11
written, 11 RUN, 11 killed** — the trailing strip restored, a bad character dropped rather than
replaced, no book written, the slug recorded despite a failed write, the baseline skipped, the
`book` field blanked, the writer allowed to raise, a missing directory read as an empty book, a
corrupt half taking the whole book down, the endpoint serving an empty book instead of 404, and the
endpoint skipping its row check.

## A shared stack can run the RE-ENTRY, and it states its LOT CEILING (2026-09-08)

Two halves of one goal: make a shared-account stack replay what the live bots actually trade.

### 🔴 The re-entry pin is retired — the app was the half that never filled the field in

`_SHARED_LEG_PINS` forced `exec_secondary` OFF on every shared leg since 2026-08-09, so a stack of
the two live bots replayed a SOS Fade nobody runs. **The stated ground was structural — a leg is one
bar frame — and it had stopped being true in the SIMULATOR long before it stopped being true here:
`LegSpec.df_fast`, `build_leg`'s dual-feed branch and `run_stack`'s plumbing were all built and
tested.** `portfolio_runner._leg_fast_frame` supplies the frame; the pin is gone.

⚠ **MEASURED on the live bots' own 116 settings** (PU Prime `XAUUSD.p`, 2020-01-01 → 2026-09-06,
$10,000, 10% cap, ECN costs): the SOS Fade leg goes **157 trades / +169.75R → 246 / +232.11R**, and
**exactly one of 116 settings differs between the two runs**, so the 89 extra trades are that
switch's and nothing else's. Peak open risk and the contention log are byte-identical.

⚠ **The question is asked of `run_feeds`, NEVER of the config by name.** That resolver is already
the one place the single-run path and the pre-flight floor check both ask, and its own comment
records what a second copy cost — a run whose fast feed could not reach the requested start date
passed validation and died at 8%. A third copy here would be that defect again.

⚠ **It goes through `_frame`, so the fast bars are the SAME OBJECT any leg trading that frame
replays.** On the live pairing it costs nothing: the extreme leg is on 5m and SOS Fade's fill clock
is 5m, so the frame is loaded once and shared.

⚠ **`exec_recovery` STAYS pinned, for a different reason** — it is INERT here (it runs from a
`finalize` hook the simulator never calls), not unrunnable. Do not read one retirement as the other's.

🔴 **The guard test was WIDENED rather than deleted.** It now asserts that every setting
`legs._refuse_unreplayable` refuses is either **pinned off OR supplied**, with both sides read from
the code — the refusals parsed out of `legs.py`, "supplied" established by reading
`portfolio_runner.py`. A third refusal added later fails until somebody classifies it. Three older
tests were re-stated onto the setting that is still pinned; **a test whose premise is edited to keep
it green has stopped guarding anything.**

### The venue lot ceiling was ENFORCED on every stack and STATED by none

🔴 **It was never missing — `run_stack` has defaulted to 100 lots since 2026-09-02, so every stack
ever run here was clamped.** What was missing is the CONTROL and the RECORD: `StackRequest` had no
such field, so nobody could ask for a different ceiling (or for none, which a parity anchor wants),
and the row recorded nothing. ⚠ **An empty `max_lots` column means NEVER STATED, not *no ceiling*
— reading it the other way is how this was first written up as "stacks compound uncapped".**

⚠ **It is BASIS, and the obvious test misses it.** R is identical either side of a ceiling — profit
and risk both scale with the quantity — so two stacks measured at different ceilings reconcile
perfectly on R and disagree on every dollar figure, with nothing on the page to say why. That is the
whole reason it has to be stored.

⚠ **Stored on the STACK row AND on each LEG row**, TEXT and JSON, the same three states
`backtest_runs.max_lots` carries: NULL = unstated, `'null'` = deliberately unclamped, a number =
that ceiling. The leg row is what the run detail page reads a ceiling off.

⚠ **Existing rows are NOT back-filled**, and here the number would even be right — every one ran at
100. Writing it would still put a figure on the row that no caller chose, and the next reader takes
a stored number for a decision.

🔴 **`lab_db._parse_three_state` DROPS THE KEY when the column is NULL, and `_parse_json_fields`
cannot express that** — it turns both a SQL NULL and the four characters `null` into `None`. The
readers downstream (`python_runner._max_lots`, and `portfolio_runner` through it) spell *unstated*
as an ABSENT KEY, because a dict has no other way to say it. Collapsing them silently un-clamps
every stored stack the moment one is rerun.

🔴 **DECODED AT THE READ, and it was wired there before it had a caller.** `get_stack_settings` is
what walk-forward and sensitivity hand to the replay — the two phases the 2026-09-07 `cost_layers`
bug hid in, for exactly this reason: **creating a stack takes its settings from the REQUEST, where
they are real values, while REPLAYING one takes them from storage.** A ceiling arriving as the
string `'null'` does not fail politely; `float('null')` raises four layers down in a background job,
naming a converter rather than this column.

⚠ **`portfolio_runner._ceiling_kwargs` returns two SHAPES, not two values**: `{}` when unstated (so
`run_stack` applies its own default, which is what every stored stack got) and `{"max_lots": ...}`
otherwise. **`UNSTATED` must never be forwarded as a value** — it would land on the account as the
ceiling itself and raise inside the sizing rather than here. It asks `python_runner._max_lots`, the
reader the single-run path already uses; a second copy of a three-state rule is how two paths come
to disagree about one stored field.

⚠ **The default is 100, matching `BacktestRunRequest` and `account.DEFAULT_MAX_LOTS`, so adding the
field moves no existing result.** It changes what is RECORDED, not what runs. ⚠ **The column is
declared in the migration list AND the `stacks` CREATE TABLE**, per this file's standing note.

**Tests:** 13 more in `tests/test_shared_stack.py` (58). ⚠ **Non-vacuity by MUTATION: 11 written,
11 RUN, 11 killed** — the NULL key decoded to `None`, the stored ceiling left as JSON text, the
stack row and the leg row each failing to record it, the sentinel forwarded, a deliberate
no-ceiling swallowed as unstated, the replay no longer passing what it resolved, the column left
out of the CREATE, the zero refusal dropped, and the request default flipped. 🔴 **One survived
first and it was the HARNESS** — the anchor matched `insert_run`, the single-run writer, which no
stack test touches. **A mutation that lands somewhere else is not a surviving mutation, and it reads
exactly like one.** It also exposed a real gap: nothing covered the LEG row, which now has its own
test. ⚠ **The wiring check reads the CALL SITE out of the source** rather than driving
`_build_and_run`, which loads real bars and resolves real strategy classes — a stub capable of
standing in for all of that is a fixture more capable than production.

---

## Stack sensitivity runs its shifts in a POOL, and the estimate stopped double-counting (2026-09-09)

Two defects in one phase. Both made a stack's sensitivity look far more expensive than it is, and
one of them had never been true.

### 🔴 "A stack cannot use that path" was a fact about ONE replay, read as a fact about TWO

`_run_stack_sensitivity` replayed its shifts one at a time since it was written, and the reason
recorded beside it was that a stack "replays several legs on one merged clock IN THIS PROCESS".
**That is true, and it is a statement about where a single replay runs — not about whether two
replays depend on each other.** They do not: every shift is an independent replay of the same bars,
and `replay_window` writes nothing. **MEASURED on the live pairing's stack before changing
anything: six replays at once finished 3.61x faster than six in a row and every one returned an
IDENTICAL trade list** (four workers: 3.08x). ✅ **Driven end to end afterwards through the real
fan-out: 2.82x on a four-shift plan, same order, same profit factors.**

⚠ **PHYSICAL cores, not logical** (`_STACK_SENS_WORKERS`). CPU-bound Python gains almost nothing
from the hyperthreads and each worker holds its own copy of the bars.

🔴 **AT MOST `workers` IN FLIGHT, TOPPED UP AS EACH LANDS — never the whole plan queued.** Queuing
all sixty makes a cancel arrive after everything has started, so *stop the remaining replays* stops
nothing (`cancel_futures` can only drop what has not begun). It also stops the parent holding sixty
account books at once, which the serial loop never had to think about.

🔴 **THE CANCELLATION CHECK RUNS BEFORE THE RESULT IS CLASSIFIED, AND THE FIRST VERSION HAD IT
INSIDE THE SUCCESS BRANCH.** A cancelled phase whose shifts were all FAILING never saw the
cancellation and ground through the whole plan — the "cancel did not cancel" defect this app has
now fixed three times, restored by an `elif`. **Found by its own test, not by reading.**

⚠ **RESULTS ARE ASSEMBLED IN PLAN ORDER, never completion order.** The plan is a priority — the
account's own settings first, then the legs taking turns — so a record shuffled by whichever worker
finished first misreports what the budget was spent on.

⚠ **The books are written in the PARENT.** Workers return the book; one writer keeps
`write_shift_book`'s contract (a slug is recorded only when the write landed) unchanged.

⚠ **A worker RETURNS its failure rather than raising**, so a dead shift is recorded as a hole in
the coverage instead of surfacing as a pool error naming no shift.

⚠ **The cancel bound genuinely CHANGED and is stated rather than implied**: whatever is already
running finishes, so a cancel costs at most one batch. What still holds is that nothing NEW starts.

### 🔴 The estimate added two rows that describe ONE run

`_stack_replay_minutes` summed each leg's duration. **On a shared stack the legs run TOGETHER on one
merged clock, so every leg row carries the same start and end** — MEASURED on the live pairing: two
rows of 498s each, quoted as 16.6 minutes for a replay that took 8.3, and a three-leg stack would
have been out by three. It takes the elapsed SPAN now.

⚠ **The smaller of the span and the sum, because there is a third case.** A SCREEN may reuse a
finished standalone run whose row is stamped from days ago, and the raw span then measures the gap
since that afternoon rather than any work. Read off the TIMESTAMPS, so neither shape has to be
declared to the function.

🔴 **IT SAID *FLOOR* AND IS A CEILING.** The row it reads describes a stack RUN — the shared book
plus one solo control per leg, then persisted — while a shift replays the shared book alone and
writes nothing. MEASURED: the stack row spans **498s** and a sensitivity-shaped replay of the same
stack over the same window takes **234s**. ⚠ **Left over-stating rather than scaled by a fitted
factor**: the gap is the solo controls, and a divisor tuned on one two-leg stack is a guessed number
wearing a measurement's clothes (rule 4). Quoting a wait that turns out shorter is the safe
direction.

⚠ **The estimate divides by the MEASURED speed-up, not by the worker count** —
`_STACK_SENS_PARALLEL_EFFICIENCY` is 0.6, and assuming a full Nx would quote a third of the real
wait. **Net effect on the live stack: 1013 minutes quoted → 147.** ⚠ **The trigger note said "one
at a time" and now names the batch size** — a note describing the old shape reads as a measurement
of the new one.

### The pool is a SEAM, and the inline stand-in is deliberately less capable

🔴 **`_shift_pool` exists so the ORCHESTRATION can be driven without spawning six interpreters** —
ordering, failure recording, cancellation and book writing are all decided in the parent. ⚠ **An
inline stand-in shares this process's memory, so it accepts a job that cannot be PICKLED and a
worker that reads a monkeypatched module — the two things that fail only across a real boundary.
Rule 13 from its other end: a double SIMPLER than production hides a defect just as well, and is
harder to notice because nothing about it looks like a claim.**
`test_the_shifts_really_do_survive_a_PROCESS_boundary` drives the real pool for that reason.

✅ **PROVEN IN PRODUCTION, not only in tests.** A sensitivity run was launched through the live
backend and a worker was confirmed at **98% CPU with the uvicorn server as its parent process** —
`ProcessPoolExecutor` spawns correctly from inside the served app on macOS. Cancelling it dropped
the workers to idle and released both platform locks.

**Tests:** 7 new in `tests/test_gradable_resolver.py` (62). ⚠ **Non-vacuity by MUTATION: 7 written,
7 RUN, 7 killed.** 🔴 **Two of them could not have failed as first written and were rewritten:** the
ordering test drove the inline pool, where completion order IS submission order, so *walk the plan*
and *take them as they land* produce the same list; and the cancel-bound test was named for a bound
it never measured, asserting only that a cancelled phase reports cancelled. **Check that a test's
inputs can distinguish the behaviours it names** — this file has now recorded that four times.
⚠ **The existing cancel test is pinned to ONE worker**, where the *stops on the very next shift*
guarantee is exact; asserting it against six would simply be wrong.

---

## 🔴 Two halves of one subtraction, read off two different CLOCKS (2026-09-09)

The Bots page reports what each bot MADE and, under it, the account's growth that no bot
recorded. That remainder is a subtraction — **and its two sides were read at different moments.**
The balance comes off `bot_state.json` over SSH and is seconds old. The bots' realised results came
off the committed archive on THIS machine, which is behind by however long ago the box last
COMMITTED *and* this machine last PULLED — **MEASURED at 66 minutes on 2026-09-09, with no upper
bound at all, because nothing here pulls on a schedule.**

🔴 **So a trade closed inside that gap sat in the balance and in NO bot's row**: that bot
under-reported by exactly its profit and the remainder over-reported by the same amount. It
happened — the extreme leg's **$1,305.58** target rendered under *"a manual fill, a deposit, or a
trade older than the record"*, three real causes, none of them true. **A stale read and a real
attribution gap were the same pixel**, and nothing on screen could separate them.

### Two fixes, and neither is sufficient alone

**(1) The box's OWN ledger rides on the snapshot's existing connection.** `_fetch_vps_snapshot`
adds one `findstr` per bot per month; `_parse_live_trades` reads it back; `read_bot_ledger` merges
it OVER the archive, deduped by `(ticket, ts)`. The two halves then share a clock. ✅ **DRIVEN
against the live box, not only tested**: both bots read `live`, the $1,305.58 landed on the extreme
leg, and `attributed + unattributed` reconciles to `net` to the cent — with the remainder unchanged
at the **$3,344.80** measured on 2026-09-05, which is the real gap and not this trade.

**(2) When the box cannot answer, the page SAYS the split is provisional.** `records_live`, a
measured `attribution_lag_seconds`, and a sentence. ✅ **Driven on the real archive with the live
read withheld: 80 minutes, stated.** That is the half that survives a dead VPS, and it is what makes
the four causes of a remainder distinguishable at all.

⚠ **The archive stays the BASE and the box is a TOP-UP.** The live window is bounded by month, so
it cannot reach an older trade; the archive cannot reach a newer one. Each holds what the other
cannot, which is why the UNION is taken rather than the fresher source preferred.

⚠ **`live_trades=None` and `live_trades=[]` are different facts** — *the box was not asked* against
*it answered and there were none*, which is the ordinary state of a bot that has not traded this
month. Rule 1, and the reason the argument is not a plain list: collapsing them prints a confident
split off a record that may be an hour behind.

⚠ **`records_through` is an INSTANT and `records_to` is a DAY.** The day comes from the filename,
so today's file always read as *recorded through today* while the newest line inside it could be an
hour old — **what was REQUESTED of the archive reported as what arrived** (rule 3). `_newest_ts`
walks BACKWARDS from the end, bounded to 20 lines (a live bot is appending, so the final line is
routinely torn), and answers `None` rather than fabricating an instant.

⚠ **`findstr /c:pnl_usd`, an unquoted token, and only a CLOSED trade carries that field** — checked
against the whole archive rather than assumed. A pattern with no spaces or quotes survives the trip
through the local shell and cmd unmangled, which the obvious `"kind": "trade"` does not. It is a
PREFILTER; the parsed fields still decide, the same rule the archive reader follows.

⚠ **A `findstr` hit is prefixed with its file path, and a Windows path carries a drive colon** — so
the JSON is found by its opening BRACE, never by splitting on a separator. A filename cannot contain
one.

⚠ **Bounded by MONTH rather than one wildcard over the folder.** Both bots' whole trade history is
**6 rows / 3.1 KB** today, so a full read would be free — and it grows with every trade for ever, on
an endpoint the page POLLS. A month window stays the same size whatever the history reaches.
`_LIVE_LEDGER_MONTHS` is 2, measured against the thing that creates the gap: the box-side half is
under an hour, and a clone that has not pulled in two months has more wrong with it than a P&L.

⚠ **The account reports the WORST lag, never the average.** The question is whether ANY trade could
be missing, so one bot an hour behind makes the whole split provisional however fresh its neighbour
is — and an average buries exactly the bot the reader needs to know about.

⚠ **A lag that cannot be measured is `None`, never `0.0`.** Zero is the most reassuring answer
available and here it is the one that cannot be supported.

**Tests:** 11 in `tests/test_bot_earnings.py` (24) + 6 in `tests/test_bots_snapshot_parse.py` (13).
⚠ **Non-vacuity by MUTATION: 18 written, 18 RUN, 18 killed**, and re-run after `ruff format` because
a reformat invalidates a patch string and a BADPATCH reads exactly like a survivor.

🔴 **ONE SURVIVED FIRST, AND IT WAS THE TEST READING THE PROSE RATHER THAN THE CODE.** Two checks
grepped `inspect.getsource(_fetch_vps_snapshot)` for `findstr /c:pnl_usd` — **and that string is
also in the COMMENT above the line**, so replacing the entire filter with `type` left them GREEN.
They drive the real fetch with `_ssh` stubbed and assert on the COMMAND now. **A test that greps a
function's source is reading its explanation as readily as its code** — the same trap
`test_deploy_commit_gate.py`'s `--no-verify` guard hit on its own docstring.

⚠ **The fetch/parse pairing is the one that fails in SILENCE**, so it is checked by ROUND TRIP —
the real fetch answered the way the box answers, then parsed. A section fetched under one name and
looked for under another is always absent, which is indistinguishable from a box that could not be
reached: the exact state this whole read exists to move away from.

## The stack sensitivity pool runs EIGHT at once, and the six was a tail-biased reading (2026-09-10)

`_STACK_SENS_WORKERS` was physical cores (6 on this box) and is now **2/3 of the logical cores (8)**.

🔴 **THE MEASUREMENT THAT CHOSE SIX WAS CONFOUNDED BY THE JOB COUNT, NOT BY THE BOX.** It submitted
TWELVE jobs, so six workers got two clean waves while eight got 8 + 4 and ten got 10 + 2 — and the
idle tail, not hyperthreading, is what made the extra workers look worthless. **RE-MEASURED on 24
jobs, a whole number of waves at every count tested, on the live two-leg stack over one year: four
workers 2.55x, six 3.37x, EIGHT 4.30x, twelve 4.07x.** A clean knee at eight, worth **1.28x of the
phase's wall clock** over six.

⚠ **A job count that is not a multiple of the worker count measures the TAIL, and the tail is
biggest exactly where you are trying to read a difference.** Pick a common multiple before
comparing worker counts, or the answer is about the arithmetic of the harness.

⚠ **The memory objection the old comment raised was CHECKED rather than repeated.** Each worker
holds its own copy of the bars. MEASURED: one worker peaks at **560 MB** on a full-history replay of
this stack (26 MB before the bars load), so eight want ~4.5 GB on a 16 GB box. **Memory is not why
twelve is slower than eight** — that is CPU contention, and it is the honest reason to stop at eight.

⚠ **`2/3 of logical` is a RATIO from one box, not a law.** Nothing has run this on another machine;
read the formula as *the shape that reproduces the measurement here* and re-measure elsewhere.

⚠ **`_STACK_SENS_PARALLEL_EFFICIENCY` moved 0.6 → 0.54, and the number to read is the PRODUCT.**
8 x 0.54 = 4.3 is what was actually observed; the constant alone means nothing.

### The phase is ~42 minutes, was ~82, and the budget was NOT spent on coverage

**One full-history sensitivity-shaped replay of the live stack is 182.6s** — it was 277.5s until the
engine gating landed the same day (`backtest/CLAUDE.md` → *An engine a strategy never READS is never
RUN*). With the pool at 4.30x, the 60-replay budget is **60 x 182.6 / 4.30 ≈ 42 minutes**, against
~82 on 2026-09-09's code.

🔴 **THE COMMENT ABOVE `_STACK_SENS_MAX_REPLAYS` STILL SAID THE SHIFTS RUN *ONE AT A TIME* AND
*SERIAL*, AND BOTH STOPPED BEING TRUE THE DAY BEFORE.** The stale half was the whole reasoning the
number rested on — *60 replays is about an hour* followed from *serial* — so it read as a
justification for a limit that no longer followed from it. **A number is only as current as the
sentence under it, and a comment that argues for a constant goes stale WITH the thing it argues
about.**

⚠ **KEPT AT 60 rather than raised, and that is a REQUIREMENT decision rather than a correctness
one.** Raising it to ~85 would put the phase back at the hour it was designed around and take the
settings actually probed from **15 of 38 to about 21**. Both are honest — what the budget cannot
reach is named in the coverage record and in the start-up estimate — so which one the speed-up buys
was Aaron's call, and he made it on 2026-09-10: **stay at 60 and keep the time.** Do not re-raise it unless something new changes the trade.

### The start screen's wait is MEASURED once a stack has been stressed (2026-09-10)

**The form quoted ~124 minutes for a ~42-minute sensitivity phase on the live pairing.** Two
independent causes, and they both pointed high.

🔴 **ONE: THE ESTIMATE READ THE STACK'S RUN ROW, AND A RUN MAKES TWO PASSES OVER THE BARS.** A
launched stack replays the shared book over every leg's bars, then one solo control per leg over
that leg's own — the solos sum to the same total whatever the leg count. A shift does the first
pass alone. **So the row is twice a shift's cost, and that 2 is ARITHMETIC, not a fitted divisor.**
The old docstring refused a divisor *"tuned on one two-leg stack"* and was right about that and
wrong about this: this one is read off what the runner does. The measured 498s-row against a 234s
shift (2.13x) is a CHECK on the reasoning, not its source. ⚠ **A SOURCED leg keeps the full span**
— its control runs a private copy of its parent, so that stack does more than two passes and
halving would under-state, the unsafe direction for a wait.

🔴 **TWO: THE ROW IS STAMPED WITH WHAT A REPLAY COST ON THE DAY IT RAN.** The live stack's row
predates the engine gating, so it carried a cost the code no longer pays — and arithmetic cannot
fix that, only a measurement can.

✅ **The fix is to MEASURE, and the measurement was already being taken.** The phase's baseline is
exactly one shift-shaped replay — same legs, window and path — so it is now TIMED and stored in the
coverage record. `lab_db.last_stack_replay_seconds` reads the newest one back, and the estimate
prefers it; the halved run row is only the fallback for a stack that has never been stressed.

⚠ **`None` means never measured and must never become zero** — zero reads as an instant replay and
quotes a wait of nothing. ⚠ **Newest wins**, because the point is to track a replay getting faster.
⚠ **Another stack's reading is never borrowed** — replay cost is a fact about this stack's legs,
bars and window.

**On the live pairing now: 124 → 62 minutes from the halving alone**, still over because its row
predates the gating. **The first sensitivity run on it records the real figure and the next
estimate lands at ~45** (182.6s x (1 + 60 / 4.32)).

**TESTED:** 12 new tests across `test_gradable_resolver.py` and `test_stack_stress_visibility.py`,
**8 mutations run and 8 killed.** 🔴 **One survived on the first pass and it is the rule-7 shape:**
the reader and the estimate were covered, but nothing proved the phase WROTE the figure — so
deleting the write left every stack quoting the fallback for ever while looking wired. A test now
drives the real phase and asserts the round trip.

## A stack's setting nudges run ONLY when its bots can compete for risk (2026-09-10)

**Aaron's call.** When a stack's bots cannot get in each other's way, a nudge to one bot moves only
that bot's trades — which that bot's OWN stress test measures, at a fraction of the cost. So the
full ~42-minute phase is kept for the case only a whole-stack test can see, and a stack otherwise
gets Monte Carlo + walk-forward on the combined book. **On the live pairing that is ~4.5 minutes.**

`stress_tester.stack_nudges_needed` decides; the endpoint asks it ONCE, before the estimate, the
platform check, the recorded phases and the task, so all four read one answer. **Full test when ANY
of these holds:**

- a leg trades off another's results — a recorded parent, OR a strategy that needs one and has none
  recorded (the same two-sided test `gradable.rebuild_legs` makes);
- the shares add up past the cap, via **`bot_accounts.shares_exceed_cap`, the check the Bots page
  uses to say the bots share the room** — never a private sum (it carries a tolerance a raw sum
  lacks). ⚠ It asked `share_overflow` until 2026-09-15, when that stopped refusing a sum;
  `shares_exceed_cap` answers `None` for an unreadable share, which reads as needed;
- the stack's own run BLOCKED an entry, or trimmed one by more than `_STACK_TRIM_IMMATERIAL` (1%);
- anything is unreadable — cap, a share, the cap-record, or a record that disagrees with its own
  summary's count. **`portfolio_runner.read_contention` keeps `[]` (never bound) apart from `None`
  (no record)**, and only the first may skip.

🔴 **THE 1% IS A DECISION, AND THE LIVE PAIRING SHOWS WHY ZERO WOULD BE WRONG.** 5% + 5% under 10%
fits exactly, yet its 6.6-year run trimmed ONE trade by $8.61 of $16,979 (0.05%): a bot's open risk
is fixed dollars, so a balance that falls while it holds makes that a bigger share and the other
bot's room comes up a hair short. That is sharing, not taking turns. Anything cutting a real slice
still goes to the full test.

⚠ **The request still says `include_sensitivity: true` and the server narrows it** — the evidence
lives here. ⚠ **It also skips the stack's own account settings** (cap, balance, smallest position),
which the full test nudges first: nudging the cap down on shares that fit it exactly manufactures
the competition the check just ruled out.

⚠ **The reason is stored** (`stress_tests.sensitivity_skipped`, written at creation beside
`phases_requested`, declared on the model or Pydantic drops it). **The grade reads it off the row**,
so the live grade and the restamp both see it: it counts as NOT RUN (no credit, no penalty, no cap
on A) and says why instead of *"may improve with full analysis"* — the full analysis would add
nothing. A stale reason is ignored when a sensitivity result exists.

🔴 **THE WALK-FORWARD ESTIMATE WAS WRONG THE SAME WAY, AND IT BECAME THE WHOLE WAIT.** A stack used
the single-run constant (ten 12-second child jobs → **2 min**); MEASURED on the live pairing, its ten
whole-stack window replays take **251.7s (4.2 min)**, serial, in-process.
`stack_walk_forward_minutes` reads this stack's last walk-forward off timestamps every test already
writes (`lab_db.last_stack_wf_seconds`, only a walk-forward that stamped its end), else one replay x
**1.38** (251.7 / 182.6, measured once). **Live: quotes ~7 the first time** (its run row predates the
gating), **~5 after.**

**TESTED:** `tests/test_stack_nudges_needed.py`, 22 tests, **26 mutations run, 26 killed.** 🔴 **One
survived first, and the lesson is about NUMBERS:** the shared-check case used 3.3 + 3.3 + 3.4, which
sums to EXACTLY 10.0, so a private sum agreed with the shared check. It uses 0.1 + 0.2 under 0.3 now,
with the float premise asserted. **Inputs that cannot tell two behaviours apart do not test which
one runs.**
