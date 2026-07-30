"""Monte Carlo — which series may be shuffled, and what "no rule to test" reports.

The reshuffle/bootstrap is only valid on a STATIONARY series: a trade from late in the run has to
be one that could equally have happened early. Dollar P&L satisfies that when position size is
constant and violates it whenever size scales with the account — a strategy risking a % of equity,
or any run the lab's sizing engine sized in consistent/bullet/manual mode.

The two properties pinned here are the ones that matter: a fixed-size run must be completely
unaffected by the compounding support, and a compounding run must stop producing paths its account
could never have taken.
"""

import numpy as np
import pytest

from services.stress_tester import choose_shuffle_series, run_monte_carlo

LIMITED = {"id": "p", "ruleset_type": "prop_funded", "max_loss_eod": 5000, "account_size": 50000}
NO_LIMIT = {"id": "u", "name": "Unconstrained", "ruleset_type": "personal",
            "max_loss_eod": 0, "max_drawdown_from_peak_pct": None, "account_size": 10000}


def _fixed_size_run(n=120, start=50_000.0):
    """Constant $ risk: P&L is stationary, percent returns shrink as the account grows."""
    rng = np.random.default_rng(1)
    pnls = rng.normal(200.0, 800.0, n)
    bal, balances = start, []
    for p in pnls:
        balances.append(bal)
        bal += p
    return list(pnls), balances


def _compounding_run(n=120, start=10_000.0, risk=0.10):
    """Fixed % risk: percent returns are stationary, dollars grow with the account."""
    rng = np.random.default_rng(2)
    rets = rng.normal(0.03, risk, n)
    bal, pnls, balances = start, [], []
    for r in rets:
        balances.append(bal)
        pnls.append(bal * r)
        bal += bal * r
    return pnls, balances


# ── series selection ──────────────────────────────────────────────────────────

def test_fixed_size_run_keeps_the_dollar_model():
    pnls, balances = _fixed_size_run()
    values, model, _ = choose_shuffle_series(pnls, balances)
    assert model == "dollars"
    assert values == pytest.approx(np.asarray(pnls))


def test_compounding_run_switches_to_returns():
    pnls, balances = _compounding_run()
    values, model, start = choose_shuffle_series(pnls, balances)
    assert model == "returns"
    assert start == pytest.approx(10_000.0)
    assert values == pytest.approx(np.asarray(pnls) / np.asarray(balances))


def test_growing_trade_size_without_account_growth_keeps_dollars():
    """A volatility regime is not compounding. If trade size doubles while the balance stays flat,
    BOTH series drift by the same factor, so neither is more stable and the default must hold."""
    n = 120
    rng = np.random.default_rng(3)
    # Trade size ramps 1x -> 4x; wins and losses cancel so the balance barely moves.
    scale = np.linspace(1.0, 4.0, n)
    pnls = (rng.normal(0.0, 500.0, n) * scale).tolist()
    balances = [50_000.0] * n
    _, model, _ = choose_shuffle_series(pnls, balances)
    assert model == "dollars"


def test_missing_or_unusable_balances_fall_back_to_dollars():
    pnls, balances = _compounding_run()
    assert choose_shuffle_series(pnls, None)[1] == "dollars"
    assert choose_shuffle_series(pnls, balances[:-1])[1] == "dollars"          # misaligned
    assert choose_shuffle_series(pnls, [0.0] * len(pnls))[1] == "dollars"      # zero balance
    assert choose_shuffle_series(pnls[:10], balances[:10])[1] == "dollars"     # too few to judge


def test_a_total_wipeout_falls_back_to_dollars():
    """A -100% trade cannot be compounded through; the dollar model is the safe answer."""
    pnls, balances = _compounding_run()
    pnls[40] = -balances[40]
    assert choose_shuffle_series(pnls, balances)[1] == "dollars"


# ── the simulation itself ─────────────────────────────────────────────────────

def test_fixed_size_results_are_unchanged_by_passing_balances():
    """The compounding support must not perturb a single existing fixed-size run."""
    pnls, balances = _fixed_size_run()
    a = run_monte_carlo(pnls, LIMITED, 2000, 500)
    b = run_monte_carlo(pnls, LIMITED, 2000, 500, 100, balances)
    assert b["shuffle_model"] == "dollars"
    # Same model and same input, so only RNG separates them — compare to a loose tolerance.
    assert b["median_max_dd"] == pytest.approx(a["median_max_dd"], rel=0.15)


def test_compounding_run_no_longer_reports_an_unreachable_drawdown():
    """The regression: shuffling a compounding run's DOLLARS puts a late, large trade early, where
    the account never held that much. On the real run this understated the worst-1% by ~8x."""
    pnls, balances = _compounding_run()
    dollars = run_monte_carlo(pnls, None, 2000, 500)
    returns = run_monte_carlo(pnls, None, 2000, 500, 100, balances)
    assert dollars["shuffle_model"] == "dollars"
    assert returns["shuffle_model"] == "returns"
    assert returns["pct1_max_dd"] > dollars["pct1_max_dd"]


def test_compounded_paths_never_lose_more_than_the_account():
    """The property the dollar model violated: no path may fall below -start_balance."""
    pnls, balances = _compounding_run()
    mc = run_monte_carlo(pnls, None, 500, 100, 100, balances)
    worst = min(min(p) for p in mc["sampled_paths"])
    assert worst > -balances[0]


# ── nothing to test against ───────────────────────────────────────────────────

def test_no_drawdown_limit_reports_none_not_zero():
    """0.0 is a claim; None is the absence of one. Reporting 0% breach AND 0% pass for the same
    run read as 'never breaches, never passes' when neither was ever measured."""
    pnls, balances = _fixed_size_run()
    mc = run_monte_carlo(pnls, NO_LIMIT, 500, 100, 100, balances)
    assert mc["prob_breach"] is None
    assert mc["prob_pass_eval"] is None


def test_no_ruleset_at_all_reports_none():
    pnls, _ = _fixed_size_run()
    mc = run_monte_carlo(pnls, None, 500, 100)
    assert mc["prob_breach"] is None
    assert mc["prob_pass_eval"] is None


def test_a_real_limit_still_produces_real_probabilities():
    pnls, balances = _fixed_size_run()
    mc = run_monte_carlo(pnls, LIMITED, 2000, 500, 100, balances)
    assert 0.0 <= mc["prob_breach"] <= 1.0
    assert mc["prob_pass_eval"] == pytest.approx(1.0 - mc["prob_breach"])
