# Command Center — Backtest, Optimize, Stress-Test, Overfit Engine
## Design Document (v1 — for discussion, not build)

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

### `strategies` — the registry
A registered NinjaScript strategy. Source of truth for what can be run.

| Field | Type | Notes |
|---|---|---|
| id | str | e.g. `orb_lucidflex_v1` |
| name | str | display name |
| class_name | str | NinjaScript class name |
| category | str | breakout / mean-reversion / momentum / etc. |
| suggested_instrument | str | e.g. `MNQ 06-26` — pre-fills the run modal, user can override |
| default_params | json | e.g. `{"ORMinutes": 15, "TpMultiple": 1.5}` |
| param_schema | json | type + range per param (for the optimizer UI) |
| created_at | ts | |

### `firms` — prop firm rules
One row per firm. Pure rules, no code.

| Field | Type | Notes |
|---|---|---|
| id | str | `lucidflex_50k_eval`, `lucidflex_50k_funded`, `apex_50k_eval`, etc. |
| account_tier | str | `"eval"` or `"funded"` — funded skips profit target + consistency checks |
| name | str | display name |
| account_size | int | |
| profit_target | int | eval only |
| max_loss_eod | int | end-of-day drawdown limit |
| max_loss_intraday | int | trailing intraday limit (Apex etc.) |
| consistency_pct | float | 50 = no single day > 50% of total profit |
| min_trading_days | int | LucidFlex has 5, Apex has 7 |
| force_flat_time_et | str | e.g. `"15:30"` |
| allowed_instruments | json | `["MES", "MNQ", "MGC", "MCL"]` |
| max_contracts | json | `{"MES": 4, "MNQ": 4, "MES_micros": 40}` |
| platform_support | json | `["NinjaTrader", "Tradovate"]` |

### `backtest_runs` — raw results
Firm-agnostic. One row per `(strategy, instrument, params, date_range)` combo.

| Field | Type | Notes |
|---|---|---|
| run_id | str | uuid |
| strategy_id | str | FK strategies |
| instrument | str | |
| params | json | exact param set used |
| bar_type / bar_value | str / int | e.g. `Minute / 5` |
| start_date / end_date | date | |
| commission_per_side | float | |
| slippage_ticks | int | |
| status | str | running / complete / error |
| created_at | ts | |
| net_pnl | float | KPI |
| max_drawdown | float | KPI |
| profit_factor | float | KPI |
| win_rate | float | KPI |
| win_count / trade_count | int | KPI |
| sharpe / sortino / cagr | float | KPI |
| equity_curve_path | str | reference to JSON file with full curve |
| trades_path | str | reference to JSON file with all trades |
| daily_pnl_path | str | reference to JSON file with daily P&L |

Heavy data (full equity curve, trade-by-trade, daily P&L) lives in JSON files
on disk, not in SQLite blobs. The DB holds the index + summary KPIs.

### `evaluations` — firm-specific verdicts
The join layer. One row per `(backtest_run, firm)` combo.

| Field | Type | Notes |
|---|---|---|
| eval_id | str | uuid |
| run_id | str | FK backtest_runs |
| firm_id | str | FK firms |
| verdict | str | PASS / WARN / DISCARD |
| drawdown_pass | bool | dd vs firm's max_loss_eod |
| target_pass | bool | net_pnl vs firm's profit_target |
| consistency_pass | bool | check 50% rule from daily P&L |
| simulated_eval_days | int | days to hit target (null if didn't pass) |
| worst_day_pnl | float | for the daily P&L distribution |
| worst_losing_streak | int | |
| breach_count | int | how many times drawdown hit the limit |
| notes | text | reasons for verdict |

### `optimization_runs` and `stress_test_runs` and `overfit_runs`
Similar pattern — index in SQLite, heavy data on disk.

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

### 5.1 Backtest
Single strategy + single param set + single date range = one run. Shows equity
curve, daily P&L histogram, trade list, KPIs. Then runs evaluation against
selected firms and shows pass/fail per firm.

### 5.2 Optimizer (parameter sweep)
User defines a param grid (e.g. `ORMinutes: [5, 10, 15, 20, 30]` ×
`TpMultiple: [1.0, 1.5, 2.0, 2.5]`). NT8's built-in Optimizer runs the grid.
Results come back as N backtests.

**The thing NT can't do well, that we build:** the **objective function**.
Default options:
- "Maximize prop firm eval pass probability" (most important)
- "Maximize Sharpe with drawdown < firm limit"
- "Maximize profit factor while passing consistency rule"

User picks the firm, picks the objective, gets a ranked param-set list.
Heatmap UI for 2D param grids. Hover any cell to see the full backtest.

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

## 6. Backend endpoints to add

Extends the existing FastAPI app. Same router pattern as smart-money / bots.

```
GET    /strategies                   - list registered strategies
POST   /strategies/scan              - re-scan local NinjaScript repo, upsert into DB
GET    /strategies/{id}              - detail (incl. all backtests across all firms)
DELETE /strategies/{id}              - remove

GET    /firms                        - list prop firm profiles
POST   /firms                        - add new firm
GET    /firms/{id}                   - detail
PUT    /firms/{id}                   - update rules
DELETE /firms/{id}

GET    /backtests/runs               - list runs (filter by strategy, firm, status)
GET    /backtests/runs/{id}          - detail (full equity curve, trades, evals)
POST   /backtests/run                - trigger new run
POST   /backtests/runs/{id}/evaluate - re-run evaluations against new firm set
DELETE /backtests/runs/{id}

GET    /optimize/runs                - list
GET    /optimize/runs/{id}           - detail (param grid results + heatmap data)
POST   /optimize/run                 - trigger

GET    /stress-tests/runs            - list
GET    /stress-tests/runs/{id}       - detail (distribution data + fan paths)
POST   /stress-tests/run             - trigger on existing backtest_run

GET    /overfit/runs                 - list
GET    /overfit/runs/{id}            - detail
POST   /overfit/run                  - trigger walk-forward + sensitivity

GET    /lab/progress                 - unified progress endpoint (poll while running)
POST   /lab/stop                     - kill any running lab job

GET    /lab/runs/{run_id}/log        - tail a run's log file
GET    /system/health                - aggregated: backend, ssh, vps_agent, NT8, compile
GET    /vps/agent/log                - proxy to vps_agent's /agent-log
GET    /vps/nt/log                   - proxy to vps_agent's /nt-log
```

All POST triggers return 202 and a job ID. Frontend polls /lab/progress for
live status — same pattern as smart-money already uses.

---

## 7. VPS agent — what to add

Your existing `vps_agent.py` already does the LucidFlex 6-combo run. Generalize
its endpoints:

**Job execution:**

| Endpoint | Purpose |
|---|---|
| `POST /backtest` | run one backtest combo (any strategy, any instrument, any params); accepts a `job_id` |
| `POST /optimize` | drive NT8 Optimizer with a param grid |
| `POST /walk-forward` | drive NT8 Walk Forward tool |
| `POST /jobs/{job_id}/cancel` | stop a specific job (sends signal to pywinauto thread) |

**Discovery & metadata:**

| Endpoint | Purpose |
|---|---|
| `GET /strategies` | list compiled NinjaScript strategies in NT8 |
| `GET /instruments` | list contract names NT8 knows + their front-month codes |

**Results:**

| Endpoint | Purpose |
|---|---|
| `GET /jobs/{job_id}/results` | results for a specific job (job-keyed, not single-CSV) |
| `GET /jobs/{job_id}/status` | live status (running / complete / failed_* / heartbeat ts) |
| `GET /jobs/{job_id}/log` | tail this job's log file |

**Observability (new — for §12):**

| Endpoint | Purpose |
|---|---|
| `GET /health` | agent alive (already exists) |
| `GET /nt-health` | NT8 process running + Strategy Analyzer window detected via pywinauto |
| `GET /nt-compile-status` | parse NT's NinjaScript log; report last compile result, errors if any |
| `GET /nt-log` | tail of NT8's most recent NinjaScript log file |
| `GET /agent-log` | tail of vps_agent.py's own log |

The current vps_agent has `/results` returning one fixed CSV. That doesn't
scale to multiple parallel jobs — needs the job_id keying.

---

## 8. Frontend dashboards

Six pages, designed to match your existing cyan-on-indigo theme.

### Lab Overview (the index page)
- Stat row: # strategies registered, # backtests this week, # firms tracked
- "Currently running" panel (poll /lab/progress)
- Recent backtests table — strategy, firm verdicts as colored dots, sparkline,
  click-through

### Strategy Detail
One page per strategy. Shows:
- Strategy metadata (NS class, default params, param schema)
- **Multi-firm evaluation matrix** — strategy × every firm, color-coded
  pass/warn/fail. The headline insight. Click any cell → backtest detail.
- All backtest runs for this strategy, sortable
- Buttons: Backtest / Optimize / Stress Test / Overfit Check

### Backtest Detail
- Equity curve (Recharts)
- Daily P&L histogram — **the most important chart for prop trading**. Shows
  the consistency-rule shape at a glance.
- Trade list (paginated)
- Per-firm evaluation cards: verdict, dd vs limit, target hit y/n,
  consistency check y/n
- Worst day, worst losing streak, longest winning streak

### Optimizer
- Param grid setup (sliders / multi-select from param_schema)
- Objective function picker
- Firm selector
- Heatmap (Recharts custom or a simple SVG grid) for 2D grids
- Top-10 param-set table for 3+D grids
- Click any param set → full backtest detail

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

### Prop Firm Config (under Settings)
- List of firms
- Add / edit / delete form for rules
- Pre-loaded: LucidFlex 50k, LucidFlex 100k

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

**M1 — Backtest + Firm abstraction (the foundation)** ✅ COMPLETE
1. Add `strategies` and `firms` tables; seed with the 3 existing NinjaScript
   files and 4 LucidFlex firm configs (50k/100k × eval/funded)
2. Generalize VPS agent: job-keyed results, `/backtest` endpoint accepting any
   strategy
3. Build /backtests/run + /backtests/runs endpoints
4. Build Backtest Detail page (equity curve + daily P&L + per-firm eval cards)
5. **Test:** run the 3 existing strategies, see them pass/fail against
   LucidFlex firms from the UI

**M2 — Optimizer + Stress Test**
1. NT Optimizer integration in VPS agent
2. Objective function module (prob-of-eval-pass calculator)
3. Monte Carlo engine (Python-side, reads backtest trades)
4. Optimizer UI + Stress Test UI

**M3 — Overfitting + multi-firm UX**
1. Walk-forward in VPS agent
2. Parameter sensitivity runner
3. Overfitting detail page + robustness grade
4. Add 2nd firm (Apex 50k) to validate the abstraction holds
5. Strategy Detail page with multi-firm evaluation matrix

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

## M1 Retrospective (completed 2026-05-30)

### What we built

Full end-to-end backtest lab: strategy scanner, firm profiles, NT8-driven backtest runs via the VPS agent, tier-aware evaluation engine, and a detailed results page with equity curve, drawdown chart, daily P&L, long/short breakdown, and 11 KPI cards including Calmar ratio.

### What changed vs original spec

**4 firms, not 1.** The spec seeded one `lucidflex_50k` firm. Reality: each firm has two distinct modes — the eval challenge and the funded account. Rules differ meaningfully (funded has no profit target, no consistency rule). We created `lucidflex_50k_eval`, `lucidflex_50k_funded`, `lucidflex_100k_eval`, `lucidflex_100k_funded`. The `account_tier` column (`"eval"` | `"funded"`) drives the evaluation logic.

**`suggested_instrument`, not `default_instrument`.** Renamed during build because "default" implied it was locked in. It pre-fills the run modal; the user always overrides freely.

**No trades.json.** The spec called for a trade-by-trade JSON file (`trades_path`). We parse trades from the NT8 Trades CSV export directly into the equity curve JSON (one point per trade with `profit`, `direction`, `exit_name`). A separate trade list is not needed — the equity curve already carries per-trade data.

**Export automation, not NT XML log.** The spec assumed reading NT8's XML output log. NT8 doesn't expose a clean XML format for arbitrary strategy runs. Instead: the VPS agent automates the Strategy Analyzer's "Export Trades" right-click menu via pywinauto, producing a CSV the backend parses. This took significant debugging to get stable (WPF ComboBox identification, two-pass right-click pattern, coordinate caching).

**Traffic-light verdict + Calmar.** Added to BacktestDetail during M1 UX pass. Not in the original spec. Both turned out to be essential for quick run assessment.

### Decisions we might revisit

- **Inline chart components:** All charts live inside BacktestDetail.tsx rather than as standalone files. Fine at current scale; worth extracting if other pages (optimizer, stress test) need the same charts.
- **NT8 export via pywinauto:** Brittle if NT8 updates its WPF layout. The coordinate cache (`_export_coords_cache`) helps but it's still screen-position dependent. A proper NT8 API or file-watch approach would be more robust long term.
