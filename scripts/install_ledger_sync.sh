#!/usr/bin/env bash
#
# install_ledger_sync.sh — put the bot's record on a 12-hourly backup, on this Mac.
#
# Aaron's requirement, 2026-08-05: *"those are the logs that I expect to be at the end of the
# day copied into the branch and push to GitHub … I think it should be at least twice a day."*
#
# Installs a launchd agent that runs `algos/tools/ledger_sync.py` at 00:05 and 12:05 local. That
# script ssh's to the VPS, fetches every per-day record file (decisions, health, and the text
# log), and commits them to `algos/ledger_archive/`.
#
# 🔴 IT NO LONGER INSTALLS ANYTHING, AND THE ONLY THING LEFT HERE IS `--uninstall`. Since
# 2026-08-24 the trading box pushes its OWN record hourly (SYS_LEDGERSYNC,
# `algos/scheduler/ledgersync_task.xml`), which made this agent a second copy of something the
# Mac already had by `git pull`. On 2026-08-28 that copy cost a day.
#
# 🔴 WHAT IT COST, because "it only commits locally" reads harmless and is not. The agent ran
# `--no-push`, so it committed to `main` and never pushed — and the commit then reached origin
# on the next human `git push` of unrelated code, which from the box's side is exactly a push.
# The box's hourly job had to merge two APPENDS to the end of one file. Git cannot do that at
# any content: the 3-way merge sees one changed region and conflicts. It aborted (correctly),
# re-failed identically every hour for EIGHT hours, stacked another commit each time, and the
# record sat on one disk the whole while.
#
# 🔴 THE RULE WAS WRITTEN AT THE WRONG LAYER, and that is the transferable part. `--no-push`
# governs PUSHING; the hazard is COMMITTING. On a shared branch a local commit is a push with a
# delay. The fix is in `algos/tools/ledger_sync.py::main`, which now refuses to commit records
# this machine did not write — so a stale agent left installed on another Mac is inert rather
# than dangerous, without anybody having to go and remove it.
#
# ⚠ A second READER is free and always was. It is a second WRITER that breaks, and this repo
# only ever needed one: the box is always on, and GitHub is the off-box copy.
#
# WHY THE BOX COULD NOT PUSH BEFORE, and what changed: its scheduled tasks run as SYSTEM, whose
# credential store has no cached token and no interactive session to ask for one — so `git push`
# BLOCKED rather than failing (measured 2026-07-31). It now uses a repo-scoped fine-grained token
# from the git-ignored `algos/credentials.json`, spliced into the push URL in memory, with Git
# Credential Manager disabled outright so it cannot run and cannot hang. The cost is stated where
# the key is documented: that box already holds a live broker password, and a token beside it
# means a break-in costs the repository too.
#
# ⚠ THE LIMIT THAT REMAINS: this agent still only runs while the Mac is on, and it now only makes
# a local copy. If you want to know whether the RECORD is safe, look at the box — the `open:` /
# `closed:` counts from `log_backup.py`, or that SYS_LEDGERSYNC last ran with result 0.
#
# Usage:
#   scripts/install_ledger_sync.sh            # install (or reinstall) and load
#   scripts/install_ledger_sync.sh --uninstall
#   scripts/install_ledger_sync.sh --status
#
set -euo pipefail

LABEL="com.lwg.ledger-sync"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$HOME/Library/Logs"

case "${1:-install}" in
  --status)
    launchctl list | grep -F "$LABEL" || echo "not loaded"
    echo "plist: $PLIST"
    tail -n 20 "$LOG_DIR/$LABEL.log" 2>/dev/null || echo "(no log yet)"
    exit 0
    ;;
  --uninstall)
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"
    echo "removed $LABEL"
    exit 0
    ;;
  install|"")
    echo "REFUSED: this agent is not installed any more, on purpose."
    echo
    echo "  The trading box commits and pushes the record itself, hourly (SYS_LEDGERSYNC)."
    echo "  A Mac agent beside it is a SECOND WRITER of an append-only file, and two appends"
    echo "  to one file end cannot be merged — that cost a day of backup on 2026-08-28."
    echo
    echo "  This Mac already gets every record with 'git pull'."
    echo "  If an old agent is still loaded here, remove it:"
    echo "      scripts/install_ledger_sync.sh --uninstall"
    exit 1
    ;;
esac

# Unreachable: the case above exits on every path. Kept so the shape of what used to be
# installed stays readable next to the reason it no longer is.
# ABSOLUTE paths throughout. launchd starts a job with a minimal environment and a PATH that has
# neither Homebrew nor a virtualenv on it, so a bare `python3` or `git` is the classic way one of
# these agents "installs fine" and then fails silently every night.
PYTHON="/usr/bin/python3"
[ -x "$PYTHON" ] || { echo "no python3 at $PYTHON"; exit 1; }

mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"

cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>$REPO/algos/tools/ledger_sync.py</string>
    <string>--no-push</string>
  </array>
  <key>WorkingDirectory</key><string>$REPO</string>
  <!-- Every 12 hours. :05 rather than :00 so a UTC-midnight roll on the VPS has finished
       writing the new day's first records before the fetch runs. -->
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Hour</key><integer>0</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>12</integer><key>Minute</key><integer>5</integer></dict>
  </array>
  <key>StandardOutPath</key><string>$LOG_DIR/$LABEL.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/$LABEL.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin</string>
    <key>HOME</key><string>$HOME</string>
  </dict>
</dict>
</plist>
PLIST_EOF

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"

echo "installed $LABEL — runs at 00:05 and 12:05 local"
echo "  plist: $PLIST"
echo "  log:   $LOG_DIR/$LABEL.log"
echo
echo "Run it once now to prove it works end to end:"
echo "  launchctl kickstart -p gui/$(id -u)/$LABEL"
