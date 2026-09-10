"""A shared stack's legs may not risk more per trade, together, than its cap (2026-09-10).

Aaron: *"if I put ten percent cap, then the strategies that I choose cannot trade more than the
cap … they cannot add up to more than the risk cap."*

The rule is `bot_accounts.share_overflow` — the one the Bots page refuses a live account with —
and `services/stack_risk_budget.py` asks it for two callers: the form's total and the launch. So
these tests pin three things: the decision is that shared check (not a private sum), an unreadable
risk refuses rather than counting as zero, and the page and the launch return the same sentence.

⚠ A fail-watch against HEAD is vacuous — none of this existed — so each test names the MUTATION
that turns it red, and each was run.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from services import lab_db
from services.stack_risk_budget import LegShare, budget, leg_share, recovery_share


def _leg(sid: str, risk):
    return LegShare(sid, sid.upper(), risk)


# ── the rule ────────────────────────────────────────────────────────────────────────────────


def test_shares_that_land_EXACTLY_on_the_cap_fit():
    """The intended configuration — two legs at 5% under 10% — is an exact fit, and so is a sum
    that binary floating point lands a hair over the cap.

    ⚠ 0.1 + 0.2 is the case that separates the shared check (which carries a tolerance) from a
    private `total <= cap`. 3.3 + 3.3 + 3.4 sums to exactly 10.0 and would NOT separate them —
    the premise is asserted so a future edit cannot quietly swap in inputs that agree by accident.

    MUTATION: decide on `total <= cap` instead of asking `share_overflow` → red here."""
    assert budget([_leg("a", 5.0), _leg("b", 5.0)], 10.0).fits

    assert 0.1 + 0.2 > 0.3  # the premise: a strict private comparison would refuse this
    fitted = budget([_leg("a", 0.1), _leg("b", 0.2)], 0.3)
    assert fitted.fits and fitted.reason is None


def test_shares_over_the_cap_are_refused_with_the_total_and_every_leg_named():
    """MUTATION: return `fits=True` when the shared check refuses → red."""
    verdict = budget([_leg("sos_fade", 10.0), _leg("extreme_leg", 5.0)], 10.0)
    assert not verdict.fits
    assert verdict.total_pct == 15.0
    assert "15%" in verdict.reason and "10% cap" in verdict.reason
    assert "SOS_FADE 10%" in verdict.reason and "EXTREME_LEG 5%" in verdict.reason


def test_an_unreadable_risk_REFUSES_and_is_never_counted_as_zero():
    """Rule 1. With the other leg at 5% under a 10% cap, a zero would FIT — the one outcome this
    exists to prevent — and a partial total is a number that gets believed.

    MUTATION: read a missing risk as 0.0 → red (it fits, total 5)."""
    verdict = budget([_leg("sos_fade", 5.0), _leg("mystery", None)], 10.0)
    assert not verdict.fits
    assert verdict.total_pct is None
    assert "MYSTERY" in verdict.reason and "not a risk of zero" in verdict.reason


def test_a_leg_s_share_is_read_off_the_settings_it_will_run_with():
    assert leg_share("a", "A", {"exec_risk_pct": 7.5}).risk_pct == 7.5
    assert leg_share("a", "A", {}).risk_pct is None
    # A string or a bool is malformed, not a number — the Bots page's reader refuses both.
    assert leg_share("a", "A", {"exec_risk_pct": "7.5"}).risk_pct is None
    assert leg_share("a", "A", {"exec_risk_pct": True}).risk_pct is None


# ── the recovery leg ────────────────────────────────────────────────────────────────────────


def test_the_recovery_share_is_its_parent_s_risk_times_the_rule_s_fraction():
    parent = _leg("sos_fade", 8.0)
    rec = recovery_share(parent, {}, {"rec_risk_frac": 0.25}, "REC")
    assert rec.risk_pct == 2.0 and rec.recovery_of == "sos_fade"
    # The request's fraction wins over the rule's stored default.
    assert (
        recovery_share(parent, {"rec_risk_frac": 0.5}, {"rec_risk_frac": 0.25}, "R").risk_pct == 4.0
    )


def test_a_STATED_but_malformed_fraction_refuses_rather_than_falling_back_to_the_default():
    """A request that states a fraction nobody can read has not asked for the default; quietly
    using it would total a stack the launch then builds differently.

    MUTATION: fall back to the rule default whenever the request's value is unreadable → red."""
    parent = _leg("sos_fade", 8.0)
    rec = recovery_share(parent, {"rec_risk_frac": "a quarter"}, {"rec_risk_frac": 0.25}, "REC")
    assert rec.risk_pct is None


# ── through the endpoints ───────────────────────────────────────────────────────────────────


def _seed(monkeypatch, tmp_path, risks: dict):
    from routers import stacks as stacks_router
    from services import portfolio_runner

    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "lab.db")
    monkeypatch.setattr(portfolio_runner, "_LAB_RESULTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(stacks_router, "_LAB_RESULTS_DIR", tmp_path / "reports")
    lab_db.init_db()
    for sid, params in risks.items():
        lab_db.upsert_strategy(
            {
                "id": sid,
                "name": sid.replace("_", " ").title(),
                "runner": "python",
                "class_name": sid,
                "source_path": f"strategies/python/{sid}",
                "scanned_at": 1,
                "param_schema": [],
                "default_params": params,
            }
        )


def _launch_body(**over):
    body = {
        "strategy_ids": ["sos_fade", "extreme_leg"],
        "instrument": "XAUUSD",
        "bar_type": "Minute",
        "bar_value": 15,
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "mode": "shared",
        "account_size": 10_000,
        "risk_cap_pct": 10,
        "broker_profile": "vantage_demo",
        "charge_costs": False,
    }
    body.update(over)
    return body


# The shipped defaults as they stand: SOS Fade 10% and the extreme leg 5% — 15% against the 10%
# default cap. This is the pair the form now blocks until a leg comes down.
_SHIPPED = {"sos_fade": {"exec_risk_pct": 10.0}, "extreme_leg": {"exec_risk_pct": 5.0}}


def test_the_form_s_check_and_the_launch_refuse_with_the_SAME_sentence(
    client, tmp_path, monkeypatch
):
    """One function, two callers — the page cannot show a reason the launch does not give.

    MUTATION: drop the refusal from `trigger_stack` → the launch answers 202 and this goes red."""
    _seed(monkeypatch, tmp_path, _SHIPPED)
    check = client.post(
        "/backtests/stacks/risk-budget",
        json={"strategy_ids": ["sos_fade", "extreme_leg"], "risk_cap_pct": 10},
    )
    # A 200 carrying the refusal: the question is legitimate, and an error status would make a
    # working form look broken.
    assert check.status_code == 200, check.text
    body = check.json()
    assert body["fits"] is False and body["total_pct"] == 15.0
    assert [leg["risk_pct"] for leg in body["legs"]] == [10.0, 5.0]

    with patch("services.portfolio_runner.launch") as launched:
        res = client.post("/backtests/stack", json=_launch_body())
    assert res.status_code == 400, res.text
    assert res.json()["detail"] == body["reason"]
    assert not launched.called


def test_a_leg_brought_down_to_fit_is_accepted_by_both(client, tmp_path, monkeypatch):
    """The per-leg risk box sends a leg's override; both callers must read it, or the page says
    it fits while the launch refuses on the stored default.

    MUTATION: resolve each leg off its stored defaults only → red."""
    _seed(monkeypatch, tmp_path, _SHIPPED)
    lowered = {"sos_fade": {"exec_risk_pct": 5.0}}
    check = client.post(
        "/backtests/stacks/risk-budget",
        json={
            "strategy_ids": ["sos_fade", "extreme_leg"],
            "risk_cap_pct": 10,
            "params_by_strategy": lowered,
        },
    )
    assert check.json()["fits"] is True and check.json()["total_pct"] == 10.0

    with patch("services.portfolio_runner.launch"):
        res = client.post("/backtests/stack", json=_launch_body(params_by_strategy=lowered))
    assert res.status_code == 202, res.text


def test_a_SCREEN_is_never_refused_on_the_cap(client, tmp_path, monkeypatch):
    """A screen gives every leg its own full account — there is no shared cap to exceed.

    MUTATION: apply the refusal regardless of mode → red."""
    _seed(monkeypatch, tmp_path, _SHIPPED)
    # The screen path schedules its legs as a task, so the stand-in has to be awaitable.
    with patch("routers.stacks.run_sweep", new=AsyncMock()):
        res = client.post("/backtests/stack", json=_launch_body(mode="screen"))
    assert res.status_code == 202, res.text


def test_the_recovery_leg_COUNTS_against_the_cap(client, tmp_path, monkeypatch):
    """A recovery can hold a position while its parent opens the next one, so it spends the same
    budget. SOS Fade 8% plus a half-size recovery (4%) is 12% — over a 10% cap.

    MUTATION: leave the recovery leg out of the budget → it fits at 8% and this goes red."""
    _seed(
        monkeypatch,
        tmp_path,
        {"sos_fade": {"exec_risk_pct": 8.0}, "loss_recovery": {"rec_risk_frac": 0.25}},
    )
    check = client.post(
        "/backtests/stacks/risk-budget",
        json={
            "strategy_ids": ["sos_fade"],
            "risk_cap_pct": 10,
            "recovery_parent": "sos_fade",
            "recovery_params": {"rec_risk_frac": 0.5},
        },
    )
    body = check.json()
    assert body["fits"] is False and body["total_pct"] == 12.0
    rec = body["legs"][-1]
    assert rec["recovery_of"] == "sos_fade" and rec["risk_pct"] == 4.0
    assert "(on Sos Fade)" in rec["name"]


@pytest.mark.parametrize("parent", ["extreme_leg", "nobody"])
def test_a_recovery_parent_outside_the_stack_is_refused(client, tmp_path, monkeypatch, parent):
    _seed(monkeypatch, tmp_path, _SHIPPED)
    res = client.post(
        "/backtests/stacks/risk-budget",
        json={"strategy_ids": ["sos_fade"], "risk_cap_pct": 10, "recovery_parent": parent},
    )
    assert res.status_code == 400
