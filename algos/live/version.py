"""version.py — which code is trading, provably.

**The problem.** The VPS runs `git pull origin main`. Edit a strategy locally to test an idea,
push, and the next pull + restart silently changes what is trading — with nothing anywhere
recording that it happened. Aaron's requirement is the opposite: *"I need to know exactly which
version of the strategy is trading."*

**Two mechanisms, because it is two different problems.**

1. **Parameters** are frozen in the bot's own instance `config.json` and read from there — never
   from the strategy's `config.py` defaults. So a lab experiment that changes a default cannot
   reach the live bot at all. Promoting a setting is an explicit write to that file.
2. **Code** is pinned by CONTENT. The instance config records `strategy_source_hash` and the
   commit it was promoted from; at startup the bot re-hashes the strategy package on disk and
   **refuses to start on a mismatch**. A code change that arrives through a routine `git pull`
   cannot quietly start trading — it stops the bot and says so.

Refusing is the right failure direction. The alternative is a bot that keeps running while
nobody can say what it is running, which is the state this module exists to make impossible.

The hash is the one `command-center`'s scanner computes
(`strategy_scanner._python_source_hash`): every `.py` in the package except tests, sorted, with
each file's NAME hashed alongside its body so a rename registers. Reimplemented here rather
than imported because `algos/` and `command-center/` are independent — but it must stay
identical, or a version promoted from the lab would never match on the VPS.

**Line endings are normalised before hashing, and that is not cosmetic.** Promotion happens on
the Mac; the bot runs on the Windows VPS, which has `core.autocrlf = true`, so git REWRITES
every newline on checkout. A byte-exact hash therefore never matched across the two machines —
measured 2026-07-31, every one of `config.py`'s 185 newlines differed — and the pin would have
refused to start every single time, on identical code. A pin that always fires is a pin that
gets switched off. The hash must describe the CODE, not the line-ending policy of the machine
that checked it out, so `\r\n` and a lone `\r` both fold to `\n` first.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Optional


class VersionMismatch(RuntimeError):
    """The strategy code on disk is not the code this bot was promoted to run."""


def python_source_hash(pkg_dir: Path) -> str:
    """Content hash of a strategy package. MUST match
    `command-center/backend/services/strategy_scanner._python_source_hash` exactly.

    Newlines are normalised to `\\n` so the same source hashes the same on the Mac the code is
    promoted from and the Windows VPS it runs on — see the module docstring for why that is a
    correctness requirement and not a tidy-up.
    """
    h = hashlib.md5()
    for py in sorted(Path(pkg_dir).rglob("*.py")):
        if "tests" in py.parts:          # test edits don't change what the strategy DOES
            continue
        h.update(py.name.encode("utf-8"))
        h.update(py.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
    return h.hexdigest()


def current_commit(repo_root: Path) -> str:
    """The commit the working tree is on, short form. Empty string if git can't answer —
    reported for the record, never used as a gate (a missing git is not a reason to refuse to
    trade; a changed strategy hash is)."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip()
    except Exception:
        return ""


def verify_pin(pkg_dir: Path, pinned_hash: Optional[str]) -> str:
    """Return the on-disk hash, raising `VersionMismatch` if it differs from the pin.

    `pinned_hash` of None or "" means UNPINNED — allowed, and the caller should say so loudly in
    its startup log. An unpinned bot is a bot nobody can audit later, so it is a state to pass
    through on the way to a promotion, not one to live in.
    """
    actual = python_source_hash(pkg_dir)
    if not pinned_hash:
        return actual
    if actual != pinned_hash:
        raise VersionMismatch(
            f"Strategy code on disk does not match this bot's pinned version.\n"
            f"  package: {pkg_dir}\n"
            f"  pinned : {pinned_hash}\n"
            f"  on disk: {actual}\n"
            f"The repo moved under a running deployment. Either check out the promoted commit, "
            f"or promote the current code deliberately (which re-pins the hash). Refusing to "
            f"trade code that was never promoted."
        )
    return actual
