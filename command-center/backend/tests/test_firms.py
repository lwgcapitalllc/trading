"""
Ruleset seeding + CRUD (firms → rulesets, M3 rename).

init_db() seeds 14 prop-firm rows across 4 firms (LucidFlex, FundedNext, Tradeify, Apex)
plus 3 personal/demo rows = 17 total. The /firms routes are a deprecated 308 redirect to
/rulesets; these tests hit the canonical /rulesets endpoint.
"""

LUCIDFLEX_IDS = {
    "lucidflex_50k_eval", "lucidflex_50k_funded",
    "lucidflex_100k_eval", "lucidflex_100k_funded",
}
PROP_FIRM_PREFIXES = ("lucidflex", "fundednext", "tradeify", "apex")


def _prop_rows(rulesets):
    return [r for r in rulesets if r["ruleset_type"] in ("prop_eval", "prop_funded")]


def test_cold_start_seeds_all_four_firms(client):
    r = client.get("/rulesets")
    assert r.status_code == 200
    rulesets = r.json()
    assert len(rulesets) == 17
    firms = {r["id"].split("_")[0] for r in _prop_rows(rulesets)}
    assert firms == set(PROP_FIRM_PREFIXES)
    assert LUCIDFLEX_IDS.issubset({r["id"] for r in rulesets})


def test_all_prop_rows_have_docs_url(client):
    rulesets = client.get("/rulesets").json()
    for r in _prop_rows(rulesets):
        assert r["docs_url"] and r["docs_url"].startswith("http"), \
            f"{r['id']} is missing docs_url"


def test_prop_eval_rows_have_positive_target(client):
    rulesets = client.get("/rulesets").json()
    evals = [r for r in rulesets if r["ruleset_type"] == "prop_eval"]
    assert len(evals) == 8  # 2 each × LucidFlex, FundedNext, Tradeify, Apex
    for r in evals:
        assert r["profit_target"] > 0, f"{r['id']} eval should have a profit target"


def test_prop_funded_rows_have_no_target(client):
    rulesets = client.get("/rulesets").json()
    funded = [r for r in rulesets if r["ruleset_type"] == "prop_funded"]
    for r in funded:
        assert r["profit_target"] == 0, f"{r['id']} funded profit_target should be 0"
        assert r["consistency_pct"] is None, f"{r['id']} funded should have no consistency"


def test_100k_accounts_have_higher_limits(client):
    rulesets = {r["id"]: r for r in client.get("/rulesets").json()}
    assert rulesets["lucidflex_100k_eval"]["max_loss_eod"] > rulesets["lucidflex_50k_eval"]["max_loss_eod"]
    assert rulesets["lucidflex_100k_eval"]["profit_target"] > rulesets["lucidflex_50k_eval"]["profit_target"]
    assert rulesets["lucidflex_100k_eval"]["account_size"] == 100_000


def test_corrected_firm_values(fresh_db):
    """Spot-check the verified corrections at the DB layer (these columns are not in the
    /rulesets API model) so a regression in the seed/migration is caught."""
    from services import lab_db
    g = lab_db.get_ruleset
    # LucidFlex eval locks the trailing MLL at start+$100; no daily cap, no min days.
    assert g("lucidflex_50k_eval")["mll_lock_balance"] == 50100
    assert g("lucidflex_50k_eval")["daily_loss_cap"] is None
    assert g("lucidflex_50k_eval")["min_trading_days"] is None
    # Tradeify $50k eval target raised to 3000; locks at 50100.
    assert g("tradeify_50k_eval")["profit_target"] == 3000
    assert g("tradeify_50k_eval")["mll_lock_balance"] == 50100
    # FundedNext raises the target on a consistency breach.
    assert g("fundednext_flex_50k_eval")["consistency_breach_action"] == "raise_target"
    # Apex locks at start+profit_target (53000), DLL stored but soft.
    assert g("apex_eod_50k_eval")["mll_lock_balance"] == 53000
    assert g("apex_eod_50k_eval")["daily_loss_cap"] == 1000


def test_update_ruleset_profit_target(client):
    """PUT /rulesets/:id updates the field and returns the updated row."""
    rs = client.get("/rulesets/lucidflex_50k_eval").json()
    original = rs["profit_target"]
    rs["profit_target"] = 9999
    r = client.put("/rulesets/lucidflex_50k_eval", json=rs)
    assert r.status_code == 200
    assert r.json()["profit_target"] == 9999
    rs["profit_target"] = original
    client.put("/rulesets/lucidflex_50k_eval", json=rs)


def test_seeding_is_idempotent(fresh_db):
    """init_db() called twice doesn't duplicate rulesets."""
    from services import lab_db
    before = len(lab_db.list_rulesets())
    lab_db.init_db()
    after = len(lab_db.list_rulesets())
    assert before == after == 17
