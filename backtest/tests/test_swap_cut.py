"""The lab-only candidate cut answers three ways and counts all three.

Rule 12: the four assertions that guard real lines were each watched go RED by mutating that
line — see each test's docstring for the mutation used.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.regime_study.swap_cut import ALLOW, REFUSE, UNKNOWN, CandidateCut


def _feed(cut: CandidateCut, closes) -> None:
    for c in closes:
        cut.on_bar(c, c + 0.5, c - 0.5, c)


def test_too_little_history_is_unknown_never_allow():
    """RED by mutating `ask`'s `return UNKNOWN` to `return ALLOW`.

    A cut that cannot see must not be indistinguishable from a cut that approved (root rule 1).
    """
    cut = CandidateCut()
    _feed(cut, np.linspace(2000.0, 2010.0, 50))
    assert cut.ask() == UNKNOWN
    assert cut.unknown_count == 1
    assert cut.refused == 0


def test_asked_counts_every_question_not_only_the_refusals():
    """RED by deleting `self.asked += 1`.

    A cut nobody wired up and a cut that allowed everything both produce a run identical to
    the baseline; `asked` is the only field that separates them.
    """
    cut = CandidateCut()
    _feed(cut, np.linspace(2000.0, 2010.0, 50))
    for _ in range(3):
        cut.ask()
    assert cut.asked == 3


def test_only_the_middle_band_is_refused():
    """RED by mutating the band comparison to `band != REFUSED_BAND`.

    The refusal rule is pre-registered as the middle third. Refusing the outer thirds instead
    is a different experiment wearing this one's name.
    """
    rng = np.random.default_rng(11)
    cut = CandidateCut()
    _feed(cut, 2000.0 + np.cumsum(rng.normal(0.0, 1.0, 1600)))
    seen = {cut.ask() for _ in range(1)}
    assert seen <= {ALLOW, REFUSE}

    import backtest.regime_study.swap_cut as mod
    from backtest.regime_study.candidate import band_of, persistence_percentile

    df = pd.DataFrame(list(cut._bars), columns=["open", "high", "low", "close"])
    band = band_of(persistence_percentile(df, lookback=mod.LOOKBACK), ("LOW", "NEUTRAL", "HIGH"))
    expected = REFUSE if band == mod.REFUSED_BAND else ALLOW
    assert cut.ask() == expected


def test_the_higher_frame_is_accepted_and_ignored():
    """Cannot go red by mutation — it pins a DROP, so it is proven by the pair below instead.

    The shipped cut this replaces is fed a higher timeframe on every bar. The candidate reads
    one scale, so it must accept that call without either crashing or letting those bars into
    its buffer — feeding them would be a second, wrongly-scaled history.
    """
    cut = CandidateCut()
    _feed(cut, np.linspace(2000.0, 2010.0, 30))
    before = len(cut._bars)
    for _ in range(10):
        cut.on_htf_bar(2000.0, 2001.0, 1999.0, 2000.0)
    assert len(cut._bars) == before


def test_buffer_is_long_enough_for_the_reading_to_ever_answer():
    """RED by mutating `_KEEP` to `120` (the shipped cut's figure).

    The reading needs its rolling window PLUS its ranking history. A buffer shorter than that
    makes the cut answer UNKNOWN forever, which is a cut that silently does nothing.
    """
    import backtest.regime_study.swap_cut as mod
    from backtest.regime_study.candidate import LOOKBACK, MIN_RANKED

    assert mod._KEEP >= LOOKBACK + MIN_RANKED

    rng = np.random.default_rng(3)
    cut = CandidateCut()
    _feed(cut, 2000.0 + np.cumsum(rng.normal(0.0, 1.0, mod._KEEP + 200)))
    assert cut.ask() != UNKNOWN


@pytest.mark.parametrize("answer", [ALLOW, REFUSE, UNKNOWN])
def test_the_three_answers_are_distinct_values(answer):
    """A bool cannot carry three states; this pins that they never collapse to two."""
    assert len({ALLOW, REFUSE, UNKNOWN}) == 3
    assert isinstance(answer, str)
