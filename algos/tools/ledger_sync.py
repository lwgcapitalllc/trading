"""ledger_sync.py — the Mac half: fetch the bot's record off the VPS and commit it.

Run it from the repo root, on the machine that has git credentials:

    python algos/tools/ledger_sync.py             # fetch, commit, push
    python algos/tools/ledger_sync.py --dry-run   # say what it would do
    python algos/tools/ledger_sync.py --no-push   # commit locally only
    python algos/tools/ledger_sync.py --closed-only   # skip today's open files

**It runs itself, twice a day.** `scripts/install_ledger_sync.sh` installs a launchd agent at
00:05 and 12:05 local (`com.lwg.ledger-sync`), which is Aaron's requirement from 2026-08-05 —
*"once a day is wrong, I think it should be at least twice a day."* launchd runs a missed
calendar job when the Mac next wakes, so a closed laptop delays the backup rather than skipping
it. ⚠ **It still only runs when this Mac is on**, and that is the honest limit of a design where
the box holding the data is not allowed to hold a git token (see below).

**Three kinds of file are fetched**, all per-day, all committed the same way:

  * `<bot>/ledger/decisions-YYYY-MM-DD.jsonl` — why it traded, or did not
  * `<bot>/ledger/health-YYYY-MM-DD.jsonl`    — starts, stops, crashes, link outages, pulses
  * `<bot>/<bot>-YYYY-MM-DD.log`              — the prose log, where the tracebacks are

**Today's files are fetched too, and they are still being written.** A copy taken mid-append can
end in a half-written line, so `_whole_lines` truncates a trailing partial JSON line before the
file is committed. The same day is fetched again on the next run with more in it, and git simply
sees a longer file. ⚠ The truncation applies to the JSONL streams only — a text log's last line
is prose, and losing a partial sentence to be tidy would be worse than committing it.

**Why the pull direction.** The VPS cannot push. Its scheduled task runs as SYSTEM, SYSTEM has
its own credential store, and Git Credential Manager there has no cached token and no
interactive session to ask for one — so `git push` BLOCKS rather than failing, until the task
is killed. Making it work means storing a GitHub write token on a box that already holds a
live MT5 password, which widens what a compromise costs for no trading benefit. See
`log_backup.py` for the measurement.

So the VPS bounds its own disk and reports which ledger days are closed; this runs where
credentials already work. The honest cost: **the record leaves the VPS when this runs, not on
a timer.** Until the day it prints has been committed, it exists on exactly one disk. That is
why the summary line says how many days are outstanding rather than just "done".

**What it will not do.** It stages only files it just fetched into `*/ledger/`, and only ones
matching `decisions-YYYY-MM-DD.jsonl` — never `git add -A`, never a path it did not write.

**Where it writes: `algos/ledger_archive/`, NOT the bot's own instance directory.** The bot
writes the live files, so the VPS always holds an untracked copy of every day this commits —
and git refuses to overwrite an untracked file on pull, which is correct and which broke `git
pull` on the VPS outright (measured 2026-08-05, the pull aborted). Committing into the live
path would have required a manual delete before every future pull, on the one box that has to
stay current. The archive mirrors the VPS layout so the two differ only by the root.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from log_backup import LEDGER_RE  # noqa: E402,F401  — one definition of a ledger filename

# The full shape a reported path must have. Two forms, because the record lives in two places:
#
#   <bot>/ledger/decisions-YYYY-MM-DD.jsonl
#   <bot>/ledger/health-YYYY-MM-DD.jsonl
#   <bot>/<bot>-YYYY-MM-DD.log
#
# Checking only the FILENAME is not enough. `--list-closed` output is read from another
# machine running whatever it last pulled, and this script turns each line into a local write
# target — so `../../../../decisions-2026-08-14.jsonl` has a perfectly valid filename and
# lands outside the repo entirely. Anchoring the whole path is the cheap way to make that
# impossible rather than unlikely, and it is why widening this to a second shape widened the
# ANCHOR too rather than loosening it.
REMOTE_PATH_RE = re.compile(
    r"^[A-Za-z0-9._-]+/(?:ledger/(?:decisions|health)-\d{4}-\d{2}-\d{2}\.jsonl"
    r"|[A-Za-z0-9._-]+-\d{4}-\d{2}-\d{2}\.log)$")

REPO_ROOT = _HERE.parent.parent
# 🔴 The archive is a SEPARATE tree from the bot's own instance directory, and that is not
# tidiness — writing it back to `algos/markets/fx/instances/<bot>/ledger/` broke `git pull`
# on the VPS (measured 2026-08-05: *"untracked working tree files would be overwritten by
# merge"*, and the pull aborted). The bot writes those files, so the VPS always holds its own
# untracked copy of every day this tool commits; git will not clobber one, and it is right not
# to. Every VPS pull would have needed a manual delete first, forever — on the box that has to
# stay current for the watchdog, the dead-man's switch and the live loop itself.
#
# It mirrors the VPS layout exactly (`<bot>/ledger/decisions-YYYY-MM-DD.jsonl`) so an archived
# file and its live original differ only by the root, which keeps a hand `diff` trivial and
# lets `REMOTE_PATH_RE` and the commit-msg hook's exemption pattern stay as they are.
LOCAL_ARCHIVE = REPO_ROOT / "algos" / "ledger_archive"

DEFAULT_HOST = "forexvps"
REMOTE_INSTANCES = "C:/trading/algos/markets/fx/instances"
REMOTE_PYTHON = r"C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe"
REMOTE_SCRIPT = r"C:\trading\algos\tools\log_backup.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True)


def remote_files(host: str, which: str) -> list[str]:
    """Ask the VPS which record files exist. `which` is "closed" or "open".

    Asking rather than re-deriving keeps "closed" defined in exactly one place. If the two
    sides ever disagreed, the way it would show up is a half-written day committed as a whole
    one — which is unreadable later and looks fine at the time.
    """
    out = _run("ssh", host, f'{REMOTE_PYTHON} {REMOTE_SCRIPT} --list-{which}')
    if out.returncode != 0:
        raise RuntimeError(f"could not list {which} files on {host}: {out.stderr.strip()}")
    return [line.strip() for line in out.stdout.splitlines()
            if REMOTE_PATH_RE.match(line.strip())]


def _whole_lines(path: Path) -> None:
    """Drop a trailing PARTIAL JSON line from a file copied while it was being appended to.

    ⚠ **Only for the `.jsonl` streams.** Half a record is not a record — it cannot be parsed,
    and committing it means every later reader has to defend against it. A text log is prose and
    keeps whatever it has, because half a sentence still says what was happening.

    The check is "does the last line parse", not "does it end in a newline": a write can be
    flushed complete without its newline landing yet, and truncating that would throw away a
    good record every single sync.
    """
    if path.suffix != ".jsonl" or not path.exists():
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if not lines:
        return
    try:
        json.loads(lines[-1])
    except ValueError:
        path.write_text("".join(f"{ln}\n" for ln in lines[:-1]), encoding="utf-8")
        return
    # Complete last record, but possibly with no newline behind it. Normalise so the next
    # sync's copy appends cleanly rather than producing one joined line in the diff.
    if not text.endswith("\n"):
        path.write_text(text + "\n", encoding="utf-8")


def fetch(host: str, rel_paths: list[str], dry_run: bool = False) -> list[Path]:
    """Copy each record file down into the local repo. Returns the local paths."""
    got = []
    for rel in rel_paths:
        local = LOCAL_ARCHIVE / rel
        if dry_run:
            got.append(local)
            continue
        local.parent.mkdir(parents=True, exist_ok=True)
        out = _run("scp", "-q", f"{host}:{REMOTE_INSTANCES}/{rel}", str(local))
        if out.returncode != 0:
            print(f"  ! fetch failed for {rel}: {out.stderr.strip()}")
            continue
        _whole_lines(local)
        got.append(local)
    return got


def ignored(paths: list[Path]) -> list[Path]:
    """Which of these files git is configured to ignore — i.e. can never be backed up.

    🔴 **This exists because the failure it catches is completely silent.** `.gitignore` carries
    a blanket `*.log`, so the first real sync copied the bot's daily text log down, `git status`
    did not list it (ignored files are not "changed"), `pending()` dropped it without a word, and
    the run reported success having committed two of the three streams. ⚠ **From the commit side
    an ignored file and a file that was never written are identical**, which is this repo's
    own never-let-two-different-things-be-one-value rule arriving through git's config.

    So an ignored fetch is NAMED and the run does not claim to be up to date.
    """
    if not paths:
        return []
    rel = [str(p.relative_to(REPO_ROOT)) for p in paths]
    # `check-ignore` exits 1 when NOTHING matches, which is the ordinary case — so the return
    # code says nothing here and only the output is read.
    out = _run("git", "-C", str(REPO_ROOT), "check-ignore", "--", *rel)
    hit = {line.strip() for line in out.stdout.splitlines() if line.strip()}
    return [p for p, r in zip(paths, rel) if r in hit]


def pending(paths: list[Path]) -> list[Path]:
    """Narrow to files git does not already have identical content for."""
    if not paths:
        return []
    rel = [str(p.relative_to(REPO_ROOT)) for p in paths]
    out = _run("git", "-C", str(REPO_ROOT), "status", "--porcelain", "--", *rel)
    changed = {line[3:].strip().strip('"') for line in out.stdout.splitlines() if line.strip()}
    return [p for p, r in zip(paths, rel) if r in changed]


def commit(paths: list[Path], push: bool, dry_run: bool = False) -> bool:
    """Stage exactly `paths` and commit. Returns True if the record is safely at origin."""
    rel = [str(p.relative_to(REPO_ROOT)) for p in paths]
    if dry_run:
        print(f"  would commit {len(rel)} file(s): {', '.join(rel)}")
        return True

    if _run("git", "-C", str(REPO_ROOT), "add", "--", *rel).returncode != 0:
        print("  git add failed")
        return False

    days = sorted({m[0] for p in paths for m in [re.findall(r"\d{4}-\d{2}-\d{2}", p.name)] if m})
    span = (days[0] if len(days) == 1 else f"{days[0]}..{days[-1]}") if days else "?"
    msg = (f"chore(ledger): bot record {span}\n\n"
           f"Fetched from the VPS by algos/tools/ledger_sync.py. {len(rel)} file(s).")
    c = _run("git", "-C", str(REPO_ROOT), "commit", "-m", msg, "--", *rel)
    if c.returncode != 0 and "nothing to commit" not in c.stdout:
        print(f"  git commit failed: {c.stderr.strip() or c.stdout.strip()}")
        return False

    if not push:
        print("  committed locally (--no-push)")
        return False
    if _run("git", "-C", str(REPO_ROOT), "push", "origin", "HEAD:main").returncode == 0:
        return True
    print("  push failed — the commit is safe locally, re-run after a pull")
    return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fetch bot records from the VPS and commit them.")
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--closed-only", action="store_true",
                    help="skip today's still-open files (the pre-2026-08-05 behaviour)")
    args = ap.parse_args(argv)

    today = datetime.now(timezone.utc).date()
    print(f"ledger_sync {today} from {args.host} {'(dry run)' if args.dry_run else ''}".rstrip())

    try:
        rel = remote_files(args.host, "closed")
        # Today's files are the whole point of running this twice a day: without them the
        # record still leaves the VPS exactly once, just at a different hour.
        if not args.closed_only:
            rel += remote_files(args.host, "open")
    except RuntimeError as e:
        print(f"  ! {e}")
        return 1

    if not rel:
        print("  nothing on the VPS to fetch")
        return 0

    local = fetch(args.host, rel, args.dry_run)
    # `pending` is a read-only `git status` query, so it is safe on a dry run and belongs on
    # one: skipping it made --dry-run report EVERY closed day as "would commit", including days
    # already committed, so it could never print "up to date" and always overstated the work.
    # A dry run that cannot say "nothing to do" is not a preview of the real run.
    #
    # ⚠ On a dry run the files were never fetched, so this compares what git already has
    # against the working tree rather than against the VPS. Days already committed are
    # correctly reported as done; a day whose local copy is somehow STALE would be reported as
    # done too, and only the real run would catch it. That is the honest limit of previewing a
    # copy you have not made.
    # Before anything else: a file git is configured to ignore can never reach origin, and it
    # drops out of `pending()` looking exactly like a file that is already committed.
    blocked = ignored(local)
    for p in blocked:
        print(f"  ! IGNORED by .gitignore, so it can never be backed up: "
              f"{p.relative_to(REPO_ROOT)}")

    todo = pending(local)
    if not todo:
        if blocked:
            print(f"  {len(blocked)} file(s) fetched but unbackupable — fix .gitignore")
            return 1
        print(f"  up to date ({len(rel)} file(s) on the VPS, all already committed)")
        return 0

    ok = commit(todo, push=not args.no_push, dry_run=args.dry_run)
    print(f"  {len(todo)} file(s) {'pushed' if ok else 'NOT pushed'}")
    return 0 if (ok and not blocked) else 1


if __name__ == "__main__":
    sys.exit(main())
