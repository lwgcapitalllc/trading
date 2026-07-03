# CLAUDE.md — indicators/

**Purpose:** From-scratch Pine Script rebuild of the "Structure OS / SMC Engine" market-structure indicator (swing highs/lows, HH/HL/LH/LL, BOS, CHoCH), replicating a private TradingView indicator's behavior using a pullback-only detection method.
**Scope:** This covers Pine Script indicator development and the market-structure detection engine only. It does NOT cover trading strategy logic, risk management, or any live/backtest execution — this is a charting indicator, not a bot.
**Status:** Under construction — Stage 2b (break-gated swing structure + BOS/CHoCH) is ~95% validated against the original; Stage 3 (internal structure) and Stage 4 (multi-symbol/timeframe comparison) not started. Blocked on chart validation by Aaron before Stage 3 begins.
**Last reviewed:** 2026-06-20

---

## Key paths & entry points

- `indicators/smc_engine_v2.pine` — the current pullback-only rewrite (v6 Pine Script), overlay indicator named "SMC Engine"
- `indicators/STRUCTURE_OS_BUILD.md` — cross-session handoff doc: architecture, design decisions, validation findings, build-stage status. Read this first when resuming work.
- `docs/market_structure_engine_spec.md` — the source-of-truth rules spec, written from the TradingView overview page. `STRUCTURE_OS_BUILD.md` treats this as priority-1 source of truth.
- `indicators/mpc_assistant.pine` — a full-featured SMC indicator (structure + order blocks + sessions + kill zones + VWAP + liquidity levels + fibonacci + SVP) that Aaron sourced separately. Its market-structure logic is pivot-seeded (`ta.pivothigh`/`ta.pivotlow`) rather than pullback-only, which breaks the rule below — but it matches the original "Structure OS" indicator at ~99.99% parity. Treat it as read-only reference; don't merge its approach into `smc_engine_v2.pine`.
- `indicators/structure_engine.pine` — a straight extraction of *only* the market-structure logic (external ASH/ASL/BOS/CHoCH/HH/HL/LH/LL + internal iSH/iSL/iBOS/iSOS) from `mpc_assistant.pine`, with every other feature (OBs, sessions, kill zones, VWAP, liquidity, fibo, SVP) stripped out. Same pivot-seeded approach as `mpc_assistant.pine`, so same exception to the no-pivot rule below. Chart-validated by Aaron; now ported to Python as the canonical `market_structure/` subsystem (imported by `algos/` bots).
- `indicators/structure_engine_export.pine` — instrumented copy of `structure_engine.pine` (logic byte-for-byte identical; adds `plot()` output columns, including the eight break-leg columns `px_bull_bos_high/low` + `px_bull_bos_h_ago/l_ago` and bear mirror added 2026-07-02). Used only to export a CSV from TradingView for the Python↔Pine parity check in `market_structure/tools/compare_tradingview.py`. That check passes at 100% on the `OANDA_XAUUSD, 15m` export (21,729 bars, exit 0) and was re-confirmed on a fresh `VANTAGE_XAUUSD, 15m` export (9,721 bars, `--warmup 227`, exit 0) after the break-leg columns were added. Do not trade off it or let its logic drift from `structure_engine.pine`.

---

## Standing instructions

**Do**
- Confirm swings only by the 3-candle pullback method: a swing high needs 3 consecutive candles each closing below the previous candle's low; a swing low needs 3 consecutive candles each closing above the previous candle's high.
- Reset the pullback count to zero at a new extreme if price prints a new high (while seeking a high) or new low (while seeking a low) before the count reaches 3.
- Keep detection to a single fixed constant (3). No numeric tuning inputs for detection.
- Reuse the same shared pullback-tracker type (`type PB`) for both the swing (external) engine and the internal engine — instantiate it twice, don't fork the logic.
- Gate new swing structure on a body-close break of the current trading range (BOS/CHoCH), per the corrected Stage 2b architecture — do not let swings form freely inside the range.
- Update `STRUCTURE_OS_BUILD.md` status/changelog as each stage is validated on a real chart.

**Never do**
- Do not use `ta.pivothigh` / `ta.pivotlow` or any fixed-lookback-window pivot method to detect swings in `smc_engine_v2.pine` (the from-scratch rebuild). This does not apply to `mpc_assistant.pine` / `structure_engine.pine`, which are a separate, intentionally pivot-seeded track — see Key paths above.
- Do not add numeric/tunable inputs for the detection logic itself — it must stay a zero-parameter mechanical rule.
- Do not fork the shared `PB` pullback-tracker type into two separate code paths for swing vs. internal — if the two ever need to diverge, branch inside `PB` with a flag instead.
- Do not build or validate Stage 2/3 logic on top of an unvalidated swing map — the swing detector is the foundation; get it confirmed against the real chart first.
- Do not treat a wick-only touch of a range boundary as a break — only a candle body close beyond the boundary counts (BOS/CHoCH).

---

## Guides & references

- `indicators/STRUCTURE_OS_BUILD.md` — full build log: settings-panel parity, architecture (two engines/one shared type), design decisions, open questions, and per-stage validation status against the original TradingView indicator.
- `docs/market_structure_engine_spec.md` — plain-language spec of the detection rules (swing points, HH/HL/LH/LL, BOS/CHoCH, internal engine) derived from the TradingView indicator's public description.
