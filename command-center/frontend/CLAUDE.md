# CLAUDE.md — Command Center Frontend

**Purpose:** React + Vite + TypeScript app (`:5173`) — the UI for the command center; all server state via TanStack Query against the FastAPI backend.
**Scope:** This covers frontend hook/component/page conventions, the theme system, and routing. It does NOT cover the backend (see `../backend/CLAUDE.md`) or `algos/`/`smart-money/`.
**Status:** Live — all pages shipped (Overview, Smart Money, Bots, Backtests lab, Stress Tests, Queue, Settings).
**Last reviewed:** 2026-06-10

Auto-loaded by Claude Code when editing any file inside `frontend/`.

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

## Foundational config

`ParamSchemaEntry` carries `category?: 'strategy_logic' | 'foundational'`. Foundational params are never shown as editable inputs in `RunBacktestModal` or the optimizer grid — both filter them out. Instead, `RunBacktestModal` shows a readonly "Foundational Config" section (10 values pulled from the primary ruleset) once a firm is selected, and pre-fills commission/slippage from that ruleset's defaults. Foundational values are edited via `FoundationalEditModal` (pencil icon on a ruleset row): Capital & Risk, Trading Hours & Days, Daily Goals, Execution Defaults. Validation: lock_pct 0–100, times match `HH:MM`, days subset of valid day names. Saves via `useUpdateRuleset`, spreading `...ruleset` so non-foundational fields survive. The `Ruleset` type holds all 10 foundational fields (`risk_per_trade_pct`, `max_consecutive_losses`, `earliest_entry_time_et`, `latest_entry_time_et`, `days_of_week_allowed`, `daily_profit_target`, `daily_profit_lock_pct`, `default_commission_per_side`, `default_slippage_ticks`, `daily_halt_fraction`).

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
6. If it's a stub, use `EmptyState` for the placeholder — replace when it goes live

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
| Bots | ✅ Live | Monitor, control, configure (risk caps + deploy), users |
| Backtests lab | ✅ Live | Strategies / Runs / Rulesets / Sweeps / Optimizations tabs; run modal; BacktestDetail |
| Worthiness Badges | ✅ Live | Tier 1/2/3 pill on every completed run |
| Sweep Detail | ✅ Live | ProgressCard, ResultsTable, FailedRunsTable, cancel + retry |
| Optimization Detail | ✅ Live | Table / Bar Chart / Heatmap toggle; best param callout; CSV export |
| Optimize Button | ✅ Live | Tier-aware modals; int-param range validation blocks decimals |
| Tier 3 Warning Modal | ✅ Live | Per-instrument past results; sweep untested; stamps contract month |
| Runner Badge | ✅ Live | NT8 (cyan) / MT5 (purple) on Strategies, StrategyDetail, Runs |
| Market Filter | ✅ Live | All / Futures / Forex on Strategies and Runs tabs |
| Stress Tests | ✅ Live | Grade card, source card, MC fan + drawdown + walk-forward + sensitivity charts |
| Regime tagging (M4) | ✅ Live | RegimeBadge + Performance by Regime table on BacktestDetail |
| Regime equity overlay (M4) | ✅ Live | RegimeOverlayToggle; per-segment colored lines; persists to localStorage |
| Optimizer regime filter (M4) | ✅ Live | Regime Filter select in OptimizerModal; chip in OptimizationDetail |
| Strategy deployment (Pass 2) | ✅ Live | Deployed sub-tab: drag/drop `.cs`/`.mq5`, delete, NT8 + MT5 compile |
| Deploy button (Pass 2.5) | ✅ Live | Per-strategy Deploy/Redeploy; filled accent when out of sync |
| MT5 backtest modal | ✅ Live | Free-text symbol, bar presets, Evaluate/Foundational hidden |
| MT5 backtest detail | ✅ Live | MT5_RUN_STEPS; NT8-only buttons hidden; Stress Test button shown |
| Run Stress Test modal | ✅ Live | WF + sensitivity always run together; ruleset locked to first eval |
| Stress test market lock | ✅ Live | One futures + one forex test at a time; button disabled when blocked |
| Running stress indicators | ✅ Live | Pulsing chips/banners on Runs, BacktestDetail, OptimizationDetail |
| Strategy best grades | ✅ Live | Best Grade column on Strategies tab; links to the grading test |
| Queue page (Speed Step 6) | ✅ Live | `/queue` route + sidebar item; position, label, status, timestamps, delete |
| Settings | ✅ Live | Config read/write; `nt8_agent_tunnel` + `mt5_agent_tunnel` |
| Sidebar health strip | ✅ Live | 4 dots: API, SSH, NT8 (3-state), MT5 Agent |

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

## Strategy deployment manager

The "Deployed" sub-tab (`FilesTab`) has a drag/drop zone (`.cs`/`.mq5`), a file list sorted by platform then filename, trash-can delete, and overwrite/delete confirm modals. "Compile NT8" (`useTriggerCompile`) and "Compile MT5" (purple, only when MT5 files present; `useTriggerCompileMt5`) both open the generic `CompileModal` (props: `title` + `usePollHook`). Strategy-file hooks live in `useLab.ts`: `useStrategyFiles`, `useStrategyFileSyncStatus`, `useUploadStrategyFile` (native `fetch()` + `FormData`, not `api.post`), `useDeleteStrategyFile`, `useTriggerCompile`, `useCompileStatus`, `useTriggerCompileMt5`, `useCompileStatusMt5`, `useDeployStrategy`. `useParamTypes(strategyId)` calls `GET /strategies/{id}/param-types` → `Record<string, 'int' | 'double'>` with `staleTime: Infinity`; used by `OptimizerModal` to validate int-param ranges; disabled when `strategyId` is null. Types: `StrategyFile` (+ `platform`), `StrategyFileSyncStatus`, `CompileJobStatus`, `DeployJobStatus`; `ScanResult` carries `warnings: string[]`.

Each row in `StrategiesTab` has a Deploy/Redeploy button. `handleDeploy(strategyId)` calls `deploy.mutateAsync()`, tracks `deployingId`, and on success toasts + invalidates `sync-status`. Out of sync: filled accent `CloudUpload` "Deploy". In sync: outlined `RotateCcw` "Redeploy". The "Needs deploy" badge is display-only — the button is the action.

