"""The run score judges a drawdown in ONE unit, and the RUN decides which (2026-09-13).

Before this the score compared a run's deepest DOLLAR drop against the ruleset's dollar limit — a
limit written for the account's opening size. A run that compounds grows away from that size, so
its late dollar drops dwarf the limit while the share of the account it lost does not. MEASURED on
run 952f14f8172e (sos_fade, 246 trades, PF 4.85): its deepest dollar drop is $1,051,553 against
the 55% ruleset's $5,500, while its worst drop from its own running peak is 46.84% against that
ruleset's 55%. DISCARD, on a run the ruleset it was scored against would have kept.

The unit is decided by `stress_tester.drawdown_basis`, the test the Monte Carlo uses to pick its
`dd_basis`, so a run's badge and its stress-test grade are never judged in two units.

⚠ A fail-watch against HEAD is VACUOUS — the new keyword is a TypeError there, which proves the
signature and nothing else. Non-vacuity is by MUTATION, planted in memory with
`python3 -m scripts.testing.mutate`; each test names the mutation that turns it red.
"""

import ast
from pathlib import Path

from services import metrics, stress_tester, worthiness

# Per-trade returns on the balance each trade was taken with: two wins and a loss, fifteen times,
# then a run of five losses and a recovery. The account grows ~3.6x before the losing run, so its
# dollar trades DRIFT while its returns do not — the shape `drawdown_basis` calls compounding.
COMPOUNDING = [0.06, 0.06, -0.03] * 15 + [-0.065] * 5 + [0.06] * 10
# The same shape at a FIXED dollar size: nothing grows, so dollars stay the comparable unit.
FIXED = [450.0, 450.0, -300.0] * 15 + [-500.0] * 12 + [450.0] * 3

RISK_55 = "personal_forex_risk"  # 55% from peak on a $10,000 account, i.e. $5,500
DANGER_PCT = 0.7 * 55  # the score's danger zone starts at 70% of the limit

_BACKEND = Path(__file__).resolve().parent.parent


def _compounding(returns, start=10_000.0):
    out, bal = [], start
    for r in returns:
        profit = bal * r
        bal += profit
        out.append({"profit": profit, "equity": bal})
    return out


def _fixed(pnls, start=10_000.0):
    out, bal = [], start
    for p in pnls:
        bal += p
        out.append({"profit": p, "equity": bal})
    return out


def _dollar_dd(curve):
    """The deepest dollar drop from a running peak, negative — the shape a run's KPIs store."""
    peak = curve[0]["equity"] - curve[0]["profit"]
    worst = 0.0
    for e in curve:
        peak = max(peak, e["equity"])
        worst = max(worst, peak - e["equity"])
    return -worst


def _pf(curve):
    wins = sum(e["profit"] for e in curve if e["profit"] > 0)
    losses = -sum(e["profit"] for e in curve if e["profit"] < 0)
    return wins / losses


def _score(curve, rulesets):
    return worthiness.score_run_after_evals(
        "r", rulesets, _pf(curve), _dollar_dd(curve), len(curve), equity_curve=curve
    )


def test_a_compounding_run_is_judged_on_the_share_of_the_account_it_lost():
    """MUTATION: `basis = stress_tester.drawdown_basis(equity_curve)` -> `basis = DD_DOLLARS` in
    worthiness.py turns this red (TIER_3, drawdown_breach)."""
    curve = _compounding(COMPOUNDING)
    # Premises: without them the two units would agree and this would test nothing.
    assert stress_tester.drawdown_basis(curve) == "percent"
    assert -_dollar_dd(curve) > 5_500  # in dollars it IS past the limit
    assert metrics.max_drawdown_pct(curve) < DANGER_PCT  # as a share of its peak it is not near it
    assert _pf(curve) > 1.3 and len(curve) >= 50

    assert _score(curve, [RISK_55]) == (worthiness.TIER_1, None, RISK_55)


def test_a_fixed_size_run_is_still_judged_in_dollars():
    """MUTATION: `basis = stress_tester.drawdown_basis(equity_curve)` -> `basis = DD_PERCENT`
    turns this red — the same drop is under 38.5% of its peak, so percent would call it TIER_1."""
    curve = _fixed(FIXED)
    assert stress_tester.drawdown_basis(curve) == "dollars"
    assert -_dollar_dd(curve) > 5_500
    assert metrics.max_drawdown_pct(curve) < DANGER_PCT  # the units disagree, so this can tell

    assert _score(curve, [RISK_55]) == (worthiness.TIER_3, "drawdown_breach", RISK_55)


def test_a_run_with_no_curve_is_judged_in_dollars():
    """The optimizer's native combos arrive with KPIs only. MUTATION: forcing `DD_PERCENT` turns
    this red — there is no curve to take a percent from, so it scores nothing."""
    w = worthiness.score_run_after_evals("r", [RISK_55], 2.0, -6_000.0, 60, equity_curve=None)
    assert w == (worthiness.TIER_3, "drawdown_breach", RISK_55)


def test_the_strictest_ruleset_is_picked_in_the_runs_own_unit():
    """$2,000 on $50,000 is 4%; $3,000 on $100,000 is 3%. The smaller DOLLAR limit is the looser
    PERCENT one, so which ruleset is strictest depends on the unit.
    MUTATION: `_limit_in(ruleset, basis)` -> `_limit_in(ruleset, DD_DOLLARS)` turns this red."""
    rulesets = ["lucidflex_50k_eval", "apex_eod_100k_eval"]
    assert _score(_compounding(COMPOUNDING), rulesets)[2] == "apex_eod_100k_eval"
    assert _score(_fixed(FIXED), rulesets)[2] == "lucidflex_50k_eval"


def test_a_ruleset_stating_no_limit_still_scores_nothing():
    """`unconstrained` states no drawdown limit in either unit, so there is nothing to score
    against — the same answer as before this change, kept on both bases."""
    assert _score(_compounding(COMPOUNDING), ["unconstrained"]) is None
    assert _score(_fixed(FIXED), ["unconstrained"]) is None


def test_the_run_score_and_the_monte_carlo_read_one_unit():
    """MUTATION: `return "percent" if model == "returns" else "dollars"` -> `return "percent"` in
    `drawdown_basis` turns this red on the fixed-size run."""
    for curve, expected in ((_compounding(COMPOUNDING), "percent"), (_fixed(FIXED), "dollars")):
        pnls, balances = stress_tester.trade_series(curve)
        mc = stress_tester.run_monte_carlo(pnls, None, 50, 50, 5, balances)
        assert stress_tester.drawdown_basis(curve) == mc["dd_basis"] == expected


def _calls_missing_the_curve(source: str) -> list[int]:
    missing = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
        if name == "score_run_after_evals" and not any(
            k.arg == "equity_curve" for k in node.keywords
        ):
            missing.append(node.lineno)
    return missing


def test_every_caller_states_which_curve_it_is_scoring():
    """`equity_curve` is keyword-only with NO default, so a caller that forgets it raises — but only
    when that path finally runs, inside a background task on a finished run. This finds it first.
    ⚠ It reads SOURCE, so an in-memory mutation cannot reach it; the positive control is what
    proves it can see a missing keyword."""
    assert _calls_missing_the_curve("worthiness.score_run_after_evals(a, b, c, d, e)") == [1]
    calls = 0
    for folder in ("services", "routers"):
        for path in sorted((_BACKEND / folder).glob("*.py")):
            src = path.read_text(encoding="utf-8")
            calls += sum(
                1
                for n in ast.walk(ast.parse(src))
                if isinstance(n, ast.Call)
                and getattr(n.func, "attr", getattr(n.func, "id", None)) == "score_run_after_evals"
            )
            assert not _calls_missing_the_curve(src), f"{folder}/{path.name}"
    assert calls >= 6, "fewer call sites than this was written against — did the sweep miss some?"
