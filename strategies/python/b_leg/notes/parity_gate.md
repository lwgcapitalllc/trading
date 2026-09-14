# Notes — The parity gate — build history, refusals and gotchas

`compare_bleg.py`'s build history and PARITY GREEN runs, plus every gate-specific rule found the hard way since: the sub-15m configuration refusal, the seventeen-day stale-export incident, the unconfirmed-tail reporting window, the scale-in default that its Pine cannot check, the missing-column refusal, and the test replay cache. Moved VERBATIM out of `strategies/python/b_leg/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## The parity gate — `tools/compare_bleg.py` + `b_leg_strategy_export.pine` (built 2026-07-26)

### The unsettled tail is a DAY, and the pivot lookahead was too small (2026-09-03)

🟢 **GREEN on a fresh 15m export — `engines/VANTAGE_XAUUSD, 15_b480e.csv`, 21,702 bars compared,
exit 0 at warmups 100 / 500 / 1000.**

🔴 **THE TRIM ADDED ON 2026-09-02 WAS SIZED TO THE SWING LOOKAHEAD AND DID NOT COVER THIS FORK'S
OTHER UNSETTLED DEPENDENCY.** It inherits SOS Fade's DAY-HIGH liquidity line, which is time-based: on
the fresh export Python placed a new Day High at 2026-09-03 00:45 and swept it while Pine still
pointed at the previous one, **65 bars from the end — four times outside a 15-bar trim.** ~230
COMPLETED day boundaries in the same file agree exactly, which is what says settling rather than a
bug. The trim is now the export's final calendar day, **floored by `major_length`** so a file
ending minutes into a new day still covers unconfirmed pivots.

⚠ **`unsettled_tail` is IMPORTED from `sos_fade/tools/compare_strategy.py`, not copied** — this
gate already imports that module's decoders, and two copies of a trim rule is how the two drift.
SOS Fade hit the identical defect the same day; the transferable half is that **a sibling gate's tail
constant is sized to ITS unsettled dependency and does not transfer**, and neither does a bar count
fitted to one export.

🔴 **`test_the_tail_is_the_pivot_lookahead_and_nothing_wider` IS RETRACTED AND RENAMED.** Its claim
— one bar wider and the gate skips settled bars — was right about padding and wrong about the set
of things that do not settle. **It stayed green through the whole period the gate was red.** The
constant is now a FLOOR, and the widening is measured rather than "to be safe".

⚠ **Three mutations SURVIVED the entire suite when this landed** — reverting the trim to the bare
constant, dropping the lookahead floor, and disabling the empty-window refusal. The first was
caught only by one real export on one machine, which is exactly the fragility rule 22 warns about.
Three tests now cover them; all three were watched RED.


🟢 **GREEN, re-run 2026-08-23 on `engines/VANTAGE_XAUUSD, 5_f8228.csv` — 20,573 M5 bars, identical
from bar 0, no warmup needed.** ⚠ Rule 14 still applies: it says the two AGREE, never that either is
RIGHT, and nothing about a branch neither entered. 🔴 **The export before it was RED, and the code was
innocent — a stale twin reds this gate exactly like a bug does.** Before hunting a defect, check which
side is older: prove the red at HEAD first (it was), then look at the export's date.

`strategies/tradingview/b_leg_strategy_export.pine`
= `b_leg_strategy.pine` (body byte-identical, only the line-40 `strategy()` title differs) + an
appended PARITY EXPORT block. Export it from a 15m XAUUSD chart, then:

```
command-center/backend/.venv/bin/python strategies/python/b_leg/tools/compare_bleg.py <export.csv> --warmup N
```

Exit 0 = bar-for-bar identical. It is also registered in `backtest/tools/verify_parity.py`, so the
one-shot "is everything in sync?" run covers the B leg now.

**What it diffs, and why it is NOT a flag on `compare_strategy.py`.** The two bots diff DIFFERENT
fields. In this fork SOS Fade never places an order, so:
- `px_dec_bits`' arm bits are the **B-LEG** arm (`bLegLongArm`/`bLegShortArm`), not `longArmed`.
  Diffing `longArmed` here would test a decision that never happens.
- `px_edge` is the frozen band's 0.5 edge, not an FVG edge.
- `px_tp1`/`px_tp2` are their own columns because the B leg derives its ladder from the band
  (TP1 = 2·edge − origin, TP2 = the expansion extreme) instead of reading fib levels.
- `px_stages` IS still diffed: the B leg arms off the SOS Fade sequence's death, so an SOS Fade stage drift is
  where a B-LEG mismatch usually ORIGINATES. It turns "a trade differs" into "the upstream moved".

What IS shared — the packed `cfg_*` decoding — is imported, not duplicated: both export Pines plot
`cfg_*` with one identical scheme on purpose, and `compare_strategy.config_from_export` now returns
the caller's config CLASS, so passing a `BLegConfig` gets one back with `bleg_max_days` intact.
`allow_bleg=True` is needed because the SOS Fade decoder (correctly) REFUSES an export with `execBLeg` on,
and this fork's export always ships it on.

**The `bl_*` columns are the point.** They carry the TRACKER's own state — `bl_bits` (on/tap per
side), `bl_bars` (the armed bar per side, packed as bar+1 so 0 = none), and the four band prices per
side (top / bot / inv / tgt). Every new B-LEG rule lives in the tracker (band freeze, deepest-band
migration, target track, tap, staleness death), and a bug there shows as a wrong band price MANY bars
before it becomes a wrong trade. Without them a mismatch says "a trade differs" and nothing about why.

**Two things that are NOT in the export, deliberately:**
- `execSlLevel` — the fork has no such input (the B-LEG stop is its band ORIGIN, not a fib on the SOS Fade
  leg). `cfg_strcodes`' SL slot is pinned to the "1.0" code so the shared decoder reads
  `exec_sl_level = "1.0"` — correct-and-unused here, and one decoder keeps serving both exports.
- The Diagnostic Log block, dropped in the export copy to stay under Pine's token cap (CE10117),
  exactly as the SOS Fade export does.

**Regenerate it whenever `b_leg_strategy.pine` changes** — the split point is exact and is
recorded in the export's own header (`sed -n '1,4486p'`, then re-append the block and restore the
line-40 title). A new trade-affecting input = a new `config.py` field + a new `cfg_*` plot + a new
read in `compare_bleg.config_from_export`, in the SAME commit as the Pine change.

Offline guard: `tests/test_compare_bleg.py` (8 tests) round-trips the tool — run the bot, serialise
its own decisions + tracker state into an export-shaped CSV using the Pine's packing, feed it back,
require exit 0 — then plants a `bl_l_top` mismatch and a `px_dec_bits` mismatch and requires the tool
to catch each at the right bar. The encoder there is written from the Pine's plot expressions rather
than from the tool's decoder, so it also catches the two drifting apart. It uses 30 synthetic days,
not 10: on 10 no leg ever ARMS, so the `bl_*` diff would prove nothing.

Two of those eight cover the **partial-export** case added 2026-07-31 — one re-packs `bl_bars` as
if the chart held 15,362 bars before the export's first row and requires exit 0, the other shifts
all but ONE armed bar and requires that odd one to still be caught. They are a pair on purpose:
the first alone would pass just as happily if the tool had stopped diffing the bar index at all.

### PARITY GREEN 2026-07-31 (exit 0) — the session-window build

`compare_bleg.py "VANTAGE_XAUUSD, 15_cabec.csv" --warmup 800` → **exit 0**. 6,329 bars,
2026-04-27 → 2026-07-31. Green at warmup 1200, 2000 and 3000 too, so nothing late is hiding
behind the skip.

**Why the warm-up is 800 and not 100.** This export is a partial chart — it starts 15,362 bars
into the loaded history, so Pine walks in already holding a frozen band that the Python side has
never seen. It has to wait for a whole fresh band to form. That is cold start in the ordinary
sense, just a longer one than a from-bar-zero export needs; the same run at `--warmup 400` fails
only on `bl_s_top`-style band prices Pine carried in, never on a decision.

**What it proves that the 21k-bar 2026-07-29 run could not.** The window is entirely inside
BST/EDT, which is exactly where the new city-clock session windows differ from the old fixed
GMT-4 ones. `b_leg_strategy.pine` had been a genuine fork on those windows; a Python side
still on the old offsets would have disagreed with Pine on every session boundary here. Config
decoded off the export: `cfg_exitmode = 20` (the ratchet trail), `cfg_trail_pct = 1`,
`cfg_tp1_pct = cfg_tp2_pct = 0`, `cfg_bleg_days = 1.25`, risk 10%, `aplus_window = 4320`.

Exercised: 605 / 695 bars with a live long / short leg, 2,063 bars armed, **2 entries, 2 trades
graded, sum 5.73R**. The usual caveat applies harder than ever on a 3-month window — that trade
count proves the two implementations agree and says nothing about the edge.

**It also found the harness bug described in "Last reviewed"** — the raw `bar_index` comparison.
Worth restating as a rule: a round trip proves the two halves agree, and a full-history export
hides an origin assumption, so **the first PARTIAL export is its own kind of gate.**

### PARITY GREEN 2026-07-29 (exit 0) — the ratchet build

`compare_bleg.py "VANTAGE_XAUUSD, 15_ab202.csv" --warmup 100` → **exit 0**. 21,493 bars,
2025-08-31 → 2026-07-29. Green at warmup 200, 500, 1000 and 2000 as well, same cold-start
picture as the first run.

This is the run that clears the 2026-07-28 stale-export warning. What makes it non-vacuous is
what the export DECODED, not just the bar count: `cfg_exitmode = 20`, `cfg_trail_pct = 1`,
`cfg_tp1_pct = cfg_tp2_pct = 0`. The tens digit of `cfg_exitmode` is the trail method, and it
went 2-way → 3-way when the ratchet landed. An OLD export would have decoded the ratchet as
the plain structure trail and gone green while comparing two different exit ladders — this one
carries the third code, so the Python side really was configured to the ratchet.

5 trades graded, **sum 10.91R** over the window. That trade count is the same warning as ever:
enough to prove the two implementations agree, nowhere near enough to tune against.

### PARITY GREEN 2026-07-26 (exit 0) — first real export

`compare_bleg.py "VANTAGE_XAUUSD, 15_9b74a.csv" --warmup 100` → **exit 0**. 21,231 bars,
2025-08-31 → 2026-07-24. Green at every warmup from 100 to 2000, so the ~100-bar skip is genuine
engine cold start, not a mask.

**The run was not vacuous** — it exercised the machinery this harness exists to check:

| what | count |
|---|---|
| bars with a live long / short leg | 2,195 / 1,010 |
| bars tapped (long / short) | 568 / 141 |
| bars ARMED (long / short) | 2,024 / 862 |
| entries taken (long / short) | 2 / 3 |
| trades closed and graded in R | 5 |
| distinct frozen band prices diffed | 48 long / 45 short |

So the band freeze, the deepest-band migration, the target track, the tap and the staleness death
were all diffed against Pine across ~90 distinct bands — not just the 5 bars that became trades.
That breadth is the whole reason the `bl_*` columns exist.

**The first run found a bug — in the HARNESS, not the port.** `bar 680 px_entry_dir: py=1 pine=-1`.
`_py_row` derived the trade direction from `Fill.qty`'s sign, but `qty` is NOT signed in this
codebase — `Fill.dir` is. Every short read as a long. Fixed to read `Fill.dir`.

**Why the round-trip test could never have caught it:** the test's encoder had the identical wrong
derivation, so encoder and decoder agreed and the round trip passed. A round trip only proves the
two halves are consistent with each other, never that either is right. That is the structural limit
of the technique, and it is why a real export is the gate.
`test_entry_direction_comes_from_fill_dir_not_qty_sign` now asserts against the FIELD rather than
against a round trip — the only way a shared-mistake bug like that gets caught offline. Apply the
same shape to any future packed column whose value is DERIVED rather than copied.

**Config decoded off the export** (all of it correct): `bleg_max_days` 1.25, SOS Fade-priority ON,
`execBLeg` ON, Structure trail, TP2 floor = TP1 price, TP1/TP2 30/40%, risk 10%.

Backtest numbers are now validated logic, not directional guesses — with the standing caveat that
**5 trades is far too thin a sample to tune against.** Parity says the code is right; it says nothing
about whether the edge is real.

## 🔴 This gate refuses a sub-15m export too, and the green above was re-checked (2026-08-23)

This fork's engine config is the parent's with one field replaced, so it inherits the
parent's **15-minute gap pins** while its Pine reads those two values off the CHART. Below
15m the two sides are configured differently before a bar is replayed, so `compare_bleg.py`
REFUSES rather than reporting a mismatch. Full reasoning and the measurement that forced it:
`strategies/python/sos_fade/CLAUDE.md` → *The gate REFUSES an export from a chart faster
than 15m*.

✅ **The M5 green recorded above STANDS, and it was re-measured rather than defended.** That
export was replayed a second time with the sub-15m pair the Pine actually used and came back
green on every bar as well — so the difference provably decided nothing there. It could not:
a B-LEG entry rests on the frozen band, never on a gap.

🔴 **That is exactly why the check was still added.** *"It did not bite this time"* is a fact
about one export and one entry rule, and the next run gets no such promise. A green obtained
under a configuration mismatch is right by luck, and luck is not a gate.

**Tests:** 2 in `tests/test_compare_bleg.py` — the refusal and its deliberate override —
both watched RED by mutation.

## 🔴 The gate was RED for seventeen days and the CODE was innocent — the export was stale (2026-09-02)

`compare_bleg.py` failed at `px_l_stage: py=3 pine=2` on 2026-05-08 02:30. Nothing was wrong with
this bot. **The export was taken on 2026-08-16 and two STRUCTURE fixes landed after it** —
`700f7f65` (the tied-extreme duplicate swing) and `f4b0410b` (a break may not install a swing the
break itself refused). Both change the swing anchor the fib is measured from, so Python extended
its anchor where the older chart did not, which moved the 0.5 level below the bar's low and latched
the half-retrace the Pine never saw. A fresh export cleared it.

🔴 **THE PROOF THAT IT WAS THE EXPORT, NOT THE CODE, IS THAT THE TWO PINE EXPORTS DISAGREED WITH
EACH OTHER.** The SOS Fade export (2026-09-02) and the B-LEG export (2026-08-16) start on the same bar of
the same Vantage 15m chart, and at that timestamp one says stage 3 and the other says 2. **Python
matched the newer one.** Two exports of one chart disagreeing is a statement about WHEN they were
taken; nothing in either Python package can produce it.

⚠ **The diagnosis cost four wrong hypotheses, and every one was ruled out by MEASUREMENT rather
than by reading**: a re-armed SOS carrying its predecessor's latch (zero re-arms in the whole run),
the EQ/FVG coupling (flipping it moves no stage), the packed structure codes (they carry only the
stop level and the HTF flags), and the two fib toggles (Python already matched the export).
**A source comparison cannot settle this class of question** — the fib logic, the anchor
assignment and the inlined structure engine are all byte-identical between the two Pine files.

⚠ **This is the SECOND time a stale twin has reddened this gate** (the first is recorded under
*The parity gate*). **Check the export's DATE against the Pine's git log before hunting a defect**,
and prove the red at HEAD first — it was, in a throwaway worktree, byte-identical failure.

## The gate does not compare the UNCONFIRMED TAIL (2026-09-02)

The last `UNCONFIRMED_TAIL` bars of an export are skipped, and the number is **DERIVED from
`major_length`, never typed**. Swings come from `ta.pivothigh(high, majorLength, majorLength)`,
which cannot confirm a pivot until `majorLength` further bars exist — so an export pulled from a
LIVE chart ends with bars whose structure has not settled on the Pine side, and Python is entitled
to a different answer there. MEASURED on the fresh export: green on every bar except the last 10,
and trimming turned the whole run green.

⚠ **It is a REPORTING window, never a shortened replay.** Every bar is still stepped, so the state
carried into the compared bars is the state the whole export produced, and a real drift starting in
the tail still shows on the next export.

⚠ **It ANNOUNCES itself on every run, and the SUCCESS line carries it too** — *"every bar from N to
the last 15 (unconfirmed swings, not compared)"*. A silently-trimmed comparison printing PARITY OK
is a gate claiming ground nobody covered, which is the over-claiming green this repo keeps
recording. `--tail 0` diffs them anyway.

🔴 **A TEST DEFINED RELATIVE TO THE NUMBER IT POLICES CANNOT POLICE IT, and that was MEASURED here
rather than reasoned.** `test_a_mismatch_OUTSIDE_the_tail_is_still_reported` plants at
`len - UNCONFIRMED_TAIL - 1`, so widening the constant moves its own plant with it — a 10x widening
reddened nothing. The value is pinned separately by
`test_the_tail_is_the_pivot_lookahead_and_nothing_wider`, which asserts the DERIVATION rather than
the number 15. **Its docstring says what it cannot catch**, because a test naming the wrong
mutation reports coverage that is not there.

**Tests: 4 in `tests/test_compare_bleg.py`, 5 mutations each watched RED against its own named
test** with an unrelated control staying green. The first two are a PAIR — *it is ignored* alone
would pass just as happily if the diff had stopped reading that column.

## ✅ This fork's shipped default is back inside its gate (2026-09-07 → 2026-09-10)

`BLegConfig` extends `SosFadeConfig`, so it inherited `exec_scale_in` when that default moved
off → on for SOS Fade on 2026-09-06. **The B-LEG Pine has no scale-in at all** — no input, no code,
no `cfg_scale_in` column — so the gate decodes it OFF on every export, correctly, while the SHIPPED
default was ON: a mode nothing could check. ✅ **Pinned OFF in `config.py` on 2026-09-10.** Aaron's
2026-09-06 call named SOS Fade, `b_leg_demo` had already pinned it off (`ca39c72b`), and the adds
bought nothing — MEASURED on PU Prime `XAUUSD.p`, 2020 → 2026-08-23: same 101 trades, **+20.07R on,
+20.20R off**. The overlap audit was re-recorded the same day. BOS had the same inheritance and it
put that bot's gate red (`strategies/python/bos/CLAUDE.md`).
`test_the_fork_does_not_add_to_winners_its_pine_cannot` goes red if the pin goes or the Pine gains
the input — the day the pin has to come out. Watched red both ways.

✅ `_write` still pins it off for a case that asks for it ON, and
`test_the_export_scheme_has_NO_scale_in_column_so_this_gate_cannot_cover_one` states what is left of
the hole — a config switched on by hand — as a test rather than a comment.

✅ **The golden export, 2026-09-10: `exports/golden/`, run by step 15 on every clone.** 20,220
Vantage M15 bars; every one of 19,668 matches from a MEASURED warm-up of 468 (the short-side SOS Fade
arm stage this fork inherits — SOS Fade measured the same 468 on the same window). 10 B-leg trades
close in the window, +3.13R on the chart.

### Two more columns the encoder was missing

`cfg_time_stop` and `cfg_time_stop_hrs` are plotted by this fork's export Pine and were absent from
the fixture, so the tool decoded the clock as OFF while the fixture replayed with it ON. Added.

⚠ **The clock is set to TWO HOURS in the non-default case on purpose, and the number is measured.**
At six hours and above the trade closes on its ladder either way (+1.26R with the clock on or off),
so the mutation that drops those columns SURVIVED — the fixture could not tell the two
configurations apart. At two hours the clock fires and the same trade closes −0.5753R, and the
mutation dies. **A column nothing can distinguish is a column whose absence no test will report.**

## 🔴 The gate REFUSES an export missing a column it compares (2026-09-10)

A file that is not this fork's twin crashed the gate with a `KeyError` out of `_expand`, and a
PARTIAL export passed, because the diff skipped any column it lacked. **Both now exit 2 by name**
through `missing_columns_refusal` — the SOS Fade gate's function, shared rather than copied; rule and
story in `strategies/python/sos_fade/CLAUDE.md`. The loop's skips are deleted, and a test holds every
compared column to this fork's own twin (every one is plotted today, so no real export is refused).


## Its gate tests replay once per distinct input (2026-09-10)

`tests/test_compare_bleg.py` builds each synthetic export once per config and remembers the gate's
replay keyed on the settings and engine settings it DECODED plus the bars byte for byte — 52s → 20s
on one core. The two memos are separate (seeding the gate's from the export's own replay would
compare the fixture with itself), and the round-trip control runs the REAL class. 🔴 **7 bugs planted
in the gate, 7 caught by the case each names**, including a gate that never decodes the settings —
the one case a looser key would have hidden. Map in the file.
