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


def test_the_six_proven_settled_params_are_hidden():
    """Each of these was tested against alternatives and lost or tied. The evidence is in
    `mpc_sos_fade_optimization.md`, named per param in this package's CLAUDE.md — Run 2's
    525-combo exit grid, Run 5/6 (`exec_close_opp_sos` at exactly 0 effect, twice), Run 12 (both
    relax routes)."""
    by = {p["name"]: p for p in _params()}
    for n in (
        "exec_close_opp_sos",
        "exec_tp2_stop_mode",
        "exec_struct_trail_buf_tk",
        "exec_trail_step",
        "exec_fvg_deep_only",
        "exec_no_late_day",
    ):
        assert by[n].get("hidden") is True, f"{n} has a sweep behind it and should be settled"


def test_the_breakeven_buffer_IN_FORCE_is_not_settled_off_the_screen():
    """🔴 IT WAS SETTLED ON THE STRENGTH OF RUN 17 UNTIL 2026-08-27, AND THAT WAS THE WRONG HALF.

    Run 17 swept the tick buffer and it did not earn a different value — which is the bar for
    settling a param. But the buffer mode has THREE values and the shipped one is Ticks, so this
    figure is the one the exit ladder actually reads on every live trade, while the two fraction
    fields it competes with were on screen. The form showed the cushions that were NOT in force
    and hid the one that was.

    That is not hypothetical. The 2026-06-04 short came off its staged stop $12.92 in profit
    rather than $0.30, because a run had been launched on the fraction mode at 0.35, and reading
    the form gave no way to see which cushion was in play. The mode dropdown is now the thing that
    picks, and whichever figure it picks is visible beside it.

    ⚠ `hidden` is not being retired — the six above are still settled. The rule this adds is
    narrower: a param that a `show_if` makes CONDITIONAL cannot also be settled, or the one
    configuration where it is live is the one where nobody can see it.

    MUTATION: put `"hidden": true` back on the row and this goes red.
    """
    by = {p["name"]: p for p in _params()}
    buf = by["exec_be_buf_tk"]
    assert not buf.get("hidden")
    assert buf["show_if"] == {"exec_be_buf_mode": "Ticks"}
    # and the pair it competes with is gated the other way, or two cushions read as live at once
    assert by["exec_be_buf_r"]["show_if"] == {
        "exec_be_buf_mode": ["Fraction of stop", "Fraction of stop + cost"]
    }


# 🔴 SETTLED **AND** CONDITIONAL IS INVISIBLE IN EVERY CONFIGURATION, and five rows are.
#
# The two mechanisms hide a row for opposite reasons and they compose badly: the gate takes it off
# the screen wherever it cannot matter, and `hidden` takes it off the screen wherever it CAN — so
# between them there is nowhere left. A reader who switches the runner trail to a fixed step and
# then looks for the step size does not find one.
#
# The five below are PRE-EXISTING and each is a real question rather than a bug this test knows
# how to settle: whether the row should stop being settled (the answer taken for the breakeven
# buffer above) or stop being gated. They are pinned as a LIST rather than asserted away, so a
# sixth cannot arrive without somebody deciding. ⚠ Raised with Aaron 2026-08-27, undecided.
KNOWN_SETTLED_AND_CONDITIONAL = [
    "exec_trail_step",
    "div_valid_bars",
    "div_extreme_ob",
    "div_extreme_os",
    "exec_htf_source",
]


def test_no_NEW_param_is_both_settled_and_conditional():
    """MUTATION: add `"hidden": true` to any gated row in the meta and this goes red.

    ⚠ It cannot go red at HEAD, and that is the point of the list — the five are the state being
    frozen, not a state being asserted correct.
    """
    both = [p["name"] for p in _params() if p.get("hidden") and p.get("show_if")]
    assert both == KNOWN_SETTLED_AND_CONDITIONAL, (
        "a row is now both settled and gated, so no configuration can show it: "
        f"{sorted(set(both) ^ set(KNOWN_SETTLED_AND_CONDITIONAL))}"
    )


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


# ── the "above zero" shape, and the fixture both evaluators answer ────────────
#
# 🔴 ONE SET OF CASES, TWO EVALUATORS. `_want_holds` here and `wantHolds` in
# `frontend/src/components/paramConditions.ts` are the same rule written twice, and they have
# already disagreed in silence: a fib level is the string "1.0" in a dropdown and the number 1.0
# in the Custom box, JS stringified them differently from Python, and a toggle stayed live in
# exactly the configuration it exists to be dead in. Neither side looked wrong alone.
#
# So the CASES are the shared artifact rather than the code. This test and
# `frontend/scripts/check_param_conditions.mjs` read the same JSON, and a shape one side learns
# and the other does not fails on the side that did not learn it. ✅ It caught one the day it was
# written: `Object.entries({}).every(...)` is true, so an empty condition HELD on the JS side and
# did not here.

CONDITIONS_FIXTURE = (
    cfg.MONOREPO_ROOT
    / "command-center"
    / "frontend"
    / "tests"
    / "fixtures"
    / "param-conditions.json"
)


def _condition_cases():
    return json.loads(CONDITIONS_FIXTURE.read_text())["cases"]


def test_the_shared_fixture_is_where_the_other_evaluator_reads_it_from():
    """The path is the whole mechanism. MUTATION: point either reader at its own copy and the two
    evaluators can drift again with every test still green — which is the state this replaced."""
    assert CONDITIONS_FIXTURE.exists(), f"{CONDITIONS_FIXTURE} is gone — the JS side reads it too"
    driver = (
        cfg.MONOREPO_ROOT / "command-center" / "frontend" / "scripts" / "check_param_conditions.mjs"
    )
    assert driver.exists()
    assert "param-conditions.json" in driver.read_text()


@pytest.mark.parametrize("case", _condition_cases(), ids=lambda c: c["why"][:60])
def test_both_evaluators_answer_the_shared_fixture_the_same_way(case):
    """MUTATIONS, each RUN rather than reasoned — the numbers are the fixture's own order.

    ⚠ That is not pedantry. The first version of this map was written from inspection and named
    the wrong cases for three of its seven entries, every time in the flattering direction.

      drop the `gt` branch from `_want_holds` ........... 11 12 14 15 19 21
      `>=` instead of `>` .............................. 12 14
      an unknown operator reads as MET ................. 22 23
      drop the list branch ............................. 8
      an empty list HOLDS (`all` for `any`) ............ 8 10
      drop the bool guard from `_numeric` .............. 17
      drop the numeric branch from `_same_value` ....... 6

    ⚠ Cases 1 2 3 4 5 7 9 13 16 18 20 are killed by no mutation above and are listed rather than
    quietly left in. They are DIRECTION checks — the plain equality that must keep working while
    the new shape lands, and the negative half of a case whose positive half is pinned.

    🔴 CASE 5 IS THE ASYMMETRY THE SHARED FIXTURE EXISTS FOR. `1.0` against `"1.0"` survives here
    when the numeric compare is removed, because `str(1.0)` is `"1.0"` — and it DIES on the JS
    side, where `String(1.0)` is `"1"`. This evaluator was right by accident for months while the
    other one was wrong, and no test on either side could see it.
    """
    from services.stress_tester import _want_holds

    assert _want_holds(case["actual"], case["want"]) is case["holds"], case["why"]


def test_an_EMPTY_condition_holds_nothing():
    """🔴 The disagreement the fixture caught on its first run, from this side.

    `not {}` is True in Python so this side already refused it; `Object.entries({}).every(...)` is
    `true` in JS, so the editor would have called every row with an empty `disable_if` dead. No
    schema uses `{}` today, which is exactly why nothing on screen could have shown it.

    MUTATION: drop the `if not cond` guard and this goes red.
    """
    from services.stress_tester import _cond_holds

    assert _cond_holds({}, lambda _n: 1) is False
    assert _cond_holds(None, lambda _n: 1) is False


def test_a_param_gated_ABOVE_ZERO_is_not_perturbed_while_its_parent_is_off():
    """The reachability half — the reason the shape was added at all.

    A rule that arms the stop after a move of N R is off at -1 and also off at 0, so the row it
    controls cannot be gated by equality without listing every number that is not off. Until this
    shape existed the dependent row was simply not gated: it sat on screen under a parent that was
    off, and sensitivity perturbed it and booked a guaranteed 0% change as a robustness result.

    MUTATION: drop the `gt` branch from `_want_holds` and the first two assertions go red.
    """
    keep = {"name": "keep_r", "type": "float", "show_if": {"arm_r": {"gt": 0}}}
    schema = [{"name": "arm_r", "type": "float"}, keep]
    assert param_is_reachable(keep, {"arm_r": -1.0}, schema) is False
    assert param_is_reachable(keep, {"arm_r": 0.0}, schema) is False
    assert param_is_reachable(keep, {"arm_r": 1.0}, schema) is True


def test_no_param_declares_the_SAME_KEY_TWICE():
    """🔴 A DUPLICATE JSON KEY IS SILENT AND THE LAST ONE WINS.

    Written after exactly that: a script inserted `show_if` after `group` on three rows that
    already carried one further down, and `json.load` took the second. The rule read as landed —
    it was in the file, on the right param, spelled correctly — and the editor served the older,
    weaker condition. Nothing failed: not the scan, not the parse, not a test, not the page.

    ⚠ It cannot be caught by reading the parsed object, because by then one of the two is gone.
    `object_pairs_hook` is the only place the collision is still visible.

    MUTATION: duplicate any key on any param in the meta and this goes red naming it.
    """

    def refuse_duplicates(pairs):
        seen = [k for k, _ in pairs]
        dupes = {k for k in seen if seen.count(k) > 1}
        assert not dupes, f"duplicate key(s) {sorted(dupes)} in {dict(pairs).get('name', '?')}"
        return dict(pairs)

    json.loads(Path(META).read_text(), object_pairs_hook=refuse_duplicates)


def test_every_gate_names_a_param_that_EXISTS():
    """A condition on a misspelled name reads the default of nothing, so it never holds and the
    row it guards is hidden forever — a setting deleted by a typo, with no error anywhere.

    MUTATION: rename any param referenced by a `show_if` / `disable_if` in the meta and this goes
    red naming both sides.
    """
    params = _params()
    names = {p["name"] for p in params}
    missing = [
        (p["name"], key)
        for p in params
        for gate in ("show_if", "disable_if")
        for key in (p.get(gate) or {})
        if key not in names
    ]
    assert missing == [], f"a gate names a param that does not exist: {missing}"
