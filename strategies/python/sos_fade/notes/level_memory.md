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

---

## Run 45 — PRE-REGISTERED 2026-09-23, written BEFORE any filtered replay was run

Aaron, off Run 44: *"did you add any confluences to test how we can filter out some of the losers
... in this case it came back to the original FVG"*. Three filters, fixed here before looking. Each is
tested ALONE, on top of the Run 44 feature exactly as it shipped (half-width stop, 2R, 72h, quiet
gate on), in the shipped configuration (re-entry ON), same window, bars and costs as Run 44.

🔴 **Why the rules below are fixed in advance.** The feature adds 65 trades worth +0.85R. Any filter
chosen AFTER seeing which of 65 trades won will look good — that is a fit, not a finding. So the
definitions, their one parameter each, and the pass bar are written down first, and all three are
reported whatever they show.

| # | Filter | Definition — every piece reuses a reading the bot already has |
|---|---|---|
| 1 | **Gap still open** | When the memory is taken, find the gap of the trade's own direction on the gap engine's live list whose band holds the level (within 0.1 x the original 1R). The limit rests only while THAT gap is still on the live list. |
| 2 | **Sweep first** | The limit rests only while the primary's own liquidity-sweep reading is live on the trade's side — buy-side swept for a short, sell-side for a long. The same reading that arms a primary. |
| 3 | **Shift confirms** | No resting limit. Once price has tapped the level, wait up to **24 fast bars (2 hours on the 5-minute feed)** for a shift of structure in the trade's direction; enter at the next bar's open, stop at the most extreme price since the tap, target 2R of THAT risk. Refused if that risk is wider than the original trade's full 1R. One attempt per level. |

⚠ **Filter 1 has a known blind spot, stated before the result:** the gap engine keeps at most seven
gaps and pushes the oldest out, so a gap can leave the live list without price ever closing through
it. Filter 1 therefore reads *still open AND still recent*. If it passes, how often it refused on a
push-out rather than a fill gets measured before it is believed.

**The pass bar — all three, or it fails:**
1. The whole book beats the shipped **+227.5R** (Run 44's baseline) — net of anything it displaces.
2. The level-memory trades themselves are positive in BOTH halves, split at 2023-05-01 (Run 42's split).
3. They stay positive with their single best trade removed.

A filter that passes gets the primary-only replay as well before anything is said about it.

### Run 45 — the result: all three FAIL. `exec_lvl_confluence` stays at None, the feature stays Off

Full numbers in `sos_fade_optimization.md` → Run 45. Scored exactly on the bar above.

| Filter | Book (re-entry on) | Added trades | Halves | Drop best | Verdict |
|---|---|---|---|---|---|
| Gap still open | **+230.8R** vs +227.5R | 22, +2.33R | +1.40 / +0.93 | +0.25 | passed — then **failed primary-only**: 166.1R vs 168.1R, added 21 worth −2.04R, first half −3.97 |
| Sweep first | +215.7R | 66, +8.45R | +5.31 / +3.14 | +4.42 | **fails bar 1** — it displaced the same +22.31R primary on 2023-01-12 |
| Shift confirms | +227.5R | **0** | — | — | **never trades** — see below |

- 🔴 **The gap filter's pass was the re-entry's, not its own.** With the re-entry on it added +3.33R;
  with it off the same filter lost 2.04R. The +5.98R of 2025 carries it both times, and 2026 is
  negative both times. Its eviction blind spot was therefore not measured — nothing survived to
  need it.
- **The sweep reading barely filters.** 66 added trades against Run 44's 65 unfiltered: a sweep is
  live on the trade's side almost always, so it removes little and still collides with the
  2023-01-12 winner. The added trades themselves did improve (+0.85R → +8.45R), which is the one
  thing here worth remembering — but a filter that cannot avoid the slot collision cannot ship.
- **"Shift confirms" is wired, and its rule is simply too tight to fire.** Instrumented over 2025:
  ~20 taps, 40 fast shifts in the year, only **2** landed inside a tap window, and both needed a
  stop wider than the original 1R, which the pre-registered rule refuses. Loosening that cap
  after seeing this would be the fit the pre-registration exists to prevent.

**Where this leaves the idea.** Four measurements now (Runs 42, 44, 45) say re-trading a level the
primary already used does not add money once the position slot is honest. The limiting cost is
not the losers these filters target — it is the one displaced primary. Not worth a fourth filter.

