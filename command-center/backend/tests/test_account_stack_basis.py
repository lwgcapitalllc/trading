"""`services/account_stack_basis.py` — what an account's bots run, as a stack to backtest.

⚠ **A fail-watch against HEAD is VACUOUS** — the module did not exist, so every test would go red
on an import error, which proves the import and nothing else. Non-vacuity is by MUTATION, each
named in the test it turns red.
"""

from __future__ import annotations

import pytest
from services.account_stack_basis import BasisStrategy, plan_account_stack

_ACCOUNT = 700152905

_SOS = BasisStrategy(
    id="sos_fade",
    name="SOS Fade",
    runner="python",
    default_params={"exec_risk_pct": 10.0, "exec_secondary": False, "exec_tp1_pct": 30.0},
)
_XLEG = BasisStrategy(
    id="extreme_leg",
    name="Extreme Leg",
    runner="python",
    default_params={"exec_risk_pct": 5.0, "xleg_lookback": 20},
)


def _bot(
    package, *, display, account=_ACCOUNT, timeframe="M15", symbol="XAUUSD.p", cap=10.0, **pins
):
    return {
        "display_name": display,
        "strategy_package": package,
        "account": account,
        "account_risk_cap_pct": cap,
        "symbol": symbol,
        "timeframe": timeframe,
        "strategy_params": pins,
    }


def _configs(**overrides):
    base = {
        "sos_fade_demo": _bot(
            "sos_fade", display="SOS Fade", exec_risk_pct=5.0, exec_secondary=True
        ),
        "extreme_leg_demo": _bot(
            "extreme_leg", display="Extreme Leg", timeframe="M5", exec_risk_pct=5.0
        ),
    }
    base.update(overrides)
    return base


def _declared(strategy):
    return set(strategy.default_params)


def _plan(configs=None, *, strategies=None, declared=None, profile="puprime_ecn", readable=True):
    configs = _configs() if configs is None else configs
    strategies = {"sos_fade": _SOS, "extreme_leg": _XLEG} if strategies is None else strategies
    if declared is None:
        declared = {pkg: (_declared(s) if s else None) for pkg, s in strategies.items()}
    return plan_account_stack(
        account=_ACCOUNT,
        configs=configs,
        displays={},
        strategies=strategies,
        declared=declared,
        account_profile=profile,
        registry_readable=readable,
    )


# ── the case this exists for ─────────────────────────────────────────────────────────────────


def test_the_bots_OWN_risk_wins_over_the_strategys_default():
    """The whole reason: SOS Fade's lab default is 10% and the bot runs 5%. Pre-filling defaults
    asked for 10 + 5 = 15% under a 10% cap, which the stack builder refuses.

    ⚠ Watched RED by merging the other way round (defaults laid over the pins).
    """
    plan = _plan()
    assert plan.blocked is None
    assert plan.params_by_strategy["sos_fade"]["exec_risk_pct"] == 5.0
    assert plan.params_by_strategy["sos_fade"]["exec_secondary"] is True


def test_each_leg_is_sent_COMPLETE_defaults_filled_under_the_pins():
    """A stack's per-leg settings REPLACE that leg's defaults, so a leg carrying only the bot's
    pins would drop every setting the bot happens not to state.

    ⚠ Watched RED by sending the pins alone.
    """
    plan = _plan()
    assert plan.params_by_strategy["sos_fade"]["exec_tp1_pct"] == 30.0  # not pinned → default
    assert plan.params_by_strategy["extreme_leg"]["xleg_lookback"] == 20
    sos = next(leg for leg in plan.legs if leg.strategy_id == "sos_fade")
    assert (sos.from_bot, sos.from_defaults) == (2, 1)
    assert any("SOS Fade's settings are not stated by the bot" in n for n in plan.notes)


def test_the_rest_of_the_stack_comes_from_the_account():
    """Chart per bot, one instrument, the account's ceiling and its cost profile."""
    plan = _plan()
    assert plan.strategy_ids == ["extreme_leg", "sos_fade"]
    assert plan.bar_values_by_strategy == {"extreme_leg": 5, "sos_fade": 15}
    assert plan.instrument == "XAUUSD.p"
    assert plan.risk_cap_pct == 10.0
    assert plan.broker_profile == "puprime_ecn"
    assert {leg.risk_pct for leg in plan.legs} == {5.0}


def test_bots_on_OTHER_accounts_are_not_part_of_it():
    plan = _plan(
        _configs(b_leg_demo=_bot("b_leg", display="B-LEG", account=123, exec_risk_pct=5.0))
    )
    assert plan.blocked is None
    assert "b_leg" not in plan.strategy_ids


# ── what is left out, and said ───────────────────────────────────────────────────────────────


def test_a_setting_the_strategy_no_longer_has_is_LEFT_OUT_and_counted():
    """Handed to the run it could not be read; dropped in silence the reader would think the
    bot's settings arrived whole.

    ⚠ Watched RED by keeping every pin regardless of what the strategy declares.
    """
    configs = _configs(
        sos_fade_demo=_bot("sos_fade", display="SOS Fade", exec_risk_pct=5.0, gone_setting=1)
    )
    plan = _plan(configs)
    assert "gone_setting" not in plan.params_by_strategy["sos_fade"]
    assert any("SOS Fade states 1 setting its strategy no longer has" in n for n in plan.notes)


def test_prose_keys_are_not_settings_and_are_not_counted_as_dropped():
    """An `_`-prefixed key is an explanation somebody left in the file."""
    configs = _configs(
        sos_fade_demo=_bot("sos_fade", display="SOS Fade", exec_risk_pct=5.0, _exec_risk_pct="why")
    )
    plan = _plan(configs)
    assert "_exec_risk_pct" not in plan.params_by_strategy["sos_fade"]
    assert not any("no longer has" in n for n in plan.notes)


def test_an_unreadable_chart_falls_back_to_the_strategys_own_and_says_so():
    configs = _configs(
        extreme_leg_demo=_bot("extreme_leg", display="Extreme Leg", timeframe="", exec_risk_pct=5.0)
    )
    plan = _plan(configs)
    assert "extreme_leg" not in plan.bar_values_by_strategy
    assert any("Extreme Leg's chart timeframe could not be read" in n for n in plan.notes)


def test_no_recorded_profile_and_an_unreadable_account_list_are_DIFFERENT_notes():
    """Rule 1: nothing recorded and could-not-ask are two answers."""
    none_recorded = _plan(profile=None)
    unreadable = _plan(profile=None, readable=False)
    assert none_recorded.broker_profile is None and unreadable.broker_profile is None
    assert any("No cost profile is recorded" in n for n in none_recorded.notes)
    assert any("account list could not be read" in n for n in unreadable.notes)
    assert not any("No cost profile is recorded" in n for n in unreadable.notes)


# ── the refusals ─────────────────────────────────────────────────────────────────────────────


def test_an_UNREADABLE_config_anywhere_refuses_because_it_might_be_on_this_account():
    """An unreadable bot has no account we can see. Backtesting without it is an account quietly
    one bot short, which reads exactly like a complete one.

    ⚠ Watched RED by skipping the unreadable-bucket check.
    """
    plan = _plan(_configs(b_leg_demo=None))
    assert plan.blocked and "b_leg_demo" in plan.blocked
    assert plan.strategy_ids == [] and plan.params_by_strategy == {}


@pytest.mark.parametrize(
    "configs, words",
    [
        ({}, "No bot trades account"),
        (
            {"sos_fade_demo": _bot("sos_fade", display="SOS Fade", exec_risk_pct=5.0)},
            "Only SOS Fade",
        ),
    ],
)
def test_fewer_than_two_bots_is_not_a_stack(configs, words):
    plan = _plan(configs)
    assert plan.blocked and words in plan.blocked


def test_bots_that_disagree_on_the_ceiling_refuse():
    """There is no single budget to backtest under — and those bots refuse to start live too."""
    configs = _configs(
        extreme_leg_demo=_bot("extreme_leg", display="Extreme Leg", cap=8.0, exec_risk_pct=5.0)
    )
    plan = _plan(configs)
    assert plan.blocked and "different risk ceilings" in plan.blocked


@pytest.mark.parametrize(
    "strategies, words",
    [
        ({"sos_fade": _SOS, "extreme_leg": None}, "a strategy the lab does not have"),
        (
            {"sos_fade": _SOS, "extreme_leg": BasisStrategy("extreme_leg", "X", "mt5", {})},
            "Python only",
        ),
        (
            {
                "sos_fade": _SOS,
                "extreme_leg": BasisStrategy(
                    "extreme_leg", "X", "python", {}, requires_source=True
                ),
            },
            "another strategy's losses",
        ),
    ],
)
def test_a_leg_the_lab_cannot_run_refuses_and_names_the_bot(strategies, words):
    plan = _plan(strategies=strategies)
    assert plan.blocked and words in plan.blocked and "Extreme Leg" in plan.blocked


def test_a_refusal_after_a_leg_was_built_carries_NO_half_built_stack():
    """`extreme_leg_demo` sorts first and is built; `sos_fade_demo` is then refused. A caller
    reading the legs off a refusal would pre-fill a form the refusal said could not be built.

    ⚠ Watched RED by returning the partly built plan with `blocked` set.
    """
    plan = _plan(strategies={"sos_fade": None, "extreme_leg": _XLEG})
    assert plan.blocked
    assert plan.strategy_ids == [] and plan.legs == [] and plan.params_by_strategy == {}


def test_two_bots_on_ONE_strategy_refuse():
    configs = _configs(extreme_leg_demo=_bot("sos_fade", display="SOS Fade Two", exec_risk_pct=5.0))
    plan = _plan(configs)
    assert plan.blocked and "run the same strategy" in plan.blocked


def test_two_instruments_refuse_and_a_missing_one_is_named():
    two = _plan(
        _configs(
            extreme_leg_demo=_bot(
                "extreme_leg", display="Extreme Leg", symbol="EURUSD.p", exec_risk_pct=5.0
            )
        )
    )
    assert two.blocked and "EURUSD.p" in two.blocked and "XAUUSD.p" in two.blocked
    missing = _plan(
        _configs(extreme_leg_demo=_bot("extreme_leg", display="Extreme Leg", symbol=""))
    )
    assert missing.blocked and "Extreme Leg names no instrument" in missing.blocked


# ── the endpoint ─────────────────────────────────────────────────────────────────────────────


def test_the_endpoint_serves_the_plan_and_a_REFUSAL_is_a_200(client, monkeypatch):
    """The route reads, the planner decides. A refusal is a real answer to a legitimate question,
    so it is a 200 carrying the sentence, never an error status that nothing renders.

    ⚠ Watched RED by dropping the leg list from the response.
    """
    from routers import bots
    from services import bot_account_registry, lab_db

    rows = {
        "sos_fade": {
            "id": "sos_fade",
            "name": "SOS Fade",
            "runner": "python",
            "default_params": dict(_SOS.default_params),
        },
        "extreme_leg": {
            "id": "extreme_leg",
            "name": "Extreme Leg",
            "runner": "python",
            "default_params": dict(_XLEG.default_params),
        },
    }
    monkeypatch.setattr(bots, "_all_instance_configs", lambda: _configs())
    monkeypatch.setattr(lab_db, "get_strategy", lambda sid: rows.get(sid))
    monkeypatch.setattr(
        bots, "_declared_strategy_params", lambda pkg: set(rows[pkg]["default_params"])
    )

    class _Reg:
        account_profile = "puprime_ecn"

    monkeypatch.setattr(bot_account_registry, "account_by_number", lambda path, n: _Reg())

    r = client.get(f"/bots/accounts/{_ACCOUNT}/stack-basis")
    assert r.status_code == 200
    body = r.json()
    assert body["blocked"] is None
    assert body["params_by_strategy"]["sos_fade"]["exec_risk_pct"] == 5.0
    assert [leg["bot"] for leg in body["legs"]] == ["extreme_leg_demo", "sos_fade_demo"]

    refused = client.get("/bots/accounts/123/stack-basis")
    assert refused.status_code == 200
    assert refused.json()["blocked"].startswith("No bot trades account 123")
