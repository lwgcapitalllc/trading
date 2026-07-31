"""log_backup.py — get the decision record off the VPS, and keep the raw logs bounded.

Run daily as `SYS_LOGBACKUP`:

    python C:/trading/algos/tools/log_backup.py            # do it
    python C:/trading/algos/tools/log_backup.py --dry-run  # say what it would do

**The problem this solves.** `algos/live/ledger.py` writes one JSONL line per bar, per
blocked setup, per trade — the only record of WHY the bot did what it did, and the input to
the shadow-diff that has to pass before real money moves. It lives on one VPS disk. There is
no historical trade data anywhere else in this repo (see `algos/CLAUDE.md` — the old suite
was deleted, deliberately, with nothing carried forward). Lose the disk and the dry run did
not happen; it has to be run again from zero.

So the two halves below are NOT the same job, and conflating them is the mistake to avoid:

  * **the ledger is COMMITTED to git.** That is what makes it survive the VPS. It is small,
    append-only, line-oriented text — exactly what git is good at.
  * **the raw `.log` files are ZIPPED IN PLACE and pruned.** That is only about keeping the
    disk bounded and the last 90 days readable. It does NOT leave the box, and nothing here
    pretends otherwise.

**Four decisions worth knowing before editing this.**

*Only days STRICTLY BEFORE today are committed.* Today's ledger file is still being appended
to by a running bot. Committing it captures a torn half-day that looks, in git, exactly like
a complete one — and the reader who later trusts it has no way to tell.

*It commits every uncommitted old file, not "yesterday's".* A job that only ever handles
yesterday loses any day the VPS was down, the push failed, or the task was disabled — and
loses it permanently and silently. Catching up on whatever is outstanding makes a missed run
a delay instead of a hole.

*It never runs `git add -A`.* This box has `credentials.json` on disk holding a live MT5
password and a Telegram token. A blanket add is one `.gitignore` slip from publishing them.
Only paths matching `*/ledger/decisions-YYYY-MM-DD.jsonl` are ever staged, and anything else
found in a ledger directory is skipped and named in the output.

*A failed push is loud and retried, not swallowed.* This is the only channel carrying
evidence off the VPS. If it silently stops, everything still looks fine — the files are on
disk, the task returns 0 — right up until the disk is gone.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# DERIVED, never hardcoded — the same rule as algos/shared/bot_state.py. A literal
# C:/trading path is right on the VPS and quietly wrong everywhere else, which is how a
# script becomes untestable on the machine it is written on.
ALGOS_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT  = ALGOS_ROOT.parent
INSTANCES  = ALGOS_ROOT / "markets" / "fx" / "instances"
ARCHIVE    = ALGOS_ROOT / "log_archive"

KEEP_DAYS = 90

# The ONLY filename shape this job will ever stage. Anything else in a ledger directory is
# somebody's scratch file, and a backup job is the wrong place to find out what it was.
LEDGER_RE = re.compile(r"^decisions-(\d{4})-(\d{2})-(\d{2})\.jsonl$")
ZIP_RE    = re.compile(r"^logs-(\d{4})-(\d{2})-(\d{2})\.zip$")


# ── choosing what to preserve ───────────────────────────────────────────────────
def ledger_files(instances: Path, today: date) -> tuple[list[Path], list[Path]]:
    """Return (closed ledger files, files skipped for not matching the shape).

    "Closed" means dated strictly before `today`: no bot can append to it again, so a commit
    can never race a write.
    """
    closed, skipped = [], []
    for ledger_dir in sorted(instances.glob("*/ledger")):
        for path in sorted(ledger_dir.iterdir()):
            if not path.is_file():
                continue
            m = LEDGER_RE.match(path.name)
            if not m:
                skipped.append(path)
                continue
            if date(int(m[1]), int(m[2]), int(m[3])) < today:
                closed.append(path)
    return closed, skipped


def uncommitted(repo: Path, paths: list[Path]) -> list[Path]:
    """Narrow to the files git does not already have identical content for.

    Without this the job commits nothing on most days but still pushes, and every run looks
    the same whether or not it did anything.
    """
    if not paths:
        return []
    rel = [str(p.relative_to(repo)).replace("\\", "/") for p in paths]
    out = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--", *rel],
                         capture_output=True, text=True)
    changed = {line[3:].strip().strip('"') for line in out.stdout.splitlines() if line.strip()}
    return [p for p, r in zip(paths, rel) if r in changed]


# ── the raw logs: bounded, local, and honest about being local ──────────────────
def archive_logs(instances: Path, archive: Path, today: date,
                 dry_run: bool = False) -> Path | None:
    """Snapshot every instance `.log` into one dated zip.

    COPIES rather than rotates. The bot holds its log open, and renaming a file Windows has
    open fails with a sharing violation — a rotation scheme here would work on the Mac,
    break on the VPS, and take the day's logs with it.
    """
    logs = sorted(p for p in instances.glob("*/*.log") if p.is_file())
    if not logs:
        return None

    target = archive / f"logs-{today.isoformat()}.zip"
    if dry_run:
        return target

    archive.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for log in logs:
            z.write(log, arcname=str(log.relative_to(instances)).replace("\\", "/"))
    return target


def prune(archive: Path, today: date, keep_days: int = KEEP_DAYS,
          dry_run: bool = False) -> list[Path]:
    """Delete zips older than `keep_days`, dated by FILENAME not mtime.

    An mtime is rewritten by a copy, a restore, or a backup tool, so pruning on it can throw
    away a file that is not actually old. The name is the only date that means anything here.
    Ledger files are never pruned — the decision record is the artefact, not the scratch.
    """
    cutoff, gone = today - timedelta(days=keep_days), []
    if not archive.exists():
        return gone
    for path in sorted(archive.iterdir()):
        m = ZIP_RE.match(path.name)
        if m and date(int(m[1]), int(m[2]), int(m[3])) < cutoff:
            gone.append(path)
            if not dry_run:
                path.unlink()
    return gone


# ── git ─────────────────────────────────────────────────────────────────────────
def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def commit_and_push(repo: Path, paths: list[Path], today: date,
                    dry_run: bool = False) -> bool:
    """Stage exactly `paths`, commit, push. Returns True if the work is safely at origin."""
    rel = [str(p.relative_to(repo)).replace("\\", "/") for p in paths]
    if dry_run:
        print(f"  would commit {len(rel)} file(s): {', '.join(rel)}")
        return True

    add = _git(repo, "add", "--", *rel)
    if add.returncode != 0:
        print(f"  git add failed: {add.stderr.strip()}")
        return False

    msg = (f"chore(ledger): decision record through {today - timedelta(days=1)}\n\n"
           f"Written by SYS_LOGBACKUP on the VPS. {len(rel)} file(s).")
    commit = _git(repo, "commit", "-m", msg, "--", *rel)
    if commit.returncode != 0 and "nothing to commit" not in commit.stdout:
        print(f"  git commit failed: {commit.stderr.strip() or commit.stdout.strip()}")
        return False

    if _git(repo, "push", "origin", "HEAD:main").returncode == 0:
        return True

    # Origin moved (a deploy from the Mac). Rebasing a ledger-only commit onto it cannot
    # conflict with source changes — different files entirely.
    print("  push rejected — rebasing onto origin/main and retrying")
    if _git(repo, "pull", "--rebase", "origin", "main").returncode != 0:
        print("  rebase failed — the commit is safe locally, next run will retry")
        return False
    if _git(repo, "push", "origin", "HEAD:main").returncode == 0:
        return True
    print("  push still rejected — the commit is safe locally, next run will retry")
    return False


# ── entry point ─────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Back up bot ledgers and logs.")
    ap.add_argument("--dry-run", action="store_true", help="report, change nothing")
    ap.add_argument("--keep-days", type=int, default=KEEP_DAYS)
    args = ap.parse_args(argv)

    today = datetime.now(timezone.utc).date()
    print(f"log_backup {today} {'(dry run)' if args.dry_run else ''}".rstrip())

    closed, skipped = ledger_files(INSTANCES, today)
    for path in skipped:
        print(f"  ! skipped, unrecognised name: {path}")

    pending = uncommitted(REPO_ROOT, closed)
    pushed  = True
    if pending:
        pushed = commit_and_push(REPO_ROOT, pending, today, args.dry_run)
        print(f"  ledger: {len(pending)} file(s) {'pushed' if pushed else 'NOT pushed'}")
    else:
        print(f"  ledger: nothing new ({len(closed)} closed file(s) already committed)")

    zipped = archive_logs(INSTANCES, ARCHIVE, today, args.dry_run)
    print(f"  logs:   {zipped.name if zipped else 'none found'}")

    dropped = prune(ARCHIVE, today, args.keep_days, args.dry_run)
    print(f"  pruned: {len(dropped)} archive(s) older than {args.keep_days} days")

    # Non-zero when the record did NOT reach origin. This is the only signal that the one
    # channel carrying evidence off this box has stopped working.
    return 0 if pushed else 1


if __name__ == "__main__":
    sys.exit(main())
