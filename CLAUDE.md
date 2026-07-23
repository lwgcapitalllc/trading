## Communication Rules — Non-Negotiable

- Plain English only. Short sentences.
- Never use bullet points to explain a simple thing.
- No preamble. No "Great question." No "Sure, I can help with that."
- Spawn subagents for routine tasks. Work sequentially unless the task explicitly requires parallel execution.


# CLAUDE.md — LWG Capital Monorepo

**Purpose:** Standing instructions for Claude Code across all subsystems.
**Scope:** This covers repo-wide rules, VPS workflow, and branch conventions. It does NOT cover subsystem internals — each subsystem has its own CLAUDE.md.
**Status:** Active — four apps, ten canonical engines, and tooling in various stages of production.
**Last reviewed:** 2026-07-12

---

## Repo Structure

See `README.md` for the full repo map and subsystem list.

`algos/`, `smart-money/`, and `command-center/` are fully independent from each other. Engines under `engines/` are canonical shared libraries, and their dependency map is: `market_structure/` is the base; `fibonacci/` and `order_blocks/` are siblings downstream of it (each consumes its public `StructureSnapshot` only, never its internals and never each other); `sessions/` is standalone and time-driven; `liquidity/` and `session_volume_profile/` compose `sessions/`; `vwap/` and `news/` are standalone and time-driven; `vwap/` and `session_volume_profile/` are the two engines that need the bar's **volume**; `fair_value_gaps/` is standalone and OHLC-driven (no upstream engine, no volume, no timestamp — pure price-pattern detection); `rsi_divergence/` is likewise standalone (needs close for Wilder's RSI + the bar's high/low for the price anchor — no upstream engine, no volume, no timestamp); `equal_highs_lows/` is likewise standalone (needs high/low/close for ATR(50) + strict price pivots — no upstream engine, no volume, no timestamp). `engines/regime/` and `engines/market_structure/` are imported by `algos/` via thin shims in `algos/shared/`; `engines/regime/` and `engines/news/` are also imported by `command-center/` directly. Every other engine gets its `algos/shared/` shim when a bot first uses it. `strategies/` is consumed by `command-center/` (scanner + deploy) and deployed to the VPS strategy folders. Per-engine detail lives in each engine's CLAUDE.md — do not restate it here.

---

## System Summaries

### algos/
Automated trading on PU Prime demo accounts (Windows VPS via Task Scheduler). No live bots currently — the four first-attempt bots (SMC Trend, Scalper, FFT, Mean Reversion) were deleted 2026-06-22 to rebuild the suite backtest-first per `docs/BOT_DEVELOPMENT_METHOD.md`. Deployment learnings (MT5 connection, configs, scheduler, liveness layer) are preserved in `algos/docs/BOT_DEPLOYMENT_INFRA.md`. Full rules in `algos/CLAUDE.md`.

### smart-money/
Scans and profiles consistent crypto/forex traders for copy trading candidate pool construction. Runs locally on Mac. Stages 1–2 and 5 live; Stages 3–4 need API keys. Full rules in `smart-money/CLAUDE.md`.

### command-center/
React + FastAPI local operations platform. Monitors bots via SSH, surfaces Smart Money pipeline output, runs and evaluates NinjaTrader, MT5, and local Python backtests. Full rules in `command-center/CLAUDE.md`.

### backtest/
Top-level Python backtest runner — strategy- and instrument-agnostic shared infrastructure (same character as `engines/`): broker-data layer with disk cache, bar-replay loop over the canonical engines, tick-level fill & cost model, lab output adapter, and a local multi-core optimizer. Consumed by `strategies/python/` bots and by the command-center lab as `runner="python"`. **Deliverable A complete 2026-07-16.** Full rules in `backtest/CLAUDE.md`.

### engines/regime/
Shared market regime classifier. Imported by the live bots (via `algos/shared/shared_regime.py` thin shim) and by the command-center backtest lab. Single output set: 5 labels (TRENDING, TRANSITIONING, RANGING, HIGH_VOLATILITY, LOW_VOLATILITY). Each bot owns its own `REGIME_RISK_TABLE` mapping labels to trade decisions. Full rules in `engines/regime/CLAUDE.md`. Algorithm documented in `engines/regime/REGIME_CLASSIFIER.md`.

### engines/market_structure/
Canonical market-structure detection engine (BOS/CHoCH, swing highs/lows, HH/HL/LH/LL, internal structure). A stateful streaming state machine ported line-by-line from `indicators/structure_engine.pine`. **Re-synced 2026-07-12 to the `choch_lock` removal in `mpc_assistant.pine`** (a CHoCH no longer needs the anti-whipsaw latch; on an SOS the promoted extreme prints ASH/ASL and is NOT written to the confirmed-swing map — this is the fix for the missing higher high) and re-validated at 100% Pine parity on a real `VANTAGE_XAUUSD, 5m` export. Note the public label domain widened: `broken_high_label`/`broken_low_label` now also carry `"ASH"`/`"ASL"` = *not yet classified*. Imported by the live bots via `algos/shared/structure_engine.py` (thin shim); the command-center backtest lab is a future consumer. This is the single implementation — do not build another anywhere. Full rules in `engines/market_structure/CLAUDE.md`; algorithm in `engines/market_structure/MARKET_STRUCTURE_ENGINE.md`.

### engines/fibonacci/
Canonical fib engine. Turns `engines/market_structure/` output (public `StructureSnapshot` only) into fib LEVEL EVENTS — the first-touch of each level (E1–E4 entries, TP1–TP3 targets, 1.0) — via four fib state machines (Structure "FFT", Sniper, Macro, Internal) ported from `indicators/mpc_assistant.pine`. Unit-tested (40 tests), 100% Pine parity re-confirmed after the 2026-07-12 structure re-sync (the fibs were STALE-BY-INPUT — own code untouched, but the structure stream feeding them changed; fresh 5m export, exit 0). Full rules in `engines/fibonacci/CLAUDE.md`.

### engines/order_blocks/
Canonical order-block engine. Turns `engines/market_structure/` output into order-block EVENTS — a supply/demand zone per structure break, its mitigation (close through the far edge), and FIFO eviction past `maxActiveOB` per direction (**default synced 6→2 on 2026-07-14** to the mpc paste); a SIBLING of `engines/fibonacci/`, consuming the structure engine's public output only. Ported from `mpc_assistant.pine`, unit-tested (12 hand-traced tests), 100% Pine parity re-confirmed on a fresh 2026-07-14 combined 5m export at the new cap-2 default (exit 0). Full rules in `engines/order_blocks/CLAUDE.md`.

### engines/sessions/
Canonical sessions engine — the first **time-driven** engine (input = the bar's UTC timestamp + high/low). Emits session EVENTS — Tokyo/London/NY windows + running session high/low, the three DST-aware NY kill zones, the NY opening range, new-day/weekday flags — standalone, and the base the liquidity and SVP engines compose. Ported from `mpc_assistant.pine`, unit-tested (17 hand-traced tests), 100% Pine parity on a real `VANTAGE_XAUUSD, 5m` export. Full rules in `engines/sessions/CLAUDE.md`.

### engines/liquidity/
Canonical liquidity-levels engine. Turns the bar stream into liquidity LEVEL EVENTS — prev day/week high & low, prev week close, the H4 sweep high/low, and Asia/London/NY session high & low, each with sweep/break mitigation; composes `engines/sessions/` for the session levels. **Non-repainting by Aaron's explicit decision (2026-07-05): every HTF level uses the PREVIOUS completed period only — never the current period's forecast.** Unit-tested (14 hand-traced tests), 100% Pine parity re-confirmed after the 2026-07-09 monthly-level (PMH/PML) removal (fresh 5m export, exit 0). XAUUSD trading day opens 18:00 NY (baked-in default). Full rules in `engines/liquidity/CLAUDE.md`.

### engines/vwap/
Canonical session-VWAP engine — a volume-weighted running mean of `hlc3` re-anchored each trading day (the same 18:00-NY boundary as the liquidity daily level), plus a derived close-vs-line cross. The first engine to need a **volume** column in the feed. Unit-tested (13 hand-traced tests), 100% Pine parity on a real `VANTAGE_XAUUSD, 5m` export (relative 1e-6 tolerance — the cumulative sum drifts at float-rounding level). Full rules in `engines/vwap/CLAUDE.md`.

### engines/session_volume_profile/
Canonical Session Volume Profile engine — the Asia point-of-control ("MV" line): on each Asia session close it builds a 100-row volume profile over the session range, reports the highest-volume row's mid-price as the POC, and marks it confirmed when price first straddles it. Composes `engines/sessions/`; needs the **volume** feed. Unit-tested (12 hand-traced tests), 100% Pine parity on a real `VANTAGE_XAUUSD, 5m` export. The **last of the roadmap's eight planned SMC-port engines — the core extraction roadmap is complete** (the fair-value-gap engine below was pulled later, for the A+ setup). Full rules in `engines/session_volume_profile/CLAUDE.md`.

### engines/fair_value_gaps/
Canonical fair-value-gap engine — turns the bar stream into FVG EVENTS: a price void left by a 3-candle imbalance (the LuxAlgo definition — the two outer candles don't overlap, the middle bar's close cleared the gap, and the gap is ≥ 0.1% of price), plus its later mitigation (a candle CLOSING fully past the far edge — a wick no longer counts) and FIFO eviction past `fvgMaxCount` (default 6). Standalone and OHLC-driven — no upstream engine, no volume (the Pine's directional-visibility filter is drawing-only and is deliberately not reproduced; every gap is emitted with its `is_bullish` flag and a consumer decides alignment). Ported line-by-line from `mpc_assistant.pine`'s FVG block, unit-tested (15 hand-traced tests). **Re-synced 2026-07-18** to the mpc default drift: the middle-bar close-cleared check is now the OPTIONAL `require_close` flag (Pine `fvgRequireClose`, default False — the classic FVG that the mpc default produces; the engine had silently required it since the gate landed in mpc on 2026-07-17), and the defaults were reconciled to the Pine (`max_count` 6→10, `threshold_pct` 0.1→0.0). `fvg_export.pine` now carries `cfg_fvg_*` columns and `compare_fvg.py` configures the engine from them, so parity survives any input tweak. **Pine-parity RE-VALIDATED 2026-07-19 (exit 0)** on a fresh 16,639-bar `VANTAGE_XAUUSD, 5m` grand export at the reconciled defaults. Pulled off the indicator later than the eight planned engines, to feed the A+ setup. Full rules in `engines/fair_value_gaps/CLAUDE.md`.

### engines/rsi_divergence/
Canonical RSI-divergence engine — turns the bar stream into RSI-DIVERGENCE EVENTS: a confirmed regular divergence at the extremes (price lower-low while Wilder's RSI higher-low from oversold = bullish; the overbought mirror = bearish), plus the live confluence flags (`bull_active`/`bear_active`) a consumer reads. Standalone and price-driven (close for RSI + the bar's high/low for the anchor — no upstream engine, no volume, no timestamp); a sibling of `fair_value_gaps/` in shape. Pivots confirm `pivot_len` bars late (non-repainting by design). Pulled off the indicator later than the eight planned engines (like FVG), to feed the A+ setup. Ported line-by-line from `mpc_assistant.pine`'s RSI DIVERGENCE block, unit-tested (9 hand-traced + reference-cross-check tests), **100% Pine parity** on a real `VANTAGE_XAUUSD, 5m` export (`compare_rsi_div.py --warmup 1630`, exit 0). Full rules in `engines/rsi_divergence/CLAUDE.md`.

### engines/equal_highs_lows/
Canonical Equal Highs/Lows (EQH/EQL) engine — turns the bar stream into EQH/EQL LEVEL EVENTS: when two consecutive same-side strict price pivots land within an ATR(50)×mult band of each other, a horizontal liquidity level prints (EQH = buy-side resting above, EQL = sell-side below) and lives until a candle CLOSES through it; FIFO cap per side (default 6). Standalone and price-driven (high/low/close — no upstream engine, no volume, no timestamp); a sibling of `fair_value_gaps/` and `rsi_divergence/` in shape. Ported line-by-line from `mpc_assistant.pine`'s EQ block, unit-tested (7 tests). **Pine-parity VALIDATED 2026-07-19 (exit 0)** on a fresh 16,639-bar `VANTAGE_XAUUSD, 5m` grand export. The real-export run exposed and FIXED a genuine pivot bug: Pine's `ta.pivothigh`/`pivotlow` allow a tie on the LEFT of the centre but require a STRICT extreme on the RIGHT (the last bar of an equal run is the pivot); the engine had used strict-both-sides, which silently dropped the frequent raw-price ties on gold. The identical latent bug was fixed in `rsi_divergence/` too (there ties on RSI values are rare, so it only surfaced as a couple of diagnostic-column misses). The Pine's `eqExemptFvg` coupling (a gap behind an EQ level survives the FVG cap) is now MODELLED (2026-07-18, Aaron's exact-match call): the FVG engine's `update()` takes `eq_levels`/`eq_tol` and the consumer runs EQ→FVG (`backtest/replay/EngineStack` wiring is a follow-up). Full rules in `engines/equal_highs_lows/CLAUDE.md`.

### engines/news/
Canonical economic-calendar (news) engine — **off the extraction roadmap and NOT a Pine port**. Standalone and time-driven: turns each bar's UTC timestamp into trade-BLACKOUT events around scheduled macro releases plus bank-holiday reporting; the engine reports, the bot decides via its own `NewsPolicy`. **Honest-coverage by Aaron's decision (2026-07-05): the filter is inert before the cache's earliest fetched date; `coverage_start_ms` marks the boundary.** Validated by 29 unit tests + live checks (no Pine source to diff). Full rules in `engines/news/CLAUDE.md`.

### strategies/
Generic trading strategy source files, organized by runner platform. `strategies/ninjatrader/` holds the only live NinjaScript strategy, `ORB.cs` (VWAP_MR and Momentum were deleted 2026-06-21 — they baked risk management into the strategy, against the gated-layer rules). The command center scanner reads from here to register strategies in the database; the Deploy button uploads files to the VPS (NT8 or MT5 folder by extension). `strategies/mt5/` holds one MQL5 strategy: `LondonBreakout.mq5` (instrument-agnostic Asian-range → London breakout). `strategies/python/` holds Python strategy packages run locally by the lab's python runner (no deploy) — currently `mpc_sos_fade/`, the MPC SOS Fade bot, Pine-logic-parity green. Full rules in `strategies/CLAUDE.md`.

### scripts/
Cross-subsystem VPS bootstrap and full-recovery scripts (`bootstrap_vps.ps1` for the MT5/algos side, `bootstrap_ninjatrader.ps1` for the NT8 side). Idempotent, run on a wiped or new VPS. Full run order in `scripts/README.md`.

### indicators/
From-scratch Pine Script rewrite of the "Structure OS / SMC Engine" market-structure indicator (`indicators/smc_engine_v2.pine`), replicating a private TradingView indicator using a pullback-only (no pivot lookback) swing detection method. Mid-rebuild: swing detection and break-gated BOS/CHoCH (Stage 2b) are ~95% validated against the original; internal structure (Stage 3) and full multi-symbol comparison (Stage 4) are not started. Full rules in `indicators/CLAUDE.md`.

---

## VPS Deploy Workflow

```bash
# Push changes
git add . && git commit -m "..." && git push

# Pull on VPS and restart bots
ssh forexvps "cd C:\trading && git pull origin main"
ssh forexvps "del C:\trading\algos\mt5_connect.lock 2>nul && taskkill /f /im python.exe"
sleep 3
ssh forexvps "schtasks /run /tn SYS_STARTUP"
sleep 60
ssh forexvps "wmic process where \"name='python.exe'\" get commandline 2>nul"
```

VPS path: `C:\trading\algos\` (main)

---

## Branches

- `main` — active development, all code changes go here

---

## Never Do

- Commit `credentials.json`, `users.json`, `.env`, any `.pkl` model files, or API tokens/keys
- Touch `algos/` when working on `smart-money/` or `command-center/` and vice versa
- Build a second regime classifier in `command-center/` or anywhere else — `engines/regime/classifier.py` is the canonical implementation; all consumers import from there
- Build a second structure engine, fib engine, order-block engine, sessions engine, liquidity engine, VWAP engine, SVP engine, fair-value-gap engine, RSI-divergence engine, equal-highs-lows engine, or news/economic-calendar engine anywhere — `engines/market_structure/engine.py`, `engines/fibonacci/`, `engines/order_blocks/`, `engines/sessions/`, `engines/liquidity/`, `engines/vwap/`, `engines/session_volume_profile/`, `engines/fair_value_gaps/`, `engines/rsi_divergence/`, `engines/equal_highs_lows/` and `engines/news/` are the canonical implementations; all consumers import from them
- Commit `engines/news/data/events.json` (or anything under `engines/news/data/`) — it is fetched calendar data, git-ignored, not source
- Commit a new or changed engine before its Pine↔Python parity check has actually run and passed (exit 0) on a real TradingView CSV export — unit tests pin the logic but do not prove parity. Build engine + tests + harness, then wait for the real export and the `compare_*.py` pass; only then commit (Aaron's standing rule, 2026-07-05)
