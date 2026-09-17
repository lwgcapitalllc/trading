# Notes — VPS scheduled tasks, ledger backup and the dead-man's switch

The box's own ledger backup, scan_terminals.py, the CLEAN SLATE reset, scheduled-task password trap, on-hold live tasks, the process-check/watchdog-race/dead-man's-switch trio, the daily record and SYS_LOGREVIEW, plus SYS_BROKERCOSTS and SYS_GETSCREENRESTART lifted from Shared MT5 Architecture. Moved VERBATIM out of `algos/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## 🔴 The box backs up its OWN record — and it is the ONLY machine that may (2026-08-24/28)

`SYS_LEDGERSYNC` runs `algos/tools/ledger_sync.py --local --alert-on-failure` **hourly at :20**.
There is no Mac agent any more; it was removed 2026-08-28 and `main()` now refuses to commit
records the running machine did not write.

**Why it changed.** The record left the box only when a Mac happened to be awake. Aaron, after a
weekend of records sitting on one disk: *"let the VPS go to work for me… so when I'm asleep,
things could run automated."*

**Why it could not before, and what actually fixed it.** The task runs as SYSTEM, whose credential
store has no cached token and no interactive session, so `git push` **BLOCKED** rather than failing.
Two changes, and the second is the one that matters:

  * a repo-scoped fine-grained token (`github_token`, git-ignored `algos/credentials.json`), spliced
    into the push URL **in memory** so it never reaches `.git/config`;
  * 🔴 **Git Credential Manager disabled outright** on every git call. **The token alone would NOT
    have fixed the hang.** MEASURED: with the helper live, even a SUCCESSFUL `ls-remote` printed
    *"Unable to persist credentials with the 'wincredman' credential store"* — it reaches for a
    store it cannot write, and under a session-less task that is what waits forever. Silent with it
    off.

🔴 **EXACTLY ONE MACHINE MAY COMMIT THIS RECORD, and writing that rule at the PUSH layer cost a
day (2026-08-28).** `--no-push` looks safe and is not: **on a shared branch a local commit is a
push with a delay** — the Mac's commit reached origin on the next human push of unrelated code.
Two APPENDS to the end of one file then cannot be merged, **at any content**, so the box's hourly
job conflicted, aborted correctly, and re-failed for eight hours stacking a commit each time.

✅ **Fixed as a property of the MACHINE, not a flag on an installer**: a run that fetched the
records over SSH refuses, before fetching, and exits non-zero. `--local` is the test — it already
means *these files are on this disk*. ⚠ Refusing BEFORE the fetch is deliberate: files copied into
the working tree are a loaded gun for the next `git add -A`. ⚠ A stale agent on anybody else's Mac
is now inert, so nothing has to be removed anywhere. ⚠ A dry run still works from any machine.
⚠ A second READER is free — the Mac has every record by `git pull`. It is a second WRITER that
breaks. Do not "restore" the Mac agent; `scripts/install_ledger_sync.sh` refuses and says why.
⚠ `merge=union` is the tempting one-line fix and it DUPLICATES records — story and numbers:
`algos/docs/ALGOS_BUILD_NOTES.md` → *the backup that conflicted with itself*.

🔴 **`_identity()` goes on the PUSH path as well as the commit — a rebase REPLAYS commits, so it
needs a committer too.** Missing there, the job committed hourly and pushed nothing for a night.
⚠ **It was invisible while the box was merely AHEAD of origin** (a fast-forward replays nothing)
and broke the instant the other machine pushed. **A branch only the rarer case reaches ships broken
and waits.**

⚠ **Reproduce a scheduled-task failure AS SYSTEM or you have not reproduced it.** The same call by
hand as Administrator succeeds — that account has a global git identity and SYSTEM has none. Every
failure this job has had was invisible to a hand-run.

⚠ **`git rev-list --count origin/main..HEAD` LIES ON THE BOX** — `_push` targets the authenticated
URL, not the remote NAME, and pushing to a URL never updates `refs/remotes/origin/main`. Compare
`rev-parse HEAD` against origin instead. The sync is unaffected; only the check is.

Story, measurements and the SYSTEM fixture: `HISTORY.md` → *The backup that committed all night*.

🔴 **It REFUSES to push when the working tree carries changes outside `algos/ledger_archive/`**
(`_foreign_changes`). `algos/tools/promote.py` freezes a live bot's snapshot out of that same
checkout, so a rebase underneath a half-finished deployment would change what is about to be
frozen. The commit stays local and the job says so. ⚠ **Untracked files do NOT count** — the box
permanently carries two, and counting them would mean the push never ran while looking installed.

⚠ **A failure sends a Telegram HEALTH message.** `--no-push` and `--dry-run` deliberately do NOT
alert: an alarm that fires when you asked for the thing is one people learn to ignore, and this
job's silence has already been mistaken for success twice.

🔴 **THAT MESSAGE COULD NOT SAY WHY UNTIL 2026-08-27, AND IT COST A NIGHT AND A SESSION.** Every
refusal above already printed a specific, actionable explanation — **to the scheduled task's
console, which nobody reads** — while what reached a human was two fixed sentences. **An alarm that
cannot distinguish its own causes is a doorbell: it tells you to go and look, which is the work you
built it to save.** ✅ `commit` and `_push` return `(ok, reason)`; the reason is the message's third
line. Story: `docs/ALGOS_BUILD_NOTES.md` → *Ten identical alerts*.

🔴 **AND IT SAYS A THING ONCE (2026-08-28).** Carrying the reason did not stop it carrying the SAME
reason eight times in one night. **An alarm that repeats itself hourly teaches people to scroll past
it**, which is the same defect as one with no reason at all, arriving from the other side.
`alert_decision` suppresses an UNCHANGED cause, and the state lives in a git-ignored file beside
`monitor_state.json`.

⚠ **Suppression is ONLY safe because RECOVERY speaks.** Without the all-clear, silence would mean
either *fixed* or *still broken, not worth mentioning*, and the reader would have to go and look.
**Never delete the cleared branch to make this quieter.** Four things always speak: a CHANGED cause
(a different cause needs a different action), a daily reminder with the failure's age, an unreadable
state file (*cannot tell whether I said this* is not *I said this*), and recovery.

✅ **It also closed a path that returned non-zero in SILENCE**: a record git is configured to IGNORE
can never be backed up at all — the worst outcome this job has — and it was the one case that never
reached the alarm, because an ignored file is not "changed" so nothing was left pending to fail on.

⚠ **`alert_state_path()` is a FUNCTION, not a constant**, so it follows `REPO_ROOT`. A constant is
bound at import and would keep pointing at the real checkout however a caller is set up — a test
writing a fixed real path is the worst failure shape a suite has.

⚠ **Reasons are written for someone with no context, and they differ by the ACTION they call for** —
clear the tree, resolve a rebase, read why the remote refused, or change `.gitignore` because that
file can never be backed up and a retry is pointless. Two failures needing different work must never
render as one sentence.

⚠ **A tuple, not a result object, and the ugliness is the point.** Any object is truthy, so
`if commit(...)` would keep compiling and read every failure as a success; unpacking breaks every
caller loudly — and immediately found one a grep had missed.

⚠ **An unexplained failure NAMES ITSELF as one** rather than leaving a blank *Why*. Rule 1 through a
message instead of a value: a blank line reads exactly like a clean failure with nothing to add.

🔴 **STILL OPEN — the same defect one branch over: when EVERY fetched record is gitignored, `todo`
is empty, the job returns 1 and alerts NOTHING.** A hole, not a design.

⚠ **What it costs, and it was a deliberate trade:** that box already holds a live broker password,
and a repo write token beside it means a break-in costs the repository too. One repo, Contents
write, nothing else, is the whole of the limit.

⚠ **A rebuild does not restore the token** — it is git-ignored. The task then commits and never
pushes, with every green tick still green. Put it back as part of the rebuild.

🔴 **THE FIRST REAL RUN ON THE BOX COMMITTED NOTHING AND REPORTED "up to date".** `Path.relative_to`
returns the HOST's separator, so a path came out `algos\ledger_archive\...` while
`git status --porcelain` prints `algos/ledger_archive/...` — every membership test against git's
output missed, `pending()` returned empty, and the job printed *"up to date — all already
committed"*. Task result 0, exit 0, two modified record files still sitting in the working tree.
`_rel()` normalises to git's spelling everywhere. ⚠ **It could not happen on a Mac, and that is the
lesson: the code was correct for as long as it only ever ran on the machine that wrote it, and broke
the moment it moved to the box it was written to back up.** A path comparison is platform-specific
even when nothing about the logic is. ⚠ **This is the THIRD Windows-only defect to reach a scheduled
task through a green suite** — `%-I` in `strftime` and cp1252 console encoding were the other two —
so the standing rule above holds: **run it on the box.** ⚠ Its test asserts on a WINDOWS-SHAPED
string, because a real path on a Mac has no backslash and the assertion would pass without testing
anything.

🔴 **AND THE RUN AFTER THAT EXITED 1, FOR A SECOND REASON ONLY THE SYSTEM ACCOUNT HAS.** SYSTEM
does not share the interactive user's global git config, and this repo has no LOCAL identity — so
`git commit` refused with *"Please tell me who you are"*, **after** the files had been copied, which
leaves the working tree looking half-done. MEASURED with a throwaway SYSTEM task:
`git config --get user.email` returned nothing. **Running the identical command as Administrator
worked**, which is the shape that makes this hard to see — the hand-check passes and the unattended
run does not. `_identity()` supplies a fallback `LWG Trading Box <bot@lwgcapital.local>` per command.
⚠ **A machine, not a person**: these commits are made on a timer, and a history that says so beats
one borrowing somebody's name. ⚠ **Fallback ONLY** — a Mac keeps its own identity, or every manual
sync would be attributed to the box. ⚠ **Passed per-command, never written into `.git/config`**: that
checkout is what `promote.py` reads, and a write would silently re-attribute a human's commits made
from the same box.

**Tests:** `algos/tests/test_ledger_sync_local.py` (37), weighted toward what the job must REFUSE.
⚠ The owner rule has a case for the box being ALLOWED as well as three refusals — a checker whose
every case asserts a refusal certifies a tool that never works (root CLAUDE.md, 2026-08-26). Both
mutations watched RED: guard removed, and guard refusing everybody.
A fail-watch is vacuous for the original functions (they were new), so non-vacuity is by MUTATION —
dropping the archive exemption and dropping the redaction each redden their own named test. ⚠ **The
four alarm-wording cases are the exception and WERE fail-watched properly**, this file copied into a
worktree at HEAD: three go red there because the old message has no room to carry a reason, and the
fourth — a good run must stay silent — is red by mutation instead, since it passes against HEAD for
the wrong reason. 🔴 **One test caught a real
defect the live check had missed: the authenticated URL was missing its `@`, so it could never have
authenticated — and the check on the box only asserted the builder returned something.**

### `tools/scan_terminals.py` — what the box is ACTUALLY logged into (2026-09-10)

**The account list above is hand-typed and nothing checked it against this machine.** On the day
this landed it claimed a terminal for 700107749 that is not logged into it, and `C:\MT5_Scalper`
had been logged into a **live** account (34957946, PUPrime-Live) for a day with no part of the
system able to see it. This tool reads every terminal and reports who it is logged into, so the
list can be compared against the box instead of believed.

🔴 **It must never attach to a terminal a bot trades through, and that safety rests entirely on it
reading the instance configs.** So **a missing instance directory REFUSES THE WHOLE SCAN** rather
than answering "nobody owns anything" — the same value, the opposite fact, and the empty answer is
the one that makes every terminal on the box eligible including the live one. Caught by running the
script from outside the repo, which is how the next person will test it.

🔴 **`mt5.login()` is not called here and must never be added.** It CHANGES what a terminal is
logged into, so one stray call re-points a terminal under a running bot. A bot may move its own
terminal; a scanner may not. There is a test that greps this file for the call.

⚠ **`mt5.initialize(path=...)` LAUNCHES a terminal that is not running**, so only terminals already
seen in the process list are probed. A stopped install reports **"could not be asked"**, never "no
account" — `account: null` here is never a statement that a terminal is empty.

⚠ **Demo-or-live comes from the broker's own account flag, never from the server name.** An
unrecognised flag reports UNKNOWN rather than the safe-sounding word: guessing demo for an account
that is real is how a bot gets pointed at somebody's money.

⚠ **The symbol suffix is the one COMMON TO EVERY probe instrument, and an ambiguous broker gets
`null`.** The first rule asked each instrument to resolve to exactly one variant and **could never
have answered on a real broker** — PU Prime quotes `XAUUSD.crp`, `XAUUSD.p` and `XAUUSD247`, and
`EURUSD` beside `EURUSD.p`. It refused safely and it refused ALWAYS, which is decoration that ships
looking careful. **A check that cannot pass is not a check.**

⚠ **Each terminal is probed in its OWN SUBPROCESS**, because the MT5 binding ties a process to one
terminal and a hang must cost one answer rather than the scan.

⚠ **Rows carry a normalised join key separate from the path a human reads.** The first real scan
spelled one terminal three ways in one report, and the consumer is the command centre matching
these against paths typed by hand.

🔴 **It carries what each bot says its terminal is on (`bot_reports`), so the Command Center asks the
box ONCE (2026-09-10).** Each owned terminal gets `reported_by_bots`, read from every bot's own
`bot_state.json`; the judgement (do they agree) stays in the Command Center. 🔴 **Only a FRESH
heartbeat counts** — a stopped bot's file still holds the last account it saw, yesterday's fact
looking exactly like today's. Fresh means younger than `HEARTBEAT_FRESH_S`, which must equal
`deadman.HEARTBEAT_STALE_SECS` and a test fails if they differ. ⚠ **Judged on the heartbeat, never
`max(heartbeat, started)`**: a bot that just restarted has a fresh start and the PREVIOUS run's
account until its first heartbeat overwrites it.

Story, and the two defects only a real terminal could show: `algos/docs/ALGOS_BUILD_NOTES.md`.

🔴 **The heartbeat reports the account the terminal is ACTUALLY on (`observed_account`), beside the
configured one (2026-09-10).** `_check_account_identity` measured it every poll and threw it away,
so nothing outside the process could check an account-list row pointing at the bots' terminal —
which is where the scan above refuses to attach. ⚠ **Reported here, ACTED ON only by the halt**; a
field that displays a mismatch must never look like the guard. ⚠ **`None` = could not ask**, paired
with `mt5_link` so the two stay readable apart. 🔴 **It is read with `getattr`, and that is
load-bearing**: the whole state write sits in one try/except whose failure mode is NO HEARTBEAT, and
the heartbeat is what SYS_MONITOR reads to catch a frozen bot. A plain attribute read made a display
field able to silence the watchdog — a suite test building a bare runner caught it.
⚠ **This is a RUNNER change, and the frozen `deployed/` snapshot does not cover the runner** — it
freezes the trees that decide what a bot TRADES (`version.py`). So it reaches a live bot on its next
restart after a pull, with no promote. Nothing here changes a trading decision.

### CLEAN SLATE — 2026-07-31. Read this before trusting anything older.

**Aaron's decision: the suite starts from scratch today. Nothing from before this date carries
forward, and nothing is expected to still be on disk.** Both the VPS and the repo were leaned out:

- **Deleted from the repo:** the four dead `shared_*` modules — commit **`e92304a`**, documented in
  [`docs/DELETED_CODE.md`](docs/DELETED_CODE.md).
- **Deleted from the VPS:** `C:\algos` (a 36 MB pre-migration copy of the whole old suite, including
  the dead bots' instance state), `C:\algos-backup`, every stale task XML and log in `C:\temp`,
  `C:\tmp`, the root probe scripts, the orphaned `C:\trading\regime`, scratch files
  (`dump_opt.json`, `filetest`, `smoke_out.txt`, dead zero-byte agent logs, a `.vpslocal.bak`), old
  bot state (`monitor_state.json`, `stop_suppress.json`), stale Telegram runtime state, and every
  `__pycache__`. `git status` on the VPS is clean.

**The consequences, stated plainly so nobody re-derives them:**

1. **There is no historical trade data on the VPS.** No old ledgers, no `bot_state.json` from a
   previous bot, no equity logs. The first live ledger entry will be the first real one.
2. **A file's absence is not a bug.** If something references a path that is not there, the answer is
   that it was deleted on purpose — check git history and `DELETED_CODE.md` before recreating it.
3. **To recover anything, use the commit hash.** Do not rewrite deleted code from memory or from a
   docstring; `git show <commit>^:<path>` gives you the real thing.
4. **What was deliberately KEPT:** all four MT5 terminal installs (`MT5_FFT`, `MT5_Lab`,
   `MT5_Scalper`, and the Program Files instances) — Aaron may attach new bots to them;
   ⚠ **Renamed 2026-09-14 so each folder names whose account it holds:** `C:\MT5_FFT` →
   `C:\MT5_Demo` (demo 700152905), `C:\MT5_Scalper` → `C:\MT5_Aaron` (live 34957946),
   `C:\Program Files\PU Prime MT5 Terminal` → `C:\MT5_Richard` (live 35710389); `C:\MT5_Lab`
   unchanged. Older notes and ledgers keep the old names. 🔴 **None of these terminals is
   portable** — each keeps its login and settings in
   `C:\Users\Administrator\AppData\Roaming\MetaQuotes\Terminal\<MD5 of the upper-cased install
   path, UTF-16LE>`, so a folder rename opens a blank, logged-out terminal unless that data folder
   is copied under the new name first (with `origin.txt` rewritten). The terminals run in
   trader's remote-desktop session; the bots run as SYSTEM, so a bot must never be the thing that
   launches a terminal. Relaunch one from an interactive task as `trader`.
   `start_mt5_agent.bat` (`MT5AgentRDP` runs it); `credentials.json` and `users.json`; and the
   `C:\temp` directory itself, which `bootstrap_vps.ps1` uses as its staging dir.
5. **Only the Telegram bot is maintained from the original suite**, and only for trade ENTRY and
   EXIT alerts. Crash alerts, P&L tracking and the daily reporter are fixed but disabled — see
   *On hold* below.

### Scheduled tasks — the stored-password trap (found 2026-07-31)

**Every `SYS_*` task on the VPS had been silently dead since 30 May.** They were registered with
`LogonType: Password` against the machine's Administrator SID, the provider rotates that password
(there is a `CheckAndPromptPasswordChange` task on the box), and once it changed Windows refused to
launch them. The symptom is the nasty part: **`schtasks /run` still reports SUCCESS** and the task
still shows `Ready` — only `Last Run Time` gives it away by never advancing.

`MT5AgentRDP` and `NT8Agent` kept working because they use `InteractiveToken` (the logged-in desktop
session), which is why the platform looked healthy while its whole scheduled layer was off.

What that cost: crash alerts were off for two months, and **`SYS_STARTUP` would not have restarted
anything after a reboot.**

All are now running as **SYSTEM** — no password to go stale, and it survives the next rotation.
`algos/scheduler/*.xml` were rewritten to match, because they also hardcoded this machine's SID and
would have re-created dead tasks on any rebuild or new VPS.

**Standing rule: a scheduled task that must run unattended runs as SYSTEM.** Never register one with
a stored password, and never trust `schtasks /run`'s exit code — verify `Last Run Time` moved.

**Follow-on, same day: the XMLs could not be registered at all.** Every file in
`algos/scheduler/` carried `<LogonType>ServiceAccount</LogonType>`, which this Windows build
rejects for `S-1-5-18` — `schtasks /create /xml` fails with *"incorrectly formatted or out of
range"* naming LogonType. A working SYSTEM principal on this box is `UserId` + `RunLevel` and **no
`LogonType` element**; `schtasks /query /tn <name> /xml` on a live task is the way to see the shape
Windows actually accepted. `bootstrap_vps.ps1` installs every task through that same call and only
`Write-Warn2`s per failure, so **a rebuild would have created no tasks and still reported success.**
All six XMLs are fixed and each was test-imported under a throwaway name. If you add a task, import
it before you trust it — and delete the throwaway immediately, because a stray copy of
`telegram_task.xml` or `startup_coordinator_task.xml` starts a SECOND bot.

**Two things a task cannot do, both found by running it as SYSTEM:**

- **It cannot `git push`.** SYSTEM has its own credential store, Git Credential Manager has no token
  there and no session to prompt in, so the push **blocks** rather than failing — the task sits in
  `Running` with no output until its execution limit kills it. ⚠ **SOLVED for the ledger since
  2026-08-24 and the fix is above, not here**: a repo-scoped token plus Git Credential Manager
  disabled outright. The cost was accepted deliberately — this box already holds a live MT5
  password, so a repo write token beside it means a break-in costs the repository too.
- **It has no console.** `timeout /t` and anything else wanting a console fails under a task and
  over SSH alike.

### Live tasks, and the two still on hold

**`SYS_MONITOR` is ON as of 2026-07-31** (Aaron's call — a dry-run bot nobody is watching is the
thing this layer exists to prevent). It runs every minute as SYSTEM and alerts on: bot gone, bot
back, **loop stalled**, Telegram bot down (auto-restart ×3, then a critical alert).

⚠ **The stalled-loop half had never been able to fire, and that is worth knowing before trusting
any watchdog here.** `monitor.py` reads a `heartbeat` timestamp from `bot_state.json`; nothing
wrote one, and the check read the missing key as `0` and then asked `0 > 300`. So it was
permanently false rather than obviously broken — and a frozen bot still answers `wmic`, so it
reads RUNNING on the Bots page, in Telegram and in the task list. `runner._heartbeat()` now stamps
it every loop (with the balance read moved OUT of that try block, so a broker hiccup cannot swallow
the stamp), and the monitor falls back to `started` when no stamp exists. `algos/tests/test_watchdog.py`
pins both halves plus three launcher↔watchdog agreement tests. **A watchdog whose failure mode is
silence is worse than none — the empty alert channel reads as good news.**

🔴 **The stale-stamp fallback is `max(heartbeat, started)`, never `heartbeat or started`.**
`bot_state.json` outlives the process, so a restart refreshes `started` and leaves the DEAD run's
`heartbeat` in the file — a stale-but-truthy stamp wins an `or` outright and every restart drew a
false `STALLED`/`RECOVERED` pair quoting the previous run's clock (measured 2026-08-13). ⚠ **The
test that was supposed to cover this passes `started` with NO `heartbeat`** — a bot that has never
run, not one that restarted — so both fields present with one of them stale was the untested shape.
Story: `docs/ALGOS_BUILD_NOTES.md` → *The restart that reported itself stalled*.

**`SYS_DEADMAN` is ON as of 2026-08-04** — every 5 minutes as SYSTEM, the external dead-man's
switch described in the header. It is the only alert here that does not originate on this box.
⚠ **It is INERT until `deadman_url` is set in `algos/credentials.json`** (deliberately: it reports
honestly and sends nothing rather than failing every five minutes). Check with
`deadman.py --status`, and treat an unset URL as an open gap rather than a configured switch.

### 🔴 A PROCESS CHECK THAT CANNOT ASK MUST NOT ANSWER "DEAD" (2026-09-09)

**Two copies of the chat bot were found running on the box, both long-polling one Telegram
token.** Story and the measured restart series: `docs/ALGOS_BUILD_NOTES.md` → *The duplicate chat
bot*.

🔴 **`monitor.is_running` returned `False` when `wmic` missed its 10s timeout — which happens on a
loaded box, i.e. exactly when a restart storm is happening.** So the watchdog started a second
copy of a process that was never dead. **Rule 1, in the one place it costs the most**, and the
same line restarts healthy TRADING bots the same way.

✅ **It answers `True` / `False` / `None`, and every caller reads `None` as *do nothing this
pass*.** ⚠ **A non-zero exit is `None` too, not `False`** — a failed query and a box with no bots
print the same empty string, and only the exit code separates them. ⚠ **The two POST-restart
re-checks make the OPPOSITE call and read `None` as NOT CONFIRMED**: there the restart has already
been requested and the only question left is whether to claim it worked, which is what
`schtasks`'s own SUCCESS is worth.

✅ **The launcher's guard is a LOCK, not a survey** — an exclusive lock held for the life of the
bot it starts, so a second launcher cannot begin. **It cannot time out and it cannot fail open.**
⚠ **A recorded child PID lets an ORPHAN be killed by PID rather than by enumerating the process
table**, which is the step that failed. ⚠ **The wmic sweep is KEPT as a backstop and must never
again be treated as the guard.** ⚠ **Failing to take the lock exits 0** — "already up" is success,
and a task that fails every minute gets ignored.

⚠ **No watchdog here can see a duplicate**, because every one of them asks a yes/no question and
two copies both answer yes. **The guard has to be at the thing that STARTS the process.**

🔴 **THE FIRST VERSION OF THAT LAUNCHER LEFT THE BOX WITH NO CHAT BOT AT ALL, AND THE CAUSE IS
RULE 7.** `telegram_bot.py` has an instance guard of its own: it reads **`telegram_bot.pid`**,
asks whether that PID is still a telegram_bot, and exits if it is. The launcher recorded its
CHILD's pid into that same file — so the bot started, read its OWN pid out of the file its parent
had just written, decided a copy was already running, and exited; the launcher then had nothing
to wait on and released its lock. **`telegram_bot.pid` belongs to the BOT and nothing else may
write it**; the launcher's record is `telegram_launcher_child.pid`, pinned apart by
`test_the_launcher_never_writes_the_file_the_chat_bot_owns`. ⚠ **A file written in one module is
a CLAIM about whoever reads it, and the reader has to be found BEFORE the write** — two writers
of one path is the defect `ledger_sync.py` already records. ⚠ **Found by RUNNING it on the box,
not by the suite**: every test passed, because the collision only exists where both programs
share one directory.

### 🔴 The watchdog was RACING deliberate stops, and the flag could never have covered it (2026-09-09)

**MEASURED on the health channel: a clean `STOPPED` was followed by `OFFLINE — restarting it now`
three times between 2026-09-08 and 2026-09-09.** A promote-then-restart had the watchdog start the
bot before the operator could. **Two things issuing starts for one bot is how a book gets
doubled** — the hazard `restart_bot`'s own docstring is written against.

🔴 **THE SUPPRESSION FLAG IS WRITTEN BY WHOEVER ISSUES THE STOP, SO IT ONLY EVER COVERED THE
ROUTES THAT REMEMBER TO WRITE IT.** The Bots page writes it; **the documented CLI route
(`echo stop > stop.request`, in the root workflow) does not**, and neither does anything else
somebody reaches for at 2am. **A rule that depends on every caller remembering it is a rule with a
hole per caller.**

✅ **`monitor.stopped_on_request` reads the BOT's OWN closing record instead** — `shutdown` with
`exit_code 0` and reason `stop requested`, which `runner._run` writes on the `stop.request` path
every stop route drives. **No caller has to remember anything**, which is the whole reason this is
not simply another suppress key.

🔴 **THE RECORD MUST BE NEWER THAN THE RUN'S OWN START, OR A STALE ONE SUPPRESSES A REAL CRASH.**
Stopped on purpose → started again → hard-killed leaves that old *stop requested* line as the
newest shutdown on file, and a hard kill writes none of its own. Believing it would let ONE
deliberate stop suppress every later crash for as long as that file survives. **Same shape as the
`max(heartbeat, started)` rule above: two fields that are not the same age across a restart.**

⚠ **It is re-checked in the RESTART block, not left to the flag the transition sets** — the
transition only runs when the state CHANGED, so a pass whose first sight of a bot is *down* (a
fresh `monitor_state.json`, a new bot, the file deleted) sets no flag and would restart a bot
somebody had stopped. Reading the record needs no memory of a previous pass.

⚠ **Every unreadable answer means RESTART** (rule 1 pointed the recoverable way): restarting a bot
somebody stopped is a nuisance they can see and undo; declining to restart one that crashed is
silent, and is the failure this watchdog exists to prevent. **A crash still restarts, and that
control is the one that matters.**

⚠ **It reaches the box by `git pull` alone** — the watchdog is a fresh process every minute, so
there is nothing to restart.

**Tests: 5 in `tests/test_watchdog.py`, 5 mutations RUN and every one RED on its own named test.**
🔴 **One mutation SURVIVED the first pass and the reason is the lesson: the unreadable-record test
asserted only that a restart happened, and `check_bot` wraps the lookup in a `try/except` — so a
version that RAISED produced exactly the same restart as one that returned False cleanly.** It
pins the function's own answer now, which is the only place the two behaviours differ. **A test
whose premise is not established is green against its own defect.**

### The dead-man's switch waits for a problem to OUTLAST a restart (2026-09-09)

🔴 **A 5-minute pass landing in the ~60s hole a restart punches sent `/fail` and paged for a
button somebody had just pressed.** **An alarm that fires when you press the button is one you
learn to scroll past** — the fourth time this repo has paid for that.

✅ **`confirmed_problems` withholds a problem until it has persisted `CONFIRM_SECS`.** ⚠ **180s is
MEASURED, not picked** (rule 4): a deliberate stop-to-online cycle is ~55–60s from the bots' own
logs, and the watchdog's own recovery is the ceiling at ~130s worst case — up to 60s to notice,
then a restart it confirms after an 8s settle. **Re-measure before moving it.**

⚠ **A held problem pings HEALTHY**, deliberately: the box is plainly answering, and the thing
briefly wrong is already owned by the watchdog that does recovery. ⚠ **An unreadable state file
ALARMS rather than suppressing** (rule 1) — *cannot tell how long this has been wrong* may not buy
the reassuring answer. ⚠ **A cleared problem is FORGOTTEN**, or the next one inherits a stale
timestamp and pages instantly, turning the fix into a different false alarm. ⚠ **A dry run does
not start the clock.**

🔴 **DELIBERATELY NOT FLAP DETECTION, and that boundary is the module's charter.** A bot dying and
being restarted repeatedly is `monitor.py`'s finding and it already sends a message per
occurrence. **This switch answers one question: can anything on that box still talk to me.**
Teaching it a second question is how one event becomes two alarms and the channel gets muted.

**Tests: 4 new in `tests/test_watchdog.py`, 5 in `tests/test_deadman.py`; 10 mutations RUN, every
one RED on its own named test.** ⚠ **`test_deadman.py`'s fixture redirects the pending-state file
into a scratch dir** — it is a module constant under the real `algos/` tree, and a test writing
one shared path is the worst failure shape a suite has. 🔴 **One pre-existing test was pinned to a
FUNCTION NAME and went red on a rewrite that kept its behaviour exactly** — the *case pinned to a
path that moved* shape recorded twice already here. It drives the real launcher now.

⚠ **All three files reach the box by `git pull`** — `algos/` is not in the frozen snapshot — **so
no promote is needed and none should be run.** The watchdog and the switch are fresh processes per
scheduled run and pick the change up themselves; **the launcher needs `SYS_TELEGRAM` restarted.**
Nothing here touches what either bot trades.

**`SYS_LOGBACKUP` is ON as of 2026-07-31.** Daily 00:30 UTC (the VPS clock is UTC), runs
`tools/log_backup.py`: zips the instance `.log` files into `algos/log_archive/`, prunes past 90
days, reports closed AND open record files. **It does no git.** The record reaches the repo
via `algos/tools/ledger_sync.py --local` on this box, hourly — see `### The daily record` below. Logs
are COPIED, never rotated: the bot holds its log open and renaming an open file on Windows fails.

**`SYS_PNLTRACKER` and `SYS_REPORTER` no longer exist — deleted 2026-08-05, tasks and scripts
both.** They had sat here as "deliberately disabled, waiting for a bot registry", which is what
made them look like features. They were not: both carried an EMPTY registry (`BOT_TRADES = {}`,
`BOTS = {}`) inherited from the four bots deleted 2026-06-22, so enabling either would have run a
script that found no bots and exited. The tracker sent daily-goal / daily-cap / weekly-cap Telegram
alerts; the reporter sent a 4pm performance summary.

⚠ **The reason for deleting rather than fixing is worth keeping, because it decides what replaces
them.** A daily report on a strategy taking ~2 trades a month says "no trades today" almost every
day, and a channel that is noise 95% of the time is the one nobody reads on the day it matters —
the bot already pings on entry and exit. And the loss cap was **an alert, not a limit**: nothing in
it could refuse a trade, so it read on the Bots page as protection while the bot traded straight
through it. A real cap belongs in `algos/live/runner.py` where it can stop the loop.

⚠ **Deleting them took out more than two files, and the collateral is the interesting half.**
`shared/thresholds.json` and `BOT_THRESHOLDS` went (nothing else read them). The derived P&L fields
went out of `bot_state.py`'s defaults — `daily_pnl`, `weekly_pnl`, `total_pnl_pct`, `peak_balance`,
`trades_today` — rather than being left at `0.0`, because with no writer they would have rendered
"+0.00% today" under a field nothing measures: **this repo's own rule, that a fabricated zero and a
measured zero must never be the same value.** `balance` stays, written by `live/runner.py`. 🔴 **And auditing that claim found the defect this pass nearly shipped: `total_pnl_pct` had no writer either.** It was `set_pnl`'s too, and the Bots page's *Overall P&L* column and Telegram's `/balance` BOTH defaulted it to `0.0` — so a live account up 5% reported dead flat, in two places, with nothing on either screen able to say the number was never measured. **`live/runner.py` writes it now, because it is the only process that can**: it already reads the balance every poll and derives the percentage — off the broker's own deal history, net of deposits, since 2026-09-12 (see *A deposit is not a return*) — `None` when the terminal is blind, never `0.0`. `/balance` reads both without a numeric default and prints `no MT5 link` or the bare balance instead of inventing a flat account. ⚠ **The lesson is about the DELETION, not the field: removing a writer leaves its readers behind, and a reader with a numeric default goes on answering confidently.** Grep for readers of anything a deleted job wrote — the seven fields that had no reader were the easy half. And
Telegram lost `/report`, `/demo`, `/live`, `/all` and **`/force`** — the last one mattering most,
because it fired *whatever* action was pending, so with reports gone it was an undocumented second
route to `/restart`, `/stop` and `/emergency`, and the `readonly` role held it.

⚠ **The same pass found `bootstrap_vps.ps1` registering neither `SYS_DEADMAN` nor `SYS_LOGBACKUP`**
despite both task XMLs sitting in `scheduler/`. A rebuilt box came back with **no dead-man's
switch** — the one alarm that fires when the box itself dies — and nothing anywhere would have said
so, because a missing alarm is silent by construction. Both are in the list now.

**The standing lesson: a job that is "disabled until later" and a job that does nothing are
indistinguishable from the outside, and the label protects the second one.** Before switching any
disabled task on, read what it would do with today's registries — not what its name says it does.

### The daily record — two streams, and what makes a silent death visible

**Built 2026-08-05 to Aaron's spec:** every day must carry (a) enough about the bot's *health* that
a bug or a silent death is readable from the logs, and (b) everything about *trades* — taken,
skipped, blocked, and why — with **nothing overlapping between the two**. Both go to GitHub twice
a day.

**Three files per bot per UTC day**, all rotating on the same boundary so they read side by side:

| file | question it answers | contents |
|---|---|---|
| `<inst>/ledger/decisions-YYYY-MM-DD.jsonl` | why did it trade, or not | `bar` (one per closed bar: stages, arms, edges, vetoes, stop, TP ladder), `blocked`, `missed`, `trade` open/close, and the broker-facing order events (`order_placed`, `order_refused`, `order_too_small`, `stop_moved`, `dry_run_action`, `warmup_position_skipped`) |
| `<inst>/ledger/health-YYYY-MM-DD.jsonl` | is the process alive and behaving | `startup` / `shutdown` / `startup_failed` / `version_mismatch`, `warmed`, `rewarm`, `mt5_link_lost` / `_restored`, `bar_error`, `loop_error`, `config_applied` / `_refused`, `halted`, `went_live`, and a `pulse` every 15 min |
| `<inst>/<bot>-YYYY-MM-DD.log` | the prose, with the tracebacks | the human log; per-day since this pass, via `runner.DailyFileHandler` |

**The dividing line is the SUBJECT, not the severity.** A record about a setup or an order is a
decision; a record about the process that runs them is health. That is why `order_refused` (the
broker declined a real order) is a decision and `halted` (the bridge stopped placing anything) is
health — one answers *why no trade on that setup*, the other *why no trading at all*.

🔴 **A `bar` RECORD MUST CARRY THE BAR, AND FOR `extreme_leg_demo` IT CARRIED NONE OF IT UNTIL
2026-09-07.** `Ledger.bar()` reads every field with `getattr(..., None)` on purpose — so a strategy
with an unfamiliar decision shape logs what it has instead of crashing the bot, and that stays. What
it also did was read the three BAR facts FLAT off the signal, and only one of the two live shapes
answers flat. SOS Fade's signal exposes `time_ms` / `index` / `close` directly; a strategy wired
through `PassThroughSignals` hands the engine stack's own `BarState` straight past, where the bar
sits one level down on `.bar` **and its timestamp is called `timestamp_ms`**. **MEASURED on the
committed record: `extreme_leg_demo` wrote 196 of 196 rows that day with bar time, bar index and
close all null, while `sos_fade_demo` wrote 66 of 66 with all three.** The extreme leg computes all
three every bar; they were never reaching the file.

⚠ **It never affected trading** — the record is written after the strategy has decided and nothing
in the decision path reads it back. ⚠ **What it cost is the only thing the file exists for**: a row
that cannot say which bar it describes or where price was cannot be lined up against a chart, so
*why did it not trade* was answerable in principle and unreadable in practice — on the one bot whose
first setup somebody is waiting for. ✅ Fixed at `ledger._bar_field`, which looks flat FIRST (so SOS
Fade's records cannot move by a byte), then through `.bar`, treating the two timestamp names as one
fact. Ten tests, `tests/test_ledger_bar_fields.py`, five mutations RUN.

🔴 **THE RULE UNDER IT IS RULE 1 AT ITS CHEAPEST: `getattr(x, name, None)` collapses *this object
has no such field* into *that field is None*.** Both write `null`, so a bot logging blanks all day
and a bot on a quiet market produce the same file — and the file is the sole witness. `_bar_field`
returns a private sentinel to keep the two separable in code; `_bar_or_none` flattens it at the
record, because the SCHEMA has one null and leaking a sentinel into the JSON would break every
reader. ⚠ **Both halves are pinned**, or somebody deletes the asymmetry as pointless.

🔴 **AND THE MUTATION MAP WAS RUN RATHER THAN REASONED, WHICH CHANGED THE TESTS.** Two of the five
rows were first written from inspection and both were wrong — and one mutation, deleting the
sentinel outright, **survived the entire file**: every case asserted on the written ROW, and
`_bar_or_none` flattens the sentinel before it gets there, so the two behaviours are byte-identical
in the record. **A distinction living one layer below the assertions is a distinction the
assertions cannot make** — the same shape as a scaling test written against a scale of exactly 1.
It is now pinned on `_bar_field` itself.

🔴 **THE REFUSAL RECORD HAD THE SAME SHAPE BUG, AND THAT ONE COST THE BAR (fixed 2026-09-11).**
`Ledger.blocked()` read SOS Fade's field names directly; the extreme leg's refusal calls its
timestamp `ts_ms`, its price `entry_price`, and carries one `code` and one `reason`. **Every
extreme-leg refusal raised — and refusals are written BEFORE `bridge.sync`, so the raise aborted
the whole bar before its broker check and re-warmed the bot.** MEASURED on the live account:
`bar_error` at 2026-09-11 05:45:09 UTC, `rewarm` ten seconds later, and no `blocked` row for the
refusal. ✅ Both record methods now read each field under both names (plural wins whenever it is
carried, even empty — SOS Fade's `code` property answers 0 on an empty list), and a record they
cannot read is WRITTEN with the error rather than raised: `_write`'s *a log must never crash the
loop it observes* covered the file and not the fields. SOS Fade's rows do not move by a byte.
Nine tests on the two strategies' REAL classes, `tests/test_ledger_refusal_fields.py`; 8 mutations
RUN and killed. ⚠ **Reaches a bot by `git pull` plus a restart** — `algos/live/`, no promote.

⚠ **Routing is ONE dict (`ledger._DECISION_EVENTS`) and it is TEST-ENFORCED.**
`tests/test_ledger_streams.py` greps every `ledger.event("...")` call in `algos/live/` and fails if
the name is not classified, in **both** directions — an unrouted event would fall into health and
read as a process fault, and a rule for an event nobody writes any more is documentation of
behaviour that does not exist. Same shape as the news calendar's matches-nothing guard.

🔴 **The two mechanisms that make a silent death visible, because every failure worth catching here
produces NO OUTPUT.** A killed process writes nothing. A wedged loop writes nothing. A quiet Sunday
writes nothing too — which is why "the file is short today" was never a signal.

1. **Every exit the process CHOOSES writes a `shutdown` record**, with its reason and exit code,
   from `run()`'s `finally`. That is what makes the converse informative:
   **no `shutdown` record ⇒ it was killed or the box died.** ⚠ Until this pass only the clean
   Ctrl-C path wrote one — a failed connect (3), a halted bridge (4) and ten consecutive loop
   errors (6) all returned in silence, so the absence meant *killed, crashed, OR one of three
   ordinary refusals*, i.e. no signal at all. The startup of the NEXT run reads it back
   (`previous_run_clean`) and logs a warning, because **the trace of a hard kill has to be written
   by something still alive.** `None` there means UNKNOWN — a first-ever start or an unreadable
   file — and is deliberately not `True`, the same three-state rule as `mt5_link`.
2. **A `pulse` every 15 minutes** carrying link, balance, bridge state, position, last bar, bars
   seen, gap and uptime. ⚠ **The cadence IS the feature**: it is the one record whose *absence* is
   the signal, so a stall becomes a gap of known size instead of an absence somebody has to
   interpret. It is not the same thing as `bot_state.json`'s heartbeat — that file is overwritten
   in place, so it can say the bot is blind NOW and can never say for how long, or that it happened
   at all once it recovers. That is exactly what the 50-minute outage on 2026-08-04 left behind.

**Backup runs hourly, on the box** (`SYS_LEDGERSYNC`, `:20`), and nowhere else — see the ONE
MACHINE MAY COMMIT rule above. `tools/ledger_sync.py --local` reads its closed and open files off
this disk, copies them into `algos/ledger_archive/`, commits and pushes. ⚠ **Today's files are fetched too and are still being
written**, so `_whole_lines` drops a trailing partial JSON line before committing — the check is
*does the last line parse*, never *does it end in a newline*, because a record can be flushed
complete a moment before its newline lands and truncating on the newline would silently discard the
newest record on every sync. Text logs are never truncated: prose is not records.

⚠ **`closed` and `open` stay separate concepts even though both are now committed.** A closed day
is final; an open one is the best copy so far and will be fetched again. Merging them is what lets
a torn half-day later read exactly like a whole one.

⚠ **The VPS pushes since 2026-08-24 — the paragraph that stood here said it could not, and said
so for weeks after it was false.** The blocker was real (SYSTEM's credential store has no token and
no session, so `git push` BLOCKED rather than failed, measured 2026-07-31) and it was FIXED, not
worked around; the how and its accepted cost are in the section above. **The old Mac-side design
was retired because its honest cost was a backup that ran only when a laptop was open**, and a Mac
off for three days meant three days of record on one disk.

⚠ **The text log rolls by choosing a NAME, never by renaming** (`runner.DailyFileHandler`).
`TimedRotatingFileHandler` renames the live file, and renaming a file Windows holds open fails with
a sharing violation — the same trap `log_backup.py` records as *"logs are COPIED, never rotated"*.

⚠ **`log_backup.py` imports `STREAM_RE` from `live/ledger.py` rather than restating it.** Two copies
of the filename pattern drift, and the drift's symptom is a whole stream that is silently never
committed — which looks exactly like a stream that was never written.

Tests: `tests/test_ledger_streams.py` (12), `tests/test_live_health_stream.py` (13, **12 watched
red against HEAD** before the fix), `tests/test_log_backup.py` (26).

🔴 **DEPLOYING THAT SPLIT BROKE STARTING THE BOT, TWICE OVER, AND BOTH FAILURES REPORTED SUCCESS.**
Found by stopping the live bot to deploy and being unable to bring it back — not by the suite.

1. **`startup_coordinator.bot_is_running` matched the coordinator ITSELF.** In single-bot mode
   this process is `startup_coordinator.py --bot <key>`, and the check was a substring search for
   `--bot <key>` over the whole `wmic` dump, so it found its own commandline. **That is the path
   the command center's Start button drives** — the button could never start a bot, and it said
   the reassuring thing while failing: *"already running — left alone"*. ⚠ The anti-duplicate
   guard it belongs to was one day old and right in intent. **`runner.already_running()` got the
   same check right by excluding its own PID** — two implementations of one rule, one wrong, the
   shape this repo keeps meeting. The match now requires the RUNNER SCRIPT *and* the key, per
   line: the key alone says which bot, the script alone says which fleet, **only the pair says a
   running bot**, and a coordinator holding the same key is not one. ⚠ **`runner.already_running()`
   had the SAME latent race and it was found by reading, not by it biting**: it excluded its own
   PID but matched `--bot <key>` alone, and the coordinator that Popens it is still alive while it
   boots — so the runner could refuse to start the very bot it was asked for, log an error and
   return 0. Fixed the same way. **The PID rule and the script+key pair cover different impostors
   — itself, and its launcher — so both stay.**
2. **`wait_for_connection` watched `<bot>.log`, which the dated handler had stopped writing.** A
   perfectly healthy start would have timed out after 180s and been marked `offline`. ⚠ **A
   healthy start reported as a failure is worse than a silent one — it sends you to fix a bot
   that is fine.** `live_log()` resolves the newest `<bot>-YYYY-MM-DD.log` each poll, falling back
   to the plain path. ⚠ **The baseline PATH now travels with the baseline SIZE** (`log_baseline`):
   on the first start of a UTC day the bot writes a *different* file from the one measured a
   moment earlier, and applying yesterday's size as an offset into today's file slices off its
   front and hides the very line being waited for.

⚠ **`schtasks /run` reported SUCCESS for the run that started nothing**, exactly as this file
already warns. The check that caught it was `wmic` — probe the thing you are claiming, every time.

🔴 **And the commit-msg hook silently broke the unattended backup for the SECOND time in one day.**
Its exemption had been widened that morning to `*/ledger/decisions-*.jsonl` after the sync was
found refusing with a day outstanding. The split added two new shapes — `health-*.jsonl` and the
dated `.log` — and **the sync broke again on its first run**, because an exemption enumerates the
shapes that existed when somebody wrote it. ⚠ **A rule that fires on a robot's commit has no human
to read its message: it does not nag, it silently stops the job**, and a backup that quietly stops
happening looks exactly like a backup with nothing to do. Both shapes are exempt now, and the real
fix is that **the hook is driven FOR REAL against the exact paths `ledger_sync.py` writes**
(`tests/test_commit_hook_ledger_exemption.py`, 6 tests, 3 watched red) — a fourth artefact added to
the sync fails in the suite instead of at midnight. ⚠ **The exemptions stay narrow PATHS, never
`*.jsonl` / `*.log`**, and a test pins that: a future file holding a contract under either
extension must still demand its doc, the way `*.meta.json` explicitly does.

🔴 **Then `.gitignore`'s blanket `*.log` swallowed the text log — the THIRD silent break of one
backup in one day, and the quietest.** The sync fetched the file, `git status` did not list it (an
ignored file is not a changed one), `pending()` dropped it without a word, and the run printed
**"2 file(s) pushed"** having committed two of the three streams it had just downloaded. ⚠ **From
the commit side an ignored file and a file that was never written are identical** — this repo's
own two-things-one-value rule, arriving through git's config where nothing was looking. Fixed
twice over, because either alone leaves the hole open: a `!algos/ledger_archive/**/*.log`
negation, and `ledger_sync.ignored()`, which NAMES an unbackupable fetch and **returns non-zero**
rather than reporting success. ⚠ **`git check-ignore` must be read WITHOUT `-v`**: with it, git
reports the last matching pattern *including negations* and exits 0 for a path a `!` rule has
re-included — the first version of the test failed on a correctly-committable file for exactly
that reason. Tests: `tests/test_ledger_archive_is_committable.py` (5), one of them run against
**this repo's real `.gitignore`** rather than a fixture, because the rule that broke the backup
was a real line in a real file and a fixture would have been written to pass.

**The standing lesson: a rename is a contract change, and the readers of a filename are invisible
from the file that writes it.** Nothing imports `<bot>.log`; two separate pieces of the launcher
simply knew the name, the commit hook knew a third, and `.gitignore` knew a fourth. **Every one of
the four failed silently and three of them reported success.** Tests:
`tests/test_startup_coordinator.py` (10, **7 watched red**).

### `SYS_LOGREVIEW` — reading the record, because nothing did

**Built 2026-08-05, hourly, `notifications/log_review.py`.** The health stream above is only worth
writing if something reads it. Nothing did: `monitor.py` asks whether the PROCESS is there and
stamping, `deadman.py` asks whether the BOX can still talk, and neither opens a line the bot wrote.

🔴 **So the bridge could be HALTED and no alert in this system could see it** — the loop runs, the
heartbeat ticks, `wmic` lists the process, the Bots page says RUNNING, and the bot places nothing.
Same for a crash loop overnight, a terminal link lost and regained four times, a re-warm storm, or a
runtime config change the bot REFUSED (so the command center shows settings it is not using).

🔴 **A REFUSAL TO START IS ANSWERED BY A START, and all three of them now clear that way
(2026-09-04).** A failed start, a version-pin refusal and a refused settings change are one claim
with three causes, and a later successful start answers every one of them — the bot re-read the
file, re-checked the pin, and got in. Only the settings one had that rule (since 2026-08-07), so
`extreme_leg_demo` showed **NEEDS REVIEW (3)** beside a green RUNNING pill for three failures it
had already recovered from. **That pair cannot be resolved by the person reading it**, and Aaron
asked what it meant. ⚠ **It is the halt-tense defect a third time**: a past event rendered as a
standing state, sticky for the full two-day window. ⚠ **A failure AFTER the last good start is
KEPT** — that bot is down now, which is the finding's whole purpose. ⚠ **An unparseable timestamp
on either side keeps the finding**, and ⚠ **the restart-loop finding is untouched**: it counts
STARTS, not failures, so a bot flapping its way to a start is still reported.

🔴 **OPEN, OR OVER — AND ONLY OPEN IS "NEEDS REVIEW" (2026-09-13).** Aaron: *"I don't want to
manually mark anything as reviewed. The platform should know that this thing was resolved."* Eight
findings stayed lit for the full two-day window after the record showed them over: a halt that
recovered, a crash it came back from, a link drop that restored, a bar or loop error it carried on
past, a closed quiet gap, a restart loop or re-warm burst that had stopped. Each `Finding` now
carries `resolved` (why it is over, `None` while open), and `review.json` files the two apart —
`findings` / `resolved`, `level` from the open ones — so a Command Center that predates the field
still shows only what is open. ⚠ **Over is read off the record, never a timer**: a one-off is over
once the record shows the bot carried on past it (a restore, a start, a later heartbeat).
⚠ **A REPEAT is over only once the bot has run longer without one than the longest gap between
them, and three pulses at least** (`_burst_over`). The link and the loop gained a repeat finding of
their own (`mt5_storm:`, `loop_storm:`, four in the window); bar errors did not — each already
counts toward the re-warm burst. ⚠ **An over finding is still announced once, as ✅**, and its key
never moves between open and over. ⚠ **Seven older tests went vacuous the day it landed** — they
asked whether a refusal was PRESENT, and an answered one now always is — and a planted mutation
found them. The page answers what is left open between passes off the bot's own heartbeat
(`command-center/backend/CLAUDE.md` → *Open, or over*). 21 mutations run, 21 killed.

**The charter, stated so this does not grow into a second watchdog: `monitor.py` owns NOW, this owns
THE RECORD.** The watchdog answers *is it alive this minute* and restarts it; this answers *what does
today's record say happened*, including things that recovered before anyone looked. That split is why
this deliberately does NOT alert on "process gone" or "heartbeat stale" — those are the watchdog's,
and two alerts for one event is how a channel gets muted.

⚠ **It restarts nothing and starts nothing.** The watchdog owns recovery; two things issuing starts
for one bot is how a book gets doubled (measured 2026-08-04).

⚠ **Silent when clean — no "nothing to report" message, ever.** The reason `reporter.py` was deleted
rather than fixed applies here in full: a channel that is noise 95% of the time is the one nobody
reads on the day it matters.

⚠ **One alert per OCCURRENCE, not per run.** Findings carry a key containing the timestamp of the
thing that happened, so the same halt does not ping 24 times a day **and a NEW halt still does**.
Keying on the KIND of thing would alert once and then stay silent through every future incident —
the classic de-duplicating-alerter bug, and it is silent by construction. State lives in
`algos/log_review_state.json`; an unreadable state file RE-ANNOUNCES rather than suppressing, because
noisy once beats silent forever.

⚠ **Being unable to read is a FINDING, never silence** — but only for a bot whose state says it
should be running. The rule this repo has now met five times, and here the reassuring answer is the
dangerous one: a checker with nothing to say is indistinguishable from a system with nothing wrong.
The other half matters just as much: **a bot you stopped on purpose has no record to write**, and an
alarm that fires every time you stop one is an alarm you learn to ignore.

🔴 **TWO OF ITS FINDINGS FIRED ON THE DEPLOY ITSELF, SO THE CHIP NEVER WENT OUT ON A BOT ANYBODY
WAS WORKING ON (fixed 2026-09-03, Aaron's call — "since I am always working on the bots it is always
going to show that warning").** The restart-loop alarm counted every start, and four promotes inside
the two-day window is an ordinary week; its own text ended *"Expected if you deployed today"*, which
is an alarm apologising for itself. The refused-settings finding kept telling you to restart for the
full window **after** you had restarted, because it replayed a log line and never asked what happened
next. ⚠ **MEASURED on the live bot's own record for 2026-09-02/03: 2 findings before, 0 after, and
the ALERT one was red.** Both fixes are about the same thing — **an alarm that fires when you press
the button is one you learn to scroll past, and then it cannot tell you about the thing it exists
for.** This repo already paid for that lesson on the deploy workflow that told you to KILL the bot
and so tripped the silent-death detector on every restart anybody performed on purpose (2026-08-13),
and the halt wording that stayed in the present tense hours after the halt ended (2026-08-07). **This
is the third time, so treat it as a standing question rather than three incidents: for every finding,
ask what a NORMAL day of your own work does to it.**

⚠ **The restart count now reads the previous run's end as `is not True`, never `is False`** — a start
records it as clean, unclean, or `None` for *nothing on record*, and `None` may not buy the
reassuring answer (rule 1, met here for the sixth time). It is rare by construction, so counting it
costs no noise, and the wording says *recorded no clean shutdown* rather than claiming a kill.

⚠ **The refusal is dropped on any LATER start, clean or not, and that seam is deliberate.** A start
reads the settings file fresh however the run before it ended, so asking whether that start was clean
would suppress nothing while looking careful — that is the restart-loop question, not this one. An
unparseable timestamp on either side KEEPS the finding: a refusal that cannot be placed in time is
precisely the one not to drop. ⚠ **It does not fix the underlying annoyance**, which is that only the
per-trade risk figure reloads under a running bot — changing anything else still writes a refusal.
It stops that refusal outliving its own answer.

🔴 **THE PRESENT TENSE NOW NEEDS A HEARTBEAT THAT COULD STILL DESCRIBE THE PRESENT (2026-09-03).**
*Bridge is HALTED right now* was decided by the newest row on file and nothing else — so a bot that
halted and was then STOPPED went on saying *"it is still running and still looks healthy everywhere
else — check the account"* for the rest of the two-day window, with every clause of it false. It
now takes three things: the newest heartbeat says halted, the bot is meant to be running, and that
heartbeat is recent enough to describe now.

⚠ **THREE tenses, not two, and the third is the whole fix** — *it recovered* and *the record cannot
say* were sharing a value, which is the rule this module meets five times over in its own docstring.
A halt that cannot be placed in the present gets its own WARN saying so, rather than being dressed
as either neighbour. It is still a standing chip: it is the only line anywhere that will tell you a
stopped bot went down with its bridge halted.

⚠ **It is NOT a live probe and must not become one.** `monitor.py` owns *now*; this owns *the
record*. A probe here would be a second watchdog reporting one event twice, which is how a channel
gets muted. **The fix is narrower than the complaint sounds: stop ASSERTING the present tense when
the record cannot support it.**

⚠ **An UNPARSEABLE pulse timestamp keeps the present tense**, deliberately — of the two wrong
answers, over-reporting a halt sends somebody to look at an account and under-reporting hides a bot
placing nothing.

⚠ **Demoting a STALE heartbeat costs no severity**, which is what makes it safe: a bot that should
be running and has gone quiet already raises its own ALERT further down. Claiming *halted right now*
off a twenty-hour-old row is a second alarm for one event, stated more confidently than the record
allows.

⚠ **A stopped bot whose newest heartbeat said LIVE still reads as RECOVERED** — that sentence stays
true after a deliberate stop, and it is the reassuring half of the same question.

⚠ **Third time a sticky present-tense claim has been reported here**, after the halt wording
(2026-08-07) and the refused settings (earlier the same day). That is why the answer is a named
function with three values rather than another inline boolean.

🔴 **THE FLAG IS NOW WRITTEN ON EVERY RUN, CLEAN OR NOT, BECAUSE DELETING IT MADE THIS REVIEWER'S
OWN DEATH INVISIBLE (2026-09-03).** An absent file meant *nothing to review* and it equally meant
*nobody looked* — the two values this module's own docstring forbids collapsing, collapsed in the
module that forbids it. A dead hourly task left the last flag it ever wrote sitting on the Bots page
looking current, and no reader anywhere had a way to tell. **Its timestamp is now the evidence that
the reviewer is alive**, and an empty findings list is a positive statement that a run happened and
found nothing. ⚠ **Nothing on the page changed** — the Bots page has always shown the chip only for
a non-empty findings list — so this added a reader for the timestamp rather than a new alarm; the
staleness rule itself belongs to the page and lives in `command-center/backend/CLAUDE.md`.
⚠ **A clean run stamps its own level (`OK`), never `WARN` by falling through the worst-of test on an
empty list.** The page never reads it, which is exactly why it has to be right here: nothing
downstream would correct a wrong value sitting in a file. ⚠ **Do not "tidy" this back into deleting
the file when clean** — the clean case is the whole point. A flag that exists only when something is
wrong cannot tell a healthy system from a checker that stopped running.

**It reports in two places because they fail differently.** Telegram gets one message per new
finding — an alert you scrolled past is gone. `<instance>/review.json` is a standing flag the command
center renders as a **Needs review** chip on the Bots page, and it is still there tomorrow. ⚠ **Its
own file, NOT `bot_state.json`**: the runner rewrites that every poll through a read-modify-write, so
a review written into it would race the heartbeat and could be lost, or clobber a balance.

⚠ **`telegram_health_chat` in `credentials.json` sends findings to a SEPARATE chat from the one
carrying fills.** These messages are routine chatter ("reconnected twice, re-warmed"), and the day you
mute them you must not also mute your trades — the same reasoning behind the dead-man's switch using
EMAIL. Unset falls back to the main group and says which it used on stdout: an alert in the wrong
room beats no alert, which is the OPPOSITE call from `deadman_url`, where unset means the check
cannot work at all.

### `SYS_BROKERCOSTS` — the broker re-quotes its overnight rate and nothing said so (2026-09-03)

`tools/watch_broker_costs.py`, daily at 06:40 UTC. It reads this bot's symbol swap off the live
terminal and reports when the BROKER moves it. Aaron's call: the noticing is not a person's job.

🔴 **FOUR READINGS IN SEVEN WEEKS, EVERY ONE FOUND BY SOMEBODY LOOKING** — -78.29 (2026-07-16),
-79.60 (2026-08-06), -81.18 (2026-08-14), -80.54 (2026-09-02). On a strategy designed to hold
overnight it is the largest re-priceable cost, and this bot's own `_measured` block already said
*"treat swap as a rate that MOVES, never a constant"* — which is a note, not a mechanism.

🔴 **IT FIRES ON THE EVENT, NOT ON A THRESHOLD.** A threshold would be a guessed number (rule 4)
and there is no measurement saying which drift matters — the one drift that HAS been replayed came
to +0.09R, and one measurement is not a rule. So it speaks when the reading CHANGES from the last
one on record. **Silence therefore means the broker has not moved it, never *we decided it was
small enough*.** The message carries the gap to the LAB's constant as a separate fact, because
that is the one a reader acts on.

⚠ **It reads through `broker_facts.py` rather than calling MT5 itself** — that module already
refuses to report the wrong terminal's numbers, and this box runs two. ⚠ **It writes NOTHING to
`backtest/fills.py`**: re-pricing re-bases every charged figure in the repo and is a deliberate
job with its own commit, the same reason `broker_facts.py` does not rewrite `_measured`.

🔴 **THIRD TASK HERE WHOSE NORMAL STATE IS SILENCE**, after the dead-man's switch and the re-entry
watch, so it carries the same hazard and the same three answers: it announces its own failure, it
writes a health record on EVERY run, and it sends nothing on a quiet one. ⚠ **That record carries
the READING, not just a verdict** — the four values above lived in three different places
(`fills.py` comments, this bot's config, a chat log) and **a doc paragraph restating the series
from two of the three got one of them wrong.** The health stream is the one place it accumulates.

🔴 **THREE DEFECTS WERE FOUND BY RUNNING IT, NONE VISIBLE FROM READING IT, AND ONE MADE THE ALARM
UNREACHABLE.** `broker_facts.attach()` raises `SystemExit` for every reason a terminal cannot be
read — not running, not logged in, **logged into the wrong account** — and `SystemExit` is not an
`Exception`, so the failure handler let all three straight past: MEASURED, the message reached
stderr and no alert was sent. **A watcher whose failure path is silent is the thing this whole
design is built against, and it shipped that way inside the file arguing for it.** The second: the
account profile lives under `strategy_params`, not at the top level, so it refused on the live
bot's own config while that config plainly names a tier. ⚠ **The lookup is now a named function
so a test can exercise the real one** — the first test re-derived the lookup inline and would have
stayed green under the mutation that restores the bug.

🔴 **THE THIRD (2026-09-03) IS THE SAME RULE-1 DEFECT THIS FILE ARGUES AGAINST, IN THE OUTPUT
NOBODY TESTED.** The verdict is rendered TWICE — once as the Telegram message, once as the line
printed to the task log — and the log line was built from *did anything move* alone, so a run with
no previous reading printed **"nothing moved since the last reading"**, asserting a reading that
does not exist. **The Telegram half was correct throughout, and that is exactly why nothing caught
it: every test read the message.** ⚠ **Two renderings of one verdict are two places the three
states can collapse, and a test on one says nothing about the other** — the fix names the log line
as its own function so a test can reach it, and the mutation that restores the bug leaves the
Telegram test green. ⚠ **The first mutation aimed at it hit BOTH renderings and reddened a test it
had no business touching; a mutation that lands on two sites proves nothing about either.**

**Tests: 24 in `tests/test_watch_broker_costs.py`, 13 mutations watched RED with a surviving
control each.** ⚠ **One control was mis-chosen and reported a FAIL that was not one** — the
mutation compared only the long side, and the control asserted both sides move, so it died
legitimately. **A control that the mutation should be allowed to kill proves nothing.**

✅ **REGISTERED ON THE BOX 2026-09-03 and PROVEN against the live terminal**, which is a
separate fact from being written: it existed in `scripts/bootstrap_vps.ps1` for the length of a
session while the running machine had never heard of it, because nothing re-runs the bootstrap on
a pull. ⚠ **`schtasks` reporting SUCCESS is not evidence it will launch** — this repo has already
lost every task on the box for two months to exactly that, so it was proven by RUNNING the tool,
which is also how the third defect above was found. ⚠ **The proving run used the print-only flag,
and that was checked rather than assumed to be safe: the state file is written only on a real run,
so the dry run does not consume tomorrow's first reading.** ⚠ **A hand run is not the scheduled
run** — SSH runs it as the logged-in user and the task runs as SYSTEM, so the first genuine 06:40
firing is still unproven.

✅ **SWITCHED ON FOR `sos_fade_demo` THE SAME DAY (Aaron's call), with its take-profit moved
50 → 0.** ⚠ **No promote, and none should be run for it** — a promote copies `strategies/`,
`engines/` and `backtest/`, and everything this needs on the code side is in `algos/`, which
reaches the box by `git pull`. The deployed snapshot was CHECKED rather than assumed to carry the
strategy half of the seam. ⚠ **It needs a RESTART**: only the per-trade risk figure reloads at
runtime, so the running bot reports one blocked-config message and keeps its old values until then.
⚠ **With that take-profit at zero the bot banks NOTHING at a price**, so the partial-bank and
full-exit paths built on 2026-09-01/02 are not exercised by it and stay unproven. The measurement,
the warnings and what does NOT change are in the bot's own `config.json` → `_re_entry_on_2026_09_02`
— **not restated here**, because a second copy of a decision is how two files come to disagree.

### `SYS_GETSCREENRESTART` — the VPS host's Getscreen.me leaks memory, so it is restarted weekly (2026-09-13)

**Getscreen.me is the host's browser remote-access agent, not ours, and it leaks Windows handles
(~24 a minute, never freed).** After 126 days it held 4.35 million handles and 2.1 GB of
non-pageable kernel memory on this 4 GB box, leaving ~460 MB for everything else. The task's first
run freed 1.8 GB. Measurements and the two checks: `scheduler/SCHEDULER_GUIDE.md`.

- ⚠ **Restarted every Saturday 12:00 UTC, not removed — Aaron's call.** Nothing here uses it;
  switching it off is one command, in the guide.
- 🔴 **FOURTH task whose normal state is silence, and nothing on the box alarms on low memory** —
  which is how the leak went unseen for four months. Prove a run by `Last Run Time`, never by the
  `schtasks /run` exit code.
- ⚠ **No low-memory alarm, and that is a decision — Aaron's call, 2026-09-13.** What low memory
  would cost is a bot stopping or the box freezing, and `SYS_DEADMAN` catches both from OFF the box
  (`deadman.py --status` → `configured: yes`, checked that day). If this task stops, the leak took
  four months to do its damage the first time. Re-raise it only for a NEW source of memory pressure.
- ⚠ **It touches nothing a bot uses** — MEASURED on its first run: both live bots kept running,
  broker link up, no restart.

## ✅ The deal stream — MT5's own account history, backed up hourly (2026-09-17)

Each bot mirrors its account's full MT5 deal history (trades, deposits, withdrawals) into
`ledger/deals-YYYY-MM-DD.jsonl`, one file per deal day on the broker server's clock, and the hourly
sync commits it like the other two streams. It feeds the Command Center's account equity and trade
chart, and the git copy is the fallback if MT5's own history is ever gone.

- ⚠ **Written only after the history rebuilt the broker's balance to the cent** (the same check the
  account return runs), so a partial read or another account's history never lands here.
- ⚠ **A snapshot, not an append** — a day's file is rewritten whole only when it differs, and rows
  carry no wall-clock stamp, so an unchanged history writes nothing.
- ⚠ **Every bot on an account writes the same history.** A reader de-duplicates by deal ticket and
  filters by the row's account number, never by which bot's folder it came from.
- ⚠ **A missing file is "not written", never "no deals".** A bot that has not reconciled since the
  change was promoted writes nothing at all.
- ⚠ The runner's call is wrapped on its own, so a failed mirror can never cost the account return.
- Reaches a live bot only through a promote. Added to `ledger.STREAM_RE`, the sync's path pattern
  and the commit-msg exemption in the same change — miss one and the stream silently never commits.
