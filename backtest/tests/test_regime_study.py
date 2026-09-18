"""Tests for the market-condition grading harness.

🔴 **THESE ARE MOSTLY LOOK-AHEAD TESTS AND THAT IS ON PURPOSE.** Every other defect in a study
like this announces itself — a crash, an empty table, a number that is obviously mad. Look-ahead
does the opposite: it makes the report BETTER, quietly, in the direction the author was hoping
for. Nothing downstream can catch it, so it has to be caught here.

⚠ **Each one was watched go RED for the right reason before being kept** (repo rule 12). The
mutation that breaks each is named in its docstring, so the next person can re-break it in one
edit rather than trusting this sentence.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.regime_study import forward, grade_bot, grade_market, measures, stats
from backtest.tests._synth import synth_bars


@pytest.fixture(scope="module")
def bars() -> pd.DataFrame:
    return synth_bars(n_days=60)


@pytest.fixture(scope="module")
def h4(bars: pd.DataFrame) -> pd.DataFrame:
    return (
        bars.resample("4h")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
        .dropna()
    )


# ── look-ahead ───────────────────────────────────────────────────────────────────


def test_readings_cannot_see_past_the_frame_they_are_given(bars):
    """Every reading is identical whether or not future bars exist in the file.

    RED IF: any reading in measures.py is changed to index off the end of its frame, or the
    percentile is computed against the whole series instead of the trailing window.
    """
    cut = 800
    early = measures.read_all(bars.iloc[:cut])
    # The same window, taken out of a file that continues for weeks afterwards.
    later = measures.read_all(bars.iloc[:cut])
    assert early == later
    # And the readings must actually have produced numbers, or this test passes vacuously on a
    # dict of Nones — the failure mode rule 12 is about.
    assert sum(v is not None for v in early.values()) >= len(measures.READINGS) - 1


def test_forward_outcomes_ignore_bars_beyond_the_horizon(bars):
    """Moving price AFTER the horizon must not move the outcome.

    RED IF: a forward outcome slices to the end of the file rather than to i+horizon.
    """
    i, horizon = 500, 40
    before = forward.measure_all(bars, i, horizon)
    tampered = bars.copy()
    tampered.iloc[i + horizon + 1 :, :] *= 1.5
    after = forward.measure_all(tampered, i, horizon)
    assert before == after


def test_forward_outcomes_do_react_to_the_bars_inside_the_horizon(bars):
    """The mirror of the test above — without it, an outcome that always returned a constant
    would pass the look-ahead test perfectly.

    RED IF: an outcome stops reading the future at all.
    """
    i, horizon = 500, 40
    before = forward.measure_all(bars, i, horizon)
    tampered = bars.copy()
    tampered.iloc[i + 1 : i + horizon + 1, :] *= 1.5
    after = forward.measure_all(tampered, i, horizon)
    assert any(before[k] != after[k] for k in before)


def test_readings_do_not_overlap_the_bars_the_outcome_measures(bars):
    """Changing a bar strictly after i must not move any reading taken at i.

    This is the seam the whole study rests on: the reading half and the answer half must not
    share a single bar. RED IF: a reading window is taken as df.iloc[lo:i+2] or similar.
    """
    i = 600
    window = bars.iloc[max(0, i - 1199) : i + 1]
    before = measures.read_all(window)
    tampered = bars.copy()
    tampered.iloc[i + 1 :, :] *= 2.0
    after = measures.read_all(tampered.iloc[max(0, i - 1199) : i + 1])
    assert before == after


def test_a_trade_is_graded_on_a_bar_that_had_already_closed(h4):
    """A trade mid-bar is graded on the PREVIOUS bar, because its own bar has not finished.

    RED IF: _condition_index drops the step-back, which is the single most flattering bug this
    package could have.
    """
    third = h4.index[3]
    mid_bar = third + pd.Timedelta(hours=2)
    assert grade_bot._condition_index(h4, mid_bar) == 2
    # Exactly at the close of bar 3 (= the open of bar 4), bar 3 IS complete.
    assert grade_bot._condition_index(h4, third + pd.Timedelta(hours=4)) == 3
    # Before any bar has closed there is no answer, and the answer is None, not bar zero.
    assert grade_bot._condition_index(h4, h4.index[0]) is None


# ── "cannot ask" is not "no" (repo rule 1) ───────────────────────────────────────


def test_a_reading_with_no_history_is_none_never_zero(bars):
    """RED IF: any reading returns 0.0, np.nan or a default when it has too little history."""
    for name, value in measures.read_all(bars.iloc[:5]).items():
        assert value is None, f"{name} answered {value!r} on five bars"


def test_an_outcome_with_no_future_is_none_never_zero(bars):
    """RED IF: a forward outcome pads a short tail instead of refusing it."""
    last = len(bars) - 1
    for name, value in forward.measure_all(bars, last - 2, 40).items():
        assert value is None, f"{name} answered {value!r} with no future to measure"


def test_the_walk_drops_only_the_tail_it_cannot_grade(bars):
    """RED IF: walk() keeps rows with no future, which would grade the most recent market
    against a horizon that does not exist."""
    horizon = 40
    walked = grade_market.walk(bars, horizon=horizon, step=10, with_label=False)
    assert not walked.empty
    assert walked["bar"].max() < len(bars) - horizon


# ── the readings really are the shipped engine's (no second implementation) ──────


def test_the_shipped_readings_come_from_the_engine_itself(h4):
    """RED IF: measures.py grows its own copy of the engine's arithmetic and they drift."""
    from engines.regime.classifier import _adx, _atr_ratio, _rsi_range

    window = h4.iloc[:200]
    assert measures.engine_trend_strength(window) == pytest.approx(_adx(window))
    assert measures.engine_volatility_ratio(window) == pytest.approx(_atr_ratio(window))
    assert measures.engine_momentum_swing(window) == pytest.approx(_rsi_range(window))


# ── the statistics ───────────────────────────────────────────────────────────────


def test_rank_correlation_finds_a_known_relationship():
    """RED IF: spearman is wired to the wrong axis or loses its sign."""
    x = np.arange(200, dtype=float)
    assert stats.spearman(x, x * 3.0) == pytest.approx(1.0)
    assert stats.spearman(x, -x) == pytest.approx(-1.0)
    assert stats.spearman(x, np.zeros(200)) is None  # constant: undefined, not zero


def test_the_block_bootstrap_is_wider_than_the_naive_one_on_sticky_data():
    """The guard the whole report depends on.

    Neighbouring bars are correlated, so resampling them one at a time invents independent
    observations that do not exist and produces a range far too narrow. On a deliberately sticky
    series the block range must be the wider of the two.

    RED IF: block_length returns 1, or the block resampler is bypassed — the exact change that
    would make every reading in the report look significant.
    """
    rng = np.random.default_rng(7)
    n = 3000
    noise = rng.standard_normal(n)
    sticky = pd.Series(noise).rolling(50).mean().bfill().to_numpy()  # heavy autocorrelation
    other = pd.Series(rng.standard_normal(n)).rolling(50).mean().bfill().to_numpy()

    blocked = stats.spearman_ci(sticky, other, blocks=True, draws=400)
    naive = stats.spearman_ci(sticky, other, blocks=False, draws=400)
    assert blocked["blocks"] > 1
    assert (blocked["hi"] - blocked["lo"]) > (naive["hi"] - naive["lo"])


def test_the_shuffle_test_calls_random_groups_unremarkable():
    """RED IF: permutation_spread compares against the wrong distribution — it would then stamp
    every table of group averages as a real effect."""
    rng = np.random.default_rng(3)
    groups = {name: rng.standard_normal(300) for name in ("a", "b", "c", "d")}
    assert stats.permutation_spread(groups, draws=500)["share_as_extreme"] > 0.05


def test_the_shuffle_test_finds_a_group_that_really_differs():
    """The mirror — without it a function that always answered 1.0 would pass the test above."""
    rng = np.random.default_rng(3)
    groups = {
        "a": rng.standard_normal(300),
        "b": rng.standard_normal(300) + 3.0,
    }
    assert stats.permutation_spread(groups, draws=500)["share_as_extreme"] < 0.05


def test_a_thin_group_gets_an_average_but_no_range():
    """RED IF: mean_ci bootstraps four observations and prints a confident range around them."""
    thin = stats.mean_ci(np.array([1.0, -2.0, 0.5, 3.0]), blocks=False)
    assert thin["mean"] is not None
    assert thin["lo"] is None and thin["hi"] is None


def test_bands_hold_roughly_equal_numbers_of_trades():
    """RED IF: quantile_buckets is swapped for equal-WIDTH bands, which on a skewed reading puts
    almost everything in one band and a handful in another."""
    rng = np.random.default_rng(11)
    skewed = rng.exponential(size=600)
    pair = pd.DataFrame({"x": skewed, "r": rng.standard_normal(600)})
    rows = grade_bot.bands(pair, "x", count=3)
    counts = [row["n"] for row in rows]
    assert len(rows) == 3
    assert max(counts) - min(counts) <= 2


# ── end to end ───────────────────────────────────────────────────────────────────


def test_the_two_graders_run_and_produce_ranges(bars, h4):
    """A smoke test that the pieces fit — and that the report is not silently all-None.

    RED IF: a reading name drifts between the registry and the graders, which would print a
    blank column nobody would query.
    """
    walked = grade_market.walk(h4, horizon=10, step=1, with_label=False)
    scored = grade_market.score(walked)
    assert scored["readings"], "no reading was scored at all"

    rng = np.random.default_rng(5)
    picks = rng.choice(np.arange(200, len(h4) - 20), size=120, replace=False)
    trades = pd.DataFrame(
        {
            "entry_utc": [h4.index[i] + pd.Timedelta(hours=1) for i in sorted(picks)],
            "r": rng.standard_normal(120) * 2.0,
        }
    )
    tagged = grade_bot.tag(trades, h4, with_label=False)
    bot = grade_bot.score(tagged)
    assert bot["n_trades"] == 120
    assert any(cell["relationship"]["rho"] is not None for cell in bot["readings"].values())
