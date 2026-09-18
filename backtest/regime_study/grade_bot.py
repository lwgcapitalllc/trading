"""Grader B — under each market reading, did THIS bot make or lose money?

Grader A asks whether a reading describes the market. This one asks the question you actually
act on: conditioned on the reading at the moment a trade was taken, what was the R, and is the
difference between readings bigger than luck.

🔴 **THE BAR USED IS THE LAST ONE THAT HAD ALREADY CLOSED WHEN THE TRADE WAS TAKEN, AND GETTING
THIS WRONG IS THE CLASSIC WAY A STUDY LIKE THIS LIES.** A bar is stamped with its OPEN time and
covers the period after it, so the bar containing the entry has not finished yet — reading it
hands the study the rest of that bar, which on a four-hour frame is hours of price the bot could
not see. The effect is subtle, always flattering, and invisible in the output. `_condition_index`
below steps back to the last fully closed bar and `tests/test_causality.py` pins it.

🔴 **SAMPLE SIZE IS THE POINT OF THIS FILE, NOT A FOOTNOTE.** A bot here may have 164 trades. Cut
five ways that is roughly thirty per group, and thirty trades of gold can show almost anything.
Every number below carries a range for that reason, and a range that straddles zero means the
group told us nothing — which is a RESULT and gets reported as one, never quietly tuned away.

⚠ **This reads a finished trade list; it never re-runs a strategy.** That keeps it strategy- and
instrument-agnostic — any tool that can emit an entry time and an R can be graded here — and it
keeps the study incapable of changing the run it is grading.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import measures
from .grade_market import LABELLERS, _minutes
from .stats import mean_ci, permutation_spread, quantile_buckets, spearman_ci

_WINDOW = 1200


def _condition_index(df: pd.DataFrame, when: pd.Timestamp) -> int | None:
    """Index of the last bar that had FULLY CLOSED at `when`. None when there is no such bar."""
    idx = df.index
    pos = int(idx.searchsorted(when, side="right")) - 1
    if pos < 0:
        return None
    bar_minutes = _minutes(df)
    # The bar at `pos` opened at or before `when`; it has closed only if its whole span is past.
    if idx[pos] + pd.Timedelta(minutes=bar_minutes) > when:
        pos -= 1
    return pos if pos >= 0 else None


def tag(
    trades: pd.DataFrame,
    df: pd.DataFrame,
    *,
    time_col: str = "entry_utc",
    r_col: str = "r",
    long_multiple: int = 6,
    with_label: bool = True,
) -> pd.DataFrame:
    """One row per trade: its R plus every reading of the market at the moment it was taken.

    Trades landing before the frame has enough history keep `None` readings and are dropped per
    column at scoring time — never silently discarded, because "the first two years of this bot
    could not be graded" is something the report has to be able to say out loud.
    """
    if time_col not in trades.columns or r_col not in trades.columns:
        raise ValueError(f"trade list needs {time_col!r} and {r_col!r} columns")
    stamps = pd.to_datetime(trades[time_col])
    if getattr(stamps.dt, "tz", None) is not None:
        stamps = stamps.dt.tz_localize(None)
    if getattr(df.index, "tz", None) is not None:
        df = df.tz_localize(None)

    rows = []
    label_cache: dict[tuple[str, int], str] = {}
    for stamp, r in zip(stamps, trades[r_col].astype(float)):
        row = {"entry": stamp, "r": float(r)}
        i = _condition_index(df, stamp)
        if i is None:
            row.update({name: None for name in measures.READINGS})
            if with_label:
                row.update(dict.fromkeys(LABELLERS, "UNKNOWN"))
            rows.append(row)
            continue
        lo = max(0, i + 1 - _WINDOW)
        row.update(measures.read_all(df.iloc[lo : i + 1]))
        if with_label:
            # Memoised per bar: two trades inside one condition bar share a label by definition,
            # and a labeller walks its whole frame on every call.
            for column, labeller in LABELLERS.items():
                key = (column, i)
                if key not in label_cache:
                    label_cache[key] = labeller(df, i, long_multiple)
                row[column] = label_cache[key]
        rows.append(row)
    return pd.DataFrame(rows)


def score(tagged: pd.DataFrame) -> dict:
    """The grade: per-reading relationship with R, and per-label average R — both with ranges."""
    out: dict = {"readings": {}, "label": {}, "n_trades": int(len(tagged))}

    for name in measures.READINGS:
        if name not in tagged.columns:
            continue
        pair = tagged[[name, "r"]].dropna()
        out["readings"][name] = {
            "relationship": spearman_ci(pair[name].to_numpy(), pair["r"].to_numpy(), blocks=False),
            "bands": bands(pair, name),
        }

    for column in LABELLERS:
        if column not in tagged.columns:
            continue
        frame = tagged[[column, "r"]].dropna()
        groups = {str(label): part["r"].to_numpy() for label, part in frame.groupby(column)}
        block = {
            "groups": {k: mean_ci(v, blocks=False) for k, v in groups.items()},
            "differ": permutation_spread(groups),
        }
        # The shipped engine keeps the top-level key it has always had, so a stored baseline
        # still reads the same way (root rule 11); a new labeller gets its own block.
        if column == "engine_label":
            out["label"] = block
        else:
            out[column] = block
    return out


def bands(pair: pd.DataFrame, name: str, count: int = 3) -> list[dict]:
    """The reading split into equal-population bands, each with its average R and range.

    Three bands by default, not five. With a couple of hundred trades, five bands is forty trades
    each and every range would swallow every other — the resolution would be decorative. A gate
    cut from a table nobody can distinguish is a gate fitted to noise.
    """
    values = pair[name].to_numpy(dtype=float)
    rs = pair["r"].to_numpy(dtype=float)
    if len(values) < 30:
        return []
    rows = []
    for lo, hi in quantile_buckets(values, count):
        top = values.max()
        mask = (values >= lo) & (values <= hi if hi == top else values < hi)
        if not mask.any():
            continue
        rows.append({"from": float(lo), "to": float(hi), **mean_ci(rs[mask], blocks=False)})
    return rows


def gate_preview(tagged: pd.DataFrame, name: str, threshold: float, above: bool) -> dict:
    """What refusing trades on one side of a threshold would have done to the whole run.

    ⚠ **This is a PREVIEW, and on the same trades the threshold was chosen from it is optimistic
    by construction** — the repo has been fooled by exactly this before. It exists so a candidate
    gate can be sized before anyone spends a replay on it, and the honest number only arrives
    from a real re-run on a window the threshold never saw. The kept/refused counts matter more
    than the R: a gate that refuses four trades cannot be measured at all.
    """
    pair = tagged[[name, "r"]].dropna()
    if pair.empty:
        return {"kept": 0, "refused": 0}
    values = pair[name].to_numpy(dtype=float)
    rs = pair["r"].to_numpy(dtype=float)
    refuse = values >= threshold if above else values <= threshold
    kept_r = rs[~refuse]
    return {
        "threshold": float(threshold),
        "side": "at or above" if above else "at or below",
        "kept": int((~refuse).sum()),
        "refused": int(refuse.sum()),
        "total_r_all": float(rs.sum()),
        "total_r_kept": float(kept_r.sum()),
        "refused_r": float(rs[refuse].sum()),
        "worst_run_all": _worst_run(rs),
        "worst_run_kept": _worst_run(kept_r),
    }


def _worst_run(rs: np.ndarray) -> float:
    """Deepest peak-to-trough stretch of the R curve. The drawdown number, in R not dollars
    (repo rule 6 — dollars across a shared balance are not comparable)."""
    if len(rs) == 0:
        return 0.0
    curve = np.cumsum(rs)
    return float(np.max(np.maximum.accumulate(curve) - curve))
