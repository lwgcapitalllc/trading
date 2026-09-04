"""The live contract must describe `algos/live/`, not a parallel invention of it.

🔴 **This is the point of the whole module.** A hand-maintained list of "what the live path needs"
is a SECOND IMPLEMENTATION of the live path's requirements, and this repo already knows what
happens to those: the next person changes one side and nothing goes red. So every list in
`live_contract` is re-derived HERE from `algos/live/` source, and a live path that starts reading
something new turns this file red instead of turning a bot silent.

⚠ **Parsing source is deliberate and it is the weaker half of the check.** It sees a literal
`getattr(dec, "stop", ...)` and cannot see a computed name. That is accepted: the live path is
written with literals throughout, and a check that reads the real file is worth far more than a
list somebody promises to update. **If the live path ever reads a decision field dynamically,
this check goes quiet and must be replaced, not relaxed.**
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_PYPKGS = _ROOT / "strategies" / "python"
for _p in (str(_ROOT), str(_PYPKGS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from live_contract import (  # noqa: E402
    DECISION_FIELDS,
    EXECUTION_ATTRS,
    LOAD_BEARING,
    LiveContractError,
    LiveDecision,
    LivePositionMixin,
    PassThroughSequence,
    PassThroughSignals,
    verify_live_ready,
)

_BRIDGE = _ROOT / "algos" / "live" / "bridge.py"
_LEDGER = _ROOT / "algos" / "live" / "ledger.py"
_RUNNER = _ROOT / "algos" / "live" / "runner.py"


def _decision_reads() -> set:
    """Every decision field the live path actually reads, off its own source."""
    found = set()
    for path in (_BRIDGE, _LEDGER):
        text = path.read_text(encoding="utf-8")
        found |= set(re.findall(r'getattr\(\s*dec\s*,\s*"([a-z_0-9]+)"', text))
    return found


def _execution_reads() -> set:
    """Every attribute the bridge reads off the execution object."""
    text = _BRIDGE.read_text(encoding="utf-8")
    return set(re.findall(r"self\._ex\.([a-z_][a-z_0-9]*)", text))


def _method_body(text: str, name: str) -> str:
    """The source of one method, from its `def` to the next `def` at the same indent.

    ⚠ Crude on purpose — it is reading a known file to answer one structural question, not
    parsing Python in general. It REFUSES rather than returning an empty string, because an empty
    body would make every assertion about it pass.
    """
    lines = text.splitlines()
    start = next(
        (i for i, ln in enumerate(lines) if re.match(rf"(\s*)def {re.escape(name)}\b", ln)),
        None,
    )
    assert start is not None, f"no method {name!r} in the source — has it been renamed?"
    indent = len(lines[start]) - len(lines[start].lstrip())
    out = [lines[start]]
    for ln in lines[start + 1:]:
        if ln.strip() and (len(ln) - len(ln.lstrip())) <= indent and re.match(r"\s*(def|class)\b", ln):
            break
        out.append(ln)
    body = "\n".join(out)
    assert len(body) > len(lines[start]), f"{name!r} parsed as an empty body"
    return body


# ── the contract matches the live path ───────────────────────────────────────


def test_the_parse_finds_something_at_all():
    """Guards every other test in this file.

    ⚠ **Without this, a regex that matches NOTHING makes every comparison below trivially pass**
    — `set() <= anything` is true. A rename in the live path or a change of quoting style would
    turn the whole file into a green no-op. MUTATION: break the regex and only this goes red.
    """
    assert len(_decision_reads()) >= 8, _decision_reads()
    assert len(_execution_reads()) >= 4, _execution_reads()


def test_every_decision_field_the_live_path_reads_is_in_the_contract():
    """MUTATION: delete an entry from `DECISION_FIELDS` and this goes red naming it."""
    undeclared = _decision_reads() - set(DECISION_FIELDS)
    assert not undeclared, (
        f"algos/live/ reads decision fields the contract does not declare: "
        f"{sorted(undeclared)}. A strategy built against this contract would leave them "
        f"unset, and every read is a defensive getattr, so nothing would fail loudly."
    )


def test_the_contract_declares_nothing_the_live_path_does_not_read():
    """The other direction — a contract that over-declares makes adopters do dead work.

    ⚠ Deliberately an equality check in both directions rather than one subset test: a contract
    that is merely a SUPERSET drifts upward forever as fields are removed from the live path.
    """
    stale = set(DECISION_FIELDS) - _decision_reads()
    assert not stale, (
        f"the contract declares decision fields nothing in algos/live/ reads: {sorted(stale)}"
    )


def test_the_load_bearing_fields_are_read_by_the_bridge_at_all():
    """A NECESSARY condition only, and the docstring says so because the first version lied.

    🔴 **This test originally claimed that adding a reporting field to `LOAD_BEARING` would turn
    it red. It does not, and the mutation run is what proved it** — the bridge reads `tp1` too,
    so "is read by the bridge" cannot separate a field that moves money from one that is merely
    recorded. **A mutation note asserting a coverage the test does not have is worse than no
    note: the next reader trusts it and stops looking.**

    ⚠ **The load-bearing/reporting split is a HUMAN reading of what the bridge does with each
    value, and it is not derivable by parsing.** Enclosing-function analysis was tried and also
    fails — `tp1` is read inside a method that happens to make a broker call of its own.
    `test_the_stop_value_reaches_a_broker_call` below is the narrow structural half that IS
    checkable; the rest of the split is maintained by review.
    """
    bridge = _BRIDGE.read_text(encoding="utf-8")
    for name in LOAD_BEARING:
        assert f'getattr(dec, "{name}"' in bridge, (
            f"{name!r} is declared load-bearing but the bridge does not read it")
    assert set(LOAD_BEARING) <= set(DECISION_FIELDS)


def test_the_stop_value_reaches_a_broker_call():
    """The stop is load-bearing because its VALUE is handed to the broker, not because it is read.

    This is the one half of the split that can be checked structurally: the value bound from
    `getattr(dec, "stop", ...)` is passed to the terminal's stop-move call in the same method.
    MUTATION: change `_sync_stop` to move a stop it computed itself and this goes red.
    """
    body = _method_body(_BRIDGE.read_text(encoding="utf-8"), "_sync_stop")
    assert 'getattr(dec, "stop"' in body, "_sync_stop no longer reads the decision's stop"
    m = re.search(r'(\w+)\s*=\s*getattr\(\s*dec\s*,\s*"stop"', body)
    assert m, "could not find what the stop is bound to"
    assert re.search(rf"move_sl\([^)]*\b{m.group(1)}\b", body), (
        f"_sync_stop reads the decision's stop into {m.group(1)!r} but does not hand that value "
        f"to move_sl — the broker's stop would be moved to something else"
    )


def test_the_fills_value_drives_the_exit_mirror():
    """`fills` is load-bearing because the bridge acts on its contents to close a position.

    MUTATION: make `_mirror_strategy_exit` ignore the decision's fills and this goes red.
    """
    body = _method_body(_BRIDGE.read_text(encoding="utf-8"), "_mirror_strategy_exit")
    assert 'getattr(dec, "fills"' in body
    assert "exit" in body, "the fills read no longer drives an exit path"


def test_every_execution_attribute_the_bridge_reads_is_in_the_contract():
    """MUTATION: drop `_pos_dir` from `EXECUTION_ATTRS` and this goes red."""
    undeclared = _execution_reads() - set(EXECUTION_ATTRS)
    assert not undeclared, (
        f"the bridge reads execution attributes the contract does not declare: "
        f"{sorted(undeclared)}"
    )


def test_the_runner_still_drives_the_three_stages_this_contract_assumes():
    """The pass-through stages exist ONLY because the runner calls three of them.

    MUTATION: if the runner is ever refactored to one call, this goes red and the shims become
    dead weight that should be deleted rather than carried.
    """
    runner = _RUNNER.read_text(encoding="utf-8")
    assert ".signals.update(" in runner
    assert ".sequence.update(" in runner
    assert ".execution.step(" in runner


def test_the_decision_dataclass_carries_every_contract_field_with_matching_defaults():
    """An adopter using `LiveDecision` must not be missing a field, or holding a different default.

    🔴 A default that disagrees with the live path's own default is worse than a missing field:
    the reader gets a confident wrong value instead of the absence it was coded for.
    MUTATION: change `l_stage` to default `1` and this goes red.
    """
    d = LiveDecision()
    for name, expected in DECISION_FIELDS.items():
        assert hasattr(d, name), f"LiveDecision is missing {name!r}"
        actual = getattr(d, name)
        if isinstance(expected, tuple) and expected == ():
            assert list(actual) == [], f"{name}: expected an empty sequence, got {actual!r}"
        else:
            assert actual == expected, f"{name}: contract default {expected!r}, got {actual!r}"


# ── the contract describes the bot that is actually trading ──────────────────


def test_the_live_bot_satisfies_this_contract_without_importing_it():
    """SOS Fade is live and armed. If the contract does not describe IT, the contract is wrong.

    🔴 **This is the test that stops this module being an invention.** SOS Fade predates it and
    imports nothing from it, so it is an independent witness: anything the contract demands that
    SOS Fade does not provide is something the live path demonstrably does not need.
    MUTATION: add a made-up required attribute to `EXECUTION_ATTRS` and this goes red.
    """
    from sos_fade import LAB_STRATEGY

    st = LAB_STRATEGY["strategy"](LAB_STRATEGY["config"]())
    assert verify_live_ready(st) == []


def test_a_strategy_that_is_not_live_ready_is_named_rather_than_crashing():
    """The whole point of the check: a list of what is missing, not an AttributeError at 3am."""

    class Bare:
        pass

    missing = verify_live_ready(Bare())
    assert missing
    assert any("execution" in m for m in missing)


def test_a_strategy_with_an_execution_but_no_seams_reports_each_missing_name():
    """MUTATION: make `verify_live_ready` return `[]` early and this goes red."""

    class Ex:
        pass

    class St:
        signals = sequence = None
        execution = Ex()

        def engine_config(self):
            return {}

    missing = verify_live_ready(St())
    for name in ("_pos_dir", "request_close", "snapshot_position"):
        assert any(m.endswith(name) for m in missing), f"{name} not reported: {missing}"


# ── the generic halves behave ────────────────────────────────────────────────


def test_the_pass_through_stages_do_exactly_nothing():
    """They are seams, not logic. MUTATION: make signals return None and this goes red."""
    state = object()
    assert PassThroughSignals().update(state) is state
    assert PassThroughSequence().update(state) is None


class _Pos(LivePositionMixin):
    _POSITION_FIELDS = ("a", "b")

    def __init__(self):
        self.a = 1
        self.b = [2, 3]
        self.flat = False

    @property
    def is_flat(self):
        return self.flat


def test_save_and_restore_round_trips_the_declared_fields():
    p = _Pos()
    snap = p.snapshot_position()
    p.a, p.b = 99, []
    p.restore_position(snap)
    assert p.a == 1 and p.b == [2, 3]


def test_restore_REFUSES_an_incomplete_record_rather_than_defaulting():
    """🔴 The safety property. A record missing a field is not a position at the default.

    MUTATION: make `restore_position` skip missing names instead of raising, and this goes red.
    """
    p = _Pos()
    with pytest.raises(ValueError) as e:
        p.restore_position({"a": 1})
    assert "b" in str(e.value)


def test_snapshotting_while_flat_refuses():
    p = _Pos()
    p.flat = True
    with pytest.raises(ValueError):
        p.snapshot_position()


def test_a_class_that_declares_no_position_fields_refuses_to_snapshot():
    """🔴 Silence is the failure mode here, so the empty declaration must REFUSE.

    An empty list would otherwise snapshot `{}`, restore cleanly, and drop the whole position —
    the exact "nothing to report vs never implemented" collapse this module exists to prevent.
    MUTATION: return `{}` instead of raising and this goes red.
    """

    class Empty(LivePositionMixin):
        is_flat = False

    with pytest.raises(LiveContractError):
        Empty().snapshot_position()
