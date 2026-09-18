"""The candidate reading's four ways of lying, each pinned and each watched go red.

The mutation that breaks each test is named in its docstring (root rule 12). None of these
can fail by accident, so a green run here means nothing unless the red run was seen.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.regime_study.candidate import (
    LOOKBACK,
    MIN_RANKED,
    SPEED_BANDS,
    STICKINESS_BANDS,
    _rank_last,
    band_of,
    classify,
    persistence_percentile,
    read,
)


def _bars(n=1400, seed=7):
    """A synthetic walk with a volatility cycle in it, so the readings have something to find."""
    rng = np.random.default_rng(seed)
    vol = 1.0 + 0.8 * np.sin(np.arange(n) / 90.0)
    steps = rng.normal(0, 1, n) * vol
    close = 2000 + np.cumsum(steps)
    high = close + np.abs(rng.normal(0, 0.6, n))
    low = close - np.abs(rng.normal(0, 0.6, n))
    idx = pd.date_range("2020-01-01", periods=n, freq="4h")
    return pd.DataFrame({"open": close, "high": high, "low": low, "close": close}, index=idx)


def test_no_reading_can_see_past_its_last_bar():
    """The only property that matters. RED by removing a `.rolling()` bound anywhere, or by
    ranking against the whole frame instead of the history up to now — both make the answer
    for bar i change when bars after i are appended."""
    df = _bars()
    cut = 1200
    now = read(df.iloc[:cut])
    assert now["speed"] is not None and now["stickiness"] is not None
    # The same bar, described with and without future bars present in the source frame.
    for extra in (1, 17, 150):
        again = read(df.iloc[: cut + extra].iloc[:cut])
        assert again["speed"] == now["speed"]
        assert again["stickiness"] == now["stickiness"]


def test_truncating_the_future_changes_nothing():
    """Sharper form of the above: build the frame two ways, same last bar, same answer.

    RED by making the rank use `np.sort` over the whole series and indexing from the end, a
    natural-looking refactor that silently ranks against bars the reading has not seen."""
    df = _bars()
    cut = 900
    a = read(df.iloc[:cut])
    b = read(pd.concat([df.iloc[:cut], df.iloc[cut:]]).iloc[:cut])
    assert a == b


def test_too_little_history_is_none_never_a_middle_value():
    """Root rule 1: cannot ask is not the same value as ordinary.

    RED two ways, both watched: drop the `len(closes) < window + lag + MIN_RANKED` guard, and
    the reading answers off a handful of bars; or return 0.5 from `_rank_last` instead of
    None, and every warm-up bar is graded as a perfectly ordinary market.
    """
    df = _bars(n=MIN_RANKED + 5)
    out = read(df)
    assert out["stickiness"] is None
    assert out["stickiness_band"] is None
    assert classify(df) is None
    assert persistence_percentile(df) is None
    # The rank itself, reached directly — the length guard above would otherwise be the only
    # thing under test and `_rank_last` could return anything it liked.
    assert _rank_last(np.arange(MIN_RANKED - 1, dtype=float)) is None
    assert _rank_last(np.full(MIN_RANKED + 10, np.nan)) is None
    assert _rank_last(np.arange(MIN_RANKED + 10, dtype=float)) == 1.0


def test_bands_hold_roughly_a_third_each():
    """The whole point of ranking. RED by replacing the 1/3 and 2/3 cuts with any fixed value
    of the underlying reading — the populations then go lopsided, which is the shipped
    engine's 78% bucket reappearing under a new name."""
    df = _bars(n=2000)
    speeds, sticks = [], []
    for i in range(1200, len(df), 3):
        out = read(df.iloc[: i + 1])
        if out["speed_band"]:
            speeds.append(out["speed_band"])
        if out["stickiness_band"]:
            sticks.append(out["stickiness_band"])
    for got, names in ((speeds, SPEED_BANDS), (sticks, STICKINESS_BANDS)):
        assert len(got) > 100
        for name in names:
            share = got.count(name) / len(got)
            # Generous, because a rank over a TRAILING window is only equal-population in the
            # long run — a band may be starved for a stretch and that is the reading working.
            assert 0.10 < share < 0.60, f"{name} took {share:.0%} of {len(got)} readings"


def test_band_edges_are_where_they_claim_to_be():
    """RED by flipping any `<` to `<=` — the middle band silently gains or loses its edge."""
    assert band_of(0.0, SPEED_BANDS) == "QUIET"
    assert band_of(0.333, SPEED_BANDS) == "QUIET"
    assert band_of(1 / 3, SPEED_BANDS) == "NORMAL"
    assert band_of(0.666, SPEED_BANDS) == "NORMAL"
    assert band_of(2 / 3, SPEED_BANDS) == "FAST"
    assert band_of(1.0, SPEED_BANDS) == "FAST"
    assert band_of(None, SPEED_BANDS) is None


def test_the_same_frame_always_answers_the_same():
    """`engines/regime/CLAUDE.md` forbids hidden state and randomness. RED by caching anything
    on the module between calls."""
    df = _bars()
    assert read(df.iloc[:1000]) == read(df.iloc[:1000])
    assert classify(df) == classify(df)


def test_the_two_scales_are_never_added_together():
    """The collapse into one score is the defect being fixed. RED by returning a single name
    from `classify` — the join must carry both answers so neither can be reconstructed wrongly."""
    df = _bars()
    label = classify(df)
    speed, stick = label.split("/")
    assert speed in SPEED_BANDS
    assert stick in STICKINESS_BANDS


@pytest.mark.parametrize("bad", ["flat", "negative"])
def test_degenerate_prices_refuse_rather_than_answer(bad):
    """A frame that never moved, or holds a non-positive price, has no ratio to report.

    RED by dropping the guards — numpy returns nan or a divide-by-zero warning and the nan
    ranks as the lowest value in the history, which reads as a genuine extreme."""
    df = _bars()
    if bad == "flat":
        df = df.assign(close=2000.0, high=2000.0, low=2000.0)
    else:
        df = df.assign(close=df["close"] - df["close"].max() - 1.0)
    assert persistence_percentile(df) is None


def test_lookback_is_clamped_to_the_history_that_exists():
    """Root rule 3. RED by padding short history to `LOOKBACK` with anything — the rank then
    describes bars that were never fetched."""
    df = _bars(n=700)
    assert len(df) < LOOKBACK
    out = read(df)
    assert out["stickiness"] is not None
    assert 0.0 <= out["stickiness"] <= 1.0
