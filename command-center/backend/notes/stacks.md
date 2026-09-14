# Notes — Portfolio stacks

Screens vs shared-account stacks, how a stack is charged, dependent legs, leg minimums and frames. Moved VERBATIM out of `command-center/backend/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## Portfolio stacks (smart reuse)

A **stack** layers 2+ Python strategies over ONE shared instrument + window + cost profile. 🔴 **THE TIMEFRAME IS NOT SHARED, AND THIS SENTENCE SAID IT WAS UNTIL 2026-09-03.** Each leg carries its own frame and falls back to the stack's only when its package declares none — see *A stack leg runs on ITS OWN frame* below, which owns the rule. Applies to BOTH modes. The combined portfolio line and per-strategy toggles are composed CLIENT-SIDE from each leg's `daily_pnl`, so there is no stack-level result row and toggling a leg off never re-runs anything.

**Ownership ≠ membership (the reuse enabler, 2026-07-25).** Two tables:
- **`stacks`** — the stack's own settings (`instrument`, `bar_type`, `bar_value`, `start_date`, `end_date`, `commission_per_side`, `slippage_ticks`, `created_at`). Persisted so a stack whose legs are ALL reused (zero owned child runs) still knows what it is — `list_stacks`/`get_stack` read settings from here, not from a child row.
- **`stack_members(stack_id, run_id, owned, position)`** — membership. `owned=1` = a fresh run the stack created (carries `backtest_runs.stack_id`, hidden from the Runs tab, **deleted with the stack**). `owned=0` = a pre-existing standalone run REUSED as-is (`stack_id` stays NULL, **stays in the Runs tab, survives stack deletion**). `list_stack_runs` INNER JOINs members→runs so a reused run the user later deletes simply drops from the stack instead of 500-ing.

**Smart reuse on create (`trigger_stack`).** For each leg, `find_matching_stack_run()` looks for the most-recent COMPLETED **standalone** Python run (`stack_id IS NULL AND stress_test_id IS NULL AND sweep_id IS NULL AND optimization_id IS NULL`) matching the leg's EXACT identity — strategy + instrument + `bar_type` + `bar_value` + window + `commission_per_side` + `slippage_ticks` + (since 2026-09-02) `cost_layers` +
`broker_profile`. Match → add an `owned=0` member, no re-run. No match → create an `owned=1` child and queue it through `run_sweep` (unchanged). The python job lock is only taken when ≥1 leg needs a fresh run; an all-reused stack is assembled instantly and returns `status="complete"`. A per-strategy `params_by_strategy` override **disables reuse for that leg** ("run it my way", not "reuse whatever exists").

**Matching is STRICT by Aaron's call (2026-07-25)** — any difference (even a one-day window shift or a different cost field) misses and the leg re-runs. Do NOT loosen it without asking. **Cost defaults are 0/0** (`commission_per_side=0`, `slippage_ticks=0`, `bar_value=15`) — matching the Pine strategies, which are all pinned `commission=0, slippage=0` for TV↔Python parity (costs are modeled inside the strategy via the 30-tick breakeven buffer). 🔴 **THIS SAID BOTH FIGURES WERE COSMETIC AND THAT NOTHING READ THEM. THAT WAS TRUE ONCE AND IS NOT NOW, IN TWO SEPARATE WAYS.** A charged run applies them (`routers/_costs.py`, since 2026-09-02) — and that resolver OVERWRITES the typed commission with the broker's MEASURED figure before the row is stored, so the number on the row is what was billed rather than what anybody typed. ⚠ **The stack form's commission box was removed on 2026-09-03 for exactly that reason** — it was a control whose value could not survive the request. Its stored value is still SENT, so that rerunning an older stack reproduces the figure it was saved with. Slippage keeps its control, because it is the one cost here nobody has measured. Rules: *A stack is CHARGED like a single run* below, and `routers/_costs.py`. The stack's original bug was the **5m timeframe** (vs the designed 15m), not costs — a stacked leg read ~⅓ of the same strategy's standalone run because it ran on entirely different signals. The forex rulesets (`personal_forex_demo`, `unconstrained`) also seed `default_slippage_ticks=0` (converged on existing DBs in `init_db`) so the Run modal shows 0/0 too; futures rulesets keep `2.25/1` (NT8/MT5 platforms genuinely apply them).

**`POST /backtests/stacks/preview`** (`StackPreviewRequest` → `StackPreviewResponse`) reports per-leg `action` (`reuse`|`run`) + the matched run's `net_pnl`/`trade_count`/`profit_factor`, running nothing — it drives the modal's live Reuse/Run badges. **`GET /stacks/{id}`** (`StackDetail`, async) now also carries `commission_per_side`/`slippage_ticks` (from the settings row, for the Rerun modal) and a full-calendar `regime_timeline` for the shared window (drives the equity chart's regime overlay). Regime source: read from a leg's `regime_timeline.json` if present; sweep-child legs aren't regime-tagged, so when none exists it computes the timeline once via `build_regime_timeline_and_tag(..., runner="python")` (off-thread) and caches it to the base leg's dir so later polls read the file. **`build_stack_chart_spec`** carries the base leg's structure `overlays`/`indicators` and a `base_run_id`. 🔴 **The parenthetical here read *identical for every leg* and that justification died on 2026-09-03**: overlays are a property of the market ON THOSE CANDLES, and the legs no longer share candles, so a leg on a finer frame has its trades drawn over swings and gaps it never saw. The behaviour is unchanged and is now a LIMITATION rather than a free choice — that leg's own run page shows its real structure. ⚠ The chart itself is `services/chart_spec.py` — so the stack's price chart has full BacktestDetail parity (structure layers, ATR pane, fib/measurement, and M1/M5 drill-down routed through the base leg's `/candles`). **`delete_stack`** removes only `owned=1` legs from `backtest_runs` (+ their report dirs, via the router) and clears the `stacks`/`stack_members` rows; reused legs are untouched. `_backfill_stack_membership` (in `init_db`, idempotent) materialises `stacks` + owned `stack_members` for any legacy pre-membership stack so old stacks survive. Python-only: summing daily P&L models independent sleeves, and NT8/MT5 have their own single-window terminals a lab stack has no reason to touch.

## Shared-account stacks — one balance, one budget, N bots competing for it

**Landed 2026-08-09.** `services/portfolio_runner.py` + the `mode` branch in `routers/stacks.py`.
Plan and the measured first run: `command-center/docs/SHARED_RISK_STACK.md`.

**A stack is now one of two DIFFERENT experiments over the same legs, and almost every rule here
is about keeping them apart.** A `screen` runs each leg as its own standalone backtest and adds
the results together — every leg sized as if it owned the account, nothing could block anything,
so it is an UPPER BOUND. A `shared` stack replays them together on one balance with one risk
budget they compete for. Confusing the two produces numbers that look perfectly ordinary and
answer a question nobody asked.

### It CALLS the simulation and owns no copy of it

`backtest/portfolio/run_stack` is the account model. This module builds legs from lab rows, runs
it on a thread and persists what comes back. **A second account model here would be a second
answer about what a shared budget does** — and the live allocator (`docs/LIVE_TRADING_PIPELINE.md`
→ G10) already has to be a third implementation, because live bots are separate OS processes that
cannot share an in-process object. Two is the most this rule can afford.

### What the first real launch found, before it found anything about portfolios

🔴 **It died in a background task on the first attempt.** `sos_fade`'s `exec_secondary` (the
1-minute re-entry) has defaulted **ON** since 2026-08-07, it needs a second bar stream through
`run_dual`, and a leg on a merged clock is one frame — so `legs._refuse_unreplayable` raised and
the only trace was a string in a progress field.

`_SHARED_LEG_PINS` in the router pins it ahead of that refusal, and two things about the fix
matter more than the pin:

- ⚠ **The pinned value is written onto the CHILD RUN**, not applied at replay time. Overriding
  during the replay while the stored row said `exec_secondary: true` is this app's most-repeated
  defect — a page stating a value no code read. Here the row and the replay agree, so that leg's
  own detail page is telling the truth about what ran.
- ⚠ **`tests/test_shared_stack.py` READS `backtest/portfolio/legs.py`** and fails if
  `_refuse_unreplayable` grows a refusal the router does not pin. A hand-written copy of that list
  here would be a second claim about one rule and would go stale in silence — the same arrangement
  `test_notification_routing.py` and `test_bot_versions.py` use.

### The schema change needed BOTH declarations, and only one of them is obvious

⚠ **`mode` / `account_size` / `risk_cap_pct` / `entry_floor_pct` are declared in the idempotent
migration list AND in the `stacks` CREATE TABLE.** The migrations run FIRST, so on a fresh
database the `ALTER TABLE stacks` lines fail (no table yet) and are swallowed by the
try/except — leaving a brand-new clone **without** the columns while every existing database has
them. That is the worst shape a schema change can take: it works on the machine that ran the
migration and breaks everywhere else. Both directions are proven by test.

⚠ **`mode` defaults to `'screen'`.** Every stack written before the column existed WAS a screen,
and defaulting to `'shared'` would relabel finished results as a simulation nobody ran.

⚠ **The account knobs are NULL on a screen, never 0** — `insert_stack` drops them rather than
storing what the request happened to carry. A screen has no account (each leg traded its own full
one), a stored `0` renders as an account with no money, and `risk_cap_pct = 0` — which refuses
every entry — would be indistinguishable from "this stack never had a cap".

### A shared stack reuses nothing, and always takes the lock

Both are departures from the screen path and both would be defects if copied across:

- **No reuse, ever.** A finished standalone run was measured on its own full account with nothing
  able to block it. Dropping one into a shared stack puts an un-contended leg beside contended
  ones and calls the pair a portfolio. The screen's reuse optimisation is only sound *because* a
  screen never claims the legs interacted. `POST /stacks/preview` takes the mode for this reason —
  otherwise the modal offers a reuse count for a run that will replay everything regardless.
- **It always takes the python lock**, because there is always work: `run_stack` is
  `1 + len(legs)` full replays (the shared book plus one solo CONTROL per leg).

### Cancel reaches the replay, and a cancelled book is not persisted

`simulate` gained `progress` / `should_cancel` (polled every 512 ticks — the check is cheap and
the loop body is cheaper). A full-history two-leg stack is four replays over ~150,000 bars, so a
Stop button that cannot reach that loop is a Stop button that does nothing.

⚠ **A cancelled `StackRun` RETURNS with `cancelled=True` and a PARTIAL book**, and the runner
refuses to persist it. That book holds every trade closed up to the tick it stopped on, which is
indistinguishable from a complete short backtest once written to disk — persisting it is the
"cancel did not cancel" defect from the other side: not a run that carried on, but a stopped run
recorded as a finished one.

⚠ **A cancelled shared run also skips the SOLO CONTROLS.** A control's whole job is to be
comparable to the shared book, and a control over the full history beside a book that stopped a
year in is two different experiments in one table — the screen-vs-shared delta would report the
missing year as the cap's doing.

⚠ **`_is_cancelled` reads the DB rows** (the single lock source) and answers **False** on an
unreadable row. Carrying on is recoverable; abandoning a multi-minute replay because sqlite was
momentarily busy is not.

### What is persisted, and the check it stores

`reports/lab/<stack_id>/` holds `contention.json` and `shared_summary.json`; each leg is written
through the same shape `sweep_runner._handle_complete` uses, so the existing drill-in detail page
works on a shared leg with no branch of its own. **The stack's own directory is deleted with the
stack** — no child run references it, so deleting only the children leaves it behind, which is
how `reports/lab` reached 191 directories against 84 runs before the stress-test audit.

⚠ **A leg's equity curve here is its CONTRIBUTION, not its balance.** It is walked from the
account's opening balance over that leg's own trades, because the real balance path belongs to the
shared account and there is no such thing as "this leg's balance" once the two compound together.
The legs' daily P&L still SUMS to the shared account's, which is what the page composes the
combined line from.

`shared_summary.json` carries a `neutral` verdict, and it is the one thing this artefact can
CHECK rather than report: **R is normalised to the trade's own risk, so with nothing refused a leg
must post the SAME R shared as solo.** A difference there is the shared account moving a decision
it must not touch — a defect in the seam, not a portfolio effect — and it is invisible in a table
of numbers unless something says so out loud.

### The SOLO CONTROL is a BOOK, not two scalars

**2026-08-10.** `run_stack` has always replayed each leg alone as a control, and `_persist` kept
only `solo_r` and `solo_closing_balance` from it. That is enough to CHECK the seam — with a full
budget a leg must post the same R shared as solo — and not enough to SHOW anyone, so the page
composed "what would the rest of this have made without that strategy" out of the SHARED trades.

🔴 **Those trades are sized off a balance every leg compounded onto, so that composition answers a
different question and reads as the right one.** Measured on `st_94aeb25f0c`, B-LEG:

| | solo | in the shared stack |
|---|---|---|
| trades | 99 | **99 — same entry timestamps, same entry and stop prices** |
| total R | **+17.8674** | **+17.8674** |
| win rate | 51.5% | 51.5% |
| risk on the last trade | $3,102 | **$16,925,791** |
| net | **$21,064** | **$47,758,999** |
| profit factor | 1.505 | **3.111** |

`_write_solo` persists the control to `<stack_dir>/solo/<strategy_id>/`, `solo_book` reads it, and
the leg serves it as `solo_equity_curve` / `solo_daily_pnl`.

- ⚠ **The control gets NO run row and NO evaluation.** It is not a lab run — nobody requested it,
  it has no id to navigate to, and putting it in `backtest_runs` would list a backtest nobody
  launched.
- ⚠ **A SCREEN is served nothing, and that is not a gap.** There every leg already traded its own
  full account, so the leg's own curve IS the solo answer; a second field would be two copies of
  one fact that can disagree. `_solo_fields` reads the mode off the SETTINGS row — a leg row
  carries no mode, so reading it from `first` would answer `None` on a legacy stack and silently
  withhold the book from a shared one.
- ⚠ **Absent is `None`, never `[]`.** A stack replayed before this landed has the scalars and no
  book, and the page renders a refusal there rather than an empty curve — the *no data is not the
  same as cannot ask* rule, on the page that met it.
- **`scripts/backfill_stack_solo.py`** re-derives the book for older stacks. ⚠ It **re-runs** the
  replay (nothing was written to recover), which is `1 + legs` full replays — the same work a
  Rerun does, except it touches no stored row, KPI or leg curve. It reproduced the stored scalars
  exactly on the live stack, which is the check that says it replayed the same thing, and it
  refuses to overwrite an existing book without `--force`.

🔴 **`models.EquityPoint` did not declare `r`, and this is the FIFTH time that model has dropped a
field already on disk** (`entry_ms`, `exit_ms`, `favorable`, `adverse`, now `r`). `backtest/output.py`
has written it since 2026-08-03 and `reprice.py` reads it straight off the file, so the value was
there the whole time and never reached the browser. **It is the one per-trade figure a change of
position SIZE cannot move**, which is precisely what a portfolio page needs: a leg's R is the same
shared or solo while its dollars differ by orders of magnitude.

### The report distinguishes its three "no answer" cases

⚠ **`available: false` is THREE answers and a caller must not collapse them**: this stack is a
SCREEN (no account exists to contend over), it is still RUNNING, or it failed. `progress`
separates the second; `StackDetail.mode` separates the first.

⚠ **`events: []` under `available: true` is the OPPOSITE of all three — a real measurement that
nothing was refused, and it is the EXPECTED result.** Open risk is measured to each trade's
current stop, so a stop moved to breakeven releases its room before the other leg asks. Read it as
*the budget would rarely have had anything to arbitrate*, never as *the cap is not working*.

⚠ **`_PROGRESS` is in-process and nothing may ever recover an IDENTITY from it.** It drives one
progress line. `lab_progress.json` was read for a job id on 2026-08-06 and a Stop cancelled an
unrelated platform's job; the rule that came out of it is that a channel built to carry a STATUS
must never be asked who something is.

✅ **`cost_layers` / `broker_profile` LANDED 2026-09-02** — see *A stack is CHARGED like a single
run* below. Both modes resolve them from one call, which is what the note that stood here asked for.

## A stack is CHARGED like a single run — `routers/_costs.py` (2026-09-02)

🔴 **EVERY STACK THIS APP RAN BEFORE THIS DATE IS GROSS, AND ITS PAGE SHOWED A COST ROW THE WHOLE
TIME.** `StackRequest` carried neither `cost_layers` nor `broker_profile`, so a stack reached
`python_runner._cost_profile` with the legacy commission/slippage pair — which the modal defaults
to **zero**. Nothing failed, nothing was empty, and the number that came out was simply the
frictionless one sitting where the answer goes. ⚠ **Stored stacks are NOT re-priced**: their rows
keep the NULL that honestly says they predate the columns, and re-running one is how it gets
charged. ⚠ **The gap is not small.** MEASURED on one matched pair — the SOS Fade and extreme-leg stack on
PU Prime `XAUUSD.p`, 2020-01-01 → 2026-08-23, $2,000 opening, 10% cap, identical in every other
input — free book **+215.17R → $4,704,587**, ECN costs charged **+204.50R → $2,911,177**. That is
**−5.0% of the edge and −38.1% of the closing balance**, because the shortfall compounds. ⚠ **The
trade count MOVED, 314 → 315** — charging the spread through the fill model changes WHICH setups
fill, which is the half a flat per-trade deduction can never reproduce.

`StackRequest` and `StackPreviewRequest` now carry `charge_costs` (nullable bool, **default True**),
`broker_profile` and `cost_layers` — the same contract `BacktestRunRequest` has carried since
2026-08-24, with the same three rules (resolved at CREATION, python-only, `None` = no opinion). The
full rule list is in *Costs are charged BY DEFAULT* and is **not restated here**.

🔴 **The resolver was EXTRACTED to `routers/_costs.py` rather than copied, and that is the point of
the change.** The block lived inline in `routers/backtests.py`; the stack path needed the identical
thing. This app has already shipped the same defect three times by copying a measurement basis
instead of sharing it — the tuning workbench, the stress children and the stack rerun each carried a
parent's PARAMS and not its costs, then put the two side by side. **A second copy drifts, and the
symptom is a comparison table where the cost gap reads as the feature under test.**

⚠ **Resolved ONCE, BEFORE the mode branch.** A screen and a shared run over the same legs measured
on different physics would make the delta column report the cost gap as the risk cap's doing — the
one comparison the whole page exists to make.

⚠ **`broker_profile` is DEFAULTED, not nullable, and it matches `BacktestRunRequest` deliberately.**
The layer resolver reads a real `PROFILES` key, so a null refuses every stack with *broker None
unknown* — a contract mismatch reported as a broker problem, which sends the reader at the wrong
half of the system.

🔴 **THE COST BASIS IS PART OF THE REUSE IDENTITY.** Without it a CHARGED stack silently reuses a
leg run measured on a FREE book and stands it beside legs that paid spread, commission and swap.
That is the mixed-basis defect above arriving in the one place it lands **inside a single result**
rather than across two, where nothing downstream can separate them.

⚠ **`find_matching_stack_run` compares them with `IS`, never `=`.** Both columns are legitimately
NULL on a pre-layer row and `= NULL` matches nothing in SQL, so an equality test would quietly stop
reusing every older run — a failure that preserves correctness and just re-runs everything, which is
exactly the kind nobody investigates.

⚠ **The layer list is matched as its STORED JSON, so it depends on the resolver emitting a stable
order.** `charged_layers` returns a fixed tuple and slippage is appended last, so it does. A
resolver that ever sorted differently would stop matching rather than match wrongly — the safe
direction, and worth keeping that way.

🔴 **THE PREVIEW MUST RESOLVE COSTS THE SAME WAY THE LAUNCH DOES, and it did not on the first
attempt.** The modal's per-leg **Reuse** / **Run** badges come from `preview_stack`; giving only the
launch the new basis made the preview promise a reuse the launch then replayed. Caught by
`test_the_PREVIEW_refuses_to_reuse_a_leg_the_launch_would_re_run`, which existed already and went
red for exactly this. **A preview that defaults differently from the thing it previews is the same
defect one level up** — both requests carry identical defaults on purpose.

⚠ **One older test moved its PREMISE, not its subject**: it seeds free-book runs and asserts the
preview reuses them, so it now says `charge_costs: False` out loud. The new behaviour is pinned
separately by `test_a_CHARGED_stack_will_not_reuse_a_run_that_was_measured_FREE` — a test whose
premise is quietly edited to keep it green is a test that has stopped guarding anything.

⚠ **`stacks` gained the two columns in BOTH the migration list and the CREATE TABLE**, per this
file's own standing note: a fresh database is built from the CREATE and an existing one from the
migrations, and a column added to only one of them works perfectly on whichever machine you tested.

🔴 **NOTHING HAD EVER STARTED A STACK IN A TEST, AND THAT IS THE BIGGER FINDING HERE.** Threading
the costs through added two arguments to the shared-launch helper and its own signature was not
updated — **every shared launch would have raised at the call site**, a 500 on the one button the
Stacks page exists for. **All 1,196 backend tests passed with it**; it was the linter that noticed.
The cause is that `test_shared_stack.py` seeds its rows straight through `lab_db` and posts only to
`/preview`, so the trigger endpoint had no test **in either mode**. ⚠ **This is the shape
`.claude/mcp/check_tradingbox.py` already names in its own docstring** — a suite whose cases all
assert what a feature REFUSES certifies a feature with no working happy path, because something
that always fails satisfies every refusal test beautifully. Both cost tests above are that kind:
they assert a reuse is *declined*. ✅ Closed by `test_the_shared_LAUNCH_can_actually_be_CALLED`,
which drives the real endpoint with the runner stubbed and was watched RED on exactly this
(`TypeError`, 36 others still green). ⚠ **The screen mode's trigger is still undriven** — worth a
matching test before anyone threads something new through it. ⚠ **The trigger route is
`/backtests/stack`, SINGULAR**, where every other route on that router is plural; posting the
plural returns 405, which does not read like a missing endpoint.

## A stack leg may READ ANOTHER LEG'S LOSSES — `recovery_parent` (2026-08-21)

`StackRequest.recovery_parent` + `recovery_params` add a loss-recovery leg that arms off one of the
other legs' closed losses. Mechanism and the five build stages:
`docs/RECOVERY_LEG_IN_COMMAND_CENTER.md`; the account side is `backtest/CLAUDE.md` → `LegSpec.source`.

🔴 **A PARENT PLUS PARAMS, NEVER A LIST, and the shape is the constraint.** At most one may exist:
the shared account keys an open position by leg NAME and two recovery legs would both be
`loss_recovery` — a duplicate silently overwrites a live reservation and the cap under-counts the
open risk while reporting itself enforced. `run_stack` refuses duplicate names, but **a refusal
that fires four minutes into a replay is a worse version of a shape the request could simply not
have.**

⚠ **`recovery_params` IS DECLARED AND THE UI NEVER SENDS IT.** The backend honours it and the
rule's own settings page renders all eleven — but `StackConfigModal` has no editor for the recovery
leg, because per-leg overrides hang off the leg LIST and the rule is filtered out of it. So a
recovery leg built from the page always runs on its defaults, which are the measured configuration.
**A declared field no caller assigns is rule 10's shape** — written down rather than left for
somebody to change a setting and watch nothing happen.

⚠ **`_validate_recovery_leg` runs BEFORE the lock and before any row is written**, and refuses four
states, each of which is silent or late otherwise: a recovery on a SCREEN (every leg has its own
full account there, so it could never take room off its parent — the only question it answers), a
parent not in the stack (the leg reads nothing and returns an empty book), a parent that is itself
sourced (the chain `run_stack` refuses), and picking the rule as an ordinary leg.

⚠ **`exec_recovery` JOINED `_SHARED_LEG_PINS`, and the reason differs from `exec_secondary`'s.**
That one is structurally unrunnable on a merged clock; this one is merely INERT — the switch runs
from a `finalize` hook the simulator never calls, so the leg came back with its recovery trades
**silently missing**. Pinned rather than refused so the stack still runs, and STORED as pinned so
the leg's row says the switch was overridden. `backtest/portfolio/legs.py` refuses it as the
backstop, and `test_shared_stack.py` reads that file and fails if the two drift.

⚠ **`portfolio_runner` is the ONE place a dependent leg's config is joined to its parent's.** The
form carries the rule; the leg also needs the instrument's contract size, the PARENT's full-size
risk, the structure length the parent read and the frame's bar rate — three of which are facts
about the parent. Reading the risk off the parent is what keeps a quarter-size recovery a quarter
when the parent's risk moves.

🔴 **`strategies.requires_source` is a new column and it is what every picker filters on.** A rule
that has no setups cannot be run alone; the flag lets the lab state that rather than leaving each
picker to remember it. ⚠ **It is still SCANNED and still gets a strategies row** — a leg's run row
references one, so without it the leg could carry no params, no KPIs and no chart. ⚠ **Declared by
the package (`LAB_STRATEGY["requires_source"]`), never set by hand.**

⚠ **`EXPECTED_CLASS_NAMES` needed `RecoveryLeg` — the FOURTH time those three tests have gone red
for that one cause.** Grep `LAB_STRATEGY`, which is what the scanner reads.

**Tests:** `tests/test_recovery_leg_wiring.py` — 12 for THIS section; the file is 19 now, the rest belonging to the two sections below. ⚠ **A fail-watch against HEAD is vacuous** —
none of it existed — so non-vacuity is by MUTATION: allowing a recovery on a screen, allowing a
parent outside the stack, and dropping the `requires_source` flag each turn their own named test
red.

## 🔴 A rule that NEEDS A PARENT is refused at every endpoint that starts a job (2026-08-21)

**The tick box was only half the hole.** `loss_recovery` also has a strategy DETAIL page with its
own Run button and its own Run modal, and that modal posts straight to `POST /backtests/run`. So
the rule could be run alone, from the UI, with nothing refusing it. Found by opening the page.

🔴 **It would not have errored.** Handed no source the rule replays the whole frame, arms off
nothing, and returns an EMPTY book — a run that completes, grades, stores KPIs and reads as *this
rule finds no trades*. That is rule 1 (never let "found nothing" and "was never asked" be the same
value), and it is why this is a 400 rather than a UI tidy-up.

`routers/_source_guard.py::refuse_if_needs_source(strategy)` is called by all three endpoints that
CREATE a job from a strategy id: `backtests.trigger_backtest`, `optimizations.trigger_optimization`
and `sweeps.trigger_sweep`. **It reads the FLAG, never the id**, so the next dependent rule inherits
the refusal by declaring `requires_source` in its package, with no router change.

⚠ **Retry, rerun and stress-test are deliberately NOT guarded** — each acts on a row that already
exists, and no such row can be created once every creation path refuses. CHECKED rather than
assumed: `backtest_runs` held zero rows for the flagged strategy when this landed. **A new creation
path must add the call.**

⚠ **A missing strategy passes straight through.** That is somebody else's 404, and swallowing it
here would turn a typo'd id into *needs a parent*.

⚠ **The frontend half is a LABEL; this is the gate.** `StrategyDetail.tsx` now swaps its Run for a
disabled *Needs a parent*, matching the list page — and there is NO automated test on it, because
Playwright is out of the suite by design. Rule 7: a label is a claim about code somewhere else.

**Tests:** four more in `tests/test_recovery_leg_wiring.py` (16 total). The durable one is
`test_every_endpoint_that_STARTS_a_job_from_a_strategy_id_refuses_a_dependent_rule` — an AST sweep
of `routers/` for any function that resolves `req.strategy_id` AND inserts, asserting it calls the
guard. ⚠ **It matches ANY `insert_*`, not a named list**: the first version named `insert_run` and
`insert_optimization` and skipped `sweeps.trigger_sweep` in silence, because that one calls
`insert_run_sweep`. **Under-including is exactly how the hole was left open in the first place.**
All four watched RED by mutation — dropping the call, never raising, raising for everything, and
raising on a missing row — plus a fifth on the refusal text losing its *add it inside a stack*
instruction. MEASURED live against the running backend: the rule refused 400 carrying the
instruction, and an ordinary strategy passed the guard and was refused by the history floor.

## 🔴 A stack's minimum is two LEGS, not two strategies (2026-08-21)

`_validate_stack_strategies` counted `strategy_ids`, so **SOS Fade plus a recovery on SOS Fade — one id, two
legs, the single most likely stack anybody builds and the exact case the recovery leg was built
for — was refused with *"a stack needs at least 2 strategies"*.** Nothing was broken; the feature
simply could not be reached from the UI at all. That is rule 9's failure shape: a feature nobody
has RUN is not a feature, and this one had been shipped, documented and tested a leg at a time
without anybody driving the whole path.

`extra_legs` is what a caller adds for legs that are not strategies of their own; `trigger_stack`
passes `1` when `recovery_parent` is set. ⚠ **The count happens BEFORE `_validate_recovery_leg`**,
so a one-strategy stack carrying a recovery is not turned away by the leg count it satisfies —
the recovery's own legality (parent in the stack, shared mode) is still that function's job.

⚠ **`preview_stack` deliberately does NOT pass it.** A preview is only ever asked for a SCREEN,
and a recovery is refused on a screen — so a one-strategy preview is correctly refused.

⚠ **The refusal names the way out** (*pick another strategy, or tick loss recovery under the one
you have*). The old message stated a rule and no remedy, which is how a reader concludes the
feature is missing rather than that they are one tick away from it.

**Tests:** three more in `tests/test_recovery_leg_wiring.py` (19 total), including an AST check
that `trigger_stack` still reads the recovery off the request — guarding only the helper would
leave the endpoint counting ids one layer up. Watched RED by four mutations. MEASURED live: one
strategy alone refused with the new message, and one strategy plus a recovery passed the count and
was refused by the history floor instead.

## A stack leg runs on ITS OWN frame, and the stack asks the broker for the symbol it quotes (2026-09-03)

Two defects reported off one screen, both of which looked like display faults and were not.

🔴 **A STACK HAD ONE TIMEFRAME FOR EVERY LEG.** `extreme_leg` is measured on 5m and
`sos_fade` on 15m, so putting them on one account replayed one of the two on a frame nobody has
ever measured it on — and the combined table said *portfolio*. **The SIMULATOR always allowed
this**: its merged clock steps a 5m leg three times inside a 15m leg's bar, and `LegSpec` has always
carried a per-leg frame. This app was the half that could only LOAD one. Same shape as the overlap
audit the day before, and worth stating as a pattern: **when a tool cannot do something, check
whether the engine under it already can.**

- **The frame is DECLARED by the strategy** (`LAB_STRATEGY["suggested_bar_value"]`), served by the
  scanner, stored on the strategy row, and a form fills each leg's box from it. ⚠ **Three-state:
  `None` means UNDECLARED, never "any frame will do"** — a leg whose package declares nothing keeps
  the stack's fallback rather than being handed an invented number.
- **It is a DEFAULT, never a refusal.** A run on another frame is legal and is simply a different
  experiment from the one the strategy's own figures come from.
- ⚠ **`_leg_bar_value` in `routers/stacks.py` is the ONE place it resolves**, so the history check,
  the reuse lookup, the stored row and the runner cannot disagree about what a leg was measured on.
  A leg's frame is part of the REUSE IDENTITY — the preview carries it too, or it badges a 15m run
  green *Reuse* for a leg the launch then replays on 5m.
- ⚠ **The stack row keeps only the stack-level FALLBACK frame, and each leg's own frame is on that
  leg's run row.** `StackDetail.bar_value` reads the settings row rather than the first leg's — one
  number on the parent describing children that no longer share it is a shape this app has been
  bitten by before.
- 🔴 **A DEPENDENT LEG IS PINNED TO ITS PARENT'S FRAME and never reads the request.** Loss recovery
  has no setups of its own: it arms off the parent's CLOSED trades and counts its wait in the
  parent's bars, so a frame of its own is a rule measuring a different clock from the book it reads.
  Nothing raises — it arms, trades, and lands in the table as a different rule. `portfolio_runner`
  takes its bar rate off the PARENT's own spec for the same reason.
- 🔴 **THE LEGAL START IS THE LATEST FLOOR ACROSS THE FRAMES**, because a broker holds less history
  the finer the bars. The window is checked PER LEG on that leg's frame. A window only the coarse
  leg can reach does not error — it answers a different question: the 15m leg compounds ALONE over
  the months the 5m leg does not exist for, and every later trade of BOTH is then sized off a
  balance one leg built unopposed.
- ⚠ **Bars are loaded ONCE PER FRAME and shared by every leg on it**, not once per leg — two legs on
  15m must replay the identical bars, and a second load is a second chance to differ. An empty frame
  REFUSES and names the frame: with two of them, *"no bars"* no longer identifies which.
- ⚠ **Progress counts every leg's stream added together.** With two frames it is no longer any
  single frame's length, and reading one would sit at 100% through the second half of the replay.

🔴 **THE STACK PATH NEVER RESOLVED THE SYMBOL AGAINST THE BROKER, and the single-run path has since
2026-08-26.** PU Prime quotes gold with a suffix and Vantage bare, so a stack under PU Prime asked
for a symbol that broker does not quote and died four layers down in the bar loader — with the
window and the timeframe named and the one wrong field not. It now resolves through the SAME
`python_runner.run_symbol` the single run uses (one implementation, so the lab and the live side
cannot drift about what gold is called), at CREATION, and the RESOLVED name is what is stored
(rule 3). ⚠ **The PREVIEW resolves it identically**, or the badge describes a different stack.
⚠ **A broker whose naming was never recorded leaves the symbol exactly as typed** — guessing hands
the terminal a symbol nobody has seen it quote, which is the failure this fixes.

Proof: `tests/test_leg_timeframes.py`, 28 checks. 21 were watched RED against HEAD; the five
declaration checks could not be (see below) and were proven by MUTATION instead — a wrong frame and
a deleted declaration each turn one red. One check is green on HEAD on purpose: a leg with no frame
of its own must keep falling back to the stack's, which is every leg of every stack stored before
this existed.

🔴 **A WORKTREE AT HEAD DOES NOT ISOLATE THIS SUITE, and finding that out is worth more than the
tests were.** `config.MONOREPO_ROOT` is an ABSOLUTE path read from machine config, so a backend test
run from any checkout still imports `strategies/`, `engines/` and `backtest/` from the MAIN tree.
Five tests "passed" against HEAD that way and the pass meant nothing — they were reading the edited
files. **A fail-watch that runs the new code is not a fail-watch**, and nothing about the run says
so: it is green, fast, and wrong. Watch repo-root code go red by MUTATING it in place.
