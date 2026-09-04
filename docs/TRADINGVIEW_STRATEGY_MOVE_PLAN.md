# Moving the Pine strategies to `strategies/tradingview/` — survey and instruction set

> # ✅ DONE — EXECUTED 2026-09-02
>
> **The move has happened.** 24 tracked files moved from `indicators/strategies/` to
> `strategies/tradingview/`, the two research files dropped to `strategies/tradingview/research/`,
> and 177 references across 71 files were swept or deliberately left. Everything below is kept as
> the RECORD of what was surveyed and decided — **it is no longer an instruction set, so do not
> run §4 again.**
>
> **The two open questions were settled Aaron's way, both on the recommendation:**
>
> - **§3 → Option A.** `london_breakout.pine` and `ny_orb.pine` went to
>   `strategies/tradingview/research/`. The top level is gated source; `research/` is scratch.
> - **§2.1 → Option A.** The Pine strategies now match the root-anchored `/strategies/` fragment
>   and collect its reminder as well as the `.pine` one. The reminder is correct for them, so it
>   was kept rather than special-cased away.
>
> **What was done differently from the plan, and why:**
>
> 1. 🔴 **§2.1's prediction that the guard check would go RED on its own was WRONG, and the way it
>    was wrong is worth more than the plan was.** `check_guard.py` names its path as a STRING, and
>    nothing asks whether that path still exists — so after the move the case stayed GREEN while
>    asserting behaviour for a file that was no longer there. It only went red once it was pointed
>    at the real path, and only then was the assertion flipped. **A guard case pinned to a moved
>    path is not testing anything; it is describing a repo you no longer have, in green.**
> 2. **No `.pine` file's content was touched at all**, including one comment in
>    `indicators/engines/mss_sweeps.pine` that now points at a moved doc. Rule 22 is about
>    `.pine` content rather than about whether an edit could plausibly matter, and that file has no
>    `compare_*.py` that could clear it. The dead pointer is recorded in
>    `indicators/engines/CLAUDE.md`.
> 3. **The relative links inside the moved CLAUDE.md broke and the plan never mentioned them** —
>    12 `../` links resolved into `indicators/` and now resolve into `strategies/`. All were
>    repointed and each was checked to resolve. §1's reference sweep counted the path STRING and
>    was blind to every link that names no path at all.
> 4. **§1's counts were stale by the time the hold lifted**, exactly as its own banner warned: 23
>    files → 24, 147 occurrences → 177, 66 files → 71. The extreme-leg export twin landed in
>    between.
>
> ⚠ **§8's ordering advice still stands and is now urgent**: `docs/DEBRAND_RENAME_PLAN.md`
> renames these same files and its paths were rewritten to match this layout.

**Written 2026-09-01 as a survey and instruction set. EXECUTED 2026-09-02 — see the banner above.**

**Who this is for:** originally the session that did the work; now anyone asking why the Pine
strategies are where they are, or what was checked before they were moved.

---

## §0 — Why, and the evidence for it

**The claim:** Pine `strategy()` files are strategy source for the TradingView runner platform, so
they belong under `strategies/tradingview/` alongside the MT5, NinjaTrader and Python strategies —
not under `indicators/`.

Three things were CHECKED rather than assumed, because the current split was a deliberate decision
on 2026-08-13 and overturning it needs more than a tidiness argument:

| Checked | Command | Result |
|---|---|---|
| Do the Pine strategies depend on `indicators/engines/`? | `grep -rn '^import ' indicators/strategies/*.pine` | **No output.** Zero Pine imports. Every strategy file is self-contained — it inlines the engine source rather than importing it. |
| What consumes them? | reference sweep, §1 | The parity gates under `strategies/python/*/tools/compare_*.py`. Their tightest coupling is to the folder they would be moving next to. |
| Would moving them register 13 Pine files as lab strategies? | `grep -n 'rglob' command-center/backend/services/strategy_scanner.py` | **No.** The scanner rglobs `*.cs` and `*.mq5` only, plus directories under `strategies/python/`. It has never globbed `.pine`. |

**So the taxonomy argument survives the coupling check.** `indicators/` is organised by LANGUAGE
("every Pine source in the repo"); `strategies/` is organised by RUNNER PLATFORM. Pine runs only on
TradingView, so for these files the two taxonomies pick the same set and the tie is broken by what
actually depends on what.

⚠ **What is LOST by moving them, and it should be said rather than discovered later.** The
`indicators/` tree currently gives you one place to read every Pine file in the repo, which is how
drift between a strategy's inlined engine copy and `indicators/engines/`'s canonical version gets
spotted by eye. After the move, an inlined copy in `strategies/tradingview/` and its source in
`indicators/engines/` are two folders apart. **Nothing enforces that they agree today either** —
this is a loss of convenience, not of a gate.

---

## §1 — What moves, and what has to be rewritten

**Re-measure all of this before starting.** Commands are given so the next reader does not have to
trust the numbers.

### The files (23 tracked, measured `git ls-files indicators/strategies | wc -l`)

```bash
git ls-files indicators/strategies
```

| Group | Count | Files |
|---|---|---|
| Pine strategy parents | 8 | `sos_fade_strategy`, `b_leg_strategy`, `bos_strategy`, `h4_sweep_strategy`, `realign_strategy`, `recovery_strategy`, `extreme_leg_strategy`, `smc_session_sweep_strategy` |
| Pine `_export` twins | 5 | `sos_fade_strategy_export`, `b_leg_strategy_export`, `bos_strategy_export`, `h4_sweep_strategy_export`, `smc_session_sweep_strategy_export` |
| `docs/` prose, one per family | 7 | one `.md` per strategy family |
| `tools/` | 2 | `build_extreme_leg.py`, `derive_htf_structure.py` |
| `CLAUDE.md` | 1 | the folder's own rules |

🔴 **Three parents have NO export twin** (`realign`, `mpc_recovery`, `extreme_leg`) — that
is a pre-existing fact about their parity gates, not something this move causes. Do not "fix" it here.

⚠ **A twin moves with its parent, in the same commit.** The editor guard's own `.pine` reminder
says so, and a gate whose two halves live in different commits is a gate that was red in between.

⚠ **Root `CLAUDE.md` says "12 `strategy(` files" and there are 13.** Count with `ls`, never from
the line. Fix that line as part of this work.

### The references (147 occurrences across 66 files, 60 of them outside the folder)

```bash
grep -rIo 'indicators/strategies' --exclude-dir=.git . | wc -l    # occurrences
grep -rIl 'indicators/strategies' --exclude-dir=.git . | wc -l    # files
```

**Almost all of them are prose** — docstrings, usage lines, doc bodies and build notes. Only three
references resolve a real path at run time, and they are listed in §2 because each needs a decision
rather than a substitution.

The ten heaviest files, for scale:

| File | Occurrences |
|---|---|
| `indicators/docs/INDICATORS_BUILD_NOTES.md` | 9 |
| `strategies/python/b_leg/CLAUDE.md` | 8 |
| `indicators/strategies/CLAUDE.md` | 8 |
| `indicators/CLAUDE.md` | 6 |
| `docs/ENGINE_EXTRACTION_ROADMAP.md` | 6 |
| `strategies/python/sos_fade/sos_fade_optimization.md` | 5 |
| `docs/SMC_SESSION_SWEEP_SPEC.md` | 5 |
| `HISTORY.md` | 5 |
| `strategies/python/sos_fade/CLAUDE.md` | 4 |
| `docs/STRATEGY_WORKFLOW.md` | 4 |

🔴 **`HISTORY.md` and the `*_BUILD_NOTES.md` files are a DATED RECORD of what happened.** A
sentence that says "on 2026-08-13 the Pine files were split into `indicators/strategies/`" was TRUE
on that date and rewriting the path makes the record lie. **Leave historical narrative alone; add a
one-line forward pointer at the top of each instead.** Only rewrite a path that tells the reader
where a file is TODAY.

---

## §2 — The four things that are NOT a text substitution

Everything else is `git mv` plus a careful sweep. These four each need a decision.

### 2.1 🔴 The editor guard silently re-aims itself — this is the one that bites

`.claude/hooks/guard_sensitive_paths.py` matches a top-level subsystem fragment ANCHORED at the repo
root. Its fragments include `/strategies/` (reminder: *"This is what a bot actually trades"*) and
`.pine` (reminder: the declaration-order rule).

**Today** `indicators/strategies/sos_fade_strategy.pine` matches `.pine` only — it is not under the
top-level `strategies/`. **After the move** `strategies/tradingview/sos_fade_strategy.pine` matches BOTH.

⚠ **`.claude/hooks/check_guard.py` has a case that asserts exactly the current behaviour**, titled
*"Pine STRATEGY source is not a deployed Python strategy"*, asserting `"what a bot actually trades"
not in s`. **That assertion inverts.** The check goes red the moment the file moves, which is the
system working — but it means a decision, not an edit:

- **Option A (recommended): accept the second reminder and flip the assertion.** A default moving in
  a Pine strategy DOES invalidate documented baselines, because that file is half of a parity gate.
  The reminder is arguably correct there. Rename the case and assert both reminders fire.
- **Option B: exclude `strategies/tradingview/` from the `/strategies/` fragment.** Keeps today's
  behaviour exactly. Costs a special case in the guard, which is the kind of thing that goes stale.

⚠ **The guard's `subsystem_matches` docstring uses this very split as its worked example** — it
explains the 2026-08-13 anchoring fix in terms of `indicators/strategies/`. After the move that
example describes a layout that no longer exists. Rewrite it to say what it now guards, and keep
the lesson (*a directory rename can silently re-aim a guard*), because this move is a second
instance of it.

✅ **Whatever you pick, run `python3 .claude/hooks/check_guard.py` and watch it go RED before the
fix and GREEN after.** A guard case edited to match new behaviour without being seen red is a case
that proves nothing.

### 2.2 `.gitignore` holds a real generated path

```
indicators/strategies/tools/_derived_structure_15.pine
```

Rewrite the pattern AND the comment above it. ⚠ **If a generated copy exists on disk under the old
path, delete it** — otherwise it stops being ignored and gets swept into a commit.

### 2.3 `derive_htf_structure.py` writes its own path into its output

It stamps `"// Generated by indicators/strategies/tools/derive_htf_structure.py from"` into the
file it generates. Update the string, then **re-run the tool** so the generated header matches. A
header naming a script that is not there sends the next reader hunting.

### 2.4 `.claude/settings.json` pins two absolute paths

Two allow-listed `awk` commands name absolute paths into `sos_fade_strategy.pine` and
`sos_fade_strategy_export.pine`. They are line-range reads from a past session. **Delete them rather than
rewriting them** — they pin line numbers that have already moved, so they are dead allowances.
⚠ `.claude/settings.local.json` has two more; it is git-ignored and per-machine, so fix it on
whichever machine complains and do not commit it.

---

## §3 — Target layout, and the one open question

```
strategies/
├── ninjatrader/
├── mt5/
├── python/
└── tradingview/          ← Pine strategy source
    ├── CLAUDE.md
    ├── sos_fade_strategy.pine + sos_fade_strategy_export.pine
    ├── … 11 more .pine …
    ├── docs/             ← one .md per strategy family
    └── tools/            ← build_extreme_leg.py, derive_htf_structure.py
```

🟡 **OPEN — where do `london_breakout.pine` and `ny_orb.pine` go?** They already sit in
`strategies/tradingview/` and `strategies/CLAUDE.md` calls that folder *"research scratch space,
hand-tested in the Strategy Tester, not picked up by the scanner"*. After the move that sentence is
false for 13 of the 15 files in there, and **a folder where two files are scratch and thirteen are
half of a parity gate is a folder whose CLAUDE.md has to say which is which on every single file.**

- **Option A (recommended): `strategies/tradingview/research/`** for the two, leaving the top level
  for gated source. One sentence in the CLAUDE.md instead of a per-file caveat.
- **Option B: flat, and the CLAUDE.md carries a list.** Cheaper now, and the list is what goes stale.

**Decide this before the first `git mv`** — it changes the destination paths.

---

## §4 — Execution order

⚠ **Use `git mv`, never `mv` + `git add`.** History following is what lets the next reader
`git log --follow` a Pine file across this move, and these files carry years of decisions.

1. **Verify the preconditions** in the hold banner. `git status` clean, both workstreams pushed.
2. **Settle §3's open question** and §2.1's Option A or B.
3. **Re-measure §1.** The counts will have moved.
4. `git mv indicators/strategies/<each> strategies/tradingview/<each>` — the 23 tracked files.
   Move `docs/` and `tools/` as whole directories.
5. **Sweep the 60 outside files.** Substitute `indicators/strategies` → `strategies/tradingview`,
   then **read every hit in `HISTORY.md` and the `*_BUILD_NOTES.md` files and revert the historical
   ones** per §1's warning. This step is not scriptable end to end.
6. **Apply §2.1 – §2.4** by hand.
7. **Rewrite the CLAUDE.md files** — §5.
8. **Verify** — §6.
9. **Commit and push** — §7.

---

## §5 — The CLAUDE.md files that must change, and what each has to say

The commit hook finds a changed file's owning doc by walking UP from its folder, so these are
required by the hook as well as by the reader.

| File | What changes |
|---|---|
| `indicators/strategies/CLAUDE.md` | **Moves** to `strategies/tradingview/CLAUDE.md`. Its rules are about the Pine panel contract and travel with the files. |
| `indicators/CLAUDE.md` | The split table (`strategies/` \| `strategy(` \| 12) loses its first row. Purpose line stops claiming "every Pine Script source in the repo" — the `strategy()` half has left. State where they went and why. |
| `strategies/CLAUDE.md` | The key-paths tree gains 13 Pine files, `docs/` and `tools/`. 🔴 **Rewrite the "research scratch space" sentence** — see §3. Add a "Adding a new TradingView strategy" section next to the NT8/MT5/Python ones. |
| Root `CLAUDE.md` | *Repo Structure* and the `indicators/` and `strategies/` rows of *The rest*. **Fix the stale "12" to 13** while you are in there. |
| `.claude/` section of root `CLAUDE.md` | The guard paragraph quotes the `indicators/strategies/` example from §2.1. Update it to the new layout and keep the lesson. |
| `strategies/python/*/CLAUDE.md` (4 files) | Each names its Pine twin's path. `b_leg` has 8 references, `sos_fade` 4, `bos` 2, `realign` 1. |
| `indicators/engines/CLAUDE.md`, `engines/fibonacci/CLAUDE.md`, `command-center/backend/CLAUDE.md`, `backtest/CLAUDE.md`, `docs/teaching/CLAUDE.md` | One or two path references each. |

⚠ **Watch the doc-growth guard.** `indicators/strategies/CLAUDE.md` is ~139 KB and
`indicators/CLAUDE.md` ~109 KB — both far over the 40 KB ceiling. The guard fires on GROWTH, so a
move is silent and a trim passes silently too. **Do not take this as an invitation to refactor them
in the same commit** — a 147-reference sweep and a doc rewrite in one diff is a diff nobody can review.

---

## §6 — Verification, before the commit

```bash
# 1. Nothing still points at the old path.
grep -rI 'indicators/strategies' --exclude-dir=.git .
#    Expected: ONLY the deliberate historical mentions in HISTORY.md / *_BUILD_NOTES.md.
#    Every other hit is a miss.

# 2. History followed the files.
git log --follow --oneline -3 strategies/tradingview/sos_fade_strategy.pine
#    Expected: commits predating the move. If it shows one commit, git mv was not used.

# 3. The guard cases agree with the new layout.
python3 .claude/hooks/check_guard.py

# 4. The Pine panel checks still find their files.
python3 indicators/tools/check_active_order.py strategies/tradingview/*.pine
python3 indicators/tools/check_scope.py        strategies/tradingview/*.pine
python3 indicators/tools/check_flat_reset.py   strategies/tradingview/*.pine
#    ⚠ Their usage docstrings name the old path — update those too.

# 5. Full suite.
scripts/run_all_tests.sh
#    Two tests name the path: command-center/backend/tests/test_param_gates.py
#    and command-center/frontend/tests/param-gates.spec.ts.
```

🔴 **Rule 22 does NOT require a parity gate run for this change, and here is why that is safe to
say.** No `.pine` file's CONTENT changes — `git mv` moves bytes, and the sweep touches only
docstrings and docs. **Prove it rather than asserting it:**

```bash
git diff --cached --stat -- '*.pine'
#    Expected: renames with 0 insertions / 0 deletions on the .pine files.
#    ANY content change on a .pine means rule 22 applies and a gate has to run.
```

⚠ **`compare_*.py` reads a CSV export you point it at**, so no gate path breaks. But the
comparators' docstrings name the Pine source, and a stale docstring is how the next reader exports
the wrong file.

---

## §7 — Committing

🔴 **Stage by PATH. Never `git add -A`.** Two sessions share this clone and a blanket stage sweeps
up another session's in-progress work — that already happened on 2026-08-25 and put a doc on `main`
describing a script that had not landed.

The commit hook wants each changed file's owning CLAUDE.md in the same commit; §5 covers that.
Money-path files are touched (`strategies/`, `indicators/*.pine`), so the message needs an evidence
line — and the honest one here is that nothing was measured because nothing executable changed:

```
refactor: move the Pine strategy sources to strategies/tradingview/

Pine strategy() files are strategy source for the TradingView runner platform,
so they now sit beside the MT5, NinjaTrader and Python strategies. The engines
stay under indicators/. No .pine content changed - git mv only.

PROOF: none - pure file move plus a path sweep; `git diff --stat -- '*.pine'`
shows renames with 0 insertions and 0 deletions.
TESTED: scripts/run_all_tests.sh green; check_guard.py watched RED on the
        re-aimed guard case before the fix and GREEN after.
```

⚠ **One commit, not several.** A gate whose two halves land separately was red in between, and a
half-swept tree is worse than either end state.

---

## §8 — Interaction with the de-branding rename

`docs/DEBRAND_RENAME_PLAN.md` renames these same Pine files in its §2.3 and is also on hold.
**The two plans touch the same 66 files and whichever runs second must be re-surveyed.**

**Recommended order: this move FIRST, the rename second.** This one is purely mechanical — no
content changes, no live bot, no lab database. The rename is the dangerous one (§3 and §4 of that
plan), and it is better to point a dangerous plan at a settled layout than to move folders
underneath a half-finished rename.

🔴 **When this plan lands, the de-branding plan's §1 counts and §2.3 paths go stale.** Add a pointer
at the top of `DEBRAND_RENAME_PLAN.md` saying so, in the same commit. That file is UNTRACKED as of
2026-09-01 — commit it first, or the pointer has nothing to attach to.
