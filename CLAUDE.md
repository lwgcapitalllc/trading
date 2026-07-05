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

`algos/`, `smart-money/`, and `command-center/` are fully independent from each other. `regime/` and `market_structure/` are shared libraries imported by `algos/` (each via a thin shim in `algos/shared/`); `regime/` is also imported by `command-center/` (directly). `fibonacci/` is a shared library downstream of `market_structure/` — it consumes that engine's public output (a `StructureSnapshot`) and will get an `algos/shared/` shim when a bot first uses it. `order_blocks/` is a sibling of `fibonacci/` — it also consumes `market_structure/`'s public output directly (via its own decoupled `StructureSnapshot`, never fibonacci) and will likewise get an `algos/shared/` shim when a bot first uses it. `sessions/` is a standalone, time-driven shared library (input = the bar's UTC timestamp, not `market_structure/` output); it is the prerequisite for the session-scoped parts of the still-to-build Liquidity and VWAP engines, and will get an `algos/shared/` shim when a bot first uses it. `strategies/` is consumed by `command-center/` (scanner + deploy) and deployed to the VPS (NT8 strategy folder).

---

## System Summaries

### algos/
Automated trading on PU Prime demo accounts (Windows VPS via Task Scheduler). No live bots currently — the four first-attempt bots (SMC Trend, Scalper, FFT, Mean Reversion) were deleted 2026-06-22 to rebuild the suite backtest-first per `docs/BOT_DEVELOPMENT_METHOD.md`. Deployment learnings (MT5 connection, configs, scheduler, liveness layer) are preserved in `algos/docs/BOT_DEPLOYMENT_INFRA.md`. Full rules in `algos/CLAUDE.md`.

### smart-money/
Scans and profiles consistent crypto/forex traders for copy trading candidate pool construction. Runs locally on Mac. Stages 1–2 and 5 live; Stages 3–4 need API keys. Full rules in `smart-money/CLAUDE.md`.

### command-center/
React + FastAPI local operations platform. Monitors bots via SSH, surfaces Smart Money pipeline output, runs and evaluates NinjaTrader and MT5 backtests. Full rules in `command-center/CLAUDE.md`.

### regime/
Shared market regime classifier. Imported by the live bots (via `algos/shared/shared_regime.py` thin shim) and by the command-center backtest lab. Single output set: 5 labels (TRENDING, TRANSITIONING, RANGING, HIGH_VOLATILITY, LOW_VOLATILITY). Each bot owns its own `REGIME_RISK_TABLE` mapping labels to trade decisions. Full rules in `regime/CLAUDE.md`. Algorithm documented in `regime/REGIME_CLASSIFIER.md`.

### market_structure/
Canonical market-structure detection engine (BOS/CHoCH, swing highs/lows, HH/HL/LH/LL, internal structure). A stateful streaming state machine ported line-by-line from `indicators/structure_engine.pine` and validated at 100% Pine parity on a real XAUUSD 15m export. Imported by the live bots via `algos/shared/structure_engine.py` (thin shim); the command-center backtest lab is a future consumer. This is the single implementation — do not build another anywhere. Full rules in `market_structure/CLAUDE.md`; algorithm in `market_structure/MARKET_STRUCTURE_ENGINE.md`.

### fibonacci/
Canonical fib engine. Turns `market_structure/` output into fib LEVEL EVENTS — the first-touch of each fib level (E1–E4 entries, TP1–TP5 targets, 1.0) — for entries, take-profits, and setup grading. One shared geometry core serves all three fibs (Structure, Sniper, Macro); each is a small state machine ported line-by-line from `indicators/mpc_assistant.pine`. Consumes the structure engine's public output only (never its internals) via a `StructureSnapshot`. All three fibs (Structure "FFT", Sniper, Macro) are ported, unit-tested, and validated at 100% Pine parity on real XAUUSD exports (Structure/Sniper on 15m, Macro on 5m — Pine gates the Macro to ≤5m). Emits events, not visuals. This is the single implementation — do not build another. Full rules in `fibonacci/CLAUDE.md`.

### order_blocks/
Canonical order-block engine. Turns `market_structure/` output into order-block EVENTS — a supply/demand zone created off each structure break (external BOS/SOS and internal iBOS/iSOS, into the same shared arrays), the bar it is later mitigated (tapped) on, and FIFO eviction past a per-direction cap of 6. Ported line-by-line from `indicators/mpc_assistant.pine`'s OB blocks. A SIBLING of `fibonacci/`, not downstream of it: both consume the structure engine's public output only (never its internals) via their own decoupled `StructureSnapshot`. Ported, unit-tested (12 hand-traced tests), and validated at 100% Pine parity on a real `VANTAGE_XAUUSD, 5m` export (harness: `indicators/ob_export.pine` + `order_blocks/tools/compare_ob.py`). Emits events, not visuals (no boxes/colours). This is the single implementation — do not build another. Full rules in `order_blocks/CLAUDE.md`.

### sessions/
Canonical sessions engine — the first **time-driven** engine (input = the bar's UTC timestamp in epoch ms + high/low, not `market_structure/` output). Turns the clock into session EVENTS: Tokyo/London/NY session windows + running session high/low (finalized on close), the three NY kill zones (DST-aware), the NY opening range, and new-day/weekday flags. Standalone (depends on nothing). Ported line-by-line from `indicators/mpc_assistant.pine`'s session/kill-zone/NY-range blocks; drops all drawing and the two "days-back" render gates. Ported, unit-tested (17 hand-traced tests), and validated at 100% Pine parity on a real `VANTAGE_XAUUSD, 5m` export (all 18 fields; re-confirmed on a 15m export for the 16 timeframe-agnostic fields) — harness: `indicators/sessions_export.pine` + `sessions/tools/compare_sessions.py`. Prerequisite for the session-scoped parts of the still-to-build Liquidity (session H/L levels) and VWAP (session anchor) engines. Emits events, not visuals. This is the single implementation — do not build another. Full rules in `sessions/CLAUDE.md`.

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
- Build a second regime classifier in `command-center/` or anywhere else — `regime/classifier.py` is the canonical implementation; all consumers import from there
- Build a second structure engine, fib engine, order-block engine, or sessions engine anywhere — `market_structure/engine.py`, `fibonacci/`, `order_blocks/` and `sessions/` are the canonical implementations; all consumers import from them
