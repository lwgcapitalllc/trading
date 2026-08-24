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
# 🔴 THIS IS NO LONGER THE BACKUP. Since 2026-08-24 the trading box pushes its OWN record hourly
# (SYS_LEDGERSYNC, `algos/scheduler/ledgersync_task.xml`), so this agent runs with `--no-push`
# and is a SECOND LOCAL COPY on the Mac, nothing more. Aaron's call, and the reason is the one
# this file used to state as an unavoidable limit: the record only left the box when a Mac
# happened to be awake, and a laptop shut for a weekend meant a weekend of record on one disk.
#
# ⚠ `--no-push` is not a detail — it is what stops the two machines racing. Both pushing to
# `main` on their own timers means one rebases under the other; the box is the copy that is
# always on, so the box is the one that pushes.
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
esac

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
