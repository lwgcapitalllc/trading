// What runs on a staged file, by extension. Driven by `.githooks/pre-commit`.
//
// **This file is the answer to "is there common ground between lint-staged and python?".**
// `lint-staged` is a node package, but it is not a JavaScript linter — it works out which files
// are staged and runs whatever COMMAND you point at a glob. So one config drives ruff for the
// 453 python files and prettier + eslint for the 108 TypeScript ones, from one hook, and each
// tool only ever sees the files in the commit.
//
// ⚠ **Order matters within a glob.** The formatter runs FIRST and the linter second: ruff's
// formatter resolves E701/E702 (statements joined by `;` or `:`) on its own, so linting first
// would report 46 findings the next command was about to fix.
//
// ⚠ **lint-staged re-stages what these commands rewrite**, so a formatting fix lands in the
// commit you are making rather than showing up as a dirty tree afterwards.
//
// ⚠ **Ruff is called by PATH, not by name.** It lives in `.venv-lint/`, which is deliberately
// not on anybody's `PATH` — see `scripts/install_dev_tools.sh` for why a dedicated venv rather
// than a global install.

const RUFF = '.venv-lint/bin/ruff'

export default {
  // ── Python ──────────────────────────────────────────────────────────────────
  // `--force-exclude` makes ruff honour `ruff.toml`'s `extend-exclude` even though the paths are
  // passed explicitly. Without it, an excluded file handed in by name is linted anyway — which
  // is exactly how a `deployed/` snapshot would get reformatted under a running bot.
  '*.py': [`${RUFF} format --force-exclude`, `${RUFF} check --fix --force-exclude`],

  // ── The frontend ────────────────────────────────────────────────────────────
  // ESLint exits non-zero on ERRORS only, so the 78 React Compiler warnings do not block a
  // commit — they are advice on code that ships today. See `eslint.config.mjs`.
  'command-center/frontend/**/*.{ts,tsx}': ['prettier --write', 'eslint --fix'],

  // ── Everything else prettier can parse ──────────────────────────────────────
  // ⚠ Markdown is NOT here, on purpose, and `.prettierignore` carries the measurement.
  '*.{json,css,scss,html,yml,yaml}': ['prettier --write'],
}
