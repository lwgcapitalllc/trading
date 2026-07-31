# CLAUDE.md — Command Center Frontend

**Purpose:** React + Vite + TypeScript app (`:5173`) — the UI for the command center; all server state via TanStack Query against the FastAPI backend.
**Scope:** This covers frontend hook/component/page conventions, the theme system, and routing. It does NOT cover the backend (see `../backend/CLAUDE.md`) or `algos/`/`smart-money/`.
**Status:** Live — all pages shipped (Overview, Smart Money, Bots, Strategies, Rulesets, Backtests lab, Optimizations, Tuning workbench, Stress Tests, Settings).
**Last reviewed:** 2026-07-30 — the News & Holiday filter **stopped duplicating the KPIs and now reshapes the real ones**. It has no section of its own: it is a pill on the empty half of the **Performance** header, driving the actual 12-card `KpiGrid` (via a synthesized filtered `Run`) plus the Equity chart, with each card's caption swapped for its delta vs unfiltered. Bank holidays became a real checkbox (ticked by default) instead of a hidden always-on rule, every label became a COUNT rather than a state word, and `exit_ms` on `EquityPoint` made **Avg Trade** computable over a subset. See `## The News & Holiday filter` below — especially the four things that deliberately do NOT follow the filter. Earlier: 2026-07-29 — the price chart's **fib levels are configurable** (add / remove / retune / recolour / hide, per drawing or as the tool's persisted default), and the News & Holiday filter became a collapsed-by-default accordion whose state lives in a page-level `useNewsFilter` hook, so the MAIN Equity chart redraws on the kept trades (its own duplicate mini-curve is gone); 2026-07-28 — price chart: a **Go to date** pill that jumps the view to a typed date (paging history in on the way); earlier, the Analysis dropdown (Trades + Winners/Losers, Blocked and **Missed** + per-reason filters), and it now ships/opens on the run's own timeframe with older history paged in on scroll-left

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
│   ├── useLab.ts            strategies, rulesets (useRulesets + useFirms alias), runs, evals, sweeps, optimizations, useChartSpec (price-chart panel), useRunNews (post-run news/holiday tags), useHistoryLimit (broker history floor → the date picker's min)
│   ├── useBots.ts
│   ├── useSmartMoney.ts
│   ├── useStressTests.ts    stress tests — useStressTests, useStressTest, useRunStressTest, useDeleteStressTest, useRunningStressLock, useStrategyBestGrades
│   └── useCalendar.ts       live News Calendar — useCalendar(fromMs, toMs) → GET /calendar?from&to, 45s poll, placeholderData keeps the prev week while paging
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
│   ├── ParamEditor.tsx      SHARED strategy-param editor used by all three editing surfaces (Run / Tune / Optimize) so they never drift. **Rows are STACKED — param label (plus the tune `was X` tag) on one line, control on the next** — because side-by-side gave the label only the leftover width and every label in the narrow tune rail truncated to `Arm on di...`, with the `was on` tag cropping it further. **Every control then renders at one size (`CONTROL_W` = `w-full max-w-[420px]` x `CONTROL_H` 34px) — toggle, select, number and switch alike** — so the list has one straight edge, a row's height never depends on its label, and a wide Run/Optimize modal doesn't stretch a toggle across half the screen. In optimize mode the number box (`NumberBox fill`) and the sweep button share that one width. Toggle state labels truncate (with a `title`) rather than wrap: a wrapping label used to grow its row and break the rhythm of the whole list. String params with a `choices` list render a **dropdown**, never free text — `choices` beats `widget`, because strategies match enum strings exactly and silently no-op on anything unrecognised, so a typo would disable a setting with no error. Essentials card (core knobs) + counted accordions, Simple/Expert switch, conditional `show_if` visibility, named toggle/switch/time widgets. Friendly labels/groups/descs/units/`core`/`options`/`guide` come from the schema (overlaid from a strategy's companion `<Strategy>.meta.json` by the scanner). Theme tokens only; colour rule: blue=focus only, gold=section-title text. `mode`: `run`|`tune`|`optimize`. `explainer`: `panel` (fixed right column — wide Run/Optimize modals) · `inline` (drops under the focused row) · `coach` (no per-row explainer — parent renders the exported `<ParamCoach>` footer; `onFocusChange` surfaces the focused param). Degrades gracefully with no metadata (no core → no Essentials card, all groups as accordions)
│   ├── PeriodPicker.tsx     shared backtest-period control (two ISO date inputs + 1Y/3Y/5Y/All presets + the start<end message) plus the `today`/`yearsAgo` helpers and the `PresetBtn` pill. Used by `RunBacktestModal` (new run), `BacktestDetail`'s `RerunModal`, and `StackConfigModal` so a period is picked identically everywhere. Takes an optional `limit?: HistoryLimit | null` (from `useHistoryLimit`) = the broker's MEASURED earliest backtestable date: it sets `min` on both inputs, **clamps the 1Y/3Y/5Y presets** to the floor (so "5Y" on a 4-year broker asks for what exists) and makes "All" mean all there IS, and renders a one-click **"Start at <date>"** fix — a native `min` stops the calendar widget but NOT a typed or pasted date. `limit == null` (non-python runner, agent down, unidentified broker) leaves the range fully open: the backend and data layer still refuse a bad window, so guessing a limit here could only be wrong. `source: 'seed'` renders as "last known — terminal unreachable" so a fallback is never mistaken for a measurement
│   ├── InfoTip.tsx          shared "ⓘ" hover tooltip for KPI/metric labels (BacktestDetail + StressTestDetail). Portalled to `<body>` with fixed positioning so a card's `overflow-hidden` can't crop it, AND clamped to the viewport on both axes — anchoring straight to the icon's rect pushed a right-edge card's tooltip (Calmar, last column) off-screen. Height is measured in a `useLayoutEffect` before paint, so it can flip below the icon when it won't fit above. `TIP_W` must stay in sync with the `w-[208px]` class — the clamp math reads it
│   ├── RulesetTypeBadge.tsx PROP EVAL / PROP FUNDED / PERSONAL / DEMO type badge for ruleset rows
│   ├── RobustnessGradeBadge.tsx  A/B/C/D/F letter grade pill
│   ├── GradeLegend.tsx      collapsible "Grade key" explaining A–F (mirrors backend services/grading.py) + the "target A or B before a bot" guidance; reused on the StressTests list. Uses RobustnessGradeBadge
│   ├── WorthinessLegend.tsx collapsible "Score key" explaining the worthiness tiers (STRESS TEST / OPTIMIZE / DISCARD; mirrors backend services/worthiness.py); shown above the Backtests Runs table. The Score-column companion to GradeLegend. Uses WorthinessBadge
│   ├── RegimeOverlayToggle.tsx  regime-band on/off pill (Layers icon + "Regimes"). SHARED by BacktestDetail's equity chart and TuningWorkbench's overlay — the tune page carried a plain checkbox, so one control looked like two different things on two charts meant to read as one system
│   ├── XModeToggle.tsx      Date / Trade # segmented switch for the equity x-axis. SHARED by BacktestDetail's equity chart and TuningWorkbench's overlay, and both read one stored preference (`lib/chartAxis.ts`), so the two pages can never disagree about the axis
│   ├── ChartTabPanel.tsx    shared tabbed chart chrome (tab strip + right-side slot + Expand button) and the portalled fullscreen `ChartModal`. **Fullscreen convention, app-wide:** the expanded view carries a **camera** (copy-as-image) button and closes with a **`Minimize2`** icon — never an X, and the inline chart never gets a copy button (expanding is what you do before sending someone the chart). `ChartModal` gives every Recharts chart both for free via `lib/chartImage.ts` (`copyChartAsPng`: clone the SVG → paint the page background in → 2× canvas → `ClipboardItem`, falling back to a download when clipboard image writes are blocked). The klinecharts price panel has its own canvas snapshot path and takes `showCopy` (host passes `isFullscreen`); the tuning workbench's own fullscreen wires the same two buttons. Extracted from BacktestDetail so StressTestDetail reuses it. Optional `aboveChart` slot renders KPI cards between the description and the chart
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
    ├── Backtests.tsx         lab landing — Runs / Sweeps / Stacks tabs. `CreateStackModal` (Stacks tab) picks 2+ Python strategies + one shared instrument/timeframe/costs/window; a live `useStackPreview` shows a green **Reuse** or amber **Run** chip per leg (reuse = a completed standalone run already matches these exact settings) + a summary; when every leg reuses, no backtest fires and the button reads **Create stack**
    ├── BacktestDetail.tsx    **Tune button carries a COUNT badge** of the iterations already run from this run (`source_run_id === runId`, off the unfiltered `useBacktestRuns()` so it shares the Runs list's cache entry) — clicking it opens the workbench where they all live. Without the badge the only way to discover a run had ever been tuned was to go back to the Runs list and spot the nested Tune rows. Full run detail — params side panel, per-firm evaluation + KPIs, tabbed charts, logs, News & Holiday filter (inline `NewsFilterPill`/`ExcludeRule`/`PerformanceHeader`, driven by the page's `useNewsFilter` hook — which feeds the KPI grid AND the Equity chart)
    ├── StrategyDetail.tsx    strategy "spec sheet" — overview + grouped param reference tables
    ├── SweepDetail.tsx       sweep results — live-updating table sorted by worthiness tier
    ├── StackDetail.tsx       portfolio stack (`/backtests/stacks/:stackId`). `composeCombined` unions the enabled legs' trades over one shared account (combined start = Σ each leg's opening balance) into a synthetic backtest-shaped `run` + portfolio equity, tagging each equity point with a `leg_<id>` running-balance field for the overlay lines. **Trades + Performance = a single backtest's two-column layout**: the left card (`StackTradesCard`, in the EVALUATION card's slot, height-matched via `KPI_ROW_H`/`_EXPANDED`) shows the per-strategy trade breakdown on top + the combined total at the bottom; the right is BacktestDetail's exported `KpiGrid` (6 core + 6 more, `fixedHeight`), `MoreMetricsToggle` below — all recomputing dynamically as strategies toggle. Charts are a `ChartTabPanel` (Equity / Price / Breakdown) with the SAME controls as a run: **Equity** is the real exported `EquityCurveChart` on the combined portfolio (so it inherits every toggle — Trade excursions, Run-ups & drawdowns, Date/Trade `XModeToggle`, Regimes `RegimeOverlayToggle`, expand) with a line per enabled strategy overlaid via the new `overlayLines` prop; Breakdown reuses exported `DrawdownChart`/`DailyPnlChart`/`DirectionBreakdown`; Price is exported `PriceChartView` fed the merged stack spec (structure layers/fib/measurement/expand/minimize, drill-down via `base_run_id`, trades layered + tinted per strategy). Regime bands come from `StackDetail.regime_timeline` (backend computes it on-demand for the shared window — sweep-child legs aren't tagged — and caches it). Everything recomputes on the per-strategy chips (≥1 always on). **Rerun** opens the shared `StackConfigModal` prefilled with the stack's full config. Per-strategy row → that leg's BacktestDetail with `state:{fromStack}` so its Back returns here; reused legs are real standalone runs. Trades handed to the price chart carry `layerColor` + `layerName`, which is what makes the chart print `<strategy> · Won` in each outcome chip and build its own **Strategies** dropdown (see `ChartPanel/CLAUDE.md`). `avg_trade_duration_min` is the legs' own averages **trade-weighted** (you can't average durations flat), and profit factor reports `Infinity` when the enabled legs have no losing trade — the KPI card prints ∞ rather than a dash that reads as missing data
    ├── Optimizations.tsx     own top-level page (/optimizations) — optimization list table
    ├── OptimizationDetail.tsx  optimizer results (/optimizations/:id) — table/bar-chart toggle, "Tune winner"
    ├── TuningWorkbench.tsx   /backtests/runs/:runId/tune — param editor + iteration leaderboard + regime overlay. The **Equity overlay** plots ACCOUNT BALANCE (not cumulative P&L from $0) off each run's own `equity_curve` — the same points BacktestDetail's equity chart draws — so the baseline traces an identical path there and here. It reuses that chart's conventions wholesale: starting balance derived as `equity[0] - profit[0]`, y-ticks anchored ON it, dashed break-even ReferenceLine, and the baseline as a monotone `Area` with `baseValue={startBal}` + the split green/red stroke and fill (split offset mapped to the filled shape's bbox, same math). Iterations ride on top as dashed palette Lines. Every run is anchored at the window's start date so the lines share a left edge, and balances FORWARD-FILL on days a run didn't trade (nulls + `connectNulls` drew a fake diagonal across flat stretches); `<runId>__pt` marks the real trade rows so only those get a dot. Regime bands come from ONE `date → regime` map, built TIMELINE-FIRST: the baseline's full-calendar `regime_timeline` if it has one, else any iteration's, else (pre-timeline runs) every run's tagged `daily_pnl` days merged — a run only reports days it traded, so any single run's tags leave the calendar full of holes. Fullscreen has the camera + minimize buttons. Its header controls are the run page's, in the run page's order and spacing — `XModeToggle` then `RegimeOverlayToggle`, `gap-2`. It carries the SAME `XModeToggle` as the run page and reads the SAME stored preference (`lib/chartAxis.ts` `getXMode`/`setXModePref`), so the two pages can never disagree about the axis: Date plots the calendar, Trade # keys each run's curve by trade ordinal (`balByIndex`) and a shorter run simply holds its final balance once it's out of trades. Regime bands project onto whichever axis is active — `regimeBandsFromTimeline` (date) or `regimeBandsByIndex` over the BASELINE's trades (trade #), both fed from one `date → regime` map, timeline-first
    ├── StressTests.tsx       stress test list — grade badge, prob breach/pass
    ├── StressTestDetail.tsx  stress test detail — grade card + tabbed Monte Carlo / Walk-Forward / Sensitivity workspace
    ├── Calendar.tsx          live News Calendar — Forex-Factory-style economic calendar. **Opens on today** (first mount selects today's day when on the current week with no explicit day; deselecting → whole week sticks). Day-summary strip (Mon–Sun counts, click-to-filter, Today button), "now" line + live countdown off the server clock, actual/forecast/previous with beat/miss colour. Filters (currency chips w/ country flags, independent High/Medium/Low impact toggles, category dropdown) + week offset + selected day all live in the URL. Fetches the whole week; filters CLIENT-SIDE so changes are instant and the strip counts stay in sync. Shared display helpers (flag map, impact colours, time/countdown formatters) live in `lib/calendar.ts` — reused by the Overview preview
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
- Sidebar nav items in `Sidebar.tsx` — one `SECTIONS` array grouped by what each item IS: an ungrouped **Overview** at the top, then **Lab** (Strategies → Backtests → Optimizations → Stress Tests, in lifecycle order), **Live** (Bots, Smart Money), **Reference** (Rulesets, Calendar). Add a new item to the section it belongs to
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

`pages/Rulesets.tsx`, route `/rulesets` (Reference group, with Calendar). Prop rows grouped by firm, personal/demo rows in their own group; page-level firm/Personal filter. Prop rows are read-only in the UI (server-side locked); personal/demo rows have an edit modal for the 5 personal rule fields.

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
3. Add an entry to the right group in `SECTIONS` in `Sidebar.tsx` (Lab / Live / Reference)
4. If it needs data, create `src/hooks/useThing.ts`
5. Add types to `src/types/index.ts`
6. If it's a stub, use `EmptyState` for the placeholder — replace when it goes live

---

## Lab UX principle

The lab is a platform for designing and stress-testing trading strategies, not a dashboard. Every page should help the user make a decision: is this strategy viable, which parameter set is most robust, does it survive Monte Carlo? Design for decisions, not metrics.

---

## Backtest detail — chart and KPI conventions

BacktestDetail's charts live in one tabbed panel (Equity / Price / Breakdown), each fullscreen-expandable, with a permanent Performance-by-Regime table below. KPIs render as a flat grid (6 core cards always shown, 6 more behind a toggle) that holds a fixed row height across firm switches so the layout never jumps. **Column one is wider than the other five** (`KPI_COLS` = `1.4fr repeat(5,1fr)`, shared by both rows so they stay aligned): it carries the money values, and a 5-figure `+$11,525` needs the extra room to render at the collapsed row's 34px without running through the card's padding. Fitting a long value is always solved by room, never by shrinking that one card's type — a KPI whose font differs from its neighbours reads as broken. `FitMoney` is the last-resort fallback for genuinely narrow windows: it measures the exact string against its cell and only then drops to `$11.5k`, never rounding harder than one decimal (`$12k` for `$11,525` reads as a different number), keeping 2px of slack off the edge and the exact figure on hover. Verdict colours, header chips, and tooltip styling all follow the shared theme tokens (see Theme system above) — nothing here is bespoke to this page beyond the tab/grid structure.

The Equity chart is a TradingView-style panel. **Its x-axis is the CALENDAR by default** (`xMode`, persisted; a Date / Trade # switch sits with the series toggles). Calendar is canonical: regime bands only have a true width on it, drawdown DURATION is a time metric, and it's the axis the tuning workbench overlays runs on — so the same run traces the same path on both pages. Trade # spaces every trade evenly and exists for per-trade forensics (streaks, excursions). `x` is the plotted position in whichever unit, and the regime bands, the run-up/drawdown ribbon and the starting-balance anchor (`windowStart` = the run's start_date in date mode) are all expressed in that same unit, so switching moves the chart together. Regime bands are built from ONE `date → regime` map (the run's full-calendar `regime_timeline` — see backend — falling back to `daily_pnl` tags on pre-timeline runs) and then PROJECTED onto whichever axis is live: `regimeBandsFromTimeline` (date) or `regimeBandsByIndex` (trade #, each trade taking its date's regime). The first band stretches back to the anchor and the last forward to the final point, and they render with `ifOverflow="visible"` — Recharts DISCARDS an out-of-domain `ReferenceArea` by default, which is why an earlier stretch silently did nothing. **Stretch AFTER filtering out UNKNOWN**, or the stretch lands on a band that never renders and the chart opens with a bare gap. Shared axis maths (`getXMode`/`setXModePref`/`dateMs`/`niceStep`/`monthTicks`/`monthLabel`/`tradeTicks`/`balTick`/`balanceTicks`/`regimeBandsFromTimeline`/`regimeBandsByIndex`) lives in `lib/chartAxis.ts` — used by BOTH equity charts so they can't drift. The cumulative-PnL line is **colour-split at the starting balance** (green above, red below — `startEq = data[0].equity - data[0].profit`, offset mapped to the fill bbox so the flip lands on the break-even line), the curve is **anchored** by a synthetic starting-balance point so it leaves the `startEq` line, the Y axis is tick-anchored on `startEq` (starting balance always labelled), and a dot on every trade point (hover → Balance + Favorable/Adverse excursion). Two opt-in `SeriesToggle`s: **one bottom-bar toggle** — on runs that carry excursion it draws the combined **Trade excursions** bar (solid net-result core + translucent favorable/adverse halo, in true dollars anchored on `startEq`), otherwise a plain profit **Histogram** — and **Run-ups & drawdowns** (green/red ribbon along the bottom, green while equity makes new highs). Regime bands skip UNKNOWN (chart matches the legend). The XAxis is `scale="point"` so the bars never shift the line. Excursion needs `favorable`/`adverse` on `models.EquityPoint` (else FastAPI drops them) — and so does `entry_ms`, which the News filter tags on; that one was missing until 2026-07-28, so read this as a rule, not a one-off.

**The Equity chart's DATA can be filtered — `equityCurve = news.filteredCurve ?? run.equity_curve`.** When the News & Holiday accordion is removing trades, this is the only chart on the page that follows it; the KPI grid beside it follows the same switch (`newsOnKpis`), and every OTHER number and chart on the page still reports the raw backtest. Two rules if you touch it. (1) A filtered curve MUST be rebuilt on the run's real starting balance (`equity = startBal + running profit`), never restarted from 0 — the chart derives `startEq` from its first point and anchors the axis, the break-even line and the green/red split there, so a zero-based curve silently rebases the whole panel. (2) Anything indexed off the curve must read the SAME curve — `regimeBandsByIndex` does, or in Trade # mode every band after the first removed trade sits one trade to the right of what it describes. Details in `FRONTEND_BUILD_NOTES.md`.

Full implementation detail (exact card set, fixed-height math, per-metric fallback rules, chart-specific quirks like the equity tooltip's segment-key filtering and the MT5 duration gap): `command-center/docs/FRONTEND_BUILD_NOTES.md`.

---

## The News & Holiday filter — it reshapes the REAL KPIs

**Reworked 2026-07-30. Read this before touching `useNewsFilter`, `NewsFilterPill` or `KpiGrid`'s `compare` prop.**

The filter has now shed a duplicate copy of the run's numbers **twice** — first its own 200px equity
curve, then its own five KPI tiles — and both times the answer was the same: **reshape the page's
real readout, never ship a smaller second one beside it.** It has no section of its own. It is a pill
on the **Performance** header (a row that was otherwise empty, so the control costs zero vertical
space) and it drives the actual 12-card `KpiGrid` plus the main Equity chart.

**1. A filtered run is a synthesized `Run`.** `buildFilteredRun` clones the run, overrides what the
trades determine (net P&L, win rate, PF, avg win/loss, drawdown, equity curve, daily P&L regrouped
with regime tags carried over by date) and then **NULLS every field derived from `daily_pnl`** so the
existing recompute path (`computeFallbacks`, `computeProfitConcentration`) redoes it off the filtered
series. The nulling is load-bearing — a left-behind `sharpe` is the raw run's, sitting in a grid
labelled filtered. This is the same transform `effRun` does for per-firm switching and
`StackDetail.composeCombined` does for a portfolio; three callers now want "synthesize a Run from a
trade list", so the next one should extract it rather than write a fourth.

**2. Four things cannot follow the filter, and none of them is faked.**
- **Per-firm SIZED runs block it outright** (`newsBlocked`). Sizing is path dependent — remove trade
  #7 and #8's position size changes, and every trade after it. That is a re-run, not arithmetic. The
  sized curve is also re-indexed 1..N over only that firm's taken trades, so the news tags (keyed on
  raw indices) would not even line up. The pill disables with that reason.
- **The firm Evaluation card** is computed server-side over every trade; it carries an `unfiltered`
  chip while Performance beside it is filtered.
- **`platform_sharpe`** is NT8/MT5's own whole-run number — no filtered version exists.
- **`sharpe_low_sample` is RECOMPUTED, not inherited.** Removing trades can only push a run *toward*
  too-few-days, so carrying `false` over would silence the warning exactly where it starts to matter.

**3. The Equity chart is gated on the SAME switch as the grid** (`newsOnKpis`). Holidays are excluded
without anyone touching a control, so on a blocked run the chart would otherwise quietly draw a
filtered curve under unfiltered numbers.

**4. Both exclusion rules are on screen, and both are switchable.** Bank holidays used to be
hardcoded always-on with no control and no row. That is what made the panel unreadable: the pill
counted trades being removed while the only visible switch said the news ones were *kept*, and
nothing accounted for the difference. Now each rule is an `ExcludeRule` row — tick, name, and **the
trades it matches whether or not it is ticked**, so the row doubles as the price tag on turning it
on. Holidays stay ticked by DEFAULT (still the standing preference); untick for the run exactly as
traded. Because a trade can match BOTH rules, `excluded` is measured off the kept list, never summed
from the two counts.

**5. Every label is a COUNT, never a state word.** "News kept" / "news filtered" read as "nothing
removed" while holidays were going out regardless. The pill says `Excluding N trades`, the header
says `Performance · 139 of 142 trades`, the popover footer says `139 of 142 trades counted`. A label
that is a number cannot say one thing while the grid says another.

**6. Deltas replace each card's caption, they don't crowd in beside it.** `KpiGrid`'s `compare` prop
runs the extracted `deriveKpis` a second time against the unfiltered run; `subFor` then swaps the
standing caption ("net of commissions") for `−$2,003 vs unfiltered`. The caption is read once; the
delta is the answer to the question the filter was opened to ask. Zero extra height. A card with no
`cmp` says "no filtered value" rather than showing a stale one.

---

## What's built (status)

| Module | Status | Notes |
|---|---|---|
| Overview | ✅ Live | Stat row + cards for each domain |
| Smart Money | ✅ Live | Scan, terminal, rankings, profiles, disqualified, config, cache |
| Bots | ✅ Live | Monitor, control, configure (risk caps + deploy), users |
| Backtests lab | ✅ Live | Runs / Sweeps tabs; run modal; BacktestDetail |
| Optimizations | ✅ Live | Own top-level page (`/optimizations`); detail at `/optimizations/:id`; "Tune winner" → workbench |
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
| News Calendar | ✅ Live | `pages/Calendar.tsx` (`/calendar`) — Forex-Factory-style economic calendar off the free TradingView feed. Opens on today; day-summary strip, server-clock "now" line + countdown, actual/forecast/previous w/ beat-miss colour, currency chips (country flags), independent High/Medium/Low toggles, category dropdown. Whole week fetched, filtered client-side; all filter/week/day state in the URL. Shared helpers in `lib/calendar.ts` |
| History-limited periods | ✅ Live | `useHistoryLimit` + `PeriodPicker`'s `limit` prop. The date picker's minimum is the broker's MEASURED earliest backtestable date (probed server-side per broker, never hardcoded here), presets clamp to it, and a typed/pasted earlier date shows a one-click "Start at <date>" fix. Wired in `RunBacktestModal`, `BacktestDetail`'s `RerunModal` (which also disables Confirm below the floor) and `StackConfigModal`. Prevents submitting a window MT5 would answer with coarser bars mislabelled as the requested timeframe. |
| Overview calendar preview | ✅ Live | `pages/Overview.tsx` — full-width "Economic Calendar" card below the module grid: next high-impact callout (flag + countdown) + a 2-col list of the next upcoming events this week; whole card navigates to `/calendar`. Reuses `useCalendar` + `lib/calendar.ts` |
| Settings | ✅ Live | Config read/write; `nt8_agent_tunnel` + `mt5_agent_tunnel` |
| Sidebar health strip | ✅ Live | 4 dots: API, SSH, NT8 (3-state), MT5 Agent |
| Price-chart panel | ✅ Live | Lazy klinecharts candlestick panel on BacktestDetail (`components/ChartPanel/`, own CLAUDE.md): TF switch (display resample up + M1→H1 drill-down w/ full-depth fetch + red "no earlier data" edge), sessions, generic overlays, indicators, day breaks, measurement + fib tools. The **fib LEVELS are configurable** TradingView-style — add, remove, retune, recolour or hide any level (extensions past 1.0 included) from a live editor, either as the tool's default ladder (gear on the tool strip, persisted) or for one drawing (its right-click menu); an un-customised fib follows the default live. **It SHIPS and opens on the timeframe the run TRADED, with no fetch** — the payload is capped by trimming the WINDOW (newest slice under `_CANDLE_CAP`; measured 33k candles / 3.1 MB / 17 months on a 2020→2026 15m run), never by coarsening the bars, so the chart paints on the first frame with no loading text and no swap. Older history **pages in as you scroll left** (one ~12k-bar chunk, ~1 MB, back to `spec.historyStartMs`), so trimming costs reach, not access — and a **Go to date** pill beside the timeframe types you straight there instead, driving that same pager itself until the date is loaded (klinecharts only ever pages one chunk, and only on reaching the left edge), then centring the target bar. **Two header dropdowns split by question:** *Analysis* = what the strategy did with its signals — **Trades** (+ Winners / Losers filters, so a run reads as all-winners or all-losers), **blocked setups**, the trades that never happened (a setup the strategy had ready and its own rules refused: a dashed line pointing at the exact would-be entry price with a uniform `Blocked` tag parked clear of the candles, every refusing rule on hover, and one filter per reason), and **missed setups**, the ones that DIED partway (the same marker with the score on the tag — `2/3` / `3/3` — and hover showing what it had vs the one thing it didn't; the routine reasons start unticked, driven by `spec.missNoise`, so the layer opens on the misses worth studying). Both default OFF and are listed only when the run reports any. *Structure* = what the market drew (structure groups + shipped indicators). Everything clock-driven — the session windows AND **Day breaks** — lives in the on-chart Sessions legend instead, so the two halves of "when did the day/session start" are in one place. Real spec via `useChartSpec`. **Market-structure overlays live** — the canonical `engines/market_structure/` engine replayed server-side (`chart_spec` → `structure_overlays.py`) into the 4 Structure toggles that mirror `structure_engine.pine` (External / Internal / Historic Internal Structure / Swing Point Labels — nesting like the Pine's via each overlay's `requires` list), default OFF, flat text tags anchored at each break line's midpoint (BOS/SOS/iBOS/iSOS), de-collided, on wick-anchored break lines |
| News & Holiday filter | ✅ Live (NT8 + Python) | **A pill on the Performance header that reshapes the page's REAL 12 KPIs** — no duplicated tiles, no section of its own (both were removed 2026-07-30). State lives in the page-level **`useNewsFilter`** hook because three things read it: the pill, the `KpiGrid` (fed `news.filteredRun`, a synthesized `Run` built by `buildFilteredRun`) and the main Equity chart (`news.filteredCurve`). Popover lists BOTH exclusion rules as `ExcludeRule` checkboxes — bank holidays (ticked by default, switchable) and high-impact news (with its before/after window sliders nested under it, default 15/30); each row shows the trades it matches whether ticked or not. News default = the strategy's `avoid_news`. Every card's caption becomes its delta vs unfiltered (`KpiGrid`'s `compare` prop). **Refused rather than faked:** per-firm SIZED runs block the filter (sizing is path-dependent), the firm Evaluation card carries an `unfiltered` chip, `platform_sharpe` goes null, `sharpe_low_sample` is recomputed. Coverage-honest (untagged where no calendar data; the pre-`entry_ms` note offers "Reload charts" on NT8 only). **Forex/MT5 not wired — TODO #3** (needs MT5 `entry_ms`/`exit_ms` + non-UTC broker timezone handling) |
| Portfolio stacks | ✅ Live | Stacks tab on Backtests + `StackDetail` page. Layer 2+ Python strategies over one shared instrument/timeframe/costs/window. **StackDetail renders like a single backtest on the combined portfolio** — reuses BacktestDetail's exported `KpiGrid` + chart components + `PriceChartView` against a client-side `composeCombined` payload (identical 6+6 KPIs, Equity/Price/Breakdown tabs, full price chart with structure/fib/measurement). New + Rerun share `components/StackConfigModal.tsx` (prefilled for rerun) — and so does the **Strategies page**: ticking 2+ python rows there reveals a gold **Stack N strategies** button that opens the SAME modal prefilled with them, so a stack is configured identically wherever you start it (the checkbox column only appears when 2+ python strategies are listed, and a non-python row has no checkbox because stacking replays python only). Per-strategy toggles drive everything (same `enabled` set, ≥1 always on); a leg's Back returns to the stack. **Smart reuse** — `CreateStackModal` calls `useStackPreview` (POST `/backtests/stacks/preview`) to show per-leg Reuse/Run chips; a leg whose exact settings already have a completed standalone run is reused (opens the real run on View), the rest re-run fresh. Costs default 0/0 (comm 0 / slip 0 / 15m) to match the Pine strategies (all pinned commission=0, slippage=0); these fields are cosmetic for Python runs (real cost comes from the account profile), so 0/0 keeps the display honest. Match is STRICT (any settings difference re-runs) |

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

**"Needs scan" pill (2026-07-23).** Separate from the deploy/compile sync above — it reads `Strategy.needs_scan` (on the strategy row itself, not `StrategyFileSyncStatus`), which the backend computes live (source hash / meta mtime vs last scan). When true, `StrategyRow`'s Status cell shows a clickable amber **● Needs scan** pill (calls `onScan` → `useScanStrategies().mutate()`, spins while pending) ABOVE the deploy/compile pills. It renders for ALL runners, and for a Python strategy — which has no deploy/compile step, so its Status cell was otherwise empty — it's the only status pill. `RunBacktestModal` shows a matching amber banner when `strategy.needs_scan` ("Parameters may be out of date … click Scan Strategies, then reopen"): the panel form is built from the last-scanned schema, so editing a Python `config.py`/meta without re-scanning silently runs on the OLD params (the bug that ran mpc_sos_fade on stale divergence-armed defaults). This is the Python analog of the MT5/NT8 deploy/compile badges.

