# Notes — Committing — the doc rule, the evidence rule and the tripwires

Why a commit must carry its doc and name its evidence, the exemptions, how the hooks get installed, and what two sessions sharing one clone must not do. Moved VERBATIM out of `CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## Committing — the docs land in the same commit as the code

**Enforced since 2026-08-04 by a git hook, not by memory.** Two people work this repo from
two machines, and these CLAUDE.md files are the only way each learns what the other did. A
code change whose doc never landed is invisible on the other machine until it bites.

`.githooks/commit-msg` refuses any commit where a changed file's **owning CLAUDE.md** is not
in the same commit. The owner is the nearest CLAUDE.md walking UP from the file's folder —
so `engines/vwap/engine.py` needs `engines/vwap/CLAUDE.md`, a ChartPanel component needs
`ChartPanel/CLAUDE.md`, and a root-level file needs this file. Updating a PARENT does not
satisfy a child: the nearest one is the one somebody reads next.

Exempt: markdown, lock files, images, data (`.csv`, `.db`, `.pkl`), `.gitignore`,
`.claude/settings.local.json`, and **`*/ledger/decisions-*.jsonl`**. Merges, rebases, reverts and
`fixup!` commits pass through — they carry somebody else's change and would ask for the same
paragraph twice. ⚠ `*.meta.json` is deliberately NOT exempt: it is a contract the Pine and the lab
both read, not data.

🔴 **The ledger exemption was added 2026-08-05 because the hook had QUIETLY DISABLED THE ONE BACKUP
THAT MATTERS.** `algos/tools/ledger_sync.py` commits the live bot's decision record unattended —
that record is the only copy of what the bot decided, including every setup it refused, and no
broker statement contains it. The hook classified the `.jsonl` as code and demanded a paragraph in
`algos/CLAUDE.md` for a data file, so **every automated sync failed and a closed day sat on the VPS
alone.** Measured: the sync refused with 2026-08-04 outstanding, and it went through the moment the
exemption landed. ⚠ **It is a PATH, not `*.jsonl`** — the extension is generic, and a future
`.jsonl` carrying a contract would be waved through the way `*.meta.json` explicitly is not, while
`*/ledger/decisions-*.jsonl` can only ever be this. ⚠ **Three streams are exempt since 2026-09-17** — decisions, health, and `deals` (the account's MT5 history, `algos/notes/vps-tasks-and-ledger.md`); a new stream needs its line here in the same change. **The standing lesson is about guardrails, not
about this file: a rule that fires on a robot's commit has no human to read its message, so it does
not nag — it silently stops the job.** When you add a check, ask what it does to the things that
commit without a person watching.

🔴 **THE SAME RECORD BROKE THE SAME WAY AGAIN ON 2026-08-27, AND THE CAUSE WAS LINE ENDINGS.**
The trading box writes the decision record with a carriage return; the Mac does not. Both machines
commit it, git stores whatever bytes it is handed, and two copies that disagree on EVERY line
conflict on every line — **even though both sides had only ever APPENDED.** Hit twice inside ten
minutes while pushing a doc change, and it was harmless only because a person was standing in front
of it. Unattended, it is the 2026-08-05 failure exactly: the sync does not nag, it stops, and the
day sits on one machine alone.

✅ **FIXED AT THE STORAGE LAYER by `.gitattributes` at the repo root** — `*.jsonl` and `*.log` are
declared text, so git normalises them however they arrive and the two machines store identical
bytes. ⚠ **Deliberately NOT fixed by making an agent write the other ending.** That is a rule living
in one script's memory, and this repo already knows what happens to those: the next tool that
touches the file has never heard of it. **Nothing has to remember anything for this fix to hold.**
⚠ **The broad glob was CHECKED, not assumed** — all 64 tracked files of those two types are these
bot records, so nothing else is touched. ⚠ **62 existing files were renormalised in the same
commit**, and each was verified byte-identical to its old version once carriage returns are ignored:
a record of what the bot decided may not be edited to fix a merge problem. ⚠ **Proven rather than
reasoned** — a carriage-return file was written, staged, and the stored blob confirmed to hold none.

⚠ **The deeper hazard is unchanged and this does not retire it: TWO machines still commit this file,
and exactly one may push.** The rule stops them conflicting on formatting. It does not stop them
diverging, and a same-day divergence still needs a human to merge — check that the fuller side is a
strict superset before taking it, because on 2026-08-27 it was, and that is the only reason nothing
was lost.

When a change genuinely needs no doc update, say so **in the message** — the reason is
required and is recorded where the other person can read it:

```
fix(chart): correct a comment typo

DOCS: none - comment only, no behaviour change
```

🔴 **`git add -A` FROM A SECOND SESSION BREAKS THE PAIRING THE HOOK EXISTS TO ENFORCE, and it
happened on 2026-08-25.** The docs check asks that a changed file's owning CLAUDE.md be in the SAME
commit. It cannot ask the reverse — that a CLAUDE.md paragraph ships with the code it describes —
so a blanket stage from a session working on something else sweeps up another session's in-progress
doc edits and lands them alone. Commit `89a6324` (an MCP fix) carried 19 lines of this file
describing a test step that lived only in an uncommitted working file, so **`main` documented step
8 of `scripts/run_all_tests.sh` while `main`'s own copy of that script still said seven steps.**

⚠ **Nothing failed and no check went red** — the same shape as the ruff carve-out that `git add -A`
undid, and this file already names that one. **Stage by PATH when two sessions share a clone**, and
before committing, read `git status` for files you did not touch.

🔴 **Never move `main` (reset, rebase, checkout) to catch up after a push without reading
`git reflog main` first** — the other session may have committed on top of you since you last looked.
On 2026-09-11 a `reset --keep` after a rebuilt push dropped three fresh commits from the other
session and rolled its files back; restored two minutes later. Message the other session before
moving the branch.

⚠ **By PATH is not enough for a file BOTH sessions are editing, and two commits at one instant
SWAP MESSAGES.** `git commit -- <path>` takes the whole working-tree file, the other session's
unsaved lines included (6ccb56e0, 2026-09-11). And `.git/COMMIT_EDITMSG` is one file per clone: two
`git commit`s racing that day put one session's message on the other's tree — 233a3686 is a
root-doc paragraph under a sweeps title. **Simplest: take turns, by message.** Otherwise plumbing: a
scratch index started from HEAD (`GIT_INDEX_FILE=<tmp> git read-tree HEAD`, `git apply --cached`
your patch — the hooks compare against HEAD, so any other base stages a revert of what HEAD has),
both hooks run by hand under it (`commit-tree` runs none), `git commit-tree -F <your own file>`,
`git update-ref refs/heads/main <new> <old>` (refuses if the branch moved), then `git reset --
<path>` in the real index. ⚠ **Never a plain `git commit` from the shared index** — it takes
whatever the other session has staged.

⚠ **The direction of the damage is the part to remember: a doc that arrives EARLY reads exactly
like a doc that is right.** The next person greps for the step, finds the paragraph, runs the
script, and sees seven — and the honest conclusion available to them is that the script is broken.

### The second half — a change to the money paths names its evidence

**Added 2026-08-12.** The docs check proves somebody WROTE something down. It does not prove
anybody CHECKED anything, and this repo's expensive mistakes all shipped with docs AND a green
suite: a 54.82-lot order on a $2,000 account, a bot re-anchoring its sizing to a stranger's
balance for two hours, an 82-combination sweep from a port whose parity gate had never once run.

So for the paths where a wrong number costs money rather than time — `engines/`, `strategies/`,
`algos/live/`, `algos/shared/`, `backtest/`, `indicators/*.pine` — the message has to carry one
line naming the evidence:

```
fix(live): halt when the terminal is on another account

TESTED: 18 new tests, 13 watched RED against HEAD; 603 algos green
MEASURED: cost_tiers.py, 155,531 M15 bars - ECN 157 trades / +151.39R
PROOF: none - renamed a local variable, no behaviour change
```

The line is **not graded**. The point is that you had to type what you actually ran, which is
the moment you notice you ran nothing. `/prove` and `/measure` exist to make that line true
rather than plausible.

⚠ **It is deliberately NARROW, and widening it has a cost.** A hook that nags on every UI tweak
is a hook people learn to bypass, and `--no-verify` leaves no trace at all — which is strictly
worse than no hook, because the history then reads as checked. `command-center/` is excluded on
purpose. If you widen it, name the reason.

⚠ **The exemptions are shared with the docs check, so the unattended ledger sync still passes** —
that was verified rather than assumed, because a rule firing on a robot's commit has no human to
read its message and silently stops the job. That has already happened twice on the docs half.

⚠ **Merges, rebases, reverts and `fixup!` pass straight through**, same as the docs check.

### Getting it switched on — four tripwires, because nothing runs on clone

⚠ **The hook lives in `.githooks/` and is switched on by `core.hooksPath`, which is per-clone
LOCAL config that `git clone` does not carry.** A fresh clone is unprotected and looks
IDENTICAL to a protected one — measured, not assumed: a clone of this repo committed a code
change with no doc and no complaint.

**Git will not execute repo code on clone or fetch**, and that is a security property, not an
oversight — so no hook of ours can fire first. The answer is to check at every entry point
somebody plausibly uses first. All four call the one installer, `scripts/install_hooks.sh`,
which is **silent when nothing needs doing** and speaks up only when it just installed:

| Tripwire | Fires when | Catches |
|---|---|---|
| `.githooks/post-merge` | every `git pull` / merge | drift, an unset config, a hook arriving without its executable bit |
| `.claude/settings.json` → `SessionStart` | every Claude Code session in this repo | **a fresh clone** — neither of us works here without Claude |
| `conftest.py` | any `pytest` run | a fresh clone, before the suite runs |
| `./go` | every launch of the command center | a fresh clone |

`post-merge` also **says so when the pull changed the rules themselves** (`.githooks/` or the
installer), because a rule that changes under you without a word makes the next refusal read
as a bug.

⚠ **`post-merge` cannot cover the clone case and must not be read as if it does** — it is the
one tripwire that requires the hooks to already be installed. The clone is covered by the
other three, and they are three rather than one because each only fires if you happen to do
that thing first.

⚠ **The pytest notice is suppressed by `pytest -q`** (which hides the header). The install
still happens; only the message is hidden. Run plain `pytest` to see it.

⚠ **A hook that is not executable is skipped by git in silence** — same "looks installed, does
nothing" shape one level down. The installer chmods every hook every run.

### `./go` is also the only thing that maintains the news calendar cache (2026-09-01)

🔴 **Its step 6 asked whether the cache FILE EXISTS, which is not a question about the dates inside
it.** The file had been there since July while its coverage stopped four weeks back, so every launch
said fine and the backend's own startup banner was the only thing that ever noticed. **Presence is
not freshness.** Step 6 now tops the cache up, costs nothing on the days there is nothing to fetch,
and never kills the launcher when it cannot. The cache is git-ignored, so this is per-machine by
design and there is no second writer. Rules, the tool, and the wiring bug that made a refusal read
as an all-clear: `engines/news/CLAUDE.md` → *Keeping the cache current*; story in `HISTORY.md`.
