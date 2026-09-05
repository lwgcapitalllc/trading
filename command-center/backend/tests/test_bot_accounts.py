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
        "strategy_package": "sos_fade",
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
    g = ba.group_by_account(
        {"a": _cfg("a", cap=10.0, risk=10.0), "b": _cfg("b", magic=2, cap=10.0, risk=10.0)}
    )[0]
    assert g.cap_takes_turns is True


def test_a_cap_above_the_summed_risk_does_not_take_turns():
    g = ba.group_by_account(
        {"a": _cfg("a", cap=25.0, risk=10.0), "b": _cfg("b", magic=2, cap=25.0, risk=10.0)}
    )[0]
    assert g.cap_takes_turns is False


def test_a_single_bot_never_takes_turns_with_itself():
    """It has no one to contend with, and its own exposure is excluded from its own check."""
    g = ba.group_by_account({"a": _cfg("a", cap=10.0, risk=10.0)})[0]
    assert g.cap_takes_turns is False


def test_turn_taking_is_not_claimed_when_the_caps_disagree():
    """There is no account cap to compare against, so the question cannot be answered."""
    g = ba.group_by_account(
        {"a": _cfg("a", cap=10.0, risk=10.0), "b": _cfg("b", magic=2, cap=50.0, risk=10.0)}
    )[0]
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


def test_the_endpoint_SERVES_the_shares_it_computed(client, monkeypatch):
    """The two fields the page renders instead of adding anything up itself.

    🔴 **ASSERTS THE VALUES, NEVER THAT THE KEYS ARE PRESENT — and BOTH earlier versions of this
    test survived their own mutation, for two DIFFERENT reasons worth keeping apart.**

    The first asserted `"share_total_pct" in g`. The response model declares both with a default of
    `None`, so the key is in the JSON whether or not the router assigns it — the trap this backend
    already met on the `python` lock scope: *ask not only whether the model declares a field, but
    whether anything actually assigns it.*

    The second compared the served values against the router's own grouping, on the REAL instance
    configs. That caught the total and still could not catch the reason: today's account holds one
    bot at 10% under a 10% cap, so its shares FIT and the honest answer is `None` — **the same
    value an unassigned field defaults to.** A comparison whose two sides agree by accident is not
    a comparison. It is the scale-of-1 lesson in the root CLAUDE.md: check that a test's inputs can
    distinguish the behaviours it names.

    So the grouping is STUBBED with an over-subscribed account, where the total is a distinctive
    number and the reason is a sentence. MUTATION: drop either field from the endpoint and this
    reddens on that field alone.
    """
    from routers import bots as bots_router

    group = ba.AccountGroup(
        account=700107749,
        server="PUPrime-Demo",
        kind="account",
        bots=[_bot("a", 10.0), _bot("b", 5.0)],
        risk_cap_pct=10.0,
    )
    assert group.share_total_pct == 15.0
    assert group.share_overflow_reason is not None, "the stub must be able to tell the two apart"
    monkeypatch.setattr(bots_router, "_account_groups", lambda: [group])

    row = client.get("/bots/accounts").json()[0]
    assert row["share_total_pct"] == 15.0
    assert row["share_overflow_reason"] == group.share_overflow_reason


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
    groups = ba.group_by_account(
        {"a": _cfg("a", account=None), "b": _cfg("b", account=None, magic=2)}
    )
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
    g = ba.group_by_account({"a": _cfg("a", magic=770115), "b": _cfg("b", magic=770115)})[0]
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
    g = ba.group_by_account(
        {"a": _cfg("a", account=None, magic=7), "b": _cfg("b", account=None, magic=7)}
    )[0]
    assert g.magic_clash == []


# ── moving a bot writes more than `account` ───────────────────────────────────
def test_joining_an_account_ADOPTS_its_cap_server_and_terminal_source():
    """MUTATION: return only `{"account": ...}` from `assign_plan` → red.

    The cap is the one that bites: a bot arriving with its own cap does not merely misconfigure
    itself, it takes every bot ALREADY on the account off the box at their next restart, because
    `live_config._assert_account_cap_agrees` refuses the whole account."""
    target = ba.group_by_account({"a": _cfg("a", cap=10.0)})[0]
    plan = ba.assign_plan("newbot", 700107749, target=target)
    assert plan.fields["account"] == 700107749
    assert plan.fields["account_risk_cap_pct"] == 10.0
    assert plan.fields["server"] == "PUPrime-Demo"
    assert plan.adopt_terminal_from == "a"


def test_joining_an_UNCAPPED_account_adopts_the_absence_of_a_cap():
    """`None` is a value here, not a field to omit — one capped bot beside one uncapped one is
    the worst shape, and it is what omitting this would produce."""
    target = ba.group_by_account({"a": _cfg("a", cap=None)})[0]
    plan = ba.assign_plan("newbot", 700107749, target=target)
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
    target = ba.group_by_account({"a": _cfg("a", cap=10.0), "b": _cfg("b", magic=2, cap=20.0)})[0]
    with pytest.raises(ValueError, match="different risk caps"):
        ba.assign_plan("newbot", 700107749, target=target)


def test_joining_an_account_with_an_unreadable_bot_is_refused():
    groups = ba.group_by_account({"a": _cfg("a", cap=10.0), "broken": None})
    target = next(g for g in groups if g.kind == "account")
    target.bots.append(
        ba.AccountBot(
            key="broken", display="broken", symbol="", magic=0, strategy_package="", unreadable=True
        )
    )
    with pytest.raises(ValueError, match="cannot be read"):
        ba.assign_plan("newbot", 700107749, target=target)


def test_a_bench_group_cannot_be_an_assignment_TARGET():
    """Passing a bench group as the target would read as "move it to the bench", which is what an
    `account` of `None` already means — two spellings of one action is how they drift apart."""
    bench = ba.group_by_account({"a": _cfg("a", account=None)})[0]
    with pytest.raises(ValueError, match="not this account"):
        ba.assign_plan("newbot", 700107749, target=bench)


# ── the assign endpoint ───────────────────────────────────────────────────────
def test_moving_a_bot_to_an_account_nobody_trades_is_a_404(client, monkeypatch):
    """Its server, terminal and cap are read off the bots already there, so a first bot has
    nothing to adopt and the honest answer is that the account does not exist here."""
    from routers import bots as bots_router

    monkeypatch.setattr(bots_router, "_bot_is_running", lambda key: False)
    r = client.patch("/bots/b_leg_demo/account", json={"account": 999999})
    assert r.status_code == 404


def test_moving_an_unknown_bot_is_a_404(client):
    r = client.patch("/bots/not_a_bot/account", json={"account": 700107749})
    assert r.status_code == 404


def test_a_RUNNING_bot_refuses_to_be_moved(client, monkeypatch):
    """It read its config at startup, so the write cannot reach the live process — the page
    would show it under one account while it went on trading another."""
    from routers import bots as bots_router

    monkeypatch.setattr(bots_router, "_bot_is_running", lambda key: True)
    r = client.patch("/bots/b_leg_demo/account", json={"account": 700107749})
    assert r.status_code == 409
    assert "running" in r.json()["detail"]


# ── the shares may not add up to more than the ceiling (2026-09-03) ───────────
#
# Aaron: "the risk per trade cannot add up to more than that cap". `cap_takes_turns` already
# stated the fact — a cap that lets both hold has to exceed the SUM — and nothing enforced it.
def _bot(key, risk):
    return ba.AccountBot(
        key=key,
        display=key.upper(),
        symbol="XAUUSD.p",
        magic=1,
        strategy_package="p",
        risk_pct=risk,
    )


def test_two_five_percent_shares_FIT_a_ten_percent_cap():
    """🔴 The intended configuration, so it must not be a near miss. Binary floating point is
    what makes this worth a test rather than an assumption."""
    assert ba.share_overflow([_bot("a", 5.0), _bot("b", 5.0)], 10.0) is None


def test_shares_that_EXCEED_the_cap_are_refused():
    assert ba.share_overflow([_bot("a", 5.0), _bot("b", 10.0)], 10.0) is not None


def test_a_THIRD_bot_is_what_tips_a_five_five_account_over():
    """The case Aaron asked about outright. Two fit exactly; a third of any size does not."""
    assert ba.share_overflow([_bot("a", 5.0), _bot("b", 5.0), _bot("c", 5.0)], 10.0) is not None


def test_the_refusal_NAMES_the_shares_and_the_total():
    """A refusal a reader cannot act on is a wall. It has to say what is on the account and by
    how much, or the only way forward is opening three config files."""
    msg = ba.share_overflow([_bot("a", 5.0), _bot("b", 10.0)], 10.0)
    assert "15%" in msg and "10%" in msg
    assert "A" in msg and "B" in msg


def test_an_UNCAPPED_account_has_nothing_to_check():
    """`None` is a deliberate, supported state — the honest one for a single-bot account — and is
    not a cap of zero. RED if an uncapped account starts refusing."""
    assert ba.share_overflow([_bot("a", 10.0), _bot("b", 10.0)], None) is None


def test_an_UNREADABLE_share_REFUSES_rather_than_counting_as_zero():
    """🔴 Rule 1. A bot whose risk cannot be read is not a bot risking nothing, and scoring it 0
    would let a genuinely over-subscribed account save cleanly — the one outcome this prevents."""
    unknown = _bot("b", None)
    assert ba.share_overflow([_bot("a", 10.0), unknown], 10.0) is not None


def test_an_unreadable_CONFIG_refuses_too():
    broken = _bot("b", 5.0)
    broken.unreadable = True
    assert ba.share_overflow([_bot("a", 5.0), broken], 10.0) is not None


def test_ONE_bot_at_the_cap_is_fine():
    """The live account today: one bot, its share equal to the ceiling. It must not be refused —
    a cap EQUAL to the only share is full allocation, not over-allocation."""
    assert ba.share_overflow([_bot("a", 10.0)], 10.0) is None


# ── the same two answers, SERVED to the page (2026-09-04) ─────────────────────
#
# 🔴 **The page had its own copy of the total and the copy was the lenient one.** It added the
# shares up with `?? 0`, so a bot whose share could not be read counted as a bot risking nothing
# — the exact leniency `share_overflow` refuses by name three functions above. The browser could
# therefore print a total that fitted under the cap on an account the save would refuse.
#
# ⚠ **And the total only appeared at all in the take-turns note**, which needs the cap to be at
# or under the largest single share — so the intended 5/5-under-10 configuration never displayed
# it, and the way you found out was to type a number and be refused.


def test_the_served_total_is_the_sum_of_the_shares():
    g = ba.group_by_account(
        {"a": _cfg("a", cap=10.0, risk=5.0), "b": _cfg("b", magic=2, cap=10.0, risk=5.0)}
    )[0]
    assert g.share_total_pct == 10.0


def test_the_served_total_REFUSES_an_unreadable_share_rather_than_scoring_it_zero():
    """🔴 The whole reason this is served. MUTATION: sum with `or 0.0` and this goes red.

    The page's own version returned 10.0 here — a number that fits a 10% cap — for an account
    holding one 10% bot and one bot whose share nobody can read."""
    g = ba.group_by_account(
        {"a": _cfg("a", cap=10.0, risk=10.0), "b": _cfg("b", magic=2, cap=10.0, risk=None)}
    )[0]
    assert g.share_total_pct is None


def test_an_unreadable_CONFIG_makes_the_total_unanswerable_too():
    """The flag is load-bearing on its own, so this bot states a PERFECTLY READABLE 5% and is
    still not counted — same shape as `test_an_unreadable_CONFIG_refuses_too` above, because both
    functions must treat an unparsed config as a share nobody knows rather than a share of 5.

    ⚠ **A config that could not be read never reaches a real account group** — it goes to the
    `unknown` bucket, since there is no way to tell which account it belongs to. That is why this
    builds the group directly instead of feeding `group_by_account` a `None`."""
    broken = _bot("b", 5.0)
    broken.unreadable = True
    g = ba.AccountGroup(account=1, server="S", bots=[_bot("a", 5.0), broken])
    assert g.share_total_pct is None


def test_the_unreadable_bucket_cannot_be_totalled_either():
    """The group an unreadable config actually lands in. It must not print 0% — an account whose
    configs cannot be read is the one place a reassuring number is most likely to be believed."""
    groups = ba.group_by_account({"a": _cfg("a", cap=10.0, risk=5.0), "b": None})
    unknown = next(g for g in groups if g.kind == "unknown")
    assert unknown.share_total_pct is None


def test_an_account_with_no_bots_totals_ZERO_not_unknown():
    """`None` here means a share could not be read. An empty account has no unreadable share —
    it has none at all, and 0% has genuinely been handed out. The page builds exactly this group
    for a registered account nobody is trading yet."""
    assert ba.AccountGroup(account=1, server="S").share_total_pct == 0.0


def test_the_served_overflow_reason_is_the_SAME_call_the_save_makes():
    """🔴 One rule, one place. MUTATION: re-derive it from `share_total_pct > risk_cap_pct` and
    the float tolerance drifts away from the write path's, which is how the page ends up
    disagreeing with the save it is standing in front of."""
    g = ba.group_by_account(
        {"a": _cfg("a", cap=10.0, risk=10.0), "b": _cfg("b", magic=2, cap=10.0, risk=5.0)}
    )[0]
    assert g.share_overflow_reason == ba.share_overflow(g.bots, g.risk_cap_pct)
    assert g.share_overflow_reason is not None
    assert "15%" in g.share_overflow_reason


def test_the_intended_split_reports_NO_overflow():
    """Two bots at 5% under a 10% cap. It must not read as a near miss on the page either."""
    g = ba.group_by_account(
        {"a": _cfg("a", cap=10.0, risk=5.0), "b": _cfg("b", magic=2, cap=10.0, risk=5.0)}
    )[0]
    assert g.share_overflow_reason is None


def test_no_overflow_verdict_is_claimed_when_the_caps_DISAGREE():
    """There is no agreed ceiling to check against, and inventing one is what `risk_cap_pct`
    already refuses to do. Same guard as `cap_takes_turns`."""
    g = ba.group_by_account(
        {"a": _cfg("a", cap=10.0, risk=10.0), "b": _cfg("b", magic=2, cap=50.0, risk=10.0)}
    )[0]
    assert g.risk_cap_pct is None
    assert g.share_overflow_reason is None


# ── the per-trade risk has ONE definition ────────────────────────────────────
def test_the_risk_read_is_the_SAME_one_the_grouping_uses():
    """🔴 A caller assembling a hypothetical account (a bot about to be MOVED) must read this
    number the way every other bot's is read. Two ways is two answers, and the hypothetical is
    the one that drifts. RED if the grouping stops going through `risk_pct_of`."""
    cfg = _cfg("a", risk=7.5)
    assert ba.risk_pct_of(cfg) == 7.5
    assert ba.group_by_account({"a": cfg})[0].bots[0].risk_pct == 7.5


def test_a_config_stating_no_risk_reads_as_UNKNOWN_not_zero():
    assert ba.risk_pct_of({"strategy_params": {}}) is None
    assert ba.risk_pct_of({}) is None


# ── the three write points that can create an over-subscribed account ─────────
#
# The rule is only real where it is ENFORCED. Each of these is a different way to arrive at the
# same broken state: lower the ceiling under the shares, add a bot, or raise one bot's share.
def _group(*bots, cap=10.0, account=700152905):
    g = ba.AccountGroup(account=account, server="PUPrime-Demo", kind="account")
    g.bots = list(bots)
    g.risk_cap_pct = cap
    g.cap_agrees = True
    return g


def test_LOWERING_the_cap_under_the_existing_shares_is_refused(client, monkeypatch):
    """The shares do not move, so the ceiling coming down under them is the same broken state
    arrived at from the other side."""
    from routers import bots as bots_router

    monkeypatch.setattr(
        bots_router,
        "_account_groups",
        lambda: [_group(_bot("a", 5.0), _bot("b", 5.0), cap=10.0)],
    )
    r = client.patch("/bots/accounts/700152905/risk-cap", json={"risk_cap_pct": 8.0})
    assert r.status_code == 409
    assert "add up to" in r.json()["detail"]


def test_a_cap_the_shares_FIT_is_not_refused_for_overflow(client, monkeypatch):
    """The control. RED if the check fires on a configuration that is exactly right — which is
    the failure mode that makes a guard get switched off."""
    from routers import bots as bots_router

    monkeypatch.setattr(
        bots_router,
        "_account_groups",
        lambda: [_group(_bot("a", 5.0), _bot("b", 5.0), cap=8.0)],
    )
    r = client.patch("/bots/accounts/700152905/risk-cap", json={"risk_cap_pct": 10.0})
    assert "add up to" not in str(r.json().get("detail", ""))


def test_ADDING_a_bot_that_would_overflow_the_account_is_refused(client, monkeypatch):
    """The case Aaron asked about: a third bot onto an account whose budget is fully allocated.
    Refused at the MOVE, where it can still be reasoned about, rather than at 3am by whichever
    bot happens to ask last."""
    from routers import bots as bots_router

    monkeypatch.setattr(bots_router, "_bot_is_running", lambda key: False)
    # The password pre-check SSHes to the box and runs BEFORE this one; the VPS interlock
    # refuses it, which is the interlock working rather than anything about this rule.
    monkeypatch.setattr(bots_router, "_accounts_with_a_password", lambda: {700152905})
    monkeypatch.setattr(
        bots_router,
        "_account_groups",
        lambda: [_group(_bot("a", 5.0), _bot("b", 5.0), cap=10.0)],
    )
    r = client.patch("/bots/b_leg_demo/account", json={"account": 700152905, "deploy": False})
    assert r.status_code == 409
    assert "add up to" in r.json()["detail"]


def test_RAISING_a_bots_own_risk_past_the_room_left_is_refused(client, monkeypatch):
    """The third way in, and the easiest to reach — it is one number in a box on the Configure
    tab, and it is the one field that reaches a RUNNING bot."""
    from routers import bots as bots_router

    monkeypatch.setattr(
        bots_router,
        "_account_groups",
        lambda: [_group(_bot("sos_fade_demo", 5.0), _bot("b", 5.0), cap=10.0)],
    )
    r = client.patch(
        "/bots/sos_fade_demo/runtime",
        json={"values": {"exec_risk_pct": 9.0}, "deploy": False},
    )
    assert r.status_code == 409
    assert "add up to" in r.json()["detail"]


def test_LOWERING_a_bots_own_risk_is_always_allowed(client, monkeypatch):
    """The control for the case above — freeing room can never over-subscribe an account, and a
    guard that blocked it would make an over-subscribed account unfixable."""
    from routers import bots as bots_router

    monkeypatch.setattr(
        bots_router,
        "_account_groups",
        lambda: [_group(_bot("sos_fade_demo", 5.0), _bot("b", 5.0), cap=10.0)],
    )
    # Stopped before the write: this test is about the CHECK not firing, and letting it
    # through would edit the LIVE bot's own config on the machine running the suite.
    written = []
    monkeypatch.setattr(
        bots_router, "_write_instance_config", lambda key, data: written.append(key)
    )
    r = client.patch(
        "/bots/sos_fade_demo/runtime",
        json={"values": {"exec_risk_pct": 2.0}, "deploy": False},
    )
    assert written == ["sos_fade_demo"], "it should have reached the write"
    assert "add up to" not in str(r.json().get("detail", ""))


# ── a param write must fit the RECEIVING strategy (2026-09-04) ────────────────
#
# 🔴 `runner._build_strategy` refuses to start on any `strategy_params` key the strategy's config
# class does not declare — "they would be ignored, so the bot would trade settings you did not
# choose" — and that refusal is right. `assign_plan` wrote the account's cost profile into every
# bot it moved without asking whether that bot's strategy has the field. MEASURED: assigning
# `extreme_leg_demo` to account 700152905 produced a bot that connected to the broker and refused
# to start on every attempt, while the page reported the move as done.
#
# THE SHAPE: a write correct for every EXISTING receiver is not a correct write. Both strategies
# that had ever been assigned declare that field, so this had a 100% pass rate right up to the
# first one that did not.
#
# Watched RED by mutation. THE MAP WAS RUN, and the second entry was written from inspection as
# "2 red" and is actually 5 — inverting the filter breaks the cases that assert a param IS carried
# as well as the ones that assert one is dropped, which reading the case names does not show:
#     write every param regardless of `declared_params`  -> 3 red
#     invert the filter (drop what IS declared)          -> 5 red
#     treat `None` (could not ask) as "declares nothing" -> 2 red
#     skip silently, with no note                        -> 2 red
# The restore was re-run after every mutation and gives 66 green, so a mutation that failed to
# apply cannot be misread here as one the suite survived.


class _Reg:
    """The registry fields `assign_plan` reads. A stub rather than a `RegisteredAccount` so a new
    required field on that dataclass cannot silently change what these cases are testing."""

    def __init__(self, profile="puprime_ecn", suffix=".p"):
        self.server = "PUPrime-Demo"
        self.mt5_path = r"C:\MT5_FFT\terminal64.exe"
        self.account_profile = profile
        self.symbol_suffix = suffix
        self.assignable = True


def _assign(declared, *, symbol="XAUUSD.s"):
    target = ba.group_by_account({"a": _cfg("a", cap=10.0)})[0]
    return ba.assign_plan(
        "newbot",
        700107749,
        target=target,
        registered=_Reg(),
        current_symbol=symbol,
        declared_params=declared,
    )


def test_a_param_the_strategy_DECLARES_is_written():
    """The working case, and it is why the fix is a filter rather than a removal: two of the three
    live strategies do declare the cost profile and must keep getting it."""
    plan = _assign({"account_profile", "symbol"})
    assert plan.param_fields["account_profile"] == "puprime_ecn"


def test_a_param_the_strategy_does_NOT_declare_is_not_written():
    """🔴 The defect. MUTATION: write every param regardless and this goes red — which is exactly
    the config that stopped the bot dead."""
    plan = _assign({"symbol"})
    assert "account_profile" not in plan.param_fields


def test_the_skipped_param_is_NAMED_rather_than_dropped_in_silence():
    """A move that quietly leaves a cost profile describing the account the bot has LEFT is the
    2026-08-12 defect. Skipping is the right action; skipping without saying so is not."""
    plan = _assign({"symbol"})
    assert any("account_profile" in n for n in plan.notes)


def test_the_filter_covers_EVERY_param_write_not_just_the_cost_profile():
    """It runs once at the end of the plan, so a param this function learns to carry tomorrow is
    covered without anyone remembering the rule. MUTATION: filter at the profile's own write site
    and this goes red, because the symbol survives."""
    plan = _assign({"account_profile"})
    assert "symbol" not in plan.param_fields
    assert any("symbol" in n for n in plan.notes)


def test_an_UNREADABLE_strategy_writes_anyway_and_says_it_could_not_check():
    """🔴 Deliberately NOT a refusal, and the one place here that does not follow *refuse when you
    cannot ask*. Of the two wrong answers, writing gives a bot that refuses to start and names the
    field; skipping gives a bot that starts and trades an account with another broker's costs
    recorded against it. The loud one is recoverable in a minute.

    MUTATION: treat `None` as "declares nothing" and this goes red — every param disappears."""
    plan = _assign(None)
    assert plan.param_fields["account_profile"] == "puprime_ecn"
    assert any("unchecked" in n for n in plan.notes)


def test_nothing_is_said_when_every_param_fits():
    """A note per assignment that always fires is a note nobody reads."""
    plan = _assign({"account_profile", "symbol"})
    assert not any("account_profile" in n for n in plan.notes)
