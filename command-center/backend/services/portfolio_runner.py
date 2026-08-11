"""The SHARED-ACCOUNT stack runner — one balance, one risk budget, N bots competing for it.

A stack in this app has always been a SCREEN: each leg was replayed as its own standalone
backtest and the results were added together. That assumes every leg traded a full account and
that no leg ever blocked another, so it is an UPPER BOUND and not a demo result. Aaron's
requirement is the other thing — *"if one bot wants to trade, but there's no risk available to
trade on, it should be blocked by the system"*, and in the backtest the legs must *"share the
equity and react the exact same way they would do in a demo account"*.

This module is the wiring, not the logic. The simulation is `backtest/portfolio/run_stack`,
which is offline, app-agnostic and separately tested; everything here is: build the legs from
lab rows, run it on a thread, and persist what comes back. **It CALLS `run_stack` and must never
grow its own copy** — a second account model is a second answer about what a shared budget does,
and the live allocator already has to be a third implementation (separate OS processes cannot
share an in-process object). Two is the most this rule can afford.

## What is persisted, and why the solo control is half of it

`run_stack` replays each leg SOLO on the same bars as well as together. That control is not a
nicety: a difference in the shared book is otherwise a mixture of *the cap bit* and *the shared
balance re-sized everything*, and nothing afterwards separates them. Both land in
`shared_summary.json` so the page can show the screen-vs-shared delta honestly rather than
inviting the reader to subtract two numbers of different kinds.

⚠ **A leg's own equity curve here is its CONTRIBUTION, not its balance.** It is walked from the
account's opening balance over that leg's own trades, because the real balance path belongs to
the shared account and there is no such thing as "this leg's balance" once the two compound
together. The legs' daily P&L still SUMS to the shared account's, which is what the page
composes the combined line from.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Optional

from services import lab_db, evaluator, worthiness
from services.metrics import apply_canonical_sharpe

_LAB_RESULTS_DIR = Path(__file__).parent.parent / "reports" / "lab"

# Live progress for the stacks currently replaying, keyed by stack_id. In-process and
# deliberately not a file: it drives one progress line and nothing may ever resolve an
# IDENTITY out of it. `lab_progress.json` was read for a job id on 2026-08-06 and a Stop
# cancelled an unrelated platform's job; the rule that came out of it is that a channel built
# to carry a STATUS must never be asked who something is.
_PROGRESS: dict[str, dict] = {}
_PROGRESS_LOCK = threading.Lock()

# How many background tasks we hold a strong reference to. `asyncio.create_task` gives the loop
# only a weak one, so a long-awaiting task is collectable mid-flight and would leave every leg
# `running` for ever — the defect the stress tester had until 2026-08-05.
_BACKGROUND_TASKS: set = set()


def progress_for(stack_id: str) -> Optional[dict]:
    with _PROGRESS_LOCK:
        p = _PROGRESS.get(stack_id)
        return dict(p) if p else None


def _set_progress(stack_id: str, **fields: Any) -> None:
    with _PROGRESS_LOCK:
        _PROGRESS.setdefault(stack_id, {}).update(fields)


def _clear_progress(stack_id: str) -> None:
    with _PROGRESS_LOCK:
        _PROGRESS.pop(stack_id, None)


def stack_dir(stack_id: str) -> Path:
    return _LAB_RESULTS_DIR / stack_id


def read_shared_summary(stack_id: str) -> Optional[dict]:
    """The shared run's own artefact, or None if this stack never produced one.

    ⚠ `None` means NOT A SHARED RUN or NOT FINISHED — never "it contended with nothing". An
    empty contention log is a real and important result (the 6.5-year measured run has one),
    so it must be reachable only through a summary that exists.
    """
    path = stack_dir(stack_id) / "shared_summary.json"
    try:
        return json.loads(path.read_text())
    except Exception:                       # noqa: BLE001 — absent or unreadable, same answer here
        return None


def launch(stack_id: str, legs: list[dict], settings: dict) -> None:
    """Fire the shared replay as a background task, holding a strong reference to it."""
    task = asyncio.create_task(run_shared_stack(stack_id, legs, settings))
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


async def run_shared_stack(stack_id: str, legs: list[dict], settings: dict) -> None:
    """Replay every leg on one account and persist the result.

    `legs` is `[{run_id, strategy_id, class_name, params, ruleset_ids}]` in leg order;
    `settings` carries the shared window, costs and account knobs.
    """
    _set_progress(stack_id, phase="starting", pct=1, message="loading bars…")
    try:
        await asyncio.to_thread(_execute, stack_id, legs, settings)
    except Exception as exc:                # noqa: BLE001 — a background task must not die silently
        detail = f"{exc}"
        for leg in legs:
            lab_db.update_run_status(leg["run_id"], "failed_error", detail)
        _set_progress(stack_id, phase="failed", pct=100, message=detail,
                      error=traceback.format_exc())
    finally:
        # Held for a beat so a poller mid-flight sees the terminal state rather than a gap that
        # reads as "no such stack".
        await asyncio.sleep(0)


def _execute(stack_id: str, legs: list[dict], settings: dict) -> None:
    from backtest.data.source import BarSource
    from backtest.portfolio import LegSpec, contention_summary, run_stack

    from services.python_runner import _build_config, _cost_profile, _resolve, _timeframe_minutes

    symbol = settings["instrument"]
    tf = _timeframe_minutes(settings)

    df = BarSource().load(symbol, tf, settings["start_date"], settings["end_date"])
    if df.empty:
        raise ValueError(f"no bars for {symbol} {tf}m over "
                         f"[{settings['start_date']}, {settings['end_date']}]")

    balance = float(settings["account_size"])
    profile = _cost_profile(settings)

    specs = []
    for leg in legs:
        found = _resolve(leg["class_name"])
        if found is None:
            raise ValueError(f"no Python strategy class named {leg['class_name']!r}")
        _, entry = found
        config = _build_config(entry["config"], leg.get("params") or {}, symbol)
        specs.append(LegSpec(name=leg["strategy_id"], strategy_cls=entry["strategy"],
                             config=config, df=df, cost_profile=profile))

    total_ticks = len(df.index)
    phases = 1 + len(specs)                 # the shared replay, then one solo control per leg
    phase_names = ["shared"] + [f"solo:{s.name}" for s in specs]

    def _progress(phase: str, i: int) -> None:
        try:
            done = phase_names.index(phase)
        except ValueError:
            done = 0
        frac = (done + min(1.0, i / max(1, total_ticks))) / phases
        _set_progress(stack_id, phase=phase, pct=min(97, 3 + int(frac * 94)),
                      message=f"{phase} · bar {i:,} / {total_ticks:,}")

    run = run_stack(specs, balance=balance,
                    risk_cap_pct=float(settings["risk_cap_pct"]) / 100.0,
                    entry_floor_pct=float(settings.get("entry_floor_pct") or 0.0) / 100.0,
                    progress=_progress,
                    should_cancel=lambda: _is_cancelled(stack_id, legs))

    if run.cancelled:
        # Every book here is PARTIAL — it holds the trades closed up to the tick the run
        # stopped on, which is indistinguishable from a complete short backtest once written to
        # disk. Persisting it would be the "cancel did not cancel" defect from the other side:
        # not a run that carried on, but a stopped run recorded as a finished one.
        _set_progress(stack_id, phase="cancelled", pct=100, message="cancelled")
        for leg in legs:
            lab_db.update_run_status(leg["run_id"], "failed_cancelled", "cancelled")
        return

    _set_progress(stack_id, phase="persisting", pct=98, message="writing results…")
    _persist(stack_id, legs, specs, run, settings, contention_summary(run))
    _set_progress(stack_id, phase="complete", pct=100,
                  message=f"{len(run.trades)} trades on one account")


def _is_cancelled(stack_id: str, legs: list[dict]) -> bool:
    """Has somebody pressed Stop? Read off the DB rows, which are the single lock source.

    ⚠ An unreadable row answers False. Carrying on is recoverable — the run finishes and can be
    deleted; abandoning a multi-minute replay because sqlite was momentarily busy is not.
    """
    try:
        for leg in legs:
            row = lab_db.get_run(leg["run_id"])
            if row and str(row.get("status", "")).startswith("failed_cancelled"):
                return True
    except Exception:                       # noqa: BLE001 — see the docstring
        return False
    return False


def _persist(stack_id: str, legs: list[dict], specs: list, run, settings: dict,
             summary: dict) -> None:
    from backtest.output import build_results

    sdir = stack_dir(stack_id)
    sdir.mkdir(parents=True, exist_ok=True)

    by_id = {leg["strategy_id"]: leg for leg in legs}
    point_value = None
    per_leg_rows = []

    for spec in specs:
        leg = by_id[spec.name]
        shared_trades = run.per_leg.get(spec.name, [])
        solo_trades = run.solo_per_leg.get(spec.name, [])
        point_value = getattr(spec.config, "point_value", 1.0)

        results = build_results(shared_trades, point_value=point_value,
                                initial_capital=run.opening_balance)
        _write_leg(leg["run_id"], results, leg.get("ruleset_ids") or [])

        # The SOLO control's own book, kept in full rather than as two scalars. This is the ONLY
        # honest answer to "what would the rest of the stack have made if this strategy never
        # existed", and until 2026-08-10 nothing kept it: `shared_summary.json` stored `solo_r` and
        # `solo_closing_balance` and the trades were discarded.
        #
        # 🔴 Without it, switching a leg off on the stack page recomposed the remaining leg from its
        # SHARED trades — which are sized off a balance the leg it just removed had grown. Measured
        # on `st_94aeb25f0c`: mpc_bleg posts 17.8674R either way, 99 trades, identical entry and stop
        # prices — and $47,758,999 shared against $21,064 alone, because the last trade risks
        # $16,925,791 of a shared balance instead of $3,102 of its own. Same R, 2,266x the dollars.
        # Reported off the screen as "how is it the b leg make forty seven million on the stack, but
        # only twenty one thousand by itself".
        solo_results = build_results(solo_trades, point_value=point_value,
                                     initial_capital=run.opening_balance)
        _write_solo(sdir, spec.name, solo_results)

        per_leg_rows.append({
            "strategy_id": spec.name,
            "run_id": leg["run_id"],
            "shared_trades": len(shared_trades),
            "shared_r": round(sum(getattr(t, "r", 0.0) for t in shared_trades), 4),
            "solo_trades": len(solo_trades),
            "solo_r": round(sum(getattr(t, "r", 0.0) for t in solo_trades), 4),
            "solo_closing_balance": round(run.solo_closing.get(spec.name, 0.0), 2),
            "contention": summary.get(spec.name, {"shrunk": 0, "blocked": 0,
                                                  "risk_refused": 0.0}),
        })

    (sdir / "contention.json").write_text(json.dumps(run.contention, default=str))
    (sdir / "shared_summary.json").write_text(json.dumps({
        "stack_id": stack_id,
        "opening_balance": run.opening_balance,
        "closing_balance": round(run.closing_balance, 2),
        "risk_cap_pct": round(run.risk_cap_pct * 100.0, 4),
        "entry_floor_pct": round(run.entry_floor_pct * 100.0, 4),
        "peak_open_risk_pct": round(run.peak_reserved_pct * 100.0, 4),
        "peak_concurrent_legs": run.peak_concurrent,
        "leg_count": len(specs),
        "combined_trades": len(run.trades),
        "combined_r": round(sum(getattr(t, "r", 0.0) for t in run.trades), 4),
        "contention_events": len(run.contention),
        "legs": per_leg_rows,
        # The one thing this artefact can CHECK rather than report, and it is worth more than
        # the totals. R is normalised to the trade's own risk, so scaling a position does not
        # move it: with nothing refused, a leg must post the SAME R shared as solo. If it does
        # not, the shared account is moving a decision it must not touch — a defect in the
        # seam, not a portfolio effect. Stored so the page can say so out loud instead of
        # leaving a reader to compare two columns and wonder.
        "neutral": _neutrality(run, per_leg_rows),
        "written_at": int(time.time()),
    }, default=str))


def _neutrality(run, rows: list[dict]) -> dict:
    """Did the shared account move a decision it should not have?"""
    if run.contention:
        return {"checkable": False,
                "reason": "the cap bound, so shared and solo are expected to differ — every "
                          "difference should trace to a row in the contention log"}
    drift = [r["strategy_id"] for r in rows if abs(r["shared_r"] - r["solo_r"]) > 1e-6]
    if drift:
        return {"checkable": True, "ok": False, "drifted": drift,
                "reason": "nothing was refused, yet these legs post different R shared and "
                          "solo — with a full budget the two books must be identical in R"}
    return {"checkable": True, "ok": True,
            "reason": "nothing was refused and every leg posts the same R shared as solo, so "
                      "the shared account changed the dollars and moved no decision"}


def _write_solo(sdir: Path, strategy_id: str, results: dict) -> None:
    """Persist one leg's SOLO control book beside the stack's other artefacts.

    ⚠ It gets NO run row and NO evaluation, deliberately. A solo control is not a lab run — it was
    never requested, has no id anybody can navigate to, and putting it in `backtest_runs` would make
    it appear in the Runs list as a backtest nobody launched. It is read only by
    `GET /stacks/{id}`, which serves it as the leg's `solo_equity_curve` / `solo_daily_pnl`.
    """
    d = sdir / "solo" / strategy_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "equity_curve.json").write_text(
        json.dumps(results.get("equity_curve", []), default=str))
    (d / "daily_pnl.json").write_text(
        json.dumps(results.get("daily_pnl", []), default=str))


def solo_book(stack_id: str, strategy_id: str) -> tuple[list, list]:
    """The leg's solo control book, or `([], [])` when this stack predates it being kept.

    ⚠ Empty means "not stored", and the caller must render that as a REFUSAL rather than as a leg
    that made nothing — see `routers/stacks.py`. A stack run before 2026-08-10 has the scalars in
    `shared_summary.json` and no book, so the page can state the closing balance and must not draw
    a curve.
    """
    d = stack_dir(stack_id) / "solo" / strategy_id
    eq = _read_json_list(d / "equity_curve.json")
    dp = _read_json_list(d / "daily_pnl.json")
    return eq, dp


def _read_json_list(p: Path) -> list:
    try:
        v = json.loads(p.read_text())
        return v if isinstance(v, list) else []
    except Exception:      # noqa: BLE001 — absent or unreadable both mean "no book stored"
        return []


def _write_leg(run_id: str, results: dict, ruleset_ids: list[str]) -> None:
    """Persist one leg exactly the way `sweep_runner._handle_complete` persists a child run, so
    the existing drill-in detail page works on a shared leg with no branch of its own."""
    kpis = results.get("kpis", {})
    equity_curve = results.get("equity_curve", [])
    daily_pnl = results.get("daily_pnl", [])

    run_dir = _LAB_RESULTS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    eq_path = run_dir / "equity_curve.json"
    dpnl_path = run_dir / "daily_pnl.json"
    eq_path.write_text(json.dumps(equity_curve, default=str))
    dpnl_path.write_text(json.dumps(daily_pnl, default=str))

    apply_canonical_sharpe(kpis, daily_pnl)

    lab_db.update_run_complete(run_id, kpis, {
        "equity_curve": str(eq_path),
        "trades": None,
        "daily_pnl": str(dpnl_path),
    })

    if ruleset_ids:
        evaluator.evaluate_run(run_id, ruleset_ids, kpis, equity_curve, daily_pnl)
        w = worthiness.score_run_after_evals(
            run_id, ruleset_ids,
            kpis.get("profit_factor"), kpis.get("max_drawdown"), kpis.get("trade_count"),
        )
        if w:
            lab_db.update_run_worthiness(run_id, w[0], w[1], w[2])
