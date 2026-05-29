"""
§11 Case 1 (partial) — firm seeding and CRUD.

Verifies that init_db() seeds exactly 4 LucidFlex firms with the correct
account tiers, docs_url, and numeric rules.
"""

EXPECTED_IDS = {
    "lucidflex_50k_eval",
    "lucidflex_50k_funded",
    "lucidflex_100k_eval",
    "lucidflex_100k_funded",
}


def test_cold_start_seeds_four_firms(client):
    r = client.get("/firms")
    assert r.status_code == 200
    firms = r.json()
    assert len(firms) == 4
    assert {f["id"] for f in firms} == EXPECTED_IDS


def test_all_firms_have_docs_url(client):
    firms = client.get("/firms").json()
    for f in firms:
        assert f["docs_url"] is not None and f["docs_url"].startswith("http"), \
            f"Firm {f['id']} is missing docs_url"


def test_eval_firms_have_consistency_and_profit_target(client):
    firms = client.get("/firms").json()
    eval_firms = [f for f in firms if f["account_tier"] == "eval"]
    assert len(eval_firms) == 2
    for f in eval_firms:
        assert f["consistency_pct"] == 50.0, f"{f['id']} consistency_pct wrong"
        assert f["profit_target"] > 0, f"{f['id']} profit_target should be > 0"


def test_funded_firms_have_no_consistency_no_target(client):
    firms = client.get("/firms").json()
    funded = [f for f in firms if f["account_tier"] == "funded"]
    assert len(funded) == 2
    for f in funded:
        assert f["consistency_pct"] is None, f"{f['id']} should have no consistency_pct"
        assert f["profit_target"] == 0, f"{f['id']} profit_target should be 0"


def test_100k_accounts_have_higher_limits(client):
    firms = {f["id"]: f for f in client.get("/firms").json()}
    assert firms["lucidflex_100k_eval"]["max_loss_eod"] > firms["lucidflex_50k_eval"]["max_loss_eod"]
    assert firms["lucidflex_100k_eval"]["profit_target"] > firms["lucidflex_50k_eval"]["profit_target"]
    assert firms["lucidflex_100k_eval"]["account_size"] == 100_000


def test_update_firm_profit_target(client):
    """PUT /firms/:id updates the field and returns the updated firm."""
    firm = client.get("/firms/lucidflex_50k_eval").json()
    original_target = firm["profit_target"]

    firm["profit_target"] = 9999
    r = client.put("/firms/lucidflex_50k_eval", json=firm)
    assert r.status_code == 200
    assert r.json()["profit_target"] == 9999

    # restore
    firm["profit_target"] = original_target
    client.put("/firms/lucidflex_50k_eval", json=firm)


def test_seeding_is_idempotent(fresh_db):
    """init_db() called twice doesn't duplicate firms."""
    from services import lab_db
    lab_db.init_db()
    firms = lab_db.list_firms()
    assert len(firms) == 4
