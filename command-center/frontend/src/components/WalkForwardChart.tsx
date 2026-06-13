import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, ReferenceLine } from 'recharts'
import { C } from '@/themes/chart'
import type { WalkForwardWindow } from '@/types'

interface Props { windows: WalkForwardWindow[] }

export default function WalkForwardChart({ windows }: Props) {
  if (!windows || windows.length === 0) return null

  const data = windows.map(w => ({
    window: `W${w.window}`,
    is_sharpe: w.is_sharpe ?? 0,
    oos_sharpe: w.oos_sharpe ?? 0,
  }))

  return (
    <ResponsiveContainer width="100%" height={248}>
      <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 12 }}>
        <XAxis dataKey="window" tick={{ fill: C.axisTick, fontSize: 12 }} tickLine={false} />
        <YAxis
          tick={{ fill: C.axisTick, fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          label={{ value: 'Sharpe (higher = better, < 0 = losing)', angle: -90, position: 'insideLeft', fill: C.axisTick, fontSize: 10, style: { textAnchor: 'middle' } }}
        />
        <Tooltip
          contentStyle={{ background: C.tooltipBg, border: `1px solid ${C.tooltipBorder}`, borderRadius: 8, fontSize: 13, padding: '8px 12px' }}
          labelStyle={{ color: C.axisTick }}
          itemStyle={{ color: '#e5e7eb' }}
          cursor={false}
          formatter={(v: number, name: string) => [v.toFixed(2), name]}
        />
        <Legend wrapperStyle={{ fontSize: 12, color: C.axisTick }} />
        <ReferenceLine y={0} stroke={C.refLine} />
        <Bar dataKey="is_sharpe"  name="In-Sample (tuned on)"   fill={C.accent} fillOpacity={0.6} radius={[2, 2, 0, 0]} activeBar={{ fillOpacity: 1 }} />
        <Bar dataKey="oos_sharpe" name="Out-of-Sample (unseen)" fill={C.pos}    fillOpacity={0.6} radius={[2, 2, 0, 0]} activeBar={{ fillOpacity: 1 }} />
      </BarChart>
    </ResponsiveContainer>
  )
}
