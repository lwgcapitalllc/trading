#!/usr/bin/env bash
#
# Point this clone's git at the tracked hooks in .githooks/.
#
#   ./scripts/install_hooks.sh
#
# Safe to run every time. ./go runs it for you; this exists for a clone that
# never runs ./go (a checkout on the VPS, a second worktree, a CI box).
#
# Hooks live in .githooks/ rather than .git/hooks because .git/ is not tracked —
# a hook in there exists only on the machine that wrote it, which is exactly the
# failure the commit-msg hook is meant to stop.

set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

git config core.hooksPath .githooks
chmod +x .githooks/* 2>/dev/null || true

echo "  git hooks installed (core.hooksPath = .githooks)"
echo ""
echo "  Active:"
echo "    commit-msg   refuses a commit whose changed code has an untouched CLAUDE.md"
echo ""
echo "  Escape valve, when a change genuinely needs no doc update — put this"
echo "  line in the commit message so the skip is recorded:"
echo ""
echo "      DOCS: none - <reason>"
echo ""
