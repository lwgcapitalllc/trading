# M2 — Optimizer + Worthiness Scorer Build Spec
## Smart routing, instrument sweeps, parameter optimization

**For Claude Code.** Second of three milestones for the command center's
backtest lab. Read `backend/CLAUDE.md` and `frontend/CLAUDE.md` first, then
`Command_Center_Backtest_Engine_Design.md` for context. M1 is shipped; this
builds on top of it without breaking it.

---

## 0. Communication rules (carried from M1)

- Plain English in reports back to me. No code blocks unless I ask for them.
- When you need my input, ask one clear question with concrete options.
- After every approved change, update the relevant CLAUDE.md in the same
  session — backend changes → `backend/CLAUDE.md`, frontend → `frontend/CLAUDE.md`.
- Stale docs are worse than no docs.

---

## 1. What M2 delivers (acceptance checklist)

When this is done, all of these must work end-to-end from the command center
UI without any terminal commands:

- [ ] Every completed backtest has a Worthiness Score badge: Tier 1 (green
  "Stress Test"), Tier 2 (cyan "Optimize"), or Tier 3 (yellow "Discard").
- [ ] Clicking "Optimize" on a Tier 1 backtest shows a soft confirmation ("This
  strategy is already strong — optimization may overfit. Proceed?").
- [ ] Clicking "Optimize" on a Tier 3 backtest opens the warning modal with
  three options: Optimize anyway / Try a different instrument / Cancel.
- [ ] "Try a different instrument" checks the DB for the same strategy's
  results on other instruments. If a Tier 1/2 result exists for a different
  instrument, the modal suggests it with a "Run on that instrument" button.
  If no other instruments have been tested, the modal offers a "Run on all
  instruments" sweep.
- [ ] "Run on all instruments" triggers N parallel backtests (one per
  instrument in the firm's allowed list) with the same params, period, and
  firm evaluations. Each appears in the Runs list as it completes.
- [ ] "Optimize from this run" button on every completed backtest pre-fills
  the optimizer modal with that run's strategy / instrument / date range /
  firms. User expands single param values into ranges, picks mode + search
  method, hits Go.
- [ ] Optimizer has two modes (Eval / Funded) and three search methods (Auto /
  Brute Force / Genetic). Auto picks brute force for 2D grids, genetic for 3+D.
- [ ] Optimization Detail page renders: heatmap for 2D grids, top-10 ranked
  table for 3+D grids, per-param-set verdicts against the chosen firm.
- [ ] New `runner` field on the `strategies` table, defaulted to
  `"ninjatrader"` for all M1 strategies. Backend dispatcher uses it.
- [ ] All four CLAUDE.md files updated to reflect what's built.

---

## 2. Worthiness Scorer (build this first — it's the smallest delta with the
biggest UX impact)

### What it is

A function that runs on every completed backtest, computes a Tier 1/2/3 score
based on the run's KPIs, and stamps the run with a recommendation.

### Thresholds

```python
def compute_worthiness(run, firm) -> WorthinessTier:
    """
    Tier 1 (STRESS_TEST):
      - profit_factor > 1.3
      - max_drawdown <= firm.max_loss_eod
      - trade_count >= 50

    Tier 2 (OPTIMIZE):
      - profit_factor between 0.8 and 1.3
      - OR max_drawdown between (0.7 * firm.max_loss_eod) and (1.0 * firm.max_loss_eod)
      - trade_count >= 30

    Tier 3 (DISCARD):
      - profit_factor < 0.8
      - OR max_drawdown > firm.max_loss_eod
      - OR trade_count < 30 (insufficient signal)
    """
```

Edge cases:
- If the backtest has no trades, tier is `DISCARD` with reason "no_trades".
- If `trade_count < 30`, tier is `DISCARD` with reason "insufficient_signal".
- If multiple firm evaluations exist on the run, compute the score against the
  **strictest firm by `max_loss_eod`**. The badge shows the score; the firm
  used is shown on hover.

### Storage

Add to `backtest_runs` table:

```sql
ALTER TABLE backtest_runs ADD COLUMN worthiness_tier TEXT;
ALTER TABLE backtest_runs ADD COLUMN worthiness_reason TEXT;
ALTER TABLE backtest_runs ADD COLUMN worthiness_computed_against_firm TEXT;
```

Computed at the end of the backtest_runner background task, right after the
evaluations are inserted. No new endpoint — the score is part of the existing
`BacktestSummary` and `BacktestDetail` shapes.

### Pydantic additions

```python
# Add to models.py
class WorthinessScore(BaseModel):
    tier: str  # "TIER_1_STRESS_TEST" | "TIER_2_OPTIMIZE" | "TIER_3_DISCARD"
    reason: Optional[str] = None
    computed_against_firm: Optional[str] = None

# Add field to BacktestSummary and BacktestDetail
worthiness: Optional[WorthinessScore] = None
```

### Frontend display

In the Runs table (Backtests page → Runs tab), add a new column "Score" between
"Status" and "Net P&L". Pill-shaped badge:

- Tier 1: green pill, label "STRESS TEST"
- Tier 2: cyan pill, label "OPTIMIZE"
- Tier 3: yellow pill, label "DISCARD"

On hover, tooltip shows the reason and the firm used for scoring.

On the Backtest Detail page, the badge appears prominently next to the run
title.

---

## 3. `runner` field — forex insurance

### Schema change

```sql
ALTER TABLE strategies ADD COLUMN runner TEXT NOT NULL DEFAULT 'ninjatrader';
```

Backfill: set all existing strategies to `"ninjatrader"`.

### Backend dispatcher

In `services/vps_client.py`, the existing methods dispatch backtest jobs to the
NT8 VPS agent unconditionally. Refactor so the dispatch is keyed by runner:

```python
def trigger_backtest(strategy, request):
    if strategy.runner == "ninjatrader":
        return nt_agent_client.run_backtest(request)
    elif strategy.runner == "mt5":
        raise NotImplementedError("MT5 runner planned for forex; not built")
    else:
        raise ValueError(f"Unknown runner: {strategy.runner}")
```

The MT5 branch is a placeholder. When forex work starts, you'll wire up an
`mt5_agent_client` and the dispatcher already routes correctly.

### Strategy scanner

The current scanner reads NinjaScript `.cs` files. No change in M2 — all
strategies stay `runner="ninjatrader"`. The scanner just sets it explicitly on
insert.

### UI

`Strategy` detail page shows the runner as a small badge near the class name:
"Runs on: NinjaTrader". No interaction; informational.

---

## 4. "Run on all instruments" sweep

### What it does

Trigger N parallel backtests for the same strategy across every instrument the
firm allows. Same params, same date range, same firm evaluations.

### Endpoint

```
POST /backtests/sweep
Body:
{
  "strategy_id": "orb_lucidflex",
  "params": {...},
  "start_date": "...",
  "end_date": "...",
  "commission_per_side": 2.25,
  "slippage_ticks": 1,
  "firm_ids": ["lucidflex_50k_eval", "lucidflex_50k_funded"],
  "instruments": ["MES 06-26", "MNQ 06-26", ...]  // explicit list
}
Response: 202
{
  "sweep_id": "sw_abc123",
  "run_ids": ["bt_xxx", "bt_yyy", ...],  // one per instrument
  "status": "started"
}
```

### Storage

Light touch — sweep is just a grouping label, not a separate table. Add one
column to `backtest_runs`:

```sql
ALTER TABLE backtest_runs ADD COLUMN sweep_id TEXT;
```

All runs in the same sweep share a `sweep_id`. Index on it for fast retrieval.

### Backend flow

1. Validate strategy, firms, instruments
2. For each instrument, create a `backtest_runs` row with the shared `sweep_id`
3. Spawn the same async polling task as a single backtest, one per run
4. VPS agent handles concurrent jobs (already supports this from M1)
5. Each run completes independently; worthiness is computed per run
6. Frontend polls all sweep runs and renders them as they finish

### UI

When user clicks "Try a different instrument" on a Tier 3 modal:

- If no other backtests exist for this strategy on other instruments, show
  "Run on all instruments" button. Click → fires the sweep, navigates to a new
  Sweep Detail page that shows all child runs and their worthiness scores as
  they complete.

- If other backtests exist, show a small "Past results across instruments"
  table inside the modal, sorted by worthiness tier, with a "Run on [best
  instrument]" button as the primary action.

### Sweep Detail page

Route: `/backtests/sweeps/:sweepId`

Layout:
- Header: strategy name, date range, firms, "X of Y instruments complete"
  status bar
- Live-updating table: instrument | status | net_pnl | max_dd | worthiness |
  actions ("View" → backtest detail)
- Sorted by worthiness tier descending — the most promising pairings rise to
  the top automatically as they finish

This page is the second-most-important UI in M2 after the optimizer itself.
It's where instrument suitability becomes visible at a glance.

---

## 5. The Optimizer

### Endpoint

```
POST /optimizations/run
Body:
{
  "strategy_id": "orb_lucidflex",
  "instrument": "MNQ 06-26",
  "start_date": "...",
  "end_date": "...",
  "commission_per_side": 2.25,
  "slippage_ticks": 1,
  "firm_id": "lucidflex_50k_eval",
  "mode": "eval",                     // "eval" | "funded"
  "search_method": "auto",            // "auto" | "brute" | "genetic"
  "param_grid": {
    "ORMinutes": {"min": 5, "max": 60, "step": 5},
    "TpMultiple": {"min": 1.0, "max": 3.0, "step": 0.25},
    "OneTradePer": [false, true]      // discrete list
  }
}
Response: 202
{
  "optimization_id": "opt_xxx",
  "status": "started",
  "estimated_runs": 144
}
```

### Search method "Auto"

```python
def pick_search_method(param_grid):
    dims = len(param_grid)
    if dims <= 2:
        return "brute"
    else:
        return "genetic"
```

User can always override via `search_method` in the request.

### Storage

```sql
CREATE TABLE optimizations (
  optimization_id   TEXT PRIMARY KEY,
  strategy_id       TEXT NOT NULL,
  instrument        TEXT NOT NULL,
  start_date        TEXT NOT NULL,
  end_date          TEXT NOT NULL,
  commission_per_side REAL NOT NULL,
  slippage_ticks    INTEGER NOT NULL,
  firm_id           TEXT NOT NULL,
  mode              TEXT NOT NULL,
  search_method     TEXT NOT NULL,
  param_grid        TEXT NOT NULL,   -- JSON
  status            TEXT NOT NULL,
  estimated_runs    INTEGER NOT NULL,
  completed_runs    INTEGER NOT NULL DEFAULT 0,
  best_run_id       TEXT,            -- run with the highest objective score
  created_at        INTEGER NOT NULL,
  completed_at      INTEGER,
  FOREIGN KEY (strategy_id) REFERENCES strategies(id),
  FOREIGN KEY (firm_id) REFERENCES firms(id)
);

-- Link backtest runs to their parent optimization
ALTER TABLE backtest_runs ADD COLUMN optimization_id TEXT;
```

Index `optimization_id` for fast retrieval of child runs.

### Objective functions

In `services/objectives.py`:

```python
def eval_pass_probability(run, firm):
    """
    For eval mode. Returns a score 0.0 to 1.0.
    1.0 = run hit profit target before any drawdown breach
    0.0 = run breached drawdown without hitting target

    Uses the simulated_eval_days field from the evaluation against this firm.
    A param set that hits target in fewer days scores higher.
    """
    eval = get_eval(run.run_id, firm.id)
    if not eval.drawdown_pass:
        return 0.0
    if not eval.target_pass:
        return 0.5 * (run.net_pnl / firm.profit_target)  # partial credit
    # Bonus for hitting target quickly
    speed_bonus = max(0, 1.0 - (eval.simulated_eval_days / 30))
    return 1.0 + 0.5 * speed_bonus

def funded_sharpe_under_drawdown(run, firm):
    """
    For funded mode. Returns the run's Sharpe ratio,
    but if the run breaches max_loss_eod, returns -infinity (disqualified).
    """
    if run.max_drawdown > firm.max_loss_eod:
        return float("-inf")
    return run.sharpe or 0.0
```

These are the M2 objectives. Easy to add more later by extending the
`OBJECTIVES` dict. Each one returns a score where higher = better; the
optimizer picks the highest-scoring param set.

### VPS agent extension

The existing `vps_agent.py` handles single backtests. Add:

```
POST /optimizations    (drives NT8 Optimizer for a full param grid)
GET  /optimizations/{id}/status
GET  /optimizations/{id}/results
```

The NT8 Optimizer already exists in the GUI — find the right pywinauto path
to drive it. Critical pieces:
- Selecting the strategy in the optimizer
- Setting the optimization type (Exhaustive = brute, Genetic = genetic)
- Entering the param ranges (NT has a different UI for each param)
- Hitting Run, waiting for completion
- Reading the result table or XML log

This is the heaviest single piece of M2 work. Budget for it accordingly. If NT
Optimizer automation is painful, fallback: drive multiple single backtests
from our side (we have the M1 plumbing for that), each with one param combo.
Slower but guaranteed to work.

**Decision for Claude Code:** Try NT Optimizer first. If pywinauto can't
reliably drive it within ~2 hours of attempted work, fall back to multi-call
brute force using the existing single-backtest endpoint. Document which path
you took and why in `backend/CLAUDE.md`.

### Backend flow

1. POST `/optimizations/run` arrives
2. Validate; insert `optimizations` row with status="running"
3. Compute `estimated_runs` from the grid
4. Spawn background task that calls VPS agent
5. As each child run completes, insert into `backtest_runs` with the
   `optimization_id` set
6. Compute the worthiness score AND the chosen objective score for each child
7. When all complete, update `optimizations.best_run_id` to the child with
   the highest objective score; status="complete"
8. Frontend polls and renders

### Tier guards in the optimizer trigger

Before kicking off an optimization, check the source backtest's worthiness:

- Tier 1: show soft confirm "This strategy is already strong (PF X.X,
  drawdown $X). Optimization may overfit. Proceed?"
- Tier 2: no friction, fire away
- Tier 3: show full warning modal with instrument suggestions (see §6)

These are UX guards in the frontend, not blocking backend checks. The backend
will still run any optimization the user confirms.

---

## 6. Tier 3 warning modal (the smart routing piece)

### Trigger

When user clicks "Optimize from this run" on a Tier 3 backtest.

### Modal layout

```
┌─ Optimize Tier 3 Strategy ───────────────────────────────────┐
│                                                               │
│  This strategy scored Tier 3 (DISCARD) on MNQ 06-26.          │
│  Reason: profit_factor 0.34 (below 0.8 threshold)             │
│                                                               │
│  Optimizing a Tier 3 strategy rarely changes the outcome.     │
│  Before optimizing, consider:                                 │
│                                                               │
│  ┌─ Past results across instruments ──────────────────────┐  │
│  │  Instrument    Worthiness        Date tested            │  │
│  │  MGC 06-26     ● TIER 1 (PASS)   2026-05-29  [Run] →    │  │
│  │  MES 06-26     ● TIER 2          2026-05-29  [Run] →    │  │
│  │  MNQ 06-26     ● TIER 3 (THIS)                          │  │
│  │  MCL 06-26     not tested                               │  │
│  │  MYM 06-26     not tested                               │  │
│  │  M2K 06-26     not tested                               │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                               │
│  [ Run on all untested instruments (3 backtests) ]            │
│                                                               │
│  ─────────────────────────────────────────────────────────    │
│                                                               │
│  Still want to optimize on MNQ?                               │
│                                                               │
│        [ Cancel ]  [ Optimize MNQ anyway ]                    │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

Backend support:

```
GET /strategies/{id}/instrument_summary?firm_id={firm}&start_date=...&end_date=...
Response:
{
  "instrument_results": [
    {
      "instrument": "MGC 06-26",
      "best_worthiness": "TIER_1_STRESS_TEST",
      "best_run_id": "bt_xxx",
      "tested_at": "..."
    },
    ...
  ],
  "untested_instruments": ["MCL 06-26", "MYM 06-26", "M2K 06-26"]
}
```

The frontend uses this to populate the modal. "Run" buttons on tested
instruments pre-fill the optimizer with that instrument. "Run on all
untested" fires a sweep over just the untested set.

### Edge case: no past results at all

If `instrument_results` is empty (strategy has only ever been tested on this
one instrument), the modal shows:

> "This strategy has only been tested on MNQ. Consider running it on the
> firm's other allowed instruments before optimizing."
>
> [ Run sweep on all 5 other instruments ] [ Optimize MNQ anyway ] [ Cancel ]

---

## 7. Optimization Detail page

### Route

`/backtests/optimizations/:optimizationId`

### Layout

**Header section:**
- Optimization ID, status, progress (X of Y runs complete)
- Strategy name, instrument, date range, firm, mode, search method
- "Best param set" callout — the winning param set highlighted, with its
  net_pnl, max_dd, worthiness tier, objective score

**Visualization section (depends on grid dimensionality):**

For 2D grids:
- Heatmap. X-axis = param A values, Y-axis = param B values. Color = objective
  score (green = high, red = low). Hover any cell to see that param set's full
  KPIs. Click to navigate to that child backtest's detail page.

For 3+D grids:
- Top-10 table sorted by objective score descending. Columns: rank, all param
  values, net_pnl, max_dd, sharpe, worthiness, objective_score, actions
  (View / Stress Test).
- Below the table: "View all N results" expands to the full sortable table.

**Per-param-set actions:**
- "View" → child backtest detail
- "Stress Test" → greyed out with tooltip "Available in M3"

**Download:**
- "Export CSV" — full N-row table of all params + KPIs + objective scores

### Component reuse

Heavy lifting only. Heatmap is a new component — `OptimizationHeatmap.tsx`,
built with Recharts (treemap or a hand-rolled SVG grid). Top-10 table reuses
the existing run row pattern from the Runs table but with the optimization-
specific columns added.

---

## 8. Backend file layout (additions)

```
backend/
├── routers/
│   ├── optimizations.py        ← NEW: optimizer endpoints
│   ├── sweeps.py               ← NEW: instrument sweep endpoints
│   └── (existing files)
├── services/
│   ├── worthiness.py           ← NEW: scoring function
│   ├── objectives.py           ← NEW: eval-pass-prob, funded-sharpe
│   ├── optimization_runner.py  ← NEW: background polling for optimizations
│   ├── sweep_runner.py         ← NEW: fans out N parallel backtests
│   └── (existing files)
└── (existing files)
```

Update `services/backtest_runner.py` to call `worthiness.compute()` after
evaluations finish.

Update `services/vps_client.py` to add the runner dispatcher pattern.

---

## 9. Frontend file layout (additions)

```
frontend/src/
├── pages/
│   ├── OptimizationDetail.tsx       ← NEW
│   ├── SweepDetail.tsx              ← NEW
│   └── (existing)
├── components/
│   ├── WorthinessBadge.tsx          ← NEW: the pill component
│   ├── OptimizationHeatmap.tsx      ← NEW: 2D grid viz
│   ├── Tier3WarningModal.tsx        ← NEW: the smart-routing modal
│   ├── OptimizeButton.tsx           ← NEW: wraps the tier-aware trigger logic
│   └── (existing)
└── hooks/
    └── useLab.ts                    ← UPDATE: add optimization + sweep hooks
```

The Backtests page gains a fourth tab: **Optimizations**. Same sub-tab pattern
as Strategies / Runs / Firms. Lists all optimization runs, sortable by
created_at, status, strategy.

Sidebar: nothing changes. Backtests still has Strategies / Runs / Firms /
Optimizations as sub-tabs.

---

## 10. Build order

Strict sequence. Stop and report after each milestone:

1. **Worthiness scorer end-to-end.** Schema migration, scoring function, badges
   in Runs table. Run a backtest, see the badge. Smallest unit, biggest
   immediate UX win.

2. **`runner` field + dispatcher refactor.** Smallest backend change, lays
   groundwork for forex.

3. **Sweep flow end-to-end.** Backend endpoint, sweep runner, Sweep Detail
   page. Trigger a sweep of ORB across all 6 LucidFlex instruments, see them
   all come back with worthiness scores. Already a major win even without the
   optimizer.

4. **Tier 3 warning modal + instrument summary endpoint.** Click "Optimize"
   on a Tier 3 backtest, see the modal route you to a better instrument.

5. **Optimizer backend.** Endpoint, optimization_runner, VPS agent integration
   (try NT Optimizer driving; fall back to multi-call brute force if needed).

6. **Optimizer frontend.** Optimize modal, Optimizations tab, Optimization
   Detail page with heatmap and top-10 table.

7. **End-to-end smoke test:** run a real optimization on ORB / MGC / 2 years
   / LucidFlex 50k Eval / brute force / a 3x3 grid of ORMinutes and
   TpMultiple. Verify: 9 child runs appear in DB, each with their own
   worthiness score, heatmap renders, best_run_id is set correctly.

After step 7, stop. Bring me back: the screenshot of the heatmap, the
worthiness badges on a Runs view, the Sweep Detail page from step 3, and a
plain-English summary of any decisions you had to make.

---

## 11. What NOT to do in M2

- Don't build Monte Carlo or stress testing — that's M3.
- Don't build walk-forward — that's M3.
- Don't add more firms — LucidFlex stays the only firm until M3.
- Don't auto-run sweeps when strategies are scanned. Manual only, per the
  user's instruction.
- Don't optimize Tier 1 strategies silently — the soft confirmation is the
  guard. (User can still proceed, but should be reminded.)
- Don't change the M1 backtest flow. Sweep and optimization are layered on
  top of it.
- Don't introduce new external libraries beyond what M1 has. Recharts handles
  the heatmap (treemap or custom SVG).

---

## 12. Update CLAUDE.md files at the end

Both `backend/CLAUDE.md` and `frontend/CLAUDE.md` need updates:

**Backend additions:**
- New routers: `optimizations.py`, `sweeps.py`
- New services: `worthiness.py`, `objectives.py`, `optimization_runner.py`,
  `sweep_runner.py`
- Updated tables: `backtest_runs` (added worthiness fields, sweep_id,
  optimization_id), `strategies` (added runner)
- New table: `optimizations`
- The `runner` dispatcher pattern in `vps_client.py`
- "What's built" section gains: worthiness scoring, sweeps, optimizer
- NT Optimizer pywinauto path documented OR fallback (whichever was used)

**Frontend additions:**
- New pages: OptimizationDetail, SweepDetail
- New components: WorthinessBadge, OptimizationHeatmap, Tier3WarningModal,
  OptimizeButton
- "What's built" section gains: worthiness badges, smart routing on Tier 3,
  optimizer UI

This is non-optional. M3 will be built on top of these docs.

---

## End of M2 spec

Sequential to M3. Don't start M3 until I've reviewed M2's smoke test results.
