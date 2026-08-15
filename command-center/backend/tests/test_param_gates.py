"""`disable_if` / `custom_from` — the second gate a param can be dead behind.

🔴 THE SUBJECT: `exec_sl_deep` on `mpc_sos_fade` cannot change anything when `exec_sl_level` is
already `1.0` — both of its states place the stop in the same spot. The Pine has greyed it out
since it was written (`indicators/strategies/mpc_strategy.pine:116`, `active = execSlLevel != "1.0"`)
and the Python UI never had the mechanism, so the lab offered a control that did nothing.

Two things had to be true for that to be more than cosmetic:

  1. `strategy_scanner._PARAM_META_KEYS` is a WHITELIST — a meta key missing from it is dropped in
     silence and the editor behaves as though nobody wrote it. The three new keys are checked
     against the REAL meta.json rather than a fixture, because the fixture is the half that cannot
     go stale on its own.
  2. Sensitivity must not perturb an inert param. Shifting one books a guaranteed 0% change, which
     the page reports as "tested, rock solid" for a setting the strategy could not have read —
     `param_is_reachable`'s own docstring, arriving through the other gate.

⚠ A fail-watch against HEAD is VACUOUS for most of this: `disable_if` did not exist, so the tests
fail on a missing key rather than on the behaviour. Non-vacuity is by MUTATION, and each test that
needed one NAMES it. Two tests CAN go red at HEAD and say so.
"""

import json
from pathlib import Path

import config as cfg
import pytest
from services import strategy_scanner
from services.stress_tester import param_is_reachable, perturbable_params

META = cfg.MONOREPO_ROOT / "strategies" / "python" / "mpc_sos_fade" / "mpc_sos_fade.meta.json"


def _params():
    return json.loads(Path(META).read_text())["params"]


def _param(name):
    for p in _params():
        if p["name"] == name:
            return p
    raise AssertionError(f"{name} is not in {META.name}")


# ── the whitelist ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("key", ["disable_if", "disable_note", "custom_from"])
def test_the_scanner_carries_the_key_rather_than_dropping_it(key):
    """MUTATION: remove the key from `_PARAM_META_KEYS` and this goes red.

    Without it the meta states a rule, the scan reports success, and the editor never sees it —
    the exact silent shape rule 7 is about.
    """
    assert key in strategy_scanner._PARAM_META_KEYS


def test_the_live_meta_actually_uses_them_so_the_whitelist_test_is_not_theoretical():
    """The keys above are only worth whitelisting if something writes them. It could go red at
    HEAD — the meta did not carry them — and it is the half that catches a future edit deleting
    the rule from the strategy rather than from the scanner."""
    deep = _param("exec_sl_deep")
    assert deep["disable_if"] == {"exec_sl_level": "1.0"}
    assert deep["disable_note"]
    assert _param("exec_sl_level")["custom_from"] == "exec_sl_custom"


def test_the_toggles_labels_read_the_dropdown_rather_than_restating_it():
    """`Stop 0.886` typed as a literal is a second copy of another param's value, which is this
    repo's most-repeated defect. Could go red at HEAD (the labels were static prose)."""
    opts = _param("exec_sl_deep")["options"]
    assert "{exec_sl_level}" in opts["off"]
    # The ON side is genuinely constant — the deep rule always anchors at 1.0.
    assert "{" not in opts["on"]


# ── the sensitivity gate ──────────────────────────────────────────────────────

SCHEMA = [
    {"name": "mode", "type": "string", "custom_from": "mode_custom"},
    {"name": "mode_custom", "type": "float", "show_if": {"mode": "Custom"}},
    {"name": "knob", "type": "float", "disable_if": {"mode": "1.0"}},
    {"name": "plain", "type": "float"},
]


def test_a_param_its_own_disable_if_kills_is_not_perturbed():
    """MUTATION: drop the `disable_if` clause from `param_is_reachable` and this goes red.

    The value really does change and the outcome cannot, so the value-equality dedupe downstream
    cannot catch it — it books 0% and reads as a robustness result.
    """
    assert param_is_reachable(SCHEMA[2], {"mode": "1.0"}, SCHEMA) is False
    assert param_is_reachable(SCHEMA[2], {"mode": "0.886"}, SCHEMA) is True


def test_custom_equal_to_the_dead_value_gates_the_SAME_way_as_the_dropdown():
    """🔴 The case the editor and the lab could silently disagree on.

    `mode = Custom` with `mode_custom = 1.0` is the same configuration as `mode = 1.0`, so the
    same param is dead. MUTATION: make `_reader_for` return `raw(name)` unconditionally and this
    goes red while everything else stays green.
    """
    assert param_is_reachable(SCHEMA[2], {"mode": "Custom", "mode_custom": 1.0}, SCHEMA) is False
    # ...and a Custom value that is NOT the dead one leaves it alive.
    assert param_is_reachable(SCHEMA[2], {"mode": "Custom", "mode_custom": 0.886}, SCHEMA) is True


def test_the_sibling_is_only_consulted_while_its_own_show_if_holds():
    """`mode_custom` carries a stale 1.0 while the dropdown reads 0.886 — the sibling is hidden,
    so its value is not in force and the knob is live. MUTATION: drop the `visible(sib)` check and
    this goes red: a leftover in an invisible box would kill a working control."""
    assert param_is_reachable(SCHEMA[2], {"mode": "0.886", "mode_custom": 1.0}, SCHEMA) is True


def test_a_param_with_no_gate_at_all_is_always_reachable():
    """The guard against fixing this in the dangerous direction — `_cond_holds(None)` must be
    False (nothing to disable), not True. MUTATION: return True for an empty cond and every
    ungated param in the lab stops being perturbed, silently."""
    assert param_is_reachable(SCHEMA[3], {"mode": "1.0"}, SCHEMA) is True


def test_a_numeric_value_matches_a_numeric_condition_whatever_it_LOOKS_like():
    """🔴 The bug the editor shipped and this side did not, which is worse than either alone.

    A fib level is the STRING `"1.0"` in a dropdown and the NUMBER `1.0` in the Custom box. JS's
    `String(1.0)` is `"1"`, so the editor's stringified compare said Custom = 1.0 is not 1.0 and
    left the toggle live in exactly the configuration it exists to be dead in. Python's `str(1.0)`
    is `"1.0"`, so this side was accidentally right — two evaluators of one rule disagreeing in
    silence. Both compare NUMBERS as numbers now.

    MUTATION: drop the numeric branch from `_same_value` and the `1` case goes red.
    """
    assert param_is_reachable(SCHEMA[2], {"mode": "Custom", "mode_custom": 1}, SCHEMA) is False
    assert param_is_reachable(SCHEMA[2], {"mode": "Custom", "mode_custom": "1"}, SCHEMA) is False
    assert param_is_reachable(SCHEMA[2], {"mode": "Custom", "mode_custom": 1.00}, SCHEMA) is False


def test_a_BOOLEAN_is_never_compared_as_a_number():
    """`float(False)` is 0.0, so a numeric param sitting at 0 would satisfy a `{flag: false}` gate
    and a whole unrelated row would vanish. MUTATION: drop the bool guard from `_numeric` and the
    second assertion goes red."""
    p = {"name": "x", "type": "float", "disable_if": {"flag": False}}
    schema = [{"name": "flag", "type": "bool"}, p]
    assert param_is_reachable(p, {"flag": False}, schema) is False  # the real match
    assert param_is_reachable(p, {"flag": 0}, schema) is True  # a number is not the bool


def test_perturbable_params_passes_the_schema_through():
    """`param_is_reachable` cannot resolve `custom_from` without the schema, and the default is
    None — so a caller that forgets it gets the CHART-only answer, which looks correct and is
    simply blind to this gate. MUTATION: drop the `schema` argument at the call site in
    `perturbable_params` and this goes red."""
    strategy = {"param_schema": SCHEMA}
    base = {"mode": "Custom", "mode_custom": 1.0, "knob": 5.0, "plain": 1.0}
    names = [p["name"] for p in perturbable_params(strategy, base)]
    assert "knob" not in names
    assert "plain" in names


# ── settled params: off the screen, still in the strategy ─────────────────────


def test_the_scanner_carries_hidden():
    """MUTATION: remove `hidden` from `_PARAM_META_KEYS` and this goes red — the meta would say
    "settled", the scan would report success, and every row would render anyway."""
    assert "hidden" in strategy_scanner._PARAM_META_KEYS


def test_a_settled_param_is_still_a_REAL_field_with_a_default():
    """🔴 The whole contract: `hidden` takes a param off the EDITOR and changes nothing about the
    strategy. Aaron's ask was explicitly "don't delete the configurations… you might be able to
    toggle it back on super easy" — so a hidden name that no longer exists in the config would be
    the one outcome that is not allowed.

    This reads the real config dataclass, so deleting a field while leaving it marked hidden fails
    here rather than at run time. Could go red at HEAD only in the sense that nothing was hidden
    yet; its value is FORWARD — it is the guard on the next person's tidy-up.
    """
    from services import strategy_import

    strategy_import.purge_strategy_modules()
    pkg = strategy_import.import_strategy_package("mpc_sos_fade", cfg.MONOREPO_ROOT)
    cfg_cls = pkg.LAB_STRATEGY["config"]
    fields = {f for f in getattr(cfg_cls, "__dataclass_fields__", {})}
    hidden = [p["name"] for p in _params() if p.get("hidden")]
    assert hidden, "nothing is marked settled — this test would be vacuous"
    missing = [n for n in hidden if n not in fields]
    assert not missing, f"settled but no longer in the config: {missing}"


def test_the_divergence_VETO_is_not_hidden_even_though_the_ARM_is():
    """⚠ The correction that matters. `exec_arm_div` is settled (sweeps only), but `div_veto` and
    `exec_respect_veto` are ON and still refusing setups — hiding those would take a LIVE rule off
    the screen. Settled means the question is closed, never that the behaviour stopped."""
    by = {p["name"]: p for p in _params()}
    assert by["exec_arm_div"].get("hidden") is True
    assert not by["div_veto"].get("hidden")
    assert not by["exec_respect_veto"].get("hidden")
    assert not by["show_div"].get("hidden")


SETTLED_SCHEMA = [
    {"name": "quiet", "type": "float", "hidden": True, "default": 30.0},
    {"name": "loud", "type": "float", "default": 30.0},
]


def test_a_SETTLED_param_is_not_perturbed_by_sensitivity():
    """🔴 The third gate. Unlike `show_if` / `disable_if`, shifting a settled param is NOT a no-op
    — the strategy really does read it and the result really does move. That is exactly why it has
    to be excluded: sensitivity would rank it, and the reader would go looking for a control that
    no page renders. A ranking that points at nothing is worse than a shorter ranking.

    MUTATION: drop the `_is_settled` call from `param_is_reachable` and this goes red.
    """
    base = {"quiet": 30.0, "loud": 30.0}
    names = [p["name"] for p in perturbable_params({"param_schema": SETTLED_SCHEMA}, base)]
    assert names == ["loud"]


def test_a_settled_param_MOVED_off_its_default_is_perturbed_again():
    """⚠ The gate is `ParamEditor.settled` (hidden AND on its default), never `p.hidden` alone.

    Moved, the row is back on screen — so it is back in the ranking too, or sensitivity would go
    silent on the one value this run actually changed. MUTATION: gate on `p.get("hidden")` alone
    and this goes red while the test above stays green.
    """
    names = [
        p["name"]
        for p in perturbable_params({"param_schema": SETTLED_SCHEMA}, {"quiet": 45.0, "loud": 30.0})
    ]
    assert "quiet" in names


def test_a_param_with_no_default_in_the_schema_is_never_called_settled():
    """`hidden` with no `default` cannot be compared against anything, and guessing "settled"
    there would drop a live param on a technicality. MUTATION: return True when `default` is
    missing and this goes red."""
    schema = [{"name": "quiet", "type": "float", "hidden": True}]
    assert param_is_reachable(schema[0], {"quiet": 30.0}, schema) is True


# ── the bar for hiding: a SWEEP, not an untouched value ───────────────────────


def test_the_seven_proven_settled_params_are_hidden():
    """Each of these was tested against alternatives and lost or tied. The evidence is in
    `mpc_sos_fade_optimization.md`, named per param in this package's CLAUDE.md — Run 2's
    525-combo exit grid, Run 5/6 (`exec_close_opp_sos` at exactly 0 effect, twice), Run 17 (the
    breakeven buffer), Run 12 (both relax routes)."""
    by = {p["name"]: p for p in _params()}
    for n in (
        "exec_close_opp_sos",
        "exec_tp2_stop_mode",
        "exec_struct_trail_buf_tk",
        "exec_trail_step",
        "exec_be_buf_tk",
        "exec_fvg_deep_only",
        "exec_no_late_day",
    ):
        assert by[n].get("hidden") is True, f"{n} has a sweep behind it and should be settled"


def test_a_param_that_was_never_SWEPT_is_not_hidden_on_the_strength_of_never_moving():
    """🔴 The criterion, pinned. "Took one value across every stored run" is NOT evidence — it is
    the absence of the experiment. Aaron's rule (2026-08-15): hide what a backtest PROVED, keep
    what nobody has asked yet.

    `exec_sl_buf_tk` is the sharp case. It WAS in a grid — Run 4 — and Run 4 is marked
    **INVALID, DO NOT USE THE NUMBERS**, which is worse than untested. The rest have no mention in
    the optimization log at all.
    """
    by = {p["name"]: p for p in _params()}
    for n in (
        "exec_sl_buf_tk",  # Run 4 swept it and Run 4 is invalid
        "exec_arm_sweep",  # never swept
        "exec_aplus",
        "aplus_window",
        "exec_sec_once_per_setup",
        "exec_sec_retrace",
        "flat_by_close",
    ):
        assert not by[n].get("hidden"), f"{n} has no valid sweep behind it and must stay visible"


def test_the_money_number_is_never_hidden():
    """`exec_risk_pct` has sat at 10 for every stored run, so a "never moved" rule would retire it.
    It decides position size on the strategy the LIVE bot runs, and a sizing input nobody can see
    is how a 54.82-lot order on a $2,000 account happens."""
    by = {p["name"]: p for p in _params()}
    assert not by["exec_risk_pct"].get("hidden")


def test_nothing_that_has_actually_been_TUNED_is_hidden():
    """A param somebody has moved is a live question, whatever it defaults to. These four have
    been swept or changed on real runs; hiding one would take away a lever in use."""
    by = {p["name"]: p for p in _params()}
    for n in ("exec_req_fvg", "exec_deep_fib", "exec_sl_level", "exec_secondary"):
        assert not by[n].get("hidden"), f"{n} has been tuned and must stay visible"
