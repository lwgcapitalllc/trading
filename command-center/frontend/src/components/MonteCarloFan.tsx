import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import { C } from '@/themes/chart'

interface Props {
  paths: number[][]
  ruleset?: { max_loss_eod?: number; profit_target?: number } | null
  tradeCount: number
}

export default function MonteCarloFan({ paths, ruleset, tradeCount }: Props) {
  if (!paths || paths.length === 0) return null

  // Downsample paths to every Nth trade for readability
  const step = Math.max(1, Math.floor(tradeCount / 100))
  const indices = Array.from({ length: Math.ceil(tradeCount / step) }, (_, i) => i * step)

  // Build chartData: [{index, p10, p25, p50, p75, p90}]
  const transposed = indices.map(idx => {
    const vals = paths.map(p => p[Math.min(idx, p.length - 1)] ?? 0).sort((a, b) => a - b)
    const len = vals.length
    return {
      index: idx + 1,
      p10: vals[Math.floor(len * 0.10)] ?? 0,
      p25: vals[Math.floor(len * 0.25)] ?? 0,
      p50: vals[Math.floor(len * 0.50)] ?? 0,
      p75: vals[Math.floor(len * 0.75)] ?? 0,
      p90: vals[Math.floor(len * 0.90)] ?? 0,
    }
  })

  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={transposed} margin={{ top: 8, right: 16, bottom: 8, left: 16 }}>
        <XAxis dataKey="index" tick={{ fill: C.axisTick, fontSize: 11 }} tickLine={false} />
        <YAxis tickFormatter={v => `$${(v / 1000).toFixed(0)}k`} tick={{ fill: C.axisTick, fontSize: 11 }} tickLine={false} axisLine={false} />
        <Tooltip
          contentStyle={{ background: C.tooltipBg, border: `1px solid ${C.tooltipBorder}`, borderRadius: 6 }}
          itemStyle={{ color: C.tooltipBorder }}
          formatter={(v: number) => [`$${v.toFixed(0)}`, '']}
        />
        {ruleset?.max_loss_eod && (
          <ReferenceLine y={-ruleset.max_loss_eod} stroke={C.neg} strokeDasharray="4 2" label={{ value: 'Limit', fill: C.neg, fontSize: 10 }} />
        )}
        {ruleset?.profit_target != null && ruleset.profit_target > 0 && (
          <ReferenceLine y={ruleset.profit_target} stroke={C.pos} strokeDasharray="4 2" label={{ value: 'Target', fill: C.pos, fontSize: 10 }} />
        )}
        <Line dataKey="p90" stroke={C.pos} strokeWidth={1} dot={false} opacity={0.5} name="90th %ile" />
        <Line dataKey="p75" stroke={C.pos} strokeWidth={1.5} dot={false} opacity={0.7} name="75th %ile" />
        <Line dataKey="p50" stroke={C.accent} strokeWidth={2} dot={false} name="Median" />
        <Line dataKey="p25" stroke={C.neg} strokeWidth={1.5} dot={false} opacity={0.7} name="25th %ile" />
        <Line dataKey="p10" stroke={C.neg} strokeWidth={1} dot={false} opacity={0.5} name="10th %ile" />
      </LineChart>
    </ResponsiveContainer>
  )
}
