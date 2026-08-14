"""The classification that turns two trade lists into a frequency.

The replay is tested elsewhere. What is tested here is the arithmetic BETWEEN two replays, and
it needs pinning for the same reason `test_overlap_audit.py` does: **its output is a small,
confident number that nobody can check by eye**, and both directions of error are silent.

- **Classify too little as a flip** and the tool reports the entry model as stable when it is
  not — which is the reassuring answer, and the one that ships a bot.
- **Classify too much as a flip** and ordinary feed noise gets reported as the rule changing its
  mind, which sends someone to rewrite an entry rule that was working.

The threshold is the load-bearing part. It is DERIVED (`2 * amp`, the widest two runs can differ
from the noise alone), not chosen, so the cases below are mostly about the boundary and about
what must not be quietly folded into the wrong bucket.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
_spec = importlib.util.spec_from_file_location(
    "jitter_audit", _REPO / "backtest" / "tools" / "jitter_audit.py"
)
ja = importlib.util.module_from_spec(_spec)
sys.modules["jitter_audit"] = ja
_spec.loader.exec_module(ja)


_BAR = 15 * 60 * 1000  # the default bar_ms the diff is told to assume
_MS = 1_700_000_000_000  # an arbitrary anchor; only differences matter


class T:
    """A trade duck-type carrying only the fields the diff reads."""

    def __init__(self, ms, price=4000.0, stop=10.0, r=1.0, direction=1):
        self.entry_ms = ms
        self.entry_price = price
        self.stop_distance = stop
        self.r = r
        self.dir = direction


# ── the flip threshold ───────────────────────────────────────────────────────────


def test_a_move_bigger_than_the_noise_can_produce_is_a_FLIP():
    # amp 0.05 => two runs can differ by at most 0.10 from noise. $10 is a different rung.
    d = ja._diff([T(100, 4000.0)], [T(100, 4010.0)], seed=1, noise_ceiling=0.10)
    assert len(d.flipped) == 1
    assert d.shifted == 0


def test_a_move_the_noise_could_have_produced_is_only_a_SHIFT():
    d = ja._diff([T(100, 4000.0)], [T(100, 4000.06)], seed=1, noise_ceiling=0.10)
    assert d.flipped == []
    assert d.shifted == 1


def test_the_boundary_is_EXCLUSIVE_so_the_worst_possible_noise_is_not_a_flip():
    # Exactly 2*amp is reachable by noise alone (+amp on one run, -amp on the other). Calling it
    # a flip would report a guaranteed-per-run false positive as the headline frequency.
    d = ja._diff([T(100, 4000.0)], [T(100, 4000.10)], seed=1, noise_ceiling=0.10)
    assert d.flipped == []
    assert d.shifted == 1


def test_one_cent_past_the_boundary_IS_a_flip():
    d = ja._diff([T(100, 4000.0)], [T(100, 4000.11)], seed=1, noise_ceiling=0.10)
    assert len(d.flipped) == 1


def test_a_flip_DOWNWARD_counts_the_same_as_a_flip_upward():
    # `exec_fib_nearest` can rest shallower or deeper. Comparing a signed delta against the
    # ceiling would only ever see half of them, and would look perfectly plausible doing it.
    d = ja._diff([T(100, 4000.0)], [T(100, 3990.0)], seed=1, noise_ceiling=0.10)
    assert len(d.flipped) == 1


def test_an_identical_entry_is_neither_flipped_nor_shifted():
    d = ja._diff([T(100, 4000.0)], [T(100, 4000.0)], seed=1, noise_ceiling=0.10)
    assert d.flipped == [] and d.shifted == 0


# ── trades appearing and disappearing ────────────────────────────────────────────


def test_a_baseline_trade_with_no_jittered_twin_is_LOST_not_flipped():
    d = ja._diff([T(100, 4000.0)], [], seed=1, noise_ceiling=0.10)
    assert len(d.lost) == 1 and d.flipped == []


def test_a_jittered_trade_with_no_baseline_twin_is_GAINED():
    d = ja._diff([], [T(100, 4000.0)], seed=1, noise_ceiling=0.10)
    assert len(d.gained) == 1


def test_a_flip_that_moves_the_ENTRY_BAR_is_never_counted_as_a_flip():
    # Documented in the module docstring and worth pinning: a deeper limit can fill a bar later
    # or not at all, so the flip count is a FLOOR. If this ever silently started pairing across
    # bars, the flip figure would change meaning without changing its name.
    d = ja._diff([T(_MS)], [T(_MS + _BAR, 4010.0)], seed=1, noise_ceiling=0.10)
    assert d.flipped == []


# ── retiming: the same setup filling a bar or two away ───────────────────────────


def test_a_setup_that_fills_a_bar_later_is_RETIMED_not_lost_and_gained():
    # The refinement that keeps this tool honest. A resting limit tagged one bar later is the
    # same setup, and scoring it as one trade destroyed plus one invented would report the trade
    # list as far less stable than it is — the alarming answer, arrived at by bookkeeping.
    d = ja._diff([T(_MS)], [T(_MS + _BAR, 4000.02)], seed=1, noise_ceiling=0.10)
    assert len(d.retimed) == 1
    assert d.lost == [] and d.gained == []
    assert d.retimed[0][2] == 1  # one bar apart


def test_a_setup_that_fills_far_away_is_genuinely_lost_and_gained():
    d = ja._diff([T(_MS)], [T(_MS + 40 * _BAR, 4000.02)], seed=1, noise_ceiling=0.10)
    assert d.retimed == []
    assert len(d.lost) == 1 and len(d.gained) == 1


def test_the_retime_window_boundary_is_INCLUSIVE():
    d = ja._diff([T(_MS)], [T(_MS + 16 * _BAR, 4000.02)], seed=1, noise_ceiling=0.10)
    assert len(d.retimed) == 1
    d2 = ja._diff([T(_MS)], [T(_MS + 17 * _BAR, 4000.02)], seed=1, noise_ceiling=0.10)
    assert d2.retimed == []


def test_retiming_works_BACKWARD_as_well_as_forward():
    # A shallower rung fills EARLIER. Comparing a signed gap would only ever pair half of them.
    d = ja._diff([T(_MS)], [T(_MS - 2 * _BAR, 4000.02)], seed=1, noise_ceiling=0.10)
    assert len(d.retimed) == 1 and d.retimed[0][2] == 2


def test_an_OPPOSITE_direction_trade_is_never_a_retimed_twin():
    # A long vanishing and a short appearing nearby are two different facts about the market,
    # and folding them together would hide a direction flip as a timing wobble.
    d = ja._diff(
        [T(_MS, direction=1)], [T(_MS + _BAR, 4000.02, direction=-1)], seed=1, noise_ceiling=0.10
    )
    assert d.retimed == []
    assert len(d.lost) == 1 and len(d.gained) == 1


def test_one_jittered_trade_cannot_be_the_twin_of_TWO_baseline_trades():
    # The pairing is one-to-one and nearest-first. Without that, a single jittered trade would be
    # claimed by every nearby baseline trade and BOTH the lost and gained counts would collapse
    # toward zero — the tool reporting perfect stability by double-counting one trade.
    base = [T(_MS), T(_MS + 2 * _BAR)]
    d = ja._diff(base, [T(_MS + _BAR, 4000.02)], seed=1, noise_ceiling=0.10)
    assert len(d.retimed) == 1
    assert len(d.lost) == 1 and d.gained == []


def test_the_nearest_candidate_wins_the_pairing():
    base = [T(_MS)]
    jit = [T(_MS + 5 * _BAR, 4000.02), T(_MS + _BAR, 4000.03)]
    d = ja._diff(base, jit, seed=1, noise_ceiling=0.10)
    assert len(d.retimed) == 1 and d.retimed[0][2] == 1
    assert len(d.gained) == 1


def test_an_exact_time_match_is_never_reclassified_as_retimed():
    # Exact matches are settled in the first pass. A trade reaching the retime pass at gap 0
    # would mean the first pass missed it, and it would be reported under the wrong name.
    d = ja._diff([T(_MS)], [T(_MS, 4000.02)], seed=1, noise_ceiling=0.10)
    assert d.retimed == [] and d.shifted == 1


def test_matching_is_by_entry_time_not_by_position_in_the_list():
    # The two runs need not produce trades in a comparable order once one has gained a trade.
    # Zipping the lists would compare unrelated trades and report a wall of flips.
    base = [T(100, 4000.0), T(300, 4100.0)]
    jit = [T(200, 4050.0), T(100, 4000.0), T(300, 4100.0)]
    d = ja._diff(base, jit, seed=1, noise_ceiling=0.10)
    assert d.flipped == [] and d.shifted == 0
    assert len(d.gained) == 1 and d.lost == []


# ── the stop, which is the part that changes position size ───────────────────────


def test_a_flip_records_the_stop_change_as_a_signed_percentage():
    d = ja._diff(
        [T(100, 4000.0, stop=32.28)], [T(100, 4010.0, stop=22.16)], seed=1, noise_ceiling=0.10
    )
    assert len(d.stop_deltas) == 1
    assert d.stop_deltas[0] == pytest.approx(-31.35, abs=0.05)


def test_a_zero_baseline_stop_records_no_percentage_rather_than_dividing_by_zero():
    # A zero stop distance cancels the order in the strategy, so this should not occur — but the
    # tool must not crash on a trade list it did not produce, and reporting 0% would be a lie.
    d = ja._diff(
        [T(100, 4000.0, stop=0.0)], [T(100, 4010.0, stop=22.0)], seed=1, noise_ceiling=0.10
    )
    assert len(d.flipped) == 1
    assert d.stop_deltas == []


def test_a_shift_records_no_stop_change():
    # Only flips carry a stop delta; folding shifts in would dilute the median toward zero and
    # make the size effect look smaller than it is.
    d = ja._diff(
        [T(100, 4000.0, stop=32.0)], [T(100, 4000.02, stop=32.02)], seed=1, noise_ceiling=0.10
    )
    assert d.stop_deltas == []


# ── the jitter itself ────────────────────────────────────────────────────────────


def _frame(n=50):
    idx = pd.date_range("2024-01-01", periods=n, freq="15min", tz=None)
    return pd.DataFrame(
        {
            "open": [4000.0 + i for i in range(n)],
            "high": [4001.0 + i for i in range(n)],
            "low": [3999.0 + i for i in range(n)],
            "close": [4000.5 + i for i in range(n)],
        },
        index=idx,
    )


def test_jitter_moves_all_four_prices_of_a_bar_by_the_SAME_offset():
    # The whole model. Independent per-price noise builds candles where the high is under the
    # close, and the engines would then be measured on data no feed can produce.
    df = _frame()
    out = ja._jitter(df, 0.05, seed=7)
    for col in ("high", "low", "close"):
        deltas = (out[col] - df[col]) - (out["open"] - df["open"])
        assert deltas.abs().max() < 1e-12


def test_jitter_keeps_every_bar_a_valid_candle():
    out = ja._jitter(_frame(), 0.05, seed=3)
    assert (out["high"] >= out[["open", "close"]].max(axis=1)).all()
    assert (out["low"] <= out[["open", "close"]].min(axis=1)).all()


def test_the_offset_VARIES_between_bars():
    # A constant offset cannot flip a rung — every fib level translates with it — so a jitter
    # that accidentally applied one value to the whole frame would measure nothing and report a
    # clean, reassuring zero.
    df = _frame()
    out = ja._jitter(df, 0.05, seed=11)
    offsets = (out["open"] - df["open"]).round(9).unique()
    assert len(offsets) > 1


def test_the_offset_stays_inside_the_amplitude():
    df = _frame(200)
    out = ja._jitter(df, 0.05, seed=5)
    assert (out["open"] - df["open"]).abs().max() <= 0.05


def test_the_same_seed_reproduces_the_same_frame():
    df = _frame()
    a, b = ja._jitter(df, 0.05, seed=42), ja._jitter(df, 0.05, seed=42)
    assert a.equals(b)


def test_different_seeds_produce_different_frames():
    df = _frame()
    assert not ja._jitter(df, 0.05, seed=1).equals(ja._jitter(df, 0.05, seed=2))


def test_jitter_does_not_mutate_the_frame_it_was_given():
    # The baseline is replayed from the same object every seed reuses. Mutating in place would
    # compound the noise seed over seed and silently make later runs the noisiest.
    df = _frame()
    before = df.copy()
    ja._jitter(df, 0.05, seed=9)
    assert df.equals(before)
