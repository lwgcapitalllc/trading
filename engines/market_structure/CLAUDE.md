# CLAUDE.md — Market Structure Engine Subsystem

**Purpose:** Canonical market-structure (BOS/CHoCH/swing) detection engine shared by live algo
bots, for use in entries, take-profits, and stop losses.
**Scope:** Structure detection logic only. No trading decisions, no MT5 operations, no UI, no
chart rendering.
**Status:** Production — ported, unit-tested, and Pine-parity-validated (100% on the
`OANDA_XAUUSD, 15m` export, 21,729 bars); wired into `algos/` via
`algos/shared/structure_engine.py` (shim).
**Pine:** ported from `indicators/structure_engine.pine`; parity harness is `indicators/structure_engine_export.pine`, diffed against this Python by `tools/compare_tradingview.py`. Pine stays in `indicators/` (shared source, TradingView-only toolchain); the CSV + compare tool are the engine's half.
**Last reviewed:** 2026-07-02

---

## Key paths

```
engines/market_structure/
├── engine.py                      ← StructureEngine (the state machine)
├── types.py                       ← Bar, SwingLevel, ExternalEvents, InternalEvents, StructureEvents
├── __init__.py                    ← re-exports the public API
├── CLAUDE.md                      ← this file
├── MARKET_STRUCTURE_ENGINE.md     ← plain-English algorithm doc
└── tests/
    └── test_engine.py             ← hand-traced synthetic-sequence tests
```

---

## Public API

```python
from market_structure import StructureEngine, Bar

eng = StructureEngine(major_length=15)   # 15 is the validated default; do not change casually

# Feed one closed candle at a time, in order:
events = eng.update(Bar(index=i, open=o, high=h, low=l, close=c))
# events.external -> ExternalEvents (bull_bos, bear_bos, bull_sos, bear_sos, new_swing_high/low,
#                    unconfirmed_high/low, broken_high/low_label,
#                    bull/bear_bos_high/low + _h_loc/_l_loc [break-leg endpoints, break bar only], ...)
# events.internal -> InternalEvents (bull_bos, bear_bos, bull_sos, bear_sos, new_swing_high/low,
#                    demoted_high/low_label,
#                    int_bull_break/int_bear_break + int_break_origin_loc [OB-creation gate, see below], ...)
# Every label the Pine source draws has a matching event field carrying its *_price and *_index.
# See the "Label -> event field" table in MARKET_STRUCTURE_ENGINE.md for the full mapping.

# Or replay a full history for backtesting (accepts Bar objects, dicts, or a pandas DataFrame):
all_events = eng.replay(bars)

# Current-state reads:
eng.dir                    # 1 bullish, -1 bearish, 0 undetermined
eng.active_swing_high      # SwingLevel | None
eng.active_swing_low
eng.last_confirmed_high
eng.last_confirmed_low
eng.internal_mode          # 1 tracking up, -1 tracking down, 0 watching
eng.internal_swing
```

---

## Why this is a stateful class, not a stateless function (deviation from `engines/regime/`)

`engines/regime/` is the sibling shared-library pattern in this repo: stateless `df -> label` functions,
recomputed fresh on every call from a dataframe slice. This module intentionally does **not**
follow that pattern, and the reason is structural, not stylistic:

Swing/BOS/CHoCH structure is inherently a streaming state machine. The active swing, the pullback
qualifying-candle counters, the trend direction, the CHoCH lock — all of it carries forward
bar-to-bar and cannot be correctly recomputed from a single bar or a short window in isolation.
Recomputing it from scratch on every call would mean replaying up to ~2000 bars of Python-level
branching per call (the Pine indicator's own `max_bars_back`), which fights directly against the
"near real-time, speed is part of the trading edge" requirement this engine exists to serve —
see `algos/CLAUDE.md`'s latency-awareness rule. A `StructureEngine` instance is built once per
symbol/timeframe, fed one bar per `update()` call as candles close, and carries its state forward
indefinitely at O(1) amortized cost per bar (aside from the bounded backward scans described in
`MARKET_STRUCTURE_ENGINE.md`, which are capped, not unbounded rescans of full history).

Do not "fix" this into a stateless function to match `engines/regime/`'s shape. The two subsystems solve
different problems: regime classification is a snapshot judgment over a rolling window; structure
tracking is inherently sequential.

---

## Pivot lag caveat (brief — full explanation in MARKET_STRUCTURE_ENGINE.md)

New external swing *candidates* are only confirmed `major_length` (15, by default) bars after the
fact — this mirrors Pine's `ta.pivothigh`/`ta.pivotlow` window and is preserved deliberately, not
a bug. **BOS/CHoCH break events themselves are same-bar/real-time** — the lag only affects how
quickly a brand-new swing candidate gets identified, not how fast a break against an
already-known level fires. Internal structure has no pivot lag at all. See
`MARKET_STRUCTURE_ENGINE.md` for the full explanation.

---

## Consumers

| Consumer | Path | Status |
|---|---|---|
| Live/algos bots | `algos/shared/structure_engine.py` (thin shim over `market_structure.StructureEngine`) | Wired |
| `engines/fibonacci/` | reads the public `ExternalEvents` + read properties via its own `StructureSnapshot` | Wired |
| `engines/order_blocks/` | reads the public `ExternalEvents` + `InternalEvents` via its own `StructureSnapshot` | Wired |
| Command-center backtest lab | `command-center/backend/services/` | Not yet wired — future consumer, not touched by this port |

**`InternalEvents` OB-creation gate (`int_bull_break` / `int_bear_break` / `int_break_origin_loc`).**
These three fields were added for `engines/order_blocks/`. They are a purely additive, capture-only exposure
of state the engine already computes — they mirror Pine's `int_bull_break` / `int_bear_break` /
`int_break_origin_loc` and are set at the six internal-break sites (iBOS bull/bear use
`tracked_ext_loc` as the origin; the four iSOS branches use `sw_loc`), right where the existing
`bull_bos` / `bear_sos` / `*_price` fields are set, before the state reset. No structure logic
changed and structure parity was re-confirmed unbroken. `engines/order_blocks/` scans back from
`int_break_origin_loc` to drop an OB on the internal break; the external OB path reads the existing
`bull_bos_l_loc` / `bear_bos_h_loc`.

---

## Do

- Port changes to `indicators/structure_engine.pine` back into `engine.py` line-by-line if that
  Pine source is ever updated post-validation. Do not let the two drift.
- Keep `update()`'s hot path free of pandas/numpy — see "Never do" below.
- When adding a new event or read property, update `MARKET_STRUCTURE_ENGINE.md` and this file's
  Public API section in the same commit.
- If you find what looks like a bug or inconsistency in the ported Pine logic, leave a `# NOTE:`
  comment in `engine.py` flagging it rather than silently correcting it. Several already exist —
  see the internal iHH/iLH labeling note and the CHoCH-branch asymmetry note in `engine.py`.

## Never do

- Do not add a pandas/numpy hard dependency to `engine.py`'s `update()` hot path. `replay()` may
  import pandas lazily (optional, DataFrame convenience only) — mirror the try/except pattern
  already used there.
- Do not simplify, "clean up", or optimize away any branch of the ported state machine (pullback
  qualifying-candle logic, choch_lock, bounded rescans, etc.) without Aaron's explicit sign-off —
  this is validated against a real chart at ~99.99% parity and any behavioral change breaks that.
- Do not build a second structure engine anywhere else in the repo. This is the canonical
  implementation; all consumers import from here.
- Do not change `major_length` from 15 in production consumers without discussing — it is the
  validated constant from the source Pine indicator.

---

## Validation (Pine ↔ Python parity)

Before trusting the engine on live money, confirm it matches the Pine source on real candles:

1. `indicators/structure_engine_export.pine` — an instrumented copy of `structure_engine.pine`
   (logic byte-identical; adds `plot()` columns for every engine output). Put it on a chart in
   TradingView and export the chart data to CSV.
2. `engines/market_structure/tools/compare_tradingview.py <that.csv>` — feeds the CSV's candles through
   `StructureEngine` and diffs its output against the Pine columns in the same file, bar by bar.
   Exit 0 = full parity; exit 1 = prints every mismatch. Pass `--major-length` to match the Pine
   build. Uses only the standard library.

The CSV carries both the candles (fed to Python) and the Pine outputs (compared against), so
there is no data-source mismatch to muddy the result.

**Result (2026-07-02):** full parity — every field matched on all 21,729 bars of the
`OANDA_XAUUSD, 15m` export (exit 0). The run closed one porting gap: the port had raised external
`new_swing_high`/`new_swing_low` on the mid-pullback break-promotion path, which the Pine source
never does (Pine sets those flags only in the 3-candle pullback-confirm block). That false signal
seeded the internal engine early and drifted `internal_mode` for ~22 bars. Fixed in
`_on_ash_broken`/`_on_asl_broken`. Re-run this tool after any `engine.py` change to keep it at 100%.

**Second gap (2026-07-02, post-validation):** the eight break-leg fields (`bull_bos_high`,
`bull_bos_h_loc`, `bull_bos_low`, `bull_bos_l_loc` + bear mirror) existed in
`structure_engine.pine` but were never ported — they carry the full impulse leg of a BOS (both
endpoints), which the Sniper-fib anchor needs. Added to `engine.py`/`types.py` and to the export +
compare tool (`px_bull_bos_high` / `px_bull_bos_h_ago` columns; `_loc` exported as "bars ago" to
survive the Pine absolute-index vs Python 0-based-index offset). The new columns are **optional** in
`compare_tradingview.py`, so old CSVs still validate every other field. **Parity confirmed
2026-07-02** on a fresh `VANTAGE_XAUUSD, 15m` export (9,721 bars): every field — the eight new
break-leg fields included — matches on all 9,494 warm bars (`--warmup 227`, exit 0). The first 227
bars mismatch only because the Pine export begins at a non-zero `bar_index` (TradingView had chart
history before the export window, so its engine was already warm while the Python engine starts
cold); both converge once the structure re-establishes inside the window. This is a second,
independent dataset from the original OANDA validation, so it re-confirms the whole engine too.

## References

- Algorithm explained in plain English: `MARKET_STRUCTURE_ENGINE.md`
- Pine source of truth: `indicators/structure_engine.pine` (validated ~99.99% parity against the
  original "Structure OS" TradingView indicator via `indicators/mpc_assistant.pine`)
- Shim and bot integration: `algos/shared/structure_engine.py`
- Sibling shared-library pattern (stateless, for contrast): `engines/regime/CLAUDE.md`
- Monorepo context: `../CLAUDE.md`
