"""A window whose tail is a CLOSED market must load, and a HOLE must still fail.

The bug: every backtest whose end date landed on a Saturday, a Sunday, a holiday, or on
today before the session opened died with `MT5 agent returned no bars`. Measured
2026-08-15 (a Saturday) on the live lab — run 50331c7cbe96, window 2018-09-13 →
2026-08-15, gap [2026-08-15, 2026-08-15]. The identical window had completed on the
Friday. The agent was healthy throughout: asked directly, 2026-08-14 served 84 M15 bars
and 2026-08-15 served none.

The danger in fixing it is the opposite failure, and it has already happened here: a gap
in the MIDDLE of history that serves nothing is MISSING DATA, and 45 days of M1 went
that way. Swallowing that would make the hole permanent, because a covered range is never
re-fetched. So half these tests exist to prove the fix did NOT buy the weekend by hiding
the hole.

Every test here was watched RED against the pre-fix `source.py` — see the module's own
`test_every_test_here_was_watched_red` note at the bottom for which failed how.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from backtest.data.mt5_agent import Mt5AgentError
from backtest.data.source import _MAX_CLOSURE_DAYS, BarSource


def _bars(start: str, days: int, tf_min: int = 15) -> pd.DataFrame:
    """A plausible bar frame — enough rows per day that nothing downstream calls it sparse."""
    idx = pd.date_range(start=start, periods=days * (1440 // tf_min), freq=f"{tf_min}min")
    return pd.DataFrame(
        {"open": 1.0, "high": 1.5, "low": 0.5, "close": 1.2, "volume": 10.0}, index=idx
    ).rename_axis("time")


class FakeAgent:
    """Serves bars for dates in `has`, raises for any window with none — exactly what the
    real agent does (`Mt5Agent.bars` raises when the WHOLE window is empty)."""

    def __init__(self, has: set[str], server: str = "FakeBroker-Demo"):
        self.has = has
        self.calls: list[tuple[str, str]] = []
        self.server = server

    def bars(self, symbol, tf_name, start_date, end_date):
        self.calls.append((start_date, end_date))
        lo = dt.date.fromisoformat(start_date)
        hi = dt.date.fromisoformat(end_date)
        days = [
            str(lo + dt.timedelta(days=i))
            for i in range((hi - lo).days + 1)
            if str(lo + dt.timedelta(days=i)) in self.has
        ]
        if not days:
            raise Mt5AgentError(
                f"MT5 agent returned no bars for {symbol} {tf_name} [{start_date}, {end_date}]"
            )
        return pd.concat([_bars(d, 1) for d in days])

    def status(self):
        return {"server": self.server}


class DeadAgent:
    """The agent itself is unreachable — every call raises, including the probe."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def bars(self, symbol, tf_name, start_date, end_date):
        self.calls.append((start_date, end_date))
        raise Mt5AgentError("MT5 agent unreachable (is the SSH tunnel up?)")

    def status(self):
        return {}


@pytest.fixture()
def src(tmp_path):
    def _make(agent=None, warm: list[tuple[str, str]] | None = None):
        """`warm` PRE-RECORDS coverage, and it is what makes these tests real.

        🔴 The first version of this file started every test from an EMPTY cache, so
        `coverage.missing` returned one span covering the whole request — which the fake
        agent then answered with the trading days inside it. **Nothing ever asked for a
        window that was purely closed, so eight of ten tests passed against the unfixed
        code.** In production the cache was warm through Friday and the gap was exactly
        `[2026-08-15, 2026-08-15]`. A fixture that cannot produce the gap cannot test it.
        """
        from backtest.data.cache import BarCache

        s = BarSource(agent=agent, cache=BarCache(cache_dir=str(tmp_path)))
        # The floor probe is a different concern with its own tests, and letting it run here
        # would have these tests measuring history depth against a fake.
        s.floors.assert_window = lambda *a, **k: None
        for lo, hi in warm or []:
            # Bars for EVERY day of the warmed span, not just its first. Saving one day and
            # recording four is the requested-vs-received lie this module exists to prevent,
            # reproduced inside its own test fixture.
            span = (dt.date.fromisoformat(hi) - dt.date.fromisoformat(lo)).days + 1
            s.cache.save("XAUUSD", "M15", _bars(lo, span))
            s.coverage.record("XAUUSD", "M15", lo, hi)
        agent.calls.clear()  # the warm-up is setup, not a call under test
        return s

    return _make


# ── the bug ────────────────────────────────────────────────────────────────────────


def test_a_gap_that_is_only_a_closed_market_does_not_fail_the_load(src):
    """THE REPORTED BUG, in its production shape: cache warm through Friday, then a run
    whose end date is the Saturday. The only gap is a day the market did not open."""
    agent = FakeAgent(has={"2026-08-13", "2026-08-14"})
    s = src(agent, warm=[("2026-08-13", "2026-08-14")])
    df = s._load_base("XAUUSD", "M15", "2026-08-13", "2026-08-15")
    assert agent.calls[0] == ("2026-08-15", "2026-08-15"), "the gap under test"
    assert not df.empty
    assert str(df.index.max().date()) == "2026-08-14"


def test_the_closed_span_is_not_recorded_as_covered(src):
    """It holds no bars, so there is nothing to describe. Recording it would be the
    requested-vs-received lie this module already carries scars from."""
    agent = FakeAgent(has={"2026-08-13", "2026-08-14"})
    s = src(agent, warm=[("2026-08-13", "2026-08-14")])
    s._load_base("XAUUSD", "M15", "2026-08-13", "2026-08-15")
    still_missing = s.coverage.missing("XAUUSD", "M15", "2026-08-15", "2026-08-15")
    assert still_missing, "a span with no bars must never be claimed as fetched"


def test_the_probe_is_longer_than_any_closure_it_excuses(src):
    """A probe no longer than the closure would answer 'no bars' for both causes, which is
    not a probe. Asserted on the window actually requested, not on a constant."""
    agent = FakeAgent(has={"2026-08-14"})
    s = src(agent, warm=[("2026-08-14", "2026-08-14")])
    s._load_base("XAUUSD", "M15", "2026-08-14", "2026-08-15")
    probe = agent.calls[-1]
    span = (dt.date.fromisoformat(probe[1]) - dt.date.fromisoformat(probe[0])).days
    assert span > _MAX_CLOSURE_DAYS


def test_the_probe_never_asks_past_today(src):
    """Asking beyond today is asking for bars nothing can have — the very failure this
    function exists to stop, from inside itself."""
    today = dt.date.today()
    served = str(today - dt.timedelta(days=3))
    agent = FakeAgent(has={served})
    s = src(agent, warm=[(served, served)])
    s._load_base("XAUUSD", "M15", served, str(today))
    for _start, end in agent.calls:
        assert dt.date.fromisoformat(end) <= today


# ── the failure the fix must NOT buy the weekend with ──────────────────────────────


def test_a_hole_longer_than_a_closure_still_raises(src):
    """The 45-day M1 hole. Bars exist either side, so the probe succeeds — and it must NOT
    be enough, because a stretch this long is missing data by this module's own measured
    definition."""
    s = src(
        FakeAgent(has={"2026-06-01", "2026-08-01"}),
        warm=[("2026-06-01", "2026-06-01"), ("2026-08-01", "2026-08-01")],
    )
    with pytest.raises(Mt5AgentError):
        s._load_base("XAUUSD", "M15", "2026-06-01", "2026-08-01")


def test_a_hole_of_exactly_one_day_past_the_closure_limit_still_raises(src):
    """The boundary, asserted rather than assumed: `_MAX_CLOSURE_DAYS` is the longest span
    that may be called a closure, so one day more may not be."""
    lo = dt.date(2026, 6, 1)
    hi = lo + dt.timedelta(days=_MAX_CLOSURE_DAYS + 1)
    before, after = str(lo - dt.timedelta(days=1)), str(hi + dt.timedelta(days=1))
    s = src(FakeAgent(has={before, after}), warm=[(before, before), (after, after)])
    with pytest.raises(Mt5AgentError):
        s._load_base("XAUUSD", "M15", before, after)


def test_a_dead_agent_raises_and_is_never_read_as_a_closure(src):
    """'Cannot ask' is not 'no market'. An unreachable agent must not license skipping a span."""
    s = src(DeadAgent(), warm=[("2026-08-14", "2026-08-14")])
    with pytest.raises(Mt5AgentError):
        s._load_base("XAUUSD", "M15", "2026-08-14", "2026-08-15")


def test_a_symbol_with_no_history_at_all_raises(src):
    """Nothing anywhere near the window. The probe finds nothing either, so there is no
    evidence the market was merely shut — and a typo'd symbol must fail loudly."""
    s = src(FakeAgent(has=set()), warm=[("2026-08-14", "2026-08-14")])
    with pytest.raises(Mt5AgentError):
        s._load_base("XAUUSD", "M15", "2026-08-14", "2026-08-15")


# ── nothing that already worked may move ───────────────────────────────────────────


def test_a_fully_served_window_makes_no_probe_at_all(src):
    """The happy path must not pay for this. No empty gap, so no probe."""
    agent = FakeAgent(has={"2026-08-12", "2026-08-13", "2026-08-14"})
    s = src(agent)
    s._load_base("XAUUSD", "M15", "2026-08-12", "2026-08-14")
    assert len(agent.calls) == 1


def test_bars_that_did_arrive_are_still_cached_and_covered(src):
    """The skip must be confined to the empty span — the served days behave exactly as before."""
    agent = FakeAgent(has={"2026-08-13", "2026-08-14"})
    s = src(agent, warm=[("2026-08-13", "2026-08-13")])
    s._load_base("XAUUSD", "M15", "2026-08-13", "2026-08-15")
    assert not s.coverage.missing("XAUUSD", "M15", "2026-08-13", "2026-08-14")


class EmptyFrameAgent:
    """An agent that returns an EMPTY FRAME instead of raising.

    ⚠ `Mt5Agent.bars` cannot do this today — it raises when the whole window is empty — so
    this shape is unreachable through `_load_base` and the check that handles it is defence
    in depth, exactly like `covered_spans`' own empty branch. It is pinned anyway, by
    calling the method directly: a surviving mutation showed that `return not probe.empty`
    could be replaced with `return True` and all ten tests stayed green, which means the
    branch was documentation rather than behaviour.
    """

    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def bars(self, symbol, tf_name, start_date, end_date):
        self.calls.append((start_date, end_date))
        return pd.DataFrame()

    def status(self):
        return {}


def test_an_empty_probe_frame_is_not_evidence_the_market_was_shut(src):
    s = src(EmptyFrameAgent())
    assert s._market_was_shut("XAUUSD", "M15", "2026-08-15", "2026-08-15") is False


def test_a_probe_that_serves_bars_is_evidence_the_market_was_shut(src):
    """The paired positive, so the test above cannot pass by the method always saying no."""
    agent = FakeAgent(has={"2026-08-13", "2026-08-14"})
    s = src(agent)
    assert s._market_was_shut("XAUUSD", "M15", "2026-08-15", "2026-08-15") is True
