# CLAUDE.md — Fibonacci Engine Subsystem

**Purpose:** Turn market-structure output into fib LEVEL EVENTS — the first-touch of each fib
level (E1–E4 entries, TP1–TP3 targets, 1.0) — for use in entries, take-profits, and grading. The
signal is the event ("price reached E1 / 0.618"), not the drawing.
**Scope:** Fib geometry + per-fib touch state machines only. No trading decisions, no structure
detection (it consumes `engines/market_structure/`), no MT5 ops, no UI, no chart rendering.
**Status:** FOUR fibs ported (Structure "FFT", Sniper, Macro, Internal), unit-tested (42 tests, green).
**2026-07-10 addition — `half_reached` (NOT yet parity-re-validated):** the Structure fib now emits
`half_reached` — the INBOUND 0.5 (TP1-price) tap during the retrace, UNGATED (not behind 0.618) and
tested on the retracement side, so it is distinct from the TP1 target (same price, outbound, gated). It
is a first-touch latch reset each new leg, and it feeds only the new A+ setup's EARLY entry tier. Ported
from `mpc_assistant.pine` (the new `fiboHalfReached` var); `fib_export.pine` gained a `px_fibo_half_reached`
column and `compare_fib.py` compares it (optional, so older exports still validate). Unit-tested (2 new
tests, green) and **parity CONFIRMED (exit 0):** on a fresh combined `VANTAGE_XAUUSD, 5m` export
(7,891 bars, `--warmup 1002`) `px_fibo_half_reached` matched Pine on every warm bar, alongside all the
existing Structure/Sniper/Macro/Internal fields (the 1002-bar warm-up is the Macro cycle cold-start).
A **2026-07-09 `mpc_assistant.pine` re-paste** changed three things: the Structure AND Internal fibs
**dropped the TP3-hit `reset_active` latch** and **added an extend-changed guard** (skip touched-checks
on any bar the live anchor moved), and the **Macro** now seeds its bear-SOS low-tracker on the first bar
so the first bullish SOS can lock a cycle immediately. All three are ported and **re-validated at 100%
Pine parity** on a fresh `VANTAGE_XAUUSD, 5m` export (13,759 bars, `--warmup 3154`, exit 0 —
Structure + Sniper + Macro + Internal). The one canonical implementation — no consumer builds its own.
**Pine:** ported from `indicators/engines/mpc_assistant.pine`; parity harness is `indicators/engines/fib_export.pine`, diffed against this Python by `tools/compare_fib.py`. Pine stays in `indicators/` (shared source, TradingView-only toolchain); the CSV + compare tool are the engine's half.
**Last reviewed:** 2026-08-02 — **the Structure fib now reports the BARS its anchors sit on** (`StructureFibEvents.ash_loc` / `.asl_loc`), beside the `ash`/`asl` prices it has carried since the Custom-SL work. Same standing as those prices, word for word: existing internal state (`_ash_loc`/`_asl_loc`, which `origin_index()` already reads) surfaced unchanged, read by nothing in the level maths, so detection cannot move. A consumer needs them because **a fib is a LEG, not just a ladder of prices**: two prices say what the levels are, never where the leg is, and the first consumer — the lab price chart drawing each trade's own fib — has to start the drawing at the bar the leg BEGAN on or it hides the retracement that produced the entry. ⚠ **`compare_fib.py` could not run: no `fib_export.pine` CSV is on disk.** Rather than argue the change is inert, it was MEASURED the way the repo measures a cosmetic change — the engine was replayed at HEAD and at the working tree over **47,263 real cached M15 bars** (2023-01-02 → 2025-01-01) and every field the parity tool compares was diffed bar by bar: **0 differences** across 47,214 active bars, 377,712 level values and 1,824 touch events, with the two new fields populated on every active bar. That is the same evidence by a different route, not a substitute for the gate — re-run `compare_fib.py` on the next real export anyway. 3 new tests (45 green). Earlier: 2026-07-31 — ⚠ **THE MACRO (CYCLE) FIB IS NOW A FORK: the two Pine files disagree, and this engine deliberately follows the STRATEGY one.** `/audit-engines` found `mpc_assistant.pine` reworked its Cycle fib on 2026-07-31 in two independent ways, each of which moves every price on the ladder:

1. **The bottom anchor moved.** It was `macro_ll_since_bear_sos` — the lowest low tracked since the last bearish SOS, which can reach a long way back and sit far below the break. It is now **`st.bull_bos_low`**, the low of the leg that actually broke structure: nearer, higher, tighter.
2. **It is measured on a different timeframe.** New `macroCycleTf = 1` + `f_cycleState()`: on any chart ABOVE 1m the whole cycle state comes from a **1-minute `request.security`** (`cyc_origin`/`cyc_extreme`/`cyc_visible`); only at or below 1m does it run natively. The Pine's own comment calls this "the smaller cycle".

Everything else is unchanged in both — lock on a bull SOS, extend the top on a higher confirmed high, die on a close below the origin, hide on a close above the extreme. (The touch-latch reset also moved from `macroNewHH` to `macroRangeChanged`, a minor equivalent.)

**`MacroFib` was deliberately NOT changed (Aaron's call, 2026-07-31).** `strategies/tradingview/mpc_strategy.pine` — the file `strategies/python/mpc_sos_fade/` actually replays — **still carries the OLD anchor** (`macro_ll_since_bear_sos`, lines 2614-2672). So this engine is stale against the *assistant* and CORRECT against the *strategy*; porting the rework would have manufactured drift in the bot rather than removing it. Same class as the `fvg_require_close` trap in `engines/fair_value_gaps/CLAUDE.md` — **the two mpc Pine files disagree, so no single behaviour is right for both.** Stakes are low today: `mpc_sos_fade` computes the macro POI (`signals.py`, discount 0.618-0.886 long / premium 0.382+ short) and reports it through the sequence state, but **execution never reads it**, so no trade depends on it either way.

**Port it when — and only when — the rework reaches `mpc_strategy.pine`.** At that point the 1-minute `request.security` becomes the real problem: this engine consumes ONE bar stream and has no lower-timeframe feed, so reproducing it needs an architectural decision (feed `EngineStack` a second M1 stream, or pin the cycle to the chart timeframe and accept the gap) — not a line edit. The other three fibs (Structure/FFT, Sniper, Internal) are **unaffected** and stay in parity. Earlier: 2026-07-12 — **re-validated after the `choch_lock` structure re-sync.** The four fibs were STALE-BY-INPUT, not stale: their own code was untouched, but the structure stream feeding them changed (more SOS fire, fewer swings confirm — and the MacroFib reads `bull_sos` + `last_conf_high` directly), and `fib_export.pine` embeds the structure block so it was re-synced first. `compare_fib.py --warmup 368` then passed exit 0 on a fresh `VANTAGE_XAUUSD, 5m` export (9,270 bars) across all four fibs — the same single CSV that validated market_structure and order_blocks, since `fib_export.pine` + `ob_export.pine` can sit on one chart (no `px_*` column collisions). Details in `engines/market_structure/CLAUDE.md`.

---

## Key paths

```
engines/fibonacci/
├── geometry.py     ← the one shared fib-math core (fib_level / fib_from_origin / fib_levels / origin_index)
├── engine.py       ← the per-fib state machines (StructureFib + SniperFib + MacroFib)
├── types.py        ← StructureSnapshot (input); FibTouch / StructureFibEvents / SniperFibEvents / MacroFibEvents (output)
├── __init__.py     ← re-exports the public API
├── CLAUDE.md       ← this file
└── tests/
    ├── test_structure_fib.py
    ├── test_sniper_fib.py
    └── test_macro_fib.py
```

---

## The four fibs (all identical geometry; they differ only in anchors + ratios + reset rule)

| Fib | Pine group | Anchors | Ratios drawn | Reset / lifecycle |
|---|---|---|---|---|
| **Structure** ("FFT") | `GRP_FIBO` | active swing high/low, **following the live pullback extreme**, and adopting a more-extreme **confirmed internal swing** (`i_confirmed_low/high`) as the pull anchor | E1–E4 (0.618/0.702/0.786/0.886), TP1–TP3 (0.5/0.382/0.0), 1.0 | new leg when the origin bar changes → all touches reset (the only spend trigger; the TP3-hit `reset_active` latch was dropped 2026-07-09); touched-checks skipped on any bar the live anchor moved |
| **Sniper** (`next`) | `GRP_SNIPER` | the **BOS impulse leg** (`bull/bear_bos_high/low` + locs) | 0.382–0.5 zone box | fires on a BOS, frozen (does not extend), replaced on the next BOS |
| **Macro** | `GRP_MACRO` | HH→LL cycle (`last_conf_high` + the running low since bear SOS, bear-SOS→bull-SOS lock) | 0.0/0.382/0.5/0.618/0.702/0.786/0.886/1.0 | own lock/reset/extend cycle; **hide-only** above the top (extend→touch→hide order); ≤5m timeframe only |
| **Internal** | `GRP_IFIB` | the **internal leg** that just broke (an iBOS/iSOS, delivered as the snapshot's `ifib_seed_*`); the moving anchor extends live | E1–E4, TP1–TP3, 1.0 (same 8 as Structure) | seeded on each iBOS/iSOS; **ANY external BOS/SOS clears it** (the TP3-hit `reset_active` latch was dropped 2026-07-09) — waits for the next iBOS/iSOS; touched-checks skipped on any bar the live anchor moved |

All four fibs are implemented.

**2026-07-08 changes:** Structure dropped TP4 (−0.270) / TP5 (−0.618) — it now stops at TP3 (0.0); it
also adopts a more-extreme confirmed internal swing as its pull anchor. Macro's held full-reset was
reverted to hide-only, its bottom anchor is now always the running low since the bear SOS, and HIDE runs
after extend+touch. The Internal fib is new.

**2026-07-09 changes:** the Structure AND Internal fibs **dropped the TP3-hit `reset_active` latch**
(the 2026-07-08 "hide the leg once TP3 is hit" is gone — TP3 is now just a touch; `reset_active` stays a
kept-but-always-False mirror, and a leg is spent only on a new origin / external-break clear). Both also
gained an **extend-changed guard**: touched-checks are skipped on any bar the live anchor itself moved (a
pullback wick), so a fresh extreme can't retroactively satisfy the level it just created. The **Macro**
seeds its bear-SOS low-tracker on the first bar too, so the first bullish SOS can lock without a prior
bear SOS.

Structure's gating logic (ported exactly): 0.618 (E1) is the gate — it must be reached before
anything else arms; the deeper retrace levels (E2/E3/E4/1.0) only register while price is
at/through 0.618; the targets (TP1–TP3) only register from the bar **after** 0.618 was first
reached; a new leg (origin bar changes) resets every touch — and any bar on which the anchor moved
skips the touched-checks.

Sniper's lifecycle (ported exactly): a BOS drops one 0.382–0.5 zone across the impulse leg
(`bull/bear_bos_high/low`), measured **from the leg origin** (`fib_from_origin`), and arms it
(`zone_active = false`). The first bar whose range trades into the zone confirms it once
(`confirmed`), latching `zone_active`. A new BOS replaces the zone and re-arms. One subtlety kept
from Pine: the break bar can latch `zone_active` if its own range already covers the fresh zone,
but it never emits a `confirmed` event for that bar — so that zone then confirms silently and no
later bar re-confirms it.

Macro's lifecycle (ported exactly): a bull-only cycle. The bottom (LL, the 1.0 level) locks on a
bullish SOS that follows a bearish SOS; the top (HH, the 0.0 level) then extends on every new
confirmed higher-high (`new_cycle` / `extended` events). The cycle **resets** when price closes
below the locked bottom, and **hides** (stays locked, `active`=false) when price closes above the
top. Level touches use the same 0.618 gate as Structure. Two subtleties kept from Pine: (1) the
macro spans multiple BOS legs — the top keeps extending, it does not reset per leg; (2) unlike
Structure, the Macro does NOT skip its checks on a lock/extend bar, so a level can be reset and
re-touched on the same bar — touch events are therefore edge-detected against the previous bar's
state (`X and not X[1]`), so that same-bar retouch emits no event. **≤5m only** — that timeframe
gate is the caller's job (feed `MacroFib` only ≤5m bars).

---

## Timeframes & what each fib needs

**Which fib works on which timeframe:**

| Fib | Timeframes | Note |
|---|---|---|
| **Structure** | any | no timeframe branching — same code every TF |
| **Sniper** | any | same |
| **Macro** | **≤5m only** | Pine gates it to `timeframe.in_seconds() <= 300`; that gate is NOT in `MacroFib` — the caller must only feed it ≤5m bars |

**What the fibs need to be accurate (all four):**

1. **An accurate structure engine.** The fibs are downstream of `engines/market_structure/` — they read its
   swings, BOS/SOS, and confirmed highs/lows. Wrong structure → wrong fibs. It is the foundation.
2. **The right candles.** They must see the same price data you chart on. Same code + a different
   broker/feed = different candles = different levels. (See "Live parity" below.)
3. **Closed bars, in order, one at a time.** Each fib is a streaming state machine — its
   touch/gate/zone/cycle state carries bar-to-bar and cannot be recomputed from a single bar. Feed
   one closed bar per `update()`, in sequence; never skip or replay out of order.
4. **Warm-up.** Nothing fires until the first real setup forms in-window: a first leg (Structure),
   a first BOS (Sniper), or a full bear-SOS→bull-SOS cycle (Macro — the longest to warm up). Don't
   act on events during warm-up.

---

## Public API

```python
from fibonacci import StructureFib, SniperFib, MacroFib, InternalFib, StructureSnapshot

fib = StructureFib()
sniper = SniperFib()
macro = MacroFib()   # only feed this <=5m bars
ifib = InternalFib()

# Each closed bar, right after market_structure's engine.update(bar) -> events:
snap = StructureSnapshot.from_engine(structure_engine, events)
fib_events = fib.update(bar.high, bar.low, snap)

fib_events.active            # anchors valid -> a fib is currently drawn
fib_events.origin_changed    # a new leg started this bar (all touches reset)
fib_events.touched           # list[FibTouch] first-reached THIS bar (edge-triggered events)
fib_events.levels            # dict{name: price} — every level's current price (state)
fib_events.touched_so_far    # set[str] — cumulative touched names on this leg
fib_events.half_reached      # inbound 0.5 tapped this leg (ungated) — A+ EARLY tier (state latch)
fib_events.ash / .asl        # the leg's two anchors — the prices every level was measured from
fib_events.ash_loc / .asl_loc  # …and the BARS they sit on (all four None while inactive)
# FibTouch = (level, ratio, price, role)  role: "entry" (retrace side) | "target" (profit side)

sniper_events = sniper.update(bar.high, bar.low, snap)
sniper_events.active         # a zone exists (a BOS has fired at least once)
sniper_events.direction      # 1 bull zone / -1 bear zone
sniper_events.zone_top       # upper edge (max of the 0.382 / 0.5 levels), .zone_bot = lower edge
sniper_events.created        # a fresh zone was set THIS bar (a BOS fired) — event
sniper_events.confirmed      # price entered the zone for the first time THIS bar — event
sniper_events.zone_active    # cumulative latch: price has entered the current zone

macro_events = macro.update(bar.index, bar.high, bar.low, bar.close, snap)  # note: needs index + close
macro_events.active          # levels currently computed (cycle locked + visible + range>0)
macro_events.top             # the HH (0.0), .bot = the LL (1.0)
macro_events.locked          # a cycle bottom is locked (may be hidden), .visible = currently shown
macro_events.new_cycle       # a fresh cycle locked THIS bar — event
macro_events.extended        # the top pushed to a new HH THIS bar — event
macro_events.touched         # list[FibTouch] first-reached THIS bar (edge-triggered)
macro_events.levels          # dict{name: price}; names: HH/TP2/TP1/E1/E2/E3/E4/LL

ifib_events = ifib.update(bar.index, bar.high, bar.low, snap)   # note: needs index (for anchor locs)
ifib_events.active           # an internal leg is currently seeded/drawn
ifib_events.direction        # 1 bull leg, -1 bear leg, 0 none
ifib_events.top              # the 0.0 anchor (bull) / 1.0 (bear); .bot = the opposite
ifib_events.seeded           # a fresh internal leg seeded THIS bar (an iBOS/iSOS) — event
ifib_events.cleared          # an external BOS/SOS wiped the fib THIS bar — event
ifib_events.reset_active     # kept-but-always-False mirror (TP3-hit setter dropped 2026-07-09)
ifib_events.touched          # list[FibTouch] first-reached THIS bar (edge-triggered)
ifib_events.levels           # dict{name: price}; names E1-E4/1.0/TP1-TP3 (same 8 as Structure)
```

---

## Relationship to `engines/market_structure/`

The fib engine is **downstream** of the structure engine and depends only on its PUBLIC output —
never its internals. `StructureSnapshot.from_engine(engine, events)` reads the documented
properties (`active_swing_high/low`, `dir`, `pullback_mode/extreme/extreme_loc`,
`last_confirmed_high/low`) and the documented `ExternalEvents` (`bull/bear_bos`, `bull/bear_sos`,
and the break-leg `bull/bear_bos_high/low` + locs). The 2026-07-08 re-sync added two capture-only
`InternalEvents` reads: `i_confirmed_high/low_*` (fired on each iSH/iSL confirm — the Structure fib's
internal-swing anchor) and `ifib_seed_*` (the internal leg's low/high/dir at each iBOS/iSOS — the
Internal fib's seed). Both are additive exposures of state the structure engine already computes; no
detection logic changed (structure parity re-confirmed exit 0). If you need a new field from structure,
add a read property/event there (as was done for these) — do not reach into `_ext`/`_int`.

**Gotcha — the internal-swing adoption is Pine-gated by `showInternal`.** The Structure fib adopts a
more-extreme `i_confirmed_low/high` ONLY when the snapshot carries it. In the Pine, the whole internal
block sits behind `internalActive = showInternal`, so when a consumer's chart has "Show Internal
Structure" OFF, `i_confirmed_*` is never set and the fib keeps its external anchor. Python's
`market_structure` engine ALWAYS computes internal structure, so a consumer that runs internal-OFF (the
mpc_sos_fade bot does) must suppress those snapshot fields — `EngineStack(EngineConfig(show_internal=False))`
blanks `i_confirmed_*` + `ifib_seed_*` for exactly this reason. This engine was validated with internal
ON (`fib_export.pine`), so its default behaviour is correct; the gate lives in the stack, not here.

The Macro fib also reads `last_confirmed_high/low` (+ locs) and needs the current bar index and
close, so its signature is `macro.update(bar_index, high, low, close, snap)` — the others take only
`(high, low, snap)`.

Same stateful-streaming rationale as `engines/market_structure/` (see its CLAUDE.md): the touch/gate/zone
state carries bar-to-bar and cannot be recomputed from a single bar. Build one `StructureFib`, one
`SniperFib` and one `MacroFib` per symbol/timeframe, feed one closed bar per `update()`.

---

## Do

- Port any change to `mpc_assistant.pine`'s fib blocks back here line-by-line. Keep the gating
  exact — do not reorder or "simplify" the 0.618-gate / targets-from-next-bar / origin-reset logic,
  the Sniper's arm-on-BOS / confirm-once / break-bar-clears-confirm interaction, nor the Macro's
  lock/reset/extend cycle and its edge-vs-previous-bar touch detection.
- When adding a new event or level, update this file's Public API and the tests in the same commit.
- Keep `geometry.py` pure (no state, no I/O) — it is the one core shared by all four fibs.

## Never do

- Do not bake in colours, lines, boxes, or any TradingView drawing concern. This layer emits
  events and prices; drawing is a separate consumer's job.
- Do not reach into `market_structure` engine internals — consume its public reads/events only.
- Do not build a second fib implementation elsewhere. This is the canonical one.
- Do not trust this on live money until the Pine-parity export check below is green.

---

## Validation (Pine ↔ Python parity)

> **2026-07-09 re-paste — parity CONFIRMED (exit 0).** A newer `mpc_assistant.pine` paste dropped the
> TP3-hit `reset_active` latch on the Structure AND Internal fibs, added an extend-changed guard to both
> (skip touched-checks on any bar the live anchor moved), and gave the Macro a first-bar bear-SOS seed.
> All three ported (engine + `fib_export.pine` harness + unit tests, 40 green) and re-validated on a fresh
> `VANTAGE_XAUUSD, 5m` export (13,759 bars) — every compared field (Structure + Sniper + Macro + Internal)
> matched on all warm bars (`--warmup 3154`, exit 0; the warm-up is the Macro cycle cold-start). The column
> set is unchanged — `px_fib_reset_active` / `px_ifib_reset_active` are now always 0 on both sides.
>
> **2026-07-08 re-sync — parity CONFIRMED 2026-07-09 (exit 0).** The four fibs were re-synced to the
> re-pasted `mpc_assistant.pine` (Structure TP4/TP5 drop + internal-swing anchor + TP3 `reset_active`;
> Macro hide-only + always-`ll_since` bottom anchor; the new Internal fib). `fib_export.pine` +
> `compare_fib.py` were updated to match (Internal fib = touch pulses + state only, no per-level price
> columns, to stay under TradingView's 64-plot cap). On a fresh `VANTAGE_XAUUSD, 5m` export (7,562 bars)
> every compared field — Structure + Sniper + Macro + Internal — matched on all 5,646 warm bars
> (`--warmup 1916`, exit 0). The warmup is the Macro cycle's cold-start (Pine's macro is warm from a
> pre-window cycle; a macro cycle is long-lived, so the two engines only reconcile once that cycle ends
> and both lock the same in-window cycle at bar 1916 — Structure/Sniper converge by ~bar 108). One
> InternalFib 0.5-touch fired a single bar late from CSV 2-dp rounding at a float-tie boundary; a
> `_TOUCH_EPS = 1e-6` inclusive margin on the InternalFib touch comparisons absorbs it (« 0.01 tick, so
> it can never register a real un-reached level early). The GREEN notes below predate the re-paste but
> re-confirm the Structure/Sniper/Macro geometry on their own datasets.

**Structure fib — GREEN (2026-07-02, pre-re-paste):** full parity on a `VANTAGE_XAUUSD, 15m` export. Every field
— each level's price, its first-touch pulse, active/dir/origin — matched Python↔Pine across 258
real touch events (E1×52, E2×44, E3×38, E4×34, 1.0×13, TP1×41, TP2×31, TP3×5; TP4/TP5 never reached
in-window).

**Sniper fib — GREEN (2026-07-03):** full parity on a fresh `VANTAGE_XAUUSD, 15m` export (5,431
bars, `--warmup 1116`, exit 0). Every `px_sniper_*` field matched on all 4,315 warm bars, across 57
zones created / 26 confirmed in-window.

**Macro fib — GREEN (2026-07-04):** full parity on a `VANTAGE_XAUUSD, 5m` export (6,862 bars,
`--warmup 2242`, exit 0). Every `px_macro_*` field matched on all 4,620 warm bars, across 3 cycles
locked / 17 top-extends / 15 touch events (2,502 active bars) in-window. The long warmup is
expected: a macro cycle can span thousands of bars, and this export opens mid-cycle (bottom 4098.87
/ top 4889.43 both locked off-window), which cold-started Python can't reproduce until that cycle
ends and an in-window one takes over. The tool only compares Macro when the export actually
exercised it (`px_macro_active` hits 1); on a higher-TF export it prints "Macro present but never
active — export on ≤5m".

The first N bars always mismatch because the Pine export begins warm (chart history before the
window) while the Python engines start cold — the same cold-start pattern as `engines/market_structure/`;
`--warmup N` skips them (the tool prints the last mismatching bar to help pick N). Re-run
`compare_fib.py` after any change to a fib or the fib blocks in `mpc_assistant.pine`.

Wired up, mirrors `engines/market_structure/`'s flow. Two pieces:

1. `indicators/engines/fib_export.pine` — the external + internal structure engine (byte-identical to
   `structure_engine_export.pine`, plus the internal-fib seed captures) + the real Structure, Sniper,
   Macro and Internal fibs lifted from `mpc_assistant.pine` (compute + state machines, drawing removed)
   + `plot()` columns for all four fibs' outputs (`px_fib_*`, `px_sniper_*`, `px_macro_*`, `px_ifib_*`).
   Put it on a chart, export chart data to CSV, drop it in `engines/fibonacci/exports/` (git-ignored).
   Export on ≤5m to also cover Macro.
2. `engines/fibonacci/tools/compare_fib.py <that.csv>` — runs the REAL pipeline (StructureEngine →
   StructureSnapshot → StructureFib + SniperFib + MacroFib + InternalFib) on the CSV's candles and
   diffs against the `px_fib_*` / `px_sniper_*` / `px_macro_*` / `px_ifib_*` columns, bar by bar.
   Exit 0 = parity. Standard library only. Sniper, Macro and Internal columns are optional, so the
   tool also runs on older/higher-TF exports (skipping whatever that export doesn't carry).

All four fibs are green. Expect early-bar mismatches on any re-run to be warmup (structure not yet
converged, or a leg/zone/cycle that began before the export window) — parity holds from the first
full in-window leg onward; the Macro needs the longest warmup because a cycle spans many bars.

## Live parity (build this when a bot first consumes the fib engine)

The export check above proves the Python == TradingView **on the same candles**. Live, the bot's
own price feed is the input, so the same math can still land on different numbers if the feed
differs from the chart. Two rules and one check keep the live bot honest:

1. **Same data source.** Point the bot at the feed you chart on. Different broker/feed = different
   candles = different fibs, even with identical code.
2. **Respect warm-up.** The bot starts cold; it must stream enough bars for structure to converge
   before its fib events mean anything (the export check needed ~1,116 warm bars). Don't act on
   fib events during warm-up.
3. **Log every event + re-check.** Have the bot append each fib event it fires (bar time, level,
   price, direction) AND the closed candle it saw, to a small log. Periodically put
   `fib_export.pine` on that same chart/feed and re-run `compare_fib.py` against the bot's logged
   candles. Green = the live bot is measuring exactly what the chart shows. This is the only way to
   catch a silent live drift once there is no chart to eyeball.

Not built yet — there is no bot consuming this engine. Wire it up together with the eventual
`algos/shared/` fib shim.

## References

- Pine source of truth: `indicators/engines/mpc_assistant.pine` (fib blocks `GRP_FIBO` Structure fib
  ~2318-2439, `GRP_SNIPER` Sniper zone, `GRP_MACRO` Macro ~2511-2655, `GRP_IFIB` Internal fib — seed
  at the six iBOS/iSOS sites ~1400-1609 + clear/extend/touch ~2727-2791) and its live "MPC - JARVIS"
  confirmation table, which defines the event model this engine reproduces. (Line numbers drift as the
  source is re-pasted — grep the `GRP_*` markers.)
- Upstream structure engine: `engines/market_structure/CLAUDE.md`.
- Monorepo context: `../CLAUDE.md`.

## The two RED gates were STALE EXPORTS, not drift — re-exported and GREEN (2026-08-27)

`compare_fib.py` was RED on both exports here — `15_b201e.csv` from bar 14123 and `5_84d6c.csv`
from bar 7322 — and **neither was this engine's fault.** Both were taken **2026-08-20**, the day
before `market_structure`'s refused-wick fix, so their Pine columns encoded the old structure
behaviour.

✅ **CLOSED THE SAME DAY. Aaron re-exported from today's Pine and BOTH gates pass:**
`VANTAGE_XAUUSD, 15_dfe47.csv` (21,403 bars) is **GREEN from bar 32**, and
`VANTAGE_XAUUSD, 5_02c0a.csv` (20,229 bars) is **GREEN from bar 49** — the 5m one with the Macro fib
actually exercised, which the 15m export can never do.

⚠ **The two superseded files were DELETED the same day** and are named below only as history.

🔴 **THIS IS THE ONE CASE WHERE "IT IS UPSTREAM, NOT ME" WAS PUT AT RISK AND SURVIVED.** That
claim is the easiest thing in this repo to say and the hardest to check, because it is exactly what a
genuinely broken port would also say. **A fresh export was the experiment that could have falsified
it.** Read the diagnosis below as a method that earned its keep, not as a story about two files.

🔴 **THE MECHANISM IS WHY THIS ENGINE IS ALWAYS THE ONE THAT LOOKS BROKEN.** `fibo_asl` / `fibo_ash`
ARE the structure engine's active swings, so a single wrong anchor upstream moves **E1-E4, the 1.0,
the whole TP ladder and both Sniper Zone edges at once** — 47 bars × 9 fields on the 15m export off
one bar's disagreement. **A long list of mismatched PRICE fields with no mismatched DIRECTION or
LATCH field beside it is the signature of an inherited anchor, never of a fib arithmetic bug.**
Read `px_fib_100_price` first: it is the leg origin, so if it differs the rest cannot agree.

✅ Confirmed at the source rather than assumed: at both diverging bars, Pine anchored on an EARLIER
and MORE EXTREME bar whose close never broke the level, which is the refused wick that fix removed.
Full table and the OHLC: `engines/market_structure/CLAUDE.md` → *The 2026-08-21 refused-wick fix*.

⚠ **The 5m export ALSO had a SEPARATE and ordinary cold start at bars 49-58** — `px_fib_origin` and
the touch latches, TradingView having been warm before the export window. It was called out
separately so nobody folded it into the anchor story; they were two different things in one file.

⚠ **Nothing here was fixed by editing this engine, and trying would have been the damage.** The fix
was a fresh export from today's Pine, and until it arrived those two reds stayed red — a red is
still a red.

🔴 **A ONE-BAR DISAGREEMENT SURVIVES ON BOTH FRESH EXPORTS, AND IT IS A REAL DIFFERENCE RATHER THAN
WARM-UP — CHECKED, NOT WAVED THROUGH.** In each file the single mismatching bar IS the very first bar
the fib becomes active (bar 31 on the 15m, bar 48 on the 5m), and the single field is the leg's
origin-changed pulse. **Pine compares the new origin index against an unset previous value, and an
unset value makes that comparison neither true nor false — so Pine reports NO change on its own first
activation while this port reports one.** ⚠ **It can only ever happen once per run**, because after
the first activation there is a real previous value to compare against; the gate is the proof, clean
across the remaining 21,371 and 20,180 bars. ⚠ **Harmless in both directions**: the pulse resets
touch latches that are still clear and internal anchors that are still unset, so nothing downstream
moves — **but do not let the next reader rediscover it as a defect, and do not "fix" it by teaching
this port to swallow its first activation.** That would make a genuine first-bar origin change
invisible, which is a worse failure than a cosmetic one, and rule 1 is the reason: *unasked* and
*measured no* must never collapse into the same value.

⚠ **This engine will always need a warm-up allowance where `market_structure` does not, and that is
inherent.** The fibs cannot exist until structure has produced an anchor, so this engine's first
compared bar is always a first activation; structure's never is. **A fib gate that needs no warm-up
at all would be the surprising result, not this one.**
