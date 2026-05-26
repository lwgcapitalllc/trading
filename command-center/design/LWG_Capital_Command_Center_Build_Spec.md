# LWG Capital Command Center — Build Spec

### Handoff document for Claude Code

This document specifies a local React web application that becomes the single
operational interface for all LWG Capital trading activity: smart-money wallet
research, algo bot management, backtesting, and stress testing.

**Read this whole document before writing code. Build in the order given in Part 9.**

---

## PART 0 — GROUND RULES (read first)

- **This app runs on localhost only.** No deployment, no auth, no HTTPS. It is a
  personal operator console on the owner's Mac. Do not add login screens, user
  accounts, or cloud hosting.
- **It replaces `algo.py`.** The existing Mac-side terminal control panel
  (`ALGO_CONTROL_PANEL_GUIDE.md`) is being retired. Every capability that panel
  had — start/stop/restart bots, view status, view logs — must exist in this app.
  Do not delete `algo.py` yet; it stays as a fallback until the Bots module is
  proven. But the app is the intended replacement.
- **Build it to scale.** This is not a smart-money viewer with extra tabs bolted
  on. It is an operations platform. Smart Money and Bot monitoring are the first
  two modules made fully functional. Every other module must be scaffolded as a
  real, navigable route with its data contract defined — not a "coming soon"
  placeholder with no structure.
- **The first build delivers two modules: Smart Money and Bots (monitoring).**
  Smart Money is the owner's top priority and is built completely. The Bots
  module is built completely for *monitoring* — the live status table is fully
  functional — but its *control actions* (start/stop/restart/emergency) ship as
  wired-but-stubbed. Rationale: monitoring is read-only and safe; the control
  actions kill and spawn live processes on the production VPS, and must not go
  live until the monitoring half has been observed reporting correctly. Backtests
  and Stress Tests are scaffolded. See Part 9 for the exact split.
- **Do not invent data.** Every number on screen comes from a real file or a real
  API response. If a data source does not exist yet, the module renders an empty
  state ("No runs found"), never fake sample data. The one exception is during
  local development: a clearly-labelled mock fixture file is acceptable, but it
  must be obviously fake and easy to delete.
- **Honest display.** This mirrors a rule from the trading specs: never style a
  result to look better than it is. A disqualified wallet is shown as
  disqualified. A failed backtest is shown as failed. The UI surfaces the truth,
  it does not market it.

---

## PART 1 — ARCHITECTURE

### The two-process model

A browser cannot read local files reliably, cannot run Python, and cannot SSH to
the VPS. So the app is **two processes**:

```
┌─────────────────────────┐         ┌──────────────────────────────┐
│  Frontend (React)        │  HTTP   │  Backend (FastAPI, Python)   │
│  Vite dev server         │ ──────► │  localhost:8000              │
│  localhost:5173          │ ◄────── │                              │
│                          │  JSON   │  - reads JSON/CSV/log files  │
│  - all UI, charts, tabs  │         │  - runs pipeline scripts     │
│  - talks ONLY to backend │         │  - SSHs to the VPS           │
│                          │         │  - wraps run_all.py etc.     │
└─────────────────────────┘         └──────────────────────────────┘
                                                  │
                                     ┌────────────┴───────────┐
                                     │  Local monorepo files  │
                                     │  SSH to forexvps       │
                                     │  SSH tunnel :8765      │
                                     │    → vps_agent.py      │
                                     └────────────────────────┘
```

**Why a backend now and not later.** The owner's vision is "an everything app to
control all operations." Reading files directly into the browser works for the
smart-money viewer today but cannot ever do `Restart bot`, `Run Stage 3`, or
`Trigger backtest combo`. Building the backend now means the frontend never has
to be re-architected. The frontend talks **only** to the backend. The backend is
the single place that touches the filesystem, runs scripts, and reaches the VPS.

### Repository placement

This lives inside the existing monorepo as a new top-level directory:

```
algos/
├── bots/                    ← existing
├── shared/                  ← existing
├── markets/                 ← existing
├── notifications/           ← existing
├── ...
└── command-center/          ← NEW — this app
    ├── frontend/            ← Vite + React + TS
    ├── backend/             ← FastAPI
    ├── README.md            ← how to run both processes
    └── start.sh             ← starts backend + frontend together
```

`start.sh` launches the FastAPI backend and the Vite dev server together, so the
owner runs one command and gets the whole app. Print both URLs on startup.

### Tech stack

**Frontend:**
- Vite + React 18 + TypeScript
- Tailwind CSS for styling
- React Router for navigation between modules
- TanStack Query (React Query) for all backend data fetching — gives caching,
  background refetch, and loading/error states for free
- Recharts for charts (bar, line, area, pie, scatter, equity-curve fan charts)
- lucide-react for icons

**Backend:**
- FastAPI + uvicorn
- pydantic models for every response shape (these models ARE the data contract)
- Plain Python file reads for JSON/CSV/log files
- `subprocess` to invoke existing pipeline scripts (`run_all.py`, the smart-money
  stage modules, `stress_test_suite.py` replacement, etc.)
- `paramiko` or shelling out to `ssh` for VPS commands — reuse whatever pattern
  `algo.py` already uses so behavior matches the retired panel exactly

### Configuration

One backend config file, `backend/config.py` or `backend/config.json`, holds all
machine-specific paths and constants. Nothing hardcoded in route handlers.

```json
{
  "monorepo_root": "/Users/alwg/algos",
  "smart_money_output_dir": "/Users/alwg/algos/markets/.../smart_money/output",
  "backtest_output_dir": "/Users/alwg/algos/markets/futures/lucid_flex/...",
  "instances_dir": "/Users/alwg/algos/markets/fx/instances",
  "ssh_alias": "forexvps",
  "vps_agent_tunnel": "http://localhost:8765"
}
```

The owner must be able to move the monorepo or rename a folder by editing this
one file and nothing else.

---

## PART 2 — APPLICATION SHELL & NAVIGATION

A persistent left sidebar with the modules below. Main content area on the right
renders the active module. A thin top bar shows app title, a global "last
refreshed" timestamp, and a manual refresh button.

| Module | Route | First build |
|---|---|---|
| Overview | `/` | Scaffold |
| Smart Money | `/smart-money` | **FULL** |
| Bots | `/bots` | **FULL — monitoring** (control actions stubbed) |
| Backtests | `/backtests` | Scaffold |
| Stress Tests | `/stress-tests` | Scaffold |
| Settings | `/settings` | Scaffold |

"Scaffold" means: the route exists, the page renders, the layout and section
headers are in place, the data-fetching hook is written and pointed at a backend
endpoint that returns an empty/not-implemented response, and an empty state is
shown. It must look like a real unfinished page, not a blank div.

### Design language

- Dark theme by default — this is a trading console, dark reduces eye strain on a
  panel left open all day. A light theme is a nice-to-have, not required for v1.
- Information-dense but not cluttered. Cards, tables, and charts. Generous use of
  numeric formatting (thousands separators, fixed decimals, % signs).
- Color semantics, consistent everywhere: green = good/profit/pass,
  red = bad/loss/fail, amber = warning/yellow-flag, gray = neutral/inactive.
- Status dots and PASS/FAIL pills, mirroring the language already used across the
  trading specs (KEEP/WARN/DISCARD, qualified/disqualified, RUNNING/STOPPED).

---

## PART 3 — MODULE: SMART MONEY  *(the one fully-built module)*

This is the priority. It visualizes the output of the Smart Money Replication
System (`smart_money_replication_system.md`) — a 5-stage pipeline that scans
crypto and forex traders and produces a ranked candidate pool.

### Data source

The pipeline writes JSON and CSV outputs. The backend reads them; it does not
re-implement any pipeline logic. Expected pipeline outputs (per its Stage 5.3):

- Full report JSON (the unified candidate pool)
- Full report CSV
- Per-stage logs (how many wallets passed/failed each filter)
- Disqualified-candidates log (with reasons)

The backend exposes these as clean typed endpoints. **If the exact output file
names/shapes are not yet finalized in the pipeline, define the contract here and
have the pipeline conform to it** — see the pydantic models in Part 7. The
frontend codes against the contract, not against whatever the files happen to
look like today.

### Sub-views (tabs within the Smart Money module)

**3.1 — Pool Overview**
The landing view. Answers "what does the latest run look like at a glance."
- Summary stat cards: total wallets/accounts scanned, total qualifying
  candidates, count by market (crypto vs forex), count by source (Hyperliquid,
  Solana, Ethereum, Myfxbook, FX Blue).
- A bar chart: candidates by source.
- A donut/pie: crypto vs forex split of the qualifying pool.
- A "run selector" — the pipeline can run many times; the user picks which run's
  output to view. Default to most recent. List runs by timestamp.
- A funnel chart or stepped bar showing attrition through the filters: scanned →
  passed 100-trade filter → passed 90-day age → passed monthly win-rate →
  survived disqualification filters → final pool. This directly visualizes the
  per-stage pass/fail logs and is exactly the kind of thing that is painful to
  read as a log file.

**3.2 — Rankings Table**
The Top 20 unified rankings (Stage 5.2). A sortable, filterable table:
- Columns: rank, wallet/account ID (truncated, copy-on-click), market, source,
  composite score, net growth %, peak drawdown, overall win rate, month-over-month
  consistency rating, trade count.
- Composite score shown as a number AND a small colored bar so the eye can scan
  relative strength.
- Filter controls: by market (crypto/forex/all), by source, by score range.
- Sort on any numeric column.
- Yellow-flag and strike indicators shown as small amber pills inline.
- Click a row → opens the Candidate Profile (3.3).
- The top 5 overall shortlist visually distinguished (e.g. a star or a gold accent
  on the rank cell).

**3.3 — Candidate Profile (detail view)**
The full intelligence report for one wallet/account (pipeline Step 1.7 / 5.2).
This is where the rich per-candidate data lives. Lay it out as sections:

*Header:* ID, market, source, composite score (large), rank, shortlist badge if
applicable, any strike/yellow flags called out prominently.

*Balance & Growth:* a line/area chart of month-over-month balance progression.
Stat cards for starting balance, ending balance, net growth %, peak balance,
lowest balance.

*Performance:* average win size vs average loss size (paired bars), average
risk/reward ratio, average drawdown per trade, peak drawdown. A small line chart
for the month-over-month win % trend with the 80% qualification line drawn as a
reference line — instantly shows whether they hold above threshold.

*Behavioral Patterns:* preferred trading days as a bar chart ranked by frequency.
Preferred instruments as a table ranked by frequency and win rate. Typical entry
time of day. Average hold time. Exit efficiency score shown as a gauge or labelled
bar. For forex candidates, also show preferred session (London/NY/Asian).

*Scoring Breakdown:* a small horizontal stacked bar or radar chart showing how the
composite score decomposes across the five weighted factors (win-rate consistency
25%, risk-adjusted return 25%, exit efficiency 20%, trade frequency 15%,
instrument/day consistency 15%). This makes "why is this wallet ranked here"
visible at a glance.

**3.4 — Disqualified Log**
A table of every disqualified candidate with the disqualification reason. The
pipeline spec is emphatic that nothing is silently dropped — so this view must
exist and be searchable/filterable by reason. Group or filter by reason
(e.g. "single trade > 40% of PnL", "drawdown exceeded 20%", "fewer than 3 active
weeks", "2 consecutive months below 80%").

**3.5 — Config (fully built)**
The smart-money pipeline already keeps every threshold in a single config file
(per its own spec: 80% win rate, 20% drawdown, 100 trades, 90 days, scoring
weights, strike rules). This sub-view is a form-based editor for that exact file
— a friendlier way to edit it than hand-editing JSON. **The pipeline does not
change.** It keeps reading the same file. The UI is just a second editor on it.

The form, grouped to mirror the pipeline's config structure:
- *Qualification thresholds:* min trades, min win rate %, max peak drawdown %,
  min active weeks per month, max single-trade share of PnL %, max average hold
  time, min account/wallet age (days).
- *Lookback tiers:* minimum / preferred / elite day counts.
- *Scoring weights:* the five factors as sliders — win-rate consistency,
  risk-adjusted return, exit efficiency, trade frequency, instrument/day
  consistency.
- *Strike rules:* months-below-threshold to yellow-flag, to disqualify, to
  reinstate.

**Validation is the point of this screen — not the buttons.** The form MUST
validate before it is allowed to save:
- The five scoring weights must sum to exactly 100. Show the running total live;
  block save until it is 100.
- Percentages are 0–100. Day counts and trade counts are positive integers.
- Lookback tiers must be ordered (minimum ≤ preferred ≤ elite).
Hand-editing the JSON file gives none of this; the form does, and that is what
makes editing-from-the-UI safer than editing the file directly.

**The config file is the single source of truth.** The UI must NOT keep its own
separate copy of these settings in app state or anywhere else. It reads the file
on open, writes the file on save, done. As long as the UI and the pipeline both
read and write the same file, they are always in agreement — there is no "sync"
step because there is nothing to sync.

**Saving writes the file locally only — it does NOT commit or push to git.**
See Part 11 for the full rationale. The Config tab shows a small "uncommitted
changes" indicator when the on-disk file differs from what is committed (the
backend runs `git status` on the file). Committing is a separate, deliberate
action the owner takes with a real commit message — never automatic on save.

A "Reset to last saved" and a "Reset to last committed" control are both useful
and safe to include.

### Smart Money — interactions beyond viewing

The module is primarily a viewer in the first build, but include the data-fetch
plumbing for one action: a **"Run Pipeline"** control (a button per stage, plus
"run all"). In the first build this calls a backend endpoint that returns
"not implemented" and the UI shows that honestly. The owner explicitly wants to
"search for smart money wallets" from this app eventually, so the button and its
endpoint exist from day one; only the backend implementation is deferred.

---

## PART 4 — MODULE: BOTS  *(fully built — monitoring; control actions stubbed)*

This module replaces the retired `algo.py` control panel. In the first build,
the **monitoring half is built completely** and the **control actions are
wired-but-stubbed**. Read the split carefully — it is deliberate.

### Why the split

Monitoring is read-only: it fetches state and displays it, and the worst failure
mode is a stale number. Control actions (`start`, `stop`, `restart`, `emergency`)
kill and spawn `python.exe` processes on the production VPS that are running real
demo-account bots. The first version of this app must not be allowed to do that
before its monitoring has been watched reporting correctly against the known-good
`algo.py` for a few days. So: build the buttons, build their endpoints' shape,
but the endpoints return HTTP 501 and the buttons show that honestly. Flipping
them on is a deliberate later step, not a v1 feature.

### Monitoring — fully built

Reproduces the live view from `ALGO_CONTROL_PANEL_GUIDE.md`:

- A live table of all trading bots: name, account, account type (demo/live),
  balance, status, uptime, daily P&L %. Data source: each instance's
  `bot_state.json` — the single source of truth, the same file `algo.py` and the
  Telegram bot read. Do not read any other file for these fields.
- Status shown as colored dots / pills: RUNNING green, STOPPED gray, ERROR red.
- A `day_locked` indicator per bot when the P&L tracker has locked the day.
- Daily P&L % colored green/red.
- Status of the scheduled jobs (Monitor, P&L Tracker, Reporter) and the Telegram
  process — a second small table, mirroring the panel's "Scheduled Jobs" and
  "Telegram" sections.
- The Demo / Live / All tab filter from the panel guide.
- Auto-refresh every 60 seconds (matching the panel), with the global manual
  refresh also triggering it. Show a "last refreshed" time.
- A per-bot **View Log** action — this one IS implemented, because reading a log
  file is read-only and safe. It opens the bot's `*_stdout.log` in a scrollable
  panel or modal.

**Critical design constraint carried over from the control panel guide:** all VPS
status is fetched in **one batched call** per refresh, never one SSH call per bot
row. The backend exposes a single `/bots/snapshot` endpoint that does the batched
VPS fetch (reuse `algo.py`'s `fetch_vps_snapshot()` approach) and returns the
whole `BotSnapshot`. The frontend renders every row, job, and the Telegram status
from that one payload. Per-row requests are a defect, not an option.

### Control actions — wired, stubbed

Build the buttons and their backend endpoints now, returning HTTP 501:

- Start all / Stop all / Restart all (via SYS_STARTUP coordinator) / Emergency
  stop / Manage individual bot.
- The UI shows these clearly as not-yet-enabled (e.g. disabled state with a
  tooltip, or a confirmation dialog that ends in "control actions are not enabled
  in this build"). They are visible so the layout is final and so enabling them
  later is a backend-only change.

The endpoints, when implemented later, wrap the exact same Task Scheduler / SSH
calls `algo.py` uses, so behavior matches the retired panel precisely.

---

## PART 5 — MODULE: BACKTESTS  *(scaffold)*

Scaffolded now, designed fully now. Visualizes the LucidFlex futures backtest
results (`LucidFlex_Bot_Suite_Build_Spec.md`).

The backtest pipeline (NT8 Strategy Analyzer → `analyze.py`) produces a results
table per strategy per instrument with a KEEP/WARN/DISCARD verdict, plus equity
curve data. The module must show:

- A results grid: one row per strategy/instrument combo (the 6 combos —
  ORB, VWAP_MR, Momentum across MNQ/MES/MGC/MCL), with the KEEP/WARN/DISCARD
  verdict as a colored pill.
- The tiered KPIs from the spec, grouped exactly as the spec groups them:
  - Tier 1 (prop-specific, most important): max drawdown vs limit with PASS/FAIL
    flag, simulated eval result (would-pass/would-fail + days taken), daily P&L
    distribution histogram, worst day / worst losing streak.
  - Tier 2 (edge quality): win rate, profit factor, avg win/loss, win:loss ratio,
    trade count, expectancy per trade.
  - Tier 3 (standard): total return, CAGR, Sharpe, Sortino, avg trade duration.
- An equity curve chart per combo.
- A daily P&L distribution histogram, with the 50%-of-total-profit consistency
  line flagged when relevant.
- A "Run Backtest" control: per-combo and run-all buttons, calling the backend,
  which wraps the existing `run_all.py --combo` / `--http` flow over the SSH
  tunnel to `vps_agent.py`. (Per the LucidFlex spec, combos run one at a time;
  the UI should reflect that — disable "run all" or make it sequential, and show
  a live status/log stream from `vps_agent.py`'s `/status`.)

First build: results grid UI, KPI card layout, chart components, all endpoints
returning empty/not-implemented.

---

## PART 6 — MODULE: STRESS TESTS  *(scaffold)*

Scaffolded now, designed fully now. Visualizes Monte Carlo stress-test output
(LucidFlex spec Part 7). Stress tests run only on backtest survivors.

Must show:
- Distribution of max drawdown across all runs: a histogram, with median, 95th
  and 99th percentile marked. The 99th-percentile (worst 1%) drawdown is the
  headline number — display it large with a PASS/FAIL against the LucidFlex
  max-loss limit.
- Probability of breaching the max-loss limit (big % stat, green if near 0).
- Probability of passing the eval (big % stat).
- Distribution of final P&L: histogram with median, 10th percentile, worst case.
- **Equity curve fan chart** — many simulated equity paths overlaid on one chart.
  Recharts can do this with many semi-transparent line series or an area band for
  percentile envelopes. This is the signature visual of the module.

First build: layout, the fan-chart component shell, KPI cards, endpoints
returning empty/not-implemented.

---

## PART 7 — DATA CONTRACTS (pydantic models = the contract)

Define these as pydantic models in the backend. The frontend mirrors them as
TypeScript interfaces. These shapes are the contract between the two processes
and between the app and the pipelines. If a pipeline's current output does not
match, the pipeline conforms to this — not the other way around.

### Smart Money

```
SmartMoneyRun
  run_id: str                 # timestamp-based
  generated_at: datetime
  total_scanned: int
  total_qualified: int
  by_market: dict[str, int]   # {"crypto": N, "forex": N}
  by_source: dict[str, int]   # {"hyperliquid": N, "myfxbook": N, ...}
  funnel: list[FunnelStage]   # ordered attrition stages

FunnelStage
  label: str                  # "Passed 100-trade filter"
  count_in: int
  count_out: int

SmartMoneyConfig                # the pipeline's config file, typed
  # qualification thresholds
  min_trades: int
  min_win_rate_pct: float       # e.g. 80
  max_drawdown_pct: float       # e.g. 20
  min_active_weeks_per_month: int
  max_single_trade_pnl_share_pct: float   # e.g. 40
  max_avg_hold_hours: float
  min_account_age_days: int
  # lookback tiers (days) — must be ordered min <= preferred <= elite
  lookback_min_days: int
  lookback_preferred_days: int
  lookback_elite_days: int
  # scoring weights — MUST sum to 100
  weight_winrate_consistency: float
  weight_risk_adjusted_return: float
  weight_exit_efficiency: float
  weight_trade_frequency: float
  weight_instrument_consistency: float
  # strike rules
  strike_months_to_yellow: int
  strike_months_to_disqualify: int
  strike_months_to_reinstate: int

ConfigGitStatus                 # for the "uncommitted changes" indicator
  file_path: str
  is_dirty: bool                # on-disk differs from last commit
  last_commit_hash: str | None
  last_commit_message: str | None
  last_commit_at: datetime | None

Candidate
  rank: int
  id: str                     # wallet address or account id
  market: str                 # "crypto" | "forex"
  source: str
  composite_score: float      # 1-100
  score_breakdown: dict[str, float]   # per-factor contribution
  starting_balance: float
  ending_balance: float
  net_growth_pct: float
  peak_balance: float
  lowest_balance: float
  monthly_balance: list[MonthlyPoint]
  overall_win_rate: float
  monthly_win_rate: list[MonthlyPoint]   # for the 80%-line chart
  avg_win: float
  avg_loss: float
  avg_rr: float
  peak_drawdown: float
  trade_count: int
  preferred_days: list[RankedItem]
  preferred_instruments: list[RankedItem]
  typical_entry_time: str
  avg_hold_time_hours: float
  exit_efficiency: float
  preferred_session: str | None      # forex only
  consistency_rating: str            # "improving" | "stable" | "declining"
  yellow_flags: list[str]
  strikes: list[str]
  is_shortlist: bool

DisqualifiedCandidate
  id: str
  market: str
  source: str
  reason: str
  stage: str                  # which stage/step removed it
```

### Bots

```
BotSnapshot
  fetched_at: datetime
  bots: list[BotStatus]
  scheduled_jobs: list[JobStatus]
  telegram: ProcessStatus

BotStatus
  name: str
  account: str
  account_type: str           # "demo" | "live"
  balance: float
  status: str                 # "RUNNING" | "STOPPED" | "ERROR"
  uptime_seconds: int | None
  daily_pnl_pct: float | None
  day_locked: bool
```

### Backtests

```
BacktestRun
  run_id: str
  generated_at: datetime
  combos: list[BacktestResult]

BacktestResult
  strategy: str
  instrument: str
  verdict: str                # "KEEP" | "WARN" | "DISCARD"
  # Tier 1
  max_drawdown: float
  max_loss_limit: float
  drawdown_pass: bool
  eval_result: str            # "would_pass" | "would_fail"
  eval_days: int | None
  daily_pnl: list[float]
  worst_day: float
  worst_losing_streak: int
  # Tier 2
  win_rate: float
  profit_factor: float
  avg_win: float
  avg_loss: float
  trade_count: int
  expectancy: float
  # Tier 3
  total_return: float
  cagr: float
  sharpe: float
  sortino: float
  avg_trade_duration_min: float
  equity_curve: list[EquityPoint]
```

### Stress Tests

```
StressTestResult
  strategy: str
  instrument: str
  runs: int
  max_dd_median: float
  max_dd_p95: float
  max_dd_p99: float
  prob_breach: float
  prob_pass_eval: float
  final_pnl_median: float
  final_pnl_p10: float
  final_pnl_worst: float
  equity_paths: list[list[EquityPoint]]   # the fan chart
```

Shared: `MonthlyPoint{month, value}`, `RankedItem{label, count, win_rate?}`,
`EquityPoint{index, equity}`, `JobStatus`, `ProcessStatus`.

---

## PART 8 — BACKEND API ENDPOINTS

All under `localhost:8000`. CORS open to `localhost:5173` only.

| Method | Endpoint | First build |
|---|---|---|
| GET | `/health` | working |
| GET | `/smart-money/runs` | working — list available runs |
| GET | `/smart-money/runs/{run_id}` | working — `SmartMoneyRun` |
| GET | `/smart-money/runs/{run_id}/candidates` | working — `list[Candidate]` |
| GET | `/smart-money/runs/{run_id}/candidates/{id}` | working — one `Candidate` |
| GET | `/smart-money/runs/{run_id}/disqualified` | working — `list[DisqualifiedCandidate]` |
| GET | `/smart-money/config` | working — `SmartMoneyConfig` (reads the file) |
| PUT | `/smart-money/config` | working — validates, then writes the file |
| GET | `/smart-money/config/git-status` | working — `ConfigGitStatus` |
| POST | `/smart-money/run` | stub — returns 501 not implemented |
| GET | `/bots/snapshot` | working — real batched VPS fetch |
| GET | `/bots/{name}/log` | working — reads `*_stdout.log` |
| POST | `/bots/start` `/bots/stop` `/bots/restart` `/bots/emergency` | stub — 501 |
| GET | `/backtests/runs` + `/backtests/runs/{id}` | stub — empty |
| POST | `/backtests/run` | stub — 501 |
| GET | `/stress-tests/results` | stub — empty |
| POST | `/stress-tests/run` | stub — 501 |
| GET | `/settings` + PUT `/settings` | working — read/write the config file |

"Working" = fully implemented, reads real files / does the real VPS fetch.
"Stub" = endpoint exists, correct shape, returns empty data or HTTP 501 so the
frontend can be built against it honestly. In build one the real work is the
smart-money GET endpoints, the smart-money config endpoints, and the two bot
*monitoring* endpoints (`/bots/snapshot`, `/bots/{name}/log`); the bot *control*
endpoints and all backtest/stress endpoints are stubs.

**`PUT /smart-money/config` must validate server-side before writing** — never
trust the form alone. Reject (HTTP 422 with a clear message) if the scoring
weights do not sum to 100, if any percentage is outside 0–100, if counts are not
positive, or if the lookback tiers are out of order. The frontend validates too,
for instant feedback, but the backend is the real gate. The endpoint writes the
file locally and does nothing with git — committing is a separate manual action.

---

## PART 9 — BUILD ORDER FOR CLAUDE CODE

Do each step, then stop and confirm before the next.

1. **Scaffold the monorepo directory.** `command-center/` with `frontend/` and
   `backend/` subfolders, `start.sh`, and a README explaining how to run it.
2. **Backend skeleton.** FastAPI app, `config.py`, CORS, `/health`, all pydantic
   models from Part 7, and every endpoint from Part 8 registered — the stubs
   returning empty/501, ready to fill in.
3. **Frontend skeleton.** Vite + React + TS + Tailwind + Router + React Query.
   The app shell from Part 2: sidebar, top bar, six routes, dark theme. Each route
   renders its scaffolded module page with section headers and empty states.
4. **Smart Money — backend.** Implement the real file-reading for all
   `/smart-money/runs*` GET endpoints against the pipeline's output files, plus
   the three `/smart-money/config*` endpoints (read, validated write, git-status).
   If the pipeline output shape needs adjusting to match Part 7, note exactly what
   and stop to confirm before changing pipeline files.
5. **Smart Money — frontend, fully built.** All five sub-views (Pool Overview,
   Rankings Table, Candidate Profile, Disqualified Log, Config) with every chart,
   table, and form in Part 3. The Config form must enforce the validation rules
   in Part 3.5 and show the uncommitted-changes indicator.
6. **Bots — backend monitoring.** Implement `/bots/snapshot` (the real batched
   VPS fetch, reusing `algo.py`'s approach) and `/bots/{name}/log`. Leave the
   control endpoints as 501 stubs.
7. **Bots — frontend monitoring, fully built.** The live bot table, scheduled-job
   and Telegram status, Demo/Live/All filter, 60s auto-refresh, and View Log,
   per Part 4. Build the control buttons in their disabled/stubbed state.
8. **Verify end to end.** Run the real smart-money pipeline (or its existing
   output) and confirm the Smart Money module displays it correctly. Confirm the
   Bots module reports live status matching `algo.py`. Stop and report.
9. **(Later, separate sessions)** Enable the bot control actions once monitoring
   is trusted; then flesh out Backtests, then Stress Tests.

Steps 1–8 are the first build. Step 9 is future work.

---

## PART 10 — WHAT NOT TO DO

- Do NOT make the frontend read local files or SSH directly. Everything goes
  through the backend.
- Do NOT fabricate data to fill a chart. Empty state, not fake state.
- Do NOT leave scaffolded modules as blank pages — they must be real routes with
  layout, headers, and empty states so the architecture is visible.
- Do NOT make per-row SSH calls in the Bots module — one batched snapshot only.
- Do NOT add authentication, cloud hosting, or HTTPS. This is a localhost tool.
- Do NOT delete `algo.py` — it stays as a fallback until the Bots module is done.
- Do NOT build the smart-money pipeline logic into the app. The app visualizes
  and triggers the pipeline; it does not reimplement it.
- Do NOT batch-run backtest combos — the LucidFlex spec requires one at a time.
- Do NOT hardcode paths in route handlers — everything machine-specific lives in
  the one config file.
- Do NOT over-build the scaffolded modules in the first pass. Smart Money and
  Bot monitoring are the only things finished now; Backtests and Stress Tests are
  scaffold-only.
- Do NOT enable the bot control actions in the first build — monitoring must be
  proven against `algo.py` first. Ship the buttons stubbed.
- Do NOT let the Config UI keep its own copy of the settings. It reads and writes
  the one pipeline config file — that file is the single source of truth.
- Do NOT auto-commit or auto-push when the config is saved. Saving writes the
  file locally; committing is a separate, deliberate action (see Part 11).
- Do NOT write threshold values into prose documentation. Docs describe the
  rules; the config file holds the numbers (see Part 11).
- Do NOT skip server-side validation on the config write. The form validating is
  not enough — the backend must reject an invalid config too.

---

## PART 11 — CONFIGURATION, DOCS, AND GIT

This part governs how the smart-money config is edited, how documentation stays
correct, and how config changes reach git. It exists because editing config from
a UI introduces three failure modes that must be designed against.

### Principle 1 — the config file is the single source of truth

The smart-money pipeline already keeps every threshold in one config file. The
Config UI (Part 3.5) is simply a second editor for that same file. There is no
"sync" problem to solve because there is nothing to sync: the UI reads the file,
writes the file, and the pipeline reads the same file. They cannot disagree.

The only way to break this is for the UI to keep its own copy of the settings.
It must not. No settings in app state, no second config file, no database row.
One file, both editors.

### Principle 2 — docs describe rules, the config holds values

Prose documentation must NOT contain live threshold numbers. The moment a value
is edited in the UI, any sentence quoting that number is wrong, and no automation
can reliably keep prose in sync with a JSON file.

So the split is:
- The **config file** is the source of truth for *what the numbers are*.
- The **docs** are the source of truth for *what the numbers mean* — they
  describe the rules and point to the config file for current values.

Example. Instead of "a wallet must have an 80% win rate and under 20% drawdown",
the doc says "a wallet must hold the win-rate threshold across every 30-day
window and stay under the max-drawdown threshold — current values in the
pipeline config file." The doc and the config never contradict because they
never overlap.

To make current values visible without hand-maintaining them, the pipeline
should emit a generated file each run — `config_used.md`, or the values stamped
into the run report — recording the exact config that run used. That file is
generated, always accurate, and never edited by hand.

**Action for this build:** when implementing the Config module, update
`smart_money_replication_system.md` so it no longer hardcodes threshold numbers
in prose — replace them with references to the config file. Note this change and
confirm before editing the pipeline doc.

### Principle 3 — commit the config, but never auto-commit

The config file SHOULD be committed to git and version-controlled. Its change
history is valuable: if a run produces odd results, `git log` on the config file
should explain what changed and when.

But the UI must NOT commit or push on save. A config form invites rapid tweaking
— nudge a weight, rerun, nudge again. If every save were a commit-and-push, the
`main` branch history would fill with noise. This also mirrors an existing
project rule: VPS backups deliberately go to a separate `backups` branch so
automated commits never touch `main`. An auto-pushing config form would violate
that same principle.

The correct flow:
- Saving in the UI writes the file locally. That is the entire save action.
- The Config tab shows an "uncommitted changes" indicator when the on-disk file
  differs from the last commit (backend runs `git status` on the file path).
- Committing is a separate, deliberate action the owner performs — with a real
  commit message describing the decision ("loosen drawdown filter to 15% — pool
  was too thin"). This can be done from the owner's normal git workflow; the app
  does not need to commit at all in the first build.

This keeps every config commit a recorded decision, not an artifact of dragging
a slider. Whether the app later grows an in-UI "commit config" button (with a
mandatory message field) is a future decision — it is explicitly NOT in the
first build. The first build only reads, validates, writes, and shows dirty
state.
