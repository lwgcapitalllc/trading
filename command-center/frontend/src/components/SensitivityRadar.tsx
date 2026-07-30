import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, Cell } from 'recharts'
import { C } from '@/themes/chart'
import type { StressTest } from '@/types'

interface Props { sensitivity: StressTest['sensitivity_summary']; height?: number }

export default function SensitivityRadar({ sensitivity, height = 252 }: Props) {
  if (!sensitivity || Object.keys(sensitivity).length === 0) return null

  // Both sensitivity paths now carry `degradation` (a profit-factor change fraction). Records
  // written before 2026-07-30 by the perturbation path instead carry a signed `pnl_delta_pct`, so
  // the metric is detected per-record and the tooltip names whichever one this record actually
  // holds — an old test must not be relabelled as something it never measured.
  const isPf = Object.values(sensitivity).some(shifts =>
    Object.values(shifts).some(s => s.pnl_delta_pct == null && s.degradation != null))
  const metricLabel = isPf ? 'PF degradation' : 'PnL impact (legacy)'

  const data: { label: string; pnl_delta_pct: number }[] = []
  for (const [param, shifts] of Object.entries(sensitivity)) {
    for (const [shift, info] of Object.entries(shifts)) {
      // `degradation` is a 0..1 profit-factor change, always ≥ 0 — render it as a negative
      // magnitude so a bigger change = a longer red bar, matching the diverging axis. A pre-
      // 2026-07-30 record instead carries a signed pnl_delta_pct and is drawn as-is.
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
