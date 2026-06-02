"""
Hardcoded correlation pairs for the correlation note on StrategyDetail.
M4 will replace this with a real correlation matrix from live data.
"""

from __future__ import annotations

HIGHLY_CORRELATED_PAIRS: list[tuple[str, str, float]] = [
    ("MES",  "MNQ",  0.85),
    ("ES",   "NQ",   0.85),
    ("GC",   "MGC",  1.00),  # same instrument, different contract size
    ("CL",   "MCL",  1.00),
    ("MYM",  "M2K",  0.72),
    ("ES",   "MES",  1.00),
    ("NQ",   "MNQ",  1.00),
]


def find_correlated_pairs(instruments: list[str]) -> list[tuple[str, str, float]]:
    """Return all correlated pairs found within the given instrument list."""
    result = []
    inst_set = set(instruments)
    for a, b, corr in HIGHLY_CORRELATED_PAIRS:
        if a in inst_set and b in inst_set:
            result.append((a, b, corr))
    return result
