#!/usr/bin/env bash
#
# setup_learning_mode.sh — one-time setup so `/learn <video-url>` works on this machine.
#
# `/learn` ships with this repo (.claude/skills/learn/) and works on clone, but it
# needs two things that do NOT ship with it:
#
#   1. ffmpeg + yt-dlp on your PATH  — the tools that fetch a video and cut it into frames
#   2. the `watch` skill             — third-party (MIT), deliberately NOT vendored into
#                                      this repo, so it can be updated on its own
#
# This script installs both. It is idempotent — run it as often as you like. Re-running
# it is also how you UPDATE the watch skill to its latest version.
#
# Usage:
#   bash scripts/setup_learning_mode.sh
#
set -euo pipefail

WATCH_REPO="https://github.com/bradautomates/claude-video.git"
VENDOR_DIR="$HOME/.claude/vendor/claude-video"
SKILLS_DIR="$HOME/.claude/skills"
WATCH_LINK="$SKILLS_DIR/watch"
CONFIG_FILE="$HOME/.config/watch/.env"

ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
info() { printf '  \033[34m→\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
die()  { printf '\n  \033[31m✗ %s\033[0m\n\n' "$1" >&2; exit 1; }

echo
echo "Setting up learning mode (/learn)"
echo

# ---------------------------------------------------------------------------
# 1. Binaries: ffmpeg, ffprobe, yt-dlp
# ---------------------------------------------------------------------------
echo "1. Video tools"

missing=()
for bin in ffmpeg ffprobe yt-dlp; do
  command -v "$bin" >/dev/null 2>&1 || missing+=("$bin")
done

if [ ${#missing[@]} -eq 0 ]; then
  ok "ffmpeg, ffprobe, yt-dlp already installed"
else
  info "missing: ${missing[*]}"
  case "$(uname -s)" in
    Darwin)
      command -v brew >/dev/null 2>&1 \
        || die "Homebrew is not installed. Get it from https://brew.sh, then re-run this script."
      info "installing via Homebrew (this can take a few minutes)…"
      brew install ffmpeg yt-dlp
      ok "installed"
      ;;
    Linux)
      if command -v apt-get >/dev/null 2>&1; then
        die "Run:  sudo apt-get update && sudo apt-get install -y ffmpeg && sudo apt-get install -y yt-dlp
      then re-run this script."
      elif command -v dnf >/dev/null 2>&1; then
        die "Run:  sudo dnf install -y ffmpeg yt-dlp
      then re-run this script."
      else
        die "Install ffmpeg and yt-dlp with your package manager, then re-run this script."
      fi
      ;;
    *)
      die "Unsupported OS. Install ffmpeg and yt-dlp manually, then re-run this script."
      ;;
  esac
fi

# yt-dlp goes stale fast — video sites change and old versions start failing.
if command -v brew >/dev/null 2>&1 && brew list yt-dlp >/dev/null 2>&1; then
  info "checking yt-dlp is current…"
  brew upgrade yt-dlp >/dev/null 2>&1 || true
  ok "yt-dlp $(yt-dlp --version 2>/dev/null || echo '?')"
fi

echo

# ---------------------------------------------------------------------------
# 2. The watch skill
# ---------------------------------------------------------------------------
echo "2. Watch skill"

mkdir -p "$SKILLS_DIR" "$(dirname "$VENDOR_DIR")"

if [ -d "$VENDOR_DIR/.git" ]; then
  info "updating existing copy…"
  git -C "$VENDOR_DIR" pull --quiet --ff-only || warn "could not fast-forward; leaving the current copy in place"
  ok "up to date at $VENDOR_DIR"
else
  rm -rf "$VENDOR_DIR"
  # ⚠ BRACES ARE LOAD-BEARING: `$WATCH_REPO…` fails on macOS's system bash.
  # The ellipsis is UTF-8 `e2 80 a6`, and bash 3.2.57 (what /bin/bash is on macOS)
  # folds that leading 0xe2 into the identifier — so the name becomes `WATCH_REPO\xe2`,
  # which `set -u` then kills as unbound. Reproduce: bash -c 'set -u; V=x; echo "$V…"'.
  # Bash 5 parses it fine, which is why this shipped: it only breaks on the system bash.
  # Every other `…` here is safe because none of them touches a variable expansion.
  info "cloning ${WATCH_REPO}…"
  git clone --quiet --depth 1 "$WATCH_REPO" "$VENDOR_DIR"
  ok "cloned to $VENDOR_DIR"
fi

[ -f "$VENDOR_DIR/skills/watch/scripts/watch.py" ] \
  || die "Clone looks wrong — $VENDOR_DIR/skills/watch/scripts/watch.py is missing."

# Symlinked, not copied, so a re-run of this script updates the installed skill too.
ln -sfn "$VENDOR_DIR/skills/watch" "$WATCH_LINK"
ok "linked into $WATCH_LINK"

echo

# ---------------------------------------------------------------------------
# 3. Config
# ---------------------------------------------------------------------------
echo "3. Config"

# The skill's own installer scaffolds ~/.config/watch/.env at 0600. It only writes
# the file when it is absent, so this never clobbers a key you already added.
python3 "$VENDOR_DIR/skills/watch/scripts/setup.py" >/dev/null 2>&1 || true

if [ -f "$CONFIG_FILE" ]; then
  ok "config at $CONFIG_FILE"
else
  warn "config was not created at $CONFIG_FILE — /learn will still run"
fi

# Mark setup done so the skill stops prompting for a speech-to-text key on every run.
# A key is OPTIONAL: it is only used for videos with no subtitles.
if [ -f "$CONFIG_FILE" ] && ! grep -q '^SETUP_COMPLETE=' "$CONFIG_FILE" 2>/dev/null; then
  printf '\nWATCH_DETAIL=balanced\nSETUP_COMPLETE=true\n' >> "$CONFIG_FILE"
  ok "defaults written"
fi

if [ -f "$CONFIG_FILE" ] && grep -qE '^(GROQ|OPENAI)_API_KEY=.+' "$CONFIG_FILE" 2>/dev/null; then
  ok "speech-to-text key found"
else
  info "no speech-to-text key set — that is fine, and optional"
  info "it is only used for videos with NO subtitles (Loom, TikTok, your own screen recordings)"
  info "to add one later, put a Groq key in $CONFIG_FILE — free tier at console.groq.com/keys"
fi

echo

# ---------------------------------------------------------------------------
# 4. Verify
# ---------------------------------------------------------------------------
echo "4. Check"

python3 "$VENDOR_DIR/skills/watch/scripts/setup.py" --check \
  && ok "watch skill ready" \
  || die "The watch skill's own preflight failed. Run it directly to see why:
      python3 $VENDOR_DIR/skills/watch/scripts/setup.py"

REPO_ROOT="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel 2>/dev/null || true)"
if [ -n "$REPO_ROOT" ] && [ -f "$REPO_ROOT/.claude/skills/learn/SKILL.md" ]; then
  ok "learn skill found in this repo"
else
  warn "could not find .claude/skills/learn/SKILL.md — run this script from inside the trading repo"
fi

cat <<'EOF'

Done. Learning mode is on.

  /learn <video-url>              watch it, and file a note
  /learn <video-url> <what to focus on>

Notes land in education/learned/ and are committed, so both of us read the same ones.

EOF
