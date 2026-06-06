# LWG Capital — Project State Snapshot
**Last updated:** 2026-06-06
**Source:** live repo state — verified against filesystem, DB, and CLAUDE.md files

> Hand this document to any new Claude.ai chat as the first message, along with
> the Roadmap document. Together they orient a new chat in 30 seconds without
> re-explaining the foundation.

---

## What this project is

LWG Capital is a personal algorithmic trading operation building toward 30–50 funded prop firm accounts. The near-term goal is to pass LucidFlex evaluation challenges using futures strategies built and validated in NinjaTrader 8. The S.Y.S.T.E.M. methodology (Synthesize, Yield, Simulate, Test, Execute, Monitor) governs every strategy decision: design it in code, simulate against historical data, stress-test for robustness, and only deploy what earns a grade of B or better against the firm's actual rules. Today the focus is futures (MES, MNQ, MGC, MCL, MYM, M2K) and prop evaluation. Forex and MT5 infrastructure exists for live demo bots but is not part of the prop firm path yet.

---

## Stack and infrastructure

**Mac dev environment**
- FastAPI (Python 3.11) backend on `:8000`
- React 18 + Vite + TypeScript frontend on `:5173`
- SQLite at `command-center/backend/data/lab.db`
- VS Code, Claude Code (terminal agent), Claude.ai (planning chats)

**Windows VPS (ForexVPS)**
- NinjaTrader 8 — backtest engine and eventually live execution
- `nt8_agent.py` — Flask HTTP server on port 8765, accessed via SSH LocalForward tunnel
- `vps_compile_runner.py` — pywinauto subprocess: opens NinjaScript Editor, presses F5, polls DLL mtime for success
- MT5 (PU Prime demo, `C:\MT5_FFT`) — live forex bots only
- MT5 Lab (`C:\MT5_Lab`, PU Prime demo) — Strategy Tester for backtest lab only; driven by `mt5_agent.py` on port 8766
- SSH alias: `forexvps` — repo at `C:\trading\`

**Repository:** lwgcapitalllc/trading (private GitHub)
- `main` — all development
- `backups` — orphan branch, VPS runtime data only, never merges to main

---

## Monorepo structure

```
trading/
├── algos/            ← Live MT5 forex bots (4 bots, Windows VPS, PU Prime demo)
│   └── shared/       ← shared_regime shim, risk engine, mt5_ops, notify
├── smart-money/      ← Crypto/forex trader scanner for copy-trading candidates
├── command-center/   ← React + FastAPI local operations platform
│   ├── backend/      ← FastAPI app, SQLite, VPS client, routers, services
│   └── frontend/     ← React UI — sidebar, pages, hooks, Recharts charts
├── regime/           ← Shared market regime classifier (live bots + backtest lab)
├── strategies/       ← Generic strategy source files, organized by runner platform
│   ├── ninjatrader/  ← ORB.cs, VWAP_MR.cs, Momentum.cs (NinjaScript / C#)
│   ├── mt5/          ← MeanReversion.mq5 (BB+RSI+VWAP, ported from bot_mean_reversion.py, smoke-tested)
│   └── tradovate/    ← placeholder (no strategies yet)
├── scripts/          ← VPS bootstrap and full-recovery PowerShell scripts
└── docs/             ← Cross-subsystem design docs, audit prompt templates, snapshots
```

---

## What's shipped (chronological)

### M1 — Lab foundation ✅
Strategy registry: scanner reads `.cs` files, extracts class name, param schema (via regex on `[NinjaScriptProperty]` blocks), suggested instrument. Rulesets (one row per prop firm challenge or personal account). Single backtest runs triggered via `nt8_agent.py` driving NT8's Strategy Analyzer via pywinauto. Per-ruleset evaluation: PASS/WARN/DISCARD verdicts computed server-side against firm rules (drawdown, profit target, consistency). Equity curve, daily P&L, trade list stored as JSON files; KPIs in SQLite.

### M2 — Sweeps, optimizer, worthiness scoring ✅
Instrument sweeps: one strategy across all instruments, NT8 runs sequentially (SA semaphore = 1). Brute-force and genetic parameter optimizer: each combo is a separate NT8 run, ranked by objective function (eval pass probability or funded Sharpe). Worthiness tiers: Tier 1 (stress-test), Tier 2 (optimize), Tier 3 (discard). Tier 3 warning modal with smart instrument routing. NT8 global SA lock (409 on collision). Source run nesting in Runs table.

### M3 — Stress tests and robustness grading ✅
Monte Carlo (10k reshuffles + 1k bootstrap, pure numpy, ~5s per run). Walk-forward (N IS/OOS NT8 window pairs). Sensitivity (±10%/±25% param perturbations via NT8). A–F grade with plain-English reasons. Pre-deployment checklist locked unless grade is B+. Auto-trigger on Tier 1 and optimizer winners. Sweep cancel and per-run retry for stuck-running recovery.

### Pre-M4 — Regime classifier unification ✅
Consolidated from two modes to one canonical 5-label output (TRENDING, TRANSITIONING, RANGING, HIGH_VOLATILITY, LOW_VOLATILITY). All consumers updated. Thin shim at `algos/shared/shared_regime.py` preserves existing bot interface.

### M4 — Regime integration into backtest lab ✅ shipped 2026-06-03
Every backtest's `daily_pnl` entries tagged with a regime label at pipeline time. Performance by Regime table on BacktestDetail. Equity curve colored regime overlay with legend. Optimizer regime filter: score child runs using only trades from matching-regime days. BacktestDetail UI overhaul: chip consolidation, Challenge/Score column split, active job indicator dots on tabs.

### Pass 1 — Foundational config layer ✅ shipped 2026-06-03
Genericized all three NT8 strategies. Renamed from `*_LucidFlex.cs` to `ORB.cs`, `VWAP_MR.cs`, `Momentum.cs`. Categorized parameters: `[Category("Strategy Logic")]` (tunable) vs `[Category("Foundational")]` (injected from ruleset). Ruleset foundational fields: risk %, daily halt fraction, max consecutive losses, entry hours ET, days allowed, daily profit target, profit lock-in, commission/slippage defaults. RunBacktestModal shows readonly Foundational Config; optimizer grid excludes foundational params. Strategy DB IDs migrated from `orb_lucidflex` → `orb` etc.

### Pass 2 — Strategy deployment manager ✅ shipped 2026-06-03
Upload, delete, and compile NT8 strategy files from the command center UI without manual RDP. NT8 agent: `GET/POST/DELETE /files/strategies`, `POST/GET /compile`. Compile via pywinauto F5 through the NinjaScript Editor (NCompile.exe does not exist on this NT8 install). Success detection by polling `NinjaTrader.Custom.dll` mtime (90s timeout). Deployed tab on Strategies page: file list, drag/drop upload, overwrite confirmation, trash-can delete, Compile All. Sync-status badges on Strategies list. Platform field on each file (NT8/MT5) with filter chips when multiple platforms present.

### Pass 2.5 — Strategy location cleanup ✅ shipped 2026-06-04
Moved ORB.cs, VWAP_MR.cs, Momentum.cs to `strategies/ninjatrader/`. Scanner reads from `strategies/` (not `algos/`). DB `source_path` migrated. `POST /strategies/{id}/deploy` endpoint + per-strategy Deploy/Redeploy buttons on Strategies tab. `strategies/CLAUDE.md` created. All path references updated across monorepo.

### M5 — MT5 runner ✅ shipped 2026-06-06
`mt5_agent.py` on VPS (port 8766) — health, historical data, Strategy Tester driver (ini+set file, terminal64.exe, HTML report parser). `mt5_agent_client.py` on backend. `nt8_agent_client` dispatches to MT5 when `strategy.runner == "mt5"`. Runner badges (NT8/MT5) on Strategies and Runs tabs. Market filter (Futures/Forex). MT5 deployment manager: upload/delete `.mq5` files, MetaEditor compile. `RunBacktestModal` and `BacktestDetail` fully MT5-aware. `MeanReversion.mq5` smoke-tested end-to-end.

---

## Current state of strategies

Four strategies across two runners. NT8 strategies are at `strategies/ninjatrader/`; MT5 strategy is at `strategies/mt5/`. None has reached Tier 1 or Tier 2 yet — these are baseline runs only.

| Strategy | Runner | Runs | Best result | Status |
|---|---|---|---|---|
| ORB | NT8 | 20 complete | +$7.6k on MNQ (still Tier 3) | Tier 3 across all instruments. Needs optimization. |
| Momentum | NT8 | 2 complete | -$1.2k on best run | Tier 3. Barely tested. |
| VWAP_MR | NT8 | 0 | — | Not yet run. |
| MeanReversion | MT5 | 1 complete | -$9.3k (smoke test run) | Smoke test complete. No further MT5 runs yet. |

ORB has been run on MES, MNQ, MGC, MCL, MYM, M2K — all TIER_3_DISCARD, most with large negative net P&L. These are pre-optimization baseline runs. Strategy improvement work (regime filter, trailing stop, daily P&L circuit breaker, re-entry) is the next priority.

---

## Current state of rulesets

**15 rulesets seeded in the database:**
- 6 `prop_eval`: LucidFlex $50k + $100k, Tradeify $50k + $100k, FundedNext $50k + $100k
- 6 `prop_funded`: same firms, same sizes, funded-account rules (drawdown only, no profit target)
- 2 `personal`: Personal $10k Futures (Example), Personal Forex Main Account
- 1 `demo`: Personal Forex Demo Account

All rulesets carry the full foundational config fields from Pass 1 (risk %, halt fraction, consecutive loss limit, entry hours, days allowed, daily profit target, lock-in percentage, commission, slippage).

---

## Architectural principles locked in

1. **One backtest, N verdicts.** A backtest is firm-agnostic. The same run evaluates against any number of rulesets in parallel. Adding a new firm never requires re-running.

2. **Generic strategies, ruleset-injected config.** No firm-specific values baked into strategy files. Account size, daily loss limit, commission, entry hours — all injected from the active ruleset at run time via the foundational config dispatcher.

3. **Categorized parameters.** Every strategy parameter is tagged Strategy Logic (tunable, visible to optimizer) or Foundational (injected from ruleset, hidden in UI). Legacy files use GroupName heuristic as fallback.

4. **One shared regime classifier.** `regime/classifier.py` is the only implementation. Live bots use it via a thin shim. The backtest lab imports directly. No duplicate anywhere.

5. **NT8 is the backtest and execution engine.** The command center drives NT8 via pywinauto. There is no Python-native backtest engine.

6. **Strategies are a top-level peer subsystem.** `strategies/<runner>/` is the canonical home for all strategy source files. The command center scanner reads from there; the Deploy button ships them to VPS.

7. **NT8 global SA lock.** Only one job may use the Strategy Analyzer at a time. Backend enforces with a DB check (409 on collision); frontend disables all job triggers when any job is running.

8. **Heavy data off SQLite.** Equity curves, trade lists, daily P&L → JSON files under `reports/lab/<run_id>/`. DB holds index and KPIs only.

9. **Observability is mandatory.** Every running job writes progress atomically. Frontend polls. Live log streaming at 2s. Pipeline stepper for multi-phase jobs.

10. **CLAUDE.md updated in same session as approved changes.** Never deferred.

11. **Strict build order with stop-and-report checkpoints.** Each numbered step verified before the next. No silent skips.

---

## Communication rules with Claude Code

- Plain English replies. No code blocks unless explicitly asked.
- One clear question with concrete options when input is needed.
- Stop and report after each numbered step in any build spec.
- Smallest viable change first — no speculative abstractions.
- Update CLAUDE.md files in the same session as the changes that made them stale.
- No comments in code explaining what it does — only non-obvious constraints or invariants.

---

## What's NOT done

See `docs/LWG_Roadmap_And_Open_Questions.md`.
