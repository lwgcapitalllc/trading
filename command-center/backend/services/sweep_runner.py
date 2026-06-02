"""
Sweep runner — fans out N sequential backtests (one per instrument) for a sweep job.
Does NOT use lab_progress.json (that's for single-run flow only).
Each run tracks state independently in backtest_runs.

NT8 Strategy Analyzer is single-window: only one job can use it at a time.
Sweep runs are serialised with _MAX_CONCURRENT = 1 — same constraint as the optimizer.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from services import lab_db, evaluator, vps_client, worthiness


_LAB_RESULTS_DIR = Path(__file__).parent.parent / "reports" / "lab"
_POLL_INTERVAL   = 5
_STALL_KILL_SEC  = 600

# NT8 SA window can only run one job at a time.
_MAX_CONCURRENT  = 1


async def _handle_complete(run_id: str, job_id: str, ruleset_ids: list[str]) -> None:
    try:
        result = await asyncio.to_thread(vps_client.job_results, job_id)
    except Exception as exc:
        lab_db.update_run_status(run_id, "failed_unknown", f"Could not fetch results: {exc}")
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


async def _run_one(run_id: str, job_id: str, job_spec: dict, ruleset_ids: list[str], runner: str) -> None:
    """Start a VPS job and poll it to completion. Called while holding the SA semaphore."""
    try:
        await asyncio.to_thread(vps_client.start_backtest, job_spec, runner)
    except Exception as exc:
        lab_db.update_run_status(run_id, "failed_unknown", str(exc))
        return

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
            await _handle_complete(run_id, job_id, ruleset_ids)
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


async def run_sweep(
    sweep_id:   str,
    run_specs:  list[dict],   # [{run_id, job_id, strategy_id, instrument, ruleset_ids, runner}]
    job_specs:  list[dict],   # VPS job_spec payloads, one per run
) -> None:
    """Run all N instruments one at a time through the single NT8 SA window."""
    sem = asyncio.Semaphore(_MAX_CONCURRENT)

    async def _one(spec: dict, job: dict) -> None:
        async with sem:
            await _run_one(spec["run_id"], spec["job_id"], job, spec["ruleset_ids"], spec["runner"])

    await asyncio.gather(*[_one(spec, job) for spec, job in zip(run_specs, job_specs)], return_exceptions=True)


async def retry_single_sweep_run(run_id: str) -> None:
    """Re-fire a single sweep run. Caller must have already called reset_run_for_retry."""
    row = lab_db.get_run(run_id)
    if not row:
        return
    sweep_id = row["sweep_id"]
    strategy = lab_db.get_strategy(row["strategy_id"])
    if not strategy:
        lab_db.update_run_status(run_id, "failed_unknown", "Strategy not found")
        return

    ruleset_ids: list[str] = []
    for r in lab_db.list_sweep_runs(sweep_id):
        if r["status"] == "complete" and r["run_id"] != run_id:
            evals = lab_db.get_run_verdict_summary(r["run_id"])
            if evals:
                ruleset_ids = [e["ruleset_id"] for e in evals]
                break

    run_specs = [{"run_id": run_id, "job_id": run_id, "strategy_id": row["strategy_id"],
                  "instrument": row["instrument"], "ruleset_ids": ruleset_ids,
                  "runner": strategy.get("runner", "ninjatrader")}]
    job_specs = [{"job_id": run_id, "strategy_class": strategy["class_name"],
                  "instrument": row["instrument"], "params": row["params"],
                  "bar_type": row["bar_type"], "bar_value": row["bar_value"],
                  "start_date": row["start_date"], "end_date": row["end_date"],
                  "commission_per_side": row["commission_per_side"],
                  "slippage_ticks": row["slippage_ticks"]}]
    await run_sweep(sweep_id, run_specs, job_specs)


async def retry_failed_sweep_runs(sweep_id: str) -> None:
    """Reset all failed child runs and re-fire them through the SA semaphore."""
    failed_rows = lab_db.list_sweep_failed_runs(sweep_id)
    if not failed_rows:
        return

    first    = failed_rows[0]
    strategy = lab_db.get_strategy(first["strategy_id"])
    if not strategy:
        for row in failed_rows:
            lab_db.update_run_status(row["run_id"], "failed_unknown", "Strategy not found")
        return

    # Recover ruleset_ids from any completed run in the same sweep
    ruleset_ids: list[str] = []
    for r in lab_db.list_sweep_runs(sweep_id):
        if r["status"] == "complete":
            evals = lab_db.get_run_verdict_summary(r["run_id"])
            if evals:
                ruleset_ids = [e["ruleset_id"] for e in evals]
                break

    for row in failed_rows:
        lab_db.reset_run_for_retry(row["run_id"])

    run_specs = [
        {
            "run_id":       row["run_id"],
            "job_id":       row["run_id"],
            "strategy_id":  row["strategy_id"],
            "instrument":   row["instrument"],
            "ruleset_ids":  ruleset_ids,
            "runner":       strategy.get("runner", "ninjatrader"),
        }
        for row in failed_rows
    ]
    job_specs = [
        {
            "job_id":              row["run_id"],
            "strategy_class":      strategy["class_name"],
            "instrument":          row["instrument"],
            "params":              row["params"],
            "bar_type":            row["bar_type"],
            "bar_value":           row["bar_value"],
            "start_date":          row["start_date"],
            "end_date":            row["end_date"],
            "commission_per_side": row["commission_per_side"],
            "slippage_ticks":      row["slippage_ticks"],
        }
        for row in failed_rows
    ]

    await run_sweep(sweep_id, run_specs, job_specs)
