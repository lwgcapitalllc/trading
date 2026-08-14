"""
Ruleset seeding + CRUD.

init_db() seeds 14 prop-firm rows across 4 firms (LucidFlex, FundedNext, Tradeify, Apex)
plus 2 personal demo rows = 16 total. These tests hit the canonical /rulesets endpoint.
(The old /firms redirect shim was removed 2026-07-01; this file was test_firms.py until
the 2026-07-06 rename.)
"""

LUCIDFLEX_IDS = {
    "lucidflex_50k_eval",
    "lucidflex_50k_funded",
    "lucidflex_100k_eval",
    "lucidflex_100k_funded",
}
PROP_FIRM_PREFIXES = ("lucidflex", "fundednext", "tradeify", "apex")


def _prop_rows(rulesets):
    return [r for r in rulesets if r["ruleset_type"] in ("prop_eval", "prop_funded")]


def test_cold_start_seeds_all_four_firms(client):
    r = client.get("/rulesets")
    assert r.status_code == 200
    rulesets = r.json()
    # 14 prop + personal forex/futures demo + unconstrained (2026-07-16)
    # + personal_forex_risk (2026-07-30).
    assert len(rulesets) == 18
    firms = {r["id"].split("_")[0] for r in _prop_rows(rulesets)}
    assert firms == set(PROP_FIRM_PREFIXES)
    assert LUCIDFLEX_IDS.issubset({r["id"] for r in rulesets})
    assert "unconstrained" in {r["id"] for r in rulesets}


def test_all_prop_rows_have_docs_url(client):
    rulesets = client.get("/rulesets").json()
    for r in _prop_rows(rulesets):
        assert r["docs_url"] and r["docs_url"].startswith("http"), f"{r['id']} is missing docs_url"


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
    assert (
        rulesets["lucidflex_100k_eval"]["max_loss_eod"]
        > rulesets["lucidflex_50k_eval"]["max_loss_eod"]
    )
    assert (
        rulesets["lucidflex_100k_eval"]["profit_target"]
        > rulesets["lucidflex_50k_eval"]["profit_target"]
    )
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


def test_put_prop_ruleset_locked(client):
    """Prop rows are locked server-side — PUT returns 403 and changes nothing."""
    rs = client.get("/rulesets/lucidflex_50k_eval").json()
    rs["profit_target"] = 9999
    r = client.put("/rulesets/lucidflex_50k_eval", json=rs)
    assert r.status_code == 403
    assert client.get("/rulesets/lucidflex_50k_eval").json()["profit_target"] != 9999


def test_put_personal_ruleset_allowed(client):
    """PUT still works for personal rows (full-row admin edit)."""
    rs = client.get("/rulesets/personal_forex_demo").json()
    rs["description"] = "edited via PUT"
    r = client.put("/rulesets/personal_forex_demo", json=rs)
    assert r.status_code == 200
    assert r.json()["description"] == "edited via PUT"


# ── PATCH /rulesets/:id — the personal-rules edit endpoint ────────────────────


def test_patch_personal_allowed_fields(client):
    """PATCH updates the allowed personal rule fields and persists them."""
    r = client.patch(
        "/rulesets/personal_forex_demo",
        json={
            "daily_loss_cap": 750,
            "max_drawdown_from_peak_pct": 20.0,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["daily_loss_cap"] == 750
    assert body["max_drawdown_from_peak_pct"] == 20.0
    # untouched fields survive
    assert body["daily_profit_target"] == 1000
    assert body["max_consecutive_loss_days"] == 3


def test_patch_prop_ruleset_rejected(client):
    """PATCH on a prop row is rejected 403 — the lock is server-side."""
    r = client.patch("/rulesets/lucidflex_50k_eval", json={"daily_loss_cap": 750})
    assert r.status_code == 403
    assert "not editable" in r.json()["detail"]


def test_patch_disallowed_field_rejected(client):
    """Non-allowlisted fields are rejected 422 even on a personal row."""
    for payload in ({"ruleset_type": "prop_eval"}, {"max_loss_eod": 5000}, {"name": "sneaky"}):
        r = client.patch("/rulesets/personal_forex_demo", json=payload)
        assert r.status_code == 422, f"{payload} should be rejected"


def test_patch_empty_body_rejected(client):
    r = client.patch("/rulesets/personal_forex_demo", json={})
    assert r.status_code == 400


def test_seeding_is_idempotent(fresh_db):
    """init_db() called twice doesn't duplicate rulesets. The count is a canary against
    losing a row; `before == after` is the property under test."""
    from services import lab_db

    before = len(lab_db.list_rulesets())
    lab_db.init_db()
    after = len(lab_db.list_rulesets())
    assert before == after == 18


# ── personal_forex_risk: the gradeable forex row ──────────────────────────────
# Every grade in services/grading.py is a statement about drawdown vs a limit, so a ruleset that
# states none cannot produce a letter. This row exists to state one.


def test_the_forex_risk_row_states_a_drawdown_limit(client):
    """55%, Aaron's stated tolerance (2026-07-30). Without it the run is 'not graded'."""
    from services.metrics import effective_dd_limit_pct

    rs = client.get("/rulesets/personal_forex_risk").json()
    assert rs["max_drawdown_from_peak_pct"] == 55.0
    assert effective_dd_limit_pct(rs) == 55.0


def test_the_forex_risk_row_does_not_inherit_the_prop_15_percent(client):
    """The 15% on personal_forex_demo is a PROP-FIRM rule. Aaron's instruction is that it must
    never be applied to forex, so a copy-paste of that row would be the specific wrong answer."""
    rs = client.get("/rulesets/personal_forex_risk").json()
    assert rs["max_drawdown_from_peak_pct"] != 15.0
    assert rs["market"] == "forex"


def test_the_forex_risk_row_carries_no_other_limit(client):
    """Drawdown is the ONLY bar. A daily cap or a loss-streak rule would fire constantly at
    10-12.5% risk per trade and turn the verdict into a statement about that rule instead."""
    rs = client.get("/rulesets/personal_forex_risk").json()
    assert rs["max_consecutive_loss_days"] is None  # the capped-day DISCARD rule is off
    assert rs["daily_profit_target"] in (None, 0)  # no halt
    assert rs["profit_target"] == 0  # nothing to hit
    assert rs["max_loss_eod"] == 0  # sentinel: no trailing EOD floor


def test_unconstrained_still_states_no_limit(client):
    """The new row is an ADDITION, not an edit. `unconstrained`'s whole purpose is having none."""
    rs = client.get("/rulesets/unconstrained").json()
    assert rs["max_drawdown_from_peak_pct"] is None
