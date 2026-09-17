/**
 * How the trades landed in R — one bar per half-R bucket.
 *
 * ⚠ A trade with no recorded risk has no R and is COUNTED beside the chart, never binned at 0: a
 * manual trade placed without a stop did not break even.
 */
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { EquityPoint } from '@/types'
import { C } from '@/themes/chart'

const STEP = 0.5

export function rBuckets(points: EquityPoint[]): { r: number; count: number }[] {
  const rs = points.map((p) => p.r).filter((r): r is number => typeof r === 'number' && isFinite(r))
  if (!rs.length) return []
  const lo = Math.floor(Math.min(...rs) / STEP)
  const hi = Math.floor(Math.max(...rs) / STEP)
  const out: { r: number; count: number }[] = []
  for (let b = lo; b <= hi; b++) out.push({ r: b * STEP, count: 0 })
  for (const r of rs) out[Math.floor(r / STEP) - lo].count += 1
  return out
}

export function RDistribution({
  points,
  height = 200,
}: {
  points: EquityPoint[]
  height?: number
}) {
  const data = rBuckets(points)
  const missing = points.filter((p) => p.r == null).length
  const note =
    missing > 0 ? `${missing} of ${points.length} trades carry no recorded stop, so no R.` : null
  if (!data.length)
    return (
      <div className="h-[120px] flex items-center justify-center text-[12px] text-text-tertiary">
        No trade here has a recorded stop to measure R against.
      </div>
    )
  return (
    <div>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
          <XAxis
            dataKey="r"
            tick={{ fill: C.axisTick, fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v: number) => `${v >= 0 ? '+' : ''}${v}R`}
          />
          <YAxis
            allowDecimals={false}
            tick={{ fill: C.axisTick, fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            width={28}
          />
          <Tooltip
            contentStyle={{
              background: C.tooltipBg,
              border: `1px solid ${C.tooltipBorder}`,
              borderRadius: 8,
              fontSize: 12,
            }}
            labelStyle={{ color: C.axisTick }}
            labelFormatter={(v: number) =>
              `${v >= 0 ? '+' : ''}${v}R to ${v + STEP >= 0 ? '+' : ''}${v + STEP}R`
            }
            formatter={(v: number) => [v, 'Trades']}
          />
          <Bar dataKey="count" radius={[2, 2, 0, 0]} isAnimationActive={false}>
            {data.map((d, i) => (
              <Cell key={i} fill={d.r >= 0 ? C.pos : C.neg} fillOpacity={0.8} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      {note && <p className="mt-1 text-[11px] text-text-tertiary">{note}</p>}
    </div>
  )
}
