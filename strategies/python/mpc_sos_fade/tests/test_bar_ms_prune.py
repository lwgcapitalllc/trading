"""The bar-number -> bar-time map prunes in O(1), and keeps the SAME keys the sort kept.

🔴 **Why this file exists.** The map's first version re-sorted all 20,000 keys to delete ONE,
on every bar past the cap — MEASURED at 8.0s of a 52.6s one-year replay (15%), and the 6.6-year
window pays it 135,807 times. The fast path relies on a dict preserving INSERTION order and on
indices arriving in ascending order, so what has to be pinned is not the speed but that **the
surviving key set is identical either way** — a prune that drops a different bar changes what
`_same_leg` can answer, and that gates whether a setup may be traded again.

Watched RED by mutation, each named in its own test.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from strategies.python.mpc_sos_fade.config import SosFadeConfig
from strategies.python.mpc_sos_fade.execution import Execution


def _ex(monkeypatch, keep=8):
    """An Execution with a small cap, so the prune is exercised in a few bars rather than 20,000."""
    monkeypatch.setattr(Execution, "_BAR_MS_KEEP", keep)
    return Execution(SosFadeConfig())


def _feed(ex, indices):
    for i in indices:
        # time_ms is derived from the index so a key's value identifies which bar wrote it.
        ex._remember_bar(SimpleNamespace(index=i, time_ms=1_000 + i * 60_000))


def _sorted_prune(pairs, keep):
    """What the ORIGINAL implementation kept: the numerically-largest `keep` keys."""
    d = {}
    for k, v in pairs:
        d[k] = v
        if len(d) > keep:
            for dead in sorted(d)[: len(d) - keep]:
                del d[dead]
    return d


def test_under_the_cap_nothing_is_pruned(monkeypatch):
    ex = _ex(monkeypatch, keep=8)
    _feed(ex, range(5))
    assert sorted(ex._bar_ms) == [0, 1, 2, 3, 4]


def test_at_the_cap_exactly_the_cap_is_held(monkeypatch):
    ex = _ex(monkeypatch, keep=8)
    _feed(ex, range(8))
    assert len(ex._bar_ms) == 8


def test_past_the_cap_it_keeps_the_RECENT_tail(monkeypatch):
    """🔴 The load-bearing one. Mutation: `next(iter(...))` -> `max(...)` keeps the oldest
    instead of the newest and reddens this immediately."""
    ex = _ex(monkeypatch, keep=8)
    _feed(ex, range(20))
    assert sorted(ex._bar_ms) == list(range(12, 20))
    assert len(ex._bar_ms) == 8


def test_the_fast_path_keeps_the_IDENTICAL_KEYS_the_sort_kept(monkeypatch):
    """The claim the speed-up rests on, asserted against the original algorithm rather than
    against a hand-written expectation — a constant typed here would just re-freeze my own
    reading of it."""
    ex = _ex(monkeypatch, keep=8)
    idx = list(range(50))
    _feed(ex, idx)
    want = _sorted_prune([(i, 1_000 + i * 60_000) for i in idx], 8)
    assert ex._bar_ms == want


def test_the_VALUES_survive_the_prune_not_just_the_keys(monkeypatch):
    """A prune that kept the right keys against the wrong times would leave `_same_leg`
    comparing a bar to another bar's timestamp, which is the whole failure it exists to stop."""
    ex = _ex(monkeypatch, keep=4)
    _feed(ex, range(10))
    for i in range(6, 10):
        assert ex._bar_ms[i] == 1_000 + i * 60_000


def test_it_stays_ORDERED_through_an_ordinary_run(monkeypatch):
    ex = _ex(monkeypatch, keep=8)
    _feed(ex, range(30))
    assert ex._bar_ms_ordered is True


def test_an_OUT_OF_ORDER_index_latches_the_flag_and_the_sort_takes_over(monkeypatch):
    """🔴 The safety net. Mutation: drop the `idx <= self._bar_ms_last` latch and the fast path
    runs on a map whose insertion order is no longer its numeric order — this reddens, because
    the numerically-smallest key is then no longer the one at the front."""
    ex = _ex(monkeypatch, keep=4)
    _feed(ex, [10, 11, 12, 13])
    _feed(ex, [1])  # a lower index than everything already held
    assert ex._bar_ms_ordered is False
    _feed(ex, [14, 15])
    # The sort keeps the numerically-largest four, which is what the original did.
    assert sorted(ex._bar_ms) == [12, 13, 14, 15]


def test_the_latch_STAYS_off_once_it_has_fired(monkeypatch):
    """Deliberately one-way. Re-arming it would mean deciding, per bar, that the map had become
    ordered again — a second claim about the same thing, and the sort is correct at any order."""
    ex = _ex(monkeypatch, keep=4)
    _feed(ex, [10, 11, 1])
    assert ex._bar_ms_ordered is False
    _feed(ex, range(20, 40))
    assert ex._bar_ms_ordered is False


def test_a_repeated_index_counts_as_out_of_order(monkeypatch):
    """A re-inserted key keeps its ORIGINAL position in a dict, so insertion order and numeric
    order part company the moment one repeats — even though nothing moved backwards."""
    ex = _ex(monkeypatch, keep=4)
    _feed(ex, [5, 6, 6])
    assert ex._bar_ms_ordered is False


def test_a_bar_with_no_time_is_not_recorded_and_does_not_move_the_latch(monkeypatch):
    """`None` means the feed did not carry one. Recording it would put a bar in the map with no
    time against it, which is exactly the not-measured/measured-zero collapse this repo refuses."""
    ex = _ex(monkeypatch, keep=8)
    _feed(ex, [1, 2])
    ex._remember_bar(SimpleNamespace(index=3, time_ms=None))
    assert 3 not in ex._bar_ms
    assert ex._bar_ms_last == 2
    assert ex._bar_ms_ordered is True


def test_same_leg_still_answers_by_TIME_after_a_prune(monkeypatch):
    """The prune is only correct if the map still identifies a recent leg — that is what the
    whole map is for (`_same_leg`, the one-trade-per-leg latch across a restart)."""
    ex = _ex(monkeypatch, keep=4)
    _feed(ex, range(10))
    assert ex._same_leg(traded_bar=None, traded_ms=1_000 + 9 * 60_000, current_bar=9) is True
    assert ex._same_leg(traded_bar=None, traded_ms=1_000 + 8 * 60_000, current_bar=9) is False


def test_a_leg_that_fell_off_the_tail_FALLS_BACK_to_the_bar_number(monkeypatch):
    """Pruned means the time is unknown, not that the answer is no. The fallback is the old
    behaviour and is documented as wrong across a restart; it is pinned so a later prune change
    cannot silently disable the latch instead."""
    ex = _ex(monkeypatch, keep=4)
    _feed(ex, range(10))
    assert 2 not in ex._bar_ms
    assert ex._same_leg(traded_bar=2, traded_ms=1_000 + 2 * 60_000, current_bar=2) is True


@pytest.mark.parametrize("keep", [1, 2, 7, 13])
def test_it_holds_at_any_cap(monkeypatch, keep):
    ex = _ex(monkeypatch, keep=keep)
    idx = list(range(40))
    _feed(ex, idx)
    assert ex._bar_ms == _sorted_prune([(i, 1_000 + i * 60_000) for i in idx], keep)
