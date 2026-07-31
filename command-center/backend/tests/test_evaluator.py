"""
Evaluation logic unit tests — current contract.

Verdict engine (services/evaluator.evaluate_run):
- Drawdown is an end-of-day TRAILING max-loss computed from daily_pnl (not the whole-test
  max_drawdown KPI). A run breaches when the running balance falls through the trailing floor.
- prop_eval ladder:    DISCARD if drawdown breached → WARN if target missed → WARN if
                       consistency breached → else PASS.
- prop_funded:         drawdown only — PASS if not breached, else DISCARD (no WARN).
- personal / demo:     INFO — no pass/fail; metrics only.

seeded_run is the base run row (its KPIs don't drive the verdict; daily_pnl passed per-test does).
LucidFlex $50k eval: account_size=50000, max_loss_eod=2000, mll_lock_balance=50100,
profit_target=3000, consistency_pct=50. Trailing floor starts at 50000-2000 = 48000.
"""

import pytest


def _eval(seeded_run, ruleset_id, net_pnl, daily_pnl=None, equity_curve=None):
    """Call evaluate_run for one ruleset and return its single result dict."""
    from services.evaluator import evaluate_run
    results = evaluate_run(
        run_id=seeded_run,
        ruleset_ids=[ruleset_id],
        kpis={"net_pnl": net_pnl},
        equity_curve=equity_curve or [],
        daily_pnl=daily_pnl or [],
    )
    assert len(results) == 1
    return results[0]


# ── prop_eval verdict paths ───────────────────────────────────────────────────

def test_eval_pass(seeded_run):
    """No floor breach, target reached, no single day dominates → PASS."""
    daily = [
        {"date": "2024-01-02", "pnl": 1000},
        {"date": "2024-01-03", "pnl": 1000},
        {"date": "2024-01-04", "pnl": 1000},
        {"date": "2024-01-05", "pnl": 1000},
    ]
    r = _eval(seeded_run, "lucidflex_50k_eval", net_pnl=4000, daily_pnl=daily)
    assert r["verdict"] == "PASS"
    assert r["drawdown_pass"] is True
    assert r["target_pass"] is True
    assert r["consistency_pass"] is True   # biggest day 1000/4000 = 25% < 50%


def test_eval_warn_target_miss(seeded_run):
    """Floor held but net P&L below profit_target → WARN."""
    daily = [{"date": "2024-01-02", "pnl": 1200}, {"date": "2024-01-03", "pnl": 1300}]
    r = _eval(seeded_run, "lucidflex_50k_eval", net_pnl=2500, daily_pnl=daily)
    assert r["verdict"] == "WARN"
    assert r["drawdown_pass"] is True
    assert r["target_pass"] is False


def test_eval_warn_consistency_fail(seeded_run):
    """Floor held, target reached, but one day > 50% of profit → WARN."""
    daily = [
        {"date": "2024-01-02", "pnl": 3500},  # 87.5% of 4000 → fails 50% rule
        {"date": "2024-01-03", "pnl": 500},
    ]
    r = _eval(seeded_run, "lucidflex_50k_eval", net_pnl=4000, daily_pnl=daily)
    assert r["verdict"] == "WARN"
    assert r["consistency_pass"] is False
    assert r["largest_day_share_pct"] == pytest.approx(87.5, abs=0.1)


def test_eval_discard_trailing_breach(seeded_run):
    """Balance falls through the trailing floor (48000) on day 1 → DISCARD."""
    daily = [{"date": "2024-01-02", "pnl": -2500}]  # balance 47500 < 48000 floor
    r = _eval(seeded_run, "lucidflex_50k_eval", net_pnl=-2500, daily_pnl=daily)
    assert r["verdict"] == "DISCARD"
    assert r["drawdown_pass"] is False
    assert r["mll_breach_day"] == 1


def test_eval_no_breach_when_floor_held(seeded_run):
    """A dip that stays above the floor does not breach (48000 floor, balance 48500)."""
    daily = [{"date": "2024-01-02", "pnl": -1500}, {"date": "2024-01-03", "pnl": 5000}]
    r = _eval(seeded_run, "lucidflex_50k_eval", net_pnl=3500, daily_pnl=daily)
    assert r["drawdown_pass"] is True
    assert r["verdict"] != "DISCARD"


# ── prop_funded verdict paths ─────────────────────────────────────────────────

def test_funded_pass_drawdown_only(seeded_run):
    """Funded: surviving drawdown is sufficient — no consistency, no target."""
    daily = [{"date": "2024-01-02", "pnl": 500}]
    r = _eval(seeded_run, "lucidflex_50k_funded", net_pnl=500, daily_pnl=daily)
    assert r["verdict"] == "PASS"
    assert r["drawdown_pass"] is True
    assert r["consistency_pass"] is None


def test_funded_discard_on_breach(seeded_run):
    """Funded: a floor breach is immediate DISCARD — no WARN tier."""
    daily = [{"date": "2024-01-02", "pnl": -2500}]  # breaches 48000 floor
    r = _eval(seeded_run, "lucidflex_50k_funded", net_pnl=-2500, daily_pnl=daily)
    assert r["verdict"] == "DISCARD"
    assert r["consistency_pass"] is None


def test_funded_never_warns(seeded_run):
    """WARN is impossible for funded — only PASS or DISCARD."""
    daily = [{"date": "2024-01-02", "pnl": 9999}]  # extreme single day — irrelevant
    r = _eval(seeded_run, "lucidflex_50k_funded", net_pnl=4000, daily_pnl=daily)
    assert r["verdict"] in ("PASS", "DISCARD")
    assert r["verdict"] != "WARN"


# ── FundedNext raise_target: consistency breach raises the bar, doesn't fail ──

def test_fundednext_raise_target_binds(seeded_run):
    """FundedNext: a consistency breach raises the effective target; net below it → WARN."""
    # biggest day 1500 of net 2600 = 57.7% > 40% limit → target raised to 1500/0.40 = 3750.
    daily = [
        {"date": "2024-01-02", "pnl": 1500},
        {"date": "2024-01-03", "pnl": 300},
        {"date": "2024-01-04", "pnl": 300},
        {"date": "2024-01-05", "pnl": 300},
        {"date": "2024-01-06", "pnl": 200},
    ]
    r = _eval(seeded_run, "fundednext_flex_50k_eval", net_pnl=2600, daily_pnl=daily)
    assert r["consistency_pass"] is True            # passed-with-adjustment
    assert r["adjusted_profit_target"] == 3750.0
    assert r["target_pass"] is False                # 2600 < 3750 raised bar
    assert r["verdict"] == "WARN"


# ── personal / demo → real verdict against the relaxed personal rules ─────────
# Rules on the $10k demos: $500 daily cap, $1,000 daily profit target (halt, info
# only), DISCARD on 3 consecutive capped days or 15% drawdown from peak.

def test_personal_passes_with_small_losses(seeded_run):
    daily = [{"date": "2024-01-02", "pnl": -200}, {"date": "2024-01-03", "pnl": 300}]
    r = _eval(seeded_run, "personal_forex_demo", net_pnl=100, daily_pnl=daily)
    assert r["verdict"] == "PASS"
    assert r["drawdown_pass"] is True
    assert r["mll_final_floor"] is None             # still no trailing MLL for personal


def test_personal_discards_on_drawdown_from_peak(seeded_run):
    """One -$9,999 day = ~100% drawdown from peak — breaches the 15% limit."""
    daily = [{"date": "2024-01-02", "pnl": -9999}]
    r = _eval(seeded_run, "personal_forex_demo", net_pnl=-9999, daily_pnl=daily)
    assert r["verdict"] == "DISCARD"
    assert r["drawdown_pass"] is False
    assert "drew down" in r["notes"]
    assert r["mll_final_floor"] is None             # no reference line for personal


def test_personal_discards_on_consecutive_capped_days(seeded_run):
    """3 capped days in a row fails — peak raised first so only the streak fires."""
    daily = [
        {"date": "2024-01-02", "pnl": 2000},   # peak 12,000 → 3×500 is 12.5% < 15%
        {"date": "2024-01-03", "pnl": -500},
        {"date": "2024-01-04", "pnl": -500},
        {"date": "2024-01-05", "pnl": -500},
    ]
    r = _eval(seeded_run, "personal_futures_demo", net_pnl=500, daily_pnl=daily)
    assert r["verdict"] == "DISCARD"
    assert r["drawdown_pass"] is True               # drawdown rule did NOT fire
    assert "consecutive days hit the $500 daily cap" in r["notes"]


def test_personal_streak_resets_on_non_capped_day(seeded_run):
    """3 capped days NOT in a row pass — the streak resets between them."""
    daily = [
        {"date": "2024-01-02", "pnl": -500},
        {"date": "2024-01-03", "pnl": 400},
        {"date": "2024-01-04", "pnl": -500},
        {"date": "2024-01-05", "pnl": 400},
        {"date": "2024-01-06", "pnl": -500},
    ]
    r = _eval(seeded_run, "personal_forex_demo", net_pnl=-700, daily_pnl=daily)
    assert r["verdict"] == "PASS"
    assert "3 day(s) hit the $500 daily cap" in r["notes"]


def test_personal_profit_halt_is_informational(seeded_run):
    daily = [{"date": "2024-01-02", "pnl": 1200}]
    r = _eval(seeded_run, "personal_futures_demo", net_pnl=1200, daily_pnl=daily)
    assert r["verdict"] == "PASS"
    assert "daily profit target" in r["notes"]


# ── A ruleset that states no limit cannot be passed ───────────────────────────
# `unconstrained` configures neither fail condition on purpose, so both checks are
# skipped and `failures` is empty no matter what the run did. It used to return PASS,
# which claimed a verdict lab_db.py's own seed note says cannot be given.

def test_unconstrained_is_not_graded(seeded_run):
    """A run that loses 95% of the account still cannot FAIL a ruleset with no limits —
    but it must not PASS one either."""
    daily = [{"date": "2024-01-02", "pnl": -9000}, {"date": "2024-01-03", "pnl": -500}]
    r = _eval(seeded_run, "unconstrained", net_pnl=-9500, daily_pnl=daily)
    assert r["verdict"] == "INFO"
    assert "no personal fail conditions configured" in r["notes"]


def test_unconstrained_is_not_graded_when_profitable(seeded_run):
    """Same verdict on a winning run — INFO is the absence of grading, not a bad grade."""
    daily = [{"date": "2024-01-02", "pnl": 4000}]
    r = _eval(seeded_run, "unconstrained", net_pnl=4000, daily_pnl=daily)
    assert r["verdict"] == "INFO"


def test_stated_limit_still_grades(seeded_run):
    """The guard is 'nothing was checked', not 'personal ruleset' — a personal row that
    DOES state a drawdown limit keeps its real PASS/DISCARD verdict."""
    daily = [{"date": "2024-01-02", "pnl": -9999}]
    r = _eval(seeded_run, "personal_forex_risk", net_pnl=-9999, daily_pnl=daily)
    assert r["verdict"] == "DISCARD"
    assert r["drawdown_pass"] is False


# ── Multiple rulesets in one call ─────────────────────────────────────────────

def test_evaluate_multiple_rulesets(seeded_run):
    from services.evaluator import evaluate_run
    daily = [{"date": "2024-01-02", "pnl": 4000}]
    results = evaluate_run(
        run_id=seeded_run,
        ruleset_ids=["lucidflex_50k_eval", "lucidflex_50k_funded", "personal_forex_demo"],
        kpis={"net_pnl": 4000},
        equity_curve=[],
        daily_pnl=daily,
    )
    assert len(results) == 3
    by_id = {r["ruleset_id"]: r for r in results}
    assert by_id["lucidflex_50k_funded"]["consistency_pass"] is None
    assert by_id["lucidflex_50k_eval"]["consistency_pass"] is not None
    assert by_id["personal_forex_demo"]["verdict"] == "PASS"  # +4000, no losses


# ── Contract-cap status (informational, never moves the verdict) ──────────────

def test_contract_cap_not_evaluable_without_size(seeded_run):
    """NT8 run with no per-trade size → not_evaluable; verdict unaffected."""
    daily = [
        {"date": "2024-01-02", "pnl": 1000},
        {"date": "2024-01-03", "pnl": 1000},
        {"date": "2024-01-04", "pnl": 1000},
        {"date": "2024-01-05", "pnl": 1000},
    ]
    r = _eval(seeded_run, "lucidflex_50k_eval", net_pnl=4000, daily_pnl=daily)
    assert r["contract_cap_status"] == "not_evaluable"
    assert r["verdict"] == "PASS"
