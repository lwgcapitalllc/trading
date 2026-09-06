"""What a stress test is allowed to grade — a single RUN, or a whole STACK.

Aaron runs stacks, and his pipeline is backtest → stress test → demo → live: *"it doesn't
matter if it's a single strategy or a stack of two or more strategies … nothing should run on
its own and then come at numbers at the end."* Everything downstream of a stress test used to
read a `backtest_runs` row directly, so a stack — which has no such row of its own — could not
be graded at all.

🔴 **This module is the ONE place that answers *what am I grading*, and both the endpoint and
the background task ask it.** Two places resolving that independently is how the pre-flight and
the run came to disagree about which bar feeds a backtest loads (`run_feeds.py`, written for
exactly that defect one layer down). Here the cost of disagreeing would be a test that is
refused on one side and started on the other, or graded against a window it did not replay.

⚠ **It RESOLVES and REFUSES. It runs nothing**, opens no job, and takes no lock — so it is safe
to call from a request handler to decide a status code, and again from the task to get the same
answer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from services import lab_db, portfolio_runner


class NotGradable(Exception):
    """This target cannot be stress tested, and `reason` says why in the reader's words.

    `status` is the HTTP code the router should use, carried here rather than inferred by the
    caller: *no such stack* and *this stack is a screen* are a 404 and a 400, and only this
    module knows which one it just decided.
    """

    def __init__(self, reason: str, status: int = 400):
        super().__init__(reason)
        self.reason = reason
        self.status = status


@dataclass(frozen=True)
class Leg:
    """One strategy inside the thing being graded. A single run has exactly one."""

    strategy_id: str
    run_id: Optional[str]
    params: dict
    bar_value: int


@dataclass(frozen=True)
class Target:
    kind: str  # "run" | "stack"
    target_id: str
    label: str
    equity_curve_path: str
    trade_count: int
    instrument: str
    bar_type: str
    bar_value: int
    start_date: str
    end_date: str
    runner: str
    legs: tuple[Leg, ...]
    # The FIRST leg's strategy row, resolved once here. The endpoint needs it for the
    # sensitivity estimate and used to look it up again off the leg's id — a second read of
    # the same fact, and the thing that decides which params get perturbed. `{}` when the
    # strategy row is gone, which the caller reads as "cannot estimate", never as "no params".
    strategy: dict

    @property
    def is_stack(self) -> bool:
        return self.kind == "stack"


def resolve_for_stress_test(st: dict) -> Target:
    """The target a stored stress-test row names.

    ⚠ Reads the row's OWN target fields rather than being told — the row is the record of what
    was asked for, and a task handed an id separately could grade something the row does not
    name.
    """
    if st.get("stack_id"):
        return resolve(stack_id=st["stack_id"])
    if st.get("run_id"):
        return resolve(run_id=st["run_id"])
    raise NotGradable("This stress test names neither a run nor a stack", status=400)


def resolve(*, run_id: Optional[str] = None, stack_id: Optional[str] = None) -> Target:
    """Exactly one of `run_id` / `stack_id`. Raises `NotGradable` with the reason."""
    if bool(run_id) == bool(stack_id):
        raise NotGradable("Name exactly one of a run or a stack to stress test", status=400)
    return _from_stack(stack_id) if stack_id else _from_run(run_id or "")


# ── A single run ──────────────────────────────────────────────────────────────


def _from_run(run_id: str) -> Target:
    run = lab_db.get_run(run_id)
    if not run:
        raise NotGradable("Run not found", status=404)
    if run.get("status") != "complete":
        raise NotGradable("Run must be complete before stress testing", status=400)
    path = run.get("equity_curve_path")
    if not path:
        raise NotGradable("Run has no equity curve data", status=400)

    strategy = lab_db.get_strategy(run.get("strategy_id", "")) or {}
    return Target(
        kind="run",
        target_id=run_id,
        label=strategy.get("name") or run.get("strategy_id") or run_id,
        equity_curve_path=path,
        trade_count=int(run.get("trade_count") or 0),
        instrument=run.get("instrument", ""),
        bar_type=run.get("bar_type", "Minute"),
        bar_value=int(run.get("bar_value") or 0),
        start_date=run.get("start_date", ""),
        end_date=run.get("end_date", ""),
        runner=strategy.get("runner", "ninjatrader"),
        strategy=strategy,
        legs=(
            Leg(
                strategy_id=run.get("strategy_id", ""),
                run_id=run_id,
                params=run.get("params") or {},
                bar_value=int(run.get("bar_value") or 0),
            ),
        ),
    )


# ── A stack ───────────────────────────────────────────────────────────────────


def _from_stack(stack_id: str) -> Target:
    settings = lab_db.get_stack_settings(stack_id)
    if not settings:
        raise NotGradable("Stack not found", status=404)

    # 🔴 A SCREEN IS NOT A PORTFOLIO AND MAY NOT BE GRADED AS ONE. There every leg traded its
    # own full account with nothing able to block anything, so the combined figure is N
    # standalone runs added up — an UPPER BOUND. Grading it would put a letter on a result no
    # account can produce, which is worse than refusing because it looks like an answer.
    if (settings.get("mode") or "screen") != "shared":
        raise NotGradable(
            "This stack is a screen — each leg traded its own full account, so there is no "
            "shared account to grade. Re-run it as a shared account stack.",
            status=400,
        )

    legs = lab_db.list_stack_runs(stack_id)
    if not legs:
        raise NotGradable("This stack has no legs", status=400)
    unfinished = [leg for leg in legs if leg.get("status") != "complete"]
    if unfinished:
        raise NotGradable(
            "Every leg must be complete before the stack can be stress tested "
            f"({len(unfinished)} of {len(legs)} are not)",
            status=400,
        )

    summary = portfolio_runner.read_shared_summary(stack_id)
    curve_path = Path(portfolio_runner.stack_dir(stack_id)) / "combined_equity_curve.json"
    # ⚠ A stack replayed before 2026-09-06 kept only a trade count and a total R — the
    # account's own book was computed and discarded — so there is genuinely nothing to grade
    # and no way to recover it but replaying. The refusal names the fix rather than reporting
    # an empty result, which would read as an account that never traded.
    if not summary or not curve_path.exists():
        raise NotGradable(
            "This stack has no combined account book on disk — it was replayed before that "
            "was kept. Re-run the stack and stress test it again.",
            status=400,
        )

    kpis = summary.get("combined_kpis") or {}
    trade_count = kpis.get("trade_count")
    if trade_count is None:
        raise NotGradable(
            "This stack's combined book records no trade count — re-run the stack.", status=400
        )

    runner = _stack_runner(legs)
    return Target(
        kind="stack",
        target_id=stack_id,
        label=_stack_label(legs),
        equity_curve_path=str(curve_path),
        trade_count=int(trade_count),
        instrument=settings.get("instrument", ""),
        bar_type=settings.get("bar_type", "Minute"),
        bar_value=int(settings.get("bar_value") or 0),
        start_date=settings.get("start_date", ""),
        end_date=settings.get("end_date", ""),
        runner=runner,
        # ⚠ The FIRST leg's strategy, and a stack has several — this exists for the sensitivity
        # estimate, which is not built for a stack and is refused for one. Do not read it as
        # "the stack's strategy": there is no such thing.
        strategy=lab_db.get_strategy(legs[0].get("strategy_id", "")) or {},
        legs=tuple(
            Leg(
                strategy_id=leg.get("strategy_id", ""),
                run_id=leg.get("run_id"),
                params=leg.get("params") or {},
                # ⚠ A leg names its OWN frame since 2026-09-03 and falls back to the stack's
                # only when its package declares none. Reading the stack's here would describe
                # a leg on a timeframe it was never replayed on.
                bar_value=int(leg.get("bar_value") or settings.get("bar_value") or 0),
            )
            for leg in legs
        ),
    )


def _stack_runner(legs: list[dict]) -> str:
    """Every leg's runner, which must agree.

    A stack is python-only by construction, but reading it off the legs rather than writing
    `"python"` here means the day that stops being true this refuses instead of filing an MT5
    leg under the python platform lock.
    """
    seen = {(leg.get("runner") or "python") for leg in legs}
    if len(seen) > 1:
        raise NotGradable(
            f"This stack's legs ran on different platforms ({', '.join(sorted(seen))}), so "
            f"there is no single platform to hold while it is stress tested.",
            status=400,
        )
    return seen.pop()


def _stack_label(legs: list[dict]) -> str:
    names = [leg.get("strategy_name") or leg.get("strategy_id") or "?" for leg in legs]
    return " + ".join(names)


def combined_book_kpis(stack_id: str) -> dict[str, Any]:
    """The stack's combined KPI dict, or `{}` when no book was stored.

    ⚠ `{}` means NOT STORED, never *this account made nothing*. Same rule as
    `portfolio_runner.combined_book`, which it sits beside.
    """
    summary = portfolio_runner.read_shared_summary(stack_id)
    return (summary or {}).get("combined_kpis") or {}


def load_equity_curve(target: Target) -> list[dict]:
    """The target's book, read once.

    ⚠ Raises rather than returning `[]` on an unreadable file: an empty book and a book that
    could not be read grade identically and mean opposite things.
    """
    p = Path(target.equity_curve_path)
    if not p.exists():
        raise NotGradable(f"No equity curve on disk for this {target.kind}", status=400)
    try:
        data = json.loads(p.read_text())
    except Exception as exc:  # noqa: BLE001 — every failure here is the same answer
        raise NotGradable(
            f"This {target.kind}'s equity curve could not be read ({type(exc).__name__})",
            status=400,
        ) from exc
    if not isinstance(data, list):
        raise NotGradable(f"This {target.kind}'s equity curve is not a trade list", status=400)
    return data
