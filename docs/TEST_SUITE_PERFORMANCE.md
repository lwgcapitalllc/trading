# The test suite audit — 2026-08-15

**The question, in Aaron's words:** *"I don't understand how we have twenty seven hundred unit
tests… running twenty seven hundred was taking us seven minutes, so I couldn't even put it as a
quick commit hook. I wanna audit all the tests, remove tests that are no longer relevant, and
then optimize."*

**The answer:** nothing needed removing, and the count was never the cause. **67 tests out of
2,811 were the entire seven minutes.** The other 2,744 ran in ~130 seconds.

The suite is now **2:45** with every test still running — ~4x faster, nothing excluded.

---

## Part 1 — the relevance audit

Ran before any optimisation, because "delete the dead ones" was the stated first step and it
would have been the wrong place to start.

| looked for | found |
|---|---|
| tests with no assertion | **7 candidates, 0 real.** All seven are deliberate *this must never raise* tests — a ledger write that must not kill the bot, a JSON-serialisability check. |
| tests for deleted code | **0.** Every repo path named in a test either exists or is a synthetic fixture inside a `tmp_path`. |
| duplicate tests | **0 real.** 17 shared test-function names, all different subjects in different modules (two fib timeframes, two news scrapers). The one true overlap is `test_notification_routing.py` existing in both `algos/` and `command-center/backend/` — two separate notifier implementations in two apps that are meant to stay independent. |
| skipped / inert tests | 13 skip conditions, every one guarding on git-ignored data or root privileges. |

**Where the 2,609 hand-written test functions live** (2,811 collected after parametrize):

| area | test functions |
|---|---|
| `command-center/backend` | 935 |
| `algos/tests` (the live bot) | 646 |
| `backtest` | 405 |
| `strategies` (4 ports) | 364 |
| `engines` (all 13) | 244 |

⚠ **The 13 canonical engines are 9% of the suite** and `market_structure` — the base engine
everything else composes — has 10 test functions. The weight is in the live bot and the ops
backend. That is not a finding about speed, and it is worth knowing.

**One oddity:** `algos/nt8/test_bt_switch.py` is a VPS debug script named `test_*`. It is already
`collect_ignore`d in the root `conftest.py` and costs nothing, but it should be renamed so it
stops being a trap.

---

## Part 2 — where the time actually went

Measured with `--durations`, both suites, before any change.

| | tests | time |
|---|---|---|
| root suite, minus 10 tests | 1,750 | **78s** |
| backend suite, minus 3 files | 991 | **53s** |
| the 67 excluded tests | 67 | **~7 min** |

Four files. Nothing else came close.

### 1. `services/bot_versions.py::changes_between` — an N+1 in PRODUCTION code

`tests/test_bot_version.py` stubs SSH carefully and stubs local `git` not at all. Profiled with
`cProfile`: **1,080 git subprocesses, 51.8s of a 53.7s run**, of which 44.3s was `select.poll` —
the parent waiting on child processes.

The cause was in the code under test, not the test. `changes_between` ran `git log` for the commit
list and then a `git show --name-only` **per commit** to read each one's file list.

🔴 **It scaled with the RANGE, so every commit either of us pushed made the `/version` endpoint and
this file slower, permanently.** A bot 89 commits behind paid ~3.7s inside the page load.

🔴 **And it was invisible.** Re-running the whole history through old and new code gives
byte-identical output — 172 commits, every field equal. No number on the Configure tab was ever
wrong. **Nothing in a result can show you a cost.**

**Fixed:** `--name-only` on the `git log` that was already running. One process per range.

| | before | after |
|---|---|---|
| full history (172 commits) | 5.5s | **0.10s** |
| `test_bot_version.py` (15 tests) | 53.7s | **8.7s** |
| git subprocesses | 1,080 | **14** |

🔴 **`areas` — the field this function exists to compute — had NO test at all.** Forcing it to
return `[]` left all 49 tests across both bot-version files green. Found by mutation, not by
review. Two tests added, each watched red against its own mutation:
`test_every_change_names_the_tree_it_touched` and
`test_the_change_list_is_ONE_git_process_per_range`.

⚠ **The second counts PROCESSES, not seconds.** A wall-clock assertion is flaky on a busy laptop
and vacuous on a fast one, and the defect was the fan-out rather than the duration.

### 2. `tests/test_structure_internal_breaks.py` — the same file read five times

Re-read the whole **31 MB / 559,035-row** M5 bar cache to build each window, and replayed the
structure engine six times to produce two distinct answers.

Component costs, measured: `csv.DictReader` over the file **2.5s**, `strptime` on the rows kept
**2.45s** — ~5s per window, three windows, no sharing.

**Fixed:** one read of the file cached at module scope, the window slice cached, the engine replay
cached per window, and `strptime` replaced by a `calendar.timegm` slice on the fixed-width stamp.
**62s → 21s.**

Every window was verified byte-identical to the previous implementation before the old code was
removed.

⚠ **The equivalence guard nearly ate the saving.** The first version checked all 559,035 rows
against `strptime` — the function it exists to replace — and cost **11.1s**, a guard more
expensive than the thing it guards. That exhaustive run WAS performed once (0 disagreements) and
is recorded here; what ships covers the failure mode instead of the volume: every boundary the
format has, plus a stratified sweep on a prime stride, **1.9s**. Watched red by mutating the
minute slice — it fails on the leap-day boundary before reaching the file sweep.

### 3. `backtest/tests/test_reprice.py` — eight replays for four answers

Each parametrized case replayed `mpc_sos_fade` over two years of M15 bars twice — free, then
charged — and the **free replay is character-for-character the same run in all four tests**. The
bar cache was read four times to do it.

**Fixed:** replays cached on their cost kwargs. Eight replays become four; one cache read.
**182s → 80s.**

⚠ Keyed on the cost kwargs, not the built profile — `_profile()` returns a fresh object per call,
so keying on it would depend on `AccountProfile` hashing by value, which is not something a test
file should be pinning.

⚠ **No stored run re-prices and no documented baseline moves.** Test file only. The reference
tests demand exact equality against a real charged replay, so a cache handing back a different run
could not pass them.

### 4. `backtest/tests/test_cache_concurrency.py` — one event, three assertions

Three tests each fired a 5-process × 250,000-row cache collision, then asserted a different
property of the result. **Fixed:** module-scoped fixture, one collision. **86s → 25s.**

⚠ **The cost, stated plainly: a racy test run three times has three chances to catch an
intermittent regression, and this has one.** Acceptable only because the reproduction is
structural rather than lucky — 250,000 rows makes the read-merge-write window enormous, which is
why that size was measured in the first place, and against the unlocked code both failures appear
on every run. **If `_ROWS_EACH` ever shrinks, this goes back to per-test.**

---

## Part 3 — parallelism, last

`pytest-xdist` was not installed. Both suites ran single-core on a 12-core box.

Deliberately done **last**, and that ordering is the point: parallelism would have hidden all four
problems above rather than fixing them — including the production N+1, which would have kept
getting worse behind a suite that looked fine.

| | serial | `-n auto --dist load` |
|---|---|---|
| root suite | 202s | **119s** |
| backend suite | 150s | **45s** |

⚠ **`--dist load`, not `--dist loadfile`, and the intuitive choice measured SLOWER.** Several
files now build an expensive artefact once at module scope; `loadfile` keeps a file on one worker
and preserves every one of those caches, which sounds right and gives **138s** — because the two
heaviest files become the whole critical path with eleven cores idle beside them. `load` spreads
them and rebuilds a cache per worker: more CPU, less wall clock.

⚠ **The script REFUSES if xdist is missing rather than falling back to serial.** pytest exits 4 on
an unrecognised `-n`, which reads as a suite failure and sends the reader at the tests; and a
silent fall-back is worse still — it turns a missing package into "the tests are slow today" and
nobody investigates. `PYTEST_PARALLEL= ./scripts/run_all_tests.sh` is the deliberate serial run.

⚠ **The suites are parallel-safe because their shared state is per-test** — `tmp_path` DBs, the
`_no_live_vps` interlock, scratch git indexes. A new test that writes a fixed path will break
*other* tests non-deterministically, which is the worst failure shape a suite has.

---

## Where it stands

Measured end to end through `./scripts/run_all_tests.sh`, which is what a hook would run:

| | before | after |
|---|---|---|
| root suite | ~4:21 | **~1:55** |
| backend suite | ~2:17 | **0:52** |
| frontend typecheck (`tsc --noEmit`) | ~0:25 | ~0:25 |
| **the whole script** | **~7 min** | **3:16** |
| tests run | 2,811 | **2,811** (+2 new) |

⚠ **Quote the 3:16, not the sum of the two python suites.** The script also typechecks the
frontend, and a number that leaves out a step somebody is about to wait for is the same class of
error as a backtest reporting a narrower window than it was asked for.

⚠ **Wall clock varies run to run under `-n auto`** — the root suite measured 105s, 119s and ~115s
on three runs of identical code, because work-stealing placement differs. Read these as ranges.

🔴 **`backtest/tests/test_reprice.py` is now ~68s of the root suite's 119s, on its own.**
Everything else in that suite finishes in **44s**. Those are four genuine two-year strategy
replays, and they are what the file exists to check.

**So any further speed is a COVERAGE decision, not a scheduling one.** The options, with what each
costs:

1. **Leave it.** Everything runs, 2:45.
2. **Mark the four real-data replay tests and run them on push rather than on commit.** ~50s on
   commit. ⚠ Those tests already `skipif` when the bar cache is absent, so they do not run on a
   fresh clone at all — which is also why nobody noticed the seven minutes sooner.
3. **Shorten the reprice reference window.** Cheapest in wall clock, and it narrows what the
   agreement between re-pricing and replay has been demonstrated over. Not a decision to make
   quietly.

That is Aaron's call, not one to take by narrowing a window and saying nothing.
