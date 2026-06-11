"""
Backtest endpoint tests covering:
- GET /backtests/runs (list + filters)
- GET /backtests/runs/:id (detail)
- POST /backtests/run (trigger — VPS mocked)
- DELETE /backtests/runs/:id

(The per-run /reevaluate endpoint was removed in the rulesets migration; reevaluation now
lives only at the sweep level. Those tests were dropped.)
"""


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
