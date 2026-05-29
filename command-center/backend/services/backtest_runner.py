"""
Async background poller for VPS backtest jobs.
Spawned as an asyncio.Task from the backtests router after POSTing to the VPS agent.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Optional

from services import lab_db, evaluator, vps_client

_POLL_INTERVAL   = 5     # seconds between agent polls
_STALL_WARN_SEC  = 120   # 2 min — warn but keep polling
_STALL_KILL_SEC  = 600   # 10 min — cancel job, mark failed_timeout

_LAB_PROGRESS_PATH = Path(__file__).parent.parent / "data" / "lab_progress.json"
_LAB_RESULTS_DIR   = Path(__file__).parent.parent / "reports" / "lab"


# ── Progress file helpers ──────────────────────────────────────────────────────

def _write_progress(data: dict) -> None:
    _LAB_PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _LAB_PROGRESS_PATH.write_text(json.dumps(data, default=str))


def read_progress() -> dict:
    try:
        return json.loads(_LAB_PROGRESS_PATH.read_text())
    except Exception:
        return {"status": "idle", "pct": 0, "message": ""}


# ── Failure path ───────────────────────────────────────────────────────────────

def _fail(run_id: str, job_id: str, status: str, error_msg: str) -> None:
    lab_db.update_run_status(run_id, status, error_msg)
    _write_progress({
        "job_id": job_id,
        "status": status,
        "pct": 0,
        "message": error_msg,
        "error_message": error_msg,
        "updated_at": str(time.time()),
        "heartbeat_age_seconds": 0.0,
    })


# ── Completion path ────────────────────────────────────────────────────────────

async def _handle_complete(
    run_id: str,
    job_id: str,
    strategy_id: str,
    instrument: str,
    firm_ids: list[str],
) -> None:
    try:
        result = await asyncio.to_thread(vps_client.job_results, job_id)
    except Exception as exc:
        _fail(run_id, job_id, "failed_unknown", f"Could not fetch results from agent: {exc}")
        return

    kpis         = result.get("kpis", {})
    equity_curve = result.get("equity_curve", [])
    daily_pnl    = result.get("daily_pnl", [])

    # persist JSON files
    run_dir = _LAB_RESULTS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    equity_path   = run_dir / "equity_curve.json"
    daily_pnl_path = run_dir / "daily_pnl.json"
    equity_path.write_text(json.dumps(equity_curve, default=str))
    daily_pnl_path.write_text(json.dumps(daily_pnl, default=str))

    lab_db.update_run_complete(run_id, kpis, {
        "equity_curve": str(equity_path),
        "trades":       None,
        "daily_pnl":    str(daily_pnl_path),
    })

    evaluator.evaluate_run(run_id, firm_ids, kpis, equity_curve, daily_pnl)

    _write_progress({
        "job_id":               job_id,
        "job_type":             "backtest",
        "status":               "complete",
        "strategy_id":          strategy_id,
        "instrument":           instrument,
        "pct":                  100,
        "message":              "Complete",
        "started_at":           None,
        "updated_at":           str(time.time()),
        "heartbeat_age_seconds": 0.0,
        "error_message":        None,
    })


# ── Main poller ────────────────────────────────────────────────────────────────

async def run_backtest_job(
    run_id:      str,
    job_id:      str,
    strategy_id: str,
    instrument:  str,
    firm_ids:    list[str],
) -> None:
    started_at = time.time()
    stall_warned = False

    _write_progress({
        "job_id":               job_id,
        "job_type":             "backtest",
        "status":               "running",
        "strategy_id":          strategy_id,
        "instrument":           instrument,
        "pct":                  0,
        "message":              "Waiting for VPS…",
        "started_at":           str(started_at),
        "updated_at":           str(started_at),
        "heartbeat_age_seconds": 0.0,
        "error_message":        None,
    })

    while True:
        await asyncio.sleep(_POLL_INTERVAL)

        try:
            status_data = await asyncio.to_thread(vps_client.job_status, job_id)
        except Exception as exc:
            elapsed = time.time() - started_at
            if elapsed > _STALL_KILL_SEC:
                _fail(run_id, job_id, "failed_timeout",
                      f"Lost contact with VPS agent after {elapsed:.0f}s: {exc}")
                return
            # transient network error — keep trying
            continue

        status     = status_data.get("status", "running")
        pct        = status_data.get("pct", 0)
        message    = status_data.get("message", "")
        updated_at = status_data.get("updated_at", time.time())

        now = time.time()
        try:
            heartbeat_age = now - float(updated_at)
        except Exception:
            heartbeat_age = 0.0

        if heartbeat_age > _STALL_WARN_SEC and not stall_warned:
            stall_warned = True
            message = f"[STALL] No agent heartbeat for {int(heartbeat_age)}s"

        _write_progress({
            "job_id":               job_id,
            "job_type":             "backtest",
            "status":               "running" if not status.startswith("failed") else status,
            "strategy_id":          strategy_id,
            "instrument":           instrument,
            "pct":                  pct,
            "message":              message,
            "started_at":           str(started_at),
            "updated_at":           str(now),
            "heartbeat_age_seconds": heartbeat_age,
            "error_message":        None,
        })

        if status == "complete":
            await _handle_complete(run_id, job_id, strategy_id, instrument, firm_ids)
            return

        if status.startswith("failed"):
            _fail(run_id, job_id, status, status_data.get("error") or message)
            return

        # kill if stalled too long
        if heartbeat_age > _STALL_KILL_SEC or (now - started_at) > _STALL_KILL_SEC:
            try:
                await asyncio.to_thread(vps_client.cancel_job, job_id)
            except Exception:
                pass
            _fail(run_id, job_id, "failed_timeout",
                  f"No heartbeat for {int(heartbeat_age)}s — job cancelled")
            return
