"""log_backup.py — the VPS half of preserving the decision record.

Runs daily on the VPS as `SYS_LOGBACKUP`:

    python C:/trading/algos/tools/log_backup.py               # zip + prune
    python C:/trading/algos/tools/log_backup.py --dry-run     # say what it would do
    python C:/trading/algos/tools/log_backup.py --list-closed # paths, for the Mac to fetch

**The problem.** `algos/live/ledger.py` writes one JSONL line per bar, per blocked setup, per
trade — the only record of WHY the bot did what it did, and the input to the shadow-diff that
has to pass before real money moves. It lives on one VPS disk, and there is no historical
trade data anywhere else in this repo (the old suite was deleted, deliberately, with nothing
carried forward). Lose that disk and the dry run did not happen; it gets run again from zero.

**Why this script does NOT push to git, though an earlier version did.** The obvious design is
for the VPS to commit the ledger itself. It cannot, and the way it fails is the interesting
part: the task runs as SYSTEM, SYSTEM has its own credential store, and Git Credential Manager
there has no cached token and no interactive session to ask for one. `git push` does not
fail — it BLOCKS, forever, until the task's execution limit kills it. Measured on 2026-07-31:
the test task sat in `Running` with no output and no error.

Fixing that means putting a GitHub write token on the VPS. That is the wrong trade. This box
already holds a live MT5 password and a Telegram token; adding a credential that can rewrite
the source repo widens what a compromise costs, and buys nothing the pull direction does not
already give. So the split is:

  * **here (VPS):** zip the raw `.log` files, prune past 90 days, and report which ledger days
    are closed. Local housekeeping. Nothing leaves the box and nothing here pretends it does.
  * **`ledger_sync.py` (Mac):** fetch those closed days and commit them, from the machine that
    already has working git credentials.

The cost of that split is honest and worth stating: the record leaves the VPS when the Mac
runs the sync, not on a VPS timer. `--list-closed` exists so the Mac side can ask rather than
re-derive, and so "closed" has exactly one definition.

**Two rules that outlive any of the above.**

*Only days STRICTLY BEFORE today count as closed.* Today's file is still being appended to by
a running bot, so a copy of it can end in a torn line. ⚠ **Since 2026-08-05 that no longer
means today is unbackupable** — the sync runs every 12 hours at Aaron's request, which
necessarily commits an open day. `--list-open` reports today separately from `--list-closed`,
and the Mac side truncates a torn final line rather than committing half a record. The
distinction is kept because the two are different promises: a closed day is final, an open one
is the best copy so far and will be committed again.

*Logs are COPIED, never rotated.* The bot holds its log open, and renaming a file Windows has
open fails with a sharing violation — a rotation scheme would pass on the Mac, break on the
VPS, and take the day's logs with it. ⚠ The bot now writes one text log PER DAY
(`<bot>-YYYY-MM-DD.log`, `algos/live/runner.DailyFileHandler`), which rolls by choosing a
filename rather than by renaming, so that rule is intact and a day's text log has become a
final artefact that can be committed like the JSONL streams.
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# DERIVED, never hardcoded — the same rule as algos/shared/bot_state.py. A literal
# C:/trading path is right on the VPS and quietly wrong everywhere else.
ALGOS_ROOT = Path(__file__).resolve().parent.parent
INSTANCES = ALGOS_ROOT / "markets" / "fx" / "instances"
ARCHIVE = ALGOS_ROOT / "log_archive"

if str(ALGOS_ROOT / "live") not in sys.path:
    sys.path.insert(0, str(ALGOS_ROOT / "live"))

# IMPORTED, not restated. The writer owns the filename shape; a copy of the pattern here would
# drift the day somebody adds a third stream, and the drift's symptom is a whole stream that is
# silently never committed — which looks exactly like a stream that was never written.
from ledger import STREAM_RE  # noqa: E402

KEEP_DAYS = 90

# Kept as its own name because `tools/ledger_sync.py` imports it. It matches the DECISION
# stream only, which is what the pre-2026-08-05 pipeline knew about.
LEDGER_RE = re.compile(r"^decisions-(\d{4})-(\d{2})-(\d{2})\.jsonl$")
ZIP_RE = re.compile(r"^logs-(\d{4})-(\d{2})-(\d{2})\.zip$")
# One text log per day, written by `algos/live/runner.DailyFileHandler`. It sits in the
# INSTANCE dir rather than in `ledger/`, because it is prose about the process and the ledger
# dir holds the structured record.
TEXTLOG_RE = re.compile(r"^(.+)-(\d{4})-(\d{2})-(\d{2})\.log$")


def _dated(path: Path) -> tuple[date, bool] | None:
    """(date, is_ledger_stream) for a file this pipeline backs up, else None."""
    m = STREAM_RE.match(path.name)
    if m:
        return date(int(m[2]), int(m[3]), int(m[4])), True
    m = TEXTLOG_RE.match(path.name)
    if m:
        return date(int(m[2]), int(m[3]), int(m[4])), False
    return None


def _record_files(instances: Path) -> tuple[list[Path], list[Path]]:
    """Every dated record file this pipeline owns, and everything it did not recognise.

    Two locations, on purpose: `<bot>/ledger/*.jsonl` is the structured record and
    `<bot>/*.log` is the prose. Both are per-day and both are committed.
    """
    found, skipped = [], []
    for inst in sorted(p for p in instances.glob("*") if p.is_dir()):
        for path in sorted(list(inst.glob("*.log")) + list((inst / "ledger").glob("*"))):
            if not path.is_file():
                continue
            (found if _dated(path) else skipped).append(path)
    return found, skipped


def ledger_files(instances: Path, today: date) -> tuple[list[Path], list[Path]]:
    """Return (closed record files, files skipped for not matching a known shape).

    "Closed" means dated strictly before `today`: no bot can append to it again, so copying
    it can never race a write. This is the single definition of closed — the Mac side asks
    for it over `--list-closed` rather than reimplementing the date comparison.
    """
    found, skipped = _record_files(instances)
    return [p for p in found if _dated(p)[0] < today], skipped


def open_files(instances: Path, today: date) -> list[Path]:
    """Today's files — still being appended to, and committed anyway.

    ⚠ **These are a BEST COPY, not a final one**, and the difference is why they are reported
    apart from the closed days rather than merged into one list. A copy taken mid-append can end
    in a half-written line, and the same day will be fetched again on the next run with more in
    it. Calling both "closed" would let a torn half-day later read exactly like a whole one,
    which is the failure the closed/open split has always existed to prevent.
    """
    found, _ = _record_files(instances)
    return [p for p in found if _dated(p)[0] == today]


def archive_logs(instances: Path, archive: Path, today: date, dry_run: bool = False) -> Path | None:
    """Snapshot every instance `.log` into one dated zip. Copies, never rotates.

    This stays even though the text logs are now committed by `ledger_sync.py`: the zip is the
    VPS's own local safety net for the window between syncs, and it costs nothing.
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


def prune(
    archive: Path, today: date, keep_days: int = KEEP_DAYS, dry_run: bool = False
) -> list[Path]:
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Zip and prune VPS bot logs.")
    ap.add_argument("--dry-run", action="store_true", help="report, change nothing")
    ap.add_argument(
        "--list-closed",
        action="store_true",
        help="print closed record paths (relative to the instances dir) and exit",
    )
    ap.add_argument(
        "--list-open",
        action="store_true",
        help="print TODAY's record paths — still being written — and exit",
    )
    ap.add_argument("--keep-days", type=int, default=KEEP_DAYS)
    args = ap.parse_args(argv)

    today = datetime.now(timezone.utc).date()
    closed, skipped = ledger_files(INSTANCES, today)

    if args.list_closed or args.list_open:
        # Machine-readable and nothing else: ledger_sync.py parses this over ssh.
        for path in closed if args.list_closed else open_files(INSTANCES, today):
            print(str(path.relative_to(INSTANCES)).replace("\\", "/"))
        return 0

    print(f"log_backup {today} {'(dry run)' if args.dry_run else ''}".rstrip())
    for path in skipped:
        print(f"  ! skipped, unrecognised name: {path}")

    zipped = archive_logs(INSTANCES, ARCHIVE, today, args.dry_run)
    print(f"  logs:   {zipped.name if zipped else 'none found'}")

    dropped = prune(ARCHIVE, today, args.keep_days, args.dry_run)
    print(f"  pruned: {len(dropped)} archive(s) older than {args.keep_days} days")
    print(f"  closed: {len(closed)} file(s) on disk, awaiting `ledger_sync.py` on the Mac")
    print(f"  open:   {len(open_files(INSTANCES, today))} file(s) for today, synced as-is")
    return 0


if __name__ == "__main__":
    sys.exit(main())
