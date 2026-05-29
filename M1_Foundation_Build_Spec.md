# M1 — Foundation Build Spec
## Strategies + Firms + First Backtest End-to-End

**For Claude Code.** This is the first of three milestones for the command
center's backtest lab. Read the design doc
(`Command_Center_Backtest_Engine_Design.md`) before starting — it has the why
and the architecture. This document has the what and the how.

When M1 is done you will be able to: scan your local NinjaScript repo, see
strategies and firms in the command center, click "Run Backtest" against any
strategy + firm combo, watch NT8 execute it on the VPS, and view the result
with pass/fail verdict per firm. Optimizer, Monte Carlo, and overfitting come
in M2 and M3.

---

## 0. Ground rules

- **Don't rebuild what exists.** `vps_agent.py`, `vps_backtest_runner.py`, and
  the 3 NinjaScript strategies all work. Extend them, don't replace them.
- **Don't break smart-money or bots.** Both ship features. Lab is additive.
- **One SQLite database** shared with the lab: `backend/data/lab.db`. Smart
  money's `smart_money.db` stays separate (different domain).
- **Follow the established patterns.** TanStack Query for fetching, `sonner`
  for toasts, `StatCard`/`ScaffoldBanner`/`EmptyState` components reused.
- **No partial steps.** Each section below is a complete unit. Finish one
  before the next. Update docs (`CLAUDE.md` in backend + frontend if present)
  as you go.

---

## 1. What M1 delivers (acceptance checklist)

When this is done, all of these must work end-to-end from the command center
UI without any terminal commands or SSH:

- [ ] Hit "Scan Strategies" → `algos/markets/futures/` is scanned, three
  existing strategies (ORB, VWAP_MR, Momentum) appear in the Strategies table
  with their param schemas extracted from `[NinjaScriptProperty]` declarations.
- [ ] Strategies list page shows the three strategies with default instrument
  and param count.
- [ ] Firms list page shows four LucidFlex rows seeded (`lucidflex_50k_eval`,
  `lucidflex_50k_funded`, `lucidflex_100k_eval`, `lucidflex_100k_funded`) with
  correct rules and `docs_url` populated.
- [ ] On any strategy detail page, hit "Run Backtest" → pick instrument, date
  range, params, firms to evaluate → VPS runs it via NT8 → result appears in
  the UI with pass/fail per selected firm.
- [ ] Backtest Detail page renders: equity curve, daily P&L histogram, KPI
  cards, per-firm evaluation cards (verdict + drawdown vs limit + target hit
  + consistency).
- [ ] System Health status strip in the sidebar shows 5 dots: Backend, SSH
  tunnel, VPS agent, NT8 process, Last compile. Each turns red with a useful
  tooltip when broken.
- [ ] Any job failure shows specific failure status, error message, and a log
  tab on the run detail page. No SSH needed to diagnose.

---

## 2. Data model — `lab.db` schema

Create `backend/data/lab.db`. Use the same SQLite pattern as smart-money
(plain `sqlite3` module, no ORM).

```sql
-- Registered NinjaScript strategies
CREATE TABLE strategies (
  id              TEXT PRIMARY KEY,        -- e.g. 'orb_lucidflex'
  name            TEXT NOT NULL,            -- display name
  class_name      TEXT NOT NULL,            -- NS class, e.g. 'ORB_LucidFlex'
  source_path     TEXT NOT NULL,            -- relative path from monorepo root
  category        TEXT,                     -- 'breakout', 'mean_reversion', etc.
  default_instrument TEXT,                  -- e.g. 'MNQ 06-26'
  default_params  TEXT,                     -- JSON
  param_schema    TEXT,                     -- JSON: {name, type, min, max, default}[]
  scanned_at      INTEGER NOT NULL,         -- unix ts of last scan
  source_hash     TEXT                      -- md5 of source file; lets re-scan detect changes
);

-- Prop firm rule configs
CREATE TABLE firms (
  id              TEXT PRIMARY KEY,         -- e.g. 'lucidflex_50k_eval'
  name            TEXT NOT NULL,            -- 'LucidFlex $50k Eval'
  account_size    INTEGER NOT NULL,
  profit_target   INTEGER NOT NULL,         -- 0 on funded rows = "no target"
  max_loss_eod    INTEGER NOT NULL,
  max_loss_intraday INTEGER,                -- nullable; LucidFlex uses EOD only
  drawdown_type   TEXT NOT NULL,            -- 'eod' | 'trailing_intraday'
  consistency_pct REAL,                     -- nullable; null on funded rows
  min_trading_days INTEGER,                 -- nullable; null on funded rows
  force_flat_time_et TEXT,                  -- '15:30'
  allowed_instruments TEXT,                 -- JSON array
  max_contracts   TEXT,                     -- JSON
  platform_support TEXT,                    -- JSON array
  account_tier    TEXT NOT NULL DEFAULT 'eval',  -- 'eval' | 'funded'
  docs_url        TEXT,                     -- canonical URL to the firm's rules
  notes           TEXT,                     -- free-form; stamp with verification date
  created_at      INTEGER NOT NULL,
  updated_at      INTEGER NOT NULL
);

-- Raw backtest runs (firm-agnostic)
CREATE TABLE backtest_runs (
  run_id          TEXT PRIMARY KEY,         -- uuid
  strategy_id     TEXT NOT NULL REFERENCES strategies(id),
  instrument      TEXT NOT NULL,
  params          TEXT NOT NULL,            -- JSON
  bar_type        TEXT NOT NULL,            -- 'Minute'
  bar_value       INTEGER NOT NULL,         -- 5
  start_date      TEXT NOT NULL,            -- 'YYYY-MM-DD'
  end_date        TEXT NOT NULL,
  commission_per_side REAL NOT NULL,
  slippage_ticks  INTEGER NOT NULL,
  status          TEXT NOT NULL,            -- see status enum below
  created_at      INTEGER NOT NULL,
  completed_at    INTEGER,
  error_message   TEXT,
  -- KPI summary (populated when status = 'complete')
  net_pnl         REAL,
  max_drawdown    REAL,
  profit_factor   REAL,
  win_rate        REAL,
  win_count       INTEGER,
  trade_count     INTEGER,
  sharpe          REAL,
  sortino         REAL,
  cagr            REAL,
  avg_win         REAL,
  avg_loss        REAL,
  avg_trade_duration_min REAL,
  worst_day_pnl   REAL,
  worst_losing_streak INTEGER,
  -- File pointers (heavy data lives in JSON files)
  equity_curve_path TEXT,
  trades_path     TEXT,
  daily_pnl_path  TEXT
);

CREATE INDEX idx_runs_strategy ON backtest_runs(strategy_id, created_at DESC);
CREATE INDEX idx_runs_status   ON backtest_runs(status);

-- Per-firm evaluations of a backtest
CREATE TABLE evaluations (
  eval_id         TEXT PRIMARY KEY,         -- uuid
  run_id          TEXT NOT NULL REFERENCES backtest_runs(run_id),
  firm_id         TEXT NOT NULL REFERENCES firms(id),
  verdict         TEXT NOT NULL,            -- 'PASS' | 'WARN' | 'DISCARD'
  drawdown_pass   INTEGER NOT NULL,         -- 0/1
  target_pass     INTEGER NOT NULL,         -- 0/1
  consistency_pass INTEGER,                 -- 0/1 (nullable if firm has no rule)
  simulated_eval_days INTEGER,              -- null if didn't pass
  breach_count    INTEGER NOT NULL,
  largest_day_share_pct REAL,               -- biggest day's % of total profit
  notes           TEXT,
  created_at      INTEGER NOT NULL,
  UNIQUE(run_id, firm_id)
);

CREATE INDEX idx_evals_firm ON evaluations(firm_id, verdict);
```

### Run status enum (string values stored in `backtest_runs.status`)

```
running
complete
failed_compile         -- strategy didn't compile on VPS
failed_no_data         -- contract has no data for the date range
failed_timeout         -- no agent heartbeat for > 10 min
failed_nt_crash        -- pywinauto lost the SA window
failed_runtime         -- NT threw during the backtest
failed_unknown         -- catch-all, error_message has details
```

### Seed data

On first run of the backend, if `firms` is empty, insert these **four** rows
(one per `{size, tier}` combo). The eval and funded phases have different
rules, so they get separate rows.

```python
# Shared defaults used by all LucidFlex rows
_LUCID_SHARED = {
    "drawdown_type": "eod",
    "force_flat_time_et": "15:30",
    "allowed_instruments": ["MES", "MNQ", "MGC", "MCL", "MYM", "M2K"],
    "platform_support": ["NinjaTrader", "Tradovate"],
    "notes": "Verified from docs_url on <today's date>",
}

# lucidflex_50k_eval
{
  **_LUCID_SHARED,
  "id": "lucidflex_50k_eval",
  "name": "LucidFlex $50k Eval",
  "account_size": 50000,
  "profit_target": 3000,
  "max_loss_eod": 2000,
  "max_loss_intraday": None,
  "consistency_pct": 50.0,
  "min_trading_days": 5,
  "max_contracts": {"mini_max": 4, "micro_max": 40},
  "account_tier": "eval",
  "docs_url": "https://support.lucidtrading.com/en/articles/12945790-lucidflex-evaluation-account",
}

# lucidflex_50k_funded — no consistency rule, no profit target
{
  **_LUCID_SHARED,
  "id": "lucidflex_50k_funded",
  "name": "LucidFlex $50k Funded",
  "account_size": 50000,
  "profit_target": 0,
  "max_loss_eod": 2000,
  "max_loss_intraday": None,
  "consistency_pct": None,
  "min_trading_days": None,
  "max_contracts": {"mini_max": 4, "micro_max": 40},
  "account_tier": "funded",
  "docs_url": "https://support.lucidtrading.com/en/articles/12945795-lucidflex-funded-account",
}

# lucidflex_100k_eval
{
  **_LUCID_SHARED,
  "id": "lucidflex_100k_eval",
  "name": "LucidFlex $100k Eval",
  "account_size": 100000,
  "profit_target": 6000,
  "max_loss_eod": 3000,
  "max_loss_intraday": None,
  "consistency_pct": 50.0,
  "min_trading_days": 5,
  "max_contracts": {"mini_max": 6, "micro_max": 60},
  "account_tier": "eval",
  "docs_url": "https://support.lucidtrading.com/en/articles/12945790-lucidflex-evaluation-account",
}

# lucidflex_100k_funded
{
  **_LUCID_SHARED,
  "id": "lucidflex_100k_funded",
  "name": "LucidFlex $100k Funded",
  "account_size": 100000,
  "profit_target": 0,
  "max_loss_eod": 3000,
  "max_loss_intraday": None,
  "consistency_pct": None,
  "min_trading_days": None,
  "max_contracts": {"mini_max": 6, "micro_max": 60},
  "account_tier": "funded",
  "docs_url": "https://support.lucidtrading.com/en/articles/12945795-lucidflex-funded-account",
}
```

**Why eval and funded are separate rows:** during the eval phase, a strategy
is judged against profit target + consistency rule + daily loss cap. Once
funded, the consistency rule and target disappear — only max loss matters.
Same strategy can pass eval evaluation but be the wrong fit for funded use
(or vice versa). Keeping them as separate firm rows means every backtest can
be evaluated against both phases independently — `evaluations` rows naturally
fan out and the UI can show "would pass eval / would survive funded" side by
side.

---

## 3. Refactor `backend/models.py`

The current `BacktestResult` and `StressTestResult` are LucidFlex-shaped. Make
them firm-agnostic.

### Remove from `BacktestResult`

```
max_loss_limit           ← firm-specific
drawdown_pass            ← firm-specific
eval_result              ← firm-specific
eval_days                ← firm-specific
```

### Replace `BacktestResult` with `BacktestRun` + `BacktestSummary`

`BacktestRun` is one row in the DB. `BacktestSummary` is the lightweight
shape for list views.

```python
class BacktestSummary(BaseModel):
    run_id: str
    strategy_id: str
    strategy_name: str
    instrument: str
    status: str                 # see enum
    created_at: datetime
    completed_at: Optional[datetime] = None
    # Summary KPIs (null while running)
    net_pnl: Optional[float] = None
    max_drawdown: Optional[float] = None
    profit_factor: Optional[float] = None
    win_rate: Optional[float] = None
    trade_count: Optional[int] = None
    # Verdicts at a glance — list of {firm_id, verdict} for sparkline UI
    verdicts: list[dict] = []


class BacktestDetail(BaseModel):
    run_id: str
    strategy_id: str
    strategy_name: str
    instrument: str
    params: dict
    bar_type: str
    bar_value: int
    start_date: str
    end_date: str
    commission_per_side: float
    slippage_ticks: int
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    # Full KPIs
    net_pnl: Optional[float] = None
    max_drawdown: Optional[float] = None
    profit_factor: Optional[float] = None
    win_rate: Optional[float] = None
    win_count: Optional[int] = None
    trade_count: Optional[int] = None
    sharpe: Optional[float] = None
    sortino: Optional[float] = None
    cagr: Optional[float] = None
    avg_win: Optional[float] = None
    avg_loss: Optional[float] = None
    avg_trade_duration_min: Optional[float] = None
    worst_day_pnl: Optional[float] = None
    worst_losing_streak: Optional[int] = None
    # Heavy data (loaded from referenced files)
    equity_curve: list[EquityPoint] = []
    daily_pnl: list[dict] = []   # [{date: 'YYYY-MM-DD', pnl: float}]
    trade_count_by_day: list[dict] = []
    # Per-firm verdicts
    evaluations: list["EvaluationDetail"] = []


class EvaluationDetail(BaseModel):
    eval_id: str
    firm_id: str
    firm_name: str
    verdict: str                # 'PASS' | 'WARN' | 'DISCARD'
    drawdown_pass: bool
    target_pass: bool
    consistency_pass: Optional[bool] = None
    simulated_eval_days: Optional[int] = None
    breach_count: int
    largest_day_share_pct: Optional[float] = None
    # Firm context for the UI
    firm_max_loss_eod: int
    firm_profit_target: int
    firm_consistency_pct: Optional[float] = None
    # Plain-English summary
    notes: Optional[str] = None
```

### New models

```python
class Strategy(BaseModel):
    id: str
    name: str
    class_name: str
    source_path: str
    category: Optional[str] = None
    default_instrument: Optional[str] = None
    default_params: dict = {}
    param_schema: list[dict] = []  # [{name, type, min?, max?, default, ui_hint?}]
    scanned_at: datetime
    # Computed
    run_count: int = 0


class Firm(BaseModel):
    id: str
    name: str
    account_size: int
    profit_target: int             # 0 on funded rows = "no target"
    max_loss_eod: int
    max_loss_intraday: Optional[int] = None
    drawdown_type: str
    consistency_pct: Optional[float] = None    # null on funded rows
    min_trading_days: Optional[int] = None     # null on funded rows
    force_flat_time_et: Optional[str] = None
    allowed_instruments: list[str] = []
    max_contracts: dict = {}
    platform_support: list[str] = []
    account_tier: str = "eval"                 # 'eval' | 'funded'
    docs_url: Optional[str] = None             # canonical URL to firm's rules
    notes: Optional[str] = None                # free-form, stamp verification date


class BacktestRunRequest(BaseModel):
    strategy_id: str
    instrument: str
    params: dict
    bar_type: str = "Minute"
    bar_value: int = 5
    start_date: str             # 'YYYY-MM-DD'
    end_date: str
    commission_per_side: float = 2.25
    slippage_ticks: int = 1
    evaluate_firms: list[str]   # firm_ids to evaluate against


class LabProgress(BaseModel):
    job_id: Optional[str] = None
    job_type: Optional[str] = None  # 'backtest' | 'optimize' | 'stress' | 'overfit'
    status: str                  # 'idle' | 'running' | 'complete' | 'failed_*'
    strategy_id: Optional[str] = None
    instrument: Optional[str] = None
    pct: int = 0
    message: str = ""
    started_at: Optional[str] = None
    updated_at: Optional[str] = None
    heartbeat_age_seconds: float = 0.0
    error_message: Optional[str] = None


class SystemHealth(BaseModel):
    backend: bool                # always true if responding
    ssh_tunnel: bool
    vps_agent: bool
    nt8_running: bool
    nt8_sa_visible: bool         # Strategy Analyzer window detected
    last_compile_ok: bool
    last_compile_at: Optional[str] = None
    last_compile_errors: list[str] = []
    checked_at: str
```

### Drop the StressTestResult model

Move it to a new `M2_models.py` placeholder or just delete. M2 will define it
properly with multi-firm output.

---

## 4. New backend routers

Create three new routers. Wire them in `main.py`.

### `routers/strategies.py`

```python
GET    /strategies                  → list[Strategy]
POST   /strategies/scan             → {scanned: int, added: int, updated: int}
GET    /strategies/{id}             → Strategy (with run_count)
DELETE /strategies/{id}             → 204
```

**Scan implementation:**

1. Resolve repo root from `config.MONOREPO_ROOT`.
2. Glob for `*.cs` files under `algos/markets/futures/**/`.
3. For each file:
   - Compute md5; if hash matches existing row, skip (no DB write).
   - Parse the file (regex is fine, this is a controlled format):
     - Find `public class <ClassName> : Strategy`
     - Find every `[NinjaScriptProperty]` block with a `[Display]` and a
       `public <type> <PropName> { get; set; }` line below it
     - Find every `[Range(min, max)]` on the same property
     - Find every default assignment inside `if (State == State.SetDefaults)`
       block to get default values
   - Build param schema: `[{name, type: "double"|"int"|"bool", min, max, default, group?, display_name?}]`
   - Skip params in the "Prop Firm" group — those are firm-injected, not
     strategy-specific (AccountSize, RiskPct, MaxDailyLoss, DailyHaltFraction,
     CommissionPerSide).
   - Upsert into `strategies` table.
4. Return counts.

The scan is idempotent — running it twice with no file changes is a no-op.

### `routers/firms.py`

```python
GET    /firms                       → list[Firm]
POST   /firms                       → Firm (create)
GET    /firms/{id}                  → Firm
PUT    /firms/{id}                  → Firm (update)
DELETE /firms/{id}                  → 204
```

On startup, if table is empty, seed all four LucidFlex rows (see §2 seed data).

### `routers/backtests.py` (replace the existing stub)

```python
GET    /backtests/runs              → list[BacktestSummary] (filter by strategy_id, firm_id, status)
GET    /backtests/runs/{run_id}     → BacktestDetail
GET    /backtests/runs/{run_id}/log → text/plain (tail of run log)
POST   /backtests/run               → {run_id, status: 'started'} (202)
DELETE /backtests/runs/{run_id}     → 204
POST   /backtests/runs/{run_id}/reevaluate → BacktestDetail
                                      (re-run evaluations against new firm set)
```

**Run flow (`POST /backtests/run`):**

1. Validate request (strategy exists, firms exist, instrument format).
2. Check there's no running job (poll `LabProgress`). If there is, 409.
3. Generate `run_id = uuid4().hex[:12]`.
4. Insert row in `backtest_runs` with `status = "running"`.
5. Write `lab_progress.json` with starting state.
6. Build the VPS agent request body (see §5).
7. POST to `{vps_agent_tunnel}/backtest` with the job_id.
8. Spawn a background task that polls VPS agent every 5s:
   - On `status = "complete"`: fetch results, parse, compute KPIs, write JSON
     files, update `backtest_runs` row, generate `evaluations` rows for each
     requested firm.
   - On `status = "failed_*"`: copy status + error into `backtest_runs`,
     update progress to idle.
   - On no heartbeat for >2min: status = "stalled" (warning). >10min: mark
     `failed_timeout` and POST `/jobs/{id}/cancel` to agent.
9. Return 202 with `run_id`.

### `routers/system.py` (new — observability)

```python
GET    /system/health               → SystemHealth
GET    /lab/progress                → LabProgress
POST   /lab/stop                    → {stopped: bool}
GET    /vps/agent/log               → text/plain
GET    /vps/nt/log                  → text/plain
```

Health computation:

- `backend`: always true (this endpoint responded)
- `ssh_tunnel`: shell out `ssh -o ConnectTimeout=3 forexvps echo ok` once,
  cache result for 30s
- `vps_agent`: GET `{vps_agent_tunnel}/health` with 3s timeout
- `nt8_running`, `nt8_sa_visible`: GET `{vps_agent_tunnel}/nt-health`
- `last_compile_ok`, errors: GET `{vps_agent_tunnel}/nt-compile-status`

Cache the result in-memory for 10s so the sidebar polling every 30s doesn't
hammer the VPS.

---

## 5. VPS agent — what to change

Edit `algos/markets/futures/lucid_flex/tools/vps_agent.py`.

### New job-keyed pattern

Replace the single-job model. Add a `_jobs` dict keyed by `job_id`:

```python
_jobs: dict[str, dict] = {}
# Each job: {
#   'job_id', 'type', 'status', 'started_at', 'updated_at', 'log': [...],
#   'heartbeat_at', 'results': {...} or None, 'error': None or {type, message}
# }
```

### New endpoints

```
POST  /backtest             body = backtest config + job_id
POST  /jobs/<job_id>/cancel
GET   /jobs/<job_id>/status → full job dict
GET   /jobs/<job_id>/results
GET   /jobs/<job_id>/log    → tail
GET   /nt-health            → {nt_running, sa_visible, sa_strategy_count?}
GET   /nt-compile-status    → {ok, last_check_at, errors: [...]}
GET   /nt-log               → tail of latest NinjaScript log
GET   /agent-log            → tail of this agent's log
GET   /strategies           → list of compiled NS strategies
GET   /instruments          → list of contract names
```

### Backtest endpoint body

```json
{
  "job_id": "abc123",
  "strategy_class": "ORB_LucidFlex",
  "instrument": "MNQ 06-26",
  "params": {"ORMinutes": 15, "TpMultiple": 1.5, "OneTradePer": "False"},
  "bar_type": "Minute",
  "bar_value": 5,
  "start_date": "2021-01-01",
  "end_date": "2026-05-23",
  "commission_per_side": 2.25,
  "slippage_ticks": 1,
  "prop_firm_params": {
    "account_size": 50000,
    "risk_pct": 0.5,
    "max_daily_loss": 2000,
    "daily_halt_fraction": 0.6
  }
}
```

The agent writes a per-job `backtest_config_<job_id>.json` to a temp dir, then
calls the existing `vps_backtest_runner.py` with `--config <path> --combo <job_id>`.
The runner already supports `--combo` for single-combo runs. Repurpose: each
run is a one-combo job. Drop the global `backtest_config.json` dependency.

### Failure classification

When `vps_backtest_runner.py` returns:
- Exit code 0 + result file present → `complete`
- "compile" or "build" error in NT log near our run timestamp → `failed_compile`
- "instrument" or "no data" warning → `failed_no_data`
- pywinauto exception (timeout finding window) → `failed_nt_crash`
- runner timeout (no result after 600s default) → `failed_timeout`
- Any other exception → `failed_runtime` with full traceback in `error`
- Anything else → `failed_unknown`

### Heartbeat

While running, the agent updates `job['heartbeat_at'] = now()` every 30s.
Backend's polling uses this to detect stalls.

### `nt-health` implementation

```python
@app.route("/nt-health")
def nt_health():
    try:
        from pywinauto import Desktop
        # Check NT process
        nt_running = bool(subprocess.run(
            ['tasklist', '/FI', 'IMAGENAME eq NinjaTrader.exe'],
            capture_output=True, text=True
        ).stdout.count('NinjaTrader.exe'))
        # Check SA window
        sa_visible = False
        if nt_running:
            try:
                Desktop(backend="uia").window(
                    title_re=".*Strategy Analyzer.*"
                ).wait("visible", timeout=2)
                sa_visible = True
            except Exception:
                pass
        return jsonify({"nt_running": nt_running, "sa_visible": sa_visible})
    except Exception as e:
        return jsonify({"nt_running": False, "sa_visible": False, "error": str(e)})
```

### `nt-compile-status` implementation

Read the latest file in `~/Documents/NinjaTrader 8/log/`. Grep for "Error" or
"failed". If any errors found after the last compile-success line, return
them.

---

## 6. Auto-scan strategy parser — details

Input: `algos/markets/futures/lucid_flex/ORB_LucidFlex.cs`

Output: row in `strategies` table:

```json
{
  "id": "orb_lucidflex",
  "name": "Opening Range Breakout (LucidFlex)",
  "class_name": "ORB_LucidFlex",
  "source_path": "algos/markets/futures/lucid_flex/ORB_LucidFlex.cs",
  "category": "breakout",
  "default_instrument": "MNQ 06-26",
  "default_params": {"ORMinutes": 15, "TpMultiple": 1.5, "OneTradePer": false},
  "param_schema": [
    {
      "name": "ORMinutes",
      "type": "int",
      "min": 5,
      "max": 60,
      "default": 15,
      "group": "Strategy",
      "display_name": "Opening Range Minutes"
    },
    {
      "name": "TpMultiple",
      "type": "double",
      "min": 0.5,
      "max": 5.0,
      "default": 1.5,
      "group": "Strategy",
      "display_name": "TP Multiple (× OR width)"
    },
    {
      "name": "OneTradePer",
      "type": "bool",
      "default": false,
      "group": "Strategy",
      "display_name": "One Trade Per Day (long OR short)"
    }
  ]
}
```

### Parsing rules

- `id`: snake_case of class_name
- `name`: from class file's first comment line (line that starts `//` after
  `using` block), or the `Description` value in `State.SetDefaults`. Fallback
  to humanized class_name.
- `category`: inferred from class file's filename or first comment. ORB →
  "breakout", VWAP_MR → "mean_reversion", Momentum → "momentum". Keep simple
  for M1.
- `default_instrument`: pull from existing `backtest_config.json` if present
  for this strategy; else null.
- Params: walk `[NinjaScriptProperty]` blocks. Skip any in `GroupName = "Prop Firm"`.
- Range/min/max: parse `[Range(min, max)]` decorator.
- Default: pull from `SetDefaults` body assignment.

This is brittle to NinjaScript style changes. Document the conventions in
`docs/STRATEGY_CONVENTIONS.md` so new strategies follow the same patterns.

---

## 7. Evaluation logic — how to compute pass/fail per firm

After a backtest completes, for each firm in the `evaluate_firms` list,
generate an `evaluations` row.

Inputs from the backtest:
- `daily_pnl`: list of `{date, pnl}` per trading day
- `max_drawdown`: peak-to-trough drawdown in $ (from equity curve)
- `net_pnl`: total profit
- `trade_count`

Inputs from the firm:
- `profit_target`, `max_loss_eod`, `consistency_pct`, `min_trading_days`

### Logic

```python
def evaluate(backtest, firm):
    # 1. Drawdown check — never breach max_loss_eod (applies to BOTH eval and funded)
    drawdown_pass = backtest.max_drawdown <= firm.max_loss_eod

    # 2. Target check — only meaningful in eval. Funded rows have profit_target = 0,
    #    treated as "no target — survive without blowing up."
    if firm.account_tier == "funded" or firm.profit_target == 0:
        target_pass = True   # no target to fail
    else:
        target_pass = backtest.net_pnl >= firm.profit_target

    # 3. Consistency check — only meaningful in eval. Funded rows have
    #    consistency_pct = null. Skip entirely.
    consistency_pass = None
    largest_day_share = None
    if firm.consistency_pct is not None and backtest.net_pnl > 0:
        biggest_day = max((d.pnl for d in backtest.daily_pnl if d.pnl > 0), default=0)
        share = biggest_day / backtest.net_pnl * 100
        largest_day_share = share
        consistency_pass = share <= firm.consistency_pct

    # 4. Breach counter — how many days dipped below max_loss_eod from peak
    breach_count = count_drawdown_breaches(backtest.equity_curve, firm.max_loss_eod)

    # 5. Verdict (tier-aware)
    if not drawdown_pass:
        verdict = "DISCARD"   # blown up regardless of tier
    elif firm.account_tier == "funded":
        # Funded just needs to not blow up. No target, no consistency.
        verdict = "PASS"
    elif not target_pass:
        verdict = "WARN"  # eval: didn't hit target but didn't blow up
    elif consistency_pass is False:
        verdict = "WARN"  # eval: target hit but consistency-rule violation
    else:
        verdict = "PASS"

    return Evaluation(
        verdict=verdict,
        drawdown_pass=drawdown_pass,
        target_pass=target_pass,
        consistency_pass=consistency_pass,
        breach_count=breach_count,
        largest_day_share_pct=largest_day_share,
        notes=generate_notes(...),
    )
```

`notes` is a human-readable summary, e.g. "Hit target in 14 days, single day
was 38% of total profit (under 50% limit), drawdown peaked at $1,847 (under
$2,000 limit)."

---

## 8. Frontend — new files and modifications

### Add to `tailwind.config.js`

Nothing new — existing tokens are sufficient.

### New types — extend `src/types.ts` (or wherever types live)

Mirror the new Pydantic models: `Strategy`, `Firm`, `BacktestSummary`,
`BacktestDetail`, `EvaluationDetail`, `BacktestRunRequest`, `LabProgress`,
`SystemHealth`.

### New hooks — `src/hooks/useLab.ts`

```typescript
useStrategies()              // GET /strategies
useScanStrategies()          // POST /strategies/scan (mutation, toast)
useStrategy(id)              // GET /strategies/{id}
useFirms()                   // GET /firms
useFirm(id)                  // GET /firms/{id}
useBacktestRuns(filters?)    // GET /backtests/runs
useBacktestRun(id)           // GET /backtests/runs/{id}
useBacktestLog(id)           // GET /backtests/runs/{id}/log
useRunBacktest()             // POST /backtests/run (mutation)
useStopLab()                 // POST /lab/stop
useLabProgress()             // GET /lab/progress (variable polling like useRunProgress)
useSystemHealth()            // GET /system/health (poll 30s)
```

Replace the stub `useBacktests.ts` with these. Stub `useStressTests.ts` stays
untouched (M2).

### Modify `src/components/Sidebar.tsx`

Replace the current two-dot footer (VPS + API) with a five-dot strip. New
component `SystemHealthStrip.tsx`:

```
Backend  ●     SSH tunnel  ●     VPS agent  ●     NT8  ●     Compile  ●
```

Each dot is the same `StatusDot` component already in Sidebar, with a tooltip
showing the failure reason on red. Poll `/system/health` every 30s.

### Modify `src/pages/Backtests.tsx`

Replace the scaffold entirely. Top-level "Backtests" page with sub-tabs (use
the smart-money sub-tab pattern):

- **Runs** (default) — list of backtest runs as table
- **Strategies** — list of registered strategies + "Scan Strategies" button
- **Firms** — list of prop firm profiles + add/edit

### New page — `src/pages/BacktestDetail.tsx`

Route: `/backtests/runs/:runId`

Layout (top to bottom):

1. **Header** — strategy name, instrument, params, date range, status
2. **Per-firm evaluation cards** — one card per firm in the eval set:
   - Verdict pill (PASS/WARN/DISCARD with appropriate color)
   - Drawdown: $X / $Y limit (green if pass, red if fail)
   - Target: $X / $Y (green/red)
   - Consistency: largest day was X% of profit (green if < firm pct)
   - Notes
3. **KPI grid** — 8 StatCards: Net P&L, Max DD, Win Rate, Profit Factor,
   Trade Count, Sharpe, Worst Day, Worst Streak
4. **Equity curve** — Recharts line chart, full width, height ~280px
5. **Daily P&L histogram** — Recharts BarChart, days on X axis, $ on Y,
   bars colored green/red. Horizontal line at 50% of total profit. THIS IS
   THE MOST IMPORTANT CHART — make it prominent.
6. **Logs tab** — collapsible, fetches `/backtests/runs/{id}/log`

When `status` is `failed_*`:
- Replace KPI grid with a red banner showing the failure reason and the
  `error_message` from the run
- Show the "What to do next" block based on failure type
- Logs are auto-expanded

### New page — `src/pages/StrategyDetail.tsx`

Route: `/backtests/strategies/:strategyId`

Layout:
1. Header: strategy name, class, default instrument, "Run Backtest" button
2. Param schema table (read-only)
3. List of all backtest runs for this strategy (sortable by created_at, sortable by verdict pass count)
4. Multi-firm verdict matrix preview (just shows verdicts from latest 5 runs as colored dots — full matrix comes in M3)

### New component — `src/components/RunBacktestModal.tsx`

A modal that opens from "Run Backtest" buttons. Fields:
- Instrument (text input, prefilled with strategy's default)
- Date range (two date pickers)
- Params (form auto-generated from `param_schema` — int → number input,
  bool → checkbox, double → number input with step)
- Firms to evaluate (multi-select checkboxes from `useFirms()`)
- Commission per side (default 2.25)
- Slippage ticks (default 1)

Submit → `useRunBacktest()` → toast "Backtest started" → navigate to the new
run's detail page (which will show "running" status and live-update as the
backend polls).

### Modify `src/components/Sidebar.tsx` — Research section

Keep "Backtests" as the single Lab entry point. Drop the "Soon" badge — it's
live now. Sub-tabs handle the rest. "Stress Tests" stays with "Soon" — M2.

---

## 9. End-to-end flow — what should happen when I click "Run Backtest"

1. User on Strategy Detail page clicks "Run Backtest" button
2. Modal opens, user fills in form, selects "LucidFlex $50k" and "LucidFlex $100k"
3. Submit → POST `/backtests/run`
4. Backend: validates, inserts `backtest_runs` row (status=running), writes
   progress.json, POSTs to VPS agent with job_id
5. Backend returns 202 with run_id; frontend navigates to `/backtests/runs/<id>`
6. BacktestDetail page mounts; `useBacktestRun(id)` polls every 1.5s while
   status is running
7. VPS agent receives, queues job, runs `vps_backtest_runner.py` via pywinauto
8. Agent updates heartbeat every 30s; backend polls agent status every 5s
9. NT runs the backtest (~30s-2min depending on date range)
10. Runner writes XML log; agent parses; agent stores results keyed by job_id
11. Backend's poller sees status=complete; fetches results; writes equity
    curve / trades / daily_pnl JSON files; computes KPIs; updates DB row
12. Backend generates 2 `evaluations` rows (one per firm)
13. Backend marks `lab_progress.json` idle
14. Frontend's next poll returns the complete BacktestDetail with all data
15. User sees: equity curve, daily P&L bars, KPI cards, 2 firm verdict cards.

If anything fails along the way, the run's status moves to a `failed_*` state,
error_message is populated, and the UI shows the failure card with logs.

---

## 10. Status dots in the sidebar — exact behavior

| Dot | Source | Green | Yellow | Red |
|---|---|---|---|---|
| Backend | self-check | API responding | n/a | API unreachable |
| SSH tunnel | `ssh forexvps echo ok` (cached 30s) | success | n/a | timeout/failure |
| VPS agent | `GET /vps/health` proxied | 200 OK | n/a | unreachable |
| NT8 | `GET /nt-health` proxied | nt_running && sa_visible | nt_running but no SA window | not running |
| Compile | `GET /nt-compile-status` proxied | last compile clean | n/a | errors present |

Tooltip on hover shows the actual status text. Click on a red dot navigates to
`/settings` (where we'll add a "System Health" diagnostics panel in M2).

For M1, no auto-fixing — just visibility. If NT8 is down, you start it
yourself. The next phase can add a "Start NT8" button.

---

## 11. Test cases — what to verify before declaring M1 done

Walk through these manually. If any fail, M1 isn't done.

1. **Cold start** — fresh `lab.db` deleted, hit Scan → 3 strategies appear, 4
   firms seeded (eval + funded for both $50k and $100k). All four have
   `docs_url` populated and `account_tier` set correctly.
2. **Scan idempotence** — hit Scan twice in a row → second run reports 0 added,
   0 updated.
3. **Edit a .cs file**, change a `[Range]`, hit Scan → that strategy's
   param_schema reflects the new range, source_hash updates.
4. **Run a backtest** on ORB_LucidFlex, MNQ 06-26, 2024-01-01 to 2024-12-31,
   evaluate against all four LucidFlex firms (50k eval + funded, 100k eval +
   funded) → result appears within ~2 min with four evaluation rows. Verify
   the funded rows skip the consistency check (consistency_pass = null) while
   the eval rows compute it.
5. **Failed compile path** — temporarily break the .cs file (introduce a
   syntax error), deploy it, run backtest → run status moves to
   `failed_compile`, error message is the compile error, log shows the NT log
   excerpt.
6. **Kill VPS agent mid-run** — start a backtest, ssh in and `taskkill` the
   agent → backend detects within 10 min, run marked `failed_timeout`.
7. **Sidebar dots** — verify all 5 reflect actual state (turn off NT, see red
   NT dot with tooltip; tunnel down, see red tunnel dot).
8. **Reevaluate** — after a complete backtest, edit a firm's
   `profit_target`, POST `/backtests/runs/{id}/reevaluate` → evaluations
   updated without re-running the backtest.

---

## 12. What is NOT in M1

To prevent scope creep — explicitly not building:

- Optimizer (M2)
- Monte Carlo / Stress Test engine (M2)
- Walk-forward / overfitting (M3)
- Multi-firm evaluation matrix UI (M3 — for now, evaluation cards on the
  backtest detail page are enough)
- Adding firms beyond LucidFlex (M3)
- Apex / Tradeify rule configs (M3, but seeing the abstraction work with just
  LucidFlex 50k vs 100k is the validation point for M1)
- Auto-fixing NT8 / agent if down (just visibility, no actions)
- Strategy editor / Pine Script / TradingView integration (not happening)

---

## 13. Build order

1. **Backend foundation** (no UI changes yet)
   - Create `lab.db` schema + seed
   - Refactor `models.py`
   - Implement `strategies.py` router + scan logic
   - Implement `firms.py` router
   - Test with curl: scan works, list works, firms list works
2. **VPS agent generalization**
   - Add job-keyed model (preserve old endpoints as deprecation shim if you
     want, or hard-cut — agent is internal)
   - Add `/nt-health`, `/nt-compile-status`, `/nt-log`, `/agent-log`
   - Adapt `vps_backtest_runner.py` to write per-job results
   - Test with curl: trigger one backtest end-to-end, verify result JSON
3. **Backend backtest flow**
   - Implement `backtests.py` router (replace stub)
   - Background poller that watches the VPS job
   - Evaluation logic
   - Test: trigger via curl, watch DB, watch JSON files appear
4. **Backend system router**
   - `/system/health` + log proxies
5. **Frontend hooks**
   - `useLab.ts` with all the new hooks
6. **Frontend Backtests page rewrite**
   - Sub-tabs: Runs / Strategies / Firms
   - Scan Strategies button on Strategies tab
7. **Frontend Backtest Detail page**
   - Equity curve, daily P&L histogram, KPI grid, eval cards
   - Failure state rendering
8. **Frontend Run Backtest modal**
9. **Sidebar SystemHealthStrip**
10. **End-to-end test of all the cases in §11**

Steps 1-4 are pure backend — should be done and curl-testable before any UI
work starts. Steps 5-9 are frontend. Step 10 validates the whole thing.

---

## 14. Files to expect to create or modify

### Backend (Mac, command-center)

```
Created:
  backend/data/lab.db                       (auto-created on startup)
  backend/data/lab_progress.json
  backend/reports/lab/                      (directory)
  backend/routers/strategies.py
  backend/routers/firms.py
  backend/routers/system.py
  backend/services/lab_db.py                (SQLite helper)
  backend/services/strategy_scanner.py
  backend/services/vps_client.py            (typed wrapper over vps_agent HTTP)
  backend/services/evaluator.py             (the §7 logic)
  backend/services/backtest_runner.py       (background polling task)

Modified:
  backend/main.py                           (register new routers)
  backend/models.py                         (refactor per §3)
  backend/routers/backtests.py              (replace stub)
  backend/config.json                       (no changes likely)
```

### VPS (algos/markets/futures/lucid_flex/tools)

```
Modified:
  vps_agent.py                              (job-keyed + observability endpoints)
  vps_backtest_runner.py                    (write per-job results)
  
Removed/deprecated:
  backtest_config.json                      (no longer global — per-job now)
```

### Frontend (command-center/frontend)

```
Created:
  src/hooks/useLab.ts
  src/pages/BacktestDetail.tsx
  src/pages/StrategyDetail.tsx
  src/components/RunBacktestModal.tsx
  src/components/SystemHealthStrip.tsx
  src/components/EvaluationCard.tsx
  src/components/DailyPnLChart.tsx
  src/components/EquityCurveChart.tsx

Modified:
  src/pages/Backtests.tsx                   (rewrite — sub-tabs)
  src/components/Sidebar.tsx                (replace 2-dot strip with 5)
  src/types.ts                              (new types)
  src/App.tsx (or router file)              (new routes)
  src/hooks/useBacktests.ts                 (delete; superseded by useLab.ts)
```

---

## End of M1 spec

Stop, report, get a thumbs-up before starting M2. M2 covers the optimizer and
Monte Carlo. M3 covers overfitting and the multi-firm matrix UI.
