#!/usr/bin/env bash
#
# Point this clone's git at the tracked hooks in .githooks/.
#
#   ./scripts/install_hooks.sh            # says what it did
#   ./scripts/install_hooks.sh --quiet    # silent unless it CHANGED something
#
# Safe to run every time, and it is run a lot: by ./go, by the post-merge hook
# after every pull, by conftest.py on any pytest run, and by Claude Code at the
# start of every session. That fan-out is deliberate.
#
# Hooks live in .githooks/ rather than .git/hooks because .git/ is not tracked —
# a hook in there exists only on the machine that wrote it, which is exactly the
# failure the commit-msg hook is meant to stop. The cost of that choice is that
# `core.hooksPath` is LOCAL config which git clone does not carry, so a fresh
# clone is unprotected and looks identical to a protected one. Nothing can run
# on clone (git will not execute code it just downloaded), so the only honest
# answer is to check at every entry point somebody might use first.

set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

QUIET=0
[ "${1:-}" = "--quiet" ] && QUIET=1

INSTALLED=0   # core.hooksPath was not pointing here — this clone was unprotected
FIXED=""      # hooks that were present but not executable

if [ "$(git config core.hooksPath 2>/dev/null || true)" != ".githooks" ]; then
  git config core.hooksPath .githooks
  INSTALLED=1
fi

# A hook that is not executable is silently skipped by git — the same "looks
# installed, does nothing" failure one level down.
for h in .githooks/*; do
  [ -f "$h" ] || continue
  if [ ! -x "$h" ]; then
    chmod +x "$h"
    FIXED="$FIXED $(basename "$h")"
  fi
done

if [ "$QUIET" = "1" ] && [ "$INSTALLED" = "0" ] && [ -z "$FIXED" ]; then
  exit 0
fi

if [ "$INSTALLED" = "1" ]; then
  echo ""
  echo "  Git hooks were NOT set up in this clone. They are now."
  echo ""
  echo "  From here on a commit is refused when it changes code and leaves the"
  echo "  owning CLAUDE.md untouched. If a change genuinely needs no doc update,"
  echo "  put this line in the commit message:"
  echo ""
  echo "      DOCS: none - <reason>"
  echo ""
  echo "  Full rule: root CLAUDE.md -> ## Committing"
  echo ""
elif [ -n "$FIXED" ]; then
  echo "  git hooks made executable:$FIXED (git silently skips a hook it cannot run)"
else
  echo "  git hooks installed (core.hooksPath = .githooks)"
fi
