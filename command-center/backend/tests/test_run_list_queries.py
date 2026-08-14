"""The runs list's queries and contracts.

Three fixes from the 2026-08-06 audit, each of which was invisible from the response:

* `GET /backtests/runs` called `get_run_verdict_summary` PER ROW — a fresh sqlite connection and
  two PRAGMAs each — on a list that is polled every 3s while anything runs.
* There was no way to ask for the runs DERIVED from one run, so the run page pulled the whole lab
  (~1.7 KB per run) to render one badge.
* `cost_layers` could not be sent as `null`, so NT8/MT5 runs were stored `[]` — "deliberately
  charged nothing" — and the detail page called them frictionless over a tester that charged.
"""

import time
from unittest.mock import patch


def _strategy(lab_db, sid="q_strategy", runner="python"):
    lab_db.upsert_strategy(
        {
            "id": sid,
            "name": "Query Strategy",
            "runner": runner,
            "class_name": "QueryStrategy",
            "source_path": f"strategies/python/{sid}",
            "scanned_at": int(time.time()),
            "param_schema": [],
            "default_params": {},
        }
    )
    return sid


def _run(
    lab_db, run_id, *, sid="q_strategy", source_run_id=None, sweep_id=None, optimization_id=None
):
    lab_db.insert_run(
        {
            "run_id": run_id,
            "strategy_id": sid,
            "instrument": "XAUUSD",
            "params": {},
            "bar_type": "Minute",
            "bar_value": 15,
            "start_date": "2024-01-01",
            "end_date": "2024-06-30",
            "commission_per_side": 0.0,
            "slippage_ticks": 0,
            "status": "complete",
            "created_at": int(time.time()),
            "runner": "python",
            "source_run_id": source_run_id,
        }
    )
    if sweep_id or optimization_id:
        # `insert_run` has no column for these; set them directly, which is what the sweep and
        # optimization insert paths do through their own inserts.
        with lab_db._connect() as conn:
            conn.execute(
                "UPDATE backtest_runs SET sweep_id = ?, optimization_id = ? WHERE run_id = ?",
                (sweep_id, optimization_id, run_id),
            )
    return run_id


# ── One query for every row's verdicts ────────────────────────────────────────


def test_verdict_summaries_key_every_requested_id(fresh_db):
    """A missing key and an empty list are different answers — the caller renders the second as
    "not graded" and would crash on the first."""
    from services import lab_db

    _strategy(lab_db)
    _run(lab_db, "vsum00000001")
    _run(lab_db, "vsum00000002")

    out = lab_db.get_run_verdict_summaries(["vsum00000001", "vsum00000002", "neverexisted"])
    assert set(out) == {"vsum00000001", "vsum00000002", "neverexisted"}
    assert out["neverexisted"] == []


def test_verdict_summaries_agree_with_the_per_run_query(fresh_db):
    """The bulk form replaces the per-row one; if they disagreed the list and the detail page
    would disagree about the same run's chips."""
    from services import lab_db

    _strategy(lab_db)
    run_id = _run(lab_db, "vsum00000003")
    lab_db.insert_evaluation(
        {
            "eval_id": "ev1",
            "run_id": run_id,
            "ruleset_id": "unconstrained",
            "verdict": "INFO",
            "drawdown_pass": True,
            "target_pass": True,
            "consistency_pass": None,
            "breach_count": 0,
            "notes": "Not graded",
        }
    )

    assert lab_db.get_run_verdict_summaries([run_id])[run_id] == lab_db.get_run_verdict_summary(
        run_id
    )


def test_the_runs_list_opens_one_connection_per_call_not_one_per_row(client, fresh_db):
    """The N+1. `_row_to_summary` asked per row, and every ask is a fresh `_connect()`."""
    from services import lab_db

    _strategy(lab_db)
    for i in range(6):
        _run(lab_db, f"nplus1{i:06d}")

    real_connect = lab_db._connect
    calls = {"n": 0}

    def _counting(*a, **kw):
        calls["n"] += 1
        return real_connect(*a, **kw)

    with patch("services.lab_db._connect", side_effect=_counting):
        r = client.get("/backtests/runs")

    assert r.status_code == 200
    assert len(r.json()) == 6
    # One for the list, one for the verdicts. The old code was 1 + 6.
    assert calls["n"] <= 3, f"{calls['n']} connections for 6 runs — the N+1 is back"


# ── The derived-runs filter ───────────────────────────────────────────────────


def test_source_run_id_filters_to_the_runs_derived_from_one_run(client, fresh_db):
    from services import lab_db

    _strategy(lab_db)
    parent = _run(lab_db, "parent000001")
    _run(lab_db, "child0000001", source_run_id=parent)
    _run(lab_db, "child0000002", source_run_id=parent)
    _run(lab_db, "unrelated001")

    r = client.get(f"/backtests/runs?source_run_id={parent}")
    assert r.status_code == 200
    assert {x["run_id"] for x in r.json()} == {"child0000001", "child0000002"}


def test_source_run_id_does_not_narrow_to_tuning_iterations(client, fresh_db):
    """A sweep and an optimization launched from a run stamp `source_run_id` too. Telling them
    apart is the CALLER's job (they carry `sweep_id` / `optimization_id`) — narrowing it here would
    make one field mean two different things depending on which query you asked."""
    from services import lab_db

    _strategy(lab_db)
    parent = _run(lab_db, "parent000002")
    _run(lab_db, "tweak0000001", source_run_id=parent)
    _run(lab_db, "sweepchild01", source_run_id=parent, sweep_id="sw_1")

    got = client.get(f"/backtests/runs?source_run_id={parent}").json()
    assert {x["run_id"] for x in got} == {"tweak0000001", "sweepchild01"}
    assert [x["sweep_id"] for x in got if x["run_id"] == "sweepchild01"] == ["sw_1"]


def test_no_source_run_id_still_lists_everything(client, fresh_db):
    """⚠ Passes against HEAD too, and is kept deliberately: it pins that adding the filter did not
    silently narrow the UNfiltered list, which is the half of the change nothing else checks."""
    from services import lab_db

    _strategy(lab_db)
    _run(lab_db, "plain0000001")
    _run(lab_db, "plain0000002", source_run_id="plain0000001")

    assert len(client.get("/backtests/runs").json()) == 2


# ── cost_layers: null is a different answer from [] ───────────────────────────


def test_a_run_can_be_created_with_no_layered_cost_contract(client, fresh_db):
    """`null` = this runner has no layer contract (NT8/MT5). `[]` = charge nothing.

    The model was `list[str] = []`, so the frontend could not express the first and sent `[]` for
    NT8/MT5 — which the detail page renders as "This run was deliberately frictionless", over a
    tester that really did charge the commission and slippage on the same row.
    """
    from services import lab_db

    _strategy(lab_db, "nt8_strategy", runner="ninjatrader")

    with (
        patch("services.runner_dispatch.start_backtest", return_value={"status": "ok"}),
        patch("services.runner_dispatch.inject_foundational", side_effect=lambda p, f: p),
    ):
        r = client.post(
            "/backtests/run",
            json={
                "strategy_id": "nt8_strategy",
                "instrument": "MNQ 06-26",
                "params": {},
                "start_date": "2024-01-01",
                "end_date": "2024-06-30",
                "commission_per_side": 2.25,
                "slippage_ticks": 1,
                "cost_layers": None,
                "evaluate_rulesets": [],
            },
        )

    assert r.status_code in (200, 202), r.text
    row = lab_db.get_run(r.json()["run_id"])
    assert row["cost_layers"] in (None, "")


def test_omitting_cost_layers_still_means_charge_nothing(client, fresh_db):
    """The default must not move — a caller that says nothing gets `[]`, exactly as before.

    ⚠ Passes against HEAD too, deliberately. It is the guard on the OTHER side of the nullable
    change: `insert_run` coerces an absent key to `[]` so a new python run can never fall into
    the legacy commission/slippage branch by omission, and only an EXPLICIT null writes NULL.
    """
    from routers.backtests import _json_list
    from services import lab_db

    _strategy(lab_db, "py_strategy", runner="python")

    with patch("services.runner_dispatch.start_backtest", return_value={"status": "ok"}):
        r = client.post(
            "/backtests/run",
            json={
                "strategy_id": "py_strategy",
                "instrument": "XAUUSD",
                "params": {},
                "start_date": "2024-01-01",
                "end_date": "2024-06-30",
                "evaluate_rulesets": [],
            },
        )

    assert r.status_code in (200, 202), r.text
    assert _json_list(lab_db.get_run(r.json()["run_id"])["cost_layers"]) == []


# ── The running-job endpoint must carry every lock scope ──────────────────────


def test_the_running_job_endpoint_reports_the_python_scope(client, fresh_db):
    """🔴 The endpoint named `nt8` and `mt5` and dropped `python` on the floor.

    `RunningJobStatus` DECLARES `python` with a `running=False` default, so the omission was
    silent and a python backtest reported its own platform free for its entire run. The gate was
    never affected — `ensure_platform_idle` reads `has_running_job`, which was right — but every
    control the UI gates on this response (the Runs list's Rerun, the detail page's Retry and
    Rerun, the Run modal, the Optimize button) stayed enabled through a python run and could only
    produce a 409 toast.
    """
    from services import lab_db

    _strategy(lab_db, "py_lock_strategy", runner="python")
    lab_db.insert_run(
        {
            "run_id": "pylock000001",
            "strategy_id": "py_lock_strategy",
            "instrument": "XAUUSD",
            "params": {},
            "bar_type": "Minute",
            "bar_value": 15,
            "start_date": "2024-01-01",
            "end_date": "2024-06-30",
            "commission_per_side": 0.0,
            "slippage_ticks": 0,
            "status": "running",
            "created_at": int(time.time()),
            "runner": "python",
        }
    )

    body = client.get("/backtests/running-job").json()
    assert body["python"]["running"] is True
    assert body["python"]["job_id"] == "pylock000001"
    # The other two scopes must partition — one job may not block a platform it never touches.
    assert body["nt8"]["running"] is False
    assert body["mt5"]["running"] is False


def test_every_lock_scope_reaches_the_api(client, fresh_db):
    """The response is DERIVED from the scope map rather than restated field by field, so a
    fourth scope cannot be dropped the way `python` was.

    ⚠ Passes against HEAD too, and is kept deliberately as a FORWARD guard rather than claimed as
    a catch: `RunningJobStatus` declares all three keys, so `python` was always PRESENT in the
    body — it was just always false, which is exactly what made the omission silent. This goes red
    only when a scope is added to `_SCOPE_RUNNER_SQL` and never reaches the model.
    """
    from services import lab_db

    body = client.get("/backtests/running-job").json()
    for scope in lab_db._SCOPE_RUNNER_SQL:
        assert scope in body, f"lock scope {scope!r} is computed but never served"
