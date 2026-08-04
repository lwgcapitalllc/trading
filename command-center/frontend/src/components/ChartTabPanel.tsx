import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Maximize2, Minimize2, Camera, Check } from 'lucide-react'
import { copyChartAsPng } from '@/lib/chartImage'

// ── Tabbed chart panel + fullscreen modal ────────────────────────────────────
// Shared by BacktestDetail and StressTestDetail: a segmented tab control, optional
// right-side controls, an Expand button, and the active chart rendered at `height`.
// `render(key, h)` draws the chart for a tab key. Keeping these here (not inline in a
// page) lets both detail pages collapse many charts into one tab strip without forking.

// Shared chart panel: a segmented tab control, optional right-side controls, an Expand button,
// and the active chart rendered at `height`. `render(key, h)` draws the chart for a tab key.
export function ChartTabPanel({ tabs, active, onActive, sub, height, onExpand, render, right, aboveChart, keepMounted }: {
  tabs: readonly (readonly [string, string])[]
  active: string
  onActive: (k: string) => void
  sub?: string
  height: number
  onExpand: () => void
  render: (key: string, h: number) => React.ReactNode
  right?: React.ReactNode
  // Optional content rendered between the description and the chart — e.g. the active tab's
  // KPI cards, so each analysis's numbers sit directly above its own chart.
  aboveChart?: React.ReactNode
  /** Tab keys that stay MOUNTED while another tab is showing, so clicking them costs nothing.
   *  Only worth it for a tab whose build is slow and whose data is already loaded — the price
   *  chart, where klinecharts spends ~2s laying 33k candles and their overlays out. An inactive
   *  one is `visibility: hidden` and out of flow: it keeps the panel's real WIDTH (so the canvas
   *  is sized correctly and the reveal needs no resize) while contributing no height, and
   *  `visibility` also takes it out of the tab order and the accessibility tree.
   *  Leave unset and every tab renders only while active, as before. */
  keepMounted?: readonly string[]
}) {
  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg px-4 pt-3 pb-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="inline-flex gap-0.5 p-0.5 rounded-lg bg-bg-sunken border border-border-subtle">
          {tabs.map(([key, label]) => (
            <button
              key={key}
              onClick={() => onActive(key)}
              className={`px-3 py-1.5 rounded-md text-[12px] font-semibold transition-colors ${
                active === key ? 'bg-accent/10 text-accent ring-1 ring-inset ring-accent/30' : 'text-text-tertiary hover:text-text-secondary'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          {right}
          <button
            onClick={onExpand}
            title="Expand to full screen"
            className="flex items-center justify-center w-7 h-7 rounded text-text-tertiary hover:text-text-secondary hover:bg-bg-hover transition-colors"
          >
            <Maximize2 size={14} />
          </button>
        </div>
      </div>
      {sub && <div className="text-[10px] text-text-tertiary mt-4 mb-4 px-0.5">{sub}</div>}
      {aboveChart}
      <div className="relative">
        {keepMounted?.map(key => (
          <div
            key={key}
            className={active === key ? undefined : 'invisible absolute inset-x-0 top-0'}
            aria-hidden={active !== key || undefined}
          >
            {render(key, height)}
          </div>
        ))}
        {!keepMounted?.includes(active) && render(active, height)}
      </div>
    </div>
  )
}

// Full-screen overlay (portalled) that renders a chart at the measured body height. Esc / backdrop /
// the minimize button close it. Every fullscreen chart carries a camera (copy-as-image) button —
// that's the point of expanding one: read it, then send it. Inline charts deliberately don't:
// a copy of the small version isn't worth the header clutter.
export function ChartModal({ title, onClose, render, controls }: {
  title: string
  onClose: () => void
  render: (h: number) => React.ReactNode
  /** The same per-chart controls the inline panel shows (series toggles, axis switch…). Fullscreen
   *  is where a chart is actually READ, so anything you can change inline must be changeable here. */
  controls?: React.ReactNode
}) {
  const bodyRef = useRef<HTMLDivElement>(null)
  const [h, setH] = useState(0)
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    if (await copyChartAsPng(bodyRef.current)) {
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    }
  }
  useEffect(() => {
    const el = bodyRef.current
    if (!el) return
    const update = () => setH(el.clientHeight)
    update()
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  // Solid background (not backdrop-blur): blurring the whole viewport is recomputed every frame of
  // the equity draw animation, which makes the line render choppy fullscreen.
  return createPortal(
    <div className="fixed inset-0 z-[90] bg-bg-base flex flex-col" onClick={onClose}>
      <div className="flex items-center justify-between px-5 py-3 border-b border-border-subtle flex-shrink-0" onClick={e => e.stopPropagation()}>
        <span className="text-[12px] font-semibold uppercase tracking-[0.7px] text-text-secondary">{title}</span>
        <div className="flex items-center gap-3">
          {controls}
          <button onClick={copy} title={copied ? 'Copied' : 'Copy chart image to clipboard'}
            className="text-text-tertiary hover:text-text-primary transition-colors">
            {copied ? <Check size={18} className="text-accent" /> : <Camera size={18} />}
          </button>
          <button onClick={onClose} title="Minimize (Esc)" className="text-text-tertiary hover:text-text-primary transition-colors">
            <Minimize2 size={18} />
          </button>
        </div>
      </div>
      <div ref={bodyRef} className="flex-1 min-h-0 overflow-hidden px-5 py-4" onClick={e => e.stopPropagation()}>
        {h > 0 && render(Math.max(200, h - 40))}
      </div>
    </div>,
    document.body,
  )
}
