import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, Cell } from 'recharts'
import { C } from '@/themes/chart'

interface Props {
  distribution: { counts: number[]; edges: number[] }
  maxLoss?: number | null
  height?: number
}

export default function DrawdownDistribution({ distribution, maxLoss, height = 252 }: Props) {
  if (!distribution?.counts) return null

  const data = distribution.counts.map((count, i) => ({
    dd: Math.round((distribution.edges[i] + distribution.edges[i + 1]) / 2),
    count,
    overLimit: maxLoss != null && distribution.edges[i] > maxLoss,
  }))

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 16, bottom: 22, left: 12 }}>
        <XAxis
          dataKey="dd"
          tickFormatter={v => `$${(v / 1000).toFixed(1)}k`}
          tick={{ fill: C.axisTick, fontSize: 10 }}
          tickLine={false}
          label={{ value: 'Max drawdown reached', position: 'insideBottom', offset: -12, fill: C.axisTick, fontSize: 10 }}
        />
        <YAxis
          tick={{ fill: C.axisTick, fontSize: 10 }}
          tickLine={false}
          axisLine={false}
          label={{ value: '# simulations', angle: -90, position: 'insideLeft', fill: C.axisTick, fontSize: 10, style: { textAnchor: 'middle' } }}
        />
        <Tooltip
          contentStyle={{ background: C.tooltipBg, border: `1px solid ${C.tooltipBorder}`, borderRadius: 8, fontSize: 13, padding: '8px 12px' }}
          labelStyle={{ color: C.axisTick }}
          itemStyle={{ color: '#e5e7eb' }}
          cursor={false}
          formatter={(v: number) => [`${v} sims`, 'Count']}
          labelFormatter={(v: number) => `Max DD: $${v.toLocaleString('en-US', { maximumFractionDigits: 0 })}`}
        />
        {maxLoss != null && (
          <ReferenceLine x={maxLoss} stroke={C.neg} strokeDasharray="4 2" label={{ value: 'Limit', fill: C.neg, fontSize: 10 }} />
        )}
        <Bar dataKey="count" radius={[2, 2, 0, 0]} activeBar={{ fillOpacity: 1 }}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.overLimit ? C.neg : C.accent} fillOpacity={d.overLimit ? 0.75 : 0.55} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
