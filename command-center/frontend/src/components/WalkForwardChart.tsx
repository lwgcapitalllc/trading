import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
  ReferenceLine,
  Cell,
} from 'recharts'
import { C } from '@/themes/chart'
import type { WalkForwardWindow } from '@/types'

interface Props {
  windows: WalkForwardWindow[]
  height?: number
}

/** Mirrors stress_tester._WF_MIN_TRADES_PER_WINDOW. Below this on EITHER side the window is
 *  excluded from the degradation average, so the chart has to say which bars are which. */
const MIN_TRADES = 20

export default function WalkForwardChart({ windows, height = 248 }: Props) {
  if (!windows || windows.length === 0) return null

  // 🔴 Which metric this walk-forward actually measured. The NATIVE (optimizer-derived) path has no
  // trade-level data at all: it degrades on PROFIT FACTOR and writes `is_sharpe: null` deliberately.
  // This chart read `is_sharpe ?? 0` regardless, so that whole path drew a row of ZERO bars — a
  // chart asserting "Sharpe 0.00 in and out" for five windows nothing had measured a Sharpe on,
  // while the KPI cards beside it correctly printed "—". Never render a null as a value.
  const isPf = windows.every((w) => w.is_sharpe == null) && windows.some((w) => w.is_pf != null)
  const pick = (w: WalkForwardWindow, side: 'is' | 'oos') =>
    isPf ? (side === 'is' ? w.is_pf : w.oos_pf) : side === 'is' ? w.is_sharpe : w.oos_sharpe

  const data = windows.map((w) => {
    // A window excluded for thin evidence is drawn faded, so a tall bar that contributed NOTHING
    // to the verdict cannot be read as the thing that decided it.
    const thin =
      (w.is_trades != null && w.is_trades < MIN_TRADES) ||
      (w.oos_trades != null && w.oos_trades < MIN_TRADES)
    return {
      window: `W${w.window}`,
      is: pick(w, 'is'),
      oos: pick(w, 'oos'),
      is_trades: w.is_trades,
      oos_trades: w.oos_trades,
      thin,
    }
  })
  const anyThin = data.some((d) => d.thin)
  const metric = isPf ? 'Profit factor' : 'Sharpe'

  return (
    <div>
      <ResponsiveContainer width="100%" height={height - (anyThin ? 22 : 0)}>
        <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 12 }}>
          <XAxis dataKey="window" tick={{ fill: C.axisTick, fontSize: 12 }} tickLine={false} />
          <YAxis
            tick={{ fill: C.axisTick, fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            label={{
              value: isPf
                ? 'Profit factor (1.0 = break-even)'
                : 'Sharpe (higher = better, < 0 = losing)',
              angle: -90,
              position: 'insideLeft',
              fill: C.axisTick,
              fontSize: 10,
              style: { textAnchor: 'middle' },
            }}
          />
          <Tooltip
            contentStyle={{
              background: C.tooltipBg,
              border: `1px solid ${C.tooltipBorder}`,
              borderRadius: 8,
              fontSize: 13,
              padding: '8px 12px',
            }}
            labelStyle={{ color: C.axisTick }}
            itemStyle={{ color: '#e5e7eb' }}
            cursor={false}
            // A window whose value could not be computed shows so in words. `v.toFixed(2)` on a
            // null renders "0.00", which is the same lie the bar used to tell.
            formatter={(v, name, entry) => {
              const row = entry?.payload as (typeof data)[number] | undefined
              const label = String(name)
              const trades = label.startsWith('In') ? row?.is_trades : row?.oos_trades
              const suffix =
                trades != null
                  ? ` · ${trades} trade${trades === 1 ? '' : 's'}${trades < MIN_TRADES ? ' (too thin to count)' : ''}`
                  : ''
              return [v == null ? 'not measured' : `${Number(v).toFixed(2)}${suffix}`, label]
            }}
          />
          <Legend wrapperStyle={{ fontSize: 12, color: C.axisTick }} />
          <ReferenceLine y={isPf ? 1 : 0} stroke={C.refLine} />
          <Bar
            dataKey="is"
            name={`In-Sample ${metric} (first 70%)`}
            fill={C.accent}
            radius={[2, 2, 0, 0]}
            activeBar={{ fillOpacity: 1 }}
          >
            {data.map((d, i) => (
              <Cell key={i} fillOpacity={d.thin ? 0.22 : 0.6} />
            ))}
          </Bar>
          <Bar
            dataKey="oos"
            name={`Out-of-Sample ${metric} (unseen last 30%)`}
            fill={C.pos}
            radius={[2, 2, 0, 0]}
            activeBar={{ fillOpacity: 1 }}
          >
            {data.map((d, i) => (
              <Cell key={i} fillOpacity={d.thin ? 0.22 : 0.6} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      {anyThin && (
        <p className="text-[10px] text-warn-text text-center mt-[2px]">
          Faded bars closed under {MIN_TRADES} trades on one side — excluded from the degradation,
          because one trade's luck would move that Sharpe more than the strategy does.
        </p>
      )}
    </div>
  )
}
