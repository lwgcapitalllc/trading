# CLAUDE.md — Command Center Frontend

**Purpose:** React + Vite + TypeScript app (`:5173`) — the UI for the command center; all server state via TanStack Query against the FastAPI backend.
**Scope:** This covers frontend hook/component/page conventions, the theme system, and routing. It does NOT cover the backend (see `../backend/CLAUDE.md`) or `algos/`/`smart-money/`.
**Status:** Live — all pages shipped (Overview, Smart Money, Bots, Strategies, Rulesets, Backtests lab, Optimizations, Tuning workbench, Stress Tests, Queue, Settings).
**Last reviewed:** 2026-06-12

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
- Recharts — analytics charts (equity, drawdown, P&L, etc.) — no D3, no other charting libs here
- klinecharts (v9) — the candlestick **price-chart panel only** (`src/components/ChartPanel/`). Lazy-loaded; do not import it elsewhere. All other charts stay on Recharts.

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
│   ├── useLab.ts            strategies, rulesets (useRulesets + useFirms alias), runs, evals, sweeps, optimizations, useChartSpec (price-chart panel), useRunNews (post-run news/holiday tags)
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
│   ├── Tier3WarningModal.tsx    smart-routing modal for Tier 3 → sweep or optimize anyway. Bounded `flex flex-col max-h-[88vh]`: header + footer are `flex-shrink-0`, the intro/sub-header/sweep-CTA stay pinned, and ONLY the instrument rows scroll (their own `overflow-y-auto` with a `sticky` thead) — so a long instrument list never clips the header/footer. Tested results always show; the untested long tail is collapsed behind a "Show N untested instruments" toggle (`showUntested`) so the tested rows stay the focus
│   ├── OptimizeButton.tsx   tier-aware optimize trigger (Tier1 soft confirm, Tier2 direct, Tier3 warning)
│   ├── ParamEditor.tsx      SHARED strategy-param editor used by all three editing surfaces (Run / Tune / Optimize) so they never drift. **Every control renders at one size (`CONTROL_W` 264px x `CONTROL_H` 34px) — toggle, select, number and switch alike** — so the right-hand column is a straight edge and a row's height never depends on its label. Toggle state labels truncate (with a `title`) rather than wrap: a wrapping label used to grow its row and break the rhythm of the whole list. Keep option labels ≤ ~15 chars (a half is ~105px of text room). String params with a `choices` list render a **dropdown**, never free text — `choices` beats `widget`, because strategies match enum strings exactly and silently no-op on anything unrecognised, so a typo would disable a setting with no error. Essentials card (core knobs) + counted accordions, Simple/Expert switch, conditional `show_if` visibility, named toggle/switch/time widgets. Friendly labels/groups/descs/units/`core`/`options`/`guide` come from the schema (overlaid from a strategy's companion `<Strategy>.meta.json` by the scanner). Theme tokens only; colour rule: blue=focus only, gold=section-title text. `mode`: `run`|`tune`|`optimize`. `explainer`: `panel` (fixed right column — wide Run/Optimize modals) · `inline` (drops under the focused row) · `coach` (no per-row explainer — parent renders the exported `<ParamCoach>` footer; `onFocusChange` surfaces the focused param). Degrades gracefully with no metadata (no core → no Essentials card, all groups as accordions)

│   ├── RulesetTypeBadge.tsx PROP EVAL / PROP FUNDED / PERSONAL / DEMO type badge for ruleset rows
│   ├── RobustnessGradeBadge.tsx  A/B/C/D/F letter grade pill
│   ├── GradeLegend.tsx      collapsible "Grade key" explaining A–F (mirrors backend services/grading.py) + the "target A or B before a bot" guidance; reused on the StressTests list. Uses RobustnessGradeBadge
│   ├── WorthinessLegend.tsx collapsible "Score key" explaining the worthiness tiers (STRESS TEST / OPTIMIZE / DISCARD; mirrors backend services/worthiness.py); shown above the Backtests Runs table. The Score-column companion to GradeLegend. Uses WorthinessBadge
│   ├── ChartTabPanel.tsx    shared tabbed chart chrome (tab strip + right-side slot + Expand button) and the portalled fullscreen `ChartModal`. Extracted from BacktestDetail so StressTestDetail reuses it. Optional `aboveChart` slot renders KPI cards between the description and the chart
│   ├── MonteCarloFan.tsx    equity path fan (100 paths, p10–p90) — shared `BANDS` array drives the lines, the percentile-named tooltip, AND the Luckier→Unluckier key below the chart; axes labelled (Cumulative P&L / Trade #). Optional `height` prop
│   ├── DrawdownDistribution.tsx  drawdown histogram with limit line; axes labelled (# simulations / max drawdown reached). Optional `height` prop
│   ├── WalkForwardChart.tsx IS vs OOS Sharpe grouped bar chart with zero baseline + "Sharpe" axis label; series named In-Sample (tuned on) / Out-of-Sample (unseen). Optional `height` prop
│   ├── SensitivityRadar.tsx param sensitivity horizontal bar chart — reads BOTH shapes: perturbation (signed `pnl_delta_pct`) and grid-injected (`degradation` → negative magnitude). X-axis domain is data-driven (`[lo-pad, hi+pad]`, always includes 0) so the worst-case bar never clips. Optional `height` prop
│   └── ChartPanel/         strategy-agnostic klinecharts price-chart panel — HAS ITS OWN CLAUDE.md.
│                            Lazy-mounted on BacktestDetail; reads a ChartSpec (candles, sessions,
│                            trades, generic overlays, indicators). Zero strategy-specific logic.
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
    ├── Rulesets.tsx          own top-level page (/rulesets) — firm-grouped prop tables + personal group
    ├── Backtests.tsx         lab landing — Runs / Sweeps tabs
    ├── BacktestDetail.tsx    full run detail — params side panel, per-firm evaluation + KPIs, tabbed charts, logs, News & Holiday filter card (inline NewsFilterCard)
    ├── StrategyDetail.tsx    strategy "spec sheet" — overview + grouped param reference tables
    ├── SweepDetail.tsx       sweep results — live-updating table sorted by worthiness tier
    ├── Optimizations.tsx     own top-level RESEARCH page (/optimizations) — optimization list table
    ├── OptimizationDetail.tsx  optimizer results (/optimizations/:id) — table/bar-chart toggle, "Tune winner"
    ├── TuningWorkbench.tsx   /backtests/runs/:runId/tune — param editor + iteration leaderboard + regime overlay
    ├── StressTests.tsx       stress test list — grade badge, prob breach/pass
    ├── StressTestDetail.tsx  stress test detail — grade card + tabbed Monte Carlo / Walk-Forward / Sensitivity workspace
    ├── Queue.tsx             job queue list — position, status, timestamps
    └── Settings.tsx
```

Path alias: `@/` → `src/`. Always use it — never `../../../`.

Implementation-level detail for the denser pages (BacktestDetail, TuningWorkbench, StressTestDetail, and the rest of the pages above) — exact layout structure, chart/KPI conventions, sizing-UI wiring, cross-linking rules: `command-center/docs/FRONTEND_BUILD_NOTES.md`.

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

## Sticky page banners (`StickyHeader` + condense-on-scroll)

Top page banners are always sticky. Only the two full-bleed detail pages (BacktestDetail, TuningWorkbench) **condense** as you scroll — the minimize earned its keep there (it reclaims vertical space for the chart while a full-height side panel stays pinned). The list/index pages (Rulesets, Backtests, Optimizations, Stress Tests, Strategies) deliberately do NOT condense: their banner stays full and just drops a scroll shadow. Content scrolls behind the banner; tabs, filters, action buttons, and any collapsed score/grade legend stay pinned.

**The 22px gotcha — read before touching any sticky banner.** The app shell's `<main>` is the scroll container and has `p-[22px]`. A `position: sticky; top: 0` child of a *padded* scroller pins **22px below** the visible top, not flush against it. That single transparent strip is what caused the earlier round of bugs: a horizontal gap content scrolled through, "cropped" table headers (rows peeking through the strip), and a 22px jump the instant scroll crossed the threshold.

Fix, baked into the shared `components/StickyHeader.tsx`: pin at **`-top-[22px]`** (not `top-0`), full-bleed back across the padding with `-mx-[22px] -mt-[22px] px-[22px] pt-[22px]`, and `flow-root` so child margins are contained and the painted `bg-bg-base` reaches the content boundary (no gap). At rest the banner already sits at its pinned spot, so there's no jump.

Use the shared `StickyHeader` for list pages — it's a render-prop: `children: (scrolled) => ReactNode`, but it now always passes `scrolled = false` so the header never condenses (it stays sticky + drops the scroll shadow). The per-page `scrolled ? …` branches are kept intact (harmless dead branches) so condensing any list page is a one-line revert in the component. Earlier condense styling for reference: shrink the title (`text-h1` 20px → `text-[16px]`), force any legend collapsed (`<GradeLegend forceCollapsed={scrolled} />`), keep the painted bottom spacing INSIDE the banner (`${scrolled ? 'mb-2.5' : 'mb-[18px]'}` — never a parent `space-y-*` gap, which is transparent and lets condensed content scroll up to the title), and never inline the title into a tab row (reads as a tab item).

Full-bleed detail pages hand-roll their banner (it coexists with a full-height sticky side panel) via the `useStickyBanner` hook. Same `-top-[22px]` correction applies, and the side panel offsets its own sticky `top` by `Math.max(headerH - 22, 0)` to pin directly below the banner (not behind it). Condensed detail banners keep the period + ruleset chips (drop them only at narrow widths via `max-[1100px]:hidden` / `max-[900px]:hidden`).

**Two glitch fixes baked into `useStickyBanner` (don't regress these).** (1) **Hysteresis** — it condenses only after scrolling past `condenseAt` (72px) and re-expands only below `expandAt` (8px). A single flip point sits right where condensing shrinks the banner, so the scroll position lands on the boundary and the banner oscillates full↔condensed. (2) **Constant scroll height** — condensing shaves ~85px off the banner, which shrinks the scrollable area; on a short page the browser then **clamps `scrollTop`**, dropping it below `expandAt` and re-expanding — a feedback loop hysteresis alone can't stop (the clamp moves the scroll position itself). So the hook returns `collapse` (px the banner gave up vs its expanded height) and each page renders an invisible `flex-shrink-0` bottom spacer of that height, holding total scroll height constant. Both BacktestDetail and TuningWorkbench wire `collapse` this way.

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
- **Activity indicator:** `Sidebar.tsx` shows a pulsing accent `ActivityDot` on Backtests / Optimizations / Stress Tests when a job is running under each (`activeByRoute`, mirroring each page's "active" logic — backtest/sweep run excluding optimization combos, optimization grid, any stress phase). The dot is anchored to the **icon's top-right corner** so it's identical expanded or collapsed; expanded also adds a "Running" pill. Polling comes from the list hooks (`useBacktestRuns` now adaptive 3s/15s like `useOptimizations`; `useStressTests` 10s)

---

## Regime color constants

Regime visualization uses `REGIME_COLORS` / `REGIME_LABEL` / `REGIME_ORDER` from `src/lib/regime.ts` (single source of truth — imported by `BacktestDetail.tsx` and `TuningWorkbench.tsx`). Applied via inline style since these data-driven colors aren't in the Tailwind theme.

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

`ParamSchemaEntry` carries `category?: 'strategy_logic' | 'foundational'`. Foundational params are never shown as editable inputs in `RunBacktestModal` or the optimizer grid — both filter them out; `RunBacktestModal` shows them read-only instead, pulled from the selected ruleset. `RunBacktestModal` also carries a **Sizing Mode** toggle (Consistent | Bullet) that picks how the dynamic sizing engine turns a strategy's unit-size signals into real contracts — it only affects strategies reshaped for the engine and is inert for the rest. `BacktestDetail` renders the resulting sized account as its own chart tab, timeline table, and per-firm KPI switching (a strategy makes the same trades for every firm, but each firm's ladder/floor sizes and halts them differently).

Implementation detail (exact param-type render rules, the sized-chart/timeline/breach-cutoff mechanics, per-firm `effRun` switching): `command-center/docs/FRONTEND_BUILD_NOTES.md`.

## Rulesets page (own top-level nav item)

`pages/Rulesets.tsx`, route `/rulesets` (RESEARCH group, between Strategies and Backtests). Prop rows grouped by firm, personal/demo rows in their own group; page-level firm/Personal filter. Prop rows are read-only in the UI (server-side locked); personal/demo rows have an edit modal for the 5 personal rule fields.

Implementation detail (exact columns, contract-cap pill rendering, canonical display names): `command-center/docs/FRONTEND_BUILD_NOTES.md`.

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

BacktestDetail's charts live in one tabbed panel (Equity / Price / Breakdown), each fullscreen-expandable, with a permanent Performance-by-Regime table below. KPIs render as a flat grid (6 core cards always shown, 6 more behind a toggle) that holds a fixed row height across firm switches so the layout never jumps. Verdict colours, header chips, and tooltip styling all follow the shared theme tokens (see Theme system above) — nothing here is bespoke to this page beyond the tab/grid structure.

Full implementation detail (exact card set, fixed-height math, per-metric fallback rules, chart-specific quirks like the equity tooltip's segment-key filtering and the MT5 duration gap): `command-center/docs/FRONTEND_BUILD_NOTES.md`.

---

## What's built (status)

| Module | Status | Notes |
|---|---|---|
| Overview | ✅ Live | Stat row + cards for each domain |
| Smart Money | ✅ Live | Scan, terminal, rankings, profiles, disqualified, config, cache |
| Bots | ✅ Live | Monitor, control, configure (risk caps + deploy), users |
| Backtests lab | ✅ Live | Runs / Sweeps tabs; run modal; BacktestDetail |
| Optimizations | ✅ Live | Own RESEARCH page (`/optimizations`); detail at `/optimizations/:id`; "Tune winner" → workbench |
| Tuning workbench | ✅ Live | `/backtests/runs/:runId/tune` — edit params, run iterations, leaderboard + regime-aware equity overlay + net-P&L-by-regime |
| Worthiness Badges | ✅ Live | Tier 1/2/3 pill on every completed run |
| Sweep Detail | ✅ Live | ProgressCard, ResultsTable, FailedRunsTable, cancel + retry |
| Optimization Detail | ✅ Live | Table / Bar Chart toggle; best param callout; CSV export |
| Optimize Button | ✅ Live | Tier-aware modals; int-param range validation blocks decimals |
| Tier 3 Warning Modal | ✅ Live | Per-instrument past results; sweep untested; stamps contract month |
| Runner Badge | ✅ Live | NT8 (cyan) / MT5 (purple) icons; Python renders a gold "PY" text mark (it's local, not a vendor platform, so it has no product icon). Always use `RunnerBadge` — never a hand-rolled `<img src={isMt5 ? … : …}>`. On Strategies, StrategyDetail, Runs |
| Market Filter | ✅ Live | All / Futures / Forex on Strategies and Runs tabs |
| Stress Tests | ✅ Live | Grade card, source card, MC fan + drawdown + walk-forward + sensitivity charts |
| Regime tagging (M4) | ✅ Live | RegimeBadge + Performance by Regime table on BacktestDetail |
| Regime equity overlay (M4) | ✅ Live | RegimeOverlayToggle; faint background bands (`ReferenceArea`) on equity — consistent with the tune page; persists to localStorage |
| Optimizer regime filter (M4) | ✅ Live | Regime Filter select in OptimizerModal; chip in OptimizationDetail |
| Strategy deployment (Pass 2) | ✅ Live | Deployed sub-tab: drag/drop `.cs`/`.mq5`, delete, NT8 + MT5 compile |
| Deploy button (Pass 2.5) | ✅ Live | Per-strategy Deploy/Redeploy; filled accent when out of sync |
| MT5 backtest modal | ✅ Live | Free-text symbol, bar presets; Evaluate Against lists forex rulesets (personal forex demo) and is required like futures; Foundational hidden (NinjaScript-only) |
| MT5 backtest detail | ✅ Live | MT5_RUN_STEPS; NT8-only buttons hidden; Stress Test button shown |
| Run Stress Test modal | ✅ Live | WF + sensitivity run together; ruleset locked to first eval. Sample-size gate (mirror backend `MIN_TRADES_FOR_STRESS = 100`): Stress Test button disabled below 100 trades with an explicit tooltip — the whole test is blocked, not just a phase |
| Stress test market lock | ✅ Live | One futures + one forex test at a time; button disabled when blocked |
| Running stress indicators | ✅ Live | Pulsing chips/banners on Runs, BacktestDetail, OptimizationDetail |
| Strategy best grades | ✅ Live | Best Grade column on Strategies tab; links to the grading test |
| Queue page (Speed Step 6) | ✅ Live | `/queue` route + sidebar item; position, label, status, timestamps, delete |
| Settings | ✅ Live | Config read/write; `nt8_agent_tunnel` + `mt5_agent_tunnel` |
| Sidebar health strip | ✅ Live | 4 dots: API, SSH, NT8 (3-state), MT5 Agent |
| Price-chart panel | ✅ Live | Lazy klinecharts candlestick panel on BacktestDetail (`components/ChartPanel/`, own CLAUDE.md): TF switch, sessions, trades, generic overlays, indicators, day breaks. Real spec via `useChartSpec`; overlays/indicators (strategy structure) still pending (Step 7b) |
| News & Holiday filter | ✅ Live (NT8) | Post-run card on BacktestDetail (`NewsFilterCard`, inline). `useRunNews` tags the RAW `equity_curve` trades; News Included/Removed segmented toggle + before/after sliders (default 15/30) → KPIs (Net/Win%/PF/MaxDD/Trades, with deltas) + a filtered equity curve recomputed **client-side** (`newsKpisFrom`). Bank holidays always excluded (off the toggle). Toggle start = the strategy's `avoid_news` (`removeNews = choice ?? avoidNews`). Coverage-honest (untagged where no data; "Reload charts" note on pre-`entry_ms` runs). **Forex/MT5 not wired — TODO #3** (needs MT5 `entry_ms` + non-UTC broker timezone handling) |

---

## Key UI decisions

**Platform-based job lock** — `GET /backtests/running-job` returns `{ nt8, mt5, python }: RunningJobInfo` (polled at 5s via `useRunningVpsJob()`). All three lock independently. **Never branch on `runner === 'mt5'`** — that conflated two different questions (which lock scope? is this NT8-only UI?) and silently gave Python jobs the NT8 badge and the NT8 lock. Resolve both through `lib/runner.ts`: `runningJobFor(runningJob, runner)` for the lock (`jobBlocked = !!runningJobFor(runningJob, run.runner)?.running`), `isNt8Runner(runner)` for NT8-only UI (futures contract months, prop-challenge rulesets, injected foundational params, the NT8 chart export), `runnerMarket(runner)` for forex-vs-futures ruleset filtering (MT5 and Python are both forex), and `runnerScope`/`RUNNER_LABEL`/`RUNNER_FULL_LABEL` for display. It mirrors the backend's `_SCOPE_RUNNER_SQL`, including NT8 as the fallback for unknown runners. Lock surfaces: `RunBacktestModal`, `OptimizeButton`, `Tier3WarningModal`, `RunRow` retry, `BacktestDetail` retry/rerun. `Strategies.tsx` calls `useRunningVpsJob()` at page level (result unused) to keep the cache warm — without this, the first modal render sees `runningJob = undefined` and treats the lock as clear. All six job-lifecycle mutations invalidate `['lab', 'running-job']` on success. `BacktestSummary.runner` must be mapped in `_row_to_summary` or `run.runner` is undefined on the frontend. The backend `get_running_job()` correctly routes MT5 optimizations to the `mt5` bucket (joins `strategies` on runner) — a running MT5 optimization does NOT set `nt8.running`.

**Optimization running indicator** — `OptimizationNestRow` shows a pulsing gold dot (`w-[6px] h-[6px] rounded-full bg-gold-text animate-pulse`) when `opt.status === 'running'`. The parent `RunRow` does NOT show an "OPTIMIZING" badge — the dot on the sub-row is the only running indicator. MT5 optimizations emit live `completed_count`/`total_count` per combo; the sub-row counter (e.g. "35/36 runs") reads these from the optimization record's `completed_runs`/`estimated_runs`.

**Tab-specific active dots** — each Backtests tab has its own pulsing dot logic (not "any job running"): `runsActive = allRuns?.some(r => !r.sweep_id && r.status === 'running')` (includes opt-combo full backtests while running). `sweepsActive = allSweeps?.some(s => s.status === 'running')`. `optsActive = allOpts?.some(o => o.status === 'running')` — only fires when an actual optimization grid is running, NOT during a single-combo full backtest (`retry_single_optimization_run` uses `set_running=False` so the optimization stays `complete`). Running opt-combo full backtests appear in the Runs tab filter (`!r.optimization_id || r.status === 'running'`) with their OPT chip visible, then disappear once complete.

**Runs table columns** — "Score" = WorthinessBadge (Tier 1/2/3, the quality verdict; the `WorthinessLegend` "Score key" above the table explains the tiers). "Trades" = `run.trade_count` for at-a-glance volume. "Challenge" = firm name chip(s) showing which challenges the run was evaluated against. Score and Challenge are intentionally separated: score = how good, challenge = under what rules. Per-firm PASS/WARN/DISCARD detail lives only on BacktestDetail. There is **no Status column** — run status is a small `RunStatusIcon` glyph after the strategy name (running = pulsing accent dot, failed = red ✕, complete = green dot); a finished run is otherwise self-evident from its populated metrics. Nested rows (optimization/sweep/tune) keep their own status pill and still span `colSpan={12}` (column count is unchanged: Status removed, Trades added).

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

The "Deployed" sub-tab (`FilesTab`) has a drag/drop zone (`.cs`/`.mq5`), a file list sorted by platform then filename, trash-can delete, and overwrite/delete confirm modals. "Compile NT8" (`useTriggerCompile`) and "Compile MT5" (purple, only when MT5 files present; `useTriggerCompileMt5`) both open the generic `CompileModal` (props: `title` + `usePollHook`). The modal has a status-icon header (`StatusIcon`: spinner / green check / red X) + one-line summary, a body capped at `max-h-[85vh]` that scrolls, and a pinned footer. While running it shows staggered pulse **skeleton rows** (no second spinner) shaped like the result rows that replace them. On completion it renders the real `job.errors` / `job.warnings` **text** — not just counts — via `CompileSection` (color-coded, numbered, monospace lines: red `neg` for errors, amber `warn` for warnings); warnings show even on a successful compile. The elapsed counter ticks every second from a **local `setInterval`** (anchored to `started_at`, freezing at `completed_at` when done) — without it the count only advanced on each poll and visibly jumped. Strategy-file hooks live in `useLab.ts`: `useStrategyFiles`, `useStrategyFileSyncStatus`, `useUploadStrategyFile` (native `fetch()` + `FormData`, not `api.post`), `useDeleteStrategyFile`, `useTriggerCompile`, `useCompileStatus`, `useTriggerCompileMt5`, `useCompileStatusMt5`, `useDeployStrategy`. `useParamTypes(strategyId)` calls `GET /strategies/{id}/param-types` → `Record<string, 'int' | 'double'>` with `staleTime: Infinity`; used by `OptimizerModal` to validate int-param ranges; disabled when `strategyId` is null. Types: `StrategyFile` (+ `platform`), `StrategyFileSyncStatus`, `CompileJobStatus`, `DeployJobStatus`; `ScanResult` carries `orphans: string[]` (DB strategies whose source file is gone) + `warnings: string[]`; `ReconcileResult` carries `removed: string[]` + `warnings: string[]`.

**Scan vs Reconcile (bidirectional delete).** Scan is read-only: `useScanStrategies` (`POST /strategies/scan`) adds/updates and its success toast flags the orphan count (`N orphaned (source deleted — use Reconcile)`). Deleting a source file from the repo propagates to the DB row + the deployed VPS file ONLY through an explicit action: `useReconcileStrategies` (`POST /strategies/reconcile`). On the `Strategies.tsx` header, a red **Reconcile (N)** button appears next to Scan **only when the last scan found orphans** (`scan.data?.orphans`), fronted by the shared `ConfirmDeleteModal` (imported from `pages/Backtests`) listing exactly which strategies will be removed. On success it invalidates `['lab','strategies']` + the strategy-files / sync-status keys, and surfaces any per-strategy VPS-delete warnings as error toasts. The per-strategy Delete button uses the same backend `remove_strategy` path. See backend CLAUDE.md "Bidirectional delete (reconcile)".

Each row in `StrategiesTab` has a Deploy/Compile/Run action driven by the **content-aware** `StrategyFileSyncStatus` (`needs_deploy` / `needs_compile`, not the old presence-only `in_sync`). `StrategyRow` takes the full `sync` object (via `syncByStrategy[s.id]`), and the Status cell shows a version chip `v{current_version}` (title tooltip: "Local vN · running vM") next to the state pill: amber **Needs deploy** (local source differs from what's deployed) → amber **Needs compile** (deployed but not compiled from that content) → green **In sync**. The action button mirrors the pill: `needs_deploy` → Deploy, else `needs_compile` → Compile, else Run. `handleDeploy` tracks `deployingId` and on success invalidates `sync-status`. **First-run:** every strategy shows Needs deploy until deployed once through the tracked path (no deploy-hash recorded yet — see backend CLAUDE.md). `StrategyVersion` type + `GET /strategies/{id}/versions` expose the full version history if a per-strategy view wants it.

