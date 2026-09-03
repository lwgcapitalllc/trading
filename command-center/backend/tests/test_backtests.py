"""
Backtest endpoint tests covering:
- GET /backtests/runs (list + filters)
- GET /backtests/runs/:id (detail)
- POST /backtests/run (trigger — VPS mocked)
- DELETE /backtests/runs/:id

(The per-run /reevaluate endpoint was removed in the rulesets migration; reevaluation now
lives only at the sweep level. Those tests were dropped.)
"""

from unittest.mock import patch

# ── List / detail ──────────────────────────────────────────────────────────────


def test_list_runs_empty_initially(client):
    r = client.get("/backtests/runs")
    assert r.status_code == 200
    assert r.json() == []


def test_get_run_404_unknown(client):
    r = client.get("/backtests/runs/doesnotexist")
    assert r.status_code == 404


def test_get_run_detail_after_seed(client, seeded_run):
    r = client.get(f"/backtests/runs/{seeded_run}")
    assert r.status_code == 200
    data = r.json()
    assert data["run_id"] == seeded_run
    assert data["status"] == "complete"
    assert data["net_pnl"] == 4000.0
    assert data["max_drawdown"] == 1500.0


def test_list_runs_returns_seeded_run(client, seeded_run):
    r = client.get("/backtests/runs")
    assert r.status_code == 200
    runs = r.json()
    assert len(runs) == 1
    assert runs[0]["run_id"] == seeded_run


# ── Trigger endpoint ───────────────────────────────────────────────────────────


def test_trigger_404_unknown_strategy(client):
    r = client.post(
        "/backtests/run",
        json={
            "strategy_id": "no_such_strategy",
            "instrument": "MNQ 06-26",
            "params": {},
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "evaluate_firms": [],
        },
    )
    assert r.status_code == 404


def test_trigger_404_unknown_firm(client):
    """Triggers require all evaluate_firms IDs to exist."""
    client.post("/strategies/scan")
    strategies = client.get("/strategies").json()
    strat_id = strategies[0]["id"]

    r = client.post(
        "/backtests/run",
        json={
            "strategy_id": strat_id,
            "instrument": "MNQ 06-26",
            "params": {},
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "evaluate_firms": ["firm_does_not_exist"],
        },
    )
    assert r.status_code == 404


def test_trigger_returns_run_id(client):
    """Valid trigger returns 202 + run_id (VPS mocked → immediate success)."""
    client.post("/strategies/scan")
    strategies = client.get("/strategies").json()
    strat_id = strategies[0]["id"]

    r = client.post(
        "/backtests/run",
        json={
            "strategy_id": strat_id,
            "instrument": "MNQ 06-26",
            "params": {},
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "evaluate_firms": ["lucidflex_50k_eval"],
        },
    )
    assert r.status_code == 202
    body = r.json()
    assert "run_id" in body
    assert len(body["run_id"]) > 0


# ── Delete ─────────────────────────────────────────────────────────────────────


def test_delete_run(client, seeded_run):
    r = client.delete(f"/backtests/runs/{seeded_run}")
    assert r.status_code == 204
    assert client.get(f"/backtests/runs/{seeded_run}").status_code == 404


def test_delete_run_404_unknown(client):
    assert client.delete("/backtests/runs/doesnotexist").status_code == 404


# ── Retry / rerun ──────────────────────────────────────────────────────────────


def test_retry_keeps_the_window_when_no_period_sent(client, seeded_run):
    """A plain rerun is unchanged — it re-fires over the run's stored dates."""
    r = client.post(f"/backtests/runs/{seeded_run}/retry")
    assert r.status_code == 202
    detail = client.get(f"/backtests/runs/{seeded_run}").json()
    assert (detail["start_date"], detail["end_date"]) == ("2024-01-01", "2024-12-31")


def test_retry_with_new_period_moves_the_window(client, seeded_run):
    """Rerunning over a longer span persists the new window on the run itself, so the
    stored record never describes a period the result wasn't produced over."""
    r = client.post(
        f"/backtests/runs/{seeded_run}/retry",
        json={
            "start_date": "2022-01-01",
            "end_date": "2025-06-30",
        },
    )
    assert r.status_code == 202
    detail = client.get(f"/backtests/runs/{seeded_run}").json()
    assert (detail["start_date"], detail["end_date"]) == ("2022-01-01", "2025-06-30")


def test_retry_rejects_half_a_period(client, seeded_run):
    r = client.post(f"/backtests/runs/{seeded_run}/retry", json={"start_date": "2022-01-01"})
    assert r.status_code == 400


def test_retry_rejects_inverted_period(client, seeded_run):
    r = client.post(
        f"/backtests/runs/{seeded_run}/retry",
        json={
            "start_date": "2025-06-30",
            "end_date": "2022-01-01",
        },
    )
    assert r.status_code == 400


def test_retry_rejects_malformed_dates(client, seeded_run):
    r = client.post(
        f"/backtests/runs/{seeded_run}/retry",
        json={
            "start_date": "01/01/2022",
            "end_date": "30/06/2025",
        },
    )
    assert r.status_code == 400


def test_retry_clears_the_failed_attempts_progress_entry(client, seeded_run):
    """A retry reuses the run_id, so the failed attempt's progress entry — error text and all —
    is still filed under it. Left there, the live banner renders the OLD error while the rerun
    is already running (seen for ~30s on a 3-year gold rerun)."""
    stale = {"job_id": seeded_run, "status": "failed_error", "pct": 0, "message": "MT5 agent 404"}
    with (
        patch("routers.backtests.read_progress", return_value=stale),
        patch("routers.backtests.clear_progress") as cleared,
    ):
        assert client.post(f"/backtests/runs/{seeded_run}/retry").status_code == 202
    cleared.assert_called_once()


def test_retry_leaves_another_jobs_progress_alone(client, seeded_run):
    """The progress file is shared across runners — clearing it because a DIFFERENT platform's
    run is being retried would blank a live job's banner."""
    other = {"job_id": "someone_elses_run", "status": "running", "pct": 42, "message": "replaying…"}
    with (
        patch("routers.backtests.read_progress", return_value=other),
        patch("routers.backtests.clear_progress") as cleared,
    ):
        assert client.post(f"/backtests/runs/{seeded_run}/retry").status_code == 202
    cleared.assert_not_called()


# ── Slim detail (`?timeline=false`) ────────────────────────────────────────────
#
# `regime_timeline` is the single biggest slice of a run detail (measured: 96 KB of 137 KB on a
# 165-trade run) and it is the SAME calendar for every run over one window. The tuning workbench
# overlays N runs and bands off exactly one copy, so it asks for the rest without it.


def _seed_timeline(monkeypatch, tmp_path, run_id):
    """Give `run_id` a regime_timeline.json under a temp results dir."""
    import json

    from routers import backtests as bt

    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "regime_timeline.json").write_text(
        json.dumps(
            [
                {"date": "2024-01-02", "regime": "TRENDING"},
                {"date": "2024-01-03", "regime": "RANGING"},
            ]
        )
    )
    monkeypatch.setattr(bt, "LAB_RESULTS_DIR", tmp_path)


def test_detail_ships_the_regime_timeline_by_default(client, seeded_run, monkeypatch, tmp_path):
    """The default must not change shape — every existing caller reads this field."""
    _seed_timeline(monkeypatch, tmp_path, seeded_run)
    data = client.get(f"/backtests/runs/{seeded_run}").json()
    assert [d["regime"] for d in data["regime_timeline"]] == ["TRENDING", "RANGING"]


def test_timeline_false_drops_it(client, seeded_run, monkeypatch, tmp_path):
    _seed_timeline(monkeypatch, tmp_path, seeded_run)
    data = client.get(f"/backtests/runs/{seeded_run}?timeline=false").json()
    assert data["regime_timeline"] == []


def test_timeline_true_is_the_same_as_omitting_it(client, seeded_run, monkeypatch, tmp_path):
    _seed_timeline(monkeypatch, tmp_path, seeded_run)
    assert (
        client.get(f"/backtests/runs/{seeded_run}?timeline=true").json()
        == client.get(f"/backtests/runs/{seeded_run}").json()
    )


def test_slimming_drops_nothing_but_the_timeline(client, seeded_run, monkeypatch, tmp_path):
    """The point of the flag is a smaller payload, not a different run. Every other field — KPIs,
    curve, params, costs, sizing — has to survive it, or a caller reading a slimmed response would
    quietly get a different answer from one reading the full one."""
    _seed_timeline(monkeypatch, tmp_path, seeded_run)
    full = client.get(f"/backtests/runs/{seeded_run}").json()
    slim = client.get(f"/backtests/runs/{seeded_run}?timeline=false").json()
    assert set(full) == set(slim)
    assert {k: v for k, v in full.items() if k != "regime_timeline"} == {
        k: v for k, v in slim.items() if k != "regime_timeline"
    }


# ── the venue lot ceiling on a stored run (2026-09-03) ─────────────────────────
#
# The column is TEXT holding a JSON scalar because the question has THREE answers and a REAL
# column carries two. What is pinned here is that a RETRY reproduces the run it is retrying —
# the failure mode is silent, because both wrong readings produce a run that finishes happily
# and reports numbers from a different basis.


def test_a_run_with_no_stored_ceiling_reads_as_UNKNOWN():
    """Rule 1. Rows written before 2026-09-03 have NULL here, and NULL is not a ceiling and not
    the absence of one — it is "nobody recorded it". RED if the reader returns 0 or a float."""
    from routers.backtests import _stored_max_lots

    assert _stored_max_lots({}) is None
    assert _stored_max_lots({"max_lots": None}) is None
    assert _stored_max_lots({"max_lots": ""}) is None


def test_a_stored_null_means_DELIBERATELY_no_ceiling():
    """The distinct third state. A run that explicitly asked for no clamp must retry that way,
    not fall back to the account's 100 — that would retry a different run and say nothing."""
    from routers.backtests import _NO_CEILING_STORED, _stored_max_lots

    assert _stored_max_lots({"max_lots": "null"}) is _NO_CEILING_STORED


def test_a_stored_number_comes_back_as_that_number():
    from routers.backtests import _stored_max_lots

    assert _stored_max_lots({"max_lots": "100.0"}) == 100.0
    assert _stored_max_lots({"max_lots": 250.0}) == 250.0  # a REAL column, defensively


def test_a_malformed_ceiling_reads_as_UNKNOWN_rather_than_raising():
    """Same call as `_json_list` makes: unknown is the honest answer, and the page already knows
    how to caption it. A retry must not die because a column got corrupted."""
    from routers.backtests import _stored_max_lots

    assert _stored_max_lots({"max_lots": "{not json"}) is None
    assert _stored_max_lots({"max_lots": '"one hundred"'}) is None


def _python_strategy_id(client) -> str:
    """A scanned strategy whose runner is `python` and which can run on its own.

    ⚠ `requires_source` is read rather than a name being hardcoded — it is the same fact
    `routers/_source_guard.py` refuses on, so a new dependent rule cannot silently become the
    one this picks and turn these tests into a 400.
    """
    client.post("/strategies/scan")
    for s in client.get("/strategies").json():
        if s.get("runner") == "python" and not s.get("requires_source"):
            return s["id"]
    raise AssertionError("no standalone python strategy was scanned; this test needs one")


def test_a_new_run_records_the_ceiling_it_was_measured_under(client):
    """The loop-closer: the field on the REQUEST must reach the ROW, or the run cannot be
    compared with any other run and a retry has nothing to read back. RED if the key is dropped
    anywhere between the two."""
    from routers.backtests import _stored_max_lots
    from services import lab_db

    r = client.post(
        "/backtests/run",
        json={
            "strategy_id": _python_strategy_id(client),
            "instrument": "XAUUSD",
            "params": {},
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "max_lots": 250.0,
        },
    )
    assert r.status_code in (200, 202), r.text
    row = lab_db.get_run(r.json()["run_id"])
    assert _stored_max_lots(row) == 250.0


def test_the_ceiling_DEFAULTS_to_one_hundred_lots_for_every_strategy(client):
    """Aaron's instruction: "All strategies will default to one hundred lots." A caller that says
    nothing must still get the ceiling — RED if the request model's default is removed."""
    from routers.backtests import _stored_max_lots
    from services import lab_db

    r = client.post(
        "/backtests/run",
        json={
            "strategy_id": _python_strategy_id(client),
            "instrument": "XAUUSD",
            "params": {},
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
        },
    )
    assert r.status_code in (200, 202), r.text
    row = lab_db.get_run(r.json()["run_id"])
    assert _stored_max_lots(row) == 100.0


def test_a_nonpython_run_records_NO_ceiling_at_all(client):
    """🔴 Rule 7. NT8 and MT5 size inside their own platforms and never reach this account, so a
    ceiling written on one of their rows is a claim about code that does not exist. The column
    must stay NULL — RED if the field is stored for every runner alike."""
    from routers.backtests import _stored_max_lots
    from services import lab_db

    client.post("/strategies/scan")
    other = [s for s in client.get("/strategies").json() if s.get("runner") != "python"]
    assert other, "this test needs a non-python strategy"

    r = client.post(
        "/backtests/run",
        json={
            "strategy_id": other[0]["id"],
            "instrument": "MNQ 06-26",
            "params": {},
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "max_lots": 250.0,
        },
    )
    assert r.status_code in (200, 202), r.text
    row = lab_db.get_run(r.json()["run_id"])
    assert row.get("max_lots") is None
    assert _stored_max_lots(row) is None
