"""Grader A — does a reading of the market predict what the market does next?

This grader knows nothing about any bot. It walks the bars, describes each one with every
reading in `measures.py` and with the shipped engine's own label, then measures what actually
happened over the following bars, and asks whether the two are related.

🔴 **A READING THAT FAILS HERE CANNOT BE RESCUED BY A STRATEGY.** If the shipped engine's
trend reading does not predict whether the market goes anywhere, then no gate built on it is
doing what its name says, however well a particular bot happens to have done under it. That is
the whole reason this grader exists separately from the per-bot one: a bot with 164 trades can
show almost anything by luck, and this grader has tens of thousands of bars to say whether there
was ever a signal to find.

🔴 **THE LONG FRAME IS BUILT HERE AND IS RECORDED IN THE MANIFEST** (repo rule 11 — anything
recreating a run for comparison carries forward everything that decides what it was measured
on). The shipped engine takes two frames and its answer depends entirely on which two. Grading it
on one pairing and then deploying it on another would make every number in the report describe a
system nobody runs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import forward, measures
from .stats import mean_ci, permutation_spread, quantile_buckets, spearman_ci

# How much history each reading is handed. Long enough for the slowest of them (the volatility
# rank wants ~1000 bars) with room to spare, and bounded so the walk stays linear rather than
# re-reading the whole file at every bar.
_WINDOW = 1200


def _label_at(df: pd.DataFrame, i: int, long_multiple: int) -> str:
    """The shipped engine's label at bar `i`, from its own code, on bars up to `i` only."""
    from engines.regime.classifier import classify_regime

    lo = max(0, i + 1 - _WINDOW)
    short = df.iloc[lo : i + 1]
    if len(short) < 200:
        return "UNKNOWN"
    rule = f"{long_multiple * _minutes(df)}min"
    long_df = (
        short.resample(rule)
        .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
        .dropna()
    )
    return classify_regime(short, long_df)


def _candidate_label_at(df: pd.DataFrame, i: int, long_multiple: int) -> str:
    """The candidate's label at bar `i`, on bars up to `i` only.

    `long_multiple` is accepted and unused: the candidate reads ONE frame, where the shipped
    engine reads two. The parameter stays in the signature so both labellers are called
    identically by `walk` — a labeller that had to be special-cased at the call site is one
    a future third labeller would have to be special-cased against too.
    """
    from backtest.regime_study.candidate import classify

    lo = max(0, i + 1 - _WINDOW)
    return classify(df.iloc[lo : i + 1]) or "UNKNOWN"


#: Every labeller the walk records, by the column it writes. Adding a labeller here is the only
#: change needed to have it graded beside the others - on the SAME rows, the same forward
#: outcomes and the same shuffle test, which is the only way two labels can be compared at all.
LABELLERS = {
    "engine_label": _label_at,
    "candidate_label": _candidate_label_at,
}


def _minutes(df: pd.DataFrame) -> int:
    """The frame's bar size in minutes, measured off the index rather than trusted from a flag."""
    deltas = df.index.to_series().diff().dropna()
    if deltas.empty:
        raise ValueError("cannot measure the bar size of an empty or single-row frame")
    return int(deltas.mode().iloc[0].total_seconds() // 60)


def walk(
    df: pd.DataFrame,
    *,
    horizon: int,
    step: int = 1,
    long_multiple: int = 6,
    with_label: bool = True,
) -> pd.DataFrame:
    """One row per sampled bar: every reading, the shipped label, and every forward outcome.

    ⚠ Rows where a reading or an outcome could not be computed keep `None` in that cell and are
    dropped per COLUMN at scoring time, never per row. Dropping a whole row because one slow
    reading had not warmed up yet would silently shorten every other reading's sample to the
    slowest one's, and the report would not say so.
    """
    rows = []
    for i in range(0, len(df), step):
        lo = max(0, i + 1 - _WINDOW)
        window = df.iloc[lo : i + 1]
        outcomes = forward.measure_all(df, i, horizon)
        if all(v is None for v in outcomes.values()):
            continue  # no future to grade against — the tail of the file
        row = {"time": df.index[i], "bar": i}
        row.update(measures.read_all(window))
        row.update(outcomes)
        if with_label:
            for column, labeller in LABELLERS.items():
                row[column] = labeller(df, i, long_multiple)
        rows.append(row)
    return pd.DataFrame(rows)


def score(walked: pd.DataFrame) -> dict:
    """Turn the walk into the grade: a range around each reading-outcome pair, and the label table.

    The range is what gets read, never the point estimate. A range spanning zero is the report
    saying this reading told us nothing about this outcome.
    """
    out: dict = {"readings": {}, "label": {}}

    for name in measures.READINGS:
        if name not in walked.columns:
            continue
        for outcome in forward.OUTCOMES:
            if outcome not in walked.columns:
                continue
            pair = walked[[name, outcome]].dropna()
            if len(pair) < 30:
                out["readings"].setdefault(name, {})[outcome] = {
                    "n": len(pair),
                    "rho": None,
                    "lo": None,
                    "hi": None,
                }
                continue
            out["readings"].setdefault(name, {})[outcome] = spearman_ci(
                pair[name].to_numpy(), pair[outcome].to_numpy(), blocks=True
            )

    for column in LABELLERS:
        if column not in walked.columns:
            continue
        # `out["label"]` keeps the shipped engine at the top level so every file written before
        # the candidate existed still reads the same way; the candidate gets its own block.
        # Renaming the old key would silently break every comparison against a stored baseline,
        # which is root rule 11 - what recreates a run for comparison carries everything that
        # decides what it is measured on.
        into = out["label"] if column == "engine_label" else out.setdefault(column, {})
        for outcome in forward.OUTCOMES:
            if outcome not in walked.columns:
                continue
            frame = walked[[column, outcome]].dropna()
            groups = {str(label): part[outcome].to_numpy() for label, part in frame.groupby(column)}
            into[outcome] = {
                "groups": {k: mean_ci(v, blocks=True) for k, v in groups.items()},
                "differ": permutation_spread(groups),
            }
    return out


def bucket_table(walked: pd.DataFrame, reading: str, outcome: str, count: int = 5) -> list[dict]:
    """The reading split into equal-population bands, with each band's average outcome and range.

    This is the shape a gate is eventually cut from — a correlation says a relationship exists,
    and a band table says WHERE on the reading the behaviour actually changes, which is the only
    form a threshold can be read off.
    """
    pair = walked[[reading, outcome]].dropna()
    if len(pair) < 50:
        return []
    values = pair[reading].to_numpy()
    rows = []
    for lo, hi in quantile_buckets(values, count):
        mask = (values >= lo) & (values <= hi if hi == values.max() else values < hi)
        band = pair[outcome].to_numpy()[mask]
        if len(band) == 0:
            continue
        stat = mean_ci(band, blocks=True)
        rows.append({"from": lo, "to": hi, **stat})
    return rows


def label_share(walked: pd.DataFrame, column: str = "engine_label") -> dict[str, float]:
    """How often each label fires. A label that never appears cannot gate anything, and a label
    covering 90% of bars is not describing a condition — both are invisible in a table of
    averages, and both have shipped in this repo before."""
    if column not in walked.columns or walked.empty:
        return {}
    counts = walked[column].value_counts()
    return {str(k): float(v) / float(len(walked)) for k, v in counts.items()}


def flip_rate(walked: pd.DataFrame, column: str = "engine_label") -> float | None:
    """How often the label changes from one sampled bar to the next.

    🔴 **THE NUMBER THAT DECIDES WHETHER A GATE IS USABLE AT ALL.** A condition that changes every
    few bars is not a condition, and a bot gated on it is turned on and off inside a single move —
    which costs money in a way no average-outcome table would ever reveal.
    """
    if column not in walked.columns or len(walked) < 2:
        return None
    labels = walked[column].to_numpy()
    return float(np.mean(labels[1:] != labels[:-1]))
