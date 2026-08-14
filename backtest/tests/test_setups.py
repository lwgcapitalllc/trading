"""Tests for `backtest/setups.py` — the contract a strategy fills in to report live setups.

These pin the SHAPE, not any strategy's use of it. Each one was watched RED against a deliberate
break of the thing it names; where a test cannot be made to fail it says so in its own docstring
rather than being kept as decoration.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backtest.setups import (
    DEAD,
    FILLED,
    RESTING,  # noqa: E402
    WATCHING,
    Confluence,
    SetupSnapshot,
    implements_contract,
)


def _snap(**kw) -> SetupSnapshot:
    base = dict(key="S:L:7", strategy="Strat", symbol="XAUUSD", side=1, state=WATCHING)
    base.update(kw)
    return SetupSnapshot(**base)


# ── the counts are DERIVED, which is what makes "2 of 3" stop being hardcoded ────────────────
def test_met_and_of_come_from_the_confluence_list_not_from_a_constant():
    """A four-confluence strategy must report 3 of 4 with no change to the alert layer.

    RED against storing `of` as a field: any test would then pass while the stored total drifted
    from the list beside it.
    """
    s = _snap(
        confluences=(
            Confluence("A", True),
            Confluence("B", True),
            Confluence("C", False),
            Confluence("D", True),
        )
    )
    assert (s.met, s.of) == (3, 4)


def test_a_setup_with_no_confluences_reports_zero_of_zero_rather_than_raising():
    """A strategy may legitimately report a setup before it has declared anything.

    The alert layer renders `(0 of 0)`, which is odd-looking and TRUE. Raising here would let a
    reporting-only path take down a trading loop.
    """
    assert (_snap().met, _snap().of) == (0, 0)


# ── the validation, which exists to stop a bad snapshot leaking a Telegram thread ────────────
def test_an_unknown_state_is_refused_at_construction():
    """RED against dropping the `state` check in `__post_init__`.

    A typo'd state is never terminal, so `is_terminal` stays False forever and the alert layer
    never drops that setup's thread bookkeeping — a leak with no symptom until the process has
    run for months. Refusing at construction turns a silent leak into a loud failure.
    """
    with pytest.raises(ValueError, match="state"):
        _snap(state="watchign")


def test_an_empty_key_is_refused_because_it_is_the_thread_id():
    """RED against dropping the `key` check. Every setup with a blank key would share one
    Telegram thread and one dedupe entry, so the second setup would be silently suppressed."""
    with pytest.raises(ValueError, match="key"):
        _snap(key="")


def test_a_side_that_is_not_plus_or_minus_one_is_refused():
    """RED against dropping the check: `direction` would render LONG for side 0."""
    with pytest.raises(ValueError, match="side"):
        _snap(side=0)


def test_a_zone_that_is_not_a_pair_is_refused():
    """RED against dropping the check — the formatter unpacks two values and would raise
    inside the notifier instead, on the live path."""
    with pytest.raises(ValueError, match="zone"):
        _snap(zone=(1.0, 2.0, 3.0))


# ── terminal states, which drive the alert layer's cleanup ───────────────────────────────────
@pytest.mark.parametrize(
    "state,terminal", [(WATCHING, False), (RESTING, False), (FILLED, True), (DEAD, True)]
)
def test_only_filled_and_dead_are_terminal(state, terminal):
    """RED against adding RESTING to `TERMINAL`: a resting setup's thread would be dropped and
    its own fill message would then arrive with nothing to reply to."""
    assert _snap(state=state).is_terminal is terminal


def test_direction_reads_from_the_sign_not_from_a_label():
    assert _snap(side=1).direction == "LONG"
    assert _snap(side=-1).direction == "SHORT"


# ── the detail line, which is what makes a message worth reading ─────────────────────────────
def test_met_lines_prefer_the_strategys_own_words_over_a_generic_yes():
    """The whole value of the confluence block is the strategy's own detail — "Day High", not
    "met". RED against dropping `detail` from the f-string."""
    s = _snap(confluences=(Confluence("Sweep", True, "Day High"), Confluence("Zone", False)))
    assert s.met_lines() == ["Sweep — Day High", "Zone — not yet"]


# ── the contract probe, whose whole job is to notice ABSENCE ─────────────────────────────────
def test_implements_contract_is_false_for_an_object_without_the_method():
    """The runner reports this state by name at startup. RED against a probe that returns True
    for everything — which is the shape that made three jobs in this repo run for weeks against
    an empty registry and report success."""

    class NoContract:
        pass

    assert implements_contract(NoContract()) is False


def test_implements_contract_is_false_when_live_setups_is_an_ATTRIBUTE_not_a_method():
    """`hasattr` alone would say True and the caller would then crash calling a list.

    RED against `hasattr(obj, "live_setups")`.
    """

    class Wrong:
        live_setups = []

    assert implements_contract(Wrong()) is False


def test_a_class_can_opt_OUT_by_declaring_reports_setups_False():
    """🔴 Inheritance produced the empty-registry failure this whole module warns about: a
    subclass that inherits `live_setups()` but cannot populate it answers `[]` on every bar, and a
    method-presence check calls it supported.

    RED against `implements_contract` returning on the callable check alone.
    """

    class Inherited:
        reports_setups = False

        def live_setups(self):
            return []

    assert implements_contract(Inherited()) is False


def test_not_declaring_reports_setups_means_YES():
    """The opt-out must be explicit. Defaulting to False would silently disable every existing
    implementation the day this was added."""

    class Ordinary:
        def live_setups(self):
            return []

    assert implements_contract(Ordinary()) is True


def test_implements_contract_does_not_CALL_the_method_to_find_out():
    """Answering a question about SHAPE must not execute strategy code, and must not swallow a
    genuine error inside a real implementation as "not implemented".

    RED against a `try: obj.live_setups() except AttributeError: return False` probe — that
    version raises here instead of returning True.
    """

    class Explodes:
        def live_setups(self):
            raise RuntimeError("should never be called by a shape check")

    assert implements_contract(Explodes()) is True
