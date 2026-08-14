# CLAUDE.md — Fair Value Gap Engine Subsystem

**Purpose:** Turn the bar stream into fair-value-gap EVENTS — a price void left by a 3-candle
imbalance (LuxAlgo definition), and the bar a candle later CLOSES fully past it (mitigation). The
signal is the event ("a bull FVG formed at 101–105.5", "a candle closed past it"), not the drawing.
**Scope:** FVG geometry + the single live gap list + its lifecycle (form / mitigate / evict) only.
No trading decisions, no structure detection (this engine is standalone — it reads price patterns
directly), no MT5 ops, no UI, no chart rendering (no boxes, no colours, no directional-visibility
filter — that filter is drawing-only in the Pine and is deliberately not reproduced).
**Status:** BUILT + ✅ **PINE-PARITY RE-VALIDATED 2026-08-06 (exit 0) ON THE REWRITTEN CAP, AND THE
RUN IS NOT VACUOUS.** `compare_fvg.py "VANTAGE_XAUUSD, 15_50e30.csv"` — a **20,046-bar** 15m export
taken off the corrected `indicators/engines/fvg_export.pine` — matches **every compared field on every bar,
from bar 0**, and stays green at warmups 500 / 1000 / 2000. The export configures the engine from
its own `cfg_*` columns and decoded **`max_count=8`, `threshold_pct=0.04`, `require_close=False`,
EQ-exempt ON (pivot=2, mult=0.1)**, so the exemption branch was live on BOTH sides rather than
agreed-upon-while-switched-off. `verify_parity.py` on the same file: `ALL IN SYNC`.

🔴 **THE EXERCISE CHECK IS THE PART THAT MATTERS, because a green gate says nothing about a branch
neither side entered.** The cap is 8, and **6,035 of 20,046 bars (30%) hold MORE than 8 live gaps,
peaking at 13.** Under the OLD swap rule that is arithmetically impossible — it bounded the live
total at `max_count` — so those 6,035 bars are the rewritten rule firing, matched to Pine on every
one of them. ⚠ **Do not settle for "the flag was on" as evidence next time**: `cfg_eq_exempt = 1`
proves the input, and the gap COUNT above the cap is what proves the behaviour.

⚠ This line said "RE-VALIDATED 2026-07-19" for the whole day the cap was rewritten, while the entry
below honestly recorded that `compare_fvg.py` was unrun — **a Status line claiming validation over
changed code is this repo's own label-vs-code defect, and it is the line a reader actually sees.**
Re-export and re-run before editing it again. Re-synced 2026-07-18 to a mpc
default drift + defaults reconciled: the middle-bar close-cleared check is now the OPTIONAL
`require_close` flag (Pine `fvgRequireClose`, default False): the gate `(not fvgRequireClose or
close[1] > high[2])` landed in mpc on 2026-07-17, AFTER the last (07-14) validation, so the engine and
`fvg_export.pine` had silently gone stale — both hardcoded the close check while the mpc DEFAULT skips
it. Defaults also reconciled to the Pine: `max_count` 6→10, `threshold_pct` 0.1→0.0 (the sub-15m value;
15m+ uses 0.04). `fvg_export.pine` now carries `cfg_fvg_*` columns and `compare_fvg.py` reads them, so
parity survives any Pine input tweak. Unit-tested (17 hand-traced tests, green). Re-validated at the new
behaviour on a fresh 16,639-bar `VANTAGE_XAUUSD, 5m` grand export — `compare_fvg.py` exit 0 (config +
EQ-exemption coupling read from the CSV's `cfg_*` columns). The one canonical implementation — no
consumer builds its own.
**Pine:** ported from `indicators/engines/mpc_assistant.pine` FVG block ("FAIR VALUE GAPS — persist until
mitigated", + the `GRP_FVG` inputs); parity harness is `indicators/engines/fvg_export.pine`, diffed against
this Python by `tools/compare_fvg.py`.
**Last reviewed:** 2026-08-06 — 🔴 **THE EQ EXEMPTION WAS SELF-CANCELLING HERE, WHICH MADE IT INERT, AND IT PUT THE A+ PARITY GATE RED FOR THREE DAYS.** The cap counted **every** gap while the drop scan skipped the exempt ones, so a protected gap still HELD A SLOT: keeping it evicted the newest ORDINARY gap in its place. That is a SWAP, not an exemption. `mpc_assistant.pine` fixed the identical bug on 2026-08-03 (`b1b461b`) and measured it over 40,000 M15 bars — **the old rule never once held more gaps than the exemption being OFF**, and it cost the A+ bot 2 setups for 0 gained, because the gaps it protected cost it the gaps it would have traded. **`max_count` now bounds the ORDINARY gaps only and an exempt gap rides ON TOP**, so the live total is unbounded by that input and bounded by the EQ engine instead (`max_levels` per side, each dying on a close through it). ✅ **MEASURED on 155,531 real M15 bars through `mpc_sos_fade`: 92,984 bars hold an exempt gap, 20,546 hold MORE than the cap of 7, max 12 at once — the same maximum the Pine commit measured independently.** ⚠ **With no `eq_levels` passed the count equals the list length, so the standalone path is byte-identical and every exemption-off result still reproduces.** 🔴 **`indicators/engines/fvg_export.pine` had the same stale rule and is fixed in the same commit** — the harness that VALIDATES this engine had gone stale against both the indicator it mirrors and the engine it checks, so the next export would have reported a correct engine as red. ⚠ ~~**Neither on-disk FVG export can run today** (3 and 6 plotted slots against the current 10), so `compare_fvg.py` is UNRUN against the new rule — re-export before treating this engine's parity as re-validated.~~ ✅ **CLOSED THE SAME DAY on a fresh 20,046-bar 15m export (`15_50e30.csv`): exit 0 from bar 0, green at warmups 500 / 1000 / 2000, `verify_parity.py` ALL IN SYNC — and NON-VACUOUS, because 6,035 of those bars (30%) hold MORE than the cap of 8, peaking at 13, which the old swap rule could not produce.** See the Status line at the top for the full run. ✅ The old test pinned the SWAP behaviour and is replaced by two: one asserts the exempt gap is held **IN ADDITION** to the cap, the other that the cap **still bites** on the ordinary gaps while an exempt one is held — a pair, because the first alone would pass just as happily for a cap that had stopped working. Both watched RED against the old rule. ⚠ **`command-center`'s chart overlays consume this change** (`services/fvg_overlays.py` passes EQ levels), so the lab's price chart now draws the extra pinned gaps — which is correct, since it mirrors `mpc_assistant.pine`; its 16 tests are green. **The standing lesson: an exemption that does not also change the COUNT is not an exemption, and it fails in the quietest way available — it looks implemented, it is unit-tested, and it measurably does nothing.** Earlier: 2026-08-01 — **a SECOND consumer landed, and it wants the INDICATOR's settings, not the strategy's.** `command-center/backend/services/fvg_overlays.py` replays this engine over a backtest's candles to draw the gaps that were live at each trade / blocked setup / missed setup on the lab's price chart. It configures the engine from `mpc_assistant.pine` (cap 8, `require_close=False`, the timeframe-split 0.0/0.04 floor, EQ-exempt cap via `equal_highs_lows/`) — i.e. the OPPOSITE side of the `require_close` fork below from the one `mpc_sos_fade` pins. **That is deliberate and it is now load-bearing in two directions**: the chart must match what TradingView draws, and the bot must match `mpc_strategy.pine`, so the two consumers legitimately see different gap sets off the same engine (the bot sees strictly fewer). Anyone reconciling "the" FVG defaults must not collapse them. The new consumer carries its own Pine check — it diffs its boxes against the export's `px_fvg_*` arrays, so it validates this engine's public output a second, independent way (`command-center/backend/tests/test_fvg_overlays.py`, 16 tests green). No engine code changed. Earlier: 2026-07-31 (late) — ✅ **RE-CONFIRMED ON A SECOND TIMEFRAME.** `compare_fvg.py --warmup 4990` → exit 0 on a 13,186-bar `VANTAGE_XAUUSD, 5m` export, where `cfg_fvg_thresh` read back as **0.0** — the timeframe split firing the OTHER way, so both branches of it are now proven through a real export. The long warm-up is pure ghost carry-in and the export proves it: **`px_fvg_formed` never mismatches on a single bar** (both sides agree on every gap FORMATION from bar 0); the slot columns differ only because Pine opens holding gaps from before the window, one of them at 4733.88 while price trades ~4520 — it can never close past its far edge, so it sits in Pine's array for ever. Textbook 2026-07-19 ghost trap, observed rather than theorised. Earlier the same evening — ✅ **VALIDATED, AND THE 15m FLOOR IS PROVEN THROUGH THE
EXPORT.** `compare_fvg.py` → **exit 0** on a real 21,691-bar `VANTAGE_XAUUSD, 15m` export
(2025-09-01 → 2026-07-31) at **zero warm-up**, across all **10** slots, with the EQ coupling active
(`cfg_eq_exempt = 1`, pivot 2, mult 0.1, max 6) so the exemption is validated rather than assumed.
The tool read `cfg_fvg_thresh = 0.04` back out of the file — i.e. the timeframe split added the same
day **fired correctly on a 15m chart**, which is the one thing a green could not have shown before it
existed. `cfg_fvg_maxcount = 8`, `cfg_fvg_requireclose = 0`. Earlier the same day — 🔴 **THE HARNESS WAS UNDER-CHECKING THE ARRAY, AND ITS SIZE FLOOR DID NOT MATCH mpc ON 15m.** Two real holes in `indicators/engines/fvg_export.pine`, both now closed; no engine code changed. (1) **It plotted 6 slots while the cap is 8**, so gaps 7 and 8 were live in Pine and invisible to the diff — every past "exit 0" covered the oldest six only. Now 10 slots per array (`px_fvg_top_/bot_/bull_1..10`), the `fvgMaxCount` input is capped at 10 to match, `compare_fvg.py`'s `_MAX_SLOTS` is 10, and the tool now REFUSES an export whose `cfg_fvg_maxcount` exceeds the plotted slots rather than reporting a partial green. (2) **The minimum-gap floor was one flat input defaulting to 0.0**, but mpc's is timeframe-split (`mpc_assistant.pine:410-412`: `0.0` below 900s, `0.04` at 15m and above). Exported on a 15m chart, the harness would have run a DIFFERENT rule from the indicator it mirrors — Pine-vs-Python parity would still have gone green, because `cfg_fvg_thresh` configures both sides, but the run would have proven nothing about the 15m gap set that `mpc_strategy.pine` actually trades. The export now carries `fvgThreshLTF` / `fvgThreshHTF` and the same `timeframe.in_seconds() < 900` ternary, and `cfg_fvg_thresh` plots the EFFECTIVE value, so the comparator needed no change. ⚠ **Consequence: `cfg_fvg_thresh` legitimately differs between a 5m and a 15m export of the same build.** That is the split working, not drift. 17 unit tests green (529 repo-wide). Earlier the same day: **`max_count` default synced 10 → 8** to the mpc paste (`fvgMaxCount`, `mpc_assistant.pine:414`), found by `/audit-engines`. **DETECTION IS UNCHANGED** — the imbalance formula, both thresholds (`0.0` sub-15m / `0.04` 15m+) and `fvgRequireClose = false` are all byte-identical, so this is a FIFO-cap default only and the 2026-07-19 parity result still describes the logic. 17 unit tests green. ⚠ **Neither strategy bot moves:** `mpc_sos_fade` and `mpc_bleg` both PIN `fvg_max_count=7` (they replay `mpc_strategy.pine`, which carries its own count), so this default reaches nothing they do. ✅ **`backtest/replay/stack.py`'s `EngineConfig` was RECONCILED 2026-07-31** (`fvg_max_count` 6→8, `fvg_threshold_pct` 0.1→0.0, both now mirroring the engine) — and doing it exposed that the "harmless, every real consumer pins" claim below was **half wrong**: `mpc_sos_fade` pins `fvg_max_count` and `fvg_require_close` but NOT `fvg_threshold_pct`, so it was silently inheriting `stack.py`'s 0.1 (which happens to be `mpc_strategy.pine`'s 15m floor) by coincidence rather than by decision. Removing it broke `compare_strategy.py` on the first compared bar. The bot now pins `fvg_threshold_pct=0.1` explicitly and a test asserts all four pins, so this shared default is free to move again. Original note, kept because the reasoning still stands: ⚠ it was **two generations stale** — it still carries `fvg_max_count = 6` and `fvg_threshold_pct = 0.1`, i.e. the pre-2026-07-18 values that the engine reconciled away and this pass moved again. Harmless today (every real consumer pins), but it is exactly the silent-parity-trap that `backtest/CLAUDE.md` → *Rules* warns about; reconcile it deliberately, not as a side effect. Also synced: `compare_fvg.py`'s FALLBACK `--max-count` (8) — the tool reads `cfg_fvg_maxcount` from the export when present, so the flag only bites on a pre-`cfg` export. Earlier: 2026-07-26 — no engine change, but the `require_close` DEFAULT is now documented as a downstream trap: it is correct for `mpc_assistant.pine` and wrong for `mpc_strategy.pine`, which hardcodes the check (see the callout under "What it detects"). Earlier: 2026-07-19 (re-synced to the mpc FVG default drift — optional `require_close`,
reconciled defaults, EQ-exemption coupling; unit tests green; Pine-parity re-validated exit 0 on a fresh
grand export)

---

## Key paths

```
engines/fair_value_gaps/
├── engine.py       ← the FVG state machine (FairValueGapEngine): detect + cap, then mitigate
├── types.py        ← FairValueGap (a gap); FvgEvents (output)
├── __init__.py     ← re-exports the public API
├── CLAUDE.md       ← this file
├── tests/
│   └── test_engine.py
└── tools/
    └── compare_fvg.py   ← Pine↔Python parity harness (reads a TradingView CSV export)
```

Pine source of truth: `mpc_assistant.pine`'s `GRP_FVG` inputs + the "FAIR VALUE GAPS" compute block.
Parity export build: `indicators/engines/fvg_export.pine`.

---

## What a fair value gap is (ported semantics)

A **bullish FVG** is the 3-candle imbalance the LuxAlgo definition describes: the two outer candles
never overlap (`low > high[2]`) and the gap is at least `threshold_pct`% of price (`(low - high[2]) /
high[2] * 100 > threshold_pct`). The middle displacement bar's close clearing the gap
(`close[1] > high[2]`) is **OPTIONAL** — gated by `require_close` (Pine `fvgRequireClose`, default
False), i.e. `(not require_close or close[1] > high[2])`. At the default the close check is skipped =
the classic FVG. There is **no** clean-impulse or progressive-close requirement — any bars that meet
the conditions qualify. The gap spans `bottom = high[2]` up to `top = low`. A **bearish FVG** mirrors
it (`high < low[2]`; optional `close[1] < low[2]`; `top = low[2]`, `bottom = high`). Either way
`top > bottom`.

> **`require_close = False` is right for `mpc_assistant.pine` and WRONG for `mpc_strategy.pine`.**
> The assistant exposes `fvgRequireClose` as an input defaulting off, which is what this default
> mirrors. The STRATEGY file HARDCODES the check (`close[1] > high[2]` / `close[1] < low[2]`,
> lines 1686/1688) — it has no input and is permanently ON. A consumer replaying the strategy must
> therefore pass `require_close=True`, and one that doesn't will create gaps the Pine never did.
> That is exactly what happened: `strategies/python/mpc_sos_fade` left it unpinned from 2026-07-18
> (when the gate landed here) until 2026-07-26, when a fresh export produced one phantom entry edge
> on a weekend-gap bar and `compare_strategy.py` caught it. The pin now lives in
> `backtest/replay/EngineConfig.fvg_require_close` + that bot's `engine_config()`. **Changing a
> default here can silently break a downstream port — the two mpc Pine files disagree, so no single
> default is correct for both.**

Two things end a gap:

- **Mitigation** — a candle **CLOSES fully past the gap's far edge** (bull: `close <= bottom`; bear:
  `close >= top`). A mere wick into the gap no longer removes it. This is the real signal — the gap
  was consumed. Emitted as `mitigated`. **Skipped on the gap's own creation bar** (`bar_index >
  born`), so a fresh gap can't self-mitigate. (Pine also gates this on `barstate.isconfirmed`; the
  engine only ever sees closed bars, so that is always true here.)
- **Eviction** — the total list already holds `max_count` (default 8) gaps, so the OLDEST **not
  exempt by the EQ coupling** is dropped when a newer one forms (Pine scans for the oldest non-EQ gap).
  With no `eq_levels` passed the first gap is never exempt → a plain drop-oldest, unchanged. **Not** a
  trading signal — emitted separately as `evicted`. An FVG behind an active EQH/EQL (`eqExemptFvg`,
  default ON in mpc) is kept until mitigated; if every gap is exempt, none are dropped.

Gaps are **not** wiped on a BOS/SOS — the impulse leg that breaks structure is exactly what leaves
the gaps, and the retracement back into them is the entry confluence (this is why the A+ setup reads
them). Only a close fully past the far edge or the FIFO cap removes a gap.

---

## Per-bar order (ported exactly — do not reorder)

Each bar, `update()` runs, mirroring the Pine's two blocks in order:

1. **Detect + cap** — form a bull and/or bear gap on a 3-candle imbalance (void + middle-close
   cleared + size > `threshold_pct`% of price), then FIFO-drop the oldest while the list exceeds
   `max_count`.
2. **Mitigate** — remove any gap a candle closed fully past this bar (far-edge close test, guarded
   off the creation bar).

Detection runs FIRST so a gap created this bar survives the cap and is not mitigated on its own bar.
Keep this order identical to Pine.

---

## Timeframes & what it needs

No timeframe branching and **no upstream engine** — FVG is standalone, driven by OHLC alone. It needs:

1. **The right candles.** Same price feed you chart on (see "Live parity" in `engines/fibonacci/CLAUDE.md`
   — the same rule applies once a bot consumes this engine).
2. **Closed bars, in order, one at a time.** The gap list + the 3-bar rolling window carry
   bar-to-bar; feed one closed bar per `update()`, in sequence, never replayed out of order.
3. **Warm-up.** Nothing forms until the first in-window qualifying imbalance; and the first two bars
   can never form (the two-bars-back candle does not exist yet).

The optional **directional filter** in the Pine (`fvgDirOnly` / `st.dir`) only recolours/hides boxes
— it does not add or remove gaps — so this engine does not consume structure. Every gap is emitted
with its `is_bullish` flag; a consumer (e.g. the A+ setup) decides alignment against structure itself.

---

## Public API

```python
from fair_value_gaps import FairValueGapEngine

fvg = (
    FairValueGapEngine()
)  # max_count=8, threshold_pct=0.0, require_close=False — the Pine defaults

# Each closed bar, in order:
ev = fvg.update(bar.index, bar.open, bar.high, bar.low, bar.close)
# To model the mpc `eqExemptFvg` coupling (a gap behind an EQH/EQL survives the cap), run the EQ
# engine FIRST and pass its state — the public-output pattern, so FVG never imports EQ:
#   eq_ev = eq.update(i, h, l, c)
#   ev = fvg.update(i, o, h, l, c, eq_levels=eq_ev.active_eqh + eq_ev.active_eql, eq_tol=eq_ev.tolerance)
# Omit eq_levels for the standalone, exemption-off behaviour (plain FIFO) — nothing else changes.

for g in ev.formed:  # gaps formed THIS bar (event)
    g.top, g.bottom, g.is_bullish
    g.born_index  # the bar it formed on
    g.id  # stable id: match a formed gap to its later mitigation
for (
    g
) in ev.mitigated:  # gaps closed fully past THIS bar — a candle closed through the far edge (event)
    ...
for g in ev.evicted:  # gaps aged out past the cap THIS bar — NOT a signal
    ...
ev.active  # live gaps, oldest-first (state) — mirrors the Pine fvg* arrays
```

---

## Do

- Port any change to `mpc_assistant.pine`'s FVG block back here line-by-line. Keep the per-bar order
  (detect+cap → mitigate), the imbalance conditions (void `low > high[2]` / `high < low[2]` + the
  OPTIONAL middle-close-cleared gate `(not fvgRequireClose or close[1] > high[2])` / `(... < low[2])` +
  `%`-of-price threshold), the close-past-far-edge mitigation, the `bar_index > born` guard and the
  FIFO cap exact — do not "clean up" or reorder them. Mirror any new `GRP_FVG` input as a constructor
  arg AND a `cfg_fvg_*` column in `fvg_export.pine` (read by `compare_fvg.py`).
- When adding a new event or field, update this file's Public API and the tests in the same commit.

## Never do

- Do not bake in colours, boxes, or the directional-visibility filter — those are TradingView
  drawing concerns; this layer emits events.
- Do not build a second FVG implementation elsewhere. This is the canonical one.
- Do not let this engine or the FVG block in `mpc_assistant.pine` drift; re-run the parity check
  after any change to either.
- Do not trust this on live money until the Pine-parity export check below is green.

---

## Validation (Pine ↔ Python parity)

**Unit tests — GREEN:** `python3 -m pytest engines/fair_value_gaps/tests/ -q` (17 hand-traced tests
pinning formation, the void + optional middle-close-cleared conditions, that a non-clean / non-progressive
sequence now DOES form a gap, the two-bar warm-up, close-past-far-edge mitigation on both sides, that
a wick no longer mitigates, the creation-bar guard, FIFO eviction, the %-of-price threshold, and the
EQ-exemption cap behaviour).

**Full Pine↔Python parity — GREEN (exit 0), 2026-07-19.** Re-validated at the new behaviour
(`require_close` gate + reconciled defaults 10/0.0 + EQ-exemption coupling) on a fresh 16,639-bar
`VANTAGE_XAUUSD, 5m` grand export. The tool reads the settings from the export's `cfg_fvg_*` /
`cfg_eq_*` columns — run it with NO config flags:
`python3 engines/fair_value_gaps/tools/compare_fvg.py "<that.csv>" --warmup N`. The harness:

1. `indicators/engines/fvg_export.pine` — the FVG compute block from `mpc_assistant.pine` (drawing removed,
   the four `fvgTops/fvgBots/fvgIsBull/fvgBorn` arrays kept) + `plot()` columns for the active gap
   arrays (**10** slots × top/bottom/is-bull — it was 6 against a cap of 8 until 2026-07-31, so two
   live gaps went unchecked; keep the slot count, the `fvgMaxCount` maxval and `compare_fvg.py`'s
   `_MAX_SLOTS` moving together), the count, the formed/mitigated pulses, the `cfg_fvg_*`
   settings columns (thresh / maxcount / requireclose), AND — to reproduce the `eqExemptFvg` coupling —
   the EQ compute block + `f_fvgNearEq` + the exempt eviction, plus `cfg_eq_*` columns (pivotlen /
   atrmult / max / exempt). `compare_fvg.py` reads `cfg_eq_*`, runs the Python EqualHighsLowsEngine, and
   feeds its active levels + tolerance into the FVG cap — so the coupling is validated, not assumed. Put
   it on a chart, Export chart data → CSV, drop it in `engines/fair_value_gaps/exports/` (git-ignored).
   **Gotcha (fixed 2026-07-10):** the parity plots MUST use a fully-transparent colour
   (`color = color.new(..., 100)`), NOT `display = display.none` — TradingView's "Export chart data"
   silently excludes `display.none` plots from the CSV, so the FVG columns never exported the first
   time. The harness now uses transparent colours (the same trick `fib_export.pine` uses).
2. `engines/fair_value_gaps/tools/compare_fvg.py <that.csv>` — runs `FairValueGapEngine` on the CSV's
   candles and diffs against the `px_fvg_*` columns, bar by bar. The active arrays are compared
   slot-by-slot (oldest first), which proves formation, mitigation AND eviction at once. Exit 0 =
   parity. Standard library only.

Expect early-bar mismatches to be warm-up (the Pine export opens with gaps whose displacement began
before the export window; the cold-started Python engine can't know them — they flush out as they
tap or evict). Use `--warmup N`; the tool prints the last mismatching bar to help pick it. **This
check must exit 0 on a fresh export before the engine is committed as validated.**

## References

- Pine source of truth: `indicators/engines/mpc_assistant.pine` FVG block + `GRP_FVG` inputs.
- Parity export build: `indicators/engines/fvg_export.pine`.
- Consumers, and they run DIFFERENT settings on purpose (see the `require_close` callout above):
  - `strategies/python/mpc_sos_fade/` — the A+ setup reads live gaps overlapping the fib entry zone
    as confluence, via `backtest/replay/stack.py`. Pins `max_count=7`, `require_close=True`,
    `threshold_pct=0.1` to match `mpc_strategy.pine`.
  - `command-center/backend/services/fvg_overlays.py` — draws the gaps that were live at each trade /
    blocked / missed setup on the lab's price chart. Uses `mpc_assistant.pine`'s settings (cap 8,
    `require_close=False`, the 0.0/0.04 timeframe split, EQ-exempt cap) because it mirrors the
    INDICATOR. See `command-center/backend/CLAUDE.md` → *Fair value gaps*.
- Sibling in shape (also events-not-visuals off the same indicator): `engines/order_blocks/CLAUDE.md`.
- Monorepo context: `../CLAUDE.md`.
