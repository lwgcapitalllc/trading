import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts'
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
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
        <XAxis dataKey="window" tick={{ fill: C.axisTick, fontSize: 12 }} tickLine={false} />
        <YAxis tick={{ fill: C.axisTick, fontSize: 11 }} tickLine={false} axisLine={false} />
        <Tooltip
          contentStyle={{ background: C.tooltipBg, border: `1px solid ${C.tooltipBorder}`, borderRadius: 8, fontSize: 13, padding: '8px 12px' }}
          labelStyle={{ color: C.axisTick }}
          itemStyle={{ color: '#e5e7eb' }}
          cursor={false}
          formatter={(v: number) => [v.toFixed(2), '']}
        />
        <Legend wrapperStyle={{ fontSize: 12, color: C.axisTick }} />
        <Bar dataKey="is_sharpe"  name="In-Sample Sharpe"      fill={C.accent} fillOpacity={0.6} radius={[2, 2, 0, 0]} activeBar={{ fillOpacity: 1 }} />
        <Bar dataKey="oos_sharpe" name="Out-of-Sample Sharpe"  fill={C.pos}    fillOpacity={0.6} radius={[2, 2, 0, 0]} activeBar={{ fillOpacity: 1 }} />
      </BarChart>
    </ResponsiveContainer>
  )
}
