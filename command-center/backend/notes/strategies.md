# Notes — Strategies: scanning, versions, files and metadata

The strategy scanner, versioning, file deployment, the Strategies page, meta-file keys (TL;DR, display_under, chart_tag). Moved VERBATIM out of `command-center/backend/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## Strategy file deployment (Pass 2)

Live behavior. NT8 agent endpoints: `GET/POST/DELETE /files/strategies/<filename>`, `POST/GET /compile`. NT8 strategy folder: `C:\Users\Administrator\Documents\NinjaTrader 8\bin\Custom\Strategies\`. Detail is in git history (Pass 2).

**Gotchas:**
- **Compile (NT8):** `nt8_compile_runner.py` uses pywinauto F5 via NinjaScript Editor (`NCompile.exe` does not exist on this install). **Success** = `NinjaTrader.Custom.dll` mtime advances (NT8 rewrites it on every successful compile). **Failure** is read straight from the editor's UIA error grid — NT8 keeps F5 compile errors ONLY in that in-memory grid, never in any trace/log file (verified: the trace/log dirs carry zero compile output), so polling logs can't surface them. The runner scrapes the grid rows (`ORB.cs  Identifier expected  CS1001  1  16`) and emits each as an `ERROR:` line, which the `CompileModal` renders one per line. It fails **fast** (~6–10s, after a 6s grace for the grid to repopulate) instead of always waiting the full 90s. Guardrails: real error rows are trusted unconditionally; the "errors must be resolved" status marker only counts if it's *fresh* (captured before vs after F5, so a stale marker from a prior failed build can't false-trip); if the grid read finds nothing it still fails fast with an honest "open the editor" message; a true hang falls back to the 90s timeout. The NT8 agent spawns the runner as a fresh subprocess per compile, so a runner change is live on `git pull` alone — no agent restart. **Note:** sync-status compares only the hashes command-center itself deployed/compiled — it never re-hashes the live VPS file, so a file hand-edited directly on the VPS (bypassing deploy) still shows green "In sync"; a failed compile never advances `compiled_source_hash` (`mark_runner_compiled` runs only on `status == "success"`), so the badge is honest for the normal deploy→compile flow.
- **Compile (MT5):** `mt5_agent._run_compile` compiles each `.mq5` explicitly (`metaeditor64.exe /compile:<file> /log`) and confirms success the same way NT8 does — by mtime. It records each `.ex5` mtime before compiling and requires it to advance afterward; MetaEditor's exit code is unreliable and the directory form (`/compile:<dir>`) could silently no-op, reporting a stale `.ex5` as success. A file whose `.ex5` mtime does not move is a hard failure (`status: failed`) with the compiler `.log` lines surfaced in `errors` — never reported as success. **Warnings** are scraped from the same `.log` and returned in `warnings`, but the match requires the `": warning"` token (MQL5 format `file(line,col) : warning 123: msg`), NOT a bare `"warning"` substring — MetaEditor's trailing summary line `Result: 0 errors, 0 warnings, …` contains the word "warning" and a loose check false-positived a clean build as "1 warning". **The MT5 agent is a long-running process** (not respawned per compile like the NT8 runner), so an agent-side change like this is live only after `git pull` on the VPS **and** restarting the `MT5AgentRDP` schtask — never a blanket `taskkill python.exe` (that also kills the NT8 backtest agent).
- **Upload limit:** 256 KB, enforced on both agent and backend router.
- **Lock detection:** agent tries `r+b` open before upload/delete; `IOError` → HTTP 423.
- **Sync-status:** `GET /strategy-files/sync-status` — **content-aware** (no longer presence-only). It reads the local source **live from disk**, hashes it (md5, same as the scanner via `strategy_scanner.source_hash`), and compares to the recorded deployed/compiled hashes: `needs_deploy = local_hash != deployed_source_hash`, `needs_compile = deployed_source_hash != compiled_source_hash`. `in_sync = file_exists_on_vps AND not needs_deploy`. Also returns `current_version` / `deployed_version` / `compiled_version`. It lazily registers the live hash (`ensure_strategy_version`) so the current version always resolves even before a re-scan. **Since 2026-08-06 an unreachable agent degrades instead of 502-ing** — see *The Strategies page — the 2026-08-06 audit* below.

## The scanner read the MODULE and hashed the FILES — so a stale row could not be fixed by scanning

🔴 **Fixed 2026-08-06.** `exec_time_stop_mode` was flipped `"Off"` → `"Before TP1 only"` in
`strategies/python/sos_fade/config.py`, the scan reported success, and the Run modal went on
offering **Off**. Clearing `source_hash` by hand in sqlite was the only way out.

`_parse_python_package` called `importlib.import_module`, which returns whatever is already in
`sys.modules`. **The backend is a long-running process, so the FIRST import of a strategy pins its
config dataclass for the life of that process** — and uvicorn's `--reload` watches `backend/`, not
`strategies/`, so editing a strategy never restarts it.

⚠ **On its own that is an ordinary staleness bug. What made it dangerous is that it SEALS ITSELF.**
`_python_source_hash` reads the FILES while `_py_param_schema` reads the cached MODULE, so a scan
after an edit writes the **new hash beside the old defaults** — and `needs_rescan` compares only the
hash. The row is satisfied for ever; every later scan skips it. **Nothing reports anything**: the
"Needs scan" pill clears, the scan says `updated`, and the lab keeps serving a default the strategy
no longer has. This repo's *no data vs cannot ask* rule, arriving as *this is current vs I last
looked before you changed it*.

`services/strategy_import.py` is the one seam: `purge_strategy_modules()` then
`import_strategy_package()`. Both `strategy_scanner.scan_strategies` and `python_runner._resolve`
go through it.

⚠ **`python_runner._resolve` had the identical bug and it is the worse half** — a backtest replaying
a strategy the repo no longer contains produces an entirely normal-looking result describing code
nobody can read. It purges too, once per job.

⚠ **Purge the whole `strategies.python` namespace, never one package.** `b_leg` imports
`sos_fade`'s execution module and sorts BEFORE it, so a per-package purge would re-import the
dependent against a still-cached dependency — the same mixed reading, one level down.

⚠ **The `strategies` ROOT is deliberately left cached** (it is an empty namespace package carrying
no strategy source). In a test that matters and is called out in the fixture: another test imports
the real `strategies` first, which pins `__path__` to the monorepo, and a `tmp_path` probe package
is then never found.

⚠ **Dropping a module from `sys.modules` does not invalidate references anything already holds** —
an in-flight backtest keeps the classes it was built with and finishes on them. That is what makes
this safe to call from a request handler.

✅ **Proven against the LIVE backend, not only by test.** With the strategy already cached in the
running process, `config.py` was edited to `"Always"`, one scan reported `updated: 1`, and
`GET /strategies` returned `Always`; reverting and re-scanning returned `Before TP1 only`. 5 new
tests (698 green), **4 of them watched RED with `purge_strategy_modules` neutered** — the fifth is
kept and LABELLED vacuous, since it pins idempotency and passes either way.

**The standing lesson is narrower than the label-vs-code refrain and worth keeping separate: when
one fact is derived from two reads, they must be reads of the same thing.** A freshness check whose
marker is read from disk and whose payload is read from memory does not merely go stale — it
records that it is up to date, and that record is what stops anyone ever finding out.

## A scan rewrites a Python row whose SCHEMA it would build differently (2026-09-13)

`strategy_scanner._same_schema`. A python row was re-written only when the package's files or its
meta moved, so a change to the SCANNER never reached a strategy whose source was untouched. The
python skip now also requires the stored `param_schema` and `default_params` to equal what this
scan built (canonical JSON — the stored side has been through a round trip). ⚠ **`needs_rescan`
does not ask it**, so a scanner change shows no *Needs scan* pill; the next Scan applies it.

**First use: the six instrument fields (`_PY_FOUNDATIONAL`) have page names**
(`_PY_FOUNDATIONAL_WORDS`) — the finished-run panel's *Instrument & broker* fold read `mintick` and
`daily close hour ny` on every python strategy. A strategy's meta.json still wins where it names
one. ⚠ Every field in the set needs a name; `tests/test_scanner_instrument_names.py` holds the two
key sets together. 2 mutations planted in memory, 2 killed.

## The Strategies page — the 2026-08-06 audit

Aaron asked for a full audit of the page — Strategies tab, Deployed tab, Scan — with one reported
symptom: *"if the NT8 agent is down I get this annoying error about remote end closed connection
without response, every couple of seconds."* The toast storm is the shallow half. **The reason it
was a storm and not a banner is that every one of these endpoints treated an unreachable agent as
a fatal error rather than as an unanswered question**, and the page polls.

🔴 **A dead NT8 agent blanked the status of every strategy, including MT5 and Python ones.** Both
`GET /strategy-files` and `GET /strategy-files/sync-status` raised a 502 on any NT8 exception while
swallowing an MT5 one with a bare `pass`. **The consequence on the page is worse than a missing
badge: a row with no sync object rendered no status pill and a Run button — so a strategy that
needed deploying looked ready to run.** Both endpoints now return an envelope
(`StrategyFilesResponse` / `StrategyFileSyncResponse`) carrying `files`/`statuses` plus `nt8_error`
and `mt5_error`, and both platforms are caught symmetrically.

⚠ **The split that makes the degraded response worth serving: `needs_deploy` and `needs_compile`
survive an unreachable agent, and `file_exists_on_vps` / `in_sync` / `is_compiled` go `None`.**
`needs_deploy` is the LOCAL source hash against this app's own deploy record — it is answerable
with the VPS switched off — while the other three are claims about the box. Nulling everything
would have been safe and useless; nulling nothing is the defect above. **Ask of each field whether
the thing that answers it was reachable, not whether the request succeeded.**

⚠ **`is_compiled` defaulted a missing column to `1`** (`s.get("is_compiled", 1)`) — a fabricated
COMPILED, this repo's own rule broken in its usual direction. `None` now, and the page renders no
claim rather than a green one.

🔴 **`nt8_running` and `nt8_sa_visible` initialised to `False` in `_build_health`**, so with the
agent down the sidebar reported *NinjaTrader is not running* — a measurement nothing took, and it
was exactly wrong on 2026-08-06: NinjaTrader was open on the VPS the whole time the agent was
wedged. Both are `Optional[bool] = None` now, the same three-state contract as `mt5_connected`.

**MT5 `needs_compile` was hash-only, so deleting the `.ex5` off the box left the row reading "In
sync".** MT5 loads the compiled artefact, so its absence is the question — `needs_compile` is now
also true when the source matches its deploy record and `is_compiled` is `False`.

**`POST /strategies/{id}/deploy` 500'd on a python strategy** — a python strategy is a package
DIRECTORY, so `read_bytes()` raised `IsADirectoryError`. It is a 400 that says why. Latent (the UI
never offers the button), which is precisely the kind of endpoint something else calls later; the
existence check also became `is_file()`. **`GET /strategies/{id}/deploy-status/{job}` served any
job from any strategy's URL** — it 404s on a mismatch, so the path segment means something.
`_deploy_jobs` is an `OrderedDict` capped at 50; nothing had ever removed an entry.

**A python package whose import failed was indistinguishable from one that is not a lab strategy** —
`_parse_python_package` returned a bare `None` for both. The row kept its STALE param schema,
`needs_scan` stayed true for ever, and the scan reported success with *0 updated*: a silent failure
whose only symptom was a pill that would not clear. It returns `(row, error)` now and the error
lands in `ScanResult.warnings`, which the frontend toasts. **A package that simply does not declare
`LAB_STRATEGY` stays silent — that is the normal state for a helper package, not a fault.**

**`is_orphan` is on the strategy row, not only in a scan result.** The Reconcile button was gated on
`scan.data?.orphans` — mutation state — so a strategy whose source file had been deleted was
invisible on a fresh page load until somebody happened to press Scan. `strategy_scanner.is_orphan`
is the read-only per-row twin of `_detect_orphans`. **A standing fact belongs on the row that states
it, not in the result of the action that last noticed it.**

**Tests:** 16 new (693 green). ⚠ **A clean fail-watch against `HEAD` was IMPOSSIBLE here and the
honest note is that it was not done** — the two endpoints changed shape from a bare list to an
envelope, so the old frontend fails against the new backend for reasons unrelated to any defect.
Non-vacuity was established by **mutation instead**: each fix was removed in turn and the naming
test confirmed red. That found a real hole — see `frontend/CLAUDE.md` → *The Strategies page*.

## A strategy may declare which row it is LISTED UNDER — `display_under` (2026-08-21)

`LAB_STRATEGY["display_under"]` holds another strategy's id; the Strategies page draws the
declarer nested beneath it. It travels the same way `requires_source` does — package → scanner →
`strategies.display_under` (TEXT, nullable) → `Strategy` → the page.

⚠ **DISPLAY ONLY, and this is the whole contract.** It restricts nothing: a nested strategy is
scanned, run, stacked, optimized and deployed exactly as a top-level one, and the recovery rule
can still be ticked under ANY parent in the stack builder whatever it is listed under here
(`recovery_parent` decides that, read off the request).

🔴 **The tree is declared by the PACKAGES, never listed in the page.** A page holding its own map
of which strategy belongs to which goes stale the first time somebody adds one, and the symptom is
a correct-looking list that is quietly wrong.

⚠ **`None`, never `""`** — an empty string reads as a declared parent in some checks and as no
parent in others, which is the same "no" / "cannot ask" collapse as rule 1.

⚠ **A typo'd parent id fails SILENTLY** — the row renders at the top level, which is precisely
what a strategy with no parent looks like, so nothing on screen is wrong and the nesting has just
gone missing. `test_every_declared_parent_IS_a_real_strategy` is the only thing that catches it.

🔴 **THE EXTREME LEG WAS MOVED BACK OUT TO THE TOP LEVEL ON 2026-09-02 (Aaron: "move it to
root"), AND THE REASON GENERALISES TO WHOEVER DECLARES THIS FIELD NEXT.** It had nested under the
SOS Fade bot on the same leg-of-one-move argument B-LEG uses, and that argument was true. **An indent
reads as "child of", and that bot is a SIBLING** — its own Pine source, its own parity gate, and it
runs standalone in any stack on any instrument. What made it misread is that ONE VISUAL LEVEL WAS
CARRYING TWO RELATIONSHIPS: `loss_recovery` sits at that same indent and genuinely cannot run
without its parent (`requires_source`, refused at every endpoint that starts a job). A row that
cannot exist alone and a row that competes as an equal were drawn identically. ⚠ **B-LEG was NOT
moved** — only the row Aaron named — so whether the same reasoning applies to it is open, not
decided. ⚠ **Before declaring this field, ask whether the relationship you mean is DEPENDENCY or
FAMILY.** The page can only draw one of them.

**Tests:** `tests/test_strategy_nesting.py` (8 — two added with the move above, pinning that the
row is top-level AND that it stayed standalone-runnable, both watched RED by mutation), watched RED by seven mutations — dropping the
field, returning `""` instead of `None`, a typo'd parent, a missing declaration, a strategy listed
under itself, dropping the B-LEG declaration, and giving B-LEG the standalone-refusal flag.
MEASURED live: a rescan updated 3 rows and the two grouping values landed in the DB.

🟢 **B-LEG joined the tree on 2026-08-23, and the interesting part is the eleven days it did not.**
Aaron asked for it in the same breath as the recovery rule. It was built, then REVERTED, because
rule 22 forbids committing a changed strategy package until its parity harness has run GREEN on a
real export — and the only B-LEG export on disk was red. **Byte-identically red at HEAD, so the
nesting had not caused it; a pre-existing red is still a red.** What shipped instead was a test
asserting the OPPOSITE — B-LEG is NOT nested — with the reason in its docstring. That tripwire went
red the moment the declaration was added, which is what put the gate back in front of whoever added
it. It ran green on a fresh export (`engines/VANTAGE_XAUUSD, 5_f8228.csv`, 20,573 M5 bars, identical
on every bar from 0) and the tripwire was replaced by the positive test in the same change.

⚠ **The transferable bit is the SHAPE, not this feature:** when a rule blocks a small change, the
thing to ship is a test that fails when somebody tries again, not a comment nobody reads and not a
branch nobody remembers. A comment saying *"do not add this yet"* is invisible to the next person
who adds it.

## The TL;DR is a meta-file key, resolved on the PAGE (2026-09-13)

`tldr` in `<Strategy>.meta.json`, a list of `{text, show_if?}`, is read by
`_read_strategy_overview`, carried by all three row builders, stored as JSON in `strategies.tldr`
and served on `Strategy.tldr`. Aaron: *"something that looks at what the default settings of a
strategy are and tells me … in six bullets."* Page half: `../frontend/CLAUDE.md` → *The strategy
page leads with a TL;DR*.

- ⚠ **The backend fills nothing.** `{param}` tokens and `show_if` are resolved on the page against
  the schema's DEFAULTS, through the editor's own token rule and condition evaluator — never a
  third copy of either.
- ⚠ **A bullet with no text, a non-object, and an EMPTY `show_if` are dropped at the scan.** Both
  evaluators read `{}` as "holds nothing", so a kept `{}` would hide its bullet for ever.
- ⚠ **Migration-only column, like `chart_tag`** — the `strategies` CREATE runs before the migration
  list. NULL (a row scanned before the column) reaches the page as `[]` through the model's
  validator, and the page then shows the four-step flow. **A meta edit needs a Scan.**
- 🔴 **`tests/test_strategy_tldr.py` is the guard, because every failure it catches is SILENT on
  the page.** Every registered strategy carries 3–7 one-line bullets; every token names a real
  number, choice or text setting (an on/off token would print `true`); every `show_if` names a real
  setting; and **every bullet SHOWS at the defaults**, so a default that moves fails the build
  instead of quietly shortening the summary. Evaluated with `stress_tester._reader_for` /
  `_cond_holds`, the twin of the page's reader.
- ⚠ **It describes defaults, never results** — no R, trade counts or dates in a bullet, for the
  reason the meta's `desc` carries none: nothing re-measures a UI string.

## Strategy versioning (content-addressed)

`strategy_versions` table — the single source of truth for "what version of strategy X exists / is running." Each distinct source content hash maps to a monotonic `version` per strategy (PK `(strategy_id, version)`, UNIQUE `(strategy_id, source_hash)`); reverting to earlier content **reuses** its original version. `lab_db.ensure_strategy_version()` assigns/returns it (content-addressed, idempotent, retries on the rare concurrent-PK race); `version_for_hash()` resolves a stored hash; `list_strategy_versions()` is the history (newest-first), exposed at `GET /strategies/{id}/versions`.

Versions are registered in three places: the **scanner** (every scan, both `.cs`/`.mq5`, before the skip check so unchanged strategies still register), the **deploy** endpoint, and the **upload** endpoint. Lab-VPS deploy/compile state lives as columns on `strategies` (`deployed_source_hash`/`deployed_at`, `compiled_source_hash`/`compiled_at`): `set_strategy_deployed()` stamps the deployed hash + flags needs-compile (`is_compiled=0`); `mark_runner_compiled()` stamps `compiled_source_hash = deployed_source_hash` on compile success (content-accurate, not just the coarse `is_compiled` boolean). **Hash parity is essential** — anything that records a deployed hash must hash the same way the scanner does (decode bytes utf-8 errors=replace → md5), or `deployed_version` won't resolve.

**First-run note:** strategies deployed before this feature have `deployed_source_hash = NULL`, so they correctly show `needs_deploy` until deployed once through the tracked path (we never fake a hash we can't verify — the VPS agent's file listing exposes size/mtime, not content). **Scalability:** the version registry is target-agnostic — a future "deploy version N to bot X" records `(strategy_id, target, version)` in its own table without touching the registry; the lab VPS is just today's only target.

⚠ **`lab_db.mark_strategy_needs_compile` was DELETED 2026-08-12 by `/dead-code-audit`, and it is
the losing half of exactly the migration described above.** It flipped the coarse `is_compiled = 0`
boolean for one `class_name`, and it had **zero call sites repo-wide** — `needs_compile` has been
COMPUTED from content hashes at `routers/strategy_files.py:232`
(`deployed_hash is not None and deployed_hash != compiled_hash`) since the day that column pair
landed. The sibling `mark_runner_compiled`'s own docstring says so out loud: *"so `needs_compile`
can be judged by content, not a coarse boolean."* ⚠ **`is_compiled` itself STAYS** — `mark_runner_compiled`
writes it and the MT5 branch of the sync check reads it, because MT5 loads the compiled `.ex5` and
its absence is a real question a hash cannot answer. **What went is the one writer that could set
that flag from a claim rather than from a measurement.**

---

## Strategy location + deploy (Pass 2.5)

Live behavior. Scanner reads from `strategies/` via `rglob("*.cs")`/`rglob("*.mq5")`; `source_path` stored relative to monorepo root (e.g. `strategies/ninjatrader/ORB.cs`); missing `source_path` warns, never auto-deletes. `POST /strategies/{id}/deploy` reads `source_path` and uploads via `runner_dispatch` (`.mq5` → MT5 agent, `.cs` → NT8 agent), returns 202 + `deploy_job_id`. Edge cases: `source_path` null → 400, file missing → 404, VPS locked → 423. Detail is in git history (Pass 2.5).

**Bidirectional delete (reconcile) — deletion propagates only on an explicit action.** Deleting a source file from the repo should mean "remove everywhere" (DB row + the deployed `.cs`/`.mq5` on the VPS NT8/MT5 folder), but that destructive step is **never** wired into a scan. `scan_strategies()` is READ-ONLY: it adds/updates from disk and calls `_detect_orphans()` (DB strategies whose recorded `source_path` no longer exists on disk) to REPORT them in `ScanResult.orphans` — it deletes nothing. A scan is a frequent read; a mis-synced disk (wrong `MONOREPO_ROOT`, repo not checked out) would otherwise silently wipe every deployed file. The destructive cleanup is a separate endpoint, `POST /strategies/reconcile` → `reconcile_strategies()`, which calls `remove_strategy(sid)` for each orphan (best-effort VPS delete — 404/"not found" counts as success; a real failure is surfaced as a warning but never blocks the DB removal) and returns `ReconcileResult{removed, warnings}`. The per-strategy `DELETE /strategies/{id}` uses the same `remove_strategy` helper. Frontend (`Strategies.tsx`): Scan toast flags orphan count; a red **Reconcile (N)** button appears only when the last scan found orphans, fronted by a `ConfirmDeleteModal` listing exactly which strategies go.

**`delete_strategy` cascades the FK chain.** Foreign keys are ON, and `backtest_runs`/`optimizations` reference `strategies` (and `evaluations`/`stress_tests` reference those runs), all `NO ACTION`. So `lab_db.delete_strategy()` purges the whole chain children-first in one transaction — evaluations + stress_tests (via the strategy's run_ids) → backtest_runs + optimizations → strategy_versions → the strategy — or deleting any strategy that has runs raises `FOREIGN KEY constraint failed` (this was an unhandled 500 on reconcile of a strategy with runs).

**MT5 delete removes BOTH the `.mq5` and the `.ex5`.** MT5 loads the compiled `.ex5`, which outlives its source — deleting only the `.mq5` leaves the strategy in the Navigator and Strategy Tester. `mt5_agent_client.delete_strategy_file()` deletes both siblings (`_delete_one` per file; an already-absent sibling 404 is fine; fails only on a real error or if neither existed). NT8 has no analog — it compiles all `.cs` into one `NinjaTrader.Custom.dll`, so deleting the `.cs` + recompiling clears it.

---

## A strategy names its own setup on the chart — `chart_tag` (2026-09-02)

`strategies.chart_tag` (TEXT, nullable), declared by the package as `LAB_STRATEGY["chart_tag"]`,
carried by the scanner, read by `chart_spec._chart_tag` and shipped as `spec.tradeTag`.

🔴 **The price chart hard-coded `SOS Fade` — `sos_fade`'s word for ITS setup — onto every strategy's
PRIMARY trades**, so three other bots' charts carried a fourth bot's label. `overlays.ts` had named
the cost and the fix in a comment since it was written (*"the honest fix is a per-strategy tag
travelling on the spec, and that needs a column on the strategies table for a chart LABEL"*); this
is that column. **Nothing was broken and nothing went red — a wrong label renders exactly as
confidently as a right one**, which is rule 7 in its quietest form.

- ⚠ **A LABEL, and nothing about a run reads it.** Changing it repaints chips and moves no trade,
  no cost and no decision. That is the whole contract.
- ⚠ **`None` is an ANSWER — the package declared none — and the key is then ABSENT from the spec,
  never `""`.** The panel falls back to `PRIMARY_TAG` on absent; an empty string would read as
  *this strategy asked for a blank chip* in some checks and as no tag in others.
- ⚠ **Undeclared still renders `SOS Fade`, deliberately.** Untagged is not an option (telling the books
  apart at a glance is the point), and a neutral fallback would strip the CORRECT tag off the live
  SOS Fade bot's charts. **So a chart reading `SOS Fade` means EITHER that bot or one that has not declared its
  own word yet.**
- 🔴 **IT RIDES THE TRADE, NEVER THE SPEC, AND A STACK IS WHY.** `build_stack_chart_spec` merges N
  legs' trades into ONE list and stamps each with its `layer`; a spec-level tag cannot survive that
  merge, so every leg's trades would wear whichever single tag the merged spec held. **That is this
  same defect one level down and HARDER to see** — the chips would look per-strategy without being
  it, which is exactly what a reader stacks two bots to tell apart. The first implementation here
  did put it on the spec, and it was caught by asking what a stack does with it.
- **Five of six packages declare one** (`SOS Fade`, `B-LEG`, `BOS`, `REALIGN`, `XLEG`). ⚠ **`loss_recovery`
  deliberately declares NONE**: its trades carry `kind="recovery"`, so the renderer tags them `REC`
  down a different branch and a `chart_tag` there could never be read — a declared field nothing can
  assign is rule 10's shape, so it is left off rather than added for symmetry.
- 🔴 **RULE 22 IS SILENT FOR ALL OF THEM, NOT SATISFIED.** Declaring a tag edits a strategy package,
  and no bar-data export is on this machine for any of these gates — the repo's own recorded state
  for most of them. **What stands in its place is a grep, not an assurance**: `chart_tag` appears
  only in the scanner, the strategies table, the model and the chart spec, and nowhere under any
  strategy's own trading code, so it cannot reach a decision. Say that rather than implying a gate
  ran. ⚠ The one export present for `extreme_leg` is a TRADE LIST, and its gate correctly
  refuses that — a file existing is not a gate that can run.
- ⚠ **Declared by the package, never mapped here.** A strategy-id→label map in this backend would
  be a second claim about what a strategy calls its setup, and it goes stale the first time
  somebody adds one.
- ⚠ **The lookup is best-effort like every other in `chart_spec`** — a chart that refuses to build
  because a LABEL could not be read has traded a missing word for a missing chart.
- ⚠ **The column is declared in BOTH the migration list and the `strategies` CREATE TABLE**, per
  this file's own standing note.

**Tests:** `tests/test_chart_trade_tag.py` (16), watched RED by five mutations — the scanner key
dropped, the raw value passed through unvalidated, the upsert unable to CLEAR a dropped
declaration, the chart stringifying `None`, and the lookup no longer best-effort. ⚠ **A sixth
mutation did NOT bite and its test is LABELLED as a forward guard rather than left claiming
otherwise**: deleting the null-id early-out leaves it green, because `get_strategy` answers `None`
for a null id rather than raising (measured, not assumed).

## Retired strategy ids are migrated by a script — `scripts/migrate_debrand_ids.py` (2026-09-13)

🔴 **A strategy's lab id IS its package folder, so the 2026-09-03 de-brand (`mpc_sos_fade` →
`sos_fade`, `mpc_bleg` → `b_leg`, `mpc_bos` → `bos`, `mpc_realign` → `realign`) left every clone's
runs filed under ids the code no longer has.** A Retry then failed with *"no Python strategy class
named 'MpcSosFadeStrategy'"*. The plan's migration SQL had itself been rewritten by the rename's
find-and-replace into a no-op — `docs/DEBRAND_RENAME_PLAN.md` §4.2 records it.

- **Preview by default; `--apply` needs `--backup`** and will not overwrite one. Idempotent.
- ⚠ **All or nothing**: an unscanned new id or a colliding `solo/<id>/` folder refuses before any
  write. Folders move first and are put back if the transaction fails.
- ⚠ **Version-history rows must go before their strategy row** — the foreign key refuses otherwise,
  and the script connects with the app's own enforcement on so a wrong order raises.
- ⚠ **A future package rename needs a new mapping here, or its own script** — the id is the folder.

Tests: `tests/test_migrate_debrand_ids.py` (8), on the real schema; 9 mutations planted in memory, 9
killed.

## A strategy marks its risk-per-trade setting — `role: "risk_pct"` (2026-09-16)

Aaron: every strategy's risk % must be changeable at the top of the run form. A self-sizing
strategy owns that value as an ordinary setting, so its meta.json marks it with
`"role": "risk_pct"`; the scanner passes the key through and the run form lifts that one setting
into a "Risk Per Trade" box under the setup row (and drops it from Strategy Settings, so it is
edited in one place). The value still travels in `params` exactly as before. Engine-sized
strategies keep Sizing Mode → Manual in the same spot.

- ⚠ A self-sizing package with no mark still runs; the form shows a warning instead of the box.
- Tests: `tests/test_risk_param_role.py` scans the REAL packages — every runnable self-sizing
  strategy must mark exactly one numeric setting. Watched red by deleting realign's mark.

### Realign's page caught up with its settings (2026-09-16)

Six realign settings added after 2026-09-03 (the retest entry and its two controls, the fixed
take-profit, the trail frame, the weekend close) had no description, so the page showed raw names.
They are described now, and the allowance for realign's undocumented settings fell 120 → 119.
The summary lost the ratchet-trail bullet (the default moved to the plain swing trail) and folded
the entry and stop bullets together — the summary check counts hidden bullets too, max seven.
