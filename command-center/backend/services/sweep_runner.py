"""
Sweep runner — fans out N parallel backtests (one per instrument) for a sweep job.
Does NOT use lab_progress.json (that's for single-run flow only).
Each run tracks state independently in backtest_runs.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Optional

from services import lab_db, evaluator, vps_client, worthiness


_LAB_RESULTS_DIR = Path(__file__).parent.parent / "reports" / "lab"
_POLL_INTERVAL   = 5
_STALL_KILL_SEC  = 600


async def _run_single(
    run_id:      str,
    job_id:      str,
    strategy_id: str,
    instrument:  str,
    firm_ids:    list[str],
    runner:      str,
) -> None:
    """Poll a single sweep child run to completion. No progress file used."""
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
            await _handle_complete(run_id, job_id, firm_ids)
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


async def _handle_complete(run_id: str, job_id: str, firm_ids: list[str]) -> None:
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

    evaluator.evaluate_run(run_id, firm_ids, kpis, equity_curve, daily_pnl)

    w = worthiness.score_run_after_evals(
        run_id, firm_ids,
        kpis.get("profit_factor"), kpis.get("max_drawdown"), kpis.get("trade_count"),
    )
    if w:
        lab_db.update_run_worthiness(run_id, w[0], w[1], w[2])


async def run_sweep(
    sweep_id:   str,
    run_specs:  list[dict],   # [{run_id, job_id, strategy_id, instrument, firm_ids, runner}]
    job_specs:  list[dict],   # VPS job_spec payloads, one per run
) -> None:
    """Launch all N runs in parallel and wait for all to finish."""
    # Fire all VPS jobs first
    for spec, job in zip(run_specs, job_specs):
        try:
            await asyncio.to_thread(vps_client.start_backtest, job, spec["runner"])
        except Exception as exc:
            lab_db.update_run_status(spec["run_id"], "failed_unknown", str(exc))

    # Poll all concurrently
    tasks = [
        _run_single(
            spec["run_id"],
            spec["job_id"],
            spec["strategy_id"],
            spec["instrument"],
            spec["firm_ids"],
            spec["runner"],
        )
        for spec in run_specs
    ]
    await asyncio.gather(*tasks, return_exceptions=True)
