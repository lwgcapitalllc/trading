"""Does a STACK need setting nudges of its own, or does each bot's own stress test cover them?

`stress_tester.stack_nudges_needed` decides it (Aaron's call, 2026-09-10): a stack's setting
nudges are its slowest phase (~42 minutes on the live pairing), and when its bots cannot get in
each other's way a nudge to one bot moves only that bot's trades — which that bot's own stress
test already measures.

🔴 **Every case below that answers NOT NEEDED is one where the fast answer is only right if the
check really looked.** So the refusals matter more than the pass: an unreadable share, a missing
record of the cap binding, a dependent leg — each must answer NEEDED, or the quick test lands on
exactly the stack nobody checked.

⚠ A fail-watch against HEAD is VACUOUS for every case here — the function did not exist — so
non-vacuity is by MUTATION, and each docstring names the mutation that turns it red.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from services import lab_db, portfolio_runner, stress_tester
from services.grading import compute_grade

STACK = "stk_n"


def _seed_leg(i: int, sid: str, params: dict, *, source: str | None = None) -> None:
    lab_db.upsert_strategy(
        {
            "id": sid,
            "name": sid.upper(),
            "class_name": f"{sid.title()}Strategy",
            "source_path": f"strategies/python/{sid}",
            "runner": "python",
            "scanned_at": 1,
            "source_hash": "h",
        }
    )
    run_id = f"r_{sid}"
    lab_db.insert_run(
        {
            "run_id": run_id,
            "strategy_id": sid,
            "instrument": "XAUUSD.p",
            "params": params,
            "bar_type": "Minute",
            "bar_value": 15,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "commission_per_side": 0.0,
            "slippage_ticks": 0,
            "status": "complete",
            "created_at": 1,
            "runner": "python",
        }
    )
    lab_db.add_stack_member(STACK, run_id, 1, i, source=source)


def _stack(
    tmp_path,
    monkeypatch,
    *,
    shares=(5.0, 5.0),
    cap: float = 10.0,
    events: list | None = None,
    write_log: bool = True,
    summary_count: int | None = None,
    sources: dict | None = None,
) -> None:
    """A finished shared stack whose legs risk `shares`, under `cap`, whose own run logged
    `events` against the cap."""
    monkeypatch.setattr(portfolio_runner, "_LAB_RESULTS_DIR", tmp_path / "reports")
    lab_db.insert_stack(
        {
            "stack_id": STACK,
            "instrument": "XAUUSD.p",
            "bar_type": "Minute",
            "bar_value": 15,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "commission_per_side": 0.0,
            "slippage_ticks": 0,
            "created_at": 1,
            "mode": "shared",
            "account_size": 10_000.0,
            "risk_cap_pct": cap,
            "entry_floor_pct": 0.0,
        }
    )
    for i, share in enumerate(shares):
        sid = f"leg{i}"
        params = {} if share is None else {"exec_risk_pct": share}
        _seed_leg(i, sid, params, source=(sources or {}).get(sid))

    events = [] if events is None else events
    sdir = portfolio_runner.stack_dir(STACK)
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / "combined_equity_curve.json").write_text(
        json.dumps([{"index": 1, "equity": 10_500.0, "profit": 500.0, "date": "2024-03-01"}])
    )
    (sdir / "combined_daily_pnl.json").write_text("[]")
    (sdir / "shared_summary.json").write_text(
        json.dumps(
            {
                "stack_id": STACK,
                "combined_kpis": {"trade_count": 150},
                "contention_events": len(events) if summary_count is None else summary_count,
            }
        )
    )
    if write_log:
        (sdir / "contention.json").write_text(json.dumps(events))


def _trim(desired: float, granted: float) -> dict:
    return {"leg": "leg1", "desired_risk": desired, "granted_risk": granted, "blocked": False}


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "lab.db")
    lab_db.init_db()
    return tmp_path


# ── The decision ──────────────────────────────────────────────────────────────


def test_shares_that_FIT_and_a_cap_that_never_bound_need_no_nudges(lab, monkeypatch):
    """The live pairing's shape: 5% + 5% under a 10% cap, and the run refused nothing.

    ⚠ The reason is asserted too: it is what the page and the grade print, and a skip that
    cannot say what it rested on is a phase that silently vanished.
    ⚠ Watched RED by making the function always answer needed.
    """
    _stack(lab, monkeypatch)
    needed, why = stress_tester.stack_nudges_needed(STACK)
    assert needed is False
    assert "5% + 5%" in why and "10% cap" in why
    assert "trimmed none" in why


def test_shares_that_add_up_PAST_the_cap_need_the_full_test(lab, monkeypatch):
    """🔴 Over the cap the bots take turns, so which trades happen depends on all of them — the
    one case a single-bot test cannot see, and the reason the full test exists.
    ⚠ Watched RED by deleting the share check.
    """
    _stack(lab, monkeypatch, shares=(10.0, 5.0))
    needed, why = stress_tester.stack_nudges_needed(STACK)
    assert needed is True
    assert "more than the 10% cap" in why


def test_the_fit_is_decided_by_the_SHARED_check_not_a_second_sum(lab, monkeypatch):
    """0.1 + 0.2 is 0.30000000000000004 in floats. The Bots page and the copy-to-demo button call
    that FITTING a 0.3% cap (their check carries a tolerance); a private `sum > cap` here would
    call the same account over-subscribed, and the two screens would disagree about one
    configuration.

    ⚠ **The first version used 3.3 + 3.3 + 3.4, which happens to sum to EXACTLY 10.0** — so the
    private sum and the shared check agreed and the mutation survived. Numbers that cannot tell
    the two behaviours apart do not test which one is used.
    ⚠ Watched RED by replacing the call to the shared check with `sum(shares) > cap`.
    """
    assert 0.1 + 0.2 > 0.3  # the premise: in floats these really do overshoot
    _stack(lab, monkeypatch, shares=(0.1, 0.2), cap=0.3)
    needed, _why = stress_tester.stack_nudges_needed(STACK)
    assert needed is False


def test_a_share_that_cannot_be_READ_is_not_a_share_of_zero(lab, monkeypatch):
    """Rule 1. Counting a missing risk setting as 0% would let an over-subscribed stack pass as
    one that fits — the one outcome the check exists to prevent.
    ⚠ Watched RED by treating an unreadable share as 0.0.
    """
    _stack(lab, monkeypatch, shares=(5.0, None))
    needed, why = stress_tester.stack_nudges_needed(STACK)
    assert needed is True
    assert "cannot be read" in why and "leg1" in why


def test_an_entry_the_cap_BLOCKED_means_the_bots_compete(lab, monkeypatch):
    """A blocked entry is a trade one bot lost to the other. That changes R, which a single-bot
    test cannot see.
    ⚠ Watched RED by ignoring the `blocked` flag.
    """
    _stack(
        lab,
        monkeypatch,
        events=[{"leg": "leg1", "desired_risk": 500.0, "granted_risk": 0.0, "blocked": True}],
    )
    needed, why = stress_tester.stack_nudges_needed(STACK)
    assert needed is True
    assert "lost 1 trade" in why


def test_a_trim_OVER_one_percent_means_the_bots_compete(lab, monkeypatch):
    """Cutting 5% off a trade to fit is competition, even though no trade was lost.
    ⚠ Watched RED by raising the threshold to 10%.
    """
    _stack(lab, monkeypatch, events=[_trim(1_000.0, 950.0)])
    needed, why = stress_tester.stack_nudges_needed(STACK)
    assert needed is True
    assert "5.0%" in why


def test_a_trim_the_size_of_the_LIVE_one_is_sharing_not_competing(lab, monkeypatch):
    """MEASURED on the live pairing: one trim of $8.61 on a $16,979 trade (0.05%) in 6.6 years.
    With shares that fit exactly, a fall in the balance while one bot holds makes its fixed
    dollar risk a slightly bigger share — that is two bots sharing a budget, not taking turns.

    ⚠ The trim is NAMED in the reason rather than hidden: the page says what was measured.
    ⚠ Watched RED by treating any trim at all as competition.
    """
    _stack(lab, monkeypatch, events=[_trim(16_979.43, 16_970.82)])
    needed, why = stress_tester.stack_nudges_needed(STACK)
    assert needed is False
    assert "trimmed 1 by at most 0.05%" in why


def test_a_MISSING_record_of_the_cap_is_not_a_record_of_it_never_binding(lab, monkeypatch):
    """🔴 An empty log is a MEASUREMENT (the cap never bound). An absent one is nothing at all,
    and reading it as empty would skip the phase on a stack nobody checked.
    ⚠ Watched RED by making the contention reader return [] for a missing file.
    """
    _stack(lab, monkeypatch, write_log=False)
    needed, why = stress_tester.stack_nudges_needed(STACK)
    assert needed is True
    assert "no readable record" in why


def test_a_log_that_DISAGREES_with_its_own_summary_is_not_trusted(lab, monkeypatch):
    """The summary and the log are written by one call. A count that does not match the file is
    a file from somewhere else (a partial write, a stale copy), so it proves nothing.
    ⚠ Watched RED by dropping the count comparison.
    """
    _stack(lab, monkeypatch, summary_count=3)
    needed, _why = stress_tester.stack_nudges_needed(STACK)
    assert needed is True


def test_a_leg_that_trades_off_ANOTHER_legs_results_needs_the_whole_stack(lab, monkeypatch):
    """A loss-recovery leg moves whenever its parent's settings do — no single-bot test can see
    that, however the risk adds up.
    ⚠ Watched RED by deleting the dependent-leg check.
    """
    _stack(lab, monkeypatch, sources={"leg1": "leg0"})
    needed, why = stress_tester.stack_nudges_needed(STACK)
    assert needed is True
    assert "leg1" in why


def test_a_leg_that_NEEDS_a_parent_but_has_none_recorded_is_still_dependent(lab, monkeypatch):
    """A stack launched before the parent was stored has the dependency and cannot state it. A
    NULL source alone cannot tell that from an independent leg; the STRATEGY's own flag can.
    ⚠ Watched RED by reading only the recorded source.
    """
    _stack(lab, monkeypatch)
    import sqlite3

    with sqlite3.connect(lab_db.DB_PATH) as c:
        c.execute("UPDATE strategies SET requires_source=1 WHERE id='leg1'")
    needed, _why = stress_tester.stack_nudges_needed(STACK)
    assert needed is True


def test_a_stack_that_records_NO_cap_runs_the_full_test(lab, monkeypatch):
    """Nothing to check the shares against is not the same as shares that fit.
    ⚠ Watched RED by treating a missing cap as no competition.
    """
    _stack(lab, monkeypatch)
    real = lab_db.get_stack_settings
    monkeypatch.setattr(
        stress_tester.lab_db,
        "get_stack_settings",
        lambda sid: {**(real(sid) or {}), "risk_cap_pct": None},
    )
    needed, why = stress_tester.stack_nudges_needed(STACK)
    assert needed is True
    assert "no readable risk cap" in why


# ── The endpoint acts on it, once, and records why ────────────────────────────


@pytest.fixture
def api(client, tmp_path, monkeypatch):
    task = AsyncMock()
    monkeypatch.setattr("routers.stress_tests.run_stress_test_task", task)
    return client, task, tmp_path, monkeypatch


def test_a_stack_whose_bots_cannot_compete_SKIPS_the_nudges_and_says_why(api):
    """🔴 The request asks for sensitivity; the server narrows it, and every consumer reads the
    narrowed answer — the recorded phases, the task, the estimate — plus the stored reason.

    ⚠ The TASK's argument is asserted, not only the row: a row saying "skipped" while the task
    still runs 60 replays would be the page and the work describing different tests.
    ⚠ Watched RED by leaving the task on the requested flag.
    """
    client, task, tmp_path, monkeypatch = api
    _stack(tmp_path, monkeypatch)
    r = client.post(
        "/stress-tests/run",
        json={"stack_id": STACK, "include_walk_forward": True, "include_sensitivity": True},
    )
    assert r.status_code == 202, r.text
    st = lab_db.get_stress_test(r.json()["stress_test_id"])
    assert st["phases_requested"] == ["monte_carlo", "walk_forward"]
    assert "fit the 10% cap" in st["sensitivity_skipped"]
    assert task.call_args.args[1:] == (True, False)
    notes = r.json()["notes"]
    assert any(n.startswith("Setting nudges skipped:") for n in notes), notes
    assert not any(n.startswith("Sensitivity:") for n in notes), notes

    served = client.get(f"/stress-tests/{st['stress_test_id']}").json()
    assert served["sensitivity_skipped"] == st["sensitivity_skipped"]


def test_a_stack_whose_bots_DO_compete_keeps_the_full_test(api):
    """The other half, and the half an always-skip would fail.
    ⚠ Watched RED by skipping unconditionally.
    """
    client, task, tmp_path, monkeypatch = api
    _stack(tmp_path, monkeypatch, shares=(10.0, 5.0))
    r = client.post("/stress-tests/run", json={"stack_id": STACK, "include_sensitivity": True})
    assert r.status_code == 202, r.text
    st = lab_db.get_stress_test(r.json()["stress_test_id"])
    assert "sensitivity" in st["phases_requested"]
    assert st["sensitivity_skipped"] is None
    assert task.call_args.args[2] is True


def test_a_test_that_never_ASKED_for_nudges_records_no_skip(api):
    """A skip is a decision about a phase somebody asked for. Recording one on a Monte-Carlo-only
    request would claim a decision nobody made.
    ⚠ Watched RED by running the check whether or not sensitivity was requested.
    """
    client, _task, tmp_path, monkeypatch = api
    _stack(tmp_path, monkeypatch)
    r = client.post("/stress-tests/run", json={"stack_id": STACK})
    st = lab_db.get_stress_test(r.json()["stress_test_id"])
    assert st["sensitivity_skipped"] is None


# ── The grade says why, and a skip costs nothing ──────────────────────────────

_RULESET = {"name": "demo", "max_drawdown_from_peak_pct": 40.0, "account_size": 10_000.0}
_WF = [{"window": 1, "is_sharpe": 1.0, "oos_sharpe": 0.9, "is_trades": 30, "oos_trades": 25}]


def _st(**over) -> dict:
    return {
        "median_final_pnl": 5_000.0,
        "prob_breach": 0.0,
        "dd_basis": "percent",
        "pct1_max_dd_pct": 20.0,
        "pct5_max_dd_pct": 15.0,
        "median_max_dd_pct": 10.0,
        "walk_forward_degradation": 0.1,
        **over,
    }


def test_a_SKIPPED_phase_says_why_instead_of_may_improve(monkeypatch):
    """🔴 "Not run — grade may improve with full analysis" about a phase ruled out on evidence
    sends the reader to spend 40 minutes finding out it changes nothing.

    ⚠ It still grades as NOT RUN — no credit, no penalty, no cap on A. The skip is justified, so
    costing the stack a letter for it would be penalising a measurement that would add nothing.
    ⚠ Watched RED by dropping the skip from the "genuinely not run" test.
    """
    monkeypatch.setattr("services.grading.effective_dd_limit_pct", lambda _r: 40.0)
    grade, reasons = compute_grade(
        _st(sensitivity_skipped="the shares fit the cap"), _WF, None, _RULESET
    )
    assert grade == "A"
    assert "Setting nudges not run on this stack: the shares fit the cap" in reasons
    assert not any("may improve" in r for r in reasons), reasons


def test_a_skip_reason_is_IGNORED_when_the_nudges_actually_ran(monkeypatch):
    """A stale reason on a row whose sensitivity DID run must not claim it was skipped.
    ⚠ Watched RED by reading the reason whether or not a sensitivity result exists.
    """
    monkeypatch.setattr("services.grading.effective_dd_limit_pct", lambda _r: 40.0)
    _grade, reasons = compute_grade(
        _st(sensitivity_skipped="stale", sensitivity_max_degradation=0.1),
        _WF,
        {"p": {"+10%": {"degradation": 0.1}}},
        _RULESET,
    )
    assert not any("Setting nudges not run" in r for r in reasons), reasons


# ── The quick test's own wait is measured too ─────────────────────────────────


def _timed_test(st_id: str, stack_id: str, created: int, mc_at, wf_at) -> None:
    import sqlite3

    lab_db.insert_stress_test(
        {
            "stress_test_id": st_id,
            "stack_id": stack_id,
            "status": "complete",
            "created_at": created,
            "phases_requested": ["monte_carlo", "walk_forward"],
        }
    )
    with sqlite3.connect(lab_db.DB_PATH) as c:
        c.execute(
            "UPDATE stress_tests SET mc_completed_at=?, wf_completed_at=? WHERE stress_test_id=?",
            (mc_at, wf_at, st_id),
        )


def test_a_stack_nobody_has_walked_forward_has_NO_measured_wait(lab, monkeypatch):
    """`None`, never 0 — a zero would quote a wait of nothing.
    ⚠ Watched RED by returning 0.0 when no row matches.
    """
    _stack(lab, monkeypatch)
    assert lab_db.last_stack_wf_seconds(STACK) is None


def test_the_measured_wait_is_the_NEWEST_finished_walk_forward_of_THIS_stack(lab, monkeypatch):
    """Newest wins; a walk-forward that never stamped its end (failed, cancelled) is not a quick
    one; and another stack's timing is never borrowed.
    ⚠ Watched RED by ordering oldest-first, by dropping the end-stamp filter, and by dropping the
    stack filter — each separately.
    """
    _stack(lab, monkeypatch)
    _timed_test("old", STACK, 1, 1_000, 1_600)  # 600s, older
    _timed_test("new", STACK, 3, 2_000, 2_252)  # 252s, newest finished
    _timed_test("died", STACK, 5, 3_000, None)  # newest of all, never finished
    _timed_test("other", "stk_other", 9, 4_000, 4_030)  # a different stack, newer still
    assert lab_db.last_stack_wf_seconds(STACK) == 252.0


def test_the_walk_forward_estimate_PREFERS_the_measurement(lab, monkeypatch):
    """252s is 5 minutes, whatever the run rows or the replay constant would say.
    ⚠ Watched RED by skipping the measured branch.
    """
    _stack(lab, monkeypatch)
    _timed_test("new", STACK, 3, 2_000, 2_252)
    monkeypatch.setattr(stress_tester, "_stack_replay_minutes", lambda *a, **k: 100.0)
    assert stress_tester.stack_walk_forward_minutes(STACK) == 5


def test_an_unmeasured_walk_forward_is_one_replay_times_the_MEASURED_ratio(lab, monkeypatch):
    """The fallback: one replay's cost times the ratio measured on the live pairing. 182.6s x 1.38
    = 252s = 5 minutes, which is what the live stack really took (4.2).
    ⚠ Watched RED by dropping the ratio.
    """
    _stack(lab, monkeypatch)
    monkeypatch.setattr(lab_db, "last_stack_replay_seconds", lambda _sid: 182.6)
    assert stress_tester.stack_walk_forward_minutes(STACK) == 5


def test_the_start_screen_quotes_the_STACK_walk_forward_not_the_single_run_constant(api):
    """🔴 The single-run constant priced a python walk-forward as ten 12-second child jobs and
    quoted 2 minutes for a measured 4.2 on the live pairing.
    ⚠ Watched RED by routing a stack through the single-run estimate.
    """
    client, _task, tmp_path, monkeypatch = api
    _stack(tmp_path, monkeypatch)
    _timed_test("prev", STACK, 1, 1_000, 1_600)  # this stack's last walk-forward took 10 min
    r = client.post(
        "/stress-tests/run",
        json={"stack_id": STACK, "include_walk_forward": True, "walk_forward_windows": 5},
    )
    assert r.status_code == 202, r.text
    note = next(n for n in r.json()["notes"] if n.startswith("Walk-forward"))
    assert note.startswith("Walk-forward: ~10 min (10 whole-stack replays"), note
