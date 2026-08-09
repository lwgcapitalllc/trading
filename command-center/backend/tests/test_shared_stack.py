"""The SHARED-account stack — storage, the API branch, and the two pins that stop it lying.

A stack is now one of two different experiments over the same legs, and almost everything worth
testing here is about keeping them distinguishable. A screen adds up N standalone runs, so no leg
could ever block another and the result is an UPPER BOUND; a shared stack replays them together on
one balance with one risk budget. Confusing the two produces numbers that look ordinary and answer
a question nobody asked.

⚠ The simulation itself is `backtest/portfolio/` and is tested there. Nothing in this file
replays a strategy — these are the seams the lab adds around it.
"""

from __future__ import annotations

import ast
import json
import sqlite3
from pathlib import Path

import pytest

from services import lab_db


# ── Storage ───────────────────────────────────────────────────────────────────

def test_a_fresh_database_has_the_mode_columns(tmp_path, monkeypatch):
    """⚠ The migration list runs BEFORE the `stacks` CREATE TABLE, so `ALTER TABLE stacks` fails
    on a fresh database and is swallowed by the idempotent-migration try/except. Without the
    columns being declared in the CREATE too, a brand-new clone would come up WITHOUT them while
    every existing database had them — working on the machine that ran the migration and broken
    everywhere else, which is the worst shape a schema change can take.
    """
    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "fresh.db")
    lab_db.init_db()
    cols = {c[1] for c in sqlite3.connect(lab_db.DB_PATH).execute("PRAGMA table_info(stacks)")}
    assert {"mode", "account_size", "risk_cap_pct", "entry_floor_pct"} <= cols


def test_an_existing_stack_stays_a_screen(tmp_path, monkeypatch):
    """The default must be 'screen'. Every stack written before this column existed WAS a screen,
    and defaulting to 'shared' would relabel finished results as a simulation nobody ran."""
    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "lab.db")
    lab_db.init_db()
    with sqlite3.connect(lab_db.DB_PATH) as conn:
        conn.execute(
            "INSERT INTO stacks (stack_id, instrument, bar_type, bar_value, start_date, "
            "end_date, commission_per_side, slippage_ticks, created_at) "
            "VALUES ('st_old', 'XAUUSD', 'Minute', 15, '2024-01-01', '2024-12-31', 0, 0, 1)")
    assert lab_db.get_stack_settings("st_old")["mode"] == "screen"


def test_a_screen_stores_NO_account_even_when_one_is_passed(tmp_path, monkeypatch):
    """A screen has no account — every leg traded its own full one — so the knobs are NULL and
    not 0. A stored `0` renders as an account with no money, and `risk_cap_pct = 0` (which
    refuses every entry) would be indistinguishable from "this stack never had a cap"."""
    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "lab.db")
    lab_db.init_db()
    lab_db.insert_stack({
        "stack_id": "st_screen", "instrument": "XAUUSD", "bar_type": "Minute", "bar_value": 15,
        "start_date": "2024-01-01", "end_date": "2024-12-31",
        "commission_per_side": 0.0, "slippage_ticks": 0, "created_at": 1,
        "mode": "screen", "account_size": 10_000.0, "risk_cap_pct": 10.0,
    })
    row = lab_db.get_stack_settings("st_screen")
    assert row["mode"] == "screen"
    assert row["account_size"] is None and row["risk_cap_pct"] is None


def test_a_shared_stack_stores_its_account(tmp_path, monkeypatch):
    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "lab.db")
    lab_db.init_db()
    lab_db.insert_stack({
        "stack_id": "st_shared", "instrument": "XAUUSD", "bar_type": "Minute", "bar_value": 15,
        "start_date": "2024-01-01", "end_date": "2024-12-31",
        "commission_per_side": 0.0, "slippage_ticks": 0, "created_at": 1,
        "mode": "shared", "account_size": 25_000.0, "risk_cap_pct": 8.5, "entry_floor_pct": 0.5,
    })
    row = lab_db.get_stack_settings("st_shared")
    assert (row["mode"], row["account_size"], row["risk_cap_pct"], row["entry_floor_pct"]) \
        == ("shared", 25_000.0, 8.5, 0.5)


# ── The request refuses what the simulator refuses ────────────────────────────

def test_a_zero_risk_cap_is_refused_at_the_request():
    """`run_stack` raises on it, and a background job that dies three minutes in is a worse way to
    learn than a 400. A cap of zero refuses every entry, so the run would complete having taken no
    trades — which reads as a strategy with no signals rather than as a setting nobody meant."""
    from models import StackRequest
    with pytest.raises(ValueError):
        StackRequest(strategy_ids=["a", "b"], instrument="XAUUSD",
                     start_date="2024-01-01", end_date="2024-12-31",
                     mode="shared", risk_cap_pct=0)


def test_an_unknown_mode_is_refused():
    from models import StackRequest
    with pytest.raises(ValueError):
        StackRequest(strategy_ids=["a", "b"], instrument="XAUUSD",
                     start_date="2024-01-01", end_date="2024-12-31", mode="portfolio")


# ── The pin that keeps the router honest about what a leg cannot run ──────────

def test_the_router_pins_every_setting_the_simulator_would_REFUSE():
    """⚠ This is the load-bearing test in this file.

    `backtest/portfolio/legs.py::_refuse_unreplayable` raises on any config a leg structurally
    cannot run — today just `exec_secondary`, the 1-minute re-entry, which needs a second bar
    stream a merged clock cannot supply. The router pins those settings AHEAD of it so the refusal
    never fires.

    The two must not drift. If `legs.py` grows a second refusal and the router does not pin it,
    every shared stack using that strategy dies in a background task with the message buried in a
    progress field — which is exactly how this feature failed on its first real run.

    It reads `legs.py` rather than restating the list, because a hand-written copy here is a
    second claim about the same rule and would go stale silently.
    """
    from routers.stacks import _SHARED_LEG_PINS

    src = (Path(__file__).resolve().parents[3] / "backtest" / "portfolio" / "legs.py").read_text()
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_refuse_unreplayable")

    # Every `getattr(config, "<field>", ...)` the refusal reads is a field the router must pin.
    refused = {
        node.args[1].value
        for node in ast.walk(fn)
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "getattr"
        and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant)
    }
    assert refused, "found no getattr(config, ...) in _refuse_unreplayable — did it change shape?"
    missing = refused - set(_SHARED_LEG_PINS)
    assert not missing, (
        f"backtest/portfolio/legs.py refuses {sorted(missing)} and routers/stacks.py does not pin "
        f"it. Every shared stack on a strategy with that setting on would die in a background "
        f"task rather than being fixed before it started.")


def test_a_pinned_setting_is_written_to_the_row_not_only_to_the_replay():
    """The stored params must BE the params that ran.

    Overriding at replay time while the child row said otherwise is this app's most-repeated
    defect — a page stating a value no code read. Here the row and the replay agree, so the
    strategy panel on that leg's own detail page is telling the truth.
    """
    from routers.stacks import _pin_for_shared
    assert _pin_for_shared({"exec_secondary": True, "exec_risk_pct": 10})["exec_secondary"] is False
    # A strategy without the field is untouched — pinning one in would hand the runner a param it
    # does not declare, which for MT5 silently degrades an optimization to a single backtest.
    assert "exec_secondary" not in _pin_for_shared({"exec_risk_pct": 10})


# ── The report distinguishes its three "no answer" cases ──────────────────────

def test_a_screen_reports_unavailable_rather_than_empty_contention(client, tmp_path, monkeypatch):
    """⚠ `available: false` is THREE answers — this is a screen, it is still running, or it
    failed — and an empty contention log under `available: true` is the OPPOSITE of all three: a
    real measurement that nothing was refused. Collapsing them would report a screen (which has
    no account at all) as a shared run that happened to contend with nobody."""
    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "lab.db")
    lab_db.init_db()
    lab_db.insert_stack({
        "stack_id": "st_scr", "instrument": "XAUUSD", "bar_type": "Minute", "bar_value": 15,
        "start_date": "2024-01-01", "end_date": "2024-12-31",
        "commission_per_side": 0.0, "slippage_ticks": 0, "created_at": 1, "mode": "screen",
    })
    body = client.get("/backtests/stacks/st_scr/contention").json()
    assert body["available"] is False
    assert body["progress"] is None          # not running either — it is simply not that kind of stack
    assert body["events"] == [] and body["legs"] == []


def test_an_empty_contention_log_is_a_MEASUREMENT(tmp_path, monkeypatch):
    """The measured 6.5-year two-bot run refused nothing, so this is the EXPECTED result and the
    report has to be able to state it: `available: true` with no events, and a `neutral` verdict
    saying the seam moved no decision."""
    from services import portfolio_runner

    monkeypatch.setattr(portfolio_runner, "_LAB_RESULTS_DIR", tmp_path)
    sdir = tmp_path / "st_ok"
    sdir.mkdir()
    (sdir / "shared_summary.json").write_text(json.dumps({
        "opening_balance": 10_000.0, "closing_balance": 36_805.85, "contention_events": 0,
        "legs": [], "neutral": {"checkable": True, "ok": True, "reason": "…"},
    }))
    assert portfolio_runner.read_shared_summary("st_ok")["contention_events"] == 0
    assert portfolio_runner.read_shared_summary("st_missing") is None
