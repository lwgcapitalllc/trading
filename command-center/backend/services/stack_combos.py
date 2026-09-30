"""Any mix of a shared stack's legs — replayed for real, never sliced out of the full book.

A shared stack stores two kinds of book: every leg together, and each leg alone (the solo
control). Aaron's requirement (2026-09-27): *"I should be able to toggle as many strategies off
and see any combination ... I just need to have at minimum 1 on."*

🔴 **A combination is REPLAYED, never composed.** Inside the full shared book every leg sizes off a
balance all of them grew, and the cap trims or blocks entries depending on who else is holding.
Removing a leg from that book leaves the others' dollars describing an account that never existed
— the defect that put $47.8M on a leg worth $21k alone (`portfolio_runner._persist`). So a subset
of two or more legs goes back through `portfolio_runner._build_and_run` on the same bars, costs,
cap and balance as the launched stack, and its book is written beside the stack's own.

⚠ **Nothing here is a second account model.** It calls the one replay path the launch, the
walk-forward and the sensitivity phase all call; this module only picks which legs go in and
where the result is kept.

⚠ **A stored combination is tied to the book it was replayed beside.** Each one is stamped with
the stack summary's `written_at`, and a stamp that no longer matches reads as NOT STORED — a
re-persisted stack must never serve combinations replayed against its previous self.

⚠ **Replays run one at a time on one worker thread.** A combination is minutes of CPU, and
queueing them means a reader toggling through every mix gets them in the order asked for rather
than N replays fighting for the same cores.
"""

from __future__ import annotations

import itertools
import json
import threading
import traceback
from collections import deque
from pathlib import Path
from typing import Any, Optional

from services import lab_db, portfolio_runner

# A launched stack replays every combination up to this many legs as soon as it finishes, so the
# toggles are instant. Past it the count explodes (2^n - n - 2: 3 legs -> 3, 5 -> 25, 6 -> 56) and
# each combination is replayed only when somebody asks for it.
MAX_AUTO_LEGS = 5

_LOCK = threading.Lock()
_QUEUE: deque = deque()  # (stack_id, key)
_PROGRESS: dict[tuple[str, str], dict] = {}
# The last failure per combination, in memory. A failed replay writes NO book, so it reads as not
# stored and can be asked again — this only lets the page say why instead of waiting for ever.
_FAILED: dict[tuple[str, str], str] = {}
_WORKER: Optional[threading.Thread] = None


def combo_key(strategy_ids) -> str:
    """One name per SET of legs — order-free, so A+B and B+A are the same replay."""
    return "+".join(sorted(strategy_ids))


def combo_dir(stack_id: str, key: str) -> Path:
    return portfolio_runner.stack_dir(stack_id) / "combos" / key


def _stamp(stack_id: str) -> Optional[int]:
    """The full book's own write time, or None when the stack has no shared book."""
    summary = portfolio_runner.read_shared_summary(stack_id)
    return summary.get("written_at") if summary else None


def refusal(stack_id: str, strategy_ids: list[str]) -> Optional[str]:
    """Why this combination cannot be replayed, or None when it can.

    ⚠ A leg that arms off another leg's trades cannot run without that leg — it would arm off
    nothing and return an empty book that looks exactly like a rule that found no setups.
    """
    settings = lab_db.get_stack_settings(stack_id)
    if not settings:
        return "Stack not found"
    if (settings.get("mode") or "screen") != "shared":
        return "Only a shared-account stack has combinations to replay"
    rows = lab_db.list_stack_runs(stack_id)
    present = {r["strategy_id"] for r in rows}
    wanted = set(strategy_ids)
    if not wanted:
        return "Leave at least one strategy on"
    if not wanted <= present:
        return f"Not in this stack: {', '.join(sorted(wanted - present))}"
    if any(r["status"] != "complete" for r in rows):
        return "Every strategy in the stack has to finish before a combination can be replayed"
    if _stamp(stack_id) is None:
        return "This stack has no shared book on disk — rerun it first"
    for r in rows:
        src = r.get("stack_source")
        if r["strategy_id"] in wanted and src and src not in wanted:
            return f"{r['strategy_id']} trades off {src}'s results, so it cannot run without it"
    return None


def read_combo(stack_id: str, strategy_ids: list[str]) -> Optional[dict]:
    """The stored book for this combination, or None when it is not stored (or is stale).

    Returns `{strategy_ids, legs: {sid: {equity_curve, daily_pnl}}, contention}`.
    """
    key = combo_key(strategy_ids)
    d = combo_dir(stack_id, key)
    try:
        meta = json.loads((d / "summary.json").read_text())
    except Exception:  # noqa: BLE001 — absent or unreadable both mean "not stored"
        return None
    stamp = _stamp(stack_id)
    if stamp is None or meta.get("stack_written_at") != stamp:
        return None
    legs = {}
    for sid in sorted(strategy_ids):
        legs[sid] = {
            "equity_curve": portfolio_runner._read_json_list(d / sid / "equity_curve.json"),
            "daily_pnl": portfolio_runner._read_json_list(d / sid / "daily_pnl.json"),
        }
    return {"strategy_ids": sorted(strategy_ids), "legs": legs, "summary": meta}


def status(stack_id: str, strategy_ids: list[str]) -> dict:
    """What the page needs for one combination: its book, its progress, or why it cannot exist."""
    key = combo_key(strategy_ids)
    why = refusal(stack_id, strategy_ids)
    if why:
        return {"key": key, "available": False, "refused": why}
    book = read_combo(stack_id, strategy_ids)
    if book:
        return {"key": key, "available": True, **book}
    with _LOCK:
        prog = _PROGRESS.get((stack_id, key))
        queued = (stack_id, key) in _QUEUE
        failed = _FAILED.get((stack_id, key))
    out: dict = {
        "key": key,
        "available": False,
        "progress": dict(prog) if prog else ({"phase": "queued", "pct": 0} if queued else None),
    }
    if failed and not prog and not queued:
        out["error"] = failed
    return out


def request(stack_id: str, strategy_ids: list[str]) -> dict:
    """Queue this combination at the FRONT (somebody is looking at it) and report its status."""
    why = refusal(stack_id, strategy_ids)
    if why is None and len(set(strategy_ids)) > 1 and read_combo(stack_id, strategy_ids) is None:
        _enqueue(stack_id, combo_key(strategy_ids), front=True)
    return status(stack_id, strategy_ids)


def missing(stack_id: str) -> list[list[str]]:
    """Every replayable combination of two or more legs, short of all of them, not yet stored."""
    rows = lab_db.list_stack_runs(stack_id)
    ids = sorted(r["strategy_id"] for r in rows)
    out = []
    for size in range(2, len(ids)):
        for combo in itertools.combinations(ids, size):
            c = list(combo)
            if refusal(stack_id, c) is None and read_combo(stack_id, c) is None:
                out.append(c)
    return out


def replay_all_missing(stack_id: str) -> int:
    """Queue every missing combination, if the stack is small enough to do it up front."""
    rows = lab_db.list_stack_runs(stack_id)
    if len(rows) > MAX_AUTO_LEGS:
        return 0
    todo = missing(stack_id)
    for c in todo:
        _enqueue(stack_id, combo_key(c), front=False)
    return len(todo)


def _enqueue(stack_id: str, key: str, *, front: bool) -> None:
    global _WORKER
    with _LOCK:
        item = (stack_id, key)
        _FAILED.pop(item, None)
        if item in _PROGRESS:  # already replaying
            return
        if item in _QUEUE:
            if not front:
                return
            _QUEUE.remove(item)
        if front:
            _QUEUE.appendleft(item)
        else:
            _QUEUE.append(item)
        if _WORKER is None or not _WORKER.is_alive():
            _WORKER = threading.Thread(target=_drain, name="stack-combos", daemon=True)
            _WORKER.start()


def _drain() -> None:
    while True:
        with _LOCK:
            if not _QUEUE:
                return
            stack_id, key = _QUEUE.popleft()
            _PROGRESS[(stack_id, key)] = {"phase": "starting", "pct": 1}
        try:
            _replay(stack_id, key.split("+"))
        except Exception as exc:  # noqa: BLE001 — one bad combination must not stop the queue
            traceback.print_exc()
            with _LOCK:
                _FAILED[(stack_id, key)] = str(exc) or type(exc).__name__
        finally:
            with _LOCK:
                _PROGRESS.pop((stack_id, key), None)


def _replay(stack_id: str, strategy_ids: list[str]) -> None:
    """Replay exactly these legs on the stack's account and write their books."""
    from backtest.output import build_results
    from services import gradable

    if refusal(stack_id, strategy_ids) is not None or read_combo(stack_id, strategy_ids):
        return
    stamp = _stamp(stack_id)
    settings = lab_db.get_stack_settings(stack_id)
    wanted = set(strategy_ids)
    legs = [leg for leg in gradable.rebuild_legs(stack_id) if leg["strategy_id"] in wanted]
    key = combo_key(strategy_ids)

    def _progress(phase: str, pct: int, message: str) -> None:
        with _LOCK:
            _PROGRESS[(stack_id, key)] = {"phase": phase, "pct": pct, "message": message}

    # ⚠ No solo controls — each leg's solo book is already stored on the stack itself.
    run, specs = portfolio_runner._build_and_run(
        legs, dict(settings), on_progress=_progress, solo_control=False
    )
    if run.cancelled:
        return

    # The stack may have been deleted or re-persisted while this ran; either makes the book stale.
    if _stamp(stack_id) != stamp:
        return

    d = combo_dir(stack_id, key)
    d.mkdir(parents=True, exist_ok=True)
    per_leg: dict[str, Any] = {}
    for spec in specs:
        trades = run.per_leg.get(spec.name, [])
        results = build_results(
            trades,
            point_value=getattr(spec.config, "point_value", 1.0),
            initial_capital=run.opening_balance,
        )
        ld = d / spec.name
        ld.mkdir(parents=True, exist_ok=True)
        (ld / "equity_curve.json").write_text(json.dumps(results["equity_curve"], default=str))
        (ld / "daily_pnl.json").write_text(json.dumps(results["daily_pnl"], default=str))
        per_leg[spec.name] = {
            "trades": len(trades),
            "r": round(sum(getattr(t, "r", 0.0) for t in trades), 4),
        }
    # Written LAST: its presence is what makes the combination read as stored.
    (d / "summary.json").write_text(
        json.dumps(
            {
                "strategy_ids": sorted(strategy_ids),
                "stack_written_at": stamp,
                "opening_balance": run.opening_balance,
                "closing_balance": round(run.closing_balance, 2),
                "contention_events": len(run.contention),
                "legs": per_leg,
            },
            default=str,
        )
    )
