# De-branding the strategies — assessment and hand-off prompt

> ## ⚠ STALE SINCE 2026-09-02 — RE-SURVEY BEFORE RUNNING ANY OF IT
>
> **The Pine strategies MOVED while this plan was on hold.** Everything that was under
> `indicators/strategies/` is now under `strategies/tradingview/`, and the two research files are
> under `strategies/tradingview/research/`. See `docs/TRADINGVIEW_STRATEGY_MOVE_PLAN.md`.
>
> **What that costs this plan:** the two path references in it have been rewritten to the new
> layout, so it points at real files again — but **its §1 file counts and its reference sweeps were
> measured on 2026-08-31 against a tree that has since moved 24 files and 177 path references.
> Re-measure every count before acting on one.** The rename itself is unaffected in substance; it
> is the arithmetic that went stale.
>
> ⚠ **This file is still UNTRACKED.** It has no committed version, so nothing above is backed up
> and a second session cannot see it. Commit it before relying on it.

> # 🔴 ON HOLD — DO NOT START
>
> **Aaron's instruction, 2026-08-31: two other sessions are working this repo. Nothing in this
> plan runs until both are finished and their work is committed.**
>
> This is not caution for its own sake. This plan renames folders, classes and import paths that
> both in-flight workstreams are editing right now, and a rename landing under an unfinished
> change produces conflicts in files nobody can cleanly merge — plus §6 step 1 requires a clean
> tree before anything moves.
>
> **In flight at the time of writing (`git status`, 2026-08-31):**
>
> | Workstream | Files | Collides with |
> |---|---|---|
> | Live bot feed / ledger / dual-clock | `algos/live/bridge.py`, `feed.py`, `ledger.py`, `runner.py`; `strategies/python/mpc_sos_fade/strategy.py` + new `dual_clock.py`; 4 test files + new `test_dual_feed_merge.py` | §2.1 (the package rename), §4.1 (the ledger), §3 (the live bot) — **the worst possible overlap** |
> | Extreme Leg strategy | `strategies/tradingview/mpc_extreme_leg_strategy.pine` + its doc, `tools/build_extreme_leg.py`, `backtest/tools/pre_sos_leg*.py`, two CLAUDE.md files | §2.3 (the Pine rename) |
>
> ⚠ **The live-bot workstream is the blocker that matters.** It is editing the very strategy
> package this plan renames and the ledger this plan moves. Renaming under it would rewrite paths
> in half-finished code.
>
> **Before starting, re-check and require all four:**
>
> 1. `git status` is clean — no modified files, no untracked work from another session.
> 2. Both workstreams above are committed and pushed.
> 3. The live bot is stopped and the account is flat (§3.2).
> 4. The lab database is backed up (§4.2).
>
> ⚠ **Re-measure §1 when the hold lifts.** Every count here was taken on 2026-08-31 against a tree
> that has since moved, and the in-flight work adds new files carrying the old names.

**Written 2026-08-31. Decisions settled with Aaron 2026-08-31 (§0). Nothing has been renamed yet —
this file is the survey and the instruction set.**

**Why:** "MPC" is MentorPeak Consulting, Aaron's brother's company. Nothing in this repo that is a
strategy, a bot, a lab row, a chart label or a Telegram message may carry it. **One thing keeps the
name: the assistant indicator, which is genuinely his brother's own.**

**Who this is for:** the AI session that does the work, on a day when nothing else is running. Read
the whole file first. The danger is in §3 and §4, not in the volume in §1.

---

## 0. Decisions — SETTLED, do not re-open

| Question | Answer |
|---|---|
| Does the live bot's identity change too? | **Yes, in full.** The bot is stopped for this work and redeployed on a new version afterwards — a deploy Aaron needs anyway, so the downtime is not extra cost. |
| Rewrite the name in the diary and older docs? | **Yes.** Everything reads under the new names. |
| The old decision records that carry the old name? | **KEPT and carried forward.** They must read as one unbroken history of the same strategy under a new name. Mechanism in §4.1. |
| What keeps the MPC name? | **Only the assistant indicator, and it is renamed to MPC JARVIS.** That is his brother's own indicator, and JARVIS is what he calls it on TradingView. |
| The other indicator carrying the name but not a strategy | **Rename it.** Drop the prefix. |
| The scraped course material under `education/` | **De-brand.** It is SMC material off YouTube and a course, not MentorPeak's. |
| Teaching handouts, PDFs, logo under `docs/teaching/` and `docs/handouts/` | **KEEP, untouched.** That is his brother's company material — watermark, logo, filenames and the strategy names printed inside them. Do not edit a single file in either folder. |

**The target vocabulary:** strategies are named for what they do — SOS Fade, B-LEG, BOS, Realign,
Recovery, H4 Sweep, Extreme Leg. No prefix.

---

## 1. Size of the job — MEASURED, not estimated

Re-run these before starting; the repo moves.

| Bucket | Files | Hits |
|---|---|---|
| Everything, whole repo | 471 | 12,413 |
| Bot decision records (`algos/ledger_archive/`) | 42 | 7,769 — **contents never edited; folder moves, see §4.1** |
| Deployed snapshot (git-ignored, promote regenerates it) | ~60 | ~1,900 |
| **Actual editing work** | **406** | **4,773** |

Of the 4,773: markdown/HTML 1,886 · Pine 1,350 · Python 1,303 · frontend 162 · JSON 47 · other 25.
By subsystem: `indicators/` 1,972 · `strategies/` 888 · `command-center/` 645 · `docs/` 317 ·
`engines/` 281 · `backtest/` 262 · `algos/` 225 · `HISTORY.md` 80 · `.claude/` 63.

**The overwhelming majority are passing references inside comments and CLAUDE.md prose.** Cheap.
The ~200 that are identifiers, paths, keys and display strings carry all the risk.

```bash
grep -ril "mpc" --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.venv --exclude-dir=.venv-lint . \
  | grep -v "^algos/ledger_archive/" \
  | grep -v "^algos/markets/fx/instances/.*/deployed/" \
  | grep -v "^command-center/backend/.venv/" | wc -l

grep -rio "mpc[a-z0-9_-]*" --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.venv . \
  | sed 's|.*:||' | tr 'A-Z' 'a-z' | sort | uniq -c | sort -rn
```

---

## 2. The name map

### 2.1 Python strategy packages — folder, class, id, display

| Today | Becomes |
|---|---|
| `strategies/python/mpc_sos_fade/` | `strategies/python/sos_fade/` |
| `strategies/python/mpc_bleg/` | `strategies/python/b_leg/` |
| `strategies/python/mpc_bos/` | `strategies/python/bos/` |
| `strategies/python/mpc_realign/` | `strategies/python/realign/` |
| `strategies/python/loss_recovery/` | **unchanged** — already generic, and the working proof this shape is fine |
| class `MpcSosFadeStrategy` | `SosFadeStrategy` |
| class `MpcBLegStrategy` | `BLegStrategy` |
| class `MpcBosStrategy` | `BosStrategy` |
| class `MpcRealignStrategy` | `RealignStrategy` |
| display `MPC SOS Fade` | `SOS Fade` |
| display `MPC B-LEG` | `B-LEG` |
| display `MPC BOS` | `BOS` |
| display `MPC REALIGN` | `Realign` |

⚠ **The editor-metadata file renames with its folder.** The lab scanner looks for
`<pkg>/<pkg>.meta.json` by folder name. A folder renamed without it loses every label, group and
description on the strategy page — silently; the page still renders on raw field names.

⚠ **Three packages subclass the first one** and import its execution module. Rename the base class
first, in one pass, or all three fail to import. The lab already purges the whole strategy
namespace at once for exactly this reason.

### 2.2 Live bot keys

| Today | Becomes |
|---|---|
| `mpc_sos_fade_demo` | `sos_fade_demo` |
| `mpc_bleg_demo` | `b_leg_demo` |

**Settled: this happens.** §3 is what it costs.

### 2.3 Pine — strategies

| Today | Becomes | Title today | Title becomes |
|---|---|---|---|
| `mpc_strategy.pine` | `sos_fade_strategy.pine` | `MPC A+ Strategy` | `SOS Fade Strategy` |
| `mpc_strategy_export.pine` | `sos_fade_strategy_export.pine` | `MPC A+ Strategy Export` | `SOS Fade Strategy Export` |
| `mpc_b_leg_strategy.pine` | `b_leg_strategy.pine` | `MPC B-LEG Strategy` | `B-LEG Strategy` |
| `mpc_b_leg_strategy_export.pine` | `b_leg_strategy_export.pine` | `MPC B-LEG Strategy Export` | `B-LEG Strategy Export` |
| `mpc_bos_strategy.pine` | `bos_strategy.pine` | `MPC BOS Strategy` | `BOS Strategy` |
| `mpc_bos_strategy_export.pine` | `bos_strategy_export.pine` | `MPC BOS Strategy Export` | `BOS Strategy Export` |
| `mpc_h4_sweep_strategy.pine` | `h4_sweep_strategy.pine` | `MPC H4 Sweep` | `H4 Sweep` |
| `mpc_h4_sweep_strategy_export.pine` | `h4_sweep_strategy_export.pine` | `MPC H4 Sweep Export` | `H4 Sweep Export` |
| `mpc_extreme_leg_strategy.pine` | `extreme_leg_strategy.pine` | `MPC Extreme Leg` | `Extreme Leg` |
| `mpc_realign_strategy.pine` | `realign_strategy.pine` | `MPC REALIGN` | `Realign` |
| `mpc_recovery_strategy.pine` | `recovery_strategy.pine` | `MPC A+ Strategy + Loss Recovery` | `SOS Fade + Loss Recovery` |

Their mirrors under `strategies/tradingview/docs/` rename to match.

### 2.4 Pine — indicators

| Today | Becomes | Note |
|---|---|---|
| `indicators/engines/mpc_assistant.pine` | **`indicators/engines/mpc_jarvis.pine`** | **KEEPS the MPC name.** Its declared title already reads `MPC- JARVIS` — leave the title exactly as TradingView has it; changing it changes the filename TradingView gives future exports for no gain. |
| `indicators/engines/mss_sweeps_mpc.pine` | `mss_sweeps.pine` | drop the prefix |

🔴 **Renaming the assistant file is not a small edit: ~130 files reference it by name.** Every
engine's docstring, `types.py`, comparison harness and CLAUDE.md names it as its Pine source, plus
the engine-audit slash command, several backend chart-overlay services and their tests. All of
those must point at the new filename. **The audit command in particular must compare against the
renamed file, or it silently audits a path that no longer exists.**

### 2.5 Docs named after a strategy

`docs/MPC_SOS_FADE_SPEC.md` · `MPC_SOS_FADE_BUILD_PLAN.md` · `MPC_SOS_FADE_SECONDARY.md` ·
`MPC_BOS_SPEC.md` · `MPC_BOS_OPTIMIZATION.md` · `MPC_REALIGN_SPEC.md` · `MPC_FB_SPEC.md` → drop the
prefix.

`strategies/python/mpc_sos_fade/mpc_sos_fade_bugs.md` and `mpc_sos_fade_optimization.md` →
`sos_fade_bugs.md`, `sos_fade_optimization.md`.

**Every inbound link moves with the file.** Grep for the old filenames AFTER the move, not before.

### 2.6 The keep-list, in full

1. **The assistant indicator**, renamed to `mpc_jarvis.pine`, declared title untouched.
2. **`docs/teaching/` — every file, unedited.** Handouts, PDFs, HTML sources, SVG artwork and the
   logo asset. They carry his brother's company watermark and they are his company's material.
3. **`docs/handouts/` — every file, unedited.** Same reason.
4. **The bytes inside every decision record** (§4.1) — the stamp on an old record is a true
   statement about what the bot was called when it wrote the line.

⚠ **The strategy names printed INSIDE the handouts stay too.** Do not "helpfully" rename a
strategy mentioned on a page of his brother's teaching material. The filenames do not change
either, so every inbound link from elsewhere in the repo stays valid with no edit.

Everything else goes generic — including the scraped SMC course material under `education/`, whose
mentions of the old strategy names are updated like any other prose. That material is SMC content
off YouTube and a course, not MentorPeak's.

### 2.7 What is NOT part of this rename

**`A+` stays.** It is the strategy's own word for its setup and appears in Pine titles, chart
overlays and alert text. It is not a company name. Do not fold it into this job.

---

## 3. The live bot — why this cannot be a find-and-replace

`mpc_sos_fade_demo` is ARMED and trading a PU Prime ECN demo account. The bot key is an identity,
not a label, and it is load-bearing in six places:

1. The instance folder name, on the Mac and on the Windows box.
2. The decision-record folder name, and a field inside every record.
3. The process lock the bot takes before touching the terminal. **A bot running under the old key
   and one restarted under the new key do not see each other's lock** — so renaming with the bot up
   can put two processes on one terminal.
4. The log filename, opened by path by the Command Center's log viewer and the log-backup task.
5. The text stamped on every broker order (`<key>-LIMIT`, `-ENTRY`, `-CLOSE-<reason>`, `-PARTIAL`).
   ✅ **Nothing reads it back** — reconciliation is by magic number, an integer, unaffected. Old
   deals keep the old string on the broker forever and cannot be changed.
6. Everywhere a human types it: the deploy commands in the root CLAUDE.md, the trading-box tools,
   the Telegram bot, the promote and stop workflow.

### 3.1 The version pin will refuse to start the bot

The most likely way to break the live bot, and it is not obvious.

The bot hashes its deployed code at every startup and **refuses to run if the hash moved**. That
hash folds in **the root folder's name and each file's path relative to its root**, deliberately, so
that moving a file between packages registers as a change. So renaming the folder changes it, and
renaming the class changes file contents which changes it too.

**Consequence:** after the rename the bot will not start until re-promoted. It fails CLOSED, which
is the safe direction — but it makes this a stop → rename → promote → restart operation, never an
edit.

A second hash, used by the lab scanner, folds in **filenames only, not the folder**. Do not reason
from one to the other; they answer different questions.

### 3.2 Order of operations on the live side

```
1. Confirm the account is FLAT — no open positions, no resting limit orders.
   A resting limit is the trap: it survives a restart, carries the old comment string,
   and counts against the account-level risk cap.
2. Stop by ASKING, never by killing:
     ssh forexvps "echo stop > C:\trading\algos\markets\fx\instances\mpc_sos_fade_demo\stop.request"
   Wait ~30s, confirm the process is gone by commandline.
   A hard kill skips the shutdown record and makes the next startup cry wolf.
3. Do the whole repo rename on the Mac. Commit. Push.
4. On the VPS: git pull, then RENAME THE INSTANCE FOLDER BY HAND.
   The folder is not in git — its config is, its deployed snapshot is not.
5. Re-promote under the new key. Read the dry-run first: expect a hash change, and expect it
   to list any config field the new code has never heard of.
6. Restart via SYS_STARTUP. Read the first minute of log: it must report the new version, and
   must NOT say "the previous run ended without shutting down."
7. Confirm from the broker side that the first new order carries the new comment prefix.
```

⚠ **Never `taskkill /f /im python.exe`.** It kills the trading bot, the Telegram bot and both
agents. It has cost three days of live downtime once already.

⚠ **A new config field is PROMOTED before it is STATED.** The running bot validates its config
against the code it is running every 10 seconds; a key the code has never heard of fails the parse
on every poll and buries the log.

---

## 4. The irreversible parts

### 4.1 The decision records — KEPT, and carried across the rename unbroken

`algos/ledger_archive/mpc_sos_fade_demo/` holds **2,518 decision records over 2026-07-31 →
2026-09-01** — 1,874 bar snapshots, 290 setups a rule refused, 279 armed-but-never-filled, 71
events, 4 trades — plus 54 health files and 23 daily logs. The 569 refusals and misses exist
nowhere else; no broker statement contains a decision not to trade.

**Requirement: after the rename this must read as one continuous history of the same strategy.**

**How the records are actually addressed — this is what makes it easy.** Every reader builds the
path from a bot key it was already given (`<archive>/<bot>/ledger/decisions-YYYY-MM-DD.jsonl`).
The bot name stamped inside each line is a LABEL, not a lookup key: **nothing in the repo filters
on it** — verified, not assumed. So continuity is a folder move plus a note, and no record is ever
edited.

**The mechanism, in four parts:**

1. **`git mv` the archive folder to the new key.** History and new records then sit in one place,
   addressed by one name, and every existing tool finds all of it with no code change.
2. **Do not touch a single byte inside any record.** An old line saying the old name is a TRUE
   statement about what the bot was called that day. Rewriting it would be falsifying a record to
   make a rename look tidy, and this repo already has a hard rule that a decision record is never
   edited — not even to fix a merge.
3. **Write a provenance file into the folder** (`RENAMED.md`, committed): the old key, the new key,
   the date and time of the switch, and one sentence saying same strategy, same account, same magic
   number, records before that timestamp carry the old stamp. That is what a future reader hits
   when the stamp changes mid-folder.
4. **State the real join key, because it is stronger than the name ever was.** The magic number
   (770115) and the account number do not change. Those are what actually tie every record to every
   deal on the broker, and they are untouched by this rename. The name was never the identity.

⚠ **Move the in-progress ledger on the VPS in the same step.** The live instance folder is renamed
by hand (§3.2 step 4); its `ledger/` subfolder goes with it, or the day splits across two folders
and the sync copies half a day into an orphan path.

⚠ **The day of the rename will have both stamps in one file.** That is correct and it is exactly
what the provenance file exists to explain. Do not split it, and do not backfill it.

⚠ **Check the unattended sync still runs afterwards.** It commits and pushes twice a day with
nobody watching. A rule that fires on a robot's commit does not nag — it silently stops the job,
and that has already happened twice here. The commit hook exempts the archive by PATH
(`*/ledger/decisions-*.jsonl`), so confirm the exemption still matches once the folder is renamed.

⚠ **The archive is committed to git and the live instance folder is not.** Renaming one does not
rename the other; both are needed.

### 4.2 The lab database

`command-center/backend/data/lab.db` is git-ignored and machine-local — 54 MB, no second copy.
**The strategy id is the package folder name lowercased**, so a rename creates a new row and orphans
everything pointing at the old one: 42 completed runs on SOS Fade, 4 on B-LEG, 4 stacks joined
through those runs, and report folders on disk named after the id.

```sql
-- back the file up first
UPDATE backtest_runs SET strategy_id = 'sos_fade' WHERE strategy_id = 'mpc_sos_fade';
UPDATE backtest_runs SET strategy_id = 'b_leg'    WHERE strategy_id = 'mpc_bleg';
UPDATE backtest_runs SET strategy_id = 'bos'      WHERE strategy_id = 'mpc_bos';
UPDATE backtest_runs SET strategy_id = 'realign'  WHERE strategy_id = 'mpc_realign';
DELETE FROM strategies WHERE id LIKE 'mpc_%';   -- the scanner re-creates them under new ids
```

Then rename the matching `reports/lab/<stack>/solo/<id>/` directories, re-run Scan Strategies, and
**open one old run in the UI** — chart, trades and metrics — before calling it done.

⚠ Aaron's brother has his own clone with his own database. Ship the migration as a committed,
idempotent one-shot script, not as SQL typed once.

### 4.3 The Pine parity gates

Rule 22: no engine or strategy change is committed before its comparison harness has run and passed
on a real TradingView export.

- The harness takes the export CSV **as an argument**, so existing exports stay valid after a title
  change.
- But exports are git-ignored scratch, so **which gates can run depends on what is sitting on that
  machine.** Last check: 9 of 14 could not run for want of an export.
- **Only a human can do the TradingView half** — paste each renamed script in, save under the new
  title, re-export. Book that separately. The repo rename must not block on it; the commit says
  honestly which gates ran and which had no export.

---

## 5. Real identifiers, not prose — the ones a careless replace gets wrong

| Where | What |
|---|---|
| `algos/markets/fx/instances/*/config.json` | bot key, display name, strategy package, strategy class, plus the long measurement notes |
| `algos/live/instance.template.json` | the same four fields — the template every future bot is copied from |
| `algos/shared/bot_state.py` | two maps: key → instance path, key → display name |
| `algos/bots/startup_coordinator.py` | per-bot launch entries: key, argv, log path |
| `algos/notifications/monitor.py`, `deadman.py` | display names used in **Telegram alert text** |
| `command-center/backend/routers/bots.py` | the bot registry: key, display name, task-name string |
| `command-center/frontend/.../ChartPanel/index.tsx` | a display-name fallback drawn on charts |
| `.claude/mcp/check_tradingbox.py`, `check_lab.py` | fixtures asserting exact bot keys and strategy ids — these WILL go red, and that is them working |
| `.claude/hooks/check_guard.py` | fixture paths naming strategy files |
| `.claude/commands/audit-engines.md` | **points at the assistant indicator by filename — must follow it to `mpc_jarvis.pine`** |
| `ruff.toml` | the formatter carve-out is BY PATH |

🔴 **The formatter carve-out is the sneaky one.** The engine and strategy trees are excluded from
formatting by path, because rule 22 says their gates must pass before they change. A renamed path
not updated in that config drops out of the exclusion, and the next repo-wide format reformats the
LIVE strategy with nothing going red. That exact failure has happened here before.

---

## 6. Order of work

Each stage is committable and leaves the repo working.

1. **Back up** the lab database. Read `git status` — the tree must be clean, with nothing
   half-finished from another session. Stage by path, never `git add -A`.
2. **Stop the live bot** (§3.2 steps 1–2). Everything below assumes it is down.
3. **Python packages**: folders, metadata files, classes, imports. Run `scripts/run_all_tests.sh`;
   expect name failures in the fixture checks, fix, re-run to green.
4. **Update the formatter carve-out in the same commit as the folder rename.** Not later.
5. **Live wiring**: instance config, template, state maps, startup coordinator, Telegram display
   names, bot registry.
6. **Lab database migration** (§4.2), then Scan Strategies, then open one old run.
7. **The assistant indicator** → `mpc_jarvis.pine`, and the ~130 references that follow it,
   including the audit command.
8. **Frontend**: the real display strings, then the comments.
9. **Pine strategies**: files and titles. Commit with an honest note on which gates ran and which
    had no export. Book the TradingView session separately.
10. **Docs and the diary**: renamed spec files with their inbound links, then the prose sweep. Last,
    because it is the biggest and least dangerous — a mistake here must not hide one above it.
11. **Move the decision archive** and write its provenance file, per §4.1. Never edit a record.
12. **Re-promote and restart the live bot** (§3.2 steps 3–7).
13. **Final sweep**: re-run the token-frequency command from §1 and read every remaining hit by
    hand. What is left should be the JARVIS indicator and nothing else.

---

## 7. How you know it worked

Not "the tests pass." Each is a separate claim needing its own check.

- `scripts/run_all_tests.sh` green end to end — all suites plus the guard, MCP and frontend checks.
  It is a person's command; no hook runs it.
- The live bot **started**, reported the new version, and did NOT say "the previous run ended
  without shutting down."
- Its first new order carries the new comment prefix — read off the broker, not off our log.
- A decision record for the day after the restart exists under the new key, the unattended sync
  pushed it, and the folder still holds every pre-rename day alongside it.
- The provenance file is present and its dates match where the stamp actually changes in the records.
- One pre-rename backtest run opens in the Command Center with chart, trades and metrics intact.
- Strategy pages still show labelled, grouped parameters — proof the metadata files came across.
- A Telegram fill alert and a setup alert both arrive under the new display name.
- The remaining hits are the JARVIS indicator, the two handout folders, and the old stamps
  inside historical records — nothing else.

⚠ **A green suite says the code agrees with itself.** It says nothing about the broker, the VPS
folder, the database or Telegram. Those four are checked by looking at them.

---

## 8. The prompt to hand a future session

> Read `docs/DEBRAND_RENAME_PLAN.md` end to end before doing anything. It removes the "MPC" prefix
> from every strategy, bot, lab row, chart label and Telegram message in this repo. Three things
> keep the name and are listed in §2.6: the assistant indicator (renamed to `mpc_jarvis.pine`, its
> declared TradingView title left alone), and the two handout folders, which are not to be edited
> at all. The bot's decision records are KEPT and carried across unbroken — §4.1, and no record is
> ever edited.
>
> First check the HOLD block at the top of that file: this work was blocked on two other sessions
> finishing, and it does not start until `git status` is clean and both are committed. Then confirm
> the live bot is stopped and the account is flat, and back up the lab database. Then work §6 in order, committing at each stage.
> Follow the repo's own rules — the owning CLAUDE.md lands in the same commit, a money-path change
> names its proof in the message, never `--no-verify`, never `git add -A`, never a hard kill on the
> trading box.
>
> Re-measure §1 rather than quoting it; this file was written on 2026-08-31 and the repo moves.
> Finish with §7 and tell me which of those checks you actually performed and which you could not.
