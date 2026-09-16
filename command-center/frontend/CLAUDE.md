# CLAUDE.md — Command Center Frontend

**Purpose:** React + Vite + TypeScript app (`:5173`) — the UI for the command center; all server state via TanStack Query against the FastAPI backend.
**Scope:** This covers frontend hook/component/page conventions, the theme system, and routing. It does NOT cover the backend (see `../backend/CLAUDE.md`) or `algos/`/`smart-money/`.
**Status:** Live — all pages shipped (Overview, Bots, Strategies, Rulesets, Backtests lab, Optimizations, Tuning workbench, Stress Tests, Settings). **Smart Money is built and flagged OFF** since 2026-08-04 — see *Feature flags*.



Auto-loaded by Claude Code when editing any file inside `frontend/`.

React + Vite + TypeScript app on `:5173`. All API calls go to the FastAPI backend on `:8000` via the Vite proxy at `/api`. Dark indigo-black UI, electric cyan accent, gold secondary.

**Lab design principle:** Run Backtest modal starts with no firms pre-selected. User must actively choose which firm challenges to evaluate against — never auto-select all.

**Say it once (Aaron, 2026-09-11).** Every fact appears ONCE on a page. A stat card over the list it counts, a header link to the row right under it, a chip and a sentence repeating a button's own label — each is a second copy, and Aaron reads every copy. Explanations go behind a hover or a fold (ⓘ, `title`, `<details>`), never as body text beside the control; wording that guards a live-money action stays on screen. When removing a copy, keep the one the reader acts on.

**Colour means one thing (Aaron, 2026-09-13).** Cyan = something you can click, the thing selected, or running now. Green / red = money up / down, pass / fail, and a health fault — never on a normal state (complete, in sync, ok) and never on a number whose sign is fixed by definition (a drawdown, a target). Amber = needs your attention. Gold = limits and rules, ★ markers, settings-group titles. Everything else is grey or white: a changed setting, a count, a market or mode badge, a chip naming an instrument or ruleset. **Before colouring anything, name which of those it is; if none, it is grey.**

---


**Last reviewed:** 2026-08-12 - the dated build narrative that used to sit here moved VERBATIM to `command-center/docs/FRONTEND_DIARY_NOTES.md`. **Nothing was deleted.** It was 110,551 bytes in 3 paragraph(s), the largest 47,237 bytes on a single line, loaded in full every time anyone opened this area. Rules stay here; the evidence is one file away.

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

## Feature flags — `src/lib/features.ts`

**Added 2026-08-04. Smart Money is OFF.** Aaron is leaning the command center down to
what he actually uses and Smart Money is not on the list for a while, so it is hidden
rather than deleted: the pages, hooks, types, backend router and the `smart-money/`
pipeline itself are all untouched, and flipping `FEATURES.smartMoney` back to `true`
restores the area whole.

**A flag hides an AREA, not a component — its nav row, its route and every card that
summarises it move together.** Hiding only the nav leaves a page reachable by URL,
which is not "removed"; hiding only the route leaves a nav row that goes nowhere. So
one flag is read in three places:

| Place | What it does |
|---|---|
| `Sidebar.tsx` | `NavEntry.feature` ties a row to a flag; `VISIBLE_SECTIONS` drops it, **and drops a section left with no rows** — a header over nothing |
| `App.tsx` | the routes are inside `{FEATURES.x && <>…</>}` |
| `Overview.tsx` | the stat cards and the module card, **and the hooks that feed them** |

- **Hidden means NOT FETCHED.** `useRunProgress` polls every 30s forever, so a card
  that is merely not rendered goes on costing a request twice a minute for a feature
  nobody can see. Both smart-money hooks took an `enabled` param for this; measured in
  a real browser, the Overview now issues **0** `/smart-money` requests.
- **A grid's column count must follow what is actually rendered.** Two cards left in a
  `grid-cols-4` row is half a row of blank space, which reads as data that failed to
  load. ⚠ Since 2026-09-11 the stat row holds ONLY the two Smart Money cards and renders
  with the flag (the bot count and balance were copies of the Bots list — *Say it once*), and
  the module cards are two fixed columns: Bots left; fleet controls, Smart Money and Research
  stacked right.
- **`FEATURES` is typed `Record<…, boolean>`, deliberately NOT `as const`.** With
  literal types every `FEATURES.x && <Card/>` narrows to `false` and TypeScript starts
  reporting the switched-off branch as dead code to delete, which is the one thing a
  flag exists to prevent.
- **`App.tsx` gained a `path="*"` redirect to Overview** in the same pass. An unmatched
  path rendered *nothing* — a blank main area beside a working sidebar — so a stale
  `/smart-money` bookmark looked like the app breaking. Verified: it lands on Overview.
- ⚠ **This does not retire the *add a route → add a NavItem* rule below** — it is that
  rule with a switch on it. Both still change in one commit.

Verified in a real browser at 1670×940: nav reads Overview / Strategies / Backtests /
Optimizations / Stress Tests / Bots / Rulesets / Calendar / Settings, the string
"Smart Money" appears nowhere on the Overview, and `/smart-money` redirects.

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
- Loading → `Shimmer` placeholders, per *Loading states — the shimmer pattern* below; `value="—"` for `StatCard`
- Status indicators → use existing `StatusPill` / `StatusDot` patterns, don't invent new shapes
- All tab state → `useSearchParams` (see above)

---

## Standard components — use before building new

| Component | Use for |
|---|---|
| `StatCard` | All stat tiles. Supports `value="—"` loading, `onClick`, `disabled` |
| `EmptyState` | Empty data screens — icon + title + description |
| `Shimmer` | Every loading placeholder — see the next section |

Extend an existing component with a new prop before forking a near-duplicate.

---

## Loading states — the shimmer pattern (2026-09-10)

**The app's ONE way to show that data is on its way: `components/Shimmer.tsx`**, a block shaped
like the content it stands in for, with a light band sweeping across it. Aaron: *"so that the UX
looks clean and it doesn't look like the page is hung or waiting on anything."* First applied to
the Bots page and its two drawers; **apply it to any page you touch that has a loading state.**

🔴 **A shimmer means STILL ASKING, and never "could not ask".** Gate it on the query's FIRST read
(`isLoading` / `isPending`), never on the data being absent — a FAILED read is also absent, and a
shimmer over a dead link is a page that looks busy for ever while the thing behind it is down.
Failed renders its words (`unknown`, the error line); answered-with-nothing renders that. ⚠ The
Bots account card's equity is a dash in both of those since 2026-09-14 — the error line is what
says the read failed. **Three states, three looks** — the repo's rule 1, applied to loading.

🔴 **A finding may not be shown while its source is still being asked.** The Bots page printed
`balance unread`, `net unknown`, `type unknown`, `No version` and **`No bots registered`** for the
~4s the trading box takes to answer — five faults reported about a healthy fleet on every load.
Each now shimmers until its OWN source has answered.

- **Only the first read shimmers.** A background refetch keeps the data on screen; blanking a 60s
  poll back to placeholders makes a live page flicker every minute.
- **Same size, same place.** Size each block to the value that lands there, so nothing moves when
  it arrives — MEASURE before/after heights, never eyeball them. ⚠ **In a row aligned on text
  baseline, pass GHOST CONTENT** (`<Shimmer>$00,000.00</Shimmer>`): it renders invisible and gives
  the block the real value's exact size and baseline. An empty block has no baseline and sat 3px
  low on the Bots account heading.
- **Shimmer only what is waiting.** Render what is already known — headings, labels, the account
  list — and never gate a whole page on its slowest read. Fixed words (a column heading, a section
  title) are rendered REAL, not shimmered.
- **Reuse the real component's loading state** in a page-level placeholder rather than drawing a
  private copy of it — the Bots page skeleton renders the same net figure, P&L cell and version pill
  the real card does.
- **No "Loading…" text or spinner beside a shimmer** — they say the same thing twice.
- **Start independent reads in parallel.** A read keyed off another read's answer cannot begin
  until that one lands; the Bots version pills waited ~4s for the snapshot before their own ~4.5s
  read could start, and are now keyed off the config list instead.

⚠ **Theme tokens only**; the sweep stops under reduced-motion. 🔴 **The sweep is
`animate-skeleton-sweep` in `src/index.css` — never Tailwind's `animate-shimmer`, which SLIDES an
element across the screen.** The first build redefined that one in `tailwind.config.js`, which a
running dev server reads only at startup, so Aaron's app drew every block flying over the text.
**Put an animation a shared component depends on where a running server hot-reloads it.**

⚠ **Pages still carrying a PRIVATE skeleton** (built on `animate-pulse`, before this existed) —
migrate each to `Shimmer` when you are next in the file, never as a drive-by across all of them:
`Backtests` (`RunsTableSkeleton`, also used by `Optimizations`), `Strategies`, `Rulesets`,
`Overview` (`BotsCardSkeleton`), `StrategyDetail`, `BacktestDetail` (page and chart skeletons).

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

## Routing

- Routes defined in `App.tsx`
- Sidebar nav items in `Sidebar.tsx` — one `SECTIONS` array grouped by what each item IS: an ungrouped **Overview** at the top, then **Lab** (Strategies → Backtests → Optimizations → Stress Tests, in lifecycle order), **Live** (Bots; Smart Money sits here too and is flagged OFF), **Reference** (Rulesets, Calendar). Add a new item to the section it belongs to. A row carrying a `feature` key is dropped when its flag is off — see *Feature flags*
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

`ParamSchemaEntry` carries `category?: 'strategy_logic' | 'foundational'`. Foundational params are never shown as editable inputs in `RunBacktestModal` or the optimizer grid — both filter them out; `RunBacktestModal` shows them read-only instead, pulled from the selected ruleset. `RunBacktestModal` also carries a **Sizing Mode** toggle (Consistent | Bullet) that picks how the dynamic sizing engine turns a strategy's unit-size signals into real contracts — it only affects strategies reshaped for the engine and is inert for the rest.

**Max Lot Size (2026-09-03, Aaron's ask: every test, every strategy, 100 by default, resize rather than refuse).** A `Cap at` / `No ceiling` pair plus a lots box, python runs only. ⚠ **It is deliberately NOT hidden alongside Sizing Mode.** That section hides for a self-sizing strategy because the engine is not deciding the size — but the ceiling lives on the run's ACCOUNT, which every strategy's sizing passes through, so it binds a self-sizing strategy too and every python bot here is one. Hiding it with its neighbour would have made the setting invisible on exactly the strategies it governs. ⚠ **`No ceiling` sends `null`, which is a real instruction and not an empty box** — it is the only way to reproduce a run made before 2026-09-02, when the account's own default became 100. ⚠ **Non-python runners send `undefined`, dropping the key**: NT8 and MT5 size inside their own platforms and never reach this account, so recording a ceiling for them would be a claim about code that does not exist. ⚠ **The explainer says what the ceiling COSTS, not just what it does** — past it, risk per trade falls as the balance grows and compounding turns linear, so a long run stops describing a tradeable account. A control that only says "capped at 100" would leave the reader to discover that from a flat equity curve. Behaviour and the measured cost: `backtest/CLAUDE.md` → *the VENUE CEILING*. `BacktestDetail` renders the resulting sized account as its own chart tab, timeline table, and per-firm KPI switching (a strategy makes the same trades for every firm, but each firm's ladder/floor sizes and halts them differently).

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

BacktestDetail's charts live in one tabbed panel (Equity / Price / Breakdown), each fullscreen-expandable, with a permanent Performance-by-Regime table below. The numbers above them render as **`PerformancePanel` — one row of four question cards** (see the section below). **`FitMoney` never abbreviates (2026-08-01).** It renders the full thousand-separated figure and, when one genuinely cannot fit, shrinks the TYPE — `$14.4M` and `$846.3k` are harder to read than the number they replace, and reading it is the entire job of a headline. `dollarShort` is deleted; do not reintroduce a `k`/`M` form here. **The measurement is the part that breaks silently:** it must measure against the hero ROW (`data-fit-box` on `CardHero`), never against its own span, which is a content-sized flex item whose width IS the text's width — so `need > avail` was true by exactly the slack, on every value, forever. That is why `+$14,387,475` rendered as `$14.4M` in a card with room for it twice over. The same trap is already recorded below for `PanelRow` values ("do not use `FitMoney` here"); it applied to the hero too and was missed. Because a CSS transform leaves the layout box at natural size, the wrapper pins its own width to the scaled width — otherwise the unit label beside it sits where the unscaled text ended. Verdict colours, chips, and tooltip styling all follow the shared theme tokens (see Theme system above) — nothing here is bespoke to this page.

## Browser tests — `npm test`, and what deliberately is NOT in them

**Added 2026-08-05.** This folder had no test runner at all: the convention was "verify it in a
real browser", done by hand, which is why the Overview's twelve defects each survived until
somebody looked. `@playwright/test` + `tests/*.spec.ts` keeps those checks runnable —
**229 tests in 21 files** (counted 2026-08-20 with `npx playwright test --list`; the figure here had
been left at a stale "66 in 5" through several passes — re-count it rather than incrementing it),
run with `npm test` from `frontend/`.

---

## The notes — read the matching file BEFORE touching its code

🔴 **This file was 451 KB on 2026-09-13 and loaded in full every time anyone opened
a file in this folder.** Everything outside the rules above moved VERBATIM into
`notes/` — nothing reworded, nothing dropped.

**How to write here from now on:** a rule gets ONE line under its topic below; its story and
evidence go in that topic's notes file. A notes file satisfies the commit hook's doc check.

⚠ **An old pointer to a section of this file still resolves** — every moved heading is
listed below under the notes file that now holds it.

### `notes/toasts.md` — Toasts

**Read before touching:** adding or debugging a toast, or a query invalidation that toasts.

- Toasts

### `notes/layout.md` — Directory layout

**Read before touching:** adding, renaming or looking for a frontend file.
Most-cited code: `lib/chartAxis.ts`, `api/client.ts`, `lib/chartImage.ts`, `lib/calendar.ts`.

- Directory layout

### `notes/bots-page.md` — The Bots page

**Read before touching:** the Bots page, a bot row, the bot panel, add/remove/move a bot, syncing bots from the VPS.
Most-cited code: `components/Drawer.tsx`, `components/FleetControls.tsx`, `pages/Bots/AccountForm.tsx`, `pages/Bots/AddBotPanel.tsx`, `lib/accountEarnings.ts`, `lib/botLabel.ts`.

- A settings GROUP must not hardcode a number one of its rows owns (2026-08-21)
- The Bots page: one list, one drawer, no tabs (2026-09-05)
- A bot row names what it is DOING — Stopping / Starting / Restarting (2026-09-10)
- "Backtest these bots" opens the builder FILLED IN by the server (2026-09-10)
- "Sync VPS" — scan first, then a Sync button (2026-09-10)
- "Add a bot" lists FREE bots only, and an empty account asks for its cap there (2026-09-11)
- "Remove from account" is a button in the bot panel (2026-09-11)
- The demo account after its bots went live — five things it got wrong (2026-09-11)
- The two panels: one budget, and no dead end on add, move or risk (2026-09-11)
- Two copies share a NAME, so the bot panel says LIVE or demo (2026-09-11)
- 🔴 Never sum a number across bots that SHARE it (2026-09-04)
- One status per row (2026-09-12)
- The bot panel says each thing once (2026-09-12)
- A running bot is stopped first, never locked (2026-09-13)
- Take off is ONE button on both panels (2026-09-13)
- Accounts are a RAIL + DETAIL, and one per kind can be PINNED open (2026-09-15)
- The detail column is ONE fleet table — headings once, five tracks, a needs-you line (2026-09-15)
- The account header — a stat cluster instead of a boring row (2026-09-14)
- The equity is what MT5 gave — a figure, its read time, or a dash (2026-09-14)
- The bot panel: one action row, Remove instead of Take off, issues that stand out (2026-09-14)
- The Equity slot's real fix, and an explicit "no bot" status (2026-09-15)
- Every strategy is a standing placeholder — "Add a bot" offers ALL of them, forever (2026-09-14)
- The Bots page shows what each BOT made, and colour means one thing (2026-09-05)
- Copying a stress test's settings onto a bot — the list IS the change (2026-09-06)
- 🔴 The page may NOT add the risk shares up itself (2026-09-04)
- Shares past the cap SHARE the room, and the account panel has a PRIORITY list (2026-09-15)
- The bot ROWS are the priority order, and you drag them there (2026-09-16)
- A blank cell is not a diagnosis — the Bots page's `No MT5 link` chip
- The affirmation ribbon, and why it holds still
- Key UI decisions

### `notes/accounts-broker.md` — Accounts and broker connections

**Read before touching:** the Accounts tab, adding/editing a broker account, moving a bot between accounts.
Most-cited code: `pages/Bots/AccountForm.tsx`, `lib/brokerName.ts`, `lib/costLayers.ts`.

- The Accounts tab is a RAIL + DETAIL, not a stack of cards (2026-08-12)
- Adding a broker account — the control that did not exist (2026-08-12)
- Dragging a bot onto an account in the RAIL — a second GESTURE, never a second path (2026-08-12)
- An account is named by its NICKNAME, else its broker (2026-09-13)
- The account net is measured off what went IN, and the page says which (2026-09-12)
- A broker account is printed in words — `lib/brokerName.ts` (2026-09-13)
- A LIVE account's Telegram channels — entered on the form, tested from the box (2026-09-13)
- The account settings: a setup checklist, the MT5 facts locked, three cards (2026-09-13)

### `notes/version-deploy.md` — Version banner, fleet strip and strategy deployment

**Read before touching:** the version banner, the fleet strip, deploying/promoting a strategy.
Most-cited code: `lib/botVersion.ts`, `pages/Bots/ConfigureTab.tsx`, `components/StepProgress.tsx`.

- The version banner — "am I behind, and by how much" (2026-08-07)
- The fleet strip re-reads itself, and its labels are about the BOT (2026-08-28)
- Strategy deployment manager
- The scheduled-job status gained an ARMED value (2026-08-21)

### `notes/overview-sidebar.md` — Overview, sidebar and the Calendar page

**Read before touching:** the Overview page, the sidebar, the Calendar page.
Most-cited code: `lib/calendar.ts`, `pages/Calendar.tsx`, `pages/Overview.tsx`, `components/SystemHealthStrip.tsx`, `hooks/useCalendar.ts`.

- What's built (status)
- Two dots that were not measuring what they said
- The Calendar page was audited 2026-08-05
- The Overview was audited 2026-08-05, and its job was to be WRONG quietly
- Decided 2026-08-05: the Overview does NOT get its own health strip
- The sidebar stopped pulling three lists to draw three dots
- The `Needs review` chip — a notification is a moment, a chip is a state

### `notes/backtest-results.md` — Backtest results page — KPIs, costs and the period filter

**Read before touching:** the backtest detail page's KPI panel, chart, cost switch, period filter, or the Backtests list.
Most-cited code: `lib/chartAxis.ts`, `lib/inputs.ts`, `components/periodWindow.ts`, `hooks/usePeriodWindow.ts`, `components/runSettings.ts`, `lib/runner.ts`.

- The News & Holiday filter — it reshapes the REAL KPIs
- Costs are switchable in TWO places, and the split is about arithmetic, not about UI
- The period filter — read a WINDOW of a finished run, with no rerun (2026-08-16)
- `useHistoryLimit` takes the run's PARAMS, and omitting them is the defect (2026-08-15)
- The strategy page leads with a TL;DR; its stacks list became a filter (2026-09-13)
- The Backtests list and the Backtest detail page — audited 2026-08-06

### `notes/strategies-stacks.md` — Strategies page and multi-leg stacks

**Read before touching:** the Strategies page, a stack's run panel, leg toggles, shared-account stacks, the stack form.
Most-cited code: `components/runSettings.ts`, `components/RegimeOverlayToggle.tsx`, `api/client.ts`.

- The Strategies page — audited 2026-08-06
- A stack renders a RUN's panel — same four cards, and the legs are the Verdict card's rows
- A leg toggle swaps in the SOLO CONTROL — it does not slice the shared book
- A loss-recovery leg is a TICK BOX ON ITS PARENT, never a row in the picker (2026-08-21)
- The stack form gained a BROKER, a COST SWITCH and PER-LEG RISK (2026-09-02)
- A NEW stack is always a SHARED ACCOUNT — the mode picker is gone
- The shared account is two rows in the Verdict card (2026-09-13)
- A running stack has ONE progress readout (2026-09-03)
- The regime overlay is OFF by default, from ONE hook
- The portfolio line is green and no leg may be confusable with it
- Shared-account stacks — the mode has to be on screen before any number is
- A whole strategy SET gets the same three hops one strategy gets (2026-09-07)

### `notes/stress-tuning-optimizations.md` — Stress Tests, Tuning workbench and Optimizations pages

**Read before touching:** the Stress Tests page, the Tuning workbench, the Optimizations page.
Most-cited code: `pages/StressTestDetail.tsx`, `pages/TuningWorkbench.tsx`, `api/client.ts`.

- The Stress Tests page — audited 2026-08-05
- The Tuning workbench — audited 2026-08-05
- The Optimizations page — audited 2026-08-04, and it had never been run
- ProgressCard pattern (SweepDetail / OptimizationDetail)

### `notes/run-modal-costs.md` — The Run modal and stack-form settings

**Read before touching:** the Run modal, the stack form's settings, re-pricing a run.

- The Run modal's Costs section is ONE SWITCH, on by default (2026-08-24)
- The Run modal's broker DEFAULTS to the attached terminal (2026-08-24)
- The Run modal: BROKER first, and it rewrites the symbol (2026-08-26)
- The re-price control dies on a charged run, and a PAIRED RE-RUN replaces it (2026-08-24)
- The stack form: one timeframe PER LEG, and the broker's own symbol (2026-09-03)
- The stack form: the account first, every number typed, a list that holds still (2026-09-10)

### `notes/browser-tests.md` — Frontend browser tests

**Read before touching:** writing or changing a Playwright spec, the offline-spec fixtures, or the ESLint setup.
Most-cited code: `components/ChartPanel/tradeGeometry.ts`, `components/paramConditions.ts`, `lib/features.ts`.

- ESLint runs on this folder, from a config at the REPO ROOT (2026-08-14)

### `notes/instrument-picker.md` — The instrument picker

**Read before touching:** the instrument picker, symbol search, per-broker recents.
Most-cited code: `components/InstrumentPicker.tsx`, `lib/instrumentSearch.ts`, `lib/instrumentRecents.ts`.

- The instrument picker — the broker's OWN list, searchable, with recents (2026-09-07)
- The stop-protection switch on a bot, with its measured cost beside it - `notes/bots-page.md`
