"""version.py — which code is trading, provably.

**The problem.** The VPS runs `git pull origin main`. Edit a strategy locally to test an idea,
push, and the next pull + restart silently changes what is trading — with nothing anywhere
recording that it happened. Aaron's requirement is the opposite: *"I need to know exactly which
version of the strategy is trading."*

**Three mechanisms, because it is three different problems.**

1. **Parameters** are frozen in the bot's own instance `config.json` and read from there — never
   from the strategy's `config.py` defaults. So a lab experiment that changes a default cannot
   reach the live bot at all. Promoting a setting is an explicit write to that file.
2. **Code is COPIED, not referenced.** Promoting snapshots the three trees that decide what the
   bot trades into `instances/<bot>/deployed/`, and the runner imports from there. The repo
   working tree is then irrelevant to a running bot: pull, refactor, backtest a new version,
   break whatever you like — the deployment does not move until you promote again.
3. **The snapshot is pinned by CONTENT**, as a tamper check on top of (2). The config records
   the hash and the commit it was promoted from; the bot re-hashes at startup and refuses to
   start on a mismatch.

**(2) was missing until 2026-08-03, and (3) alone was not enough — that is the whole lesson
here.** The pin existed and worked, but it guarded a bot that imported live out of the repo, so
its normal job was to fire on ordinary work: a `git pull` on the VPS rewrote the strategy under
a running deployment, and the bot then refused to restart. Measured — the live bot sat dead for
three days on exactly that. Worse, the pin hashed only `strategies/python/<pkg>`, while the
strategy's actual logic lives in `engines/` and `backtest/`, so a change THERE moved the bot's
behaviour with the pin still green. A guard that fires on safe changes and stays quiet on
dangerous ones is worse than none: it trains you to switch it off.

The order matters. Freeze first so the pin has something stable to describe; pin second so
nobody can edit the frozen copy in place. Refusing is still the right failure direction — a bot
that keeps running while nobody can say what it is running is the state this module exists to
make impossible — but with (2) in place, refusing should now be a rare event rather than the
cost of doing routine work.

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


def deployment_hash(roots) -> str:
    """Content hash of EVERY tree that decides what a bot trades, in the order given.

    **Why this exists alongside `python_source_hash`.** That one hashes the strategy package,
    because it has to stay byte-identical to the lab's scanner. But the strategy is a thin
    layer: it imports `engines.*` (market structure, fibs, FVG, RSI divergence, sessions,
    liquidity) and `backtest.replay` / `backtest.fills`, and that is where the logic actually
    lives. Hashing only the package meant an engine could change under a GREEN pin — the bot
    would start, report the version it was promoted at, and trade different rules. That is the
    same failure shape as the phantom-exit bug: a guard that looks fine while the thing beneath
    it moved.

    Two deliberate differences from `python_source_hash`:

    * the path is hashed RELATIVE TO ITS ROOT, not just the filename, so moving a file between
      sub-packages registers as a change (`engines/a/x.py` → `engines/b/x.py` is not a no-op);
    * a root's name is folded in, so two roots cannot swap contents and hash the same.

    Line endings are normalised for the same reason as `python_source_hash` — the Windows VPS
    rewrites every newline on checkout, and a pin that always fires is a pin that gets switched
    off. A missing root hashes as empty rather than raising: an unpromoted bot has no snapshot
    yet, and that is reported by the caller as UNPINNED, not as a crash.
    """
    h = hashlib.md5()
    for root in roots:
        root = Path(root)
        h.update(f"\x00root:{root.name}\x00".encode("utf-8"))
        if not root.is_dir():
            continue
        for py in sorted(root.rglob("*.py")):
            rel = py.relative_to(root)
            if "tests" in rel.parts or "__pycache__" in rel.parts:
                continue
            h.update(rel.as_posix().encode("utf-8"))
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


def verify_pin(roots, pinned_hash: Optional[str], *, frozen: bool = True,
               bot_key: str = "") -> str:
    """Return the on-disk hash of `roots`, raising `VersionMismatch` if it differs from the pin.

    `pinned_hash` of None or "" means UNPINNED — allowed, and the caller should say so loudly in
    its startup log. An unpinned bot is a bot nobody can audit later, so it is a state to pass
    through on the way to a promotion, not one to live in.

    `frozen` says whether `roots` point at the bot's own snapshot or at the repo working tree,
    and it only changes the ADVICE in the error. On a frozen bot a mismatch means the snapshot
    was edited in place — someone reached past the promote step — and re-promoting is right. On
    an unfrozen one it means the repo moved, which is ordinary work and should never have been
    able to break a deployment; the fix there is to promote so the bot stops tracking the repo
    at all.
    """
    actual = deployment_hash(roots)
    if not pinned_hash:
        return actual
    if actual != pinned_hash:
        listed = "\n".join(f"    {Path(r)}" for r in roots)
        remedy = (
            "This bot's own deployed snapshot has been modified in place, which bypasses the "
            "promote step. Re-promote to re-pin it, or restore the snapshot."
            if frozen else
            "This bot is NOT FROZEN — it is still importing straight out of the repo working "
            "tree, so ordinary repo work (a pull, a lab experiment, a backtest of a new "
            "version) changes what it trades and stops it starting. Promote it: "
            f"`python algos/tools/promote.py --bot {bot_key or '<bot_key>'}` takes a snapshot "
            "so the repo can move freely without touching this deployment."
        )
        raise VersionMismatch(
            f"Deployed code does not match this bot's pinned version.\n"
            f"  roots  :\n{listed}\n"
            f"  pinned : {pinned_hash}\n"
            f"  on disk: {actual}\n"
            f"{remedy}"
        )
    return actual
