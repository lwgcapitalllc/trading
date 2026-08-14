"""Clock tests — hand-built streams, offline. Lock the k-way merge, co-timed grouping,
and stable leg order."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backtest.portfolio.clock import merge_streams


@dataclass(frozen=True)
class Bar:
    timestamp_ms: int
    tag: str = ""


def _times(ticks):
    return [t.time for t in ticks]


def test_two_streams_interleave_in_time_order():
    a = [Bar(1), Bar(3), Bar(5)]
    b = [Bar(2), Bar(4), Bar(6)]
    ticks = list(merge_streams({"A": a, "B": b}))
    assert _times(ticks) == [1, 2, 3, 4, 5, 6]
    # each timestamp has exactly one leg here
    assert all(len(t.bars) == 1 for t in ticks)


def test_co_timed_bars_group_into_one_tick():
    # a 15m leg and a 5m leg: the 5m steps 3× per 15m bar, and they share t=0 and t=15.
    slow = [Bar(0, "15m"), Bar(15, "15m")]
    fast = [Bar(0, "5m"), Bar(5, "5m"), Bar(10, "5m"), Bar(15, "5m")]
    ticks = list(merge_streams({"SLOW": slow, "FAST": fast}))
    assert _times(ticks) == [0, 5, 10, 15]
    # t=0 carries BOTH legs
    t0 = ticks[0]
    assert [leg for leg, _ in t0.bars] == ["SLOW", "FAST"]
    # t=5 and t=10 carry only the fast leg
    assert [leg for leg, _ in ticks[1].bars] == ["FAST"]
    assert [leg for leg, _ in ticks[2].bars] == ["FAST"]
    # t=15 carries both again
    assert [leg for leg, _ in ticks[3].bars] == ["SLOW", "FAST"]


def test_leg_order_is_stable_dict_order():
    a = [Bar(0)]
    b = [Bar(0)]
    c = [Bar(0)]
    ticks = list(merge_streams({"B": b, "A": a, "C": c}))
    assert len(ticks) == 1
    assert [leg for leg, _ in ticks[0].bars] == ["B", "A", "C"]


def test_bar_payload_is_carried_through():
    ticks = list(merge_streams({"X": [Bar(7, "hello")]}))
    leg, bar = ticks[0].bars[0]
    assert leg == "X" and bar.tag == "hello"


def test_custom_time_key():
    pts = [{"t": 10}, {"t": 20}]
    ticks = list(merge_streams({"D": pts}, time_key=lambda b: b["t"]))
    assert _times(ticks) == [10, 20]


def test_empty_streams_yield_nothing():
    assert list(merge_streams({"A": [], "B": []})) == []


def test_single_stream_passes_straight_through():
    ticks = list(merge_streams({"only": [Bar(1), Bar(2), Bar(3)]}))
    assert _times(ticks) == [1, 2, 3]
