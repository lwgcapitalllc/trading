import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, Cell } from 'recharts'
import { C } from '@/themes/chart'

interface Props {
  distribution: { counts: number[]; edges: number[] }
  maxLoss?: number | null
}

export default function DrawdownDistribution({ distribution, maxLoss }: Props) {
  if (!distribution?.counts) return null

  const data = distribution.counts.map((count, i) => ({
    dd: Math.round((distribution.edges[i] + distribution.edges[i + 1]) / 2),
    count,
    overLimit: maxLoss != null && distribution.edges[i] > maxLoss,
  }))

  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
        <XAxis dataKey="dd" tickFormatter={v => `$${v}`} tick={{ fill: C.axisTick, fontSize: 10 }} tickLine={false} />
        <YAxis tick={{ fill: C.axisTick, fontSize: 10 }} tickLine={false} axisLine={false} />
        <Tooltip
          contentStyle={{ background: C.tooltipBg, border: `1px solid ${C.tooltipBorder}`, borderRadius: 6 }}
          itemStyle={{ color: C.tooltipBorder }}
          formatter={(v: number) => [`${v} sims`, 'Count']}
          labelFormatter={v => `Max DD: $${v}`}
        />
        {maxLoss != null && (
          <ReferenceLine x={maxLoss} stroke={C.neg} strokeDasharray="4 2" label={{ value: 'Limit', fill: C.neg, fontSize: 10 }} />
        )}
        <Bar dataKey="count" radius={[2, 2, 0, 0]}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.overLimit ? C.neg : C.accent} fillOpacity={d.overLimit ? 0.8 : 0.6} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
