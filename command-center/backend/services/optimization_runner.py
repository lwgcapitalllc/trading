"""
Optimization runner — native NT8/MT5 optimizer.

All new optimizations use the platform's built-in optimizer (NT8 Strategy
Analyzer Optimization mode / MT5 Strategy Tester Optimization=1).  One VPS
job loads data once and runs the full param grid across all CPU cores.

The brute-force batch path (_run_batch, expand_grid, sample_combinations,
pick_search_method) is retained only to support retry of the two legacy
opt runs already in the DB.  It is not reachable from the UI or API for
new optimization requests.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import math
import random
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import logging

from services import lab_db, evaluator, runner_dispatch, worthiness
from services.metrics import daily_sharpe_from_values, apply_canonical_sharpe
from services.objectives import choose_objective
from services.backtest_runner import build_date_regime_map, write_job_progress, clear_progress, _tag_daily_pnl_with_regime, _LAB_RESULTS_DIR as _BR_RESULTS_DIR

log = logging.getLogger("optimization_runner")


_LAB_RESULTS_DIR = Path(__file__).parent.parent / "reports" / "lab"
_POLL_INTERVAL   = 5
_STALL_KILL_SEC  = 600

# ── Regime-filtered scoring ───────────────────────────────────────────────────

def _regime_filtered_score(
    run_id: str,
    date_to_regime: dict[str, str],
    regime_filter: str,
    obj_fn,
    firm: Optional[dict],
) -> float:
    """
    Load this run's equity_curve, keep only trades on regime_filter days,
    compute KPIs from that subset, and apply obj_fn.
    Returns -inf if the run has no trades in the target regime.
    """
    eq_path = _BR_RESULTS_DIR / run_id / "equity_curve.json"
    try:
        equity_curve: list[dict] = json.loads(eq_path.read_text())
    except Exception:
        return float("-inf")

    regime_trades = [
        t for t in equity_curve
        if t.get("date") and date_to_regime.get(t["date"]) == regime_filter
    ]
    if not regime_trades:
        return float("-inf")

    profits = [t.get("profit") or 0.0 for t in regime_trades]
    net_pnl  = sum(profits)
    wins     = [p for p in profits if p > 0]
    losses   = [abs(p) for p in profits if p < 0]
    pf       = sum(wins) / sum(losses) if losses else (1.5 if net_pnl > 0 else 0.0)
    win_rate = len(wins) / len(profits) if profits else 0.0

    # Cumulative DD on regime sub-sequence
    peak = eq = max_dd = 0.0
    for p in profits:
        eq += p
        if eq > peak:
            peak = eq
        dd = peak - eq
        if dd > max_dd:
            max_dd = dd

    # Daily-regime pnl for Sharpe (requires ≥2 distinct days).
    # Deliberately the UNDATED helper: this scores a regime-FILTERED population, so the days in
    # between are other regimes, not flat days of this one. Zero-filling them (as the canonical
    # daily_sharpe does) would answer the wrong question — "how does it do overall" instead of
    # "how does it do in this regime". Sparse-by-definition, so it stays sparse.
    daily: dict[str, float] = {}
    for t in regime_trades:
        d = t.get("date") or ""
        daily[d] = daily.get(d, 0.0) + (t.get("profit") or 0.0)
    sharpe = daily_sharpe_from_values(list(daily.values()))

    filtered_kpis = {
        "net_pnl":       net_pnl,
        "profit_factor": pf,
        "max_drawdown":  max_dd,
        "trade_count":   len(profits),
        "win_rate":      win_rate,
        "sharpe":        sharpe,
    }
    return obj_fn(filtered_kpis, firm)


def _rank(
    rows: list[dict],
    obj_fn,
    firm: Optional[dict],
    evals_by_run: dict[str, list[dict]],
    regime_filter: Optional[str],
    date_to_regime: dict[str, str],
    min_trades: int,
) -> Optional[str]:
    """One scoring pass. Returns the winning run_id, or None if nothing was eligible."""
    best_run_id: Optional[str] = None
    best_score = float("-inf")
    for row in rows:
        if min_trades and (row.get("trade_count") or 0) < min_trades:
            continue
        run_id = row["run_id"]
        if regime_filter and date_to_regime:
            score = _regime_filtered_score(run_id, date_to_regime, regime_filter, obj_fn, firm)
        else:
            score = obj_fn({**row, "_evaluations": evals_by_run.get(run_id, [])}, firm)
        # `-inf` is how every objective here says INELIGIBLE (drawdown breached, no trades in
        # the target regime). Starting the comparison at -inf and using a strict `>` therefore
        # left best_run_id None when every combo was ineligible — a finished optimization with
        # no winner and nothing on the page explaining it. The fallbacks below are the answer.
        if score > best_score:
            best_score  = score
            best_run_id = run_id
    return best_run_id


async def _pick_best_run(
    complete_rows: list[dict],
    opt: dict,
    firm: Optional[dict],
) -> tuple[Optional[str], Optional[str]]:
    """
    Score all complete child runs and return (best_run_id, winner_note).

    If opt["regime_filter"] is set, scores using regime-filtered KPIs. If opt["min_trades"] is
    set, a combo below the floor is scored and listed but cannot win.

    `winner_note` is non-None when the winner came from a FALLBACK rather than the stated rule.
    An optimization that names no winner is useless, so falling back is right — but the page
    must say the ★ was not chosen the way its header claims.
    """
    obj_fn = choose_objective(opt["mode"])
    regime_filter: Optional[str] = opt.get("regime_filter") or None
    min_trades = int(opt.get("min_trades") or 0)

    date_to_regime: dict[str, str] = {}
    if regime_filter:
        try:
            opt_strategy = lab_db.get_strategy(opt["strategy_id"])
            opt_runner = opt_strategy.get("runner", "ninjatrader") if opt_strategy else "ninjatrader"
            date_to_regime = await asyncio.to_thread(
                build_date_regime_map,
                opt["instrument"],
                opt["start_date"],
                opt["end_date"],
                opt_runner,
            )
            log.info("Regime filter '%s': %d trading days mapped", regime_filter, len(date_to_regime))
        except Exception as exc:
            log.warning("Could not build regime map (filter='%s'): %s — scoring unfiltered", regime_filter, exc)
            regime_filter = None

    # One query for every combo's evaluations, not one per combo.
    evals_by_run = (
        {} if (regime_filter and date_to_regime)
        else await asyncio.to_thread(
            lab_db.get_evaluations_for_runs, [r["run_id"] for r in complete_rows])
    )

    def rank(rf: Optional[str], floor: int) -> Optional[str]:
        return _rank(complete_rows, obj_fn, firm, evals_by_run, rf, date_to_regime, floor)

    best = rank(regime_filter, min_trades)
    if best:
        return best, None

    # Fallback 1 — the trade floor excluded everything. Drop the floor, keep the scoring.
    if min_trades:
        best = rank(regime_filter, 0)
        if best:
            return best, (
                f"No combination reached the {min_trades}-trade minimum, so the winner is the "
                "best of the whole grid. Treat it as a small sample.")

    # Fallback 2 — no combo traded in the target regime (or every combo breached drawdown).
    # Re-score unfiltered; this needs the evaluations the filtered pass skipped.
    if regime_filter:
        evals_by_run = await asyncio.to_thread(
            lab_db.get_evaluations_for_runs, [r["run_id"] for r in complete_rows])
        best = rank(None, min_trades) or rank(None, 0)
        if best:
            return best, (
                f"No combination produced trades in {regime_filter.replace('_', ' ').lower()} "
                "conditions, so the winner is scored on ALL trades — the regime filter did "
                "not apply.")

    # Nothing scored at all (an empty grid, or every combo ineligible on both passes).
    if complete_rows:
        best = max(complete_rows, key=lambda r: r.get("profit_factor") or 0.0)["run_id"]
        return best, (
            "Every combination was rejected by the scoring rule, so the winner is simply the "
            "highest profit factor. Read it as a ranking, not a pass.")
    return None, None


# NT8 Strategy Analyzer is single-window — only one backtest can use it at a time.
# Running more than 1 concurrent job causes SA window conflicts, display switch failures,
# and missing XML logs. Runs must be sequential for NinjaTrader.
_MAX_CONCURRENT  = 1

# Genetic-style: max samples for 3+D grids
_GENETIC_MAX_SAMPLES = 200


# ── Grid expansion ────────────────────────────────────────────────────────────

# One axis may not produce more values than this, and one grid may not produce more combos.
# Both are backstops against a typo, not opinions about a sensible grid — 250k combos is far
# past anything anyone would sit through, and the point is to REFUSE rather than to start.
_MAX_AXIS_VALUES = 10_000
_MAX_GRID_COMBOS = 250_000


def _expand_axis(spec: Any, name: str = "parameter") -> list:
    """Expand a single param spec to a list of values.

    ⚠ Raises rather than looping. Until 2026-08-04 the range branch was a `while v <= hi`
    loop with `v += step` and no guard on step: a `0` typed into a step box (or a max below
    the min with a negative step) never terminated, appending to a list forever. It ran inside
    the request handler on the event loop, so it did not hang the optimization — it hung the
    whole backend, every endpoint, until the process was killed.
    """
    if isinstance(spec, list):
        if not spec:
            raise ValueError(f"{name}: value list is empty — a swept parameter needs at least one value")
        if len(spec) > _MAX_AXIS_VALUES:
            raise ValueError(f"{name}: {len(spec)} values is more than the {_MAX_AXIS_VALUES} limit")
        return spec
    if isinstance(spec, dict):
        try:
            lo   = float(spec["min"])
            hi   = float(spec["max"])
            step = float(spec["step"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{name}: range needs numeric min, max and step ({exc})") from exc
        if not all(math.isfinite(v) for v in (lo, hi, step)):
            raise ValueError(f"{name}: min, max and step must be finite numbers")
        if step <= 0:
            raise ValueError(f"{name}: step must be greater than 0 (got {step:g})")
        if hi < lo:
            raise ValueError(f"{name}: max ({hi:g}) is below min ({lo:g})")
        # Counted arithmetically, not accumulated — the old loop's repeated `v += step` drifted
        # on floats, and an exact count is also what lets the ceiling be checked before building.
        n = int(math.floor((hi - lo) / step + 1e-9)) + 1
        if n > _MAX_AXIS_VALUES:
            raise ValueError(
                f"{name}: {lo:g} → {hi:g} step {step:g} is {n:,} values, over the "
                f"{_MAX_AXIS_VALUES:,} limit — widen the step or narrow the range")
        return [round(lo + i * step, 8) for i in range(n)]
    return [spec]


def validate_param_grid(param_grid: dict) -> int:
    """Check a grid is expandable and return how many combinations it produces.

    Raises ValueError with a message meant for a human. Called at REQUEST time so a bad grid
    is a 400 instead of a job that fails minutes later (or, before the guards above, a wedged
    backend).
    """
    if not param_grid:
        raise ValueError("param_grid cannot be empty")
    total = 1
    for name, spec in param_grid.items():
        total *= len(_expand_axis(spec, name))
        if total > _MAX_GRID_COMBOS:
            raise ValueError(
                f"that grid is over {_MAX_GRID_COMBOS:,} combinations — widen a step or "
                "drop a swept parameter")
    return total


def expand_grid(param_grid: dict) -> list[dict]:
    """Return list of {param: value} dicts for all combinations."""
    keys   = list(param_grid.keys())
    axes   = [_expand_axis(param_grid[k], k) for k in keys]
    combos = list(itertools.product(*axes))
    return [{k: v for k, v in zip(keys, combo)} for combo in combos]


def pick_search_method(param_grid: dict, requested: str) -> str:
    if requested == "native":
        return "native"
    if requested != "auto":
        return requested
    return "brute" if len(param_grid) <= 2 else "genetic"


def base_params_for(opt: dict, strategy: dict) -> dict:
    """The values every NON-SWEPT param is held at for the whole grid.

    Read the SOURCE RUN's params, not just the strategy's scanned defaults. The optimize modal
    shows the source run's values and labels them "inherited"; until 2026-08-02 this function did
    not exist and the grid ran on `default_params`, so optimizing from a tuned run silently used
    a different configuration from the one on screen (measured: run 096432c2ad20 shows TP1/TP2 at
    30/40 and the grid ran them at the 0/0 defaults).

    Only keys the strategy ALREADY declares are adopted. A run can carry leftovers from an older
    schema, and for MT5 a fixed_params dict polluted with inputs the EA does not declare makes the
    tester treat the set file as mismatched and silently run a single backtest instead of the
    optimization — so this may change a value, never introduce a key.
    """
    base = dict(strategy.get("default_params") or {})
    src_id = opt.get("source_run_id")
    if not src_id:
        return base
    src = lab_db.get_run(src_id)
    for k, v in ((src or {}).get("params") or {}).items():
        if k in base:
            base[k] = v
    return base


def sample_combinations(combos: list[dict], method: str) -> list[dict]:
    """Return the subset to actually run based on method."""
    if method == "genetic":
        if len(combos) <= _GENETIC_MAX_SAMPLES:
            return combos
        return random.sample(combos, _GENETIC_MAX_SAMPLES)
    return combos  # brute, native: run all combos


# ── Single run poller ─────────────────────────────────────────────────────────

async def _poll_one(run_id: str, job_id: str, ruleset_ids: list[str], opt_mode: str, write_progress: bool = False) -> None:
    started_at = time.time()

    # When write_progress is set, this poller writes the shared single-run progress
    # file. It MUST release that lock on every terminal path, or the stale "running"
    # status blocks all future NT8 single backtests (409). try/finally guarantees it.
    try:
        while True:
            await asyncio.sleep(_POLL_INTERVAL)

            try:
                status_data = await asyncio.to_thread(runner_dispatch.job_status, job_id)
            except Exception:
                if time.time() - started_at > _STALL_KILL_SEC:
                    lab_db.update_run_status(run_id, "failed_timeout", "Lost VPS contact")
                    return
                continue

            if write_progress:
                write_job_progress(
                    job_id=job_id,
                    pct=int(status_data.get("pct") or 0),
                    message=str(status_data.get("message") or ""),
                    started_at=started_at,
                )

            status = status_data.get("status", "running")

            if status == "complete":
                await _handle_opt_complete(run_id, job_id, ruleset_ids, opt_mode)
                return

            if status.startswith("failed"):
                lab_db.update_run_status(run_id, status, status_data.get("error") or "")
                return

            if time.time() - started_at > _STALL_KILL_SEC:
                try:
                    await asyncio.to_thread(runner_dispatch.cancel_job, job_id)
                except Exception:
                    pass
                lab_db.update_run_status(run_id, "failed_timeout", "No heartbeat — cancelled")
                return
    finally:
        if write_progress:
            clear_progress()


async def _handle_opt_complete(run_id: str, job_id: str, ruleset_ids: list[str], opt_mode: str) -> None:
    try:
        result = await asyncio.to_thread(runner_dispatch.job_results, job_id)
    except Exception as exc:
        lab_db.update_run_status(run_id, "failed_unknown", str(exc))
        return

    kpis         = result.get("kpis", {})
    equity_curve = result.get("equity_curve", [])
    daily_pnl    = result.get("daily_pnl", [])

    run_dir = _LAB_RESULTS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    eq_path   = run_dir / "equity_curve.json"
    dpnl_path = run_dir / "daily_pnl.json"
    eq_path.write_text(json.dumps(equity_curve, default=str))
    dpnl_path.write_text(json.dumps(daily_pnl, default=str))

    if daily_pnl:
        run_row = lab_db.get_run(run_id)
        tagged_pnl = await asyncio.to_thread(
            _tag_daily_pnl_with_regime,
            (run_row or {}).get("instrument", ""),
            (run_row or {}).get("start_date", ""),
            (run_row or {}).get("end_date", ""),
            daily_pnl,
            (run_row or {}).get("runner", "ninjatrader"),
        )
        dpnl_path.write_text(json.dumps(tagged_pnl, default=str))
        daily_pnl = tagged_pnl

    apply_canonical_sharpe(kpis, daily_pnl)  # consistent daily-√252 Sharpe (winner rerun)

    lab_db.update_run_complete(run_id, kpis, {
        "equity_curve": str(eq_path),
        "trades":       None,
        "daily_pnl":    str(dpnl_path),
    })

    evaluator.evaluate_run(run_id, ruleset_ids, kpis, equity_curve, daily_pnl)

    w = worthiness.score_run_after_evals(
        run_id, ruleset_ids,
        kpis.get("profit_factor"), kpis.get("max_drawdown"), kpis.get("trade_count"),
    )
    if w:
        lab_db.update_run_worthiness(run_id, w[0], w[1], w[2])


# ── Semaphore-limited batch runner ────────────────────────────────────────────

async def _run_batch(
    run_ids:       list[str],
    job_specs:     list[dict],
    ruleset_ids:   list[str],
    opt_mode:      str,
    runner:        str,
    opt_id:        str,
    write_progress: bool = False,
) -> None:
    sem = asyncio.Semaphore(_MAX_CONCURRENT)

    async def _one(run_id: str, job_spec: dict):
        async with sem:
            # Abort if the optimization was cancelled while we were queued
            current_opt = lab_db.get_optimization(opt_id)
            if current_opt and current_opt.get("status") == "failed_cancelled":
                lab_db.update_run_status(run_id, "failed_cancelled", "Optimization cancelled")
                return
            try:
                await asyncio.to_thread(runner_dispatch.start_backtest, job_spec, runner)
            except Exception as exc:
                lab_db.update_run_status(run_id, "failed_unknown", str(exc))
                lab_db.increment_optimization_completed(opt_id)
                return
            await _poll_one(run_id, job_spec["job_id"], ruleset_ids, opt_mode, write_progress=write_progress)
            lab_db.increment_optimization_completed(opt_id)

    await asyncio.gather(*[_one(rid, spec) for rid, spec in zip(run_ids, job_specs)])


# ── Grid sensitivity (Part A) ─────────────────────────────────────────────────

def _compute_grid_sensitivity(combos_all: list[dict], param_ranges: dict) -> tuple[float, dict]:
    """
    Measure how isolated the winner is in the full optimizer grid.

    For each ranged param, finds the winner's adjacent neighbors (one step up or
    down in that param, all others matching) and measures the PF degradation.
    A flat plateau → score near 0 (robust). A lone spike → score near 1 (overfit).

    Returns (max_degradation_score, per_param_summary_dict).
    """
    if not combos_all:
        return 0.0, {}

    winner = max(combos_all, key=lambda c: c.get("kpis", {}).get("profit_factor") or 0.0)
    winner_pf = winner.get("kpis", {}).get("profit_factor") or 0.0
    winner_params = winner.get("params", {})

    if winner_pf <= 0:
        return 0.0, {}

    # Collect sorted unique values per ranged param for neighbor lookup
    param_vals: dict[str, list] = {}
    for pname in param_ranges:
        raw = sorted({c["params"].get(pname) for c in combos_all if pname in c.get("params", {})})
        if len(raw) > 1:
            param_vals[pname] = raw

    summary: dict = {}
    max_degradation = 0.0

    for pname, vals in param_vals.items():
        w_val = winner_params.get(pname)
        if w_val is None:
            continue
        # Find winner's position in the sorted value list
        dists = [abs(v - w_val) for v in vals]
        idx = dists.index(min(dists))

        neighbors = []
        if idx > 0:
            neighbors.append(("down", vals[idx - 1]))
        if idx < len(vals) - 1:
            neighbors.append(("up", vals[idx + 1]))

        param_summary = {}
        for direction, n_val in neighbors:
            # Find combo matching winner on all params except pname
            for c in combos_all:
                cp = c.get("params", {})
                if abs(cp.get(pname, -999) - n_val) > 1e-6:
                    continue
                if all(abs(cp.get(k, -999) - winner_params.get(k, -999)) < 1e-6
                       for k in winner_params if k != pname):
                    n_pf = c.get("kpis", {}).get("profit_factor") or 0.0
                    deg = max(0.0, (winner_pf - n_pf) / winner_pf)
                    max_degradation = max(max_degradation, deg)
                    param_summary[direction] = {
                        "value": n_val,
                        "profit_factor": round(n_pf, 4),
                        "degradation": round(deg, 4),
                    }
                    break

        if param_summary:
            summary[pname] = param_summary

    return round(max_degradation, 4), summary

# ── Native optimizer path ─────────────────────────────────────────────────────

# Max seconds to wait for the native optimizer VPS job (all combos in one run)
_NATIVE_OPT_STALL_SEC = 7200  # 2 hours


async def run_native_optimization(optimization_id: str) -> None:
    """
    Drive NT8's built-in optimizer for one strategy in a single VPS job.

    Instead of N individual backtest calls, sends ONE /native-optimize request
    that runs NT8's Strategy Analyzer in Optimization mode (one data load, all CPU
    cores).  Result is a grid of {params, kpis} combos.  Run rows are created
    after the grid comes back, marked complete immediately.

    Auto-trigger stress test is skipped — native combo runs have no per-combo
    equity curve.  The winner can be stress-tested manually via a separate run.
    """
    opt = lab_db.get_optimization(optimization_id)
    if not opt:
        return

    strategy = lab_db.get_strategy(opt["strategy_id"])
    if not strategy:
        lab_db.fail_optimization(optimization_id, "Strategy not found")
        return

    runner_str = strategy.get("runner", "ninjatrader")
    firm = lab_db.get_ruleset(opt["ruleset_id"]) if opt.get("ruleset_id") else None

    # Build fixed_params: the source run's values as baseline (see base_params_for — this is what
    # makes the modal's "inherited" label true), foundational config on top. Foundational must come
    # last so ruleset values (AccountSize, RiskPerTradePct, etc.) override strategy sentinel
    # defaults (-1) — not the other way around.
    param_ranges = opt["param_grid"]
    fixed_params: dict = {}
    for k, v in base_params_for(opt, strategy).items():
        if k not in param_ranges:
            fixed_params[k] = v
    # Foundational injection is NinjaScript-only — MQL5 strategies have no
    # [Category("Foundational")] inputs, so injecting NT8 params (AccountSize,
    # EarliestEntryTimeET, DaysOfWeekAllowed, ...) pollutes the MT5 .set file with
    # parameters the EA doesn't declare. MT5 then treats the set file as mismatched
    # and silently runs a single backtest instead of the optimization (no
    # opt_results.csv). Mirror trigger_backtest, which forces no injection for mt5.
    # `python` is excluded alongside mt5: a Python strategy's config is a dataclass with a fixed
    # field set, so an injected NT8 param is a TypeError at construction, not a spare input.
    if firm and runner_str not in ("mt5", "python"):
        fixed_params.update(runner_dispatch.build_foundational_params(firm))

    opt_job_id = f"nopt_{optimization_id}"

    async def _persist_log() -> None:
        """Fetch the final VPS agent log and save it so it survives agent restarts."""
        try:
            txt = await asyncio.to_thread(
                lambda: runner_dispatch.job_log(opt_job_id, lines=500, runner=runner_str)
            )
            if txt:
                log_dir = _LAB_RESULTS_DIR / optimization_id
                log_dir.mkdir(parents=True, exist_ok=True)
                (log_dir / "opt_log.txt").write_text(txt, encoding="utf-8")
        except Exception as _exc:
            log.warning("Could not persist opt log for %s: %s", optimization_id, _exc)

    spec = {
        "job_id":             opt_job_id,
        "strategy_class":     strategy["class_name"],
        "instrument":         opt["instrument"],
        "bar_type":           opt.get("bar_type", "Minute"),
        "bar_value":          opt.get("bar_value", 5),
        "start_date":         opt["start_date"],
        "end_date":           opt["end_date"],
        "commission_per_side": opt["commission_per_side"],
        "slippage_ticks":     opt["slippage_ticks"],
        "param_ranges":       param_ranges,
        "fixed_params":       fixed_params,
        # Layered costs ride through to `python_runner._cost_profile`. NT8 and MT5 ignore them
        # (they have no such contract), which is why they are passed unconditionally rather than
        # behind a runner branch — the spec states what was asked for, and each runner charges
        # what it can. ⚠ NULL is NOT [] here either: an optimization row written before this
        # column keeps the old, free-book behaviour rather than being silently re-priced.
        "cost_layers":        opt.get("cost_layers"),
        "broker_profile":     opt.get("broker_profile"),
    }

    try:
        await asyncio.to_thread(runner_dispatch.start_native_optimization, spec, runner_str)
    except Exception as exc:
        lab_db.fail_optimization(optimization_id, f"VPS submit failed: {exc}")
        await _persist_log()
        return

    # Poll the single job until it completes, is cancelled, or stalls
    started_at   = time.time()
    last_written = -1  # track last completed_count written to DB to avoid redundant writes
    while True:
        await asyncio.sleep(_POLL_INTERVAL)

        # Cancel is issued against the DB row by the endpoint; this loop is what makes it mean
        # something. Without the check, a cancelled optimization kept running to the end and
        # then overwrote its own 'failed_cancelled' status with 'complete'.
        current = lab_db.get_optimization(optimization_id)
        if current and current.get("status") == "failed_cancelled":
            log.info("Native opt %s cancelled — stopping the poller", optimization_id)
            await _persist_log()
            return

        try:
            status_data = await asyncio.to_thread(runner_dispatch.job_status, opt_job_id, runner_str)
        except Exception:
            if time.time() - started_at > _NATIVE_OPT_STALL_SEC:
                lab_db.fail_optimization(optimization_id, "Lost VPS contact")
                return
            continue

        status = status_data.get("status", "running")

        # Live completed_runs update for sequential runners (MT5).
        completed_count = status_data.get("completed_count")
        if completed_count is not None and completed_count != last_written:
            lab_db.set_optimization_completed_runs(optimization_id, completed_count)
            last_written = completed_count

        if status == "complete":
            break

        if status.startswith("failed"):
            lab_db.fail_optimization(
                optimization_id,
                status_data.get("error") or status,
            )
            await _persist_log()
            return

        if time.time() - started_at > _NATIVE_OPT_STALL_SEC:
            try:
                await asyncio.to_thread(runner_dispatch.cancel_job, opt_job_id, runner_str)
            except Exception:
                pass
            lab_db.fail_optimization(optimization_id, "Native optimizer timed out")
            await _persist_log()
            return

    # Retrieve the full combo grid
    try:
        result = await asyncio.to_thread(runner_dispatch.native_opt_results, opt_job_id, runner_str)
    except Exception as exc:
        lab_db.fail_optimization(optimization_id, f"Could not fetch grid: {exc}")
        await _persist_log()
        return

    combos = result.get("combos", [])
    if not combos:
        lab_db.fail_optimization(optimization_id, "Native optimizer returned no combos")
        await _persist_log()
        return

    # NT8 drops zero-trade combos from its CSV. Update estimated_runs to the actual
    # count so the progress bar reaches 100% instead of sitting at grid_size% complete.
    lab_db.update_optimization_estimated_runs(optimization_id, len(combos))

    # Step 3A — grid sensitivity from the FULL combo set (before any cut).
    # Measures how isolated the winner is; no new NT8 backtests required.
    try:
        gs_score, gs_summary = _compute_grid_sensitivity(combos, param_ranges)
        lab_db.update_optimization_grid_sensitivity(optimization_id, gs_score, gs_summary)
        log.info("Native opt %s: grid_sensitivity_score=%.4f (%d params in summary)",
                 optimization_id, gs_score, len(gs_summary))
    except Exception as exc:
        log.warning("Grid sensitivity compute failed for opt %s: %s", optimization_id, exc)

    # Drawdown substitution for prop firm evaluation.
    # NT8 "Max. drawdown" is the cumulative peak-to-trough over the full backtest (~months).
    # Prop firm max_loss_eod is a per-DAY limit.  Comparing them directly marks every combo
    # as a drawdown breach.  The strategy's own MaxDailyLoss cap IS the correct per-period
    # comparison: if MaxDailyLoss <= max_loss_eod the strategy never exceeds the daily limit.
    _max_daily_loss = fixed_params.get("MaxDailyLoss")
    _effective_dd: Optional[float] = float(_max_daily_loss) if _max_daily_loss is not None and _max_daily_loss >= 0 else None

    ruleset_ids = [opt["ruleset_id"]] if opt.get("ruleset_id") else []
    now         = int(time.time())
    run_ids: list[str] = []

    from services import evaluator, worthiness

    # A native combo arrives already finished, so the whole grid is one bulk write rather than
    # two statements (and two sqlite connections) per combo. On a 1,000-combo grid that was
    # ~2,000 connections before the evaluator and the winner scan even started.
    rows_to_insert: list[dict] = []
    scored: list[dict] = []
    for combo in combos:
        run_id = uuid.uuid4().hex[:12]
        run_ids.append(run_id)

        kpis         = combo.get("kpis", {})
        combo_params = combo.get("params", {})

        rows_to_insert.append({
            "run_id":             run_id,
            "strategy_id":        opt["strategy_id"],
            "instrument":         opt["instrument"],
            "params":             {**fixed_params, **combo_params},
            "bar_type":           opt.get("bar_type", "Minute"),
            "bar_value":          opt.get("bar_value", 5),
            "start_date":         opt["start_date"],
            "end_date":           opt["end_date"],
            "commission_per_side": opt["commission_per_side"],
            "slippage_ticks":     opt["slippage_ticks"],
            "created_at":         now,
            "optimization_id":    optimization_id,
            "runner":             runner_str,
            "kpis":               kpis,
        })
        scored.append({"run_id": run_id, "kpis": kpis})

    await asyncio.to_thread(lab_db.insert_complete_optimization_runs, rows_to_insert)

    # Evaluate against rulesets using effective_dd (MaxDailyLoss) not cumulative max_drawdown.
    # Skipped wholesale when there is no ruleset — every python optimization is in that case,
    # and evaluating against nothing is a per-combo call that can only return [].
    worthiness_rows: list[tuple] = []
    if ruleset_ids:
        for s in scored:
            kpis = s["kpis"]
            kpis_for_eval = {**kpis}
            if _effective_dd is not None:
                kpis_for_eval["max_drawdown"] = _effective_dd
            evaluator.evaluate_run(s["run_id"], ruleset_ids, kpis_for_eval, [], [])
            w = worthiness.score_run_after_evals(
                s["run_id"], ruleset_ids,
                kpis.get("profit_factor"),
                kpis_for_eval.get("max_drawdown"),
                kpis.get("trade_count"),
            )
            if w:
                worthiness_rows.append((s["run_id"], w[0], w[1], w[2]))
        await asyncio.to_thread(lab_db.update_run_worthiness_bulk, worthiness_rows)

    lab_db.set_optimization_completed_runs(optimization_id, len(run_ids))

    # Score all completed runs and pick the winner
    complete_rows = await asyncio.to_thread(lab_db.list_optimization_runs, optimization_id)
    complete_rows = [r for r in complete_rows if r["status"] == "complete"]
    best_run_id, note = await _pick_best_run(complete_rows, opt, firm)
    lab_db.set_optimization_winner_note(optimization_id, note)
    lab_db.complete_optimization(optimization_id, best_run_id)
    await _persist_log()


# ── Main entry point ──────────────────────────────────────────────────────────

async def run_optimization(optimization_id: str) -> None:
    opt = lab_db.get_optimization(optimization_id)
    if not opt:
        return

    if opt.get("search_method") == "native":
        await run_native_optimization(optimization_id)
        return

    strategy = lab_db.get_strategy(opt["strategy_id"])
    if not strategy:
        lab_db.fail_optimization(optimization_id, "Strategy not found")
        return

    firm = lab_db.get_ruleset(opt["ruleset_id"]) if opt.get("ruleset_id") else None

    method = pick_search_method(opt["param_grid"], opt["search_method"])
    all_combos = expand_grid(opt["param_grid"])
    combos     = sample_combinations(all_combos, method)

    now = int(time.time())
    run_ids   = []
    job_specs = []

    for combo in combos:
        run_id = uuid.uuid4().hex[:12]
        run_ids.append(run_id)

        base_params = {**base_params_for(opt, strategy), **combo}
        merged_params = (
            runner_dispatch.inject_foundational(base_params, firm) if firm else base_params
        )
        lab_db.insert_run_optimization({
            "run_id":             run_id,
            "strategy_id":        opt["strategy_id"],
            "instrument":         opt["instrument"],
            "params":             merged_params,
            "bar_type":           opt.get("bar_type", "Minute"),
            "bar_value":          opt.get("bar_value", 5),
            "start_date":         opt["start_date"],
            "end_date":           opt["end_date"],
            "commission_per_side": opt["commission_per_side"],
            "slippage_ticks":     opt["slippage_ticks"],
            "status":             "running",
            "created_at":         now,
            "optimization_id":    optimization_id,
            "runner":             strategy.get("runner", "ninjatrader"),
        })

        job_specs.append({
            "job_id":            run_id,
            "strategy_class":    strategy["class_name"],
            "instrument":        opt["instrument"],
            "params":            merged_params,
            "bar_type":          opt.get("bar_type", "Minute"),
            "bar_value":         opt.get("bar_value", 5),
            "start_date":        opt["start_date"],
            "end_date":          opt["end_date"],
            "commission_per_side": opt["commission_per_side"],
            "slippage_ticks":    opt["slippage_ticks"],
        })

    ruleset_ids = [opt["ruleset_id"]] if opt.get("ruleset_id") else []
    await _run_batch(
        run_ids, job_specs,
        ruleset_ids=ruleset_ids,
        opt_mode=opt["mode"],
        runner=strategy.get("runner", "ninjatrader"),
        opt_id=optimization_id,
    )

    # Find best run by objective score (regime-filtered if opt["regime_filter"] is set)
    complete_rows = [
        row for run_id in run_ids
        if (row := lab_db.get_run(run_id)) and row["status"] == "complete"
    ]
    best_run_id, note = await _pick_best_run(complete_rows, opt, firm)
    lab_db.set_optimization_winner_note(optimization_id, note)
    lab_db.complete_optimization(optimization_id, best_run_id)
    if best_run_id and ruleset_ids:
        from services import stress_tester
        asyncio.create_task(stress_tester.trigger_auto_stress_test(
            best_run_id, ruleset_ids
        ))


def resolve_opt_eval_rulesets(opt: dict) -> list[str]:
    """Which rulesets a combo's full backtest should be scored against.

    Optimizer combos don't store an eval selection. Prefer the optimization's own
    ruleset (set for prop/futures `eval`/`funded` modes); otherwise inherit the
    selection from the run that spawned the optimization (the forex/`raw` case has
    no ruleset_id but is usually launched from an evaluated parent run). Returns []
    when nothing is inheritable — the caller then prompts the user to choose.
    """
    if opt.get("ruleset_id"):
        return [opt["ruleset_id"]]
    src_id = opt.get("source_run_id")
    if src_id:
        src = lab_db.get_run(src_id)
        if src and src.get("evaluate_firms"):
            try:
                return list(json.loads(src["evaluate_firms"]))
            except (json.JSONDecodeError, TypeError):
                return []
    return []


async def retry_single_optimization_run(run_id: str, evaluate_rulesets: Optional[list[str]] = None) -> None:
    """Re-fire a single optimization run as a full backtest. Caller must have already
    called reset_run_for_retry. `evaluate_rulesets` is the explicit scoring selection
    (e.g. chosen in the UI prompt); when None, it's resolved from the optimization."""
    row = lab_db.get_run(run_id)
    if not row:
        return
    opt_id = row["optimization_id"]
    opt = lab_db.get_optimization(opt_id)
    if not opt:
        return
    strategy = lab_db.get_strategy(opt["strategy_id"])
    if not strategy:
        lab_db.update_run_status(run_id, "failed_unknown", "Strategy not found")
        return
    ruleset_ids = evaluate_rulesets if evaluate_rulesets is not None else resolve_opt_eval_rulesets(opt)
    firm = lab_db.get_ruleset(ruleset_ids[0]) if ruleset_ids else None

    # Keep the optimization's own status as-is (complete/failed) — this is a
    # single-combo full backtest, not a re-run of the grid. Only the child run
    # should show as running.
    lab_db.decrement_optimization_completed(opt_id, 1, set_running=False)

    job_spec = {
        "job_id":             run_id,
        "strategy_class":     strategy["class_name"],
        "instrument":         row["instrument"],
        "params":             row["params"],
        "bar_type":           row["bar_type"],
        "bar_value":          row["bar_value"],
        "start_date":         row["start_date"],
        "end_date":           row["end_date"],
        "commission_per_side": row["commission_per_side"],
        "slippage_ticks":     row["slippage_ticks"],
    }
    await _run_batch(
        [run_id], [job_spec],
        ruleset_ids=ruleset_ids,
        opt_mode=opt["mode"],
        runner=strategy.get("runner", "ninjatrader"),
        opt_id=opt_id,
        write_progress=True,
    )

    # Re-score best run across all complete runs
    all_complete = [r for r in lab_db.list_optimization_runs(opt_id) if r["status"] == "complete"]
    best_run_id, note = await _pick_best_run(all_complete, opt, firm)
    lab_db.set_optimization_winner_note(opt_id, note)
    lab_db.complete_optimization(opt_id, best_run_id)
    if best_run_id and ruleset_ids:
        from services import stress_tester
        asyncio.create_task(stress_tester.trigger_auto_stress_test(
            best_run_id, ruleset_ids
        ))


async def retry_failed_runs(optimization_id: str) -> None:
    """Reset all failed child runs and re-fire them. Reuses the same run IDs — no new rows."""
    opt = lab_db.get_optimization(optimization_id)
    if not opt:
        return

    strategy = lab_db.get_strategy(opt["strategy_id"])
    if not strategy:
        lab_db.fail_optimization(optimization_id, "Strategy not found")
        return

    firm = lab_db.get_ruleset(opt["ruleset_id"]) if opt.get("ruleset_id") else None
    ruleset_ids = [opt["ruleset_id"]] if opt.get("ruleset_id") else []

    failed_rows = lab_db.list_optimization_failed_runs(optimization_id)
    if not failed_rows:
        return

    # Reset each failed run and decrement the completed counter
    for row in failed_rows:
        lab_db.reset_run_for_retry(row["run_id"])
    lab_db.decrement_optimization_completed(optimization_id, len(failed_rows))

    run_ids   = [r["run_id"] for r in failed_rows]
    job_specs = [
        {
            "job_id":             r["run_id"],
            "strategy_class":     strategy["class_name"],
            "instrument":         r["instrument"],
            "params":             r["params"],
            "bar_type":           r["bar_type"],
            "bar_value":          r["bar_value"],
            "start_date":         r["start_date"],
            "end_date":           r["end_date"],
            "commission_per_side": r["commission_per_side"],
            "slippage_ticks":     r["slippage_ticks"],
        }
        for r in failed_rows
    ]

    await _run_batch(
        run_ids, job_specs,
        ruleset_ids=ruleset_ids,
        opt_mode=opt["mode"],
        runner=strategy.get("runner", "ninjatrader"),
        opt_id=optimization_id,
    )

    # Re-score best run across all complete runs (original + retried)
    all_complete = [
        r for r in lab_db.list_optimization_runs(optimization_id)
        if r["status"] == "complete"
    ]
    best_run_id, note = await _pick_best_run(all_complete, opt, firm)
    lab_db.set_optimization_winner_note(optimization_id, note)
    lab_db.complete_optimization(optimization_id, best_run_id)
    if best_run_id and ruleset_ids:
        from services import stress_tester
        asyncio.create_task(stress_tester.trigger_auto_stress_test(
            best_run_id, ruleset_ids
        ))
