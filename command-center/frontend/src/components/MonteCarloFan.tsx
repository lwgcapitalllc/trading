import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import { C } from '@/themes/chart'

interface Props {
  paths: number[][]
  /** Only `profit_target` is drawable here — see the note on the removed drawdown line below. */
  ruleset?: { profit_target?: number } | null
  tradeCount: number
  height?: number
}

export default function MonteCarloFan({ paths, ruleset, tradeCount, height = 276 }: Props) {
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

  // One source of truth for each band's colour/opacity — shared by the lines, the tooltip,
  // and the legend below so the key always matches what's drawn. Ordered luckier → unluckier.
  const BANDS = [
    { key: 'p90', label: '90th pct', stroke: C.pos,    width: 1,   opacity: 0.5 },
    { key: 'p75', label: '75th pct', stroke: C.pos,    width: 1.5, opacity: 0.7 },
    { key: 'p50', label: 'Median',   stroke: C.accent, width: 2,   opacity: 1   },
    { key: 'p25', label: '25th pct', stroke: C.neg,    width: 1.5, opacity: 0.7 },
    { key: 'p10', label: '10th pct', stroke: C.neg,    width: 1,   opacity: 0.5 },
  ]
  const labelByKey: Record<string, string> = Object.fromEntries(BANDS.map(b => [b.key, b.label]))

  return (
    <div>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={transposed} margin={{ top: 8, right: 16, bottom: 20, left: 16 }}>
          <XAxis
            dataKey="index"
            tick={{ fill: C.axisTick, fontSize: 11 }}
            tickLine={false}
            label={{ value: 'Trade #', position: 'insideBottom', offset: -10, fill: C.axisTick, fontSize: 10 }}
          />
          <YAxis
            tickFormatter={v => `$${(v / 1000).toFixed(0)}k`}
            tick={{ fill: C.axisTick, fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            label={{ value: 'Cumulative P&L (from $0)', angle: -90, position: 'insideLeft', fill: C.axisTick, fontSize: 10, style: { textAnchor: 'middle' } }}
          />
          <Tooltip
            contentStyle={{ background: C.tooltipBg, border: `1px solid ${C.tooltipBorder}`, borderRadius: 8, fontSize: 13, padding: '8px 12px' }}
            labelStyle={{ color: C.axisTick }}
            itemStyle={{ color: '#e5e7eb' }}
            formatter={(v: number, name: string) => [`$${v.toLocaleString('en-US', { maximumFractionDigits: 0 })}`, labelByKey[name] ?? name]}
          />
          {/* 🔴 There is NO drawdown-limit line here, deliberately. One used to be drawn at
              `y = -max_loss_eod` — a horizontal level on a CUMULATIVE-P&L axis — and a drawdown
              limit is not that quantity. A drawdown is peak-to-trough, so a path can breach the
              limit many times over without ever crossing a line below zero: a fan sitting entirely
              above it reads "no simulation breaches" while `prob_breach` beside it says otherwise.
              The breach question is answered honestly by the Prob. Breach card and by the drawdown
              histogram, which measures the right thing. A profit TARGET is a genuine level of
              cumulative P&L, so that line stays. */}
          {ruleset?.profit_target != null && ruleset.profit_target > 0 && (
            <ReferenceLine y={ruleset.profit_target} stroke={C.pos} strokeDasharray="4 2" label={{ value: 'Target', fill: C.pos, fontSize: 10 }} />
          )}
          {BANDS.map(b => (
            <Line key={b.key} dataKey={b.key} stroke={b.stroke} strokeWidth={b.width} dot={false} opacity={b.opacity} name={b.key} />
          ))}
        </LineChart>
      </ResponsiveContainer>

      {/* Key — maps each colour to its percentile, ordered best-case to worst-case */}
      <div className="flex items-center justify-center gap-x-[14px] gap-y-[6px] flex-wrap mt-[6px] px-2">
        <span className="text-[10px] uppercase tracking-[0.6px] text-text-tertiary">Luckier</span>
        {BANDS.map(b => (
          <span key={b.key} className="flex items-center gap-[6px]">
            <span className="inline-block w-[16px] rounded-full" style={{ height: Math.max(2, b.width), backgroundColor: b.stroke, opacity: b.opacity }} />
            <span className="text-[11px] text-text-secondary">{b.label}</span>
          </span>
        ))}
        <span className="text-[10px] uppercase tracking-[0.6px] text-text-tertiary">Unluckier</span>
      </div>
    </div>
  )
}
