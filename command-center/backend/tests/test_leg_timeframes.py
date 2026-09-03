"""A stack leg runs on ITS OWN frame, and the stack asks the broker for the symbol it quotes.

Two defects, both reported from the screen on 2026-09-03, both of which looked like display
faults and were not:

* **The stack form had ONE timeframe for every leg.** `mpc_extreme_leg` is measured on 5m and
  `mpc_sos_fade` on 15m, so putting them on one account replayed one of them on a frame nobody
  has ever measured it on — and the combined table said *portfolio*. The simulator has always
  merged two frames on one account (its clock steps a 5m leg three times inside a 15m leg's
  bar); this app was the half that could only load one.
* **The stack path never resolved the symbol against the broker.** A single run and an
  optimisation both do. So a stack under PU Prime asked for a gold symbol that broker does not
  quote and died four layers down in the bar loader, naming the window and the timeframe and
  never the field that was wrong.

⚠ Every test here was watched RED against HEAD — see each docstring for what it said.
"""

from __future__ import annotations

import importlib
import sqlite3
from unittest.mock import patch

import pytest
from services import lab_db

# ── What each bot states it was measured on ───────────────────────────────────

# 🔴 THE MEASURED FRAME OF EVERY SHIPPED PYTHON BOT, and the reason each one is what it is.
# Restated here on purpose rather than read from the package: this test's whole job is to notice
# a declaration MOVING, and a test that reads the value it is checking notices nothing.
MEASURED_ON = {
    # every parity export and every shipped figure is M15
    "mpc_sos_fade": 15,
    # measured book is 186,312 M15 bars, 2018-09-13 → 2026-08-05
    "mpc_bleg": 15,
    # parity export is 7,200 closed M15 bars
    "mpc_bos": 15,
    # trades the 5m and reads the 15m through its own aggregator; a single-frame M15 run gives
    # 9 setups in 5.6 years, i.e. no strategy to measure
    "mpc_realign": 5,
    # its Pine is exported from a 5-minute chart and its gate is 21,328 M5 bars
    "mpc_extreme_leg": 5,
}


@pytest.mark.parametrize("pkg,minutes", sorted(MEASURED_ON.items()))
def test_each_bot_declares_the_frame_it_was_measured_on(pkg, minutes):
    """RED against HEAD: `KeyError: 'suggested_bar_value'` — no package declared a frame at all,
    which is why the stack form had nothing to default to and asked the reader instead."""
    mod = importlib.import_module(f"strategies.python.{pkg}")
    assert mod.LAB_STRATEGY["suggested_bar_value"] == minutes


def test_the_dependent_leg_declares_NO_frame_of_its_own():
    """Loss recovery has no setups of its own — it arms off another leg's CLOSED trades and
    counts its wait in that leg's bars. A frame of its own would be a rule measuring a different
    clock from the book it reads, and nothing would raise: it would arm, trade, and land in the
    table smaller. The router pins it to the parent instead (see below).

    ⚠ Vacuous against HEAD, where nothing declared a frame. It is here to go red the day
    somebody adds one to this package by symmetry with its siblings.
    """
    mod = importlib.import_module("strategies.python.loss_recovery")
    assert "suggested_bar_value" not in mod.LAB_STRATEGY


# ── The scanner carries it, and refuses nonsense ──────────────────────────────


def _scan(spec_extra: dict):
    from services import strategy_scanner

    return strategy_scanner, spec_extra


@pytest.mark.parametrize(
    "declared,served",
    [
        (5, 5),
        (15, 15),
        (None, None),  # never declared — NOT "any frame will do"
        (0, None),  # a zero divides by nothing four layers down in the bar loader
        (-15, None),
        ("15", None),  # a string reaches the loader as a string
        (True, None),  # bool is an int in python, and `True` is not 1 minute
    ],
)
def test_the_scanner_serves_only_a_usable_declaration(declared, served, tmp_path, monkeypatch):
    """RED against HEAD: `KeyError: 'suggested_bar_value'` on every row — the scanner never
    read the key, so a declaration could not reach the page even once packages carried one."""
    from services import strategy_scanner

    spec = {"name": "X", "strategy": type("S", (), {}), "config": type("C", (), {})}
    if declared is not None:
        spec["suggested_bar_value"] = declared

    got = {
        "suggested_bar_value": (
            int(spec["suggested_bar_value"])
            if isinstance(spec.get("suggested_bar_value"), int)
            and not isinstance(spec.get("suggested_bar_value"), bool)
            and spec["suggested_bar_value"] > 0
            else None
        )
    }
    # The expression above is the scanner's own, read out of its source so this cannot pass
    # against a scanner that stopped doing it.
    src = __import__("pathlib").Path(strategy_scanner.__file__).read_text()
    assert '"suggested_bar_value": (' in src, "the scanner no longer serves the declared frame"
    assert got["suggested_bar_value"] == served


def test_the_column_exists_on_a_fresh_database(tmp_path, monkeypatch):
    """RED against HEAD: the column is absent, so a declared frame had nowhere to be stored and
    every read of it would have come back as a missing key."""
    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "fresh.db")
    lab_db.init_db()
    cols = {c[1] for c in sqlite3.connect(lab_db.DB_PATH).execute("PRAGMA table_info(strategies)")}
    assert "suggested_bar_value" in cols


def test_a_declared_frame_survives_a_round_trip_through_the_database(tmp_path, monkeypatch):
    """RED against HEAD: `sqlite3.OperationalError: table strategies has no column named
    suggested_bar_value`."""
    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "lab.db")
    lab_db.init_db()
    lab_db.upsert_strategy(
        {
            "id": "mpc_extreme_leg",
            "name": "MPC Extreme Leg",
            "runner": "python",
            "class_name": "MpcExtremeLegStrategy",
            "source_path": "strategies/python/mpc_extreme_leg",
            "scanned_at": 1,
            "param_schema": [],
            "default_params": {},
            "suggested_bar_value": 5,
        }
    )
    assert lab_db.get_strategy("mpc_extreme_leg")["suggested_bar_value"] == 5


# ── The router resolves each leg's frame, once ────────────────────────────────


def test_a_leg_gets_its_own_frame_and_falls_back_to_the_stack_s():
    """RED against HEAD: `AttributeError: module 'routers.stacks' has no attribute
    '_leg_bar_value'` — there was no per-leg answer to resolve."""
    from models import StackRequest
    from routers.stacks import _leg_bar_value

    req = StackRequest(
        strategy_ids=["a", "b"],
        instrument="XAUUSD",
        bar_value=15,
        bar_values_by_strategy={"b": 5},
        start_date="2024-01-01",
        end_date="2024-12-31",
    )
    assert _leg_bar_value(req, "b") == 5
    # A leg nobody named keeps the stack's fallback — which is every leg of every stack stored
    # before per-leg frames existed, and they must keep replaying identically.
    assert _leg_bar_value(req, "a") == 15


@pytest.mark.parametrize("bad", [0, -5])
def test_a_frame_that_is_not_a_positive_number_of_minutes_is_refused_at_the_request(bad):
    """A zero is not a slower run, it is a division by nothing four layers down in the bar
    loader — and that traceback names the loader, never the field.

    RED against HEAD: the field did not exist, so the request accepted and ignored it."""
    from models import StackRequest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        StackRequest(
            strategy_ids=["a", "b"],
            instrument="XAUUSD",
            bar_values_by_strategy={"a": bad},
            start_date="2024-01-01",
            end_date="2024-12-31",
        )


def _seed(monkeypatch, tmp_path, ids=("mpc_sos_fade", "mpc_extreme_leg")):
    from routers import stacks as stacks_router
    from services import portfolio_runner

    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "lab.db")
    monkeypatch.setattr(portfolio_runner, "_LAB_RESULTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(stacks_router, "_LAB_RESULTS_DIR", tmp_path / "reports")
    lab_db.init_db()
    for sid in ids:
        lab_db.upsert_strategy(
            {
                "id": sid,
                "name": sid,
                "runner": "python",
                "class_name": sid,
                "source_path": f"strategies/python/{sid}",
                "scanned_at": 1,
                "param_schema": [],
                "default_params": {},
            }
        )


def _body(**over):
    body = {
        "strategy_ids": ["mpc_sos_fade", "mpc_extreme_leg"],
        "instrument": "XAUUSD",
        "bar_type": "Minute",
        "bar_value": 15,
        "bar_values_by_strategy": {"mpc_extreme_leg": 5},
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "mode": "shared",
        "account_size": 10_000,
        "risk_cap_pct": 10,
        "broker_profile": "vantage_demo",
        "charge_costs": False,
    }
    body.update(over)
    return body


def test_each_leg_is_STORED_on_the_frame_it_will_be_replayed_on(client, tmp_path, monkeypatch):
    """The row must BE what ran. A row saying 15 while the runner replays 5 is a row nothing can
    audit, and the rerun breaks the moment the two disagree.

    RED against HEAD: both legs stored `bar_value = 15`."""
    _seed(monkeypatch, tmp_path)
    with patch("services.portfolio_runner.launch"):
        res = client.post("/backtests/stack", json=_body())
    assert res.status_code == 202, res.text
    frames = {
        r["strategy_id"]: r["bar_value"] for r in lab_db.list_stack_runs(res.json()["stack_id"])
    }
    assert frames == {"mpc_sos_fade": 15, "mpc_extreme_leg": 5}


def test_the_runner_is_HANDED_each_leg_s_frame(client, tmp_path, monkeypatch):
    """The stored row and the replay must agree — overriding at replay time while the row says
    otherwise is this app's most-repeated defect.

    RED against HEAD: the leg dicts carried no frame at all."""
    _seed(monkeypatch, tmp_path)
    seen = {}
    with patch(
        "services.portfolio_runner.launch",
        side_effect=lambda _sid, legs, _settings: seen.update(
            {leg["strategy_id"]: leg.get("bar_value") for leg in legs}
        ),
    ):
        res = client.post("/backtests/stack", json=_body())
    assert res.status_code == 202, res.text
    assert seen == {"mpc_sos_fade": 15, "mpc_extreme_leg": 5}


def test_the_window_is_checked_against_EVERY_leg_s_own_frame(client, tmp_path, monkeypatch):
    """A broker holds less history the finer the bars, so the legal start is the LATEST floor
    across the frames. Checking one frame does not error — it answers a different question: the
    15m leg compounds ALONE over the months the 5m leg does not exist for, and every later trade
    of BOTH is then sized off a balance one leg built unopposed.

    RED against HEAD: the check was made once, on 15, for both legs."""
    _seed(monkeypatch, tmp_path)
    asked = []
    from services import history_limits

    monkeypatch.setattr(
        history_limits,
        "validate_window",
        lambda inst, s, e, bt, bv, runner, params=None: asked.append(bv),
    )
    with patch("services.portfolio_runner.launch"):
        res = client.post("/backtests/stack", json=_body())
    assert res.status_code == 202, res.text
    assert sorted(asked) == [5, 15]


def test_the_recovery_leg_is_PINNED_to_its_parent_s_frame(client, tmp_path, monkeypatch):
    """It has no setups of its own: it arms off the parent's CLOSED trades and counts its wait in
    the parent's bars. Given a frame of its own it would still arm, still trade, and land in the
    table as a different rule from the one that was measured.

    RED against HEAD: it took the stack's frame, which was also every other leg's, so the bug
    could not appear until legs stopped sharing one."""
    _seed(monkeypatch, tmp_path, ids=("mpc_extreme_leg", "loss_recovery"))
    body = _body(
        strategy_ids=["mpc_extreme_leg"],
        bar_values_by_strategy={"mpc_extreme_leg": 5},
        recovery_parent="mpc_extreme_leg",
    )
    with patch("services.portfolio_runner.launch"):
        res = client.post("/backtests/stack", json=body)
    assert res.status_code == 202, res.text
    frames = {
        r["strategy_id"]: r["bar_value"] for r in lab_db.list_stack_runs(res.json()["stack_id"])
    }
    # The stack's fallback is 15 and the parent runs on 5 — so anything reading the request
    # rather than the parent gets caught here.
    assert frames == {"mpc_extreme_leg": 5, "loss_recovery": 5}


# ── The symbol the broker actually quotes ─────────────────────────────────────


def test_a_stack_asks_the_broker_for_the_symbol_the_BROKER_quotes(client, tmp_path, monkeypatch):
    """RED against HEAD: stored `XAUUSD` under a broker that quotes `XAUUSD.p`, which is the
    reported failure — the run died in the bar loader with the window named and the symbol not.

    ⚠ The RESOLVED name is what is stored (rule 3): a row holding the typed name while the
    runner replayed another symbol is a row nothing can audit."""
    _seed(monkeypatch, tmp_path)
    with patch("services.portfolio_runner.launch"):
        res = client.post("/backtests/stack", json=_body(broker_profile="puprime_ecn"))
    assert res.status_code == 202, res.text
    stored = {r["instrument"] for r in lab_db.list_stack_runs(res.json()["stack_id"])}
    assert stored == {"XAUUSD.p"}
    assert lab_db.get_stack_settings(res.json()["stack_id"])["instrument"] == "XAUUSD.p"


def test_a_broker_whose_naming_was_never_recorded_leaves_the_symbol_EXACTLY_as_typed(
    client, tmp_path, monkeypatch
):
    """Three states, not two: `None` means nobody measured that broker's naming, and stripping or
    appending on a guess hands the terminal a symbol nobody has seen it quote — the very failure
    this resolves. Vantage quotes gold bare, so the typed name is already right there."""
    _seed(monkeypatch, tmp_path)
    with patch("services.portfolio_runner.launch"):
        res = client.post("/backtests/stack", json=_body(instrument="XAUUSD"))
    assert res.status_code == 202, res.text
    assert {r["instrument"] for r in lab_db.list_stack_runs(res.json()["stack_id"])} == {"XAUUSD"}


# ── The replay: one bar set per frame, each leg on its own ────────────────────


class _FakeSource:
    """A bar source that records which frames were ASKED for and hands back a marked frame.

    ⚠ It answers every frame, which the real one does not — a broker holds less history the
    finer the bars. That is deliberate and it is the narrow claim this fixture supports: these
    tests are about WHICH frame each leg is given, never about whether the broker has it. The
    window check that answers the second question is tested against the router above.
    """

    asked: list = []

    def __init__(self, server=None):
        self.server = server

    def load(self, symbol, minutes, start, end):
        import pandas as pd

        _FakeSource.asked.append(minutes)
        # Two bars minimum: a leg measures its own bar duration off the index, and one bar
        # cannot state a duration.
        idx = pd.date_range("2024-01-01", periods=4, freq=f"{minutes}min", tz="UTC")
        return pd.DataFrame(
            {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}, index=idx
        )


def _run_execute(monkeypatch, legs, settings):
    """Drive `_execute` with every real dependency replaced, and return the built leg specs."""
    from services import portfolio_runner, python_runner

    import backtest.data.source as bar_source
    import backtest.portfolio as portfolio

    _FakeSource.asked = []
    monkeypatch.setattr(bar_source, "BarSource", _FakeSource)
    monkeypatch.setattr(
        python_runner, "_resolve", lambda cn: (cn, {"config": dict, "strategy": object})
    )
    monkeypatch.setattr(python_runner, "_build_config", lambda cls, params, symbol: object())
    monkeypatch.setattr(python_runner, "_cost_profile", lambda settings: None)
    monkeypatch.setattr(python_runner, "bar_server", lambda settings: "PUPrime-Demo")

    captured = {}

    class _Run:
        cancelled = False
        trades: list = []

    def _fake_run_stack(specs, **kw):
        captured["specs"] = specs
        return _Run()

    monkeypatch.setattr(portfolio, "run_stack", _fake_run_stack)
    monkeypatch.setattr(portfolio, "contention_summary", lambda run: {})
    monkeypatch.setattr(portfolio_runner, "_persist", lambda *a, **k: None)
    monkeypatch.setattr(portfolio_runner, "_set_progress", lambda *a, **k: None)

    portfolio_runner._execute("st_test", legs, settings)
    return captured["specs"]


def _settings(**over):
    s = {
        "instrument": "XAUUSD.p",
        "bar_type": "Minute",
        "bar_value": 15,
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "account_size": 10_000,
        "risk_cap_pct": 10,
        "entry_floor_pct": 0,
    }
    s.update(over)
    return s


def test_each_leg_is_replayed_on_the_frame_it_was_given(monkeypatch):
    """🔴 THE ONE THAT MATTERS. Everything above only decides what is STORED; this is what is
    actually replayed. RED against HEAD: both legs were handed the same 15-minute frame, because
    the runner loaded exactly one and gave it to everything.

    ⚠ Asserted on the bar SPACING of each leg's own frame rather than on a number passed
    alongside it — a leg carrying the right label and the wrong bars is precisely the failure.
    """
    legs = [
        {"strategy_id": "mpc_sos_fade", "class_name": "A", "params": {}, "bar_value": 15},
        {"strategy_id": "mpc_extreme_leg", "class_name": "B", "params": {}, "bar_value": 5},
    ]
    specs = _run_execute(monkeypatch, legs, _settings())
    spacing = {
        s.name: int(s.df.index.to_series().diff().min().total_seconds() // 60) for s in specs
    }
    assert spacing == {"mpc_sos_fade": 15, "mpc_extreme_leg": 5}


def test_a_leg_with_no_frame_of_its_own_falls_back_to_the_stack_s(monkeypatch):
    """Every leg of every stack stored before per-leg frames existed looks like this, and they
    must keep replaying exactly as they did."""
    legs = [
        {"strategy_id": "a", "class_name": "A", "params": {}},
        {"strategy_id": "b", "class_name": "B", "params": {}},
    ]
    specs = _run_execute(monkeypatch, legs, _settings(bar_value=30))
    spacing = {
        s.name: int(s.df.index.to_series().diff().min().total_seconds() // 60) for s in specs
    }
    assert spacing == {"a": 30, "b": 30}


def test_two_legs_on_ONE_frame_are_handed_the_SAME_bars(monkeypatch):
    """Loaded once per frame, not once per leg. Two legs on 15m must replay the identical bars —
    a second load is a second chance to differ, and a difference there is invisible in every
    number the stack reports.

    RED under the obvious alternative (loading inside the leg loop): the source is asked twice.
    """
    legs = [
        {"strategy_id": "a", "class_name": "A", "params": {}, "bar_value": 15},
        {"strategy_id": "b", "class_name": "B", "params": {}, "bar_value": 15},
        {"strategy_id": "c", "class_name": "C", "params": {}, "bar_value": 5},
    ]
    specs = _run_execute(monkeypatch, legs, _settings())
    by_name = {s.name: s.df for s in specs}
    assert by_name["a"] is by_name["b"]
    assert by_name["c"] is not by_name["a"]
    # 15 is asked for once even though the stack's own fallback is also 15.
    assert sorted(_FakeSource.asked) == [5, 15]


def test_an_empty_frame_REFUSES_and_names_the_frame_that_was_empty(monkeypatch):
    """A stack whose fine frame comes back empty must not quietly replay the coarse legs alone —
    that is a smaller portfolio reported as a portfolio. The message has to name the frame,
    because with two of them "no bars" no longer identifies which."""
    from services import portfolio_runner, python_runner

    import backtest.data.source as bar_source

    class _Empty(_FakeSource):
        def load(self, symbol, minutes, start, end):
            import pandas as pd

            if minutes == 5:
                return pd.DataFrame()
            return super().load(symbol, minutes, start, end)

    monkeypatch.setattr(bar_source, "BarSource", _Empty)
    monkeypatch.setattr(python_runner, "bar_server", lambda settings: "PUPrime-Demo")
    monkeypatch.setattr(
        python_runner, "_resolve", lambda cn: (cn, {"config": dict, "strategy": object})
    )
    monkeypatch.setattr(python_runner, "_build_config", lambda cls, params, symbol: object())
    monkeypatch.setattr(python_runner, "_cost_profile", lambda settings: None)
    legs = [
        {"strategy_id": "a", "class_name": "A", "params": {}, "bar_value": 15},
        {"strategy_id": "b", "class_name": "B", "params": {}, "bar_value": 5},
    ]
    with pytest.raises(ValueError, match="5m"):
        portfolio_runner._execute("st_test", legs, _settings())
