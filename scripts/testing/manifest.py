"""What the working tree holds, as {path: content hash}; what moved since a green run; the records.

⚠ **Content, never timestamps.** A green run is recorded against the HASH of every file it saw,
so a touched-but-identical file is not a change and an edit reverted by hand is not either. Two
sessions share this clone, and a clock-based record would let one session's run vouch for
another session's edit made a second later.

⚠ **The manifest is taken at the START of a run and recorded at the end.** A file edited while the
tests were running then reads as changed next time, which is the conservative direction: the run
cannot vouch for content it may never have seen.

⚠ **What it cannot see, stated rather than hidden:** git-ignored data (the bar cache the re-pricing
replays read, the news calendar) and git HISTORY (the deploy-version tests read the real log). A
change to either needs `--force`. Installed packages ARE covered - see env_key().
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LOG_DIR = REPO / ".test-logs"
GREEN = LOG_DIR / "green.json"


def _git(*args, input_=None) -> str:
    out = subprocess.run(
        ["git", "-C", str(REPO), *args],
        input=input_,
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout


def current() -> dict:
    """{path: blob hash} for every tracked and untracked-but-not-ignored file, as it is on disk."""
    tree = {}
    for rec in _git("ls-files", "-s", "-z").split("\0"):
        if rec:
            meta, path = rec.split("\t", 1)
            tree[path] = meta.split()[1]
    moved = [p for p in _git("diff", "--name-only", "--no-renames", "-z").split("\0") if p]
    extra = [p for p in _git("ls-files", "-o", "--exclude-standard", "-z").split("\0") if p]
    to_hash = []
    for p in moved + extra:
        if (REPO / p).is_file():
            to_hash.append(p)
        else:
            tree.pop(p, None)  # deleted on disk, still in the index
    if to_hash:
        hashes = _git("hash-object", "--stdin-paths", input_="\n".join(to_hash) + "\n").split()
        tree.update(zip(to_hash, hashes))
    return tree


def at(rev: str) -> dict:
    tree = {}
    for rec in _git("ls-tree", "-r", "-z", rev).split("\0"):
        if rec:
            meta, path = rec.split("\t", 1)
            tree[path] = meta.split()[2]
    return tree


def diff(old: dict, new: dict) -> dict:
    out = {}
    for p, h in new.items():
        if p not in old:
            out[p] = "added"
        elif old[p] != h:
            out[p] = "modified"
    for p in old:
        if p not in new:
            out[p] = "deleted"
    return out


def env_key(python: str) -> str:
    """The interpreter and every package installed beside it - a pip upgrade moves every suite."""
    site = Path(python).resolve().parent.parent / "lib"
    names = sorted(
        d.name for d in site.glob("python*/site-packages/*") if d.name.endswith(".dist-info")
    )
    return hashlib.sha256(
        (sys.version + "\n" + str(Path(python).resolve()) + "\n" + "\n".join(names)).encode()
    ).hexdigest()[:16]


def upstream_base():
    """(rev, label) to compare against when no run has ever gone green: everything not pushed."""
    try:
        base = _git("merge-base", "HEAD", "@{upstream}").strip()
        return base, "the last pushed commit"
    except subprocess.CalledProcessError:
        return "HEAD", "the last commit"


def load_green(tier: str):
    try:
        return json.loads(GREEN.read_text()).get(tier)
    except (OSError, ValueError):
        return None


def save_green(tier: str, tree: dict, env: str) -> None:
    """Record a green run. A full run is also the newest green for the fast tier."""
    try:
        data = json.loads(GREEN.read_text())
    except (OSError, ValueError):
        data = {}
    rec = {
        "tier": tier,
        "time": _dt.datetime.now().isoformat(timespec="seconds"),
        "head": _git("rev-parse", "HEAD").strip(),
        "env": env,
        "manifest": tree,
    }
    data["any"] = rec
    if tier == "full":
        data["full"] = rec
    LOG_DIR.mkdir(exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=LOG_DIR, suffix=".json")
    with os.fdopen(fd, "w") as fh:
        json.dump(data, fh)
    os.replace(tmp, GREEN)  # two sessions share this file; never leave it half-written


def describe(rec) -> str:
    when = rec.get("time", "?").replace("T", " ")
    return f"the last green {rec.get('tier', '?')} run ({when})"
