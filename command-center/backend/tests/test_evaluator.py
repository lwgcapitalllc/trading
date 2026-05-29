"""
Evaluation logic unit tests — all verdict paths for eval and funded tiers.

Uses seeded_run (net_pnl=4000, max_dd=1500) as the base run.
The 4 LucidFlex firms are seeded by fresh_db / init_db():

  lucidflex_50k_eval:    account_tier=eval,   max_loss_eod=2000, profit_target=3000, consistency_pct=50
  lucidflex_50k_funded:  account_tier=funded, max_loss_eod=2000, profit_target=0,    consistency_pct=None
  lucidflex_100k_eval:   account_tier=eval,   max_loss_eod=3000, profit_target=6000, consistency_pct=50
  lucidflex_100k_funded: account_tier=funded, max_loss_eod=3000, profit_target=0,    consistency_pct=None
"""

import pytest


def _eval(seeded_run, firm_id, net_pnl, max_drawdown, daily_pnl=None, equity_curve=None):
    """Shorthand: call evaluate_run and return the single result for firm_id."""
    from services.evaluator import evaluate_run
    results = evaluate_run(
        run_id=seeded_run,
        firm_ids=[firm_id],
        kpis={"net_pnl": net_pnl, "max_drawdown": max_drawdown},
        equity_curve=equity_curve or [],
        daily_pnl=daily_pnl or [],
    )
    assert len(results) == 1
    return results[0]


# ── Eval-tier verdict paths ────────────────────────────────────────────────────

def test_eval_pass(seeded_run):
    """DD under limit, target reached, no single day dominates → PASS."""
    daily = [
        {"date": "2024-01-02", "pnl": 1000},
        {"date": "2024-01-03", "pnl": 1000},
        {"date": "2024-01-04", "pnl": 1000},
        {"date": "2024-01-05", "pnl": 1000},
    ]
    r = _eval(seeded_run, "lucidflex_50k_eval",
              net_pnl=4000, max_drawdown=1500, daily_pnl=daily)
    assert r["verdict"] == "PASS"
    assert r["drawdown_pass"] is True
    assert r["target_pass"] is True
    assert r["consistency_pass"] is True   # biggest day = 1000/4000 = 25% < 50%


def test_eval_warn_target_miss(seeded_run):
    """DD ok but net_pnl below profit_target → WARN."""
    r = _eval(seeded_run, "lucidflex_50k_eval",
              net_pnl=2500, max_drawdown=1500)
    assert r["verdict"] == "WARN"
    assert r["drawdown_pass"] is True
    assert r["target_pass"] is False


def test_eval_warn_consistency_fail(seeded_run):
    """DD ok, target reached, but one day > 50% of profits → WARN."""
    daily = [
        {"date": "2024-01-02", "pnl": 3500},  # 87.5% of 4000 → fails 50% rule
        {"date": "2024-01-03", "pnl": 500},
    ]
    r = _eval(seeded_run, "lucidflex_50k_eval",
              net_pnl=4000, max_drawdown=1500, daily_pnl=daily)
    assert r["verdict"] == "WARN"
    assert r["consistency_pass"] is False
    assert r["largest_day_share_pct"] == pytest.approx(87.5, abs=0.1)


def test_eval_discard_drawdown_breach(seeded_run):
    """Max DD exceeds firm limit → DISCARD regardless of profit."""
    r = _eval(seeded_run, "lucidflex_50k_eval",
              net_pnl=5000, max_drawdown=2500)  # 2500 > 2000 limit
    assert r["verdict"] == "DISCARD"
    assert r["drawdown_pass"] is False


# ── Funded-tier verdict paths ──────────────────────────────────────────────────

def test_funded_pass_drawdown_only(seeded_run):
    """Funded: surviving drawdown is sufficient — no consistency check."""
    r = _eval(seeded_run, "lucidflex_50k_funded",
              net_pnl=0, max_drawdown=1500)
    assert r["verdict"] == "PASS"
    assert r["drawdown_pass"] is True
    assert r["consistency_pass"] is None    # must be None for funded


def test_funded_discard_drawdown_breach(seeded_run):
    """Funded: DD breach is immediate DISCARD — no WARN tier."""
    r = _eval(seeded_run, "lucidflex_50k_funded",
              net_pnl=9999, max_drawdown=2500)
    assert r["verdict"] == "DISCARD"
    assert r["consistency_pass"] is None


def test_funded_no_warn_verdict(seeded_run):
    """WARN verdict is impossible for funded firms."""
    daily = [{"date": "2024-01-02", "pnl": 9999}]  # extreme single day — irrelevant
    r = _eval(seeded_run, "lucidflex_50k_funded",
              net_pnl=4000, max_drawdown=1500, daily_pnl=daily)
    assert r["verdict"] != "WARN"


# ── NT8 quirk regression: negative max_drawdown input ─────────────────────────

def test_negative_drawdown_normalised(seeded_run):
    """NT8 reports max_drawdown as a negative number — evaluator must abs() it."""
    r = _eval(seeded_run, "lucidflex_50k_eval",
              net_pnl=4000, max_drawdown=-1500)   # negative input
    # 1500 < 2000 limit → drawdown_pass = True (would be False if not abs'd)
    assert r["drawdown_pass"] is True
    assert r["verdict"] != "DISCARD"


# ── Breach counting ───────────────────────────────────────────────────────────

def test_breach_count_via_equity_curve(seeded_run):
    """breach_count uses equity_curve when provided."""
    # Peak = 1000, then drops to -1500 = drawdown of 2500 > 2000 → breach
    equity = [
        {"date": "2024-01-01", "equity": 0},
        {"date": "2024-01-02", "equity": 1000},
        {"date": "2024-01-03", "equity": -1500},  # 2500 drawdown → breach
    ]
    r = _eval(seeded_run, "lucidflex_50k_eval",
              net_pnl=4000, max_drawdown=1500, equity_curve=equity)
    assert r["breach_count"] >= 1


def test_breach_count_zero_when_no_breach(seeded_run):
    equity = [
        {"date": "2024-01-01", "equity": 0},
        {"date": "2024-01-02", "equity": 500},
        {"date": "2024-01-03", "equity": 1000},
    ]
    r = _eval(seeded_run, "lucidflex_50k_eval",
              net_pnl=4000, max_drawdown=500, equity_curve=equity)
    assert r["breach_count"] == 0


# ── Multiple firms in one call ─────────────────────────────────────────────────

def test_evaluate_all_four_firms(seeded_run):
    from services.evaluator import evaluate_run
    results = evaluate_run(
        run_id=seeded_run,
        firm_ids=[
            "lucidflex_50k_eval",
            "lucidflex_50k_funded",
            "lucidflex_100k_eval",
            "lucidflex_100k_funded",
        ],
        kpis={"net_pnl": 4000, "max_drawdown": 1500},
        equity_curve=[],
        daily_pnl=[],
    )
    assert len(results) == 4
    funded = [r for r in results if "funded" in r["firm_id"]]
    for f in funded:
        assert f["consistency_pass"] is None
    eval_firms = [r for r in results if "eval" in r["firm_id"]]
    for e in eval_firms:
        assert e["consistency_pass"] is not None
