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
# `sos_fade` over two years of M15 bars, which is the thing it exists to check. Everything
# else in this suite finishes in ~44s. If this needs to get faster, that file is the whole
# conversation, and the lever is coverage rather than scheduling.
echo "  [1/16] engines / backtest / algos / strategies / smart-money ..."
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
echo "  [2/16] command-center backend ..."
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
echo "  [3/16] frontend typecheck ..."
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
echo "  [4/16] browser guard ..."
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
echo "  [5/16] trading-box server ..."
if "$PYTHON" .claude/mcp/check_tradingbox.py; then
  pass "trading-box server (menu, refusals, cannot-ask)"
else
  fail "trading-box server (menu, refusals, cannot-ask)"
fi

echo ""

# ── 6. Documentation-size guard ───────────────────────────────────────────────
# Milliseconds. `.claude/hooks/guard_sensitive_paths.py` is what keeps a CLAUDE.md from
# quietly growing into a file nobody reads — every byte of it loads into context on every
# session in that subsystem. It is in the suite because its whole failure mode is SILENCE,
# and silence is indistinguishable from "checked". Both halves are asserted here: the
# reminder before an Edit/Write, and the after-the-fact size check that catches a file
# rewritten by any other means.
echo "  [6/16] documentation-size guard ..."
if "$PYTHON" .claude/hooks/check_guard.py; then
  pass "documentation-size guard (21 cases, warnings and silences)"
else
  fail "documentation-size guard (21 cases, warnings and silences)"
fi

echo ""

# ── 7. Lab server ─────────────────────────────────────────────────────────────
# Milliseconds. The comparison in `.claude/mcp/lab_server.py` refuses when two runs were not
# measured the same way — rule 11, broken four times in this app. The check that matters most
# is the FIRST one: it parses `BacktestRunRequest` out of models.py, so adding an input to a
# backtest goes red here until somebody decides whether it belongs to the measurement basis.
echo "  [7/16] lab server ..."
if "$PYTHON" .claude/mcp/check_lab.py; then
  pass "lab server (basis contract, per-field refusals)"
else
  fail "lab server (basis contract, per-field refusals)"
fi

echo ""

# ── 8. Trade-overlay geometry ─────────────────────────────────────────────────
# Milliseconds. The backtest price chart's trade box decides two things from PRICES: how far the
# adverse (red) band reaches, and whether the exit gets a marker at all. Both were wrong on real
# trades for as long as they existed — the band ran to a stop price never traded, and a trade that
# came off at its staged breakeven stop had no exit drawn anywhere on it.
#
# ⚠ It is here and not in Playwright because a trade annotation is painted into a canvas and has
# no element to assert on: the browser suite can only measure pixels, and it needs the app up.
# These rules are arithmetic, so they run with nothing running.
echo "  [8/16] trade-overlay geometry ..."
if [ -d "command-center/frontend/node_modules" ]; then
  if (cd command-center/frontend && node scripts/check_trade_geometry.mjs); then
    pass "trade geometry (26 cases, adverse band + exit marker)"
  else
    fail "trade geometry (26 cases, adverse band + exit marker)"
  fi
else
  fail "trade geometry - command-center/frontend/node_modules missing (run: cd command-center/frontend && npm install)"
fi

echo ""

# ── 9. Parameter-condition evaluator ──────────────────────────────────────────
# Milliseconds. `show_if` / `disable_if` decide which settings a run form draws, and the SAME rule
# is written twice — once in the editor and once in the lab's sensitivity gate. They have already
# disagreed in silence: a fib level that is "1.0" in a dropdown and 1.0 in a Custom box compared
# equal in Python and unequal in JS, and a toggle stayed live in the one configuration it exists
# to be dead in. Neither side looked wrong alone.
#
# ⚠ The cases are the shared artifact, not the code. This step drives the JS evaluator over
# `frontend/tests/fixtures/param-conditions.json`; `backend/tests/test_param_gates.py` drives the
# python one over the same file, in step 2. A shape one side learns and the other does not fails
# on the side that did not learn it — which is how the empty-condition disagreement was found.
echo "  [9/16] parameter-condition evaluator ..."
if [ -d "command-center/frontend/node_modules" ]; then
  if (cd command-center/frontend && node scripts/check_param_conditions.mjs); then
    pass "param conditions (28 cases, shared with the python evaluator)"
  else
    fail "param conditions (28 cases, shared with the python evaluator)"
  fi
else
  fail "param conditions - command-center/frontend/node_modules missing (run: cd command-center/frontend && npm install)"
fi

# Milliseconds. The PERIOD window's arithmetic, which returns the constant that every dollar on the
# single-backtest page AND the stack page is multiplied by. It lived inside a hook until 2026-09-03,
# reachable only from a browser — the same shape that let the trade box draw a wrong adverse band on
# real trades for as long as it sat inside a chart callback.
#
# ⚠ A wrong scale here is not a broken chart. It is a plausible dollar figure with nothing on screen
# to say it is wrong, on two pages at once.
echo "  [10/16] period-window rebase ..."
if [ -d "command-center/frontend/node_modules" ]; then
  if (cd command-center/frontend && node scripts/check_period_window.mjs); then
    pass "period window (25 cases, filter bounds + the rebase constant)"
  else
    fail "period window (25 cases, filter bounds + the rebase constant)"
  fi
else
  fail "period window - command-center/frontend/node_modules missing (run: cd command-center/frontend && npm install)"
fi

# The instrument picker's RANKING, and the recents row that fills the box for you. Both decide from
# data, neither has any pixels in it, and until 2026-09-07 the form they belong to offered ten
# symbol names typed into the source by hand — which were the wrong broker's, describing Vantage
# while the lab sat attached to PU Prime and its 1,085 instruments.
#
# ⚠ A wrong rank does not look broken. It looks like a list with the instrument you wanted three
# pages down, which a reader takes for "the broker does not offer it". The fixture is cut from the
# live terminal for exactly that reason — the two rows an invented one would have tidied away
# (a disabled `EURUSD` beside a tradable `EURUSD.p`, and `TSLA` / `TSLAUSD` / `TSLA.24H`) are the
# two that decide the tie-breaks, and without them a whole ranking tier was dead in green.
echo "  [11/16] instrument search + recents ..."
if [ -d "command-center/frontend/node_modules" ]; then
  if (cd command-center/frontend && node scripts/check_instrument_search.mjs); then
    pass "instrument search (31 cases, ranking + per-broker recents)"
  else
    fail "instrument search (31 cases, ranking + per-broker recents)"
  fi
else
  fail "instrument search - command-center/frontend/node_modules missing (run: cd command-center/frontend && npm install)"
fi

# ── 12. Every theme COLOUR a component names exists in the palette ───────────────────────────
# Tailwind DROPS a class it cannot resolve, in total silence: no build error, no console warning,
# no red test. So a mistyped colour and a colour deliberately set to transparent are the SAME
# THING on screen, and nothing in the running app can tell you which one you wrote. The instrument
# dropdown shipped with `bg-bg-raised` as its background (the palette is base / sunken / surface /
# surface-2) and rendered with NO BACKGROUND — sixty instrument rows drawn straight over the form
# underneath. The same pass found three more, live, in pages nobody had suspected. This is rule 7
# arriving in CSS: a class name is a CLAIM about a definition somewhere else, and nothing was
# checking the definition was there.
echo "  [12/16] theme colour tokens ..."
if [ -d "command-center/frontend/node_modules" ]; then
  if (cd command-center/frontend && node scripts/check_theme_tokens.mjs); then
    pass "theme colour tokens (every bg-/text-/border- colour resolves)"
  else
    fail "theme colour tokens (every bg-/text-/border- colour resolves)"
  fi
else
  fail "theme colour tokens - command-center/frontend/node_modules missing (run: cd command-center/frontend && npm install)"
fi

echo ""

# ── 13. Git-hook bypass guard ─────────────────────────────────────────────────
# Milliseconds. `.claude/hooks/block_hook_bypass.py` is the only place the "never bypass the
# commit hook" rule CAN be enforced: the bypass flag tells git to skip its hooks, so a
# refusal written as a git hook is unreachable by construction. This one refuses before git
# is invoked at all. It BLOCKS rather than advises, so both directions are asserted here —
# 15 refusals, 13 silences and one command it cannot parse — because a guard that refused an
# ordinary commit would be switched off within a day, and a guard that refused nothing would
# read as protection while providing none.
echo "  [13/16] git-hook bypass guard ..."
if "$PYTHON" .claude/hooks/check_no_verify.py; then
  pass "git-hook bypass guard (29 cases, refusals and silences)"
else
  fail "git-hook bypass guard (29 cases, refusals and silences)"
fi

# ── 14. Pine block drift ─────────────────────────────────────────────────────
# 🔴 THE PARITY GATES ARE STRUCTURALLY BLIND TO THIS AND THAT IS WHY THIS STEP EXISTS.
# A compare_*.py asks "does the Python agree with ONE Pine file, on ONE export, on ONE
# machine". It cannot see two PINE files disagreeing with each other. Pine has no import,
# so every engine block is copy-pasted into the indicator, its own harness, any harness
# that embeds it for a coupling, and each strategy plus that strategy's export twin -
# ~10 files per rule, with nothing asserting they match.
# On 2026-09-09 the equal-level mitigation rule moved close -> wick in the indicator, the
# Python engine and two harnesses, while SEVEN strategy Pine files stayed on close. Every
# gate that could run stayed green. This step went red on 28 findings the moment it existed.
# ⚠ It compares each copy against the INDICATOR rather than against a value typed into the
# checker, so a deliberate future rule change needs no edit here - move the indicator, move
# the copies, this stays green.
echo "  [14/16] pine block drift (copies vs the indicator) ..."
if "$PYTHON" scripts/check_pine_blocks.py; then
  pass "pine block drift (7 rules across 11 Pine copies)"
else
  fail "pine block drift (7 rules across 11 Pine copies)"
fi

# ── 15. Engine parity gates, against COMMITTED golden exports ────────────────
# 🔴 RULE 22 WAS UNSATISFIABLE FOR MOST OF THIS REPO AND THAT IS WHY THIS EXISTS.
# "No engine change without a green compare_*.py on a real export" is the right rule, but
# exports were git-ignored scratch - so whether a gate could run depended on which CSVs
# happened to be on one laptop. Measured 2026-09-09: NINE of fourteen gates could not
# answer at all, and the ones that could were red against exports taken two months earlier
# from a Pine that no longer existed. A rule that cannot be satisfied stops being a rule;
# it blocks work instead of gating it, and both stalling and routing around it happened.
# ⚠ THIS IS REGRESSION, NOT ACCEPTANCE, and the two must not be confused:
#     golden (here)  catches the PYTHON drifting from a known-good answer. Always runnable.
#     fresh export   catches PINE and Python disagreeing after a Pine edit. Needs a human.
#   A green run here says nothing about a Pine change made after the golden file was taken.
# ⚠ Engines are DISCOVERED (engines/*/exports/golden/*.csv), never listed, and finding zero
#   is a FAILURE - a runner that quietly finds nothing reads as coverage.
echo "  [15/16] engine parity gates (golden exports) ..."
if "$PYTHON" scripts/check_engine_gates.py; then
  pass "engine parity gates vs golden exports (PARTIAL coverage - the step prints the fraction)"
else
  fail "engine parity gates vs committed golden exports"
fi

# ── 16. The generated zone harness is still what its sources say it is ──────
# 🔴 THE ENTRY-BAND EXEMPTION NEEDS FOUR ENGINE BLOCKS IN ONE PINE SCRIPT, so its harness is a
# TENTH copy of the FVG block plus a fresh copy of the structure engine - in a repo whose most
# expensive class of defect is exactly that (step 14 exists because seven strategy files sat on a
# superseded rule while every gate stayed green).
# So that harness is GENERATED: every block is sliced verbatim out of fib_export.pine or
# fvg_export.pine, and this step regenerates and diffs. Edit either source without regenerating and
# it goes RED - the one thing a hand-maintained tenth copy could never give you.
# ⚠ A red here means the harness is validating Python against a Pine block the repo no longer has.
#   Regenerate, then RE-EXPORT before trusting its gate: a regenerated harness is a changed harness,
#   and the committed CSV was taken from the old one.
echo "  [16/16] generated pine harness in sync with its sources ..."
if "$PYTHON" scripts/build_fvg_zone_harness.py --check; then
  pass "fvg_zone_export.pine matches fib_export.pine + fvg_export.pine"
else
  fail "fvg_zone_export.pine is stale against its generator sources"
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
