"""
Backtest endpoint tests covering:
- GET /backtests/runs (list + filters)
- GET /backtests/runs/:id (detail)
- POST /backtests/run (trigger — VPS mocked)
- POST /backtests/runs/:id/reevaluate (§11 Case 8)
- DELETE /backtests/runs/:id

The reevaluate test exercises §11 Case 8:
  1. Start with a completed run (seeded_run: net_pnl=4000, max_dd=1500)
  2. Verify initial evaluation → PASS (4000 > 3000 target, 1500 < 2000 DD limit)
  3. Update firm profit_target to 5000 (above run's net_pnl)
  4. Reevaluate → WARN (target miss) — no new run triggered
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


# ── §11 Case 8: reevaluate ────────────────────────────────────────────────────

def test_reevaluate_initial_verdict_is_pass(client, seeded_run):
    """
    seeded_run: net_pnl=4000, max_dd=1500
    lucidflex_50k_eval: profit_target=3000, max_loss_eod=2000
    4000 > 3000, 1500 < 2000 → PASS
    """
    r = client.post(f"/backtests/runs/{seeded_run}/reevaluate",
                    json={"firm_ids": ["lucidflex_50k_eval"]})
    assert r.status_code == 200
    evals = r.json()["evaluations"]
    assert len(evals) == 1
    assert evals[0]["verdict"] == "PASS"
    assert evals[0]["drawdown_pass"] is True
    assert evals[0]["target_pass"] is True


def test_reevaluate_after_firm_target_change_gives_warn(client, seeded_run):
    """
    §11 Case 8: edit firm profit_target → reevaluate → verdict changes.
    No new backtest is triggered — same run_id, same KPIs.
    """
    # Raise profit_target above the run's net_pnl (4000)
    firm = client.get("/firms/lucidflex_50k_eval").json()
    original_target = firm["profit_target"]
    firm["profit_target"] = 5000
    assert client.put("/firms/lucidflex_50k_eval", json=firm).status_code == 200

    r = client.post(f"/backtests/runs/{seeded_run}/reevaluate",
                    json={"firm_ids": ["lucidflex_50k_eval"]})
    assert r.status_code == 200
    evals = r.json()["evaluations"]
    assert evals[0]["verdict"] == "WARN"
    assert evals[0]["target_pass"] is False

    # Restore (keeps DB clean for other assertions if tests share client)
    firm["profit_target"] = original_target
    client.put("/firms/lucidflex_50k_eval", json=firm)


def test_reevaluate_funded_never_checks_consistency(client, seeded_run):
    r = client.post(f"/backtests/runs/{seeded_run}/reevaluate",
                    json={"firm_ids": ["lucidflex_50k_funded"]})
    assert r.status_code == 200
    eval_row = r.json()["evaluations"][0]
    assert eval_row["consistency_pass"] is None


def test_reevaluate_all_four_firms(client, seeded_run):
    r = client.post(f"/backtests/runs/{seeded_run}/reevaluate", json={
        "firm_ids": [
            "lucidflex_50k_eval",
            "lucidflex_50k_funded",
            "lucidflex_100k_eval",
            "lucidflex_100k_funded",
        ]
    })
    assert r.status_code == 200
    evals = r.json()["evaluations"]
    assert len(evals) == 4


def test_reevaluate_400_on_running_run(client):
    """Reevaluate requires status=complete — running run should 400."""
    from services import lab_db
    from tests.conftest import _insert_strategy
    import time

    _insert_strategy(lab_db)
    lab_db.insert_run({
        "run_id": "runningrun01",
        "strategy_id": "test_strategy",
        "instrument": "MNQ 06-26",
        "params": {}, "bar_type": "Minute", "bar_value": 5,
        "start_date": "2024-01-01", "end_date": "2024-12-31",
        "commission_per_side": 0.5, "slippage_ticks": 1,
        "status": "running", "created_at": int(time.time()),
    })

    r = client.post("/backtests/runs/runningrun01/reevaluate",
                    json={"firm_ids": ["lucidflex_50k_eval"]})
    assert r.status_code == 400
