"""The fast-frame INTERNAL change-of-character feed (`InternalShift1m`).

🔴 **The defect these tests exist to catch is the feed reading the wrong events.**
`Structure1m` and `InternalShift1m` run the same engine on the same bars and differ only in
which half of its output they read. A copy-paste that leaves the external read in place
produces a feed that works, streams, and answers a different question than its name — the
kind of mistake nothing downstream can show you afterwards.

⚠ **The bars are a SEEDED random walk, not a hand-built fixture.** A fixture shaped to make one
event fire would prove only that the event can fire; the question here is whether the two feeds
disagree across an ordinary stretch of price, which needs a stretch of price. The seed pins it,
so this is deterministic.
"""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sos_fade.secondary import InternalShift1m, Structure1m  # noqa: E402


def _walk(n=3000, seed=7):
    rnd = random.Random(seed)
    px = 2000.0
    for i in range(n):
        px += rnd.gauss(0, 1.2)
        o = px
        c = px + rnd.gauss(0, 0.8)
        h = max(o, c) + abs(rnd.gauss(0, 0.6))
        lo = min(o, c) - abs(rnd.gauss(0, 0.6))
        yield i, o, h, lo, c


def _streams():
    ext, internal = Structure1m(), InternalShift1m()
    e_bars, i_bars = [], []
    for i, o, h, lo, c in _walk():
        se = ext.update(i, o, h, lo, c)
        si = internal.update(i, o, h, lo, c)
        if se.new_bull_sos or se.new_bear_sos:
            e_bars.append(i)
        if si.new_bull or si.new_bear:
            i_bars.append(i)
    return e_bars, i_bars


def test_the_internal_feed_is_not_the_external_one_reading_a_different_name():
    """The whole point of the class. Both feeds fire over the same 3,000 bars and they fire on
    DIFFERENT bars — 17 external against 12 internal, with no bar in common.

    Watched RED by mutation: pointing `InternalShift1m.update` at `st.external` (the copy-paste
    this test is about) makes the two streams identical and fails the disagreement assertion."""
    e_bars, i_bars = _streams()
    assert e_bars, "external feed fired on no bar — the walk exercises neither feed"
    assert i_bars, "internal feed fired on no bar — every assertion below would be vacuous"
    assert set(e_bars) != set(i_bars)
    assert not (set(e_bars) & set(i_bars))


def test_the_internal_feed_reports_a_price_on_every_bar_it_fires():
    """A fired event with no price is the `None`-means-two-things defect (rule 1): a consumer
    cannot tell "the engine published no level" from "nothing fired". The bar and price are
    reporting-only and the bear bar is KNOWN wrong at 22 of 25 breaks — but they must still be
    present, because a study that drops them cannot later notice they were missing."""
    feed = InternalShift1m()
    fired = 0
    for i, o, h, lo, c in _walk():
        st = feed.update(i, o, h, lo, c)
        if st.new_bull:
            fired += 1
            assert st.bull_price is not None
        if st.new_bear:
            fired += 1
            assert st.bear_price is not None
    assert fired == 12


def test_a_quiet_bar_reports_nothing_fired():
    """The other half of the same distinction — no event means every flag is False, never a
    stale latch from an earlier bar. This feed deliberately does NOT latch, unlike
    `Structure1m`, because the study asks 'did a shift print on THIS bar'."""
    feed = InternalShift1m()
    seen_quiet = False
    for i, o, h, lo, c in _walk(n=400):
        st = feed.update(i, o, h, lo, c)
        if not st.new_bull and not st.new_bear:
            seen_quiet = True
            assert st.bull_price is None and st.bear_price is None
            assert st.bull_loc is None and st.bear_loc is None
    assert seen_quiet
