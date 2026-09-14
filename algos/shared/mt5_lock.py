"""mt5_lock.py — the MT5 connect lock, ONE PER TERMINAL.

`BotMT5.connect` takes a file lock around `initialize` + `login`, so two bots starting against the
SAME terminal do not race each other through its login. Its own docstring says that is the
purpose: *"concurrent bot startups don't race against the same terminal."*

🔴 **Until 2026-09-13 the lock was ONE FILE FOR THE WHOLE BOX, so it serialised terminals that
have nothing to do with each other.** Each account has its own terminal, so a connect on one
account made every other account's bots queue behind it — and a terminal that hung mid-connect
(an auto-update restarts one underneath its bots, measured 2026-08-04) held the lock until it went
stale, then its waiters gave up after `LOCK_TIMEOUT`, failed to connect, and exited for the
watchdog to restart. **One account's bad terminal could take another account's bots down**, which
is the one thing two separately owned accounts on one box must never do to each other.

Keyed on the terminal's path, normalised, because that is the thing being protected: two bots on
one account share one terminal and still wait for each other, exactly as before.

⚠ **The old single `mt5_connect.lock` matches `mt5_connect*.lock`**, so every cleaner that sweeps
the prefix (the boot sequence, the Command Center's stop-all) also clears a lock left by a bot
still running the code from before this change.

Pure standard library — the boot sequence and the tests load it without MetaTrader5.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import List, Optional

ALGOS_ROOT = Path(__file__).resolve().parent.parent
LOCK_PREFIX = "mt5_connect"

# How long a connect waits for the lock, and how old a lock must be before a waiter may take it
# over. Unchanged from the single lock's values — splitting the lock changes WHO waits, not how long.
LOCK_TIMEOUT = 90
LOCK_TTL = 45


def terminal_slug(mt5_path: str) -> str:
    """A terminal path as a file-name fragment. Case, slashes and quotes are folded, so two
    spellings of one terminal share one lock — a lock that two bots on one terminal did NOT share
    would let them race, which is the whole thing it exists to stop."""
    norm = (mt5_path or "").strip().strip('"').replace("/", "\\").lower()
    slug = re.sub(r"[^a-z0-9]+", "_", norm).strip("_")
    return slug[-100:] or "default"


def lock_path(mt5_path: str, root: Optional[Path] = None) -> Path:
    """The lock file for this terminal."""
    base = Path(root) if root is not None else ALGOS_ROOT
    return base / f"{LOCK_PREFIX}_{terminal_slug(mt5_path)}.lock"


def all_locks(root: Optional[Path] = None) -> List[Path]:
    """Every connect lock on the box, per-terminal and the old single one alike."""
    base = Path(root) if root is not None else ALGOS_ROOT
    return sorted(base.glob(f"{LOCK_PREFIX}*.lock"))


def stale_locks(
    root: Optional[Path] = None, *, now: Optional[float] = None, ttl: float = LOCK_TTL
) -> List[Path]:
    """The locks older than `ttl` — the only ones a cleaner may remove.

    ⚠ **A fresh lock is a bot mid-connect and must be left alone.** The boot sequence used to delete
    the lock outright on every run, and running it to restart ONE bot pulled the lock from under
    whichever other bot was connecting at that moment. A lock that cannot be dated is left too:
    removing what you cannot judge is the guess this module exists to avoid.
    """
    now = time.time() if now is None else now
    out: List[Path] = []
    for p in all_locks(root):
        try:
            age = now - p.stat().st_mtime
        except OSError:
            continue
        if age > ttl:
            out.append(p)
    return out
