# Notes — Bots page, versions and deploys

Bot snapshot, versions, promote/deploy, stopping a bot, the bot registries, the app's own git commits. Moved VERBATIM out of `command-center/backend/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## 🔴 The app's commit swept up whatever ELSE was staged (2026-09-10)

🔴 **`_git_commit_push` staged its own files and then ran a bare `git commit -m`, which commits the
WHOLE INDEX.** Two sessions share this clone, so anything another session had staged went out
inside the app's commit under the app's message. It happened: a Sync VPS press committed a staged
rename from a different session as `05dbd703 accounts: synced with the VPS`, leaving a page that
imported a file the commit had moved. **Nothing failed** — the hook passed, the push ran.

✅ **It commits `-- <its own paths>` now**, so other staged work stays staged and untouched.
Proven both ways through the REAL pre-commit and commit-msg hooks in a throwaway worktree (bare: 2
files committed; with the paths: 1, the other still staged) and pinned by
`test_the_commit_carries_ONLY_its_own_paths_never_another_sessions_staged_work` (mutation: drop the
paths → red). ⚠ **Every endpoint that commits goes through this one helper**, so the fix covers
account moves, caps, risk and the registry alike.

## 🔴 The app's PUSH carried every commit waiting on `main` (2026-09-13)

🔴 **The commit named its paths (above); the push did not — it sent `main`, and `main` holds every
commit this clone has not pushed.** Two sessions share the clone, so one Bots-page save published
another session's finished work with it. MEASURED that day: an account save sent three commits
nobody asked it to, and the next save would have sent a fourth session's local commit before that
session had run its tests.

✅ **`_push_own_change` rebuilds the change on the REMOTE's tip and pushes it by id.** The local
commit is still made first, through the real hooks; the remote gets its own tree with the saved
paths set to that commit's version, under the same message.

- **Nothing else waiting ⇒ the local commit itself goes out**, so the ordinary case leaves one
  commit. Other work waiting ⇒ the remote gets a copy with the identical change; the next merge is
  clean and the log shows it twice.
- 🔴 **A path the remote also changed since this clone last had it is REFUSED**, never overwritten
  — building on the tip would otherwise undo another machine's save in silence.
- 🔴 **Nothing in the clone moves.** The old recovery ran `pull --rebase --autostash` here, which
  rewrote every session's local commits and stashed their unsaved work. The copy is built in a
  scratch index; `main`, the index and the working tree are untouched.
- ⚠ **`commit-tree` runs no hook**, so the copy is only ever built from a hooked commit's blobs.
  The push still runs pre-push, which skips a range holding only a config file.
- ⚠ **Nothing new to commit is not "nothing to push".** A save whose push was refused left its
  commit here; saving the same thing again now sends it rather than reporting it deployed.

Tests: `tests/test_bot_git_push.py` (10), on real git — a bare remote, this clone, and the box's
clone racing the push.

## 🔴 A REJECTED push was reported as a deployment (2026-09-04)

🔴 **`_git_commit_push` ran `git push` without `check=True` and never read its return code, so it
returned git's rejection text as its SUCCESS value.** All four endpoints wrap it in
`except subprocess.CalledProcessError` and report *git push failed* — an exception the push could
not raise; the endpoint then pulled on the VPS (succeeding, pulling nothing) and answered 200 while
the box held the old config. **MEASURED: an account move and a risk-share change sat unpushed for an
hour with the page reporting both deployed.**

⚠ **The rule was already in this file 200 lines below the bug** — *`subprocess.run` without
`check=True` does not raise on a non-zero exit, and the one failure mode a "never raises" helper
must still detect is the one that never raises.* It was written for the alert-thread write and never
applied to the push.

⚠ **A rejection here is the NORMAL case.** The box pushes its own decision record hourly, so any
deploy landing between its push and this clone's next fetch is a non-fast-forward, and **failing
loudly alone would turn an hourly race into an hourly manual recovery.** So the change is rebuilt
on the new tip and sent **once** more; never `--force`. It was `pull --rebase --autostash` here
until 2026-09-13 — see the section above.

## Every Deploy button in this app was dead for eight days (2026-08-12)

🔴 **`_git_commit_push` could not commit at all between 2026-08-04 and 2026-08-12, and every
endpoint that uses it reported the wrong failure.** The repo's `.githooks/commit-msg` refuses any
commit whose changed files' owning CLAUDE.md is not staged in the same commit, and an instance
config under `algos/markets/fx/instances/` is owned by `algos/CLAUDE.md`. Nothing here stages that
file — **nor could it, since the hook exists to demand a paragraph a human wrote** — so the commit
died, `subprocess.run(..., check=True)` raised, and the browser got **500 "git push failed"**.

**Three endpoints, all of them the ones Aaron is asking to use more of:** `PATCH
/bots/accounts/{account}/risk-cap`, `PATCH /bots/{bot}/account` (move a bot between accounts), and
`PATCH /bots/{bot}/runtime`.

✅ **MEASURED, not reasoned about, and both directions were run against the REAL hook:** a staged
instance config with an ordinary message is refused with exit 1 and the *"COMMIT REFUSED — code
changed, its CLAUDE.md did not"* banner; the same staged file with a `DOCS: none - …` line is
accepted with exit 0. The corroborating evidence is in the log — **the last commit this app ever
made is dated 2026-07-30**, five days before the hook landed.

⚠ **The fix is the hook's own in-band escape, and the two easier fixes are both worse.**
`--no-verify` is forbidden repo-wide precisely because it leaves NO TRACE, so the next person cannot
tell a deliberate skip from a forgotten one. An exemption for `*/instances/*.json` would also wave
through a **human** hand-editing one — which is the case the hook is right about, and is exactly
what the 2026-08-12 account move needed. A `DOCS: none - <reason>` line asks the caller to say why,
in the log, where the next person reads it.

⚠ **`docs_reason` is a REQUIRED third parameter with no default.** A default is boilerplate the
moment a second caller copies it, and the whole value of the line is that it is specific to what
was written. It is validated HERE rather than left to the hook, because the hook's refusal arrives
as a `CalledProcessError` two lines later and is reported as *"git push failed"* — which names the
wrong step and sends the reader at git.

**This is the THIRD time a rule fired on a robot's commit and silently stopped the job** —
`algos/tools/ledger_sync.py` twice on 2026-08-05, recorded in the root `CLAUDE.md`. **A hook has no
human to read its message when the committer is a program: it does not nag, it stops the work and
reports something else.** When you add a check, ask what it does to the things that commit
unattended.

✅ 5 tests (`tests/test_deploy_commit_gate.py`). One drives the app's real message shape through the
**real hook binary** and fails if it is refused; one proves that hook is still capable of saying no,
so the first is not vacuous; one pins the ValueError; and one walks the AST of `routers/bots.py` to
fail if a NEW call site forgets a reason — a behavioural test only covers the routes somebody
remembered to write one for, which is `test_bot_kill_scope.py`'s reasoning. ⚠ **The `--no-verify`
guard walks the AST rather than grepping**, because the prose explaining why the flag is banned is
in the same file; the first version failed on its own docstring.

## A bot's VERSION — the number the page showed was never written (2026-08-07)

🔴 **The Configure tab's version row read `v0`, and it always would have.**
`BotDeployedVersion.strategy_version` comes from `deployed.json`, which `promote.py` copies from
`live_config.LiveConfig.strategy_version` — an int that defaults to **0** and that **no code path
in this repo assigns**. So the card read `v0` before a promote and `v0` after one. Aaron asked the
question the tab exists for and found it unanswerable: *"I just wanna know what is the version that
I have compiled in my backtester versus the version that is deployed... and if I'm behind, there
should be a big nice button."*

`services/bot_versions.py` builds the real one, served as `BotDeployedVersion.compare`.

**A version is the number of commits that changed a file the bot's deploy COPIES, counted at a
commit.** Three properties fall out of that and the page needs all three: it moves when — and only when —
the code this bot runs moves; it is derived from the git history, so this machine and Aaron's
brother's compute the SAME number with no registry to sync; and subtracting two of them is not an
estimate of the work waiting to go out, it IS it. Measured on the live deployment: **v100 → v121,
21 behind**, which is exactly the 21 commits `git log 4e97565..HEAD -- <trees>` returns.

🔴 **IT COUNTED EVERY COMMIT *TOUCHING* THE TREES UNTIL 2026-09-10, SO A NOTES EDIT WAS A NEW
VERSION.** MEASURED that day: both live bots read "1 behind" because another session's commit
edited `engines/market_structure/CLAUDE.md`, and the page offered to deploy byte-identical code and
restart both for nothing. **Aaron's call: count only commits that change what ships.**
`strategies/python/package_deps.version_pathspecs` is the rule — the snapshot's own (a `.py`
outside `tests/`), called by every function here AND by `algos/tools/promote.py`, so the stamped
number and this one cannot drift. On the day: 154 files selected for the SOS Fade bot, 162 for the
extreme leg, each set identical to what the copier ships.

⚠ **EVERY VERSION NUMBER DROPPED ONCE** (SOS Fade v220 → v174, extreme leg v225 → v178). The bot's
own banner and ledger keep the OLD stamp until its next deploy, while this page shows the new
count — expected for one deploy, not a fault. ⚠ **A change to a LOOSE MODULE names that module as
its tree** (equality, not `startswith(tree + "/")`), or it named no tree and read as a merge.

⚠ **Not the lab's own `strategy_versions` registry, and the reason is the whole design.** That
table is content-addressed and monotonic and it hashes the **strategy package**, while a bot runs
that package plus `engines/` and `backtest/` — which is where most of the logic lives, and is
precisely why `algos/live/version.py::deployment_hash` spans all three. A number off the lab
registry would sit unchanged while the engines beneath it moved: the bot would report the version
it was promoted at and trade different rules. **That is the exact failure the deployment pin exists
to prevent, re-introduced one layer up as a label.**

⚠ **`trees_for` mirrors `algos/tools/promote.py::repo_trees` and the two must not drift.** That
function decides what is COPIED into a snapshot; this one decides what is COUNTED. A tree promoted
but not counted is a change that deploys while the page says you are up to date — silent, and wrong
in the reassuring direction. The subsystem rule forbids importing into `algos/`, so the agreement
is pinned by a test that READS that file, the same arrangement `test_notification_routing.py` uses.

🔴 **MIRRORING IS EXACTLY HOW BOTH CAME TO BE WRONG TOGETHER (2026-09-04).** Each said
`strategies/python/<package>` and they matched perfectly — while a strategy package borrows from
its siblings by bare name, so neither described the code a bot runs. **Two implementations
agreeing is not the same as either being right**, and a mirror test can only ever catch the
FIRST of them drifting. ✅ **The strategy side of both lists now comes from ONE resolver**,
`strategies/python/package_deps.py`, which walks the imports and returns the closure —
`strategies/` is not `algos/`, and this app already scans and deploys it. The mirror test was
replaced by one asserting each side CALLS that resolver, which is the only arrangement under
which they cannot drift. Rules and the deploy half: `algos/CLAUDE.md` → *A snapshot carries what
the package IMPORTS*.

⚠ **A resolver failure returns `[]`, which `version_at` renders as *cannot say*.** Falling back
to the shared trees would print a confident number that is quietly too small — the one outcome
every function here refuses. A strategy file mid-edit is a real state, and the page saying so is
correct.

⚠ **A bot's version number MOVED when this landed.** `sos_fade` borrows `loss_recovery`, so
commits touching it now count. The old number was too small; expect the Configure tab to read
further behind than it did the day before, once.

⚠ **Every function answers `None` rather than a number it cannot stand behind**, and `compare`
carries a plain-English `reason` instead. A missing commit (never fetched), an unreadable git, a
bot with no package: `0` would mean *up to date*, the most reassuring answer available and the one
most likely to be wrong. Same rule as `mt5_link` and `grid_sensitivity_score`.

### The RUNNER is counted too — it moves on a restart, never a version (2026-09-12)

🔴 **Both live bots read "up to date" while running code eight fixes behind.** The version counts
what a deploy COPIES, the strategy's closure. The runner — `algos/live`, `algos/shared`, and
`strategies/python/live_contract.py`, which `runner.py` loads by path — is repo code imported at
process start: a pull moves it on disk, only a RESTART loads it, and nothing counted it.
`BotDeployedVersion.running_code` is that count (`bot_versions.running_code`).

- **The start rides the SAME round trip as the version.** The command greps the bot's
  `health-<month>-*.jsonl` for its `startup` rows (`===STARTS===`, this month and last), and
  `_latest_startup` keeps the NEWEST by timestamp, never the last line — two months' files
  concatenate in name order. Only `event == "startup"` counts.
- **The start must be THIS process's.** When the state file states `started`, a start stamped more
  than `_START_SLACK_S` (60s) after it describes a later run than the one answering, and is refused.
  The page does the other half on the SNAPSHOT's clock: a process that began more than 10 minutes
  after the recorded start is a newer run and is not asked to restart again.
- **The count is `git log <started>..@{upstream}` over `RUNNER_TREES`, through `version_pathspecs`**
  — the deploy's own rule, so a notes edit beside the runner is not a change. `@{upstream}`, not
  HEAD: a commit only on this laptop cannot reach the box. The list is capped at 20; the count is not.
- ⚠ **`None` with its own reason, never 0, for every could-not-tell**: no start in two months, a
  start newer than the process, a commit this machine has not fetched, a branch tracking nothing,
  unreadable git. Each names a different fix.
- ⚠ **`RUNNER_TREES` mirrors what `runner.py` puts on `sys.path`**, held by a test that READS
  `runner.py` (the `trees_for`/`repo_trees` arrangement above). A path loaded there and not counted
  here reaches a bot on restart while the page says nothing is waiting.
- ⚠ **The fix it names is RE-DEPLOY, not Restart.** A plain restart starts whatever the box's
  checkout holds; the deploy pulls first. Re-deploying the version a bot already runs moves no
  strategy code — what it buys is the pull and the restart.

Pinned by 6 tests in `tests/test_bot_version.py` and 8 in `tests/test_bot_running_code.py` (a real
scripted repo, never a mocked `subprocess`); 10 mutations run through `scripts/testing/mutate.py`,
10 killed. The page's half: `../frontend/CLAUDE.md` → *One status per row*.

### A commit the box has and this clone does not is FETCHED (2026-09-12)

🔴 **Straight after a deploy made from this page, the panel read "Version unknown … Pull, then
reload."** The box pulls on every deploy and commits its own record hourly, so the commit it reports
can be newer than this clone's last fetch — and nothing in the app fetched.
`bot_versions.holds_commit` fetches once before calling a commit unknown; `compare` (the deployed
commit) and `running_code` (the commit a run started on) both ask it.

- ⚠ **At most one fetch a minute per clone, whoever asks** (`_FETCH_EVERY_S`, under a lock) — the
  page reads every bot's version when it opens.
- ⚠ **`git fetch` touches no working-tree file**, so it cannot reload this server or move what a bot
  runs.
- ⚠ **Still missing after a fetch is two reasons with two fixes**: the remote does not hold it (the
  box has a commit it has not pushed), or the fetch failed (this machine's connection).
- 🔴 **A test on the REAL clone never fetches** — `tests/conftest.py` → `_no_fetch_from_the_real_clone`
  answers *could not fetch* there, since a version read about an unknown commit would otherwise
  reach the network and move the developer's remote-tracking refs. A scratch repo fetches for real,
  from its own local remote.

Pinned by 6 new tests — 4 in `tests/test_bot_running_code.py` (a scripted repo with a bare remote and
a "box" clone), 2 in `tests/test_bot_versions.py` — and one re-pointed wording check; 7 mutations, 6
in memory through `scripts/testing/mutate.py` and the fence in a throwaway worktree, 7 killed.

### The ceiling on a promote is the REMOTE, not this laptop's HEAD (2026-08-14)

🔴 **A successful deploy of `sos_fade_demo` landed v164 while the backtester read v165, and
nothing anywhere said why.** `promote.py` PULLS on the VPS and deploys from its working tree, so a
commit sitting unpushed here is code the VPS cannot fetch — the promote runs, reports success,
restarts the bot, and leaves it behind by exactly those commits. Every number on the Configure tab
was correct; the reader was left pressing a button that could not change anything.

`compare()` now carries **`unpushed_commits`** — commits touching this bot's TREES that are not on
`@{upstream}`. ⚠ **It is scoped to the bot's own trees**, or a commit to `algos/live/` would tell the
reader to push before a deploy that is already complete. ⚠ **`None` (no upstream to measure against)
is not `[]` (measured, all pushed)** — the same rule as `mt5_link`, on a precondition rather than a
reading. ⚠ **`versions_behind` is deliberately unchanged**: it answers *how far behind is the bot*,
and folding the unpushed count into it would make a true number silently mean something else. This
is `uncommitted_edits` one step further out — **the working tree is not HEAD, and HEAD is not what
the VPS can reach.**

### A deploy's three messages are a THREAD, rooted here (2026-08-14)

A promote produces STOPPED, PROMOTED and ONLINE — **this router sends the middle one and the bot
on the VPS sends the other two**, so they read as three unrelated events. `_notify_telegram` now
returns Telegram's message id (via the new `services/notify.send_telegram_id`), and
`_set_alert_thread` writes it into `<instance>/alert_thread.json` with a 15-minute expiry. The
bot replies to it; the rules that keep a stale id from mis-parenting future messages live in
`algos/CLAUDE.md`, next to the code that reads the file.

⚠ **The root is sent BEFORE `_kill_bot`, and that ordering is the feature** — the bot writes
STOPPED seconds later, and a root sent after it is not the root of anything. Nothing was lost by
moving it: `restarted` was never a measurement (it was `ok and req.restart`, set unconditionally
after the kill), so the wording now states the INTENT and the replies report the outcome.

⚠ **`_set_alert_thread` NEVER raises and never blocks the promote.** A deploy that failed because
a Telegram convenience could not be written would be a spectacularly bad trade; the worst case is
two unthreaded messages, which is every deploy before this. It also writes **nothing** for a
message id of `0` or `None` — `send_telegram_id` answers 0 for *delivered but the id was
unreadable*, and writing that asks the bot to reply to message zero.

⚠ **The payload travels over STDIN, not argv** — it is JSON, and `^`-escaping braces through cmd
is the kind of quoting that works until a value changes shape. Same shape as
`_write_account_password`, minus the confirmation marker, because this write is allowed to fail.

⚠ **`test_notification_routing.py`'s sweep now matches `send_telegram_id` too.** A pattern naming
only the wrapper would let a new call site aim at the trades room unseen — **a sweep that
silently stops covering a function is worse than no sweep, because green reads as checked.**

#### The deploy that ships this feature can never thread its own STOPPED

⚠ **STRUCTURAL, not a bug, and it will be reported as one — it was.** STOPPED is sent by the
process being REPLACED, which is running whatever `algos/live/runner.py` was on disk when it
STARTED. On the deploy that first carries the threading code, that process predates it and has no
`_deploy_thread` at all. **Measured on the 2026-08-14 promote: the stopping bot's own banner reads
`commit 1bc3297` — the commit before the feature — while the bot that replaced it reads
`d65c996`.** The generalisation is worth more than the instance: **a change to `algos/live/` reaches
the STOPPING process only on the deploy AFTER the one that ships it**, so any behaviour you add to
the shutdown path is unobservable exactly once, on the deploy you would naturally check it on.

#### 🔴 And the write could not report its own failure, which is why the ONLINE half took an hour

**The same deploy sent all three messages loose. Every hop was then verified working IN ISOLATION**
— `_set_alert_thread` put the file on the VPS from this machine, and the bot's own `_deploy_thread`
read the id back out of it — **and nothing on either machine said which hop had dropped it.** That
is the least useful outcome an investigation can have, and it was designed in:

- **`subprocess.run` has no `check=True` here** (deliberately — raising would let a Telegram
  convenience fail a promote), so it does **not** raise on a non-zero exit. The blanket try/except
  therefore caught the failures that raise and waved through every failure ssh reports by EXIT
  CODE — a refused connection, a remote traceback, a read-only path.
- **A falsy `message_id` returned in silence.** `send_telegram_id` answers `None` for *the send
  failed* and `0` for *delivered but the id was unreadable* (it has a 5s timeout, and a response
  that arrives late is delivered-and-lost), and both land in that branch. It is where a brief
  Telegram hiccup becomes a whole deploy's worth of unthreaded messages.

`_set_alert_thread` returns a bool and prints on all three failure paths. ⚠ **Nothing branches on
the return value and nothing should** — the promote genuinely does not care. **The point is that a
helper allowed to fail must still be ABLE to say it did; otherwise the second occurrence is as
unreadable as the first.** ⚠ It is `print`, not a raised error, for the same reason the whole
helper is best-effort.

### The PROMOTED alert now names the versions it moved between (2026-08-14)

🔴 It said only *"It is now running the code that was just deployed"* — a sentence a reader cannot
check against anything, about the one action in this router that changes what a live account
trades. Aaron: *"The prompted message should say the version of the bot that was promoted from and
to."*

`promote.py` prints `##VERSIONS <from> <to>`; `_run_promote` parses it, STRIPS it from the output
the panel renders, and returns it as a third value. ⚠ **The "from" is read off the PREVIOUS
`deployed.json`, not off `HEAD~1`** — a bot three deployments behind must not be described as one
behind. ⚠ **A malformed or absent marker is `(None, None)`, never half-read**: taking the first
number off a broken line is how a message comes to name a version nobody measured, and an older
`promote.py` on the VPS prints no marker at all, which must degrade to the sentence rather than
inventing a version. ⚠ **`_vlabel` renders an unknown `v?`, never `v0`** — 0 is a version somebody
could be on, and it is the exact value that misreported `strategy_version` for its whole life
(see `algos/CLAUDE.md`). ⚠ **A FAILED promote sends no alert at all**, so no version pair can
describe a move that did not happen.

### `changes_between` is ONE git process per RANGE, never one per commit

🔴 **It was one `git show --name-only` per commit until 2026-08-15**, and the output was
byte-identical either way — so nothing on the page could show it. **MEASURED: 5.5s → 0.10s over
this repo's full history; `tests/test_bot_version.py` fired 1,080 git subprocesses, 51.8s of a
53.7s run.** ⚠ **The fan-out scaled with the RANGE, so it got worse every time anybody pushed.**
`--name-only` on the same `git log` returns every file list in one stream. Story:
`../docs/BACKEND_BUILD_NOTES.md` → *The change list was one git process per commit*.

⚠ **Records are split on `%x1e`, never parsed line by line** — git puts a blank line between the
format line and the file list, and a record separator does not care what git puts between fields.

⚠ **The `tree + "/"` test is KEPT even though the pathspec now filters git's output.** A pathspec
of `engines` also matches a top-level FILE of that name; dropping it widens what counts as touching
a tree.

🔴 **`areas` had NO test at all and it was found by MUTATION, not review** — forcing `areas = []`
left all 49 tests across both bot-version files GREEN. Pinned now by
`test_every_change_names_the_tree_it_touched` and `test_the_change_list_is_ONE_git_process_per_range`,
each watched red against its own mutation. ⚠ **The second counts PROCESSES, not seconds**: a
wall-clock assertion is flaky on a busy laptop and silent on a fast one, and the defect was the
fan-out rather than the speed.

⚠ **The standing rule: a cost can hide in correct code run N times, and no result will show it.**
When a helper loops over a list calling something that launches a process, ask what sets the
length of that list.

✅ **Merges and renames are pinned on a SCRIPTED repo (`tests/test_bot_versions_history.py`,
2026-09-10)**, because real history cannot promise either: a merge was checked only when one sat
in the window, and `_path_before_renames` had no test at all. 5 mutations run, 5 killed. ⚠ **The
endpoint tests remember git's answers per file** (`test_bot_version.py`, 15s → 3s) — they are about
the VPS record, not the comparison — and ONE of them now reads the comparison off the endpoint,
which nothing did: its try/except turns any shape mismatch into no banner at all, in silence.

### The settings that change without anyone asking

`setting_changes` diffs the strategy's dataclass DEFAULTS between the two commits and marks which
ones the bot's config PINS. This is the half of a promote nobody requests and everybody gets:
`live_config.py` states that *"a value that is not in the file is a value this bot does not have an
opinion about"*, so a default that moves in the repo moves the live bot on its next promote with
nothing in the request saying so. On the promote in front of Aaron that is the **36-hour time
stop** — and the service reproduces `promote.py --dry-run`'s four settings independently, which is
the cross-check that says the derivation is right.

⚠ **A `stated` row is RETURNED, not filtered out.** *This changed in the repo and your bot is
holding it still* is the reassuring half of the same question, and dropping it leaves the reader
unable to tell "not affected" from "not checked". It caught a real one: `exec_secondary` went
Off → On in the repo and this bot pins it Off — which `promote.py --dry-run` does not report.

⚠ **`ast`, never `import` or `exec`.** This parses source read out of an arbitrary historical
commit; running it would execute that commit's code inside the backend. Two refusals rather than
two guesses: a non-literal default is `_UNPARSED` (reported as *changed, cannot say to what*), and
a field declared in two classes with different defaults is also `_UNPARSED`, because `b_leg`
subclasses `sos_fade`'s config and picking one silently would describe the wrong bot.

⚠ **`was` is `""` exactly when `is_new`, never `"Off"`.** The deployed version had no such lever at
all, which is not the same as having it switched off — and "Off" is the lie in the safe-looking
direction.

⚠ **Labels come from the strategy's own `*.meta.json`**, copied. A name→sentence mapping written in
this app would be a second claim about what a setting does, which is this repo's most-repeated
defect; the same discipline the trade-fib layer follows.

🔴 **THE TEST THAT CHECKS EVERY SETTING HAS A DESCRIPTION CHECKED ONE STRATEGY OUT OF SIX, UNDER A
NAME THAT SAYS "EVERY" (fixed 2026-09-02).** `test_every_tunable_param_is_documented` named
`sos_fade` outright, so a green run said nothing about the other five — a setting with no
description renders as a raw field name and a dash on the strategy page, and four new ones landed
that way the day this was found. MEASURED by scanning each package the way the lab does:
`loss_recovery` 0 undocumented, `sos_fade` 0, `extreme_leg` 0, **`b_leg` 98, `bos`
91, `realign` 120.**

⚠ **It is now a RATCHET rather than a blanket rule, and the reason is this file's own lesson about
walls.** Turning it on everywhere fails 309 params at once with nothing that can auto-fix them, and
a wall gets `--no-verify`'d, which leaves no trace and reads as checked. The three clean packages
are locked clean; the three others are named with their counts in a second test that fails if a
count goes UP — which an ignore-list can never do — **and also fails when one reaches zero**, so a
package that gets fixed is promoted rather than left permanently exempt. **Moving a package out of
that list is the unit of work.**

⚠ **`areas` on a change names which TREE a commit touched and is not a claim about trades.**
`backtest/` holds both the fill model the bot runs on and the lab's own cache, and no path can tell
those apart. Naming the area is derived; naming the effect would be a guess wearing a label.

✅ **36 tests (`tests/test_bot_versions.py`), non-vacuity proven by MUTATION** — a fail-watch
against HEAD is vacuous for a new module. Four mutations, four distinct tests red: dropping the
shared trees from `trees_for`, returning `0` instead of `None` for an unfetched commit, letting a
subclass override win silently, and claiming a new setting `was: "Off"`.

🔴 **A PACKAGE RENAME MADE EVERY EARLIER COMMIT UNREADABLE BY THE NEW NAME (2026-09-03).**
`setting_changes` reads `strategies/python/<package>/config.py` at both commits, so after the
de-branding rename the OLD side simply did not exist under the new name and the whole preview
answered `None` — which renders as *not checked*. ⚠ **The promote that needs it most is the FIRST
one after such a rename**: a bot deployed before it, being compared against a repo that has moved
the tree. Blank at exactly the moment somebody is deciding whether to deploy.

✅ **`_path_before_renames` ASKS GIT** (`diff --name-status -M`) what the file was called at the
older commit, rather than carrying a map of past renames — so it works for the next rename too and
cannot go stale. ⚠ **A directory rename reaches git as one rename per FILE**, which is why asking
about `config.py` answers a question about the package tree. ⚠ **It runs only when the old side is
missing and the new side is present**, so an ordinary promote pays nothing and a genuinely
unreadable commit still reports *not checked* rather than inventing a comparison.

🔴 **THEY ALL REACHED BACK BY `HEAD~50` AND AN HOURLY ROBOT MADE THAT MEANINGLESS (2026-09-01).**
The trading box commits its own record every hour, so 49 of the last 50 commits here touch nothing
but a `.jsonl`. `HEAD~50` came to mean *a day and a half ago* rather than *a while of real work
ago*: the range stopped containing any strategy change, three cases went red against completely
correct code, and a fourth compared version 264 against version 264 and asserted it was smaller.
✅ One shared anchor (`_before_the_last`) now reaches back over the last commits that actually
TOUCHED the strategy. ⚠ **The lesson is not about these tests: a commit COUNT is a proxy for
elapsed work that only holds while commits are human-paced, and anything using `HEAD~n` here is
measuring the robot's schedule.** It DEGRADES daily rather than failing once — the kind of red
that gets rerun, shrugged at, and eventually excluded.

## A promote as a JOB — the steps the deploy panel draws (2026-09-10)

`POST /bots/{bot}/promote/job` (202, returns the job) + `GET /bots/{bot}/promote/job` (that bot's
latest job, or `null`). Built so the page can show ONE progress readout over a deploy that is a
30–60s request with nothing to watch (Aaron: *"a static disabled button doesn't catch my focus"*).

- 🔴 **One implementation of what a deploy DOES.** The job and the one-shot `/promote` (kept — the
  trading-box MCP calls it) both go through `_run_promote` + `_finish_promote`.
- 🔴 **A step is entered by the code as it enters it** (a `stage` callback), never timed: pull →
  build → stop → start → confirm. The pull is now its OWN ssh call — it was chained with `&`, which
  never stopped on a failed pull either, so no outcome changed; each half gets its own 30s timeout.
- ⚠ **`skipped` is not `done`** — a step not asked for, or one a failure never reached.
- 🔴 **`confirm` is a measurement, and the hash alone cannot make it.** On a re-deploy of unchanged
  code the OLD process already reports the deployed hash. It needs a new `started` stamp and a new
  heartbeat compared with what the old process wrote (read just before the stop) — box values
  against box values, no two clocks subtracted. Past the wait limit (48 × 5s, a LIMIT rather than a
  claim about start time) it ends `unconfirmed`, never `done`.
- 🔴 **It could not confirm ANY real deploy for its first day** — it read the deployed hash under a
  key `promote.py` never writes, got `""`, and every deploy waited out its four minutes while the
  bot was already on the new code. The fixture used the same invented key, so the tests agreed with
  the bug (rule 13). `_deployed_hash` is now the ONE reader, shared with the version card, and a
  test takes the key from `promote.py::write_pin`'s own source.
- ⚠ **A raised failure's `error` depends on the step it hit** (`_describe_job_failure`): *untouched*
  only for the pull, *may or may not have deployed* for a build that timed out or reported nothing
  (a structured `error`, so the page never reads promote.py's prose), *IS deployed* past the build.
- ⚠ **A second job for the same bot while one runs is a 409**, and eviction never drops a running
  job. **In memory**: a backend restart loses the readout, never the deploy.
- ⚠ **The browser guard refuses the POST** — it is the same action as `/promote`.
- ✅ `tests/test_bot_promote_job.py` (24). **15 mutations run, 15 killed.**

## Stopping a bot ASKS it to stop (2026-08-07)

🔴 **Every deliberate stop this app issued was a hard `wmic ... call terminate`, so the bot never
reached the `finally` that writes its `shutdown` record — and the NEXT startup reported *"the
previous run ended WITHOUT a shutdown record: it was killed, it crashed, or the box went down."***

That sentence is the **silent-death detector** (`algos/CLAUDE.md` → *The daily record*): no shutdown
record ⇒ the process was killed or the box died. **It only carries information if a DELIBERATE stop
leaves one.** It did not, so it fired on every restart anybody performed on purpose, and the Bots
page carried a permanent `NEEDS REVIEW` chip saying a healthy bot had crashed. Aaron read exactly
that on 2026-08-07 and asked why. ⚠ **An alarm that fires when you press the button is one you learn
to scroll past — the noise was not the cost, the signal it was burying was.**

`_kill_bot` now writes `<instance>/stop.request`, polls for the process to go for
`_GRACEFUL_STOP_SECONDS` (30, at `_STOP_POLL_SECONDS` 3), and terminates only a bot that ignored it.
`runner._loop` checks for the file at the top of every pass and exits through the ordinary clean
path. The return value names which path ran.

⚠ **A FILE, not a signal.** Windows has no usable SIGTERM for a console process — `taskkill` without
`/f` posts WM_CLOSE, which a Python console app never receives — and a file fits what that loop
already is: something that polls its own instance directory every `poll_seconds` and already
re-reads its config from there.

⚠ **The escalation is not a fallback nobody exercises.** A wedged bot, one blocked in an MT5 call, or
one running code that predates the file will never see it, and terminating those is the honest
answer. It keeps the two-clause `wmic` match — see `tests/test_bot_kill_scope.py` for why each half
is load-bearing.

⚠ **THE ONE WAY THIS COULD BE WORSE THAN THE KILL IT REPLACES is a STALE request stopping a healthy
bot seconds after boot** (left by a crash, a failed shutdown, an aborted SSH call). Four guards:
`run()` clears the file BEFORE the loop, both sides delete it after use, an unreadable instance
directory is never read as a stop request, and a clear that FAILS warns rather than refusing to
start. **A trading bot that will not stay up is a far worse failure than a noisy chip.**

⚠ **`_bot_is_running` answers True when the process list cannot be read**, so the caller escalates to
a kill rather than reporting a stop that may not have happened. Of the two wrong answers, "kill a
process that was already gone" is harmless and "report a live trading bot as stopped" is not.

⚠ **The kill-scope suite needed a SECOND fixture for this.** Its whole subject is that the terminate
command names both `python.exe` and `--bot <key>` — and after this change a healthy bot never
reaches that command, so those tests would have passed against a `_kill_bot` that issued no kill at
all. `stubborn_ssh` drives a bot that ignores its stop request. **A safety test whose scenario stops
occurring passes for ever and protects nothing.**

### Which process IS a bot — its runner, with exactly its key (2026-09-11)

🔴 **A STOPPED bot read RUNNING whenever any tool carrying its key was running.** Every tool that acts
on a bot takes the same flag — `promote.py --bot X`, the hourly `watch_reentry.py --bot X`, the
coordinator starting it — and all four checks here matched the key anywhere. MEASURED: the demo SOS
Fade copy read RUNNING straight after its first deploy, with no process and no account. Now:

- `_is_bot_runner` is the rule in Python — a line running `runner.py` whose `--bot` value is exactly
  the key (ends at a space, quote or line end, so `sos_fade_2` is not `sos_fade_20`). The snapshot's
  status and `_running_bot_keys` both go through it.
- `_runner_wql` is the same rule in WMI, for the probe and the forced stop: `runner.py` is in the
  filter, so a forced stop never kills the bot's own deploy or re-entry check. ✅ **Verified on the box
  with a read-only query before it shipped** (the two live bots by their PIDs, nothing for a stopped
  one). ⚠ **Exact since 2026-09-13**: WQL's `_` is escaped as `[_]` and the key must end at a
  space or the line end, so one key may start another's. Verified read-only on the box.
- ✅ **Every bot check on the box uses the same rule since 2026-09-13** — the watchdog, the dead-man
  switch, the coordinator and the chat bot (`algos/shared/bot_registry.is_runner_line`) — and both
  sides are tested against ONE list of cases, `algos/tests/fixtures/runner_lines.json`. Tests:
  `tests/test_bot_process_match.py`; 6 mutations run, 6 killed — the status one first SURVIVED the
  helper-only tests and needed a check through `get_snapshot`.

## `_BOTS` is DISCOVERED from the bot folders (2026-09-13)

Listing a bot here makes it ADDRESSABLE — the Accounts tab, its version, params and state. **Whether
it TRADES is a different question**, answered by its config's `account`. It was a hand-kept list,
one of five; a bot IS its folder now (`_discover_bots`, by the rule `algos/CLAUDE.md` →
*Registering a bot* owns — not restated here).

- ⚠ **Refreshed on every /bots request, rebuilt only when a config or the account list CHANGED**
  (`_registry_signature`, a router dependency), so a new folder appears with no restart. The maps
  are rebuilt IN PLACE, so a function reading one by name sees the current list.
- ⚠ **A folder that cannot be listed is a 503**, never an empty page (rule 1).
- 🔴 **`BotReg.account_type` is read off the folder's config and the account list** — `demo` for a
  benched bot, `live` for an account the list cannot classify. It is `_account_type_of`'s FALLBACK,
  so a test stubbing a config with NO account meets the real folder's label: the settings copy
  correctly refused the live `sos_fade_demo` until the stub stated and classified its account.
- ⚠ `algos/tests/test_bot_bench.py` PARSES this file and fails on a filled `_BOTS` literal or a real
  bot key typed into a `key="..."`.

⚠ **One strategy can be TWO bots (2026-09-11)** — `sos_fade_2` and `extreme_leg_2` are the demo
copies of the two live bots, each its own folder, process and deploy. Born benched; the order
(register → promote → assign) and why lives in `algos/CLAUDE.md` → *One strategy, two bots*.

🔴 **The copies carry the SAME display name as the originals (same day, Aaron: *"it's a generic
strategy"*)** — a name is the strategy, demo or live belongs to the account, and "(demo)" would have
gone on saying demo on real money the day a copy moved. So: the page groups by account;
`_bot_label` adds LIVE or demo to every Telegram message this app sends (off the config's account
in the registry — a benched or unregistered bot keeps the plain name, never the hardcoded
`account_type`); and **`_resolve_bot` refuses a name two bots share (409)** — its first-match would
have sent a by-name Stop to whichever registered first, the LIVE bot. Callers pass the key. ⚠ GONE
LIVE names the bots, not their keys (the keys say `demo`). Tests: `test_bot_label.py`,
`test_bot_registry.py`; `test_bot_promote.py` now names its bot by key.

## The "needs review" flag — the one thing this page could not see

`BotStatus.review`, served from `<instance>/review.json` on the VPS, written hourly by
`algos/notifications/log_review.py` (`SYS_LOGREVIEW`), which reads each bot's own health record.

**Why it exists.** Every other signal on the Bots page is about the PROCESS — is it in the process
list, is it stamping a heartbeat, does it still hold its MT5 link. **None of them can see a HALTED
order bridge**: the loop runs, the heartbeat ticks, `wmic` lists the process, the page says RUNNING,
and the bot places nothing. Nor a bot that crash-looped overnight, nor a link outage that recovered
before anyone looked, nor a runtime config change the bot REFUSED (so the page shows settings it is
not using). All of those are in the bot's health stream and nothing here read a line of it.

⚠ **It is fetched on the SAME batched snapshot connection as `bot_state.json`.** A second ssh round
trip per bot is precisely the cost `_fetch_vps_snapshot` exists to avoid — the same reasoning that
moved `GET /{bot}/version`'s state read onto its git round trip (8.5s → 3.7s).

⚠ **The section name is DERIVED, `_review_section(key)`, used by the fetch and the parse both.** A
marker written under one spelling and read under another produces a flag that is always absent —
which renders exactly like a healthy bot, i.e. it fails in the reassuring direction and nothing
anywhere raises. `tests/test_bot_review_flag.py` pins that the two agree.

⚠ **`review_file` is PER BOT even when two bots share a `bot_state.json`.** A review is about one
bot's own record, and merging two into one file makes *which bot needs attention* unanswerable from
the file whose entire job is answering it.

⚠ **A missing file is UNKNOWN and stays quiet — it is no longer the normal state.** `log_review.py`
deleted it when a bot came back clean until 2026-09-03 and now always writes it, so an absence means
the flag could not be read rather than that the bot is healthy. A malformed one is dropped rather
than raised: this page must not invent an alarm out of its own plumbing failing. **The review job's
own state is visible as the Record review entry in the scheduled-jobs list — which is true as of
2026-09-03 and was false for as long as this sentence had been written.**

🔴 **A DEAD REVIEWER FROZE THE CHIP ON WHATEVER IT LAST WROTE, AND NOTHING COULD SAY SO
(2026-09-03).** Nothing read the flag's own `checked_at`, so an hour-old flag and a month-old one
rendered identically — the page reporting a state that had stopped being true, with the reader
having no way to ask. **Worse, the paragraph below this one PROMISED the safety net: it said the
review job's own absence would show as a DISABLED job in the scheduled-jobs list.** That list held
Monitor, the dead-man switch and log backup, and no reviewer entry had ever existed. ⚠ **A comment
asserting a safety net that is not there is worse than no comment, because the next reader stops
looking** — this file has now shipped that shape twice, and the other one was also a docstring about
another program's control flow.

✅ **Two halves, and neither works alone.** `SYS_LOGREVIEW` and `SYS_REENTRYWATCH` joined
`_SYS_DISPLAY_NAMES` and `_SCHEDULED_JOBS`, so a disabled or stopped task is visible; and
`_review_payload` raises an ALERT finding of its own when `checked_at` is older than
`_REVIEW_STALE_SECONDS` (three missed hourly runs — the same three-in-a-row shape the reviewer's own
stale-heartbeat check uses). ⚠ **Measured from the last flag the reviewer WROTE, never from the
schedule**, so a task that is armed and crashing every run is caught — the case `schtasks` alone
reports as a healthy ARMED.

⚠ **Those two are the only jobs on that box whose normal state is SILENCE.** Every other watcher
here says something when it runs, so its death surfaces as an absence somebody notices; a silent
watcher that dies looks exactly like a quiet week. That is why they had to be listed rather than
left to the flag alone.

⚠ **`_parse_reviews` now returns EVERY readable flag, including a clean one, and the CHIP's gate
moved into `_review_payload`.** It filtered on a non-empty findings list, which threw away the one
field that says the reviewer is alive — so a clean flag and a dead reviewer arrived as the same
nothing. The reviewer side of that (it no longer deletes the file when clean) is
`algos/CLAUDE.md`; do not restate it here.

⚠ **The stale finding goes FIRST in the list.** It is the reason not to trust the findings under it,
so it cannot be buried below them.

⚠ **An unparseable or missing `checked_at` is treated as STALE, never as fresh** — a flag that
cannot say when it was written is exactly the one not to trust, and here the reassuring answer is
the dangerous one. A naive timestamp is read as UTC rather than raising: an exception in this
function would cost the whole Bots page, not just one chip.

⚠ **An ABSENT flag stays quiet rather than becoming an alarm, and that is a decision with a stated
gap.** The reviewer writes one per registered bot per run, so after one hourly pass an absence
really would mean something — but it also looks exactly like *this change has not reached the box
yet*, and a false alarm in the hour after a deploy is how a chip gets ignored. The gap closes on its
own within an hour of the reviewer next running; until then the scheduled-jobs entry is what covers
a dead task.

⚠ **The job SCHEDULES in `_SCHEDULED_JOBS` are display text and nothing verifies them against the
box.** Both were read off `schtasks /query /v` when they landed (hourly, starting :20 and :23) — a
cadence changed there and not here reads as a lie in the calmest possible voice. Check the task.

**Tests:** `tests/test_bot_review_flag.py` (19). ⚠ **None of the freshness cases can go RED** —
`_review_payload` did not exist, and the old code never suppressed anything, so a test asserting
*this case is still reported* passes against the bug it was written for. Ten MUTATIONS were run,
each alone, and each took down exactly its own named test: the staleness window widened, an unknown
age read as fresh, the stale finding appended rather than prepended, the empty gate removed, the
timezone fill-in dropped, the finding type filter dropped, the level hardcoded, the reviewer entry
deleted from the jobs list, a job name typo'd, and the task-membership filter dropped.

⚠ **It is NOT gated on `status == "RUNNING"`, unlike `mt5_link` directly above it.** The findings
that matter most — it crashed, it was killed, it refused to start — are exactly the ones you can only
read once the bot is no longer running, so hiding the flag on a stopped bot would suppress the
explanation at the moment somebody is looking for it. `mt5_link` is gated because a stopped bot's
last link stamp describes a process that no longer exists; a review describes the record, which does.

🔴 **Open, or over — only OPEN is "needs review" (2026-09-12, widened 2026-09-13).** The reviewer
files what the record shows has ended under `resolved` (`algos/CLAUDE.md` → `SYS_LOGREVIEW`);
`_review_payload` passes it on as history and takes the level from what is open — `"ok"` when
nothing is. A finding filed as open that states why it is over is over wherever it sits; a flag
with no `resolved` list keeps everything open. **Between passes the bot's own readings SINCE the
review answer what it left open** (`_answered_since_review`, the table above the prefixes): a
RUNNING bot's newer heartbeat — bridge not halted, MT5 link up, any beat after a bar or loop error —
and a run that began after it for a refused start, pin or setting. A newer reading saying the thing
is STILL so drops the review's copy: the row raises Halted / No MT5 link itself. MEASURED: live SOS
Fade read *Needs review — Bridge is HALTED right now* for 40 minutes after a re-deploy cleared it.
⚠ **A repeat is answered by neither** — one good heartbeat does not end a burst. ⚠ **A missing,
older or unreadable time KEEPS the finding.** ⚠ The start is not gated on RUNNING: a run that began
after the review answered its refusal even if it stopped since. ⚠ The prefixes and the `resolved`
list are a contract with `log_review.py`, pinned by a test that reads that file. Tests: 19 in
`tests/test_bot_review_flag.py`; 15 mutations planted in memory, 15 killed.

## 🔴 The log panel read a file the bot abandoned nineteen days ago (2026-08-24)

`BotReg.log_file` defaulted to `<key>.log`, beside a comment stating that was what
`algos/live/runner.py` writes. **It was true when written and stopped being true on 2026-08-05**,
when the runner moved to one file per UTC day (`<key>-YYYY-MM-DD.log`, `DailyFileHandler`). Nothing
here changed, so `GET /bots/{bot}/log` — and the trading-box tool that fronts it — served the
5 August file and read as live. The bot placed thirteen orders in that window and none of it
appeared.

⚠ **Nothing errored and nothing went red.** The endpoint returned a full, well-formed log. Rule 7 in
its purest form: a label is a CLAIM about code somewhere else, and no test tied this one to the
runner. That is why the cases assert on the COMMAND sent to the box, never on a filename constant —
a constant can agree with itself for ever.

`_newest_log_files` lists the dated files and takes the newest `_LOG_DAYS` (2), oldest first.

⚠ **Sorted by NAME, not modified time.** `algos/tools/log_backup.py` copies these into a zip, and a
copy or restore rewrites the timestamp while the name still says which day it is.

⚠ **TWO days, not one.** The runner rolls at 00:00 UTC, so a request at 00:05 against a single file
returns four lines and reads as a bot that just woke up.

⚠ **`log_file` empty now means DISCOVER; a value is an override that skips discovery.** A bot running
pre-2026-08-05 code still writes one fixed file, so an empty listing falls back to `<key>.log` rather
than reporting no log. An unreachable box RAISES — *nothing there* and *cannot ask* stay apart.

**Tests:** `tests/test_bot_log_view.py` (7). Three watched RED against HEAD (each read
`…\sos_fade_demo.log`). The fallback and override cases passed at HEAD by construction and are
pinned by MUTATION, named in their own docstrings.

## Nav activity — three booleans so the sidebar stops pulling three lists

`GET /system/activity` → `lab_db.get_nav_activity()` → `{backtests, optimizations, stress_tests}`.

**Added 2026-08-05 because `Sidebar.tsx` is mounted on EVERY page** and derived those three
booleans client-side from the full runs / optimizations / stress-test lists. So having the app
open at all cost a `GET /backtests/runs` on a poll — **measured 1.69 KB per run, 66% of it the
54-key `params` dict** (~137 KB at 81 runs), plus the other two lists — to decide whether to draw
three pulsing dots. The endpoint is 62 bytes.

⚠ **The predicates must mirror `Sidebar.tsx`'s `activeByRoute` exactly, and they are now the ONLY
statement of them** — the dot used to be derived next to the thing it drew, and nothing in the
browser can contradict this any more. That is the saving and equally the risk, so every one is
pinned in `tests/test_nav_activity.py`, including the ones that must NOT match:

- a run carrying `optimization_id` is **not** a Backtests-section job (it belongs to the
  Optimizations section, whose own grid reports it) — one job must not light two dots;
- sweep and stack children **are**, because they surface in the Runs tab;
- stress tests match **`LIKE 'running%'`**, never `= 'running'` — a test spends most of its life
  in `running_wf` / `running_sens`, and an equality check leaves the dot off for the bulk of the
  run, which looks exactly like a test that already finished.

⚠ **It is deliberately NOT `has_running_job()`.** That answers *may I start work on this PLATFORM*
and partitions by runner; this answers *is this NAV SECTION busy* and partitions by job kind.
Collapsing them makes an MT5 optimization light the Backtests dot, or a python backtest fail to.

⚠ **The trimming stops here.** Dropping `params` from the runs LIST was considered and rejected:
`TuningWorkbench` genuinely reads it off that list to compute per-iteration deltas, so making it
conditional would produce a response where `params: {}` means both *"I did not ask for it"* and
*"there are none"* — the same **no data vs cannot ask** defect as `mt5_link` and
`grid_sensitivity_score`, landing in the tune page as "no parameters changed".

## The snapshot says whether a bot's account may TRADE (2026-09-12)

`BotStatus.trade_allowed` / `trade_block`, passed straight through from the bot's heartbeat
(`algos/CLAUDE.md` → *Whether the account may TRADE*). **Gated on RUNNING, like `mt5_link`**: a
stopped bot's last reading describes a process that no longer exists. ⚠ `None` = could not ask,
never off. ⚠ Declared on the model, or Pydantic drops them. Tests: 1 in `test_bot_registry.py`;
3 mutations run, 3 killed.

## The snapshot carries the bot's open trade and its halt (2026-09-12)

`BotStatus.bridge_state` / `halt_reason` / `in_trade` / `position` (`BotPosition`), from the bot's
heartbeat (`algos/CLAUDE.md` → *The heartbeat says what the bot holds at the broker*). **All gated
on RUNNING**: a stopped bot's trade may have closed since its last heartbeat.
- ⚠ **`_bridge_state` reads `bridge_state`, and `status` only as a fallback for a bot on an older
  runner — and only for a bridge word** (warming / live / halted). The watchdog writes running /
  stalled / stopped / offline into that same key.
- ⚠ **`halt_reason` only while halted; `in_trade` only a real boolean** (Pydantic reads `"yes"` as
  true); **`position` checked field by field** (`_position_payload`; `_finite` refuses a boolean,
  NaN and infinity) and DROPPED when unreadable — a 500 here blanks every bot on the page.
- ⚠ Declared on the model, or Pydantic drops them. Tests: 3 in `test_bot_registry.py`; 7 mutations
  run, 7 killed.
