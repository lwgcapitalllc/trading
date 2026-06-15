# CLAUDE.md — ChartPanel (backtest candlestick panel)

**Purpose:** A strategy-agnostic candlestick chart for the backtest page, built on klinecharts v9. It renders whatever a `ChartSpec` declares and contains **zero** strategy-specific logic.
**Scope:** This folder only. The host page is `pages/BacktestDetail.tsx`.
**Status:** Building in numbered steps (see seed `docs/LWG_chart_panel_seed.md`). **Steps 1–6 done; Step 7a (real-spec emitter, real M15 candles) done.** Step 7b (strategy structure: overlays + indicators) remains.

---

## The one rule

No strategy or instrument names, and no strategy concepts (sessions, ranges, breakout levels), are hardcoded in this component. The panel draws **only** what the spec carries. Adding a new strategy later means the lab emits a different spec — the code in this folder does not change.

---

## Files

```
ChartPanel/
├── index.tsx          default export ChartPanel({ spec? }) — inits klinecharts, draws candles + overlays
├── types.ts           ChartSpec — the contract the lab emits per run (THE source of truth)
├── chartStyles.ts     klinecharts style object, derived from the app theme (no hardcoded hex)
├── overlays.ts        custom klinecharts overlay templates (registerChartOverlays, idempotent)
├── indicators.ts      shipped-series indicator: ensureSeriesIndicator + mapSeriesToCandles (pure)
├── sessions.ts        session placement math: tz + broker offset → broker-axis windows (DST-aware)
├── fixtures/audjpy.ts  AUDJPY_FIXTURE — hand-written stand-in spec until Step 7 wires real specs
└── CLAUDE.md          this file
```

---

## The contract (`types.ts`)

`ChartSpec` carries: `instrument`, `baseTimeframe`, `brokerGmtOffsetHours`, `candles`,
`sessions[]`, `trades[]`, `overlays[]` (`box`/`hline`/`vline`, each tagged with a `group`),
`indicators[]`. **All times are epoch milliseconds** (klinecharts' native unit) — convert at
the emitter, never in the browser. Indicator series are shipped from the run, **not recomputed
here**, so the chart shows exactly what the strategy saw.

---

## Conventions

- **Lazy-mounted.** `BacktestDetail.tsx` imports the panel via `React.lazy` inside a collapsed
  "Price chart" section. klinecharts (~205 kB) and the fixture only load when the section opens
  — verified as a separate build chunk. Keep it this way; never import this folder eagerly from
  a page.
- **Theme.** Colors come from the app theme via `chartStyles.ts` (it reads `@/themes/electric-indigo`,
  the same source `@/themes/chart` uses for Recharts). No raw hex in components. Grid is off.
- **klinecharts data shape.** Spec candles use `time`; klinecharts wants `timestamp`. The
  `candlesToKLine` mapper in `index.tsx` is the single conversion point.
- **Timeframe = display only.** The segmented control (`DISPLAY_TFS`, filtered to TFs ≥ and
  divisible by the spec's base TF) resamples base bars up with `resample` (epoch-aligned
  buckets). Higher-TF bars are display aggregations; `spec.baseTimeframe` is the source of
  truth. Switching TF re-applies data; it must NOT re-init the chart, so overlays (anchored by
  timestamp) survive the switch.
- **Overlays are registered once, created per-spec.** Custom templates live in `overlays.ts`
  (`registerChartOverlays()`, guarded so StrictMode/remounts don't double-register). The panel
  creates instances with `points` (anchored by `timestamp`) + `extendData` (colors/labels).
  `applyNewData` can clear overlays, so the overlay-build effect runs AFTER the data effect and
  re-creates everything on every TF switch / toggle. Geometry is derived from BASE candles so it
  is TF-invariant.
- **Sessions are data, placed DST-correctly.** `sessions.ts` converts a session's local time
  (its IANA `tz`) → true UTC (via `Intl`, reading the real offset per date) → broker axis
  (`+ brokerGmtOffsetHours`). Verified: London shifts BST↔GMT across the year; Tokyo is fixed.
  Boxes hug the high/low of the candles inside each window. Per-session toggles in the header.
- **Trades** (`TRADE` overlay): up-arrow (long) / down-arrow (short) at entry, dashed line to
  the exit, dot at the exit. Direction is shown by arrow orientation, not color; color is the
  theme blue (`theme.series[3]`, passed via `extendData` — `overlays.ts` stays theme-free). No
  exit-reason text on the chart. One on/off toggle for all trades. Supported figure types are
  `circle/line/polygon/rect/text` (verified via `getSupportedFigures`).
- **Generic overlays** (`BOX` / `HLINE` / `VLINE`): render `spec.overlays`, grouped by `group`,
  each group independently toggleable. This is what carries strategy structure (range box,
  buy/sell levels, breakout marker in the fixture) — the chart never knows which strategy made
  them. Style (`color`/`fillColor`/`lineStyle`/`lineWidth`) + `label` come from the spec via
  `extendData`. `vline` spans the pane height (`bounding.height`); its point `value` is a dummy
  (only `x`/timestamp matters).
- **Indicators are shipped, not recomputed.** `indicators.ts` registers one klinecharts indicator
  template per indicator NAME (so multiple on a pane don't collide). Its `calc` doesn't compute
  anything — `mapSeriesToCandles` looks the shipped value up by timestamp (last shipped point in
  each displayed bar's window = value as of bar close), so higher-TF display is correct and
  klinecharts re-runs calc automatically on TF switch (the indicator effect does NOT depend on
  `displayCandles`). `pane:'main'` overlays the price (`IndicatorSeries.Price`, candle pane);
  `pane:'sub'` gets its own pane. Sub-pane ids are tracked in a ref for clean removal. Colors come
  from `INDICATOR_PALETTE` (theme).
- **Daily session breaks** (`DAY_BREAK`): vlines at each interior broker-day boundary (candle
  epochs are broker wall-clock, so boundaries fall on `DAY_MS` multiples; the left edge is
  skipped). Separate overlay name from `VLINE` so the two toggle independently. Own toggle.
- **All layer toggles** use one `ToggleChip` component (colored dot + label).
- **Decision (2026-06-14):** no per-trade trade table exists on the backtest page yet (trades
  are collapsed into `equity_curve` points — no per-trade entry/exit). Per Aaron, the clickable
  trade list + row→zoom is **deferred to Step 7**, when the real spec emitter provides per-trade
  data. Step 4 ships the chart overlay + toggle only.
- **Lifecycle.** Chart is `init()`-ed once on mount and `dispose()`-ed on unmount; a
  `ResizeObserver` calls `chart.resize()`. Data is (re)applied in a `spec`-keyed effect so the
  spec can change without re-initialising.

---

## Step log

- **Step 1 — Scaffold (done).** Lazy "Price chart" section on `BacktestDetail`; klinecharts loads
  candles from `AUDJPY_FIXTURE`; themed from app tokens; grid off. `tsc` clean, `vite build` green,
  klinecharts confirmed in its own lazy chunk.
- **Step 2 — Timeframe switch (done).** M5/M15/M30/H1 segmented control resamples base bars up
  for display (`resample`, epoch-aligned). Verified 288 M5 → 96 M15 / 48 M30 / 24 H1 with correct
  OHLCV aggregation. Re-applies data without re-init so overlays stay anchored. `tsc`/`build` green.
- **Step 3 — Sessions (done).** Generic `sessionBox` overlay (`overlays.ts`) hugging the candles
  in each session window; placement via `sessions.ts` (tz + broker offset, DST-aware — verified
  London BST↔GMT, Tokyo fixed). Per-session toggles. Overlays rebuilt after data/TF changes.
  `tsc`/`build` green.
- **Step 4 — Trades (done, partial by decision).** `TRADE` overlay (entry arrow + dashed line +
  exit dot) and an all-trades on/off toggle. Trade prices in the fixture derive from candle
  closes so they sit on the price. Row-click select/zoom + trade list **deferred to Step 7** (no
  trade table exists yet). `tsc`/`build` green.
- **Step 5 — Generic overlays (done).** `BOX`/`HLINE`/`VLINE` templates render `spec.overlays`
  grouped by `group`, each group toggleable. Fixture carries a Range box + Buy/Sell levels +
  Breakout marker (all derived from candles). `tsc`/`build` green.
- **Step 6 — Indicators + breaks (done).** `spec.indicators` render as main-pane overlay (EMA) or
  sub-pane (ATR) from shipped series, each toggleable; values mapped by timestamp (verified base +
  M15 resample). Daily session breaks as `DAY_BREAK` vlines (verified one interior break in 2-day
  fixture). Fixture extended to 2 days. `tsc`/`build` green.
- **Step 7a — Real-spec emitter (done, real intraday).** Backend `services/chart_spec.py` builds a
  real `ChartSpec` per run (`GET /backtests/runs/{id}/chart-spec`, cached to the run dir).
  `useChartSpec` fetches it; `PriceChartSection` opens lazily and renders the real spec (loading /
  error / empty / daily-fallback states). Verified end-to-end on run `7030bcffd856` (USDJPY
  londonbreakout): **24,785 real M15 candles + 18 trades (real entry/exit prices) + 3 sessions**.
  **candles + sessions + trades only** — overlays/indicators empty.
  - **MT5 agent fix (deployed).** Getting intraday required two fixes: (1) `algos/.../mt5_agent.py`
    `/historical_data` now maps M5/M15/M30 and calls `symbol_select()` before `copy_rates_range`
    (was 400/404); (2) `chart_spec` fetches with the **canonical/root symbol** (`USDJPY`, not
    `USDJPY.s`) — `ohlc_fetcher`'s resolver re-adds the broker suffix from metadata, so passing the
    already-suffixed run symbol found nothing on the agent's plain-named terminal. The daily-fallback
    path remains for runs with no intraday history (e.g. NT8 futures).
- **Step 7b — Strategy structure (overlays + indicators). _pending._** Not captured by any run today;
  needs strategy-side logging or backend recompute (see the run's `params`: Asian range + ATR levels).
