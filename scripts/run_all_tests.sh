#!/usr/bin/env bash
#
# Every test in this repo, in one command.
#
#   ./scripts/run_all_tests.sh
#
# Run by `.githooks/pre-push`. Exit 0 only if everything passed.
#
# 🔴 **THIS SCRIPT EXISTS BECAUSE "run all tests" WAS NOT ONE COMMAND.** A bare `pytest` at the
# repo root collects 2,670 tests and then DIES on a collection error: `command-center/backend`
# has its own `pytest.ini` and its own venv, and its tests import `services`/`routers` by bare
# name, which only resolves with that directory as the working directory. So the honest answer
# is two pytest invocations with different roots, plus a typecheck — and until this file existed
# there was no single thing to point a hook at.
#
# ⚠ **The three suites are INDEPENDENT and all of them run.** Stopping at the first failure
# would report the backend as unknown whenever an engine test broke, and "unknown" reads as
# "fine" the moment somebody is in a hurry.

set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# The python that has this repo's dependencies (pandas, numpy, fastapi). It is the backend's venv
# on both Macs today — there is no separate root env, and the root suite has always been run with
# whatever `python3` happened to resolve to, which was this. Named rather than assumed, and
# overridable: `PYTHON=/usr/local/bin/python3.14 ./scripts/run_all_tests.sh`.
PYTHON="${PYTHON:-$ROOT/command-center/backend/.venv/bin/python}"
[ -x "$PYTHON" ] || PYTHON="$(command -v python3)"

FAILED=""
pass() { printf '  \033[32m✓\033[0m %s\n' "$1"; }
fail() { printf '  \033[31m✗\033[0m %s\n' "$1"; FAILED="$FAILED
    $1"; }

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Test suite"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── 1. Engines, backtest, algos, strategies, smart-money ──────────────────────
# ~4:45, 1,698 tests. `conftest.py` at the root puts `engines/` on sys.path so the canonical
# engines import by bare name.
echo "  [1/3] engines / backtest / algos / strategies / smart-money ..."
if "$PYTHON" -m pytest engines backtest algos strategies smart-money -q; then
  pass "root suite"
else
  fail "root suite (engines / backtest / algos / strategies / smart-money)"
fi
echo ""

# ── 2. Command-center backend ─────────────────────────────────────────────────
# ~2:20, 1,001 tests. MUST be run from its own directory: its pytest.ini carries the
# `-m "not integration"` interlock that keeps the destructive live-VPS suite deselected, and a
# `-m` from anywhere else would replace it.
echo "  [2/3] command-center backend ..."
if (cd command-center/backend && ./.venv/bin/python -m pytest -q); then
  pass "backend suite"
else
  fail "backend suite (command-center/backend)"
fi
echo ""

# ── 3. Frontend typecheck ─────────────────────────────────────────────────────
# ⚠ **NOT the Playwright suite, and that is a safety decision rather than a speed one.**
# `playwright.config.ts` deliberately has no `webServer` block: this backend talks to a live VPS
# and a live MT5 terminal, so a runner that boots it on demand is a runner that can start things
# on the trading box. Its own comment says starting it is a person's decision. So the automated
# gate takes the half that needs nothing running — `tsc`, which is the check that would actually
# have caught a broken build — and the browser tests stay a deliberate `./start.sh` then
# `npm test` in `command-center/frontend`.
echo "  [3/3] frontend typecheck ..."
if [ -d "command-center/frontend/node_modules" ]; then
  if (cd command-center/frontend && npx --no-install tsc --noEmit); then
    pass "frontend typecheck (tsc --noEmit)"
  else
    fail "frontend typecheck (tsc --noEmit)"
  fi
else
  # Refuse rather than skip quietly: a check that silently did not run is the failure mode this
  # whole repo keeps meeting.
  fail "frontend typecheck - command-center/frontend/node_modules missing (run: cd command-center/frontend && npm install)"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ -n "$FAILED" ]; then
  printf '  \033[31mFAILED:\033[0m%s\n' "$FAILED"
  echo ""
  echo "  ⚠ Playwright browser tests are NOT in this run - they need the app up."
  echo "    ./start.sh, then: cd command-center/frontend && npm test"
  echo ""
  exit 1
fi

echo "  All green."
echo ""
echo "  ⚠ Playwright browser tests are NOT in this run - they need the app up."
echo "    ./start.sh, then: cd command-center/frontend && npm test"
echo ""
