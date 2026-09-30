"""Tests for `backtest/tools/generic_ltf_trigger.py` — the rules that make the study watch a setup
the way the strategy's own 1-minute entry does (`strategies/python/sos_fade/shift_entry.py`).

Each rule here was a real disagreement with lab run 8bcf06ffa418 before it was mirrored; see
`backtest/notes/study-reconciliation.md`. Synthetic 1-minute bars, one long setup: 0.0 at 110,
1.0 at 100, reported by the 15m bar opening at minute 0 and known at minute 15.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

_TOOL = Path(__file__).resolve().parents[1] / "tools" / "generic_ltf_trigger.py"
_spec = importlib.util.spec_from_file_location("generic_ltf_trigger", _TOOL)
g = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(g)

M, N = 60_000, 200
P = "ext SOS -> BOS"


def _bars(n=N):
    tl = np.arange(n, dtype=np.int64) * M
    return tl, np.full(n, 105.0), np.full(n, 106.0), np.full(n, 104.0), np.full(n, 105.0)


def _ev(n=N, **marks):
    ev = {
        k: np.zeros(n, dtype=bool)
        for k in ("xs1", "xs-1", "xb1", "xb-1", "is1", "is-1", "ib1", "ib-1")
    }
    for k, bars in marks.items():
        ev[k][list(bars)] = True
    return ev


def _ep(t=0, until=45, d=1, key="K"):
    ash, asl = (110.0, 100.0) if d > 0 else (100.0, 90.0)
    return dict(
        key=key,
        dir=d,
        ash=ash,
        asl=asl,
        fdir=d,
        t=t * M,
        known_ms=(t + 15) * M,
        until_ms=until * M,
        sos_ms=0,
    )


def _first(eps, ev):
    tl, O, H, L, C = _bars()
    return g.first_completion(P, eps, ev, tl, H, L, C)


def test_an_SOS_inside_the_tag_bar_counts_but_a_BOS_inside_it_is_NOT_seen():
    """The lab only knows the tag at the 15m close. RED against watching from the bar's open."""
    got = _first([_ep()], _ev(xs1=[3], xb1=[5, 20]))
    assert got["K"][1] == 20


def test_a_wick_to_the_1_0_ends_the_watch_for_GOOD_even_if_the_setup_comes_back():
    """RED against retiring only the episode — the lab's dead set is per setup."""
    tl, O, H, L, C = _bars()
    L[18] = 99.0
    ev = _ev(xs1=[16, 60], xb1=[20, 70])
    got = g.first_completion(P, [_ep(), _ep(t=45, until=90)], ev, tl, H, L, C)
    assert got == {}


def test_a_setup_that_comes_back_is_watched_AFRESH_and_an_old_SOS_does_not_carry():
    """RED against carrying the SOS latch across episodes: the lab rebuilds the window."""
    got = _first([_ep(), _ep(t=60, until=120)], _ev(xs1=[20], xb1=[80]))
    assert got == {}
    got = _first([_ep(), _ep(t=60, until=120)], _ev(xs1=[20, 62], xb1=[80]))
    assert got["K"][1] == 80


def test_a_short_whose_target_is_touched_only_on_the_BID_is_not_a_win():
    """🔴 2023-02-09 GBPJPY: the bid low touched the target exactly; the lab needs the ask there.
    RED against walking a short's exits on the bid bar."""
    tl, O, H, L, C = _bars()
    s = _ep(d=-1)  # short: 0.0 at 90, 1.0 at 100
    O[:], H[:], L[:], C[:] = 95.0, 95.5, 94.5, 95.0
    L[30] = 90.0  # the bid touches the 0.0 exactly
    H[40] = 99.99  # the ask (bid + 0.015) reaches the 1.0
    tr = g.trade(s, 20, O, H, L, C, tl, M, 0.015, _Free(), None)
    assert tr["win"] is False


def test_a_trade_has_NO_time_limit():
    """The lab holds until stop or target. RED against a 30-day walk (43,200 1m bars)."""
    n = 50_000
    tl, O, H, L, C = _bars(n)
    H[-1] = 111.0
    tr = g.trade(_ep(), 20, O, H, L, C, tl, M, 0.0, _Free(), None)
    assert tr is not None and tr["win"] is True


class _Free:
    """A cost profile charging nothing — these tests pin WHEN a trade ends, not what it costs."""

    class swap:
        @staticmethod
        def charge(*_):
            return 0.0

    @staticmethod
    def commission(_):
        return 0.0

    @staticmethod
    def lots(_):
        return 0.0

    @staticmethod
    def spread_or_refuse():
        return 0.0
