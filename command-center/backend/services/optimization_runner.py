"""
Optimization runner — multi-call brute force implementation.

Decision (per M2 spec §5): NT Optimizer GUI automation (pywinauto) was not
attempted. Instead we generate all param combinations here and drive them as
individual backtest calls through the existing VPS agent pipeline. This is
slower but reliable and reuses all M1 infrastructure.

For "auto" search method, brute force is used for ≤2D grids and a simple
random-subset genetic-style sample is used for 3+D grids.
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

from services import lab_db, evaluator, vps_client, worthiness
from services.objectives import choose_objective


_LAB_RESULTS_DIR = Path(__file__).parent.parent / "reports" / "lab"
_POLL_INTERVAL   = 5
_STALL_KILL_SEC  = 600

# NT8 Strategy Analyzer is single-window — only one backtest can use it at a time.
# Running more than 1 concurrent job causes SA window conflicts, display switch failures,
# and missing XML logs. Runs must be sequential for NinjaTrader.
_MAX_CONCURRENT  = 1

# Genetic-style: max samples for 3+D grids
_GENETIC_MAX_SAMPLES = 200


# ── Grid expansion ────────────────────────────────────────────────────────────

def _expand_axis(spec: Any) -> list:
    """Expand a single param spec to a list of values."""
    if isinstance(spec, list):
        return spec
    if isinstance(spec, dict):
        lo   = float(spec["min"])
        hi   = float(spec["max"])
        step = float(spec["step"])
        vals = []
        v = lo
        while v <= hi + 1e-9:
            vals.append(round(v, 8))
            v += step
        return vals
    return [spec]


def expand_grid(param_grid: dict) -> list[dict]:
    """Return list of {param: value} dicts for all combinations."""
    keys   = list(param_grid.keys())
    axes   = [_expand_axis(param_grid[k]) for k in keys]
    combos = list(itertools.product(*axes))
    return [{k: v for k, v in zip(keys, combo)} for combo in combos]


def pick_search_method(param_grid: dict, requested: str) -> str:
    if requested != "auto":
        return requested
    return "brute" if len(param_grid) <= 2 else "genetic"


def sample_combinations(combos: list[dict], method: str) -> list[dict]:
    """Return the subset to actually run based on method."""
    if method == "genetic":
        if len(combos) <= _GENETIC_MAX_SAMPLES:
            return combos
        return random.sample(combos, _GENETIC_MAX_SAMPLES)
    return combos  # brute: run all


# ── Single run poller ─────────────────────────────────────────────────────────

async def _poll_one(run_id: str, job_id: str, ruleset_ids: list[str], opt_mode: str) -> None:
    started_at = time.time()

    while True:
        await asyncio.sleep(_POLL_INTERVAL)

        try:
            status_data = await asyncio.to_thread(vps_client.job_status, job_id)
        except Exception:
            if time.time() - started_at > _STALL_KILL_SEC:
                lab_db.update_run_status(run_id, "failed_timeout", "Lost VPS contact")
                return
            continue

        status = status_data.get("status", "running")

        if status == "complete":
            await _handle_opt_complete(run_id, job_id, ruleset_ids, opt_mode)
            return

        if status.startswith("failed"):
            lab_db.update_run_status(run_id, status, status_data.get("error") or "")
            return

        if time.time() - started_at > _STALL_KILL_SEC:
            try:
                await asyncio.to_thread(vps_client.cancel_job, job_id)
            except Exception:
                pass
            lab_db.update_run_status(run_id, "failed_timeout", "No heartbeat — cancelled")
            return


async def _handle_opt_complete(run_id: str, job_id: str, ruleset_ids: list[str], opt_mode: str) -> None:
    try:
        result = await asyncio.to_thread(vps_client.job_results, job_id)
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
    run_ids:      list[str],
    job_specs:    list[dict],
    ruleset_ids:  list[str],
    opt_mode:     str,
    runner:       str,
    opt_id:       str,
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
                await asyncio.to_thread(vps_client.start_backtest, job_spec, runner)
            except Exception as exc:
                lab_db.update_run_status(run_id, "failed_unknown", str(exc))
                lab_db.increment_optimization_completed(opt_id)
                return
            await _poll_one(run_id, job_spec["job_id"], ruleset_ids, opt_mode)
            lab_db.increment_optimization_completed(opt_id)

    await asyncio.gather(*[_one(rid, spec) for rid, spec in zip(run_ids, job_specs)])


# ── Main entry point ──────────────────────────────────────────────────────────

async def run_optimization(optimization_id: str) -> None:
    opt = lab_db.get_optimization(optimization_id)
    if not opt:
        return

    strategy = lab_db.get_strategy(opt["strategy_id"])
    if not strategy:
        lab_db.fail_optimization(optimization_id, "Strategy not found")
        return

    firm = lab_db.get_ruleset(opt["ruleset_id"])
    if not firm:
        lab_db.fail_optimization(optimization_id, "Firm not found")
        return

    method = pick_search_method(opt["param_grid"], opt["search_method"])
    all_combos = expand_grid(opt["param_grid"])
    combos     = sample_combinations(all_combos, method)

    now = int(time.time())
    run_ids   = []
    job_specs = []

    for combo in combos:
        run_id = uuid.uuid4().hex[:12]
        run_ids.append(run_id)

        merged_params = {**strategy.get("default_params", {}), **combo}
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

    await _run_batch(
        run_ids, job_specs,
        ruleset_ids=[opt["ruleset_id"]],
        opt_mode=opt["mode"],
        runner=strategy.get("runner", "ninjatrader"),
        opt_id=optimization_id,
    )

    # Find best run by objective score
    obj_fn = choose_objective(opt["mode"])
    best_run_id: Optional[str] = None
    best_score  = float("-inf")

    for run_id in run_ids:
        row = lab_db.get_run(run_id)
        if not row or row["status"] != "complete":
            continue
        evals = lab_db.get_evaluations(run_id)
        run_with_evals = {**row, "_evaluations": evals}
        score = obj_fn(run_with_evals, firm)
        if score > best_score:
            best_score   = score
            best_run_id  = run_id

    lab_db.complete_optimization(optimization_id, best_run_id)


async def retry_single_optimization_run(run_id: str) -> None:
    """Re-fire a single optimization run. Caller must have already called reset_run_for_retry."""
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
    firm = lab_db.get_ruleset(opt["ruleset_id"])
    if not firm:
        lab_db.update_run_status(run_id, "failed_unknown", "Firm not found")
        return

    lab_db.decrement_optimization_completed(opt_id, 1)

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
        ruleset_ids=[opt["ruleset_id"]],
        opt_mode=opt["mode"],
        runner=strategy.get("runner", "ninjatrader"),
        opt_id=opt_id,
    )

    # Re-score best run across all complete runs
    all_complete = [r for r in lab_db.list_optimization_runs(opt_id) if r["status"] == "complete"]
    obj_fn = choose_objective(opt["mode"])
    best_run_id: Optional[str] = None
    best_score = float("-inf")
    for r in all_complete:
        evals = lab_db.get_evaluations(r["run_id"])
        score = obj_fn({**r, "_evaluations": evals}, firm)
        if score > best_score:
            best_score  = score
            best_run_id = r["run_id"]
    lab_db.complete_optimization(opt_id, best_run_id)


async def retry_failed_runs(optimization_id: str) -> None:
    """Reset all failed child runs and re-fire them. Reuses the same run IDs — no new rows."""
    opt = lab_db.get_optimization(optimization_id)
    if not opt:
        return

    strategy = lab_db.get_strategy(opt["strategy_id"])
    if not strategy:
        lab_db.fail_optimization(optimization_id, "Strategy not found")
        return

    firm = lab_db.get_ruleset(opt["ruleset_id"])
    if not firm:
        lab_db.fail_optimization(optimization_id, "Firm not found")
        return

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
        ruleset_ids=[opt["ruleset_id"]],
        opt_mode=opt["mode"],
        runner=strategy.get("runner", "ninjatrader"),
        opt_id=optimization_id,
    )

    # Re-score best run across all complete runs (original + retried)
    all_complete = [
        r for r in lab_db.list_optimization_runs(optimization_id)
        if r["status"] == "complete"
    ]
    obj_fn = choose_objective(opt["mode"])
    best_run_id: Optional[str] = None
    best_score  = float("-inf")
    for row in all_complete:
        evals = lab_db.get_evaluations(row["run_id"])
        score = obj_fn({**row, "_evaluations": evals}, firm)
        if score > best_score:
            best_score  = score
            best_run_id = row["run_id"]

    lab_db.complete_optimization(optimization_id, best_run_id)
