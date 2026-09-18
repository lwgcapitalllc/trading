"""The arithmetic that turns "these numbers look related" into a range you can act on.

🔴 **THE BAR-LEVEL BOOTSTRAP IS A MOVING BLOCK BOOTSTRAP AND THAT IS NOT A DETAIL.** Consecutive
bars are not independent — a volatility reading barely moves from one bar to the next, so 400,000
bars carry nowhere near 400,000 independent observations. Resampling them one at a time would
produce a confidence range perhaps five to ten times too NARROW, and every reading in the report
would come back confidently significant, including pure noise. Resampling in contiguous blocks
keeps the local correlation inside each block, and the range it produces is the honest one. This
is the exact failure that makes most published regime studies worthless, and the repo has a rule
about believing a number just because its arithmetic reproduces.

⚠ **TRADES USE THE ORDINARY BOOTSTRAP AND THAT IS DELIBERATE.** Two trades days apart share no
bars and are close to independent, so blocks would only throw away resolution on the sample that
is already the smallest.

🔴 **A RANGE THAT STRADDLES THE NO-EFFECT POINT MEANS THE READING TOLD US NOTHING.** Not "a weak
signal", not "promising". Every summary in this package prints the range rather than the point
estimate for that reason — a bare correlation of 0.04 reads as a small effect when it is usually
no effect at all.

⚠ **Rank correlation, not ordinary correlation.** Every reading here is bounded or long-tailed
and gold has fat tails; an ordinary correlation on this data is dominated by a handful of crisis
bars. Ranks ask the question we mean — when this reading is higher, does the outcome tend to be
higher — and a single 2020 bar cannot carry it.
"""

from __future__ import annotations

import numpy as np

# Fixed so a report is reproducible: the same inputs must print the same range twice, or nobody
# can tell a real change from resampling noise when comparing two engine versions.
_SEED = 20260917


def _rank(values: np.ndarray) -> np.ndarray:
    """Average ranks, ties shared — the ordinary competition ranking would bias every bounded
    reading, and `range_position` alone produces thousands of ties."""
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    ranks[order] = np.arange(len(values), dtype=float)
    # Average the ranks inside each run of equal values.
    sorted_vals = values[order]
    start = 0
    for end in range(1, len(values) + 1):
        if end == len(values) or sorted_vals[end] != sorted_vals[start]:
            if end - start > 1:
                ranks[order[start:end]] = ranks[order[start:end]].mean()
            start = end
    return ranks


def spearman(x: np.ndarray, y: np.ndarray) -> float | None:
    """Rank correlation. None when either side is constant — undefined, not zero."""
    if len(x) < 3 or len(x) != len(y):
        return None
    rx, ry = _rank(np.asarray(x, dtype=float)), _rank(np.asarray(y, dtype=float))
    sx, sy = rx.std(), ry.std()
    if sx <= 0 or sy <= 0:
        return None
    return float(((rx - rx.mean()) * (ry - ry.mean())).mean() / (sx * sy))


def block_length(n: int) -> int:
    """How many consecutive bars travel together in one resample.

    The standard n^(1/3) rule for a moving block bootstrap, floored at 2 so blocks exist at all
    and capped at an eighth of the sample so a resample is never three blocks wide. This is a
    rule of thumb and is stated as one — it is chosen from sample size only, never fitted to the
    data, because a block length tuned until the answer looked significant would be the whole
    study fitting itself.
    """
    return int(max(2, min(n // 8, round(n ** (1 / 3)))))


def _block_indices(n: int, size: int, rng: np.random.Generator) -> np.ndarray:
    starts = rng.integers(0, n - size + 1, size=int(np.ceil(n / size)))
    idx = (starts[:, None] + np.arange(size)[None, :]).ravel()
    return idx[:n]


def spearman_ci(
    x: np.ndarray, y: np.ndarray, *, blocks: bool, draws: int = 2000, level: float = 0.95
) -> dict:
    """Rank correlation with a bootstrap range around it.

    `blocks=True` for bar-level data (neighbouring rows are correlated), False for trades.
    """
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    point = spearman(x, y)
    n = len(x)
    if point is None or n < 30:
        return {"n": n, "rho": point, "lo": None, "hi": None, "blocks": None}
    rng = np.random.default_rng(_SEED)
    size = block_length(n) if blocks else 1
    samples = []
    for _ in range(draws):
        idx = _block_indices(n, size, rng) if blocks else rng.integers(0, n, size=n)
        value = spearman(x[idx], y[idx])
        if value is not None:
            samples.append(value)
    if len(samples) < draws // 2:
        return {"n": n, "rho": point, "lo": None, "hi": None, "blocks": size}
    lo, hi = np.quantile(samples, [(1 - level) / 2, 1 - (1 - level) / 2])
    return {"n": n, "rho": point, "lo": float(lo), "hi": float(hi), "blocks": size}


def mean_ci(values: np.ndarray, *, blocks: bool, draws: int = 2000, level: float = 0.95) -> dict:
    """A group's average with a bootstrap range around it."""
    values = np.asarray(values, dtype=float)
    n = len(values)
    if n == 0:
        return {"n": 0, "mean": None, "lo": None, "hi": None}
    if n < 10:
        # Too few to put a range on. The average is still reported, WITHOUT a range, so a thin
        # bucket cannot be mistaken for a measured one.
        return {"n": n, "mean": float(values.mean()), "lo": None, "hi": None}
    rng = np.random.default_rng(_SEED)
    size = block_length(n) if blocks else 1
    samples = [
        float(values[_block_indices(n, size, rng) if blocks else rng.integers(0, n, n)].mean())
        for _ in range(draws)
    ]
    lo, hi = np.quantile(samples, [(1 - level) / 2, 1 - (1 - level) / 2])
    return {"n": n, "mean": float(values.mean()), "lo": float(lo), "hi": float(hi)}


def permutation_spread(groups: dict[str, np.ndarray], draws: int = 2000) -> dict:
    """Do these labelled groups differ at all, or is the spread what shuffling produces anyway?

    Answers the question a table of per-label averages invites and never settles. The statistic is
    the spread between the highest and lowest group average; the labels are then shuffled against
    the values and the spread recomputed, which is the distribution of "this table, if the label
    meant nothing". A high share means the real table is unremarkable.
    """
    names = [k for k, v in groups.items() if len(v) > 0]
    if len(names) < 2:
        return {"spread": None, "share_as_extreme": None, "draws": 0}
    values = np.concatenate([groups[k] for k in names])
    sizes = [len(groups[k]) for k in names]
    observed = float(max(groups[k].mean() for k in names) - min(groups[k].mean() for k in names))
    rng = np.random.default_rng(_SEED)
    hits = 0
    for _ in range(draws):
        shuffled = rng.permutation(values)
        means, at = [], 0
        for size in sizes:
            means.append(shuffled[at : at + size].mean())
            at += size
        if max(means) - min(means) >= observed:
            hits += 1
    return {"spread": observed, "share_as_extreme": hits / draws, "draws": draws}


def quantile_buckets(values: np.ndarray, count: int = 5) -> list[tuple[float, float]]:
    """Edges that split a reading into equal-population bands.

    Equal POPULATION, never equal width — a reading like volatility rank is uniform by
    construction but a raw trend-strength reading is not, and fixed-width bands on it would put
    most of the sample in one box and three trades in another.
    """
    values = np.asarray(values, dtype=float)
    edges = np.unique(np.quantile(values, np.linspace(0, 1, count + 1)))
    if len(edges) < 3:
        return []
    return [(float(edges[i]), float(edges[i + 1])) for i in range(len(edges) - 1)]
