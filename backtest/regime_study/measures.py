"""Continuous readings of the market at one bar — the candidates that may replace a label.

🔴 **EVERY FUNCTION HERE IS CAUSAL AND THAT IS THE ONLY PROPERTY THAT MATTERS.** Each takes a
frame that ENDS at the bar being described and reads nothing past its last row. A reading that
peeked one bar ahead would score beautifully against the forward outcomes in `forward.py` and the
whole study would be a lie. `tests/test_causality.py` proves it by truncation: every reading is
computed twice, once on the window and once on the window with future bars appended, and the two
must be identical.

🔴 **"CANNOT ASK" IS `None`, NEVER `0.0`** (repo rule 1). A reading with too little history in
front of it returns `None` and is COUNTED as unanswerable by the grader. A reading that quietly
returned zero would be graded as a real measurement of a flat market, which is a different
market from one we could not see.

⚠ **Nothing here is a second implementation of `engines/regime/`.** The three readings the
canonical engine already uses are re-exposed below by IMPORTING its private calculators, so the
grader scores the engine's own arithmetic rather than a lookalike of it. If those ever diverge,
the engine is right and this file is broken.

⚠ **Scale-free by construction.** Every reading is a ratio, a rank or a bounded fraction, so a
number means the same thing on gold at $1,200 as on gold at $4,000 and can be compared across
instruments. A reading in price units could not be.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# The canonical engine's own signal maths, imported not copied. `engines/` goes on the path as a
# package because the classifier does a relative import of its thresholds — the same seam
# `algos/shared/shared_regime.py` and `strategies/python/extreme_leg/filters.py` already use.
_ENGINES = _ROOT / "engines"
if str(_ENGINES) not in sys.path:
    sys.path.insert(0, str(_ENGINES))

from engines.regime.classifier import _adx, _atr_ratio, _rsi_range  # noqa: E402

# ── helpers ──────────────────────────────────────────────────────────────────────


def _true_range(df: pd.DataFrame) -> pd.Series:
    h, l, prev = df["high"], df["low"], df["close"].shift(1)
    return pd.concat([h - l, (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)


def atr(df: pd.DataFrame, period: int = 14) -> float | None:
    """Average true range in PRICE units. Not a reading — the unit other things divide by."""
    if len(df) < period + 1:
        return None
    value = float(_true_range(df).rolling(period).mean().iloc[-1])
    return None if not np.isfinite(value) or value <= 0 else value


def _finite(value: float) -> float | None:
    return float(value) if np.isfinite(value) else None


# ── the candidate readings ───────────────────────────────────────────────────────


def trend_efficiency(df: pd.DataFrame, window: int = 60) -> float | None:
    """How much of the distance travelled ended up as progress. 0 = pure chop, 1 = straight line.

    Kaufman's efficiency ratio: the net move over the window divided by the sum of every
    bar-to-bar move inside it. It answers the question a trend-strength reading is REACHING for
    directly, in one line, with no smoothing constants and no arbitrary scale — where a
    trend-strength reading of 25 is a number whose meaning depends on the instrument and the
    timeframe, 0.35 here means the same thing everywhere.
    """
    if len(df) < window + 1:
        return None
    closes = df["close"].to_numpy()[-(window + 1) :]
    travel = float(np.abs(np.diff(closes)).sum())
    if travel <= 0:
        return None  # a window that never moved cannot be graded as efficient OR inefficient
    return _finite(abs(closes[-1] - closes[0]) / travel)


def volatility_percentile(df: pd.DataFrame, period: int = 14, lookback: int = 1000) -> float | None:
    """Where today's volatility ranks against its own past. 0 = quietest ever, 1 = wildest ever.

    🔴 **THIS IS THE READING THAT REPLACES A RAW VOLATILITY RATIO, AND THE DIFFERENCE IS NOT
    COSMETIC.** A ratio of current volatility to its 20-bar average says "faster than this
    fortnight", which in a long calm stretch flags a nothing-move as an expansion and in a crisis
    reads 1.0 while the market tears itself apart. A rank against a year of its own history says
    "faster than it usually is", which is the question a risk decision actually asks.

    The rank is strictly over history BEFORE and INCLUDING now, never a full-sample rank — a
    percentile computed against the whole file would know the future.
    """
    if len(df) < period + 1:
        return None
    series = _true_range(df).rolling(period).mean().dropna()
    if len(series) < 2:
        return None
    history = series.to_numpy()[-lookback:]
    current = history[-1]
    if not np.isfinite(current):
        return None
    # Clamped to the history that EXISTS, never to the history requested (repo rule 3). A short
    # window gives a coarse percentile, and the grader is told how many bars backed it.
    return _finite(float((history <= current).sum() - 1) / max(1, len(history) - 1))


def variance_ratio(df: pd.DataFrame, window: int = 240, lag: int = 8) -> float | None:
    """Do moves persist or unwind? Above 1 = they persist, below 1 = they revert, 1 = coin flip.

    The Lo–MacKinlay variance ratio: the variance of returns measured over `lag` bars, against
    `lag` times the variance measured bar to bar. In a market with no memory the two match by
    definition, so this is the one reading here that has a MEANINGFUL ZERO POINT rather than only
    a rank — and it is close to independent of how fast the market is moving, which is exactly
    what the canonical engine's three inputs are not.
    """
    if len(df) < window + lag + 1:
        return None
    closes = df["close"].to_numpy()[-(window + 1) :]
    if (closes <= 0).any():
        return None
    rets = np.diff(np.log(closes))
    if len(rets) < lag * 2:
        return None
    var_one = float(np.var(rets, ddof=1))
    if var_one <= 0:
        return None
    # Overlapping k-bar returns, which is the estimator's whole point — non-overlapping would
    # throw away all but 1/lag of the sample.
    cumulative = np.cumsum(rets)
    k_returns = cumulative[lag - 1 :] - np.concatenate(([0.0], cumulative[:-lag]))
    var_k = float(np.var(k_returns, ddof=1))
    return _finite(var_k / (lag * var_one))


def range_position(df: pd.DataFrame, window: int = 60) -> float | None:
    """Where price sits in its own recent range. 0 = at the low, 1 = at the high, 0.5 = middle.

    A market pinned at an extreme and one sitting mid-range behave differently even when every
    other reading here agrees, and nothing in the canonical engine asks this.
    """
    if len(df) < window:
        return None
    tail = df.iloc[-window:]
    high, low = float(tail["high"].max()), float(tail["low"].min())
    if high <= low:
        return None
    return _finite((float(df["close"].iloc[-1]) - low) / (high - low))


# ── the canonical engine's own three, so old and new are graded on one footing ───


def engine_trend_strength(df: pd.DataFrame) -> float | None:
    """The trend-strength reading the canonical engine scores on. Its maths, imported."""
    if len(df) < 34:
        return None
    return _finite(_adx(df))


def engine_volatility_ratio(df: pd.DataFrame) -> float | None:
    """The volatility-expansion reading the canonical engine scores on. Its maths, imported."""
    if len(df) < 34:
        return None
    return _finite(_atr_ratio(df))


def engine_momentum_swing(df: pd.DataFrame) -> float | None:
    """The momentum-swing reading the canonical engine scores on. Its maths, imported."""
    if len(df) < 34:
        return None
    return _finite(_rsi_range(df))


def candidate_persistence(df: pd.DataFrame) -> float | None:
    """The candidate's stickiness scale: the variance ratio RANKED against its own past.

    Imported lazily because `candidate.py` reads `volatility_percentile` from this module, and
    a module-level import here would close the circle. The lazy call is not a workaround for a
    layering mistake — the candidate is built ON the readings, and this registry entry exists
    so the candidate is scored by exactly the graders that score everything else, on the same
    rows and the same forward outcomes. Scoring it any other way would make the comparison
    against the shipped engine a comparison of two harnesses.
    """
    from backtest.regime_study.candidate import persistence_percentile

    return persistence_percentile(df)


# ── the registry ─────────────────────────────────────────────────────────────────
# Adding a candidate reading means adding one entry here and nothing else: the graders, the CLI
# and the output files all read this dict. That is the seam — a future engine's readings get
# scored against the same forward outcomes and the same baseline without touching a grader.

READINGS: dict[str, dict] = {
    "trend_efficiency": {
        "fn": trend_efficiency,
        "label": "how straight the move is (0 chop - 1 straight)",
        "family": "candidate",
    },
    "volatility_percentile": {
        "fn": volatility_percentile,
        "label": "how fast vs its own past year (0 calm - 1 wild)",
        "family": "candidate",
    },
    "variance_ratio": {
        "fn": variance_ratio,
        "label": "do moves persist (>1) or unwind (<1)",
        "family": "candidate",
    },
    "range_position": {
        "fn": range_position,
        "label": "where price sits in its recent range",
        "family": "candidate",
    },
    "candidate_persistence": {
        "fn": candidate_persistence,
        "label": "candidate: do moves stick, vs how much they usually do",
        "family": "candidate",
    },
    "engine_trend_strength": {
        "fn": engine_trend_strength,
        "label": "shipped engine: trend strength",
        "family": "shipped",
    },
    "engine_volatility_ratio": {
        "fn": engine_volatility_ratio,
        "label": "shipped engine: volatility expansion",
        "family": "shipped",
    },
    "engine_momentum_swing": {
        "fn": engine_momentum_swing,
        "label": "shipped engine: momentum swing",
        "family": "shipped",
    },
}


def read_all(df: pd.DataFrame) -> dict[str, float | None]:
    """Every reading at the last bar of `df`. Unanswerable ones come back None, never 0."""
    return {name: spec["fn"](df) for name, spec in READINGS.items()}
