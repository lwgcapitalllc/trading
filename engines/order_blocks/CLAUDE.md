**Purpose:** Turn the bar stream into order-block EVENTS — the base candle a turn left behind once
price displaced away from it, and the bar it is later consumed on. The signal is the event ("a bull
OB formed at 4102-4108", "price consumed it"), not the drawing.
**Scope:** OB zone geometry + the two live OB lists + their lifecycle (create / mitigate / expire /
evict) only. No trading decisions, no structure detection, no MT5 ops, no UI, no chart rendering (no
boxes, no colours, no box width, no trend-aligned hide — those are all drawing).
**Status:** Production — RE-PORTED 2026-07-31 to the turn-anchored definition and **100%
Pine-parity-VALIDATED the same day**: `compare_ob.py` exit 0 on a real 21,691-bar
`VANTAGE_XAUUSD, 15m` export (2025-09-01 → 2026-07-31) at `--warmup 798`, config read from the
export's own `cfg_ob_*` columns, and still green at warm-up 1000 / 2000 / 5000 / 10000. Engine +
types + `__init__` + 19 unit tests + a rebuilt `indicators/engines/ob_export.pine` + a rebuilt
`tools/compare_ob.py`. ⚠ **Budget ~300 bars of warm-up** — see *The 798-bar warm-up* below; it was
investigated rather than accepted, and the direction of the error matters to a consumer. The one
canonical implementation — no consumer builds its own.
**Pine:** ported from `indicators/engines/mpc_assistant.pine`; parity harness is `indicators/engines/ob_export.pine`,
diffed against this Python by `tools/compare_ob.py`. Pine stays in `indicators/` (shared source,
TradingView-only toolchain); the CSV + compare tool are the engine's half.
**Last reviewed:** 2026-08-03 — **THE FIRST CONSUMER LANDED, AND IT IS A DISPLAY ONE.**
`command-center/backend/services/ob_overlays.py` replays this engine over a backtest's candles to
draw the blocks that were live at each trade / blocked setup / missed setup on the lab's price chart.
**No engine code changed**, and the note below claiming nothing imports this engine is now false —
it has been corrected in place rather than left to be read as current. Two things worth knowing here
rather than only over there. **(1) The consumer owns the Pine's DRAWING rules, which are deliberately
not in this engine** — `OB_STUB` (the 30-bar box width), the `obNear` stretch, and delete-on-death.
That split is the same one the engine's Scope line has always stated (events, not boxes), and it
means a change to mpc's box geometry belongs in the consumer while a change to creation or
mitigation belongs here. **(2) It runs the engine at its DEFAULTS, because there is no fork to
resolve** — unlike `fair_value_gaps/`, whose two consumers legitimately see different gap sets, the
strategy files dropped order blocks entirely on 2026-07-24/25, so `mpc_assistant.pine` is the only
source and these defaults ARE its constants. ⚠ **That consumer brings NO new Pine evidence.** The FVG
one diffs its boxes against the export's own `px_fvg_*` arrays and so validates that engine a second
independent way; this one cannot, because all three exports in `exports/` predate the 2026-07-31
re-port (six slots, no `cfg_ob_*`) and `compare_ob.py` refuses them outright. Its 18 tests prove the
EMITTER only, and say so. **`compare_ob.py` on a fresh export is still the sole parity evidence for
this engine — re-run it on the next one.** Earlier: 2026-07-31 (late) — ✅ **RE-CONFIRMED ON A SECOND TIMEFRAME, AND IT SETTLES THE WARM-UP QUESTION.** `compare_ob.py --warmup 326` → exit 0 on a 13,186-bar `VANTAGE_XAUUSD, 5m` export, stable at warm-up 1000 / 5000. **326, not 798** — and the reason matters: this export is a mid-history SLICE, so Pine is WARM and Python is the cold one, exactly the configuration of the cold-start-at-2000/6000/12000 test below. Same ~300-bar figure, same direction, reached from different data and a different timeframe. Earlier the same evening — ✅ **VALIDATED. `compare_ob.py` exit 0** on a real
21,691-bar `VANTAGE_XAUUSD, 15m` export, all 55 columns, warm-up 798, stable to warm-up 10000. The
re-port below is now proven against TradingView, not just against unit tests. One Pine bug had to be
fixed to get there: `ob_export.pine` did not compile (`CE10088 — cannot modify global variable in
function`), because the export-only counters were incremented inside `extendOBs` and inside
`f_obAdd`. Pine lets a function READ a global but never WRITE one. `extendOBs` now returns its
mitigation count and the creation counters are bumped at `f_obAdd`'s call sites off its existing bool
return; the counters do not exist in mpc, so no ported logic moved. **See *The 798-bar warm-up*
below — it is not ghost blocks, and the error direction reverses for a normal cold start.** Earlier
the same day — 🔴 **FULL RE-PORT. The order block is a DIFFERENT OBJECT now, not a
tweaked one.** Found by `/audit-engines` on the 2026-07-31 mpc paste. Nothing of the old definition
survives, so this was a rewrite rather than a re-sync:

* **Structure breaks no longer create blocks at all.** `f_obMake` / `f_obCandle` and all four
  creation sites (external bull/bear, internal bull/bear) are commented out in the Pine. **This
  engine is therefore STANDALONE** — it consumes no other engine, `StructureSnapshot` is deleted,
  and `update()` takes plain OHLC. A test guards the signature so the snapshot cannot drift back in.
  It is now a sibling of `fair_value_gaps/` and `equal_highs_lows/` in shape.
* **Every block belongs to a TURN** (`ta.pivotlow/pivothigh`, len 2), read two ways, at most ONE
  block per turn. **PUSH** = the engulf reading (an impulsive candle that closed through the nearest
  opposing candle's open with a bigger body than the one it consumed, which must itself clear the
  ATR noise floor — a doji is not a level); it must sit at or within `turn_scan` bars *after* a
  matching-direction pivot. **TURN** = the no-engulf reading (walk forward from the pivot to the
  first candle that CLOSES clear of every BODY in the base so far, anchor on the bar before it).
  Both are read `wait` (10) bars late. The push runs first and latches the pivot; the turn refuses
  a latched pivot. **Source order is load-bearing** — first drawn wins the overlap dedupe.
* **Six creation gates** (`f_obAdd`): min-back, dead, displacement (≥ 1.0 x ATR of travel measured
  on CLOSES), tap-after-departure, overlap dedupe (0.5 of the CANDIDATE's own height), height
  ceiling (2.0 x ATR).
* **Mitigation redefined three ways over:** a wick in that closes back out kills it (tap); a close
  INSIDE keeps it alive until a later close outside either side (enter-then-leave); a close clean
  past the far edge kills it outright. Plus an age cap (500 bars), reported as `expired` — a
  separate event from `mitigated`, because a block price never returned to was not consumed.
* **`max_active` 2 → 10**, and eviction no longer protects structure-born blocks (there are none).

**Nothing downstream broke:** at the time of the re-port no consumer imported this engine — not
`backtest/replay/EngineStack`, not either bot — so it carried no strategy risk. **⚠ That is no longer
true as of 2026-08-03 and the sentence is kept for the re-port's context only: `command-center`'s
price chart now consumes it** (`backend/services/ob_overlays.py` → the chart's *Analysis → Order
Blocks* layer, one box per block that was live at a trade / blocked / missed setup). It reads the
public events ONLY, and it is a DISPLAY consumer — no strategy reads a block, so a change here still
moves no trade — but a change here now moves what a reader sees on a backtest, and the box geometry
that consumer mirrors is the Pine's drawing rule (`OB_STUB`, the `obNear` stretch, delete-on-death),
which is NOT in this engine. Keep those in step: `command-center/backend/CLAUDE.md` → *Order blocks*.
And unlike the Cycle fib, there is **no
two-Pine fork to worry about**: the strategy files dropped order blocks entirely on 2026-07-24/25, so
`mpc_assistant.pine` is the only source. **`indicators/engines/ob_export.pine` was rebuilt too** — it used to
EMBED the whole structure engine (1148 lines → ~300), which was its single biggest maintenance trap
(it silently went stale twice); it now needs no structure re-sync ever again, and carries `cfg_ob_*`
columns so `compare_ob.py` configures the Python engine FROM the export. Earlier: 2026-07-14 —
`max_active` default synced 6→2; 2026-07-12 — re-validated after the `choch_lock` structure re-sync.

---

## Key paths

```
engines/order_blocks/
├── engine.py       ← the OB state machine (OrderBlockEngine): mitigate → push source → turn source
├── types.py        ← OrderBlock (a zone); OrderBlockEvents (output)
├── __init__.py     ← re-exports the public API
├── CLAUDE.md       ← this file
├── tests/
│   └── test_engine.py       ← 19 hand-traced tests
└── tools/
    └── compare_ob.py   ← Pine↔Python parity harness (reads a TradingView CSV export)
```

Pine source of truth: `mpc_assistant.pine` — the type + `manageOBs`/`extendOBs` (191-393), the shared
turn pivot + PUSH source (2626-2715), `f_obAdd` (2269-2550), the TURN source (2717-2881).
Parity export build: `indicators/engines/ob_export.pine`.

---

## What an order block is (ported semantics)

**A block is the base a turn left behind, drawn only once price has DISPLACED away from it.** It is
made by looking BACK: the turn nominates a candidate, and the move away is what confirms it. No zone
is ever drawn around price where it currently stands.

A **bullish OB** sits below price (demand to buy from); a **bearish OB** sits above (supply to sell
from). The zone spans the anchor candle's full high/low, or its body extremes when `body_only=True`.

**Two sources, one turn, at most one block.** A turn is a short pivot (`ta.pivotlow`/`pivothigh`,
`turn_len=2`). Both sources read that same turn, `wait=10` bars late:

| source | what it looks for | anchor |
|---|---|---|
| **PUSH** (the engulf reading) | an impulsive candle that closed through the nearest opposing candle's OPEN, with a **bigger body than the one it consumed**; the consumed candle must itself clear `push_mult × ATR` (a doji is not a level); and the anchor must sit at or within `turn_scan` bars *after* a matching-direction pivot | the candle it consumed |
| **TURN** (the no-engulf reading) | any pivot. Walks forward from it to the first candle that **CLOSES clear of every BODY in the base so far** | the bar immediately before that one |

The push runs FIRST and latches the pivot it used; the turn source refuses a latched pivot. That
order is load-bearing — first drawn wins the overlap dedupe. If the wrong reading ever wins
consistently, swapping the two call sites is the entire fix (the Pine says so too).

**Six gates, all in `_add` (Pine `f_obAdd`). A candidate must clear every one:**

| gate | rule | why |
|---|---|---|
| min-back | anchor ≥ `min_back` (3) bars behind the live bar | a level belongs in history, not beside the forming candle |
| dead | no bar since has CLOSED clean past the far edge | else `_extend` would delete it next bar — refuse rather than flicker |
| **displacement** | furthest CLOSE beyond the departed edge ≥ `disp_mult` (1.0) × ATR(14) | leaving is not enough. In chop price closes just past a candle constantly; without this every nothing-turn became a level |
| tap-after-departure | once displaced, no bar may reach into the zone and close outside it | that is a real tap-and-reject; refuse at birth rather than draw and delete |
| dedupe | overlap with a live block ≥ `dupe_overlap` (0.5) **of the CANDIDATE's own height** | the two sources land on ADJACENT candles at one turn, so an equality test never matched and both boxes printed |
| height | zone ≤ `max_atr` (2.0) × ATR(14) | a box the size of the impulse is a redrawing of the move, not its base — and oversized zones become immortal |

Measuring in ATR everywhere is deliberate: it travels across instruments and timeframes with no
per-chart retuning. Measuring displacement on CLOSES means a single spike out and back cannot buy a
level.

**Four ways a block leaves, and only one is a signal:**

- **mitigated** — the real signal, and it is now three rules in one. A **close clean past the far
  edge** kills it outright (without this, price that runs cleanly THROUGH in one bar leaves an
  immortal block). Otherwise, when the bar is not closing inside, it dies if the bar **touched** the
  zone (a wick in that closed back out) OR it had previously **entered** (closed inside earlier, now
  closing outside — either side). So a zone survives exactly one thing: price still being in it at
  the close. ⚠ **The wick half is a tap rule, and a tap rule kills the blocks that HELD** — a level
  that rejects price cleanly is wicked and closed out of. That is the trade Aaron chose (2026-07-31)
  for a chart with no worked-through zones left on it.
- **expired** — age only (`max_age`, 500 bars). Under enter-then-leave a block price never returns
  to can never be mitigated (both halves need price at the zone), so age is the only thing retiring
  those. **Not** a signal.
- **evicted** — FIFO past `max_active` (10). Plain oldest-out; it no longer protects structure-born
  blocks, because there are none. **Not** a signal.
- **created** — a new zone exists.

**A block is born CLEAN (`entered=False`).** The look-back replay computes `dead` and the
displacement, but deliberately does NOT carry `entered` forward. It used to, and it killed correct
blocks on arrival: the base candles nearly always contain a close inside the zone, and since the
displacement gate already requires price to be OUTSIDE, `_extend` fired on the very next bar. **A
block cannot be mitigated by the move that created it — the level did not exist yet.**

---

## Per-bar order (ported exactly — do not reorder)

1. **History + ATR**, so `[0]` is the current bar.
2. **Mitigate/expire both lists** (Pine `extendOBs`, mpc 2158) — BEFORE any creation. This is what
   guarantees a block is never mitigation-checked on the bar it is born.
3. **Pivots** — detect this bar's, and remember the latest confirmed pivot bar per side.
4. **PUSH source** (mpc 2710-2715).
5. **TURN source** (mpc 2878-2881).

Steps 4 and 5 in that order decide which reading claims a turn, and the dedupe in step 4/5 sees the
post-mitigation lists from step 2. Keep it identical to Pine.

---

## Timeframes & what it needs

No timeframe branching, and **no upstream engine** — this engine is standalone and OHLC-driven. It
needs:

1. **The right candles.** Same price feed you chart on (see "Live parity" in
   `engines/fibonacci/CLAUDE.md` — the same rule applies here once a bot consumes this engine).
2. **Closed bars, in order, one at a time.** The two lists, the rolling OHLC/ATR/pivot history and
   the push latch all carry bar-to-bar; feed one closed bar per `update()`, never out of order.
3. **Warm-up.** Short in absolute terms — ATR(14) is None for 13 bars, the pivot needs 5, and the
   turn source needs `turn_len + turn_wait` (12) bars, so the earliest block lands around bar 14.
   Against a Pine export the practical warm-up is much longer (see Validation).

It needs **no timestamp and no volume**.

---

## Public API

```python
from order_blocks import OrderBlockEngine

ob = OrderBlockEngine()  # max_active=10, body_only=False, … — the Pine defaults

# Each closed bar, in order:
ev = ob.update(bar.index, bar.open, bar.high, bar.low, bar.close)

for o in ev.created:  # zones created THIS bar (event)
    o.top, o.bottom, o.is_bullish
    o.origin_index  # bar index of the anchor candle itself
    o.created_index  # bar index it was added on (~10 bars later — the sources read late)
    o.id  # stable id: match a created OB to its later mitigation
    o.entered  # has a candle closed inside it yet (mitigation state)
    o.from_break  # always False today — the structure sources are commented out in the Pine
for o in ev.mitigated:  # zones CONSUMED this bar — the signal
    ...
for o in ev.expired:  # zones that simply aged out — NOT a signal
    ...
for o in ev.evicted:  # zones dropped past the cap — NOT a signal
    ...
ev.active_bull  # live bull OBs, oldest-first (state) — mirrors Pine activeBullOBs
ev.active_bear  # live bear OBs, oldest-first (state) — mirrors Pine activeBearOBs
```

Every Pine constant is a constructor arg (`max_active`, `body_only`, `max_age`, `min_back`,
`max_atr`, `dupe_overlap`, `disp_mult`, `turn_len`, `turn_scan`, `turn_wait`, `push_look`,
`push_wait`, `push_mult`, `atr_len`) so a consumer can match a tweaked Pine.

---

## Relationship to the other engines

**None — this engine is STANDALONE.** It used to be a sibling of `engines/fibonacci/` downstream of
`engines/market_structure/`, because every block was born on a BOS/SOS/iBOS/iSOS. The 2026-07-31 mpc
rework commented out all four of those creation sites, so `StructureSnapshot` is gone and `update()`
takes plain OHLC. In shape it is now a sibling of `fair_value_gaps/`, `rsi_divergence/` and
`equal_highs_lows/`: price-pattern detection with no upstream engine, no volume and no timestamp.

A test (`test_update_takes_no_structure_snapshot`) guards the signature, so the dependency cannot
drift back in unnoticed. **If the Pine's structure source is ever restored**, restore
`StructureSnapshot` with it — read the structure engine's documented public output, never its
internals.

---

## Do

- Port any change to `mpc_assistant.pine`'s OB blocks back here line-by-line. Keep the per-bar order
  (mitigate → push → turn), the six gates, the enter-then-leave/tap/through mitigation, the Pine
  pivot tie rule and the FIFO cap exact — do not "clean up" or reorder them.
- Mirror any new mpc OB input as a constructor arg AND a `cfg_ob_*` column in `ob_export.pine` that
  `compare_ob.py` reads, in the same commit.
- When adding a new event or field, update this file's Public API and the tests in the same commit.

## Never do

- Do not bake in colours, boxes, the `OB_STUB` box width, or the trend-aligned hide — those are all
  TradingView drawing concerns. This layer emits events.
- Do not carry `entered` forward from the birth replay. It reads like a fix and it kills correct
  blocks on arrival — see "A block is born CLEAN" above.
- Do not re-add a structure dependency because it "feels" like an order block should need one. The
  Pine decides that, and today it does not.
- Do not build a second OB implementation elsewhere. This is the canonical one.
- Do not let this engine or the OB blocks in `mpc_assistant.pine` drift; re-run the parity check
  after any change to either.

---

## Validation (Pine ↔ Python parity)

**Unit tests — GREEN:** `python3 -m pytest engines/order_blocks/tests/ -q` (19 hand-traced tests
pinning the Wilder-ATR seed, the Pine pivot tie rule on both sides, creation off a real displaced
turn, the no-displacement and min-back and dead and height-ceiling refusals, all four mitigation
paths plus the bear mirror, age expiry reported separately from mitigation, FIFO eviction through
the real add path, the overlap dedupe both ways, the one-block-per-turn latch, and the standalone
`update()` signature). Several are A/B against one feed — the same bar that creates a block on a
clean engine must create nothing once the latch or a duplicate zone is in place — so they cannot
pass vacuously.

**✅ FULL Pine↔Python parity — GREEN (2026-07-31).** `compare_ob.py` exit 0 on a real
`VANTAGE_XAUUSD, 15m` export, **21,691 bars, 2025-09-01 → 2026-07-31**, at `--warmup 798`, with **no
config flags** (the tool read `body_only=False, disp_mult=1.0, dupe_overlap=0.5, max_active=10,
max_age=500, max_atr=2.0, push_mult=0.3, push_wait=10, turn_wait=10` out of the export's own
`cfg_ob_*` columns). All 55 columns matched — both count columns, both created and both mitigated
pulses, and all 40 slot columns (10 slots × top/bottom × 2 directions), so creation, mitigation,
age-expiry and FIFO eviction are all proven at once. Still green at warm-up 1000 / 2000 / 5000 /
10000, so 798 is not a threshold sitting just past a real mismatch.

The export was a **grand export**: `sessions_export`, `liquidity_export`, `ob_export` and
`fvg_export` on ONE 15m chart, 146 columns, no column-name collisions between the four. All four
comparators ran off that single file.

**One Pine bug had to be fixed first.** `ob_export.pine` would not compile — `CE10088: cannot modify
global variable "obBullMit" in function`. Pine lets a function or method READ a global but never
assign to one, and the export-only counters were being incremented inside `extendOBs` AND inside
`f_obAdd`. Fix: `extendOBs` returns its mitigation count (its `isBull` parameter became pointless and
is gone), and the creation counters are bumped at `f_obAdd`'s four call sites off the bool it already
returned. Those counters do not exist in `mpc_assistant.pine` at all — they are pure instrumentation
— so no ported logic moved.

### The 798-bar warm-up — investigated, not assumed

798 is long, so it was chased rather than waved through. **It is NOT the usual pre-window-ghost
warm-up**, and the finding changes what a consumer should expect:

- The export starts at Pine's **bar_index 0** — Pine holds zero blocks at row 0 and creates its first
  only at bar 122 — so there are no off-screen anchors carried in. The standard explanation is out.
- Over bars 0–324 Python creates a strict **superset**: 20 blocks Pine never made, and **zero** that
  Pine made and Python missed.
- Not the displacement gate going marginal — those 20 clear it at **travel/ATR 1.06 … 6.71**, none
  near ×1.0. Not the ATR seed, not `obHuge`.
- **The decisive test: cold-start the Python engine at bar 2000, 6000 and 12000 instead.** Every one
  produces the OPPOSITE signature — Python *misses* 1–3 blocks inside its first ~300 bars (Pine is
  warm there, Python is not), then matches exactly. The over-firing happens ONLY at bar 0, i.e. only
  where **Pine itself is also cold**.

So Pine suppresses creation over the oldest bars of a chart in a way this port does not. The
mechanism could not be identified from this export because it plots no intermediate values
(`obTurnHi`/`obTurnLo`, `obTravel`, the pivot series), and it never recurs across the following
20,893 bars.

**What this means for a consumer: budget ~300 bars of warm-up, and expect a cold engine to be
MISSING a block or two in that window rather than inventing one.** That is the safe direction — a
missing zone declines a trade, an invented one takes a bad one. If it ever needs settling, add
`px_ob_pv_hi` / `px_ob_pv_lo` / `px_ob_travel` diagnostic columns to the harness and re-export; that
is the cheap follow-up.

**Standing warning that still applies to a NARROWER export.** Pine's arrays can open holding blocks
whose anchor candles are off-screen, and under enter-then-leave those clear only as they mitigate or
FIFO out. **If warm-up never clears, re-export a WIDER window rather than raising `--warmup`** — a
block price never returns to cannot mitigate, so a pre-window ghost can sit in Pine's array for ever.
That is the 2026-07-19 EQ/FVG lesson, and it applies to this engine more than any other now that age
is the only backstop. It did not bite on the 21,691-bar run above.

## References

- Pine source of truth: `indicators/engines/mpc_assistant.pine` OB blocks (191-393 / 2269-2550 / 2626-2881).
- Parity export build: `indicators/engines/ob_export.pine`.
- **Consumers** (public events only — never this engine's internals):
  - `command-center/backend/services/ob_overlays.py` — draws the blocks that were live at each trade
    entry / blocked setup / missed setup on the lab's price chart (Analysis → Order Blocks). A
    DISPLAY consumer: no strategy reads a block, so a change here cannot move a trade. It owns the
    Pine's DRAWING rules, which are deliberately not in this engine — the `OB_STUB` box width, the
    `obNear` stretch, and delete-on-death. See `command-center/backend/CLAUDE.md` → *Order blocks*.
- Siblings in shape (standalone, price-pattern, events-not-visuals): `engines/fair_value_gaps/CLAUDE.md`,
  `engines/equal_highs_lows/CLAUDE.md`, `engines/rsi_divergence/CLAUDE.md`.
- The audit that found this: `docs/ENGINE_EXTRACTION_ROADMAP.md` → "Audit findings — 2026-07-31".
- Monorepo context: `../CLAUDE.md`.
