# LondonBreakout.mq5 — design notes & results

Reference doc for `strategies/mt5/LondonBreakout.mq5`. Standing rules for all strategies
live in `strategies/CLAUDE.md`; this file holds the design rationale and the backtest
record (v1 baseline + v2 spec-faithful), which are reference material, not standing
instructions.

## Design (v1)

Fully instrument-agnostic by construction — no symbol, no pip value, no per-pair
number in the source. Everything per-instrument is read from the broker
(`SymbolInfo`, points) or expressed as a multiple of the instrument's own daily
ATR, so the same file runs on AUDJPY, CADJPY, USDJPY, or XAUUSD with nothing
changed but the injected layers. The word "pip" never appears in the logic.

- **Layer A (tunable, no prefix):** GMT session windows (`AsianStartGMT`,
  `AsianEndGMT`, `LondonOpenGMT`, `EntryCutoffGMT`, `ForceFlatGMT`) plus the
  ATR-scaled knobs `AtrPeriod` (daily ATR), `RangeMinAtr`/`RangeMaxAtr` (range
  filter, default 0.5/1.3 — the pair-agnostic replacement for a fixed pip
  filter), `BufferAtr` (breakout buffer, default 0.1), and `TargetRR` (1:1).
- **Foundational (`f_` prefix, injected):** sizing + risk caps + costs from the
  active ruleset; sentinel `-1` defaults hard-fail at init if injection didn't
  happen.
- **Timezone is fully automatic — no knob.** Session windows are GMT; the
  broker→GMT offset is derived live from the broker (`TimeTradeServer()` −
  `TimeGMT()`, snapped to the minute) and recomputed on **every bar** by
  `BrokerToGmtSec()`, so a DST shift on either the broker side or the GMT side
  is tracked automatically. There is no manual offset param and no dependency on
  the machine's local clock — it follows whatever broker the EA runs on. (The
  earlier single-sample-at-init approach was replaced: caching one offset would
  miss a broker's seasonal DST shift.) On PU Prime the offset is constant across
  2008–2026, so this changed no results there; its value is correctness on any
  broker that does observe DST. The same broker-derived principle applies when
  porting session logic to NT8 (use the instrument's exchange time zone, never a
  hardcoded offset).
- **Both-sided-bar diagnostic:** independent of trading, counts M15 bars in the
  entry window whose high reached the buy level AND low reached the sell level —
  the case the bar model can't resolve. Written to
  `Common\Files\LondonBreakout_diag_<symbol>.csv` (FILE_COMMON) and printed in
  the journal; quantifies how much the bar model is silently guessing.

## v1 honest run

**AUDJPY.s, M15, 2008-01-01 → 2026-05-06 (full available history),
`personal_forex_demo` costs (commission 0; PU Prime forex is spread-only), real
spread:** net −$965.87, win rate 45.4%, 430 trades, PF 0.84, max DD ~$1,023,
Sharpe −2.83. Both-sided bars: **2 of 2,065 qualifying days (0.10%)** — the bar
model is essentially never guessing, so the negative edge is real, not an
artifact. No edge on AUDJPY at defaults; AUDJPY's Asian session is itself active
(AUD+JPY are Asian-hours currencies), which undercuts the "quiet Asian range →
London expansion" premise. Not yet registered in `lab.db` (run via the MT5 agent
directly; run **Scan Strategies** when the command center is next up to register
it).

## Design (v2 — spec-faithful toggles)

v1 deviated from the NexGenAlgo source (brief No. 146 + the creator's video) in
three ways, any of which could mask the edge: a 1:1 target with no stop
management, an ATR range band instead of the fixed pip filter, and bar-close
market entry instead of pending stop orders. v2 adds each deviation back as an
INDEPENDENT, default-OFF toggle, so the delta of one change can be measured one at
a time. With all three off and `TargetRR=1.0` the EA reproduces v1 byte-for-byte.

- **`PendingEntry`** (default false) — off = bar-close market entry with the ATR
  buffer; on = pending stop orders at the breakout levels, OCO (first fill cancels
  the other), both cancelled if neither fills by `EntryCutoffGMT`. The buffer
  becomes a fixed `BufferPips` (default 5) derived from the broker point size.
  `PipSize()` returns 10 points on 3/5-digit quotes, 1 otherwise — no hardcoded pip.
- **`PipRangeFilter`** (default false) — off = ATR band (`RangeMin/MaxAtr`); on =
  fixed pip band `[RangeMinPips, RangeMaxPips]` (default 15-40). Days inside
  `[SweetMinPips, SweetMaxPips]` (default 20-35) are tallied separately in the
  diagnostic CSV — logged only, never a gate.
- **`BreakEvenMove`** (default false) — off = fixed stop to SL/TP/force-flat; on =
  pull the stop to entry once price reaches +1R. Trailing is intentionally out of
  scope (a separate later test).
- **`TargetRR` default is now 2.0** (the source's 2:1), not 1.0. It is a free dial,
  not a toggle — to reproduce v1 set it back to 1.0.

The both-sided diagnostic also writes `sweet_spot_days`. Magic number is
`MAGIC_NUMBER` (20240003); pending fills are detected per tick by symbol+magic.

## v2 spec-faithful results (AUDJPY)

All runs M15, **2015-01-01 → 2026-05-06** (creator's window), `personal_forex_demo`
costs (2.25/side, 1 tick), $10k / 1% risk defaults. Exp R uses average realized
loss as R (same definition as the v1 baseline). Position sizes are small (avg loss
~$59 vs the $100 1% target — min-lot rounding on $10k), so the ratios (PF, payout,
exp R) are the trustworthy figures, not the dollar amounts.

**v1 baseline on this window (toggles off, RR=1.0, run `812653902b15`):** 258
trades, win 47.3%, PF 0.88, payout 0.98, −0.063 R, max DD $562, 1,307 qualifying
days. Reproduced byte-for-byte by the v2 build with toggles off (`46ebfbf8795b`).

**Additive ladder (each row adds one toggle):**

| Step | Config | Trades | Win% | PF | Payout | Exp R | Max DD |
|---|---|---|---|---|---|---|---|
| A | v1 (off, RR 1.0) | 258 | 47.3% | 0.88 | 0.98 | −0.063 | $562 |
| B | + RR 2.0 | 258 | 47.3% | 0.86 | 0.96 | −0.073 | $646 |
| C | + PipRangeFilter 15-40 | 334 | 42.5% | 0.69 | 0.94 | −0.177 | $2140 |
| D | + PendingEntry (OCO) | 434 | 46.3% | 0.92 | 1.07 | −0.041 | $1248 |
| E | + BreakEvenMove (full spec) | 434 | 47.0% | 0.93 | 1.08 | −0.036 | $1147 |

Pending entry was the high-impact toggle (payout crossed 1.0). At the 11:00
force-flat the full spec still lost (PF 0.93) — the 2:1 target can't pay out inside
a ~4-hour window.

**Force-flat sweep (config E, 15-40, RR 2.0):** PF climbs monotonically as the
flatten moves later — 11:00 → 0.93, 13:00 → 0.99, 15:00 → 1.04, 16:00 → 1.04. The
11:00 cut was strangling the 2:1. 16:00 is the better corner (payout 1.21, DD lower
than 15:00).

**TargetRR sweep (16:00 flatten, 15-40):** 1.5 → 0.98, 2.0 → 1.04, 2.5 → 1.04 — a
plateau at 2.0-2.5 with a drop below. The source's 2:1 sits in the centre; pick RR 2.0.

**Range-band sweep (16:00 flatten, RR 2.0) — plateau, not a spike:** every band is
profitable (PF 1.04-1.24); PF degrades smoothly as the band widens past the 20-35
core, with the high end (→40 pips) the bigger drag. The PF≥1.15 cluster (18-37,
20-35, 22-33) all centre at 27.5 pips; 20-35 is the centre band.

| Band | Trades | Win% | PF | Payout | Exp R | Max DD |
|---|---|---|---|---|---|---|
| 20-35 | 278 | 51.4% | 1.24 | 1.23 | +0.116 | $1109 |
| 22-33 | 220 | 51.8% | 1.21 | 1.19 | +0.101 | $1225 |
| 18-37 | 344 | 50.3% | 1.15 | 1.23 | +0.075 | $944 |
| 17-33 | 276 | 50.7% | 1.10 | 1.16 | +0.050 | $1027 |
| 20-40 | 391 | 48.1% | 1.06 | 1.22 | +0.032 | $1149 |
| 15-40 | 434 | 48.4% | 1.04 | 1.21 | +0.019 | $1165 |

**AUDJPY survivor — full spec-faithful, ForceFlat 16:00, RR 2.0, range 20-35**
(run `016fdf4175fc`): 278 trades, win 51.4%, PF 1.24, payout 1.23, +0.116 R/trade,
max DD $1,108. Not yet stress-tested. CADJPY, EURUSD, GBPUSD not yet run on the
spec-faithful ladder. The earlier v1 read that "the pip filter hurts AUDJPY" was
confounded by the 11:00 force-flat — with a later flatten the 20-35 band is the
best config tested.

## Known issue — MT5 compile path

The command-center "Compile MT5" button (agent `metaeditor64 /compile:<dir>`,
directory form) reported success but produced **no new `.ex5`** — the first
spec-faithful run batch silently executed the stale v1 binary, so the new toggles
appeared inert until caught. The single-file form (`metaeditor64 /compile:<file.mq5>`)
works. Until the agent's compile is fixed, verify the `.ex5` mtime on the VPS after
any MT5 deploy before trusting results.
