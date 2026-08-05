import { useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, Cell } from 'recharts'
import { C } from '@/themes/chart'
import type { StressTest } from '@/types'

interface Props { sensitivity: StressTest['sensitivity_summary']; height?: number }

/** How many bars to draw before the chart stops being readable. A strategy here has ~35 tunable
 *  numerics × 4 shifts = ~140 rows; at 440px that is three pixels a bar in dictionary order, which
 *  answers nothing. The worst movers are what the panel is for, and the rest are one click away. */
const TOP_N = 24

export default function SensitivityRadar({ sensitivity, height = 252 }: Props) {
  const [showAll, setShowAll] = useState(false)
  if (!sensitivity || Object.keys(sensitivity).length === 0) return null

  // Both current paths carry `degradation` (a profit-factor change MAGNITUDE) and, since
  // 2026-08-05, `pf_delta_pct` — the same measurement with its SIGN kept. Records written before
  // 2026-07-30 instead carry a signed `pnl_delta_pct`, so the metric is detected per record and the
  // tooltip names whichever one this record actually holds — an old test must not be relabelled as
  // something it never measured.
  const isPf = Object.values(sensitivity).some(shifts =>
    Object.values(shifts).some(s => s.pnl_delta_pct == null && s.degradation != null))
  const metricLabel = isPf ? 'Profit-factor change' : 'PnL impact (legacy)'

  // 🔴 The direction is READ, never invented. This used to draw `-degradation * 100`, so a shift
  // that IMPROVED profit factor rendered as a long red bar; and a shift whose child backtest failed
  // (`degradation: null`) fell through to `: 0` and drew a flat bar at zero, which reads as "tested,
  // no effect" — the most reassuring answer available, for a measurement that never happened.
  type Row = { label: string; pct: number | null; magnitude: number }
  const all: Row[] = []
  for (const [param, shifts] of Object.entries(sensitivity)) {
    for (const [shift, info] of Object.entries(shifts)) {
      const signed = info.pf_delta_pct ?? info.pnl_delta_pct ?? null
      const magnitude = info.degradation != null ? info.degradation * 100
        : signed != null ? Math.abs(signed) : null
      // No measurement at all → the row is DROPPED, not drawn at zero. The KPI cards above report
      // how many shifts failed, so nothing disappears silently.
      if (magnitude == null) continue
      all.push({ label: `${param} ${shift}`, pct: signed, magnitude })
    }
  }
  if (all.length === 0) return null

  // Biggest mover first — the panel's whole question is "what moves this the most".
  const sorted = [...all].sort((a, b) => b.magnitude - a.magnitude)
  const data = showAll ? sorted : sorted.slice(0, TOP_N)
  const hidden = sorted.length - data.length

  // Scale the x-axis to the actual data range (with 10% padding) and always include 0, so the
  // worst-case bar can't render off-screen — Recharts' default domain clipped large values.
  // A row with no sign is plotted at its magnitude with a NEUTRAL colour rather than being forced
  // to one side of zero.
  const vals = data.map(d => d.pct ?? d.magnitude)
  const lo = Math.min(0, ...vals)
  const hi = Math.max(0, ...vals)
  const pad = ((hi - lo) || 1) * 0.1
  const rows = data.map(d => ({ ...d, plotted: d.pct ?? d.magnitude }))

  return (
    <div>
      <ResponsiveContainer width="100%" height={height - 22}>
        <BarChart data={rows} margin={{ top: 8, right: 16, bottom: 26, left: 16 }} layout="vertical">
          <XAxis
            type="number"
            domain={[lo - pad, hi + pad]}
            tickFormatter={v => `${v.toFixed(0)}%`}
            tick={{ fill: C.axisTick, fontSize: 10 }}
            tickLine={false}
            label={{ value: 'Change vs baseline (%) — left/red = worse, right/green = better', position: 'insideBottom', offset: -14, fill: C.axisTick, fontSize: 10 }}
          />
          <YAxis type="category" dataKey="label" tick={{ fill: C.axisTick, fontSize: 10 }} tickLine={false} axisLine={false} width={150} />
          <Tooltip
            contentStyle={{ background: C.tooltipBg, border: `1px solid ${C.tooltipBorder}`, borderRadius: 8, fontSize: 13, padding: '8px 12px' }}
            labelStyle={{ color: C.axisTick }}
            itemStyle={{ color: '#e5e7eb' }}
            cursor={false}
            formatter={(_v: number, _n: string, entry) => {
              const row = entry?.payload as (typeof rows)[number] | undefined
              if (!row) return ['—', metricLabel]
              return [
                row.pct == null
                  ? `${row.magnitude.toFixed(1)}% (direction not recorded)`
                  : `${row.pct > 0 ? '+' : ''}${row.pct.toFixed(1)}%`,
                metricLabel,
              ]
            }}
          />
          <ReferenceLine x={0} stroke={C.refLine} />
          <Bar dataKey="plotted" radius={[0, 2, 2, 0]} activeBar={{ fillOpacity: 1 }}>
            {rows.map((d, i) => (
              <Cell key={i}
                fill={d.pct == null ? C.axisTick : d.pct >= 0 ? C.pos : C.neg}
                fillOpacity={d.pct == null ? 0.35 : 0.6} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div className="text-center mt-[2px] h-[18px]">
        {hidden > 0 ? (
          <button onClick={() => setShowAll(true)} className="text-[10px] text-accent hover:underline">
            Showing the {TOP_N} biggest movers — show all {sorted.length}
          </button>
        ) : sorted.length > TOP_N ? (
          <button onClick={() => setShowAll(false)} className="text-[10px] text-accent hover:underline">
            Show only the {TOP_N} biggest movers
          </button>
        ) : null}
      </div>
    </div>
  )
}
