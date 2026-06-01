# CLAUDE.md — Command Center Frontend

Auto-loaded by Claude Code when editing any file inside `frontend/`.

**Last reviewed:** 2026-05-31 (session 4)

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
│   ├── useLab.ts            strategies, firms, runs, evals, sweeps, optimizations, instrument summary
│   ├── useBots.ts
│   ├── useSmartMoney.ts
│   └── useStressTests.ts    stub — no live endpoints yet
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
│   └── OptimizeButton.tsx   tier-aware optimize trigger (Tier1 soft confirm, Tier2 direct, Tier3 warning)
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
    ├── Backtests.tsx         lab landing — Strategies / Runs / Firms / Optimizations tabs (URL-based)
    ├── BacktestDetail.tsx    full run detail — charts, KPIs, per-firm eval cards, verdict, worthiness badge, OptimizeButton
    ├── StrategyDetail.tsx    strategy metadata + all runs + runner badge
    ├── SweepDetail.tsx       sweep results — live-updating table sorted by worthiness tier
    ├── OptimizationDetail.tsx  optimizer results — heatmap (2D) or top-10 table (3+D), best param callout, CSV export
    ├── StressTests.tsx       stub — ScaffoldBanner placeholder
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

- Charts: equity curve, drawdown, daily P&L (full-width), long/short breakdown
- KPIs: Net P&L, Max Drawdown, Win Rate, Profit Factor, Trade Count, Sharpe, Worst Day, Worst Streak, Avg Win, Avg Loss, Calmar Ratio (11 cards, `grid-cols-4 lg:grid-cols-6`)
- Traffic-light verdict banner: green (profitable + no DD breach + consistency pass), yellow (profitable + DD ok + consistency fail), red (net negative or DD breach)
- Drawdown chart shows firm limit reference lines from evaluations
- Calendar-based x-axis ticks (start, quarterly, end) — not interval-based
- All chart tooltips: dark bg `#0c0c1a`, `itemStyle={{ color: '#e5e7eb' }}` for readable text

---

## What's built (status)

| Module | Status | Notes |
|---|---|---|
| Overview | ✅ Live | Stat row + cards for each domain |
| Smart Money | ✅ Live | Full pipeline UI — scan, terminal, rankings, profiles, disqualified, config, cache |
| Bots | ✅ Live | Monitor, control (global + per-bot), configure (risk caps + deploy), users (Telegram) |
| Backtests lab | ✅ Live | Strategies, Runs, Firms, Optimizations tabs; run modal; backtest detail with charts + eval cards |
| Worthiness Badges | ✅ Live | Every completed run shows a Tier 1/2/3 pill in the Runs table and on BacktestDetail header |
| Sweep Detail | ✅ Live | `/backtests/sweeps/:sweepId` — ProgressCard (segmented bar, elapsed timer, status icons), ResultsTable, FailedRunsTable. Cancel button for stuck sweeps. Retry-all and per-row retry buttons. Visual parity with OptimizationDetail. |
| Optimization Detail | ✅ Live | `/backtests/optimizations/:optimizationId` — heatmap (2D) or top-10 table (3+D), best param callout, CSV export. Per-row retry button in FailedRunsTable. |
| Optimize Button | ✅ Live | Tier-aware button on BacktestDetail: Tier 1 = soft confirm, Tier 2 = direct modal, Tier 3 = warning with instrument routing |
| Tier 3 Warning Modal | ✅ Live | Shows past results per instrument, offers sweep of untested instruments. `withContractMonth()` stamps root symbols with contract month from source run before submitting sweep. Now passes `source_run_id: run.run_id` on every sweep trigger. |
| Runner Badge | ✅ Live | StrategyDetail shows "Runs on: NinjaTrader" badge |
| Stress Tests | 🔲 Stub | ScaffoldBanner placeholder; M3 scope |
| Settings | ✅ Live | Config read/write |

---

## ProgressCard pattern (SweepDetail / OptimizationDetail)

Both detail pages use an identical `ProgressCard` sub-component with:
- Left: status icon + label + segmented progress bar (green = complete, red = failed) + counts
- Right: elapsed/duration timer (`useElapsed` hook) + Cancel button (while running) + Retry-N-failed button (when not running)
- Inline warning when failures accumulate during a run

`useElapsed(startIso, endIso, running)` — counts up live when `running`, freezes at final duration when done.

Per-row retry in `FailedRunsTable`: a `RotateCcw` icon button calls `useRetryBacktest().mutate(run.run_id)`. Spinner activates on the specific row via `retryRun.variables === run.run_id`. `e.stopPropagation()` prevents the row-click navigation from firing.

---

## Session 4 additions

### Sweep nesting in Runs tab

New `SweepNestRow` component renders directly below a run row when the sweep's `source_run_id` matches the run. Style: cyan accent left border (distinct from gold optimization rows). Shows instrument count, status pill with pulse dot while running. Clicking navigates to `/backtests/sweeps/:sweepId`.

Sweep child runs are hidden from the flat Runs list only when their sweep has a `source_run_id` (the sweep is shown nested). Old sweeps without `source_run_id` keep their child runs visible as flat rows with the SWEEP badge — there is no way to backfill the link retroactively.

`sweepsBySourceRun` map built in `RunsTab` alongside the existing `optsBySourceRun` map.

### Active tab indicators

`TabBar` accepts `runsActive`, `sweepsActive`, `optsActive` booleans. A small pulsing cyan dot appears on the tab label when any job in that category is `status = 'running'`. Derived from `allRuns`/`allSweeps`/`allOpts` cache data — no extra fetch.

### Cascade delete warning

When deleting a run that has linked optimizations or sweeps (via `source_run_id`), the `ConfirmDeleteModal` shows a specific message listing the counts: "This run has N optimizations and M sweeps attached — they and all their results will also be permanently deleted."

Backend `delete_run` cascades automatically; the warning is purely informational. Bulk run delete now also invalidates `['lab', 'sweeps']` and `['lab', 'optimizations']` query keys so the tabs update.

### Header consolidation (BacktestDetail / OptimizationDetail / SweepDetail)

- **BacktestDetail**: Removed `bar_value` and `commission_per_side` chips. Added a chip showing evaluated firm IDs (tertiary, font-mono). Instrument chip remains first and accent-colored.
- **OptimizationDetail**: Instrument chip is now first and accent-colored. Mode + search method merged into one chip (`eval · Brute Force`). "Optimization" type label chip removed (redundant on the detail page itself).
- **SweepDetail**: Removed standalone "N instruments" chip (already shown in the ProgressCard instrument tracker). Count embedded in the type chip: "5-instrument Sweep".

### Log terminal colors

`LogsSection` in BacktestDetail now matches the SmartMoney terminal pattern:
- **Running**: pulsing cyan dot (unchanged)
- **Complete**: solid cyan dot + "· complete" label
- **Failed**: red dot + "· failed" label
- **Idle**: dim grey dot (unchanged)
