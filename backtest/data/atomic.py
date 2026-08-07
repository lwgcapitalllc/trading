"""All-or-nothing cache writes, and one writer at a time per cache entry.

🔴 **Built 2026-08-06, after the XAUUSD M1 cache was destroyed twice in one day by two
processes writing it at once — and both times the damage was SILENT.**

`BarCache.save` is a read-modify-write: load the whole CSV, merge the new bars in, write the
whole CSV back. Two of those interleaving is not a race that loses a few rows. The second
writer lands its bytes on top of the first's at whatever offset it reached, so the file ends up
as two different frames stitched together, with one token cut in half at the seam:

    2026-03-01 23:59:00,5385.17,...     ← the tail of writer A's file
    6-17 07:47:00,1722.35,...           ← writer B's, clipped mid-timestamp
    2020-06-17 07:48:00,1723.46,...

The measured version of that was 2.59M rows claiming to be one sorted history and containing
two, and it took three failed quarter fetches to notice. The earlier M15 incident the same day
was worse, because it produced no parse error at all: the file simply lost ~31,000 rows out of
its middle while `ranges.json` went on claiming full coverage, so nothing would ever have
re-fetched them. **A cache that lies about being complete is the failure this whole package
exists to prevent, and concurrency was a hole straight through it.**

Two mechanisms, and they answer different halves:

1. **`atomic_write_*` — a reader never sees a partial file.** The content is written to a temp
   file beside the target and then `os.replace`d, which is atomic within a filesystem. A reader
   gets either the whole old file or the whole new one. This alone makes the torn-file shape
   above impossible.
2. **`cache_lock` — a writer never loses another writer's work.** Atomicity is not enough on
   its own: two writers can each read the same base file, merge their own bars, and replace it
   in turn, and the second one silently discards the first one's fetch. The file stays valid
   and the coverage sidecar still claims both spans, which is the *quiet* version of the same
   lie. The lock makes read-merge-write one operation.

⚠ **The lock covers the CSV and its `ranges.json` sidecar TOGETHER, and that pairing is the
point.** The invariant worth protecting is not "the CSV is valid" — it is *coverage never
claims more than the bars on disk*. Locking each file separately would keep both files
individually well-formed and still let a crash or an interleave land between the save and the
record, which is precisely the state that strands missing bars behind a cache HIT for ever.

⚠ **It is re-entrant on purpose.** `BarSource._load_base` holds it across the save/record pair
while `BarCache.save` takes it again underneath — and `flock` is per file DESCRIPTOR, so a
second acquisition through a fresh fd in the same process would deadlock against itself rather
than nest. The depth count is what makes the inner call free, and the `threading.RLock` is what
makes a second THREAD wait instead of walking straight through the flock its own process
already holds.
"""

from __future__ import annotations

import json
import os
import re
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

try:                                    # POSIX: a real cross-process lock.
    import fcntl
    CROSS_PROCESS = True
except ImportError:                     # pragma: no cover - Windows
    fcntl = None                        # type: ignore[assignment]
    CROSS_PROCESS = False

# ⚠ `CROSS_PROCESS` is exported rather than swallowed. On a platform with no `flock` this
# degrades to a THREAD lock, which protects one process's own workers and nothing else — and a
# lock that silently protects less than it claims is the same class of defect it was built to
# fix. Everything in this repo that writes the cache runs on macOS/Linux; the flag exists so a
# future Windows caller can see the difference rather than inherit it.


def _safe(token: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", token).strip("_")


class _Entry:
    """Per-lock-path state: the in-process gate, the held fd, and the nesting depth."""

    __slots__ = ("rlock", "fd", "depth")

    def __init__(self) -> None:
        self.rlock = threading.RLock()
        self.fd = -1
        self.depth = 0


_entries: dict[str, _Entry] = {}
_entries_guard = threading.Lock()


def lock_path(cache_dir: str | os.PathLike, symbol: str, tf_name: str) -> Path:
    """The lock file for one (symbol, timeframe) cache entry.

    A separate `.lock` file rather than locking the CSV itself: the CSV is replaced wholesale on
    every write, and a lock held on a file that gets unlinked out from under it protects an inode
    nobody can reach any more.
    """
    return Path(cache_dir) / f"{_safe(symbol)}__{_safe(tf_name)}.lock"


@contextmanager
def cache_lock(cache_dir: str | os.PathLike, symbol: str, tf_name: str) -> Iterator[None]:
    """Exclusive access to one (symbol, timeframe) cache entry — CSV, meta and ranges.

    Blocks until the holder releases. Re-entrant within a process (see the module docstring for
    why that is required rather than convenient).
    """
    key = str(lock_path(cache_dir, symbol, tf_name))
    with _entries_guard:
        entry = _entries.setdefault(key, _Entry())

    entry.rlock.acquire()
    acquired_fd = False
    try:
        if entry.depth == 0:
            Path(key).parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(key, os.O_RDWR | os.O_CREAT, 0o644)
            try:
                if fcntl is not None:
                    fcntl.flock(fd, fcntl.LOCK_EX)
            except BaseException:
                os.close(fd)
                raise
            entry.fd = fd
            acquired_fd = True
        entry.depth += 1
        try:
            yield
        finally:
            entry.depth -= 1
            if entry.depth == 0 and acquired_fd:
                try:
                    if fcntl is not None:
                        fcntl.flock(entry.fd, fcntl.LOCK_UN)
                finally:
                    os.close(entry.fd)
                    entry.fd = -1
    finally:
        entry.rlock.release()


def _replace_via_temp(path: Path, write: Any) -> None:
    """Write through a sibling temp file, then `os.replace` onto `path`.

    The temp file is a SIBLING, never `/tmp`: `os.replace` is atomic only within one filesystem,
    and across a mount boundary it degrades to a copy — which is the partial-file window this
    function exists to close, reintroduced by the fix.

    The temp name carries the pid so two writers cannot clobber each other's temp file. That is
    belt-and-braces under `cache_lock`, and it is what keeps this function safe for a caller that
    forgets the lock: the worst case becomes a lost update rather than a corrupt file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    try:
        write(tmp)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def atomic_write_text(path: str | os.PathLike, text: str) -> None:
    """Replace `path`'s contents with `text`, all or nothing."""
    _replace_via_temp(Path(path), lambda tmp: Path(tmp).write_text(text, encoding="utf-8"))


def atomic_write_json(path: str | os.PathLike, obj: Any) -> None:
    """Replace `path` with `obj` as JSON, all or nothing."""
    atomic_write_text(path, json.dumps(obj))


def atomic_write_csv(path: str | os.PathLike, df: pd.DataFrame) -> None:
    """Replace `path` with `df` as CSV, all or nothing. The frame is written as given —
    reset the index first if the caller wants it as a column."""
    _replace_via_temp(Path(path), lambda tmp: df.to_csv(tmp, index=False))
