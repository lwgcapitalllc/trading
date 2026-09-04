# CLAUDE.md — VWAP Engine Subsystem

**Purpose:** Turn the bar stream into a running, volume-weighted average price line — the session
VWAP — plus the derived close-vs-line cross. The signal is the value and the cross ("VWAP = 3987.4",
"close crossed up through VWAP"), not the drawn line.
**Scope:** The VWAP value + its trading-day anchor + a derived cross only. No trading decisions, no
MT5 ops, no UI, no chart rendering (no line, colours or fill). First engine that needs a **volume**
column in the feed.
**Status:** Production — ported from `mpc_jarvis.pine`'s `ta.vwap(hlc3)` line, unit-tested (13
hand-traced tests, green), and **100% Pine-parity-validated on a real `VANTAGE_XAUUSD, 5m` export**
(6,973 bars): both fields — the VWAP value and the trading-day anchor pulse — match on every warm bar
(`--htf-rollover 18 --warmup 90`, exit 0). The one canonical implementation — no consumer builds its
own.
**Pine:** ported from `indicators/engines/mpc_jarvis.pine` line 852 (`vwapValue = ta.vwap(hlc3)`); parity
harness is `indicators/engines/vwap_export.pine`, diffed against this Python by `tools/compare_vwap.py`. Pine
stays in `indicators/` (shared source, TradingView-only toolchain); the CSV + compare tool are the
engine's half.
**Consumers:** `strategies/python/bos/` since 2026-08-07 — the FIRST strategy consumer this
engine has had, and the first thing in the repo's strategy layer to need a volume column. It reads
`VwapEvents.value` for its F10 filter (refuse a setup while price is not closing on the trend's own
side of the line) and reads nothing else. ⚠ **That makes this engine trade-affecting now**, where
before it fed nothing: a change here moves BOS entries. The `crossed_up` / `crossed_down` edges are
still unconsumed — the BOS filter is a STATE, deliberately, and asks only which side the bar closed.
⚠ A private VWAP anchored at a structure break was considered and REFUSED: it would be a second
implementation of this engine, and it would not be the line anyone is looking at on the chart.
**Last reviewed:** 2026-08-07 — gained its first consumer (above); no code change. The one thing a
consumer must handle is `value = None`, which this engine returns whenever the session has seen no
volume yet. It means **cannot compute**, never zero, and `bos` reads it as a REFUSAL on both
sides for exactly that reason. Earlier: 2026-07-05

---

## What this engine is (ported semantics)

The source is one line: `vwapValue = ta.vwap(hlc3)`. That is a **session-anchored, volume-weighted
mean** of `hlc3` (the (high+low+close)/3 mid-price):

    value = sum(hlc3 * volume) / sum(volume)   — accumulated since the trading-day anchor, reset daily

`ta.vwap` with no explicit anchor resets at the start of each **trading day**. So each bar the engine
adds `hlc3 * volume` and `volume` to running sums, divides, and clears the sums on the trading-day
roll. A bar with zero/na volume adds nothing; a session with no volume yields `None` (Pine `na`).

### Pine-validated vs derived

- **`value`** and the **`anchored`** (trading-day reset) pulse are the ported, Pine-validated
  output — checked bar-for-bar against `ta.vwap(hlc3)` and the "D" roll in the export.
- **`side` / `crossed_up` / `crossed_down`** are a **derived convenience** the engine adds — the
  Pine source only DRAWS the line, it has no cross event. They are unit-tested but are **not** in the
  Pine parity set. (Same split the liquidity engine used: it consumed the sessions engine's H/L and
  added sweep tracking on top.)

---

## The anchor = the trading-day boundary (same knob as the liquidity engine)

`ta.vwap`'s default anchor is the start of the exchange's trading day — the **same** boundary
`request.security(..., "D", ...)` rolls on, which for VANTAGE:XAUUSD opens at **18:00 New York**.
This engine reconstructs it exactly like `engines/liquidity/`: convert the bar's UTC time to
`htf_timezone`, shift the clock FORWARD by `(24 - open_hour)` so the open hour lands at midnight, and
cut the day on that shifted date. Defaults: `htf_timezone="America/New_York", htf_rollover_hours=18`.
Both are calibration knobs, locked against the real export by the `px_vwap_anchor` roll pulse in
`tools/compare_vwap.py` (sweep `--htf-rollover` until the pulse matches, then the value follows). A
different instrument may open at a different hour (e.g. other FX at 17:00) — pass its open hour then.

---

## Volume (the new feed requirement)

Every prior engine took only OHLC + timestamp. VWAP also needs the bar's **volume**. For XAUUSD this
is **tick volume** — which is exactly what Pine's `ta.vwap` reads, so parity is unaffected and the
value is meaningful. The parity export plots the volume it used as `px_volume`, and the compare tool
feeds THAT back to the engine, so both sides use an identical volume series (no data-source
mismatch). A bot must feed the broker bar's volume alongside OHLC + timestamp.

---

## Key paths

```
engines/vwap/
├── engine.py       ← VwapEngine: the streaming state machine
├── types.py        ← VwapEvents (value + anchor + derived cross)
├── __init__.py     ← re-exports the public API
├── CLAUDE.md       ← this file
├── tests/
│   └── test_engine.py       ← 13 hand-traced tests
└── tools/
    └── compare_vwap.py      ← Pine↔Python parity harness (reads a TradingView CSV export)
```

Pine source of truth: `indicators/engines/mpc_jarvis.pine` line 852 (`vwapValue = ta.vwap(hlc3)`).
Parity export build: `indicators/engines/vwap_export.pine`.

---

## Public API

```python
from vwap import VwapEngine

vw = VwapEngine()  # Pine defaults: hlc3, volume-weighted, 18:00-NY trading-day anchor

# Each closed bar (timestamp is epoch MILLISECONDS, UTC — exactly Pine's `time`):
ev = vw.update(bar.index, bar.timestamp_ms, bar.high, bar.low, bar.close, bar.volume)

ev.value  # session VWAP price this bar (None until first volume) — Pine-validated
ev.anchored  # did the session reset (new trading day) on this bar? (edge)
ev.side  # +1 close above VWAP, -1 below, 0 on it
ev.crossed_up  # DERIVED: close crossed up through VWAP this bar (edge)
ev.crossed_down  # DERIVED: close crossed down through VWAP this bar (edge)
vw.value()  # current VWAP (read)
```

`htf_timezone` and `htf_rollover_hours` are the two constructor knobs.

---

## Relationship to the other engines

- **Standalone / time-driven**, like `engines/sessions/` and `engines/liquidity/` — it needs the
  bar's UTC timestamp (for the trading-day anchor) plus high/low/close **and volume**. It does not
  depend on `engines/market_structure/`.
- The roadmap lists it downstream of `engines/sessions/` for "the session anchor"; in practice the
  Pine `ta.vwap` anchor is the **trading-day** boundary (the same one the liquidity daily level
  uses), not the Asia/London/NY session windows, so this engine reconstructs that boundary directly
  rather than composing the sessions engine. Keep the anchor a trading-day roll.
- Downstream of nothing. A bot consuming it will get an `algos/shared/` shim (none built yet).

---

## Do

- Port any change to `mpc_jarvis.pine`'s VWAP line back here. Keep the source `hlc3`, the
  volume weighting, and the trading-day anchor exact.
- Keep the anchor calibration in step with `engines/liquidity/`'s daily boundary — both cut the
  trading day on the same instrument session; if one is recalibrated, check the other.
- When adding a field, update this file's Public API and the tests in the same commit.

## Never do

- Do not bake in a drawn line, colours or fill — this layer emits a value + events.
- Do not silently promote the derived cross fields into "Pine-validated" — the source has no cross.
- Do not build a second VWAP implementation elsewhere. This is the canonical one.
- Do not let this engine or the VWAP line in `mpc_jarvis.pine` drift; re-run the parity check
  after any change to either.

---

## Validation (Pine ↔ Python parity)

**Unit tests — GREEN:** `python3 -m pytest engines/vwap/tests/ -q` (13 hand-traced tests pinning the
volume-weighted running mean, the trading-day re-anchor + reset, the na/zero-volume guard, and the
derived close-vs-line cross).

**Full Pine↔Python parity — GREEN (2026-07-05).** 100% match on a real `VANTAGE_XAUUSD, 5m` export
(6,973 bars): both fields — the VWAP value and the trading-day anchor pulse — matched on every warm
bar (`--htf-rollover 18 --warmup 90`, exit 0). The 90-bar warm-up is the export's first (partial)
session: it opens Fri 13:30 UTC mid-way through Friday's trading day, so Pine's `ta.vwap` already
holds Friday's pre-window volume while Python starts cold; both re-anchor cleanly at the first
in-window trading-day open (Sun 31 May 18:00 NY = bar 90) and match from there. The harness mirrors
the other engines:

1. `indicators/engines/vwap_export.pine` — `ta.vwap(hlc3)` plus `px_volume`, `px_vwap`, and the
   `px_vwap_anchor` trading-day roll pulse. Put it on the same `VANTAGE_XAUUSD` chart/timeframe (5m),
   Export chart data → CSV, drop it in `engines/vwap/exports/` (git-ignored).
2. `python3 engines/vwap/tools/compare_vwap.py <that.csv> --warmup 90` — feeds each bar (timestamp +
   high/low/close + volume) through `VwapEngine` and diffs `px_vwap` + `px_vwap_anchor`, bar by bar.
   Exit 0 = parity. Standard library only. If `px_vwap_anchor` mismatches, sweep `--htf-rollover`
   (and/or `--htf-tz`) until it matches; the VWAP value follows.

**Tolerance note (why VWAP differs from the frozen-level engines):** the VWAP is a *cumulative*
volume-weighted sum over a whole session (thousands of bars by late day), so Python's float64 and
Pine's own accumulation drift apart at the float-rounding level (~1 part per million: ~1e-4 on a
~4000 gold price, 100x under a 1-cent tick). The parity check therefore uses a **relative** tolerance
(1e-6), not the exact-price match the copied-value level engines (liquidity, sessions) can use. This
is expected and correct — the structural match is 100%.

Re-run `compare_vwap.py` after any change to the VWAP line in `mpc_jarvis.pine` or here.

## References

- Pine source of truth: `indicators/engines/mpc_jarvis.pine` line 852.
- Parity export build: `indicators/engines/vwap_export.pine`.
- Anchor twin (same trading-day boundary): `engines/liquidity/CLAUDE.md`.
- Sibling engines / the shared porting pattern: `engines/sessions/CLAUDE.md`,
  `engines/order_blocks/CLAUDE.md`.
- Roadmap: `docs/ENGINE_EXTRACTION_ROADMAP.md` (VWAP was the #1 remaining engine).
- Monorepo context: `../CLAUDE.md`.
