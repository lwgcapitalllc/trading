"""Identical-rerun cache for Python lab backtests — a run whose every input matches an earlier
run's gets that run's results back instead of replaying the bars again.

🔴 **Why this exists.** A full SOS Fade run on the 1-minute re-entry feed took 976 seconds
(run 7760823a639e, 2026-09-27), and the lab re-runs the same basis constantly — a retry, a
comparison, a stress child, a sweep point that lands on a combination already measured. A
backtest is a pure function of its inputs, so the second answer is the first answer.

⚠ **Keyed on EVERYTHING that decides the answer, and refuses rather than guess.** The key is:
the whole job spec except its id, the bytes of every bar frame the run replays, the conversion
rate series when one is installed, the source of every file that can move a trade (`backtest/`,
`engines/`, `strategies/python/`, the news calendar, and this runner), and the Python / numpy /
pandas versions. An edit anywhere in that tree misses the cache on purpose — a cached result from
superseded code is exactly the silent wrongness this repo keeps paying for (root CLAUDE.md,
rule 11). When any part cannot be fingerprinted, `key()` returns None and the run replays: a
refusal costs minutes, a partial key serves a stale answer forever.

⚠ **Fails OPEN.** A broken, missing or half-written cache file is a miss, never an error — this
is a shortcut for the next run, never part of producing this one.

Same design as the regime-map cache in `backtest_runner.py`, which it deliberately mirrors.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import sys
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

_MONOREPO = Path(__file__).resolve().parents[3]
_CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "run_cache"

#: Bumped by hand when the MEANING of a stored result changes without any fingerprinted file
#: changing — e.g. a new field the lab starts expecting in `results`.
_CACHE_LOGIC_VERSION = "1"

#: Newest results kept. A sweep writes one file per point; without a ceiling the folder grows
#: for ever. The oldest by modification time are removed first.
_MAX_ENTRIES = 2000

#: Source trees whose files can change a trade. Tests and parity exports cannot, and are skipped.
_SOURCE_TREES = ("backtest", "engines", "strategies/python")
_SKIP_PARTS = {"tests", "__pycache__", "exports", "cache", "reports", "archive"}
_EXTRA_FILES = (
    "engines/news/data/events.json",  # the news filter reads it; fetched data, not source
    "command-center/backend/services/python_runner.py",
    "command-center/backend/services/run_feeds.py",
    "command-center/backend/services/strategy_import.py",
    "command-center/backend/services/run_result_cache.py",
)


def _source_digest() -> str:
    h = hashlib.sha1()
    files: list[Path] = []
    for tree in _SOURCE_TREES:
        for p in (_MONOREPO / tree).rglob("*"):
            if not p.is_file() or _SKIP_PARTS.intersection(p.relative_to(_MONOREPO).parts):
                continue
            if p.suffix == ".py" or p.name.endswith(".meta.json"):
                files.append(p)
    files.sort()
    for p in files:
        h.update(str(p.relative_to(_MONOREPO)).encode())
        h.update(p.read_bytes())
    for rel in _EXTRA_FILES:
        p = _MONOREPO / rel
        h.update(rel.encode())
        # A missing file is a VALUE in the key, not a skipped one: the news filter behaves
        # differently with no calendar than with one.
        h.update(p.read_bytes() if p.is_file() else b"<absent>")
    return h.hexdigest()


def _frame_digest(h: "hashlib._Hash", df: pd.DataFrame) -> None:
    h.update(f"|rows={len(df)}|cols={','.join(map(str, df.columns))}|".encode())
    h.update(np.ascontiguousarray(df.index.values).tobytes())
    for col in df.columns:
        # Exact stored bytes, no dtype coercion — an object column is refused below rather than
        # converted, because a lossy conversion would let two different frames share a key.
        arr = df[col].to_numpy()
        if arr.dtype == object:
            raise TypeError(f"column {col!r} is object dtype - cannot fingerprint exactly")
        h.update(np.ascontiguousarray(arr).tobytes())


def _rate_digest(h: "hashlib._Hash", rate: Any) -> None:
    """The conversion series, when one is installed. Only a bound method of a series we can read
    exactly is accepted; anything else refuses the cache."""
    if rate is None:
        h.update(b"|rate=none|")
        return
    series = getattr(rate, "__self__", None)
    times, closes = getattr(series, "_t", None), getattr(series, "_c", None)
    if times is None or closes is None:
        raise TypeError(f"unrecognised rate provider {rate!r} - cannot fingerprint")
    h.update(f"|rate|invert={getattr(series, '_invert', None)}|".encode())
    h.update(np.asarray(times, dtype=np.int64).tobytes())
    h.update(json.dumps(list(closes)).encode())


def key(spec: dict, frames: Iterable[pd.DataFrame], rate: Any = None) -> Optional[str]:
    """Fingerprint every input of this run, or None when any one of them cannot be taken."""
    try:
        h = hashlib.sha1()
        basis = {k: v for k, v in spec.items() if k != "job_id"}
        h.update(json.dumps(basis, sort_keys=True, default=repr).encode())
        h.update(
            f"|v={_CACHE_LOGIC_VERSION}|py={platform.python_version()}"
            f"|np={np.__version__}|pd={pd.__version__}|".encode()
        )
        h.update(_source_digest().encode())
        for df in frames:
            _frame_digest(h, df)
        _rate_digest(h, rate)
        return h.hexdigest()
    except Exception as exc:  # noqa: BLE001 - any failure means "cannot key it", never "no key needed"
        log.warning("run cache: could not fingerprint inputs (%s) - replaying", exc)
        return None


def read(cache_key: Optional[str]) -> Optional[dict]:
    """The stored results for this key, or None."""
    if not cache_key:
        return None
    try:
        path = _CACHE_DIR / f"{cache_key}.json"
        if not path.is_file():
            return None
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or data.get("key") != cache_key:
            return None
        results = data.get("results")
        if not isinstance(results, dict):
            return None
        os.utime(path)  # recently used survives the pruning
        return results
    except Exception:  # noqa: BLE001 - unreadable, truncated, mid-write: all mean "no shortcut"
        return None


def write(cache_key: Optional[str], results: dict) -> None:
    """Store the results, atomically. Fails open and silently.

    ⚠ Only stored when a JSON round trip gives back EXACTLY what the run produced. A result
    holding a tuple, a NaN-bearing structure the encoder rewrites, or any non-JSON object would
    come back from the cache as a subtly different value — so it is simply not cached."""
    if not cache_key or not isinstance(results, dict):
        return
    try:
        text = json.dumps({"key": cache_key, "results": results})
        if not _same(json.loads(text)["results"], results):
            log.info("run cache: results do not survive a JSON round trip - not cached")
            return
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _CACHE_DIR / f".{cache_key}.{os.getpid()}.tmp"
        tmp.write_text(text)
        tmp.replace(_CACHE_DIR / f"{cache_key}.json")
        _prune()
    except Exception:  # noqa: BLE001
        pass


def _same(a: Any, b: Any) -> bool:
    """Exact equality with the TYPE checked too, and NaN equal to NaN — so a tuple that would come
    back as a list, or an int that would come back as a float, counts as a difference."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    if isinstance(a, float) and a != a:
        return b != b
    return a == b


def _prune() -> None:
    entries = sorted(_CACHE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
    for p in entries[: max(0, len(entries) - _MAX_ENTRIES)]:
        try:
            p.unlink()
        except OSError:
            pass


if __name__ == "__main__":  # pragma: no cover - a quick look at the source fingerprint
    print(_source_digest(), sys.version)
