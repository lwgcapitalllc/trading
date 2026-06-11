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


# ── personal / demo → INFO ────────────────────────────────────────────────────

def test_personal_is_info_no_judgment(seeded_run):
    """Personal accounts get INFO — no drawdown/target/consistency fail, no reference floor."""
    daily = [{"date": "2024-01-02", "pnl": -9999}]  # would breach any real floor
    r = _eval(seeded_run, "personal_forex_main", net_pnl=-9999, daily_pnl=daily)
    assert r["verdict"] == "INFO"
    assert r["drawdown_pass"] is True               # neutral, not a fail
    assert r["mll_final_floor"] is None             # no reference line for personal


def test_demo_is_info(seeded_run):
    daily = [{"date": "2024-01-02", "pnl": 250}]
    r = _eval(seeded_run, "personal_forex_demo", net_pnl=250, daily_pnl=daily)
    assert r["verdict"] == "INFO"


# ── Multiple rulesets in one call ─────────────────────────────────────────────

def test_evaluate_multiple_rulesets(seeded_run):
    from services.evaluator import evaluate_run
    daily = [{"date": "2024-01-02", "pnl": 4000}]
    results = evaluate_run(
        run_id=seeded_run,
        ruleset_ids=["lucidflex_50k_eval", "lucidflex_50k_funded", "personal_forex_main"],
        kpis={"net_pnl": 4000},
        equity_curve=[],
        daily_pnl=daily,
    )
    assert len(results) == 3
    by_id = {r["ruleset_id"]: r for r in results}
    assert by_id["lucidflex_50k_funded"]["consistency_pass"] is None
    assert by_id["lucidflex_50k_eval"]["consistency_pass"] is not None
    assert by_id["personal_forex_main"]["verdict"] == "INFO"


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
