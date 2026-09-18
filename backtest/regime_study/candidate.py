"""A candidate market-condition reading, built to be SCORED before it is shipped.

🔴 **THIS IS NOT AN ENGINE AND MUST NOT BE IMPORTED BY A STRATEGY.** It lives under
`backtest/` on purpose: a candidate sitting in `engines/regime/` is one import away from
reaching a live bot before anything has graded it, and the repo has shipped that mistake
before. It moves into the engine when, and only when, `grade_market.py` and `grade_bot.py`
say it beats what is there — and the engine keeps exactly one implementation either way
(root `CLAUDE.md`, *Never Do*).

WHAT IT CHANGES, AND WHY EACH CHANGE HAS A MEASUREMENT BEHIND IT
(the measurement is `backtest/notes/regime-grading.md`, 12,372 four-hour gold bars):

1. **Two scales, not one label.** The shipped engine folds three inputs into one score and
   then one of five names. Measured, 78% of all bars came out with the same name, which is
   not a reading — it is a constant with noise on it. Here the two questions are answered
   separately and never collapsed, because "fast" and "sticky" are different facts and a
   market can be either without being the other.

2. **Ranked against its own past, not against a round number.** Every threshold in the
   shipped engine is a hand-picked constant, identical for every instrument. A reading of
   "faster than it usually is" needs no such constant and cannot go stale: the bands are
   thirds of the instrument's own trailing history, so each band holds a third of the bars
   BY CONSTRUCTION and the degenerate 78% bucket is impossible.

3. **The two readings measured were the two that survived eight years.** How fast the market
   is moving relative to its own history was the strongest single reading in the study; how
   much moves persist was the only other one with a real link to whether the NEXT stretch
   trends. Two readings the shipped engine uses were indistinguishable from noise on three
   of four outcomes, and the third tracked only future volatility.

⚠ **THE BANDS ARE RELATIVE AND THAT IS A REAL PROPERTY, NOT A DETAIL.** In a permanently calm
year "fast" still fires a third of the time. That is the right shape for a gate deciding
*should this bot trade now, compared with how this market usually is* — and the wrong shape
for a question about absolute danger. Say which question is being asked before using it.

⚠ **CAUSAL, like everything else here.** Each function takes a frame that ENDS at the bar
being described and reads nothing past its last row. Every rolling window looks backwards
only, and the rank is over history up to and including now — a full-sample rank would know
the future and would score beautifully for that reason alone.

⚠ **"Cannot ask" is `None`, never a middle value** (root rule 1). Too little history returns
`None`, which the grader counts as unanswerable. A 0.5 would be graded as a real measurement
of an ordinary market, and an ordinary market is not the same thing as no answer.

⚠ **No hidden state, no randomness, no fitting** — `engines/regime/CLAUDE.md` forbids all
three, and nothing here has any. The same frame always returns the same answer.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from backtest.regime_study.measures import volatility_percentile

__all__ = [
    "SPEED_BANDS",
    "STICKINESS_BANDS",
    "persistence_percentile",
    "read",
    "classify",
    "band_of",
]

#: The two band names, quietest/most-reverting first. Thirds of the instrument's own history,
#: so the populations are equal by construction rather than by luck.
SPEED_BANDS = ("QUIET", "NORMAL", "FAST")
STICKINESS_BANDS = ("REVERTING", "NEUTRAL", "PERSISTING")

#: A rank needs history to rank against. 1,000 bars is ~6 months of four-hour gold — long
#: enough that a band means something, short enough that a reading adapts within a regime
#: rather than being anchored to a market that no longer exists. Below this the reading is
#: still ANSWERED, against whatever history exists, and `read` reports how much backed it, so
#: the grader can tell a coarse answer from a fine one (root rule 3 — clamp to the data that
#: is there, never to the data that was asked for).
LOOKBACK = 1000

#: The minimum history that makes a rank meaningful at all. Below it, `None`.
MIN_RANKED = 60


def _rank_last(history: np.ndarray) -> float | None:
    """Where the last value sits among the ones before it. 0 = lowest ever, 1 = highest ever."""
    history = history[np.isfinite(history)]
    if len(history) < MIN_RANKED:
        return None
    current = history[-1]
    return float((history <= current).sum() - 1) / max(1, len(history) - 1)


def persistence_percentile(
    df: pd.DataFrame, window: int = 240, lag: int = 8, lookback: int = LOOKBACK
) -> float | None:
    """Do moves stick or unwind, ranked against this market's own past. 1 = stickiest ever.

    The underlying quantity is the Lo-MacKinlay variance ratio — the variance of returns over
    `lag` bars against `lag` times the bar-to-bar variance. It is RANKED here rather than read
    against its textbook no-memory value of 1.0, because measured over eight years of gold the
    thing never centres on 1.0 (its middle third ran 0.985 to 1.133), so a band drawn at the
    textbook value would not split this market into the parts the theory names.

    Computed as a rolling series over the frame handed in, then ranked — every window inside it
    looks backwards only, so the answer for the last bar uses no bar after it.
    """
    closes = df["close"].to_numpy(dtype=float)
    if len(closes) < window + lag + MIN_RANKED or (closes <= 0).any():
        return None
    rets = pd.Series(np.diff(np.log(closes)))
    # Overlapping k-bar returns — the estimator's whole point; non-overlapping would discard
    # all but 1/lag of the sample and make the rank far noisier than the data deserves.
    k_returns = rets.rolling(lag).sum()
    var_one = rets.rolling(window).var(ddof=1)
    var_k = k_returns.rolling(window).var(ddof=1)
    ratio = (var_k / (lag * var_one)).to_numpy()
    ratio = np.where(np.isfinite(ratio) & (var_one.to_numpy() > 0), ratio, np.nan)
    return _rank_last(ratio[-lookback:])


def band_of(percentile: float | None, names: tuple[str, ...]) -> str | None:
    """Which third of its own history a percentile falls in. `None` in, `None` out."""
    if percentile is None:
        return None
    if percentile < 1 / 3:
        return names[0]
    if percentile < 2 / 3:
        return names[1]
    return names[2]


def read(df: pd.DataFrame) -> dict:
    """Both scales at the last bar of `df`, plus how much history backed each one.

    Returns the raw percentiles as well as the bands. The bands are for a gate; the raw
    numbers are what the grader scores, because a threshold throws away most of what a
    continuous reading knows and the study measured that loss directly.
    """
    speed = volatility_percentile(df, lookback=LOOKBACK)
    stickiness = persistence_percentile(df, lookback=LOOKBACK)
    return {
        "speed": speed,
        "stickiness": stickiness,
        "speed_band": band_of(speed, SPEED_BANDS),
        "stickiness_band": band_of(stickiness, STICKINESS_BANDS),
        "bars": len(df),
    }


def classify(df: pd.DataFrame) -> str | None:
    """The two bands as one name, e.g. `FAST/REVERTING`. `None` when either cannot be asked.

    ⚠ It is a JOIN of two independent answers, never a score. Nothing here adds the two
    together or ranks one cell above another — that collapse is what produced the shipped
    engine's single 78% bucket, and there is no measurement saying the nine cells lie on a
    line. A consumer that wants an ordering has to justify its own.
    """
    both = read(df)
    if both["speed_band"] is None or both["stickiness_band"] is None:
        return None
    return f"{both['speed_band']}/{both['stickiness_band']}"
