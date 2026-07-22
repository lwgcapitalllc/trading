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
    r = client.post("/backtests/run", json={
        "strategy_id": "no_such_strategy",
        "instrument": "MNQ 06-26",
        "params": {},
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "evaluate_firms": [],
    })
    assert r.status_code == 404


def test_trigger_404_unknown_firm(client):
    """Triggers require all evaluate_firms IDs to exist."""
    client.post("/strategies/scan")
    strategies = client.get("/strategies").json()
    strat_id = strategies[0]["id"]

    r = client.post("/backtests/run", json={
        "strategy_id": strat_id,
        "instrument": "MNQ 06-26",
        "params": {},
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "evaluate_firms": ["firm_does_not_exist"],
    })
    assert r.status_code == 404


def test_trigger_returns_run_id(client):
    """Valid trigger returns 202 + run_id (VPS mocked → immediate success)."""
    client.post("/strategies/scan")
    strategies = client.get("/strategies").json()
    strat_id = strategies[0]["id"]

    r = client.post("/backtests/run", json={
        "strategy_id": strat_id,
        "instrument": "MNQ 06-26",
        "params": {},
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "evaluate_firms": ["lucidflex_50k_eval"],
    })
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
    r = client.post(f"/backtests/runs/{seeded_run}/retry", json={
        "start_date": "2022-01-01",
        "end_date": "2025-06-30",
    })
    assert r.status_code == 202
    detail = client.get(f"/backtests/runs/{seeded_run}").json()
    assert (detail["start_date"], detail["end_date"]) == ("2022-01-01", "2025-06-30")


def test_retry_rejects_half_a_period(client, seeded_run):
    r = client.post(f"/backtests/runs/{seeded_run}/retry", json={"start_date": "2022-01-01"})
    assert r.status_code == 400


def test_retry_rejects_inverted_period(client, seeded_run):
    r = client.post(f"/backtests/runs/{seeded_run}/retry", json={
        "start_date": "2025-06-30",
        "end_date": "2022-01-01",
    })
    assert r.status_code == 400


def test_retry_rejects_malformed_dates(client, seeded_run):
    r = client.post(f"/backtests/runs/{seeded_run}/retry", json={
        "start_date": "01/01/2022",
        "end_date": "30/06/2025",
    })
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
