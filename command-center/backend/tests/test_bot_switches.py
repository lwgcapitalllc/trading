"""The two-state runtime settings — the stop-protection switch on the Bots page.

🔴 **These exist because a switch is a TYPED write to a live bot's config, and the type is not
cosmetic.** `runner._build_strategy` hands `strategy_params` straight to the strategy's config
class, so a bool written where the strategy declares a float — or the reverse — is a bot that
refuses to start, on a path nobody exercises until they flip the switch.

⚠ Python's `True == 1` is the specific trap: a check written as `value in (spec["off"],
spec["on"])` accepts `1` for a bool switch and `True` for a numeric one, and both write the wrong
thing. Every check below was watched RED by the mutation named in its docstring.
"""

import pytest
from services import bot_params


def test_both_switches_are_in_the_editable_set():
    """MUTATION: drop either name from RUNTIME_EDITABLE → red here, and the page stops offering it."""
    assert "exec_be_arm_r" in bot_params.RUNTIME_EDITABLE
    assert "use_breakeven" in bot_params.RUNTIME_EDITABLE
    assert set(bot_params.RUNTIME_SWITCHES) <= bot_params.RUNTIME_EDITABLE


def test_every_switch_carries_the_measured_sentence():
    """A switch with no number beside it reads as prudent and is a trap — see BotSwitchEditor.

    MUTATION: blank a `warn` → red. The page refuses to draw a switch without one, so a silent
    blank would remove the control rather than the warning, which is worse than either.
    """
    for name, spec in bot_params.RUNTIME_SWITCHES.items():
        assert spec["warn"].strip(), name
        assert spec["on_label"].strip(), name
        assert type(spec["off"]) is type(spec["on"]), name
        assert spec["off"] != spec["on"], name


def test_a_switch_keeps_its_declared_TYPE_and_a_bool_is_not_one():
    """MUTATION: replace the `type(value) is type(want)` guard with `value in (off, on)` → red.

    `True == 1` and `False == 0`, so the loose check writes 1.0 into the extreme-leg bot's
    boolean and `True` into the R-multiple the other two declare as a float.
    """
    assert bot_params.validate_runtime({"use_breakeven": True}) == {"use_breakeven": True}
    assert bot_params.validate_runtime({"exec_be_arm_r": 1.0}) == {"exec_be_arm_r": 1.0}

    with pytest.raises(bot_params.RuntimeUpdateError):
        bot_params.validate_runtime({"use_breakeven": 1})
    with pytest.raises(bot_params.RuntimeUpdateError):
        bot_params.validate_runtime({"use_breakeven": 1.0})
    with pytest.raises(bot_params.RuntimeUpdateError):
        bot_params.validate_runtime({"exec_be_arm_r": True})


def test_a_switch_REFUSES_any_value_that_is_not_one_of_its_two_states():
    """It is a switch, not the field's range — 2R is unmeasured and has no way in from here.

    MUTATION: fall through to the numeric branch for a switch → 2.0 is accepted, red.
    """
    for bad in (0, 2.0, -1.5, "on"):
        with pytest.raises(bot_params.RuntimeUpdateError):
            bot_params.validate_runtime({"exec_be_arm_r": bad})


def test_the_risk_share_is_still_a_NUMBER_and_not_a_switch():
    """The switch branch must not capture the one setting that was always editable.

    MUTATION: add exec_risk_pct to RUNTIME_SWITCHES → red, 4.25 stops being accepted.
    """
    assert "exec_risk_pct" not in bot_params.RUNTIME_SWITCHES
    assert bot_params.validate_runtime({"exec_risk_pct": 4.25}) == {"exec_risk_pct": 4.25}


def test_the_view_hands_the_page_the_switch_and_marks_it_editable():
    """MUTATION: stop putting `switch` on the row → red, and the page draws a decimal box."""
    view = bot_params.build_view(
        "sos_fade_demo",
        {"strategy_params": {"exec_risk_pct": 5.0, "exec_be_arm_r": -1.0}},
    )
    rows = {r["name"]: r for r in view["runtime"]}
    assert rows["exec_be_arm_r"]["switch"]["on"] == 1.0
    assert rows["exec_be_arm_r"]["editable"] is True
    assert rows["exec_risk_pct"]["switch"] is None


def test_a_setting_NOT_on_this_bot_is_simply_absent_rather_than_invented():
    """The editable set is a FILTER, not a requirement — rule 1's shape at the config level.

    The extreme-leg bot has no R-multiple arm and the other two have no boolean. Neither may be
    conjured onto a bot whose strategy does not declare it: `runner._build_strategy` refuses any
    key the config class does not have, so an invented row would stop the bot dead.
    MUTATION: seed every editable name into the view → red, the row appears on a bot without it.
    """
    view = bot_params.build_view(
        "extreme_leg_demo",
        {"strategy_params": {"exec_risk_pct": 5.0, "use_breakeven": False}},
    )
    names = {r["name"] for r in view["runtime"]}
    assert names == {"exec_risk_pct", "use_breakeven"}
