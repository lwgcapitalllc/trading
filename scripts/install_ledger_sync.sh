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
# ⚠ WHY THIS RUNS ON THE MAC AND NOT ON THE VPS, which is where the data is. The VPS cannot
# push: its scheduled tasks run as SYSTEM, SYSTEM has its own credential store, and Git
# Credential Manager there has no cached token and no interactive session to ask for one — so
# `git push` BLOCKS rather than failing, forever, until the task's execution limit kills it
# (measured 2026-07-31). Making it work means putting a GitHub write token on a box that already
# holds a live MT5 password, which widens what a compromise costs for no trading benefit. See
# `algos/tools/log_backup.py`.
#
# ⚠ THE HONEST LIMIT: this only runs while this Mac is on. launchd will fire a MISSED calendar
# job when the machine next wakes, so a closed laptop DELAYS the backup rather than skipping it —
# but a Mac off for three days means three days of record living on one VPS disk. The `open:` /
# `closed:` counts printed by `log_backup.py` on the VPS are how you check.
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
