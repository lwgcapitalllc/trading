# Notes — Stress Tests, Tuning workbench and Optimizations pages

The 2026-08-04/05 audits of the Stress Tests page, the Tuning workbench and the Optimizations page, plus the shared ProgressCard pattern. Moved VERBATIM out of `command-center/frontend/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## The Stress Tests page — audited 2026-08-05

`pages/StressTestDetail.tsx` + `StressTests.tsx` + the four charts. **The frame is one query: the
`stress_tests` table held ONE row, written 2026-07-27 — three days BEFORE the accuracy pass that
rewrote this engine.** So the page had been driven end to end exactly once, against code that no
longer existed, and nothing had re-scored the stored row since. Every defect below is what that
looks like from the browser.

**And the shape they share is the Overview's: not one of them rendered an error.** A magnitude drawn
as a loss, a null drawn as 0%, a dollar figure drawn under a grade decided in percent — each renders
a confident number.

### Both stress test windows pick the 55% ruleset first (2026-09-16)

Aaron: *"we should always default to the 55% one"* (`src/lib/stressRuleset.ts`). The single-run
window offers it on a FOREX run even when the run was never evaluated against it; a futures run
keeps the strictest of its own evaluations. The stack window puts it ahead of the ruleset the stack
was last graded against, and warns (`stack-ruleset-differs`) when the two differ, because the
grades will not compare. ⚠ **An explicit "No ruleset" is sent as `null`** — an omitted field gets
the server's 55% default (`backend/notes/stress-tests.md`). Test: `tests/stress.spec.ts`, the last
check, which intercepts the start and never launches a test.

### The drawdown was shown in a unit the grade did not read

🔴 **The engine picks its basis per run** — `dd_basis` is `percent` on a compounding run (the
2026-07-30 fix: shuffling dollar P&L on a run whose trade size drifts 17.7x simulates a strategy
that never existed) and `dollars` otherwise. The page read **neither `dd_basis` nor the percent
columns**. It printed dollars against a dollar limit and coloured them over/under, while the letter
beside them had been decided on percentages — **so a red "over limit" could sit next to an A**.

`dd(dollars, pct)` is the one derivation: on the percent basis it renders the percent and compares
it to `ddLimitPct`, on the dollar basis it renders dollars against `ddLimit`. ⚠ **It shows ONE of
them, never both** — showing a percent drawdown beside a dollar limit is what invited the
comparison in the first place — and a `basisNote` says which unit is in force and why.

⚠ **A prop ruleset's percent limit is DERIVED** (`ddLimit / account_size`), a personal one's is
stated (`max_drawdown_from_peak_pct`). Do not swap them: a trailing dollar floor and a
peak-relative percentage are different rules, and this is the same distinction `DrawdownMeter`
already refuses to blur.

### Null was rendered as zero, in two places, both reassuring

🔴 **`st.prob_pass_eval ?? 0` printed "0%"** — *this strategy never passes the eval* — for a
measurement that was never taken. The backend made both probability fields `Optional[float]`
specifically so a ruleset with no limit could say **nothing to breach**; the page collapsed that
third answer into the worst of the two real ones. It says `no limit to breach` now and renders no
probability card at all.

🔴 **A sensitivity shift whose backtest FAILED was drawn as a flat zero bar** — "tested, no effect",
the most reassuring answer available. Rows with no measurement are DROPPED from the radar
(`if (magnitude == null) continue`), and the coverage line says how many.

🔴 **A completed test with no letter rendered a card with no letter and no explanation**, which
reads as a broken page. `grade_reasons` had been computed and stored since the accuracy pass and
**nothing displayed it** — the one thing that says *why* there is no grade. It renders now, beside
`phase_failures` and `results_error`.

### A magnitude drawn as a direction

🔴 **`degradation` is `|Δ| / baseline` — a MAGNITUDE — and the page drew `-degradation * 100`**, so
every shift rendered as a loss and "Median Change" was negative by construction. **A parameter shift
that IMPROVED the result was drawn as a long red bar.** The engine now records `pf_delta_pct`
(signed) alongside it; the radar reads `pf_delta_pct ?? pnl_delta_pct ?? null`, ranks on
`magnitude`, and paints neutral when the direction is genuinely unknown rather than inventing one.

⚠ **Ranked by magnitude, capped at `TOP_N = 24` with a show-all toggle.** A 60-shift run rendered 60
rows at 11px; the worst shifts are the point and the tail is scroll.

### Walk-forward: the numbers the verdict turns on were dropped by the model

🔴 **`is_trades` / `oos_trades` were written by the engine and undeclared on `WalkForwardWindow`**,
so Pydantic stripped them and the page could never show that **every window on the stored test
closed 6 out-of-sample trades** — under the engine's own 20-trade floor, i.e. a degradation figure
with nothing behind it. **This is the `entry_ms` / `exit_ms` / `favorable` trap for the fourth
time**; the rule in `backend/CLAUDE.md` is not an anecdote. Thin windows now fade to 0.22 opacity
and a caption reads `5 of 5 windows too thin`.

🔴 **The native path writes `is_sharpe: null` deliberately** (it has no trade-level data and degrades
on profit factor), and the chart did `is_sharpe ?? 0` — **five pairs of zero bars asserting "Sharpe
0.00 in and out"**. It detects the PF shape and reports profit factor, with `not measured` in the
tooltip for a genuine null.

### The fan drew a reference it cannot support

🔴 **`MonteCarloFan` drew a `ReferenceLine` at `y = -max_loss_eod` on a CUMULATIVE-P&L axis.** A
drawdown is peak-to-trough, so a path can breach many times over without ever crossing a line below
zero — **a fan sitting entirely above it read "no simulation breaches" while Prob. Breach said
otherwise.** Removed. The histogram, which actually measures drawdown, keeps its limit line and
takes a `unit` prop so it is labelled in the basis it was measured on.

### The rest

`WF_MIN_TRADES_PER_WINDOW = 20` mirrors the backend and drives a **live feasibility warning in the
Run modal** — the windows slider says `~10 OOS trades per window` before you spend an hour finding
out. A **Stop** button (`useCancelStressTest`, distinguishing `job_stopped` the way the optimizer's
cancel does). `phases_requested` drives the pipeline stepper, so a walk-forward-only test no longer
draws a Sensitivity step that can never complete. The list page gained a basis-correct **Worst 1%
DD** column, `n/a` instead of blank for null probabilities, and a `not graded` chip. And a
`Fragment key={step.key}` — the stepper was building a keyless array.

### `tests/stress.spec.ts` — 11 checks, all 11 watched to fail

Every one is red against the page at `HEAD` and green against the fix. Same mock discipline as the
Overview's and the Tuning workbench's: the states cannot be produced on demand — a compounding run
graded on percent, a crashed walk-forward, a native path with no Sharpes, a shift whose child failed
— so they are built by **MUTATING the real detail response**, never hand-written.

⚠ **Two locator traps this suite had to learn, and both produce a VACUOUS PASS rather than a
failure.** `page.locator('svg').first()` is the **sidebar logo** — a page-wide search for an absent
element passes on any page, including the broken one, so the fan's no-limit-line check proved
nothing until it was scoped to the fan's own container. And a chart label appears three times (the
KPI card, the chart `<tspan>`, and Recharts' hidden `#recharts_measurement_span`), so a bare
`getByText` is a strict-mode violation rather than a miss — scope to `locator('tspan', {hasText})`.

---

## The Tuning workbench — audited 2026-08-05

`pages/TuningWorkbench.tsx`. Edit a completed run's params, fire an iteration, compare the children
against the baseline in a leaderboard + equity overlay + per-regime table. Route:
`/backtests/runs/:runId/tune`.

**Everything on this page is a COMPARISON, and that is the frame for every rule below.** A number
here is never read on its own — it is read as a difference from the baseline — so anything that
makes the child and the parent incomparable is a defect even when both numbers are individually
correct. Both of the audit's worst findings were of exactly that shape, and both were invisible
unless you checked a child against its own parent.

### The iteration is measured on the baseline's physics

`runIteration` carries `cost_layers`, `broker_profile`, `sizing_mode` and `manual_risk_pct` off the
baseline's detail, alongside the window and the legacy `commission_per_side`/`slippage_ticks`. It
sent only the last two until 2026-08-05, so an iteration off a charged run ran **free** and the Δ
column blamed the param for the difference.

🔴 **From 2026-08-24 to 2026-09-13 the layers it sent were OVERWRITTEN.** The cost switch landed
with a default of TRUE and this page never sent it, so the backend re-resolved every iteration to
the full charged set — an uncharged baseline sat beside charged tweaks while the caption above the
Run button said "no costs charged". It sends `charge_costs: null` (keep the layers as sent) and the
baseline's lot ceiling (`max_lots`, omitted when the baseline never recorded one). The run page's
free/charged twin (`CostPairButton`) was missing the ceiling the same way.

MEASURED against the live backend, same params, same window, same strategy — one iteration fired
with the new body and one with the old:

| body | layers stored | PF | net P&L | trades |
|---|---|---|---|---|
| new (costs carried) | `['spread','swap']` | 1.499 | $3,157.33 | 17 |
| old (no cost fields) | `[]` | 1.581 | $3,646.75 | 17 |

**Trade counts identical at 17** is the check that the charge is real and correctly placed: spread
and swap change what a trade MAKES, never whether it happens. A row where the count moved would
mean something else had changed.

⚠ **`cost_layers: null` on the baseline is sent as `[]`, never as `null`.** `null` means "a run
written before layered costs existed" — a contract a NEW run cannot be created under — and `[]` is
its honest equivalent, charging exactly the same nothing. The distinction still matters everywhere
it is READ; it just has no meaning on the way in.

⚠ **The panel STATES what it is carrying**, above the Run button (`no costs charged` / the layer
names + broker, and the sizing mode). The fix and the caption landed together on purpose: a page
that silently inherits is one refactor away from silently not inheriting.

### Everything the request sends and the button promises comes from ONE key set

`knownParams` = the baseline's own params ∪ the current schema. The changed-count on the button, the
dot on the collapsed panel and the params in the request are all filtered through it, so the button
can never promise a change the request then drops. It only ever bites on a `sessionStorage` edit for
a param that has since disappeared — and a request carrying an input the runner does not declare is
worse than a dropped edit, because MT5 treats a set file with an unknown input as mismatched and
silently runs a single backtest instead.

### Edits are persisted, not guarded

`sessionStorage`, keyed per baseline run, cleared when the edits are spent. Clicking a leaderboard
row to inspect it is the common way to leave this page, and losing the form was the complaint —
**persistence rather than a navigation-guard dialog, because nothing lost means nothing to warn
about.** Reset is enabled whenever an edit is HELD, not only when one differs from the baseline: a
value typed and typed back is still an edit sitting there, and greying out the only way to clear it
made the button look broken.

### The leaderboard ranks, the ★ has a floor, and Max DD is a percent

- **Sorted by profit factor**, because that is what the caption says. Rows with no PF (running,
  failed) sink to the bottom, newest first.
- **`MIN_STAR_TRADES = 10`**, and the caption names it. A PF off a handful of trades is not a
  measurement, and a threshold nobody can see is indistinguishable from a bug when the obvious
  winner has no star. The **Trades delta is uncoloured on purpose** — fewer trades is not worse, it
  is a different sample, and it is the number to read before trusting a ★.
- **`max_drawdown_pct` leads, dollars beneath.** Same rule as the Runs list (2026-08-01): a dollar
  drawdown beside a compounded profit reads an order of magnitude too small. A **negative value is
  the backfill's "measured, no answer" sentinel** and is never rendered — the cell falls back to
  dollars. Deltas are in percentage points when both sides have a percent, dollars otherwise, and
  the two are never mixed.

### Iterations are DESCENDANTS, and `source_run_id` is not exclusive to tuning

The tree is walked breadth-first with a seen-set (a cycle cannot hang the page), so tuning an
iteration keeps the grandchild on the page that compares it. ⚠ **A sweep or an optimization launched
from a run stamps `source_run_id` too**, so both are excluded by their own ids — before this they
would have shown up here as tweaks. Stress-test children never reach the client (`list_runs` filters
them server-side).

### Colours come from creation order

The palette is assigned by `created_at` among the iterations, not by table order. Table order moves
— a finishing iteration re-sorts the leaderboard — and colouring off it meant **every line on the
chart swapped colour underneath the reader** whenever a run completed. Creation order never changes
for a run that already exists.

### The payload: fetch the timeline once

Each run's detail is 137 KB and `regime_timeline` is 96 KB of it (measured, 165-trade run) — the
same full calendar for every run in the window, and the chart bands off exactly one copy. The
baseline is fetched whole; the iterations go through **`GET /backtests/runs/{id}?timeline=false`**
(49 KB). Two guards, both load-bearing:

- **Only slimmed when the BASELINE actually carries a timeline.** A run completed before the backend
  emitted one falls back to the iterations' own sparse tags, and slimming would leave the chart with
  no bands at all.
- **Cached under `['lab','run',id,'slim']`, never `['lab','run',id]`.** That key belongs to the run
  page, which renders the timeline; handing it a stripped copy would blank the bands over there
  instead. Prefix invalidation still reaches both.

### Smaller things worth not undoing

- The fullscreen chart's height is **measured with a `ResizeObserver`**, not read once from
  `window.innerHeight` — same pattern as BacktestDetail's fullscreen panel. The inline chart
  unmounts while fullscreen is open, so there is only ever one live chart.
- The baseline's `dot`/`activeDot` renderers are **memoised**. Recharts repaints every dot when the
  prop is a new function, so a keystroke in the param editor was redrawing 165 markers.
- Runs are named by **what they changed** (`exec_tp1_pct=40 · exec_tp2_pct=30 +2`) in the chart
  legend, tooltip and regime headers — a `Tweak 15f0122a` in a legend tells the reader nothing. The
  table's Run cell keeps the short form, because the Changes column beside it already spells out
  old→new.
- **A loading chart says so.** "No completed runs to chart yet" was rendered during the fetch, which
  is the state that arrives on every single visit.
- ⚠ **One audit finding was wrong and is recorded as wrong: `copyChartAsPng` already toasts on every
  failure path.** The call site ignoring its boolean is not a silent failure, and a second toast
  would have double-reported it.

---

## The Optimizations page — audited 2026-08-04, and it had never been run

The `optimizations` table was **EMPTY** when this audit ran. That is the frame for everything
below: the page had never been driven end to end, so every defect was latent rather than
corrupting data, and none of them had been caught by use. The backend half is in
`../backend/CLAUDE.md`; this section is the UI half.

**What a reader could not see, and now can.**

- **Winner robustness** (`RobustnessCard`). The backend has computed `grid_sensitivity_score`
  on every native optimization since that pass landed, and stored it, and **nothing rendered
  it** — the one number a parameter sweep exists to produce was the one number the page did not
  show. 0 = the settings either side score the same (a plateau you can trade); 1 = they
  collapse (a lone spike, i.e. a number fitted to this history). The per-param breakdown prints
  each neighbour's PF and its % drop.
- **`BaselineRow`** — the run the optimization was launched FROM, beside the winner. Without it
  the grid is a ranking with no reference point: you can see which combination won and not
  whether it beat the settings you already had, which is the only question that decides whether
  to adopt it. It reads `opt.source_run_id` through `useBacktestRun`.
- **`winner_note`** — an amber banner when the ★ was picked by a FALLBACK rather than by the
  rule the chips above it name (an empty regime-filtered population, a trade floor that
  excluded everything). Falling back is right, because an optimization with no winner is
  useless. Falling back *silently* is this repo's signature defect.
- **A costs chip.** A grid ranked on a free book is not comparable to a priced run, and nothing
  said which one you were looking at. ⚠ `cost_layers === null` ("not recorded", a row predating
  layers) and `[]` ("none charged") are worded **differently** on purpose.

**Things that were true on screen and wrong.**

- `useElapsed` returned a number for a finished run with no `completed_at`, counting up from
  `Date.now()` — so a failed optimization read `Ran for 74h` and kept climbing. It returns
  `null` now and the page draws `—`. The backend stamps `completed_at` on failure too.
- `fmtOptStatus` labelled `failed_cancelled` as **Failed** on the list page while the detail
  page said **Cancelled** for the same row. One row, two words. `fmtOptStatus` gained the case.
- ★ fell back to `i === 0` when `bestRunId` was absent, so with the table sortable the star
  followed the sort and appeared to crown a different combination. **★ is the winner the
  BACKEND chose, or nothing.**
- The Retry-N-failed button rendered *while running* too. `retry-failed` calls
  `ensure_platform_idle`, and the running optimization IS the job holding that platform, so the
  request could only ever 409 — a button whose single outcome was an error toast. Removed;
  cancel first, then retry.

**Two toasts, and the useful one was the one thrown away.** Every optimization mutation's
`onError` read `(e as {detail?: string}).detail` off an error that never carried it, so the
branch could not fire and a generic message toasted **on top of** the one `api.request` had
already shown. `api/client.ts` now throws **`ApiError`** (carrying `status` + `detail`) and the
optimization hooks have **no `onError` toast at all**. ⚠ The rule: `request` owns the message;
a hook's `onError` is for BRANCHING on a reason, not for restating it.

**Modal (`OptimizeButton.tsx`).**
- Go is blocked on `comboIncomplete` and on `rangeErrors` (step ≤ 0, max below min). Both used
  to render as `— combos` with Go still enabled, so the run started and died minutes later.
  `rangeProblem()` distinguishes *still typing* from *finished and wrong* and names the param.
- **Cost layers are inherited from the source run** and stated in the modal. Without this the
  whole grid was ranked on a free book and its winner compared against a priced run — two
  numbers produced under different physics, presented as a comparison.
- **`min_trades` (Minimum trades to win)**, defaulted to **30 in the modal** and **0 in the
  API**. Profit factor has no opinion about sample size, so two lucky trades at PF 8.0 outrank
  two hundred at PF 2.0. ⚠ The split of defaults is deliberate: nothing is assumed of a caller
  that states nothing (the 0/0 commission rule), and the modal's 30 is *visible and editable*,
  which is what keeps it from being a silent narrowing. A combo under the floor still runs and
  still shows — dimmed — it just cannot be ★.
- A **runtime estimate**, from the source run's own measured duration × combos ÷ cores. ⚠
  **Python only.** A python sweep replays the same bars this run replayed on this box; NT8 and
  MT5 load data once and parallelise inside their own tester, so per-combo cost there is not
  this run's cost and no estimate is offered rather than a wrong one.

**Payload and render.** The detail endpoint now ships only the **grid's own** param keys per
combo (a combo's stored params are fixed+swept, 50+ keys on a Python strategy), the table and
bar chart sorts are `useMemo`'d, and both pages stopped pulling the **entire** lab run list —
`OptimizationDetail` scopes it to `{ strategy_id }`, and `Optimizations` dropped it outright
(it fetched every run to choose between two empty-state sentences that said the same thing).

**List page.** Runner, winner (with a ⚠ when a `winner_note` exists), and start time are
columns now; Firm prints a short name instead of the raw `lucidflex_50k_eval` slug; the Method
column went (every new optimization is `native`).

---

## ProgressCard pattern (SweepDetail / OptimizationDetail)

Both detail pages use an identical `ProgressCard` sub-component with:
- Left: status icon + label + segmented progress bar + counts
- Right: elapsed/duration timer (`useElapsed` hook) + Cancel button (while running) + Retry-N-failed button (when not running)
- Inline warning when failures accumulate during a run

**Terminal color scheme** (matches Smart Money terminal aesthetic):
- Complete (no failures): `border-accent/20 bg-accent/5` background, `text-accent` status label + icon, `bg-accent` progress bar, `text-accent` count
- Instrument/combo done pills: `border-accent/25 bg-accent/10 text-accent`
- Failed/partial: unchanged (red/amber)
- Running: unchanged (cyan spinner, already matched)

`useElapsed(startIso, endIso, running)` — counts up live when `running`, freezes at final duration when done, and returns **`null`** when a finished job has no `completed_at` (the caller draws `—`). ⚠ It must never fall back to `Date.now()` for a finished job: a failed optimization then reads `Ran for 74h` and keeps climbing, which is how a job that died on Tuesday looked like a job still running.

Per-row retry in `FailedRunsTable`: a `RotateCcw` icon button calls `useRetryBacktest().mutate(run.run_id)`. Spinner activates on the specific row via `retryRun.variables === run.run_id`. `e.stopPropagation()` prevents the row-click navigation from firing.

## Stress Test greys out while its platform is busy (2026-09-22)

Stress Test on a run page and on a stack page, and the Run button inside both stress forms, now
grey out while that platform's slot is taken, with the reason on hover ("A Python job is already
running…"). Before, a Python stack could hold the slot while Stress Test stayed pressable, and its
one outcome was a 409. The reason comes from one helper in `src/lib/runner.ts`, worded like the
backend's refusal. Rerun, Optimize and "Run this free" already followed the same flag.
⚠ A browser test that opens a stress form off the REAL lab must state the platform free: whether a
job is running is the live lab's state, and `stress.spec.ts` went red on a day a stack was running.
Pinned in `tests/stress-busy.spec.ts` (run page); the stack page is type-checked, not browser-driven.
