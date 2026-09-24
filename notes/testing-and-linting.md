# Notes — Tests, formatting and linting

The two test tiers and when each is required, the formatter and linter rules and why each was measured, and the parallel-run dependency that stops the suite starting. Moved VERBATIM out of `CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## Formatting, linting and the test gate

**Added 2026-08-14.** Until this date the repo had no formatter, no linter and no automated test
run — the standing practice was to run the suites by hand before committing, which is a practice
rather than a mechanism.

**One command installs everything:** `./scripts/install_dev_tools.sh` (run by `./go`, named by the
pre-commit hook when a clone lacks it).

| | tool | where |
|---|---|---|
| Python — format + lint | **ruff** 0.16.3, pinned | `.venv-lint/` (git-ignored), `requirements-lint.txt`, config in `ruff.toml` |
| TS/TSX/JSON/CSS — format | **prettier** | `node_modules/`, config in `.prettierrc.json` |
| TS/TSX — lint | **eslint** | `eslint.config.mjs` |
| Which tool sees which file | **lint-staged** | `lint-staged.config.mjs` |
| pre-commit | format + lint the STAGED files | `.githooks/pre-commit` |
| pre-push | repo-wide lint + format sweep (**NOT the tests**) | `.githooks/pre-push` |

**Prettier cannot format Python** — no official support, the community plugin is abandoned — so
ruff owns `.py` and prettier owns the frontend. **`lint-staged` is the common ground**: it is a node
package, but it runs whatever command you point at a glob, so one config drives both languages from
one hook.

🔴 **NO HOOK RUNS THE TESTS. `pre-push` ran the full suite for one day and it was removed on
2026-08-14 (Aaron's call).** MEASURED: 4:21 for the root suite (1,725 tests) + 2:17 for the backend
(1,014) = **~7 minutes on every push**. That is the same argument that kept the suite off
`pre-commit`, one step later: a seven-minute guard is one people route around, and
`LWG_SKIP_TESTS=1` on every push is indistinguishable from no gate while reading like one.

⚠ **State the loss plainly rather than letting the next reader find it: a broken suite can now
reach `main`, and the first to know is whoever pulls it.** `scripts/run_all_tests.sh` is still the
one command — it is now a thing a PERSON runs, and both the hook's output and its header say so. If
that bites twice, the answer is a FASTER suite rather than a slower hook.

✅ **The answer was a faster suite (2026-08-15, 2026-08-27), then a second TIER (2026-09-10).** The
history and every per-file number are in `docs/TEST_SUITE_PERFORMANCE.md`. 🔴 **The lesson that
stays here: a slow TEST is sometimes a defect in the code under it** (a git N+1 in
`services/bot_versions.py` made `/version` slower on every push), **and fixing production code is
how a suite gets faster without a single scheduling decision.** Nothing in a result shows a cost.

### The everyday command is `scripts/test.sh` — the full run is a deliberate act (2026-09-10)

Why (236 full runs in 60 sessions, ~11 hours waited, 17 only to re-read output):
`docs/TEST_SUITE_PERFORMANCE.md`.

- **After every piece of work: `scripts/test.sh`.** It runs only what the change since the last
  green run can reach — a static import graph plus file tables (`scripts/testing/`): an engine edit
  runs that engine's tests and its parity gate, a frontend edit the typecheck and node checks (and
  the offline browser specs for the pages it can reach — the Bots ones ~45s), a doc edit nothing. An
  unchanged tree answers in 0.3s. `--explain` prints what would run and why.
- **The full run (`scripts/run_all_tests.sh`) is REQUIRED** (1) before pushing anything under
  `engines/`, `strategies/`, `backtest/`, `algos/live/`, `algos/shared/`, `algos/tools/promote.py`
  or a `*.pine`; (2) after changing test plumbing — a `conftest.py`, `pytest.ini`,
  `requirements*.txt`, `scripts/run_all_tests.sh` or `scripts/testing/`; (3) before a promote.
  **Run it in the background and keep working.** It refuses an unchanged tree and names the log;
  `--force` overrides.
- 🔴 **Never re-run anything to see its output.** Both tiers print one line per piece plus the
  failures and keep everything in `.test-logs/fast.log` / `.test-logs/full.log`. Read the log.
- **Prove a test can fail (rule 12) with `python3 -m scripts.testing.mutate FILE 'old' 'new'`** — the
  bug is planted IN MEMORY and only the covering tests run. 🔴 **Never plant a bug by editing a
  file**: two sessions share this clone, and the other one's run or commit picks it up. Python only.
  ⚠ **It REFUSES a test module or conftest** — pytest reads those from disk, so a plant there never
  runs and used to report a false SURVIVED; plant those in a throwaway `git worktree` copy instead.
- ⚠ **The fast tier cannot see git-ignored data** (the bar cache the re-pricing replays read, the
  news calendar) **or git history** (the deploy-version tests). After changing either, `--force`.
- ⚠ **The selector is wrong in exactly one dangerous direction** — a test it never picks goes red on
  main — **so a red full run names every failure the fast tier would have skipped** (`BLIND SPOT`).
  Add the missing rule to `scripts/testing/rules.py`; a selector that skipped a red test once will
  skip it again. `scripts/testing/tests/test_rules.py` goes red when `run_all_tests.sh` gains a step,
  or step 1 a folder, the fast tier does not know.

⚠ **The suites are only parallel-safe because the shared state is per-test** (`tmp_path` DBs, the
`_no_live_vps` interlock, scratch git indexes). A new test that writes a fixed path breaks other
tests non-deterministically, which is the worst failure shape a suite has. ⚠ **Scheduling is not the
lever** — MEASURED: `--dist load` 117s, work-stealing 121s, longest-first 125s; see the comment in
`scripts/run_all_tests.sh`.

### 🔴 If the tests will not START on this machine, it is the xdist dependency — fix it, do not work around it

**The first pull after 2026-08-15 needs one install, and a fresh clone needs it too.**
`scripts/run_all_tests.sh` passes `-n auto` to both python suites, and `pytest-xdist` was added to
`command-center/backend/requirements.txt` in the same commit — but **nothing re-installs
requirements on a `git pull`**, so a machine that had a working venv yesterday will not have the
package today.

**Symptom:** the script prints `pytest-xdist is not installed in …` and exits 1 before running a
single test. **Fix, and it is the whole fix:**

```bash
command-center/backend/.venv/bin/python -m pip install -r command-center/backend/requirements.txt
```

⚠ **Do NOT "fix" it by dropping `-n auto`, by running bare `pytest`, or by exporting
`PYTEST_PARALLEL=` permanently.** Those all work and they all hide the missing package while
putting the suite back to one core on a twelve-core box — the exact state this change existed to
leave. `PYTEST_PARALLEL=` is for a deliberate one-off serial run when you are debugging a suspected
parallelism problem, and nothing else.

⚠ **`./go` and `command-center/start.sh` DO install it** (they run `pip install -r
requirements.txt`), so launching the app once is the other way out. **Nothing else does** — not
`post-merge`, not `conftest.py`, not `install_dev_tools.sh`, which owns `.venv-lint/` and has no
opinion about the backend venv.

⚠ **The refusal is deliberate and must stay a refusal.** pytest exits **4** on an unrecognised
`-n`, which reads as a suite failure and sends the reader at the tests rather than at the venv; and
a silent fall-back to serial would turn a missing package into *"the tests are slow today"*, which
nobody investigates. **This is the same rule as everywhere else here: never let *cannot run* and
*ran and passed slowly* be the same outcome.**

**What `pre-push` does now costs ~3s and is still worth having**: `pre-commit` only ever sees
STAGED files, so a `--no-verify` commit, a rebase that resurrected an old file, or an edit from
another tool reaches a branch unformatted. This is the repo-wide sweep that catches them.
⚠ **The 3s is entirely down to CACHING, and it is all eslint** — MEASURED: ruff clears 628 python
files in **0.2s**, prettier takes **6.4s**, eslint takes **28s** (70% of the hook) because
`typescript-eslint` is type-aware and rebuilds the TS program. `--cache` on both makes it **1.9s**
warm. A first run after a frontend pull pays the full ~35s again — that is the cache working.
⚠ **The cache files are git-ignored**: they key on local file mtimes, so a checked-in cache is a
linter skipping files it has never read on this machine.

⚠ **"Run all tests" is NOT a bare `pytest`** — the root collects 2,670 tests and dies on a
collection error, because the backend has its own `pytest.ini`, its own venv, and imports
`services`/`routers` by bare name. Use `scripts/run_all_tests.sh`. It runs all three suites even
when one fails: stopping early reports the others as unknown, and unknown reads as fine.

✅ **Frontend logic CAN be gated when it is pulled out of the canvas.** Step 8 runs
`command-center/frontend/scripts/check_trade_geometry.mjs` with nothing running — the backtest
chart's trade box decides from PRICES how far its adverse band reaches and whether the exit is
drawn at all, and both were wrong on real trades for as long as they lived inside a klinecharts
callback that only a browser could reach. ⚠ **The lesson is about REACHABILITY, not about charts:
logic with no seam a test can grab is logic nobody checks.** The rules are in
`command-center/frontend/src/components/ChartPanel/CLAUDE.md`.

🔴 **Step 9 (2026-08-27) is the same move for a harder case: a rule written TWICE, in two
languages.** `check_param_conditions.mjs` drives the run form's visibility evaluator, whose twin is
the lab's own `stress_tester.param_is_reachable` — and the two have already disagreed in silence, a
number that compared equal in Python and unequal in JavaScript leaving a dead control live on
screen. ⚠ **The CASES are the shared artifact, not the code**: one fixture file, read by the node
check here and by the python test in step 2, so a shape one side learns and the other does not
fails on the side that did not learn it. ✅ It found a real disagreement on its first run. **When
you write the same rule on both sides of a boundary, make the two answer ONE list of cases** —
mirroring them by hand is how they drift, and neither side looks wrong alone.

🔴 **Step 10 (2026-09-03) gates the one number two different pages multiply every dollar by.**
`check_period_window.mjs` drives the period window's rebase — the constant that reads a slice of a
finished book as though it were the whole book — for the single-backtest page and the stack page
at once. It lived inside a React hook until that day, reachable only from a browser, which is the
same shape rule that put steps 8 and 9 here. ⚠ **A wrong scale here is not a broken chart; it is a
plausible dollar figure with nothing on screen to say it is wrong.** 🔴 **Its mutation map caught
the sharper lesson: four scaling cases were written against a window whose scale happened to be
exactly 1, where *"this field is scaled"* and *"this field is left alone"* are the same assertion.
They were green and two mutations survived them.** A scale of 1 is the arithmetic version of a
fixture more capable than production — the test describes a system where the thing under test does
nothing. **Check that a test's inputs can distinguish the behaviours it names.**

🔴 **Step 11 (2026-09-07) gates the list a reader picks the INSTRUMENT off.** `check_instrument_search.mjs`
drives the picker's ranking and its per-broker recents — both decide from data, neither has any
pixels in it, and the form they belong to offered ten symbol names typed into the source until that
day, which were the WRONG BROKER'S: Vantage's spellings while the lab sat attached to PU Prime and
its 1,085 instruments. ⚠ **A wrong rank does not look broken. It looks like a list with the
instrument you wanted three pages down, which a reader takes for "the broker does not offer it".**
🔴 **Its map carries the sharpest lesson yet, and it is one step past step 10's: SIX mutations
survived across two passes, and the last three survived because a LATER FIX REROUTED their cases
onto a code path the mutation could no longer reach.** Nothing went red and no case was edited — the
map simply stopped being true, and re-running it end to end is the only thing that showed it. **A
fix that reroutes a case can silently un-cover the branch that case used to exercise.** ⚠ **One
ranking tier was DELETED rather than covered** — unreachable by construction, killable by no
mutation, and reading to the next person as a covered branch.

🔴 **Step 12 (2026-09-07) gates something no test in this repo could previously see: a COLOUR that
does not exist.** `check_theme_tokens.mjs` checks every `bg-`/`text-`/`border-` class in the
frontend against the palette in `tailwind.config.js`. **Tailwind DROPS a class it cannot resolve
and says nothing** — no build error, no console warning — so the instrument dropdown shipped with
`bg-bg-raised` as its background (the palette is base / sunken / surface / surface-2) and rendered
with NO BACKGROUND at all: sixty rows drawn straight over the form underneath. ⚠ **A colour that
does not exist and a colour deliberately set to transparent are THE SAME THING on screen**, so
nothing in the running app can tell you which one you wrote — this is rule 7 arriving in CSS, a
class name being a CLAIM about a definition somewhere else with nothing checking it. 🔴 **It found
three more the same minute, live, in pages nobody suspected** (`bg-bg-elevated` on the run detail
page, `text-gold-bright`, and a missing hyphen in `bg-bg-surface2`), each invisible for as long as
it had existed. ⚠ **It reads the palette OUT of the config rather than from a list typed into the
check**, so a colour added to the theme cannot start failing it. ⚠ **It carries a SELF-TEST,
because otherwise "no findings" means *the app is clean* and *the scanner is broken* at the same
time** — the exact defect it exists to stop. ⚠ **Nine mutations killed and one DELETED**: a guard
rejecting arbitrary values (`text-[11px]`) that no mutation could kill, because the rule beside it
already rejected every one of them — **a branch nothing can kill reads as a covered branch**, the
same call step 11 made about its unreachable ranking tier.

⚠ **Playwright is deliberately NOT in the gate — except the OFFLINE specs.** Its config has no
`webServer` block on purpose — this backend talks to a live VPS and a live MT5 terminal, so a runner
that boots it on demand can start things on the trading box. `./start.sh` then `npm test` stays a
person's decision; `tsc --noEmit` is the half that needs nothing running. ✅ **Since 2026-09-11 the
offline specs are step 19**: they replay recorded answers and load a build of the app off disk, so
they need nothing running and reach nothing live. The fast tier picks them ONE SPEC AT A TIME: the
pages a spec opens are read off its `page.goto` calls and App.tsx's route table, and the app's
imports are followed from `main.tsx` to those pages only (`rules.py` → `offline_spec_sources`), so
a Bots edit never runs the chart specs. A page that crashes as it loads is the one miss, and the
full run names the failing SPEC as a BLIND SPOT. Rules: `command-center/frontend/CLAUDE.md` →
*Offline specs*.

### 🔴 Both hooks are built around the UNATTENDED committer

`algos/tools/ledger_sync.py` commits AND pushes the live bot's decision record twice a day from the
Mac with nobody watching, staging only `.jsonl` and `.log`. **A rule that fires on a robot's commit
has no human to read its message: it does not nag, it silently stops the job** — which has already
happened twice on the docs half of `commit-msg` (2026-08-05).

- **`pre-commit` checks SCOPE BEFORE TOOLS** — nothing lintable staged ⇒ exit 0 without ever asking
  whether node is installed.
- **`pre-push` skips a push carrying no code**, on a POSITIVE trigger rather than an ignore-list, so
  a new data format added tomorrow is skipped by default — the safe direction.
- Deliberate skip: `LWG_SKIP_PREPUSH=1 git push` (`LWG_SKIP_TESTS=1` still works — it is what is in
  everyone's muscle memory). It prints a loud line and has no silent form.

### The rules were MEASURED, not picked

Every number behind them is in `HISTORY.md` → *Formatting and linting arrive*. The rules themselves:

- **`line-length = 100`**, because that is how this code is already written (p90 94). Ruff's default
  88 would rewrap 21,040 lines against 2,647.
- **`target-version = "py39"`** — the lowest runtime here. It is why `UP` is not selected: those
  rules propose 3.10+ syntax the backend venv cannot run.
- 🔴 **`E402` is OFF because the engine imports DEPEND on breaking it** — 193 files do
  `sys.path.insert` then `from market_structure import ...`. ⚠ **That makes the import SORTER the
  thing to watch, and it was checked rather than assumed: 0 hoisted across all 193.** Re-run that
  check if `I` is ever swapped for a different sorter.
- 🔴 **`F401`'s "unused" is per-MODULE, so `--fix` DELETES a RE-EXPORT and nothing fails until
  run time.** It cannot see `other_module.NAME` read in a different file. It did exactly that on
  2026-08-14 to `sizing_pipeline.MODES`, and one test caught it — an `AttributeError` inside a
  sizing branch, i.e. a crash on a real backtest rather than on import. ⚠ **Checking `__init__.py`
  files is NOT enough** — that reasoning covers a package's public API and a plain module launders
  a re-export straight past it. **A deliberate re-export needs `# noqa: F401` and a comment naming
  its consumer**, or the next `--fix` removes it again.
- **`E741`, `B904`, and eslint's React Compiler rules are off or at warn** — each fires dozens of
  times on code that ships and works. `rules-of-hooks` stays an error: a conditional hook call is a
  crash, not advice.
- 🔴 **A rule nothing can AUTO-FIX blocks the ratchet, and that is worse than it sounds.**
  `pre-commit` runs `ruff check --fix`, which exits non-zero while any finding remains — so a
  legacy file carrying one un-fixable finding is a file you cannot commit a one-line change to.
  Six such rules (`B023`, `F841`, `B007`, `B008`, `B017`, `E731`) were selected wholesale, never
  measured, and turned 46 shipping-and-working sites into a wall; each is now off with its count
  and the reason it was READ rather than waved through, in `ruff.toml`. ⚠ **Before selecting a
  rule, ask what it does to the files you are NOT going to fix** — a wall gets `--no-verify`d, and
  that leaves no trace.
- **Markdown is NOT formatted.** Prettier pads table columns, which grows a CLAUDE.md ~35% in pure
  whitespace and would trip this repo's own doc-growth guard on every commit.

### The ratchet, and the one bulk pass that was allowed through it

413 of 627 python files predated any formatter. A bulk pass ran on **2026-08-14** and covers 424 of
them — but **`engines/` and `strategies/` were carved OUT of it by rule 22**, and how that was
decided is the part worth keeping.

**Rule 22 was applied by RUNNING all 14 gates, not by reasoning that layout cannot change
behaviour.** It cannot — and that is exactly the confident argument a gate exists so you do not
have to trust. **Only the 5 engines whose gate ran GREEN were reformatted** (`market_structure`,
`rsi_divergence`, `session_volume_profile`, `candlesticks`, `vwap`). `fibonacci`, `order_blocks`,
`sessions`, `liquidity`, `fair_value_gaps`, `equal_highs_lows` and **all four strategies including
the LIVE `sos_fade`** were reverted to HEAD and are still unformatted.

🔴 **9 of the 14 gates COULD NOT RUN, and that is the finding.** Exports are git-ignored scratch
(`.gitignore` → `*VANTAGE_*.csv`), so **which engine you can gate depends on what is sitting on
that machine**, and a fresh clone can gate almost nothing. ⚠ **Rule 22 is therefore unsatisfiable
on demand for most of this repo — it blocks work rather than gating it.** Fixing that is a decision
about where exports live, not a formatting job.

⚠ **A "pre-existing" red is still a red.** `fibonacci`, `sessions` and `liquidity` were re-run
against HEAD in a throwaway worktree and gave byte-identical output. That exonerates the formatter
and changes nothing about whether they may be committed. They may not.

⚠ **`regime/` and `news/` were reformatted and have NO parity gate by construction** — no Pine
source, so no `compare_*.py` can exist. Unit tests are the only gate they will ever have. Do not
read this as rule 22 having a general exception.

🔴 **THE CARVE-OUT IS ENFORCED IN `ruff.toml`, NOT BY REMEMBERING WHAT YOU REVERTED.** It was
first done with `git checkout --` on those paths, which holds exactly until the next
`ruff format .` over the whole repo — which re-formatted every one of them, `git add -A` staged
it, and the LIVE `sos_fade` shipped in a commit whose message said it was excluded. **Nothing
failed and no test went red; the commit message was the only thing that disagreed with the tree.**
⚠ **A decision that lives in your memory of what you reverted is not one the next command
respects.** ⚠ **The exclusion only binds an explicitly-named path when `--force-exclude` is
passed** — `lint-staged.config.mjs` passes it on both ruff commands, the same flag that protects
`deployed/`.

Per-gate bar counts and the full verdict table: `HISTORY.md` → *The bulk reformat, and the nine
gates that could not answer*. Outside those two trees the repo still converges as it is worked on.

🔴 **`deployed/` is excluded in `ruff.toml` AND the hook passes `--force-exclude`** — that flag is
what makes an explicitly-named path still honour the exclusion. An edit there changes what a running
bot executes, with no promote and no restart.

⚠ **Ruff's version is PINNED**, or two machines reformat the same file differently and each undoes
the other on every commit.

## `backtest/tools/` is never collected as tests (2026-09-24)

- The root `conftest.py` ignores every file under `backtest/tools/`. That folder holds study scripts, and two named `*_test.py` were being collected and replaying six years of bars against the trading box's data agent — 24 errors in `scripts/run_all_tests.sh`.
- The whole folder is ignored, not the two files, so the next script named after what it studies cannot do it again. A tool's real tests go in `backtest/tests/`.
- ⚠ Naming one of those files directly on the pytest command line still collects it — that is pytest's own behaviour and not a gap in this rule.
