# Notes — Level memory: the level the bot ALREADY traded

**Read before touching:** `strategies/python/sos_fade/level_memory.py`, the `exec_lvl_*` fields in
`config.py`, or the level-memory branches in `execution.py` and `dual_clock.py`.

**Status: MEASURED AND REFUSED (2026-09-23, Run 44). Ships `exec_lvl_memory = False` and stays
off.** It is kept, tested and documented so the question is answered rather than re-asked, and so a
later run can re-measure it. Nothing about the shipped book changes.

---

## What it is

Aaron, 2026-09-22, watching it happen live: the Monday short filled at the gap edge the setup
published, tagged its first target, moved the stop into profit and closed there for roughly
nothing — and about twenty hours later price came all the way back to that same price and sold off,
with the bot holding nothing. *"We did not have any logic to take that trade. Why? How many trades
like this have we been missing?"*

**Why it had nothing, read out of its own decision record** (`algos/ledger_archive/sos_fade_demo/`,
2026-09-21 and -22) — two independent causes, either one sufficient:

1. **The setup DIED at 05:15 UTC when structure re-broke.** `Execution._sync_gap_latch` clears the
   published entry price with the setup, which is correct for everything that reads it. The side
   effect is that the bot has no memory of a level it filled an hour earlier. The watch moved to a
   new level, and price ran through that one at 19:30 UTC.
2. **No shift of structure ever printed on the short side that evening.** The sequence sat at its
   first stage — a sweep and nothing more — so nothing armed and nothing could be placed.

✅ **The 19:44 and 21:20 UTC restarts did NOT cost the trade, and must not be written up as if they
did.** The decision record is unbroken 17:45 → 20:45.

## The shape of the feature

| | |
|---|---|
| LEVEL | the price the PRIMARY itself entered at — the number the execution published and filled on, never a re-derived gap edge |
| ARMED | from the bar that primary CLOSES, for `exec_lvl_days` |
| AWAY | price must first travel `exec_lvl_away_r` x that trade's own 1R away, in its own direction |
| ENTRY | a limit at the level, same direction, filled on the fill clock |
| STOP | `exec_lvl_stop_frac` x the ORIGINAL trade's stop distance |
| QUIET | by default it rests only while no primary limit is on the book on that side |

🔴 **IT IS NOT `exec_sec_poi_fallback` (Run 41).** That one rests the re-entry at the primary's own
entry price WHILE THE SETUP IS STILL ALIVE. This is the opposite case: the setup is gone.

## Where it lives, and why it is where it is

- `level_memory.py` holds **no structure engine, no fib and no gap rule.** Every price it hands out
  came from a trade the execution already booked. A second reading of the entry rules is how two
  halves of one strategy silently disagree.
- It emits **`SecArm`, the re-entry's own record**, so sizing, the minimum-stop floor, the budget
  fit, the fill and the ladder are all the re-entry's existing path. The only thing that tells the
  two apart at the far end is `src`, which `_PROTECT_RULES`, `_first_rung` and `_tp1_pct_for` key on.
- **It is NOT gated by `exec_secondary`.** It shares the order path and nothing else — no shift
  leg, no live setup, no primary outcome — and Run 42 graded it with the re-entry pinned off.
- `DualClock._merge_arm` folds it in **per side, with the re-entry winning any contested side.**
  One position slot means two armed sources are two claims on it, not two trades.
- **It survives `reset_fast`.** The re-entry's arm state goes when the fast feed is rebuilt because
  its latches are fast BAR NUMBERS; nothing here is a bar number.

## The two defects this build produced, both found by running it

🔴 **THE MEMORY RESURRECTED ITSELF AND THE FEATURE BECAME A CASCADE.** The execution keeps its
last-closed-primary record standing for days and this class POLLS it, so a level retired by a fill
dropped to `None` and was rebuilt from the same record on the very next bar, for ever. **MEASURED
on the first replay: 141 extra trades where Run 42's screen found 39 returns it could take at all,
and +227.5R fell to +205.4R.** Fixed with a per-side *last close time this side has ever taken*
marker — *held it* and *never saw it* must not be the same value, which is rule 1 from the other
end. ⚠ The first version of its test PASSED against the bug, because its bars could not re-latch
the away gate; the test now carries price a full 1R away again on purpose.

🔴 **`run_report.py` COULD NOT SEE THE FEATURE AT ALL WITH THE RE-ENTRY OFF.** Its `_choose_replay`
asked only about `exec_secondary` when deciding whether to take the fast-clock path, so a run with
the level memory on and the re-entry off took the 15m-only path and booked NONE of its trades — the
config said the feature was on, the replay could not reach it, and the report said nothing. That is
the exact defect that function's own docstring exists to prevent, arriving through a second door.
**Anything that needs the fast feed must be asked about there.** Fixed and tested 2026-09-23.

## The result

Full numbers in `sos_fade_optimization.md` → Run 44. The short version: **65 level-memory trades in
6.7 years are worth +0.85R, and drop the single best and they are worth +0.80R.** They displaced a
+22.31R primary on 2023-01-12, so the replayed book falls 168.1R → 150.7R primary-only and
227.5R → 215.7R with the re-entry on. **The screen's +16.35R did not survive the position slot** —
the same shape as the no-gap entry, which screened positive and replayed at −15.3R (Runs 28→29).
