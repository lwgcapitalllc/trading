"""ledger_sync.py — commit the bots' record to git. Runs ON THE BOX hourly; also runs on a Mac.

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

🔴 **`--local` IS THE BACKUP NOW, AND IT INVERTS WHAT THIS FILE USED TO SAY.** Until 2026-08-24
the header here stated flatly that the VPS *cannot* push, and built the whole design around it:
its task runs as SYSTEM, whose credential store has no cached token and no interactive session
to ask for one, so `git push` **BLOCKED** rather than failing (measured 2026-07-31). That was
true and it is now fixed rather than worked around. Two things had to change:

  * **A repo-scoped fine-grained token** (`github_token` in the git-ignored
    `algos/credentials.json`), spliced into the push URL **in memory** by `_authenticated_remote`
    so it never reaches `.git/config` where `git remote -v` would print it.
  * **Git Credential Manager disabled outright** on every call (`_GIT_NO_PROMPT` +
    `GIT_TERMINAL_PROMPT=0`). ⚠ **This is the half that fixes the HANG, and the token alone
    would not have.** MEASURED 2026-08-24: with the helper live even a successful `ls-remote`
    printed *"Unable to persist credentials with the 'wincredman' credential store"* — it is
    reaching for a store it cannot write, and under a task with no session that is what waits
    forever. With it disabled the same call is silent.

**So the box now backs itself up hourly** (`SYS_LEDGERSYNC`) and the Mac agent runs `--no-push`
as a second local copy. ⚠ **Exactly one machine may push**, or two timers rebase under each
other on one branch; the box is the one that is always on, so the box is the one that pushes.

⚠ **What this COSTS, stated plainly because it was a deliberate trade:** that box already holds
a live broker password, and a repo write token beside it means a break-in costs the repository
too. Scoping the token to this one repository, with Contents write and nothing else, is the
whole of the limit on that.

⚠ **A machine with NO token still works** — `_authenticated_remote` returns `None`, git uses the
ordinary `origin`, and a developer Mac pushes with its own credentials exactly as before. That
is a supported state, not a failure, which is why nothing here refuses to run without one.

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
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

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
    r"|[A-Za-z0-9._-]+-\d{4}-\d{2}-\d{2}\.log)$"
)

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

# The same two facts as seen from the BOX itself, for `--local`.
LOCAL_INSTANCES = REPO_ROOT / "algos" / "markets" / "fx" / "instances"
LOCAL_SCRIPT = _HERE / "log_backup.py"

# Git invoked for a push must never be able to BLOCK, and on this box it could.
# `GIT_TERMINAL_PROMPT=0` turns a credential prompt into an error, and an empty
# `credential.helper` stops Git Credential Manager running at all — under the scheduled task's
# SYSTEM account it has no cached token, no interactive session, and its own store is
# unwritable, so it hangs instead of failing. MEASURED 2026-08-24: with the helper live a
# plain `ls-remote` still succeeded but printed *"Unable to persist credentials with the
# 'wincredman' credential store"*; with these two settings the same call is silent.
_GIT_NO_PROMPT = ("-c", "credential.helper=", "-c", "credential.interactive=false")


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True)


def remote_files(host: str, which: str) -> list[str]:
    """Ask the VPS which record files exist. `which` is "closed" or "open".

    Asking rather than re-deriving keeps "closed" defined in exactly one place. If the two
    sides ever disagreed, the way it would show up is a half-written day committed as a whole
    one — which is unreadable later and looks fine at the time.
    """
    if host is None:
        out = _run(sys.executable, str(LOCAL_SCRIPT), f"--list-{which}")
        where = "this box"
    else:
        out = _run("ssh", host, f"{REMOTE_PYTHON} {REMOTE_SCRIPT} --list-{which}")
        where = host
    if out.returncode != 0:
        raise RuntimeError(f"could not list {which} files on {where}: {out.stderr.strip()}")
    return [line.strip() for line in out.stdout.splitlines() if REMOTE_PATH_RE.match(line.strip())]


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
        if host is None:
            # ⚠ Still a COPY into the archive, never a move or a symlink. The bot holds the
            # live file open and appends to it; the archive is the tracked snapshot, and the
            # two differing only by their root is what keeps `git pull` on this box working
            # (committing into the live path made pull abort outright — 2026-08-05).
            try:
                shutil.copyfile(LOCAL_INSTANCES / rel, local)
            except OSError as e:
                print(f"  ! copy failed for {rel}: {e}")
                continue
        else:
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
    msg = (
        f"chore(ledger): bot record {span}\n\n"
        f"Fetched from the VPS by algos/tools/ledger_sync.py. {len(rel)} file(s)."
    )
    c = _run("git", "-C", str(REPO_ROOT), "commit", "-m", msg, "--", *rel)
    if c.returncode != 0 and "nothing to commit" not in c.stdout:
        print(f"  git commit failed: {c.stderr.strip() or c.stdout.strip()}")
        return False

    if not push:
        print("  committed locally (--no-push)")
        return False
    return _push()


def _foreign_changes() -> list[str]:
    """Modified tracked files OUTSIDE the ledger archive. Empty is the healthy state here.

    🔴 **This is the guard that keeps a backup job away from a deployment.** `algos/tools/promote.py`
    builds a bot's frozen snapshot out of THIS working tree and refuses on a dirty one, so a rebase
    that checked out different content underneath it would change what a promote is about to freeze.
    Nothing about backing up yesterday's record is worth that risk, so the push stands down and says
    so rather than tidying up after somebody.
    """
    out = _run("git", "-C", str(REPO_ROOT), "status", "--porcelain")
    if out.returncode != 0:
        # Cannot ask is not the same as nothing there, and of the two wrong answers "refuse to
        # push tonight" is recoverable while "rebase under a promote" is not.
        return ["<could not read the working tree>"]
    keep = []
    for line in out.stdout.splitlines():
        path = line[3:].strip().strip('"')
        if not path or path.startswith("algos/ledger_archive/"):
            continue
        if line.startswith("??"):
            continue  # untracked files are not moved by a rebase
        keep.append(path)
    return keep


def _authenticated_remote() -> Optional[str]:
    """`origin`'s URL with a token spliced in, or None when this machine has no token.

    ⚠ **Built in memory on every run and never written anywhere.** Putting it in `.git/config`
    (or in the `origin` remote) would leak it into every `git remote -v`, every config dump and
    every screenshot of this box — for no gain, since it is one string built from a file that is
    already sitting there.

    ⚠ **`None` means this machine does not push, which is a supported state, not a failure.** A
    Mac running this has git credentials of its own and never needs the token; only the VPS's
    SYSTEM-account task does.
    """
    sys.path.insert(0, str(REPO_ROOT / "algos" / "shared"))
    try:
        import credentials as _c

        token = _c.get("github_token")
    except Exception:
        return None
    if not token:
        return None
    out = _run("git", "-C", str(REPO_ROOT), "remote", "get-url", "origin")
    url = out.stdout.strip()
    if out.returncode != 0 or not url.startswith("https://"):
        # An ssh remote already carries its own auth and must not be rewritten.
        return None
    return "https://x-access-token:" + token + "@" + url[len("https://") :]


def _redact(text: str, secret: Optional[str]) -> str:
    """Never let a token reach a log, a console or a Telegram message."""
    if not secret:
        return text
    return text.replace(secret, "REDACTED")


def _push() -> bool:
    """Rebase onto origin, then push. True only when the record is actually AT origin.

    The rebase is what lets two machines commit to one branch. It is scoped by `_foreign_changes`
    rather than trusted: this same checkout is what a promote freezes.
    """
    remote = _authenticated_remote()
    target = remote or "origin"
    secret = None
    if remote:
        secret = remote.split("x-access-token:", 1)[1].split("@", 1)[0]

    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    git = ("git", "-C", str(REPO_ROOT)) + _GIT_NO_PROMPT

    foreign = _foreign_changes()
    if foreign:
        print("  NOT pushing — this working tree has changes outside the ledger archive:")
        for f in foreign[:5]:
            print(f"      {f}")
        print("  The commit is safe locally. A rebase here could move what a promote freezes.")
        return False

    r = subprocess.run(
        [*git, "pull", "--rebase", target, "main"], capture_output=True, text=True, env=env
    )
    if r.returncode != 0:
        detail = _redact((r.stderr or r.stdout).strip(), secret)
        print(f"  rebase failed — the commit is safe locally: {detail[:300]}")
        subprocess.run([*git, "rebase", "--abort"], capture_output=True, text=True, env=env)
        return False

    r = subprocess.run([*git, "push", target, "HEAD:main"], capture_output=True, text=True, env=env)
    if r.returncode == 0:
        return True
    print(f"  push failed: {_redact((r.stderr or r.stdout).strip(), secret)[:300]}")
    return False


def _alert(message: str) -> None:
    """Tell the health channel this job failed. Never raises, whatever happens.

    🔴 **The whole point of moving this onto the box is that it runs while nobody is watching,
    and an unattended job that fails in silence is worse than no job — its silence reads exactly
    like success.** This has already bitten twice: the commit hook refused this very script's
    commits for a day in 2026-08-05 and again on the first run after the first fix, and both
    times the only symptom was a day quietly not arriving.

    ⚠ A notifier may never take down the thing it reports on, so every failure here is swallowed.
    The worst case is the old behaviour: a failure nobody was told about.
    """
    try:
        sys.path.insert(0, str(REPO_ROOT / "algos" / "shared"))
        from notify import HEALTH, send_telegram  # type: ignore

        # HEALTH, never TRADE. This is machinery reporting on itself, and the room carrying
        # fills is the one room that must stay worth looking at.
        send_telegram(message, kind=HEALTH)
    except Exception as e:  # noqa: BLE001 - reported, never raised
        print(f"  (could not send the failure alert: {e})")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fetch bot records from the VPS and commit them.")
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument(
        "--local",
        action="store_true",
        help="run ON the trading box: read the records off this disk instead of over SSH",
    )
    ap.add_argument(
        "--alert-on-failure",
        action="store_true",
        help="send a Telegram HEALTH message if the record does not reach origin",
    )
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument(
        "--closed-only",
        action="store_true",
        help="skip today's still-open files (the pre-2026-08-05 behaviour)",
    )
    args = ap.parse_args(argv)

    host = None if args.local else args.host
    today = datetime.now(timezone.utc).date()
    where = "this box" if args.local else args.host
    print(f"ledger_sync {today} from {where} {'(dry run)' if args.dry_run else ''}".rstrip())

    try:
        rel = remote_files(host, "closed")
        # Today's files are the whole point of running this twice a day: without them the
        # record still leaves the VPS exactly once, just at a different hour.
        if not args.closed_only:
            rel += remote_files(host, "open")
    except RuntimeError as e:
        print(f"  ! {e}")
        return 1

    if not rel:
        print(f"  nothing on {where} to fetch")
        return 0

    local = fetch(host, rel, args.dry_run)
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
        print(
            f"  ! IGNORED by .gitignore, so it can never be backed up: {p.relative_to(REPO_ROOT)}"
        )

    todo = pending(local)
    if not todo:
        if blocked:
            print(f"  {len(blocked)} file(s) fetched but unbackupable — fix .gitignore")
            return 1
        print(f"  up to date ({len(rel)} file(s) on the VPS, all already committed)")
        return 0

    ok = commit(todo, push=not args.no_push, dry_run=args.dry_run)
    print(f"  {len(todo)} file(s) {'pushed' if ok else 'NOT pushed'}")

    # ⚠ Only a genuine failure alerts. `--no-push` returns False on purpose (the operator asked
    # for a local commit), and alerting there would train the reader to ignore this message —
    # which is the one thing an unattended job's alarm cannot afford.
    if args.alert_on_failure and not args.no_push and not args.dry_run and not (ok and not blocked):
        _alert(
            f"Ledger backup did NOT reach origin ({where}).\n"
            f"{len(todo)} file(s) committed locally; the record is on one disk until this clears."
        )
    return 0 if (ok and not blocked) else 1


if __name__ == "__main__":
    sys.exit(main())
