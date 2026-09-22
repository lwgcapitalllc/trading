# Notes — Backtest runs, rulesets, sizing and metrics

How a single run is launched, sized, scored and shown; history floors; comparing runs. Moved VERBATIM out of `command-center/backend/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

### The percentage IS the fraction of the bars done (2026-08-20)

🔴 **Any split of the 0–100 range is a CLAIM about how long each part takes, and the UI draws that
claim.** `python_runner._execute` used to report 5 while loading, 15 on entering the bar loop,
15–94 across the loop and 95 while building results — and the run page drew three evenly-spaced
stages over it, so a few seconds of loading owned half the bar and a 156,721-bar loop crawled
through the other half. The split is now **loading 0–2, the bar loop 2–98, results the rest**, so
the number is near enough bars-done ÷ bars-total to say so out loud and the bar moves at one speed
end to end. MEASURED on a 3-month `sos_fade` run with the 1m re-entry on: 1 → 2 → a straight
climb 2→96 in step with the bars, never once backwards.

⚠ **Reported every 1/500th of the run, not every 1/100th** (`_replay`'s `step`). `_set` is a dict
update behind a lock, so the cost is nothing; the granularity is the whole of what the person
watching sees, and at 1% steps a long run looked frozen between jumps.

⚠ **`run_backtest_job` polls a python run every 1s, everything else every 5s.** A python run
happens IN THIS PROCESS — there is no agent to be polite to and `job_status` is a dict read — so
the 5s interval was capping how often the bar could move however finely the runner reported.
Everything else there is an HTTP call to a machine over a tunnel and keeps the original interval.

⚠ **The messages are sentences a person reads** (*Testing bar 84,384 of 156,721*), because the run
page shows them verbatim and *replaying* is internal vocabulary for stepping the strategy over the
bars. Nothing parses them — checked before changing them.

⚠ **`/lab/progress` is ONE FILE for the whole app**, so it describes whatever job wrote it last and
a page watching one run can be handed another job's numbers. What the run page does about that is
in `frontend/CLAUDE.md` → *The running banner*.

---

## Ruleset abstraction (M3)

The `firms` table is now `rulesets`; `firm_id` is `ruleset_id` everywhere (evaluations, optimizations). The `/firms/*` backward-compat redirect shim (`routers/firms.py`) was removed 2026-07-01 — no callers were found (frontend's `useFirms` is an alias to `useRulesets`, never hit `/firms` directly). `BacktestRunRequest.evaluate_rulesets` replaces `evaluate_firms` (backward-compat alias still accepted). Full migration story is in git history (M3).

**`ruleset_type` values and evaluation logic:**

| ruleset_type | Who uses it | Evaluator behavior |
|---|---|---|
| `prop_eval` | Prop firm eval challenges | EOD trailing max-loss (DISCARD on breach) → profit target (WARN if missed; target is raised when a `raise_target` firm's consistency is breached) → consistency (WARN). PASS if all clear. |
| `prop_funded` | Prop firm funded accounts | EOD trailing max-loss only — PASS if not breached, else DISCARD. No WARN. |
| `personal` | Personal trading accounts | Real PASS/DISCARD verdict against the relaxed personal rules (`_evaluate_personal`): DISCARD on `max_consecutive_loss_days` consecutive days whose loss hit `daily_loss_cap`, or on EOD equity dropping `max_drawdown_from_peak_pct` from its running peak; otherwise PASS. **`INFO` when the ruleset configures NEITHER condition** — see *Nothing checked is not a pass* below. `daily_profit_target` is an informational halt note, never a fail. No trailing MLL (max_loss_eod = 0 sentinel), no profit-target requirement, no consistency rule, no reference line. |
| `demo` | Paper/demo accounts | Same as `personal`. |

**Nothing checked is not a pass (fixed 2026-07-31).** `_evaluate_personal` ended
`verdict = "DISCARD" if failures else "PASS"`, and both of its checks are guarded — check 1 needs
`daily_loss_cap` AND `max_consecutive_loss_days`, check 2 needs `account_size` AND
`max_drawdown_from_peak_pct`. On `unconstrained`, which states neither by design, both were skipped
and `failures` was empty *by construction*: **a run that lost 95% of the account returned PASS.**
Zero failures out of zero checks is the absence of a verdict, not a passing one, and it contradicted
the rule `lab_db.py`'s own seed note states on that row ("a run against it cannot be graded… there is
no honest default to substitute"). It now returns `INFO`, which the frontend already renders
neutrally as **Not graded** with no rule chips. Two things to keep in mind if you touch it: the
"was anything checked" test must **mirror the two guards exactly** (testing the caps alone called a
run graded when a missing `streak_limit` had silently skipped check 1), and because verdicts are
**stored**, the source fix alone leaves history wrong — `init_db` carries an idempotent migration
rewriting stored `PASS` rows on limit-less personal/demo rulesets to `INFO` (every evaluation row in
the live DB was exactly this case). Guard on `!= 0` as well as `IS NOT NULL`: `daily_loss_cap` is
`0`, not null, on both no-limit rows.

For prop types the verdict reads `max_loss_eod` (the trailing-MLL amount) and `mll_lock_balance` for drawdown; it never reads `daily_loss_cap` (a soft/informational field for firms like Apex). For personal/demo types `daily_loss_cap` IS a rule input (the capped-day trigger) and `max_loss_eod` is never read (0 sentinel = no trailing EOD rule). `metrics.effective_dd_limit_usd()` is the one place that turns a ruleset into a dollar MC/objective drawdown limit — personal/demo rows translate to `account_size × max_drawdown_from_peak_pct`. The stress-test primary pick excludes personal/demo rows from its strictest-ruleset comparison; worthiness prefers prop rows but falls back to the strictest personal/demo limit when a run was evaluated against personal/demo only (forex).

`account_tier` is still present on rows (eval/funded/live) — useful for prop rulesets. `ruleset_type` is the broader category.

Columns on `rulesets`: `ruleset_type`, `daily_loss_cap`, `weekly_loss_cap`, `daily_profit_goal`, `description`.

Seeded rulesets (18 rows): 4 prop firms = 14 prop rows — LucidFlex, FundedNext, Tradeify each at 50k/100k × eval/funded (12 rows), plus Apex EOD eval-only at 50k/100k (2 rows; funded/PA not yet seeded) — plus 2 personal demo rows (`personal_forex_demo`, `personal_futures_demo`; ruleset_type `personal`, account_tier `demo`), `unconstrained`, and `personal_forex_risk`. Personal demo rules on a $10k balance: $500 daily loss cap, $1,000 daily profit target, fail at 15% drawdown from peak (`max_drawdown_from_peak_pct`) or 3 consecutive capped-loss days (`max_consecutive_loss_days`) — stored now, enforced in a later evaluator pass. `max_loss_eod = 0` is the sentinel for "no trailing EOD rule" on personal rows (the column is NOT NULL); the evaluator must treat it as rule-absent. All seeded via the per-id idempotent pattern (`_PROP_SEED_ROWS` + `_seed_apex_eod_eval`). The core KPIs of all 14 prop rows (account size, target, drawdown type/amount/lock, consistency, min trading days, contract scaling, funded split, doc links) are documented for hand-off in `command-center/docs/PROP_RULESET_KPIS.md`, which also carries the firm doc links, the saved sync query (`scripts/prop_kpi_audit.py`), and a verification prompt; re-run that prompt to re-check the firms and keep the doc in sync with the DB. Display names: the firm name lives in the UI group header only; `name` carries the program/challenge ("LucidFlex $50k Evaluation", "Select $50k Evaluation", "Futures Flex $50k Challenge", "EOD $50k Evaluation") — canonical map in `_RULESET_DISPLAY_NAMES`, re-applied on every `init_db`. The firm behind the `lucidflex_*` ids is Lucid (Lucid Trading); LucidFlex is its program name.

**The two forex rows are a PAIR, and the difference is the whole point (2026-07-30).** `unconstrained` states no limit, which makes it the honest raw-behaviour view AND ungradeable — every grade in `services/grading.py` is a statement about drawdown vs a limit, and there is no defensible default to substitute (see the ruin walk-back in `grading.compute_grade`). `personal_forex_risk` ("Personal Forex — 55% Drawdown") is the same row with the one bar stated, so the same run returns a letter. 55% is **Aaron's stated tolerance**, picked against his own measured numbers on the SOS Fade SOS Fade run: worst-5% of simulations draws down 53.2%, worst-1% draws down 62.1% — so 55% accepts the 5% tail and explicitly does not accept the 1% tail. Every other limit on it is deliberately absent (no daily cap, no loss-streak rule, no profit target), because at 10–12.5% risk per trade a daily cap fires constantly and the verdict stops being about drawdown.

⚠ **The 15% on `personal_forex_demo` is a PROP-FIRM figure and must never be applied to forex** (Aaron, 2026-07-29). Grading a forex run against it produces a D that says nothing about the strategy. Pinned by `tests/test_rulesets.py::test_the_forex_risk_row_does_not_inherit_the_prop_15_percent`.

---

## Dynamic sizing & risk engine + decision log

The mechanism behind the LWG gated-layer model (`docs/LWG_Strategy_Framework.md`,
`docs/dynamic_sizing_engine.md`): the strategy proposes setups at unit size; gates decide
*whether* a trade is allowed; the engine decides *how big* from the room left now. No strategy
manages risk.

- **`services/sizing_engine.py`** — PURE (no DB/network/clock). `run_engine(trades, ruleset,
  *, is_micro, mode)` where mode is the per-run **bullet/consistent** switch: bullet = the most
  the rules allow (with a one-loss-can't-breach guard); consistent = **room ÷ 7** per trade.
  Room is measured to the **trailing floor** (highest-EOD-based, capped at the firm lock — NOT
  balance−start, so growth doesn't fake a buffer). It reserves **open-trade risk** (a running
  trade holds its risk; the next signal shrinks or is blocked), rounds a sub-minimum size **up
  to 1 only if 1 still fits the room** else skips, applies the daily-loss / profit-target halts,
  and detects breaches. Output: `daily_pnl` (size-correct — feeds `evaluator.evaluate_run`
  unchanged, so no second grader), a day-by-day `timeline`, `sized_trades`, and `decisions`.
  Sizing is goal-driven, NOT % of balance and NOT `daily-loss ÷ trade-count` (both dead).
- **`services/decision_log.py`** — `TradeDecision` / `DecisionLog`, the one reusable audit log.
  One JSONL record per signal (taken or not): idea + setup score, every gate's verdict in order
  (which one shut it down, or that all passed), the sizing decision (size + what bound it, or why
  skipped), and the full life of a taken trade (entry, exit, exit reason, P&L). Gates are an
  ordered list — a new gate just calls `decision.gate(name, passed, reason)`, no schema change.
  Pure stdlib, identical in backtest and live.
- **`services/sizing_pipeline.py`** — the FS/IO wiring: `run_sizing_engine(run_id, trade_records,
  ruleset, *, mode, instrument, strategy, results_dir)` builds `RawTrade`s from a runner's export,
  runs the engine, and persists `decisions.jsonl` + `engine_timeline.json` + `engine_daily_pnl.json`
  to the run dir. `size_run_for_rulesets(...)` sizes once per ruleset and additionally writes every
  firm's `{kpis, daily_pnl, timeline}` to `ruleset_sizing.json`, keyed by ruleset id, so every
  evaluation carries its own P&L, timeline, and equity curve (not just the primary/headline
  ruleset) — this is what lets BacktestDetail switch all ruleset-dependent charts/KPIs per firm.
  Locks the runner→engine column contract.
- **Tests:** `tests/test_sizing_engine.py` (20), `tests/test_decision_log.py` (7),
  `tests/test_sizing_pipeline.py` (7) — all green.

🔴 **`sizing_pipeline` RE-EXPORTS `MODES` / `MODE_BULLET` / `MODE_CONSISTENT` / `MODE_MANUAL`, and
the autofixer deleted them (2026-08-14).** `backtest_runner._handle_complete` reads them off THIS
module (`sizing_pipeline.MODES`) rather than importing `sizing_engine` itself, so they are imported
here and never used here — which is precisely what `ruff check --fix` removes. **F401's "unused" is
per-MODULE and cannot see an attribute read in another file**, so the repo-wide reformat stripped
them and nothing failed at import: the break is an `AttributeError` at line 537, inside the branch
that only runs when a non-self-sizing strategy carries `engine_trades`. ⚠ **The pre-check that
cleared the reformat looked at `__init__.py` files only** — the `__all__` reasoning that protects a
package's public API does not reach a plain module, and this laundered straight past it.
⚠ **`test_sizing_pipeline.py::test_unit_size_strategy_is_still_sized_by_the_engine` is the only
thing that caught it**, because it is the one test that drives the full run row → `_handle_complete`
→ pipeline → engine path. The import now carries `# noqa: F401` and a comment naming its consumer;
**do not "tidy" either away.** ⚠ **If you add another cross-module re-export, mark it the same way** —
the next `--fix` is indiscriminate. Rule and the wider lesson: root `CLAUDE.md` → *Formatting,
linting and the test gate*.

**Current state:** ORB.cs (NT8) and LondonBreakout.mq5 (MT5) are both reshaped to trade unit
size and emit `engine_trades.csv` (the runner→engine contract). `nt8_backtest_runner` and the
MT5 agent both read that file back after a run and attach it as `result["engine_trades"]`;
`backtest_runner._handle_complete` sizes any run that carries `engine_trades` per ruleset,
runner-agnostically (same gate for NT8 and MT5). The per-run **bullet/consistent** sizing mode
is plumbed end-to-end: `BacktestRunRequest.sizing_mode` → `backtest_runs.sizing_mode` column →
`BacktestDetail.sizing_mode`/`sized`/`sized_timeline`. Native (unit-size, non-reshaped) runs
carry no `engine_trades` and are unaffected. The whole sized path only activates once a reshaped
strategy actually emits `engine_trades.csv` from a VPS run.

Build history (the ORB/LondonBreakout reshape, the NT8/MT5 wiring order, the per-firm
`ruleset_sizing.json` rollout, and the MT5 tester-agent sandbox file-path gotcha) is in
`command-center/docs/BACKEND_BUILD_NOTES.md`.

### The lot ceiling — a per-run setting on every python strategy (2026-09-03)

Aaron: *"for all tests, for all strategies, there should be a setting showing the max lot size to
trade. All strategies will default to one hundred lots. Don't ever refuse. Just resize."*

Plumbed end to end: `BacktestRunRequest.max_lots` → the `backtest_runs.max_lots` column → the job
spec → `python_runner._max_lots` → `backtest.replay.build_strategy`, which builds the run's account
with it. The behaviour, and why a clamp at the sizing decision is coherent when a clamp at the
order is not, belongs to `backtest/CLAUDE.md` — do not restate it here.

🔴 **THREE states, one column, and the column is TEXT for exactly that reason.** NULL is *this run
never recorded a ceiling*; `'null'` is *deliberately no ceiling*; `'100.0'` is a ceiling. A REAL
column carries two of those and the third would have to be a magic number. `_stored_max_lots` in
`routers/backtests.py` is the only reader, and a malformed value reads as unknown — the same call
`_json_list` makes, for the same reason.

🔴 **EXISTING ROWS ARE NOT BACK-FILLED, AND THAT IS A DECISION.** The account's own default became
100 lots on 2026-09-02, so runs either side of that date were measured differently while looking
identical — and `created_at` is not evidence of what the code did, it is a date. Writing a number
onto a row nobody chose it for is rule 4 with extra steps. ⚠ **A retry of such a run therefore
OMITS the key rather than sending null**, because absent reproduces what that run actually did
(the account decides) while null would reproduce a run that never happened.

⚠ **PYTHON ONLY, and the key is omitted for the others rather than stored as null.** NT8 and MT5
size inside their own platforms and never reach this account, so a ceiling on one of their rows
would be a claim about code that does not exist — root rule 7, and the same reason `cost_layers`
stays NULL for them.

⚠ **It is a BASIS field for `mcp__lab__compare_runs`, and the obvious test misses it.** R is
identical either side of a ceiling — profit and risk both scale with the quantity — so a
comparison in R shows nothing while balance, drawdown and CAGR all move. MEASURED on the live SOS Fade
bot over 6.6 years: same 205 trades, same +107.36R, closing balance $11,528,822 uncapped against
$10,752,175 at 100 lots.

⚠ **A clamp is reported through `lot_capped.json`, which is written even when EMPTY.** Empty is the
measurement *"the ceiling never bit"*; a missing file is *"nothing recorded it"*. Every other
optional artefact here uses `_write_or_clear`, which deletes on empty — right for a chart layer,
wrong for this, because a resized entry is otherwise indistinguishable from a full-size one on
every number a page shows.

## Lens metrics (the per-run scoring layer)

**Drawdown = EOD trailing max-loss** (`services/trailing_drawdown.compute_trailing_mll`), not whole-test max DD. Floor trails the highest EOD balance, capped at `mll_lock_balance` when set; a breach (balance falls through the floor) is the only thing that fails `drawdown_pass`. Detail columns on `evaluations`: `mll_final_floor`, `mll_highest_eod_balance`, `mll_breach_day`, `mll_min_floor_distance`.

**Canonical Sharpe — one definition everywhere.** `metrics.apply_canonical_sharpe(kpis, daily_pnl)` writes the daily-√252 Sharpe into `sharpe`, moves the platform's value to `platform_sharpe`, and sets `sharpe_low_sample`. It's called at every run-completion path that has `daily_pnl` — single run, sweep child, stress child, optimizer winner — but NOT the native-combo path (no daily_pnl). **Idempotency guard:** only runs when `platform_sharpe` is null, so a second pass can't overwrite the platform value. Walk-forward window Sharpe (`stress_tester._compute_sharpe`) goes through the dated `daily_sharpe`.

**Flat days are zero-filled before the Sharpe (2026-07-16).** `daily_pnl` carries only days that closed a trade (the trailing-drawdown engine walks the days that exist), so Sharpe used to average the ACTIVE days and annualize by √252 — scoring a strategy that's flat 90% of the time as if every day earned the active-day mean. A real 22-trade/225-day run read **7.80 against a true ~2.2**; TradingView's own Sharpe on the same trades, annualized, independently agreed at ~2.0 (see `metrics.zero_filled_daily_values`). `daily_sharpe(daily_pnl)` now zero-fills every weekday in the span first — dates PRESENT are always kept, even on a weekend, so a Sunday-open forex fill isn't dropped. **Do NOT change `daily_pnl` itself** — the trailing-drawdown engine depends on flat days being absent; the zero-filled series exists only for Sharpe.

Two traps this creates, both guarded:
- **`sharpe_low_sample` must count ACTIVE days** (`metrics.active_day_count`), never `len()` of the zero-filled series — otherwise a 3-trade year reads as ~250 well-sampled days and the flag never fires, exactly where it's needed most.
- **`daily_sharpe_from_values` (undated) does NOT zero-fill and must stay that way** for callers whose day population is sparse *by definition* — the optimizer's regime-filtered scoring, where the days in between are other regimes, not flat days of this one.

**Backfill (`scripts/backfill_metrics.py`) recomputes `sharpe`/`sharpe_low_sample` on EVERY pass** (pure functions of the stored `daily_pnl` → idempotent), which is how a change to the canonical definition reaches history; only the one-way `sharpe`→`platform_sharpe` move stays null-guarded. **The move skips `runner = 'python'`**: `backtest/output.py` deliberately computes no Sharpe, so a python run's `sharpe` is already ours, and moving it would stamp our own value as "the platform's" and invent a reference that never existed — NULL is the honest answer.

**Contract cap** (`evaluator.compute_contract_cap_status`, informational — never moves the verdict): scaling ladder → `not_applicable`; MT5 (lots) → `not_applicable`; NT8 without per-trade size → `not_evaluable`; NT8 fixed cap + size → real largest-single-trade vs cap. Per-trade `size` is captured from NT8's Quantity column / MT5 volume.

**Profit concentration** persisted as `profit_concentration_pct` (largest quarter's share of gross profit) for later grading use, alongside `profit_concentration_basis` — `'return'` or `'dollars'` — which says how it was weighted, so a row is self-describing.

**It is weighted in RETURNS whenever the run COMPOUNDED (fixed 2026-07-31), and this was a real false alarm, not a refinement.** In dollars the metric reports the compounding rather than the clustering it exists to detect: on an account that grows 85x, the final quarter must hold nearly all the dollars however evenly the edge is spread. Measured on run `d2ab68f9e884` — dollar quarters of $9k / $49k / $71k / $1,039k read **88.94%**, which is past the 60% "edge clustered — overfit risk" threshold and was the only warning colour on that page; the same trades weighted by each one's return on the equity it was taken with read **39.97%** ("spread across the test"). The switch is whether the equity curve carries a real account base (`_equity_base > 0`): a %-of-equity strategy compounds and must be normalized, while an NT8-shaped cum-P&L-from-zero curve is a unit-size run whose dollars ARE already comparable across periods — dividing those by a fictitious balance would introduce the opposite bias. **`profit_concentration_pct` therefore needs the EQUITY CURVE, not just `daily_pnl`**; every caller passes it (`backtest_runner._handle_complete`, `scripts/backfill_metrics.py`).

Because the figure is stored, `init_db` carries a one-time `_restamp_profit_concentration` that re-reads each completed run's `equity_curve.json` and rewrites it; `profit_concentration_basis IS NULL` is the marker that makes it run exactly once. A run whose file is missing is stamped `'dollars'` — that IS what its stored number is, and leaving it NULL would re-read a missing file on every startup forever. It restamped all 78 completed runs in the live DB. The frontend recomputes client-side rather than reading the column (`frontend/CLAUDE.md` → *Profit concentration measures the edge*), so a page never depends on this migration having run.

### The Python runner's costs were collected and never charged (fixed 2026-08-01)

`commission_per_side` and `slippage_ticks` are collected in the Run modal, stored on
`backtest_runs`, shown on the run page — and `services/python_runner.py` read neither. Every
Python run was **frictionless** while reporting a cost profile it had not applied. The tell in the
data was 52 of one run's 54 losing trades each losing **exactly 10.00%** of prior equity, which no
cost model can produce; the values themselves (2.25/1) came from a FUTURES prop-firm ruleset and
were never meaningful for spot gold.

`python_runner._cost_profile(spec)` is the seam: it turns the run's stated costs into a
`backtest.fills.AccountProfile`, passed to both the single-run path and `run_sweep` (so the
optimizer cannot rank combos on a frictionless book and then hand the winner to a run that is
not). Four rules, each of which fails silently if broken:

- **0/0 returns `None`, not a zero-valued profile.** No profile means no charge path is entered at
  all, which is what keeps every result measured before this date reproducible.
- **Either number alone builds one.** An `and` there would drop slippage-only runs back to
  frictionless — the same bug, one level down.
- **Commission is per LOT per side** (a lot = `contract_size` units, 100 oz for gold). Reading the
  field as per-unit overcharges gold 100x and nothing downstream looks wrong.
- ~~**`swap=None` deliberately.**~~ **Superseded 2026-08-02 — see below.**

#### Layered costs — and the two numbers that were never typed in (2026-08-02)

Aaron's framing, and it is the right one: the spread and the swap are things we KNOW, so leaving
them unpriced is a choice nobody made. Both are now chargeable in bar mode, and the request carries
**`cost_layers`** (which costs to charge) + **`broker_profile`** (whose measured facts to charge
them from) — `python_runner.COST_LAYERS` is the roster, `backtest.fills.PROFILES` the source.

**Every layer is OFF by default, and that is Aaron's explicit call.** A bare run charges nothing,
so it stays directly comparable to the TradingView Strategy Tester, and each cost is switched on
deliberately. **Slippage keeps its own switch and its own typed number** for the opposite reason
to the rest: it is the one cost no amount of history can measure, so it must never ride along with
the measured ones.

Four rules, each of which fails silently if broken:

- **`cost_layers` absent (`None`) is NOT `[]`.** `None` = a row written before layers existed and
  must keep the old contract (charge whatever commission/slippage it stated); `[]` = charge
  nothing. Collapsing them would re-price all 80 stored runs the first time one was retried.
  `routers/backtests._json_list` preserves the distinction on the way out, and the API models it
  as `Optional[list[str]]` so the page can caption which it is.
- **`spread` and `swap` are never accepted from the request.** They are measurements, and a field
  the operator can type is a field that can disagree with the broker. Picking `puprime_standard`
  over the default `vantage_demo` moves the spread 0.22 → **0.32** because those are two different
  measurements — **using one broker's figure for the other overstates the cost by 45%.** (This
  paragraph said 0.33 until 2026-08-06; the figure was re-measured over 1,893,438 ticks and the
  code has been 0.32 since. The prose was the stale half.)
- 🔴 **A BROKER PROFILE CAN NOW REFUSE, AND A 500 HERE IS THE FEATURE WORKING (2026-08-06).**
  `backtest/fills.py` used to give all four PU Prime tiers the SAME spread and swap — both measured
  on a **Standard** demo, which is the one tier priced by a marked-up spread. So `puprime_ecn`
  charged ECN's commission on top of Standard's spread and swap: a cost model no real account
  offers, and **nothing errored**. An unmeasured tier carries `SPREAD_UNMEASURED` /
  `UNMEASURED_SWAP` and raises `CostsNotConfigured` naming `algos/tools/broker_facts.py`. **So a run
  requesting `spread`, `bid_ask_fills` or `swap` on a tier nobody has read
  now FAILS instead of returning a plausible wrong number.** ✅ **`puprime_ecn`'s SPREAD left that
  set on 2026-08-14** (measured $0.12 over 5 days of its own ticks), so a lab run asking for the
  spread layer on ECN now succeeds where it used to 500 — **that is not a regression in the guard**.
  ⚠ **What still refuses is narrower than this paragraph used to imply**: the SPREAD on
  `puprime_prime` and `puprime_cent`, and the SWAP on `puprime_cent` alone — Prime's and ECN's swap
  was measured on each tier on 2026-08-08. **Check `PROFILES` before telling a user a tier refuses.** ⚠ **`commission` on those tiers still
  works** — it is the one of the three a broker states unambiguously per lot, so the refusal is on
  the unmeasured COST, not on the tier. ⚠ **The swap half was measured, not assumed:** on ONE PU
  Prime account `XAUUSD.s` and `XAUUSD.crp` are the same market (median M15 close difference $0.08
  over 200 shared bars) with swaps **8.5x apart** and the short CREDIT gone entirely. Full record:
  `backtest/CLAUDE.md` and `docs/BROKER_QUESTIONS.md`. **If a lab run starts 500-ing on a raw tier,
  do not "fix" it by defaulting the spread — measure that account, or run without the layer.**
- **`bid_ask_fills` REPLACES the spread cost, never adds to it** (see the strategy's
  `_charge_spread`), and it is the only layer that can change which trades exist.
- **`GET /backtests/broker-profiles` exists so the Run modal never retypes a spread.** It serves
  `PROFILES` itself — the object the runner bills from. A number copied into a form is a second
  claim about what is charged, which is this lab's most-repeated defect.

Both `_cost_profile` call sites (single run and the optimizer sweep) inherit it, so the optimizer
cannot rank combos on one cost model and hand the winner to a run on another. ⚠ **Sweeps and stacks
do NOT write the columns yet**, so they land in the legacy branch and stay frictionless — correct
today (that is also the default), but wire them before anyone expects a priced stack.

Strategies are constructed through **`backtest.replay.build_strategy`**, never by calling the
class: `LAB_STRATEGY` is an open contract, so a strategy may predate the `cost_profile` kwarg, and
that helper **raises** rather than dropping a stated cost on the floor. Defaults on every request
model are now **0/0** (`models.py`), and `RunBacktestModal` resolves its primary ruleset across
BOTH the futures and forex lists — searching futures only is why a forex run's 0/0 ruleset default
never reached the form.

### Three numbers that were true and got misread

Auditing run `f866873aa862` found **no arithmetic wrong anywhere** — every stored KPI reproduced
from the raw trades, Sharpe included. What was wrong was what three headline numbers let a reader
conclude, and none was fixable by relabelling; each needed a companion that had never been
computed. All three live in `services/metrics.py`, are stored on `backtest_runs`, and are
backfilled onto history by `lab_db._backfill_run_shape_metrics`.

| stored | what it fixes |
|---|---|
| `max_drawdown_pct` | the drawdown was stored and LISTED in dollars only. $1.73M beside $14.4M of profit reads as ~12%; against the running peak it is **55.9%**. `BacktestDetail` always computed the percentage client-side — the RUNS LIST, which is where runs get compared, did not, and a list is exactly where a wrong order of magnitude does its damage. |
| `scratch_count` | the win rate counts a trade that made a cent as a win. 45 of that run's 111 "winners" made under a sixth of a typical loss, every one exiting at the breakeven-stop buffer — the stop doing its job, which is risk control and not an edge. Honest split: 40% won / 27% scratched / 33% lost. |
| `trade_concentration_pct` | `profit_concentration_pct` is the largest QUARTER's share — a question about time. Readers hear the question about TRADES, and the two can disagree completely: that run is 34.5% by quarter (spread evenly over 6.6 years) while **5 of 165 trades made 47%** of everything won. |

Three rules they share, and each is load-bearing:

- **All three weight by RETURN when the run compounded** (`_trade_weights`, the same
  `_equity_base` switch `profit_concentration_pct` uses). Dollars on a compounding account measure
  the compounding.
- **The scratch yardstick is the run's own MEDIAN full loss**, not a typed-in figure. For a
  fixed-risk strategy that median IS 1R, so the bar self-scales across strategies, instruments and
  account sizes with nothing to tune; the median rather than the mean so one outsized loss cannot
  move it. (It landed on the same 0.15 that `sos_fade_strategy.pine`'s own `exec_scratch_r` uses — not
  a coincidence, since 0.15 of the median loss and 0.15R are the same bar at fixed risk.)
- **`None` is never rounded to 0.** No losing trade means no scale to measure a scratch against,
  and `0` would read as "no scratches" — the opposite of "cannot tell". The backfill stamps
  `max_drawdown_pct = -1.0` for a run whose curve is missing, for the same reason
  `_restamp_profit_concentration` stamps `'dollars'`: a row left NULL is re-read on every startup
  forever.

## 🔴 A trade's `exitPrice` is an AVERAGE, so the chart is given its FILLS (2026-08-25)

`chart_spec._build_trades` emits **every** leg on `profitLegs` with a `banked` flag, where it used
to DROP any leg that did not clear a tenth of the entry risk. Two defects, one cause:

- **A trade that banked nothing had no exit anywhere on its chart.** The long of 2020-10-13 came
  off in one piece at 1902.01 on its staged breakeven stop — 0.30 favourable against a 21.99 stop,
  so it missed the 2.20 band and was discarded. Aaron: *"exit should always be shown."*
- **`exitPrice` cannot stand in for it.** It is the SIZE-WEIGHTED AVERAGE of the fills. On a
  one-fill exit it is the fill that was just discarded; on a two-fill exit it is a price nothing
  ever traded at. Drawn as an `Exit` line it put a third chip between two real ones 32 cents apart
  (run `6b18811e25d5`, 2020-11-04: fills 1895.40058 and 1895.72498, average 1895.56278) and shoved
  both real chips off their levels.

⚠ **`banked` is a FLAG, never a filter, and its absence means TRUE.** Runs stored before it carry
only the profitable rungs, so reading a missing flag as `false` would repaint every historical
profit-take as a plain exit — a claim about size that nobody measured.
⚠ **The consumer must take the green band's top off the BANKED fills only.** With every fill on
the wire, the extreme of all of them lets a breakeven-stop exit set the top and read as a
profit-take. See `frontend/src/components/ChartPanel/CLAUDE.md`.

**The same bar now grades EACH trade, for the chart — `metrics.trade_outcomes` (2026-08-18).** It
returns `won` / `scratch` / `lost` per curve point and `chart_spec` stamps it on the trade as
`outcome`, so the price chart's per-trade chip and the KPI row's `scratch_count` cannot tell two
stories about the same trade. 🔴 **It exists because they did.** The chart graded on `pnl > 0`
alone, which files a trade that netted **exactly $0.00** under LOSS — and on run `295a6ff29d21`
eight trades did exactly that, one of them a short whose exit sat plainly BELOW its entry. That
chip sent a reader looking for a bug in the exit code; the exit was right (the profit went to a
scale-in add — see `strategies/python/sos_fade/CLAUDE.md` → *Scale-in*).

⚠ **It is aligned 1:1 with the curve, which `_trade_weights` is NOT** — that one drops any point it
cannot weight, so its indices stop matching the trades the moment one is dropped. ⚠ **A run with no
losing trade carries NO verdict rather than an all-`won` list**, same rule as `scratch_count`
returning `None`: the chart then falls back to the sign of the P&L, and its fallback never says
`scratch`, because an ungraded trade is not a measured flat one.

**A high `trade_concentration_pct` is not a verdict.** A runner-based strategy is supposed to be
fat-tailed and this repo's stated design intent is few high-quality setups, so read it as "the
edge lives in the tail, size the risk for that" rather than as a defect. The frontend recomputes
both trade-shape metrics client-side (same rule as profit concentration — the stored value is
whatever basis was current when a run finished, and the news filter needs them over a subset).

**Backfill:** `scripts/backfill_metrics.py` recomputes the file-derivable columns (Sharpe trio, profit concentration + basis, contract status) on old runs — idempotent, only touches what's derivable from stored result files.

**Capital-based scores stay client-side** (BacktestDetail). Calmar / Max-DD-% need an account balance (the ruleset's `account_size` or the what-if slider); they're computed in the browser by rebasing the equity, never persisted, and never feed the verdict. **Both are measured against the RUNNING PEAK, not the starting balance (2026-07-30)** — the same defect `dd_basis` fixed for Monte Carlo, found in a second file: dividing a late dollar drawdown by a static `account_size` reported **1096.7%** and a red **Calmar 0.11** on a run whose honest figures are 54.9% and 2.25. If you add another percent-of-capital metric anywhere, the denominator has to grow with the account. Detail: `frontend/CLAUDE.md` → *Drawdown is peak-relative*.

---

## Foundational config (Pass 1)

Rulesets carry 10 foundational fields (risk %, halt fraction, consecutive loss limit, entry hours ET, days allowed, daily profit target, profit lock-in %, commission/side, slippage ticks), injected into strategy params at run creation by `runner_dispatch.inject_foundational()`. Detail is in git history (Pass 1).

**Standing rules:**
- **Category tagging:** every `[NinjaScriptProperty]` carries `[Category("Strategy Logic")]` (tunable, optimizer-visible) or `[Category("Foundational")]` (injected, hidden in UI). Legacy `[Display(GroupName = "Prop Firm")]` falls back to `"foundational"` via GroupName heuristic.
- **Dispatcher injection** happens at three creation points — `trigger_backtest()`, `trigger_sweep()`, `run_optimization()` — using the primary ruleset (first in `evaluate_rulesets`). Merged params stored in DB at creation so all retry paths pick them up without re-injection. **NinjaScript-only:** never inject for the `mt5` runner — foundational params map to `[Category("Foundational")]` properties MQL5 strategies don't have. Forex runs now carry a (personal) ruleset for *evaluation*, but `trigger_backtest()` forces `primary_ruleset=None` when `runner == "mt5"`, so no config is injected. **`run_native_optimization()` enforces the same gate** (`if firm and runner_str != "mt5"`): it previously injected NT8 foundational params (`AccountSize`, `EarliestEntryTimeET`, `DaysOfWeekAllowed`, …) into the MT5 optimizer's `.set` file regardless of runner, and MT5 treats a set file carrying inputs the EA doesn't declare as mismatched — silently running a single backtest instead of the optimization, so `opt_results.csv` is never written. See the set-file purity rule under "Runner dispatcher" below.
- **Primary ruleset rule:** only the first ruleset injects foundational config; others evaluate only. To test two rulesets' configs, run two separate backtests.
- **Sentinel guard:** strategies refuse to trade (warn + return) if foundational params are still at placeholders (-1 or empty string), catching dispatcher failures early.

---

## What's built (status)

| Domain | Status | What it does |
|---|---|---|
| Smart Money | ✅ Live | Scan, terminal, rankings, profile, disqualified log, config, cache tabs. |
| Bots | ✅ Live | SSH monitor + control. A bot IS its folder under `algos/markets/fx/instances/`. ⚠ **Count them there or on the Bots page, never from this line** — it read "none registered" until 2026-08-04 and "three, one trading" until 2026-09-13, each time while wrong. **Registered and TRADING are different questions**: registration is what makes a bot addressable so it can be given an account at all. [Detail](../docs/BACKEND_BUILD_NOTES.md#bots) |
| Strategies | ✅ Live | Registry scanned from `strategies/`. Param schema from `[NinjaScriptProperty]`. `runner` field per strategy. [Detail](../docs/BACKEND_BUILD_NOTES.md#strategies) |
| Rulesets | ✅ Live | CRUD at `/rulesets`. 4 types: `prop_eval`, `prop_funded`, `personal`, `demo`. 18 seeded rows (14 prop + 2 personal demo + `unconstrained` + `personal_forex_risk`). [Detail](../docs/BACKEND_BUILD_NOTES.md#rulesets) |
| Backtests | ✅ Live | NT8/MT5 runs via agent. Equity curve, daily P&L, per-ruleset verdicts, Worthiness tier (1/2/3). |
| Sweeps | ✅ Live | N sequential backtests across instruments (`_MAX_CONCURRENT = 1`). Cancel, retry-all, per-run retry. |
| Optimizations | ✅ Live | Native NT8/MT5 optimizer (one VPS job, full grid, all CPU cores). Scores by objective. `best_run_id` tracked. Source run nesting. Per-run retry. |
| System | ✅ Live | Health (SSH, NT8, MT5 agents). Log proxies. `POST /system/{nt8,mt5}-agent/start` fires schtasks. |
| Stress Tests | ✅ Live | MC (10k reshuffles + 1k bootstrap), walk-forward (IS/OOS windows), sensitivity (±10%/±25%). [Detail](../docs/BACKEND_BUILD_NOTES.md#stress-tests) |
| Regime Tags | ✅ Live | `backtest_runner.build_regime_timeline_and_tag()` classifies **every trading day in the run's window** once (via the existing `build_date_regime_map`), writes it to `reports/lab/<run_id>/regime_timeline.json` → `BacktestDetail.regime_timeline` `[{date, regime}]`, and tags `daily_pnl` from that same … [Detail](../docs/BACKEND_BUILD_NOTES.md#regime-tags) |
| Strategy Files | ✅ Live | Upload/delete/compile `.cs` (NT8 F5) and `.mq5` (MetaEditor) files. Sync-status badges. |
| Strategy Deploy | ✅ Live | `POST /strategies/{id}/deploy` reads `source_path`, uploads to VPS. `.mq5` → MT5 agent, `.cs` → NT8 agent. |
| Param types | ✅ Live | `GET /strategies/{id}/param-types` parses `.cs`/`.mq5` source → `{paramName: "int"\|"double"}`. Used by optimizer modal to block decimal steps on integer params. |
| MT5 runner | ✅ Live | `mt5_agent.py` port 8766: Strategy Tester driver (ini+set, terminal64, HTML report). `mt5_agent_client.py` typed wrapper. [Detail](../docs/BACKEND_BUILD_NOTES.md#mt5-runner) |
| MT5 deployment | ✅ Live | MT5 agent upload/delete `.mq5`. `POST /compile` → MetaEditor. Backend: `POST/GET /strategy-files/compile-mt5`. |
| MT5 native optimizer | ✅ Live | `mt5_agent.py` `POST /native-optimize` + `POST /native-walkforward`; `mt5_agent_client.py` typed wrappers. [Detail](../docs/BACKEND_BUILD_NOTES.md#mt5-native-optimizer) |
| Python runner + optimizer | ✅ Live | `services/python_runner.py` — runs `strategies/python/` packages LOCALLY, in-process, via the top-level `backtest/` package (data cache → engine replay → `output.build_results`). [Detail](../docs/BACKEND_BUILD_NOTES.md#python-runner--optimizer) |
| Portfolio stacks | ✅ Live | `routers/stacks.py` + `services/lab_db.py` — layer 2+ **Python** strategies over ONE shared instrument/window/cost profile, **each leg on its OWN timeframe since 2026-09-03**, to see combined P&L (summed client-side from each leg's `daily_pnl`; toggling a leg off never re-runs). [Detail](../docs/BACKEND_BUILD_NOTES.md#portfolio-stacks) |
| Telegram notifications | ✅ Live | `services/notify.py` — urllib Telegram sender, no extra deps. **No token in the source (2026-07-30):** env var, else the git-ignored `algos/credentials.json` read by path. [Detail](../docs/BACKEND_BUILD_NOTES.md#telegram-notifications) |
| Live calendar tab | ✅ Live | `routers/calendar.py` (`GET /calendar?from&to`) → `services/calendar_service.py` → `engines/news/` `TradingViewSource.fetch_window()` (never a 2nd impl). [Detail](../docs/BACKEND_BUILD_NOTES.md#live-calendar-tab) |
| History floors | ✅ Live | `services/history_limits.py` + `GET /backtests/history-limit`. Refuses (400) any backtest window starting before the broker's REAL history for that timeframe — MT5 silently substitutes coarser bars, which would produce a plausible but fictional run. [Detail](../docs/BACKEND_BUILD_NOTES.md#history-floors) |
| Settings | ✅ Live | Config read/write. `nt8_agent_tunnel` and `mt5_agent_tunnel` both present. |
| Startup — agent supervisor | ✅ Live | `services/agent_supervisor.py` — 60s loop, guarded on the per-platform job lock. Replaces the one-shot startup thread. See *The agent supervisor* below. |
| Startup — readiness report | ✅ Live | `services/readiness.py` — one boot-time line per silently-degrading dependency; `GET /system/readiness`. |

---

## The Backtests list and the Backtest detail page — the 2026-08-06 audit

Aaron asked for an in-depth audit of both pages and then for the fixes. **27 findings; nine were
real defects and three of those were destructive.** The shape they share is the one this repo keeps
meeting from new directions: **not one of them produced an error.** Each reported success while
doing something other than what it said. The UI half is in `../frontend/CLAUDE.md`.

### Stop cancelled whatever job the shared progress file named

🔴 **`stop_backtest_run` read the job id out of `lab_progress.json`** — ONE file shared by every
runner — and `job_id == run_id` for every backtest this app starts, so the lookup could only ever
be wrong. **Measured on the live file when this was found: it held `"j2"`,** a stale entry, so a
Stop would have sent `cancel_job("j2")`, had the failure swallowed by `except Exception: pass`,
marked THIS run `failed_cancelled`, released its platform lock — **and left the real job running.**
With two platforms busy it cancels the *other* platform's job. `clear_progress()` on the next line
blanked another platform's live progress the same way; it is now conditional on the entry being
ours.

⚠ **`job_stopped` is reported separately**, exactly as the optimizer's cancel does: the row is
cancelled either way, but *the runner acknowledged* and *we could not reach it* are different
facts and only the first means the machine is free.

### Cancelling did not stop the poller, so a cancelled run came back as `complete`

🔴 `run_backtest_job` never re-read the row, so when the agent eventually finished,
`_handle_complete` wrote KPIs and `complete` straight over `failed_cancelled`. The same "cancel did
not cancel" defect the Optimizations audit fixed on 2026-08-04, still live here.

`run_was_cancelled(run_id)` reads the DB — **the single lock source, therefore the single place a
cancellation is recorded** — and the poller stands down. Three rules hold it:

- **The router marks the row BEFORE it reaches for the runner.** The other order leaves a window in
  which the job finishes and overwrites the cancellation.
- **`_handle_complete` re-checks AFTER fetching results**, not only before. That await is where a
  Stop lands most often, and everything below it writes.
- ⚠ **An unreadable row answers False.** The poller carrying on is recoverable; abandoning a live
  run because sqlite was momentarily busy is not.

### A rerun left every artefact except two, so the page showed the PREVIOUS attempt

🔴 `retry_backtest_run` deleted `equity_curve.json` and `daily_pnl.json`. A run directory also holds
`chart_spec.json`, `blocked_setups.json`, `missed_setups.json`, `regime_timeline.json`,
`engine_timeline.json` and `ruleset_sizing.json` — **all of it derived, none of it cleared.** The
consequences are not stale numbers, they are the old run's data rendered as this one's: the spec is
CACHED, so the Price tab drew the previous candles and trades until somebody clicked Reload charts;
the blocked/missed files are written only when non-empty, so the old refusals stayed on the chart;
a rerun over a NEW window kept the old regime calendar; and a stale `engine_timeline.json` kept
`sized` true on a run that no longer was.

`_clear_run_dir` rmtrees it, on the standalone **and** the sweep and optimization retry paths —
neither of which cleared anything at all. `_handle_complete` also writes-or-UNLINKS the optional
artefacts, because an optional file's ABSENCE is what removes its chart layer, so `if blocked:`
alone left the previous attempt's refusals on disk.

### A ten-minute wall clock killed healthy jobs and blamed the agent

🔴 `heartbeat_age > _STALL_KILL_SEC or (now - started_at) > _STALL_KILL_SEC`. The second clause
cancels a perfectly healthy, heartbeating job and writes **"No heartbeat for 0s — job cancelled"**,
which points at the agent for something the lab did. Latent rather than live — the longest
completed run in this lab is 275s — but a tick-mode run, a wider window or a slower box crosses it.

`_MAX_RUNTIME_SEC` (6h) is now separate from `_STALL_KILL_SEC` (10 min of NO heartbeat), and the two
write different messages, because **a stall and an overrun are different diagnoses.**

### The runs list was N+1, and the run page pulled the whole lab for a badge

`_row_to_summary` called `get_run_verdict_summary` per row, and every call opens a fresh sqlite
connection with two PRAGMAs — on a list polled every 3s while anything runs, and read by the Runs
tab, the sweep detail and the optimization detail. ✅ **MEASURED against the live lab:
12 connections / 23.72 ms → 1 connection / 2.28 ms, with byte-identical output** (12x fewer
connections, 10.4x faster; it would be 81x on the lab as it stood a week ago).
`get_run_verdict_summaries` is the bulk form and all three list callers use it.

`GET /backtests/runs` also takes **`source_run_id`** now, so the run page can count its own tuning
iterations without fetching every run. ✅ **MEASURED: 20.6 KB → 0.002 KB and 10.5 ms → 5.3 ms.**
⚠ **It does NOT narrow to tuning iterations** — a sweep and an optimization stamp `source_run_id`
too, and telling them apart is the caller's job (they carry `sweep_id` / `optimization_id`).
Narrowing it here would make one field mean two different things depending on which query you asked.

### `_JOBS` in the python runner was never evicted

Every python backtest and every optimizer grid held its whole `results` / `combos` structure in the
backend process until somebody restarted it, for data no caller can still ask for
(`_handle_complete` fetches results exactly once). ✅ **MEASURED: a 115-trade run's output is
4.14 MB, so the 12 payloads now retained are ~50 MB — and the old code retained every job for the
life of the process.**

⚠ **The eviction drops the PAYLOAD and keeps the status metadata**, rather than deleting the entry:
`job_status` answers `failed_error` for an unknown id, so a straight delete would turn *this
finished an hour ago* into *this failed* for any late poller. A shed job's `job_results` raises and
says so, which is correct — the data is genuinely gone.

### `cost_layers` could not be sent as `null`

`BacktestRunRequest.cost_layers` was `list[str] = []`, so the Run modal sent `[]` for NT8 and MT5 —
and `[]` means *deliberately charged nothing*, which the detail page renders as **"This run was
deliberately frictionless"** over a tester that really did charge the commission and slippage on the
same row. It is `Optional[list[str]] = []` now.

⚠ **The KEY BEING ABSENT and the key being explicitly `None` are different requests**, and
`insert_run` keeps them apart: absent (sweeps, stacks, every caller with no opinion) → `[]`, so a
new python run can never fall into the legacy commission/slippage branch by omission; explicitly
`None` → NULL, which is the honest description of a runner that has no layer switches at all.

### `_DEFAULT_CAPITAL`

`python_runner` read `spec.get("deposit") or 10_000` and **nothing in this app has ever set
`deposit`** — a constant wearing the shape of a setting. It is named now, because the run page has
to agree with it: a self-sizing strategy compounds off this balance, so it is the only honest
denominator for a percentage drawdown, and the page reads it back off the run's own equity curve
rather than off an evaluated ruleset's `account_size` (a different account entirely).

### Two audit findings were WRONG, and are recorded as wrong

Both were flagged as efficiency problems and both were over-flagged; measuring is what settled it.
**`compute_regime_breakdown` on every detail GET** is a linear pass over ~1,500 daily rows and ~165
trades, and **`/repriced` walking the curve four times** is 4 × 165 iterations — the WHOLE endpoints
measure **20.1 ms and 19.3 ms** end to end. Neither is worth a cache, and adding one would be
complexity bought with nothing. *A cost guessed at is the same error as a number guessed at.*

### The `python` lock scope was computed, declared, read — and never served

🔴 **Found by DRIVING the fixes rather than by reading them (2026-08-06).** A real python backtest
was started to press Stop against, and `GET /backtests/running-job` reported
`python.running = false` **while the run's own row said `running`.**

`get_running_job` in the ROUTER built its response by naming fields — `nt8=…, mt5=…` — and never
passed `python`. Every other layer of that scope was built and correct: `lab_db.get_running_job`
computes it, `RunningJobStatus` **declares** it, `lib/runner.ts` resolves it and `runningJobFor`
reads it. Because the model declares a default of `running=False`, **the omission was silent and
the answer was the most reassuring one available.**

⚠ **The GATE was never affected, and that distinction is the whole severity assessment.**
`ensure_platform_idle` reads `has_running_job`, which was right — ✅ **proven live: a second python
run submitted during the first was refused `409 An Python job is already running`.** So nothing
could ever double-run. What broke is every control the UI gates on this response — the Runs list's
Rerun, the detail page's Retry and Rerun, the Run modal, the Optimize button — all of which stayed
enabled through a python run and could only ever produce a 409 toast. **A button whose single
outcome is an error is the same defect this audit fixed twice elsewhere.**

⚠ **The response is DERIVED from `_SCOPE_RUNNER_SQL` now, never restated field by field.** Naming
the keys is what let one go missing. This is the `entry_ms` / `exit_ms` / `favorable` / `is_trades`
trap arriving from the OPPOSITE direction, and it is worth separating: those were fields the MODEL
failed to declare, so the value never left the backend. Here the model declared it and the
CONSTRUCTOR failed to fill it — and a declared field with a default cannot be caught by the same
reasoning, because nothing is missing from the response. **Ask not only whether the model declares
a field, but whether anything actually assigns it.**

✅ **Verified live after the fix**: `python.running=true`, `job_id` matching the run, description
`SOS Fade on XAUUSD`, and `false` again the moment it finished.

### Driven against a real running job, not only against mocks

The Stop path is the largest fix here and every test of it drove the router and the poller with the
runner MOCKED, so it was driven for real before being believed:

- **A full-history python backtest was started and stopped mid-replay.** `job_stopped: true`, the
  row `failed_cancelled` in **287 ms**, the platform lock released immediately, and the row still
  `failed_cancelled` **120 seconds later** — well past the point the old code wrote `complete` over
  it. The python job's own log reads `[failed_cancelled] cancelled`, i.e. it reached a terminal
  state, so the wait was not vacuous.
  ⚠ **What that drive does NOT prove is the resurrection guard itself**: the cooperative cancel
  makes the python job report `failed_cancelled`, so the poller takes the failure branch rather
  than the completion one. The `complete`-over-`cancelled` case is covered by
  `test_a_cancelled_run_does_not_come_back_as_complete`, which calls `_handle_complete` with real
  results on a cancelled row. Say which half is measured and which is unit-tested.
- **A rerun was fired at a run whose `chart_spec.json` had been built.** Six artefacts before
  (including the cached spec), **zero immediately after the retry**, five rebuilt on completion.
  That is the defect's visible consequence — the Price tab can no longer serve the previous
  attempt's candles — rather than just the directory call.

🔴 **The dev server wedged once during this drive, was recorded as UNEXPLAINED, and is now
DIAGNOSED AND FIXED (2026-08-06) — and the hypothesis that stood in for it was wrong.** The
uvicorn worker went unresponsive at 0% CPU with the reloader still holding port 8000. The stated
guess was a reload killing a replay thread mid-flight. **It is not that, and it has nothing to do
with backtests: `touch main.py` on an idle server reproduces it exactly**, /health going from
`200` in 19 ms to a hard timeout, the same worker PID alive at 0% CPU twenty seconds later.

**The mechanism, measured end to end.** On a reload the reloader asks the worker to stop and then
JOINS it; the worker's own shutdown waits for open connections to close. **The Vite dev server
holds a keep-alive POOL to port 8000 — `lsof` counted 19 established sockets from one `node` PID —
and an idle keep-alive socket is never going to close on its own.** So the worker waits for ever,
the reloader waits for the worker, and the listening socket stays bound with nobody accepting on
it, which is why every request HANGS rather than being refused. `/usr/bin/sample` (no root needed,
unlike py-spy) put the main thread in `uv__io_poll` inside `run_until_complete` — a live event loop
awaiting a shutdown that cannot finish. Confirmed from the other end too: `kill` on the reloader
did nothing until the worker was `kill -9`'d, at which point the reloader immediately spawned a
replacement.

**The fix is one flag in `start.sh`: `--timeout-graceful-shutdown 10`.** ✅ Proven by reproducing
the same sequence with the pool rebuilt to 14 sockets — `200` in 1.9 ms after the reload, and again
on a second file — with `Application shutdown complete` / `Started server process` in the log both
times. 10s is deliberate: it clears the slowest measured request on this app (a cold ChartSpec
build, 7.6s) so an in-flight request still finishes, and only ever bounds the wait on sockets doing
nothing. `tests/test_dev_server_flags.py` guards it, **2 of its 4 checks watched RED against the
old `start.sh`**, and every grep in it asserts it matched something first.

⚠ **The standing lesson is about what an undiagnosed failure costs, and it is uncomfortable: the
hypothesis was plausible, related, written in the right file — and it sent the next reader at
`--reload` and replay threads, which is the half of the system that was innocent.** The thing that
actually cracked it was refusing to reason and running `touch main.py` on an idle box. **A recorded
guess is not a cheap placeholder for a diagnosis; it is a signpost, and a wrong one costs more than
no sign at all.** ⚠ **And the failure itself is this repo's silent-failure shape in a new place:
nothing logged, nothing crashed, the port still answered `LISTEN`, and every symptom pointed at the
app rather than at its supervisor.**

### Tests

**25 new (723 green), in `tests/test_backtest_lifecycle.py`, `tests/test_run_list_queries.py` and
`tests/test_dev_server_flags.py` (the last 4 added with the reload-wedge fix above, 2 of them
watched red against the old `start.sh`).**
**17 of the 21 were WATCHED RED against the code at HEAD.** The four that passed there are kept
and **labelled as such in their own docstrings**: one pins that our own stale progress entry is
still cleared (the old code did it unconditionally, satisfying this by accident while failing the
test beside it), one pins that adding the `source_run_id` filter did not narrow the UNfiltered list,
one pins that an omitted `cost_layers` still means `[]`, and one is a FORWARD guard that every
scope in `_SCOPE_RUNNER_SQL` reaches the API (it could not be red, because the model declares all
three keys — which is precisely what made the `python` omission silent). Each is the half of a rule
that was already right, and a rule stated in one direction is the one that gets "simplified" back.

## History floors — blocking a window the broker has no bars for

**MT5 does not error when a symbol lacks history at the requested timeframe — it returns the nearest
COARSER bars, still labelled as what you asked for.** A backtest fed daily bars as 15m does not crash:
it produces a full trade list, a clean equity curve, and a completely fictional answer. So the lab
refuses the window instead of running it.

The floor is **measured, never hardcoded**: `backtest/data/history.py` binary-searches the live
terminal by bar density and caches per `(server, symbol, timeframe)` — swap MT5_Lab to a broker with
deeper history and the limit widens by itself. `services/history_limits.py` is a thin shim over it and
declares no dates of its own; duplicating them here would guarantee the UI and the data layer
eventually disagree, and the disagreement would surface as a run that passes validation then dies
mid-flight.

- **`GET /backtests/history-limit?instrument=&bar_type=&bar_value=&runner=[&refresh=]`** → `HistoryLimit`
  (`earliest_date`, `broker`, `verified`, `source: probed|seed`, `note`) or **`null`** when unbounded.
  The frontend date picker reads this instead of hardcoding a date. `refresh=true` re-probes (~15s).
- **400 at every trigger that accepts dates**, checked BEFORE the platform lock is taken or a run row
  is inserted: `POST /backtests/run`, `POST /runs/{id}/retry` (period override), `POST /backtests/sweep`
  (per instrument), `POST /optimizations/run`, `POST /backtests/stacks`. `BarSource.load` raises too, so
  a path that forgets the check still cannot replay substituted bars — but it raises at FETCH time, by
  which point a row exists, a lock is held, and the user is watching a progress bar. That is the whole
  reason the router-level check exists as well.
- **Python runner ONLY.** NT8 (NinjaTrader) and MT5 pull history from their own terminals, so their
  depth is a different question with a different answer. `limits_for()`/`validate_window()` return
  None / no-op for them. Claiming a Vantage gold floor on an NT8 futures run would be a lie in the
  more dangerous direction.
- **`null` means UNKNOWN, never "unlimited"** — agent down, or a broker we cannot identify. Nothing is
  refused on a guess; the data layer's bar-spacing backstop still catches substituted bars.

Full mechanism, the evidence table, and the probe's two-phase design: `backtest/CLAUDE.md` →
*History floors*.

### 🔴 THE FLOOR IS PER-RUN, NOT PER-CHART-TIMEFRAME (2026-08-15)

**A run loads more than its chart.** `exec_secondary` replays a SECOND feed alongside the 15m
primary, and each feed has its own measured floor — so the window is bounded by the LATEST of
them. ⚠ **That feed is 5m, not 1m, since 2026-08-21** — the incident below happened while it was
still 1m, and the numbers in it are that feed's. `EXTRA_FEEDS` owns the current value; do not read
"1m" here as a live fact. Until this date everything here asked only about the chart timeframe, and
a run with the secondary on sailed through a pre-flight that had never heard of the 1m floor:
measured on run
`50331c7cbe96`, Vantage XAUUSD reaches **2018-09-13 at M15 and only 2018-09-14 at M1**, so the
picker offered a date this module blessed and the runner refused at 8%. **The pre-flight promise
three bullets up was not being kept.** Story and the verification: `../docs/BACKEND_BUILD_NOTES.md`
→ *The floor was per-CHART-TIMEFRAME*.

- 🔴 **`services/run_feeds.py` is the ONE answer to which feeds a run loads, and BOTH the runner
  and the floor check ask it.** The real defect was that two places decided that independently
  and only one was ever updated; `exec_secondary` is just the flag that exposed it. **Adding a
  feed is one row in `EXTRA_FEEDS`** — the runner loads it, the pre-flight bounds it, the picker
  moves. Do not re-answer the question anywhere else.
- ⚠ **PASS `params` AT EVERY CALL SITE.** Omitting it silently asks the chart-only question and
  the answer looks perfectly correct — it is just too EARLY. The retry path passes the STORED
  row's params, which is what makes Retry able to fix a run that failed on the floor; before
  this it re-offered the same illegal date and failed identically, so the only way out was
  deleting the run.
- ⚠ **A STACK is checked per LEG.** Legs share a window, not their params, and the window is
  legal only if EVERY leg can be served. A shared stack pins `exec_secondary` off before it
  runs, so `_leg_param_sets` applies the same pin rather than refusing for a feed that path
  never loads.
- 🔴 **The runner must ask `run_feeds.uses_secondary(params)`, NEVER `1 in
  required_timeframes(...)`.** The chart is always in the feed set, so a run whose CHART is 1m
  makes the membership test true and would fire the dual replay with the secondary switched
  OFF. Pinned by an AST test that also refuses a `getattr(config, "exec_secondary")` here.

## Comparing two runs — the BASIS before the result

`scripts/run_diff.py <run_a> <run_b>` (read-only, stdlib, `--list` to find ids). Exit 0 when the
two share a measurement basis, 1 when they do not.

**It exists because this app has shipped the same defect three times** — the Tuning workbench, the
stress-test children and the stack rerun each launched a child carrying the parent's PARAMS and
not its `cost_layers` / `broker_profile` / `sizing_mode`, then put the two side by side. The rule
that came out of it is already stated three times in this file; the script is the way to CHECK it
on two rows rather than remember it. So the basis is printed FIRST and a difference there is a
refusal, not a footnote under a table of deltas.

✅ **It found a live instance on the first real pair.** Runs `2240fc689636` and `7d9fb2466867`:
**160 trades and +141.1774R on both sides**, identical win rate — and **net P&L $49,204,855 against
$136,657,910**, with max drawdown 45.57% vs 64.51%. Nothing about the strategy differs;
`cost_layers` and `broker_profile` do. The control is the pair beside it: `e51d95f212e3` vs
`c3e4c968a4e4` share all 13 basis fields, differ on one param (`exec_req_fvg`), and the result
delta is therefore attributable — 166 → 322 trades for +6R while PF falls 3.866 → 1.268 and
drawdown goes 45% → 77%.

⚠ **`BASIS_FIELDS` must stay in step with `stress_tester.child_measurement_fields()` and
`python_runner._cost_profile`.** Those decide what a child INHERITS; this decides what a reader is
WARNED about. A field that moves the numbers and is missing from this list makes the script report
"comparable" over two runs that are not — the same failure it exists to catch, wearing a green
verdict.

⚠ **NULL `cost_layers` is rendered as a THIRD state, never as `[]`.** NULL is a pre-layer row that
charges whatever commission and slippage the row states; `[]` charges nothing. **11 of the 19
completed runs in this lab are NULL**, so this is the common case, not an edge one.

⚠ **A missing total R prints "not recorded", never `0.0`,** and a PARTIAL one refuses rather than
summing the subset that happens to carry the field. Per-trade `r` has only been written since
2026-08-03 — measured here, 10 of 16 runs carry it on every trade and 6 on none.

⚠ **Net P&L is never the lead figure and is labelled when the basis moved.** R is the one number a
change of position size cannot move; the shared-stack audit measured 99 identical trades at
+17.8674R reading $21,064 solo and $47,758,999 stacked.

✅ **NON-VACUITY IS NOW COMPLETE, AND IT NEEDED A SYNTHETIC ROW BECAUSE HISTORY CANNOT EXPRESS THE
CASE.** `tests/test_run_diff.py` (11) builds two runs differing in `cost_layers` ALONE, against the
real schema via `lab_db.init_db`. **No pair of stored runs can do that** — `cost_layers` and
`broker_profile` landed in the same change and have moved together on every row, so on live data
something else always differs and the verdict reads "not comparable" even with the guard disarmed.
**Six mutations were RUN, each turning its named test red**, and each is recorded in its own test's
docstring: collapsing NULL into `[]`, returning `0.0` for an unrecorded R, dropping the partial-R
refusal, dropping the dollar warning, typo-ing a basis field, and forcing `diff_basis` to always
report a difference. ⚠ **The first of those is the one with no real-data counterexample**, which is
the whole argument for the file.

⚠ **A typo in `BASIS_FIELDS` does NOT fail silently, and the test that guards it was first written
on the opposite assumption.** `sqlite3.Row["nope"]` raises IndexError — checked, not assumed — so
the script crashes on every comparison rather than quietly calling two different runs comparable.
The guard is kept because it NAMES the bad field, where the raw IndexError says only that a key was
missing.

## `python_runner` finalizes the strategy after `_replay` (2026-08-20)

`_replay` reproduces `SosFadeStrategy.run()`'s bar loop (it needs the progress + cancel seams
`run()` has no room for), so it does not inherit `run()`'s end-of-book passes. `_execute` now calls
`strategy.finalize(df)` after the loop and before `build_results`. Without it `exec_recovery` would
be a toggle the form renders, the config carries, and **nothing consumes** — the run would simply
report no recovery trades and look correct. `run_dual` finalizes itself and the pass is idempotent,
so the call is safe on both paths. Guarded by `hasattr`: the runner serves every python strategy.

## A RERUN reads the broker the run was MADE on (2026-08-24)

🔴 Reported from the screen: *"when we click rerun charged it should still rerun against the broker
that the data originated from — otherwise all of my backtests will be broken."* The COST account was
already carried by the paired re-run; the BARS were not. `python_runner.bar_server(spec)` resolves
the run's stored `broker_profile` to its server and pins `BarSource` to it, so **a stored run
replays its own history and only a NEW run follows the attached terminal.**

⚠ **A profile with no recorded server pins nothing** rather than guessing — every pre-2026-08-02
row is that. ⚠ The refusal, the fetch-time check and why merging is unrecoverable live in
`backtest/CLAUDE.md`; do not restate them here.

## The BROKER spells the symbol, and the run records the resolved name (2026-08-26)

A strategy suggests a bare `XAUUSD`; PU Prime quotes gold as `XAUUSD.p` and Vantage quotes it bare.
`python_runner.run_symbol(instrument, broker)` rebases the typed name onto the profile's
`symbol_suffix`, and **run creation and the optimizer store the RESOLVED name** (rule 3 — the row
is what a rerun, the re-price endpoint and every comparison read back).

- ⚠ **It resolves BEFORE the history-floor check, not after.** That check is per broker and per
  symbol, so asking it about the typed name clears a window for a symbol the run never loads.
- ⚠ **The rebase is the LIVE side's `bot_account_registry.rebase_symbol`, not a second copy.** One
  implementation, so the two cannot drift about what gold is called.
- ⚠ **Three-state, and the middle one is the point.** `""` = measured to quote bare names,
  `None` = **nobody recorded it**, and the symbol is then left exactly as typed with the page
  saying so. Collapsing them hands a terminal a symbol nobody has seen it quote — failing in the
  very way this fixes. PU Prime Cent is `None`.
- ⚠ **PYTHON-ONLY.** NT8 and MT5 have no broker profile to resolve against; their instrument is
  sent exactly as given.
- ⚠ The Run modal resolves it for DISPLAY only — the backend is what binds, so the page can never
  put a wrong symbol on a row.

Why it went unnoticed for so long, and what the error said instead: `HISTORY.md` → *The broker that
spelled gold differently*.

## Recorded answers a browser spec replays are held to their route's model (2026-09-10)

`tests/test_api_recordings.py` validates every answer under `frontend/tests/recordings/` against the
`response_model` of the GET route that would serve it, matched in FastAPI's own order. The Bots page's
browser checks replay those recordings OFFLINE (`frontend/CLAUDE.md` -> *Offline specs*), so a
recording is a claim about this backend's SHAPE that goes stale in silence. ⚠ **A red here means
re-record, not relax.** ⚠ A required field ADDED to a model fails it; an optional one does not.
⚠ **Finding no recordings is a FAILURE.** 3 planted, 3 killed — two of them in a throwaway worktree,
because the in-memory bug planter cannot reach a test file (root `CLAUDE.md`).
⚠ **The chart spec is exempt BY NAME (`_UNMODELLED`), with its reason, since 2026-09-11**: it is
streamed as bytes with no model, and its contract is append-only because every run's spec is cached
for ever. A test fails the day that route gains a model. `GET /stress-tests/running-lock` gained
`StressLock` rather than an exemption — a missing model is a gap, not a reason.

## A run on a frame its strategy cannot read FAILS (2026-09-22)

The single-run runner hands the loaded frame's bar size to the strategy as it builds it (see
`backtest/notes/architecture.md`), so FFT on 5m bars now fails with its own reason instead of
completing on 0 trades (run 2db0e08a8ccc). Pinned in `tests/test_python_runner.py`, watched red.
