"""One BUILD on the trading box at a time, across every process this app runs.

🔴 **WHY IT EXISTS (2026-10-01).** Deploys started together each ran `git pull` and promote.py on
the box at the same time, and the box has two CPUs. MEASURED over the 20 deploy records then on
disk: a build alone took 11-17s; a build overlapping others took 17-36s, and 4 of the 11
overlapping deploys hit the 30s SSH limit and failed ("may or may not have deployed"), against 0
of 9 alone. The same load starves the LIVE bots on that box while it lasts.

**The rule: the pull and the build hold this lane; everything after them does not.** Stopping,
starting and confirming a bot are light and are left to overlap — a build is about a quarter of a
deploy (pull ~2s, build ~12s, stop ~10s, start ~2s, confirm ~25s, from the same records), so
lining up only the builds costs a batch of four roughly nothing against the timeouts it removes.

⚠ **Waited for, unlike `bot_ops`, and the difference is WHAT is contended.** `bot_ops` refuses a
second action on ONE bot, because two stop/starts on one process is a state nobody meant. This
lane is a shared MACHINE: two deploys of two different bots are both meant, and the second simply
goes next. The waiter is told who it is behind (`on_wait`), so the page can say "Queued".

⚠ **An OS file lock, not a threading lock.** Every deploy runs in its own process
(`services/promote_worker.py`) and a preview runs on a backend thread; `flock` is the one primitive
all of them share. The OS drops it when its holder dies, so a crashed deploy can never leave the
lane shut. POSIX only — the backend runs on the laptops, never on the Windows box.

⚠ Two clones each run their own backend and do not see each other's lane — the same limit
`bot_ops` names. The box has no lock of its own to offer.
"""

from __future__ import annotations

import fcntl
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

_DEFAULT = Path(__file__).resolve().parent.parent / "data" / "box_build.lock"


def _path() -> Path:
    raw = os.environ.get("CC_BOX_LANE_LOCK")
    return Path(raw) if raw else _DEFAULT


@contextmanager
def hold(who: str, on_wait: Callable[[str], None] | None = None) -> Iterator[None]:
    """Hold the lane for the duration of the block, waiting for it if another build has it.

    `who` is written into the lock file while held, so a waiter can name what it is behind.
    `on_wait` is called ONCE, with that name, only when the lane was taken — never on a free one,
    so "queued" is never claimed for a build that did not wait."""
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+", encoding="utf-8") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            if on_wait is not None:
                f.seek(0)
                on_wait(f.read().strip() or "another deploy")
            fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.seek(0)
            f.truncate()
            f.write(who)
            f.flush()
            yield
        finally:
            f.seek(0)
            f.truncate()
            f.flush()
            fcntl.flock(f, fcntl.LOCK_UN)
