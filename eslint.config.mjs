// ESLint — the linter for the ONE node subsystem in this repo, `command-center/frontend`.
//
// It lives at the repo ROOT rather than inside the frontend for the same reason `package.json`
// does: `lint-staged` has to see every staged path, python included, and a tool rooted inside
// one subsystem cannot. ESLint resolves its plugins from the config's own directory, so the
// root `node_modules` is what it reads.
//
// ⚠ **Nothing else in this repo is JavaScript.** `algos/`, `backtest/`, `engines/`,
// `strategies/` and `smart-money/` are python (ruff's), and the Pine / NinjaScript / MQL5
// sources have no linter at all. So this file's `files` globs are deliberately narrow: a
// broad glob would make ESLint walk 453 python files to find nothing.

import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  {
    // Everything that is not hand-written frontend source.
    ignores: [
      '**/node_modules/**',
      '**/dist/**',
      '**/build/**',
      '.venv-lint/**',
      '**/.venv/**',
      'test-results/**',
      'playwright-report/**',
    ],
  },
  {
    files: ['command-center/frontend/**/*.{ts,tsx}'],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,

      // A component file that also exports something else breaks Vite's fast refresh. A warning
      // rather than an error: it costs a dev-server refresh, never a bug in production.
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],

      // An unused parameter is often a deliberate signature (an event handler that ignores its
      // event), so the underscore prefix is the opt-out — the same convention the python side
      // uses. An unused IMPORT stays an error, because that is dead weight in a bundle.
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' },
      ],

      // ⚠ `any` is a WARNING here, not an error, and that is a measured decision rather than a
      // shrug: `src/types/index.ts` mirrors `backend/models.py` by hand, and the places that
      // reach for `any` are mostly the chart payloads whose shape the backend owns. Making it an
      // error would block commits on files nobody is changing — the ratchet failure this whole
      // setup is arranged to avoid. Tighten it once the chart types are generated rather than
      // typed twice.
      '@typescript-eslint/no-explicit-any': 'warn',

      // `set.has(x) ? set.delete(x) : set.add(x)` is a deliberate toggle idiom used in 11 places
      // across this frontend, always the same shape. The rule's real job is catching a statement
      // that computes nothing — a stray `foo.bar`, or an `a === b` where `a = b` was meant — and
      // it still does with these two allowances on.
      '@typescript-eslint/no-unused-expressions': [
        'error',
        { allowTernary: true, allowShortCircuit: true },
      ],

      // ── The React Compiler rules — kept ON, kept at WARN ──────────────────────────────────
      // `eslint-plugin-react-hooks` v7 promoted the React Compiler's correctness rules into its
      // recommended set, and on this codebase they account for **51 of 65 errors** (28 of them
      // `set-state-in-effect` alone). They are worth reading — several point at real re-render
      // bugs — but every one of them is on code that ships and works today, and this repo is
      // set up to lint what you TOUCH. An error here means editing one line of `BacktestDetail.tsx`
      // blocks the commit on 28 findings nobody in that commit created, which is how a hook
      // teaches people to reach for `--no-verify`.
      //
      // ⚠ **`rules-of-hooks` stays an ERROR** (it is on by default in the recommended set above,
      // and is deliberately not downgraded here): a conditional hook call is a crash, not advice.
      'react-hooks/set-state-in-effect': 'warn',
      'react-hooks/static-components': 'warn',
      'react-hooks/refs': 'warn',
      'react-hooks/purity': 'warn',
      'react-hooks/immutability': 'warn',
      'react-hooks/use-memo': 'warn',
    },
  },
  {
    // Playwright specs run in node, not the browser, and legitimately use its globals.
    files: ['command-center/frontend/tests/**/*.{ts,tsx}'],
    languageOptions: { globals: { ...globals.node, ...globals.browser } },
  },
  {
    // Config files are node-side ESM.
    files: ['*.js', 'command-center/frontend/*.{js,ts}'],
    languageOptions: { globals: globals.node },
  }
)
