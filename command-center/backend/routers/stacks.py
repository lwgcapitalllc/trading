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
    StackSharedReport, StackLegContention, StackContentionEvent,
)
from services import chart_spec, lab_db, history_limits, portfolio_runner
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


def _solo_fields(stack_id: str, mode: Optional[str], strategy_id: str) -> dict:
    """The leg's solo-control book, or nothing at all.

    ⚠ A SCREEN gets `None` and that is not a gap: on a screen every leg ALREADY traded its own full
    account, so the leg's own curve IS the solo answer and a second copy of it would be two fields
    holding one fact. Only a SHARED stack has two different books for one leg.

    ⚠ `None` rather than `[]` when a shared stack has no stored book (it ran before 2026-08-10). The
    page refuses to answer there instead of drawing an empty curve — the same *no data is not the
    same as cannot ask* rule `mt5_link` and `grid_sensitivity_score` follow.
    """
    if mode != "shared":
        return {}
    eq, dp = portfolio_runner.solo_book(stack_id, strategy_id)
    if not eq:
        return {}
    return {"solo_equity_curve": eq, "solo_daily_pnl": dp}


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
        # Two independent reasons a leg cannot be reused, and BOTH have to be mirrored from
        # `trigger_stack` or the badge promises something the launch will not do: a shared stack
        # reuses nothing at all, and a per-strategy param override means "run it my way".
        forced = bool(req.params_by_strategy.get(strat["id"]))
        match = None if (req.mode == "shared" or forced) else lab_db.find_matching_stack_run(
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

    if req.mode == "shared":
        return _trigger_shared_stack(req, strategies, stack_id, now)

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


# Settings a leg of a SHARED stack structurally cannot carry, pinned to the value the simulator
# can run. `backtest/portfolio/legs.py::_refuse_unreplayable` is the AUTHORITY — it raises on
# each of these — and this pins them ahead of it so the refusal never has to fire.
#
# ⚠ It is a structural impossibility, not a preference: `exec_secondary` is the 1-minute
# re-entry, it needs a second bar stream through `run_dual`, and a leg on a merged clock is one
# frame. Replaying it single-stream is the dangerous option — the leg comes back primary-only
# while its own solo control and the screen both have the re-entries in them.
#
# ⚠ The pinned params are what gets STORED on the child run, deliberately. Overriding at replay
# time while the row said otherwise is this app's most-repeated defect: a page stating a value
# no code read. Here the row and the replay say the same thing, and the page says it was pinned.
# `tests/test_shared_stack.py` reads `legs.py` and fails if it grows a refusal this misses.
_SHARED_LEG_PINS = {"exec_secondary": False}


def _pin_for_shared(params: dict) -> dict:
    return {**params, **{k: v for k, v in _SHARED_LEG_PINS.items() if k in params}}


def _trigger_shared_stack(req: StackRequest, strategies: list[dict],
                          stack_id: str, now: int) -> StackResponse:
    """One balance, one risk budget, every leg replayed together.

    Deliberately different from the screen path in three ways, each of which would be a defect
    if it were copied across:

    * **No reuse, ever.** A finished standalone run was measured on its own full account with
      nothing able to block it. Dropping one into a shared stack would put an un-contended leg
      beside contended ones and call the pair a portfolio — the reuse optimisation is only
      sound because a screen never claims the legs interacted.
    * **It always takes the python lock**, because there is always work: `run_stack` is
      `1 + len(legs)` full replays (the shared book plus one solo CONTROL per leg).
    * **One job, not N.** The legs share a clock and an account, so they cannot be serialised
      one after another the way `run_sweep` fans out a screen's legs.
    """
    if lab_db.has_running_job("python"):
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
        "mode":                "shared",
        "account_size":        req.account_size,
        "risk_cap_pct":        req.risk_cap_pct,
        "entry_floor_pct":     req.entry_floor_pct,
    })

    legs:    list[dict] = []
    run_ids: list[str]  = []
    for pos, strat in enumerate(strategies):
        run_id = uuid.uuid4().hex[:12]
        run_ids.append(run_id)
        params = dict(req.params_by_strategy.get(strat["id"])
                      or strat.get("default_params") or {})
        params = _pin_for_shared(params)
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
        legs.append({
            "run_id":      run_id,
            "strategy_id": strat["id"],
            "class_name":  strat["class_name"],
            "params":      params,
            "ruleset_ids": req.ruleset_ids,
        })

    # ⚠ No `cost_layers` / `broker_profile` here, and that is the CURRENT state of stacks
    # rather than a decision: the stacks table does not carry those columns, so a stack takes
    # the legacy commission/slippage branch of `python_runner._cost_profile` like every other
    # stack in this app. Wire them before anyone expects a priced shared stack — and wire them
    # for BOTH modes at once, or a screen and a shared run over the same legs would be measured
    # on different physics and the delta column would report the cost gap as the cap's doing.
    portfolio_runner.launch(stack_id, legs, {
        "instrument":          req.instrument,
        "bar_type":            req.bar_type,
        "bar_value":           req.bar_value,
        "start_date":          req.start_date,
        "end_date":            req.end_date,
        "commission_per_side": req.commission_per_side,
        "slippage_ticks":      req.slippage_ticks,
        "account_size":        req.account_size,
        "risk_cap_pct":        req.risk_cap_pct,
        "entry_floor_pct":     req.entry_floor_pct,
    })
    return StackResponse(stack_id=stack_id, run_ids=run_ids, status="started")


@router.get("/stacks/{stack_id}/contention", response_model=StackSharedReport)
def get_stack_contention(stack_id: str) -> StackSharedReport:
    """What the shared risk budget actually did — and, while it is still replaying, how far in.

    ⚠ **`available: false` is not one answer, it is three, and the caller must not collapse
    them**: this stack is a SCREEN (no account exists to contend over), it is still RUNNING, or
    it failed. `progress` separates the second from the others, and `mode` on the detail
    separates the first. An empty `events` list under `available: true` is the opposite of all
    three — a real measurement that nothing was refused.
    """
    settings = lab_db.get_stack_settings(stack_id)
    if not settings and not lab_db.list_stack_runs(stack_id):
        raise HTTPException(404, f"Stack '{stack_id}' not found")

    progress = portfolio_runner.progress_for(stack_id)
    summary = portfolio_runner.read_shared_summary(stack_id)
    if not summary:
        return StackSharedReport(stack_id=stack_id, available=False, progress=progress)

    events = _load_json(str(portfolio_runner.stack_dir(stack_id) / "contention.json"))
    return StackSharedReport(
        stack_id=stack_id,
        available=True,
        opening_balance=summary.get("opening_balance"),
        closing_balance=summary.get("closing_balance"),
        risk_cap_pct=summary.get("risk_cap_pct"),
        entry_floor_pct=summary.get("entry_floor_pct"),
        peak_open_risk_pct=summary.get("peak_open_risk_pct"),
        peak_concurrent_legs=summary.get("peak_concurrent_legs"),
        leg_count=summary.get("leg_count"),
        combined_trades=summary.get("combined_trades"),
        combined_r=summary.get("combined_r"),
        contention_events=summary.get("contention_events"),
        neutral=summary.get("neutral"),
        progress=progress,
        legs=[
            StackLegContention(
                strategy_id=row.get("strategy_id", ""),
                run_id=row.get("run_id", ""),
                shared_trades=row.get("shared_trades", 0),
                shared_r=row.get("shared_r", 0.0),
                solo_trades=row.get("solo_trades", 0),
                solo_r=row.get("solo_r", 0.0),
                solo_closing_balance=row.get("solo_closing_balance", 0.0),
                shrunk=(row.get("contention") or {}).get("shrunk", 0),
                blocked=(row.get("contention") or {}).get("blocked", 0),
                risk_refused=(row.get("contention") or {}).get("risk_refused", 0.0),
            )
            for row in (summary.get("legs") or [])
        ],
        events=[
            StackContentionEvent(
                leg=str(e.get("leg", "")),
                time=int(e["time"]) if e.get("time") is not None else None,
                blocked=bool(e.get("blocked")),
                desired_risk=float(e.get("desired_risk") or 0.0),
                granted_risk=float(e.get("granted_risk") or 0.0),
            )
            for e in events
        ],
    )


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
    # A SHARED stack owns a directory of its own (`contention.json`, `shared_summary.json`),
    # which no child run references — so deleting only the children leaves it behind, and the
    # stress-test audit already measured what that habit costs: 191 directories against 84 live
    # runs. `stack_id` cannot collide with a `run_id` (it is `st_`-prefixed), so this is safe.
    sdir = _LAB_RESULTS_DIR / stack_id
    if sdir.exists():
        shutil.rmtree(sdir)
    return Response(status_code=204)


@router.get("/stacks/{stack_id}/chart-spec")
async def get_stack_chart_spec(stack_id: str, refresh: bool = False) -> dict:
    """Merged ChartSpec for the stack's price chart — shared candles + every completed leg's
    trades tagged with `layer` (strategy_id). camelCase (the chart contract) + a `layers` list.
    The candle fetch is heavy, so it runs off-thread like the single-run chart-spec.

    `refresh=true` rebuilds every leg's own cached spec first — the merge holds no cache of its
    own, so nothing else would change. Same flag, same meaning, as `/runs/{id}/chart-spec`."""
    spec = await asyncio.to_thread(chart_spec.build_stack_chart_spec, stack_id, refresh)
    if spec is None:
        raise HTTPException(404, f"No completed runs in stack '{stack_id}' yet")
    return spec


def _cached_regime_timeline(rows: list[dict]) -> tuple[list, bool]:
    """The regime calendar off a completed leg's cache — `(timeline, a_cache_exists)`.

    ⚠ The two halves answer different questions and a caller needs both. `[]` with
    `cached=True` is a MEASUREMENT ("we classified this window and it has nothing to show");
    `[]` with `cached=False` means nobody has looked yet. Collapsing them is what made every
    poll of this endpoint re-fetch OHLC before 2026-08-10.
    """
    cached = False
    for r in rows:
        if r["status"] != "complete":
            continue
        cache = _LAB_RESULTS_DIR / r["run_id"] / "regime_timeline.json"
        if cache.exists():
            cached = True
            tl = _load_json(str(cache))
            if tl:
                return tl, True
    return [], cached


async def _build_regime_timeline(rows: list[dict], first: dict, status: str) -> list:
    """Read the calendar off a leg's cache, or classify the shared window once and cache it.

    Regime is a property of the MARKET on a date, so it is the same for every leg — but a
    Python sweep-child leg is never regime-tagged, so on most stacks nobody has one and it has
    to be computed here. `[]` is WRITTEN on an empty result, because it is a real answer.
    """
    timeline, cached = _cached_regime_timeline(rows)
    if cached or status == "running":
        return timeline

    first_complete = next((r for r in rows if r["status"] == "complete"), None)
    if first_complete is None:
        return []
    try:
        from services.backtest_runner import build_regime_timeline_and_tag
        tl, _ = await asyncio.to_thread(
            build_regime_timeline_and_tag,
            first["instrument"], first["start_date"], first["end_date"], [], "python",
        )
        timeline = tl or []
        cache = _LAB_RESULTS_DIR / first_complete["run_id"] / "regime_timeline.json"
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(timeline))
    except Exception:  # noqa: BLE001 — regimes are a nice-to-have overlay, never block the page
        pass
    return timeline


@router.get("/stacks/{stack_id}/regime-timeline")
async def get_stack_regime_timeline(stack_id: str) -> dict:
    """The full-calendar regime timeline on its own — the equity chart's regime overlay.

    It is split out because it is the single biggest slice of the stack detail (**96,766 of
    226,036 bytes, 43%, measured on `st_94aeb25f0c`**) and the overlay it feeds defaults OFF,
    so the common page load has no use for it at all. This is also the only path that will
    CLASSIFY a window that has never been classified — `GET /stacks/{id}?timeline=false`
    deliberately will not, since that fetches OHLC for something nobody asked to see.
    """
    rows = lab_db.list_stack_runs(stack_id)
    settings = lab_db.get_stack_settings(stack_id)
    if not rows and not settings:
        raise HTTPException(404, f"Stack '{stack_id}' not found")
    first  = settings or (rows[0] if rows else {})
    status = "running" if any(r["status"] == "running" for r in rows) else "other"
    return {"regime_timeline": await _build_regime_timeline(rows, first, status)}


@router.get("/stacks/{stack_id}", response_model=StackDetail)
async def get_stack(stack_id: str, timeline: bool = True) -> StackDetail:
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
            # `list_stack_runs` already parses this column, so it arrives as a dict. A leg's params
            # are the only record of what the stack PINNED onto it (`_SHARED_LEG_PINS`) and the only
            # thing a rerun can carry forward — see the field's note on the model.
            params=r.get("params") or {},
            daily_pnl=_load_json(r.get("daily_pnl_path")),
            equity_curve=_load_json(r.get("equity_curve_path")),
            # The mode comes off the SETTINGS row, the same source `StackDetail.mode` reads below —
            # a leg row carries no mode, so `first` would answer None on a legacy stack and quietly
            # withhold the solo book from a shared one.
            **_solo_fields(stack_id, (settings or {}).get("mode"), r["strategy_id"]),
        )
        for r in rows
    ]

    # Full-calendar regime timeline — the same for every leg, because regime is a property of the
    # MARKET on a date. It is 43% of this response (96,766 of 226,036 bytes, measured), and the
    # overlay it feeds defaults OFF, so `?timeline=false` drops it and the page fetches it from
    # `/stacks/{id}/regime-timeline` only when the reader switches the overlay on.
    #
    # ⚠ The DEFAULT stays `true`. A caller that says nothing gets the whole run — the same rule
    # `GET /runs/{id}?timeline=false` states, and for the same reason: `[]` on the slim response is
    # indistinguishable from a stack whose window has no regimes, so it is only ever safe for a
    # caller that knows it is asking for the rest of the fields.
    regime_timeline: list = await _build_regime_timeline(rows, first, status) if timeline else []

    # ⚠ Served on BOTH branches, and it is what makes the slim one usable: the page hides the
    # regime toggle when there is nothing to overlay, so without this a slimmed response would
    # remove the CONTROL rather than the payload — the reader could never turn it back on.
    # It never classifies: an uncached window answers from whether one COULD be built.
    _cached_tl, _tl_cached = _cached_regime_timeline(rows)
    has_regime_timeline = bool(_cached_tl) if _tl_cached else (
        status != "running" and any(r["status"] == "complete" for r in rows)
    )

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
        has_regime_timeline=has_regime_timeline,
        strategies=legs,
        mode=(settings or {}).get("mode") or "screen",
        # Served from the settings row and NOT defaulted to a number. A screen has no account —
        # every leg traded a full one — so `None` is the answer, and a `0` here would render as
        # an account with no money rather than as a question that does not apply.
        account_size=(settings or {}).get("account_size"),
        risk_cap_pct=(settings or {}).get("risk_cap_pct"),
        entry_floor_pct=(settings or {}).get("entry_floor_pct"),
    )
