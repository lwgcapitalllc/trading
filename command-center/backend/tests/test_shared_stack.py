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


# ── The SOLO CONTROL book — "what would this have made if the others never existed" ───

def test_the_solo_control_book_is_KEPT_not_reduced_to_two_scalars(tmp_path, monkeypatch):
    """🔴 `_persist` stored `solo_r` and `solo_closing_balance` and threw the control's TRADES away,
    so the only book a subset of a shared stack could be composed from was the SHARED one — where
    every leg is sized off a balance all of them grew.

    Measured on the live stack `st_94aeb25f0c`: MPC B-LEG posts 17.8674R and 99 trades either way,
    at identical entry and stop prices, and reads **$47,758,999 shared against $21,064 alone**,
    because its last trade risks $16,925,791 of the shared balance instead of $3,102 of its own.
    """
    from services import portfolio_runner

    sdir = tmp_path / "st_solo"
    portfolio_runner._write_solo(sdir, "mpc_bleg", {
        "equity_curve": [{"index": 1, "equity": 10_500.0, "profit": 500.0, "r": 1.25,
                          "direction": "Long", "date": "2024-03-01"}],
        "daily_pnl": [{"date": "2024-03-01", "pnl": 500.0}],
    })
    monkeypatch.setattr(portfolio_runner, "_LAB_RESULTS_DIR", tmp_path)
    eq, dp = portfolio_runner.solo_book("st_solo", "mpc_bleg")
    assert [p["profit"] for p in eq] == [500.0]
    assert [d["pnl"] for d in dp] == [500.0]
    # ⚠ R is what makes the two books comparable at all, so it has to survive the round trip.
    assert eq[0]["r"] == 1.25


def test_a_missing_solo_book_is_EMPTY_and_never_an_exception(tmp_path, monkeypatch):
    """A shared stack replayed before 2026-08-10 has no control book on disk, and neither does a
    screen. ⚠ The caller must be able to tell that apart from a leg that made nothing — the page
    renders a refusal there rather than composing an answer out of the shared trades, which is the
    defect this whole section exists for."""
    from services import portfolio_runner

    monkeypatch.setattr(portfolio_runner, "_LAB_RESULTS_DIR", tmp_path)
    assert portfolio_runner.solo_book("st_nothing", "mpc_bleg") == ([], [])


def test_the_leg_serves_its_solo_book_on_a_SHARED_stack_and_not_on_a_screen(
    client, tmp_path, monkeypatch,
):
    """⚠ A screen gets NOTHING, and that is not a gap: there every leg already traded its own full
    account, so the leg's own curve IS the solo answer and a second copy would be two fields
    holding one fact. Only a shared stack has two different books for one leg."""
    from services import portfolio_runner
    from routers import stacks as stacks_router

    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "lab.db")
    monkeypatch.setattr(portfolio_runner, "_LAB_RESULTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(stacks_router, "_LAB_RESULTS_DIR", tmp_path / "reports")
    lab_db.init_db()
    lab_db.upsert_strategy({
        "id": "mpc_bleg", "name": "MPC B-LEG", "runner": "python",
        "class_name": "MpcBLegStrategy", "source_path": "strategies/python/mpc_bleg",
        "scanned_at": 1, "param_schema": [], "default_params": {},
    })

    for sid, mode in (("st_sh", "shared"), ("st_sc", "screen")):
        lab_db.insert_stack({
            "stack_id": sid, "instrument": "XAUUSD", "bar_type": "Minute", "bar_value": 15,
            "start_date": "2024-01-01", "end_date": "2024-12-31",
            "commission_per_side": 0.0, "slippage_ticks": 0, "created_at": 1, "mode": mode,
            "account_size": 10_000.0, "risk_cap_pct": 10.0, "entry_floor_pct": 0.0,
        })
        run_id = f"r_{sid}"
        curve = tmp_path / f"{run_id}.json"
        curve.write_text(json.dumps([{"index": 1, "equity": 12_622.0, "profit": 2_622.0,
                                      "r": 6.31, "direction": "Long", "date": "2024-03-01"}]))
        lab_db.insert_run({
            "run_id": run_id, "strategy_id": "mpc_bleg", "instrument": "XAUUSD",
            "params": {}, "bar_type": "Minute", "bar_value": 15,
            "start_date": "2024-01-01", "end_date": "2024-12-31",
            "commission_per_side": 0.0, "slippage_ticks": 0, "status": "complete",
            "created_at": 1, "stack_id": sid, "runner": "python",
        })
        lab_db.update_run_complete(run_id, {"trade_count": 1, "net_pnl": 2_622.0},
                                   {"equity_curve": str(curve), "trades": None, "daily_pnl": None})
        lab_db.add_stack_member(sid, run_id, owned=1, position=0)
        # BOTH get a control book on disk. The mode alone must decide whether it is served — a
        # screen that happened to have one must not start reporting two answers for one leg.
        portfolio_runner._write_solo(portfolio_runner.stack_dir(sid), "mpc_bleg", {
            "equity_curve": [{"index": 1, "equity": 10_500.0, "profit": 500.0, "r": 6.31,
                              "direction": "Long", "date": "2024-03-01"}],
            "daily_pnl": [{"date": "2024-03-01", "pnl": 500.0}],
        })

    shared = client.get("/backtests/stacks/st_sh").json()["strategies"][0]
    assert shared["solo_equity_curve"][0]["profit"] == 500.0
    assert shared["solo_daily_pnl"][0]["pnl"] == 500.0
    # The shared curve is untouched beside it — two books, both served, neither substituted.
    assert shared["equity_curve"][0]["profit"] == 2_622.0

    screen = client.get("/backtests/stacks/st_sc").json()["strategies"][0]
    assert screen["solo_equity_curve"] is None
    assert screen["solo_daily_pnl"] is None


def test_r_reaches_the_API_because_the_model_declares_it(client, tmp_path, monkeypatch):
    """🔴 `r` has been written to `equity_curve.json` since 2026-08-03 and `models.EquityPoint` did
    not declare it, so Pydantic dropped it on the way out — the FIFTH time this model has done that
    (`entry_ms`, `exit_ms`, `favorable`, `adverse`, now `r`).

    It matters here specifically: R is the one per-trade figure a change of position SIZE cannot
    move, which is what lets a stack's per-leg row read the same number shared or solo while the
    dollars differ by orders of magnitude. Without it the row falls back to a trade count.
    """
    from services import portfolio_runner
    from routers import stacks as stacks_router

    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "lab.db")
    monkeypatch.setattr(portfolio_runner, "_LAB_RESULTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(stacks_router, "_LAB_RESULTS_DIR", tmp_path / "reports")
    lab_db.init_db()
    lab_db.upsert_strategy({
        "id": "mpc_bleg", "name": "MPC B-LEG", "runner": "python",
        "class_name": "MpcBLegStrategy", "source_path": "strategies/python/mpc_bleg",
        "scanned_at": 1, "param_schema": [], "default_params": {},
    })
    lab_db.insert_stack({
        "stack_id": "st_r", "instrument": "XAUUSD", "bar_type": "Minute", "bar_value": 15,
        "start_date": "2024-01-01", "end_date": "2024-12-31",
        "commission_per_side": 0.0, "slippage_ticks": 0, "created_at": 1, "mode": "shared",
        "account_size": 10_000.0, "risk_cap_pct": 10.0, "entry_floor_pct": 0.0,
    })
    curve = tmp_path / "r_r.json"
    curve.write_text(json.dumps([{"index": 1, "equity": 12_622.0, "profit": 2_622.0,
                                  "r": 6.31, "direction": "Long", "date": "2024-03-01"}]))
    lab_db.insert_run({
        "run_id": "r_r", "strategy_id": "mpc_bleg", "instrument": "XAUUSD",
        "params": {}, "bar_type": "Minute", "bar_value": 15,
        "start_date": "2024-01-01", "end_date": "2024-12-31",
        "commission_per_side": 0.0, "slippage_ticks": 0, "status": "complete",
        "created_at": 1, "stack_id": "st_r", "runner": "python",
    })
    lab_db.update_run_complete("r_r", {"trade_count": 1, "net_pnl": 2_622.0},
                               {"equity_curve": str(curve), "trades": None, "daily_pnl": None})
    lab_db.add_stack_member("st_r", "r_r", owned=1, position=0)

    point = client.get("/backtests/stacks/st_r").json()["strategies"][0]["equity_curve"][0]
    assert point["r"] == 6.31
