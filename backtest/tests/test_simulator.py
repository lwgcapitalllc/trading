"""Simulator tests — scripted fake legs over one shared account, offline. Lock the
release-before-entry ordering and the contention log."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backtest.portfolio.account import PortfolioAccount
from backtest.portfolio.simulator import simulate


@dataclass
class _Bar:
    timestamp_ms: int
    act: str = ""          # "open" | "close" | ""


class FakeLeg:
    """A leg scripted by (timestamp, action). It routes fills through the shared account and
    frees its reservation on close (no P&L, so the room math stays easy to hand-check)."""

    def __init__(self, name, script, account, *, desired_qty=200.0, entry=100.0,
                 stop=95.0, pv=1.0, dir=1):
        self.name = name
        self._script = script
        self._acct = account
        self.trades: list = []
        self._open = False
        self._granted = 0.0
        self._p = dict(desired_qty=desired_qty, entry=entry, stop=stop, pv=pv, dir=dir)

    def bars(self):
        for ts, act in self._script:
            yield _Bar(ts, act)

    def in_position(self):
        return self._open

    def step(self, bar):
        p = self._p
        if bar.act == "open" and not self._open:
            g = self._acct.request_fill(self.name, p["dir"], p["entry"], p["stop"],
                                        p["desired_qty"], p["pv"])
            if g > 0.0:
                self._open = True
                self._granted = g
                self.trades.append({"leg": self.name, "qty": g})
        elif bar.act == "close" and self._open:
            self._acct.close_position(self.name)   # free reservation, no P&L
            self._open = False
            self._granted = 0.0


def _acct(balance=10_000.0, cap=0.10, floor=0.0):
    return PortfolioAccount(balance=balance, risk_cap_pct=cap, entry_floor_pct=floor)


def test_non_overlapping_legs_never_contend():
    a = _acct()
    A = FakeLeg("A", [(0, "open"), (10, "close")], a)
    B = FakeLeg("B", [(20, "open"), (30, "close")], a)
    res = simulate([A, B], a)
    assert res.contention == []                       # they never collided
    assert len(res.trades) == 2                        # both filled
    assert res.per_leg["A"][0]["qty"] == 200.0         # full size
    assert res.per_leg["B"][0]["qty"] == 200.0


def test_release_before_entry_lets_next_leg_fill_full():
    # tight cap: one leg's trade fills the whole budget. A holds, then at t=20 A CLOSES and
    # B OPENS on the same tick. Holders step first, so A frees the room before B is sized.
    a = _acct()                                        # room 1000; each leg's risk = 1000
    A = FakeLeg("A", [(0, "open"), (20, "close")], a)
    B = FakeLeg("B", [(20, "open"), (40, "close")], a)
    res = simulate([A, B], a)
    assert res.contention == []                        # B was NOT shrunk — A released first
    assert res.per_leg["B"][0]["qty"] == 200.0         # full size


def test_forced_overlap_blocks_second_and_logs_it():
    # A opens at t=0 and holds; B tries to open at t=10 while A still holds → no room.
    a = _acct()
    A = FakeLeg("A", [(0, "open"), (99, "close")], a)
    B = FakeLeg("B", [(10, "open")], a)
    res = simulate([A, B], a)
    assert res.per_leg["B"] == []                       # B never got in
    assert len(res.contention) == 1
    c = res.contention[0]
    assert c["leg"] == "B" and c["blocked"] is True and c["time"] == 10


def test_forced_overlap_shrinks_second_and_logs_it():
    # A reserves 800 (dist 4), leaving 200 room. B wants 1000 → shrunk to 200, floor 0.
    a = _acct(floor=0.0)
    A = FakeLeg("A", [(0, "open"), (99, "close")], a, entry=100.0, stop=96.0)  # risk 800
    B = FakeLeg("B", [(10, "open")], a, entry=100.0, stop=95.0)                 # wants 1000
    res = simulate([A, B], a)
    assert res.per_leg["B"][0]["qty"] == 40.0          # 200 granted / (1 × 5)
    assert len(res.contention) == 1
    c = res.contention[0]
    assert c["leg"] == "B" and c["blocked"] is False
    assert c["desired_risk"] == 1000.0 and c["granted_risk"] == 200.0


# ── Cancel and progress (2026-08-09) ──────────────────────────────────────────
#
# The lab drives a shared stack from a UI, and a full-history two-leg run is four replays over
# ~150,000 bars. A Stop button that cannot reach this loop is a Stop button that does nothing.


def test_a_cancelled_run_says_so_and_stops_stepping():
    """⚠ The FLAG is the whole point, not the early return.

    A cancelled result holds every trade closed up to the tick it stopped on, which is
    indistinguishable from a complete short backtest once it is written to disk. A caller must
    branch on `cancelled`, never on the trade list — persisting a partial book as a finished one
    is the "cancel did not cancel" defect from the other side.
    """
    acct = _acct()
    # Long enough that the cancel lands inside the run rather than after it.
    script = [(i, "open" if i == 0 else "") for i in range(4_000)]
    leg = FakeLeg("a", script, acct)
    seen = {"ticks": 0}

    def _cancel():
        seen["ticks"] += 1
        return seen["ticks"] > 1        # clear on the first poll, cancelled on the second

    res = simulate([leg], acct, should_cancel=_cancel)
    assert res.cancelled is True
    assert acct.now < 4_000 - 1, "it kept stepping after the cancel"


def test_a_run_nobody_cancels_is_not_marked_cancelled():
    """The other direction, and it is the one that would be "simplified" back — a flag that is
    always true reports every finished run as partial."""
    acct = _acct()
    leg = FakeLeg("a", [(0, "open"), (1, "close")], acct)
    res = simulate([leg], acct, should_cancel=lambda: False)
    assert res.cancelled is False
    assert len(leg.trades) == 1


def test_progress_reports_the_tick_index_and_is_polled_sparsely():
    """Polled every `_CHECK_EVERY` ticks rather than every tick: the check is cheap and the loop
    body is cheaper, so per-tick polling is measurable overhead on a run that never cancels."""
    from backtest.portfolio.simulator import _CHECK_EVERY

    acct = _acct()
    n = _CHECK_EVERY * 3
    leg = FakeLeg("a", [(i, "") for i in range(n)], acct)
    seen: list = []
    simulate([leg], acct, progress=seen.append)
    assert seen == [0, _CHECK_EVERY, _CHECK_EVERY * 2]


def test_simulate_without_the_new_arguments_is_untouched():
    """Every existing caller passes neither, and a replay that started polling a None would be a
    behaviour change dressed as a feature addition."""
    acct = _acct()
    leg = FakeLeg("a", [(0, "open"), (1, "close")], acct)
    res = simulate([leg], acct)
    assert res.cancelled is False and len(res.trades) == 1
