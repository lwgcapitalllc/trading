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
    StackContentionEvent,
    StackDetail,
    StackLegContention,
    StackPreviewLeg,
    StackPreviewRequest,
    StackPreviewResponse,
    StackRequest,
    StackResponse,
    StackSharedReport,
    StackStrategyLeg,
    StackSummary,
)
from services import chart_spec, history_limits, lab_db, portfolio_runner
from services.sweep_runner import run_sweep

from routers import _costs

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


def _validate_stack_strategies(ids: list[str], *, extra_legs: int = 0) -> list[dict]:
    # 🔴 THE MINIMUM IS TWO **LEGS**, NOT TWO STRATEGIES, AND THE DIFFERENCE IS THE WHOLE POINT OF
    # THE RECOVERY LEG. A+ plus a recovery on A+ is one strategy id and two legs competing for one
    # balance — the exact stack the leg was built to make possible — and counting ids refused it
    # with a message about strategies that named nothing the reader could act on. `extra_legs` is
    # what the caller adds for legs that are not strategies of their own.
    if len(ids) + extra_legs < 2:
        raise HTTPException(
            400,
            "A stack needs at least 2 legs — pick another strategy, or tick loss recovery "
            "under the one you have.",
        )
    strategies = []
    for sid in ids:
        strat = lab_db.get_strategy(sid)
        if not strat:
            raise HTTPException(404, f"Strategy '{sid}' not found")
        if strat.get("runner") != "python":
            raise HTTPException(
                409, f"Strategy '{sid}' is not a Python strategy — stacks are Python-only"
            )
        strategies.append(strat)
    return strategies


def _leg_bar_value(req, strategy_id: str) -> int:
    """The frame THIS leg runs on: its own if the caller named one, else the stack's.

    🔴 Until 2026-09-03 there was no per-leg answer and every leg ran on the stack's ONE frame.
    That is not a display fault: `extreme_leg` is measured on 5m and `sos_fade` on 15m,
    so stacking them replayed one of the two on a frame nobody has ever measured it on, and the
    combined table read as a portfolio result. The form declares each leg's frame now; this is
    the one place that resolves it, so the history check, the reuse lookup, the stored row and
    the runner cannot disagree about what a leg was measured on.

    ⚠ A DEPENDENT leg never comes through here — see `_recovery_bar_value`.
    """
    return int(req.bar_values_by_strategy.get(strategy_id, req.bar_value))


def _run_instrument(req) -> str:
    """The symbol this stack must actually ask the broker for.

    🔴 The single-run path has resolved the typed name against the broker since 2026-08-26 and
    the stack path never did, so a stack under PU Prime asked for `XAUUSD` — a symbol that
    broker does not quote — and died four layers down in the bar loader with a message naming
    the window and the timeframe and never the field that was wrong. Same function, not a second
    copy: one implementation is why the lab and the live side cannot drift about what gold is
    called.

    ⚠ Resolved at CREATION and the RESOLVED name is what is stored (rule 3) — a row holding the
    typed name while the runner replayed another symbol is a row nothing can audit, and it
    breaks the rerun the moment the two disagree.
    ⚠ A broker whose naming was never recorded leaves the symbol exactly as typed.
    """
    from services import python_runner

    return python_runner.run_symbol(req.instrument, req.broker_profile)


@router.post("/stacks/preview", response_model=StackPreviewResponse)
def preview_stack(req: StackPreviewRequest) -> StackPreviewResponse:
    """Which legs would be reused from an existing completed run vs re-run fresh, for the
    given shared settings. Pure lookup — runs nothing. Drives the modal's live badges."""
    strategies = _validate_stack_strategies(list(dict.fromkeys(req.strategy_ids)))
    # Resolved the SAME way `trigger_stack` resolves it — the basis is part of the reuse
    # identity, so a preview that resolved it differently would promise a reuse the launch
    # cannot honour. That now covers the SYMBOL as well as the costs: a preview asking about a
    # bare name while the launch stores the broker's suffixed one badges every leg "run" and
    # then reuses, or the reverse, and either way the badge is describing a different stack.
    instrument = _run_instrument(req)
    cost_layers, commission_per_side = _costs.resolve_costs(
        runner="python",
        charge_costs=req.charge_costs,
        broker_profile=req.broker_profile,
        cost_layers=req.cost_layers,
        commission_per_side=req.commission_per_side,
        slippage_ticks=req.slippage_ticks,
        # EVERY leg, not the first: the spread's model is a property of the whole stack, and one
        # leg that cannot move fills drags them all onto the flat charge. Legs on one account
        # measured under two fill models is not a portfolio, it is two experiments added up.
        strategies=strategies,
    )
    legs: list[StackPreviewLeg] = []
    reuse = 0
    for strat in strategies:
        # Two independent reasons a leg cannot be reused, and BOTH have to be mirrored from
        # `trigger_stack` or the badge promises something the launch will not do: a shared stack
        # reuses nothing at all, and a per-strategy param override means "run it my way".
        forced = bool(req.params_by_strategy.get(strat["id"]))
        match = (
            None
            if (req.mode == "shared" or forced)
            else lab_db.find_matching_stack_run(
                strat["id"],
                instrument,
                req.bar_type,
                _leg_bar_value(req, strat["id"]),
                req.start_date,
                req.end_date,
                commission_per_side,
                req.slippage_ticks,
                cost_layers,
                req.broker_profile,
            )
        )
        if match:
            reuse += 1
            legs.append(
                StackPreviewLeg(
                    strategy_id=strat["id"],
                    strategy_name=strat.get("name", ""),
                    action="reuse",
                    matched_run_id=match["run_id"],
                    net_pnl=match.get("net_pnl"),
                    trade_count=match.get("trade_count"),
                    profit_factor=match.get("profit_factor"),
                )
            )
        else:
            legs.append(
                StackPreviewLeg(
                    strategy_id=strat["id"],
                    strategy_name=strat.get("name", ""),
                    action="run",
                )
            )
    return StackPreviewResponse(legs=legs, reuse_count=reuse, run_count=len(legs) - reuse)


@router.post("/stack", status_code=202, response_model=StackResponse)
async def trigger_stack(req: StackRequest) -> StackResponse:
    ids = list(dict.fromkeys(req.strategy_ids))  # dedupe, keep order
    # The recovery leg is counted BEFORE its own validation so a one-strategy stack carrying one
    # is not turned away by the leg count it satisfies. `_validate_recovery_leg` is still what
    # decides whether the recovery itself is legal (parent in the stack, shared mode, and so on).
    strategies = _validate_stack_strategies(ids, extra_legs=1 if req.recovery_parent else 0)
    _validate_recovery_leg(req, ids)

    for rid in req.ruleset_ids:
        if not lab_db.get_ruleset(rid):
            raise HTTPException(404, f"Ruleset '{rid}' not found")

    # The symbol the BROKER quotes, resolved before anything is checked or stored — the floor
    # check below is per broker and per symbol, so asking it about the typed name would clear a
    # window for a symbol this stack is never going to load.
    instrument = _run_instrument(req)

    # Broker-history floor. Stacks are python-only and every leg shares one WINDOW — but not its
    # params and, since 2026-09-03, not its FRAME either, and both decide which bar feeds a leg
    # loads (`run_feeds`). So the check is per LEG: one leg with `exec_secondary` on needs 1m
    # history the others do not, a 5m leg's history is shallower than a 15m leg's, and the window
    # is only legal if EVERY leg can be served.
    #
    # 🔴 **This is what makes the legal start the LATEST floor across the frames, and it is not a
    # tidiness point.** A window the fine frame cannot reach but the coarse one can does not
    # error — it answers a different question: the 15m leg compounds ALONE over the months the 5m
    # leg does not exist for, and every later trade of BOTH is then sized off a balance one leg
    # built unopposed. The refusal names the frame that cannot serve it.
    for _strat, _leg_params in zip(strategies, _leg_param_sets(req, strategies)):
        try:
            history_limits.validate_window(
                instrument,
                req.start_date,
                req.end_date,
                req.bar_type,
                _leg_bar_value(req, _strat["id"]),
                "python",
                params=_leg_params,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    stack_id = "st_" + uuid.uuid4().hex[:10]
    now = int(time.time())

    # 🔴 What this stack is CHARGED, resolved ONCE and BEFORE the mode branch. Both modes must
    # get the identical answer: a screen and a shared run over the same legs measured on
    # different physics would make the delta column report the cost gap as the risk cap's doing,
    # which is the one comparison this whole page exists to make.
    cost_layers, commission_per_side = _costs.resolve_costs(
        runner="python",
        charge_costs=req.charge_costs,
        broker_profile=req.broker_profile,
        cost_layers=req.cost_layers,
        commission_per_side=req.commission_per_side,
        slippage_ticks=req.slippage_ticks,
        # EVERY leg, not the first: the spread's model is a property of the whole stack, and one
        # leg that cannot move fills drags them all onto the flat charge. Legs on one account
        # measured under two fill models is not a portfolio, it is two experiments added up.
        strategies=strategies,
    )

    if req.mode == "shared":
        return _trigger_shared_stack(
            req, strategies, stack_id, now, cost_layers, commission_per_side, instrument
        )

    run_specs: list[dict] = []  # only the fresh legs actually need running
    job_specs: list[dict] = []
    run_ids: list[str] = []

    # Resolve each leg to reuse-or-run FIRST, so we only take the python lock if at least
    # one leg genuinely needs a backtest. An all-reused stack is assembled instantly.
    plan: list[tuple[dict, Optional[dict]]] = []  # (strategy, matched_run|None)
    for strat in strategies:
        match = None
        if not req.params_by_strategy.get(strat["id"]):
            # Only reuse when the caller isn't forcing a custom param set for this leg —
            # a custom override means "run it my way", not "reuse whatever exists".
            match = lab_db.find_matching_stack_run(
                strat["id"],
                instrument,
                req.bar_type,
                _leg_bar_value(req, strat["id"]),
                req.start_date,
                req.end_date,
                commission_per_side,
                req.slippage_ticks,
                cost_layers,
                req.broker_profile,
            )
        plan.append((strat, match))

    needs_run = any(match is None for _strat, match in plan)
    if needs_run and lab_db.has_running_job("python"):
        raise HTTPException(409, "A Python job is already running — wait for it to finish")

    lab_db.insert_stack(
        {
            "stack_id": stack_id,
            "instrument": instrument,
            "bar_type": req.bar_type,
            # ⚠ The stack row keeps the stack-level FALLBACK frame; each leg's own frame is on
            # that leg's run row, where every reader of a leg already looks for its window, its
            # costs and its params. One number on the parent describing legs that no longer
            # share it is exactly the shape this app has been bitten by before.
            "bar_value": req.bar_value,
            "start_date": req.start_date,
            "end_date": req.end_date,
            "commission_per_side": commission_per_side,
            "slippage_ticks": req.slippage_ticks,
            "cost_layers": cost_layers,
            "broker_profile": req.broker_profile,
            "created_at": now,
        }
    )

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

        lab_db.insert_run_stack(
            {
                "run_id": run_id,
                "strategy_id": strat["id"],
                "instrument": instrument,
                "params": params,
                "bar_type": req.bar_type,
                "bar_value": _leg_bar_value(req, strat["id"]),
                "start_date": req.start_date,
                "end_date": req.end_date,
                "commission_per_side": commission_per_side,
                "slippage_ticks": req.slippage_ticks,
                "cost_layers": cost_layers,
                "broker_profile": req.broker_profile,
                "status": "running",
                "created_at": now,
                "stack_id": stack_id,
                "runner": "python",
            }
        )
        lab_db.add_stack_member(stack_id, run_id, owned=1, position=pos)

        run_specs.append(
            {
                "run_id": run_id,
                "job_id": run_id,
                "strategy_id": strat["id"],
                "instrument": instrument,
                "ruleset_ids": req.ruleset_ids,
                "runner": "python",
            }
        )
        job_specs.append(
            {
                "job_id": run_id,
                "strategy_class": strat["class_name"],
                "instrument": instrument,
                "params": params,
                "bar_type": req.bar_type,
                "bar_value": _leg_bar_value(req, strat["id"]),
                "start_date": req.start_date,
                "end_date": req.end_date,
                "commission_per_side": commission_per_side,
                "slippage_ticks": req.slippage_ticks,
                "cost_layers": cost_layers,
                "broker_profile": req.broker_profile,
            }
        )

    # run_sweep is strategy/instrument-agnostic: it fans the fresh specs out one-at-a-time
    # through a Semaphore(1) and persists each child's equity_curve.json + daily_pnl.json.
    # An all-reused stack has no specs and is already complete on return.
    if run_specs:
        asyncio.create_task(run_sweep(stack_id, run_specs, job_specs))

    status = "started" if run_specs else "complete"
    return StackResponse(stack_id=stack_id, run_ids=run_ids, status=status)


# The registered id of the loss-recovery rule. It is a strategy ROW so a leg run can reference
# it (and carry its own params, KPIs and chart), and it is flagged `requires_source` so no picker
# offers it — the only thing that may create one is the tick box on a parent.
_RECOVERY_ID = "loss_recovery"


def _validate_recovery_leg(req: StackRequest, ids: list[str]) -> None:
    """Refuse every recovery request the runner could not honestly answer.

    Each of these is silent or late if it is not caught here:

    * **On a SCREEN** every leg has its own full account, so a recovery leg could never take room
      off its parent — which is the whole question. It would produce a plausible page answering
      something nobody asked.
    * **A parent not in the stack** leaves the leg reading nothing: an empty book, which is
      indistinguishable from a rule that found no setups.
    * **A parent that is itself a dependent** is the chain `run_stack` refuses, caught here so the
      refusal arrives before the replay rather than four minutes into it.
    * **Picking the rule as an ordinary leg** is refused with the tick box named, because
      `requires_source` means it cannot run alone and the message has to say what to do instead.
    """
    if _RECOVERY_ID in ids:
        raise HTTPException(
            400,
            "Loss recovery cannot be stacked as a strategy of its own — it has no setups and "
            "arms off another leg's losses. Add it by attaching it to the leg whose losses it "
            "should recover (recovery_parent), not by listing it in strategy_ids.",
        )
    if not req.recovery_parent:
        if req.recovery_params:
            raise HTTPException(
                400,
                "recovery_params were sent with no recovery_parent — nothing would read them. "
                "Name the leg whose losses the recovery should follow.",
            )
        return
    if req.mode != "shared":
        raise HTTPException(
            400,
            "A loss-recovery leg only means something on a SHARED stack. On a screen every leg "
            "trades its own full account, so the recovery could never take room off its parent — "
            "which is the only question it exists to answer.",
        )
    if req.recovery_parent not in ids:
        raise HTTPException(
            400,
            f"recovery_parent '{req.recovery_parent}' is not one of this stack's strategies "
            f"({', '.join(ids) or 'none'}). It would read nothing and return an empty book, "
            f"which looks exactly like a rule that found no setups.",
        )


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
# ⚠ `exec_recovery` joins it for a DIFFERENT reason and the difference is worth stating. The
# 1-minute re-entry is structurally unrunnable here; the recovery switch is merely INERT — it runs
# from a `finalize` hook the simulator never calls, so the leg would come back with its recovery
# trades silently missing. Pinned rather than refused so the stack still runs, and STORED as pinned
# so the leg's own row says the switch was overridden. The way to get a recovery leg in a stack is
# `recovery_parent`, which competes for the budget; the switch cannot, by construction.
_SHARED_LEG_PINS = {"exec_secondary": False, "exec_recovery": False}


def _pin_for_shared(params: dict) -> dict:
    return {**params, **{k: v for k, v in _SHARED_LEG_PINS.items() if k in params}}


def _leg_param_sets(req: StackRequest, strategies: list[dict]) -> list[dict]:
    """What each leg will actually RUN with — the same resolution both trigger paths use.

    Built for the history-floor check, which has to know each leg's feeds. It must mirror how
    the legs are really built or the check bounds a stack nobody is going to run:

    * the request's per-strategy override wins, else the strategy's stored defaults — the same
      order `_resolve_leg` and `_trigger_shared_stack` apply;
    * a SHARED stack pins `_SHARED_LEG_PINS` on top, so it is not refused for a feed that path
      switches off anyway. Skipping the pin here would refuse a shared stack whose legs default
      `exec_secondary` on — legal, because that path never loads the secondary feed.
    """
    out = []
    for strat in strategies:
        params = dict(req.params_by_strategy.get(strat["id"]) or strat.get("default_params") or {})
        out.append(_pin_for_shared(params) if req.mode == "shared" else params)
    return out


def _trigger_shared_stack(
    req: StackRequest,
    strategies: list[dict],
    stack_id: str,
    now: int,
    cost_layers: list[str] | None,
    commission_per_side: float,
    instrument: str,
) -> StackResponse:
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

    lab_db.insert_stack(
        {
            "stack_id": stack_id,
            "instrument": instrument,
            "bar_type": req.bar_type,
            # The stack-level FALLBACK frame — see the screen path's copy of this note.
            "bar_value": req.bar_value,
            "start_date": req.start_date,
            "end_date": req.end_date,
            "commission_per_side": commission_per_side,
            "slippage_ticks": req.slippage_ticks,
            "cost_layers": cost_layers,
            "broker_profile": req.broker_profile,
            "created_at": now,
            "mode": "shared",
            "account_size": req.account_size,
            "risk_cap_pct": req.risk_cap_pct,
            "entry_floor_pct": req.entry_floor_pct,
        }
    )

    legs: list[dict] = []
    run_ids: list[str] = []
    for pos, strat in enumerate(strategies):
        run_id = uuid.uuid4().hex[:12]
        run_ids.append(run_id)
        params = dict(req.params_by_strategy.get(strat["id"]) or strat.get("default_params") or {})
        params = _pin_for_shared(params)
        lab_db.insert_run_stack(
            {
                "run_id": run_id,
                "strategy_id": strat["id"],
                "instrument": instrument,
                "params": params,
                "bar_type": req.bar_type,
                "bar_value": _leg_bar_value(req, strat["id"]),
                "start_date": req.start_date,
                "end_date": req.end_date,
                "commission_per_side": commission_per_side,
                "slippage_ticks": req.slippage_ticks,
                "cost_layers": cost_layers,
                "broker_profile": req.broker_profile,
                "status": "running",
                "created_at": now,
                "stack_id": stack_id,
                "runner": "python",
            }
        )
        lab_db.add_stack_member(stack_id, run_id, owned=1, position=pos)
        legs.append(
            {
                "run_id": run_id,
                "strategy_id": strat["id"],
                "class_name": strat["class_name"],
                "params": params,
                "ruleset_ids": req.ruleset_ids,
                # 🔴 THE LEG CARRIES ITS OWN FRAME, and the runner loads one bar set per distinct
                # value rather than one for the stack. The merged clock has always allowed it —
                # a 5m leg steps three times inside a 15m leg's bar — and this app was the half
                # that could only load one.
                "bar_value": _leg_bar_value(req, strat["id"]),
            }
        )

    # The loss-recovery leg, if one was asked for. It goes on the END so its parent is already
    # in `legs` — `run_stack` orders sources first anyway, but a reader of this list should see
    # the dependency the way it is built.
    if req.recovery_parent:
        rec_run_id = uuid.uuid4().hex[:12]
        run_ids.append(rec_run_id)
        rec_params = dict(req.recovery_params or {})
        # 🔴 PINNED TO THE PARENT'S FRAME, never read from the request. This leg has no setups
        # of its own: it arms off the parent's CLOSED trades and counts its wait in the parent's
        # bars, so a frame of its own would be a rule measuring a different clock from the book
        # it reads. Nothing would raise — it would arm, trade, and land in the table smaller.
        rec_bar_value = _leg_bar_value(req, req.recovery_parent)
        lab_db.insert_run_stack(
            {
                "run_id": rec_run_id,
                "strategy_id": _RECOVERY_ID,
                "instrument": instrument,
                "params": rec_params,
                "bar_type": req.bar_type,
                "bar_value": rec_bar_value,
                "start_date": req.start_date,
                "end_date": req.end_date,
                "commission_per_side": commission_per_side,
                "slippage_ticks": req.slippage_ticks,
                "cost_layers": cost_layers,
                "broker_profile": req.broker_profile,
                "status": "running",
                "created_at": now,
                "stack_id": stack_id,
                "runner": "python",
            }
        )
        lab_db.add_stack_member(stack_id, rec_run_id, owned=1, position=len(legs))
        legs.append(
            {
                "run_id": rec_run_id,
                "strategy_id": _RECOVERY_ID,
                "class_name": "RecoveryLeg",
                "params": rec_params,
                "ruleset_ids": req.ruleset_ids,
                "bar_value": rec_bar_value,
                # The ONE field that makes this a dependent leg rather than a strategy.
                "source": req.recovery_parent,
            }
        )

    # ✅ `cost_layers` / `broker_profile` ARE carried since 2026-09-02, and both modes resolve
    # them from the ONE call in `trigger_stack` — which is what the previous note here asked for.
    # Before that a stack fell into the legacy commission/slippage branch of
    # `python_runner._cost_profile` and charged only what had been typed into the form, which
    # defaults to zero: **every stack in this app before that date is GROSS while its page shows
    # a cost row.** ⚠ Those stored stacks are NOT re-priced — their rows keep the NULL that
    # honestly says they predate the columns; re-run one to charge it.
    portfolio_runner.launch(
        stack_id,
        legs,
        {
            "instrument": instrument,
            "bar_type": req.bar_type,
            # The FALLBACK only — a leg with no frame of its own falls back to this. Each leg
            # carries its own above, and the runner loads a bar set per distinct frame.
            "bar_value": req.bar_value,
            "start_date": req.start_date,
            "end_date": req.end_date,
            "commission_per_side": commission_per_side,
            "slippage_ticks": req.slippage_ticks,
            "cost_layers": cost_layers,
            "broker_profile": req.broker_profile,
            "account_size": req.account_size,
            "risk_cap_pct": req.risk_cap_pct,
            "entry_floor_pct": req.entry_floor_pct,
        },
    )
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
            first["instrument"],
            first["start_date"],
            first["end_date"],
            [],
            "python",
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
    first = settings or (rows[0] if rows else {})
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
    first = settings or (rows[0] if rows else {})
    completed = sum(1 for r in rows if r["status"] == "complete")

    if any(r["status"] == "running" for r in rows):
        status = "running"
    elif all(r["status"] == "complete" for r in rows):
        status = "complete"
    elif all(r["status"].startswith("failed") for r in rows):
        status = (
            "failed_cancelled" if any(r["status"] == "failed_cancelled" for r in rows) else "failed"
        )
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
            # What this leg was replayed on. Legs no longer share the stack's frame, so this is
            # the only honest source for it, and a rerun reads it rather than the stack row.
            bar_value=r.get("bar_value"),
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
    has_regime_timeline = (
        bool(_cached_tl)
        if _tl_cached
        else (status != "running" and any(r["status"] == "complete" for r in rows))
    )

    _created_ts = min((r["created_at"] for r in rows), default=None) or (
        settings["created_at"] if settings else int(time.time())
    )
    created_at = datetime.fromtimestamp(_created_ts, tz=timezone.utc)
    done_ats = [r["completed_at"] for r in rows if r.get("completed_at")]
    completed_at = (
        datetime.fromtimestamp(max(done_ats), tz=timezone.utc)
        if done_ats and status not in ("running", "partial")
        else None
    )

    return StackDetail(
        stack_id=stack_id,
        instrument=first["instrument"],
        start_date=first["start_date"],
        end_date=first["end_date"],
        bar_type=first["bar_type"],
        # 🔴 THE STACK-LEVEL FALLBACK, off the settings row — NOT the first leg's frame. Since
        # 2026-09-03 the legs may each run on their own, so reading `first` would take one leg's
        # frame and print it as the whole stack's, which is the exact shape this app has been
        # bitten by: a number on the parent describing children that no longer share it. Each
        # leg reports its own (`StackStrategyLeg.bar_value`) and the page reads those.
        # ⚠ `first` remains the fallback for a stack stored before the settings row existed,
        # where every leg genuinely did share one frame.
        bar_value=(settings or first).get("bar_value") or first["bar_value"],
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
