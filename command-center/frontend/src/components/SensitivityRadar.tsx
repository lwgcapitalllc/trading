import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, Cell } from 'recharts'
import { C } from '@/themes/chart'
import type { StressTest } from '@/types'

interface Props { sensitivity: StressTest['sensitivity_summary'] }

export default function SensitivityRadar({ sensitivity }: Props) {
  if (!sensitivity || Object.keys(sensitivity).length === 0) return null

  const data: { label: string; pnl_delta_pct: number }[] = []
  for (const [param, shifts] of Object.entries(sensitivity)) {
    for (const [shift, info] of Object.entries(shifts)) {
      data.push({
        label: `${param} ${shift}`,
        pnl_delta_pct: info.pnl_delta_pct ?? 0,
      })
    }
  }

  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ top: 8, right: 16, bottom: 24, left: 16 }} layout="vertical">
        <XAxis type="number" tickFormatter={v => `${v.toFixed(0)}%`} tick={{ fill: C.axisTick, fontSize: 10 }} tickLine={false} />
        <YAxis type="category" dataKey="label" tick={{ fill: C.axisTick, fontSize: 10 }} tickLine={false} axisLine={false} width={120} />
        <Tooltip
          contentStyle={{ background: C.tooltipBg, border: `1px solid ${C.tooltipBorder}`, borderRadius: 8, fontSize: 13, padding: '8px 12px' }}
          labelStyle={{ color: C.axisTick }}
          itemStyle={{ color: '#e5e7eb' }}
          cursor={false}
          formatter={(v: number) => [`${v.toFixed(1)}%`, 'PnL Delta']}
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
