# Command Center — Backtest, Optimize, Stress-Test, Overfit Engine
## Design Document

---

## 1. What we're building, in one sentence

A NinjaTrader-native "lab" inside the command center that lets you design a
strategy once, then evaluate it against any prop firm's rules — backtest,
optimize, stress test, and overfit-check it — all from the React UI, with NT8
on the VPS doing the actual compute.

The end goal of this module is the S and T steps of your S.Y.S.T.E.M. method.
The bots module you already built covers E and M.

---

## 2. Core design decision — abstract the prop firm out

Today, your `BacktestResult` model has `max_loss_limit`, `drawdown_pass`,
`eval_result` baked into it. That's a LucidFlex-shaped result. The moment you
add Apex, you'd have to rerun every backtest to get Apex-shaped numbers, or
worse, copy-paste fields.

**Fix:** separate the raw backtest from the evaluation.

- A **Backtest** is firm-agnostic. It just contains the trades, equity curve,
  daily P&L, and basic KPIs. No "did it pass" anywhere.
- A **Prop Firm Profile** is a JSON config describing one firm's rules
  (max loss, target, consistency, drawdown type, allowed instruments, session
  rules, instrument size limits).
- An **Evaluation** is `Backtest + Firm Profile → verdict`. The same backtest
  can be evaluated against LucidFlex, Apex, and Tradeify in parallel and
  produce three independent verdicts.

This is the single biggest decision in the design. Everything else falls out
of it.

---

## 3. Data Model

Five core entities. SQLite database (consistent with smart-money pattern).

**M1+M2 entities are implemented — see `backend/CLAUDE.md` for full schema and migration history.**

### `strategies` — the registry
Key fields: `id`, `name`, `class_name`, `category`, `suggested_instrument` (pre-fills modal, always overridable), `default_params`, `param_schema`, `runner` (default `"ninjatrader"`), `created_at`.

### `firms` — prop firm rules
One row per firm. Pure rules, no code.

| Field | Type | Notes |
|---|---|---|
| id | str | e.g. `lucidflex_50k_eval`, `lucidflex_50k_funded` |
| account_tier | str | `"eval"` or `"funded"` — funded skips profit target + consistency checks |
| name | str | display name |
| account_size | int | |
| profit_target | int | eval only |
| max_loss_eod | int | end-of-day drawdown limit |
| max_loss_intraday | int | trailing intraday limit |
| consistency_pct | float | e.g. 40 = no single day > 40% of total profit |
| min_trading_days | int | |
| force_flat_time_et | str | e.g. `"16:45"` |
| allowed_instruments | json | `["MES", "MNQ", "MGC", "MCL"]` |
| max_contracts | json | free-form; carries optional `scaling` object and `mix_allowed` flags |
| docs_url | str | link to firm's published rules — required on insert |

### `backtest_runs` — raw results
Firm-agnostic. Key fields: core KPIs, file paths for heavy data (equity curve, daily P&L), plus `worthiness_tier / worthiness_reason / worthiness_computed_against_firm`, `sweep_id`, `optimization_id`, `source_run_id`. See `backend/CLAUDE.md § DB schema — notable columns` for migration-added fields.

Heavy data (equity curve, daily P&L) lives in JSON files under `reports/lab/<run_id>/`, not in SQLite. The DB holds the index + summary KPIs.

### `evaluations` — firm-specific verdicts
One row per `(backtest_run, firm)`. Fields: `verdict` (PASS/WARN/DISCARD), `drawdown_pass`, `target_pass`, `consistency_pass`, `simulated_eval_days`, `worst_day_pnl`, `worst_losing_streak`, `breach_count`, `notes`.

### `optimizations`
One row per optimizer job. Key fields: `optimization_id`, `strategy_id`, `instrument`, `firm_id`, `mode`, `search_method`, `param_grid` (JSON), `status`, `estimated_runs`, `completed_runs`, `best_run_id`, `source_run_id`. See `backend/CLAUDE.md § DB schema`.

### `stress_test_runs` and `overfit_runs` (M3 — not yet built)
Same pattern — index in SQLite, heavy data on disk.

---

## 4. Pipeline flow (what happens when you hit "Run Backtest")

```
1. User picks: strategy, instrument, date range, params, firms to evaluate
   (in the React UI)
        ↓
2. Backend POST /backtests/run
   - Validates inputs against strategies + firms tables
   - Creates backtest_runs row with status="running"
   - Calls VPS agent at http://localhost:8765/run-backtest
        ↓
3. VPS agent (already exists, needs extension)
   - Receives the JSON spec
   - Writes a backtest_config.json on the VPS
   - Drives NT8 Strategy Analyzer via pywinauto (the code you already have)
   - Reads NT's XML log + writes results JSON to a shared folder
        ↓
4. Backend polls VPS agent /status until done
        ↓
5. Backend fetches /results, parses, writes to SQLite + JSON files
        ↓
6. Backend runs evaluation pass:
   for each firm in selected_firms:
       create evaluations row(backtest_run, firm)
       → verdict, drawdown_pass, target_pass, consistency_pass
        ↓
7. Backend updates backtest_runs.status = "complete"
        ↓
8. Frontend polls /backtests/runs/{run_id} → shows results
```

This is the same trigger/poll/fetch pattern smart-money already uses. The VPS
agent is the bridge that lets NT8 (inside the RDP session) be driven from the
Mac.

---

## 5. The four "lab" features

### 5.1 Backtest — ✅ implemented
See `backend/CLAUDE.md § What's built (status)` and `frontend/CLAUDE.md § What's built (status)`.

### 5.2 Optimizer — ✅ implemented (brute-force multi-call, not NT8 Optimizer GUI)
See `backend/CLAUDE.md § Key architectural decisions` for the approach and `§ Objective functions` for scoring detail. NT8's built-in Optimizer tab was not used — driving individual SA runs via the existing pipeline is more stable and gives full control over the objective function.

### 5.3 Monte Carlo Stress Test
Take the trades from a backtest, reshuffle 10k times, plus bootstrap-resample.
Output: distribution of max drawdown, P95 and P99 worst drawdown, probability
of breach per firm, probability of passing eval per firm. Fan chart of equity
paths. Same logic as the existing LucidFlex spec — just generalized to any
firm.

### 5.4 Overfitting Detector
Three complementary tests, all run automatically on any strategy:

1. **Walk-forward** — train on first 70% of data, test on last 30%. If
   performance drops more than a threshold, flag it. NT8 has a Walk Forward
   tool we can drive.
2. **Parameter sensitivity** — re-run the strategy with each param ±20% and
   ±50% of its optimal value. Robust strategies degrade smoothly; overfit ones
   crater.
3. **In-sample vs out-of-sample Sharpe ratio** — score difference.

Output: a single robustness grade (A / B / C / D / F) plus the underlying
charts. A strategy that doesn't get at least a B doesn't deploy.

---

## 6. Backend endpoints

**M1+M2 — implemented.** See `backend/CLAUDE.md § Directory layout` for the current router and service file list.

**M3 — to add:**

```
GET    /stress-tests/runs            - list
GET    /stress-tests/runs/{id}       - detail (distribution data + fan paths)
POST   /stress-tests/run             - trigger on existing backtest_run

GET    /overfit/runs                 - list
GET    /overfit/runs/{id}            - detail
POST   /overfit/run                  - trigger walk-forward + sensitivity
```

---

## 7. VPS agent

**M1+M2 — implemented.** `POST /backtest` (job-keyed, any strategy/instrument/params), job status/results/log endpoints, strategy list, instrument list, NT8 health, compile status, and agent log are all live in `algos/markets/futures/lucid_flex/tools/vps_agent.py`.

Note: `POST /optimize` driving NT8's built-in Optimizer GUI was **not implemented** — M2 used multi-call `/backtest` with brute force instead.

**M3 — to add:**

| Endpoint | Purpose |
|---|---|
| `POST /walk-forward` | drive NT8 Walk Forward tool |
| `POST /jobs/{job_id}/cancel` | stop a specific job mid-run |

---

## 8. Frontend dashboards

**M1+M2 — implemented.** See `frontend/CLAUDE.md § Directory layout` and `§ What's built (status)`.

**M3 — to build:**

### Stress Test Detail
- Fan chart of equity paths (semi-transparent overlay of 100 sampled paths)
- Max-drawdown distribution histogram
- Per-firm: probability of breach, probability of pass
- Worst 1% drawdown — the headline number

### Overfitting Detail
- Robustness grade (A-F)
- Walk-forward chart (in-sample vs out-of-sample equity)
- Parameter sensitivity radar / line chart
- IS vs OOS Sharpe comparison

---

## 9. Where things live (filesystem)

Backend stays on Mac. Pattern:

```
command-center/backend/
  data/
    lab.db                          ← SQLite for strategies, firms, runs index
  reports/
    lab/
      backtests/{run_id}/
        equity_curve.json
        trades.json
        daily_pnl.json
        raw_nt_results.csv          ← what NT exported
      optimizations/{run_id}/
        grid_results.json
      stress_tests/{run_id}/
        equity_paths.json           ← 100 sampled paths
        distribution.json
      overfit/{run_id}/
        walk_forward.json
        sensitivity.json
      lab_progress.json             ← poll target while a job runs
```

NT8 output stays on the VPS in its standard NinjaTrader folder; the VPS agent
parses + serves via HTTP. Backend fetches over the SSH tunnel
(`http://localhost:8765`) and writes its own copy to disk.

---

## 10. Build order I'd suggest

Three milestones, in this order. Each is a stop-and-test point.

**M1 — Backtest + Firm abstraction** ✅ COMPLETE
Strategy registry, firm profiles, NT8-driven backtest runs via VPS agent, per-firm evaluation engine, full KPI set, equity curve + daily P&L charts, traffic-light verdict, Calmar ratio.

**M2 — Worthiness Scorer + Instrument Sweeps + Brute-Force Optimizer** ✅ COMPLETE
Tier 1/2/3 worthiness scoring, instrument sweeps (N sequential runs, SA semaphore), brute-force parameter optimizer (multi-call, not NT8 Optimizer GUI), Tier 3 smart routing modal, NT8 SA global lock, runner field + vps_client dispatcher. Monte Carlo stress test moved to M3.

**M3 — Stress Tests + Walk-Forward + Overfitting** ✅ COMPLETE
Monte Carlo stress test, walk-forward (N NT8 windows), parameter sensitivity, A–F robustness grade, auto-trigger on Tier 1, pipeline stepper UI, pre-deployment checklist.

**M4 — Regime Classifier Integration** ✅ COMPLETE (2026-06-03, UI finalized 2026-06-02 session 11)
Regime tags on every backtest's daily_pnl (TRENDING/TRANSITIONING/RANGING/HIGH_VOLATILITY/LOW_VOLATILITY/UNKNOWN). Pipeline auto-tags on every new run. Manual backfill endpoint + "Tag Regimes" button in BacktestDetail header. Performance by Regime table slides in/out below equity curve (CSS max-height transition) when Regimes toggle is active. Equity curve **colored-line overlay** — equity line split into per-regime `Area` segments (fill=transparent, regime-colored stroke). Optimizer regime filter (scores child runs on regime-only trades). End-to-end verified on 12-month ORB/MNQ.

---

## 11. Decisions locked in

These were open questions in the v1 draft. All resolved.

1. **Backend stays on Mac.** Scaling limits documented in §13.
2. **Single SQLite database** for the whole lab — same pattern as smart-money.
3. **Auto-scan strategies from local repo.** "Scan Strategies" button reads
   the `algos/markets/futures/lucid_flex/` (and future) directories, parses
   each `.cs` file for the class name + `[NinjaScriptProperty]` declarations,
   upserts into the `strategies` table with the param schema auto-derived.
   No manual entry.
4. **Walk-forward via NT8 automation** (drive its Walk Forward tool).
5. **Refactor `models.py` to firm-agnostic** + add `Evaluation` model.
6. **Deprecate the hardcoded LucidFlex `backtest_config.json`.** All runs are
   job-keyed configs sent from the backend.

---

## 12. Observability & failure visibility — non-negotiable

**Principle:** the command center is the only place you ever look. If anything
breaks anywhere — Mac backend, SSH tunnel, VPS agent, NT8, a strategy compile
error — the command center shows you what broke, where, and why. You never
SSH to the VPS to diagnose. You never RDP in to "check on" anything. If you
have to, that's a bug in this design.

### Health & status — system-wide

A top-bar status strip (you already have the dots in the prototype). Each dot
has a tooltip with the failure reason if not green.

| Dot | What it pings | Green means |
|---|---|---|
| **Backend** | self | FastAPI alive |
| **SSH tunnel** | `ssh forexvps echo ok` | tunnel up |
| **VPS agent** | `GET http://localhost:8765/health` | agent responding |
| **NT8** | `GET /vps/nt-health` (new endpoint, agent-side) | NT8 process running + Strategy Analyzer window present |
| **Strategy compile** | `GET /vps/nt-compile-status` | last compile succeeded, no errors in NT log |

The first three are easy. The NT8 ones need new VPS agent endpoints — see
§7 update below.

### Job-level failure capture

Every run (backtest, optimize, stress, overfit) carries a status field. Failure
states are explicit, not silent:

| Status | What it means | UI shows |
|---|---|---|
| `running` | job in progress | spinner + live log tail |
| `complete` | finished cleanly, results available | green check |
| `failed_compile` | strategy didn't compile on VPS | red, with NT compile log excerpt |
| `failed_no_data` | instrument has no data for the date range | red, with the contract + date range |
| `failed_timeout` | no progress for > N minutes | yellow→red, with last-seen log line |
| `failed_nt_crash` | pywinauto lost the SA window mid-run | red, with reconnect button |
| `failed_runtime` | NT threw during the backtest | red, with the NT exception text |
| `failed_unknown` | catch-all | red, with the full traceback |

Each failure shows:
1. **What** went wrong (the status label)
2. **Where** it happened (which step, which strategy, which combo)
3. **Why** it happened (the actual error message — NT log line, Python
   exception, missing file path)
4. **What to do next** (specific action, e.g. "Open NT, click Strategies, F5
   to recompile" — pre-canned per failure type)

### Log tails — exposed via API

The backend already has `/bots/{bot_name}/log` for live bots. Mirror that:

```
GET /lab/runs/{run_id}/log         - tail the run's log file
GET /vps/agent/log                 - tail vps_agent.py's log
GET /vps/nt/log                    - tail NT8's NinjaScript log (errors only)
```

Frontend shows a "Logs" tab on every run detail page. No SSH needed.

### Heartbeat & stuck-job detection

The VPS agent updates a heartbeat field every 30s while running. Backend
watches for staleness:

- > 2 min stale → status changes to "stalled" (warning)
- > 10 min stale → status changes to "failed_timeout" (error), VPS agent
  receives a "kill current job" signal

This catches NT freezes that pywinauto can't see.

### Alerts (optional but recommended)

You already have a Telegram bot for the live bots. Hook it into lab failures
too: any job moving to a `failed_*` status fires a Telegram message with a
deep link back to the command center. So you can ignore the UI when a
multi-hour optimization is running and just get pinged if it dies.

---

## 13. Mac backend — scaling limits

You'll outgrow the Mac-based backend when one of these hits:

| Bottleneck | When you hit it | Mitigation |
|---|---|---|
| Mac sleeping | when you close the laptop and a long optimization is running | run on the VPS, OR run on a small always-on box (Mac mini, Raspberry Pi) |
| SSH tunnel drops | flaky home internet, ISP reset, lid close | use `autossh` instead of plain `ssh`; survives drops |
| Single-user assumption | if you ever want to log in from another device | rebuild auth (none today) and host on a small server |
| SQLite write contention | when multiple jobs write simultaneously (probably never, but possible at 30+ funded accounts running data collection) | migrate to Postgres |
| File-system reports dir | when you have 1000s of historical runs and disk fills | add a "archive runs older than X" routine |

**Practical threshold:** Mac stays fine through ~5 funded accounts. Beyond
that you'll want either (a) the backend on the VPS, or (b) a dedicated tiny
always-on server. None of this changes the code — it's just a host swap.

---

---

## 12. What this does NOT include

To stop scope creep — explicitly out of scope for this module:

- Live trading or order routing. Bots dashboard handles that.
- Walk-forward across multiple instruments simultaneously (multi-asset
  portfolio optimization). Future.
- Strategy authoring inside the UI. Strategies are written in NinjaScript in
  your editor. The command center catalogs and evaluates them.
- Cross-firm portfolio optimization (e.g. "best strategy assignment across 10
  funded accounts"). That's a separate problem we'll come back to once you're
  actually running accounts.

---

*End of design doc — review and we iterate before any code is written.*

---

## Pre-M4 Architecture Note — Regime Classifier Location

Before M4 begins, the regime classifier was promoted to a shared top-level subsystem at `trading/regime/`. M4 must import from there rather than building a new classifier in `command-center/backend/services/`.

```python
# Correct — import the canonical classifier
from regime import classify_regime, compute_signals

# Never — do not create a new classifier here
# command-center/backend/services/regime_classifier.py  ← must not exist
```

### M4 scope — what to build

Only the classifier's source location changed. Every other M4 deliverable is unchanged. The complete M4 scope is:

**Backend:**
- New service: `ohlc_fetcher.py` (with NT8 path first, yfinance fallback)
- New table: `instrument_daily_ohlc` — caches OHLC by (instrument, date) to avoid refetching
- Pipeline integration in `backtest_runner.py` — classifier runs at end of every backtest, filling in `regime_tag` on each `daily_pnl` entry
- New endpoint: `POST /backtests/{run_id}/backfill_regime` — for backtests that pre-date M4
- Updated endpoint: optimizer accepts optional `regime_filter` field (one of the 5 fine labels or null)

**Frontend:**
- New components: `RegimeBadge`, `PerformanceByRegimeTable`, `RegimeOverlayToggle`, `BackfillRegimeButton`
- Backtest Detail page gains a "Performance by Regime" section (KPIs sliced by regime)
- Equity curve gains an optional color overlay toggle to color-code days by regime
- Optimize Modal gains a "Regime filter (optional)" dropdown

**Documentation:**
- The canonical algorithm doc lives at `trading/regime/REGIME_CLASSIFIER.md` (already written during the unification pass). M4 does not create a duplicate doc in `backend/docs/`. Instead, `backend/CLAUDE.md` should reference the canonical doc by path so future Claude Code sessions know where to look.

**Color scheme for regime visualization** (used by `RegimeBadge`, `RegimeOverlayToggle`, `PerformanceByRegimeTable`):
- TRENDING: green (`#10b981`)
- RANGING: blue (`#3b82f6`)
- HIGH_VOLATILITY: orange (`#f97316`)
- LOW_VOLATILITY: gray (`#9ca3af`)
- TRANSITIONING: yellow (`#eab308`)
- UNKNOWN: dark gray (`#374151`) with hatching pattern

*Note: The classifier was simplified from two modes (coarse/fine) to a single 5-label output set on 2026-06-02. All callers — bots and lab — now use 5-label output directly. Each bot owns its own `REGIME_RISK_TABLE`.*

**Import pattern for M4 lab services:**
```python
# Pass the same daily df for both arguments when working with lab data
from regime import classify_regime, compute_signals

label = classify_regime(df_daily, df_daily)
# Returns: TRENDING | TRANSITIONING | RANGING | HIGH_VOLATILITY | LOW_VOLATILITY | UNKNOWN

signals = compute_signals(df_daily, df_daily)
# Returns: {"adx": float, "atr_ratio": float, "rsi_range": float, "score_norm": int} | None
```

**Thresholds:** all cutoffs live in `regime/thresholds.py`. To adjust them for the lab context, pass a `thresholds=` dict override to `classify_regime`. Do not fork or copy the math.

**Reference:** `trading/regime/REGIME_CLASSIFIER.md` — full plain-English algorithm doc.

---

## M1 + M2 Retrospective

### What M1 built

Full end-to-end backtest lab: strategy scanner, firm profiles, NT8-driven backtest runs via the VPS agent, tier-aware evaluation engine, and a detailed results page with equity curve, drawdown chart, daily P&L, long/short breakdown, and 11 KPI cards including Calmar ratio.

### What M2 built

Worthiness scorer (Tier 1/2/3 — PF, drawdown, trade count against strictest firm). Instrument sweeps (N sequential NT8 runs, SA semaphore = 1, each run gets its own worthiness score). Brute-force parameter optimizer (generates all param combos, drives as individual NT8 runs, up to 200-combo cap for 3+D grids, objective = eval_pass_probability or funded_sharpe_under_drawdown). Tier 3 Warning Modal with smart instrument routing. NT8 SA global lock (single physical SA window shared across all job types). Runner field on strategies + vps_client dispatcher. source_run_id linkage — sweep and optimization children nest under source run in the Runs tab. Cascade delete.

### What changed vs original spec

**M1 changes:**

**12 firms, not 2.** The spec seeded two LucidFlex configs. Reality: each firm needs both eval and funded variants (rules differ meaningfully — funded has no profit target, no consistency rule). Seeded 4 LucidFlex + 4 Tradeify Select + 4 FundedNext Futures Flex (3 providers × 2 account sizes × eval/funded = 12). The `account_tier` column drives evaluation logic.

**`suggested_instrument`, not `default_instrument`.** Renamed during build — "default" implied it was locked in. It pre-fills the run modal; the user always overrides freely.

**Export automation, not NT XML log.** NT8 doesn't expose a clean XML format. The VPS agent automates the Strategy Analyzer's "Export Trades" right-click menu via pywinauto. WPF ComboBox identification required significant debugging (coordinate caching, two-pass right-click pattern).

**Traffic-light verdict + Calmar.** Added during M1 UX pass — not in original spec. Both essential for quick run assessment.

**M2 changes:**

**Brute-force optimizer, not NT8 Optimizer GUI.** NT8's Optimizer tab has poor pywinauto accessibility. Multi-call individual SA runs through the existing pipeline is more stable and gives full control over the objective function.

**Worthiness scorer not in original M2 spec.** Emerged during design as a prerequisite for smart routing — you need a quality signal to decide whether to sweep, optimize, or discard.

**Tier 3 Warning Modal not in original spec.** The smart routing UX (show past results per instrument, offer untested instrument sweep) wasn't planned — it came from the realization that Tier 3 alone isn't actionable enough.

**Monte Carlo stress test moved to M3.** M2 was already large enough without it.

### M4 Retrospective

**What M4 built:** Regime classification integrated into the backtest pipeline. Every new backtest automatically tags each `daily_pnl` entry with one of 5 regime labels (TRENDING/TRANSITIONING/RANGING/HIGH_VOLATILITY/LOW_VOLATILITY) or UNKNOWN. Pre-M4 backtests can be tagged via a one-click backfill. On BacktestDetail: Performance by Regime table (Days/Trades/Net P&L/Win Rate/PF/Worst Day per regime, with Overall row pulled from run summary fields) — slides in below the equity curve with a CSS transition when the Regimes toggle is active. Equity curve gets a regime colored-line overlay. Optimizer gains a `regime_filter` field that scores child runs on regime-filtered trades only.

**What changed vs original spec:**

**Dual-mode classifier eliminated before M4 started.** The classifier had two modes (coarse 3-label for bots, fine 5-label for lab). Before M4 began, both were collapsed into a single 5-label output. All three bots gained `REGIME_RISK_TABLE` dicts mapping all 5 labels. The shim (`algos/shared/shared_regime.py`) returns neutral defaults; bots own their own decision tables.

**Colored equity line, not background bands.** The spec left the overlay strategy open. Initial implementation used `ReferenceArea` background bands (transparent-to-colored gradient fills), but these created muddy visual noise on the dark chart background. Final design: the equity curve itself is split into per-regime colored `Area` segments (`fill="transparent"`, regime-colored `stroke`). The data is augmented with per-segment keys (`_s0`, `_s1`, …); a hidden base Area anchors the Recharts tooltip. When the overlay is off, the chart reverts to the normal single-color green line. Regimes are per-day, not per-trade — a segment spans all trades that share a date.

**Optimizer filter at scoring time, not at run time.** NT8 runs the full backtest period regardless of `regime_filter`. The filter is applied when scoring child runs after they complete: trades on non-matching days are excluded from the objective function. OHLC is fetched once per optimization (not once per child run) and reused across all scoring.

**`from __future__ import annotations` fix.** `dict | None` union syntax in `regime/classifier.py` requires Python 3.10+ at runtime. The Mac runs 3.9.6. Adding `from __future__ import annotations` at the top of the module fixes it without changing behavior.

### Decisions we might revisit

- **Sweep state without a dedicated table.** `SweepSummary` is derived via GROUP BY on `backtest_runs`. Works but complicates sweep-level metadata.
- **200-combo brute-force cap.** Works for typical 2–3 param grids. For larger search spaces, sequential model-based optimization (e.g. tree-structured Parzen estimator) would be more efficient.
- **Inline chart components.** All charts live inside `BacktestDetail.tsx`. Fine now; worth extracting if additional pages need the same charts.
- **NT8 export via pywinauto.** Still screen-position dependent. A proper NT8 API or file-watch approach would be more robust long-term.
- **Regime classifier uses daily OHLC for both `df_short` and `df_long`.** The classifier was designed for H1/H4 pairs (bots). Passing the same daily DataFrame twice is a reasonable approximation for the lab's daily-granularity use case. If the classifier is tuned for multi-timeframe data, this will need revisiting.
