import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, Cell } from 'recharts'
import { C } from '@/themes/chart'
import type { StressTest } from '@/types'

interface Props { sensitivity: StressTest['sensitivity_summary']; height?: number }

export default function SensitivityRadar({ sensitivity, height = 252 }: Props) {
  if (!sensitivity || Object.keys(sensitivity).length === 0) return null

  // Grid sensitivity (auto-injected from an optimization) carries `degradation` (a PF drop)
  // instead of the perturbation path's signed `pnl_delta_pct` — detect once so the tooltip names
  // the metric correctly rather than always saying "PnL Delta".
  const isGrid = Object.values(sensitivity).some(shifts =>
    Object.values(shifts).some(s => s.pnl_delta_pct == null && s.degradation != null))
  const metricLabel = isGrid ? 'PF degradation' : 'PnL impact'

  const data: { label: string; pnl_delta_pct: number }[] = []
  for (const [param, shifts] of Object.entries(sensitivity)) {
    for (const [shift, info] of Object.entries(shifts)) {
      // Perturbation sensitivity carries a signed pnl_delta_pct. Grid sensitivity (auto-injected
      // from an optimization) instead carries `degradation` (a 0..1 PF drop, always ≥ 0) — render
      // it as a negative magnitude so a bigger drop = a longer red bar, matching the diverging axis.
      const pct = info.pnl_delta_pct != null
        ? info.pnl_delta_pct
        : info.degradation != null ? -info.degradation * 100 : 0
      data.push({ label: `${param} ${shift}`, pnl_delta_pct: pct })
    }
  }

  // Scale the x-axis to the actual data range (with 10% padding) and always include 0, so the
  // worst-case bar can't render off-screen — Recharts' default domain clipped large values.
  const vals = data.map(d => d.pnl_delta_pct)
  const lo = Math.min(0, ...vals)
  const hi = Math.max(0, ...vals)
  const pad = ((hi - lo) || 1) * 0.1

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 16, bottom: 26, left: 16 }} layout="vertical">
        <XAxis
          type="number"
          domain={[lo - pad, hi + pad]}
          tickFormatter={v => `${v.toFixed(0)}%`}
          tick={{ fill: C.axisTick, fontSize: 10 }}
          tickLine={false}
          label={{ value: 'Change vs baseline (%) — left/red = worse', position: 'insideBottom', offset: -14, fill: C.axisTick, fontSize: 10 }}
        />
        <YAxis type="category" dataKey="label" tick={{ fill: C.axisTick, fontSize: 10 }} tickLine={false} axisLine={false} width={120} />
        <Tooltip
          contentStyle={{ background: C.tooltipBg, border: `1px solid ${C.tooltipBorder}`, borderRadius: 8, fontSize: 13, padding: '8px 12px' }}
          labelStyle={{ color: C.axisTick }}
          itemStyle={{ color: '#e5e7eb' }}
          cursor={false}
          formatter={(v: number) => [`${v.toFixed(1)}%`, metricLabel]}
        />
        <ReferenceLine x={0} stroke={C.refLine} />
        <Bar dataKey="pnl_delta_pct" radius={[0, 2, 2, 0]} activeBar={{ fillOpacity: 1 }}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.pnl_delta_pct >= 0 ? C.pos : C.neg} fillOpacity={0.6} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
