# LondonBreakout.mq5 — design notes & v1 results

Reference doc for `strategies/mt5/LondonBreakout.mq5`. Standing rules for all strategies
live in `strategies/CLAUDE.md`; this file holds the design rationale and the v1 backtest
record, which are reference material, not standing instructions.

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
