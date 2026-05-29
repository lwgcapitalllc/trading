# CLAUDE.md — Command Center Frontend
## Standing Instructions for Claude Code

This file is auto-loaded by Claude Code at the start of every session.
Read it before touching any code in `frontend/`.

---

## What this is

React + Vite + TypeScript app served on `:5173`. Talks to the FastAPI backend
on `:8000` via the Vite proxy at `/api`. Dark indigo-black UI with electric
cyan accent and gold secondary. Built for hours-long use — quiet, readable,
non-fatiguing.

Stack:
- React + TypeScript
- Vite (dev + build)
- React Router (client routing)
- **TanStack Query** for all server state (`@tanstack/react-query`)
- **sonner** for toasts (every mutation, every error)
- **TailwindCSS** with the custom theme in `tailwind.config.js`
- **Lucide React** for icons (no other icon libraries)
- **Recharts** for charts (no D3 directly, no other chart libraries)

That stack is intentionally minimal. **Do not add new UI libraries** (no MUI,
Ant, Radix, Chakra, Headless UI) without raising it first.

---

## Directory layout — where things go

```
frontend/src/
├── App.tsx                ← Router + layout shell
├── main.tsx               ← Entry point
├── api/
│   └── client.ts          ← Fetch wrapper — the ONLY place fetch() lives
├── types.ts               ← TypeScript types mirroring backend Pydantic models
├── pages/                 ← One file per route
│   ├── Overview.tsx
│   ├── SmartMoney.tsx
│   ├── Bots.tsx
│   ├── Backtests.tsx       ← Lab landing — sub-tabs handle the rest
│   ├── BacktestDetail.tsx
│   ├── StrategyDetail.tsx
│   ├── StressTests.tsx
│   └── Settings.tsx
├── components/            ← Reusable, dumb components
│   ├── Sidebar.tsx
│   ├── TopBar.tsx
│   ├── StatCard.tsx
│   ├── ScaffoldBanner.tsx
│   ├── EmptyState.tsx
│   ├── SystemHealthStrip.tsx
│   ├── RunBacktestModal.tsx
│   ├── EvaluationCard.tsx
│   ├── EquityCurveChart.tsx
│   └── DailyPnLChart.tsx
└── hooks/                 ← TanStack Query hooks, one file per domain
    ├── useBots.ts
    ├── useSmartMoney.ts
    └── useLab.ts          ← strategies, firms, runs, evals, system health
```

**Path aliases:** `@/` resolves to `src/`. Always import via alias:
`@/api/client`, `@/hooks/useLab`, `@/components/StatCard`, `@/types`.

---

## Hook conventions

One hooks file per backend domain. Every hook wraps a single endpoint.
Reference `useSmartMoney.ts` as the canonical pattern.

```typescript
// Read — useQuery
export function useThings() {
  return useQuery({
    queryKey: ['things'],
    queryFn: () => api.get<Thing[]>('/things'),
    refetchInterval: 30_000,   // optional
  })
}

// Write — useMutation with toast + invalidate
export function useCreateThing() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: ThingCreate) => api.post<Thing>('/things', body),
    onSuccess: () => {
      toast.success('Thing created')
      qc.invalidateQueries({ queryKey: ['things'] })
    },
    onError: (err) => toast.error(`Create failed: ${err}`),
  })
}
```

**Rules:**
- Never call `fetch()` directly. Always go through `api.get/post/put/patch/delete`.
- Every mutation has `onSuccess` with a toast AND `qc.invalidateQueries` for affected query keys.
- Every mutation has `onError` with a `toast.error` — `api/client.ts` already shows a generic toast, but per-action context is better.
- Query keys: `[domain, resource]` or `[domain, resource, id]`. Match what's used elsewhere.
- For polling that varies by state (running vs idle), copy the pattern in `useRunProgress` in `useSmartMoney.ts`.

---

## Component conventions

Components are **dumb**. They render props, fire callbacks, and use hooks for
data. No business logic, no inline calculations of pass/fail, no fetch calls.

```typescript
// GOOD — page-level hooks, component-level rendering
export function BacktestDetail() {
  const { runId } = useParams()
  const { data, isLoading, isError } = useBacktestRun(runId)
  if (isLoading) return <LoadingState />
  if (isError || !data) return <ErrorState />
  return <BacktestDetailView run={data} />
}

// BAD — component fetches its own data
export function BacktestDetailView() {
  const [data, setData] = useState(null)
  useEffect(() => { fetch(...) }, [])   // NO
}
```

**Rules:**
- Pages own data fetching. Components own rendering.
- All numbers render with `font-mono tabular-nums` (the theme has `mono` utility).
- Status indicators (running/stopped/error) use the existing pills and dots —
  copy the patterns from `Overview.tsx` (`StatusPill`) or `Sidebar.tsx`
  (`StatusDot`). Don't invent new shapes.
- Loading states: skeleton (see `BotsCardSkeleton` in Overview.tsx) for
  cards/tables; `—` placeholder in `StatCard`'s value prop for individual
  numbers.

---

## Reuse the standard components

Before building a new component, check if one of these fits:

| Component | Use for |
|---|---|
| `StatCard` | All stat tiles. Has loading (`value="—"`), interactive (`onClick`), and disabled states. |
| `ScaffoldBanner` | Yellow warning banner on stub pages. Delete the banner when the page becomes real. |
| `EmptyState` | Empty data screens — icon + title + description. |
| `StatusDot` (in Sidebar) | Health dots — green/red with tooltip. |
| `StatusPill` (in Overview) | Running/stopped/error chip. |

If something almost fits but not quite, **extend the existing component** (add
a prop) instead of forking a near-duplicate.

---

## Theme tokens — never hardcode colors

`tailwind.config.js` is the source of truth. Use the semantic tokens:

| Use | Class |
|---|---|
| Primary text | `text-text-primary` |
| Secondary text | `text-text-secondary` |
| Tertiary / dim text | `text-text-tertiary` |
| Surface | `bg-bg-surface`, `bg-bg-sunken`, `bg-bg-base` |
| Borders | `border-border-subtle`, `border-border-default` |
| Interactive accent | `text-accent`, `bg-accent`, `border-accent` |
| Profit / pass / running | `text-pos-text`, `bg-pos-muted` |
| Loss / fail / error | `text-neg-text`, `bg-neg-muted` |
| Warning / yellow flag | `text-warn-text`, `bg-warn-muted` |
| Highlights (shortlist) | `text-gold-text`, `bg-gold-muted` |

**Never put a raw hex color in JSX or inline styles.** If you need a new
token, add it to `tailwind.config.js` first.

The only inline style exceptions are dynamic values (glow strengths, computed
positions) and the brand gradient in `TopBar.tsx` — both already documented.

---

## Routing & navigation

- Routes defined in `App.tsx`.
- Add new routes to the sidebar via `Sidebar.tsx` — `WORKSPACE` for live
  modules, `RESEARCH` for lab-side modules.
- Mark a route with `live: false` to show a "Soon" badge.
- Navigation between pages: `useNavigate()` from `react-router-dom`. Don't
  use `<a href>` for in-app links.

---

## Toasts

`sonner` is wired globally. Use only via:

```typescript
import { toast } from 'sonner'

toast.success('Saved')
toast.error('Failed: ...')
```

Rules:
- Every user-initiated action that changes state → toast on success AND failure.
- Reads do not toast. The `api/client.ts` wrapper already toasts hard errors.
- Don't toast for navigation, hover, or query refetches.

---

## What NOT to do

- Don't call `fetch()` directly. `api/client.ts` is the only entry point.
- Don't hardcode colors. Tokens only.
- Don't put business logic in components. Compute in hooks or in the backend.
- Don't forget `qc.invalidateQueries` after a mutation. Stale data is a bug.
- Don't create new "loading spinner" or "empty state" components. Use the
  ones that exist.
- Don't introduce a new UI library, animation library, or chart library
  without raising it first.
- Don't use `any` in TypeScript. If you need a flexible type, define it.
  `unknown` + narrow is fine; `any` is not.
- Don't store server state in `useState` or React context. It belongs in
  TanStack Query.
- Don't bypass the path aliases. Always `@/...` imports, never relative
  paths that escape the current folder (`../../../`).

---

## When you add a new page

Checklist:

1. Create `src/pages/PageName.tsx` following the established shape.
2. Add the route in `App.tsx`.
3. Add a `NavLink` in `Sidebar.tsx`. Place under `WORKSPACE` if it's a live
   module, `RESEARCH` if it's a lab-side module.
4. If it has its own data, create a `src/hooks/useThing.ts`.
5. Add any new types to `src/types.ts`.
6. If it's a stub, use `ScaffoldBanner` + `EmptyState`. Delete both when the
   page becomes real.

---

## When you finish a milestone

If you replace stub content with a real page, **delete the `ScaffoldBanner`**.
Stale "Coming soon" banners on live pages are confusing.

Update this file's directory layout section if you added new components or
hooks worth knowing about.
