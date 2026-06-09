# CLAUDE.md — Command Center Frontend

Auto-loaded by Claude Code when editing any file inside `frontend/`.

**Last reviewed:** 2026-06-08

React + Vite + TypeScript app on `:5173`. All API calls go to the FastAPI backend on `:8000` via the Vite proxy at `/api`. Dark indigo-black UI, electric cyan accent, gold secondary.

**Lab design principle:** Run Backtest modal starts with no firms pre-selected. User must actively choose which firm challenges to evaluate against — never auto-select all.

---

## Stack

- React 18 + TypeScript + Vite
- React Router v6 — client-side routing
- TanStack Query — all server state
- sonner — toasts
- TailwindCSS — custom theme in `tailwind.config.js`
- Lucide React — icons (no other icon libraries)
- Recharts — charts (no D3, no other chart libraries)

Do not add UI libraries (MUI, Radix, Headless UI, etc.) without raising it first.

---

## Directory layout

```
frontend/src/
├── App.tsx                  router + layout shell
├── main.tsx                 entry point
├── api/client.ts            ONLY place fetch() lives
├── types/index.ts           mirrors all backend Pydantic models exactly
├── hooks/                   one file per backend domain
│   ├── useLab.ts            strategies, rulesets (useRulesets + useFirms alias), runs, evals, sweeps, optimizations
│   ├── useBots.ts
│   ├── useSmartMoney.ts
│   ├── useStressTests.ts    stress tests — useStressTests, useStressTest, useRunStressTest, useDeleteStressTest, useRunningStressLock, useStrategyBestGrades
│   └── useQueue.ts          job queue — useQueue, useEnqueueOptimization, useEnqueueStressTest, useDeleteQueueItem
├── components/              reusable, dumb components
│   ├── Sidebar.tsx
│   ├── TopBar.tsx
│   ├── StatCard.tsx
│   ├── ScaffoldBanner.tsx
│   ├── EmptyState.tsx
│   ├── SystemHealthStrip.tsx
│   ├── RunBacktestModal.tsx
│   ├── WorthinessBadge.tsx  Tier 1/2/3 pill badge (green/cyan/yellow)
│   ├── OptimizationHeatmap.tsx  SVG 2D heatmap for 2-param optimizer grids
│   ├── Tier3WarningModal.tsx    smart-routing modal for Tier 3 → sweep or optimize anyway
│   ├── OptimizeButton.tsx   tier-aware optimize trigger (Tier1 soft confirm, Tier2 direct, Tier3 warning)
│   ├── RulesetTypeBadge.tsx PROP EVAL / PROP FUNDED / PERSONAL / DEMO type badge for ruleset rows
│   ├── RobustnessGradeBadge.tsx  A/B/C/D/F letter grade pill
│   ├── MonteCarloFan.tsx    equity path fan chart (100 paths, percentile bands)
│   ├── DrawdownDistribution.tsx  drawdown histogram with ruleset limit line
│   ├── WalkForwardChart.tsx IS vs OOS Sharpe grouped bar chart
│   ├── SensitivityRadar.tsx param sensitivity horizontal bar chart (PnL delta %)
│   └── PreDeploymentChecklist.tsx  5-item checklist on StrategyDetail — first checkbox locked if strategy's best stress test grade is below B
│                            NOTE: EvaluationCard, EquityCurveChart, DrawdownChart,
│                            DailyPnlChart, DirectionBreakdown are all inline
│                            components inside BacktestDetail.tsx — not separate files.
└── pages/
    ├── Overview.tsx
    ├── SmartMoney/
    │   ├── index.tsx         tab shell + scan control
    │   ├── Rankings.tsx
    │   ├── CandidateProfile.tsx
    │   ├── PoolOverview.tsx
    │   ├── DisqualifiedLog.tsx
    │   └── Config.tsx
    ├── Bots/
    │   ├── index.tsx         monitor tab + live snapshot
    │   ├── ConfigureTab.tsx  risk caps + deploy
    │   └── UsersTab.tsx      Telegram users
    ├── Backtests.tsx         lab landing — Strategies / Runs / Rulesets / Sweeps / Optimizations tabs (URL-based)
    ├── BacktestDetail.tsx    full run detail — charts, KPIs, per-firm eval cards, verdict, worthiness badge, OptimizeButton
    ├── StrategyDetail.tsx    strategy metadata + all runs + runner badge
    ├── SweepDetail.tsx       sweep results — live-updating table sorted by worthiness tier
    ├── OptimizationDetail.tsx  optimizer results — 3-view toggle (Table / Bar Chart / Heatmap); `RankedBars` inline component; best param callout, CSV export
    ├── StressTests.tsx       stress test list — grade badge, strategy/instrument/status columns, prob breach/pass, created; all left-aligned
    ├── StressTestDetail.tsx  stress test detail — grade column card (coloured strip + name + ruleset chip + reasons), source backtest card (links back to run via useBacktestRun), MetricCard MC stats with pos/neg colouring, InfoTip tooltips, prob bars, fan chart, drawdown dist, walk-forward, sensitivity
    ├── Queue.tsx             job queue list — position, job label (type + id prefix), status pill, queued/started/finished timestamps, trash-can delete for pending items
    └── Settings.tsx
```

Path alias: `@/` → `src/`. Always use it — never `../../../`.

---

## Tab state — always use URL

All page-level tab state lives in the URL via `useSearchParams`, never `useState`. This preserves the active tab across refresh, back/forward, and deep links.

```typescript
// Pattern used in Backtests, Bots, SmartMoney
const [searchParams, setSearchParams] = useSearchParams()
const tab = (searchParams.get('tab') ?? 'default') as TabType
const setTab = (t: TabType) => setSearchParams({ tab: t }, { replace: true })
```

Special case — SmartMoney's `profile` tab requires `selectedCandidate` in session state. If arriving cold on `?tab=profile` with no candidate, fall back to `rankings`.

---

## Live log streaming during active runs

`useRunLog` accepts a third `live` boolean parameter. Pass `live={isRunning}` from the parent page so logs poll at 2 s during an active run and stop polling when the run completes:

```tsx
// In LogsSection or equivalent:
const { data: log } = useRunLog(open ? runId : null, 200, isRunning)
```

Also auto-expand the log panel when `isRunning` is true (`autoExpand={isFailed || isRunning}`) so the user sees live output without clicking.

---

## Hook conventions

One hooks file per backend domain. Every hook wraps a single endpoint.

```typescript
// Read
export function useThings() {
  return useQuery({
    queryKey: ['things'],
    queryFn: () => api.get<Thing[]>('/things'),
    refetchInterval: 30_000,
  })
}

// Write
export function useCreateThing() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: ThingCreate) => api.post<Thing>('/things', body),
    onSuccess: () => {
      toast.success('Thing created')
      qc.invalidateQueries({ queryKey: ['things'] })
    },
    onError: () => toast.error('Create failed'),
  })
}
```

- Never call `fetch()` directly — always `api.get/post/put/patch/delete`
- Every mutation needs `onSuccess` toast + `invalidateQueries`, and `onError` toast
- Query keys: `[domain, resource]` or `[domain, resource, id]`

---

## Component conventions

Pages own data fetching. Components own rendering. No business logic in components.

- Numbers → `font-mono tabular-nums`
- Loading → skeleton for tables/cards; `value="—"` for `StatCard`
- Status indicators → use existing `StatusPill` / `StatusDot` patterns, don't invent new shapes
- All tab state → `useSearchParams` (see above)

---

## Standard components — use before building new

| Component | Use for |
|---|---|
| `StatCard` | All stat tiles. Supports `value="—"` loading, `onClick`, `disabled` |
| `EmptyState` | Empty data screens — icon + title + description |
| `ScaffoldBanner` | Stub pages only. Delete when the page goes live |

Extend an existing component with a new prop before forking a near-duplicate.

---

## Theme system — how it works and how to swap

All color values live in **`src/themes/electric-indigo.js`** — the single source of truth.

| File | What it feeds |
|---|---|
| `src/themes/electric-indigo.js` | Master color values |
| `tailwind.config.js` | Imports the theme → builds all Tailwind tokens |
| `src/themes/chart.ts` | Imports the theme → exports constants for Recharts (SVG can't use Tailwind classes) |
| `src/index.css` | Body bg + scrollbar are hardcoded here to `bgBase` / `bgSurface2` — update manually when swapping |

**To swap themes:**
1. Create `src/themes/<new-theme>.js` with the same shape as `electric-indigo.js`
2. Update the import in `tailwind.config.js` → `from './src/themes/<new-theme>.js'`
3. Update the import in `src/themes/chart.ts` → `from './<new-theme>.js'`
4. Update 3 values in `src/index.css` (body bg, scrollbar thumb, scrollbar border — comments label which theme key each maps to)
5. Rebuild

**Theme token classes — never hardcode colors in components:**

| Use | Class |
|---|---|
| Primary text | `text-text-primary` |
| Secondary text | `text-text-secondary` |
| Tertiary / dim | `text-text-tertiary` |
| Surfaces | `bg-bg-base`, `bg-bg-sunken`, `bg-bg-surface` |
| Borders | `border-border-subtle`, `border-border-default` |
| Accent (cyan) | `text-accent`, `bg-accent`, `border-accent` |
| Profit / pass | `text-pos-text`, `bg-pos-muted` |
| Loss / fail | `text-neg-text`, `bg-neg-muted` |
| Warning | `text-warn-text`, `bg-warn-muted` |
| Gold / highlight | `text-gold-text`, `bg-gold-muted` |

**Chart components** — import from `@/themes/chart` and use `C.pos`, `C.neg`, `C.accent`, `C.tooltipBg`, `C.axisTick`, etc. Never paste raw hex in chart props.

No raw hex anywhere else. Exception: brand gradient in `TopBar.tsx` (intentional — it defines the wordmark style).

---

## Toasts

```typescript
import { toast } from 'sonner'
toast.success('Saved')
toast.error('Failed: ...')
```

- Every user-initiated state change → success + failure toast
- Reads don't toast
- Don't toast on navigation, hover, or query refetches

---

## Routing

- Routes defined in `App.tsx`
- Sidebar nav items in `Sidebar.tsx` — `WORKSPACE` for live modules, `RESEARCH` for lab
- `live: false` shows a "Soon" badge; set to `true` when the page is real
- Navigation: `useNavigate()` — never `<a href>` for in-app links

---

## Regime color constants

Regime visualization uses a `REGIME_COLORS` constant defined inline in `BacktestDetail.tsx`. Applied via inline style since these data-driven colors aren't in the Tailwind theme.

| Regime | Hex | Notes |
|---|---|---|
| TRENDING | `#06b6d4` | cyan — app accent |
| TRANSITIONING | `#8b5cf6` | violet |
| RANGING | `#f59e0b` | amber |
| HIGH_VOLATILITY | `#ef4444` | red |
| LOW_VOLATILITY | `#64748b` | slate |
| UNKNOWN | `#6b7280` | produces no colored segment in the overlay |

Companion constants in `BacktestDetail.tsx`: `REGIME_LABEL` (full display strings), `REGIME_LABEL_SHORT` (abbreviated for narrow zones, e.g. `Trans.`, `Hi Vol.`).

## Pass 1 — Foundational Config (frontend changes)

### Param filtering in Run Backtest Modal and Optimizer Modal

`ParamSchemaEntry` now has a `category?: 'strategy_logic' | 'foundational'` field served by the backend scanner. Both modals filter on it:

**RunBacktestModal:**
- `params` state initializes only from entries where `category !== 'foundational'`
- `paramGroups` skips foundational entries entirely — they're never shown as editable inputs
- A readonly "Foundational Config" section appears below the Evaluate section once a firm is selected. It shows 10 values (Account Size, Risk/Trade, Max Daily Loss, Halt Fraction, Max Consecutive Losses, Force Flat, Entry Hours, Days Allowed, Daily Target, Lock-In At) pulled from the primary ruleset (first selected firm)
- Commission and slippage inputs pre-fill from the primary ruleset's `default_commission_per_side` / `default_slippage_ticks` when a firm is first selected (user can still override)

**OptimizerModal (OptimizeButton.tsx):**
- `FOUNDATIONAL_PARAMS` set filters `run.params` so axes state only includes strategy-logic keys
- `paramEntries` filtered to same set — foundational params never appear in the optimizer grid

### Ruleset foundational config edit

`FoundationalEditModal` component in `Backtests.tsx` — appears when the pencil icon is clicked on any ruleset row. Four sections:
- **Capital & Risk**: Risk % per Trade, Daily Halt Fraction (0–1), Max Consecutive Losses
- **Trading Hours & Days**: Earliest/Latest Entry ET (HH:MM), Days Allowed (comma-separated)
- **Daily Goals**: Daily Profit Target ($), Lock-In At (% of target → stored as 0–1)
- **Execution Defaults**: Commission/Side ($), Slippage (ticks)

Validation: lock_pct 0–100, times match `HH:MM` regex, days subset of valid day names. Calls `useUpdateRuleset` on save. The modal passes the full ruleset through `...ruleset` so existing non-foundational fields aren't overwritten.

The `Ruleset` type in `types/index.ts` now carries all 10 new foundational fields (`risk_per_trade_pct`, `max_consecutive_losses`, `earliest_entry_time_et`, `latest_entry_time_et`, `days_of_week_allowed`, `daily_profit_target`, `daily_profit_lock_pct`, `default_commission_per_side`, `default_slippage_ticks`, `daily_halt_fraction`).

---

## What NOT to do

- Call `fetch()` directly
- Hardcode colors — tokens only
- Put business logic in components
- Forget `invalidateQueries` after a mutation
- Create new spinner or empty-state components — use existing ones
- Add a UI/animation/chart library without raising it first
- Use `any` in TypeScript — use `unknown` + narrow instead
- Store server state in `useState` or React context
- Use relative imports that escape the current folder — always `@/...`
- Use `useState` for page-level tab state — use `useSearchParams`

---

## When you add a new page

1. Create `src/pages/PageName.tsx`
2. Add the route in `App.tsx`
3. Add `NavItem` in `Sidebar.tsx` (WORKSPACE or RESEARCH)
4. If it needs data, create `src/hooks/useThing.ts`
5. Add types to `src/types/index.ts`
6. If it's a stub, use `ScaffoldBanner` + `EmptyState` — delete both when it goes live

---

## Lab UX principle

The lab is a platform for designing and stress-testing trading strategies, not a dashboard. Every page should help the user make a decision: is this strategy viable, which parameter set is most robust, does it survive Monte Carlo? Design for decisions, not metrics.

---

## Backtest detail — chart and KPI conventions

- Charts: equity curve (+ regime overlay when enabled), drawdown, daily P&L (full-width), long/short breakdown (pie charts)
- KPIs: Net P&L, Max Drawdown, Win Rate, Profit Factor, Trade Count, Sharpe, Worst Day, Worst Streak, Avg Win, Avg Loss, Calmar Ratio (11 cards, `grid-cols-4 lg:grid-cols-6`)
- No standalone traffic-light verdict banner — evaluation state is conveyed entirely through the EvalCard (amber border/badge when profitable DISCARD, red when net-negative DISCARD)
- EvalCard color override: when `ev.verdict === 'DISCARD'` but `netPnl > 0`, use amber (`VERDICT_CONFIG.WARN`) colors for border/badge — but keep the DISCARD label and icon from the original verdict
- Header chips: instrument = `font-semibold font-mono bg-accent/10 text-accent border border-accent/20`; date = `font-medium font-mono bg-bg-surface border border-border-subtle text-text-secondary`; ruleset = `font-semibold font-mono bg-warn-muted border border-warn-text/20 text-warn-text`
- WorthinessBadge removed from BacktestDetail header — verdict lives in EvalCard only
- StatusBadge only rendered while the run is actively `running` — not shown for `complete` (implied by being on the detail page)
- Drawdown chart shows firm limit reference lines from evaluations
- Calendar-based x-axis ticks (start, quarterly, end) — not interval-based
- Long vs Short section uses donut pie charts (Recharts `PieChart`/`Pie`/`Label`): won (green) vs lost (red) slices, win rate % as center label. Won label on right (matches green arc), lost label on left.
- All chart tooltips: `contentStyle={{ background: C.tooltipBg, border: '1px solid ${C.tooltipBorder}', borderRadius: 8, fontSize: 13, padding: '8px 12px' }}`, `labelStyle={{ color: C.axisTick }}`, `itemStyle={{ color: '#e5e7eb' }}`. Never use `C.tooltipBorder` as text color — it's a dark border hex, not readable text.
- Equity curve custom tooltip: uses `content` prop (not `formatter`/`labelFormatter`) to filter out `_s0..N` segment keys from the payload — only the `equity` entry is shown.

---

## What's built (status)

| Module | Status | Notes |
|---|---|---|
| Overview | ✅ Live | Stat row + cards for each domain |
| Smart Money | ✅ Live | Scan, terminal, rankings, profiles, disqualified, config, cache |
| Bots | ✅ Live | Monitor, control (global + per-bot), configure (risk caps + deploy), users (Telegram) |
| Backtests lab | ✅ Live | Strategies, Runs, Rulesets, Sweeps, Optimizations tabs; run modal; BacktestDetail with charts + per-ruleset eval cards |
| Worthiness Badges | ✅ Live | Tier 1/2/3 pill on every completed run in Runs table and BacktestDetail |
| Sweep Detail | ✅ Live | ProgressCard (segmented bar, elapsed timer), ResultsTable, FailedRunsTable, cancel + retry-all + per-row retry |
| Optimization Detail | ✅ Live | 3-view toggle (Table / Bar Chart / Heatmap). Table: ranked table, always available. Bar Chart: sorted by PF desc, colored by tier, winner ★. Heatmap: 2-param only, message otherwise. Best param callout, CSV export. "Full Backtest" button on BacktestDetail (not inline in table). |
| Optimize Button | ✅ Live | Tier-aware: Tier 1 = soft confirm, Tier 2 = direct modal, Tier 3 = warning modal with instrument routing |
| Tier 3 Warning Modal | ✅ Live | Past results per instrument; sweep of untested instruments; `withContractMonth()` stamps contract month; passes `source_run_id` |
| Runner Badge | ✅ Live | `RunnerBadge` on Strategies tab, StrategyDetail, Runs tab — NT8 (cyan) or MT5 (purple) |
| Market Filter | ✅ Live | `MarketFilterBar` on Strategies and Runs tabs. All / Futures / Forex. `runner=mt5` → Forex, others → Futures. `useState` (not URL) |
| Stress Tests | ✅ Live | `/stress-tests` page. Grade column card, source backtest card, MC fan + drawdown dist + walk-forward + sensitivity charts. Pipeline stepper while running |
| Backtests M4 — Regime tagging | ✅ Live | `RegimeBadge` + `PerformanceByRegimeTable` on BacktestDetail. Auto-tagged at pipeline time (Tagging step visible) |
| Backtests M4 — Equity overlay | ✅ Live | `RegimeOverlayToggle`; per-segment colored `Area` lines; `RegimeLegend` (dash swatches). Persists to `localStorage` |
| Backtests M4 — Optimizer regime filter | ✅ Live | "Regime Filter" select in `OptimizerModal`; chip in `OptimizationDetail` when set |
| Pass 2 — Strategy Deployment | ✅ Live | "Deployed" sub-tab: drag/drop `.cs`/`.mq5`, file list, trash-can delete, NT8 + MT5 `CompileModal` |
| Pass 2.5 — Deploy button | ✅ Live | Per-strategy Deploy/Redeploy buttons. `useDeployStrategy()` → `POST /strategies/{id}/deploy`. Filled accent when out of sync |
| MT5 backtest modal | ✅ Live | Branches on `strategy.runner === 'mt5'`: free-text symbol, bar presets [5m–4h], Evaluate/Foundational sections hidden |
| MT5 backtest detail | ✅ Live | `MT5_RUN_STEPS` (Launch→Testing→Results→Tagging); runner-specific guidance; "Load chart data from NT8" and "Refresh" hidden for MT5; Stress Test button visible for all completed runs with trades |
| Run Stress Test modal | ✅ Live | No checkboxes — WF + sensitivity always run together. Ruleset locked to `run.evaluations[0]` — shown as readonly chip. Fixed estimate: ~45 min (native WF) or ~80 min (non-native). Sends `include_walk_forward: true, include_sensitivity: true` always. On success navigates to `/stress-tests/{stress_test_id}`. Stress Test button shows pulsing "In progress" (clickable, navigates to stress test) when a test is already running; shows modal-opener otherwise. |
| Stress test market lock | ✅ Live | `useRunningStressLock()` polls `GET /stress-tests/running-lock` (5s). Response: `{futures, forex, run_ids}`. `stressBlocked = isMt5 ? lock.forex : lock.futures`. Stress Test button disabled + tooltip when market is blocked. |
| Running stress test indicators | ✅ Live | **Runs tab:** `RunsTab` builds `stressRunIds = new Set(lock.run_ids)`, passes `hasRunningStress` to `RunRow` (pulsing "STRESS TESTING" chip) and `hasRunningStress={stressRunIds.has(opt.best_run_id)}` to `OptimizationNestRow` (same chip). `OptimizationNestRow` no longer shows instrument. **BacktestDetail:** Stress Test button transforms to pulsing "In progress" (navigates to stress test) when `latestStress` is running; no separate banner. **OptimizationDetail:** `useRunningStressLock` + `useStressTests(bestRunId)` → clickable "Stress test in progress on winner run" banner when best run has a running stress test. |
| Strategy best grades | ✅ Live | `useStrategyBestGrades()` polls `GET /stress-tests/strategy-grades` (30s) → `Record<strategyId, {grade, stress_test_id}>`. Strategies tab "Best Grade" column: `RobustnessGradeBadge` per row, clickable (stops row click, navigates to that stress test). `—` when no graded test exists. |
| StressTestDetail fixes | ✅ Live | `useState`/`useEffect` for `nowSec` hoisted above early returns (Rules of Hooks — was causing black screen on open). `nowSec` ticks via `setInterval` while `isRunning` (was frozen at first render, making "Total elapsed" stuck). View Run navigates to `/backtests/runs/${st.run_id}` (was missing `runs/` segment). Delete uses in-app confirm modal, not `window.confirm`. **Pipeline stepper:** `hasSens = hasWF || ...` — Sensitivity step is always visible once WF is active; shows as pending/upcoming during `running_wf` phase instead of being hidden until `running_sens`. |
| BacktestDetail polish | ✅ Live | Rerun button; clickable strategy `<h1>`; `StatusPill` shared component; stale progress guard (`job_id` match) |
| Speed Step 6 — Queue page | ✅ Live | `/queue` route + sidebar nav item (Research section, `ListOrdered` icon). `QueueItem` type. `useQueue` (polls 5s), `useEnqueueOptimization`, `useEnqueueStressTest`, `useDeleteQueueItem` hooks in `useQueue.ts`. `Queue.tsx` table: position, job label (type + short id), `StatusPill` (pending/running/done/failed), timestamps, trash-can for pending items. |
| Settings | ✅ Live | Config read/write. `nt8_agent_tunnel` and `mt5_agent_tunnel` both present |
| Sidebar health strip | ✅ Live | 4 dots: API, SSH, NT8 (3-state), MT5 Agent. `SystemHealthStrip.tsx` |

---

## Key UI decisions

**Platform-based job lock** — `GET /backtests/running-job` returns `{ nt8: RunningJobInfo, mt5: RunningJobInfo }` (polled at 5s via `useRunningVpsJob()`). NT8 and MT5 lock independently. `jobBlocked = isMt5 ? !!runningJob?.mt5?.running : !!runningJob?.nt8?.running`. Lock surfaces: `RunBacktestModal`, `OptimizeButton`, `Tier3WarningModal`, `RunRow` retry, `BacktestDetail` retry/rerun. `Strategies.tsx` calls `useRunningVpsJob()` at page level (result unused) to keep the cache warm — without this, the first modal render sees `runningJob = undefined` and treats the lock as clear. All six job-lifecycle mutations invalidate `['lab', 'running-job']` on success. `BacktestSummary.runner` must be mapped in `_row_to_summary` or `run.runner` is undefined on the frontend. The backend `get_running_job()` correctly routes MT5 optimizations to the `mt5` bucket (joins `strategies` on runner) — a running MT5 optimization does NOT set `nt8.running`.

**Optimization running indicator** — `OptimizationNestRow` shows a pulsing gold dot (`w-[6px] h-[6px] rounded-full bg-gold-text animate-pulse`) when `opt.status === 'running'`. The parent `RunRow` does NOT show an "OPTIMIZING" badge — the dot on the sub-row is the only running indicator. MT5 optimizations emit live `completed_count`/`total_count` per combo; the sub-row counter (e.g. "35/36 runs") reads these from the optimization record's `completed_runs`/`estimated_runs`.

**Tab-specific active dots** — each Backtests tab has its own pulsing dot logic (not "any job running"): `runsActive = allRuns?.some(r => !r.sweep_id && r.status === 'running')` (includes opt-combo full backtests while running). `sweepsActive = allSweeps?.some(s => s.status === 'running')`. `optsActive = allOpts?.some(o => o.status === 'running')` — only fires when an actual optimization grid is running, NOT during a single-combo full backtest (`retry_single_optimization_run` uses `set_running=False` so the optimization stays `complete`). Running opt-combo full backtests appear in the Runs tab filter (`!r.optimization_id || r.status === 'running'`) with their OPT chip visible, then disappear once complete.

**Runs table columns** — "Score" = WorthinessBadge (Tier 1/2/3, the quality verdict). "Challenge" = firm name chip(s) showing which challenges the run was evaluated against. These are intentionally separated: score = how good, challenge = under what rules. Per-firm PASS/WARN/DISCARD detail lives only on BacktestDetail.

---

## ProgressCard pattern (SweepDetail / OptimizationDetail)

Both detail pages use an identical `ProgressCard` sub-component with:
- Left: status icon + label + segmented progress bar + counts
- Right: elapsed/duration timer (`useElapsed` hook) + Cancel button (while running) + Retry-N-failed button (when not running)
- Inline warning when failures accumulate during a run

**Terminal color scheme** (matches Smart Money terminal aesthetic):
- Complete (no failures): `border-accent/20 bg-accent/5` background, `text-accent` status label + icon, `bg-accent` progress bar, `text-accent` count
- Instrument/combo done pills: `border-accent/25 bg-accent/10 text-accent`
- Failed/partial: unchanged (red/amber)
- Running: unchanged (cyan spinner, already matched)

`useElapsed(startIso, endIso, running)` — counts up live when `running`, freezes at final duration when done.

Per-row retry in `FailedRunsTable`: a `RotateCcw` icon button calls `useRetryBacktest().mutate(run.run_id)`. Spinner activates on the specific row via `retryRun.variables === run.run_id`. `e.stopPropagation()` prevents the row-click navigation from firing.

---

## Pass 2 — Strategy Deployment Manager (frontend)

**`FilesTab`** ("Deployed" sub-tab): drag/drop zone (`.cs`/`.mq5`), file list sorted by platform then filename, trash-can delete, overwrite/delete confirmation modals. "Compile NT8" → `useTriggerCompile()` → NT8 `CompileModal`. "Compile MT5" (purple, only when MT5 files present) → `useTriggerCompileMt5()` → MT5 `CompileModal`. `CompileModal` is generic: `title` + `usePollHook` props.

**New hooks in `useLab.ts`:** `useStrategyFiles`, `useStrategyFileSyncStatus`, `useUploadStrategyFile` (native `fetch()` + `FormData` — not `api.post`), `useDeleteStrategyFile`, `useTriggerCompile`, `useCompileStatus`, `useTriggerCompileMt5`, `useCompileStatusMt5`, `useDeployStrategy`.

**New types:** `StrategyFile` (+ `platform`), `StrategyFileSyncStatus`, `CompileJobStatus`, `DeployJobStatus`. `ScanResult` gains `warnings: string[]`.

---

## Pass 2.5 — Strategy Location Cleanup (frontend)

Deploy/Redeploy buttons per row in `StrategiesTab`. `handleDeploy(strategyId)` calls `deploy.mutateAsync()` and tracks `deployingId` state. On success: toast + `sync-status` invalidation. Out of sync: filled accent + `CloudUpload` "Deploy". In sync: outlined + `RotateCcw` "Redeploy". "Needs deploy" badge is display-only — the button is the action.

