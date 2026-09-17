/**
 * The price-chart BODY every run-shaped page draws: the klinecharts panel plus its loading, empty,
 * error and fullscreen chrome, fed an already-fetched ChartSpec. Moved VERBATIM out of
 * `pages/BacktestDetail.tsx` on 2026-09-17 (see `frontend/notes/backtest-results.md` → *The analysis panels are shared*).
 */
import { Suspense, lazy, useEffect, useRef, useState } from 'react'
import { Minimize2, RefreshCw } from 'lucide-react'
import type { ChartPage, ChartSpec } from '@/components/ChartPanel/types'

// Lazy so klinecharts + the chart fixture only load when the Price chart section opens — but the
// import is NAMED so the run page can start it in the background on mount (`preloadChartPanel`)
// rather than at the moment the tab is clicked. A second call is free: the module registry
// resolves the same promise, and `lazy()` reads that already-settled promise instead of a fetch.
const importChartPanel = () => import('@/components/ChartPanel')
const ChartPanel = lazy(importChartPanel)
export function preloadChartPanel() {
  void importChartPanel()
}

export function ChartLoadingSkeleton({ height }: { height: number }) {
  const bars = [
    42, 61, 38, 74, 55, 88, 49, 72, 64, 91, 46, 68, 81, 53, 77, 59, 84, 44, 70, 57, 86, 51,
  ]
  const barsH = Math.round(height * 0.68)
  return (
    <div style={{ height }} className="relative overflow-hidden">
      {[25, 50, 75].map((p) => (
        <div
          key={p}
          className="absolute left-0 right-0 h-px bg-border-subtle/25"
          style={{ top: `${p}%` }}
        />
      ))}
      <div
        className="absolute bottom-8 left-2 right-2 flex items-end gap-[3px]"
        style={{ height: barsH }}
      >
        {bars.map((h, i) => (
          <div
            key={i}
            className="flex-1 min-w-0 rounded-sm bg-white/[0.07] animate-pulse"
            style={{ height: `${h}%`, animationDelay: `${(i * 75) % 700}ms` }}
          />
        ))}
      </div>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-[12px] text-text-tertiary">Loading chart…</span>
      </div>
    </div>
  )
}

/**
 * Rebuild chart data — ONE control, on the price chart's own vertical TOOL STRIP, just above the
 * Chart settings cog.
 *
 * 🔴 It sat in the tab strip until 2026-08-08, on a written-down rule that actions are not view
 * state and so belong beside the tabs. That rule holds for the equity/breakdown `ChartModal`, whose
 * fullscreen is a portal over a page whose chrome is still there — and it is wrong for the PRICE
 * chart, which goes fullscreen by `position: fixed` over the whole app and takes the tab strip off
 * screen with it. Reported in exactly those terms: *"allow me to rebuild chart on full screenview
 * also it only allows me to do on minimized view"*, then placed here on Aaron's call.
 *
 * ⚠ It was MOVED, not copied. A second copy in the tab strip would be two controls firing one
 * action — the argument that already removed the fib tool's own gear from that strip when the
 * ladder moved into Chart settings (`ChartPanel/CLAUDE.md`). The strip is inside the panel, so one
 * button covers both views.
 *
 * ⚠ Icon-only, sized and styled as a strip button: the strip is 40px wide, and a labelled button
 * there would either overflow it or force the strip wider on every chart in the app.
 */
export function RebuildChartButton({
  onClick,
  pending,
}: {
  onClick: () => void
  pending: boolean
}) {
  return (
    <button
      onClick={onClick}
      disabled={pending}
      title="Rebuild chart data — re-fetches the candles and replays the engines. Use it after a fix that changes what a layer draws."
      aria-label="Rebuild chart"
      className="flex items-center justify-center w-8 h-8 rounded-md border border-transparent text-text-tertiary hover:text-text-secondary hover:bg-bg-surface transition-colors disabled:opacity-50"
    >
      <RefreshCw className={`w-4 h-4 ${pending ? 'animate-spin' : ''}`} />
    </button>
  )
}

// The runId-agnostic price-chart body: same klinecharts panel, structure layers, fib/measurement
// tools, and fullscreen chrome, driven by an already-fetched ChartSpec. BacktestDetail feeds it a
// single run's spec; StackDetail feeds it the merged stack spec (trades layered by strategy) — both
// get identical functionality. `requestCandles` wires M1/M5 drill-down; pass undefined to disable.
export function PriceChartView({
  spec,
  isLoading,
  isError,
  requestCandles,
  height = 520,
  isFullscreen = false,
  onFullscreenClose,
  onRebuild,
  rebuilding = false,
}: {
  spec: ChartSpec | undefined
  isLoading: boolean
  isError: boolean
  requestCandles?: (tf: string, fromMs: number, toMs: number) => Promise<ChartPage>
  height?: number
  isFullscreen?: boolean
  onFullscreenClose?: () => void
  /** Optional — a stack has no single run to rebuild, so it passes neither and the button is absent. */
  onRebuild?: () => void
  rebuilding?: boolean
}) {
  const fsBodyRef = useRef<HTMLDivElement>(null)
  const [fsBodyH, setFsBodyH] = useState(0)

  // Measure the fullscreen body height once the overlay is open.
  useEffect(() => {
    if (!isFullscreen) return
    const el = fsBodyRef.current
    if (!el) return
    const update = () => setFsBodyH(el.clientHeight)
    update()
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => ro.disconnect()
  }, [isFullscreen])

  // Escape key to close fullscreen.
  useEffect(() => {
    if (!isFullscreen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onFullscreenClose?.()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [isFullscreen, onFullscreenClose])

  // When fullscreen: body clientHeight minus its padding (pt-2/pb-2 ~16px), the ChartPanel header
  // row (now the single top bar — TF/Layers/Copy + the injected Price title & exit X, ~40px with its
  // border-b), and a small safety buffer. Without subtracting the header the chart overflows and
  // overflow-hidden clips the klinecharts x-axis.
  const effectiveH = isFullscreen
    ? fsBodyH > 0
      ? Math.max(200, fsBodyH - 64)
      : Math.max(200, window.innerHeight - 120)
    : height

  // 🔴 The Rebuild control rides on the CHART PANEL's tool strip, and that panel only mounts once
  // there are candles — so an empty or failed chart hid the one button that could fix it. Reported
  // from the screen 2026-08-25: "there is no way to rebuild chart or anything." **A recovery
  // control that lives inside the thing that failed is not a recovery control**, so both the empty
  // and the error state carry their own copy.
  const box = (msg: string, cls = 'text-text-tertiary') => (
    <div
      style={{ height: effectiveH }}
      className={`flex flex-col items-center justify-center gap-3 text-[12px] ${cls}`}
    >
      <span>{msg}</span>
      {onRebuild ? <RebuildChartButton onClick={onRebuild} pending={rebuilding} /> : null}
    </div>
  )

  // chartBody is always at the same tree position inside the body div so the klinecharts
  // instance (ChartPanel) is never unmounted when toggling between inline and fullscreen.
  const chartBody = isLoading ? (
    <ChartLoadingSkeleton height={effectiveH} />
  ) : isError ? (
    box("Couldn't load chart data for this run.", 'text-neg-text')
  ) : !spec || spec.candles.length === 0 ? (
    box('No price data available for this run.')
  ) : (
    <>
      {spec.baseTimeframe === 'D1' && !isFullscreen && (
        <div className="mb-2 text-[11px] text-warn-text">
          Showing daily candles — intraday history wasn't available from the data agent for this
          run.
        </div>
      )}
      <Suspense fallback={<ChartLoadingSkeleton height={effectiveH} />}>
        {/* Drill-down (1m/5m) only for intraday runs — a D1 (NT8 daily) run has no sub-base bars.
              Fullscreen: fold the "Price" title + exit X onto the panel's own top row (header
              slots), so TF/Layers/Copy and the exit all share one bar instead of stacking two. */}
        <ChartPanel
          spec={spec}
          height={effectiveH}
          onRequestCandles={spec.baseTimeframe !== 'D1' ? requestCandles : undefined}
          // Snapshot button on the expanded chart only — same rule as every other chart here.
          showCopy={isFullscreen}
          // On the tool strip, so it is there in BOTH views — the tab strip that used to carry it
          // is off screen in fullscreen.
          toolActions={
            onRebuild ? <RebuildChartButton onClick={onRebuild} pending={rebuilding} /> : undefined
          }
          headerClassName={isFullscreen ? 'border-b border-border-subtle pb-2' : undefined}
          headerLeading={
            isFullscreen ? (
              <span className="text-[15px] font-bold uppercase tracking-wide text-text-primary ml-1 mr-2">
                {spec.instrument}
              </span>
            ) : undefined
          }
          headerTrailing={
            isFullscreen ? (
              <button
                onClick={onFullscreenClose}
                title="Minimize (Esc)"
                className="text-text-tertiary hover:text-text-primary"
              >
                <Minimize2 size={18} />
              </button>
            ) : undefined
          }
        />
      </Suspense>
    </>
  )

  return (
    <div className={isFullscreen ? 'fixed inset-0 z-[90] bg-bg-base flex flex-col' : ''}>
      {/* Minimal left/right padding in fullscreen to maximise chart space (the price gets its own
          small inset via headerLeading's ml-1; the tool strip sits just inside the edge). */}
      <div
        ref={fsBodyRef}
        className={isFullscreen ? 'flex-1 min-h-0 overflow-hidden pl-2 pr-2 pt-2 pb-2' : ''}
      >
        {chartBody}
      </div>
    </div>
  )
}
