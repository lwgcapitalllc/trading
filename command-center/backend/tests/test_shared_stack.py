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
from dataclasses import dataclass
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
            "VALUES ('st_old', 'XAUUSD', 'Minute', 15, '2024-01-01', '2024-12-31', 0, 0, 1)"
        )
    assert lab_db.get_stack_settings("st_old")["mode"] == "screen"


def test_a_screen_stores_NO_account_even_when_one_is_passed(tmp_path, monkeypatch):
    """A screen has no account — every leg traded its own full one — so the knobs are NULL and
    not 0. A stored `0` renders as an account with no money, and `risk_cap_pct = 0` (which
    refuses every entry) would be indistinguishable from "this stack never had a cap"."""
    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "lab.db")
    lab_db.init_db()
    lab_db.insert_stack(
        {
            "stack_id": "st_screen",
            "instrument": "XAUUSD",
            "bar_type": "Minute",
            "bar_value": 15,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "commission_per_side": 0.0,
            "slippage_ticks": 0,
            "created_at": 1,
            "mode": "screen",
            "account_size": 10_000.0,
            "risk_cap_pct": 10.0,
        }
    )
    row = lab_db.get_stack_settings("st_screen")
    assert row["mode"] == "screen"
    assert row["account_size"] is None and row["risk_cap_pct"] is None


def test_a_shared_stack_stores_its_account(tmp_path, monkeypatch):
    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "lab.db")
    lab_db.init_db()
    lab_db.insert_stack(
        {
            "stack_id": "st_shared",
            "instrument": "XAUUSD",
            "bar_type": "Minute",
            "bar_value": 15,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "commission_per_side": 0.0,
            "slippage_ticks": 0,
            "created_at": 1,
            "mode": "shared",
            "account_size": 25_000.0,
            "risk_cap_pct": 8.5,
            "entry_floor_pct": 0.5,
        }
    )
    row = lab_db.get_stack_settings("st_shared")
    assert (row["mode"], row["account_size"], row["risk_cap_pct"], row["entry_floor_pct"]) == (
        "shared",
        25_000.0,
        8.5,
        0.5,
    )


# ── The request refuses what the simulator refuses ────────────────────────────


def test_a_zero_risk_cap_is_refused_at_the_request():
    """`run_stack` raises on it, and a background job that dies three minutes in is a worse way to
    learn than a 400. A cap of zero refuses every entry, so the run would complete having taken no
    trades — which reads as a strategy with no signals rather than as a setting nobody meant."""
    from models import StackRequest

    with pytest.raises(ValueError):
        StackRequest(
            strategy_ids=["a", "b"],
            instrument="XAUUSD",
            start_date="2024-01-01",
            end_date="2024-12-31",
            mode="shared",
            risk_cap_pct=0,
        )


def test_an_unknown_mode_is_refused():
    from models import StackRequest

    with pytest.raises(ValueError):
        StackRequest(
            strategy_ids=["a", "b"],
            instrument="XAUUSD",
            start_date="2024-01-01",
            end_date="2024-12-31",
            mode="portfolio",
        )


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
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "_refuse_unreplayable"
    )

    # Every `getattr(config, "<field>", ...)` the refusal reads is a field the router must pin.
    refused = {
        node.args[1].value
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", None) == "getattr"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
    }
    assert refused, "found no getattr(config, ...) in _refuse_unreplayable — did it change shape?"
    missing = refused - set(_SHARED_LEG_PINS)
    assert not missing, (
        f"backtest/portfolio/legs.py refuses {sorted(missing)} and routers/stacks.py does not pin "
        f"it. Every shared stack on a strategy with that setting on would die in a background "
        f"task rather than being fixed before it started."
    )


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
    lab_db.insert_stack(
        {
            "stack_id": "st_scr",
            "instrument": "XAUUSD",
            "bar_type": "Minute",
            "bar_value": 15,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "commission_per_side": 0.0,
            "slippage_ticks": 0,
            "created_at": 1,
            "mode": "screen",
        }
    )
    body = client.get("/backtests/stacks/st_scr/contention").json()
    assert body["available"] is False
    assert body["progress"] is None  # not running either — it is simply not that kind of stack
    assert body["events"] == [] and body["legs"] == []


def test_an_empty_contention_log_is_a_MEASUREMENT(tmp_path, monkeypatch):
    """The measured 6.5-year two-bot run refused nothing, so this is the EXPECTED result and the
    report has to be able to state it: `available: true` with no events, and a `neutral` verdict
    saying the seam moved no decision."""
    from services import portfolio_runner

    monkeypatch.setattr(portfolio_runner, "_LAB_RESULTS_DIR", tmp_path)
    sdir = tmp_path / "st_ok"
    sdir.mkdir()
    (sdir / "shared_summary.json").write_text(
        json.dumps(
            {
                "opening_balance": 10_000.0,
                "closing_balance": 36_805.85,
                "contention_events": 0,
                "legs": [],
                "neutral": {"checkable": True, "ok": True, "reason": "…"},
            }
        )
    )
    assert portfolio_runner.read_shared_summary("st_ok")["contention_events"] == 0
    assert portfolio_runner.read_shared_summary("st_missing") is None


# ── The SOLO CONTROL book — "what would this have made if the others never existed" ───


def test_the_solo_control_book_is_KEPT_not_reduced_to_two_scalars(tmp_path, monkeypatch):
    """🔴 `_persist` stored `solo_r` and `solo_closing_balance` and threw the control's TRADES away,
    so the only book a subset of a shared stack could be composed from was the SHARED one — where
    every leg is sized off a balance all of them grew.

    Measured on the live stack `st_94aeb25f0c`: B-LEG posts 17.8674R and 99 trades either way,
    at identical entry and stop prices, and reads **$47,758,999 shared against $21,064 alone**,
    because its last trade risks $16,925,791 of the shared balance instead of $3,102 of its own.
    """
    from services import portfolio_runner

    sdir = tmp_path / "st_solo"
    portfolio_runner._write_solo(
        sdir,
        "b_leg",
        {
            "equity_curve": [
                {
                    "index": 1,
                    "equity": 10_500.0,
                    "profit": 500.0,
                    "r": 1.25,
                    "direction": "Long",
                    "date": "2024-03-01",
                }
            ],
            "daily_pnl": [{"date": "2024-03-01", "pnl": 500.0}],
        },
    )
    monkeypatch.setattr(portfolio_runner, "_LAB_RESULTS_DIR", tmp_path)
    eq, dp = portfolio_runner.solo_book("st_solo", "b_leg")
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
    assert portfolio_runner.solo_book("st_nothing", "b_leg") == ([], [])


def test_the_leg_serves_its_solo_book_on_a_SHARED_stack_and_not_on_a_screen(
    client,
    tmp_path,
    monkeypatch,
):
    """⚠ A screen gets NOTHING, and that is not a gap: there every leg already traded its own full
    account, so the leg's own curve IS the solo answer and a second copy would be two fields
    holding one fact. Only a shared stack has two different books for one leg."""
    from routers import stacks as stacks_router
    from services import portfolio_runner

    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "lab.db")
    monkeypatch.setattr(portfolio_runner, "_LAB_RESULTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(stacks_router, "_LAB_RESULTS_DIR", tmp_path / "reports")
    lab_db.init_db()
    lab_db.upsert_strategy(
        {
            "id": "b_leg",
            "name": "B-LEG",
            "runner": "python",
            "class_name": "BLegStrategy",
            "source_path": "strategies/python/b_leg",
            "scanned_at": 1,
            "param_schema": [],
            "default_params": {},
        }
    )

    for sid, mode in (("st_sh", "shared"), ("st_sc", "screen")):
        lab_db.insert_stack(
            {
                "stack_id": sid,
                "instrument": "XAUUSD",
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
        run_id = f"r_{sid}"
        curve = tmp_path / f"{run_id}.json"
        curve.write_text(
            json.dumps(
                [
                    {
                        "index": 1,
                        "equity": 12_622.0,
                        "profit": 2_622.0,
                        "r": 6.31,
                        "direction": "Long",
                        "date": "2024-03-01",
                    }
                ]
            )
        )
        lab_db.insert_run(
            {
                "run_id": run_id,
                "strategy_id": "b_leg",
                "instrument": "XAUUSD",
                "params": {},
                "bar_type": "Minute",
                "bar_value": 15,
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "commission_per_side": 0.0,
                "slippage_ticks": 0,
                "status": "complete",
                "created_at": 1,
                "stack_id": sid,
                "runner": "python",
            }
        )
        lab_db.update_run_complete(
            run_id,
            {"trade_count": 1, "net_pnl": 2_622.0},
            {"equity_curve": str(curve), "trades": None, "daily_pnl": None},
        )
        lab_db.add_stack_member(sid, run_id, owned=1, position=0)
        # BOTH get a control book on disk. The mode alone must decide whether it is served — a
        # screen that happened to have one must not start reporting two answers for one leg.
        portfolio_runner._write_solo(
            portfolio_runner.stack_dir(sid),
            "b_leg",
            {
                "equity_curve": [
                    {
                        "index": 1,
                        "equity": 10_500.0,
                        "profit": 500.0,
                        "r": 6.31,
                        "direction": "Long",
                        "date": "2024-03-01",
                    }
                ],
                "daily_pnl": [{"date": "2024-03-01", "pnl": 500.0}],
            },
        )

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
    from routers import stacks as stacks_router
    from services import portfolio_runner

    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "lab.db")
    monkeypatch.setattr(portfolio_runner, "_LAB_RESULTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(stacks_router, "_LAB_RESULTS_DIR", tmp_path / "reports")
    lab_db.init_db()
    lab_db.upsert_strategy(
        {
            "id": "b_leg",
            "name": "B-LEG",
            "runner": "python",
            "class_name": "BLegStrategy",
            "source_path": "strategies/python/b_leg",
            "scanned_at": 1,
            "param_schema": [],
            "default_params": {},
        }
    )
    lab_db.insert_stack(
        {
            "stack_id": "st_r",
            "instrument": "XAUUSD",
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
    curve = tmp_path / "r_r.json"
    curve.write_text(
        json.dumps(
            [
                {
                    "index": 1,
                    "equity": 12_622.0,
                    "profit": 2_622.0,
                    "r": 6.31,
                    "direction": "Long",
                    "date": "2024-03-01",
                }
            ]
        )
    )
    lab_db.insert_run(
        {
            "run_id": "r_r",
            "strategy_id": "b_leg",
            "instrument": "XAUUSD",
            "params": {},
            "bar_type": "Minute",
            "bar_value": 15,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "commission_per_side": 0.0,
            "slippage_ticks": 0,
            "status": "complete",
            "created_at": 1,
            "stack_id": "st_r",
            "runner": "python",
        }
    )
    lab_db.update_run_complete(
        "r_r",
        {"trade_count": 1, "net_pnl": 2_622.0},
        {"equity_curve": str(curve), "trades": None, "daily_pnl": None},
    )
    lab_db.add_stack_member("st_r", "r_r", owned=1, position=0)

    point = client.get("/backtests/stacks/st_r").json()["strategies"][0]["equity_curve"][0]
    assert point["r"] == 6.31


# ── The merged price chart carries every leg's analysis ───────────────────────
#
# 🔴 It carried NONE of it until 2026-08-10. `build_stack_chart_spec` dropped blocked setups,
# missed setups and every anchored overlay group, on the argument that none of them carried a
# `layer` — which was true, and was a reason to TAG them rather than to omit them. With the layers
# gone, isolating one strategy on a stack left the reader with winners, losers and fibs while that
# same strategy's own backtest page carried ten more rows.


class _FakeSpec(dict):
    """Just enough of a leg's ChartSpec for the merge to work on."""


def _leg_spec(*, gap_t0: int, block_time: int, layer_only_group: str = "Order Blocks") -> dict:
    return {
        "instrument": "XAUUSD",
        "baseTimeframe": "M15",
        "runTimeframe": "M15",
        "historyStartMs": 0,
        "brokerGmtOffsetHours": 0,
        "candles": [{"time": 1, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0}],
        "sessions": [],
        "indicators": [],
        "trades": [{"id": "T1", "entryTime": 10, "dir": "long", "pnl": 1.0}],
        "blocks": [
            {
                "id": "B1",
                "time": block_time,
                "dir": "long",
                "price": 1.0,
                "reasons": [{"label": "Veto", "reason": "…"}],
            }
        ],
        "misses": [
            {
                "id": "M1",
                "time": 20,
                "dir": "long",
                "price": 1.0,
                "met": 2,
                "of": 3,
                "near": True,
                "metLines": [],
                "reasons": [{"label": "No FVG", "reason": "…"}],
            }
        ],
        "missNoise": ["No retrace"],
        "overlays": [
            # A market fact selected for drawing by whichever leg fired near it.
            {
                "type": "box",
                "group": "Fair Value Gaps",
                "t0": gap_t0,
                "t1": gap_t0 + 100,
                "p0": 1.0,
                "p1": 2.0,
            },
            # …and one only this leg reported, so the dedupe has something to leave alone.
            {"type": "box", "group": layer_only_group, "t0": 999, "t1": 1099, "p0": 3.0, "p1": 4.0},
            # Structure — computed from the CANDLES, so it belongs to no leg.
            {"type": "hline", "group": "External Structure", "t0": 1, "t1": 2, "price": 1.5},
            # The candle repaint, whose spans/deepestOf are indices into THIS run's anchor list.
            {
                "type": "candle",
                "group": "Candlestick Reversals",
                "t": 10,
                "spans": [0],
                "deepestOf": [0],
                "deepestNames": {"0": "Hammer"},
            },
        ],
    }


def _merged(
    monkeypatch, specs: dict[str, dict], *, refresh: bool = False, seen: list | None = None
) -> dict:
    from services import chart_spec

    rows = [
        {
            "run_id": f"run_{sid}",
            "strategy_id": sid,
            "strategy_name": sid.upper(),
            "status": "complete",
        }
        for sid in specs
    ]

    def _fake(run_id, refresh_arg=False):
        if seen is not None:
            seen.append((run_id, refresh_arg))
        return specs[run_id.removeprefix("run_")]

    monkeypatch.setattr(chart_spec.lab_db, "list_stack_runs", lambda _sid: rows)
    monkeypatch.setattr(chart_spec, "build_chart_spec", _fake)
    return chart_spec.build_stack_chart_spec("st_x", refresh)


def test_a_block_and_a_miss_are_TAGGED_with_the_leg_that_produced_them(monkeypatch):
    """Both were dropped entirely because they carried no layer. Tagging is the fix, not omission.

    ⚠ The id is namespaced too: two legs both numbering their setups from B1 would collide, and the
    chart keys its markers on the id.
    """
    merged = _merged(
        monkeypatch,
        {"a": _leg_spec(gap_t0=500, block_time=1), "b": _leg_spec(gap_t0=500, block_time=2)},
    )
    assert [b["layer"] for b in merged["blocks"]] == ["a", "b"]
    assert [m["layer"] for m in merged["misses"]] == ["a", "b"]
    assert sorted(b["id"] for b in merged["blocks"]) == ["a:B1", "b:B1"]


def test_two_legs_reporting_ONE_market_fact_produce_ONE_overlay_carrying_BOTH(monkeypatch):
    """A gap is a fact about the market, so identical copies merge and the overlay draws while
    EITHER leg is shown.

    That is the opposite rule from a block, which belongs to one strategy — and it is what stops a
    stack double-counting its own box counts and stacking two identical rectangles.
    """
    merged = _merged(
        monkeypatch,
        {"a": _leg_spec(gap_t0=500, block_time=1), "b": _leg_spec(gap_t0=500, block_time=2)},
    )
    gaps = [o for o in merged["overlays"] if o["group"] == "Fair Value Gaps"]
    assert len(gaps) == 1, "one gap reported by both legs must not be drawn twice"
    assert gaps[0]["layers"] == ["a", "b"]


def test_a_gap_only_ONE_leg_saw_stays_that_leg_s(monkeypatch):
    """The dedupe must key on the DRAWING, not on the group — otherwise two different gaps merge
    into one and a zone the other leg never traded into survives its leg being switched off."""
    merged = _merged(
        monkeypatch,
        {"a": _leg_spec(gap_t0=500, block_time=1), "b": _leg_spec(gap_t0=900, block_time=2)},
    )
    gaps = sorted(
        (o for o in merged["overlays"] if o["group"] == "Fair Value Gaps"), key=lambda o: o["t0"]
    )
    assert [g["layers"] for g in gaps] == [["a"], ["b"]]


def test_the_structure_overlays_belong_to_NO_leg(monkeypatch):
    """They are computed from the candles, which every leg shares, so the base leg's are the
    stack's — and they must carry no `layers`, or isolating a strategy would blank the market
    structure underneath it."""
    merged = _merged(
        monkeypatch,
        {"a": _leg_spec(gap_t0=500, block_time=1), "b": _leg_spec(gap_t0=900, block_time=2)},
    )
    struct = [o for o in merged["overlays"] if o["group"] == "External Structure"]
    assert len(struct) == 1
    assert "layers" not in struct[0]


def test_the_candle_repaint_is_DROPPED_because_its_anchors_are_run_relative(monkeypatch):
    """`spans` / `deepestOf` / `deepestNames` are INDICES into one run's own anchor list, and a
    stack re-sorts every leg's trades into one list and then filters it by which legs are on. An
    index minted against one run addresses a different trade here — so it would name the wrong
    trade's outcome chip, which is a confident wrong answer rather than a missing layer.
    """
    merged = _merged(
        monkeypatch,
        {"a": _leg_spec(gap_t0=500, block_time=1), "b": _leg_spec(gap_t0=900, block_time=2)},
    )
    assert not [o for o in merged["overlays"] if o["group"] == "Candlestick Reversals"]


def test_missNoise_is_a_UNION_across_the_legs(monkeypatch):
    """A reason one leg calls routine is routine on the merged chart too. A leg that never produced
    that reason has no opinion, so it cannot vote against it."""
    a = _leg_spec(gap_t0=500, block_time=1)
    b = _leg_spec(gap_t0=900, block_time=2)
    b["missNoise"] = ["Never filled"]
    merged = _merged(monkeypatch, {"a": a, "b": b})
    assert merged["missNoise"] == ["No retrace", "Never filled"]


def test_the_shared_runner_captures_each_leg_s_blocked_and_missed_setups():
    """`StackRun` carries them per leg, off the SHARED replay.

    Without this the lab's `_persist` had nothing to hand `build_results`, so a shared stack's legs
    wrote no `blocked_setups.json` at all — and the layer was therefore missing from the leg's OWN
    detail page as well as from the stack's, while the identical leg run through the screen path
    had it.
    """
    from backtest.portfolio.runner import StackRun

    run = StackRun(opening_balance=0.0, risk_cap_pct=0.1, entry_floor_pct=0.0, closing_balance=0.0)
    assert run.blocked_per_leg == {}
    assert run.missed_per_leg == {}


def test_a_stack_rebuild_reaches_EVERY_leg_s_cached_spec(monkeypatch):
    """`refresh=True` must rebuild each leg's own cached spec, not just re-run the merge.

    The merge holds no cache — it is recomputed on every request — so a Rebuild that stopped at the
    merge would return byte-identical stale layers while the button spun and stopped. And it has to
    reach EVERY leg rather than the base one: the blocked setups, missed setups and anchored
    analysis on this chart come from all of them, so refreshing only the leg that supplies the
    candles would leave most of the chart stale.
    """
    seen: list = []
    _merged(
        monkeypatch,
        {"a": _leg_spec(gap_t0=500, block_time=1), "b": _leg_spec(gap_t0=900, block_time=2)},
        refresh=True,
        seen=seen,
    )
    assert seen == [("run_a", True), ("run_b", True)]


def test_a_stack_chart_spec_does_NOT_rebuild_the_legs_by_default(monkeypatch):
    """The other half of the same rule, and the one that keeps the page usable.

    The stack spec is fetched on every visit to the price section, and a leg rebuild re-fetches
    candles and replays the engines — measured at ~55s for two legs of a full-history run. Defaulting
    to a rebuild would turn opening the chart into that wait, every time.
    """
    seen: list = []
    _merged(
        monkeypatch,
        {"a": _leg_spec(gap_t0=500, block_time=1), "b": _leg_spec(gap_t0=900, block_time=2)},
        seen=seen,
    )
    assert seen == [("run_a", False), ("run_b", False)]


# ── The regime timeline is computed ONCE, including when the answer is "nothing" ──


def _stack_with_one_complete_leg(client_db: Path, reports: Path) -> None:
    """One shared stack, one finished leg, no `regime_timeline.json` anywhere."""
    lab_db.init_db()
    lab_db.upsert_strategy(
        {
            "id": "b_leg",
            "name": "B-LEG",
            "runner": "python",
            "class_name": "BLegStrategy",
            "source_path": "strategies/python/b_leg",
            "scanned_at": 1,
            "param_schema": [],
            "default_params": {},
        }
    )
    lab_db.insert_stack(
        {
            "stack_id": "st_rg",
            "instrument": "XAUUSD",
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
    curve = reports / "curve.json"
    curve.parent.mkdir(parents=True, exist_ok=True)
    curve.write_text(
        json.dumps(
            [
                {
                    "index": 1,
                    "equity": 10_500.0,
                    "profit": 500.0,
                    "r": 1.0,
                    "direction": "Long",
                    "date": "2024-03-01",
                }
            ]
        )
    )
    lab_db.insert_run(
        {
            "run_id": "r_rg",
            "strategy_id": "b_leg",
            "instrument": "XAUUSD",
            "params": {},
            "bar_type": "Minute",
            "bar_value": 15,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "commission_per_side": 0.0,
            "slippage_ticks": 0,
            "status": "complete",
            "created_at": 1,
            "stack_id": "st_rg",
            "runner": "python",
        }
    )
    lab_db.update_run_complete(
        "r_rg",
        {"trade_count": 1, "net_pnl": 500.0},
        {"equity_curve": str(curve), "trades": None, "daily_pnl": None},
    )
    lab_db.add_stack_member("st_rg", "r_rg", owned=1, position=0)


def test_an_EMPTY_regime_timeline_is_cached_so_it_is_not_recomputed_every_poll(
    client,
    tmp_path,
    monkeypatch,
):
    """🔴 The "have we tried" test was whether the timeline came back NON-EMPTY, so a window the
    classifier legitimately answers nothing for was recomputed on every single GET — and that
    recompute FETCHES OHLC.

    This endpoint is polled every 3 seconds while a stack runs, so the cost is not theoretical and
    it compounds with the poll that never stopped on a failed stack. `[]` on disk is a real answer
    ("measured, nothing to show"), which is exactly why it has to be written.

    ⚠ Watched RED against HEAD: the old code called the builder on every request (2 calls).
    """
    from routers import stacks as stacks_router
    from services import backtest_runner

    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "lab.db")
    monkeypatch.setattr(stacks_router, "_LAB_RESULTS_DIR", tmp_path / "reports")
    _stack_with_one_complete_leg(tmp_path / "lab.db", tmp_path / "reports")

    calls: list = []

    def _empty(instrument, start, end, daily, runner):
        calls.append(instrument)
        return [], daily

    monkeypatch.setattr(backtest_runner, "build_regime_timeline_and_tag", _empty)

    assert client.get("/backtests/stacks/st_rg").json()["regime_timeline"] == []
    assert client.get("/backtests/stacks/st_rg").json()["regime_timeline"] == []
    assert calls == ["XAUUSD"], f"the builder ran {len(calls)} times, not once"
    assert (tmp_path / "reports" / "r_rg" / "regime_timeline.json").read_text() == "[]"


def test_a_real_regime_timeline_is_still_computed_once_and_served(client, tmp_path, monkeypatch):
    """The other half, kept because a fix that stops computing anything would pass the test above.

    ⚠ This one CANNOT be watched red — the old code served a computed timeline too — so it is a pin
    on the half that was already right, not a catch.
    """
    from routers import stacks as stacks_router
    from services import backtest_runner

    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "lab.db")
    monkeypatch.setattr(stacks_router, "_LAB_RESULTS_DIR", tmp_path / "reports")
    _stack_with_one_complete_leg(tmp_path / "lab.db", tmp_path / "reports")

    calls: list = []
    timeline = [{"date": "2024-03-01", "regime": "TRENDING"}]

    def _real(instrument, start, end, daily, runner):
        calls.append(instrument)
        return timeline, daily

    monkeypatch.setattr(backtest_runner, "build_regime_timeline_and_tag", _real)

    assert client.get("/backtests/stacks/st_rg").json()["regime_timeline"] == timeline
    assert client.get("/backtests/stacks/st_rg").json()["regime_timeline"] == timeline
    assert calls == ["XAUUSD"]


def test_timeline_false_drops_the_calendar_and_changes_NOTHING_else(client, tmp_path, monkeypatch):
    """The regime calendar is 43% of this payload (96,766 of 226,036 bytes, measured on the live
    stack) and the overlay it feeds defaults OFF, so `?timeline=false` leaves it out.

    ⚠ The assertion that matters is the SECOND one: a slimmed response must be the same run. The
    point of the flag is a smaller payload, not a different answer, and a caller reading the slim
    response must never be told something a caller reading the full one is not.

    ⚠ Non-vacuity by MUTATION (the parameter did not exist at HEAD): making the slim branch drop
    any other field, or making `timeline=True` also drop the calendar, turns this red.
    """
    from routers import stacks as stacks_router
    from services import backtest_runner

    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "lab.db")
    monkeypatch.setattr(stacks_router, "_LAB_RESULTS_DIR", tmp_path / "reports")
    _stack_with_one_complete_leg(tmp_path / "lab.db", tmp_path / "reports")

    timeline = [{"date": "2024-03-01", "regime": "TRENDING"}]
    monkeypatch.setattr(
        backtest_runner, "build_regime_timeline_and_tag", lambda i, s, e, d, r: (timeline, d)
    )

    full = client.get("/backtests/stacks/st_rg").json()
    slim = client.get("/backtests/stacks/st_rg?timeline=false").json()

    assert full["regime_timeline"] == timeline
    assert slim["regime_timeline"] == []
    assert {k: v for k, v in slim.items() if k != "regime_timeline"} == {
        k: v for k, v in full.items() if k != "regime_timeline"
    }


def test_the_DEFAULT_still_carries_the_calendar(client, tmp_path, monkeypatch):
    """⚠ A caller that says nothing gets the whole run, exactly as `GET /runs/{id}` states.

    Defaulting this to False would silently empty `regime_timeline` for every existing consumer,
    and `[]` there is indistinguishable from a stack whose window genuinely has no regimes — so the
    breakage would render as a missing overlay rather than as an error. This is a pin on a rule
    that is right today, not a catch; it exists because the tempting "optimisation" is to flip it.
    """
    import inspect

    from routers import stacks as stacks_router

    assert inspect.signature(stacks_router.get_stack).parameters["timeline"].default is True


def test_the_slim_branch_does_NOT_classify_a_window_nobody_asked_to_see(
    client, tmp_path, monkeypatch
):
    """Classifying a window FETCHES OHLC, so the slim branch must never trigger it.

    ⚠ This is the whole point of splitting the calendar out. Dropping the field from the response
    while still computing it would move bytes off the wire and leave the expensive half exactly
    where it was — a saving the reader can see and the server cannot.

    ⚠ Non-vacuity by MUTATION: computing unconditionally and slicing the field out afterwards
    turns this red.
    """
    from routers import stacks as stacks_router
    from services import backtest_runner

    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "lab.db")
    monkeypatch.setattr(stacks_router, "_LAB_RESULTS_DIR", tmp_path / "reports")
    _stack_with_one_complete_leg(tmp_path / "lab.db", tmp_path / "reports")

    calls: list = []

    def _build(instrument, start, end, daily, runner):
        calls.append(instrument)
        return [{"date": "2024-03-01", "regime": "TRENDING"}], daily

    monkeypatch.setattr(backtest_runner, "build_regime_timeline_and_tag", _build)

    client.get("/backtests/stacks/st_rg?timeline=false")
    assert calls == [], f"the slim branch classified the window ({len(calls)} OHLC fetches)"

    # ...and the dedicated endpoint is the path that DOES, so the calendar is still reachable.
    assert client.get("/backtests/stacks/st_rg/regime-timeline").json()["regime_timeline"] == [
        {"date": "2024-03-01", "regime": "TRENDING"}
    ]
    assert calls == ["XAUUSD"]


def test_the_slim_response_still_says_whether_a_calendar_EXISTS(client, tmp_path, monkeypatch):
    """🔴 Without this the flag would remove the CONTROL rather than the payload.

    The page hides the regime toggle when there is nothing to overlay, and it decided that by
    reading `regime_timeline.length`. On a slimmed response that is always 0 — so the reader would
    lose the only way to ask for the overlay, and the page would look like a build with the feature
    removed. `has_regime_timeline` is the answer that survives the switch.

    ⚠ It must NOT classify to answer: an uncached window reports whether one COULD be built, which
    is why this asserts the builder was never called.

    ⚠ Non-vacuity by MUTATION: deriving the flag from `regime_timeline` turns this red.
    """
    from routers import stacks as stacks_router
    from services import backtest_runner

    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "lab.db")
    monkeypatch.setattr(stacks_router, "_LAB_RESULTS_DIR", tmp_path / "reports")
    _stack_with_one_complete_leg(tmp_path / "lab.db", tmp_path / "reports")

    calls: list = []
    monkeypatch.setattr(
        backtest_runner,
        "build_regime_timeline_and_tag",
        lambda i, s, e, d, r: (calls.append(i), ([], d))[1],
    )

    slim = client.get("/backtests/stacks/st_rg?timeline=false").json()
    assert slim["has_regime_timeline"] is True
    assert slim["regime_timeline"] == []
    assert calls == [], "answering whether a calendar exists must not classify one"


def test_a_window_MEASURED_as_having_no_regimes_reports_no_calendar(client, tmp_path, monkeypatch):
    """The other side of the flag, and the reason it is not simply "is this stack complete".

    An empty calendar on disk is a MEASUREMENT — we classified the window and it has nothing to
    show — so the overlay control is correctly withheld. Reporting `true` there would offer a
    toggle that draws nothing, which reads as the overlay being broken.
    """
    from routers import stacks as stacks_router

    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "lab.db")
    monkeypatch.setattr(stacks_router, "_LAB_RESULTS_DIR", tmp_path / "reports")
    _stack_with_one_complete_leg(tmp_path / "lab.db", tmp_path / "reports")

    cache = tmp_path / "reports" / "r_rg" / "regime_timeline.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text("[]")

    assert (
        client.get("/backtests/stacks/st_rg?timeline=false").json()["has_regime_timeline"] is False
    )


# ── A leg's PARAMS, and the two things that could not be answered without them ──────────────
#
# Round 4 of the stacks audit. Both defects are the same missing field, and neither produced an
# error: the page had no way to show a param the STACK pinned, and a rerun silently substituted
# today's stored defaults for what each leg actually ran with.


def _stack_leg_with_params(db: Path, reports: Path, params: dict, mode: str = "shared") -> None:
    """One stack, one finished leg, replayed with `params`."""
    lab_db.init_db()
    lab_db.upsert_strategy(
        {
            "id": "b_leg",
            "name": "B-LEG",
            "runner": "python",
            "class_name": "BLegStrategy",
            "source_path": "strategies/python/b_leg",
            "scanned_at": 1,
            "param_schema": [],
            # Deliberately DIFFERENT from what the leg ran with — that difference is the whole
            # subject. A fixture where the two agree cannot tell a carried-forward param from a
            # defaulted one.
            "default_params": {"exec_secondary": True, "exec_risk_pct": 10.0},
        }
    )
    lab_db.insert_stack(
        {
            "stack_id": "st_p",
            "instrument": "XAUUSD",
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
    curve = reports / "curve_p.json"
    curve.parent.mkdir(parents=True, exist_ok=True)
    curve.write_text(
        json.dumps(
            [
                {
                    "index": 1,
                    "equity": 10_500.0,
                    "profit": 500.0,
                    "r": 1.0,
                    "direction": "Long",
                    "date": "2024-03-01",
                }
            ]
        )
    )
    lab_db.insert_run(
        {
            "run_id": "r_p",
            "strategy_id": "b_leg",
            "instrument": "XAUUSD",
            "params": params,
            "bar_type": "Minute",
            "bar_value": 15,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "commission_per_side": 0.0,
            "slippage_ticks": 0,
            "status": "complete",
            "created_at": 1,
            "stack_id": "st_p",
            "runner": "python",
        }
    )
    lab_db.update_run_complete(
        "r_p",
        {"trade_count": 1, "net_pnl": 500.0},
        {"equity_curve": str(curve), "trades": None, "daily_pnl": None},
    )
    lab_db.add_stack_member("st_p", "r_p", owned=1, position=0)


def test_a_leg_carries_the_params_it_was_REPLAYED_with(client, tmp_path, monkeypatch):
    """🔴 `StackStrategyLeg` served no params, so the one value a stack PINS was invisible.

    `_SHARED_LEG_PINS` forces `exec_secondary: false` onto every shared leg before it replays,
    because a leg on a merged clock is one bar frame and the 1-minute re-entry cannot run there.
    The strategy's own stored default is `true`. So the run genuinely differs from the strategy,
    for a reason nothing on the stack page could state — the reader's only route to it was
    opening the leg's own page and knowing to look for it.

    MUTATION: drop `params=` from the `StackStrategyLeg(...)` constructor in `routers/stacks.py`
    and this goes red on the pinned value.
    """
    from routers import stacks as stacks_router

    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "lab.db")
    monkeypatch.setattr(stacks_router, "_LAB_RESULTS_DIR", tmp_path / "reports")
    _stack_leg_with_params(
        tmp_path / "lab.db", tmp_path / "reports", {"exec_secondary": False, "exec_risk_pct": 2.5}
    )

    leg = client.get("/backtests/stacks/st_p?timeline=false").json()["strategies"][0]

    # The PINNED value, which is the one that cannot be recovered from anywhere else on the page.
    assert leg["params"]["exec_secondary"] is False
    # And it must be what the RUN carried, not what the strategy stores.
    assert leg["params"]["exec_risk_pct"] == 2.5


def test_a_leg_that_stored_no_params_reports_an_empty_dict_not_a_missing_field(
    client,
    tmp_path,
    monkeypatch,
):
    """A leg written before params were served must not break the response.

    `{}` renders as no settings section, which is honest: the run recorded none. It is the
    absence of a SECTION, never a claim that the leg ran on nothing.

    ⚠ VACUOUS against the mutation its sibling names, and kept anyway. Dropping `params=` from
    the constructor leaves the model's own `{}` default, so this stays green — it was RUN under
    that mutation and confirmed to pass, rather than assumed to fail. What it pins is the shape a
    caller may rely on, which is the half that gets "simplified" to `None` later.
    """
    from routers import stacks as stacks_router

    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "lab.db")
    monkeypatch.setattr(stacks_router, "_LAB_RESULTS_DIR", tmp_path / "reports")
    _stack_leg_with_params(tmp_path / "lab.db", tmp_path / "reports", {})

    leg = client.get("/backtests/stacks/st_p?timeline=false").json()["strategies"][0]
    assert leg["params"] == {}


def test_the_PREVIEW_refuses_to_reuse_a_leg_the_launch_would_re_run(client, tmp_path, monkeypatch):
    """🔴 A per-strategy param override DISABLES reuse, and the preview did not know.

    `trigger_stack` skips `find_matching_stack_run` entirely for a leg carrying an override —
    "run it my way", not "reuse whatever exists". The preview had no such field, so on a rerun
    (which now carries every leg's params forward) it would badge the leg green **Reuse** and
    then watch it replay. The preview and the thing it previews would be answering the same
    request differently.

    MUTATION: drop the `or forced` clause from `preview_stack` and this goes red.
    """
    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "lab.db")
    # A SCREEN, because a shared stack reuses nothing regardless — the override rule is only
    # observable where reuse is otherwise possible.
    _stack_leg_with_params(
        tmp_path / "lab.db", tmp_path / "reports", {"exec_risk_pct": 2.5}, mode="screen"
    )
    lab_db.upsert_strategy(
        {
            "id": "sos_fade",
            "name": "SOS Fade",
            "runner": "python",
            "class_name": "SosFadeStrategy",
            "source_path": "strategies/python/sos_fade",
            "scanned_at": 1,
            "param_schema": [],
            "default_params": {},
        }
    )
    # A standalone completed run per leg at exactly these settings — genuine reuse candidates.
    for i, sid in enumerate(("b_leg", "sos_fade")):
        lab_db.insert_run(
            {
                "run_id": f"r_free_{i}",
                "strategy_id": sid,
                "instrument": "XAUUSD",
                "params": {},
                "bar_type": "Minute",
                "bar_value": 15,
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "commission_per_side": 0.0,
                "slippage_ticks": 0,
                "status": "complete",
                "created_at": 2,
                "runner": "python",
            }
        )
        lab_db.update_run_complete(
            f"r_free_{i}",
            {"trade_count": 1, "net_pnl": 1.0},
            {"equity_curve": None, "trades": None, "daily_pnl": None},
        )

    body = {
        "strategy_ids": ["b_leg", "sos_fade"],
        "instrument": "XAUUSD",
        "bar_type": "Minute",
        "bar_value": 15,
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "commission_per_side": 0.0,
        "slippage_ticks": 0,
        "mode": "screen",
        # ⚠ Costs OFF, because the seeded runs above are free-book ones and since 2026-09-02 the
        # cost basis is part of the reuse identity — a charged stack will not reuse a run that
        # never paid a spread. Stating it keeps this test about the OVERRIDE rule rather than
        # accidentally about the cost default, which is a separate rule with its own test below.
        "charge_costs": False,
    }
    # Without an override BOTH reuse — this half is what makes the assertion below mean something
    # rather than passing on legs that could never have been reused.
    assert client.post("/backtests/stacks/preview", json=body).json()["reuse_count"] == 2

    # Override ONE leg. The other must be untouched, or the rule is "any override disables all
    # reuse", which is a different and wrong thing.
    forced = {**body, "params_by_strategy": {"b_leg": {"exec_risk_pct": 2.5}}}
    out = client.post("/backtests/stacks/preview", json=forced).json()
    assert out["reuse_count"] == 1
    by_id = {leg["strategy_id"]: leg["action"] for leg in out["legs"]}
    assert by_id == {"b_leg": "run", "sos_fade": "reuse"}


def test_a_CHARGED_stack_will_not_reuse_a_run_that_was_measured_FREE(client, tmp_path, monkeypatch):
    """🔴 The cost basis is part of a leg's identity, and the failure it prevents lands INSIDE
    one result rather than across two.

    Reuse exists so a stack does not replay a leg it already has. But a finished run measured on
    a FREE book, dropped into a stack that charges spread, commission and swap, puts one
    un-costed leg beside costed ones — and the combined line, the per-leg contribution and every
    delta on the page are then a mixture of the strategies and the physics. This app has shipped
    that defect three times across two runs (the tuning workbench, the stress-test children, the
    stack rerun); here it would sit in a single stack with nothing to compare against.

    Watched RED by dropping the two cost columns from `find_matching_stack_run`'s WHERE clause:
    the charged request then reuses both free runs and `reuse_count` is 2.
    """
    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "lab.db")
    _stack_leg_with_params(
        tmp_path / "lab.db", tmp_path / "reports", {"exec_risk_pct": 2.5}, mode="screen"
    )
    lab_db.upsert_strategy(
        {
            "id": "sos_fade",
            "name": "SOS Fade",
            "runner": "python",
            "class_name": "SosFadeStrategy",
            "source_path": "strategies/python/sos_fade",
            "scanned_at": 1,
            "param_schema": [],
            "default_params": {},
        }
    )
    for i, sid in enumerate(("b_leg", "sos_fade")):
        lab_db.insert_run(
            {
                "run_id": f"r_free_{i}",
                "strategy_id": sid,
                "instrument": "XAUUSD",
                "params": {},
                "bar_type": "Minute",
                "bar_value": 15,
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "commission_per_side": 0.0,
                "slippage_ticks": 0,
                "status": "complete",
                "created_at": 2,
                "runner": "python",
                "cost_layers": [],
            }
        )
        lab_db.update_run_complete(
            f"r_free_{i}",
            {"trade_count": 1, "net_pnl": 1.0},
            {"equity_curve": None, "trades": None, "daily_pnl": None},
        )

    body = {
        "strategy_ids": ["b_leg", "sos_fade"],
        "instrument": "XAUUSD",
        "bar_type": "Minute",
        "bar_value": 15,
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "commission_per_side": 0.0,
        "slippage_ticks": 0,
        "mode": "screen",
    }
    # The control: asking on the SAME basis the runs were measured on reuses both, so the
    # refusal below is about the basis rather than about anything else being mismatched.
    free = client.post("/backtests/stacks/preview", json={**body, "charge_costs": False}).json()
    assert free["reuse_count"] == 2

    charged = client.post("/backtests/stacks/preview", json={**body, "charge_costs": True}).json()
    assert charged["reuse_count"] == 0
    assert {leg["action"] for leg in charged["legs"]} == {"run"}


def test_the_shared_LAUNCH_can_actually_be_CALLED(client, tmp_path, monkeypatch):
    """🔴 NOTHING IN THIS SUITE EVER STARTED A STACK, so a launch that could not even be called
    passed all 1,196 backend tests (found 2026-09-02 by the linter, not by a test).

    `_trigger_shared_stack` was handed two new arguments and its own signature was not updated —
    every shared launch would have died on a `TypeError` at the call site, a 500 on the one
    button the whole page exists for. It survived because this file seeds its rows straight
    through `lab_db` and posts only to `/preview`: **the trigger endpoint had no test at all, in
    either mode.**

    That is the shape `.claude/mcp/check_tradingbox.py` already names in its own docstring — a
    suite whose cases all assert what a feature REFUSES certifies a feature with no working happy
    path, because a thing that always fails satisfies every refusal test beautifully. The cost
    tests above are exactly that kind: they assert a reuse is declined. This one asserts the
    thing runs.

    It also pins the cost basis onto the LAUNCH, which is the half no stored row can show: the
    settings dict is what `run_stack` prices the replay from, so a stack could store a charged
    basis and still replay free.

    MUTATION: remove `cost_layers` / `commission_per_side` from `_trigger_shared_stack`'s
    parameter list and this goes red while the other 36 tests here stay green — which is the
    whole point of it existing.
    """
    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "lab.db")
    lab_db.init_db()
    for sid, cls in (("b_leg", "BLegStrategy"), ("sos_fade", "SosFadeStrategy")):
        lab_db.upsert_strategy(
            {
                "id": sid,
                "name": sid,
                "runner": "python",
                "class_name": cls,
                "source_path": f"strategies/python/{sid}",
                "scanned_at": 1,
                "param_schema": [],
                "default_params": {},
            }
        )

    # Capture instead of replay — the simulation is `backtest/portfolio/`'s to test, and firing
    # it here would run two real backtests inside the unit suite.
    fired: dict = {}
    monkeypatch.setattr(
        "routers.stacks.portfolio_runner.launch",
        lambda stack_id, legs, settings: fired.update(
            stack_id=stack_id, legs=legs, settings=settings
        ),
    )

    # ⚠ The trigger is `/backtests/stack`, SINGULAR — every other route on this router is
    # `/stacks`, and posting the plural returns 405 rather than anything that reads like a
    # missing endpoint. Worth pinning by using it.
    resp = client.post(
        "/backtests/stack",
        json={
            "strategy_ids": ["b_leg", "sos_fade"],
            "instrument": "XAUUSD",
            "bar_type": "Minute",
            "bar_value": 15,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "mode": "shared",
            "account_size": 10_000.0,
            "risk_cap_pct": 10.0,
            "entry_floor_pct": 0.0,
        },
    )
    assert resp.status_code == 202, resp.text
    stack_id = resp.json()["stack_id"]

    # It reached the runner at all — this is the assertion the missing parameters broke.
    assert fired["stack_id"] == stack_id

    # ⚠ Costs default ON, so the resolved layers must be on the settings the replay is priced
    # from. Asserting non-empty rather than a fixed list: WHICH layers a broker charges is
    # `python_runner.charged_layers`'s business and has its own tests — pinning the list here
    # would make this test fail for a reason that has nothing to do with what it is guarding.
    assert fired["settings"]["cost_layers"]
    assert fired["settings"]["broker_profile"]

    # And the same basis is STORED, or the page would describe a run it did not price.
    stored = lab_db.get_stack_settings(stack_id)
    assert json.loads(stored["cost_layers"]) == fired["settings"]["cost_layers"]


# ── The Stacks LIST could not be read without opening every row ────────────────────────────


def test_the_list_carries_the_portfolios_own_result(client, tmp_path, monkeypatch):
    """The stacks list had no result column at all — every other list in this app has one.

    It is the SUM of the legs', which is the same arithmetic the detail page composes its Made
    hero from, so the two cannot disagree about what a stack made.

    MUTATION: drop `net_pnl`/`trade_count` from the members SELECT in `list_stacks` and this
    goes red.
    """
    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "lab.db")
    _stack_leg_with_params(tmp_path / "lab.db", tmp_path / "reports", {})

    row = next(r for r in client.get("/backtests/stacks").json() if r["stack_id"] == "st_p")
    assert row["net_pnl"] == 500.0
    assert row["trade_count"] == 1
    # And by ID, so a strategy page can find its stacks without matching a display name.
    assert row["strategy_ids"] == ["b_leg"]


def test_a_stack_with_nothing_finished_reports_NO_result_rather_than_zero(
    client,
    tmp_path,
    monkeypatch,
):
    """🔴 `sum([])` is `0.0`, and a fabricated zero is indistinguishable from a measured one.

    A stack still replaying and a stack that made exactly nothing are different facts, and the
    list renders the first as an em-dash. This is the repo's own rule — never let "no" and
    "cannot ask" be the same value — reaching the newest column on the page.

    MUTATION: replace `_sum_or_none` with a plain `sum(...)` and this goes red on `None`.
    """
    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "lab.db")
    lab_db.init_db()
    lab_db.upsert_strategy(
        {
            "id": "b_leg",
            "name": "B-LEG",
            "runner": "python",
            "class_name": "BLegStrategy",
            "source_path": "strategies/python/b_leg",
            "scanned_at": 1,
            "param_schema": [],
            "default_params": {},
        }
    )
    lab_db.insert_stack(
        {
            "stack_id": "st_run",
            "instrument": "XAUUSD",
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
    lab_db.insert_run(
        {
            "run_id": "r_run",
            "strategy_id": "b_leg",
            "instrument": "XAUUSD",
            "params": {},
            "bar_type": "Minute",
            "bar_value": 15,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "commission_per_side": 0.0,
            "slippage_ticks": 0,
            "status": "running",
            "created_at": 1,
            "stack_id": "st_run",
            "runner": "python",
        }
    )
    lab_db.add_stack_member("st_run", "r_run", owned=1, position=0)

    row = next(r for r in client.get("/backtests/stacks").json() if r["stack_id"] == "st_run")
    assert row["net_pnl"] is None
    assert row["trade_count"] is None


# ── The COMBINED book — what the shared ACCOUNT itself did, trade by trade ────


@dataclass
class _FakeTrade:
    """The trade duck-type `backtest/output.build_results` actually reads.

    Deliberately a plain object rather than the real trade class: this file tests the lab's
    seams around the simulation, never the simulation, and a fixture that could only be produced
    by a full replay would make these tests unrunnable without one.
    """

    entry_ms: int
    exit_ms: int
    pnl_usd: float
    dir: int = 1
    qty: float = 1.0
    entry_price: float = 2000.0
    exit_price: float = 2010.0
    stop_distance: float = 10.0
    exit_reason: str = "target"
    r: float = 1.0


class _FakeRun:
    """The fields `_persist` reads off a finished stack replay."""

    def __init__(self, trades, per_leg, opening, closing):
        self.trades = list(trades)
        self.per_leg = dict(per_leg)
        self.solo_per_leg = {k: list(v) for k, v in per_leg.items()}
        self.solo_closing = dict.fromkeys(per_leg, 0.0)
        self.blocked_per_leg = {}
        self.missed_per_leg = {}
        self.contention = []
        self.opening_balance = opening
        self.closing_balance = closing
        self.risk_cap_pct = 0.10
        self.entry_floor_pct = 0.0
        self.peak_reserved_pct = 0.05
        self.peak_concurrent = 1
        self.cancelled = False


class _Cfg:
    point_value = 1.0


class _Spec:
    def __init__(self, name, point_value=1.0):
        self.name = name
        self.config = _Cfg()
        self.config.point_value = point_value


def _persist_a_stack(tmp_path, monkeypatch, *, a_trades, b_trades, closing=None):
    """Run `_persist` over two legs and hand back the stack dir."""
    from services import portfolio_runner

    monkeypatch.setattr(portfolio_runner, "_LAB_RESULTS_DIR", tmp_path)
    monkeypatch.setattr(portfolio_runner, "_write_leg", lambda *a, **k: None)

    opening = 10_000.0
    total = sum(t.pnl_usd for t in a_trades) + sum(t.pnl_usd for t in b_trades)
    run = _FakeRun(
        list(a_trades) + list(b_trades),
        {"leg_a": a_trades, "leg_b": b_trades},
        opening,
        opening + total if closing is None else closing,
    )
    portfolio_runner._persist(
        "st_combined",
        [
            {"strategy_id": "leg_a", "run_id": "r_a", "ruleset_ids": []},
            {"strategy_id": "leg_b", "run_id": "r_b", "ruleset_ids": []},
        ],
        [_Spec("leg_a"), _Spec("leg_b")],
        run,
        {},
        {},
    )
    return tmp_path / "st_combined"


def test_the_COMBINED_book_is_KEPT_not_reduced_to_two_scalars(tmp_path, monkeypatch):
    """🔴 `_persist` stored `combined_trades` and `combined_r` and threw the ACCOUNT's own trade
    stream away — so the one thing a shared stack exists to produce was computed on every run and
    never written. Nothing could grade a stack because there was nothing to grade.

    Watched RED: with the combined block removed the files are absent and this fails on the
    first read.
    """
    from services import portfolio_runner

    sdir = _persist_a_stack(
        tmp_path,
        monkeypatch,
        a_trades=[_FakeTrade(1_000, 2_000, 500.0)],
        b_trades=[_FakeTrade(3_000, 4_000, -200.0)],
    )
    eq, dp = portfolio_runner.combined_book("st_combined")
    assert [p["profit"] for p in eq] == [500.0, -200.0]
    assert sum(d["pnl"] for d in dp) == 300.0
    assert (
        json.loads((sdir / "shared_summary.json").read_text())["combined_kpis"]["trade_count"] == 2
    )


def test_the_combined_curve_is_in_EXIT_ORDER_across_legs_not_grouped_by_leg(tmp_path, monkeypatch):
    """⚠ The simulator hands `run.trades` over grouped BY LEG — every leg A trade, then every leg B
    trade — and an account's book in that order is not the account's book. `build_equity_curve`
    sorts on exit time, which is the ONLY reason passing it that list is safe.

    Watched RED by sorting the trades by leg instead: the curve then reads 500, 100, -200.
    """
    from services import portfolio_runner

    _persist_a_stack(
        tmp_path,
        monkeypatch,
        a_trades=[_FakeTrade(1_000, 2_000, 500.0), _FakeTrade(9_000, 10_000, 100.0)],
        b_trades=[_FakeTrade(3_000, 4_000, -200.0)],
    )
    eq, _ = portfolio_runner.combined_book("st_combined")
    assert [p["profit"] for p in eq] == [500.0, -200.0, 100.0]


def test_the_combined_curve_is_CHECKED_against_the_account_balance(tmp_path, monkeypatch):
    """The curve is walked from the opening balance over the trades; the account tracked its
    balance live. They must agree — and when they do not, the account applied something no trade
    carries, which is a defect in the seam rather than a rounding difference.

    Watched RED by pinning the flag to True.
    """
    ok = _persist_a_stack(
        tmp_path,
        monkeypatch,
        a_trades=[_FakeTrade(1_000, 2_000, 500.0)],
        b_trades=[_FakeTrade(3_000, 4_000, -200.0)],
    )
    assert json.loads((ok / "shared_summary.json").read_text())["combined_curve_agrees"] is True

    bad = _persist_a_stack(
        tmp_path / "other",
        monkeypatch,
        a_trades=[_FakeTrade(1_000, 2_000, 500.0)],
        b_trades=[_FakeTrade(3_000, 4_000, -200.0)],
        closing=99_999.0,
    )
    assert json.loads((bad / "shared_summary.json").read_text())["combined_curve_agrees"] is False


def test_legs_disagreeing_on_CONTRACT_SIZE_are_refused_rather_than_priced_at_one_of_them(
    tmp_path, monkeypatch
):
    """A stack is one instrument, so its legs must agree. Taking whichever leg happened to be last
    would price the other leg's trades at the wrong size and report it as the account's book."""
    from services import portfolio_runner

    with pytest.raises(ValueError, match="disagree on contract size"):
        portfolio_runner._stack_point_value([_Spec("leg_a", 1.0), _Spec("leg_b", 100.0)])
    assert (
        portfolio_runner._stack_point_value([_Spec("leg_a", 100.0), _Spec("leg_b", 100.0)]) == 100.0
    )


def test_a_stack_with_NO_combined_book_reports_empty_and_never_an_exception(tmp_path, monkeypatch):
    """⚠ Empty means NOT STORED — a screen, or a stack replayed before the combined book existed.
    A caller rendering it as a flat account is reporting a stack that never ran as one that
    traded nothing."""
    from services import portfolio_runner

    monkeypatch.setattr(portfolio_runner, "_LAB_RESULTS_DIR", tmp_path)
    assert portfolio_runner.combined_book("st_nothing") == ([], [])


def test_the_combined_KPIs_carry_the_CANONICAL_sharpe(tmp_path, monkeypatch):
    """Every other book in this app has its Sharpe stamped from daily P&L at completion. A stack
    computing its own differently would be a second answer to the same question — and the grader
    reads this one."""
    sdir = _persist_a_stack(
        tmp_path,
        monkeypatch,
        a_trades=[_FakeTrade(1_000, 2_000, 500.0), _FakeTrade(200_000_000, 300_000_000, 250.0)],
        b_trades=[_FakeTrade(3_000, 4_000, -200.0)],
    )
    kpis = json.loads((sdir / "shared_summary.json").read_text())["combined_kpis"]
    assert "sharpe" in kpis
