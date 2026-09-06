"""What a stress test is allowed to grade, resolved in ONE place.

`services/gradable.py` is asked the same question twice — by the endpoint deciding a status
code, and by the background task deciding what to read. Two places answering it independently
is how a pre-flight and a run come to disagree about what they are looking at; `run_feeds.py`
exists because of exactly that, one layer down.

⚠ A fail-watch against HEAD is VACUOUS for every case here — the module did not exist — so
non-vacuity is by MUTATION, and each docstring names the mutation that turns it red.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from services import gradable, lab_db, portfolio_runner

CURVE = [
    {"index": 1, "equity": 10_500.0, "profit": 500.0, "date": "2024-03-01"},
    {"index": 2, "equity": 10_300.0, "profit": -200.0, "date": "2024-03-02"},
]


def _seed_strategy(sid: str, runner: str = "python") -> None:
    lab_db.upsert_strategy(
        {
            "id": sid,
            "name": sid.upper(),
            "class_name": f"{sid.title()}Strategy",
            "source_path": f"strategies/python/{sid}",
            "runner": runner,
            "scanned_at": 1,
            "source_hash": "h",
        }
    )


def _seed_run(run_id: str, sid: str, *, bar_value: int = 15, runner: str = "python") -> None:
    lab_db.insert_run(
        {
            "run_id": run_id,
            "strategy_id": sid,
            "instrument": "XAUUSD.p",
            "params": {"exec_risk_pct": 10.0},
            "bar_type": "Minute",
            "bar_value": bar_value,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "commission_per_side": 0.0,
            "slippage_ticks": 0,
            "status": "running",
            "created_at": 1,
            "runner": runner,
        }
    )


def _complete(run_id: str, *, trades: int, curve_path: str | None) -> None:
    with sqlite3.connect(lab_db.DB_PATH) as c:
        c.execute(
            "UPDATE backtest_runs SET status='complete', trade_count=?, equity_curve_path=? "
            "WHERE run_id=?",
            (trades, curve_path, run_id),
        )


def _stack(
    tmp_path,
    monkeypatch,
    *,
    mode: str = "shared",
    legs: tuple = (("sos_fade", 15), ("b_leg", 5)),
    write_book: bool = True,
    complete_legs: bool = True,
    runner: str = "python",
) -> str:
    """A whole stack, seeded the way the app builds one, with its combined book on disk."""
    monkeypatch.setattr(portfolio_runner, "_LAB_RESULTS_DIR", tmp_path / "reports")
    lab_db.insert_stack(
        {
            "stack_id": "stk_1",
            "instrument": "XAUUSD.p",
            "bar_type": "Minute",
            "bar_value": 15,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "commission_per_side": 0.0,
            "slippage_ticks": 0,
            "created_at": 1,
            "mode": mode,
            "account_size": 10_000.0,
            "risk_cap_pct": 10.0,
            "entry_floor_pct": 0.0,
        }
    )
    for i, (sid, bar_value) in enumerate(legs):
        _seed_strategy(sid, runner=runner)
        _seed_run(f"r_{sid}", sid, bar_value=bar_value, runner=runner)
        if complete_legs:
            # 🔴 EACH LEG GETS ITS OWN BOOK, HOLDING DIFFERENT TRADES. Without this the legs
            # carried no curve at all, so *resolve the account's book* and *resolve the first
            # leg's book* returned the identical path and a mutation swapping them SURVIVED.
            # A fixture whose two behaviours cannot produce different output is not testing
            # the thing it names.
            leg_curve = tmp_path / f"leg_{sid}.json"
            leg_curve.write_text(json.dumps([{"index": 1, "equity": 1.0, "profit": 1.0}]))
            _complete(f"r_{sid}", trades=60, curve_path=str(leg_curve))
        lab_db.add_stack_member("stk_1", f"r_{sid}", 1, i)

    if write_book:
        sdir = portfolio_runner.stack_dir("stk_1")
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "combined_equity_curve.json").write_text(json.dumps(CURVE))
        (sdir / "combined_daily_pnl.json").write_text(json.dumps([]))
        (sdir / "shared_summary.json").write_text(
            json.dumps({"stack_id": "stk_1", "combined_kpis": {"trade_count": 120}})
        )
    return "stk_1"


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "lab.db")
    lab_db.init_db()
    return tmp_path


# ── Exactly one target ────────────────────────────────────────────────────────


def test_naming_BOTH_or_NEITHER_target_is_refused(lab):
    """The rule the table's CHECK enforces on the row, enforced again on the way in so the
    caller gets a sentence rather than an IntegrityError.

    🔴 It asserts the REASON, not just that something raised. The first version checked the
    exception type alone and SURVIVED its own mutation: with the guard weakened to
    `if run_id and stack_id`, naming neither falls through to `_from_run("")`, which raises
    the same class saying *Run not found*. **A refusal for the wrong reason passes a test that
    only asks whether it refused** — and *no such run* would have sent the reader hunting for
    a run they never named.

    ⚠ Watched RED by mutating the guard to `if run_id and stack_id`.
    """
    with pytest.raises(gradable.NotGradable, match="exactly one"):
        gradable.resolve(run_id="r", stack_id="s")
    with pytest.raises(gradable.NotGradable, match="exactly one"):
        gradable.resolve()


# ── A single run ──────────────────────────────────────────────────────────────


def test_a_completed_RUN_resolves_to_its_own_book(lab, monkeypatch):
    """⚠ Watched RED by returning the stack's combined path for a run target."""
    _seed_strategy("sos_fade")
    _seed_run("r1", "sos_fade")
    curve = lab / "eq.json"
    curve.write_text(json.dumps(CURVE))
    _complete("r1", trades=161, curve_path=str(curve))

    t = gradable.resolve(run_id="r1")
    assert (t.kind, t.trade_count, t.runner) == ("run", 161, "python")
    assert t.equity_curve_path == str(curve)
    assert [leg.strategy_id for leg in t.legs] == ["sos_fade"]
    assert gradable.load_equity_curve(t) == CURVE


def test_a_run_that_is_MISSING_or_UNFINISHED_is_refused_with_the_right_CODE(lab):
    """404 and 400 are different answers, and only the resolver knows which it just decided —
    which is why `NotGradable` carries the status rather than the router guessing.

    ⚠ Watched RED by hardcoding `status=400` on the exception.
    """
    with pytest.raises(gradable.NotGradable) as missing:
        gradable.resolve(run_id="nope")
    assert missing.value.status == 404

    _seed_strategy("sos_fade")
    _seed_run("r_running", "sos_fade")
    with pytest.raises(gradable.NotGradable) as unfinished:
        gradable.resolve(run_id="r_running")
    assert unfinished.value.status == 400


# ── A stack ───────────────────────────────────────────────────────────────────


def test_a_shared_STACK_resolves_to_the_COMBINED_book(lab, monkeypatch):
    """🔴 The whole point: the subject is the ACCOUNT, so the curve is the account's own book
    and the trade count is the combined one — never a leg's.

    ⚠ Watched RED by resolving the first leg's equity curve instead.
    """
    _stack(lab, monkeypatch)
    t = gradable.resolve(stack_id="stk_1")
    assert t.kind == "stack"
    assert t.trade_count == 120, "the COMBINED book's count, not a leg's 60"
    assert t.equity_curve_path.endswith("combined_equity_curve.json")
    assert gradable.load_equity_curve(t) == CURVE
    assert t.is_stack is True


def test_a_SCREEN_is_refused_because_it_has_no_shared_account(lab, monkeypatch):
    """A screen is N standalone runs added together — every leg on its own full account, so
    nothing could block anything and the total is an UPPER BOUND. Grading it puts a letter on
    a result no account can produce, which is worse than refusing because it looks like an
    answer.

    ⚠ Watched RED by dropping the mode check.
    """
    _stack(lab, monkeypatch, mode="screen")
    with pytest.raises(gradable.NotGradable, match="screen"):
        gradable.resolve(stack_id="stk_1")


def test_a_stack_with_NO_combined_book_is_refused_and_the_reason_names_the_FIX(lab, monkeypatch):
    """Every stack replayed before 2026-09-06 kept a trade count and a total R and threw the
    account's own book away. There is nothing to grade and no way to recover it but replaying,
    so the refusal says *re-run the stack* rather than reporting an empty result — which would
    read as an account that never traded.

    ⚠ Watched RED by falling back to an empty curve instead of refusing.
    """
    _stack(lab, monkeypatch, write_book=False)
    with pytest.raises(gradable.NotGradable, match="[Rr]e-run"):
        gradable.resolve(stack_id="stk_1")


def test_an_UNFINISHED_leg_blocks_the_stack(lab, monkeypatch):
    """⚠ Watched RED by dropping the completeness check: the stack then grades a book missing
    whatever the unfinished leg has not contributed yet."""
    _stack(lab, monkeypatch, complete_legs=False)
    with pytest.raises(gradable.NotGradable, match="complete"):
        gradable.resolve(stack_id="stk_1")


def test_a_missing_stack_is_a_404(lab):
    with pytest.raises(gradable.NotGradable) as exc:
        gradable.resolve(stack_id="nope")
    assert exc.value.status == 404


def test_each_leg_carries_ITS_OWN_frame_not_the_stacks(lab, monkeypatch):
    """🔴 A leg names its own timeframe since 2026-09-03. Reading the stack's fallback for
    every leg describes a leg on a frame it was never replayed on — and every figure computed
    from it would be about a different experiment.

    ⚠ Watched RED by reading `settings["bar_value"]` for every leg.
    """
    _stack(lab, monkeypatch, legs=(("sos_fade", 15), ("extreme_leg", 5)))
    t = gradable.resolve(stack_id="stk_1")
    assert sorted(leg.bar_value for leg in t.legs) == [5, 15]


def test_legs_on_DIFFERENT_platforms_are_refused(lab, monkeypatch):
    """The runner decides which platform lock the test holds. Two answers means holding the
    wrong one, which lets a second job start on a busy terminal.

    ⚠ Watched RED by returning `"python"` outright instead of reading the legs.
    """
    _stack(lab, monkeypatch)
    with sqlite3.connect(lab_db.DB_PATH) as c:
        c.execute("UPDATE backtest_runs SET runner='mt5' WHERE run_id='r_b_leg'")
    with pytest.raises(gradable.NotGradable, match="different platforms"):
        gradable.resolve(stack_id="stk_1")


# ── Reading the book ──────────────────────────────────────────────────────────


def test_an_UNREADABLE_book_raises_rather_than_reading_as_EMPTY(lab, monkeypatch):
    """An empty book and a book that could not be read grade identically and mean opposite
    things — this repo's oldest rule, in the one function that opens the file.

    ⚠ Watched RED by returning `[]` on the exception.
    """
    _stack(lab, monkeypatch)
    t = gradable.resolve(stack_id="stk_1")
    Path(t.equity_curve_path).write_text("{ not json")
    with pytest.raises(gradable.NotGradable):
        gradable.load_equity_curve(t)


def test_the_row_itself_says_what_is_being_graded(lab, monkeypatch):
    """The task resolves off the ROW, not off an id passed alongside it — a task told
    separately could grade something the row does not name.

    ⚠ Watched RED by making `resolve_for_stress_test` prefer `run_id`.
    """
    _stack(lab, monkeypatch)
    assert gradable.resolve_for_stress_test({"stack_id": "stk_1"}).is_stack is True
    with pytest.raises(gradable.NotGradable):
        gradable.resolve_for_stress_test({})


# ── The endpoint ──────────────────────────────────────────────────────────────


@pytest.fixture
def stack_client(client, tmp_path, monkeypatch):
    """The API, with a finished shared stack seeded and the background task stubbed.

    ⚠ The task is stubbed because starting it would run a real 10,000-path Monte Carlo inside
    the request. What is under test here is what the ENDPOINT decides and records.
    """
    from unittest.mock import AsyncMock

    monkeypatch.setattr("routers.stress_tests.run_stress_test_task", AsyncMock())
    _stack(tmp_path, monkeypatch)
    return client


def test_a_STACK_can_be_stress_tested_and_the_row_says_so(stack_client):
    """🔴 The row records the stack and NOT a run. Naming its first leg would have satisfied
    the foreign key and filed a portfolio result under one strategy.

    ⚠ Watched RED by writing `run_id` from `target.legs[0].run_id`.
    """
    r = stack_client.post("/stress-tests/run", json={"stack_id": "stk_1"})
    assert r.status_code == 202, r.text
    st = lab_db.get_stress_test(r.json()["stress_test_id"])
    assert st["stack_id"] == "stk_1"
    assert st["run_id"] is None


def test_SENSITIVITY_is_refused_for_a_stack_and_WALK_FORWARD_is_not(stack_client):
    """A shift cannot say WHICH LEG's setting it is nudging, so sensitivity would perturb one
    strategy and report the answer as the whole account's. Walk-forward has no such problem —
    the whole stack replays per window — so it is allowed.

    ⚠ Watched RED both ways: dropping the sensitivity guard (a 202 for a test that would
    measure the wrong thing) and re-adding walk-forward to it (a 400 for a phase that works).
    """
    refused = stack_client.post(
        "/stress-tests/run", json={"stack_id": "stk_1", "include_sensitivity": True}
    )
    assert refused.status_code == 400
    assert "which leg" in refused.json()["detail"]

    allowed = stack_client.post(
        "/stress-tests/run", json={"stack_id": "stk_1", "include_walk_forward": True}
    )
    assert allowed.status_code == 202, allowed.text


def test_a_stack_holding_a_DEPENDENT_leg_is_refused_WALK_FORWARD_up_front(
    stack_client, tmp_path, monkeypatch
):
    """🔴 A loss-recovery leg's PARENT is passed at launch and never written down, so a window
    replay would rebuild it with nothing to arm off — an empty book landing in the summary
    looking exactly like a rule that found no setups, with the whole account graded on a
    strategy set quietly one leg short.

    ⚠ Refused at the REQUEST, not ten minutes into the phase.
    ⚠ Watched RED by dropping the `requires_source` check from `rebuild_legs`.
    """
    with sqlite3.connect(lab_db.DB_PATH) as c:
        c.execute("UPDATE strategies SET requires_source=1 WHERE id='b_leg'")
    r = stack_client.post(
        "/stress-tests/run", json={"stack_id": "stk_1", "include_walk_forward": True}
    )
    assert r.status_code == 400
    assert "not recorded" in r.json()["detail"]


def test_the_trade_FLOOR_counts_the_COMBINED_book(stack_client, tmp_path):
    """⚠ Aaron's stated design is that sample size arrives at the PORTFOLIO level, so two legs
    that each trade too rarely to grade alone clear the floor together. That is one account's
    real trade history, not a trade count bought by loosening anything.

    Each leg here closes 60 trades — under the 100 floor — and the account closes 120.

    ⚠ Watched RED by counting the first leg's `trade_count` instead.
    """
    assert stack_client.post("/stress-tests/run", json={"stack_id": "stk_1"}).status_code == 202

    sdir = portfolio_runner.stack_dir("stk_1")
    (sdir / "shared_summary.json").write_text(
        json.dumps({"stack_id": "stk_1", "combined_kpis": {"trade_count": 12}})
    )
    r = stack_client.post("/stress-tests/run", json={"stack_id": "stk_1"})
    assert r.status_code == 422
    assert "this stack has 12" in r.json()["detail"]


def test_naming_NEITHER_target_is_a_400_at_the_endpoint(client):
    r = client.post("/stress-tests/run", json={})
    assert r.status_code == 400
    assert "exactly one" in r.json()["detail"]


# ── Walk-forward over a stack ─────────────────────────────────────────────────


def _book(*, trades: int, pnl: float, sharpe_seed: float = 1.0) -> dict:
    """A window's combined book, shaped the way `replay_window` returns one."""
    from datetime import date, timedelta

    # ⚠ Real calendar dates, walked forward — the first version formatted `2024-01-{i}` and
    # produced 2024-01-40 at forty trades, which reads as a code failure and is a fixture bug.
    day0 = date(2024, 1, 1)
    curve = [
        {
            "index": i + 1,
            "equity": 10_000 + pnl * (i + 1),
            "profit": pnl * sharpe_seed,
            "date": (day0 + timedelta(days=i)).isoformat(),
        }
        for i in range(max(trades, 1))
    ]
    return {
        "cancelled": False,
        "equity_curve": curve if trades else [],
        "daily_pnl": [],
        "kpis": {},
        "trade_count": trades,
        "net_pnl": pnl,
        "total_r": 1.0,
    }


@pytest.fixture
def wf(lab, monkeypatch):
    """A stack ready for walk-forward, with the REPLAY stubbed and every call recorded.

    ⚠ The replay is stubbed because a real one needs bar data and a live strategy package.
    What is under test here is the WINDOW LOOP — which legs go into each window, what balance
    each starts from, and what happens when one fails — none of which the replay decides.
    """
    _stack(lab, monkeypatch)
    calls: list[dict] = []

    def fake_replay(legs, settings, start_date, end_date, should_cancel=None):
        calls.append(
            {
                "legs": [leg["strategy_id"] for leg in legs],
                "account_size": settings["account_size"],
                "start": start_date,
                "end": end_date,
            }
        )
        return _book(trades=40, pnl=1_000.0)

    monkeypatch.setattr(portfolio_runner, "replay_window", fake_replay)
    return calls


def _run_wf(stress_test_id="st_wf", windows=2):
    import asyncio

    from services import stress_tester

    lab_db.insert_stress_test(
        {
            "stress_test_id": stress_test_id,
            "stack_id": "stk_1",
            "status": "running",
            "created_at": 1,
            "walk_forward_windows": windows,
        }
    )
    return asyncio.run(stress_tester.run_walk_forward_task(stress_test_id))


def test_EVERY_window_replays_the_WHOLE_stack_together(wf):
    """🔴 The point of the phase on a stack. Replaying the legs separately and adding their
    windows up drops contention in the one place the answer is meant to be hardest — and is
    not a portfolio result at all.

    ⚠ Watched RED by passing `legs[:1]` to the replay.
    """
    ok, err = _run_wf()
    assert (ok, err) == (True, None)
    assert len(wf) == 4, "two windows, an in-sample and an out-of-sample half each"
    for call in wf:
        assert call["legs"] == ["sos_fade", "b_leg"]


def test_every_window_starts_from_the_SAME_opening_balance(wf):
    """Aaron's call. A balance carried forward makes the last window's dollars enormous and the
    in-sample/out-of-sample comparison meaningless; a fresh account makes the windows
    comparable to each other, which is the only comparison this phase draws.

    ⚠ Watched RED by compounding the account size across windows.
    """
    _run_wf()
    assert {c["account_size"] for c in wf} == {10_000.0}


def test_the_two_halves_of_a_window_do_NOT_share_a_day(wf):
    """The split date used to be backtested on BOTH sides — a day the "unseen" half had
    already seen. Immaterial to the numbers and still a bar on the wrong side of the only line
    this phase draws."""
    _run_wf()
    is_end = wf[0]["end"]
    oos_start = wf[1]["start"]
    assert oos_start > is_end


def test_a_window_that_RAISES_is_recorded_as_a_failed_period_not_dropped(lab, monkeypatch):
    """A period that produced nothing keeps None on its side, which excludes it from the
    average — and the count is what lets the phase say *N of M failed* rather than reporting a
    degradation off whatever survived.

    ⚠ Watched RED by letting the exception escape: the whole phase dies on one bad window.
    """
    _stack(lab, monkeypatch)
    calls = {"n": 0}

    def flaky(legs, settings, start_date, end_date, should_cancel=None):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("no bars for this window")
        return _book(trades=40, pnl=500.0)

    monkeypatch.setattr(portfolio_runner, "replay_window", flaky)
    ok, err = _run_wf()
    assert ok is True, "one bad window must not kill the phase"
    st = lab_db.get_stress_test("st_wf")
    summary = st["walk_forward_summary"]
    # ⚠ The failed half leaves its keys ABSENT, which is the single-run path's own convention —
    # the scorer reads them with `.get()`, so absent excludes the window from the average. What
    # matters is that it is never a real `0.0`: that value passes through as a measurement and
    # draws a bar on the chart for a period nothing was measured on.
    assert summary[0].get("oos_sharpe") is None, "the failed half is UNMEASURED, never a 0.0"
    assert summary[0].get("oos_pnl") is None
    assert summary[0]["is_trades"] == 40, "the half that DID run is kept"


def test_EVERY_window_failing_is_a_FAILED_phase(lab, monkeypatch):
    """Not a clean summary of nothing. Reported as an error so the row can say so — otherwise
    grading reads the NULL summary as *not run* and neither credits nor penalises it, which is
    how a crashed phase used to cost a test nothing."""
    _stack(lab, monkeypatch)

    def always_fails(legs, settings, start_date, end_date, should_cancel=None):
        raise RuntimeError("nope")

    monkeypatch.setattr(portfolio_runner, "replay_window", always_fails)
    ok, err = _run_wf()
    assert ok is False
    assert "every walk-forward backtest failed" in err


def test_a_CANCELLED_stack_walk_forward_stops_between_windows(lab, monkeypatch):
    """⚠ Watched RED by dropping the cancellation check from the loop — the phase then runs
    every window after the Stop and writes a summary for a test the reader stopped."""
    _stack(lab, monkeypatch)
    from services import stress_tester

    monkeypatch.setattr(portfolio_runner, "replay_window", lambda *a, **k: _book(trades=9, pnl=1))
    monkeypatch.setattr(stress_tester, "is_cancelled", lambda _st: True)
    ok, err = _run_wf()
    assert (ok, err) == (False, "cancelled")
