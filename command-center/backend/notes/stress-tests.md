# Notes — Stress tests on a single run

Monte Carlo, walk-forward, sensitivity and grading of one run. Moved VERBATIM out of `command-center/backend/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## Stress tests — the 2026-08-05 audit

**Read this before touching `services/stress_tester.py`, `services/grading.py` or the stress-test
half of `lab_db.py`.** The frame is one query: `SELECT count(*) FROM stress_tests` returned **1**,
and that row was written **2026-07-27 — three days before the accuracy pass** that replaced the
shuffle series, the drawdown basis, the sensitivity metric and the walk-forward floor. So the
feature had been driven end to end exactly once, against an engine that no longer exists, and
nothing had re-scored the row since. It carried a confident **D** for over a week; re-scored
through the live backend it is **ungraded**, with both probabilities NULL and sensitivity
0.858 → 0.205.

### Driven against the live backend, because a page nobody has run is not a page anybody has tested

That is the whole reason this list exists, so the fixes were driven rather than reasoned about — a
real stress test on a real **charged** 161-trade XAUUSD M15 baseline (`spread`+`swap`,
`vantage_demo`), walk-forward and sensitivity both on.

- **Every child carries the baseline's physics.** All of them, walk-forward and sensitivity alike,
  in ONE group: `["spread","swap"] / vantage_demo / consistent`. Under the old code that group
  would have been `NULL / NULL / consistent`.
- 🔴 **And the charge is REAL, which is a separate claim and needed its own measurement.** Carrying
  a field proves nothing about whether anything downstream reads it, so a walk-forward child of a
  charged baseline was re-run FREE over its own window and params — the body the stress tester used
  to send:

  | `wf_1_is`, 2020-01-01 → 2022-04-22 | charged | free |
  |---|---|---|
  | trades | 51 | **51 — identical** |
  | profit factor | 1.463 | 1.612 |
  | net P&L | $69,838.19 | $108,443.55 |

  **The identical trade count is the check that says the charge is correctly placed** — spread and
  swap change what a trade MAKES, never whether it happens, so a moved count would mean something
  else had changed. That $38,605 is what the old code reported as the strategy's out-of-sample
  behaviour while its parent was measured charged. The same pair on the full-history baseline
  itself: **159 trades either way, PF 3.942 → 3.668, $34,877,368 → $13,012,425.**
- **`phases_requested` is readable while the test is still running** — `["monte_carlo",
  "walk_forward", "sensitivity"]` at `running_sens`, so the page's pipeline stepper draws all three
  with per-phase elapsed (MC 1s, WF 1m 31s, sensitivity in flight). It was NULL until the very end.
- **The walk-forward numbers are the counterpart of the stored row, which is what makes them
  useful.** That row ran 5 windows and closed **6** out-of-sample trades in every one — under the
  20 floor, i.e. a degradation figure with nothing behind it, and the page could not say so because
  the field was stripped by the model. This run at 2 windows closes **30**, and the page reads
  `all windows have enough` beside IS 0.90 → OOS 1.70. `walk_forward_feasibility(161, w)` predicted
  it: OK at 2, infeasible at 3 (16 OOS), 5 (10) and 8 (6).
- **Cancel stops the work, and it was pressed against a real running test rather than a fixture.**
  A sensitivity phase 16 children deep returned `job_stopped: true` with 1 in-flight child cancelled,
  then sat at **16 children for 120 seconds** with the status holding at `failed_cancelled` — never
  overwritten by `complete`, which is what the old code did on the way out. **Both locks released
  immediately**: `running-lock` `{futures: false, forex: false}` and the python bucket of
  `running-job` free. Before this, the row said cancelled while the sweep kept every core and the
  per-platform lock reported the platform idle, so a second job could start on top of it.
- **Delete removes the files**: `reports/lab` 216 → 192 directories on a real delete, rows gone, and
  a dirs-vs-runs diff afterwards shows **no orphan dated today**.
- ✅ **The pre-existing backlog was cleared too, at Aaron's request: 109 orphaned directories,
  7.9 MB** — 92 stress-test children whose parent was deleted before this fix, 13 `opt_*` combos,
  and 3 sizing-pipeline test fixtures (`t_consistent`, `t_bullet`, `r2`). They are the
  "191 directories against 84 live runs" the audit opened with. **`reports/lab` is now 82
  directories and a dirs-vs-rows diff is CLEAN in the orphan direction (0).** ⚠ **The orphan set is
  computed against `backtest_runs` UNION `stress_tests`** — a test's own directory holds its
  `equity_paths.json` and is referenced by no run row, so diffing against runs alone would delete
  live data. ⚠ **Three ROWS legitimately have no directory** (`equity_curve_path` empty, never
  written); that is the opposite condition and is left alone.
- **Sensitivity skips what it cannot reach**: 3 of 17 numeric non-foundational params on this run
  are behind a switch it has off, so 12 backtests that could only reproduce the baseline are not
  run, and the coverage says so.
- ✅ **A full sensitivity phase finished, which is what "driven end to end" finally means here.**
  `status: complete`, grade **D** with real reasons ("Median simulation is profitable but median
  drawdown breaches the limit" / "55% probability of breaching ruleset limit at some point"), and
  `sensitivity_coverage` populated on real charged data: **12 params perturbed, 46 shifts run, 0
  failed, 14 skipped and NAMED** (`exec_tp1_pct`/`exec_tp2_pct` sit at 0.0 so every shift lands
  back on 0; `div_pivot_len ±25%` rounds onto values already run) **and 3 params unreachable and
  named**. `phase_failures` is `{}` — empty, and distinguishable from null.

⚠ **The drive killed its own test TWICE, and the pair is the cleanest proof the
`phases_requested` fix was needed.** The backend is served with `--reload`; a `.py` edit landed
while a test was in flight and `reset_stale_stress_tests` correctly marked it `failed_crashed`.
**The first time — before the fix — the row recorded `phases_requested: NULL`, so nothing anywhere
said what that test had been asked to do.** The second time, after the fix, the same crash left
`["monte_carlo", "walk_forward", "sensitivity"]` on the row. Same failure, same recovery path, and
the difference is the whole point: a record written at the END does not survive the failures it
exists to describe. ⚠ **Do not edit backend source while a stress test is running** — a `.md` edit
is safe (uvicorn's reloader watches `*.py` only), a docstring is not.

⚠ **What this audit did NOT verify live, stated so it is not mistaken for measured: the NATIVE
walk-forward path (optimizer-derived, profit-factor based), the MT5 and NT8 runners, and the worker
pool's peak memory.** Everything driven here was the **python** runner, which is Aaron's stated
focus for this feature (2026-08-05) — so the native paths keep their unit tests and are deliberately
not on the critical path. The memory figure is simply missing: the sample was taken after the pool
had already torn down, which measures nothing. **Do not read any of the four as checked.**

### A child run must be measured on the BASELINE's physics

🔴 **`run_walk_forward_task` and `run_sensitivity_task` built a job spec carrying the window, the
params and the legacy `commission_per_side`/`slippage_ticks` — and no `cost_layers`, no
`broker_profile`, no `sizing_mode`.** `python_runner._cost_profile` reads those off the spec, so
stress-testing a run that charged spread and swap measured **every child on a free book**. On
walk-forward that makes the IS→OOS comparison a comparison against a run neither half resembles;
on sensitivity it is worse, because the score is `|child_pf − baseline_pf| / baseline_pf` and the
baseline PF came from the CHARGED parent — **so the cost gap was reported as the parameter's
fragility, on every single shift.**

`child_measurement_fields(source_run)` is the one seam, spread into both specs and into the child
row. ⚠ **`cost_layers` goes through `_json_list`** — it is stored as raw JSON TEXT, so handing the
string on iterates its CHARACTERS; the same trap `/runs/{id}/repriced` hit on 2026-08-03. ⚠
**`null` is forwarded as `[]`**, for the reason the tune page states: `null` means "written before
layered costs existed", which is not a contract a NEW run can be created under.

**This is the third launcher in this app found carrying the window but not the physics** (the Run
modal's costs, the Optimize modal's params, the tune page's `cost_layers`). The rule is now
general: **anything that creates a child run for COMPARISON must carry everything that decides
what a run is measured on.**

### "It never ran" and "it ran and crashed" were the same value

🔴 **A phase that crashed left its summary NULL, and grading reads a NULL summary as NOT RUN** —
explicitly unpenalised, with a caveat printed saying so. **So a walk-forward whose every backtest
failed cost the test nothing and could be handed an A carrying the words "walk-forward not run".**

Both phase tasks return `(ok, err)` now, and `phases_requested` / `phase_failures` are stored.
`compute_grade` takes `wf_failed=` / `sens_failed=`: a failed phase is neither credited nor
described as absent, and `genuinely_not_run` replaces the old `walk_forward is None` at both
caveat sites.

⚠ **`phases_requested` is written when the ROW IS INSERTED, not when the task finishes** — the only
point that cannot be missed. Written at the end it is absent for a test's entire life, so the page
has to infer which phases are coming, and **a task killed mid-flight leaves no record of what was
asked for at all.** That is not hypothetical: the backend reloaded under a live test during this
audit and left exactly that hole. `phases_requested(include_wf, include_sens)` in `stress_tester`
is the single definition, used at creation and again at the end. ⚠ **NULL still means "written
before this was recorded"** and the page falls back to inferring — `["monte_carlo"]` would be a
positive claim that nothing else was requested.

🔴 **The native walk-forward path failing left the test with no walk-forward at all.** It now falls
through to the serial path rather than reporting nothing; `failed_periods` is tracked, and a
missing curve gives `sharpe = None`, never `0.0` (which reads as a measured flat window).

### Sensitivity runs its shifts in PARALLEL

🔴 **The phase replayed 60 full-history backtests ONE AT A TIME on a 12-core box, while
`backtest/optimizer.run_sweep` had been fanning optimizer grids across every core the whole time.**
Aaron asked why it was slow when the bars are cached — and the cache was never the bottleneck.
MEASURED: **69s per child, 65–71s across children.** That tightness is the tell — it is compute
(an engine replay stepping ~165k bars in Python), not I/O.

⚠ **The obvious fix does not work, and it would have looked like it did.** Wrapping the loop in
`asyncio.gather` with a semaphore is the natural move, but `python_runner.start_backtest` runs each
backtest on a THREAD and the replay is pure-Python bar-by-bar, i.e. **GIL-bound** — N threads buy
almost nothing while appearing to be a fix. It needs PROCESSES.

`_run_shifts_pooled` submits the whole shift set as ONE sweep job. Rules that hold it together:

- **It goes through `runner_dispatch` → `python_runner`, never `run_sweep` directly**, because
  `_cost_profile` lives there. A second caller building its own cost profile is precisely how the
  children came to be measured on a free book in the first place. `python_runner` gained a
  `param_sets` passthrough for it — sensitivity is ONE-PARAM-AT-A-TIME, and `expand_grid` would
  return the CARTESIAN PRODUCT of the same shifts, a different and far larger experiment.
- **Python only, and that is not a limitation to lift.** NT8 and MT5 each drive one physical
  terminal; there is nothing to parallelise on, and firing concurrent jobs at a single Strategy
  Tester would be actively harmful. They keep `_run_shifts_serial`.
- ⚠ **Rows are matched back by `(param, value)`, NEVER by index.** `run_sweep` ends with
  `[r for r in results if r is not None]` — it COMPACTS on cancellation — so a cancelled sweep
  returns fewer rows than combos and index-matching would hand one shift's profit factor to a
  different parameter, silently. `sensitivity_plan` dedupes values per param, so the pair is unique.
- ⚠ **A shift the sweep did not return is FAILED, never a complete row with zero KPIs** — a zero
  scores as "this parameter does nothing", the most reassuring answer available for a measurement
  that never happened.
- ⚠ **Pooled children carry KPIs but no equity curve or daily P&L**, because a sweep worker returns
  KPIs only. Nothing reads a sensitivity child's curve (scoring uses profit factor and net P&L, and
  the UI never navigates to one), so the paths are NULL rather than pointing at files that do not
  exist, and no canonical Sharpe is computed — there is no daily series to compute one from.

✅ **PROVEN, and the correctness check mattered more than the speed one.** The same shift
(`sens_aplus_window_+25%`) was run through the pool and then re-run down the single-run path:
**161 trades, PF 3.268, $12,184,685.53 — identical to the cent both ways.** A 4x speedup that
quietly moves a number is worse than the slow version.

**MEASURED end to end: 46 shifts in 841s (14 min) against ~3,174s (53 min) serial — 3.8x.** ⚠ **Not
the ~10x the core count suggests, and the gap is worth knowing**: `default_workers` deliberately
leaves a core free (this runs inside the backend serving the UI that reports its progress), and the
~165k-row frame is pickled to each worker at pool start.

**`_estimate_sens_duration_min` was recalibrated in the same pass and was wrong twice over.** It
used a flat `_mins_per_job` of 0.2 min for python — true for a short backtest, 6x optimistic for a
6.6-year replay — and it summed serially. It now takes the SOURCE RUN's own measured duration (the
same reasoning the optimizer modal's estimate uses; a per-job constant is wrong by construction
because the cost scales with the window) and divides by the worker count. Quoted 13 min for the run
that took 14, against the old code's 12 for a 53-minute job. ⚠ **`started_at`/`completed_at` are
read `is not None`, never truthily** — a timestamp of 0 is a value, and `if started` silently
dropped it back to the constant. A test caught that, not review.

### Sensitivity: what was NOT tested is part of the answer

🔴 **A param behind a `show_if` switch this run has OFF was perturbed anyway**, and every shift
reproduced the baseline exactly — 3 of 17 numeric non-foundational params on the measured run, i.e.
**12 backtests that could not tell you anything.** `param_is_reachable` mirrors `ParamEditor`'s own
`show_if` rules (single value or array, stringified comparison) and `perturbable_params` is the one
roster, shared with the router's estimate so the two cannot drift.

⚠ **It mirrors TWO gates since 2026-08-15, and the second has the opposite polarity.** `disable_if`
holding means a setting whose two states cannot differ in this configuration, which produces the
same guaranteed 0% as a hidden one. ⚠ **The editor GREYED those rows until 2026-08-27 and now hides
them; this function did not change, because the reachability answer was the same before and
after** — worth knowing before reading its old wording as stale. ⚠ **`schema` must be
PASSED**: it is what makes `custom_from` resolvable, and without it a dropdown reading `Custom` =
1.0 gates differently here than it does on screen. The default is `None`, so a caller that forgets
it gets an answer that looks correct and is simply blind to the second gate. ⚠ **A THIRD gate landed the same day and it is NOT the same shape as the other two.** A SETTLED param (`hidden` in the meta AND still on its default, i.e. off the editor entirely) is excluded — but shifting one is not a no-op, the strategy really reads it and the result really moves. The reason to exclude it is that sensitivity would RANK a parameter no page renders, and a ranking that points at nothing is worse than a shorter one. ⚠ **`_is_settled` mirrors `ParamEditor.settled`, never `p.hidden` alone** — a hidden param MOVED off its default is back on screen, so it must be back in the ranking; gating on `hidden` would silently drop a param the reader can see and edit. Both are pinned by
`tests/test_param_gates.py` (non-vacuous by run mutations); the editor side is in
`../frontend/CLAUDE.md` → `ParamEditor.tsx`. ⚠ **Both of those tests cite the Pine file that greyed the control out first, and that file MOVED on 2026-09-02** — the `strategy()` sources left `indicators/strategies/` for `strategies/tradingview/`, so the docstrings were repointed. **The Pine is still the source of truth for which controls are dead**: the lab is catching up to a decision made there, never making a new one.

🔴 **A CONDITION'S RIGHT-HAND SIDE TAKES A THIRD SHAPE SINCE 2026-08-27: `{"gt": n}`, "a number
above n".** Some switches have no OFF value to name — a rule arming the stop after a move of N R is
off at -1 and off at 0 and on at everything above — so the row it controls could not be gated by
equality without listing every number that is not off, and was simply not gated. ⚠ **An operator
this side does not recognise is NOT MET**, so a typo hides a row rather than showing one it was
meant to hide. ⚠ **A bool is still not a number** (`_numeric` refuses it), or a checkbox would arm
a numeric gate.

🔴 **THE TWIN IS NOW DRIVEN OVER ONE SHARED FIXTURE, AND THAT IS THE PART TO KEEP.** `_want_holds`
here and `wantHolds` in `frontend/src/components/paramConditions.ts` are one rule written twice,
and they have already disagreed in silence — a fib level that is `"1.0"` in a dropdown and `1.0` in
a Custom box compared equal in Python and unequal in JS, leaving a toggle live in exactly the
configuration it exists to be dead in. **The CASES are the shared artifact rather than the code**:
`frontend/tests/fixtures/param-conditions.json` is read by `test_param_gates.py` and by
`frontend/scripts/check_param_conditions.mjs` (step 9 of `scripts/run_all_tests.sh`), so a shape
one side learns and the other does not fails on the side that did not learn it. ✅ **It caught one
on its first run**: `Object.entries({}).every(...)` is `true`, so an empty condition HELD in JS and
did not here. No schema uses `{}` today, which is exactly why nothing on screen could have shown
it. ⚠ **A new shape goes in the fixture in the same commit as the code**, or the drift guard is
guarding the old rule.

🔴 **A ROW THAT IS SETTLED *AND* GATED CANNOT BE REACHED FROM THE FORM, and `test_param_gates.py`
refuses one with no exceptions since 2026-08-27.** The two mechanisms hide it for opposite reasons
and compose badly: the gate takes it off the screen wherever it cannot matter, `hidden` takes it
off wherever it CAN. ⚠ **It is not literally invisible in every configuration** — `hidden` only
holds while the value sits at its default, so a run already carrying a moved value shows the row
again. **That IS the defect**: the only way to reach the row is to have changed it somewhere else.
⚠ **Six rows on `sos_fade` carried both and all six lost the `hidden` flag**, so the meta is
the state the test pins rather than a list of known exceptions — a list would have grown.

⚠ **`strategy_scanner._PARAM_META_KEYS` IS A WHITELIST, and a key missing from it is dropped in
SILENCE** — the meta states a rule, the scan reports success, and the editor behaves as though
nobody wrote it. Add the key there in the same commit as the rule that uses it. (It is also why a
meta-only edit needs a **Scan** before the UI moves.)

⚠ **`short` joined it 2026-08-20** — the same setting named in as few words as possible, for
surfaces that RECORD a run rather than teach it (the finished-run params panel, in a 248px rail).
`label` stays the teaching name the editor and the Pine input title share. Optional: a param
without one falls back to `label`.

🔴 **`shifted_value` REFUSES a shift past the param's own `min`/`max` rather than clamping it.** A
clamped shift is a duplicate of the bound, scored as though it were the ±25% case — a measurement
of a different question wearing the right label.

⚠ **`coverage` is stored and rendered.** A silent skip reads as coverage that never happened, which
is the same defect as the zero bar for a failed shift, one level up.

### Monte Carlo, cancel, delete

- **`prob_pass_eval` is measured on the basis the grade will read.** It was computed against the
  dollar limit while `prob_breach` had switched to percent, so on a compounding run the two
  contradicted each other. Measured on a synthetic compounding fixture with a 60%-of-account limit:
  old = 0.0% breach / **31.2%** pass, new = 0.0% / **100%**.
- **`distribution["max_dd_pct"]` exists exactly when the percent basis does**, so the histogram is
  labelled in the unit it was measured in and never invents one.
- **`_split_windows` starts out-of-sample the day AFTER in-sample ends.** The two halves shared a
  boundary day, so one day's trades were in both.
- 🔴 **Cancel now cancels** — `POST /{id}/cancel` marks the row, returns its running children, and
  cancels each through `runner_dispatch`, reporting `job_stopped` separately (the row is cancelled
  either way; "we told the runner" and "we could not reach it" are different facts). Every phase
  checks `is_cancelled` between children, and a cancelled test is not graded.
- 🔴 **Delete removes the files.** It returned a bare bool and the router did nothing else, so every
  child left its `reports/lab/<run_id>/` behind — which is how that directory reached **191 entries
  against 84 live runs**. It returns the child ids now and the router rmtrees the test's own dir and
  each child's. Measured live: 216 → 192.
- 🔴 **`asyncio.create_task` was called with no strong reference.** The loop only holds a task while
  one of its callbacks is scheduled, so a long-awaiting background task is collectable and can
  vanish mid-flight, leaving the row `running` for ever. `_BACKGROUND_TASKS` holds one.
- **`update_stress_test_mc` takes `next_status`.** It hardcoded `complete` even with phases still to
  come, so the market lock (`status LIKE 'running%'`) RELEASED in that gap and a crash inside it left
  a permanently `complete` test `reset_stale_stress_tests` cannot see.
- **A results file that is present-and-unreadable is a different fact from one never written**, and
  both arrived as `None`. `results_error` names it.

### The migration

`GRADE_ENGINE = 3` + `_restamp_stress_tests()` in `init_db`, idempotent and stamped so it runs once.
It rebuilds each stored test's walk-forward and sensitivity summaries under today's rules and
re-grades. ⚠ **It may only RE-DERIVE from stored inputs — it never re-runs a backtest** — so a row
whose child data is gone is left alone rather than being given a number nothing measured.

### A stress test posts NOTHING to Telegram (2026-09-10)

🔴 **The grade was posted to the health room on every finish** — the room that carries a dead bot,
a halted order bridge, a deploy. Aaron: *"I shouldn't get notification about these things… that is
not related to health."* A lab result there is noise, and noise is how the real alert stops being
read. The send, its formatter and the fixture script's stub are gone; the grade lives on the Stress
Tests page.

⚠ **Pinned by `test_notification_routing.py::test_a_stress_test_sends_nothing`**, which sweeps both
stress modules for a send AND refuses an import of the notifier — the sweep matches the function by
NAME, so an aliased import would slip past it alone. Both halves watched RED by mutation.

⚠ **If lab pings are wanted again, they get their OWN chat and their own kind** — never `HEALTH`.
Adding a kind means adding its credential key on both sides (`test_the_keys_match_the_algos_side`).

---

### A forex test that names no ruleset is graded against the 55% one (2026-09-16)

Aaron: *"we should always default to the 55% one"* — "Personal Forex — 55% Drawdown"
(`personal_forex_risk`). `routers/stress_tests.py` applies it when the request OMITS the ruleset
and the subject is forex. Stress test `89987e5088a045f2` is why: started from outside the page
with no ruleset, it completed with no letter.

- ⚠ **Omitted and null are different requests.** An explicit null is the reader choosing Monte
  Carlo only, and it stays ungraded — read off `model_fields_set`, never off a falsy value.
- ⚠ **Futures tests are untouched** — they keep whatever the request names.
- ⚠ **Both stress test windows pick the 55% ruleset first** (`frontend/src/lib/stressRuleset.ts`).
  The stack window warns when that differs from the ruleset the stack was last graded against,
  because the two grades will not compare.
- Tests: `tests/test_gradable_resolver.py` (both watched RED by mutation) and
  `frontend/tests/stress.spec.ts` (watched RED by restoring the strictest-evaluation default).

## How stress tests work

**Monte Carlo** — pure Python (numpy), no NT8 involved. Takes the trade P&L list from a completed backtest and runs two simulations:
- 10,000 reshuffles: same trades, random order. Probes whether the sequence of wins/losses was lucky. Sum is invariant, so final PnL doesn't vary across reshuffles — only drawdown does.
- 1,000 bootstrap resamples: samples trades with replacement. Both total PnL and drawdown vary.
- **Drawdown** stats (median/P95/P99, prob-breach) use BOTH pools (order genuinely varies drawdown). **Final-PnL** stats — the median/p5/p1 percentiles, the PnL histogram, AND the "probability of passing the eval" — use the **BOOTSTRAP pool only**: reshuffle final PnLs are all the net total (order-invariant), so including them collapses those onto one degenerate value. Don't reintroduce `all_pnls` into a final-PnL stat.
- **Pass-probability by ruleset_type** (`run_monte_carlo`): `prop_eval` with a profit target = `mean(final_pnl ≥ target AND max_dd ≤ limit)` (hit target AND never breach). `prop_funded`, `demo`, **and `personal`** = `1 − prob_breach` ("pass" = never breached the drawdown rule — none of them has a profit-target requirement). `personal` MUST stay in the `1 − prob_breach` branch with `demo`: it was previously only in the target branch, so with `profit_target = 0` it fell through both and defaulted to `0.0`, silently reporting 0% pass for any good personal strategy.
- **`prob_breach`/`prob_pass_eval` are `Optional[float]`, and `None` when the ruleset states no limit.** Not `0.0` (never breaches) and not `1.0` (always does) — there is nothing to breach, which is a third answer. Grading reads them through `_num()`, which falls back ONLY on `None`; the old `value or fallback` was a live bug in both directions, since every metric here can legitimately be `0.0` (a stored `prob_breach = 0.0` was reported to the user as "100% probability of breaching ruleset limit", and a `0.0` drawdown became `inf` and failed every limit check).

**Which SERIES gets shuffled — dollars or returns (2026-07-30).** Reshuffling a dollar P&L list assumes the trades are exchangeable, which is only true at constant position size. A %-risk compounding strategy violates it outright: on run `06f7eece0db1` the median |P&L| per trade drifts **$222 → $3,913 across the run (17.7x)**, so a shuffle was moving late $4k trades to the front of a $10k account and back-loading the small ones — measuring a strategy that never existed. `choose_shuffle_series(trade_pnls, balances)` picks per run: it measures the drift of both the dollar series and the per-trade RETURN series (`pnl / balance_before`, median |value| of the last third over the first third) and switches to returns only when the dollars actually drift (≥ `_DRIFT_TRIGGER` 2.0, ≥ `_DRIFT_MIN_TRADES` 30 trades) AND returns are the more stationary of the two. Same run: dollar drift 17.66x vs return drift 1.42x → returns. Paths then COMPOUND (`start_bal × cumprod(1+r) − start_bal`) instead of `cumsum`. **Fixed-size runs are untouched** — no balance series, or no drift, means dollars exactly as before. This is not a cosmetic change: the same run's worst-1% drawdown went **$41,970 → $359,886**, i.e. the old number understated the tail ~8x.

**Drawdown basis — `dd_basis` (`"percent"` | `"dollars"`).** A compounded run reports drawdown as a percent of the running peak (`median_max_dd_pct` / `pct5_max_dd_pct` / `pct1_max_dd_pct`, alongside the dollar columns, both persisted), because a fixed dollar limit stops being comparable to an account that has grown away from the size the limit was written for. The dollar view of that same run reported a **100% breach of TOTAL RUIN across 20,000 simulations in which the account was never once wiped out** — real ruin 0.00%, real worst-1% drawdown 61%. `prob_breach` is measured on whichever basis the grade will read, so the headline number and the letter can never come off different bases and contradict. Rows written before 2026-07-30 carry no `dd_basis` and keep the dollar path, so their stored grades stay reproducible.

**Walk-forward** — sends real backtests to NT8. Splits the original date range into N equal windows. Each window is split 70% in-sample / 30% out-of-sample — two separate NT8 backtests per window. Measures how much Sharpe drops from in-sample to out-of-sample. Large drop = strategy may be overfit to the training period. **Degradation is only computed over windows with a MEANINGFUL positive IS Sharpe** (the serial/MT5 path) — `1 − OOS/IS` is a meaningless signed ratio when IS Sharpe ≤ 0, and *explodes* when IS Sharpe is a tiny positive (a flat in-sample window with Sharpe ~0.002 once produced a 539,229% per-window value → 134,540% average). So windows below `_WF_IS_SHARPE_FLOOR` (0.1) are excluded as not-assessable, and each surviving window is clamped to `_WF_DEG_CLAMP` (`[-100%, +200%]`) before averaging. If no window qualifies, degradation is stored as `None` → UI shows "n/a (IS Sharpe ≤ 0)" and grading treats it as not-run (neither credit nor penalty). The native NT8 WF path (optimization-derived runs) degrades on **profit factor**, not Sharpe (no per-trade data), so the signed-ratio sign-flip can't occur — but it applies the **same honesty rule**: when no window has IS PF > 0, degradation is stored as `None` (not `0.0` — `0.0` would read as "0% = solid robustness" for a strategy unprofitable in every in-sample window), and grading's not-assessable reason is PF-worded ("IS profit factor ≤ 0"). Both WF paths now treat unassessable degradation identically (`None`); `0.0`-as-solid is gone from both. **Thin windows are excluded too (`_WF_MIN_TRADES_PER_WINDOW = 20`, 2026-07-30):** a Sharpe off 6 out-of-sample trades is noise wearing a decimal point, and averaging it in produced a confident-looking degradation figure with nothing behind it (measured windows on run `06f7eece0db1`: IS/OOS = 15/6, 24/6, 10/6, 16/12, 22/8 — every one thin). `window_data` now carries `is_trades`/`oos_trades` so the filter can see them, and when every window is thin the degradation is `None` with a reason that names the fix ("the windows closed too few trades each to support a Sharpe. Re-run with fewer walk-forward windows") rather than the generic IS-Sharpe wording, which would be a false diagnosis.

**Sensitivity** — re-runs the strategy with each numeric parameter shifted, one VPS backtest per shift. **Only STRATEGY-LOGIC params are perturbed** — foundational params (`category == "foundational"` or the MQL5 `f_` prefix) are excluded via `_is_foundational`, the same split the optimizer tunes; perturbing injected config (often at the `-1` sentinel) is wasteful and meaningless. Booleans are skipped. **Scored on PROFIT FACTOR, not net P&L (2026-07-30, Aaron's call):** `degradation = |child_pf − baseline_pf| / baseline_pf`. Net P&L is not scale-free, so any parameter that moves position SIZE dominates the score by construction — on run `06f7eece0db1` `exec_risk_pct` read **85.8% on profit and 11.8% on profit factor**, and since the field is a max across params it single-handedly set the run's score to 85.8% (true worst on PF: `aplus_window` at 12.6%). That is a sizing knob doing exactly what it is supposed to do, graded as fragility. Excluding the param instead would have been overfitting the engine to one strategy; changing the metric is generic. `pnl_delta` is still recorded per shift (the frontend keeps it as a legacy field), and `degradation` is `None` — never `0.0` — when the baseline PF is missing or non-finite. **A shift that changes nothing is skipped, not run:** integer rounding made 43 of this run's 60 sensitivity backtests reproduce the baseline exactly (a ±10% shift on a param whose value is 1 rounds back to 1), which is ~50 minutes of VPS time measuring the same number. `seen_vals` also dedupes shifts that collide with each other. Both are reported in `skipped` — a silent skip would read as coverage that never happened. Large swings = strategy is fragile to exact parameter values. **MT5 uses 2 shifts (±10%)** to limit queue depth; NT8 uses 4 shifts (±10% and ±25%). `SHIFTS` in `stress_tester.run_sensitivity_task()` is runner-aware. The UI time estimate, the note's backtest count, and the run loop all read from shared helpers (`sensitivity_param_count` = perturbed (non-foundational) count, `sensitivity_shift_count` = 2/4 by runner) so they can't drift — `_estimate_sens_duration_min(n_params, runner)`.

**Auto-trigger** — fires MC only (no NT8) automatically when a Tier 1 backtest completes or an optimizer picks a winner. Manual trigger always runs all three phases (MC + walk-forward + sensitivity); no user checkbox.

**Sample-size gate** (`stress_tester.MIN_TRADES_FOR_STRESS = 100`) — one flat floor: below 100 trades the WHOLE stress test is blocked, not just walk-forward. Rationale: the page's output is the A–F grade, and the grade leans on Monte Carlo TAIL percentiles (A = worst-1% drawdown, B = worst-5%) that small samples can't estimate — so a sub-100 grade is false confidence, the same disease as the 134,540% walk-forward number. `POST /stress-tests/run` returns **422** below 100 and `trigger_auto_stress_test` skips (so Tier 1 runs with 50–99 trades get no auto Monte Carlo either). `BacktestDetail.tsx` mirrors the constant and disables the Stress Test button below 100 with an explicit tooltip — backend is authoritative. Clear the bar with more DATA (longer period, more instruments, smaller timeframe), never by loosening params to inflate the trade count (that just curve-fits).

**Child run isolation** — walk-forward and sensitivity runs are inserted into `backtest_runs` with `stress_test_id` set. `lab_db.list_runs()` always adds `r.stress_test_id IS NULL` to its WHERE clause so they never appear in the Runs tab. They're accessible only from `StressTestDetail`.

**Market lock** — `lab_db.running_stress_test_markets()` queries `stress_tests WHERE status LIKE 'running%'` (covers `running`, `running_wf`, `running_sens`), joins to derive `runner`, returns `{futures, forex, run_ids}`. `POST /stress-tests/run` checks this before inserting; 409 if same market is already running. `GET /stress-tests/running-lock` exposes it for the frontend poll.

**Crash recovery** — `lab_db.reset_stale_stress_tests()` marks any `running%` stress tests as `failed_crashed` and their child runs as `failed_timeout`. Called in `main.py` `startup()` — backend restarts automatically clear stuck tests and release the market lock.
