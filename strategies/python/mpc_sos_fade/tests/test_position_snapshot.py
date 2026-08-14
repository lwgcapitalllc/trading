"""The emulator's open-trade state can be written down and put back EXACTLY.

`algos/live/` uses this to survive a restart while a trade is open. These tests run against the
REAL `Execution`, never a stand-in: the whole class of bug this guards against is a field the
snapshot forgets, and a double built from the same list as the code under test cannot see one.
That is the `test_secondary.py` lesson of 2026-08-06, where a hand-built fixture carried two
fields production never produced and three weeks of green tests said the feature worked.
"""

from __future__ import annotations

import inspect
import re

import pytest

from mpc_sos_fade.config import SosFadeConfig
from mpc_sos_fade.execution import Execution, TradeFib


def _ex() -> Execution:
    return Execution(SosFadeConfig(), 10_000.0)


def _open(ex: Execution, *, direction=1, entry=3290.0, stop=3280.0, qty=2.0, stage=0):
    """Put the emulator into a plausible mid-trade state by hand.

    Deliberately NOT by replaying bars: this is about the STATE, and a hand-set state can carry
    the awkward values a tidy replay never produces — a stage above 0, a moved trail anchor, a
    ladder, a part-filled leg.
    """
    ex._pos_dir = direction
    ex._entry_kind = "primary"
    ex._qty = qty
    ex._entry = entry
    ex._entry_index = 4_812
    ex._entry_ms = 1_754_000_000_000
    ex._init_stop = stop
    ex._sl = stop
    ex._tp1, ex._tp2 = 3305.0, 3315.0
    ex._stage = stage
    ex._max_fav = 3301.5
    ex._trail_swing_hi, ex._trail_swing_lo = 3302.0, 3281.0
    ex._ext_high, ex._ext_low = 3303.0, 3286.0
    ex._risk_usd = abs(entry - stop) * qty
    ex._entry_equity = 10_000.0
    ex._sos_bar_open = 4_800
    ex._traded_sos_l = 4_800
    ex._fib = TradeFib(levels=[(0.5, 3300.0), (0.886, 3279.0)], start_ms=1_753_900_000_000)
    ex._legs = [{"rung": "tp1", "qty": 0.5, "price": 3305.0}]
    return ex


# ── the field set ────────────────────────────────────────────────────────────


def test_the_snapshot_covers_every_field_open_position_assigns():
    """DERIVED from `_open_position`'s own source, never hand-listed.

    A hand-written list would re-freeze exactly the assumption that fails. The failure mode this
    catches is silent and expensive: a field left out is restored at its constructor default, so
    a zero `_max_fav` un-ratchets the trail and a zero `_stage` puts a breakeven stop back to the
    full stop. Nothing raises; the trade is just managed differently from the one that was open.
    """
    src = inspect.getsource(Execution._open_position)
    assigned = set(re.findall(r"^\s+self\.(_[a-z0-9_]+)\s*=", src, re.MULTILINE))

    # `_pend_*` are the RESTING ORDERS, cleared by `_open_position` because a position is now
    # open. `restore_position` clears them for the same reason, so they are covered by behaviour
    # rather than by being carried — pinned below in its own test.
    assigned -= {"_pend_long", "_pend_short", "_pend_sec"}

    missing = assigned - set(Execution._POSITION_FIELDS)
    assert not missing, (
        f"`_open_position` assigns {sorted(missing)} and `_POSITION_FIELDS` does not carry them, "
        f"so a restarted bot would manage the trade with those at their DEFAULTS. Add each to "
        f"`Execution._POSITION_FIELDS`."
    )


def test_the_snapshot_carries_the_traded_leg_latch():
    """Not assigned by `_open_position` itself, so the derived test above cannot see it.

    Without it a restored bot could re-enter the very setup it is already holding, the moment
    this trade closes — the one-trade-per-15m-leg rule silently switched off by a restart.
    """
    assert "_traded_sos_l" in Execution._POSITION_FIELDS
    assert "_traded_sos_s" in Execution._POSITION_FIELDS


# ── round trip ───────────────────────────────────────────────────────────────


def test_a_snapshot_restores_every_field_to_the_same_value():
    a = _open(_ex(), stage=2)
    snap = a.snapshot_position()

    b = _ex()
    b.restore_position(snap)

    for name in Execution._POSITION_FIELDS:
        assert getattr(b, name) == getattr(a, name), f"{name} did not survive the round trip"


def test_the_fib_ladder_survives_as_a_real_TradeFib_not_a_dict():
    """It is reporting-only, and it still has to come back as the type the closed `Trade` expects
    — a dict here would raise on the exit, i.e. at the worst possible moment."""
    a = _open(_ex())
    b = _ex()
    b.restore_position(a.snapshot_position())
    assert isinstance(b._fib, TradeFib)
    assert b._fib.levels == a._fib.levels
    assert b._fib.start_ms == a._fib.start_ms


def test_a_trade_with_no_recorded_fib_round_trips_as_None():
    """`_freeze_fib` is all-or-nothing and legitimately returns None, so None is a real state
    rather than a missing value — it must not become an empty ladder."""
    a = _open(_ex())
    a._fib = None
    b = _ex()
    b.restore_position(a.snapshot_position())
    assert b._fib is None


def test_the_snapshot_is_plain_json_types():
    """It is written to disk as JSON. A dataclass or a tuple in here fails at `json.dump`, on the
    bar a real trade opened — so it is asserted rather than left to the first live fill."""
    import json

    snap = _open(_ex()).snapshot_position()
    json.loads(json.dumps(snap))  # raises if anything in there is not serialisable


def test_a_pending_close_survives_as_a_tuple():
    """A force-close decided at one bar's close fills at the NEXT bar's open. If the process dies
    in between, the broker still holds the position and the decision must not be lost — it would
    read as a trade the time stop never cut."""
    a = _open(_ex())
    a._pending_close = ("L-TIME", "primary")
    b = _ex()
    b.restore_position(a.snapshot_position())
    assert b._pending_close == ("L-TIME", "primary")


# ── the refusals ─────────────────────────────────────────────────────────────


def test_restoring_an_incomplete_record_REFUSES_rather_than_defaulting():
    """The whole safety property. A record missing `_stage` is not "a trade at stage 0" — it is a
    record we cannot trust, and managing a real position against a guess is the failure this
    exists to end. The caller halts, which is what the bot did before any of this existed."""
    snap = _open(_ex(), stage=2).snapshot_position()
    del snap["_stage"]

    b = _ex()
    with pytest.raises(ValueError) as e:
        b.restore_position(snap)
    assert "_stage" in str(e.value)
    assert b._pos_dir == 0, "it must not half-apply a record it refused"


def test_snapshotting_while_flat_is_an_error_not_an_empty_record():
    """An empty record would read back as a real position at zero size and zero price. Refusing
    keeps "there is no open trade" and "here is a trade with nothing in it" apart."""
    with pytest.raises(ValueError):
        _ex().snapshot_position()


def test_restore_clears_the_resting_limits():
    """A position is open, so the strategy holds no pending entry — and `algos/live/bridge.py`
    cancels every stale broker-side order at startup for the same reason. Leaving one here would
    have the emulator believing in an order the broker no longer has."""
    b = _ex()
    b._pend_long = object()
    b._pend_short = object()
    b._pend_sec = object()
    b.restore_position(_open(_ex()).snapshot_position())
    assert b._pend_long is None and b._pend_short is None and b._pend_sec is None


# ── it changes nothing about a backtest ──────────────────────────────────────


def test_nothing_in_the_bar_path_calls_either_method():
    """Parity is structurally unaffected, and that is checked rather than asserted: if `step` or
    `step_secondary` ever reached for one of these, a lab replay and the Pine would part company
    and `compare_strategy.py` would be the thing that found out."""
    for fn in (Execution.step, Execution.step_secondary, Execution._manage_open):
        src = inspect.getsource(fn)
        assert "snapshot_position" not in src
        assert "restore_position" not in src
