"""A stack's stress test must be VISIBLE and must hold a LOCK.

🔴 Both of these were joined for through `run_id`, which a stack-targeted row does not carry, so
an INNER JOIN dropped every stack row in silence. MEASURED 2026-09-07 before the fix:

    list_stress_tests()          -> ['st_run']                        (the stack row missing)
    running_stress_test_markets  -> {futures: False, forex: False}    (a RUNNING stack, no lock)

The second is the dangerous one. `POST /stress-tests/run` refuses when its market is locked, so
with the lock silently open a second stress test could start beside a running one, on one box
driving one terminal.

⚠ Every case here was WATCHED RED against HEAD except the two marked as forward guards in their
own docstrings.
"""

from __future__ import annotations

import sqlite3

import pytest
from services import lab_db


def _seed(*, runner: str = "python") -> None:
    lab_db.upsert_strategy(
        {
            "id": "sos",
            "name": "SOS Fade",
            "class_name": "SosStrategy",
            "source_path": "strategies/python/sos_fade",
            "runner": runner,
            "scanned_at": 1,
            "source_hash": "h",
        }
    )
    lab_db.insert_run(
        {
            "run_id": "r1",
            "strategy_id": "sos",
            "instrument": "XAUUSD.p",
            "params": {},
            "bar_type": "Minute",
            "bar_value": 15,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "commission_per_side": 0.0,
            "slippage_ticks": 0,
            "status": "complete",
            "created_at": 1,
            "runner": runner,
        }
    )
    lab_db.insert_stack(
        {
            "stack_id": "stk",
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
            "risk_cap_pct": 10.0,
            "entry_floor_pct": 0.0,
        }
    )
    lab_db.add_stack_member("stk", "r1", 1, 0)


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "lab.db")
    lab_db.init_db()
    _seed()
    return tmp_path


def _stack_test(**over) -> None:
    row = {
        "stress_test_id": "st_stack",
        "stack_id": "stk",
        "status": "running",
        "created_at": 2,
        "runner": "python",
        "target_label": "SOS Fade + XLEG",
    }
    row.update(over)
    lab_db.insert_stress_test(row)


def _run_test(**over) -> None:
    row = {
        "stress_test_id": "st_run",
        "run_id": "r1",
        "status": "complete",
        "created_at": 1,
        "runner": "python",
        "target_label": "SOS Fade",
    }
    row.update(over)
    lab_db.insert_stress_test(row)


# ── The list ──────────────────────────────────────────────────────────────────


def test_a_stacks_stress_test_APPEARS_in_the_list(lab):
    """It did not, for as long as a stack could be stress tested at all. A row missing from the
    list reads as a test that was never started — the page has no way to show a result it cannot
    fetch, and no way to say why.

    ⚠ Watched RED against HEAD (the row was absent entirely).
    """
    _stack_test()
    _run_test()
    assert {r["stress_test_id"] for r in lab_db.list_stress_tests()} == {"st_stack", "st_run"}


def test_a_stacks_row_carries_the_STACKS_instrument_and_the_stored_label(lab):
    """A stack has no run and no single strategy, so both fields used to come back empty. The
    label is built ONCE, in `services.gradable`, and stored — never rebuilt in SQL here, which
    would be a second statement of what a stack is called.

    ⚠ Watched RED against HEAD.
    """
    _stack_test()
    row = next(r for r in lab_db.list_stress_tests() if r["stress_test_id"] == "st_stack")
    assert row["instrument"] == "XAUUSD.p"
    assert row["strategy_name"] == "SOS Fade + XLEG"


def test_a_stacks_row_names_NO_strategy_id(lab):
    """🔴 ON PURPOSE. A stack is not a strategy, and filling this with a leg's id would name one
    strategy as the subject of an account's result — the same thing the nullable `run_id` exists
    to prevent one layer down.

    ⚠ Watched RED by coalescing the stack's first leg into the field.
    """
    _stack_test()
    row = next(r for r in lab_db.list_stress_tests() if r["stress_test_id"] == "st_stack")
    assert row["strategy_id"] is None


def test_a_single_run_keeps_its_LIVE_strategy_name(lab):
    """The stored label is the LAST fallback, so renaming a strategy still shows through on its
    old tests. A stack has no live name to read; a run does.

    ⚠ Watched RED by putting the stored label ahead of the joined name.
    """
    _run_test(target_label="whatever this run was called when it started")
    with sqlite3.connect(lab_db.DB_PATH) as c:
        c.execute("UPDATE strategies SET name='SOS Fade (renamed)' WHERE id='sos'")
    row = next(r for r in lab_db.list_stress_tests() if r["stress_test_id"] == "st_run")
    assert row["strategy_name"] == "SOS Fade (renamed)"


# ── The lock ──────────────────────────────────────────────────────────────────


def test_a_RUNNING_stack_stress_test_LOCKS_its_market(lab):
    """🔴 The severe half. The endpoint refuses a new test when its market is locked, so a lock
    that cannot see a stack lets a second test start beside a running one.

    ⚠ Watched RED against HEAD ({futures: False, forex: False} with the stack running).
    """
    _stack_test()
    assert lab_db.running_stress_test_markets()["forex"] is True


def test_the_stack_locks_its_market_while_naming_NO_run_id(lab):
    """The id list is what the page points at to say which run is blocking; a stack has none. The
    BOOLEANS are the lock, and they must not depend on that list being non-empty.

    ⚠ Watched RED by appending a null id (the page then links to nothing).
    """
    _stack_test()
    locks = lab_db.running_stress_test_markets()
    assert locks["run_ids"] == []
    assert locks["forex"] is True


def test_the_lock_reads_the_platform_OFF_THE_ROW_not_off_todays_strategy(lab):
    """The row records the platform the test was STARTED on. Deriving it from the strategy means a
    re-scan onto another runner moves the lock of a test already in flight — freeing a platform
    that is genuinely busy.

    ⚠ Watched RED by dropping the row's runner from the COALESCE.
    """
    _stack_test(runner="ninjatrader")
    locks = lab_db.running_stress_test_markets()
    assert locks["futures"] is True
    assert locks["forex"] is False


def test_a_row_written_BEFORE_the_column_still_locks_through_the_join(lab):
    """A test in flight across the upgrade has no stored runner, and the join is kept as the
    fallback for exactly that. Falling back to the NT8 default instead would move an in-flight
    python test onto the futures lock.

    ⚠ Watched RED by dropping the joined runner from the COALESCE.
    """
    _run_test(status="running_wf", runner=None)
    locks = lab_db.running_stress_test_markets()
    assert locks["forex"] is True
    assert locks["futures"] is False


# ── The grade ─────────────────────────────────────────────────────────────────


def test_a_stacks_GRADE_is_never_filed_under_a_legs_strategy(lab):
    """🔴 A stack's grade judges a whole strategy set sharing one balance and one risk budget.
    Hanging that letter on one leg claims evidence about that strategy which nothing measured.

    ⚠ It PASSES against HEAD and is a FORWARD guard, stated as one: a stack row has a NULL
    `run_id`, so the inner join already dropped it and the right answer came out by accident. The
    exclusion is written now so the next person to widen this query gets a red test instead of
    silence. Watched RED by LEFT-joining the stack's legs in.
    """
    _stack_test(status="complete")
    _run_test()
    with sqlite3.connect(lab_db.DB_PATH) as c:
        c.execute("UPDATE stress_tests SET grade='A' WHERE stress_test_id='st_stack'")
        c.execute("UPDATE stress_tests SET grade='C' WHERE stress_test_id='st_run'")
    assert lab_db.best_grades_by_strategy() == {"sos": {"grade": "C", "stress_test_id": "st_run"}}


# ── Cancelling ────────────────────────────────────────────────────────────────


def test_CANCEL_dispatches_to_the_platform_the_ROW_names(client):
    """The row records the platform the test was started on, so that is the runner its children
    are cancelled through.

    🔴 It used to be looked up through the run's strategy — which a STACK does not have, so a
    stack resolved to the NinjaTrader default, and a strategy re-scanned onto another runner
    mid-test would have had its children cancelled on the wrong platform.

    ⚠ Watched RED by resolving the runner through the strategy again.
    """
    from unittest.mock import patch

    _seed(runner="ninjatrader")
    _run_test(status="running", runner="python")
    lab_db.insert_run_stress_test_child(
        {
            "run_id": "child1",
            "strategy_id": "sos",
            "instrument": "XAUUSD.p",
            "params": {},
            "bar_type": "Minute",
            "bar_value": 15,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "commission_per_side": 0.0,
            "slippage_ticks": 0,
            "status": "running",
            "created_at": 2,
            "stress_test_id": "st_run",
            "runner": "python",
        }
    )

    seen: list = []
    with patch("services.runner_dispatch.cancel_job", side_effect=lambda cid, r: seen.append(r)):
        resp = client.post("/stress-tests/st_run/cancel")

    assert resp.status_code == 200, resp.text
    assert seen == ["python"], "the row said python; the strategy row says ninjatrader"
