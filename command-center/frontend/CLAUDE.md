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
│   ├── useLab.ts            strategies, rulesets (useRulesets + useFirms alias), runs, evals, sweeps, optimizations, useChartSpec (price-chart panel)
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
│   ├── ParamEditor.tsx      SHARED strategy-param editor used by all three editing surfaces (Run / Tune / Optimize) so they never drift. Essentials card (core knobs) + counted accordions, Simple/Expert switch, conditional `show_if` visibility, named toggle/switch/time widgets. Friendly labels/groups/descs/units/`core`/`options`/`guide` come from the schema (overlaid from a strategy's companion `<Strategy>.meta.json` by the scanner). Theme tokens only; colour rule: blue=focus only, gold=section-title text. `mode`: `run`|`tune`|`optimize`. `explainer`: `panel` (fixed right column — wide Run/Optimize modals) · `inline` (drops under the focused row) · `coach` (no per-row explainer — parent renders the exported `<ParamCoach>` footer; `onFocusChange` surfaces the focused param). Degrades gracefully with no metadata (no core → no Essentials card, all groups as accordions)

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
    ├── Rulesets.tsx          rulesets — own top-level page (/rulesets): firm-grouped prop tables + personal group, page-level brand/Personal filter, Contracts/scaling column, PersonalRulesEditModal (prop rows locked)
    ├── Backtests.tsx         lab landing — Runs / Sweeps tabs (URL-based). Exports shared ConfirmDeleteModal, RunsTableSkeleton, fmtOptStatus. Sweep child runs are NEVER flat top-level Runs rows (filtered by `!r.sweep_id`, same as optimization combos): a UI-created sweep nests under its origin run via `SweepNestRow`; a standalone/legacy sweep (no `source_run_id`) lives only in the Sweeps tab. Runs table has no Status column (the count was redundant with the tab badge too, so it's gone): status shows as a small `RunStatusIcon` after the strategy name (pulsing accent dot = running, red ✕ = failed, green dot = complete — done is otherwise implied by populated metrics). Column order is `… Score · Trades · Net P&L · Max DD · Win% · Challenge · Duration` (Trades = `run.trade_count`, right after Score; Duration last). Duration uses `run.started_at ?? run.created_at` → `completed_at` so a retried run counts only the latest attempt, not back to the first kickoff. A collapsible `WorthinessLegend` ("Score key") sits above the table. The Runs filters (market All/Futures/Forex, status select, Refresh) render on the tab row itself, right-aligned via TabBar's `right` slot — `statusFilter`/`marketFilter` are lifted to the page shell; Refresh just re-fetches `['lab','runs']` (the list also auto-polls, so it's a manual override, not the only way to update). Market is derived from `run.runner` (`mt5` = forex, else futures) via `runMarket()` — NOT the instrument name, which mis-bucketed broker-suffixed forex (`GBPJPY.s`) and futures months (`MYM 06-26`)
    ├── BacktestDetail.tsx    full run detail — full-bleed page (`-m-[22px]` cancels main's padding) laid out as a column: (1) a FULL-WIDTH header row (back link, title, chips, action buttons Rerun/Tune/Optimize/Stress Test) spanning the entire width; (2) below it a flex row that shares the remaining space between the collapsible left ParamsSidePanel (full-height bg-surface column flush against the nav sidebar, border-r divider; inner block sticky top-0 so params stay visible while scrolling; strategy-logic params + collapsible foundational; marks params changed vs baseline with strikethrough old→new for tune iterations; collapse persists in localStorage 'bt_params_panel'; collapses to a thin vertical rail) and the detail content (flex-1, re-adds px/pb-[22px], reflows when the panel toggles): banners; an Evaluation + Performance row (per-firm eval cards with the trade-count standout · flat core/more KpiGrid that shares an items-stretch row with the eval card so their heights match — an **optimizer combo** (`isOptCombo`: has `optimization_id`, no equity curve, complete) uses the SAME two-column layout but the Evaluation column is an `UnscoredEvalCard` "UNSCORED" placeholder with a **Run Full Backtest** CTA instead of a verdict; only a plain run with no evaluations and no combo origin falls through to the full-width Performance-only layout. Running a full backtest on a combo with no inheritable ruleset opens `FullBacktestEvalModal` (market-aware ruleset picker — forex for MT5, futures for NT8) — driven by the backend's `status: "needs_ruleset"` reply; the choice re-fires via `useRetryBacktest({ runId, evaluateRulesets })`); tabbed charts (Equity/Price/Breakdown — Breakdown holds Drawdown + Daily P&L + Long-Short together; each panel fullscreen-expandable via ChartModal) + permanent Performance by Regime; logs. The account-balance slider now lives in the ParamsSidePanel footer
    ├── StrategyDetail.tsx    strategy "spec sheet" — full-width header (labeled Type/Runs-on/Market/Parameters chips) + Overview card (editable description "What it does", optional flow `steps`, optional "The edge" — both from `<Strategy>.meta.json` top-level `steps`/`edge`), then a two-column body: sticky LEFT side panel (Jump-to-group nav, ★ Essentials at-a-glance, Backtest-runs summary + deep-link to `/backtests?tab=runs&market=forex|futures`) and RIGHT collapsible grouped param tables (Parameter · What it does · Default+unit · Tuning effect from `guide`; no raw types; ★ on `core`; `show_if` → "only when" chip; toolbar: Essentials-only / Expand-all / Collapse-all). Column tops are kept inline via equal-height `ColHead`s. No pre-deployment checklist (removed — it was a prop-eval concept that didn't map to a strategy).
    ├── SweepDetail.tsx       sweep results — live-updating table sorted by worthiness tier
    ├── Optimizations.tsx     OWN top-level RESEARCH page (route /optimizations) — optimization list table. Decoupled from the Backtests tab. Count shown as a pill beside the title (not a "N optimizations" text label); checkbox multi-select bulk delete (matches the Backtests pattern: select-all header checkbox + per-row, "Delete N" button by the count, `ConfirmDeleteModal`, `Promise.allSettled` over `DELETE /optimizations/{id}`). Running optimizations are not selectable (cancel first)
    ├── OptimizationDetail.tsx  optimizer results (route /optimizations/:id) — 2-view toggle (Table / Bar Chart); `RankedBars` inline; CSV export; "Tune winner" button → workbench
    ├── TuningWorkbench.tsx   route /backtests/runs/:runId/tune — param editor seeded from a baseline run, runs tweak iterations (source_run_id=baseline), leaderboard with deltas, regime-aware cumulative-P&L overlay, net-P&L-by-regime table. Live progress for the running iteration via useLabProgress (watch in-place; no need to leave). **Layout:** chart + leaderboard are the hero; the shared `ParamEditor` lives in a full-height **dockable left side panel** (mirrors BacktestDetail's `ParamsSidePanel` pattern — `-m-[22px]` full-bleed root, sticky inner, `panelCollapsed` → thin rail, persists `tune_params_panel` in localStorage). The editor runs in `explainer="coach"` mode: rows never shift as focus moves; instead a pinned **`<ParamCoach>` strip** sits at the bottom of the dock (above the Run-iteration footer) showing the focused param's name/current-value/`default`/desc + ↓Lower/↑Higher guide (numbers) or named states (toggles), driven by `onFocusChange`→`coachParam`. The cumulative-P&L overlay (`renderOverlay(h)`) is the visual hero (~440px) with an Expand button → fullscreen modal (Esc/✕ to close). Cross-linking: tune iterations are NEVER top-level Runs rows — they nest under their baseline (TuneNestRow) when it's a visible row, otherwise (e.g. tuned from an optimization winner) they live only in the workbench. In-progress indicators (presence only, never a count, shown on ONE row not both): in the Runs tab the pulsing "TUNING" chip lives on the OptimizationNestRow whose winner has a running tune (driven by `runningTuneSourceRuns`) — NOT also on the parent RunRow; a direct tune of a standalone run shows via its TuneNestRow "Running" status. On OptimizationDetail the indicator is a "TUNING WINNER" chip in the Results header (kept out of the table so it doesn't widen columns) + the "Tune winner" button becomes "Tuning…" with a spinner. Reached via: those rows, the "Tune winner" button, and BacktestDetail's "Tuning iteration → workbench/optimization" breadcrumb (runs with source_run_id). The Runs-tab single-run progress banner is suppressed when the running job is a tune (no orphan indicator).
    ├── StressTests.tsx       stress test list — grade badge, strategy/instrument/status columns, prob breach/pass, created. Count shown as a pill beside the title (not a text label); a collapsible `GradeLegend` above the table; checkbox multi-select bulk delete (matches the Backtests pattern: select-all header checkbox + per-row, "Delete N" button by the count, `ConfirmDeleteModal`, `Promise.allSettled` over `DELETE /stress-tests/{id}`)
    ├── StressTestDetail.tsx  stress test detail — laid out as a CONTEXT ROW + a unified tabbed ANALYSIS WORKSPACE. Context row (2 cols, side by side): the grade card (coloured grade strip + name + ruleset chip + three `VerdictTile`s — the headline KPI from each analysis so the whole test reads at a glance: Monte Carlo breach %, Walk-Forward degradation, Sensitivity worst-case, each graded robust/acceptable/fragile) and the source backtest card (links back to the run via useBacktestRun). Delete lives top-right in the header row (labelled "Delete" button, mirrors OptimizationDetail). Below: ONE `ChartTabPanel` (Monte Carlo / Walk-Forward / Sensitivity) where each tab renders its own KPI cards (`aboveChart`) directly above its own chart, so KPIs and chart always match. MC tab = 6 cards (4 MC stats + `ProbCard` breach + pass) above a tall Equity Path Fan (the hero, ~⅔ height) + a smaller Max Drawdown Distribution; WF tab = degradation/avg-IS/avg-OOS/windows above the IS-vs-OOS bars; Sens tab = worst-case/most-fragile-param/params-tested/median-change above the tornado bars. Per-tab fullscreen via `ChartModal`. `gradeWord()` grades a ratio → {pct, word, cls}; thresholds: MC breach 5/20, WF degradation 20/30, sensitivity 25/40. The dollar drawdown limit threaded to cards/charts is `ddLimit` — mirrors backend `effective_dd_limit_usd` (personal/demo = account_size × %-from-peak; prop = max_loss_eod), so personal rows never render a $0 limit. Prob-pass card label is ruleset-aware (personal: "Prob. Stay Safe")
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

`ParamSchemaEntry` carries `category?: 'strategy_logic' | 'foundational'`. Foundational params are never shown as editable inputs in `RunBacktestModal` or the optimizer grid — both filter them out. Instead, `RunBacktestModal` shows a readonly "Foundational Config" section (10 values pulled from the primary ruleset) once a firm is selected, and pre-fills commission/slippage from that ruleset's defaults. The `Ruleset` type holds all 10 foundational fields (`risk_per_trade_pct`, `max_consecutive_losses`, `earliest_entry_time_et`, `latest_entry_time_et`, `days_of_week_allowed`, `daily_profit_target`, `daily_profit_lock_pct`, `default_commission_per_side`, `default_slippage_ticks`, `daily_halt_fraction`) plus the 2 personal fail-condition fields (`max_drawdown_from_peak_pct`, `max_consecutive_loss_days`).

`RunBacktestModal`'s `ParamInput` must render strategy-logic params **by `ParamSchemaEntry.type`**: `bool`→checkbox, `string`→text input, everything else→numeric (`type="number"`). The `string` branch is required — without it, string params (e.g. LondonBreakout's GMT session-window times `"00:00"`, MeanReversion's session-hours strings) fall through to the numeric input, which can't display a non-numeric value and renders **blank**, and `parseFloat` would corrupt it on edit. The scanner extracts string defaults correctly (`raw_val.strip('"')`), so a blank field is always a render-type bug, not a missing default.

`RunBacktestModal` also carries a **Sizing Mode** toggle (`sizingMode` state, Consistent | Bullet, default consistent) above "Evaluate Against", sent as `BacktestRunRequest.sizing_mode`. It picks how the dynamic sizing engine turns the strategy's unit-size signals into real contracts (consistent = room÷7 per trade; bullet = max the firm's ladder allows) — it only affects strategies reshaped for the engine (ORB) and is inert for the rest. Backend stores it on `backtest_runs.sizing_mode` and reads it back at completion. `BacktestDetail` then carries `sizing_mode` + `sized` (bool) + `sized_timeline` (`SizedTimelineDay[]`, the engine's day-by-day record); the detail page renders an accent **"Engine-sized · Consistent/Bullet"** pill in both header layouts (full + condensed sticky), shown only when `run.sized` — invisible on every current unit-size run.

**Sized equity curve (chart tab).** When `run.sized && run.sized_timeline.length`, the BacktestDetail chart panel inserts a **Sized** tab (between Equity and Price). `SizedEquityCurveChart` (Recharts `ComposedChart`) plots the REAL sized account day by day: an area for **end-of-day balance** (green/red by net) and a red dashed **stepAfter** line for the **trailing risk floor** (`risk_floor` — the firm's max-loss line). The gap is the buffer; balance crossing the floor is a breach (red `ReferenceDot`); halt days are gold `ReferenceDot`s; the per-day tooltip shows balance / floor / buffer / trades / contracts / halt reason. `SizedCurveLegend` below names the two lines + the sizing mode. The tab is fullscreen-expandable like the others (`renderChart` `case 'sized'`; `primaryTab` union includes `'sized'`). It's distinct from the existing per-trade **Equity** tab (unit-size trade P&L) — this is what actually traded under the rules. Inert for every unit-size run (tab never appears).

## Rulesets page (own top-level nav item)

`pages/Rulesets.tsx`, route `/rulesets` (RESEARCH group, between Strategies and Backtests; old `/strategies?tab=rulesets` links redirect). Prop rows grouped by FIRM name (`FIRM_BRAND_NAMES`: Lucid / Tradeify / FundedNext / Apex — "LucidFlex" is Lucid's PROGRAM, not the firm); row names carry only the program/challenge (e.g. "Select $50k Evaluation" under TRADEIFY) — canonical names live in `lab_db._RULESET_DISPLAY_NAMES`, applied every `init_db`. The filter row is page-level: All / each firm / Personal — a firm chip shows only that firm, Personal shows only the personal group. Prop table columns: Name / Type / Account Size / Profit Target / Max DD (EOD) / Consistency / Min Days / Contracts (`Min Days` = `min_trading_days`, the eval-pass minimum — "—" when the firm publishes none; verified 2026-06 against firm docs: LucidFlex/FundedNext-Flex/Apex-EOD = none, Tradeify Select eval = 3 from its 40% consistency rule). Personal/demo rows show Daily Cap / Daily Target / Max DD from Peak / Max Loss Days (no Min Days — not a personal-account concept). Both tables end with a Contracts column (`ContractsCell`): fixed caps as `N mini / M micro`, scaling rows add a gold SCALES pill, FundedNext rows add a cyan MIX pill (minis+micros share one cap at 1:10; excess profit voided). SCALES and MIX both use CSS hover tooltips (never the native `title` attr — unreliable) anchored `right-0` so they grow INTO the table — the wrapper is `overflow-hidden`, so a left-anchored tooltip in the last column gets cropped. Personal rows show a dash. **Editing:** personal/demo rows get a pencil → `PersonalRulesEditModal` (5 fields: account_size, daily_loss_cap, daily_profit_target, max_drawdown_from_peak_pct, max_consecutive_loss_days) saving via `usePatchPersonalRuleset` → `PATCH /rulesets/{id}`. Prop rows show a lock icon ("Firm rules — not editable") and no edit affordance — the real lock is server-side: PATCH and PUT both return 403 for prop rows, and PATCH rejects non-allowlisted fields 422. `FoundationalEditModal` was removed with the lock; foundational values on personal rows are still editable via the PUT endpoint (no UI affordance currently).

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

- Charts: one **tabbed panel** — **Equity / Price / Breakdown** (shared `ChartTabPanel` draws the tab chrome). Equity & Price are the big ~520px charts (Price lazy-loads its ChartSpec via `PriceChartPanel`). The **Breakdown** tab stacks all three supporting charts together (Drawdown full-width on top, then Daily P&L + Long/Short side by side) sized to share the tab height. Every panel has an **Expand** button (`Maximize2`) → a portalled full-screen `ChartModal` (Esc / backdrop / X to close) that re-renders the active tab at the measured viewport height — fullscreening Breakdown blows up all three together. A `renderChart(key, h)` helper draws each chart at a given height for both inline and fullscreen. **Performance by Regime** is a permanent table below. Regime context shows as **faint background bands** on the equity view (`ReferenceArea`, fillOpacity 0.1 — NOT line-segment colors), toggled by `RegimeOverlayToggle`; same treatment as the tune page. The equity draw animation is kept; the `ChartModal` overlay uses a **solid** `bg-bg-base` (NOT `backdrop-blur`) — blurring the whole viewport is recomputed every animation frame and made the fullscreen line render choppy.
- KPIs (`KpiGrid`): a flat grid — **6 core cards always shown** (Net P&L · Sharpe · Win Rate · Max DD % · Profit Factor · Calmar) plus **6 "more" cards** (Profit Concentration · Expectancy · Z-Score · Avg Trade · Worst Day · Worst Streak) revealed by a "More metrics" toggle (`showMoreKpis`, lifted to the page). Big-number cards with a sentiment-coloured left accent (`KPI_TONE_BORDER`, derived from the value's text colour). On `lg` the grid is **pinned to the evaluation card's measured height** (a `ResizeObserver` on the eval column → `evalH` → `fixedHeight`): collapsed = one tall row (value font 38px), expanded = two half-height rows summing to the same total (value font 26px). Dollar-valued cards (Net P&L, Worst Day) render through `FitMoney`, which shows the full figure (e.g. `-$3,231`) when it fits the cell and abbreviates to `$3.2k` only when it would overflow — it measures a hidden full-width copy against the cell (observing both) so it switches back to full when the grid expands and the font shrinks. Pure-CSS `items-stretch` was tried but caused a grow-then-shrink reflow on toggle due to circular flex sizing, so JS measurement is the canonical approach. The eval card is intentionally a touch shorter than prototype (trimmed header, rule row, and footer padding) so the collapsed row sits at a comfortable height. Trade Count is NOT a card — it's the standout at the bottom of the eval card (`TradeCountStandout`); the single-eval case hides the eval-card name (it's in the breadcrumb), multi-eval keeps it.
- Folded-in metrics (no separate card): Recovery Factor → Calmar's tooltip; Avg Win/Loss + R:R → Expectancy's sub; the dollar Max Drawdown → Max DD %'s sub (`"$5,227 peak-to-trough"`).
- **Account-balance what-if slider lives in the `ParamsSidePanel` footer** ("Account balance · rebases Max DD %") — moved off the Max DD card so that card aligns with the others. It only rebases the Max DD % KPI. `KpiGrid` takes `balance` (for the calc only); `ParamsSidePanel` takes `balance` / `defaultBalance` / `onBalanceChange` and renders the slider. The % uses a **trade-derived** drawdown rebased to the chosen balance (`rebaseEquity` + `maxDrawdownOf`), identical across NT8/MT5. **Calmar is capital-independent by design** (CAGR÷MaxDD% — the balance cancels) and does NOT move with the slider; every other metric comes from the trades, not the balance.
- **Avg Trade** (duration) is **blank ("—") for MT5 runs** — the MT5 Strategy Tester report carries only trade-close times (no entry time), so duration can't be computed (`algos/.../mt5_agent.py`, off-limits + would need a VPS redeploy). The card's sub reads "duration unavailable" in that case so it doesn't look broken. **Net P&L** carries a sub (return % of balance, else "net of commissions") so it lines up with the other cards (every KPI card reserves the sub line's height).
- Sharpe shows the **canonical daily-√252** value, with the platform value + `low sample` flag in its sub. Profit Concentration and Sharpe prefer the **backend-persisted** value (`run.profit_concentration_pct` / `run.platform_sharpe`), falling back to a client calc for older runs.
- Verdict colours: `VERDICT_CONFIG` maps `PASS`/`WARN`/`DISCARD`/`INFO`. Personal/demo runs get **real PASS/DISCARD verdicts** with their own chips (drawdown-from-peak + consecutive-capped-days, keyed on `ev.ruleset_type`, never on the `firm_max_loss_eod = 0` sentinel — that value must never render, incl. drawdown-chart limit lines). Pre-evaluator-pass rows still carry INFO (neutral badge, chips suppressed) until re-evaluated. `StrategyDetail`'s `VERDICT_PILL_STYLE` also maps INFO to a neutral style; `Backtests` ChallengePills are verdict-agnostic (coloured by ruleset). `EvalCard` colour override: when `verdict === 'DISCARD'` but `netPnl > 0`, use amber (`VERDICT_CONFIG.WARN`) for border/badge but keep the DISCARD label/icon.
- Header chips: instrument = `font-semibold font-mono bg-accent/10 text-accent border border-accent/20`; date = `font-medium font-mono bg-bg-surface border border-border-subtle text-text-secondary`; ruleset = `font-semibold font-mono bg-warn-muted border border-warn-text/20 text-warn-text`
- WorthinessBadge removed from BacktestDetail header — verdict lives in EvalCard only
- StatusBadge only rendered while the run is actively `running` — not shown for `complete` (implied by being on the detail page)
- Drawdown chart shows firm limit reference lines from evaluations
- Calendar-based x-axis ticks (start, quarterly, end) — not interval-based
- Long vs Short section uses donut pie charts (Recharts `PieChart`/`Pie`/`Label`): won (green) vs lost (red) slices, win rate % as center label. Won label on right (matches green arc), lost label on left.
- All chart tooltips: `contentStyle={{ background: C.tooltipBg, border: '1px solid ${C.tooltipBorder}', borderRadius: 8, fontSize: 13, padding: '8px 12px' }}`, `labelStyle={{ color: C.axisTick }}`, `itemStyle={{ color: '#e5e7eb' }}`. Never use `C.tooltipBorder` as text color — it's a dark border hex, not readable text.
- Equity curve custom tooltip: uses `content` prop (not `formatter`/`labelFormatter`) to filter out `_s0..N` segment keys from the payload — only the `equity` entry is shown.
- **Price chart** (separate from the Recharts analytics above): a lazy-mounted `<PriceChartSection>` renders the klinecharts candlestick panel (`components/ChartPanel/`). It is collapsed by default and only fetches the run's ChartSpec (`useChartSpec`, served by `GET /backtests/runs/{id}/chart-spec`) when opened — the candle fetch is heavy. Falls back to a daily-candle note when intraday history is unavailable. See `components/ChartPanel/CLAUDE.md`.

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
| Runner Badge | ✅ Live | NT8 (cyan) / MT5 (purple) on Strategies, StrategyDetail, Runs |
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

---

## Key UI decisions

**Platform-based job lock** — `GET /backtests/running-job` returns `{ nt8: RunningJobInfo, mt5: RunningJobInfo }` (polled at 5s via `useRunningVpsJob()`). NT8 and MT5 lock independently. `jobBlocked = isMt5 ? !!runningJob?.mt5?.running : !!runningJob?.nt8?.running`. Lock surfaces: `RunBacktestModal`, `OptimizeButton`, `Tier3WarningModal`, `RunRow` retry, `BacktestDetail` retry/rerun. `Strategies.tsx` calls `useRunningVpsJob()` at page level (result unused) to keep the cache warm — without this, the first modal render sees `runningJob = undefined` and treats the lock as clear. All six job-lifecycle mutations invalidate `['lab', 'running-job']` on success. `BacktestSummary.runner` must be mapped in `_row_to_summary` or `run.runner` is undefined on the frontend. The backend `get_running_job()` correctly routes MT5 optimizations to the `mt5` bucket (joins `strategies` on runner) — a running MT5 optimization does NOT set `nt8.running`.

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

The "Deployed" sub-tab (`FilesTab`) has a drag/drop zone (`.cs`/`.mq5`), a file list sorted by platform then filename, trash-can delete, and overwrite/delete confirm modals. "Compile NT8" (`useTriggerCompile`) and "Compile MT5" (purple, only when MT5 files present; `useTriggerCompileMt5`) both open the generic `CompileModal` (props: `title` + `usePollHook`). Strategy-file hooks live in `useLab.ts`: `useStrategyFiles`, `useStrategyFileSyncStatus`, `useUploadStrategyFile` (native `fetch()` + `FormData`, not `api.post`), `useDeleteStrategyFile`, `useTriggerCompile`, `useCompileStatus`, `useTriggerCompileMt5`, `useCompileStatusMt5`, `useDeployStrategy`. `useParamTypes(strategyId)` calls `GET /strategies/{id}/param-types` → `Record<string, 'int' | 'double'>` with `staleTime: Infinity`; used by `OptimizerModal` to validate int-param ranges; disabled when `strategyId` is null. Types: `StrategyFile` (+ `platform`), `StrategyFileSyncStatus`, `CompileJobStatus`, `DeployJobStatus`; `ScanResult` carries `orphans: string[]` (DB strategies whose source file is gone) + `warnings: string[]`; `ReconcileResult` carries `removed: string[]` + `warnings: string[]`.

**Scan vs Reconcile (bidirectional delete).** Scan is read-only: `useScanStrategies` (`POST /strategies/scan`) adds/updates and its success toast flags the orphan count (`N orphaned (source deleted — use Reconcile)`). Deleting a source file from the repo propagates to the DB row + the deployed VPS file ONLY through an explicit action: `useReconcileStrategies` (`POST /strategies/reconcile`). On the `Strategies.tsx` header, a red **Reconcile (N)** button appears next to Scan **only when the last scan found orphans** (`scan.data?.orphans`), fronted by the shared `ConfirmDeleteModal` (imported from `pages/Backtests`) listing exactly which strategies will be removed. On success it invalidates `['lab','strategies']` + the strategy-files / sync-status keys, and surfaces any per-strategy VPS-delete warnings as error toasts. The per-strategy Delete button uses the same backend `remove_strategy` path. See backend CLAUDE.md "Bidirectional delete (reconcile)".

Each row in `StrategiesTab` has a Deploy/Compile/Run action driven by the **content-aware** `StrategyFileSyncStatus` (`needs_deploy` / `needs_compile`, not the old presence-only `in_sync`). `StrategyRow` takes the full `sync` object (via `syncByStrategy[s.id]`), and the Status cell shows a version chip `v{current_version}` (title tooltip: "Local vN · running vM") next to the state pill: amber **Needs deploy** (local source differs from what's deployed) → amber **Needs compile** (deployed but not compiled from that content) → green **In sync**. The action button mirrors the pill: `needs_deploy` → Deploy, else `needs_compile` → Compile, else Run. `handleDeploy` tracks `deployingId` and on success invalidates `sync-status`. **First-run:** every strategy shows Needs deploy until deployed once through the tracked path (no deploy-hash recorded yet — see backend CLAUDE.md). `StrategyVersion` type + `GET /strategies/{id}/versions` expose the full version history if a per-strategy view wants it.

