#!/usr/bin/env bash
#
# setup.sh — one-command install for skool-transcript.
#
# Run once, from anywhere in the repo:
#     bash tools/skool-transcript/setup.sh
#
# Installs the dependencies (via Homebrew) and links the `skool-transcript`
# command onto your PATH. Re-run any time to repair things.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$HERE/skool-transcript"

echo "== skool-transcript setup =="

# 1. Homebrew must exist (we don't auto-install it — it needs your password).
if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew isn't installed. Install it first (one line, from https://brew.sh):"
  echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
  echo "Then re-run this script."
  exit 1
fi

# 2. Install missing dependencies.
need_install=()
command -v yt-dlp  >/dev/null 2>&1 || need_install+=("yt-dlp")
command -v ffmpeg  >/dev/null 2>&1 || need_install+=("ffmpeg")
command -v python3 >/dev/null 2>&1 || need_install+=("python")
if [[ ${#need_install[@]} -gt 0 ]]; then
  echo "Installing: ${need_install[*]}"
  brew install "${need_install[@]}"
else
  echo "Dependencies already present (yt-dlp, ffmpeg, python3)."
fi

# 3. Link the command into Homebrew's bin (always on PATH after brew).
chmod +x "$SRC"
BINDIR="$(brew --prefix)/bin"
ln -sf "$SRC" "$BINDIR/skool-transcript"
echo "Linked $BINDIR/skool-transcript -> $SRC"

echo
echo "Done. To rip a video:"
echo "  1. On the Skool video, open DevTools (Cmd+Opt+I) -> Network tab -> filter 'm3u8' -> press play."
echo "  2. Right-click the stream.video.skool.com row -> Copy -> Copy link address."
echo "  3. Run:  skool-transcript"
echo "It asks for the title, then saves into smc-course/ automatically."
