# Notes — Bot registries and lifecycle

Snapshot-vs-import naming, assignment param declarations, registering a bot across five registries, one-strategy-two-bots demo copies, extreme_leg_demo going live, and the de-branding leaving stale watchers. Moved VERBATIM out of `algos/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

### 🔴 A snapshot carries what the package IMPORTS, not what it is CALLED (2026-09-04)

**`repo_trees` copied ONE strategy directory, and a strategy package borrows from its siblings.**
`extreme_leg` takes one class from `sos_fade` and the shared live contract from a loose module
beside it; `b_leg` takes six things across three files; `sos_fade` itself takes `loss_recovery`.
None of it was copied, so **a snapshot for either benched bot could not import at all** — the
promote staged 137 files, ran its verify step, and failed on a missing module.

⚠ **Nothing caught it for as long as it existed, and the reason is the finding.** The only bot
anybody has ever promoted is `sos_fade`, whose one borrowing is a LAZY import inside a method
nothing on the live path calls — so every promote that has ever run was green, and the two bots
that would have failed had never been promoted. **Rule 9: a feature nobody has RUN is not a
feature**, and here the un-run feature was a deploy.

✅ **The strategy side of the list is now DERIVED** — `strategies/python/package_deps.py` walks
the imports and returns the closure, so a borrowing added tomorrow ships without anybody
remembering. ⚠ **A hand-kept list of extra trees per bot was the obvious fix and is the same
failure one level up**: a second statement of what the code already says, going stale in silence
the first time somebody adds an import.

⚠ **It REFUSES rather than answering partially** — an unparseable file or a package that does not
exist raises, and the promote stops. A partial closure stages a snapshot that does not import,
which is this defect exactly, except discovered later by a bot that will not start.

🔴 **THE FIRST RUN OF THE FIX STILL FAILED ON THE BOX, ONE LAYER ABOVE THE FIX.** The resolver,
the copier and the file list all handled a loose module; `main`'s preflight still asked
`src.is_dir()` and refused with *missing source tree* for a file sitting right there. **The
generalisation is worth more than the line: when a thing gains a second SHAPE, the audit is every
place that asks it a question, not the place that produces it.** The preflight asks `exists()`
now, and a test reads that block with its COMMENTS STRIPPED — the comment explaining the rule
names the call it forbids, so the first version of the test went red on its own prose, which this
repo has done once before on the `--no-verify` guard.

⚠ **`command-center/backend/services/bot_versions.trees_for` calls the SAME resolver.** What is
COPIED and what is COUNTED were previously kept in step by MIRRORING, and that is precisely how
both came to be wrong together — they matched each other perfectly while neither described the
code.

🔴 **THE LIVE BOT'S VERSION NUMBER MOVES BECAUSE OF THIS, and it is a correction rather than a
bug.** `loss_recovery` is now one of `sos_fade`'s counted trees, so commits touching it count
toward the version and the Configure tab may show the bot further behind than it did yesterday.
The old number was too small — the promoted-but-not-counted failure that file's own docstring
warns about.

🔴 **THE PIN DOES NOT COVER THE NEW FILES, AND THIS CHANGE WIDENED THAT GAP RATHER THAN CREATING
IT.** `LiveConfig.source_roots` still hashes exactly three roots — the strategy dir, `engines/`
and `backtest/` — so a borrowed package now SHIPS in the snapshot and is not hashed. Before, it
was neither shipped nor hashed; now a file the bot really loads can change under a green pin.
⚠ **The obvious fix breaks the running bot**: adding roots changes the hash (the root NAME is
folded in before the missing-directory check), so the live bot would refuse to start until it is
re-promoted. **The safe shape is for `deployed.json` to record the roots that were hashed and the
runner to hash those**, which is backward-compatible by construction. **Not built — a stated gap,
and it needs a promote in the same operation.**

**Promoting is `algos/tools/promote.py`** (stage → verify in a clean subprocess → activate, so a
failed promote leaves the running bot untouched) or the **Promote button on the Bots page →
Configure**, which previews before it deploys. `instances/*/deployed/` and `deployed.json` are
git-ignored: they are a per-machine build artefact, reproducible from `promoted_commit`, and
promoting happens ON the VPS, so committing them would collide with the next pull.

⚠ **The freeze covers the STRATEGY, not `algos/live/`.** The runner itself is repo code loaded at
process start, so a runner fix reaches a bot on `git pull` + restart with no promote — which is
correct (it is plumbing, not trading logic) and worth knowing when you change one.

**Phase:** No live bots. All four first-attempt bots were deleted 2026-06-22. The suite is being rebuilt backtest-first per the S.Y.S.T.E.M. method (`docs/BOT_DEVELOPMENT_METHOD.md`) — strategies are validated through the command-center backtest lab before any return to live demo trading. The reusable deployment infrastructure is preserved in `docs/BOT_DEPLOYMENT_INFRA.md`.

### 🔴 An assignment may only write a strategy param the receiving strategy DECLARES (2026-09-04)

**`runner._build_strategy` refuses to start on any `strategy_params` key the strategy's dataclass
does not declare** — a silently-ignored param is a bot trading a setting nobody chose. ✅ **That
refusal is correct and stays.** 🔴 **`bot_accounts.plan_assignment` writes `account_profile` off
the account registry into the receiving bot unconditionally, without asking whether that strategy
has the field** — so assigning `extreme_leg_demo` produced a bot that connected to the broker and
refused to start on every attempt.

🔴 **THE SHAPE: a write that is correct for every existing receiver is not a correct write.** Both
strategies that had ever been assigned declare that field, so the rule had a 100% pass rate right
up to the first one that did not, and nothing in the code was going to show it before a third
strategy existed. **Rule 7 pointed the other way — the WRITER made a claim about a receiver it
never read.**

⚠ **This one fails LOUDLY; the sibling trap in the same function does not.** A wrong symbol suffix
from the same assignment path gives a bot that runs, warms up and receives no bars. **A move
between accounts can break a bot in two directions and only one of them tells you.**

⚠ **Until the writer is fixed the field returns on the next assignment**, so
`instances/extreme_leg_demo/config.json` carries the warning at `_strategy_params`.

### One strategy, two bots — the demo copies (2026-09-11)

**`sos_fade_2` and `extreme_leg_2` are the DEMO copies of the two live bots**: same strategy, own
process, own instance folder, own deploy. Aaron's call, after weighing one signal sent to both
accounts: a copy can be moved onto a NEW version to trial it while live keeps the proven one, and
one signal cannot do that. **So the two are independent by design — a promote of one does not move
the other.** Settings were copied from the live bots on 2026-09-11 (the snapshot built from
`3483e40e`); why each setting holds its value stays in the LIVE bot's config, not repeated.

- ⚠ **Keyed by a number, not a place.** `sos_fade_demo` trades the LIVE account; a key naming its
  account goes stale the day the bot moves.
- 🔴 **The display name is the STRATEGY, and two copies SHARE it (2026-09-11, Aaron: *"it's a
  generic strategy, not a demo specific strategy"*).** They were "SOS Fade (demo)" for their first
  day, which would have gone on saying demo on real money the day one moved. What tells copies
  apart is the ACCOUNT, worked out per message: `bot_state.labelled` writes `SOS Fade · LIVE` /
  `· demo` off the registry's `kind` (plain name when it cannot say — never a guess), and a live
  account's trades and signals get their own channels (*The live rooms*, below). ⚠ The bridge
  named the bot by its KEY until then, so the live fills read `sos_fade_demo`; the key stays on MT5
  order comments and the restart record, which are identifiers. ⚠ The Command Center refuses a
  name two bots share (409) — pass the key. ⚠ Two copies on two accounts of the SAME kind would
  read alike; none exist, and the account number is the fix when one does.
- ⚠ **Magic = the original's + 10** (770125, 770127). Sharing would pass the per-account guard,
  but the originals traded the demo account under 770115/770117 until 2026-09-11 and a copy must
  not read those deals back as its own.
- 🔴 **Born BENCHED, and the order matters: register → promote on the box → assign.** The watchdog
  starts an assigned bot it finds down within a minute, and without a deployed snapshot that start
  fails every minute. Assigning from Bots → Accounts pulls the box, so the copy starts on the next
  watchdog pass.
- ⚠ **Compare the pair in R, never dollars** — the two balances are nothing alike (rule 6).

`bot_state.ALGOS_ROOT` is **derived from `__file__`**, not the literal `C:/trading/algos` it used to
be. The runner is dry-run-capable off the VPS, and a hardcoded Windows path made every state write
fail on a Mac while looking perfectly correct in the source.

Update this section when the phase changes or a new open question arises.

---

### `extreme_leg_demo` — LIVE ON AN ACCOUNT AND ARMED (2026-09-04; benched 2026-09-03, "cannot be a bot yet" before that)

🔴 **THIS HEADING SAID BENCHED FOR THREE DAYS AFTER THE BOT WAS ASSIGNED, RUNNING AND ARMED — inside
the very section whose lesson is that a stale blocker outlives the work that cleared it.** The
reader who accepted "benched" had no reason to look again, which is the failure named four
paragraphs down, arriving as a bill.

**It is on PU Prime demo account 700152905 at 5% per trade under a 10% account cap, promoted and
frozen, and it has been running since 2026-09-05.** Verified on the box 2026-09-07: link up, warm,
bars advancing, flat, not a dry run. ⚠ **It has taken NO trade yet** — see the Rule 9 paragraph
below, because armed and proven are different states and only one of them is true. ✅ **All five rows of the table this
section used to carry are now built** — the per-bar step, the commanded close, save/restore, the
fields the bridge reads directly, and the account-budget clamp at the sizing seam. `verify_live_ready`
returns nothing missing, and the last of them, a route that OPENS at market, is the section below.

⚠ **THE FIVE ❌ IN THIS SECTION WERE TRUE ON THE MORNING OF 2026-09-03 AND FALSE BY THE EVENING, AND
THE STALE VERSION READ AS A STANDING BLOCKER.** It said in as many words that adding an instance
directory *"would produce a bot that appears in the list, looks deployable, and cannot start"* —
which is exactly the sentence a reader acts on. **A doc that says a thing is impossible outlives the
work that made it possible, because nobody re-reads a blocker they have already accepted.**

🔴 **THE FRAME IS `M5` AND GETTING IT WRONG FAILS SILENTLY.** This strategy measures its trigger on
5-minute bars and builds its 15-minute half in code; on M15 the two collapse into one series and it
never fires — no error, no refusal code, no alert, indistinguishable from a quiet market. It is the
one field in that file that produces a bot which runs, logs cleanly and does nothing.

✅ **IT WAS LANDED ON 2026-09-04 AND THE ORDERING TRAP BELOW IS HOW.** `sos_fade_demo` went to
5% **FIRST**, then this bot was assigned at 5%. The Command Center refuses a write whose shares sum
past the account cap, so assigning first is refused: 10 + 5 > 10 — loudly, at the moment of
assignment, rather than later. ⚠ **THE SAME ORDERING APPLIES TO A THIRD BOT, AND THAT IS ALL IT IS — A CHOICE, NOT A
BLOCKER.** Two shares of 5 fill the 10% cap exactly, so a third at any positive risk sums past it
and the three take turns instead of sharing. Aaron's answer, 2026-09-07: *"I can lower individual
bots risk or just up the cap so no issue there."* Both are one write. 🔴 **AN EARLIER REVISION OF
THIS LINE SAID *decide what the cap becomes before assigning anything*, WHICH IS THIS SECTION'S OWN
FAILURE MODE ARRIVING FROM THE OTHER SIDE**: the paragraphs above exist because a doc called a
solved thing impossible, and a doc that calls a routine choice a blocker does the same damage a
week later. **State the mechanic; do not tell the owner to stop and decide.** ⚠ **The old warning here — do not move the sibling down before this bot
is ready — was ANSWERED, not retired**: an account holding 5% for a bot that is not trading earns
half its measured return for nothing, and the window between the two writes is the whole exposure.
Do them together.

⚠ **`warmup_bars` is 15,000 M5 bars (52 days), and the floor under it is MEASURED at 1,008.** Twelve
quarterly start dates, 34 reference trades, judging the 30 days after each: 1,008 bars and up
reproduce a 20,000-bar reference everywhere, 504 does not. It is set ~15× the floor because being
generous costs a few seconds at startup and being short is silent. 🔴 **The first version of that
probe fingerprinted a bar NUMBER, which is local to each run's start, so every run-up disagreed with
every other and it read exactly like an engine that never warms — and its first window held two
trades, which cannot separate warm from cold at all.** Compare run-ups on DECISIONS; never on bar
numbers, and never on dollar fields, because a longer run-up books more prior trades onto the
emulator's compounding balance and moves every size legitimately.

✅ **PROMOTED 2026-09-05** — frozen snapshot, `deployed.json` present, content hash
`8b966299…`, built from commit `28527db7`, strategy version 193. Verified on the box 2026-09-07.
🔴 **`strategy_source_hash` IN `config.json` IS EMPTY AND THAT IS NOT WHAT IT LOOKS LIKE — this
line read it as proof the bot was unpromoted for three days after the promote.** `promote.py` writes
the pin to `deployed.json`, a SEPARATE file that `live_config` overlays onto the config at load, so
the field in `config.json` stays empty on a perfectly pinned bot. **Read `deployed.json`, or ask the
box, before ever concluding a bot is unpinned.**

⚠ **Its parity gate covers 3.5 months and 7 entries and cannot cover its shipped form at all** — the
chart has no engine for the market-condition refusal that is switched ON in its params, so the gate
forces that off and compares the shared logic. **The shipped bot takes fewer trades than any green
gate has ever checked.** 🔴 **Rule 9 is NOT closed by this bot being live, and that distinction is
the whole point of the rule.** As of 2026-09-07 it is running, warm, linked and flat, and it has
taken **zero** trades — so nothing in this package has still been near a broker, and neither has the
bridge's market-entry path. **Running is not executed.** The live proving period in
`docs/EXTREME_LEG_BOT_PLAN.md` §4.3 is the only thing that closes that, and its first entry is the
event to watch.

⚠ **Magic `770117`**, one above `b_leg_demo`. Both guards that would police it — the magic clash and
the account-cap agreement — **exempt a benched bot**, so neither enforces anything today; the number
is chosen now so assignment is never blocked by it.

### 🔴 The de-brand left both silent watchers pointing at a bot that no longer exists (2026-09-04)

`SYS_REENTRYWATCH` and `SYS_BROKERCOSTS` are registered from `algos/scheduler/*.xml`, and both XMLs
still passed `--bot mpc_sos_fade_demo` after the rename. **`SCHEDULER_GUIDE.md`'s table was already
correct** — it listed both under the new key — so the page a person reads and the file that actually
registers the task disagreed, and only the table had been renamed. **That is rule 7 with the label
and its consumer one directory apart: the table is a CLAIM about the XML sitting beside it.**

🔴 **THE ROOT CAUSE IS AN EXTENSION LIST, AND IT IS THE THING TO CHECK ON THE NEXT RENAME.** The
sweep that did the de-brand walked 23 text extensions and `.xml` was not one of them, so a Windows
task definition was never opened. **A rename is only as complete as the file types its sweep can
see, and nothing about a clean run tells you which types it skipped** — the report counts what it
changed, never what it never looked at. ⚠ **`scripts/bootstrap_vps.ps1` would have reinstalled the
broken pair onto a rebuilt box**, so this survived a rebuild as well as a pull.

🔴 **The failure mode is the exact one this pair exists to prevent.** `watch_reentry.py` derives the
instance directory from the key it is handed, so the missing bot made it raise — and its health
record, *the evidence that it ran*, was written into a freshly created
`instances/mpc_sos_fade_demo/`. **So the real bot's health stream shows a GAP, which this file tells
you to read as "the watcher stopped", while the task itself reports success.** Both halves of the
*"the evidence is the record, never the quiet"* design were defeated by one stale string.

🔴 **The generalisation is worth more than the fix: a watcher that writes its liveness record to a
path derived from the thing it is watching cannot report that it is watching the wrong thing.** The
evidence and the subject have to be able to fail independently, or the record proves nothing on the
one occasion it matters.

⚠ **It was loud only by luck of WHICH call failed first.** The missing `config.json` raised, and the
top-level handler turned that into a Telegram message. **Had the lookup returned an empty ledger
instead, it would have graded zero re-entries and reported nothing — and a watcher that finds
nothing is byte-identical to a quiet month.** Rule 1, one refactor away.

✅ **It announced itself anyway, and that is the half that worked.** The error reached Telegram on
the 01:23 run. The 00:23 run had succeeded (2,789 rows) because the instance folder had not been
renamed yet, so the two records an hour apart are the whole story.

✅ Both XMLs fixed, both tasks re-registered from them and verified by reading back what Windows
holds, both watchers dry-run clean under the new key, and the phantom folder deleted. The 00:23
record — written before the rename and stamped with the old name — was left exactly as it was.

---

## A bot that was never deployed REFUSES to start (2026-09-16)

🔴 **This was a warning at every startup for months and nobody read it.** A bot with no snapshot of
its own imports from the repo working tree on the trading box, so a `git pull` there changes what it
trades with nobody deploying anything. Two bots ran that way for a day, and their code fingerprint
had already moved between two boots with nobody touching them.

It is now a refusal in the same shape as the version-pin and missing-channel ones: CRITICAL in the
log, a health alert naming the fix, a `startup_failed` ledger record, and **exit 7** — a code of its
own, so the ending is distinguishable from the pin mismatch (2) and the channel refusal (5).

🔴 **The warning was justified by "a bot has to run unfrozen once to be promotable". THAT WAS
FALSE, and it was proved false rather than argued about.** A whole deploy was run against
`extreme_leg_1` from a cold instance folder holding nothing but its config — 171 files staged, the
import-and-build check passed, version counted as 187. Nothing in the deploy path reads an artefact
a prior run leaves: the deployment record answers `{}` when there is none and the open-position
check answers `None` when there is no record, both fail-open by their own design. **A comment
justifying a hazard with an untested claim is how that hazard survives** — the same claim was in
`live_config.code_root`'s docstring and is corrected there too.

⚠ **Order: the BENCH wins, then this, then the version pin.** A benched bot is not trying to trade,
so it still ends ordinarily (exit 0, no alert) even though it has no snapshot either — which is
`b_leg_demo`'s exact state on the box. And an undeployed bot has nothing to pin against, so
reporting *wrong version* would send the reader to re-deploy a version that was never deployed.

⚠ **There is no setting to switch it off.** Being deployed is derived purely from whether the
snapshot directory exists, so the only way past it is to deploy the bot.

⚠ **The monitor relaunches it three times and then latches a WILL NOT START alert**, exactly as it
does for the version-pin refusal — there is no refusal-aware latch on the box and this change does
not add one. The refusal exits before any code is imported, well inside the monitor's 8-second
confirmation window, so it cannot be mistaken for a start that took.

⚠ **Blast radius when this shipped:** all six assigned bots on the box were frozen (checked
per-bot, not from a doc line), the seventh was benched, so nothing stopped. The runner itself is
loaded from the box's checkout rather than any snapshot, so this reaches a bot at its next restart
whatever version it is pinned to.

Checks: `algos/tests/test_live_runner_startup.py` — refuses before anything connects or imports,
announces and records it and names the fix, the bench still wins, and it comes before the pin. Each
mutation named in its docstring and run red on 2026-09-16. Three fixtures were building bots with no
snapshot while testing guards further down the start; they now build the snapshot directory the
check actually looks at, because a fixture describing a state production cannot reach is rule 13
from the other end.

## 🔴 The startup line's commit is the PROMOTED commit, or "unknown" (2026-09-16)

`sos_fade_demo`'s startup line said `commit c8cdd64e` while its code fingerprint matched a
snapshot promoted from `4f87809d`. The runner read the box repo's HEAD — which a `git pull` moves
while the frozen `deployed/` snapshot stays put. Now a frozen bot prints the commit `promote.py`
recorded in `deployed.json` (`promoted_commit`), and **"unknown"** when there is no record. A bot
running from the repo (not frozen) still prints HEAD, because that is what it runs. The same value
goes into the ledger's startup row. ⚠ A promote with `--allow-dirty` still records HEAD, which then
does not fully describe the files — `promote.py` already warns about that at promote time.

Tests: `tests/test_running_commit_label.py` (4; red at HEAD — no such function, and the line read HEAD).

## 🔴 `realign_1` carried three settings its code does not have (found 2026-09-16)

The benched realign bot's config held `exec_ngs`, `exec_ngs_tp_r` and `exec_ngs_risk_pct` — the
parked no-gap SOS Fade settings that live only on `research/nogap-shift-entry`. The strategy config
refuses an unknown key, so **this bot would have failed on its first start**, and nothing flagged it
because a benched bot is never loaded. Found by loading its `strategy_params` into `RealignConfig`
while moving its defaults; removed. ⚠ **Before assigning any benched bot, load its settings into its
strategy's config once** — a folder created from a session on another branch can carry that
branch's settings. The same pass moved its window to 72h, its trail to structure-only and stated the
20-day momentum filter (`strategies/python/realign/realign_optimization.md` → Runs 12-13).

---

## 🔴 The startup line's commit is the PROMOTED commit, or "unknown" (2026-09-16)

`sos_fade_demo`'s startup line said `commit c8cdd64e` while its code fingerprint matched a
snapshot promoted from `4f87809d`. The runner read the box repo's HEAD — which a `git pull` moves
while the frozen `deployed/` snapshot stays put. Now a frozen bot prints the commit `promote.py`
recorded in `deployed.json` (`promoted_commit`), and **"unknown"** when there is no record. A bot
running from the repo (not frozen) still prints HEAD, because that is what it runs. The same value
goes into the ledger's startup row. ⚠ A promote with `--allow-dirty` still records HEAD, which then
does not fully describe the files — `promote.py` already warns about that at promote time.

Tests: `tests/test_running_commit_label.py` (4; red at HEAD — no such function, and the line read HEAD).

---

## 🔴 The ORDER-SENDING code is frozen too — and a restart cancels a resting order (2026-09-17)

**Found:** `algos/live/` and `algos/shared/` — the runner, the bridge, the sizing check, the kill
switch reader — ran from the box's working tree, so a `git pull` there changed what a live bot sent
to the broker with no promote, and the version pin never covered them. The root doc said "a git pull
cannot move a live bot"; that was true of the strategy half only.

**Now:** `promote.py` copies both folders plus `markets/fx/tools/broker_clock.py` into the snapshot
(`live_config.ORDER_PATH_ROOTS`, the one list), and the pin covers them. `runner.py` hands the
whole process to the snapshot's own `runner.py` before importing anything (`_run_from_snapshot`,
in-process so the PID and the process-list match are unchanged), and `_bind_code` refuses to start
if the bridge, sizing, `mt5_ops`, `fleet_halt` or `live_config` loaded from anywhere else.

- ⚠ **Data paths go through `shared/repo_paths.py`**, which finds the REPO from inside a snapshot.
  Kill switch, credentials, bot folders, state and the MT5 lock all live in the one checkout; a
  snapshot copy looking beside itself would read the kill switch as *not set*.
- ⚠ **A snapshot promoted before this date keeps its old three-tree pin and runs the repo's order
  code** until its next promote (`LiveConfig.carries_order_path`). Nothing strands it.
- ⚠ **A wording change in `algos/live/` now needs a promote**, not just a restart. The Command
  Center's version count includes these trees (`bot_versions._SHARED_TREES`), so the Bots page's
  version numbers jumped once.
- 🔴 **A restart CANCELS every resting order the bot has no record of — its own included** — and
  re-places at the next bar (`bridge._observe_orphans`). So the promote-and-restart that brings a
  bot onto this change moves its resting limit. Restart a live bot only when it is flat and has
  nothing resting.

TESTED: `test_deploy_freeze.py` (5 new), `test_live_runner_startup.py` (2 new),
`test_promote_version.py` (2 updated) — the handover, the pin and the kill-switch path each went red
under a mutation. MEASURED: a staged `sos_fade_1` snapshot run in a throwaway box loaded `bridge`,
`order_sizing`, `live_config`, `fleet_halt` and `notify` from `deployed/`, never the planted repo
bridge, and read the box's own kill switch.

🔴 **It stopped both SOS Fade bots starting on its first deploy (2026-09-17, 15:33 UTC).** The
runner's startup gate reads `strategies/python/live_contract.py` from beside itself — the snapshot,
once frozen — and only strategies that import it had it copied. It now ships with the order code
(`ORDER_PATH_ROOTS`). The throwaway-box check had stopped at `--help`, before the gate ran; it now
calls the gate for `sos_fade_demo`, `extreme_leg_demo` and `realign_1`, all reading the snapshot's copy.
