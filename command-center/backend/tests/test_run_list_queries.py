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


# ── The cost switch (2026-08-24) ─────────────────────────────────────────────
#
# All four tests below were watched RED by MUTATION on 2026-08-24, each on its own assertion:
#   * `charge_costs` default flipped True → None ..... "omitting ... means CHARGED" fails
#   * the commission override deleted ................ "bills the ACCOUNT commission" fails
#   * the unmeasured-broker refusal removed .......... "an unmeasured broker refuses" fails
# The fourth (costs off still reachable) is the guard on the other side and passes throughout —
# it exists so a later "simplification" that hard-wires charging cannot land quietly, since the
# detail page's paired free re-run goes through exactly that path.


def test_omitting_cost_layers_now_means_CHARGED(client, fresh_db):
    """🔴 **The default REVERSED on 2026-08-24 and this test reversed with it.**

    It used to assert that a caller saying nothing got `[]` — frictionless. That was the 2026-08-02
    design, and Aaron's call on 2026-08-24 replaced it: a run nobody configured is a run you can't
    trade, and it must not be the first number the lab shows. A python run that states nothing now
    stores the resolved charged layers.

    ⚠ It still guards the OTHER side of the nullable change, which did NOT move: only an EXPLICIT
    null writes NULL, so NT8 and MT5 keep having no layer contract at all.
    """
    from routers.backtests import _json_list
    from services import lab_db, python_runner

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
    stored = _json_list(lab_db.get_run(r.json()["run_id"])["cost_layers"])
    assert stored == list(python_runner.CHARGED_LAYERS), (
        "a python run that configured nothing came out frictionless — that is the default "
        "reversed on 2026-08-24"
    )
    # Asserted by NAME rather than by count: `slippage` is deliberately not in the charged set
    # (it is a typed-in guess), and a test that only counted layers would wave it in.
    assert "slippage" not in stored


def test_costs_off_is_still_reachable_and_stores_empty(client, fresh_db):
    """Off is a deliberate choice, not an absence — and it must still be sayable.

    The paired free run behind the detail page's re-run button goes through exactly this path.
    """
    from services import lab_db

    _strategy(lab_db, "py_free", runner="python")
    with patch("services.runner_dispatch.start_backtest", return_value={"status": "ok"}):
        r = client.post(
            "/backtests/run",
            json={
                "strategy_id": "py_free",
                "instrument": "XAUUSD",
                "params": {},
                "start_date": "2024-01-01",
                "end_date": "2024-06-30",
                "evaluate_rulesets": [],
                "charge_costs": False,
            },
        )
    assert r.status_code in (200, 202), r.text
    from routers.backtests import _json_list

    assert _json_list(lab_db.get_run(r.json()["run_id"])["cost_layers"]) == []


def test_an_unmeasured_broker_refuses_to_run_charged(client, fresh_db):
    """Rule 17 applied to a measurement: refusing is the answer.

    PU Prime's Prime tier has never had its spread read on an open market. Charging it would mean
    borrowing a sibling tier's figure — and those tiers measured 2.7x apart.
    """
    from services import lab_db

    _strategy(lab_db, "py_unpriced", runner="python")
    with patch("services.runner_dispatch.start_backtest", return_value={"status": "ok"}):
        r = client.post(
            "/backtests/run",
            json={
                "strategy_id": "py_unpriced",
                "instrument": "XAUUSD",
                "params": {},
                "start_date": "2024-01-01",
                "end_date": "2024-06-30",
                "evaluate_rulesets": [],
                "charge_costs": True,
                "broker_profile": "puprime_prime",
            },
        )
    assert r.status_code == 400
    assert "spread" in r.text and "measured" in r.text


def test_a_charged_run_bills_the_ACCOUNT_commission_not_the_form(client, fresh_db):
    """The one cost still typed in by hand until 2026-08-24.

    A form figure sitting beside a measured spread and a measured swap is indistinguishable from
    them on the page. ECN's $1.00/side/lot was settled by filling a real round turn.
    """
    from services import lab_db

    _strategy(lab_db, "py_comm", runner="python")
    with patch("services.runner_dispatch.start_backtest", return_value={"status": "ok"}):
        r = client.post(
            "/backtests/run",
            json={
                "strategy_id": "py_comm",
                "instrument": "XAUUSD",
                "params": {},
                "start_date": "2024-01-01",
                "end_date": "2024-06-30",
                "evaluate_rulesets": [],
                "charge_costs": True,
                "broker_profile": "puprime_ecn",
                "commission_per_side": 99.0,  # a wrong number somebody typed
            },
        )
    assert r.status_code in (200, 202), r.text
    assert lab_db.get_run(r.json()["run_id"])["commission_per_side"] == 1.00


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


# ── The cost account must follow the ATTACHED terminal (2026-08-24) ──────────
#
# 🔴 The bar cache is partitioned by broker, so one broker's BARS can no longer reach another
# broker's replay. The cost profile is picked independently, so a run could still replay PU Prime's
# bars and charge Vantage's spread — the same mixed basis one level up, silent in the same way, and
# the two gold spreads are $0.12 and $0.22 an ounce.
#
# All three watched RED by MUTATION, named per test.


def _profiles(client):
    return {p["id"]: p for p in client.get("/backtests/broker-profiles").json()}


def test_the_attached_profile_is_resolved_by_ACCOUNT_not_by_server(client):
    """🔴 The server CANNOT separate PU Prime's tiers — Prime and ECN share `PUPrime-Demo`.

    Blessing a tier on the server alone hands a run ECN's $0.12 spread while it sits on Prime,
    which is the 2.7x error the unmeasured-spread sentinel exists to prevent, arriving through the
    front door.

    MUTATION: match on `p.server == attached_server` alone and this fails — every PU Prime tier
    comes back attached at once.
    """
    with patch(
        "services.mt5_agent_client.status",
        return_value={"mt5_connected": True, "server": "PUPrime-Demo", "account": 700152905},
    ):
        got = _profiles(client)
    assert got["puprime_ecn"]["attached"] is True
    assert got["puprime_prime"]["attached"] is False, "the server alone blessed the wrong tier"
    assert got["puprime_standard"]["attached"] is False
    assert got["vantage_demo"]["attached"] is False


def test_an_unreachable_agent_attaches_NOTHING_rather_than_a_default(client):
    """Rule 1 at this seam: "cannot ask" must never take the same value as "the usual broker".

    MUTATION: fall back to any profile when the status call fails and this goes red — the page
    would then bless a broker nobody measured against.
    """
    with patch("services.mt5_agent_client.status", side_effect=RuntimeError("agent down")):
        got = _profiles(client)
    assert not any(p["attached"] for p in got.values())


def test_a_terminal_that_is_NOT_connected_attaches_nothing(client):
    """The agent answers `ok` while its terminal has dropped the broker link — this repo's own
    incident. A server name from a disconnected terminal is a stale claim, not a measurement.

    MUTATION: drop the `mt5_connected is True` check and this goes red.
    """
    with patch(
        "services.mt5_agent_client.status",
        return_value={"mt5_connected": False, "server": "PUPrime-Demo", "account": 700152905},
    ):
        got = _profiles(client)
    assert not any(p["attached"] for p in got.values())
