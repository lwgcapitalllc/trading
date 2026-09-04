# Three exit-ladder experiments, built 2026-08-26 and STASHED 2026-08-27

**If you are looking for work on the A+ bot's exit ladder that you cannot find in the code, this
is it. It is not gone — it is in a git stash on Aaron's Mac.** Nothing here was ever committed,
so it exists on exactly one machine and `git log` will never show it.

```bash
git stash list          # find the entry named below
git stash show -p stash@{N}
git stash pop stash@{N} # or `apply`, to keep the stash while you look
```

**Stash message:** `A+ exit ladder: vol rung + two re-entry banking levers — built and tested
2026-08-26, NEVER MEASURED ON — see strategies/python/sos_fade/docs/STASHED_EXIT_LADDER_EXPERIMENTS.md`

⚠ **A stash is LOCAL and it is not a backup.** It does not travel with a push, a clone, or a
pull, and `git stash drop` / a `git stash clear` deletes it with no recovery. If this work is
still worth having in a month, it needs to be a commit or a branch instead.

---

## What it was

Three new settings on the A+ SOS Fade bot's exit ladder, all **shipped OFF**, so with them
present and untouched the ladder behaves byte-identically to what is committed today.

| The setting, as the Command Center labels it | What it does |
|---|---|
| **"Vol rung size %"** + **"Vol rung distance (x ATR14)"** | Banks a slice of the position at a rung IN FRONT of the first fib target, placed a multiple of recent 15-minute range away from the fill and frozen there. Banks SIZE only — it cannot move a stop, change a stage, or change which trades are taken. |
| **"Re-entry banks at its second target (%)"** | Lets a re-entry close a chosen percentage at its second target instead of handing the remainder to the runner trail. Defaults to inheriting the shared setting, which is zero. |
| **"Re-entry trails from its first target"** | Drops a re-entry's second target entirely and starts the runner trail the moment the first target is touched. Off by default. |

**Why they were built (Aaron, 2026-08-26):** the two fib targets sit too far out and are hit too
rarely to do anything about the case he was complaining about — a trade that runs a long way and
hands most of it back. And a re-entry is a recovery trade, not a second A+ setup: *"not to make
back what you lost and a little more? not to make more than an A+ setup."* A runner is the wrong
instrument for that job.

## What was actually proven

- **28 new tests across three files, all green**, and the whole A+ suite was 555 green with the
  work applied (measured 2026-08-27, `python3 -m pytest strategies/python/sos_fade/tests/ -q`).
- Each test file states it was **watched RED against HEAD** (the settings did not exist, so every
  test failed at construction) and then **re-proved by mutation** against the real implementation.
  That claim is the authors', recorded in the file docstrings — it was not re-run before stashing.

## What was NOT proven, and this is the reason it got stashed

🔴 **Not one of the three has ever been measured with the lever switched ON.** Seven lab runs
were made after the code was written and every single one carries all three settings at their
off/inherit values:

```
a6cbe197c3d5  b59f8d4e5a93 (timed out)  5c35fc4081bf  24932e4e0dba
70cb82c27613  ee2b70e3c738  229936427a0f
```

`229936427a0f` (2026-08-27) is the only run carrying all three keys, and it has all three off.
No optimizer sweep touched any of them either. **So there is no evidence any of these three
levers helps anything.** The code's own comments say the honest prior is that banking size has
measured WORSE on this bot every time it has been asked, and that the early-banking rung is
therefore only ever worth pulling for what it does to drawdown — that trade has not been measured.

⚠ **The run the justification rests on no longer exists.** The comments cite run `f3e8bc41db50`
for "the two fib targets sit at a median 1.10R and 1.76R and are reached by 137 and 59 of 245
trades". That run is **not in `command-center/backend/data/lab.db` and has no artefacts on
disk** — it is only quoted, in this strategy's committed docs and in the stashed test file. The
figure cannot be re-derived from this machine, so re-measure it rather than quoting it onward.

## What would need to happen before any of it could be committed

1. **A paragraph in `strategies/python/sos_fade/CLAUDE.md`.** There is nothing there about
   any of the three, so the commit hook will refuse the commit outright.
   ⚠ That file is 298 KB — far over the doc-growth ceiling — so adding to it will trip the guard.
   Trim something in the same edit, or the reminder is earned.
2. **A measurement in the commit message** (`MEASURED:` / `TESTED:`), because this is a strategy
   path. The tests give you the `TESTED:` half; the `MEASURED:` half does not exist yet.
3. **A parity decision.** There is **no TradingView side for any of the three** — nothing in
   `indicators/` mentions them. While they are off, the parity gate is unaffected; the moment
   one is switched on, the Python and the Pine are trading different ladders. Two of the three
   are re-entry-only, which is already a lab-only path the gate does not cover; the early-banking
   rung is on the shared ladder and would need Pine before it could ever go live.

## What it does NOT touch

- **The live bot is untouched, and pulling this stash cannot change that.** The frozen deployment
  at `algos/markets/fx/instances/sos_fade_demo/deployed/` contains none of it, and only a
  promote could move that.
- With every setting left at its default the committed ladder is unchanged — the early-banking
  branch reduces to the exact expression that ships today when its percentage is zero.

## Two things the author deliberately did NOT fix, and you should not "tidy" either

- The shared target ladder was changed as an **offset on the original branch** rather than
  rewritten. A cleaner rewrite that subtracted the already-filled quantity changed behaviour in
  24 partial-fill states — none of them this feature's business, and a silent fix to a shared
  path is indistinguishable, in anyone else's run, from a defect this change introduced.
- A **pre-existing inconsistency in the step trail on a flipped re-entry** is recorded in a
  comment rather than corrected, because correcting it would change what today's shipped
  configuration trades. It is unreachable in the swept basis.

---

## The exact setting names, for whoever restores the stash

Only needed to grep the stash or read the diff.

```
exec_tp0_pct            "Vol rung size %"                             default 0.0   (off)
exec_tp0_atr_x          "Vol rung distance (x ATR14)"                 default 1.2
exec_sec_tp2_pct        "Re-entry banks at its second target (%)"     default -1.0  (inherit)
exec_sec_trail_at_tp1   "Re-entry trails from its first target"       default False (off)
```

**Files in the stash:**

```
M  strategies/python/sos_fade/config.py
M  strategies/python/sos_fade/execution.py
M  strategies/python/sos_fade/sos_fade.meta.json
?? strategies/python/sos_fade/tests/test_vol_rung.py
?? strategies/python/sos_fade/tests/test_sec_tp2_pct.py
?? strategies/python/sos_fade/tests/test_trail_at_tp1.py
```

**Provenance:** written by a Claude Code session on Aaron's Mac on 2026-08-26 (test files created
08:22, 09:50 and 11:09; the two source files last written 2026-08-27 14:27). Nothing in git
history, nothing from the trading box.
