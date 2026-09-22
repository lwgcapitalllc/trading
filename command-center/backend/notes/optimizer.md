# Notes — Optimizer and worthiness

Worthiness tiers, objective functions, how the optimizer picks and reports a winner. Moved VERBATIM out of `command-center/backend/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## Worthiness scoring

`services/worthiness.py`. Scored against the strictest evaluated ruleset. Prop rows win the pick; a run evaluated against personal/demo rulesets only (e.g. a forex run — no prop firm covers forex) is scored against the strictest of those, so forex runs still get a tier.

| Tier | Criteria |
|---|---|
| **Tier 1 — STRESS_TEST** | PF > 1.3 AND DD ≤ firm limit AND DD not in danger zone AND trade_count ≥ 50 |
| **Tier 2 — OPTIMIZE** | PF in [0.8, 1.3] OR DD in danger zone (0.7×–1.0× of limit), trade_count ≥ 30 |
| **Tier 3 — DISCARD** | PF < 0.8 OR DD > firm limit OR trade_count < 30 |

Columns on `backtest_runs`: `worthiness_tier`, `worthiness_reason`, `worthiness_computed_against_firm` (firm_id of the strictest firm used). Added via migration — not in the original CREATE TABLE.

🔴 **The drawdown and its limit are compared in ONE unit, and the RUN decides which (2026-09-13).**
Percent of the running peak when the run compounded, dollars otherwise — `stress_tester.drawdown_basis`,
the decision the Monte Carlo makes for its own `dd_basis`, off the same `trade_series`. It compared
dollars always until then, and a compounding run's late dollar drops dwarf a limit written for its
opening size: run `952f14f8172e` lost 46.84% from its peak against the 55% ruleset and would have
scored DISCARD ($1,051,553 is past $5,500). No stored run carried a score, so nothing was re-scored.

- ⚠ **"Strictest" is the smallest limit IN THAT UNIT** — $2,000 on $50,000 (4%) is the smaller
  dollar limit and the looser percent one beside $3,000 on $100,000 (3%).
- ⚠ **`equity_curve` is keyword-only with NO default.** `None` is a real answer (a native optimizer
  combo carries KPIs only and is judged in dollars), so every caller states it;
  `test_every_caller_states_which_curve_it_is_scoring` walks the source for one that forgets.
- ⚠ **A fixed-size run under a personal ruleset stays in dollars** (`account_size × pct`), as its
  stress test does. That ruleset's own rule is percent-from-peak; the two agree while the account
  sits near its opening size, and one unit shared with the grade was kept over a second rule here.

Tests: `tests/test_worthiness.py` (7); 4 mutations planted in memory, 4 killed.

---

## Objective functions

`services/objectives.py`. Two registered objectives; chosen by `mode`:

- **`eval_pass_probability`** (default) — score 0.0–1.5. 1.0 = DD ok + target hit; speed bonus up to +0.5 for hitting target in fewer than 30 simulated days. Partial credit (0–0.5) if DD passes but target not reached. 0.0 if DD breached.
- **`funded_sharpe_under_drawdown`** — Sharpe ratio if DD within limit, −∞ if breached. Used when `mode = "funded"`.
- **`raw_profit_factor`** — profit factor, straight. Used when `mode = "raw"`, which is **every MT5 and every Python optimization**. ⚠ It has no opinion about sample size: two lucky trades at PF 8.0 outrank two hundred at PF 2.0. The floor that stops that is `optimizations.min_trades`, applied in `_pick_best_run` and **not** inside the objective — a combo below the floor is still run, still scored and still listed, it just cannot WIN.

⚠ **−∞ is how every objective here says INELIGIBLE**, and `_pick_best_run` starts at −∞ with a strict `>`, so a field where *every* combo is ineligible used to leave `best_run_id` NULL — a finished optimization with no ★ and nothing on the page explaining it. See the fallback ladder below.

---

## The optimizer's winner — three fallbacks, each of which must SAY SO

`_pick_best_run` returns `(best_run_id, winner_note)`. An optimization that names no winner is
useless, so falling back is right; a **silent** fallback is this repo's signature defect — a
page claiming something the code did not do. `winner_note` is stored on the row and rendered as
an amber banner above the results.

1. The stated scoring (objective + regime filter + trade floor).
2. Trade floor excluded everything → drop the floor, keep the scoring. *"No combination reached
   the N-trade minimum… treat it as a small sample."*
3. Regime filter matched no trades in any combo → re-score on ALL trades. *"…the regime filter
   did not apply."* ⚠ This one was a hard NULL before: `_regime_filtered_score` returns −∞ when
   a run has no trades in the target regime, and on a filter that matches nothing that is every
   run.
4. Everything still ineligible → highest profit factor, flatly. *"Read it as a ranking, not a
   pass."*

---

## Optimizations — the 2026-08-04 audit

The `optimizations` table was **EMPTY** when this ran, which is the frame: the page had never
been driven end to end, so every defect was latent and none had been caught by use. UI half in
`../frontend/CLAUDE.md`.

✅ **DRIVEN AGAINST THE LIVE BACKEND AFTERWARDS, not only unit-tested** — four real python
optimizations on cached XAUUSD M15, because a page nobody has run is not a page anybody has
tested, and that is the whole reason this list existed.
- **The hang is gone at the seam that matters**: `step: 0` posted to the live server returned
  `400 exec_risk_pct: step must be greater than 0` in milliseconds and the backend kept
  answering. Before, that request never returned and took every other endpoint with it.
- **Costs are CHARGED, not just carried.** The same 4-combo grid (`exec_tp1_pct` 0→45, Jan 2024
  → Jun 2025) run free and then with `spread`+`swap` on `vantage_demo`: PF 2.631/2.478/2.308/
  2.119 → 2.551/2.400/2.230/2.041, P&L $33,228/$28,323/$23,443/$18,624 → $31,149/$26,408/
  $21,703/$17,069. ⚠ **Trade counts identical at 33 across all eight runs** — which is the
  check that says the charge is real and correctly placed: spread and swap change what a trade
  MAKES, never whether it happens. A grid where the trade count moved would mean something else
  had changed.
- **Cancel stops the work.** A 6-combo full-history sweep cancelled mid-flight returned
  `job_stopped: true`, then sat at `failed_cancelled` with **0 runs written for 100+ seconds**
  and never flipped to `complete`; the platform lock released immediately (a new optimization
  was accepted straight after). Before, that sweep would have run to the end and overwritten
  its own cancelled status.
- **The fallback ladder fires and speaks.** `min_trades: 500` on a window that produces 4
  trades completed with a winner and the note *"No combination reached the 500-trade minimum,
  so the winner is the best of the whole grid. Treat it as a small sample."*
- **Robustness anchors on the ★** and the payload trim holds: a combo row came back with
  `params` = `{"exec_tp1_pct": 0.0}` alone, out of the strategy's full config.
- **Delete cleans up**: all four removed 204, leaving zero orphaned `backtest_runs` and zero
  orphaned `evaluations`.

🔴 **A `0` typed into a step box hung the WHOLE BACKEND.** `_expand_axis` expanded a range with
`while v <= hi: v += step` and never checked `step`, so zero (or a negative step, or a max below
the min with one) appended forever — and it ran **on the event loop inside the request
handler**, so it took every endpoint with it, not just this optimization. The range is counted
arithmetically now (`n = floor((hi-lo)/step) + 1`, which also stops the old loop's float drift),
and `_expand_axis` **raises** on step ≤ 0, max < min, non-finite values, an empty value list, or
an axis over `_MAX_AXIS_VALUES`. `validate_param_grid()` runs at REQUEST time → 400, and
`expand_grid` moved off the event loop. ⚠ **The ceiling is checked from the COUNT, before the
list is built** — a guard that materialises the thing it is guarding against is the event.

🔴 **Cancel did not cancel.** `POST /cancel` wrote `failed_cancelled` to the row and nothing
else: the sweep kept every core busy, the per-platform job lock (which reads that status) said
the platform was free so a second job could start on top of it, and the finished job overwrote
its own cancelled status with `complete`. Cancel now calls `runner_dispatch.cancel_job` —
runner-agnostic, three implementations behind one call — and the native poller checks the row's
status each tick and abandons the job. ⚠ It reports **`job_stopped`**: the row is cancelled
either way, but "stopped" and "could not tell it to stop" are different facts and only one of
them means the machine is free.

🔴 **Every grid was ranked on a FREE BOOK** while the run it was launched from had spread and
swap charged — two numbers produced under different physics, presented as a comparison.
`optimizations` gained `cost_layers` + `broker_profile`, the modal inherits them from the source
run, and they ride the spec into `python_runner._cost_profile`. ⚠ **NULL is not `[]`** here
either: NULL = a row predating the column, which keeps the old behaviour rather than being
silently re-priced on its next re-run.

🔴 **Delete and re-run both 500'd on a foreign key.** `stress_tests.run_id` and
`evaluations.run_id` are FKs into `backtest_runs` under `PRAGMA foreign_keys=ON`.
`delete_optimization` purged evaluations but not stress tests; `reset_optimization_for_rerun`
purged neither — so **re-run crashed on every optimization that had a ruleset** (NT8 writes an
evaluation row per combo). Both go through `_purge_stress_tests_for_runs` now. Re-run also
clears `best_run_id`, `winner_note` and the grid-sensitivity columns: a re-run re-measures, and
carrying them forward describes a grid that no longer exists.

🔴 **"Winner robustness" was measured on a combination that is not the winner.**
`_compute_grid_sensitivity` ran BEFORE the winner existed and anchored itself on the highest
profit factor. That is the same row only under `raw` mode with no trade floor — under `eval` or
`funded` the objective is not profit factor at all, and with `min_trades` set the top row may be
the very fluke the floor exists to exclude. It runs LAST now and takes the ★'s own params. ⚠ **It returns
`None` — never 0.0 — when the question cannot be answered** (winner absent from the grid after a
retry, winner PF ≤ 0, one value per axis, empty grid), and the caller then writes nothing so the
column stays NULL and the card does not render. **0.0 is the PERFECT-PLATEAU score**, the
strongest "trust this winner" the metric can say, so using it for "not measured" prints the most
reassuring number on screen exactly when nothing was checked. Same rule as `mt5_link` and
`mt5_connected`: never let "no" and "cannot ask" be the same value.

**`fail_optimization` stamps `completed_at`.** Without it the page had no end to measure against
and fell back to now(), so a job that died on Tuesday read `Ran for 74h` and kept climbing. **A
failure is a finish.**

**Write batching.** A native combo arrives already finished, so the whole grid is one
`insert_complete_optimization_runs` executemany instead of insert + update per combo (~2 sqlite
connections each — 2,000 on a 1,000-combo grid), evaluations come back through
`get_evaluations_for_runs` in one chunked query instead of one per combo, and worthiness writes
through `update_run_worthiness_bulk`. The evaluator loop is skipped wholesale when there is no
ruleset, which is every Python optimization. ⚠ `get_evaluations_for_runs` **chunks at 500** —
SQLite's default host-parameter ceiling is 999 and the thousand-combo case is the entire point
of the function — and it keys **every** requested id, because a missing key and an empty list
are different answers.

**`GET /{id}` trims the payload** to the grid's own param keys per combo (a combo's stored
params are fixed+swept, 50+ keys on a Python strategy) and moved its `job_status` call off the
event loop — for NT8/MT5 that is an HTTP round trip over the SSH tunnel, polled every 3 seconds.
⚠ It is a **projection**, not a deletion: the full params stay on the row.

## A grid can now tune a strategy whose re-entry layer is on (2026-09-20)

- **Before this, the sweep refused any grid whose config wanted the second, faster bar stream.** SOS Fade ships with its re-entry on, so none of its settings could be tuned at all.
- The sweep now loads ONE extra frame and hands it to every combo that asks for it. A grid that sweeps the re-entry's own fill clock is refused by name, because one frame cannot serve two clocks.
- **A grid must also survive the strategy re-import.** The backend purges and re-imports every strategy package before each scan and run. A combo pickled to a worker after that purge failed with "not the same object as …" (grid `opt_2d74db78e9`, 2026-09-20, 0 of 108 combos ran). A combo now pickles its config as class path plus values and is rebuilt in the worker. Fix: `backtest/optimizer.py`.
- ⚠ **A grid job lives in memory. A backend restart kills it as crashed, and so does saving any backend `.py` file,** because uvicorn is started with reload. Measured 2026-09-21: the rerun died at 11 of 108 when the backend restarted.
- ⚠ **Grid combos store no trade list.** Ranking a grid in R means re-running the shortlist as full runs, where each trade's R sits in `equity_curve.json`.
- TESTED: `backtest/tests/test_combo_pickles_after_reimport.py` (two tests watched red on the production error), `backtest/tests/test_sweep_second_stream.py`. MEASURED: grid `opt_2d74db78e9` completed all 108 combos.
