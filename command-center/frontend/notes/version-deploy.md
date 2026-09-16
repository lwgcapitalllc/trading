# Notes — Version banner, fleet strip and strategy deployment

How the version-behind banner, the fleet strip and the deployment manager work, and the defects found in each. Moved VERBATIM out of `command-center/frontend/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## The version banner — "am I behind, and by how much" (2026-08-07)

`VersionBanner` in `pages/Bots/ConfigureTab.tsx`, first and full width on the detail panel.

### ONE button, ONE progress readout (2026-09-10) — read this before the history below

Aaron: *"a static disabled button doesn't catch my focus"* and *"I am only acting on one CTA and
there is only 1 progress indicator."* 🔴 **The preview → confirm two-step is GONE; the paragraphs
below that describe it (the second button, `awaitingConfirm`, `result.kind`) are history.** One
click on `Deploy & restart vX → vY` starts `POST /bots/{bot}/promote/job`, and
`components/StepProgress.tsx` draws the steps directly under the heading: Pull code → Build &
check → Stop bot → Start bot → Running vY.

- ⚠ **Dropping the preview is not dropping a check.** What the reader decides on (settings that
  would change, code changes) is on the banner BEFORE the click; the checks the dry run ran are the
  ones `promote.py` runs before it swaps anything, refusing with the bot untouched — they are now the
  first two steps.
- ⚠ **A bot on a LIVE account takes a second click on the SAME button** — it re-labels itself and
  disarms after 6s. One place to act; one extra deliberate press where the money is real.
- 🔴 **Steps come from the backend job, never a timer.** A step's bar is full or empty; the active
  one carries a travelling band (`animate-step-sweep`, in `index.css` so it hot-reloads). The last
  step is a MEASUREMENT (the restarted bot reporting the deployed code); `unconfirmed` renders
  amber, never green. ⚠ **ONE spinner, on the heading** — the active step's icon is a still dot,
  because its band already moves (Aaron: *"I don't need a spinner and a progress bar"*).
- 🔴 **The PAGE watches every bot's job (`usePromoteJobs`) and hands it to the panel (2026-09-10).**
  It was polled from inside the drawer, so closing it mid-deploy stopped the watch: the row said
  *behind* through the whole deploy and nobody saw the finish until a reopen. ⚠ Keep ONE watcher —
  each observer runs its own 1s timer. A reopened drawer still adopts a running job (render-time line).
- 🔴 **A finish is HELD as running until the version is re-read** — the watcher awaits that re-read,
  so the job and the version change on one render everywhere; without it the row flashed *behind*
  for one SSH round trip. It replaced the panel's own `isFetching` guard, which no check could reach.
- ⚠ **The row's pill reads `Deploying vN`** while a job runs, winning over its other states.
- ⚠ **The button names the version a promote can REACH** (`deployable`), never the backtester's.
- 🔴 **Behind ONLY by unpushed commits is its own state** (`deployWouldAdvance` in `lib/botVersion.ts`,
  read by the panel AND the pill). The panel offered *Deploy & restart v218 → v218* straight after a
  deploy that worked. Now no big button and no *would change* list; the heading says *has everything
  that is pushed*, a note names what to push, and the pill reads `vN · not pushed`.
- ⚠ **A failure's caption is `job.error` verbatim when present** — it says what state the step it
  hit left the bot in. Without one the build REFUSED, which touches nothing. Never read promote.py's
  prose to decide.
- `usePreviewPromote` / `usePromoteBot` were deleted with no consumer left. The endpoints stay: the
  trading-box MCP calls them.
- ✅ `tests/bots-version.spec.ts` → 27 checks; the deploy ones run a scripted job that advances one
  step per poll, behind `refuseLiveWrites`. **20 mutations run, 20 killed.** ⚠ Only
  `sos_fade_demo` has a scripted job — the page watches every bot, so a shared script puts every
  row mid-deploy. ⚠ A flash lasting one round trip is caught by RECORDING the row pill's states
  (`recordPillStates`); reading it once can land either side of it and pass. ⚠ The first full run had
  4 failures that did not reproduce in 55 later runs — concurrent backend reloads suspected, not
  confirmed. 🔴 **A check about the panel MID-deploy must HOLD the job on a step (`holdAt`)** — the
  spinner check first raced a job advancing every second and went red on the wrong line under its
  mutation: the deploy had finished, so neither spinner was on screen and the real assertion passed
  for free.

🔴 **The version row on `DeployCard` read `v0`, and it always would have** —
`strategy_version` defaulted to 0 in `algos/live/live_config.py` and nothing wrote it. (Fixed at
the source 2026-08-14: `promote.py` stamps a real count, and the field is `number | null` here
with `null` meaning a deployment made before the stamp. **The banner still renders `compare`**,
which can answer for such a deployment and is the only side that knows what the BACKTESTER is on.) So the one
question the Configure tab exists to answer had no answer on it. Aaron said so directly: *"If you
make me look at commit IDs or parameters from code from a configuration, like exec_time_stop_mode,
I don't know what any of that means. I just wanna know what is the version that I have compiled in
my backtester versus the version that is deployed... and if I'm behind, there should be a big nice
button."*

The banner reads `compare` off the version endpoint (derivation and why not the lab's own registry:
`../backend/CLAUDE.md` → *A bot's VERSION*). Live it renders **"SOS Fade is 21 versions behind
· Deployed v100 · 2026-08-05 · Backtester v121"** over the settings that would move, with
`Deploy v100 → v121`.

⚠ **It is the ONLY promote entry point on the page.** `DeployCard` carried its own until this
landed, and two controls firing one destructive action is two places for the confirmation copy, the
disabled state and the preview gate to drift apart — on the single control that changes what a live
account trades. `DeployCard` is now purely the detail (hash, commit, files) and says where the
button went.

⚠ **`comparable` false renders the `reason` and NO BUTTON.** Never promoted, commit not fetched, no
git — each is an ordinary state with its own fix and none of them is "press deploy". Rendering `0`
there would say *up to date*, which is the most reassuring answer available and the one most likely
to be wrong. Same rule as `mt5_link` and `DrawdownMeter`'s unmeasured tail.

⚠ **A PINNED setting is listed separately, not filtered out.** *This changed in the repo and your
bot is holding it still* is the reassuring half of the same question, and dropping it leaves the
reader unable to tell "not affected" from "not checked". It is also the one the promote preview
does not report.

⚠ **A new setting reads `not in v100`, never `Off → On`.** The deployed version had no such lever
at all, and "Off" is the lie in the safe-looking direction. `is_new` carries it; the backend sends
`was: ""` rather than wording it.

⚠ **The wording of every setting row is the STRATEGY's own**, from its meta file, with the full
`desc` on the row's `title`. A name→sentence map written here would be a second claim about what a
setting does.

⚠ **Uncommitted edits in the bot's trees are called out**, because the backtester runs the WORKING
TREE while a version describes a commit — and `promote.py` refuses a dirty tree, so this is also
the explanation for that refusal before you hit it. It caught a real one on the first render.

⚠ **The 21 code changes are behind a disclosure, and the settings are not.** The settings are what
CHANGES ON THIS BOT; the commit list is context. Putting them at the same level is what made the
old card read like a git log.

🔴 **A FINISHED DEPLOY RENDERED AS A PENDING ONE, and Aaron hit it the first time he used this.**
The output panel held a bare `output: string`, so a completed promote printed under the PREVIEW's
own caption — *"Checked the code on the VPS — nothing deployed yet"* — with **Deploy & restart**
still sitting beneath it. He pressed it, it worked, and the page gave him no way to tell:
*"confused what to do I click deploy and restart."* ✅ The deploy really had landed — the ledger
shows `shutdown exit_code 0 · reason "stop requested"` at 18:36:12 and `startup hash 556bf70c18b7 ·
previous_run_clean: true` eleven seconds later.

**`result` now carries `kind: 'preview' | 'deploy'` plus `ok` and `restarted`**, and the panel
branches on it: a deploy gets a green *"Deployed — SOS Fade restarted and is running v121"*,
the button is **withdrawn**, and Cancel becomes Close. ⚠ **The text alone cannot carry this** —
`promote.py`'s own output reads much the same either way, and the one line that distinguishes them
(`dry run — nothing was deployed`) is at the bottom of a scrolling `<pre>`. **A panel that shows a
result has to say which ACTION produced it.**

⚠ **`restarted` is rendered, not assumed.** `ok && !restarted` means the snapshot is on disk and
the OLD code is still trading — the most misleading state this page can be in — so it says *restart
it to pick this up* rather than claiming the new version is live. And a FAILED deploy says the bot
is **untouched and still on v100**, because a promote that fails leaves the running bot exactly as
it was; claiming otherwise sends somebody to debug a bot that is fine.

### A version the box would not give reads UNREAD — never a toast (2026-09-11)

🔴 **Every Bots-page load toasted a 500 per bot, twice with the retry.** Each version read is one
SSH round trip per bot, and a crowded box refused a third of connections (backend CLAUDE.md →
*The box refuses SSH*). The backend now retries that refusal and answers 502 when it cannot. On
this side the reads are `silent` with `retry: false`, and the failure has a state of its own.

- The pill reads **Unread** (`data-state="unread"`, reason on its title). The banner reads
  **Could not read the version** with the server's reason and **Try again**, and offers no deploy,
  because a deploy would go to the same box that just did not answer.
- ⚠ **Never "No version" / "Version unknown".** Those are ANSWERS (never deployed, the commit not
  fetched here); this is *could not ask*. That is rule 1.
- ⚠ **Only while there is no earlier reading.** A failed REFETCH keeps the last good version on
  screen, which is still true.
- ⚠ `versionReadFailure` (`lib/botVersion.ts`) is the ONE reading of the failure, for the pill and
  the banner alike.
- ⚠ **The spec COUNTS toasts as they appear** (a MutationObserver). At the offline clock a toast
  lives ~0.4s, so a count taken at the end could miss one that came and went.

Tests: 1 check in `bots-version.spec.ts`; 3 mutations run in a throwaway worktree, 3 killed.

### The accordion that would not close, and the deploy that landed short (2026-08-14)

⚠ **History: the two-button flow this describes was replaced on 2026-09-10** — see *ONE button,
ONE progress readout* above. The unpushed-commits rule below is still live.

🔴 **A SUCCESSFUL deploy left the panel in its PRE-DEPLOY shape under a green success line** — the
promote's `<pre>` held the block open at full height and the "N settings would change" section still
described the state before the deploy. A success now collapses to the green line with the output
behind a **Show output** toggle; a **preview** and a **FAILED** deploy keep theirs open unasked,
because that text is what you read before deciding and the only place a failure's reason lives.

🔴 **And the Deploy button stayed live across the refetch** — for that request every number on the
banner still described the state before the deploy. ⚠ Superseded 2026-09-10: the page's watcher
holds the finish until the re-read lands (see *ONE button*), and that hold has a check.

🔴 **THE SAME BUTTON WAS ALSO LIVE OVER ITS OWN PREVIEW, and that half was reported separately the
same day:** *"I click deploy and then it expanded to show me all the things that it will commit. But
the deploy button is still there. I click it. It just keeps repeating the process over and over."*
Pressing it re-ran the dry run and re-rendered an identical panel, which is **pixel-identical to a
dead button** — so the reader's reasonable next move is to press it again. It is disabled while a
preview is on screen (`awaitingConfirm`), leaving **exactly one live control**: `Deploy & restart`
below. ⚠ **Disabling was not enough on its own** — a greyed button still labelled `Deploy v164 →
v167` reads as BROKEN rather than as done-its-part, so the label becomes `checked — confirm below`
and names where the action went. ⚠ **`Cancel` hands it back** rather than the gate being one-shot:
the repo can move while you are reading the preview. ⚠ **It is a separate flag from `busy`, not an
addition to it** — `busy` also disables the confirm button, so folding it in would disable BOTH and
leave no way to deploy at all.

🔴 **The success line named `local_version` — what the reader ASKED for, not what landed.** MEASURED:
it read *"running v165"* over a bot running **v164**. It is `deployed_version` now, and is withheld
until the refetch answers — **a version quoted from the pre-deploy payload is a claim about the thing
that just changed.**

🔴 **`unpushed_commits` is why that deploy landed short, and the page could not say it. A promote
PULLS on the VPS, so the ceiling is the REMOTE, never this laptop's HEAD** — an unpushed commit is
unreachable however many times Deploy is pressed, and every number on the banner stays correct while
the button looks broken. It names the count and the version a promote can actually reach, beside the
uncommitted-files line it is the outward twin of. ⚠ **`null` = no upstream to ask, `[]` = measured
and all pushed** — both silent here, and collapsing them upstream is what makes the answer wrong.

⚠ **The `/version` mock must ANSWER DIFFERENTLY AFTER A PROMOTE or three checks are vacuous** — a
route frozen at `deployed_version: 100` leaves the page reading "21 versions behind" after a deploy,
indistinguishable from the defect. `landsAt` is what pins a deploy that deliberately falls short.

🔴 **And the mutation harness silently no-opped TWICE: restoring the file and applying the next
mutation IN THE SAME SHELL CALL left Vite serving the previous module**, so two mutations read as
*did not bite* against plainly mutated source. **The `__pycache__` trap from `backend/CLAUDE.md`,
arriving in the dev server.** Every step asserts the replacement APPLIED and runs in its own call —
**a mutation that silently no-ops looks exactly like a test doing its job.**

✅ **`tests/bots-version.spec.ts` — 17 checks, and they need NO BACKEND and no VPS** (the real
`/version` route SSHes to the live trading box and `/promote` deploys onto it, so both are
intercepted whole — the `calendar.spec.ts` shape, and it matters more here than anywhere).
⚠ **A fail-watch against HEAD is VACUOUS** — the banner did not exist, so every check would go red
because the element is absent, proving the locator and nothing else. **Non-vacuity is by MUTATION,
named in a comment on each check**; collapsing `result.kind` back to a string turns the three
deploy-state checks red together.

🔴 **Two of the ten were VACUOUS on the first run and this file's own trap caught them: the
Risk-per-trade card carries its OWN `Deploy` button**, so a page-wide *"no deploy button"*
assertion passes against a broken banner. That is the third instance recorded here
(`svg.first()` was the sidebar logo; a page-wide Retry matched the page header's own).
`data-testid="version-banner"` is a declared test seam and **every assertion is scoped to it**.

#### The confirmation says one thing, and the dirty-file line said a FALSE one (2026-08-14)

Aaron, on the v168 promote: *"this confirmation looks complicated."* Two separate faults stacked
under one green tick.

🔴 **The dirty-file warning claimed a refusal that cannot happen, and a promote had just
disproved it six inches above.** It read *"a promote refuses a dirty tree — commit or revert
first"* over a deploy of v168 that succeeded with **54 files edited here**. The two dirty checks
run on DIFFERENT MACHINES: `promote.py::dirty_paths` runs on the VPS and measures the VPS's own
checkout, while `compare().uncommitted_files` measures THIS laptop. A local edit cannot block a
promote and never could. It now says what is true — those files are not in v168, so a lab run
here is not testing what the bot has, and committing and pushing is how they reach it.
⚠ **This is `unpushed_commits` from the other end**: there the page understated what a promote
could reach, here it invented a reason one would be refused. **Both come from reading a fact
measured on one machine as though it described the other.** ⚠ **The VPS-side dirty state — the
one that really does refuse — is still not measured anywhere on this page.**

🔴 **And the success line restated the header.** *"Deployed — SOS Fade restarted and is
running v168"* sat directly under *"SOS Fade is up to date · Deployed v168 · Backtester
v168"*, with the bot's name in the page title above both: the version three times, the name
three times, under two green ticks. It is **`Deployed and restarted`** now. ⚠ **A FAILURE stays
explicit** (`Deploy failed — <bot> is untouched and still on v164`) and the asymmetry is the
point: after a success the header has re-read the version and agrees, while after a failure the
banner still describes the state BEFORE the attempt, so the line must carry the version itself.
⚠ **The *restart it to pick it up* branch also stays explicit** — nothing in the header says the
running process is older than the snapshot on disk.

⚠ **`the success line names the version that LANDED` MOVED rather than went.** Its subject was a
string that no longer exists, and the rule it guards is live — a deploy that could not reach HEAD
must never be described as having landed there — so it asserts the HEADER now, where that fact
went. **Re-mutated to confirm it still bites**: rendering `local_version` as the deployed version
turns it red.

## The fleet strip re-reads itself, and its labels are about the BOT (2026-08-28)

🔴 **A DEPLOYMENT BADGE THAT NEVER RE-READS IS A BADGE THAT LIES.** Both version hooks had
`staleTime: 30_000` and **no `refetchInterval`**, so the only refetch a promote caused was the one
`usePromoteBot` fires when the HTTP call returns — while the bot it just asked to stop takes tens of
seconds to go, come back and stamp its new hash. **That refetch lands mid-restart, reads the OLD
running hash, and nothing asks again.** ✅ MEASURED: the strip read `1 restart pending` over a bot
whose deployment record and running hash agreed exactly. Numbers, timings and the fail-watch:
`../docs/FRONTEND_BUILD_NOTES.md` → *The fleet strip's badge that never re-read*.

✅ **Poll on the ANSWER, never on the action** (`versionPoll`): pending ⇒ 15s, settled ⇒ no poll.
⚠ **"Poll for a while after a promote" was rejected** — it covers only the restarts THIS page
started, so a CLI restart, a crash-loop or somebody else's promote goes on lying. Reading the flag
off the data watches every cause and stops itself when the hashes agree. ⚠ **15s, not the 3s a lab
run gets: this endpoint is one SSH round trip PER BOT — MEASURED 4.5s — and it multiplies by the
fleet.** ⚠ **An idle page that has never SEEN a pending restart is covered by the global 30s
`staleTime` + refetch-on-focus, not by a baseline poll** — nothing polls for a state it has not
seen, and that is the deliberate limit.

🔴 **`isRestartPending` lives in `lib/botVersion.ts` because TWO layers need it** — the badge draws
it, the hook polls on it. A private copy in either lets the page poll for a condition it no longer
draws, or draw one it never polls for.

⚠ **The strip SAYS when it is re-reading** (`re-checking…`, off `isFetching`, distinct from
`loading`'s first read). A page that refreshes silently gives the reader no way to tell a live
number from a frozen one — the defect above, wearing a fix.

🔴 **`not frozen` → `never deployed`.** "Frozen" names the MECHANISM (a promoted bot runs a frozen
snapshot) and says nothing about the bot — Aaron, reading `1 not frozen`: *"idk what that even
means"*. What is true is that nobody ever deployed it, so it has no pinned version and runs whatever
the repo holds when it starts. **The DeployCard's warning changed in the same commit**, or the strip
explains a word the card it sends you to no longer uses.

🔴 **A non-zero count is a BUTTON that selects the bot it counts, and its tooltip NAMES them.** A
condition plus a number left *which bot?* answerable only by clicking every rail row — and the
sentence explaining the condition lives on the card you reach by doing that. ⚠ **The number is
`bots.length` of the list behind it**, so the figure and the bot it navigates to cannot come apart.
⚠ **Zero stays a `<span>`** — a button that navigates nowhere reads as broken.

✅ **`tests/bots-version.spec.ts` (17 → 20), scoped to a new `fleet-strip` seam** — "restart pending"
and "behind repo" also appear in the DeployCard's warnings, so a page-wide locator matches a card
that is not the strip and passes against a broken one. 🔴 **The polling check is the one test in
that file with a CLEAN fail-watch** (WATCHED RED with the fleet hook's `refetchInterval` removed).
⚠ **It asserts the TRANSITION, never a number**, so the registry's SIZE cannot break it. 🔴 **Its
mock's clock starts at the FIRST REQUEST, not at route registration** — anchored at registration it
spends the page's whole boot, answers SETTLED on the first read, and fails on its opening assertion
having proved nothing. **A fixture that measures from a moment the subject has not reached yet is a
fixture testing its own timing.**

## Strategy deployment manager

The "Deployed" sub-tab (`FilesTab`) has a drag/drop zone (`.cs`/`.mq5`), a file list sorted by platform then filename, trash-can delete, and overwrite/delete confirm modals. "Compile NT8" (`useTriggerCompile`) and "Compile MT5" (purple, only when MT5 files present; `useTriggerCompileMt5`) both open the generic `CompileModal` (props: `title` + `usePollHook`). The modal has a status-icon header (`StatusIcon`: spinner / green check / red X) + one-line summary, a body capped at `max-h-[85vh]` that scrolls, and a pinned footer. While running it shows staggered pulse **skeleton rows** (no second spinner) shaped like the result rows that replace them. On completion it renders the real `job.errors` / `job.warnings` **text** — not just counts — via `CompileSection` (color-coded, numbered, monospace lines: red `neg` for errors, amber `warn` for warnings); warnings show even on a successful compile. The elapsed counter ticks every second from a **local `setInterval`** (anchored to `started_at`, freezing at `completed_at` when done) — without it the count only advanced on each poll and visibly jumped. Strategy-file hooks live in `useLab.ts`: `useStrategyFiles`, `useStrategyFileSyncStatus`, `useUploadStrategyFile` (native `fetch()` + `FormData`, not `api.post`), `useDeleteStrategyFile`, `useTriggerCompile`, `useCompileStatus`, `useTriggerCompileMt5`, `useCompileStatusMt5`, `useDeployStrategy`. `useParamTypes(strategyId)` calls `GET /strategies/{id}/param-types` → `Record<string, 'int' | 'double'>` with `staleTime: Infinity`; used by `OptimizerModal` to validate int-param ranges; disabled when `strategyId` is null. Types: `StrategyFile` (+ `platform`), `StrategyFileSyncStatus`, `CompileJobStatus`, `DeployJobStatus`; `ScanResult` carries `orphans: string[]` (DB strategies whose source file is gone) + `warnings: string[]`; `ReconcileResult` carries `removed: string[]` + `warnings: string[]`. **Since 2026-08-06 both file endpoints return an ENVELOPE, not a bare list** — `StrategyFilesResponse { files, nt8_error, mt5_error }` and `StrategyFileSyncResponse { statuses, nt8_error, mt5_error }` — so one unreachable agent degrades the other platform's rows instead of 502-ing the whole call, and the page can say WHICH agent is down. The modal now has a header X and an Escape handler (the footer Close renders only on completion, so a hung poll had no way out) and reads `isError`, so a failed status poll ends the spinner.

**Scan vs Reconcile (bidirectional delete).** Scan is read-only: `useScanStrategies` (`POST /strategies/scan`) adds/updates and its success toast flags the orphan count (`N orphaned (source deleted — use Reconcile)`). Deleting a source file from the repo propagates to the DB row + the deployed VPS file ONLY through an explicit action: `useReconcileStrategies` (`POST /strategies/reconcile`). On the `Strategies.tsx` header, a red **Reconcile (N)** button appears next to Scan whenever any strategy row carries **`is_orphan`** — ⚠ **not `scan.data?.orphans`, which is MUTATION state**: gated on that, an orphan was invisible on a fresh page load and stayed invisible until somebody happened to press Scan (fixed 2026-08-06). It is fronted by the shared `ConfirmDeleteModal` (imported from `pages/Backtests`) listing exactly which strategies will be removed. On success it invalidates `['lab','strategies']` + the strategy-files / sync-status keys, and surfaces any per-strategy VPS-delete warnings as error toasts. The per-strategy Delete button uses the same backend `remove_strategy` path. See backend CLAUDE.md "Bidirectional delete (reconcile)".

Each row in `StrategiesTab` has a Deploy/Compile/Run action driven by the **content-aware** `StrategyFileSyncStatus` (`needs_deploy` / `needs_compile`, not the old presence-only `in_sync`). `StrategyRow` takes the full `sync` object (via `syncByStrategy[s.id]`), and the Status cell shows a version chip `v{current_version}` next to the state pill. **The pill is ONE ordered-exclusive chain and must stay one** (2026-08-06): amber **Needs deploy** → red **Missing on VPS** (`file_exists_on_vps === false`, previously returned by the backend and rendered by nothing, so a file deleted off the box read green) → amber **Needs compile** → grey **VPS unknown** (`file_exists_on_vps == null`, i.e. the agent could not be asked) → green **In sync**. ⚠ **The first attempt at this added *Missing on VPS* as a chip BESIDE the hash-derived pill, so a row rendered green *In sync* next to red *Missing on VPS*** — the exact contradiction the fix existed to remove, one line lower, caught by a browser check and not by reading the diff. The action mirrors the pill (`Deploy` / `Redeploy` / `Compile` / `Run`), and **the whole action cell is gated on `isPython || sync !== undefined`** — with sync-status down every row lost its `sync` object and fell through to Run, so a strategy that needed deploying offered to run. ⚠ **`liveVer` is `sync.compiled_version`, full stop** — it used to fall back to `deployed_version` when `needs_compile`, which named the deployed source as what was running while NT8 and MT5 both execute the COMPILED artefact. `handleDeploy` tracks `deployingId` and on success invalidates `sync-status`. **First-run:** every strategy shows Needs deploy until deployed once through the tracked path (no deploy-hash recorded yet — see backend CLAUDE.md). `StrategyVersion` type + `GET /strategies/{id}/versions` expose the full version history if a per-strategy view wants it.

**"Needs scan" pill (2026-07-23).** Separate from the deploy/compile sync above — it reads `Strategy.needs_scan` (on the strategy row itself, not `StrategyFileSyncStatus`), which the backend computes live (source hash / meta mtime vs last scan). When true, `StrategyRow`'s Status cell shows a clickable amber **● Needs scan** pill (calls `onScan` → `useScanStrategies().mutate()`, spins while pending) ABOVE the deploy/compile pills. It renders for ALL runners, and for a Python strategy — which has no deploy/compile step, so its Status cell was otherwise empty — it's the only status pill. `RunBacktestModal` shows a matching amber banner when `strategy.needs_scan` ("Parameters may be out of date … click Scan Strategies, then reopen"): the panel form is built from the last-scanned schema, so editing a Python `config.py`/meta without re-scanning silently runs on the OLD params (the bug that ran sos_fade on stale divergence-armed defaults). This is the Python analog of the MT5/NT8 deploy/compile badges.

---

## The scheduled-job status gained an ARMED value (2026-08-21)

`JobStatus.status` now carries `ARMED` alongside `RUNNING` / `STOPPED` / `DISABLED` / `UNKNOWN`.
It is what the backend returns for a scheduled task that is enabled and waiting for its next
trigger — the normal state of a once-a-minute watchdog. Full story, and why the payload was wrong
while the page was right, in `command-center/backend/CLAUDE.md`.

⚠ **No component changed, and that is deliberate.** `ARMED` falls through the same else-branch
`STOPPED` did in both `JobDot` (Bots) and `JobPill` (Overview), onto the same gold *"waiting for
next trigger"* dot with the same tooltip — which was already the correct thing to show. `allJobsOk`
still counts only `RUNNING`, so the summary tile is unchanged too. **The type learned a value the
UI already handled correctly**; rendering armed differently from unrecognised is a separate decision
nobody has made.

---

## Never deployed is a PROBLEM, not a blank (2026-09-16)

🔴 **Two bots traded the trading box's own working tree for a day and every screen was calm about
it.** A bot with no frozen snapshot imports its code from the box's checkout, so a pull there
changes what it trades with nobody deploying anything — and it had already happened once, the
fingerprint moving between two boots. Both bots warned about it at every startup. Nobody reads a
log.

**What the page did.** The row's pill drew a dim grey *No version* — the SAME badge it draws when a
version simply cannot be worked out — and the panel drew the grey *Version unknown* box, which
offers no deploy button. So the one bot that most needed deploying was the one bot the page would
not deploy, with its own *Never deployed* warning sitting below, unreachable.

**Three things changed, and they all read one flag.**

- The pill has its own amber **Not deployed** state (`components/VersionPill.tsx`), ahead of the
  unknown branch. Order is now deploying → loading → unread → not deployed → unknown → behind →
  restart → not pushed → current.
- `versionNeed` (`lib/botVersion.ts`) returns it FIRST, before the comparable check, so the
  "needs you" line over the table counts it — the line and the pill can never disagree, which is
  the whole reason that function exists.
- The panel's unanswerable guard lets it FALL THROUGH to the real banner
  (`pages/Bots/ConfigureTab.tsx`), which now tolerates a missing deployed version: amber, a
  *Deploy & restart* button, and *Deployed **never*** rather than a `v0` for a deployment that does
  not exist.

⚠ **The flag is the deployment record's own `frozen`, never the comparison's `reason` wording.**
The box's answer to *does this bot have a snapshot* is the very thing the runner decides by; the
comparison only knows it has nothing to compare against, which is the calm state. Matching on a
sentence would make that sentence load-bearing — reword it and the warning silently stops.

⚠ **Three states, three looks, still.** *Unread* is the box not answering, *No version* is this
machine unable to count one, *Not deployed* is a bot trading unfrozen code. Only the last is amber.

Checks: `tests/bots-version.spec.ts` — the row's pill, the "needs you" line, and the panel's deploy
button, each with its mutation named and run red on 2026-09-16.

---

## A move onto an account DEPLOYS the bot, and the page has to notice (2026-09-16)

The server starts that deploy itself (`backend/notes/bots-deploys.md`), so no button was pressed
here and nothing on the page knows a job exists. `usePromoteJobs` stops polling the moment a bot's
job is not running — so without a nudge the row would sit on its last answer: no progress, no
version re-read when it landed, and the bot still drawn as never deployed.

- `BotAccountAssignResult.deploy_job` names the job the move started. `''` means none was started
  — benching, or one that could not start, whose reason arrives in `notes` as a warning. It never
  means one finished.
- The move's `onSuccess` invalidates that bot's promote-job and version reads when the field is
  set, which restarts the poll; the row's pill then draws the deploy like any other.
- The success toast says *deploying it now* only when a job was actually started. What was ASKED
  for, never what finished — the deploy runs in the background and a failed one warns separately.
