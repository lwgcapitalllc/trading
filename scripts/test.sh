#!/usr/bin/env bash
#
# The EVERYDAY test command. Runs only what your change since the last green run can reach.
#
#   scripts/test.sh              the default - use this after every piece of work
#   scripts/test.sh --explain    what would run and why; runs nothing
#   scripts/test.sh --since origin/main
#
# The FULL run is scripts/run_all_tests.sh, and it is a deliberate act - root CLAUDE.md ->
# *Formatting, linting and the test gate* says exactly when it is required.
#
# ⚠ Output is one line per piece plus the failures. Tracebacks are in .test-logs/fast.log:
#   read that file - never re-run an unchanged tree to see output again.

set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# The same interpreter the full run uses (the backend venv carries pytest, xdist and pandas).
PYTHON="${PYTHON:-$ROOT/command-center/backend/.venv/bin/python}"
[ -x "$PYTHON" ] || PYTHON="$(command -v python3)"

exec "$PYTHON" -m scripts.testing.fast "$@"
