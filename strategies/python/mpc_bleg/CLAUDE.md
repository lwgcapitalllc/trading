# CLAUDE.md — strategies/python/mpc_bleg/ (the MPC B-LEG bot)

**Purpose:** The B-LEG setup as a standalone Python strategy — a port of
`indicators/mpc_b_leg_strategy.pine` (Aaron's brother's B-LEG fork of MPC-JARVIS). The
B LEG is the SOS whose retrace arrived LATE: an A+ reversal dies at 2/3 on a continuation
BOS before it retraces, the Sniper-Zone band (0.382–0.5) of that break is frozen, and a
resting limit at the 0.5 edge waits for the late return.
**Scope:** This bot only — its tracker, order layer, config, tests. It does NOT own the
engines (`engines/`), the replay runner (`backtest/`), or the A+ machinery it reuses
(`strategies/python/mpc_sos_fade/`).
**Status:** Built + unit-tested (21 tests green) + **Pine-parity GREEN (exit 0) 2026-07-26** on a
real 21,231-bar `VANTAGE_XAUUSD, 15m` export — bar-for-bar identical decision stream, including
~90 distinct frozen bands and 5 graded trades. The harness is `tools/compare_bleg.py` +
`indicators/mpc_b_leg_strategy_export.pine`, registered in `verify_parity.py`. **Sample size is the
open question, not correctness:** 5 trades is far too thin to tune against. See "The parity gate".
**Last reviewed:** 2026-07-27 — `bleg_sl_level` made the hardcoded stop configurable in both Pine forks + Python, the first 4.5y performance measurement landed, and a 15-cell sweep adopted exactly one change (`bleg_max_days` 1.25 → 2.5). See "The exit ladder is inherited" and "Measured performance".

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
  - `config.py` `BLegConfig(SosFadeConfig)` — a strict superset, adds `bleg_max_days` + `bleg_sl_level`.
    Both were swept 2026-07-27; only `bleg_max_days` moved. See "Measured performance".
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
- **This bot OVERRIDES TP1 / TP2 / SL** with its band prices (SL = `bleg_sl_level` off the band,
  TP1 = the broken swing extreme, TP2 = the expansion extreme). Everything from the stop staging
  down — the floor, the trail, both dropdowns — is the parent's, unchanged.
- **`bleg_sl_level` (added 2026-07-27)** — the stop was HARDCODED to the band origin until then.
  Own field, not the inherited `exec_sl_level`, because the two index different geometry: the A+
  one picks a level off the fib engine (`sig.fibo_p3..p10`), the B leg has no fib engine and must
  derive its stop from the band's own origin + range. Options **`0.382` / `0.236` / `0.0`**,
  defaulting to `"0.0"` = the old hardcoded origin, which is byte-identical on a full 4.5y replay,
  so the parity gate is unaffected.

  ⚠ **THIS ZONE'S FIB IS DRAWN THE OPPOSITE WAY ROUND — read before adding a level.** `bleg.py`
  builds the band as `origin + f·range`, so the zone's fib has **0 at the leg origin and 1.0 at
  the expansion extreme** — the mirror of a standard retracement, which puts 0 at the extreme.
  The setup's author (Aaron's brother) draws and reasons about it in this frame, and the field
  uses HIS frame:

  | Zone level | Where it sits | Stop distance |
  |---|---|---|
  | 0.5 | the resting entry limit (`l_top`/`s_bot`) | — |
  | 0.382 | the band's far edge (`l_bot`/`s_top`) | 0.118·range |
  | 0.236 | below the band | 0.264·range |
  | 0.0 | the leg origin (`l_inv`/`s_inv`) — **DEFAULT** | 0.500·range |

  The levels ABOVE 0.5 — 0.618 / 0.786 / 0.886 — sit on the WRONG SIDE of the entry here (above
  it on a long) and are deliberately not offered. **A first version of this field got that wrong**:
  it mirrored the standard ladder into the zone, pricing stops at 0.298 / 0.214 / 0.114 — valid
  points arithmetically, but not fib levels in this frame, and labelled with numbers that name
  levels on the opposite side of the entry. Corrected same-day on the author's own reading. Six
  tests in `tests/test_bleg.py` pin the frame, including one asserting every offered level sits
  below the entry in both directions. To sit BEYOND the origin, use `exec_sl_buf_tk` (ticks).

  **The stop is COUPLED to TP1 — a tighter stop does not cut losers sooner.** Entry rests at 0.5
  and TP1 is `2·edge − origin`, so `stop = (0.5 − f)·range` while `TP1 = 0.5·range` ALWAYS. TP1
  measured in R is therefore `0.5 / (0.5 − f)`: **1.00R** at 0.0, 1.89R at 0.236, **4.24R** at
  0.382. Since a TP1 touch is the ONLY thing that stages the stop to breakeven, tightening the
  stop pushes safety further away in R rather than closer — verified empirically on the 4.5y
  baseline, where the single loss that reached 1.0R MFE lost only −0.74R while **every** loss
  short of 1.0R lost the full −1.00R. At 0.382 the stop also sits ON the band's far edge, so any
  wick through the zone kills the trade, and the median stop falls to ~$2.59 on gold with 11 of
  36 trades under $2 — the degenerate-stop artifact documented in `mpc_sos_fade_optimization.md`
  Runs 4–5. **Do not adopt 0.382 without a minimum-stop-distance guard.**

`indicators/mpc_b_leg_strategy.pine` was ported in the same pass and now matches: `execRunnerTrail`,
`execStructTrailBufTk`, `execTp2StopMode`, `execAplus`, and the `lStage2Floor` / structure-trail
exit block copied line-for-line from `mpc_strategy.pine`. `bLegSlLevel` + `f_bLegSl` were added to
BOTH Pine forks on 2026-07-27, and the export fork plots `cfg_bleg_sl` so `compare_bleg.py` can
reproduce whatever level an export was taken under (a missing column means a pre-input export, which
ran the hardcoded origin — exactly what the `"0.0"` default reproduces, so it is silent, not a
warning). This supersedes the earlier note that `execSlLevel` was deliberately not ported: the
*inherited* one still is not (it indexes fib-engine levels this fork has none of), but the B leg now
has its OWN equivalent. **Not ported, deliberately:**
the pink blocked-trade markers, whose codes describe why an **A+** setup was refused — in this fork
A+ never trades, so those tags would report the opposite of what a reader would assume. A B-LEG
block tag would need its own code set, which is new design work, not a port.

## Measured performance + the 2026-07-27 sweep (the ONLY adopted change)

**First real performance read.** Pine parity proved the two implementations AGREE; it never showed
the setup makes money, and the 21,231-bar parity export is only ~11 months. `run_report.py` replays
the Python bot over the M15 broker cache instead (back to 2015), so the numbers below are 4.5y —
2022-01-02 → 2026-07-24, 107,803 bars, `fill_model="bar"` (zero costs; a tick run will be worse).

**Headline: at the shipped config B-LEG made 6.5R on 35 trades in 4.5 years.** ~8 trades a year. The
A+ bot does 118 trades / 33.6R over the identical window. Treat B-LEG as a side dish.

### What was swept (15 cells: 3 stop levels × 5 staleness windows)

| Stop | Timer | n | sumR | minus top 2 | maxDD | wr | median stop | stops < $2 |
|---|---|---|---|---|---|---|---|---|
| **0.0** | **2.5d** | **55** | **10.2** | **+4.0** | **−5.8** | **47%** | **$11.36** | **0** |
| 0.0 | 3.0d | 58 | 8.9 | +2.6 | −5.4 | 47% | $11.89 | 0 |
| 0.0 | 1.25d | 35 | 6.5 | +2.6 | −6.7 | 51% | $11.36 | 0 |
| 0.0 | 1.75d | 44 | 1.5 | −2.5 | −8.7 | 43% | $10.62 | 0 |
| 0.236 | 2.5d | 58 | 7.2 | −0.5 | −17.5 | 33% | $5.81 | 3 |
| 0.382 | 3.0d | 62 | **18.0** | **−0.3** | −13.6 | 26% | $2.80 | 17 |
| 0.382 | 2.5d | 58 | 17.9 | +0.8 | −20.3 | 26% | $2.60 | 18 |

**ADOPTED: `bleg_max_days` 1.25 → 2.5.** The only cell better than the shipped one on every axis —
more trades, more R, SMALLER drawdown, 4 positive years instead of 3, no degenerate stops.

**REJECTED: every tighter stop.** Two different failure modes, both worth knowing:
- **0.382 is a mirage.** Biggest headline in the grid (18.0R) and the worst row in it: strip its two
  best trades and it is **−0.3R**, win rate 26%, worst losing streak **11**, median stop $2.80 with
  17 of 62 trades under $2 — inside the spread on gold, so R is a division artifact. Same failure the
  A+ bot hit; see `mpc_sos_fade_optimization.md` Runs 4–5.
- **0.236 fails honestly, which is more instructive.** No fake stops, just more real losses — 37 of
  58 vs 25 at the origin stop, drawdown roughly tripled to −17.5R. Its losers reach a **median 1.03R
  MFE** before dying: they get a full R into profit and hand it all back, because at 0.236 TP1 sits
  at 1.89R and the stop never stages to breakeven. This is the TP1 coupling (see `bleg_sl_level`)
  showing up as money, not theory.

### Two caveats that must travel with these numbers

1. **The timer surface is NOT monotonic.** 1.25 → 6.5R, 1.75 → **1.5R**, 2.5 → 10.2R. A genuine
   improvement would rise smoothly. Part of the 2.5 result is which trades landed where. It is
   "probably better than 1.25", not an optimum — do not sweep it finer on this sample.
2. **Strip the top 5 trades and EVERY cell goes negative** (best case 0.0/2.5 at −1.6R). B-LEG's
   entire 4.5y result rests on a handful of winners. It does not have a broad edge yet, and no
   stop or timer setting creates one.

### What was measured INERT (do not re-test without a reason)

- **`exec_req_fvg`** — the B-LEG entry never consults an FVG (`_place_entries` rests at the band's
  0.5 edge). Turning it off moved the trade count 35 → 34, and only indirectly, by letting A+ arm
  more often and stand the B leg down. Not a B-LEG lever.
- **`exec_aplus` (the priority gate)** — off = 36 trades / 5.5R vs 35 / 6.5R. Byte-identical to
  "both off", which proves FVG's only route into this bot was through that gate. The file's
  long-standing "first tuning candidate" is worth one trade over 4.5 years.

⚠ **The setups table in a B-LEG `run_report.py` run is about A+ LEGS, not B legs.** `_collect_legs`
reads `d.l_stage`/`d.s_stage` (the A+ sequence stages) while `BLegExecution` overwrites the edge/arm
fields with the B-LEG's own — so its "no FVG in the zone" rows describe legs this bot never trades.
Do not read a B-LEG constraint off it; that misreading is what produced the wrong first answer here.

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

Offline guard: `tests/test_compare_bleg.py` (5 tests) round-trips the tool — run the bot, serialise
its own decisions + tracker state into an export-shaped CSV using the Pine's packing, feed it back,
require exit 0 — then plants a `bl_l_top` mismatch and a `px_dec_bits` mismatch and requires the tool
to catch each at the right bar. The encoder there is written from the Pine's plot expressions rather
than from the tool's decoder, so it also catches the two drifting apart. It uses 30 synthetic days,
not 10: on 10 no leg ever ARMS, so the `bl_*` diff would prove nothing.

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
