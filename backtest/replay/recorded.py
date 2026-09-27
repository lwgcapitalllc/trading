"""Recorded streams — a per-bar output that depends only on the bars and a few settings, computed
once and replayed from disk on every later run.

🔴 **Why this exists.** The 1-minute re-entry runs the structure engine on every one of 2.4
million one-minute bars (2020-01..2026-09), and that stream is identical in every run on the same
bars whatever the strategy's own settings are. MEASURED 2026-09-27 on 87,985 one-minute bars:
2.50s to compute, 0.30s to load from disk. A sweep over strategy settings recomputed it per combo.

**The contract a producer must meet to be recorded here — check it, do not assume it:**

1. Its per-bar output is a pure function of the bars fed so far and the settings in the key.
2. Each output is FROZEN at the bar it was emitted and nothing mutates it later. An engine that
   hands out a live object and changes it on a later bar (the liquidity engine marks a level swept
   bars after emitting it) CANNOT be recorded: a stored copy is either frozen at emission — and a
   consumer that re-reads the object later sees stale state — or taken at the end, and the
   consumer sees the FUTURE. Neither is detectable in a result.
3. It is fed every bar of the frame, from the first, in order — the recording is only valid for
   that exact sequence, and the consumer's playback must refuse any other.

⚠ **Keyed on the bar bytes, the settings, and the source of every file that can change the
output.** An edit to any of them is a miss, by design. Anything that cannot be fingerprinted is a
miss, never a guess. The store fails OPEN: a corrupt or missing file recomputes.
"""

from __future__ import annotations

import hashlib
import json
import os
import pickle
import platform
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd

_STORE_DIR = Path(__file__).resolve().parents[1] / "cache" / "streams"

#: Total bytes kept on disk. The full 1-minute structure stream is ~250 MB, so this holds a
#: handful of windows and settings. The least recently used go first.
_MAX_BYTES = 5 * 1024**3


def _files_digest(sources: Iterable[Path]) -> str:
    h = hashlib.sha1()
    paths: List[Path] = []
    for src in sources:
        src = Path(src)
        paths.extend(sorted(src.rglob("*.py")) if src.is_dir() else [src])
    for p in paths:
        if "tests" in p.parts or "__pycache__" in p.parts:
            continue
        h.update(p.name.encode())
        h.update(p.read_bytes())  # a missing source raises, and key() turns that into no key
    return h.hexdigest()


def _frame_digest(h: "hashlib._Hash", df: pd.DataFrame) -> None:
    h.update(f"|rows={len(df)}|".encode())
    h.update(np.ascontiguousarray(df.index.values).tobytes())
    for col in ("open", "high", "low", "close"):
        arr = df[col].to_numpy()
        if arr.dtype == object:
            raise TypeError(f"column {col!r} is object dtype - cannot fingerprint exactly")
        h.update(np.ascontiguousarray(arr).tobytes())


def key(name: str, df: pd.DataFrame, settings: dict, sources: Sequence[Path]) -> Optional[str]:
    """Fingerprint of the stream, or None when any input cannot be taken."""
    try:
        h = hashlib.sha1()
        h.update(f"{name}|{json.dumps(settings, sort_keys=True)}|".encode())
        h.update(
            f"py={platform.python_version()}|np={np.__version__}|pd={pd.__version__}|".encode()
        )
        h.update(_files_digest(sources).encode())
        _frame_digest(h, df)
        return h.hexdigest()
    except Exception:  # noqa: BLE001 - "cannot key it" means recompute, never "no key needed"
        return None


def load(stream_key: Optional[str]) -> Optional[list]:
    if not stream_key:
        return None
    try:
        path = _STORE_DIR / f"{stream_key}.pkl"
        if not path.is_file():
            return None
        with path.open("rb") as fh:
            stored = pickle.load(fh)
        if not isinstance(stored, dict) or stored.get("key") != stream_key:
            return None
        outputs = stored.get("outputs")
        if not isinstance(outputs, list):
            return None
        os.utime(path)  # recently used survives the pruning
        return outputs
    except Exception:  # noqa: BLE001 - unreadable, truncated, mid-write: all mean "recompute"
        return None


def save(stream_key: Optional[str], outputs: list) -> None:
    if not stream_key:
        return
    try:
        _STORE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _STORE_DIR / f".{stream_key}.{os.getpid()}.tmp"
        with tmp.open("wb") as fh:
            pickle.dump(
                {"key": stream_key, "outputs": outputs}, fh, protocol=pickle.HIGHEST_PROTOCOL
            )
        tmp.replace(_STORE_DIR / f"{stream_key}.pkl")
        _prune()
    except Exception:  # noqa: BLE001
        pass


def _prune() -> None:
    files = sorted(_STORE_DIR.glob("*.pkl"), key=lambda p: p.stat().st_mtime, reverse=True)
    total = 0
    for p in files:
        total += p.stat().st_size
        if total > _MAX_BYTES:
            try:
                p.unlink()
            except OSError:
                pass
