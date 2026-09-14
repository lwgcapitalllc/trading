# Notes — Frontend browser tests

What `npm test` covers, the offline specs, and two fixture defects found in the suite. Moved VERBATIM out of `command-center/frontend/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## ESLint runs on this folder, from a config at the REPO ROOT (2026-08-14)

`eslint.config.mjs`, `.prettierrc.json` and `node_modules/` are at the monorepo root, not here.
That is not an accident of layout: `lint-staged` has to see every staged path — python included —
and a tool rooted inside one subsystem cannot. This folder keeps its own `package.json` for the
React build; the root one is dev tooling only. Full rules and why each is set: root `CLAUDE.md` →
*Formatting, linting and the test gate*.

Two things that decide what you see here:

- **The React Compiler rules are at WARN, not error.** `eslint-plugin-react-hooks` v7 promoted them
  into its recommended set and they are **51 of the 65 errors** this frontend produced, every one on
  code that ships and works (28 are `set-state-in-effect` alone). Read them — several point at real
  re-render bugs — but an error would mean editing one line of `BacktestDetail.tsx` blocks the commit
  on 28 findings nobody in that commit created. ⚠ **`rules-of-hooks` stays an ERROR** and must: a
  conditional hook call is a crash, not advice.
- **`@typescript-eslint/no-unused-expressions` allows ternaries**, because
  `set.has(x) ? set.delete(x) : set.add(x)` is a deliberate toggle idiom used in 11 places here.

**Current state: 0 errors, 78 warnings.** Getting to zero errors deleted three genuinely dead
symbols the linter found in the Playwright specs — an unused `type Page` import, an uncalled
`weekStart` helper, and an unreferenced `API` constant. ⚠ **`prettier` is configured `semi: false`
/ `singleQuote: true` because that is what these 108 files already do** (377 single-quoted imports
against 4 double, 30 semicolon-terminated lines out of 40,677) — it codifies the house style rather
than imposing one. Markdown is deliberately excluded; the measurement is in `.prettierignore`.

### `scripts/*.mjs` — the checks that need NOTHING running

Three so far, and they exist for the same reason: the thing they check is ARITHMETIC, while the only
browser-side evidence for it is formatted text or canvas pixels. A check that settles for those is
asserting on a formatter or on a locator.

- **`check_period_rebase.mjs`** — the period filter's numeric identities. Needs the backend on
  :8000, so it is run by hand. Detail under *The period filter* above.
- **`check_trade_geometry.mjs`** — the trade box's two PRICE rules: how far the adverse band
  reaches, and whether the exit gets a marker. Needs nothing running, so it IS in the gate,
  as **step 8 of `../../scripts/run_all_tests.sh`** — 25 cases, non-vacuity by mutation with the
  map RUN rather than reasoned. **The rules and why each exists live in
  `src/components/ChartPanel/CLAUDE.md`; do not restate them here.**

- **`check_param_conditions.mjs`** — the `show_if` / `disable_if` evaluator, which decides which
  settings a run form draws. Needs nothing running; **step 9 of `../../scripts/run_all_tests.sh`**,
  28 cases. 🔴 **Its reason is different from the other two and is the stronger one: this rule has a
  TWIN in `backend/services/stress_tester.py`, and the two have already disagreed in silence.** So
  the CASES are the shared artifact — `tests/fixtures/param-conditions.json` is read by this script
  AND by `backend/tests/test_param_gates.py`, and a shape one side learns and the other does not
  fails on the side that did not learn it. ✅ It caught an empty-condition disagreement on its first
  run, in code neither side's own tests could see.

⚠ **The pure module they drive is the point.** `src/components/ChartPanel/tradeGeometry.ts` and
`src/components/paramConditions.ts` are both import-light precisely so a plain node script can run
them — the trade rules were wrong on real trades for as long as they lived inside a canvas callback
nothing could reach, and the condition evaluator lived inside a `.tsx` component where only a
browser could reach it. ⚠ **`paramConditions.ts` imports one TYPE from `@/types`, which esbuild
erases** — a VALUE import added there needs an alias resolver in the script, and the failure is an
unhelpful `MODULE_NOT_FOUND`.

### 🔴 A FIXTURE PINNED TO A DATABASE ROW — bitten three times now

**A spec that asserts on which rows happen to be in the lab will fail on a day nothing is wrong, and
that failure is indistinguishable from a regression until somebody reads it.** Third instance
2026-08-16 (`chart-paging.spec.ts`, both checks, a 120s timeout pointing at paging code that was
fine); the incidents are in `../docs/FRONTEND_BUILD_NOTES.md` → *Fixtures pinned to a row*. Two
answers, chosen by what the check needs:

- **RESOLVE when the check needs a SHAPE.** `period-filter` wants "any run with ≥20 dated trades".
  ⚠ **Derive the DATE constants from the resolved run too** — a literal `TARGET` beside a resolved
  run moves the expiry from the run id to the calendar instead of removing it. ⚠ **Keep the vacuity
  guard**; with the fixture no longer fixed, it stops being self-evident.
- ✅ **RECORD it when the check needs particular LAYERS (2026-09-11).** Seven chart specs named a
  run for its VWAP series, fib legs or candle-reversal marks and called `requireRun` to fail by name
  when it left; the runs HAD left. They replay recordings now (*Offline specs*), `requireRun` is
  deleted, and a recording cannot leave the lab.

### 🔴 …and a row is only ONE of the five things a spec drifts against (2026-08-16)

**Sixteen checks were red across three specs nobody had touched, and every one was the page being
RIGHT.** A database row is the version of this everybody sees; the other four are the same defect
wearing different clothes, and each has its own fix. Full record: `../docs/FRONTEND_BUILD_NOTES.md`
→ *The five things a browser spec drifts against*.

| Pinned to | How it bit | The fix |
|---|---|---|
| a **row** | `chart-paging` (2), 7 specs at risk | resolve, or record it — above |
| the **weekday** | `calendar.spec.ts` (2) — the fixture built Mon–Fri and **the page opens on TODAY**, so both checks were green five days in seven and failed on a Sunday | **the FIXTURE covers all seven days.** The file had already met this trap and written it down beside one `?day=1`; the next two tests walked straight in. **A trap named in a comment is one the next test still hits — fix it where it is GENERATED** |
| the **calendar** | `overview.spec.ts` (1) — `?week=12 // US fall-back, 2026-11-01`, a fixed date written in an offset from today, so it named a different week every Monday and asserted 169h against a correct 168h | **derive the offset.** `nextDstWeek()` scans `getTimezoneOffset()` forward for the real changeover and expects 169h on a fall-back, 167h on a spring-forward. ⚠ It THROWS on a no-DST timezone — a silent skip and a pass are the same outcome |
| the **registry's SIZE** | `overview.spec.ts` (2) — `1 of 1` / `1 of 2` not reporting, against a fleet that grew to 3 | **SET the fleet, don't add to it.** Trim the real snapshot to the bots the rule needs. ⚠ And STATE the reporting bot's balance rather than inheriting it — the live one is `null` whenever the terminal is quiet, which would make the check pass for the wrong reason on exactly the days it matters |
| an **empty table** | `stress.spec.ts` (11) — the lab held ZERO stress tests, so a whole feature's suite had switched itself off | **make the fixture one command.** `backend/scripts/seed_stress_fixture.py` seeds a Monte-Carlo-only test (seconds, no VPS, no child backtests, Telegram stubbed), and the suite's own failure prints that command |
| a **count of somebody else's metadata** | `param-gates.spec.ts` (4, 2026-09-06) — `26 settled` against a page correctly saying `20`, `Already decided · 31`, and `{ name: /^Secondary re-entries$/ }` against a header that states its own settings count | **DERIVE it.** `settledInSchema()` counts the `hidden` params in the served schema and the escape check subtracts exactly one; group names anchor at the START only. ⚠ Where deriving would mean re-writing the rule under test, assert the INVARIANT instead — the fold's literal became *every param the run sent is rendered somewhere on the panel* (`run-param-row`), which is stronger AND cannot rot |
| a **UI that was deliberately replaced** | `param-gates.spec.ts` (2) — the Costs section's five tickboxes and its typed Commission box became ONE switch on 2026-08-24, and the summary word `frictionless` went with them | **re-point to the rule that REPLACED it, do not delete.** The commission check now pins that the figure is stated off the broker account and that no typed box exists — which is why the old control was removed. ⚠ Deleting these as rot loses the evidence for the decision |

🔴 **A SEVENTH, AND IT IS NOT DRIFT AT ALL: A HELPER'S PRECONDITION CONTRADICTED THE TEST IT SET
UP.** `openEditor` asserted the dependent row was VISIBLE — fine for three checks, and the fourth
opens the editor in the one configuration where that row must be GONE (Custom = 1.0). It failed
inside the setup, so it read as a broken page rather than as a setup asserting the opposite of its
own subject. **A shared precondition may assert only what EVERY caller needs**; the positive
control belongs in the checks, beside the assertion it guards. ⚠ Moving it out is what makes those
checks honest anyway — an absent row and a row that was never drawn are the same DOM.

⚠ **The generalisation is the repo's own rule one level out: a test may depend on the world, but it
must not be able to fail SILENTLY-WRONGLY when the world moves.** Every one of these five failed
loudly enough to be seen and quietly enough to be read as a regression, which is the expensive half.

🔴 **AND A DEAD PIN IS NOT ALWAYS RE-POINTABLE.** `param-gates.spec.ts` named a run whose stated
requirement was *every param at its shipped default*; that run has left the lab and **no run in it
today can satisfy that sentence** — the closest differs in 11 places. So the four checks resolve a
run BY SHAPE now (completed python `sos_fade`, secondary OFF, a settled param still at its default,
rows in the groups the checks open) and refuse by name when the lab holds none. ⚠ **When a pin
dies, re-read what it was pinned FOR before naming a replacement** — a second literal buys the same
failure on a later date.

⚠ **`tsc --noEmit` DOES NOT COVER `tests/`.** A spec's syntax error typechecks clean and surfaces
only when Playwright loads the file. **`npx playwright test --list` is the parse check** — seconds,
every file, and where the count above comes from.

⚠ **The trade outcome chip's NAME still has no automated check, and that gap widened on 2026-08-08
when the naming rule gained an outcome dimension.** The chip is canvas-drawn with no DOM and its
inputs live inside `extendData`, so pinning it would mean contorting the product for the test. The
RULE is pinned backend-side (`test_candle_overlays.py`, mutation-proven); what is verified by hand
is that the browser renders it. Named here rather than skipped.

**`tests/chart-rebuild-fullscreen.spec.ts` (1, ~7s) — added 2026-08-08, WATCHED RED against HEAD.**
It asserts **Rebuild chart** is on the chart panel itself, in both the inline and the expanded view,
and that clicking it reaches the endpoint. ⚠ **Every locator is scoped to the panel's own root
(`[data-applied-lo]`) and has to be**: anything the HOST renders is outside that root, and in
fullscreen the host's chrome is still in the DOM behind the `position: fixed` overlay — covered, not
hidden — so a page-wide `getByRole` matches it and passes against the broken page. **Fourth instance
of that trap in this folder.** ⚠ **It also asserts a page-wide count of exactly ONE**, which is the
only assertion that says the button was MOVED rather than duplicated; without it, the tab strip's
copy could come back and the check would stay green. ⚠ **The refresh call is intercepted and
rewritten to the CACHED spec URL** — a genuine rebuild is a 7.6s engine replay, and the click only
has to prove it reaches the endpoint; the panel still gets a real payload, so nothing downstream is
mocked into a shape the server never sends.

**`tests/chart-rebuild-empty.spec.ts` (2, ~6s) — added 2026-08-25.** 🔴 **A recovery control must
not live inside the thing that failed.** Rebuild rode on the chart panel's tool strip, and that
panel only mounts once there are candles — so the one state where a reader needs the button was the
one state that hid it. Reported from the screen over a charged re-run whose chart came back empty:
*"there is no way to rebuild chart or anything."* Both the empty and the failed-to-load box now
carry their own copy. ⚠ **It does not clash with the page-wide count of ONE above** — the states
are mutually exclusive, and that assertion is what would catch it if they stopped being. ⚠ **Each
check asserts the STATE first and the button second**: an empty viewport and a withheld button are
otherwise indistinguishable, the trap this folder has now recorded five times. ⚠ **Mocked, so it
needs no bars and no terminal** — an empty spec cannot be produced on demand. Non-vacuity by
mutation: dropping the button from the box turns both red.

**`tests/candle-reversals.spec.ts` (9, ~57s) — added 2026-08-08 with the Candlestick Reversals
layer, and it also carries the Missed layer's two filters.** ⚠ **The 9th check is the only one here
with a clean fail-watch and it is the most valuable for that reason** — the cross-filter defect
existed at HEAD, so the check goes RED there naming the count that does not move (a reason chip
stuck at 179 while the layer draws 35). Every other check in the file pins a layer HEAD did not
have, where a red is just the element being absent. ⚠ **It asserts a chip's count falls to exactly
`0` rather than merely decreasing**, because 0 is the finding: no 3/3 miss can be missing its FVG,
since a 3/3 met all three confluences. ⚠ **And it asserts the chip is STILL VISIBLE at 0** — the
roster is deliberately built from every record while only the count is filtered, so a control never
disappears at the moment it reads zero. ⚠ **Its `RUN` and `DATE_WITH_A_MARK` constants are tied to real data and drift**: the layer
went 424 marks → 153 → **820** in one day as its anchor rule was corrected twice, and a date that had
a mark under one rule need not under the next. When a check here goes red, ask what the run actually
draws now before touching the assertion. It drives the REAL backend, because the marks come from a server-side engine replay over
the run's own candles and a mocked spec would be testing the mock. ⚠ **A fail-watch against HEAD is
vacuous for a layer that did not exist** — every check would go red on the element being absent,
which proves the locator and nothing else — so four are proven by MUTATION and the other is
non-vacuous by construction (it measures the same pixels off and on). **The fifth check pins that a
setting EXPLAINS ITSELF FROM THE ⓘ**, and it asserts both halves — the paragraph is gone from the row
AND the text is one hover away — because *checking only that the paragraph is gone would pass against
a panel that simply deleted the answer*, which is the same tidy-up with the content thrown out. 🔴 **Two of the four broke when
blocked setups stopped being anchors, and they broke CORRECTLY: they read the opening viewport, which
held a mark only while the run carried 424 of them.** At 153 the newest bars have none, and **an
empty viewport is pixel-identical to a layer that never draws** — so both now jump to a date that has
one. **A pixel check has to be pointed at something before it means anything.** ⚠ The label check
counts the mark's lighter EDGE colour, not the navy body: the body is drawn either way, so a
`navyPixels` assertion would pass against a mark with no tag. ⚠ **Check 6 (the Missed layer's SCORE
filter) lives here rather than in a Missed-layer spec because this is the only suite that drives that
dropdown, and it reads the layer's COUNT rather than pixels — a pixel check cannot tell 35 markers
from 179.** ⚠ **Its "every score starts shown" assertion is what makes it non-vacuous: without it a
mutation defaulting `2/3` hidden PASSED.** ⚠ The Chart settings gear is a TOGGLE —
a second click closes the panel — and closing it via `.getByRole('button').last()` inside the panel
picks up the fib editor's own delete buttons instead.

**`tests/chart-trade-labels.spec.ts` (3, ~17s) — added 2026-08-20 with the *Annotate trades*
setting.** ⚠ **A fail-watch against HEAD is VACUOUS for all three** — the setting did not exist, so a
red only proves the row is absent. **Every one is watched red by MUTATION, named in its own comment**;
the middle one is also non-vacuous BY CONSTRUCTION, measuring the same pixels three times (on → off →
on). ⚠ **The drawing is measured in PIXELS and the diff is computed IN THE PAGE**: a trade annotation
is painted into klinecharts' canvas with no element of its own, so a check reading the toggle would
be asserting the toggle — and a full frame is millions of bytes, so a copy is parked on `window` and
only the count of differing pixels crosses into Node. 🔴 **Its first version PASSED VACUOUSLY at a
diff of 0**: the chart opens at the right edge, so every marker is BEHIND the viewport centre and
`Next marker` is enabled with nothing to step to — **an empty viewport is pixel-identical to a
setting that removed everything.** It steps `Previous marker` and asserts the Step pill is PARKED
before it measures anything. ⚠ **The restore is asserted as ~1% of the change, not as byte
equality**, and the residue was MEASURED rather than tolerated — 127 pixels in one dashed column,
the Step focus line repainted under a rebuilt trade box.

**`tests/chart-paging.spec.ts` (2, ~45s) — added 2026-08-06 with the go-to-date progress readout,
both watched RED against `HEAD`.** ⚠ **It drives the REAL backend rather than intercepting the
candles route, which is the opposite call from `calendar.spec.ts` and is deliberate**: the thing
under test is that the readout tracks pages ACTUALLY LANDING, so a mocked feed would be measuring
the mock's cadence. It keeps the jump short (~1 year, 2 pages) so it costs ~45s instead of the 90s a
full-history jump takes. ⚠ **The second check nearly shipped vacuous** — the progress bar carries a
3% floor so it is visible from the first frame, and `> 0%` would therefore pass against a completely
dead progress value; it asserts the width GROWS. Full detail: `ChartPanel/CLAUDE.md`.

**`tests/strategies.spec.ts` (11, ~38s) — added 2026-08-06 with the Strategies audit.** ⚠ **This is
the one suite in this folder with NO clean fail-watch, and the reason is recorded rather than
glossed**: the endpoints it covers changed shape (bare list → envelope) in the same pass, so the
page at `HEAD` fails against the new backend for reasons unrelated to any defect. Non-vacuity came
from **mutation** — remove a fix, confirm the test goes red — and that is what exposed a test of
mine that passed with the guard it named deleted. Full detail: *The Strategies page* above.

**`tests/stress.spec.ts` (11, ~44s) — added 2026-08-05 with the Stress Tests audit, and every one
of the 11 was watched to fail against the page at `HEAD`.** ⚠ **Two locator traps live here, and
both fail by PASSING**, which is the only kind worth writing down: `page.locator('svg').first()`
resolves to the **sidebar logo**, so a page-wide assertion that some element is absent passes on
the broken page too (the fan's no-limit-line check proved nothing until it was scoped to the fan's
own container); and a chart label exists three times over — the KPI card, the chart `<tspan>`, and
Recharts' hidden `#recharts_measurement_span` — so a bare `getByText` is a strict-mode violation
rather than a miss. Scope to `locator('tspan', { hasText })`. ⚠ Like the calendar's, this suite
intercepts one endpoint whole, so **it needs no live VPS** — only the backend and the dev server.

**`tests/tuning.spec.ts` (8, ~19s) — added 2026-08-05 with the Tuning workbench audit, and it was
WATCHED TO FAIL before it was kept.** Every one of the 8 fails against the page as it was at
`HEAD` and passes against the fix; a suite written after a fix and never run against the defect is
a description of the fix, not a test of it. Same mock discipline as the Overview's: the leaderboard
states that cannot be produced on demand — a grandchild, a sweep child wearing a tweak's
`source_run_id`, a 3-trade fluke at PF 99 — are built by MUTATING the real runs list and the real
run detail. ⚠ **Scope table locators to `.first()`**: the per-regime table further down that page is
also a `tbody` of rows whose second cell is a number, and an unscoped `td:nth-child(2)` silently
picks up three extra rows.

🔴 **Two of these tests broke on the DATA rather than on the code, and both were coupled to the lab
in a way a rendering test must not be (repaired 2026-08-06).** The Overview's disabled-job check
named `P&L Tracker` and `Reporter` — **the two scheduled jobs deleted on 2026-08-05** — so it was
asserting on a subject that no longer exists and failed for that reason rather than for the defect;
it now MUTATES the snapshot to force one job `DISABLED` and one `STOPPED`, so the rule survives the
fleet changing shape. The Stress Tests `not graded` check was a bare substring match that also
caught the reasons panel's heading and the reason line; it passed only while the lab held one row
whose reasons were empty, and became a strict-mode violation the moment a real ungraded row carried
them — `{ exact: true }` now scopes it to the badge. **A test that asserts on which rows happen to
be in the database is a test that will fail on a day nothing is wrong**, and the failure is
indistinguishable from a regression until somebody reads it. Mock the state; never name the data.

⚠ **Every spec but the OFFLINE ones runs against the RUNNING app** (`./start.sh` first — backend
on `:8000`, dev server on `:5173`; the offline ones need nothing running, see *Offline specs*), and
`playwright.config.ts` deliberately has **no `webServer` block**. The backend here
talks to a live VPS and a live MT5 terminal, so a runner that boots it on demand is a runner that
can start things on the trading box. Starting it stays a person's decision — the same reasoning
`test_integration.py` is deselected under.

⚠ **`retries: 0`** — a retry that turns a real flake green is how a broken page ships. **Workers
are per PROJECT since 2026-09-10**: specs that read the real backend stay on ONE worker (they
share its state); OFFLINE specs run fully parallel. See *Offline specs* below.

### Offline specs — `tests/offline.ts`, recorded answers, a quick clock (2026-09-10)

`bots-version.spec.ts` and `bots-accounts.spec.ts` (6.1 min together → **~45 s** with the build)
run OFFLINE: `offlineTest('bots-page')` answers every `/api` read the spec does not route from
`tests/recordings/bots-page.json`, and ABORTS anything else — then fails the check naming it.
**The seven chart specs joined 2026-09-11** (`chart-sos-fade.json` / `chart-b-leg.json`). 🔴
**Before this, both read the real snapshot and health dots, which reach the live trading box on
every check** (an SSH round trip each), and inherited its STATE: on 2026-09-10 both bots moved to a
live account, which would have turned every demo-assuming check red on a day the page was fine.

- ⚠ **A spec STATES the state it needs** by mutating a copy from `recorded()` (e.g. `pinSnapshot`
  puts `sos_fade_demo` on a demo account) — never trusts what the box said the day it was recorded.
- ⚠ **Re-record by hand** with the app up: `node scripts/record-api.mjs tests/recordings/<f>.json
  [--add /path]`. GETs only; Telegram users are scrubbed. It is the ONE step that touches the box.
  ⚠ One answer per LINE, and `.prettierignore` names the folder — indenting a 4 MB chart spec
  doubled it. ⚠ **A spec reads its run id off the recording** (`recordedRun()`), never types one.
- ⚠ **The drill-down's finer bars are a RECORDED FEED** — two wide windows cut to each request;
  one outside them FAILS naming the window. Move `DATE` in `chart-drilldown.spec.ts`, re-record them.
- ⚠ **The recording's SHAPE is checked on every backend run** —
  `backend/tests/test_api_recordings.py` validates each answer against its route's response model,
  so a renamed field goes red there, not as a confusing browser failure. Re-record when it does.
- ⚠ **`playwright.config.ts` DISCOVERS offline specs** (a file calling `offlineTest(`) and gives
  them their own `fullyParallel` project; every other spec keeps `workers: 1`. Never list them.
- ⚠ **`clockFactor: 10` runs the page's clock ten times faster** — every poll still fires, in
  order, just sooner. Route handlers run in Node on the REAL clock, so a mock that times something
  keeps real milliseconds. 🔴 **It exposed a latent race**: a mid-deploy check passed only because
  a one-second poll was slower than its assertions; it now holds the job (`holdAt`).
- 🔴 **The APP is a development BUILD read off disk, not the dev server (2026-09-11).** Six workers
  pulling hundreds of modules each from ONE dev server made it the bottleneck: a check took 1.3s on
  one worker and 5.1s on six (a lone page load differs by only 0.2s — the cost was crowding). The
  `offline-app` step builds this checkout once per run (~11s) into a folder only that run reads,
  and pages load it at `https://app.test`, which nothing on the network answers. MEASURED back to
  back, 93 checks: dev server 90s → build 48s → build without traces 32s (+ the build). Three
  alternating pairs under a load average of 200–540 from another session: 91–134s → 52–65s with
  the build, and only a dev-server run timed out (3 checks). `tests/offlineApp.ts`.
- ⚠ **Development, never production, and the build REFUSES otherwise** — production React drops
  StrictMode's double-run, and the app only ever runs in development. It also refuses a stylesheet
  without the app's classes: Tailwind reads its config from the WORKING folder, and from anywhere
  else it emitted 13 KB instead of 70 KB with only a warning. Both refusals watched red.
- ⚠ **https, not http** — clipboard exists only on a secure origin, and the Bots page copies logs.
- ⚠ **No trace on offline checks** — recording one cost a third of every green run's CPU. They
  replay recordings, so a failure repeats: `npx playwright test <spec> -g '<name>' --trace on`.
- ✅ **Both test tiers run them (2026-09-11)** — step 19 of `scripts/run_all_tests.sh`, and
  `scripts/test.sh` ONE SPEC AT A TIME: only the specs whose page an edit can reach, so a Bots
  edit never pays for the chart specs. Selection: root `CLAUDE.md`.
- ⚠ The old write backstop (`refuseLiveWrites`) is DROPPED from offline specs: it aborted an
  unrouted write before the harness could flag it. Specs on the real backend keep it —
  `overview.spec.ts` gained it 2026-09-10 (the page carries the fleet controls).

⚠ **Mocks MUTATE THE REAL SNAPSHOT rather than hand-writing a fixture** (`mockSnapshot`). A
hand-written fixture drifts from the backend's model and then pins a shape the server never sends
— which is a test that passes while the page is broken.

**Two things were verified by hand and are deliberately NOT committed as tests:**

- 🔴 **The Smart Money render, which needs `FEATURES.smartMoney` flipped ON.** The one-off check
  did that by REWRITING `lib/features.ts`, and **a committed test that edits a source file is a
  hazard, not a test** — a crash mid-run leaves the flag on and Smart Money silently returns to
  the nav. It was run manually (both grids take their 4 / 3 columns, `relativeTime` reads
  `65d ago`, no console errors); re-run it by hand after touching anything that branch calls.
  ⚠ **The general point: a flagged-off branch is exactly the code a compiler blesses and nobody
  renders** — `relativeTime` gained an argument that only that branch passes, and a typecheck is
  not a render.
- **The 1s ticker's cost**, measured through CDP `Performance.getMetrics`: **44ms of scripting per
  10s wall clock (0.44%)** against a 1ms baseline on `/rulesets`, layout and style both 0ms.
  A one-off measurement, not a threshold worth asserting on every run.

⚠ **Two API facts the suite had to learn the hard way, and both will mislead the next test:**
`main.tsx` sets a global **`staleTime: 30_000`**, so navigating away and back does NOT re-fetch
inside 30s (measured: the mocked route was hit exactly once), and **`page.goto` is a full page
load** that destroys the query cache entirely. Any test about *stale data still on screen* must
therefore wait out the real poll — which is why one test is 65s and says so.
