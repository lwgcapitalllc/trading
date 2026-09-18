"""What the market ACTUALLY did after a bar — the answer sheet the readings are marked against.

🔴 **THIS IS THE HALF THAT MAKES THE QUESTION ANSWERABLE AT ALL.** A market condition is not
observable, so there is no true label to compare a reading against and "is the classifier
accurate" has no meaning. What IS observable is what happened next. Every outcome here is a fact
measured off bars that had not printed yet when the reading was taken, so "does this reading
predict anything" becomes a question with a number for an answer.

🔴 **EVERY OUTCOME READS ONLY BARS STRICTLY AFTER THE READING BAR**, and every reading in
`measures.py` reads only bars up to and including it. The two halves never share a bar. If they
did, the study would grade a reading on information it partly contains and every correlation in
the report would be inflated by an amount nobody could see. `tests/test_causality.py` pins the
split at the bar boundary in both directions.

🔴 **A SHORT TAIL RETURNS `None`, IT IS NEVER PADDED OR CLAMPED TO WHAT EXISTS** (repo rule 3 —
never record what you requested as what you received). The last few hundred bars of any file have
no future to measure, and scoring them against a partial horizon would quietly mix two different
questions and weight the most recent market most heavily.

⚠ **Outcomes are in ATR at the reading bar, never in price.** A 20-dollar move on gold in 2019
and in 2026 are not the same event, and a study that summed them would be measuring the price of
gold rather than the behaviour of the market.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .measures import _true_range, atr


def _future(df: pd.DataFrame, i: int, horizon: int) -> pd.DataFrame | None:
    """Bars i+1 .. i+horizon, or None when the file does not hold all of them."""
    end = i + horizon
    if i < 0 or end >= len(df):
        return None
    return df.iloc[i + 1 : end + 1]


def forward_efficiency(df: pd.DataFrame, i: int, horizon: int) -> float | None:
    """Did the market go somewhere over the next `horizon` bars? 0 = chopped, 1 = straight line.

    The same measure as the trend reading in `measures.py`, pointed forwards. A trend reading
    that cannot predict this one is not measuring trend in any useful sense — this is the single
    most important cell in the report.
    """
    fut = _future(df, i, horizon)
    if fut is None:
        return None
    closes = np.concatenate(([df["close"].iloc[i]], fut["close"].to_numpy()))
    travel = float(np.abs(np.diff(closes)).sum())
    if travel <= 0:
        return None
    return float(abs(closes[-1] - closes[0]) / travel)


def forward_volatility_change(df: pd.DataFrame, i: int, horizon: int) -> float | None:
    """Next `horizon` bars' average true range against the previous `horizon` bars'.

    Above 1 = the market sped up, below 1 = it went quiet. Volatility is the one property of a
    market that genuinely does persist, so a volatility reading that CANNOT predict this is
    broken rather than merely unlucky.
    """
    fut = _future(df, i, horizon)
    if fut is None or i < horizon:
        return None
    past = df.iloc[i - horizon + 1 : i + 1]
    # True range needs each bar's predecessor, so both slices are taken with one bar of lead-in
    # and that lead-in row is dropped — otherwise the first true range in each window silently
    # uses a NaN previous close and the two halves are measured differently.
    past_tr = _true_range(df.iloc[i - horizon : i + 1]).iloc[1:]
    fut_tr = _true_range(df.iloc[i : i + horizon + 1]).iloc[1:]
    if len(past_tr) != len(past) or len(fut_tr) != len(fut):
        return None
    before, after = float(past_tr.mean()), float(fut_tr.mean())
    if not np.isfinite(before) or before <= 0 or not np.isfinite(after):
        return None
    return after / before


def forward_move(df: pd.DataFrame, i: int, horizon: int) -> float | None:
    """How far price ended up from here, in ATR. Unsigned — direction is the strategy's job."""
    fut = _future(df, i, horizon)
    if fut is None:
        return None
    unit = atr(df.iloc[: i + 1])
    if unit is None:
        return None
    return float(abs(float(fut["close"].iloc[-1]) - float(df["close"].iloc[i])) / unit)


def forward_excursion(df: pd.DataFrame, i: int, horizon: int) -> float | None:
    """The furthest price travelled either way before the horizon, in ATR.

    This is the outcome a STOP cares about, and it is deliberately different from where price
    ended up: a market that runs two ATR against you and comes back is the one that takes a bot
    out, and it looks identical to a quiet market in every end-point measure.
    """
    fut = _future(df, i, horizon)
    if fut is None:
        return None
    unit = atr(df.iloc[: i + 1])
    if unit is None:
        return None
    here = float(df["close"].iloc[i])
    up = float(fut["high"].max()) - here
    down = here - float(fut["low"].min())
    return float(max(up, down) / unit)


OUTCOMES: dict[str, dict] = {
    "forward_efficiency": {
        "fn": forward_efficiency,
        "label": "did the market go somewhere (0 chop - 1 straight)",
    },
    "forward_volatility_change": {
        "fn": forward_volatility_change,
        "label": "did it speed up (>1) or go quiet (<1)",
    },
    "forward_move": {"fn": forward_move, "label": "how far it ended up, in ATR"},
    "forward_excursion": {"fn": forward_excursion, "label": "furthest it ran either way, in ATR"},
}


def measure_all(df: pd.DataFrame, i: int, horizon: int) -> dict[str, float | None]:
    """Every outcome after bar `i`. Unmeasurable ones come back None, never 0."""
    return {name: spec["fn"](df, i, horizon) for name, spec in OUTCOMES.items()}
