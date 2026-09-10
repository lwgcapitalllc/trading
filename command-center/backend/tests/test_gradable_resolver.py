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
from concurrent.futures import Future
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
    sources: dict | None = None,
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
        # The leg this one arms off, by strategy id. Recorded on the MEMBER row since
        # 2026-09-07 — before that it lived only in the launch request, so a rebuilt stack
        # could not know it and the whole stack was refused a window replay.
        lab_db.add_stack_member("stk_1", f"r_{sid}", 1, i, source=(sources or {}).get(sid))

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


def _finish(stress_test_id: str) -> None:
    """Mark a started stress test complete, releasing its market lock.

    ⚠ A test that starts one and leaves it `running` blocks every later request in the same
    case with a 409 — which is the lock doing its job, and reads as the endpoint refusing the
    phase under test.
    """
    with sqlite3.connect(lab_db.DB_PATH) as c:
        c.execute(
            "UPDATE stress_tests SET status='complete' WHERE stress_test_id=?", (stress_test_id,)
        )


def test_BOTH_deep_phases_are_allowed_on_a_stack_and_sensitivity_quotes_its_own_plan(
    stack_client,
):
    """Walk-forward (2026-09-06) and sensitivity (2026-09-07) both replay the WHOLE stack, so
    both are allowed on one.

    ⚠ The estimate is asserted too, not just the status code. A 202 says the request was
    accepted; it says nothing about whether the modal is about to quote an experiment other
    than the one that will run — which is the defect this endpoint has already shipped once,
    quoting ~12 minutes for a ~69 minute job.

    ⚠ Watched RED by re-adding the old refusal, and again by pointing the estimate at the
    single-run counter (which reports 0 backtests here, the fixture's strategies having no
    param schema).

    🔴 **Each accepted test is FINISHED before the next request, and the first version of this
    was not** — it fired three requests back to back and passed, because a running stack test
    held no market lock at all (fixed 2026-09-07, `test_stack_stress_visibility.py`). So this
    test's premise was the defect. Needing the finish now is the lock working.
    """
    for phase in ("include_walk_forward", "include_sensitivity"):
        r = stack_client.post("/stress-tests/run", json={"stack_id": "stk_1", phase: True})
        assert r.status_code == 202, (phase, r.text)
        _finish(r.json()["stress_test_id"])

    r = stack_client.post(
        "/stress-tests/run", json={"stack_id": "stk_1", "include_sensitivity": True}
    )
    assert r.status_code == 202, r.text
    _finish(r.json()["stress_test_id"])
    note = next(n for n in r.json()["notes"] if n.startswith("Sensitivity"))
    # The stack's own risk budget and starting balance, four shifts each. The smallest-position
    # setting is 0.0 in this fixture, so every shift of it lands back on 0 and is dropped as a
    # no-op — which is the honest count, not a shortfall.
    assert "8 whole-stack replays" in note, note


def test_a_stack_holding_a_DEPENDENT_leg_is_refused_SENSITIVITY_up_front(stack_client):
    """Same refusal as walk-forward's, for the same reason and at the same moment.

    🔴 Sensitivity replays the stack once per shift, so a stack that cannot be REBUILT cannot be
    perturbed either — and rebuilding it without the parent produces a leg that arms off nothing
    and returns an empty book. Every shift would then be measured on an account quietly one leg
    short, and the phase would look like it worked.

    ⚠ **The subject narrowed on 2026-09-07 and this case is the half that SURVIVES.** The parent
    is recorded on the member row now, so a stack launched since then replays; what is still
    refused is one launched BEFORE, which has the dependency and cannot state it. The fixture
    records no source, which is exactly that stack.
    ⚠ Watched RED by narrowing the pre-check back to walk-forward only.
    """
    with sqlite3.connect(lab_db.DB_PATH) as c:
        c.execute("UPDATE strategies SET requires_source=1 WHERE id='b_leg'")
    r = stack_client.post(
        "/stress-tests/run", json={"stack_id": "stk_1", "include_sensitivity": True}
    )
    assert r.status_code == 400
    assert "not recorded" in r.json()["detail"]


def test_a_stack_holding_a_DEPENDENT_leg_is_refused_WALK_FORWARD_up_front(
    stack_client, tmp_path, monkeypatch
):
    """🔴 A loss-recovery leg rebuilt with nothing to arm off returns an EMPTY book, which lands
    in the summary looking exactly like a rule that found no setups — the whole account graded on
    a strategy set quietly one leg short.

    ⚠ **This is now the PRE-COLUMN stack only.** The parent is stored on the member row since
    2026-09-07, so a stack launched since then replays; this fixture records none, which is every
    stack launched before it. **The refusal keys on the STRATEGY needing a parent, never on the
    column being NULL** — an ordinary leg stores NULL too, so the column alone cannot tell an
    independent leg from an unrecorded dependency.
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


# ── Sensitivity over a STACK ──────────────────────────────────────────────────
#
# ⚠ A fail-watch against HEAD is VACUOUS for every case below — the stack path did not exist —
# so non-vacuity is by MUTATION, and each docstring names the mutation that turns it red.

SHIFTS_2 = [("+10%", 1.10), ("-10%", 0.90)]

_STACK_SETTINGS = {
    "account_size": 10_000.0,
    "risk_cap_pct": 10.0,
    "entry_floor_pct": 2.0,
    "start_date": "2024-01-01",
    "end_date": "2024-12-31",
}


def _schema(*names) -> dict:
    return {"param_schema": [{"name": n, "type": "float"} for n in names]}


def _plan(settings, legs, strategies, shifts=SHIFTS_2, budget=100):
    from services import stress_tester

    return stress_tester.stack_sensitivity_plan(settings, legs, strategies, shifts, budget)


def test_the_STACKS_OWN_settings_are_nudged_before_any_legs():
    """Aaron's call, and the whole reason this phase is different from the single-run one: the
    account risk budget, the starting balance and the smallest position it will still take are
    the only settings that belong to the ACCOUNT rather than to a strategy, so a portfolio
    answer spends its first replays on them.

    ⚠ Watched RED by appending the stack's settings after the legs' instead of before.
    """
    plan, _skipped, _dropped = _plan(
        _STACK_SETTINGS, [{"strategy_id": "a", "params": {"x": 1.0}}], {"a": _schema("x")}
    )
    assert list(dict.fromkeys(e["key"] for e in plan)) == [
        "risk_cap_pct",
        "account_size",
        "entry_floor_pct",
        "a.x",
    ]


def test_the_legs_take_TURNS_so_one_long_leg_cannot_eat_the_budget():
    """A flat pass in leg order spends the whole budget on the first leg when it carries twenty
    settings and the second carries three — and reports the account as though the second leg had
    no settings at all.

    ⚠ Watched RED by flattening the per-leg lists in order instead of interleaving them.
    """
    plan, _s, _d = _plan(
        {},
        [
            {"strategy_id": "a", "params": {"x": 1.0, "y": 2.0, "z": 3.0}},
            {"strategy_id": "b", "params": {"p": 4.0}},
        ],
        {"a": _schema("x", "y", "z"), "b": _schema("p")},
    )
    assert list(dict.fromkeys(e["key"] for e in plan)) == ["a.x", "b.p", "a.y", "a.z"]


def test_the_budget_stops_at_a_SETTING_and_never_skips_ahead_to_a_cheaper_one():
    """Two rules at once, and the second is the one worth the test.

    A setting that makes the cut gets ALL of its shifts — half a setting's shifts would put a
    max degradation on the record measured over a probe nobody chose. And once the budget stops,
    it STAYS stopped: squeezing in a later setting that happens to be cheaper would quietly
    reorder the priority the plan exists to enforce, with nothing on screen to show it happened.

    ⚠ `z` is deliberately affordable — one of its two shifts is out of bounds, so it costs 1 and
    the single remaining replay would fit it. It must still go unmeasured.
    ⚠ Watched RED by `continue`-ing past an unaffordable setting instead of stopping, and again
    by spending the budget shift by shift.
    """
    plan, _s, dropped = _plan(
        {},
        [{"strategy_id": "a", "params": {"x": 1.0, "y": 2.0, "z": 10.0}}],
        {
            "a": {
                "param_schema": [
                    {"name": "x", "type": "float"},
                    {"name": "y", "type": "float"},
                    {"name": "z", "type": "float", "max": 10.5},
                ]
            }
        },
        budget=3,
    )
    assert [e["key"] for e in plan] == ["a.x", "a.x"]
    assert dropped == ["a.y", "a.z"]


def test_a_refused_shift_names_WHICH_LEG_it_belonged_to():
    """A two-leg stack reporting *"ratio +10% (above the parameter's maximum)"* does not say
    whose ratio. The refusal messages are built off the name the planner hands down, so the name
    it hands down is the leg-qualified key.

    ⚠ Watched RED by passing the bare parameter name down instead of the key.
    """
    _plan_out, skipped, _d = _plan(
        {},
        [{"strategy_id": "b_leg", "params": {"ratio": 0.886}}],
        {"b_leg": {"param_schema": [{"name": "ratio", "type": "float", "max": 0.9}]}},
    )
    assert any(s.startswith("b_leg.ratio +10%") and "maximum" in s for s in skipped)


def test_a_stack_setting_that_was_never_recorded_is_ABSENT_from_the_record_entirely():
    """A setting the stack never carried a number for was not probed and was not skipped — it
    does not exist. Substituting 0 for it puts `account_size +10% (=0.0)` in the coverage record,
    which reads as a setting that WAS probed and turned out to be flat.

    🔴 The first version of this asserted only that the setting stayed out of the PLAN, and it
    survived both of its own mutations: a `None` is refused by `shifted_value` as non-numeric and
    a 0 is dropped as a no-op, so the plan comes out identical either way. A test whose two
    behaviours cannot produce different output is not testing the thing it names.

    ⚠ Watched RED by falling back to 0.0 for a missing setting.
    """
    plan, skipped, dropped = _plan(
        {"risk_cap_pct": 10.0, "account_size": None, "entry_floor_pct": None}, [], {}
    )
    assert {e["key"] for e in plan} == {"risk_cap_pct"}
    assert not [s for s in skipped + dropped if s.startswith(("account_size", "entry_floor"))]


def test_applying_a_shift_COPIES_and_touches_only_the_named_leg():
    """The plan is walked in a loop and every shift is measured against one baseline, so a
    mutation in place would make each replay carry every earlier shift and report the
    accumulation as the last setting's fragility.

    ⚠ Watched RED by assigning into the leg's own params dict.
    """
    from services import stress_tester

    legs = [
        {"strategy_id": "a", "params": {"x": 1.0}},
        {"strategy_id": "b", "params": {"x": 1.0}},
    ]
    settings = {"risk_cap_pct": 10.0}
    out_legs, out_settings = stress_tester.stack_shift_applied(
        legs, settings, {"scope": "leg", "leg": "a", "param": "x", "value": 1.1}
    )
    assert [leg["params"]["x"] for leg in out_legs] == [1.1, 1.0]
    assert [leg["params"]["x"] for leg in legs] == [1.0, 1.0], "the originals are untouched"
    assert out_settings is settings

    _legs2, out_settings2 = stress_tester.stack_shift_applied(
        legs, settings, {"scope": "stack", "leg": None, "param": "risk_cap_pct", "value": 11.0}
    )
    assert out_settings2["risk_cap_pct"] == 11.0
    assert settings["risk_cap_pct"] == 10.0


def _book_pf(pf: float, pnl: float = 1_000.0) -> dict:
    return {
        "cancelled": False,
        "equity_curve": [{"index": 1, "equity": 10_000.0 + pnl, "profit": pnl}],
        "daily_pnl": [],
        "kpis": {"profit_factor": pf, "net_pnl": pnl, "trade_count": 40},
        "trade_count": 40,
        "net_pnl": pnl,
        "total_r": 1.0,
    }


def _run_sens(stress_test_id="st_sens"):
    import asyncio

    from services import stress_tester

    lab_db.insert_stress_test(
        {
            "stress_test_id": stress_test_id,
            "stack_id": "stk_1",
            "status": "running",
            "created_at": 1,
        }
    )
    return asyncio.run(stress_tester.run_sensitivity_task(stress_test_id))


@pytest.fixture
def sens(lab, monkeypatch):
    """A stack ready for sensitivity, with the REPLAY stubbed and every call recorded.

    ⚠ The replay is stubbed because a real one needs bar data and a live strategy package. What
    is under test is the SHIFT LOOP — which settings move, one at a time, on how many legs, and
    what the phase records when one fails — none of which the replay decides.

    ⚠ The fixture's strategies carry NO param schema, so the plan is the stack's own settings
    alone: the risk budget and the starting balance, four shifts each. The smallest-position
    setting sits at 0.0, so every shift of it lands back on 0 and is dropped as a no-op.

    🔴 **The lab results directory is redirected, and that is not tidiness.** Since 2026-09-07 the
    phase WRITES each shift's book under `<results>/<stress_test_id>/shifts/`, so without this
    every run of this file would leave folders in the real `reports/lab` — the orphaned-directory
    backlog this app has already had to clear once, created by its own test suite.
    """
    from services import backtest_runner, stress_tester

    monkeypatch.setattr(backtest_runner, "LAB_RESULTS_DIR", lab / "reports")
    _stack(lab, monkeypatch)
    calls: list[dict] = []

    def fake_replay(legs, settings, start_date, end_date, should_cancel=None):
        calls.append(
            {
                "legs": [leg["strategy_id"] for leg in legs],
                "risk_cap_pct": settings.get("risk_cap_pct"),
                "account_size": settings.get("account_size"),
                "start": start_date,
                "end": end_date,
            }
        )
        return _book_pf(pf=2.0)

    monkeypatch.setattr(portfolio_runner, "replay_window", fake_replay)
    monkeypatch.setattr(stress_tester, "_shift_pool", lambda workers: _InlinePool())
    return calls


class _InlinePool:
    """Runs each shift in THIS process, so the ORCHESTRATION can be driven without spawning six
    interpreters — the ordering, the failure recording, the cancellation and the book writing are
    all decided in the parent.

    🔴 **DELIBERATELY LESS CAPABLE THAN THE REAL POOL, WHICH IS WHY IT IS NOT THE ONLY COVER.**
    It shares this process's memory, so it accepts a job that could not be pickled and a worker
    that reads a monkeypatched module — the two things that fail ONLY across a real process
    boundary. Rule 13 from its other end: a double SIMPLER than production hides a defect just as
    well as one more capable, and is harder to notice because nothing about it looks like a claim.
    `test_the_shifts_really_do_survive_a_PROCESS_boundary` drives the real one.
    """

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def submit(self, fn, job):
        fut: Future = Future()
        try:
            fut.set_result(fn(job))
        except BaseException as exc:  # noqa: BLE001 — a worker returns its failure, never raises
            fut.set_exception(exc)
        return fut

    def shutdown(self, wait=True, cancel_futures=False):
        return None


def test_every_NUDGE_replays_the_WHOLE_stack(sens):
    """🔴 The point of the phase on a stack. The other legs are in there competing for the same
    risk budget throughout, so what comes back is the ACCOUNT's number under that nudge.
    Perturbing a leg on its own and adding the answers up measures a strategy and labels it a
    portfolio.

    ⚠ Watched RED by replaying `legs[:1]`.
    """
    ok, err = _run_sens()
    assert (ok, err) == (True, None)
    assert len(sens) == 9, "a baseline, plus four shifts each of the risk budget and the balance"
    for call in sens:
        assert call["legs"] == ["sos_fade", "b_leg"]


def test_the_BASELINE_is_REPLAYED_through_the_same_path_not_read_off_the_stored_book(sens):
    """🔴 Degradation divides a shifted profit factor by the baseline's, so a baseline measured
    on a different code path reports the path difference as a setting's fragility. The stored
    book is close, and close is exactly what makes it dangerous.

    ⚠ Watched RED by taking the baseline from the stack's stored combined KPIs: eight calls
    instead of nine, and the first one already carrying a shift.
    """
    _run_sens()
    assert sens[0]["risk_cap_pct"] == 10.0
    assert sens[0]["account_size"] == 10_000.0


def test_only_ONE_setting_moves_per_replay(sens):
    """Moving several at once is a grid — a different and far larger experiment answering a
    different question.

    ⚠ Watched RED by applying each shift on top of the previous one instead of on the baseline.
    """
    _run_sens()
    base = sens[0]
    for call in sens[1:]:
        moved = [k for k in ("risk_cap_pct", "account_size") if call[k] != base[k]]
        assert len(moved) == 1, call


def test_a_STACK_is_probed_with_the_SAME_shifts_as_a_single_run(sens):
    """Both paths write the same degradation field and are read against the same grading
    thresholds, and the ±25% pair is usually the one that produces the maximum — so probing a
    stack with ±10% only would make every stack grade EASIER than every run, on one letter
    scale, with nothing saying so.

    ⚠ Watched RED by giving the stack path its own two-shift list: four replays and a baseline
    instead of eight and a baseline.
    """
    _run_sens()
    st = lab_db.get_stress_test("st_sens")
    assert sorted(st["sensitivity_summary"]["risk_cap_pct"]) == ["+10%", "+25%", "-10%", "-25%"]


def test_a_shift_that_RAISES_is_recorded_as_UNMEASURED_never_a_zero(lab, monkeypatch):
    """A shift that produced nothing is a hole in the coverage. Reporting a max degradation over
    whatever survived, with nothing saying how much did not, is the failure this module is
    written against — and a 0.0 in its place reads as *this setting was tested and did nothing*.

    ⚠ Watched RED by letting the exception escape (one bad shift kills the phase), and again by
    booking 0.0 for an unmeasurable shift.
    """
    from services import stress_tester

    _stack(lab, monkeypatch)
    calls = {"n": 0}

    def flaky(legs, settings, start_date, end_date, should_cancel=None):
        calls["n"] += 1
        if calls["n"] == 2:  # the first SHIFT; the baseline is call 1
            raise RuntimeError("no bars")
        return _book_pf(pf=2.0)

    monkeypatch.setattr(portfolio_runner, "replay_window", flaky)
    # ⚠ The shifts run in a POOL, so a stub set here cannot reach a worker in another process.
    # This drives the orchestration inline; the real boundary is covered by its own test.
    monkeypatch.setattr(stress_tester, "_shift_pool", lambda workers: _InlinePool())
    ok, err = _run_sens()
    assert ok is True, "one bad shift must not kill the phase"
    st = lab_db.get_stress_test("st_sens")
    first = st["sensitivity_summary"]["risk_cap_pct"]["+10%"]
    assert first["degradation"] is None
    assert first["profit_factor"] is None
    assert st["sensitivity_coverage"]["shifts_failed"] == ["risk_cap_pct +10%"]


def test_what_the_BUDGET_could_not_reach_is_recorded_with_what_it_did(lab, monkeypatch):
    """A page reading *"2 settings tested"* over a phase that never reached the other thirty is
    describing coverage that did not happen — the same reason the optimizer logs what its caps
    dropped.

    ⚠ Watched RED by dropping the extra coverage from the record.
    """
    from services import stress_tester

    _stack(lab, monkeypatch)
    monkeypatch.setattr(stress_tester, "_STACK_SENS_MAX_REPLAYS", 4)
    monkeypatch.setattr(
        portfolio_runner,
        "replay_window",
        lambda *a, **k: _book_pf(pf=2.0),
    )
    _run_sens()
    cov = lab_db.get_stress_test("st_sens")["sensitivity_coverage"]
    assert cov["replay_budget"] == 4
    assert cov["settings_out_of_budget"] == ["account_size", "entry_floor_pct"]


def test_an_unusable_baseline_profit_factor_books_NONE_for_every_shift(lab, monkeypatch):
    """A baseline of zero gives nothing to measure a change against. That is NOT ASSESSABLE, and
    a 0.0 there is the most reassuring answer available on a phase where nothing was measured.

    ⚠ Watched RED by dropping the usability check inside the shared scorer.
    """
    _stack(lab, monkeypatch)
    monkeypatch.setattr(
        portfolio_runner, "replay_window", lambda *a, **k: _book_pf(pf=0.0, pnl=0.0)
    )
    ok, _err = _run_sens()
    assert ok is True
    st = lab_db.get_stress_test("st_sens")
    assert st["sensitivity_max_degradation"] is None
    assert st["sensitivity_summary"]["risk_cap_pct"]["+10%"]["degradation"] is None


def test_CANCELLING_stops_the_remaining_replays(lab, monkeypatch):
    """A cancel that only relabels the row leaves every core busy — the optimizer shipped exactly
    that and then overwrote its own cancelled status when the work finished.

    ⚠ Watched RED by dropping the cancellation check between shifts.

    🔴 **PINNED TO ONE WORKER, AND THAT IS WHAT MAKES `== 2` AN HONEST NUMBER.** Since the shifts
    run in a pool, up to `workers` replays are in flight when a cancel lands and every one of them
    finishes — so on the shipped six-worker setting the true answer is *at most one batch more*,
    not *exactly one more*. At one worker the guarantee is exact and the assertion means what it
    says. **The bound under real parallelism is a different claim and gets its own test**
    (`test_a_CANCEL_starts_no_FURTHER_replays_beyond_the_batch_in_flight`); asserting `== 2`
    against six workers would just be wrong.
    """
    from services import stress_tester

    monkeypatch.setattr(stress_tester, "_STACK_SENS_WORKERS", 1)
    _stack(lab, monkeypatch)
    calls = {"n": 0}

    def cancelling(legs, settings, start_date, end_date, should_cancel=None):
        calls["n"] += 1
        if calls["n"] == 2:
            with sqlite3.connect(lab_db.DB_PATH) as c:
                c.execute(
                    "UPDATE stress_tests SET status='failed_cancelled' "
                    "WHERE stress_test_id='st_sens'"
                )
        return _book_pf(pf=2.0)

    monkeypatch.setattr(portfolio_runner, "replay_window", cancelling)
    # ⚠ Inline, for the reason above: a stub in this process cannot reach a pool worker.
    monkeypatch.setattr(stress_tester, "_shift_pool", lambda workers: _InlinePool())
    ok, err = _run_sens()
    assert (ok, err) == (False, "cancelled")
    assert calls["n"] == 2, "it stops rather than finishing the plan"


def test_two_legs_of_the_SAME_strategy_are_refused(lab, monkeypatch):
    """A shift is recorded under `<strategy>.<setting>`, so two legs of one strategy would file
    both under one key — the second silently overwriting the first, and the phase grading on
    whichever landed last.

    ⚠ The duplicate is INJECTED, because the replay itself already requires unique leg names and
    the app cannot build one today. That is the point: the day it can, the failure is silent.
    ⚠ Watched RED by removing the duplicate check.
    """
    from services import gradable, stress_tester

    _stack(lab, monkeypatch)
    monkeypatch.setattr(
        gradable,
        "rebuild_legs",
        lambda _sid: [
            {"strategy_id": "sos_fade", "params": {}, "class_name": "X"},
            {"strategy_id": "sos_fade", "params": {}, "class_name": "X"},
        ],
    )
    monkeypatch.setattr(portfolio_runner, "replay_window", lambda *a, **k: _book_pf(pf=2.0))
    assert stress_tester is not None
    ok, err = _run_sens()
    assert ok is False
    assert "same strategy" in (err or "")


# ── A dependent leg's parent is RECORDED, so the stack can be replayed ────────────────────


def test_a_dependent_leg_with_a_RECORDED_parent_is_rebuilt_and_carries_it(lab, monkeypatch):
    """🔴 The whole point of the column. `LegSpec.source` is what makes the leg arm off its
    parent's closed trades; a rebuilt leg missing it arms off nothing and returns an empty book
    that reads as a rule with no setups.

    ⚠ It asserts the rebuilt leg CARRIES the parent, not merely that the rebuild succeeded — a
    rebuild that silently dropped the field would pass the second and produce the empty book.
    ⚠ Watched RED by dropping `source` from the rebuilt leg dict.
    """
    _stack(lab, monkeypatch, sources={"b_leg": "sos_fade"})
    with sqlite3.connect(lab_db.DB_PATH) as c:
        c.execute("UPDATE strategies SET requires_source=1 WHERE id='b_leg'")

    legs = gradable.rebuild_legs("stk_1")
    by_id = {leg["strategy_id"]: leg for leg in legs}
    assert by_id["b_leg"]["source"] == "sos_fade"


def test_an_ORDINARY_leg_carries_no_source_at_all(lab, monkeypatch):
    """⚠ Absent rather than `None`. The runner reads it with `.get()`, so both mean the same
    thing — and stating it once is one fewer way for the two to disagree.

    ⚠ Watched RED by emitting the key unconditionally.
    """
    _stack(lab, monkeypatch)
    assert all("source" not in leg for leg in gradable.rebuild_legs("stk_1"))


def test_a_recorded_parent_that_is_NOT_IN_THE_STACK_is_refused(lab, monkeypatch):
    """The leg would arm off nothing, which is the same empty book by another route.

    ⚠ `run_stack` refuses a dangling source too — but that arrives minutes into a replay, and
    names the simulator rather than the stack. This one arrives before the phase starts.
    ⚠ Watched RED by dropping the membership check.
    """
    _stack(lab, monkeypatch, sources={"b_leg": "ghost_strategy"})
    with sqlite3.connect(lab_db.DB_PATH) as c:
        c.execute("UPDATE strategies SET requires_source=1 WHERE id='b_leg'")

    with pytest.raises(gradable.NotGradable) as exc:
        gradable.rebuild_legs("stk_1")
    assert "ghost_strategy" in exc.value.reason
    assert "not in this stack" in exc.value.reason


def test_a_stack_with_a_RECORDED_parent_is_ACCEPTED_for_both_deep_phases(
    stack_client, tmp_path, monkeypatch
):
    """🔴 The gap this closes, driven through the endpoint rather than the helper. Before the
    column, a stack holding a loss-recovery leg was refused walk-forward AND sensitivity outright
    — the two phases that make a stack's grade mean anything.

    ⚠ Watched RED by keeping the old blanket `requires_source` refusal.
    """
    with sqlite3.connect(lab_db.DB_PATH) as c:
        c.execute("UPDATE strategies SET requires_source=1 WHERE id='b_leg'")
        c.execute("UPDATE stack_members SET source='sos_fade' WHERE run_id='r_b_leg'")

    for phase in ("include_walk_forward", "include_sensitivity"):
        r = stack_client.post("/stress-tests/run", json={"stack_id": "stk_1", phase: True})
        assert r.status_code == 202, r.json()
        _finish(r.json()["stress_test_id"])


def test_the_LAUNCH_records_the_recovery_parent_on_the_member_row(client, monkeypatch, tmp_path):
    """🔴 Rule 7 — the column is only worth having if the thing that creates a stack WRITES it.
    A rebuild reading a column nobody fills refuses every stack for ever, which looks exactly
    like the bug it replaced.

    ⚠ Watched RED by dropping `source=` from the router's `add_stack_member` call.
    """
    from routers import stacks as stacks_router

    launched: dict = {}
    monkeypatch.setattr(
        stacks_router.portfolio_runner,
        "launch",
        lambda sid, legs, settings: launched.update(legs=legs),
    )
    for sid in ("sos_fade", "loss_recovery"):
        _seed_strategy(sid)
    with sqlite3.connect(lab_db.DB_PATH) as c:
        c.execute("UPDATE strategies SET requires_source=1 WHERE id='loss_recovery'")

    r = client.post(
        "/backtests/stack",
        json={
            "strategy_ids": ["sos_fade"],
            "instrument": "XAUUSD",
            "bar_type": "Minute",
            "bar_value": 15,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "mode": "shared",
            "account_size": 10_000.0,
            "risk_cap_pct": 10.0,
            "recovery_parent": "sos_fade",
        },
    )
    # 202, not "any 2xx": a shared launch that never reached the runner would still answer,
    # and a loose check would call that a pass.
    assert r.status_code == 202, r.text
    stack_id = r.json()["stack_id"]
    assert launched["legs"], "the launch never reached the runner"

    with sqlite3.connect(lab_db.DB_PATH) as c:
        c.row_factory = sqlite3.Row
        rows = c.execute(
            "SELECT m.source AS source, r.strategy_id AS sid FROM stack_members m "
            "JOIN backtest_runs r ON r.run_id = m.run_id WHERE m.stack_id = ?",
            (stack_id,),
        ).fetchall()
    by_sid = {row["sid"]: row["source"] for row in rows}
    assert by_sid["loss_recovery"] == "sos_fade"
    assert by_sid["sos_fade"] is None


# ── A stack shift's own book — the drill-down a stack shift has no run row for ────────────


def _shift_dir(lab, stress_test_id="st_sens"):
    return lab / "reports" / stress_test_id / "shifts"


def test_two_shift_labels_that_differ_only_by_a_DROPPED_character_get_different_slugs():
    """🔴 THE DEFECT THIS CASE WAS WRITTEN FOR WAS MINE, and it was found by looking at the files
    rather than by reading the code. The first slug ended with `.strip("_")`, which deleted the
    underscore the substitution had just put there in place of the `%` — so `+25%` and `+25` both
    became `account_size__+25`, and the second shift's book would have overwritten the first's in
    silence.

    ⚠ **No shift label today lacks a `%`, so it could not fire** — and the docstring positively
    claimed the collision was impossible, which is exactly the shape that stops the next reader
    looking.
    ⚠ Watched RED by restoring the trailing strip.
    """
    from services.stress_tester import stack_shift_slug

    assert stack_shift_slug("account_size", "+25%") != stack_shift_slug("account_size", "+25")
    assert stack_shift_slug("a.b", "+10%") != stack_shift_slug("a.b", "-10%")
    # And it stays a legal single path segment whatever the setting is called.
    assert "/" not in stack_shift_slug("a/b", "+10%")


def test_every_SHIFT_stores_its_own_account_book_and_so_does_the_BASELINE(sens, lab):
    """🔴 A stack shift spawns no child run, so without a stored book there is nothing to open.

    ⚠ **The baseline is stored too, and it is not decoration**: every shift's number is a RATIO
    against it, so a reader opening a shift with nothing to compare it to holds half a
    measurement. It is the baseline THIS phase replayed, not the stack's own stored book, which
    was measured on a different code path.
    ⚠ Watched RED by writing nothing, and again by skipping the baseline.
    """
    ok, err = _run_sens()
    assert (ok, err) == (True, None)

    stored = sorted(p.name for p in _shift_dir(lab).iterdir())
    assert "__baseline__" in stored
    # Eight shifts: four each of the risk budget and the starting balance.
    assert len([n for n in stored if n != "__baseline__"]) == 8
    one = _shift_dir(lab) / stored[0]
    assert {p.name for p in one.iterdir()} == {
        "equity_curve.json",
        "daily_pnl.json",
        "kpis.json",
    }


def test_the_stored_record_names_the_BOOK_and_it_is_NOT_the_run_id(sens):
    """🔴 TWO FIELDS, DELIBERATELY. `run_id` means *there is a lab run row you can navigate to*;
    `book` means *a stored account book you can read*. A stack shift has the second and never the
    first, and folding them into one field would make a page that follows `run_id` request a run
    that does not exist.

    ⚠ Watched RED by writing the slug into `run_id`.
    """
    _run_sens()
    st = lab_db.get_stress_test("st_sens")
    # ⚠ `get_stress_test` already parses this column — reading it back through
    # `json.loads` is a second parse of a dict.
    sensitivity = st["sensitivity_summary"]
    shift = sensitivity["risk_cap_pct"]["+10%"]
    assert shift["run_id"] is None
    assert shift["book"] and shift["book"].startswith("risk_cap_pct__")


def test_a_shift_whose_book_could_NOT_be_written_records_no_link(sens, monkeypatch):
    """⚠ A slug on a record whose book is not on disk is a link that opens nothing, and *cannot
    open* would then be indistinguishable from *was never stored*.

    ⚠ **The phase still succeeds**, because the score comes off the KPIs in memory — a phase that
    died because a drill-down could not be written would have traded a measurement for a link.
    ⚠ Watched RED by recording the slug unconditionally.
    """
    from services import stress_tester

    monkeypatch.setattr(stress_tester, "write_shift_book", lambda *a, **k: False)
    ok, err = _run_sens()
    assert (ok, err) == (True, None)

    sensitivity = lab_db.get_stress_test("st_sens")["sensitivity_summary"]
    assert all(shift["book"] is None for param in sensitivity.values() for shift in param.values())


def test_the_book_writer_NEVER_raises_and_says_it_failed(lab, monkeypatch):
    """A drill-down is a convenience; it may never take a phase down with it. The return value is
    what the caller reads, so a silent False is not silent to the code that matters.

    ⚠ Watched RED by letting the write raise.
    """
    from services import backtest_runner, stress_tester

    # A FILE where the directory has to go — `mkdir` on it raises, which is the realistic
    # failure (a full disk, a read-only mount) without needing either.
    blocker = lab / "blocked"
    blocker.write_text("not a directory")
    monkeypatch.setattr(backtest_runner, "LAB_RESULTS_DIR", blocker)
    assert stress_tester.write_shift_book("st_x", "slug", _book_pf(pf=1.0)) is False


def test_reading_a_slug_that_was_never_stored_is_None_not_an_empty_book(lab, monkeypatch):
    """⚠ An account that traded nothing and a book nobody kept are different answers, and the
    router turns only the second into a 404.

    ⚠ Watched RED by returning an empty book for a missing directory.
    """
    from services import backtest_runner, stress_tester

    monkeypatch.setattr(backtest_runner, "LAB_RESULTS_DIR", lab / "reports")
    assert stress_tester.read_shift_book("st_x", "nothing_here") is None


def test_a_CORRUPT_half_of_a_book_still_reports_the_readable_half(lab, monkeypatch):
    """The KPIs are what the reader came for; an unreadable curve should not withhold them.

    ⚠ Watched RED by returning None when any file fails to parse.
    """
    from services import backtest_runner, stress_tester

    monkeypatch.setattr(backtest_runner, "LAB_RESULTS_DIR", lab / "reports")
    stress_tester.write_shift_book("st_x", "slug", _book_pf(pf=1.5))
    (lab / "reports" / "st_x" / "shifts" / "slug" / "equity_curve.json").write_text("{oops")

    book = stress_tester.read_shift_book("st_x", "slug")
    assert book["kpis"]["profit_factor"] == 1.5
    assert book["equity_curve"] == []


# ── The endpoint ─────────────────────────────────────────────────────────────────────────


@pytest.fixture
def book_client(client, lab, monkeypatch):
    """The API, with one stored shift book on disk."""
    from services import backtest_runner, stress_tester

    monkeypatch.setattr(backtest_runner, "LAB_RESULTS_DIR", lab / "reports")
    lab_db.insert_stress_test(
        {"stress_test_id": "st_b", "stack_id": "stk_1", "status": "complete", "created_at": 1}
    )
    stress_tester.write_shift_book("st_b", "risk_cap_pct__+10_", _book_pf(pf=2.5))
    stress_tester.write_shift_book("st_b", "__baseline__", _book_pf(pf=2.0))
    return client


_BOOK_URL = "/stress-tests/st_b/shift-book"


def test_a_stored_shift_book_is_served(book_client):
    """⚠ Watched RED by dropping the route."""
    r = book_client.get(f"{_BOOK_URL}/risk_cap_pct__+10_")
    assert r.status_code == 200
    assert r.json()["kpis"]["profit_factor"] == 2.5
    assert r.json()["slug"] == "risk_cap_pct__+10_"


def test_the_BASELINE_is_servable_through_the_same_route(book_client):
    """A shift's number is a ratio against it, so the reader needs both from one place.

    ⚠ Watched RED by refusing the baseline slug.
    """
    r = book_client.get(f"{_BOOK_URL}/__baseline__")
    assert r.status_code == 200
    assert r.json()["kpis"]["profit_factor"] == 2.0


def test_an_unknown_SLUG_is_a_404_that_says_only_a_stack_keeps_one(book_client):
    """404 covers a phase that predates this, a write that failed, and a slug naming nothing —
    all of which are *not stored*, and none of which is an empty book.

    ⚠ Watched RED by returning an empty book instead of raising.
    """
    r = book_client.get(f"{_BOOK_URL}/never_stored")
    assert r.status_code == 404
    assert "STACK" in r.json()["detail"]


def test_an_unknown_STRESS_TEST_is_a_404_before_the_disk_is_touched(book_client):
    """⚠ Watched RED by dropping the row check — a slug under a made-up test id would then read
    the filesystem and answer *no stored book*, naming the wrong thing as missing.
    """
    r = book_client.get("/stress-tests/st_nope/shift-book/__baseline__")
    assert r.status_code == 404
    assert r.json()["detail"] == "Stress test not found"


# ── the shifts run in a POOL, and the estimate stopped double-counting (2026-09-09) ───────────
#
# 🔴 The phase was serial because a note said a stack "cannot use that path" — which is a fact
# about where ONE replay runs, not about whether two replays depend on each other. They do not.
# MEASURED on the live pairing before this landed: six at once ran 3.61x faster than six in a row
# and every one returned an identical trade list.


def _rows(*spans):
    """Leg rows carrying only the two timestamps the estimate reads."""
    return [{"started_at": s, "completed_at": e} for s, e in spans]


def test_the_estimate_reads_the_SPAN_when_the_legs_ran_TOGETHER():
    """🔴 THE DEFECT THIS FIXES, AND IT SCALED WITH LEG COUNT. On a shared stack the legs run on
    one merged clock, so every leg row carries the SAME start and end — and the old code ADDED
    them. MEASURED on the live pairing: two rows of 498s each, quoted as 16.6 minutes for a replay
    that took 8.3.

    MUTATION: sum the durations instead and this goes red.
    """
    from services import stress_tester

    together = _rows((1000, 1600), (1000, 1600))
    assert stress_tester._stack_replay_minutes(together) == pytest.approx(10.0)


def test_the_estimate_still_ADDS_when_the_legs_ran_ONE_AT_A_TIME():
    """The other shape, and the reason this is read off the TIMESTAMPS rather than off a mode
    flag: a screen really does run its legs sequentially, and there the total IS the sum. Neither
    shape has to be declared to the function.
    """
    from services import stress_tester

    sequential = _rows((1000, 1600), (1600, 2200))
    assert stress_tester._stack_replay_minutes(sequential) == pytest.approx(20.0)


def test_a_REUSED_leg_stamped_days_ago_cannot_inflate_the_estimate():
    """🔴 THE CASE THAT MADE THE FIRST FIX WRONG. A screen may reuse a finished standalone run,
    whose row is stamped from whenever it originally ran — so the raw span measures the gap since
    that afternoon rather than any work. Here the span is 25 hours and the real work is 20 minutes.

    MUTATION: return the span alone and this goes red.
    """
    from services import stress_tester

    stale = _rows((0, 600), (89_400, 90_000))
    assert stress_tester._stack_replay_minutes(stale) == pytest.approx(20.0)


def test_the_estimate_ACCOUNTS_for_the_pool_rather_than_quoting_the_serial_wait():
    """A modal quoting the serial figure over a parallel phase is this app's own ~12-for-69
    defect pointing the other way — it would now over-state by the worker count.

    ⚠ It is NOT divided by the worker count: MEASURED at about 0.6 of it, because this is
    CPU-bound Python on half as many physical cores as logical ones and macOS spawns rather than
    forks. Asserting a full Nx speed-up here would pin a number the machine cannot produce.

    MUTATION: drop the divisor and this goes red.
    """
    from services import stress_tester

    assert stress_tester._effective_parallelism() > 1.0
    assert stress_tester._effective_parallelism() < stress_tester._STACK_SENS_WORKERS


def test_the_results_are_assembled_in_PLAN_order_not_COMPLETION_order(lab, monkeypatch):
    """🔴 THE PLAN IS A PRIORITY — the account's own budget first, then the legs taking turns — so
    a coverage record shuffled by whichever worker happened to finish first would misreport what
    the replay budget was spent on.

    🔴 **THE FIRST VERSION OF THIS COULD NOT HAVE CAUGHT IT.** It drove the phase through the
    inline pool, where completion order IS submission order, so *walk the plan* and *take them as
    they land* produce the identical list and the mutation survived. **A test whose inputs cannot
    distinguish the behaviours it names is describing a system where the thing under test does
    nothing** — the trap this file already records twice. It now hands results back DELIBERATELY
    REVERSED, which is the only arrangement where the two answers differ.

    MUTATION: return `list(done.values())` instead of walking the plan and this goes red.
    """
    from services import stress_tester

    _stack(lab, monkeypatch)
    lab_db.insert_stress_test(
        {"stress_test_id": "st_sens", "stack_id": "stk_1", "status": "running", "created_at": 1}
    )
    monkeypatch.setattr(portfolio_runner, "replay_window", lambda *a, **k: _book_pf(pf=2.0))
    monkeypatch.setattr(stress_tester, "_shift_pool", lambda w: _ReversedPool())

    settings = lab_db.get_stack_settings("stk_1")
    legs = gradable.rebuild_legs("stk_1")
    plan, _skipped, _oob = stress_tester.stack_sensitivity_plan(
        settings,
        legs,
        {leg["strategy_id"]: {} for leg in legs},
        stress_tester.sensitivity_shifts("python"),
        20,
    )
    assert len(plan) > 2, "one shift cannot be out of order"
    monkeypatch.setattr(stress_tester, "_STACK_SENS_WORKERS", len(plan))

    results = stress_tester._replay_shifts(plan, legs, settings, "st_sens")

    assert results is not None
    got = [(r["entry"]["key"], r["entry"]["label"]) for r in results]
    want = [(e["key"], e["label"]) for e in plan]
    assert got == want, "the record must follow the PLAN, not the order the replays landed in"


class _ReversedPool(_InlinePool):
    """An inline pool that hands its finished futures back in REVERSE submission order.

    ⚠ **It exists to make one test able to fail.** A real pool completes in whatever order the
    workers finish, which is not submission order; an inline stand-in that resolves as it submits
    cannot express that, so it silently agrees with a bug that takes results as they land.
    """

    def __init__(self):
        self._order: list = []

    def submit(self, fn, job):
        fut = super().submit(fn, job)
        self._order.insert(0, fut)
        return fut


def test_the_shifts_really_do_survive_a_PROCESS_boundary(lab, monkeypatch):
    """🔴 THE ONE THING THE INLINE POOL CANNOT CHECK, AND THE REASON IT IS NOT THE ONLY COVER.

    Every other sensitivity test here swaps the pool for an inline stand-in so the orchestration
    can be driven without spawning six interpreters. That stand-in shares this process's memory,
    so it would happily accept a job that cannot be PICKLED and a worker that reads a
    monkeypatched module — **the exact two things that fail only across a real boundary.** Rule 13
    from its other end: a double SIMPLER than production hides a defect just as well as one more
    capable, and is harder to notice because nothing about it looks like a claim.

    So this one drives the REAL pool. It does not need a real replay to be meaningful: the legs
    resolve to a strategy class that does not exist in a worker, so each shift comes back as a
    RECORDED FAILURE — which is only possible if the job pickled in, the worker ran, and the
    result pickled out. A boundary that could not carry them would raise instead.

    ⚠ It asserts the failures are RECORDED rather than dropped, which is the contract a hole in
    the coverage depends on.
    """
    from services import stress_tester

    _stack(lab, monkeypatch)
    settings = lab_db.get_stack_settings("stk_1")
    legs = gradable.rebuild_legs("stk_1")
    plan, _skipped, _oob = stress_tester.stack_sensitivity_plan(
        settings,
        legs,
        {leg["strategy_id"]: {} for leg in legs},
        # ⚠ At least one whole SETTING's worth. The budget is spent a setting at a time and
        # STOPS rather than part-funding one, so a cap below the shift count plans NOTHING.
        stress_tester.sensitivity_shifts("python"),
        8,
    )
    assert plan, "no plan means this test asserts nothing"

    monkeypatch.setattr(stress_tester, "_STACK_SENS_WORKERS", 2)
    results = stress_tester._replay_shifts(plan, legs, settings, "st_sens")

    assert results is not None, "the phase must not report itself cancelled"
    assert len(results) == len(plan), "every shift must come back, failed or not"
    assert all(r["ok"] is False for r in results), (
        "these legs cannot resolve in a worker, so every shift must be RECORDED as failed — "
        "an ok result here means the job never crossed a boundary at all"
    )


def test_a_CANCEL_starts_no_FURTHER_replays_beyond_the_batch_in_flight(lab, monkeypatch):
    """🔴 THE BOUND PARALLELISM CHANGED, MEASURED RATHER THAN LEFT IMPLIED.

    The serial loop stopped on the very next shift. A pool cannot: whatever is already running
    runs to completion, so a cancel costs at most one batch. **What must still hold is that
    nothing NEW is started** — which is why at most `workers` replays are in flight at once and
    why the queue is topped up only AFTER the cancellation check. Queuing the whole plan up front
    would make *stop the remaining replays* stop nothing, because `cancel_futures` can only drop
    what has not begun.

    ⚠ **The first version of this test was named for that bound and never measured it** — it
    asserted only that an already-cancelled phase reports cancelled, which a dozen mutations
    survive. It counts the replays now.

    MUTATION: submit the whole plan up front, or top up before the cancellation check, and the
    count reaches the plan length instead of one batch.
    """
    from services import stress_tester

    _stack(lab, monkeypatch)
    lab_db.insert_stress_test(
        {"stress_test_id": "st_sens", "stack_id": "stk_1", "status": "running", "created_at": 1}
    )

    workers = 2
    monkeypatch.setattr(stress_tester, "_STACK_SENS_WORKERS", workers)
    monkeypatch.setattr(stress_tester, "_shift_pool", lambda w: _InlinePool())

    calls = {"n": 0}

    def cancelling(legs, settings, start_date, end_date, should_cancel=None):
        calls["n"] += 1
        if calls["n"] == 1:
            with sqlite3.connect(lab_db.DB_PATH) as c:
                c.execute(
                    "UPDATE stress_tests SET status='failed_cancelled' "
                    "WHERE stress_test_id='st_sens'"
                )
        return _book_pf(pf=2.0)

    monkeypatch.setattr(portfolio_runner, "replay_window", cancelling)

    settings = lab_db.get_stack_settings("stk_1")
    legs = gradable.rebuild_legs("stk_1")
    plan, _skipped, _oob = stress_tester.stack_sensitivity_plan(
        settings,
        legs,
        {leg["strategy_id"]: {} for leg in legs},
        stress_tester.sensitivity_shifts("python"),
        20,
    )
    assert len(plan) > workers + 2, "the plan must outrun one batch or the bound is untestable"

    results = stress_tester._replay_shifts(plan, legs, settings, "st_sens")

    assert results is None, "a cancelled phase must report cancelled"
    assert calls["n"] <= workers, (
        f"a cancel must start nothing new: {calls['n']} replays ran against a batch of "
        f"{workers} and a plan of {len(plan)}"
    )
