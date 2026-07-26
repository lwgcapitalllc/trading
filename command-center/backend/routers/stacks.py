"""
Stacks router — POST /backtests/stack, GET /backtests/stacks, GET/DELETE/cancel.

A "stack" layers 2+ Python strategies over ONE shared instrument/window to see combined
portfolio P&L. Each strategy runs as a normal single-strategy Python backtest (grouped by
stack_id) through the existing python runner; the runs are serialised one-at-a-time by the
same Semaphore(1) the sweep uses (and guarded by the python platform lock). The combined
portfolio line + per-strategy toggles are composed CLIENT-SIDE from each child's daily_pnl,
so there is no stack-level result — toggling a strategy off never re-runs anything.

Python strategies only: summing daily P&L models a portfolio of independent sleeves, and the
NT8/MT5 runners have their own single-window terminals a lab stack has no reason to touch.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Response

from models import (
    StackRequest, StackResponse, StackSummary, StackDetail, StackStrategyLeg,
    StackPreviewRequest, StackPreviewResponse, StackPreviewLeg,
)
from services import chart_spec, lab_db, history_limits
from services.sweep_runner import run_sweep

_LAB_RESULTS_DIR = Path(__file__).parent.parent / "reports" / "lab"

router = APIRouter(prefix="/backtests", tags=["stacks"])


def _load_json(path: Optional[str]) -> list:
    if not path:
        return []
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return []


@router.get("/stacks", response_model=list[StackSummary])
def list_stacks() -> list[StackSummary]:
    return [StackSummary(**r) for r in lab_db.list_stacks()]


def _validate_stack_strategies(ids: list[str]) -> list[dict]:
    if len(ids) < 2:
        raise HTTPException(400, "A stack needs at least 2 strategies")
    strategies = []
    for sid in ids:
        strat = lab_db.get_strategy(sid)
        if not strat:
            raise HTTPException(404, f"Strategy '{sid}' not found")
        if strat.get("runner") != "python":
            raise HTTPException(409, f"Strategy '{sid}' is not a Python strategy — stacks are Python-only")
        strategies.append(strat)
    return strategies


@router.post("/stacks/preview", response_model=StackPreviewResponse)
def preview_stack(req: StackPreviewRequest) -> StackPreviewResponse:
    """Which legs would be reused from an existing completed run vs re-run fresh, for the
    given shared settings. Pure lookup — runs nothing. Drives the modal's live badges."""
    strategies = _validate_stack_strategies(list(dict.fromkeys(req.strategy_ids)))
    legs: list[StackPreviewLeg] = []
    reuse = 0
    for strat in strategies:
        match = lab_db.find_matching_stack_run(
            strat["id"], req.instrument, req.bar_type, req.bar_value,
            req.start_date, req.end_date, req.commission_per_side, req.slippage_ticks,
        )
        if match:
            reuse += 1
            legs.append(StackPreviewLeg(
                strategy_id=strat["id"], strategy_name=strat.get("name", ""),
                action="reuse", matched_run_id=match["run_id"],
                net_pnl=match.get("net_pnl"), trade_count=match.get("trade_count"),
                profit_factor=match.get("profit_factor"),
            ))
        else:
            legs.append(StackPreviewLeg(
                strategy_id=strat["id"], strategy_name=strat.get("name", ""), action="run",
            ))
    return StackPreviewResponse(legs=legs, reuse_count=reuse, run_count=len(legs) - reuse)


@router.post("/stack", status_code=202, response_model=StackResponse)
async def trigger_stack(req: StackRequest) -> StackResponse:
    ids = list(dict.fromkeys(req.strategy_ids))  # dedupe, keep order
    strategies = _validate_stack_strategies(ids)

    for rid in req.ruleset_ids:
        if not lab_db.get_ruleset(rid):
            raise HTTPException(404, f"Ruleset '{rid}' not found")

    # Broker-history floor. Stacks are python-only and every leg shares one window, so a
    # single check covers the whole stack.
    try:
        history_limits.validate_window(
            req.instrument, req.start_date, req.end_date,
            req.bar_type, req.bar_value, "python")
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    stack_id = "st_" + uuid.uuid4().hex[:10]
    now      = int(time.time())
    run_specs: list[dict] = []   # only the fresh legs actually need running
    job_specs: list[dict] = []
    run_ids:   list[str]  = []

    # Resolve each leg to reuse-or-run FIRST, so we only take the python lock if at least
    # one leg genuinely needs a backtest. An all-reused stack is assembled instantly.
    plan: list[tuple[dict, Optional[dict]]] = []  # (strategy, matched_run|None)
    for strat in strategies:
        match = None
        if not req.params_by_strategy.get(strat["id"]):
            # Only reuse when the caller isn't forcing a custom param set for this leg —
            # a custom override means "run it my way", not "reuse whatever exists".
            match = lab_db.find_matching_stack_run(
                strat["id"], req.instrument, req.bar_type, req.bar_value,
                req.start_date, req.end_date, req.commission_per_side, req.slippage_ticks,
            )
        plan.append((strat, match))

    needs_run = any(match is None for _strat, match in plan)
    if needs_run and lab_db.has_running_job("python"):
        raise HTTPException(409, "A Python job is already running — wait for it to finish")

    lab_db.insert_stack({
        "stack_id":            stack_id,
        "instrument":          req.instrument,
        "bar_type":            req.bar_type,
        "bar_value":           req.bar_value,
        "start_date":          req.start_date,
        "end_date":            req.end_date,
        "commission_per_side": req.commission_per_side,
        "slippage_ticks":      req.slippage_ticks,
        "created_at":          now,
    })

    for pos, (strat, match) in enumerate(plan):
        if match:
            # Reuse an existing standalone run as-is — no new row, no re-run.
            lab_db.add_stack_member(stack_id, match["run_id"], owned=0, position=pos)
            run_ids.append(match["run_id"])
            continue

        # Fresh leg — create an owned child run and queue it.
        run_id = uuid.uuid4().hex[:12]
        run_ids.append(run_id)
        params = req.params_by_strategy.get(strat["id"]) or strat.get("default_params") or {}

        lab_db.insert_run_stack({
            "run_id":             run_id,
            "strategy_id":        strat["id"],
            "instrument":         req.instrument,
            "params":             params,
            "bar_type":           req.bar_type,
            "bar_value":          req.bar_value,
            "start_date":         req.start_date,
            "end_date":           req.end_date,
            "commission_per_side": req.commission_per_side,
            "slippage_ticks":     req.slippage_ticks,
            "status":             "running",
            "created_at":         now,
            "stack_id":           stack_id,
            "runner":             "python",
        })
        lab_db.add_stack_member(stack_id, run_id, owned=1, position=pos)

        run_specs.append({
            "run_id":       run_id,
            "job_id":       run_id,
            "strategy_id":  strat["id"],
            "instrument":   req.instrument,
            "ruleset_ids":  req.ruleset_ids,
            "runner":       "python",
        })
        job_specs.append({
            "job_id":            run_id,
            "strategy_class":    strat["class_name"],
            "instrument":        req.instrument,
            "params":            params,
            "bar_type":          req.bar_type,
            "bar_value":         req.bar_value,
            "start_date":        req.start_date,
            "end_date":          req.end_date,
            "commission_per_side": req.commission_per_side,
            "slippage_ticks":    req.slippage_ticks,
        })

    # run_sweep is strategy/instrument-agnostic: it fans the fresh specs out one-at-a-time
    # through a Semaphore(1) and persists each child's equity_curve.json + daily_pnl.json.
    # An all-reused stack has no specs and is already complete on return.
    if run_specs:
        asyncio.create_task(run_sweep(stack_id, run_specs, job_specs))

    status = "started" if run_specs else "complete"
    return StackResponse(stack_id=stack_id, run_ids=run_ids, status=status)


@router.post("/stacks/{stack_id}/cancel", status_code=200)
def cancel_stack(stack_id: str) -> dict:
    rows = lab_db.list_stack_runs(stack_id)
    if not rows:
        raise HTTPException(404, f"Stack '{stack_id}' not found")
    if not any(r["status"] == "running" for r in rows):
        raise HTTPException(400, "No running runs to cancel")
    lab_db.cancel_stack_runs(stack_id)
    return {"stack_id": stack_id, "status": "failed_cancelled"}


@router.delete("/stacks/{stack_id}", status_code=204)
def delete_stack(stack_id: str) -> Response:
    rows = lab_db.list_stack_runs(stack_id)
    if not rows:
        raise HTTPException(404, f"Stack '{stack_id}' not found")
    if any(r["status"] == "running" for r in rows):
        raise HTTPException(409, "Cannot delete a running stack — wait for it to finish first")
    deleted, child_ids = lab_db.delete_stack(stack_id)
    if not deleted:
        raise HTTPException(404, f"Stack '{stack_id}' not found")
    for run_id in child_ids:
        run_dir = _LAB_RESULTS_DIR / run_id
        if run_dir.exists():
            shutil.rmtree(run_dir)
    return Response(status_code=204)


@router.get("/stacks/{stack_id}/chart-spec")
async def get_stack_chart_spec(stack_id: str) -> dict:
    """Merged ChartSpec for the stack's price chart — shared candles + every completed leg's
    trades tagged with `layer` (strategy_id). camelCase (the chart contract) + a `layers` list.
    The candle fetch is heavy, so it runs off-thread like the single-run chart-spec."""
    spec = await asyncio.to_thread(chart_spec.build_stack_chart_spec, stack_id)
    if spec is None:
        raise HTTPException(404, f"No completed runs in stack '{stack_id}' yet")
    return spec


@router.get("/stacks/{stack_id}", response_model=StackDetail)
async def get_stack(stack_id: str) -> StackDetail:
    rows = lab_db.list_stack_runs(stack_id)
    settings = lab_db.get_stack_settings(stack_id)
    if not rows and not settings:
        raise HTTPException(404, f"Stack '{stack_id}' not found")

    # Shared settings are authoritative (a fully-reused stack has them even if a leg row
    # was later deleted); fall back to the first leg for legacy stacks with no settings row.
    first     = settings or (rows[0] if rows else {})
    completed = sum(1 for r in rows if r["status"] == "complete")

    if any(r["status"] == "running" for r in rows):
        status = "running"
    elif all(r["status"] == "complete" for r in rows):
        status = "complete"
    elif all(r["status"].startswith("failed") for r in rows):
        status = "failed_cancelled" if any(r["status"] == "failed_cancelled" for r in rows) else "failed"
    else:
        status = "partial"

    legs = [
        StackStrategyLeg(
            run_id=r["run_id"],
            strategy_id=r["strategy_id"],
            strategy_name=r.get("strategy_name", ""),
            status=r["status"],
            net_pnl=r.get("net_pnl"),
            max_drawdown=r.get("max_drawdown"),
            trade_count=r.get("trade_count"),
            sharpe=r.get("sharpe"),
            avg_trade_duration_min=r.get("avg_trade_duration_min"),
            error_message=r.get("error_message"),
            daily_pnl=_load_json(r.get("daily_pnl_path")),
            equity_curve=_load_json(r.get("equity_curve_path")),
        )
        for r in rows
    ]

    # Full-calendar regime timeline — the same for every leg (market property). Read it from the
    # first complete leg that has one; if none does (Python sweep-child legs aren't regime-tagged),
    # compute it once for the shared window and cache it to that leg's dir so later polls are cheap.
    regime_timeline: list = []
    first_complete = next((r for r in rows if r["status"] == "complete"), None)
    for r in rows:
        if r["status"] != "complete":
            continue
        tl = _load_json(str(_LAB_RESULTS_DIR / r["run_id"] / "regime_timeline.json"))
        if tl:
            regime_timeline = tl
            break
    if not regime_timeline and first_complete is not None and status != "running":
        try:
            from services.backtest_runner import build_regime_timeline_and_tag
            tl, _ = await asyncio.to_thread(
                build_regime_timeline_and_tag,
                first["instrument"], first["start_date"], first["end_date"], [], "python",
            )
            if tl:
                regime_timeline = tl
                cache = _LAB_RESULTS_DIR / first_complete["run_id"] / "regime_timeline.json"
                cache.write_text(json.dumps(tl))
        except Exception:  # noqa: BLE001 — regimes are a nice-to-have overlay, never block the page
            pass

    _created_ts = min((r["created_at"] for r in rows), default=None) or (
        settings["created_at"] if settings else int(time.time())
    )
    created_at = datetime.fromtimestamp(_created_ts, tz=timezone.utc)
    done_ats   = [r["completed_at"] for r in rows if r.get("completed_at")]
    completed_at = (
        datetime.fromtimestamp(max(done_ats), tz=timezone.utc)
        if done_ats and status not in ("running", "partial") else None
    )

    return StackDetail(
        stack_id=stack_id,
        instrument=first["instrument"],
        start_date=first["start_date"],
        end_date=first["end_date"],
        bar_type=first["bar_type"],
        bar_value=first["bar_value"],
        commission_per_side=(settings or first).get("commission_per_side", 0.0) or 0.0,
        slippage_ticks=(settings or first).get("slippage_ticks", 0) or 0,
        total_strategies=len(rows),
        completed_strategies=completed,
        status=status,
        created_at=created_at,
        completed_at=completed_at,
        regime_timeline=regime_timeline,
        strategies=legs,
    )
