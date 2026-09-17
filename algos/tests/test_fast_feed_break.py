"""The re-entry feed's gap alert must not fire for a market that was simply shut (2026-09-17).

"RE-ENTRY FEED GAP · missed 13 M5 bars" reached the health room at 22:05 UTC. It was gold's daily
one-hour break: the clock counted thirteen intervals and the broker had printed no bars in them.
The re-warm still runs either way; only the alert is withheld, and only on a positive answer.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

_REPO = Path(__file__).resolve().parent.parent.parent
for _p in (str(_REPO), str(_REPO / "algos" / "live")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from runner import LiveRunner  # noqa: E402


class _FastFeed:
    timeframe = "M5"

    def __init__(self, gap, real):
        self._gap, self._real = gap, real

    def gap_bars(self):
        return self._gap

    def bars_since_last(self, span):
        if isinstance(self._real, Exception):
            raise self._real
        return self._real


class _Runner(LiveRunner):
    _label = "SOS Fade · LIVE"  # the real one reads the registry


def _runner(gap, real):
    r = _Runner.__new__(_Runner)
    r.fast_feed = _FastFeed(gap, real)
    r._fast_pending = ["stale"]
    r._fast_stale_alerted = False
    r.rewarmed = 0
    r._rewarm_fast = lambda: setattr(r, "rewarmed", r.rewarmed + 1)
    r.ledger = SimpleNamespace(event=lambda *a, **k: None)
    r.log = SimpleNamespace(info=lambda m: None, warning=lambda m: None)
    r.alerts = []
    r._notify_health = lambda m, **_kw: r.alerts.append(m)
    return r


def test_the_daily_break_re_warms_but_does_not_alert():
    """MUTATION: drop the `market_break` return -> red."""
    r = _runner(gap=13, real=2)
    r._check_fast_feed()
    assert r.rewarmed == 1 and r._fast_pending == []
    assert r.alerts == []


def test_real_missing_bars_still_alert():
    r = _runner(gap=13, real=13)
    r._check_fast_feed()
    assert r.rewarmed == 1
    assert len(r.alerts) == 1 and "RE-ENTRY FEED GAP" in r.alerts[0]


def test_a_feed_that_CANNOT_be_asked_still_alerts():
    for real in (None, RuntimeError("IPC recv failed")):
        r = _runner(gap=13, real=real)
        r._check_fast_feed()
        assert len(r.alerts) == 1, real
