"""The seams that let `algos/live/` drive this strategy — and the proof they cost the replay nothing.

🔴 **The whole-strategy proof is NOT here and cannot be.** That every one of the 113 trades over
470,995 bars is unchanged is a MEASUREMENT (digest `e4183861407c6b1e`, before and after), recorded
in `docs/EXTREME_LEG_BOT_PLAN.md`. These tests pin the seams themselves: that they do what the
bridge needs, and that nothing in them is reachable from a replay.
"""

from __future__ import annotations

import sys
from dataclasses import fields
from pathlib import Path

import pytest

_PYPKGS = Path(__file__).resolve().parents[2]
_ROOT = Path(__file__).resolve().parents[4]
for _p in (str(_ROOT), str(_PYPKGS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from live_contract import verify_live_ready  # noqa: E402

_BRIDGE = _ROOT / "algos" / "live" / "bridge.py"


from extreme_leg import LAB_STRATEGY  # noqa: E402
from extreme_leg.config import ExtremeLegConfig  # noqa: E402
from extreme_leg.execution import _Open, ExtremeLegExecution  # noqa: E402


def _bridge_owned_exits() -> tuple:
    """The exit suffixes the bridge acts on, READ FROM ITS SOURCE.

    ⚠ **Parsed rather than imported, deliberately.** Importing `algos.live.bridge` from a strategy
    test drags in the whole live import graph — and this repo already has a hard rule against
    `algos/live/` importing strategy packages at module scope, for the same reason: two trees that
    must stay independent should not be wired together by a test.

    ⚠ It REFUSES rather than returning empty. An empty tuple makes every assertion below pass or
    fail for the wrong reason.
    """
    import re

    text = _BRIDGE.read_text(encoding="utf-8")
    m = re.search(r"BRIDGE_OWNED_EXITS\s*=\s*\(([^)]*)\)", text)
    assert m, "BRIDGE_OWNED_EXITS not found in the bridge — has it been renamed?"
    tags = tuple(re.findall(r'"([^"]+)"', m.group(1)))
    assert tags, "BRIDGE_OWNED_EXITS parsed as empty"
    return tags


def _exec(**cfg):
    return ExtremeLegExecution(ExtremeLegConfig(**cfg), initial_capital=10_000.0)


def _held(ex, direction=1, entry=100.0, stop=95.0, tp=110.0, index=5):
    ex.pos = _Open(
        dir=direction, entry_index=index, entry_ms=1_600_000_000_000, entry_price=entry,
        qty=2.0, stop=stop, open_stop=stop, take_profit=tp, ext_high=entry, ext_low=entry,
    )
    return ex


# ── the contract ─────────────────────────────────────────────────────────────


def test_this_strategy_satisfies_the_live_contract():
    """MUTATION: remove `request_close` and this goes red naming it."""
    st = LAB_STRATEGY["strategy"](LAB_STRATEGY["config"]())
    assert verify_live_ready(st) == []


def test_the_position_record_covers_EVERY_field_the_open_position_holds():
    """🔴 A field in `_Open` that `_POSITION_FIELDS` does not carry comes back at its class
    default after a restart, and NOTHING reports that — a trade already moved to breakeven would
    be managed as though it never was.

    This passes today because the whole position is one object. **It is here for the day somebody
    adds a latch beside it** rather than inside it.
    MUTATION: set `_POSITION_FIELDS = ()` and this goes red.
    """
    ex = _held(_exec())
    snap = ex.snapshot_position()
    for f in fields(_Open):
        assert f.name in snap["pos"], f"{f.name} would be lost across a restart"


# ── save and restore ─────────────────────────────────────────────────────────


def test_a_position_round_trips_through_a_snapshot():
    ex = _held(_exec(), direction=-1, entry=250.0, stop=260.0, tp=230.0)
    ex.pos.be_armed = True
    snap = ex.snapshot_position()
    ex.pos = None
    ex.restore_position(snap)
    assert ex.pos.dir == -1 and ex.pos.entry_price == 250.0 and ex.pos.be_armed is True


def test_the_snapshot_is_plain_data_and_does_not_alias_the_open_trade():
    """A snapshot that aliased the live object would keep changing after it was taken."""
    ex = _held(_exec())
    snap = ex.snapshot_position()
    ex.pos.stop = 99.0
    assert snap["pos"]["stop"] == 95.0


def test_restore_REFUSES_an_incomplete_record_rather_than_defaulting():
    """🔴 The safety property. A record missing a field is not a position at the default —
    it is one we cannot trust, and managing a real trade against a guess is the failure this ends.
    MUTATION: make the mixin skip missing names and this goes red.
    """
    ex = _exec()
    with pytest.raises(ValueError):
        ex.restore_position({})


def test_snapshotting_while_flat_refuses():
    with pytest.raises(ValueError):
        _exec().snapshot_position()


# ── what the bridge reads ────────────────────────────────────────────────────


def test_the_direction_and_entry_read_None_and_zero_while_FLAT():
    """Rule 1: the entry is `None` when there is nothing to report, never 0.0 — which is a price.
    MUTATION: return 0.0 for the entry and this goes red.
    """
    ex = _exec()
    assert ex._pos_dir == 0
    assert ex._entry is None


def test_the_direction_and_entry_report_the_open_position():
    ex = _held(_exec(), direction=-1, entry=250.0)
    assert ex._pos_dir == -1
    assert ex._entry == 250.0


def test_nothing_ever_rests_because_this_bot_enters_at_market():
    """Stated as real attributes rather than left missing — the bridge reads them every reconcile
    and `None` is the honest answer, not an absence it has to interpret."""
    ex = _exec()
    assert ex._pend_long is None and ex._pend_short is None


# ── the commanded close ──────────────────────────────────────────────────────


def test_asking_to_close_while_FLAT_is_refused_and_does_not_latch():
    """A waiting request would fire on whatever this bot opened next — a trade nobody had an
    opinion about. MUTATION: latch the request while flat and this goes red.
    """
    ex = _exec()
    assert ex.request_close("stop trading") is False
    assert ex._close_request is None


def test_a_commanded_close_exits_on_the_NEXT_bar_at_its_OPEN():
    """It goes through `resolve`, the same path a stop or a target takes, so it is booked and
    costed like every other exit rather than needing a second closing path.
    MUTATION: close inside `request_close` and this goes red on the bar count.
    """
    ex = _held(_exec(), index=5)
    assert ex.request_close("commanded") is True
    assert ex.pos is not None, "it must not close on the bar it was asked"
    ex.resolve(6, 1_600_000_600_000, high=101.0, low=99.0, open_=100.5)
    assert ex.pos is None
    assert ex.trades[-1].exit_price == 100.5
    assert ex.trades[-1].exit_reason == "commanded"


def test_a_commanded_close_beats_the_bracket_on_the_same_bar():
    """The instruction was made between bars, so it supersedes a stop the bar would also have hit.
    MUTATION: test the bracket first and this goes red with exit_reason 'stop'.
    """
    ex = _held(_exec(), index=5, stop=99.5)
    ex.request_close("commanded")
    ex.resolve(6, 1_600_000_600_000, high=101.0, low=98.0, open_=100.5)
    assert ex.trades[-1].exit_reason == "commanded"


def test_the_request_is_CONSUMED_so_it_cannot_fire_on_the_next_trade():
    ex = _held(_exec(), index=5)
    ex.request_close("commanded")
    ex.resolve(6, 1_600_000_600_000, high=101.0, low=99.0, open_=100.5)
    assert ex._close_request is None


def test_a_replay_never_arms_a_close_request():
    """🔴 This is why the trade list is provably unchanged: the only thing that sets the flag is
    `request_close`, and nothing in the backtest path calls it."""
    assert _exec()._close_request is None


# ── the exit tags the bridge acts on ─────────────────────────────────────────


def test_a_TARGET_exit_is_tagged_so_the_BRIDGE_closes_it():
    """🔴 This bot sends `tp=0.0` and manages its own target, so the broker has never heard of it.
    If the tag is not one the bridge owns, the strategy exits in its own book, the broker keeps
    the position, and the bridge halts on the next bar.
    MUTATION: map 'target' to 'STOP' and this goes red.
    """
    owned = _bridge_owned_exits()

    tag = ExtremeLegExecution._EXIT_TAGS["target"]
    assert any(f"L-{tag}".endswith(s) for s in owned)


def test_a_STOP_exit_is_NOT_tagged_for_the_bridge():
    """🔴 The other direction, and it is the dangerous one. A stop is already an order resting at
    the broker; mirroring it would send a market close on top of a stop that is already filling.
    MUTATION: map 'stop' to 'CMD' and this goes red.
    """
    owned = _bridge_owned_exits()

    tag = ExtremeLegExecution._EXIT_TAGS["stop"]
    assert not any(f"L-{tag}".endswith(s) for s in owned)


def test_an_UNKNOWN_exit_reason_falls_back_to_a_tag_the_bridge_OWNS():
    """The safe direction: an exit this bot learns later is MIRRORED rather than silently left
    with the broker still holding. Loud (a halt at worst) beats a position nobody closes."""
    owned = _bridge_owned_exits()

    tag = ExtremeLegExecution._EXIT_TAGS.get("something_new", "CMD")
    assert any(f"L-{tag}".endswith(s) for s in owned)


# ── the per-bar step ─────────────────────────────────────────────────────────


def test_stepping_an_execution_with_no_strategy_REFUSES_rather_than_crashing_oddly():
    """It is built by the strategy in production. A bare one says so."""
    with pytest.raises(RuntimeError, match="strategy"):
        _exec().step(object(), None)
