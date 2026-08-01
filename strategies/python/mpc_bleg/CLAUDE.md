# CLAUDE.md — strategies/python/mpc_bleg/ (the MPC B-LEG bot)

**Purpose:** The B-LEG setup as a standalone Python strategy — a port of
`indicators/mpc_b_leg_strategy.pine` (Aaron's brother's B-LEG fork of MPC-JARVIS). The
B LEG is the SOS whose retrace arrived LATE: an A+ reversal dies at 2/3 on a continuation
BOS before it retraces, the Sniper-Zone band (0.382–0.5) of that break is frozen, and a
resting limit at the 0.5 edge waits for the late return.
**Scope:** This bot only — its tracker, order layer, config, tests. It does NOT own the
engines (`engines/`), the replay runner (`backtest/`), or the A+ machinery it reuses
(`strategies/python/mpc_sos_fade/`).
**Status:** Built + unit-tested (19 tests green) + **Pine-parity GREEN (exit 0), re-validated 2026-07-31**
on a fresh 6,329-bar `VANTAGE_XAUUSD, 15m` export off the session-window build — bar-for-bar
identical decision stream. The harness is `tools/compare_bleg.py` +
`indicators/mpc_b_leg_strategy_export.pine`, registered in `verify_parity.py`. **Sample size is the
open question, not correctness:** the validated windows have produced 2–5 trades each, far too thin
to tune against. See "The parity gate".
**Last reviewed:** 2026-07-31 — **the session-window fork is CLOSED and proven, and the harness had a
latent hole that a partial chart export walked straight into.** `mpc_b_leg_strategy.pine` had never
received the DST-aware session windows its A+ parent has carried since 2026-07-12; both were synced
and `compare_bleg.py` re-run on a fresh export → **exit 0 at `--warmup 800`**, green at 1200 / 2000 /
3000. **What makes this run the right one for that fix:** the window is 2026-04-27 → 2026-07-31,
which sits ENTIRELY inside BST/EDT — the half of the year where the new city-clock windows and the
old fixed GMT-4 windows actually disagree (New York `0800-1700` America/New_York is 12:00–21:00 UTC
under EDT, an hour earlier than the old `0900-1800` GMT-4). A stale Python side would have disagreed
with Pine on every session boundary in this export, so green here is a real result rather than a
window where the two happen to coincide. **The harness hole:** `bl_l_bar`/`bl_s_bar` carry Pine's
`bar_index`, which counts from the first bar the CHART loaded, while the Python tracker counts from
the export's first ROW. Every previous export was the whole loaded history, so the two origins
coincided and nobody noticed the assumption. This one starts 15,362 bars in, and all 2,409 armed-bar
comparisons failed at exactly that constant — the logic was identical the whole time. `compare_bleg.py`
now MEASURES the origin (the modal `pine - python` difference) instead of assuming zero, and the
normalisation is deliberately majority-based so a genuine drift in WHICH bar armed is a minority
offset and still fails; `test_partial_chart_export_still_parity` and
`test_offset_normalisation_still_catches_a_real_armed_bar_drift` pin both halves. **Generalise it:
any parity column holding a Pine BAR INDEX is export-window-relative, and a harness that compares one
raw is only correct by the accident of a full-history export.** 19 tests green.
Earlier: 2026-07-30 — **the parent's new MINIMUM-STOP guard is PINNED OFF here, and is inert
on this path.** `mpc_sos_fade` gained `exec_min_stop_mode` / `exec_min_stop_val` (refuse a setup whose
stop lands too close to the entry — `qty = risk / stop_distance`, so a collapsing stop buys an enormous
position). It does not reach this fork: the floor is enforced in the parent's `_place_entries`, which
`BLegExecution` overrides, and `mpc_b_leg_strategy.pine` has no matching input to be parity-checked
against. `BLegConfig` pins the mode to `"Off"` so a future parent default change cannot silently claim a
guard this fork never runs. The hazard is also structurally absent here — a B leg's stop is the band
ORIGIN, always a full band away from the 0.5 entry edge, never a fib that can land on top of it. Porting
it = the Pine input + the floor check in this fork's `_place_entries` + a `cfg_min_stop` export column, in
one commit, then re-run `compare_bleg.py`. Nothing else changed and the parity run below still stands.
Earlier: 2026-07-29 — **the stale export is CLEARED: `compare_bleg.py` re-run GREEN on the
ratchet build.** `compare_bleg.py "VANTAGE_XAUUSD, 15_ab202.csv" --warmup 100` → exit 0, 21,493 bars,
2025-08-31 → 2026-07-29, still green at warmup 200/500/1000/2000. The export decoded
`cfg_exitmode = 20` (the new 3-way trail digit reading as "Structure + % ratchet"), `cfg_trail_pct = 1`
and `cfg_tp1_pct = cfg_tp2_pct = 0` — so the ladder changes below are proven through the export, not
merely present in it. `mpc_b_leg_strategy.pine` also compiles clean in TradingView. The ratchet's
43% → 53% run-capture caveat below still stands: parity proves the two sides AGREE, never that the
setting is right for B legs. Earlier: 2026-07-28 — **`mpc_b_leg_strategy.pine` caught up to the A+ exit ladder**, so this
package's two divergence pins are gone: `exec_runner_trail` is INHERITED again ("Structure + % ratchet",
with `exec_trail_pct` alongside it) and the TP rungs sit at the inherited 0/0. The Pine also gained the
`qty_percent = 0` guard — without it a 0 rung closed the WHOLE position at TP1, which is why typing 0
"blew up" there. Nothing changed in this package's CODE (the ladder has always lived in the parent's
`Execution`); what changed is that the config no longer has to lie to stay parity-green. ⚠ **The export
is now STALE and every B-LEG number from this build is unvalidated until `compare_bleg.py` is re-run**
— `cfg_exitmode`'s trail digit went 2-way → 3-way and `cfg_trail_pct` is new, so an OLD export decodes
the ratchet as the plain structure trail. ⚠ The ratchet's 43% → 53% run-capture result was measured on
**A+ trades only**; it is inherited for one-ladder consistency, not as a proven B-LEG result. Earlier:
2026-07-27 — the A+ blocked-setup AND missed-setup markers stay non-ported here, both now pinned by a test (the miss watch needed an explicit opt-out). Earlier: 2026-07-26 — the exit levers landed, the Pine-parity harness was built, and it came back GREEN on the first real export (see "The parity gate").

## Why it exists (the split, 2026-07-24)

The B LEG lived inside `mpc_strategy.pine` as a second setup type (`execBLeg`, default OFF).
Turned ON alongside A+ it made significantly more money, and Aaron wants to run it PARALLEL
to the A+ bot on the shared account (the portfolio-stacking seam he built). Decision:
**abstract it into its own strategy that shares the READ layer** (the engine stack + the A+
sequence tracker) and owns its OWN entry/stop/TP — because he intends to tune those
independently, which is the textbook signal to split. The coupling is only on the A+
sequence STATE (a clean read dependency, like depending on an engine), never on the A+ entry
logic. See the Pine file's header for the same reasoning.

## What it reuses vs what is new

It is deliberately ~90% the A+ bot. The fill / TP-ladder / stop-staging / %-risk-sizing /
R-grading machinery is direction- and setup-agnostic, so it is REUSED wholesale:

- **Reused from `mpc_sos_fade`:** `SignalAdapter` → `Signals`, `SosFadeSequence` → `SeqState`
  (the whole A+ engine + sequence), and `Execution` (the broker emulator + exit ladder).
- **New here:**
  - `bleg.py` `BLegTracker` → `BLegState` — the band-freeze / target-track / arm / tap /
    death state machine (Pine 3683-3758). Standalone; reads `Signals` + the `bleg_arm_*`
    flags off `SeqState`.
  - `execution.py` `BLegExecution(Execution)` — a thin subclass: `step(sig, seq, bleg)`
    stashes the `BLegState`; `_place_entries` is the ONLY override — A+ entries disabled,
    B-LEG limit rested at the band's 0.5 edge (SL beyond the leg origin, TP1 = broken swing
    extreme `2·edge−inv`, TP2 = expansion extreme `tgt`, TP3 runner). Everything from
    `_open_position` onward is the parent's.
  - `config.py` `BLegConfig(SosFadeConfig)` — a strict superset, adds only `bleg_max_days`.
  - `strategy.py` `MpcBLegStrategy(MpcSosFadeStrategy)` — inherits `_fill_model` +
    `engine_config` (the SAME `fvg_max_count=7` + `show_internal=False` pins — the B-LEG reads
    the same structure/fib engines), overrides `__init__`/`run`/`step` to splice the tracker.
    `run_dual` is disabled (no 1m secondary).

## The "A+ has priority" gate (kept for baseline; first tuning candidate)

`BLegExecution._place_entries` still computes the A+ `longArmed`/`shortArmed` via the parent's
`_armed()` and stands the B-LEG down on a side where A+ is armed — faithful to the Pine fork.
A+ never PLACES an order (the fork's whole point), it just holds the priority. When stacked
with the real A+ bot on one account the account layer re-does this arbitration, so **dropping
this gate is the first thing to try when tuning** (Aaron's own note in the Pine tooltip). Run
SOLO, the bot fires MORE B-legs than the parent did with `execBLeg` on, because no A+ position
occupies the account — that is correct and expected, not drift.

## Three parity-safe additions to `mpc_sos_fade` (do not revert)

The reuse needed three ADDITIVE, decision-neutral changes there (all re-verified: the A+'s
55 offline tests stay green):

1. **`signals.py`** — `Signals` gained `bull_bos_high/low` + `bear_bos_high/low` (the break-
   leg endpoints the band-freeze reads). Nothing in the A+ path reads them.
2. **`sequence.py`** — `SeqState` gained `bleg_arm_l`/`bleg_arm_s`, computed at the EXACT Pine
   point (Pine 3661): after the opposite-SOS death, BEFORE the continuation-BOS death clears
   `l_sos_bar` and BEFORE the half/618 latch update. This is the whole reason the sequence had
   to expose them — by the time `update()` returns, the state the B-LEG arms off is gone.
3. **`execution.py`** — the A+ arm decision was extracted from `_place_entries` into `_armed()`
   (a pure refactor) so the B-LEG subclass can reuse the priority gate. No behaviour change.

## The exit ladder is inherited (2026-07-26)

The structure runner trail, the TP2 stop-floor dropdown and the two setup toggles were ported into
`mpc_sos_fade`, and this bot picks up ALL of them for free — `BLegConfig` subclasses `SosFadeConfig`
and `BLegExecution` subclasses `Execution`, and the exit ladder lives entirely in the parent. The
full register is `mpc_sos_fade/CLAUDE.md` → `## The exit ladder`. What is specific here:

- **`exec_bleg` is re-defaulted to True.** `mpc_b_leg_strategy.pine` ships `execBLeg = true` (the
  A+ file ships it false), so `BLegConfig` overrides the inherited default to match. It gates the
  B-LEG arm in `_place_entries`; OFF the bot trades nothing, which is its only real use.
- **`exec_aplus` controls the PRIORITY GATE here, not entries.** A+ never places an order in this
  fork, so `exec_aplus=False` doesn't disable an entry path — it drops the "A+ stands the B leg
  down" gate entirely. That is the tuning experiment this file's own notes have called for since
  2026-07-24, now a one-flag run instead of a code edit. The same input was added to
  `indicators/mpc_b_leg_strategy.pine` under the label "A+ has priority (stand the B-leg down)".
- **This bot OVERRIDES TP1 / TP2 / SL** with its band prices (SL = band origin, TP1 = the broken
  swing extreme, TP2 = the expansion extreme). Everything from the stop staging down — the floor,
  the trail, both dropdowns — is the parent's, unchanged.
- **`exec_min_stop_mode` is PINNED `"Off"` (2026-07-30) and is INERT here.** The parent's
  minimum-stop guard runs inside `_place_entries`, which this fork overrides, so the floor is never
  applied on this path — and there is no `execMinStopMode` in `mpc_b_leg_strategy.pine` to be
  parity-checked against. The pin exists so a future parent default change cannot make this config
  claim a guard the code does not run. Structurally the hazard is absent too: a B leg's stop is the
  band ORIGIN, a full band away from the 0.5 entry edge, so it cannot collapse onto the entry the
  way a fib stop can. Porting it is three edits in one commit (Pine input, floor check in this
  fork's `_place_entries`, `cfg_min_stop` export column) followed by `compare_bleg.py`.

`indicators/mpc_b_leg_strategy.pine` was ported in the same pass and now matches: `execRunnerTrail`,
`execStructTrailBufTk`, `execTp2StopMode`, `execAplus`, and the `lStage2Floor` / structure-trail
exit block copied line-for-line from `mpc_strategy.pine`. **Completed 2026-07-28** — that Pine had
fallen a lever behind: it lacked the `"Structure + % ratchet"` trail method (+ `f_swingRatchet` and
`execTrailPct`), still defaulted the TP rungs 30/40, and still called `strategy.exit()` on a 0% rung.
All three were ported, so the two forks are back on ONE ladder with nothing pinned around a gap. **Not ported, deliberately:** `execSlLevel`
(the SL fib dropdown) is meaningless here because the B leg's stop is its band origin, not a fib; and
the pink blocked-trade markers, whose codes describe why an **A+** setup was refused — in this fork
A+ never trades, so those tags would report the opposite of what a reader would assume. A B-LEG
block tag would need its own code set, which is new design work, not a port.

**That non-port now also holds on the PYTHON side (2026-07-27).** `mpc_sos_fade`'s `Execution` gained
`blocks` (the same six codes, feeding the lab price chart's Blocked layer). This fork records none by
CONSTRUCTION: the recording hangs off the parent's `_place_entries`, which `BLegExecution` overrides.
`test_this_fork_records_no_blocked_setups` pins it, so restoring the parent's entry path here can't
quietly switch on tags that would mean the opposite of what they say.

**Same call for the MISSED-setup markers (2026-07-27), but this one is NOT free.** The parent's miss
watch scores how far an **A+** setup got before it died (2 of 3 / 3 of 3) — meaningless in a fork
where A+ never places an order. Unlike the blocks it runs from `step()`, which this fork delegates
straight to the parent, so it takes an explicit class-level opt-out: `BLegExecution._records_misses
= False`. `test_this_fork_records_no_missed_setups` pins it — a flag is far easier to flip by
accident than an overridden method. A B-LEG version of either marker needs its own code set (what
would "2 of 3" even mean for a frozen band?), which is new design work, not a port.

## Sizing — sizes ITSELF

`LAB_STRATEGY` declares `self_sizing: True` (like the A+ bot): `qty = equity·exec_risk_pct /
stop_distance`, so the lab's dynamic sizing engine leaves it alone and `exec_risk_pct` is the
risk knob. Registered as class `MpcBLegStrategy` (distinct from `MpcSosFadeStrategy`), so both
register and run side by side — the parallel-stack use case.

## The parity gate — `tools/compare_bleg.py` + `mpc_b_leg_strategy_export.pine` (built 2026-07-26)

BUILT, plumbing-tested, **awaiting its first real export**. `indicators/mpc_b_leg_strategy_export.pine`
= `mpc_b_leg_strategy.pine` (body byte-identical, only the line-40 `strategy()` title differs) + an
appended PARITY EXPORT block. Export it from a 15m XAUUSD chart, then:

```
command-center/backend/.venv/bin/python strategies/python/mpc_bleg/tools/compare_bleg.py <export.csv> --warmup N
```

Exit 0 = bar-for-bar identical. It is also registered in `backtest/tools/verify_parity.py`, so the
one-shot "is everything in sync?" run covers the B leg now.

**What it diffs, and why it is NOT a flag on `compare_strategy.py`.** The two bots diff DIFFERENT
fields. In this fork A+ never places an order, so:
- `px_dec_bits`' arm bits are the **B-LEG** arm (`bLegLongArm`/`bLegShortArm`), not `longArmed`.
  Diffing `longArmed` here would test a decision that never happens.
- `px_edge` is the frozen band's 0.5 edge, not an FVG edge.
- `px_tp1`/`px_tp2` are their own columns because the B leg derives its ladder from the band
  (TP1 = 2·edge − origin, TP2 = the expansion extreme) instead of reading fib levels.
- `px_stages` IS still diffed: the B leg arms off the A+ sequence's death, so an A+ stage drift is
  where a B-LEG mismatch usually ORIGINATES. It turns "a trade differs" into "the upstream moved".

What IS shared — the packed `cfg_*` decoding — is imported, not duplicated: both export Pines plot
`cfg_*` with one identical scheme on purpose, and `compare_strategy.config_from_export` now returns
the caller's config CLASS, so passing a `BLegConfig` gets one back with `bleg_max_days` intact.
`allow_bleg=True` is needed because the A+ decoder (correctly) REFUSES an export with `execBLeg` on,
and this fork's export always ships it on.

**The `bl_*` columns are the point.** They carry the TRACKER's own state — `bl_bits` (on/tap per
side), `bl_bars` (the armed bar per side, packed as bar+1 so 0 = none), and the four band prices per
side (top / bot / inv / tgt). Every new B-LEG rule lives in the tracker (band freeze, deepest-band
migration, target track, tap, staleness death), and a bug there shows as a wrong band price MANY bars
before it becomes a wrong trade. Without them a mismatch says "a trade differs" and nothing about why.

**Two things that are NOT in the export, deliberately:**
- `execSlLevel` — the fork has no such input (the B-LEG stop is its band ORIGIN, not a fib on the A+
  leg). `cfg_strcodes`' SL slot is pinned to the "1.0" code so the shared decoder reads
  `exec_sl_level = "1.0"` — correct-and-unused here, and one decoder keeps serving both exports.
- The Diagnostic Log block, dropped in the export copy to stay under Pine's token cap (CE10117),
  exactly as the A+ export does.

**Regenerate it whenever `mpc_b_leg_strategy.pine` changes** — the split point is exact and is
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
GMT-4 ones. `mpc_b_leg_strategy.pine` had been a genuine fork on those windows; a Python side
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

**Config decoded off the export** (all of it correct): `bleg_max_days` 1.25, A+-priority ON,
`execBLeg` ON, Structure trail, TP2 floor = TP1 price, TP1/TP2 30/40%, risk 10%.

Backtest numbers are now validated logic, not directional guesses — with the standing caveat that
**5 trades is far too thin a sample to tune against.** Parity says the code is right; it says nothing
about whether the edge is real.

## Tests

```
command-center/backend/.venv/bin/python -m pytest strategies/python/mpc_bleg/tests/ -q
```
Offline. Hand-traced `BLegTracker` (band maths, arm, tap, staleness + invalidation death,
deepest-band migration, BLEG_MAX conversion) + end-to-end driver run + longs/shorts-off.

## Do / Never

- **Do** port any change to `mpc_b_leg_strategy.pine`'s B-LEG block or execution here
  line-for-line, and any change to its A+ engine into `mpc_sos_fade` first.
- **Do** keep `BLegConfig` a superset of `SosFadeConfig` — a new A+ toggle should flow in for free.
- **Never** build a second copy of any engine or of the A+ sequence here — reuse `mpc_sos_fade`.
- **Never** trust a backtest number until a `compare_bleg.py` is green on a fresh export.

## References

- Pine source of truth: `indicators/mpc_b_leg_strategy.pine` (B-LEG block ~3683-3758,
  execution ~4429-4506).
- The A+ bot it reuses: `strategies/python/mpc_sos_fade/CLAUDE.md`.
- Upstream runner: `backtest/CLAUDE.md`; engines: `engines/*/CLAUDE.md`.
