## Communication Rules — Non-Negotiable

- Plain English only. Short sentences.
- Never use bullet points to explain a simple thing.
- No preamble. No "Great question." No "Sure, I can help with that."
- Spawn subagents for routine tasks. Work sequentially unless the task explicitly requires parallel execution.


# CLAUDE.md — LWG Capital Monorepo

**Purpose:** Standing instructions for Claude Code across all subsystems.
**Scope:** This covers repo-wide rules, VPS workflow, and branch conventions. It does NOT cover subsystem internals — each subsystem has its own CLAUDE.md.
**Status:** Active — six subsystems in various stages of production.
**Last reviewed:** 2026-06-12

---

## Repo Structure

See `README.md` for the full repo map and subsystem list.

`algos/`, `smart-money/`, and `command-center/` are fully independent from each other. `engines/regime/` and `engines/market_structure/` are shared libraries imported by `algos/` (each via a thin shim in `algos/shared/`); `engines/regime/` is also imported by `command-center/` (directly). `engines/fibonacci/` is a shared library downstream of `engines/market_structure/` — it consumes that engine's public output (a `StructureSnapshot`) and will get an `algos/shared/` shim when a bot first uses it. `engines/order_blocks/` is a sibling of `engines/fibonacci/` — it also consumes `engines/market_structure/`'s public output directly (via its own decoupled `StructureSnapshot`, never fibonacci) and will likewise get an `algos/shared/` shim when a bot first uses it. `engines/sessions/` is a standalone, time-driven shared library (input = the bar's UTC timestamp, not `engines/market_structure/` output); it is the prerequisite for the session-scoped parts of the Liquidity engine (now built) and the still-to-build VWAP engine, and will get an `algos/shared/` shim when a bot first uses it. `engines/liquidity/` is another time-driven library that CONSUMES `engines/sessions/` (composes it) for its session high/low levels and reconstructs the day/week/month/H4 levels from the bar stream; it depends on nothing else and will get an `algos/shared/` shim when a bot first uses it. `engines/news/` is a standalone, time-driven library (input = the bar's UTC timestamp) that is **off-roadmap — NOT a `mpc_assistant.pine` port**: it turns an external economic-calendar feed (the free Forex Factory feed) into trade-BLACKOUT events so a bot can veto trading around scheduled macro news; it depends on nothing and will get an `algos/shared/` shim when a bot first uses it. `strategies/` is consumed by `command-center/` (scanner + deploy) and deployed to the VPS (NT8 strategy folder).

---

## System Summaries

### algos/
Automated trading on PU Prime demo accounts (Windows VPS via Task Scheduler). No live bots currently — the four first-attempt bots (SMC Trend, Scalper, FFT, Mean Reversion) were deleted 2026-06-22 to rebuild the suite backtest-first per `docs/BOT_DEVELOPMENT_METHOD.md`. Deployment learnings (MT5 connection, configs, scheduler, liveness layer) are preserved in `algos/docs/BOT_DEPLOYMENT_INFRA.md`. Full rules in `algos/CLAUDE.md`.

### smart-money/
Scans and profiles consistent crypto/forex traders for copy trading candidate pool construction. Runs locally on Mac. Stages 1–2 and 5 live; Stages 3–4 need API keys. Full rules in `smart-money/CLAUDE.md`.

### command-center/
React + FastAPI local operations platform. Monitors bots via SSH, surfaces Smart Money pipeline output, runs and evaluates NinjaTrader and MT5 backtests. Full rules in `command-center/CLAUDE.md`.

### engines/regime/
Shared market regime classifier. Imported by the live bots (via `algos/shared/shared_regime.py` thin shim) and by the command-center backtest lab. Single output set: 5 labels (TRENDING, TRANSITIONING, RANGING, HIGH_VOLATILITY, LOW_VOLATILITY). Each bot owns its own `REGIME_RISK_TABLE` mapping labels to trade decisions. Full rules in `engines/regime/CLAUDE.md`. Algorithm documented in `engines/regime/REGIME_CLASSIFIER.md`.

### engines/market_structure/
Canonical market-structure detection engine (BOS/CHoCH, swing highs/lows, HH/HL/LH/LL, internal structure). A stateful streaming state machine ported line-by-line from `indicators/structure_engine.pine` and validated at 100% Pine parity on a real XAUUSD 15m export. Imported by the live bots via `algos/shared/structure_engine.py` (thin shim); the command-center backtest lab is a future consumer. This is the single implementation — do not build another anywhere. Full rules in `engines/market_structure/CLAUDE.md`; algorithm in `engines/market_structure/MARKET_STRUCTURE_ENGINE.md`.

### engines/fibonacci/
Canonical fib engine. Turns `engines/market_structure/` output into fib LEVEL EVENTS — the first-touch of each fib level (E1–E4 entries, TP1–TP5 targets, 1.0) — for entries, take-profits, and setup grading. One shared geometry core serves all three fibs (Structure, Sniper, Macro); each is a small state machine ported line-by-line from `indicators/mpc_assistant.pine`. Consumes the structure engine's public output only (never its internals) via a `StructureSnapshot`. All three fibs (Structure "FFT", Sniper, Macro) are ported, unit-tested, and validated at 100% Pine parity on real XAUUSD exports (Structure/Sniper on 15m, Macro on 5m — Pine gates the Macro to ≤5m). Emits events, not visuals. This is the single implementation — do not build another. Full rules in `engines/fibonacci/CLAUDE.md`.

### engines/order_blocks/
Canonical order-block engine. Turns `engines/market_structure/` output into order-block EVENTS — a supply/demand zone created off each structure break (external BOS/SOS and internal iBOS/iSOS, into the same shared arrays), the bar it is later mitigated (tapped) on, and FIFO eviction past a per-direction cap of 6. Ported line-by-line from `indicators/mpc_assistant.pine`'s OB blocks. A SIBLING of `engines/fibonacci/`, not downstream of it: both consume the structure engine's public output only (never its internals) via their own decoupled `StructureSnapshot`. Ported, unit-tested (12 hand-traced tests), and validated at 100% Pine parity on a real `VANTAGE_XAUUSD, 5m` export (harness: `indicators/ob_export.pine` + `engines/order_blocks/tools/compare_ob.py`). Emits events, not visuals (no boxes/colours). This is the single implementation — do not build another. Full rules in `engines/order_blocks/CLAUDE.md`.

### engines/sessions/
Canonical sessions engine — the first **time-driven** engine (input = the bar's UTC timestamp in epoch ms + high/low, not `engines/market_structure/` output). Turns the clock into session EVENTS: Tokyo/London/NY session windows + running session high/low (finalized on close), the three NY kill zones (DST-aware), the NY opening range, and new-day/weekday flags. Standalone (depends on nothing). Ported line-by-line from `indicators/mpc_assistant.pine`'s session/kill-zone/NY-range blocks; drops all drawing and the two "days-back" render gates. Ported, unit-tested (17 hand-traced tests), and validated at 100% Pine parity on a real `VANTAGE_XAUUSD, 5m` export (all 18 fields; re-confirmed on a 15m export for the 16 timeframe-agnostic fields) — harness: `indicators/sessions_export.pine` + `engines/sessions/tools/compare_sessions.py`. Prerequisite for the session-scoped parts of the Liquidity engine (session H/L levels — now built) and the still-to-build VWAP engine (session anchor). Emits events, not visuals. This is the single implementation — do not build another. Full rules in `engines/sessions/CLAUDE.md`.

### engines/liquidity/
Canonical liquidity-levels engine. Turns the bar stream into liquidity LEVEL EVENTS — the prices price runs toward and grabs: previous day/week/month high & low (PDH/PDL/PWH/PWL/PMH/PML), previous week close (PWC), the H4 sweep high/low (SSH/BSL), and Asia/London/NY session high & low — each created off a completed period / session close, then mitigated by a **sweep** (day/session/H4: wick through + close back) or a **break** (week/month: close through), with FIFO-style replacement on the next roll. A time-driven engine that CONSUMES `engines/sessions/` (composes it) for session H/L and reconstructs day/week/month/H4 from the stream. **Non-repainting by Aaron's explicit decision (2026-07-05): every HTF level uses the PREVIOUS completed period only — the engine never forecasts the current period's high/low.** Ported from `indicators/mpc_assistant.pine`'s liquidity blocks, unit-tested (15 hand-traced tests), and validated at **100% Pine parity on a real `VANTAGE_XAUUSD, 5m` export** (all 33 fields — 15 level prices, their mitigation flags, 4 boundary-roll pulses — `--htf-rollover 18 --warmup 4653`, exit 0; harness: `indicators/liquidity_export.pine` + `engines/liquidity/tools/compare_liquidity.py`). Calibrated boundary: XAUUSD session opens 18:00 NY (baked-in default). Emits events, not visuals. This is the single implementation — do not build another. Full rules in `engines/liquidity/CLAUDE.md`.

### engines/news/
Canonical economic-calendar (news) engine — **off the extraction roadmap and NOT a `mpc_assistant.pine` port**. A standalone, time-driven engine (input = the bar's UTC timestamp) that turns an external calendar into trade-BLACKOUT EVENTS: for each closed bar it reports whether trading is inside a blackout window around a scheduled macro release (NFP/CPI/FOMC/PCE/ISM/EIA…), whether the bar's day is a **bank holiday** (always reported via `is_holiday`; folded into `in_blackout` only if the bot opts in with `block_holidays=True` — the engine reports, the strategy decides), the coming-up / happening-now / just-finished phases, and whether the bar even has data. A bot consults `in_blackout` and/or `is_holiday` to veto trading; the bot owns its own `NewsPolicy` (currencies, min impact, pre/post minutes, `block_holidays`) — same split as `REGIME_RISK_TABLE`. It is a **macro** calendar keyed by currency, so it serves FX, gold and index/rates futures alike (not single-stock earnings). Two data paths feed one local `EventStore` cache, behind a swappable `CalendarSource`: **live** = the free Forex Factory / faireconomy JSON feed (current week, no deps, `tools/refresh.py`); **history** = scrape the FF website month-by-month past Cloudflare via `curl_cffi` (`tools/backfill.py`), cached so static months are fetched once. **Honest-coverage by Aaron's decision (2026-07-05): before the cache's earliest fetched date the filter is inert (backtests trade normally); the engine exposes `coverage_start_ms` for a UI "news starts here" line (drawing it in the backtest lab is a follow-up).** Because there is no Pine source, it is NOT Pine-parity-validated — instead: 29 unit tests + a live-feed smoke + a real Feb-2025 backfill (blacked out ISM PMI + USD Presidents Day), all green. `curl_cffi` is needed only for history backfill (lazy-imported, isolated); the core + live feed are pure-stdlib. This is the single implementation — do not build another. Full rules in `engines/news/CLAUDE.md`.

### strategies/
Generic trading strategy source files, organized by runner platform. `strategies/ninjatrader/` holds the only live NinjaScript strategy, `ORB.cs` (VWAP_MR and Momentum were deleted 2026-06-21 — they baked risk management into the strategy, against the gated-layer rules). The command center scanner reads from here to register strategies in the database; the Deploy button uploads files to the VPS (NT8 or MT5 folder by extension). `strategies/mt5/` holds one MQL5 strategy: `LondonBreakout.mq5` (instrument-agnostic Asian-range → London breakout). Full rules in `strategies/CLAUDE.md`.

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
- Build a second structure engine, fib engine, order-block engine, sessions engine, liquidity engine, or news/economic-calendar engine anywhere — `engines/market_structure/engine.py`, `engines/fibonacci/`, `engines/order_blocks/`, `engines/sessions/`, `engines/liquidity/` and `engines/news/` are the canonical implementations; all consumers import from them
- Commit `engines/news/data/events.json` (or anything under `engines/news/data/`) — it is fetched calendar data, git-ignored, not source
