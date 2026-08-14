#!/usr/bin/env bash
#
# Install the formatting and linting tools this repo's hooks need.
#
#   ./scripts/install_dev_tools.sh            # says what it did
#   ./scripts/install_dev_tools.sh --quiet    # silent unless it CHANGED something
#
# Safe to run every time. Run by `./go`, and named by `.githooks/pre-commit` when a clone is
# missing them. Two halves, because the repo is two languages:
#
#   .venv-lint/     ruff   — formats and lints the 453 python files
#   node_modules/   prettier, eslint, lint-staged — the 108 TS/TSX files, and the hook runner
#
# ⚠ **Ruff goes in its own venv rather than a global install, and that is deliberate.** There is
# no official ruff on npm (the `ruff` package there is an unrelated 2017 generator library), so
# it has to come from pip — and the alternatives are all worse here. A global `pip install`
# fights macOS's managed python; `pipx` and `uv` are not on this machine; and installing into
# `command-center/backend/.venv` would make a repo-wide tool depend on one subsystem's
# environment, which the subsystem-independence rule forbids. A dedicated venv pinned by
# `requirements-lint.txt` is reproducible, removable with `rm -rf`, and cannot drift into the
# runtime dependencies of anything that trades.
#
# ⚠ **It is git-ignored, so it is per-machine** — which is exactly why the pre-commit hook
# refuses rather than skipping when it is absent. A formatter that quietly does nothing on one
# clone produces a repo formatted on one machine and not the other.

set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

QUIET=0
[ "${1:-}" = "--quiet" ] && QUIET=1

DID=""

say()  { [ "$QUIET" = "1" ] || printf '  %s\n' "$1"; }
ok()   { [ "$QUIET" = "1" ] || printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }

# ── 1. Ruff ───────────────────────────────────────────────────────────────────
RUFF_WANT="$(grep -E '^ruff==' requirements-lint.txt | cut -d= -f3)"
RUFF_HAVE=""
[ -x ".venv-lint/bin/ruff" ] && RUFF_HAVE="$(.venv-lint/bin/ruff --version 2>/dev/null | awk '{print $2}')"

if [ "$RUFF_HAVE" != "$RUFF_WANT" ]; then
  if [ ! -x ".venv-lint/bin/python" ]; then
    # /usr/bin/python3 rather than whatever `python3` resolves to: a shell with a project venv
    # active would otherwise build the tool venv on top of it, and the point is independence.
    /usr/bin/python3 -m venv .venv-lint
  fi
  .venv-lint/bin/pip install --quiet --upgrade pip
  .venv-lint/bin/pip install --quiet -r requirements-lint.txt
  DID="$DID ruff"
  ok "ruff $RUFF_WANT installed (.venv-lint/)"
else
  say "ruff $RUFF_HAVE already installed"
fi

# ── 2. The node tooling ───────────────────────────────────────────────────────
if ! command -v npm >/dev/null 2>&1; then
  warn "npm not found. The python half is installed; the frontend half is not."
  warn "Install node (brew install node), then re-run this script."
  exit 1
fi

# ⚠ MEASURED 2026-08-14: node v20.11.0 on this machine, and eslint 9.39 declares it needs
# ^20.19.0. Every tool RUNS today and npm prints an EBADENGINE warning. It is called out here
# rather than left in the install noise, because "works but is below the declared floor" is the
# state that breaks on an unrelated upgrade and looks like the upgrade's fault.
#
# ⚠ **Suppressed under --quiet, which is how `./go` calls this.** Everything works, so this
# would otherwise print on every single launch of the command center — and this repo has already
# paid for the lesson that a warning firing on work it should not be criticising is one people
# learn to scroll past, which costs more than saying nothing (root CLAUDE.md, the doc guard that
# was changed to fire on GROWTH rather than size). It speaks up when somebody runs this script
# on purpose, which is when they can act on it.
if [ "$QUIET" != "1" ]; then
  NODE_MAJOR="$(node -p 'process.versions.node.split(".").map(Number)[0]' 2>/dev/null || echo 0)"
  NODE_MINOR="$(node -p 'process.versions.node.split(".").map(Number)[1]' 2>/dev/null || echo 0)"
  if [ "$NODE_MAJOR" -lt 20 ] || { [ "$NODE_MAJOR" -eq 20 ] && [ "$NODE_MINOR" -lt 19 ]; }; then
    warn "node $(node -v) is below eslint's declared floor (^20.19.0). Everything runs today;"
    warn "upgrade when convenient: brew upgrade node"
  fi
fi

if [ ! -d "node_modules/lint-staged" ]; then
  say "installing prettier / eslint / lint-staged ..."
  npm install --no-audit --no-fund --silent
  DID="$DID node"
  ok "prettier, eslint, lint-staged installed (node_modules/)"
else
  say "node tooling already installed"
fi

# The frontend has its OWN package.json for the React build — separate install, separate
# node_modules. `run_all_tests.sh` needs it for `tsc`.
if [ ! -d "command-center/frontend/node_modules" ]; then
  say "installing command-center/frontend dependencies ..."
  (cd command-center/frontend && npm install --no-audit --no-fund --silent)
  DID="$DID frontend"
  ok "frontend dependencies installed"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
if [ "$QUIET" = "1" ] && [ -z "$DID" ]; then
  exit 0
fi

if [ -n "$DID" ]; then
  echo ""
  echo "  Dev tools ready. From here on:"
  echo ""
  echo "    git commit  -> formats and lints the files in that commit"
  echo "    git push    -> runs the full test suite first (~7 min)"
  echo ""
  echo "  Full rule: root CLAUDE.md -> ## Formatting, linting and the test gate"
  echo ""
else
  say "dev tools already installed"
fi
