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

# ── Parallelism ───────────────────────────────────────────────────────────────
#
# Both python suites are single-core without this, on a box with 12 of them.
# MEASURED 2026-08-15: root 202s -> 119s, backend 150s -> 45s.
#
# ⚠ **`--dist load`, not the default `--dist each`/`loadscope`.** Several test files build an
# expensive artefact once at MODULE scope and share it across their tests — a 31 MB bar cache, a
# two-year strategy replay, a 5-process cache collision. `loadfile` keeps a file on one worker and
# preserves every one of those, which sounds right and MEASURED SLOWER (138s vs 119s): the two
# heaviest files then become the whole critical path with eleven cores idle beside them. `load`
# spreads them and rebuilds a cache per worker, which costs CPU and buys wall clock.
#
# ⚠ **REFUSE rather than fall back to serial.** pytest exits 4 on an unrecognised `-n`, which reads
# as a suite failure and sends the reader at the tests; and a silent fall-back to serial is worse
# still — it turns a missing package into "the tests are slow today" and nobody investigates.
PYTEST_PARALLEL="${PYTEST_PARALLEL:--n auto --dist load}"
if [ -n "$PYTEST_PARALLEL" ] && ! "$PYTHON" -c "import xdist" 2>/dev/null; then
  echo ""
  echo "  pytest-xdist is not installed in $PYTHON"
  echo "  Install it:  $PYTHON -m pip install -r command-center/backend/requirements.txt"
  echo "  Or run serially:  PYTEST_PARALLEL= $0"
  echo ""
  exit 1
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Test suite"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── 1. Engines, backtest, algos, strategies, smart-money ──────────────────────
# ~2:00 across 12 cores, 1,760 tests. `conftest.py` at the root puts `engines/` on sys.path so
# the canonical engines import by bare name.
#
# ⚠ **`backtest/tests/test_reprice.py` is ~68s of that 2:00 on its own** — four full replays of
# `mpc_sos_fade` over two years of M15 bars, which is the thing it exists to check. Everything
# else in this suite finishes in ~44s. If this needs to get faster, that file is the whole
# conversation, and the lever is coverage rather than scheduling.
echo "  [1/5] engines / backtest / algos / strategies / smart-money ..."
if "$PYTHON" -m pytest engines backtest algos strategies smart-money -q $PYTEST_PARALLEL; then
  pass "root suite"
else
  fail "root suite (engines / backtest / algos / strategies / smart-money)"
fi
echo ""

# ── 2. Command-center backend ─────────────────────────────────────────────────
# ~45s across 12 cores, 1,051 tests. MUST be run from its own directory: its pytest.ini carries the
# `-m "not integration"` interlock that keeps the destructive live-VPS suite deselected, and a
# `-m` from anywhere else would replace it.
echo "  [2/5] command-center backend ..."
if (cd command-center/backend && ./.venv/bin/python -m pytest -q $PYTEST_PARALLEL); then
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
echo "  [3/5] frontend typecheck ..."
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

# ── 4. Browser guard ──────────────────────────────────────────────────────────
# Milliseconds. `.claude/mcp/browser_guard.js` is injected into every page the Playwright MCP
# server opens, and it is what stops browser automation stopping the armed bot, promoting code
# under it, deploying a strategy or rewriting a broker account row. It is in the suite because
# a check nobody runs is not a check — and because the guard is a DENY-list, so a new live route
# is allowed until somebody adds it here.
echo "  [4/5] browser guard ..."
if command -v node >/dev/null 2>&1; then
  if node .claude/mcp/check_browser_guard.js; then
    pass "browser guard (34 cases, refusals and allowances)"
  else
    fail "browser guard (34 cases, refusals and allowances)"
  fi
else
  fail "browser guard - node not found on PATH"
fi

echo ""

# ── 5. Trading-box server ─────────────────────────────────────────────────────
# Milliseconds. `.claude/mcp/tradingbox_server.py` is the fixed menu of trading-box operations
# Claude is given instead of an open SSH prompt. This asserts the dangerous forms are still
# absent from that menu, that a guarded operation refuses BEFORE touching the network, and
# that an unreachable Command Center reads as "cannot ask" rather than as "the bot is stopped".
echo "  [5/5] trading-box server ..."
if "$PYTHON" .claude/mcp/check_tradingbox.py; then
  pass "trading-box server (menu, refusals, cannot-ask)"
else
  fail "trading-box server (menu, refusals, cannot-ask)"
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
