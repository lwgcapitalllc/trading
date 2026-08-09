"""Which bots share an account, and the one number that says how much risk it may hold.

A live "stack" is READ from the instance configs, not configured separately, so most of these
are about the grouping being derived rather than stored. The rest are about the cap, whose
awkwardness is that it is an ACCOUNT-level fact living in N per-bot files: every way it can be
half-applied is a way the account ends up with two ceilings and no error anywhere.
"""

from __future__ import annotations

import pytest

from services import bot_accounts as ba


def _cfg(key, *, account=700107749, magic=770115, cap=None, risk=10.0, name=None):
    return {
        "bot_key": key,
        "display_name": name or key.upper(),
        "account": account,
        "server": "PUPrime-Demo",
        "symbol": "XAUUSD.s",
        "magic": magic,
        "strategy_package": "mpc_sos_fade",
        "account_risk_cap_pct": cap,
        "strategy_params": {"exec_risk_pct": risk},
    }


# ── grouping is derived from what the bots actually trade ─────────────────────
def test_two_bots_naming_one_account_are_stacked():
    """There is no stack object to be in or out of — sharing a balance IS the definition."""
    groups = ba.group_by_account({"a": _cfg("a"), "b": _cfg("b", magic=770116)})
    assert len(groups) == 1
    assert groups[0].stacked is True
    assert {b.key for b in groups[0].bots} == {"a", "b"}


def test_two_bots_on_different_accounts_are_not_stacked():
    groups = ba.group_by_account({"a": _cfg("a"), "b": _cfg("b", account=999)})
    assert len(groups) == 2
    assert all(g.stacked is False for g in groups)


def test_an_unreadable_config_still_counts_as_a_bot():
    """Dropping it would report an account with fewer bots on it than it has — the most
    reassuring wrong answer available on a page about how much risk is on."""
    groups = ba.group_by_account({"a": _cfg("a"), "broken": None})
    keys = {b.key for g in groups for b in g.bots}
    assert "broken" in keys
    assert next(b for g in groups for b in g.bots if b.key == "broken").unreadable is True


def test_an_unreadable_config_makes_its_accounts_cap_unknown():
    """Unknown is a THIRD state beside capped and uncapped. Reading it as either would let the
    page make a claim about a ceiling it could not check."""
    groups = ba.group_by_account({"a": _cfg("a", cap=10.0), "broken": None})
    assert any(g.cap_unknown for g in groups)


# ── the cap must mean ONE thing per account ───────────────────────────────────
def test_one_agreed_cap_is_reported():
    g = ba.group_by_account({"a": _cfg("a", cap=10.0), "b": _cfg("b", magic=2, cap=10.0)})[0]
    assert g.cap_agrees is True and g.risk_cap_pct == 10.0


def test_disagreeing_caps_report_NO_cap_rather_than_picking_one():
    """Not the max and not the min. Picking one invents a ceiling nobody configured, and hides
    the fault behind a number that looks exactly like a configured one."""
    g = ba.group_by_account({"a": _cfg("a", cap=10.0), "b": _cfg("b", magic=2, cap=20.0)})[0]
    assert g.cap_agrees is False
    assert g.risk_cap_pct is None


def test_a_capped_bot_beside_an_uncapped_one_is_a_DISAGREEMENT():
    """`None` means uncapped, not "no opinion". Treating it as inheritable would let the absent
    value silently acquire a meaning nobody wrote down — and this is the worst shape of the
    three, because the uncapped bot fills the account while the capped one is refused."""
    g = ba.group_by_account({"a": _cfg("a", cap=10.0), "b": _cfg("b", magic=2, cap=None)})[0]
    assert g.cap_agrees is False


def test_every_bot_uncapped_is_coherent_and_not_a_disagreement():
    """The honest state of a one-bot account, and of every account before this existed."""
    g = ba.group_by_account({"a": _cfg("a"), "b": _cfg("b", magic=2)})[0]
    assert g.cap_agrees is True and g.risk_cap_pct is None


# ── a cap at or under a bot's own risk % does not SHARE, it takes turns ───────
def test_a_cap_equal_to_the_per_trade_risk_takes_turns():
    """The two numbers together imply something neither states: at a 10% cap against two bots
    each risking 10%, one full-size position or resting order fills the whole budget and the
    other bot is refused until it comes back."""
    g = ba.group_by_account({"a": _cfg("a", cap=10.0, risk=10.0),
                             "b": _cfg("b", magic=2, cap=10.0, risk=10.0)})[0]
    assert g.cap_takes_turns is True


def test_a_cap_above_the_summed_risk_does_not_take_turns():
    g = ba.group_by_account({"a": _cfg("a", cap=25.0, risk=10.0),
                             "b": _cfg("b", magic=2, cap=25.0, risk=10.0)})[0]
    assert g.cap_takes_turns is False


def test_a_single_bot_never_takes_turns_with_itself():
    """It has no one to contend with, and its own exposure is excluded from its own check."""
    g = ba.group_by_account({"a": _cfg("a", cap=10.0, risk=10.0)})[0]
    assert g.cap_takes_turns is False


def test_turn_taking_is_not_claimed_when_the_caps_disagree():
    """There is no account cap to compare against, so the question cannot be answered."""
    g = ba.group_by_account({"a": _cfg("a", cap=10.0, risk=10.0),
                             "b": _cfg("b", magic=2, cap=50.0, risk=10.0)})[0]
    assert g.cap_takes_turns is False


# ── writing the cap is all-or-nothing ─────────────────────────────────────────
def test_the_change_plan_names_only_the_bots_that_differ():
    """A no-op write would still produce a commit, a push and a VPS pull."""
    g = ba.group_by_account({"a": _cfg("a", cap=10.0), "b": _cfg("b", magic=2, cap=20.0)})[0]
    assert ba.cap_change_plan(g, 10.0) == ["b"]


def test_the_change_plan_covers_every_bot_when_none_match():
    g = ba.group_by_account({"a": _cfg("a", cap=10.0), "b": _cfg("b", magic=2, cap=10.0)})[0]
    assert sorted(ba.cap_change_plan(g, 20.0)) == ["a", "b"]


def test_clearing_the_cap_is_a_real_change():
    """`None` means uncapped, which is a value — not "leave it alone"."""
    g = ba.group_by_account({"a": _cfg("a", cap=10.0)})[0]
    assert ba.cap_change_plan(g, None) == ["a"]


def test_an_unreadable_bot_REFUSES_the_whole_write():
    """Writing to three of four configs leaves exactly the disagreement this mechanism exists to
    prevent, and it would report success."""
    g = ba.group_by_account({"a": _cfg("a", cap=10.0), "broken": None})
    target = next(x for x in g if any(b.unreadable for b in x.bots))
    with pytest.raises(ValueError, match="EVERY bot"):
        ba.cap_change_plan(target, 10.0)


# ── the API ───────────────────────────────────────────────────────────────────
def test_the_accounts_endpoint_answers_without_touching_the_vps(client):
    """It reads the same files the bots read, so it is pollable and it still answers while the
    box is unreachable. `tests/conftest.py` refuses any live VPS call, so a route that shelled
    out would fail here rather than passing slowly."""
    r = client.get("/bots/accounts")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    for g in body:
        assert "stacked" in g and "cap_agrees" in g and "risk_cap_pct" in g


def test_setting_a_cap_on_an_unknown_account_is_a_404(client):
    r = client.patch("/bots/accounts/12345/risk-cap", json={"risk_cap_pct": 10.0})
    assert r.status_code == 404


def test_a_zero_cap_is_refused_because_it_would_block_every_order(client):
    """If the intent is "stop trading", that is the fleet halt — which stops orders without
    making every bot log a risk refusal for the rest of the day."""
    r = client.patch("/bots/accounts/700107749/risk-cap", json={"risk_cap_pct": 0})
    assert r.status_code == 422


def test_a_cap_over_100_percent_is_refused(client):
    r = client.patch("/bots/accounts/700107749/risk-cap", json={"risk_cap_pct": 150})
    assert r.status_code == 422
