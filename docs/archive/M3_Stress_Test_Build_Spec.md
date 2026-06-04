# M3 — Stress Testing, Robustness Grading, Ruleset Abstraction
## Build Spec

**For Claude Code.** Third and final milestone of the command center's
backtest lab. Read `backend/CLAUDE.md` and `frontend/CLAUDE.md` first, then
`Command_Center_Backtest_Engine_Design.md` for context. M1 + M2 are shipped;
this builds on top of them.

---

## 0. Communication rules (carried from M1 + M2)

- Plain English in reports back to me. No code blocks unless I ask for them.
- When you need my input, ask one clear question with concrete options.
- After every approved change, update the relevant CLAUDE.md in the same
  session — backend changes → `backend/CLAUDE.md`, frontend → `frontend/CLAUDE.md`.
- Stale docs are worse than no docs.

---

## 1. What M3 delivers (acceptance checklist)

When this is done, all of these must work end-to-end from the command center
UI without any terminal commands:

- [ ] Every completed backtest can be Monte Carlo stress-tested. Auto-runs on
  optimizer winners and on Tier 1 backtests; manual button on any completed
  backtest.
- [ ] Stress test produces a distribution of outcomes from ~10,000 trade
  reshuffles + 1,000 bootstrap resamples. Output: median final PnL, worst 1%
  drawdown, worst 5% drawdown, probability of breaching ruleset's max loss,
  probability of passing the eval.
- [ ] Walk-forward analysis: system runs 5 sliding windows (configurable),
  reports in-sample vs out-of-sample Sharpe and PnL for each window.
- [ ] Parameter sensitivity: re-runs the strategy with each parameter shifted
  ±10% and ±25%, reports performance degradation per parameter.
- [ ] Robustness grade A–F computed from Monte Carlo + walk-forward + sensitivity
  results, displayed as a letter badge alongside the worthiness Tier badge.
- [ ] Deployment gates: A or B required to mark a strategy "Ready for Eval";
  C minimum to deploy to demo; D/F shows warning with reasons.
- [ ] Pre-Deployment Checklist on any graded strategy — 5 static checkboxes
  user manually confirms before marking ready.
- [ ] **Ruleset abstraction shipped:** `firms` table renamed to `rulesets` (or
  semantically expanded with `ruleset_type` field), supporting `prop_eval`,
  `prop_funded`, `personal`, `demo`. Existing LucidFlex rows migrated cleanly.
  UI relabeled to "Ruleset" / "Trading Account" instead of "Firm" where
  appropriate.
- [ ] New "Stress Tests" tab under Backtests (no longer "Soon"). New
  StressTest Detail page with all visualizations.
- [ ] All three additions from the YouTube debrief: regime_tag stub field on
  daily_pnl, correlation note on multi-instrument grades, Pre-Deployment
  Checklist UI.
- [ ] All four CLAUDE.md updated to reflect what's built.

---

## 2. Ruleset abstraction (do this FIRST — it's a schema rename + most
breakage-prone change in M3)

### What changes

The `firms` table is renamed `rulesets`. New `ruleset_type` field with values
`prop_eval`, `prop_funded`, `personal`, `demo`. Existing LucidFlex rows
migrate to `prop_eval` or `prop_funded` based on their current `account_tier`.

New optional fields on `rulesets` to support non-prop rulesets:

- `daily_loss_cap` (integer, USD) — same as `max_loss_eod` for prop firms,
  but explicit for personal rulesets
- `weekly_loss_cap` (integer, USD) — new
- `daily_profit_goal` (integer, USD) — info only, not pass/fail
- `description` (text) — free-form notes about the ruleset

### Migration

```sql
ALTER TABLE firms RENAME TO rulesets;
ALTER TABLE rulesets ADD COLUMN ruleset_type TEXT NOT NULL DEFAULT 'prop_eval';
ALTER TABLE rulesets ADD COLUMN daily_loss_cap INTEGER;
ALTER TABLE rulesets ADD COLUMN weekly_loss_cap INTEGER;
ALTER TABLE rulesets ADD COLUMN daily_profit_goal INTEGER;
ALTER TABLE rulesets ADD COLUMN description TEXT;

-- Backfill: rows with account_tier='funded' → 'prop_funded', else 'prop_eval'
UPDATE rulesets SET ruleset_type = 'prop_funded' WHERE account_tier = 'funded';
UPDATE rulesets SET ruleset_type = 'prop_eval' WHERE account_tier = 'eval';

-- Copy max_loss_eod into daily_loss_cap so the field is populated
UPDATE rulesets SET daily_loss_cap = max_loss_eod WHERE daily_loss_cap IS NULL;
```

Keep the `account_tier` field — it's still useful for prop rulesets to know
eval vs funded. `ruleset_type` is the broader category.

### Pydantic refactor

- Rename `Firm` model → `Ruleset` model
- Add fields: `ruleset_type`, `daily_loss_cap`, `weekly_loss_cap`,
  `daily_profit_goal`, `description`
- Rename router endpoints: `/firms` → `/rulesets`. Add a redirect from
  `/firms` → `/rulesets` for backward compatibility in M3 only; deprecate
  after M3.
- All references in `BacktestRunRequest.evaluate_firms` → `evaluate_rulesets`
- `Evaluation` table: rename `firm_id` → `ruleset_id`

### Evaluator logic update

The evaluator must branch on `ruleset_type`:

```python
def evaluate(backtest, ruleset):
    drawdown_pass = backtest.max_drawdown <= ruleset.daily_loss_cap
    
    if ruleset.ruleset_type == "prop_funded":
        # Funded: just don't blow up
        if not drawdown_pass:
            return Evaluation(verdict="DISCARD", ...)
        return Evaluation(verdict="PASS", ...)
    
    elif ruleset.ruleset_type == "prop_eval":
        # Eval: hit target before drawdown, follow consistency
        target_pass = backtest.net_pnl >= ruleset.profit_target
        consistency_pass = check_consistency(backtest, ruleset.consistency_pct)
        # ... existing logic
    
    elif ruleset.ruleset_type == "personal":
        # Personal: did we stay within daily/weekly caps?
        # No target requirement — verdict based on capital preservation + growth
        weekly_pnl_pass = check_weekly_cap(backtest, ruleset.weekly_loss_cap)
        if drawdown_pass and weekly_pnl_pass:
            verdict = "PASS"
        elif not drawdown_pass:
            verdict = "DISCARD"  # blew up
        else:
            verdict = "WARN"  # weekly limit breached but daily OK
    
    elif ruleset.ruleset_type == "demo":
        # Demo: info only, just report P&L; never DISCARD
        verdict = "PASS" if backtest.net_pnl > 0 else "WARN"
```

### UI rename

Search the frontend for "firm" / "Firm" and replace with "ruleset" / "Ruleset"
where the user-facing meaning is generic. Keep "Prop firm" only where the
context specifically refers to a prop firm (e.g. the Run Backtest modal can
still group by category: "Prop Firm Challenges" vs "Personal Accounts").

Specific renames:
- Sidebar nav doesn't change (Backtests stays)
- Sub-tabs: "Firms" tab → "Rulesets" tab
- Modal labels: "Evaluate against firm" → "Evaluate against ruleset"
- Type badge appears on every ruleset row: PROP EVAL / PROP FUNDED / PERSONAL / DEMO

### Seed a personal ruleset for testing

In addition to the existing LucidFlex rows, seed one example personal ruleset
so users can see what the abstraction enables:

```json
{
  "id": "personal_futures_10k_example",
  "name": "Personal $10k Futures (Example)",
  "ruleset_type": "personal",
  "account_size": 10000,
  "profit_target": 0,
  "max_loss_eod": 200,           // $200/day stop
  "daily_loss_cap": 200,
  "weekly_loss_cap": 700,         // $700/week stop
  "daily_profit_goal": 150,       // info only
  "drawdown_type": "static",
  "consistency_pct": null,
  "min_trading_days": null,
  "force_flat_time_et": "15:50",
  "allowed_instruments": ["MES", "MNQ", "MGC", "MCL"],
  "max_contracts": {"any": 2},
  "platform_support": ["NinjaTrader", "Tradovate"],
  "account_tier": "live",
  "description": "Example template — adjust limits to match your real capital and risk tolerance.",
  "notes": "Seed example for the personal ruleset type. Edit or delete as needed."
}
```

---

## 3. Monte Carlo stress test

### What it is

Takes a backtest's actual trades and runs 10,000 reshuffles + 1,000 bootstrap
resamples to produce a distribution of outcomes. Pure Python — no NT
involvement.

### Storage

```sql
CREATE TABLE stress_tests (
  stress_test_id    TEXT PRIMARY KEY,
  run_id            TEXT NOT NULL,            -- parent backtest
  ruleset_id        TEXT,                     -- ruleset evaluated against (optional)
  status            TEXT NOT NULL,            -- 'running' | 'complete' | 'failed_*'
  created_at        INTEGER NOT NULL,
  completed_at      INTEGER,
  -- Monte Carlo results
  num_simulations    INTEGER NOT NULL DEFAULT 10000,
  num_bootstrap      INTEGER NOT NULL DEFAULT 1000,
  median_final_pnl  REAL,
  pct5_final_pnl    REAL,
  pct1_final_pnl    REAL,
  median_max_dd     REAL,
  pct5_max_dd       REAL,
  pct1_max_dd       REAL,
  prob_breach       REAL,                     -- 0.0-1.0: probability of breaching ruleset's max loss
  prob_pass_eval    REAL,                     -- 0.0-1.0: probability of passing the eval (if applicable)
  -- Walk-forward results
  walk_forward_windows INTEGER NOT NULL DEFAULT 5,
  walk_forward_summary TEXT,                  -- JSON: [{window: 1, is_pnl, oos_pnl, is_sharpe, oos_sharpe}, ...]
  walk_forward_degradation REAL,              -- avg drop in OOS Sharpe vs IS Sharpe
  -- Parameter sensitivity results
  sensitivity_summary TEXT,                   -- JSON: {param_name: {shift_pct: pnl_delta, ...}, ...}
  sensitivity_max_degradation REAL,           -- worst case % drop
  -- Robustness grade
  grade             TEXT,                     -- 'A' | 'B' | 'C' | 'D' | 'F'
  grade_reasons     TEXT,                     -- JSON list of plain-English reasons
  -- File references (heavy data)
  equity_paths_path TEXT,                     -- 100 sampled equity paths
  distribution_path TEXT,                     -- full distribution histograms
  FOREIGN KEY (run_id) REFERENCES backtest_runs(run_id),
  FOREIGN KEY (ruleset_id) REFERENCES rulesets(id)
);
CREATE INDEX idx_stress_tests_run ON stress_tests(run_id);
CREATE INDEX idx_stress_tests_grade ON stress_tests(grade);
```

### Backend

New router: `routers/stress_tests.py`.

Endpoints:
```
GET    /stress-tests                            → list, filter by run_id, grade
GET    /stress-tests/{stress_test_id}           → detail with paths to chart data
POST   /stress-tests/run                        → trigger on a backtest_run
DELETE /stress-tests/{stress_test_id}           → cleanup
```

New service: `services/stress_tester.py` — pure Python, no external deps
beyond numpy and pandas.

```python
def run_monte_carlo(trades, num_sims=10000, num_bootstrap=1000):
    """
    trades: list of trade dicts with at least pnl_usd
    Returns: dict with median/pct5/pct1 final_pnl, median/pct5/pct1 max_dd,
             and a sample of 100 equity curves.
    """

def run_walk_forward(strategy_id, instrument, params, full_range, ruleset_id, num_windows=5):
    """
    Splits full_range into N sliding windows. For each:
      - Train period: 70% of window
      - Test period: 30% of window
    Triggers N backtests via the existing VPS agent + backtest_runner flow.
    Returns: list of {window_num, is_pnl, oos_pnl, is_sharpe, oos_sharpe}
    """

def run_sensitivity(strategy_id, instrument, params, ruleset_id):
    """
    For each parameter in params:
      - Run backtest with param shifted +10%, -10%, +25%, -25%
    Compare results.
    Returns: {param_name: {shift: delta, ...}, ...}
    """

def compute_grade(monte_carlo_results, walk_forward, sensitivity, ruleset):
    """
    A: worst 1% Monte Carlo passes eval, walk-forward IS-vs-OOS degradation ≤20%,
       sensitivity max degradation ≤25%
    B: worst 5% passes, walk-forward degradation ≤30%, sensitivity ≤40%
    C: median passes but worst 5% doesn't, walk-forward shows degradation
    D: only median passes, worst 5% breaches drawdown
    F: median fails entirely
    Returns: grade ('A'-'F') + list of reasons in plain English
    """
```

### Auto-trigger logic

The backtest_runner background task is extended:
- When a backtest completes AND its worthiness is Tier 1 → auto-trigger stress test
- When an optimization completes AND its best_run is found → auto-trigger stress test on best_run

Manual trigger button stays available on every completed backtest (no auto needed if user already runs it).

### Walk-forward implementation

Walk-forward runs as N parallel backtests via the existing `services/backtest_runner.py`. Each window's `train` and `test` get their own `backtest_runs` row (with a `walk_forward_window_id` field to link them). The stress_tester aggregates the results once they finish.

This means walk-forward is **slow** — N backtests run sequentially through NT. Budget accordingly. For M3, default N=5 and warn the user that walk-forward takes ~10× a single backtest's time.

### Sensitivity implementation

Same pattern — each parameter perturbation is its own backtest. Default 4 perturbations per parameter (×±10%, ×±25%). For a strategy with 3 parameters → 12 backtests total per sensitivity test.

Can be slow. Document the time cost. Skip if it would take >1 hour estimated.

---

## 4. Robustness grading (the gate)

### Grading rules

Implemented in `compute_grade()` above. Pseudocode:

```python
def compute_grade(mc, wf, sens, ruleset):
    reasons = []
    
    # A grade: worst 1% Monte Carlo passes eval
    pct1_passes = (mc.pct1_max_dd <= ruleset.max_loss_eod)
    walk_forward_solid = (wf.walk_forward_degradation < 0.20)
    sensitivity_solid = (sens.max_degradation < 0.25)
    
    if pct1_passes and walk_forward_solid and sensitivity_solid:
        reasons.append("Worst 1% of Monte Carlo simulations stays under ruleset limit")
        reasons.append(f"Walk-forward degradation only {wf.walk_forward_degradation*100:.0f}% from IS to OOS")
        reasons.append(f"Parameter sensitivity worst case is {sens.max_degradation*100:.0f}% drop")
        return ("A", reasons)
    
    # B grade: worst 5% Monte Carlo passes eval
    pct5_passes = (mc.pct5_max_dd <= ruleset.max_loss_eod)
    walk_forward_ok = (wf.walk_forward_degradation < 0.30)
    sensitivity_ok = (sens.max_degradation < 0.40)
    
    if pct5_passes and walk_forward_ok and sensitivity_ok:
        reasons.append("Worst 5% of Monte Carlo simulations stays under ruleset limit")
        reasons.append(f"Walk-forward degradation {wf.walk_forward_degradation*100:.0f}%")
        reasons.append(f"Parameter sensitivity worst case is {sens.max_degradation*100:.0f}% drop")
        return ("B", reasons)
    
    # C grade: median passes but worst 5% doesn't
    median_passes = (mc.median_max_dd <= ruleset.max_loss_eod)
    if median_passes:
        if not pct5_passes:
            reasons.append(f"Worst 5% breaches limit by ${(mc.pct5_max_dd - ruleset.max_loss_eod):.0f}")
        if wf.walk_forward_degradation >= 0.30:
            reasons.append(f"Walk-forward shows significant degradation ({wf.walk_forward_degradation*100:.0f}%)")
        return ("C", reasons)
    
    # D grade: median doesn't pass
    if mc.median_final_pnl > 0:
        reasons.append("Median Monte Carlo simulation is profitable but worst 5% breaches drawdown limit")
        reasons.append(f"50% probability of breaching limit at some point")
        return ("D", reasons)
    
    # F grade: complete failure
    reasons.append(f"Median Monte Carlo simulation ends with loss of ${abs(mc.median_final_pnl):.0f}")
    reasons.append(f"{mc.prob_breach*100:.0f}% probability of breaching ruleset limit")
    return ("F", reasons)
```

### Deployment gate

In the UI, when a user tries to mark a strategy "Ready for Eval" or "Deploy to Demo":

```
Action               Minimum Grade
Run on Demo Account  C
Purchase Eval        B
Deploy to Funded     A
```

The UI shows the grade gate. Below the minimum: show a warning modal. Above: allow.

This is a soft gate — user can always proceed with confirmation. Like Tier 3 in M2.

---

## 5. Three small additions from the YouTube debrief

### 5a. Regime tag stub

Daily P&L payload (the JSON file referenced by `daily_pnl_path`) gets a new
field per day:

```json
[
  {"date": "2026-01-15", "pnl": 145.20, "regime_tag": "UNKNOWN"},
  ...
]
```

For M3, every day's `regime_tag` is `"UNKNOWN"`. M4 will fill them in based
on a regime classifier (not built in M3). No UI exposure in M3 — just the
field exists.

### 5b. Correlation note on multi-instrument grades

When a strategy has been graded on multiple instruments and those instruments
are known to be correlated, add a note to the Strategy Detail page.

Hardcode the correlation table for now:
```python
HIGHLY_CORRELATED_PAIRS = [
    ("MES", "MNQ"),       # micro indices, ~0.85 correlation
    ("ES", "NQ"),          # full-size indices, ~0.85
    ("GC", "MGC"),         # gold (same instrument, micro vs mini)
    ("CL", "MCL"),         # crude oil (same instrument, micro vs mini)
    ("MYM", "M2K"),        # dow and russell micro
]
```

If a strategy has A grades on both MES and MNQ:
> "Note: This grade is based on two highly correlated instruments (MES and MNQ
> are 85% correlated). For independent confirmation, run on an uncorrelated
> asset like MGC or MCL."

This is just an informational note. Doesn't change the grade.

### 5c. Pre-Deployment Checklist

A static 5-item checklist that appears as a card on the Strategy Detail page
when the user attempts to mark a strategy "Ready for Eval":

```
☐ Strategy has been graded A or B by the robustness test
☐ Strategy has clear stop loss and target rules (not fixed only)
☐ Strategy has at least one daily/weekly circuit breaker  
☐ Strategy has been backtested on at least 1 year of data
☐ I have read the strategy's NinjaScript file and understand the logic
```

User must tick all 5 before clicking "Mark Ready for Eval." Then the strategy
gets a `is_ready_for_eval = True` flag. This is informational only — doesn't
gate anything beyond the existing grade gate.

---

## 6. Backend file layout (additions)

```
backend/
├── routers/
│   ├── stress_tests.py            ← NEW
│   ├── rulesets.py                 ← Renamed from firms.py
│   └── (existing files)
├── services/
│   ├── stress_tester.py           ← NEW: Monte Carlo + walk-forward + sensitivity
│   ├── grading.py                 ← NEW: compute_grade() logic
│   ├── correlation_table.py       ← NEW: hardcoded correlation pairs (small)
│   └── (existing files)
└── (existing files)
```

Update `services/backtest_runner.py` to auto-trigger stress tests on
Tier 1 backtests.

Update `services/optimization_runner.py` to auto-trigger stress test on
best_run when an optimization completes.

---

## 7. Frontend file layout (additions)

```
frontend/src/
├── pages/
│   ├── StressTestDetail.tsx       ← NEW
│   ├── StrategyDetail.tsx          ← Update to show grade + Pre-Deployment Checklist
│   └── (existing)
├── components/
│   ├── RobustnessGradeBadge.tsx   ← NEW: letter grade pill (A-F)
│   ├── MonteCarloFan.tsx          ← NEW: equity paths fan chart
│   ├── DrawdownDistribution.tsx   ← NEW: histogram with limit line
│   ├── WalkForwardChart.tsx       ← NEW: IS vs OOS equity curves
│   ├── SensitivityRadar.tsx       ← NEW: radar chart for parameter sensitivity
│   ├── PreDeploymentChecklist.tsx ← NEW: 5-item checklist
│   ├── RulesetTypeBadge.tsx       ← NEW: PROP EVAL / PROP FUNDED / PERSONAL / DEMO badge
│   └── (existing)
└── hooks/
    └── useLab.ts                   ← Add stress test + grade hooks
```

The Backtests page already has Stress Tests as a stub tab. Replace the stub
with the real page: list all stress test runs, filterable by grade.

---

## 8. Build order

Strict sequence. Stop and report after each milestone:

1. **Ruleset abstraction first.** Schema rename + Pydantic refactor + UI
   rename + seed personal example. Verify M2 still works end-to-end after
   the rename. Smoke test: hit `/api/rulesets`, see 5 rows (4 LucidFlex + 1
   personal example). This is the most breakage-prone change so it goes first.

2. **Monte Carlo stress test (pure Python).** stress_tester.py + stress_tests
   table + router endpoints. Smoke test: trigger a stress test on an existing
   backtest, verify results JSON has all the percentile fields.

3. **Walk-forward + sensitivity (involves multiple backtests).** Slow but
   straightforward. Update stress_tester.py to coordinate N backtests via the
   existing backtest_runner pipeline.

4. **Grade computation + auto-trigger.** Wire compute_grade() into the
   pipeline. Auto-trigger on Tier 1 and optimizer winners.

5. **Frontend visualizations.** Stress Test Detail page with all four charts
   (fan, distribution, walk-forward, sensitivity radar).

6. **Grade gates + Pre-Deployment Checklist + correlation note.** Final UI
   polish.

7. **End-to-end smoke test:** take an ORB backtest from M1/M2, manually run
   a stress test, verify Monte Carlo charts render, walk-forward shows the
   expected pattern, grade comes back with reasons. Then run an optimizer
   and verify the auto-triggered stress test fires on the best result.

After step 7, stop. Bring me back:
- The grade and reasons for the existing ORB backtest
- Screenshots of all four stress test charts
- Confirmation auto-trigger works on Tier 1 backtests
- Confirmation the personal ruleset shows in the rulesets list

---

## 9. What NOT to do in M3

- Don't build a regime classifier (HMM, etc.). That's M4. Just leave the
  regime_tag stub as `UNKNOWN`.
- Don't auto-fill the deployment checklist. User must manually tick.
- Don't change anything in M1/M2's core flows beyond the firms→rulesets
  rename. Backtest, optimizer, sweep should all still work identically.
- Don't introduce a new charting library — Recharts handles all 4 stress
  test charts.
- Don't try to evaluate against more than one ruleset at a time in a stress
  test. Stress tests run against ONE ruleset (the one the backtest was
  primarily evaluated against, or user-selected on manual trigger).
- Don't make the deployment gates blocking by default — they're warnings,
  user can always proceed.

---

## 10. Update CLAUDE.md files at the end

**Backend additions:**
- New routers: `stress_tests.py`, `rulesets.py` (renamed)
- New services: `stress_tester.py`, `grading.py`, `correlation_table.py`
- New tables: `stress_tests`
- Renamed/expanded table: `rulesets` (formerly `firms`)
- `ruleset_type` field and the four ruleset types explained
- Grading rules table (A-F thresholds)
- "What's built" section gains: stress tests, robustness grading, ruleset
  abstraction

**Frontend additions:**
- New pages: StressTestDetail
- New components: RobustnessGradeBadge, MonteCarloFan, DrawdownDistribution,
  WalkForwardChart, SensitivityRadar, PreDeploymentChecklist, RulesetTypeBadge
- UI rename pass (firm → ruleset) documented
- Deployment gate UX explained
- "What's built" section gains: stress tests + grading

This is non-optional. The platform is now feature-complete after M3 and the
docs need to reflect that.

---

## 11. After M3 is shipped

The lab is feature-complete for futures + prop. Going forward you would
focus on:

- **M4 (later):** Real regime detection — fill in those `regime_tag` stubs
  with a Hidden Markov Model classifier
- **M5 (later):** Live deployment — one-click push from "graded A" → NT8 live
- **M6 (later):** MT5 / forex runner

None of these are in M3 scope.

---

*End of M3 spec. After M3 ships, the platform is feature-complete for
futures + prop firm work. Strategy improvements and going live become the
focus.*
