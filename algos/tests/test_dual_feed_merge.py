"""The live runner's SECOND bar feed must read the same 15m context the lab does, bar for bar.

🔴 **WHY THIS FILE EXISTS.** `docs/LIVE_TRADING_PIPELINE.md` G18 stage 1 adds a second bar stream
to the live runner so the re-entry can eventually run live. The merge — *which bar is stepped
when* — is the part that is easy to get wrong and impossible to see afterwards: a fast bar
stepped against the wrong 15m context produces a perfectly ordinary-looking trade at a slightly
wrong price, for ever, with nothing in any output able to show it. So the rule has ONE
implementation (`strategies/python/mpc_sos_fade/dual_clock.DualClock`, driven by the lab's
`run_dual` and by this runner alike) and these tests pin the live driver to it.

⚠ **The lab and the live driver receive bars DIFFERENTLY, and that is the whole risk.** The lab
has both frames complete and pushes every 15m bar before it steps a single fast one. Live, two
feeds poll independently, a 15m bar is stepped the MOMENT it closes (the primary must never wait
on the re-entry's feed), and a fast bar can arrive late. Every test below is about a way those
two could disagree.

**Watched RED by mutation** — each test names the mutation that reddens it in its own docstring.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

WARNINGS = []

# MetaTrader5 is Windows-only and imported lazily inside `_tf_const`. A stub keeps this file
# runnable on the Mac, which is where these tests actually get run.
sys.modules.setdefault(
    "MetaTrader5",
    types.SimpleNamespace(
        TIMEFRAME_M1=1,
        TIMEFRAME_M5=5,
        TIMEFRAME_M15=15,
        TIMEFRAME_M30=30,
        TIMEFRAME_H1=60,
        TIMEFRAME_H4=240,
        TIMEFRAME_D1=1440,
    ),
)

_REPO = Path(__file__).resolve().parent.parent.parent
for p in (
    str(_REPO),
    str(_REPO / "algos" / "live"),
    str(_REPO / "algos" / "shared"),
    str(_REPO / "strategies" / "python"),
):
    if p not in sys.path:
        sys.path.insert(0, p)

from feed import timeframe_for_minutes  # noqa: E402
from runner import LiveRunner, _SingleFeedClock  # noqa: E402

TF15, TF5 = 900_000, 300_000


# ── frames ───────────────────────────────────────────────────────────────────
#
# The 15m CLOSE of each bar is its own index, so "which primary bar was this fast bar's context"
# is readable straight off `clock.last_close_primary`. That is the whole trick that makes the
# merge order observable at all — with flat prices the two drivers agree trivially and prove
# nothing.
def _frames(n15=40):
    i15 = pd.date_range("2026-05-01", periods=n15, freq="15min", tz="UTC")
    df15 = pd.DataFrame(
        {"open": 1.0, "high": 2.0, "low": 0.5, "close": [float(i) for i in range(n15)]},
        index=i15,
    )
    i5 = pd.date_range("2026-05-01", periods=n15 * 3, freq="5min", tz="UTC")
    df5 = pd.DataFrame(
        {"open": 1.0, "high": 2.0, "low": 0.5, "close": [1000.0 + i for i in range(n15 * 3)]},
        index=i5,
    )
    return df15, df5


def _bars(df):
    from backtest.replay import iter_bars

    return list(iter_bars(df))


def _clock(strategy=None):
    """A `DualClock` over a stub strategy — the merge needs no engines to be exercised."""
    from mpc_sos_fade.dual_clock import DualClock

    st = strategy or _stub_strategy()
    stack = SimpleNamespace(step=lambda bar: SimpleNamespace(bar=bar))
    return DualClock(st, stack, tf_primary_ms=TF15, major_length=15)


def _stub_strategy(secondary=False):
    """A strategy shaped like the real one, with the secondary OFF by default.

    ⚠ With it off, `step_fast` still updates the fast structure feed and still flushes primaries
    — which is exactly the half these tests are about. Turning it on would drag the whole arm
    state machine in and test something else.
    """
    cfg = SimpleNamespace(exec_secondary=secondary)
    return SimpleNamespace(
        config=cfg,
        signals=SimpleNamespace(update=lambda s: SimpleNamespace(bar=s.bar)),
        sequence=SimpleNamespace(update=lambda s: SimpleNamespace()),
        execution=SimpleNamespace(step=lambda sig, seq: SimpleNamespace()),
    )


# ── the merge order ──────────────────────────────────────────────────────────
# WARM = how many 15m bars are replayed before either driver starts recording. A real bot warms
# both feeds before its first poll, so the pairing only means anything from that boundary on —
# the same restriction `algos/tools/shadow_diff.py` puts on a live-vs-lab comparison, and for the
# same reason: a warm-up is a deliberate difference, and everything after it is not.
WARM = 4


def _lab_pairing(df15, df5, boundary):
    """`run_dual`'s order: every primary pushed first, then each fast bar stepped."""
    clock = _clock()
    for b in _bars(df15):
        clock.push_primary(b)
    out = []
    for b in _bars(df5):
        clock.step_fast(b)
        if b.timestamp_ms >= boundary:
            out.append((b.timestamp_ms, clock.last_close_primary))
    return out


class _FakeFeed:
    """Hands out bars whose CLOSE has passed the harness clock — what MT5 does, minus the lies."""

    def __init__(self, df, secs, timeframe, clock):
        self.df, self.bar_seconds, self.timeframe = df, secs, timeframe
        self._clock = clock
        self.i = 0
        self.last_bar_time = None
        self.closes = [int(t.value // 1_000_000) + secs * 1000 for t in df.index]

    def _upto(self):
        j = 0
        while j < len(self.df) and self.closes[j] <= self._clock[0]:
            j += 1
        return j

    def new_bars(self, lookback=5):
        j = self._upto()
        out = self.df.iloc[self.i : j]
        self.i = j
        if len(out) and self.last_bar_time is not None:
            out = out[out.index > self.last_bar_time]
        if len(out):
            self.last_bar_time = out.index[-1]
        return out

    def gap_bars(self):
        return 0  # holes have their own tests; this one is about ORDER

    def history(self, n):
        j = self._upto()
        self.i = j
        return self.df.iloc[max(0, j - n) : j]

    def mark_seen(self, df):
        if len(df):
            self.last_bar_time = df.index[-1]


def _live_pairing(df15, df5, boundary):
    """The LIVE order — driven through the REAL `LiveRunner` methods, not a copy of them.

    🔴 **Driving the runner rather than re-creating its loop is the point.** An earlier version of
    this harness reimplemented the poll order beside the code it was checking, and it kept finding
    its own bugs while missing the real one's: the session-gap defect below is invisible to a
    harness that has its own idea of when a bar is steppable.
    """
    now = [0]
    r = LiveRunner.__new__(LiveRunner)
    r.cfg = SimpleNamespace(warmup_bars=WARM, timeframe="M15", symbol="X", display_name="x")
    r.log = SimpleNamespace(
        info=lambda *a, **k: None,
        warning=lambda *a, **k: WARNINGS.append(a),
        error=lambda *a, **k: WARNINGS.append(a),
    )
    r.ledger = SimpleNamespace(event=lambda *a, **k: None, bar=lambda *a, **k: None)
    r.strategy = _stub_strategy()
    r.setup_alerts = None
    r.bridge = None
    r._bar_index = 0
    r._fast_index = 0
    r._fast_pending = []
    r._fast_stale_alerted = False
    r._settle_primary = lambda ps: None
    r._drain_records = lambda: None
    r._notify_health = lambda *a, **k: None
    r.feed = _FakeFeed(df15, 900, "M15", now)
    r.fast_feed = _FakeFeed(df5, 300, "M5", now)
    r.stack = SimpleNamespace(step=lambda bar: SimpleNamespace(bar=bar))
    r.clock = _clock(r.strategy)
    # A bridge that answers and does nothing. These tests are about the MERGE ORDER, not about
    # orders reaching a broker — but production has never reached `_observe_secondary` without a
    # bridge (it is built in `_run`, before the loop that pumps a single fast bar), so the
    # harness must have one too. ⚠ A `self.bridge is not None` guard in the runner was the other
    # way to make this pass and is the WRONG one: it would encode "the bridge might be missing"
    # into the money path, and a missing bridge would then silently place nothing while the
    # emulator filled — the exact divergence that halts a bot.
    r.bridge = SimpleNamespace(sync_fast=lambda step: None, dry_run=True)

    seen = []
    real_step = r.clock.step_fast

    def _record(bar):
        out = real_step(bar)
        seen.append((bar.timestamp_ms, r.clock.last_close_primary))
        return out

    # Warm exactly as `warm()` does: the whole primary history, then the fast side.
    for b in _bars(df15)[:WARM]:
        r.clock.push_primary(b)
        r.clock.drain_primary()
    r._bar_index = WARM - 1
    r.feed.mark_seen(df15.iloc[:WARM])
    r.feed.i = WARM
    now[0] = boundary
    r._warm_fast()
    r.clock.step_fast = _record

    events = sorted({c for f in (r.feed, r.fast_feed) for c in f.closes if c >= boundary})
    for ms in events:
        now[0] = ms
        r._check_fast_feed()
        r._pump_fast()
        for _, row in r.feed.new_bars().iterrows():
            r._on_bar(row)
    return seen


def _boundary(df15):
    """The instant the warm-up leaves the 15m context at."""
    return _bars(df15)[WARM - 1].timestamp_ms + TF15


def test_the_live_merge_reads_the_same_15m_context_as_run_dual_bar_for_bar():
    """THE claim of G18 stage 1, stated as the thing that could be wrong.

    Each pair is (fast bar's open, the 15m close it read as context). The lab and the live
    driver receive bars in genuinely different orders, so agreeing here is a real result.

    MUTATION: swap the two `while` blocks in `_live_pairing` so the primary is pushed before the
    fast bars are pumped — i.e. do in the harness what reversing those two lines in `_loop` would
    do — and 39 of 120 pairs read a context one 15m bar into their own future.
    """
    df15, df5 = _frames()
    b = _boundary(df15)
    lab, live = _lab_pairing(df15, df5, b), _live_pairing(df15, df5, b)
    assert len(live) > 50, "the live driver stepped too few fast bars — the harness proves nothing"
    assert live == lab, (
        f"the two drivers disagree about which 15m bar a fast bar reads.\n"
        f"lab : {lab[:6]}\nlive: {live[:6]}"
    )


def test_a_fast_bar_never_reads_a_context_from_its_own_future():
    """The invariant underneath the test above, stated without reference to the lab.

    A fast bar opening at X may only read a 15m bar that CLOSED at or before X. This is the
    property a merge bug destroys, and it is checkable on the live pairing alone.

    MUTATION: make `can_step_fast` return True unconditionally and 39 pairs break it.
    """
    df15, df5 = _frames()
    closes = {float(i): b.timestamp_ms + TF15 for i, b in enumerate(_bars(df15))}
    for fast_open, ctx_close in _live_pairing(df15, df5, _boundary(df15)):
        assert closes[ctx_close] <= fast_open, (
            f"a fast bar opening at {fast_open} read the 15m bar closing at {closes[ctx_close]} — "
            f"a context from its own future"
        )


def test_a_fast_bar_that_arrives_late_is_REFUSED_not_stepped():
    """A fast bar whose slot has passed cannot be stepped honestly, so it raises.

    ⚠ It is the live-only case by construction: the lab pushes every primary before it steps a
    fast bar, so its context can never be ahead of one.

    MUTATION: drop the `fast_bar_is_stale` check at the top of `step_fast` and no exception is
    raised — the bar is stepped against a context 15 minutes into its future.
    """
    clock = _clock()
    b15, b5 = _bars(_frames()[0]), _bars(_frames()[1])
    clock.push_primary(b15[0])
    clock.push_primary(b15[1])
    clock.drain_primary()  # context now at b15[1].close
    late = b5[0]  # opens before b15[1] even started
    assert clock.fast_bar_is_stale(late.timestamp_ms)
    with pytest.raises(clock.OutOfOrder):
        clock.step_fast(late)


def test_a_fast_bar_opening_exactly_AT_the_context_close_is_NOT_late():
    """The boundary, and it is the one an off-by-one would get wrong in the expensive direction.

    A 15m bar closing at X and a fast bar opening at X: the merge flushes that 15m bar IN FRONT
    of that fast bar, so the fast bar is the next one due, never a late one. Refusing it would
    throw away a bar on every single 15m boundary.

    MUTATION: change `fast_bar_is_stale`'s `<` to `<=` and this goes red.
    """
    clock = _clock()
    b15 = _bars(_frames()[0])
    clock.push_primary(b15[0])
    clock.drain_primary()
    edge = b15[0].timestamp_ms + TF15
    assert not clock.fast_bar_is_stale(edge)
    assert clock.fast_bar_is_stale(edge - 1)


def test_nothing_steps_before_the_first_primary_bar():
    """`can_step_fast` refuses while no primary has been pushed — *cannot tell* is not *yes*.

    With nothing pushed there is no way to know whether a primary belongs in front of this fast
    bar. Live that state exists only before the warm-up, which pushes the whole primary history.

    MUTATION: return True when `_covered_to_ms is None` and this goes red.
    """
    clock = _clock()
    assert clock.can_step_fast(0) is False
    assert clock.can_step_fast(10**13) is False


def _frames_with_a_break(n15=40, gap_after=12, gap_bars=8):
    """The same frames with a DAILY BREAK cut out of both feeds — gold stops for an hour.

    The two frames stay consistent with each other: the same wall-clock window is missing from
    both, which is what a real session break looks like.
    """
    df15, df5 = _frames(n15)
    cut_from = df15.index[gap_after]
    cut_to = df15.index[gap_after + gap_bars]
    keep15 = (df15.index < cut_from) | (df15.index >= cut_to)
    keep5 = (df5.index < cut_from) | (df5.index >= cut_to)
    return df15[keep15], df5[keep5]


def test_a_SESSION_BREAK_does_not_strand_a_fast_bar():
    """🔴 THE DEFECT THIS FILE'S HARDEST FIX EXISTS FOR — found on real bars, not by reasoning.

    `can_step_fast` answers *has the 15m stream reached this fast bar*, and the only cheap live
    answer is *one primary bar past what has been pushed* — which assumes primary bars are
    CONTIGUOUS. Gold breaks daily. Across the break the next 15m bar is not one bar later, so a
    queued fast bar was still waiting when the post-break primary was pushed, and the eager drain
    then moved the context past it: **stale, once per trading day.** MEASURED on a three-month
    replay before the fix: 13 forced re-warms, one per day.

    ✅ `LiveRunner.flush_fast_before` fixes it by asking the merge rule directly — *does this bar
    open before the primary I am about to push* — which needs no assumption about spacing at all.

    MUTATION: delete the `flush_fast_before` call in `_on_bar` and this goes red with a re-warm
    warning per break, and the pairing loses the bars the re-warm threw away.
    """
    df15, df5 = _frames_with_a_break()
    b = _boundary(df15)
    WARNINGS.clear()
    live = _live_pairing(df15, df5, b)
    lab = _lab_pairing(df15, df5, b)
    assert not WARNINGS, (
        f"a session break forced {len(WARNINGS)} re-warm(s) of the fast feed: {WARNINGS[:2]}"
    )
    assert live == lab, "the merge disagreed with the lab across a session break"


# ── the runner's own wiring ──────────────────────────────────────────────────
def test_a_bot_with_no_reentry_gets_the_single_feed_clock_and_the_old_primary_path():
    """A bot with the re-entry OFF must keep the path it has always had.

    That is what makes G18 shippable in stages: nothing about the LIVE bot changes until the
    re-entry is deliberately turned on.

    MUTATION: make `_make_clock` always ask the strategy and this goes red for a strategy with
    no second feed.
    """
    r = LiveRunner.__new__(LiveRunner)
    r.fast_feed = None
    r.strategy = _stub_strategy()
    r.stack = SimpleNamespace(step=lambda bar: SimpleNamespace(bar=bar))
    assert isinstance(r._make_clock(), _SingleFeedClock)


def test_the_single_feed_clock_steps_a_primary_bar_the_moment_it_is_pushed():
    """The degenerate case still has to answer the one question a clock is asked."""
    clock = _SingleFeedClock(
        _stub_strategy(), SimpleNamespace(step=lambda b: SimpleNamespace(bar=b))
    )
    b = _bars(_frames()[0])[0]
    clock.push_primary(b)
    out = clock.drain_primary()
    assert len(out) == 1 and out[0].bar is b
    assert clock.can_step_fast(b.timestamp_ms) is False, "there is no fast feed to step"


def test_a_fill_clock_MT5_has_no_timeframe_for_is_REFUSED_not_rounded():
    """A 7-minute fill clock served as 5m or 10m is a strategy replayed on a stream nobody chose.

    MUTATION: return the nearest timeframe instead of raising and this goes red.
    """
    assert timeframe_for_minutes(5) == "M5"
    assert timeframe_for_minutes(15) == "M15"
    with pytest.raises(ValueError, match="No MT5 timeframe is 7 minutes"):
        timeframe_for_minutes(7)


def test_a_fill_clock_that_is_not_faster_than_the_primary_is_REFUSED():
    """A re-entry fills INSIDE a 15m bar, so a 15m or slower second feed cannot express one.

    ⚠ It refuses at STARTUP rather than running a second feed that can never help — the same
    call `assert_supported` makes, one layer down.

    MUTATION: drop the comparison and a 15m 'fill clock' is accepted, giving two identical feeds.
    """
    r = LiveRunner.__new__(LiveRunner)
    r.cfg = SimpleNamespace(timeframe="M15", symbol="XAUUSD.p")
    r.feed = SimpleNamespace(bar_seconds=900)
    r.mt5 = SimpleNamespace(symbol="XAUUSD.p")
    r.log = SimpleNamespace(info=lambda *a, **k: None)
    r.strategy = SimpleNamespace(fast_feed_minutes=lambda: 15)
    with pytest.raises(RuntimeError, match="not FASTER"):
        r._build_fast_feed(SimpleNamespace(exec_secondary=True))


def test_a_strategy_that_wants_no_second_feed_gets_None_rather_than_a_refusal():
    """`None` is *this configuration does not want one*. It must never mean *could not have one*
    — an impossible fill clock raises, loudly, at startup."""
    r = LiveRunner.__new__(LiveRunner)
    r.strategy = SimpleNamespace(fast_feed_minutes=lambda: None)
    assert r._build_fast_feed(SimpleNamespace(exec_secondary=False)) is None

    r.strategy = SimpleNamespace()  # a strategy with no opinion at all
    assert r._build_fast_feed(SimpleNamespace(exec_secondary=True)) is None


# ── the bridge is actually driven (G18 stage 2) ─────────────────────────────


class _RecordingBridge:
    def __init__(self, dry_run):
        self.dry_run = dry_run
        self.steps: list = []

    def sync_fast(self, step):
        self.steps.append(step)


class _CountingLedger:
    def __init__(self):
        self.names: list = []

    def event(self, name, **kw):
        self.names.append(name)


def _observer(dry_run):
    """A runner with only the three attributes `_observe_secondary` reads.

    ⚠ The REAL method is called, unbound from the real class. Re-creating it here is how a
    harness ends up testing itself — this file's own stage-1 notes record that trap.
    """
    r = LiveRunner.__new__(LiveRunner)
    r.bridge = _RecordingBridge(dry_run)
    r.ledger = _CountingLedger()
    r.log = SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None)
    return r


def _armed_step(bar):
    return SimpleNamespace(
        bar=bar,
        primaries=[],
        arm=SimpleNamespace(l_src="fvg", s_src=None),
        filled_dir=1,
        stopped_dir=None,
    )


def test_every_fast_bar_reaches_the_bridge_even_when_nothing_is_armed():
    """The bridge has to see EVERY fast bar, not only the interesting ones: a resting order it
    placed two bars ago is cancelled by a bar on which nothing arms.

    MUTATION: move the `self.bridge.sync_fast(step)` call below the `if step.arm is None: return`
    and this goes red — the bridge stops being told about the quiet bars, which is most of them.
    """
    r = _observer(dry_run=True)
    bar = _bars(_frames()[1])[0]

    r._observe_secondary(
        SimpleNamespace(bar=bar, primaries=[], arm=None, filled_dir=None, stopped_dir=None)
    )

    assert len(r.bridge.steps) == 1
    assert r.ledger.names == [], "a bar with nothing armed wrote a record"


def test_a_shadow_record_is_written_on_a_DRY_RUN_and_never_beside_a_real_order():
    """🔴 The narrowing stage 2 forces. `secondary_shadow_fill` says *nothing was sent to the
    broker*, which was true of every run while the bridge placed nothing. It places now, so on a
    live bot that sentence is false — and the record would sit in the ledger beside the real
    `trade_opened` the bridge writes from the broker's own answer, putting one trade in the book
    twice.

    MUTATION: drop the `if not self.bridge.dry_run: return` guard and the live half goes red with
    a shadow record for a trade that really happened.
    """
    bar = _bars(_frames()[1])[0]

    dry = _observer(dry_run=True)
    dry._observe_secondary(_armed_step(bar))
    assert dry.ledger.names == ["secondary_shadow_fill"]

    live = _observer(dry_run=False)
    live._observe_secondary(_armed_step(bar))
    assert live.ledger.names == [], "a shadow record was written beside a real order"
    assert len(live.bridge.steps) == 1, "the bridge was not driven"
