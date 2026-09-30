# CLAUDE.md — directional_trend

**Purpose:** the JARVIS panel's five direction rows — BIAS W, BIAS D, STR 4H, STR 15m, STR 1m — as a
streaming engine any bot can read.
**Scope:** this engine only. The structure logic itself belongs to `engines/market_structure/`.
**Status:** ✅ **GATED 2026-09-30** on real VANTAGE:XAUUSD exports (see *Parity gate*). No bot reads it
yet — wiring one in is a strategy change with its own backtest.

## Rules

- **No second implementation.** The STR rows ARE `market_structure.StructureEngine`, one per
  timeframe. Jarvis's `processMTF` is the external half of its chart engine byte for byte (diffed
  2026-09-29). The day / week / 4H boundaries are the liquidity engine's validated period keys,
  imported, never retyped.
- **Non-repainting, on purpose — the liquidity-engine decision (Aaron, 2026-07-05).** A
  higher-timeframe row reads the last CLOSED candle only, published on the first bar of the next
  period. Jarvis's live panel shows the developing candle; a bot must not trade that. The export
  mirrors the deviation, so the gate checks what a bot actually reads.
- **None means cannot know.** Warm-up, and a timeframe finer than the fed bars (the 1m row on a 15m
  feed), return None — never Neutral. The first period seen is thrown away as partial, so the weekly
  row needs three weeks of history.
- **Feed ONE timeframe: 1, 3, 5 or 15 minutes.** Rows at or above it are built here. For the 1m row,
  feed 1m bars.
- ⚠ **Cost of non-repainting:** a higher-timeframe row lands one fed bar after its candle closes.

## Consumers

None yet. Candidates once gated: SOS Fade, B-LEG and BOS carry a weekly/daily bias setting whose
input was NEVER filled in Python (it always reads empty). The extreme leg and Realign each build
their own 15m structure in a local `htf.py`; both could move onto this engine.

## Parity gate

- Export script: `indicators/engines/directional_trend_export.pine` — copies Jarvis's bias rule and
  multi-timeframe structure block verbatim. `scripts/check_pine_blocks.py` holds both copies to Jarvis.
- Harness: `tools/compare_directional_trend.py <csv> [--warmup N]`. Fails if any field was compared
  on fewer than 200 bars.
- **MEASURED 2026-09-30 — 15m export** (golden, `exports/golden/`): all eight fields (W, D, 4H,
  15m, state + event) match on **18,283 of 18,283** bars, 2025-12-22 → 2026-09-30, at warm-up 3209.
  Every earlier mismatch is the 4H row warming up — TradingView's 4H series starts warm, Python cold.
- **MEASURED 2026-09-30 — 1m export** (by hand, not golden): the 1m row matches on **24,425 of
  24,425** bars from bar 0. On that file the 15m row settles after 4 days, and the 4H row needs almost
  the whole 3.5 weeks, so the file is too short to be a clean golden for the higher rows.
- Earlier cross-check: feeding the 5m structure export's candles
  (`market_structure/exports/VANTAGE_XAUUSD, 5_9c376.csv`) through this engine, the 15m row matched
  TradingView's own 15m direction (`15_c7722.csv`) on **2,491 of 2,491** bars after an 11-hour cold
  start, across 13 flips.

## Files

| File | What |
|---|---|
| `engine.py` | `DirectionalTrend`, `bias_state` |
| `types.py` | row types and codes |
| `tests/test_engine.py` | hand-traced mechanics; mutation-checked 2026-09-29 (4 mutants, all red) |
| `tools/compare_directional_trend.py` | the parity gate |
