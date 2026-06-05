# CLAUDE.md — Command Center Frontend

Auto-loaded by Claude Code when editing any file inside `frontend/`.

**Last reviewed:** 2026-06-05

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
│   └── useStressTests.ts    stress tests — useStressTests, useStressTest, useRunStressTest, useDeleteStressTest
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
    ├── OptimizationDetail.tsx  optimizer results — heatmap (2D) or top-10 table (3+D), best param callout, CSV export
    ├── StressTests.tsx       stress test list — grade badge, strategy/instrument/status columns, prob breach/pass, created; all left-aligned
    ├── StressTestDetail.tsx  stress test detail — grade column card (coloured strip + name + ruleset chip + reasons), source backtest card (links back to run via useBacktestRun), MetricCard MC stats with pos/neg colouring, InfoTip tooltips, prob bars, fan chart, drawdown dist, walk-forward, sensitivity
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
| Smart Money | ✅ Live | Full pipeline UI — scan, terminal, rankings, profiles, disqualified, config, cache |
| Bots | ✅ Live | Monitor, control (global + per-bot), configure (risk caps + deploy), users (Telegram) |
| Backtests lab | ✅ Live | Strategies, Runs, Rulesets, Sweeps, Optimizations tabs; run modal; backtest detail with charts + per-ruleset eval cards |
| Worthiness Badges | ✅ Live | Every completed run shows a Tier 1/2/3 pill in the Runs table and on BacktestDetail header |
| Sweep Detail | ✅ Live | `/backtests/sweeps/:sweepId` — ProgressCard (segmented bar, elapsed timer, status icons), ResultsTable, FailedRunsTable. Cancel button for stuck sweeps. Retry-all and per-row retry buttons. Visual parity with OptimizationDetail. |
| Optimization Detail | ✅ Live | `/backtests/optimizations/:optimizationId` — heatmap (2D) or top-10 table (3+D), best param callout, CSV export. Per-row retry button in FailedRunsTable. |
| Optimize Button | ✅ Live | Tier-aware button on BacktestDetail: Tier 1 = soft confirm, Tier 2 = direct modal, Tier 3 = warning with instrument routing |
| Tier 3 Warning Modal | ✅ Live | Shows past results per instrument, offers sweep of untested instruments. `withContractMonth()` stamps root symbols with contract month from source run before submitting sweep. Now passes `source_run_id: run.run_id` on every sweep trigger. |
| Runner Badge | ✅ Live | `RunnerBadge` component on Strategies tab, StrategyDetail, and Runs tab rows. Shows NT8 (cyan) or MT5 (purple) platform pill. |
| Market Filter (Step 8) | ✅ Live | `MarketFilterBar` on Strategies and Runs tabs. Three chips: All / Futures / Forex. Instrument→market mapping: `runner=mt5` → Forex, all others → Futures. State in `useState` (not URL — it's a filter, not a nav destination). |
| Stress Tests | ✅ Live | Own sidebar page at `/stress-tests`. StressTestDetail: **grade column card** (coloured left strip A–F, name, gold ruleset chip, grade reasons inline); **source backtest card** below it (strategy name, instrument, date range, Net P&L, trades, "View Run →" → `/backtests/:run_id`); MetricCard with pos/neg coloured values + InfoTip hover tooltips on all stats; ProbBars color-coded by severity; equity fan, drawdown dist, walk-forward, sensitivity charts. "Stress Test" button on BacktestDetail. No COMPLETE status pill (implied). Running status pill is cyan (matches all other tables). **Pipeline stepper** shown while running: fixed-width phase nodes (MC → Walk-forward → Sensitivity) with flex-1 connector lines, per-phase elapsed timers using `mc_completed_at` / `wf_completed_at` DB columns. |
| Backtests lab M4 — Regime tagging | ✅ Live | `RegimeBadge` inline component (colored dot + label, spec colors). `PerformanceByRegimeTable` inline component on BacktestDetail — shown when ≥1 non-UNKNOWN tag exists; columns: Regime/Days/Trades/Net P&L/Win Rate/PF/Worst Day; Overall row pulls from `run.*` fields, never recomputed from regime rows. `BackfillRegimeButton` in header action row — shown when any `daily_pnl` entry has missing or UNKNOWN `regime_tag`; polls backfill status at 1s; invalidates run query on completion. |
| Backtests lab M4 — Equity overlay | ✅ Live | `RegimeOverlayToggle` button in Charts header — active when non-UNKNOWN tags exist. Toggle persists to `localStorage` (`regime_overlay_enabled`), defaults to on. **Colored equity line**: `EquityCurveChart` augments the data with per-band segment keys (`_s0`, `_s1`, …); each regime segment renders as a separate `Area` with `fill="transparent"` and the regime's stroke color. When overlay is off, falls back to the normal single-color green line + fill. `RegimeLegend` (dash swatches, not dots) below equity curve when overlay is on. `PerformanceByRegimeTable` slides in/out below the equity curve with a CSS `max-height` + `opacity` transition (350ms) — only mounts when tags exist, visibility driven by `overlayOn`. UNKNOWN days produce no colored segment. |
| Backtests lab M4 — Optimizer regime filter | ✅ Live | `OptimizerModal` gains a "Regime Filter" select (col-span-3, all 5 labels + no-filter option). `regime_filter` flows through types → hook → backend. `OptimizationDetail` shows regime chip in metadata row when set. |
| Backtests lab Pass 2 — Strategy Deployment | ✅ Live | "Deployed" sub-tab in `Strategies.tsx`: drag/drop zone (`.cs` and `.mq5`), file list sorted by platform then filename, trash-can delete, overwrite confirmation, "Compile NT8" button → NT8 `CompileModal`, "Compile MT5" button (purple, shown only when MT5 files present) → MT5 `CompileModal`. `StrategiesTab` shows ● In sync / ● Needs deploy status badges; rows sorted by platform then name. `CompileModal` takes `title` + `usePollHook` props — one component for both NT8 and MT5. |
| Backtests lab Pass 2.5 — Deploy button | ✅ Live | Per-strategy Deploy/Redeploy buttons in the Strategies tab. Works for both `.cs` (NT8) and `.mq5` (MT5) — routing is transparent (handled by nt8_agent_client on the backend). `useDeployStrategy()` fires `POST /strategies/{id}/deploy` + chained GET. Filled accent "Deploy" when out of sync; outlined "Redeploy" when in sync. |
| Settings | ✅ Live | Config read/write. Fields: `nt8_agent_tunnel` and `mt5_agent_tunnel` both present. |
| Sidebar health strip | ✅ Live | 4 dots: API, SSH, NT8, MT5 Agent. NT8 dot is three-state: red (agent down, clickable) → yellow (agent up, NT8/SA not ready) → green (all clear). MT5 Agent dot: red (down, clickable) → green. `SystemHealthStrip.tsx`. |

---

## Key UI decisions

**NT8 single-instance lock** — `GET /backtests/running-job` (polled at 5s via `useRunningVpsJob()`) is the UI-side source of truth. All job-trigger surfaces (RunBacktestModal, OptimizeButton, Tier3WarningModal, retry buttons) check this and show a banner + disable their action. The backend 409 guard (`has_any_running_vps_job`) remains the authoritative lock; the UI enforcement prevents wasted round-trips.

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

## Pass 2 — Strategy Deployment Manager (frontend changes)

### Components — live in `Strategies.tsx` (moved from `Backtests.tsx` during nav refactor)

**`FilesTab`** — Now the "Deployed" sub-tab under Strategies. Contains:
- Drag/drop zone (accepts `.cs` and `.mq5`; toasts on other file types)
- File list table: Filename, Platform badge, Size, Modified, Status badge, Trash2 delete icon — rows sorted by platform then filename
- No platform filter chips (removed — sorting by platform is sufficient)
- "Compile NT8" button → triggers `useTriggerCompile()` → shows NT8 `CompileModal`
- "Compile MT5" button (purple) — only shown when MT5 files present (`hasMt5Files`) → triggers `useTriggerCompileMt5()` → shows MT5 `CompileModal`
- Overwrite confirmation modal: shown when a dropped file already exists on the VPS
- Delete confirmation modal: shown when trash icon is clicked
- `FileStatusBadge`: green "In sync" / red "Missing" pill

**`CompileModal`** — generic for both NT8 and MT5. Props: `compileJobId`, `onClose`, `title` (e.g. "Compiling NinjaScript" vs "Compiling MQL5 (MetaEditor)"), `usePollHook` (either `useCompileStatus` or `useCompileStatusMt5`). Polls at 2s while running. Shows spinner + elapsed time. "Close" only appears when done.

### `StrategiesTab` changes

Sync-status badges (● In sync / ● Needs deploy) are now display-only. Tab counts (number pills on each tab label) fetched at page-shell level via three hooks — TanStack Query deduplicates requests.

### New hooks in `useLab.ts`

| Hook | Purpose |
|---|---|
| `useStrategyFiles()` | `GET /strategy-files` — 30s refetch |
| `useStrategyFileSyncStatus()` | `GET /strategy-files/sync-status` — 60s refetch |
| `useUploadStrategyFile()` | `POST /strategy-files/upload` — multipart via native `fetch()` (not `api.post`) |
| `useDeleteStrategyFile()` | `DELETE /strategy-files/{filename}` |
| `useTriggerCompile()` | `POST /strategy-files/compile` — NT8 pywinauto F5 |
| `useCompileStatus(id)` | `GET /strategy-files/compile/{id}` — polls at 2s while running |
| `useTriggerCompileMt5()` | `POST /strategy-files/compile-mt5` — MetaEditor compile |
| `useCompileStatusMt5(id)` | `GET /strategy-files/compile-mt5/{id}` — polls at 2s while running |
| `useDeployStrategy()` | `POST /strategies/{id}/deploy` + chained GET — returns `DeployJobStatus` |

Upload hook uses native `fetch()` with `FormData` (not `api.post`) because multipart encoding requires special handling not available in the `api` wrapper.

### New types in `types/index.ts`

`StrategyFile` (+ `platform: string`), `StrategyFileSyncStatus`, `CompileJobStatus`, `DeployJobStatus`. `ScanResult` gains `warnings: string[]`.

---

## Pass 2.5 — Strategy Location Cleanup (frontend changes)

### Deploy / Redeploy buttons on `StrategyRow`

Each row in the Strategies tab now has a Deploy button (when out of sync) or a Redeploy button (when in sync), alongside the existing Run button. Both call `handleDeploy(strategyId)` in the parent `StrategiesTab`, which calls `deploy.mutateAsync(strategyId)` and tracks the deploying row via `deployingId` state. Spinner shown on the specific row while deploying. On success: toast + `sync-status` query invalidation.

- Out of sync: filled accent button, `CloudUpload` icon, label "Deploy"
- In sync: outlined subtle button, `RotateCcw` icon, label "Redeploy", title="Redeploy to VPS"
- Disabled + spinner while `deployingId === s.id`

The "Needs deploy" badge is now a plain status indicator (not a navigating button). The Deploy button is the action.

