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


# ── the BENCH: a bot on no account, which is what "remove" writes ─────────────
#
# Added 2026-08-09 with add/remove on the Accounts tab. Removing a bot from an account has to
# land SOMEWHERE, and `account: null` is that place — registered, configured, trading nothing.


def test_a_benched_bot_is_its_own_group_and_not_an_unreadable_one():
    """MUTATION: key `group_by_account` on `account` alone (dropping `kind`) → these two land in
    one group and this goes red. They are opposite things: one is a state somebody chose, the
    other is a fault, and merging them gives a broken config the same controls as a resting bot."""
    groups = ba.group_by_account({"benched": _cfg("benched", account=None), "broken": None})
    kinds = {g.kind: g for g in groups}
    assert set(kinds) == {"bench", "unknown"}
    assert [b.key for b in kinds["bench"].bots] == ["benched"]
    assert [b.key for b in kinds["unknown"].bots] == ["broken"]


def test_two_benched_bots_are_NOT_stacked():
    """MUTATION: drop the `kind` guard from `AccountGroup.stacked` → red.

    They share no balance, so a Stacked chip here would be a false alarm about doubled risk on
    bots that are not trading — the one direction that chip must never fail in."""
    groups = ba.group_by_account({"a": _cfg("a", account=None),
                                  "b": _cfg("b", account=None, magic=2)})
    assert len(groups) == 1
    assert groups[0].kind == "bench"
    assert groups[0].stacked is False


def test_a_benched_bot_does_not_join_a_real_account():
    groups = ba.group_by_account({"live": _cfg("live"), "benched": _cfg("benched", account=None)})
    real = next(g for g in groups if g.kind == "account")
    assert [b.key for b in real.bots] == ["live"]
    assert real.stacked is False


# ── the order tag, reported only when it is a problem ────────────────────────
def test_two_bots_on_one_account_sharing_a_magic_are_named():
    """The raw number told the reader nothing ("I don't know what the column magic even means"),
    but two bots sharing one each read the OTHER's orders as their own. So the FACT is reported
    and the number is not shown at all."""
    g = ba.group_by_account({"a": _cfg("a", magic=770115),
                             "b": _cfg("b", magic=770115)})[0]
    assert g.magic_clash == ["a", "b"]


def test_distinct_magics_report_no_clash():
    g = ba.group_by_account({"a": _cfg("a", magic=1), "b": _cfg("b", magic=2)})[0]
    assert g.magic_clash == []


def test_bots_with_no_magic_at_all_do_not_manufacture_a_clash():
    """MUTATION: drop the `unreadable or not b.magic` skip → both read magic 0, collide, and a
    pair of configs that simply do not state one is reported as a live order-tag conflict.

    🔴 The first version of this test was VACUOUS and PASSED against that mutation. It used two
    UNREADABLE configs — and an unreadable bot is grouped under `unknown`, where `magic_clash`
    returns early on `kind`, so the skip it named was never reached. The reachable half of that
    guard is a READABLE config with no `magic` key, which is what this drives. The `unreadable`
    clause beside it is defensive and is deliberately NOT claimed as covered.
    """
    a, b = _cfg("a"), _cfg("b")
    del a["magic"], b["magic"]
    g = ba.group_by_account({"a": a, "b": b})[0]
    assert g.kind == "account"
    assert g.magic_clash == []


def test_benched_bots_sharing_a_magic_are_not_a_clash():
    """They are on no terminal, so there is no order book for them to collide in — and
    `live_config._assert_magic_is_unique` exempts the bench for the same reason."""
    g = ba.group_by_account({"a": _cfg("a", account=None, magic=7),
                             "b": _cfg("b", account=None, magic=7)})[0]
    assert g.magic_clash == []


# ── moving a bot writes more than `account` ───────────────────────────────────
def test_joining_an_account_ADOPTS_its_cap_server_and_terminal_source():
    """MUTATION: return only `{"account": ...}` from `assign_plan` → red.

    The cap is the one that bites: a bot arriving with its own cap does not merely misconfigure
    itself, it takes every bot ALREADY on the account off the box at their next restart, because
    `live_config._assert_account_cap_agrees` refuses the whole account."""
    target = ba.group_by_account({"a": _cfg("a", cap=10.0)})[0]
    plan = ba.assign_plan("newbot", target)
    assert plan.fields["account"] == 700107749
    assert plan.fields["account_risk_cap_pct"] == 10.0
    assert plan.fields["server"] == "PUPrime-Demo"
    assert plan.adopt_terminal_from == "a"


def test_joining_an_UNCAPPED_account_adopts_the_absence_of_a_cap():
    """`None` is a value here, not a field to omit — one capped bot beside one uncapped one is
    the worst shape, and it is what omitting this would produce."""
    target = ba.group_by_account({"a": _cfg("a", cap=None)})[0]
    plan = ba.assign_plan("newbot", target)
    assert "account_risk_cap_pct" in plan.fields
    assert plan.fields["account_risk_cap_pct"] is None


def test_benching_writes_ONLY_the_account():
    """The server, terminal and cap are what make re-assignment cheap, and a cap of None on a
    benched bot is not a claim about any account — the startup guard exempts the bench."""
    plan = ba.assign_plan("a", None)
    assert plan.fields == {"account": None}
    assert plan.adopt_terminal_from == ""


def test_joining_an_account_whose_bots_DISAGREE_about_the_cap_is_refused():
    """MUTATION: drop the `cap_agrees` check → the new bot adopts `None` (the disagreement's
    reported cap) and quietly becomes the third opinion."""
    target = ba.group_by_account({"a": _cfg("a", cap=10.0),
                                  "b": _cfg("b", magic=2, cap=20.0)})[0]
    with pytest.raises(ValueError, match="different risk caps"):
        ba.assign_plan("newbot", target)


def test_joining_an_account_with_an_unreadable_bot_is_refused():
    groups = ba.group_by_account({"a": _cfg("a", cap=10.0), "broken": None})
    target = next(g for g in groups if g.kind == "account")
    target.bots.append(ba.AccountBot(key="broken", display="broken", symbol="", magic=0,
                                     strategy_package="", unreadable=True))
    with pytest.raises(ValueError, match="cannot be read"):
        ba.assign_plan("newbot", target)


def test_a_bench_group_cannot_be_an_assignment_TARGET():
    """`assign_plan(bot, bench_group)` would read as "move it to the bench", which is what
    `None` already means — two spellings of one action is how they drift apart."""
    bench = ba.group_by_account({"a": _cfg("a", account=None)})[0]
    with pytest.raises(ValueError, match="real account"):
        ba.assign_plan("newbot", bench)


# ── the assign endpoint ───────────────────────────────────────────────────────
def test_moving_a_bot_to_an_account_nobody_trades_is_a_404(client, monkeypatch):
    """Its server, terminal and cap are read off the bots already there, so a first bot has
    nothing to adopt and the honest answer is that the account does not exist here."""
    from routers import bots as bots_router
    monkeypatch.setattr(bots_router, "_bot_is_running", lambda key: False)
    r = client.patch("/bots/mpc_bleg_demo/account", json={"account": 999999})
    assert r.status_code == 404


def test_moving_an_unknown_bot_is_a_404(client):
    r = client.patch("/bots/not_a_bot/account", json={"account": 700107749})
    assert r.status_code == 404


def test_a_RUNNING_bot_refuses_to_be_moved(client, monkeypatch):
    """It read its config at startup, so the write cannot reach the live process — the page
    would show it under one account while it went on trading another."""
    from routers import bots as bots_router
    monkeypatch.setattr(bots_router, "_bot_is_running", lambda key: True)
    r = client.patch("/bots/mpc_bleg_demo/account", json={"account": 700107749})
    assert r.status_code == 409
    assert "running" in r.json()["detail"]
