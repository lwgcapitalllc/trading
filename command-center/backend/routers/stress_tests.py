"""
Stress Tests router — /stress-tests/*
"""

from __future__ import annotations

import asyncio
import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from models import StressShiftBook, StressTest, StressTestCreate, StressTestDetail
from services import gradable, lab_db, stress_tester
from services.backtest_runner import LAB_RESULTS_DIR
from services.stress_tester import (
    MIN_TRADES_FOR_STRESS,
    _estimate_sens_duration_min,
    _estimate_wf_duration_min,
    phases_requested,
    run_stress_test_task,
    sensitivity_param_count,
    sensitivity_shift_count,
    stack_sensitivity_preview,
    walk_forward_feasibility,
)

router = APIRouter(prefix="/stress-tests", tags=["stress-tests"])


@router.get("", response_model=list[StressTest])
def list_stress_tests(
    run_id: Optional[str] = None, grade: Optional[str] = None, stack_id: Optional[str] = None
):
    return lab_db.list_stress_tests(run_id=run_id, grade=grade, stack_id=stack_id)


@router.get("/running-lock")
def running_stress_lock():
    return lab_db.running_stress_test_markets()


@router.get("/strategy-grades")
def strategy_best_grades():
    return lab_db.best_grades_by_strategy()


@router.get("/gradable")
def can_be_stress_tested(run_id: Optional[str] = None, stack_id: Optional[str] = None):
    """Can this run or stack be stress tested, and if not, why — WITHOUT starting anything.

    🔴 **It exists because a refusal that only arrives after the click is a refusal in the wrong
    place.** Promoting a stack was offered on stacks that cannot be graded, and the screen had no
    way to know: the stack reported 272 combined trades and its contention data as available, so
    every check the page could make PASSED. What was missing was the combined account book on
    disk, which only this process can see. The reader clicked, waited, and got a 400.

    🔴 **IT CALLS `gradable.resolve` RATHER THAN RE-ASKING ITS QUESTIONS, and that is the whole
    design.** A second copy of *"is this gradable"* is two answers about the same stack, and the
    one the button reads would be the one nobody kept up to date — the exact shape of defect this
    repo names as a label being a claim about code somewhere else. Every reason returned here is
    the reason the run endpoint would itself raise, produced by the same lines.

    ⚠ **Read-only and free.** It resolves the target and throws it away; nothing is written, no
    replay starts, and it is safe to call on every render.

    ⚠ **It takes a run OR a stack** because the resolver does. The single-run flow has the same
    class of precondition (no equity curve, run not complete) and would otherwise grow its own
    private copy of this check later.
    """
    try:
        target = gradable.resolve(run_id=run_id, stack_id=stack_id)
    except gradable.NotGradable as exc:
        # NOT an HTTP error: "cannot be graded" is this endpoint's ANSWER, and raising would make
        # a page asking a legitimate question look broken in the console.
        return {"gradable": False, "reason": exc.reason, "trade_count": None}
    return {"gradable": True, "reason": None, "trade_count": target.trade_count}


@router.get("/{stress_test_id}/shift-book/{slug}", response_model=StressShiftBook)
def get_stress_shift_book(stress_test_id: str, slug: str):
    """The combined ACCOUNT book one sensitivity shift produced, so a stack shift can be opened.

    🔴 **A stack shift has no run row and must not be given one.** A single run's shift IS a
    backtest and gets a child row somebody can navigate to; a stack's shift is a function call in
    this process, and manufacturing a run row for it would put a backtest in the Runs lineage that
    nobody launched — naming one strategy as the subject of an account's result, which is the
    mistake the nullable `run_id` on the stress test exists to prevent. The BOOK is stored
    instead, and this is how it is read.

    ⚠ **Pass `__baseline__` for the run every shift is scored against**, replayed by the same
    phase through the same path. A shift's number is a RATIO against it, so a reader holding only
    the shift is holding half a measurement.

    ⚠ **404 means NOT STORED**, which covers a phase that predates this, a write that failed, and
    a slug that names nothing. It is deliberately not an empty book: an account that traded
    nothing and a book nobody kept are different answers.
    """
    if not lab_db.get_stress_test(stress_test_id):
        raise HTTPException(404, "Stress test not found")
    book = stress_tester.read_shift_book(stress_test_id, slug)
    if book is None:
        raise HTTPException(
            404,
            f"No stored book for {slug!r}. Only a STACK's sensitivity shifts keep one, and only "
            f"since 2026-09-07 — a single run's shift is a child backtest you can open directly.",
        )
    return StressShiftBook(
        stress_test_id=stress_test_id,
        slug=slug,
        equity_curve=book["equity_curve"],
        daily_pnl=book["daily_pnl"],
        kpis=book["kpis"],
    )


@router.get("/{stress_test_id}", response_model=StressTestDetail)
def get_stress_test(stress_test_id: str):
    st = lab_db.get_stress_test(stress_test_id)
    if not st:
        raise HTTPException(404, "Stress test not found")

    # Load heavy files from disk. A file that is PRESENT and unreadable is a different fact from a
    # file that was never written, and both used to arrive as `None` — so a corrupt result rendered
    # as a test that simply had no chart. `results_error` names it.
    equity_paths = None
    distribution = None
    errors: list[str] = []

    def _load(path_key: str, label: str):
        raw = st.get(path_key)
        if not raw:
            return None
        p = Path(raw)
        if not p.exists():
            errors.append(f"{label} file is missing from disk")
            return None
        try:
            return json.loads(p.read_text())
        except Exception as exc:
            errors.append(f"{label} file could not be read ({type(exc).__name__})")
            return None

    equity_paths = _load("equity_paths_path", "Simulated equity paths")
    distribution = _load("distribution_path", "Drawdown distribution")

    return {
        **st,
        "equity_paths": equity_paths,
        "distribution": distribution,
        "results_error": "; ".join(errors) or None,
    }


@router.post("/run", status_code=202)
async def trigger_stress_test(body: StressTestCreate):
    # 🔴 ONE resolver decides what is being graded, and the background task asks the SAME one.
    # Two places answering that independently is how a pre-flight and a run come to disagree
    # about what they are looking at — `run_feeds.py` exists because of exactly that, one layer
    # down. `NotGradable` carries its own status code, because only the resolver knows whether
    # it just decided *no such stack* or *this stack is a screen*.
    try:
        target = gradable.resolve(run_id=body.run_id, stack_id=body.stack_id)
    except gradable.NotGradable as exc:
        raise HTTPException(exc.status, exc.reason) from exc

    # 🔴 A STACK'S SETTING NUDGES RUN ONLY WHEN ITS BOTS CAN COMPETE FOR RISK (Aaron's call,
    # 2026-09-10). Otherwise a nudge to one bot moves only that bot's trades, which its own stress
    # test already measures — and on the live pairing that phase was ~42 of the test's minutes.
    # Decided HERE, once, so the estimate, the platform check, the recorded phases and the task all
    # read the same answer; the reason is stored on the row so the page and the grade can say why.
    #
    # ⚠ **The request still says `include_sensitivity: true` and the server narrows it.** The
    # evidence (shares, cap, the stack's own cap record) lives here, not in the browser, and a
    # second copy of the rule in the page is the drift this app keeps paying for.
    include_sensitivity = body.include_sensitivity
    sensitivity_skipped: Optional[str] = None
    if target.is_stack and include_sensitivity:
        needed, why = stress_tester.stack_nudges_needed(target.target_id)
        if not needed:
            include_sensitivity = False
            sensitivity_skipped = why

    # ✅ BOTH deep phases are built for a stack now — walk-forward on 2026-09-06, sensitivity on
    # 2026-09-07. Each replays the WHOLE stack on one account rather than picking a leg out of it.
    #
    # ⚠ Both replay IN THIS PROCESS rather than spawning child backtests, so both are refused up
    # front when the stack cannot be REBUILT — a dependent leg's parent is not persisted anywhere,
    # and replaying without it would drop that leg in silence and grade the account one strategy
    # short. Asked here so the answer is a 400 naming the reason rather than a phase that fails
    # ten minutes in.
    if target.is_stack and (body.include_walk_forward or include_sensitivity):
        try:
            gradable.rebuild_legs(target.target_id)
        except gradable.NotGradable as exc:
            raise HTTPException(exc.status, exc.reason) from exc

    # Sample-size gate — one flat floor. Below MIN_TRADES_FOR_STRESS the whole test is blocked:
    # the A-F grade leans on Monte Carlo tail percentiles (worst-1%/worst-5% drawdown) that small
    # samples can't estimate, and walk-forward's IS/OOS windows would be a coin flip. Get more
    # DATA to clear it (longer period, more instruments, smaller timeframe) — not looser params,
    # which just curve-fits the trade count up.
    #
    # ⚠ For a STACK this counts the COMBINED book, which is the point: Aaron's stated design is
    # that sample size arrives at the PORTFOLIO level, so a pair of legs that each trade too
    # rarely to grade alone can clear this floor together. That is the honest reading — it is
    # one account's trade history — and not a way of buying trades by loosening anything.
    trade_count = target.trade_count
    if trade_count < MIN_TRADES_FOR_STRESS:
        raise HTTPException(
            422,
            f"Stress test needs at least {MIN_TRADES_FOR_STRESS} trades to be meaningful — "
            f"this {target.kind} has {trade_count}. Get more trades from more data (longer "
            f"period, more instruments, or a smaller timeframe) before stress testing.",
        )

    if body.ruleset_id:
        rs = lab_db.get_ruleset(body.ruleset_id)
        if not rs:
            raise HTTPException(404, "Ruleset not found")

    run = lab_db.get_run(body.run_id) if body.run_id else None
    # ⚠ Off the RESOLVED target, never looked up again here — the resolver already read it, and
    # two reads of one fact is what this module's own defects have been made of.
    #
    # ⚠ This endpoint deliberately does NOT call `refuse_if_needs_source`, and that is the same
    # decision `_source_guard.py` already records: a stress test acts on a result that ALREADY
    # EXISTS, and no run of a parentless rule can be created once every creation path refuses
    # one. For a STACK the guard would be actively wrong — a stack may legitimately hold a
    # loss-recovery leg, which is the case that leg was built for.
    strategy = target.strategy or None
    runner = target.runner
    # ONE definition of which market a runner belongs to (lab_db.stress_market_for_runner), mirrored
    # by the frontend's `runnerMarket`. Inline, a python run was filed under futures here and read
    # as forex on the page, so its own button never knew it was blocked.
    market = lab_db.stress_market_for_runner(runner)
    locks = lab_db.running_stress_test_markets()
    if locks[market]:
        raise HTTPException(409, f"A {market} stress test is already running")

    if (body.include_walk_forward or include_sensitivity) and lab_db.has_running_job(runner):
        raise HTTPException(
            409,
            f"An {'MT5' if runner == 'mt5' else 'NT8'} job is already running — walk-forward and sensitivity require the platform to be idle",
        )

    st_id = uuid.uuid4().hex[:16]
    lab_db.insert_stress_test(
        {
            "stress_test_id": st_id,
            # ⚠ Written from the RESOLVED target, not from the request body. The resolver has
            # already refused every shape but exactly-one, so this cannot record a row the
            # table's CHECK would reject — and it cannot record a target the resolver did not
            # bless either.
            "run_id": target.target_id if not target.is_stack else None,
            "stack_id": target.target_id if target.is_stack else None,
            "ruleset_id": body.ruleset_id,
            # ⚠ The platform this test HOLDS and what it is grading, in words — both off the
            # resolved target, both written here at creation. The market lock and the list used
            # to join for these through `run_id`, which a stack does not have: a running stack
            # test held no lock and did not appear in the list at all.
            "runner": runner,
            "target_label": target.label,
            "status": "running",
            "created_at": int(time.time()),
            "num_simulations": body.num_simulations,
            "num_bootstrap": body.num_bootstrap,
            "walk_forward_windows": body.walk_forward_windows,
            "phases_requested": phases_requested(body.include_walk_forward, include_sensitivity),
            "sensitivity_skipped": sensitivity_skipped,
        }
    )

    task = asyncio.create_task(
        run_stress_test_task(st_id, body.include_walk_forward, include_sensitivity)
    )
    # Hold a strong reference. `asyncio.create_task` alone does NOT keep one — the loop only holds
    # the task while a callback of its is scheduled, so a long-awaiting background task is
    # collectable and can vanish mid-flight, leaving the row `running` for ever.
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)

    # Build time estimate + warnings for the UI
    est_min = 0
    notes = []
    warnings: list[str] = []
    if body.include_walk_forward and target.is_stack:
        # ⚠ A stack's windows are whole-stack replays run one after another in this process, not
        # small child jobs — the constant below quoted 2 minutes for a measured 4.2 on the live
        # pairing. Measured off this stack's last walk-forward when there is one.
        wf_min = stress_tester.stack_walk_forward_minutes(target.target_id)
        est_min += wf_min
        notes.append(
            f"Walk-forward: ~{wf_min} min ({body.walk_forward_windows * 2} whole-stack replays, "
            f"one after another)"
        )
    elif body.include_walk_forward:
        wf_min = _estimate_wf_duration_min(body.walk_forward_windows, runner)
        est_min += wf_min
        notes.append(f"Walk-forward: ~{wf_min} min ({body.walk_forward_windows * 2} backtests)")
    if body.include_walk_forward:
        # A walk-forward whose windows cannot each hold enough trades is arithmetic, not luck —
        # it is knowable BEFORE 10 backtests run, and it caps the grade at B when it lands. Saying
        # so up front is the difference between an unassessable result and a wasted hour.
        feasible, why = walk_forward_feasibility(trade_count, body.walk_forward_windows)
        if not feasible:
            warnings.append(why)
    if include_sensitivity and target.is_stack:
        # ⚠ A stack's estimate is built by RUNNING THE PLANNER, not by multiplying a param count
        # by a shift count. The plan is already decided — which settings, in which order, and
        # where the replay budget runs out — so quoting anything else here would describe a
        # different experiment from the one about to run.
        preview = stack_sensitivity_preview(target.target_id)
        est_min += preview["minutes"]
        # ⚠ **"one at a time" until 2026-09-09, and it stopped being true when the phase gained a
        # pool.** A note describing the old shape reads as a measurement of the new one.
        notes.append(
            f"Sensitivity: ~{preview['minutes']} min "
            f"({preview['replays']} whole-stack replays plus the baseline, "
            f"{stress_tester._STACK_SENS_WORKERS} at a time)"
        )
        # What the budget could not reach travels WITH the estimate, not only into the record
        # afterwards. A reader who can see it now can drop a leg and re-run; a reader who finds
        # it in the coverage record afterwards has already spent the hour.
        if preview["out_of_budget"]:
            warnings.append(
                f"{len(preview['out_of_budget'])} setting(s) will not be reached inside the "
                f"replay budget and will go unmeasured: "
                f"{', '.join(preview['out_of_budget'][:6])}"
                + ("…" if len(preview["out_of_budget"]) > 6 else "")
            )
    elif include_sensitivity:
        # Count only the params sensitivity actually perturbs (numeric, non-foundational, and
        # REACHABLE — not behind a switch this run has off) and use the runner's real shift count
        # (MT5 = 2, NT8/python = 4) — both via the shared helpers, so the estimate can't drift
        # from the run loop.
        # ⚠ Params come off the RESOLVED target's leg, not off a second read of the run row.
        # For a single run they are the same dict; keeping one source is what stops the
        # estimate describing a different configuration from the one that will be perturbed.
        n_params = sensitivity_param_count(strategy, target.legs[0].params if target.legs else {})
        n_backtests = n_params * sensitivity_shift_count(runner)
        # The RUN is passed so the estimate can use its own measured duration instead of a
        # per-job constant — a 6.6-year replay costs ~69s a child, not the 12s the constant
        # assumes, and the modal was quoting ~12 min for a ~69 min job.
        sens_min = _estimate_sens_duration_min(n_params, runner, run)
        est_min += sens_min
        notes.append(
            f"Sensitivity: at most ~{sens_min} min ({n_backtests} backtests before "
            f"no-op shifts are skipped)"
        )
    if sensitivity_skipped:
        notes.append(f"Setting nudges skipped: {sensitivity_skipped}")

    return {
        "stress_test_id": st_id,
        "status": "running",
        "estimated_duration_min": est_min if est_min else None,
        "notes": notes,
        "warnings": warnings,
    }


# Strong references to fire-and-forget background tasks. See the note at the create_task above.
_BACKGROUND_TASKS: set = set()


@router.post("/{stress_test_id}/cancel")
async def cancel_stress_test(stress_test_id: str) -> dict:
    """Stop a running stress test and its in-flight child backtest.

    ⚠ It reports **`job_stopped`** separately from the cancellation, the same distinction the
    optimizer's cancel makes: the row is cancelled either way, but "the runner acknowledged the
    stop" and "we could not reach the runner to tell it" are different facts, and only the first
    means the platform is actually free again."""
    st = lab_db.get_stress_test(stress_test_id)
    if not st:
        raise HTTPException(404, "Stress test not found")

    children = lab_db.cancel_stress_test(stress_test_id)
    if children is None:
        raise HTTPException(
            409, f"Stress test is '{st['status']}' — only a running test can be cancelled"
        )

    # ⚠ The platform is READ OFF THE ROW, which is where the trigger wrote it. Looking it up
    # through the run meant a stack — which has no run — resolved to NinjaTrader, and a strategy
    # re-scanned onto a different runner mid-test would have been cancelled on the wrong one.
    # The lookup is kept only as a fallback for rows written before that column existed.
    run = lab_db.get_run(st["run_id"]) if st.get("run_id") else None
    strategy = lab_db.get_strategy((run or {}).get("strategy_id", "")) or {}
    runner = st.get("runner") or strategy.get("runner") or "ninjatrader"

    from services import runner_dispatch

    job_stopped = True
    for child_id in children:
        try:
            await asyncio.to_thread(runner_dispatch.cancel_job, child_id, runner)
        except Exception:
            job_stopped = False
    return {
        "stress_test_id": stress_test_id,
        "status": "failed_cancelled",
        "children_cancelled": len(children),
        "job_stopped": job_stopped,
    }


@router.delete("/{stress_test_id}", status_code=204)
def delete_stress_test(stress_test_id: str):
    child_ids = lab_db.delete_stress_test(stress_test_id)
    if child_ids is None:
        raise HTTPException(404, "Stress test not found")
    # The test's own results dir (equity_paths.json + distribution.json) AND every child run's dir.
    # Deleting the rows and leaving the files is how `reports/lab` grew to 191 directories against
    # 84 live runs.
    for d in [LAB_RESULTS_DIR / stress_test_id] + [LAB_RESULTS_DIR / rid for rid in child_ids]:
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
