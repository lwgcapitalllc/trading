import { useNavigate } from 'react-router-dom'
import type { BacktestSummary } from '@/types'

interface Props {
  runs: BacktestSummary[]
  paramX: string
  paramY: string
}

function lerp(t: number, lo: number, hi: number) {
  return lo + t * (hi - lo)
}

function scoreColor(score: number, min: number, max: number): string {
  if (max === min) return '#3b82f6'
  const t = Math.max(0, Math.min(1, (score - min) / (max - min)))
  const r = Math.round(lerp(t, 255, 0))
  const g = Math.round(lerp(t, 59, 229))
  const b = Math.round(lerp(t, 92, 255))
  return `rgb(${r},${g},${b})`
}

export function OptimizationHeatmap({ runs, paramX, paramY }: Props) {
  const navigate = useNavigate()

  const complete = runs.filter(r => r.status === 'complete' && r.params)

  const xValsSet = new Set<number>()
  const yValsSet = new Set<number>()
  for (const r of complete) {
    const px = r.params?.[paramX]
    const py = r.params?.[paramY]
    if (px != null) xValsSet.add(Number(px))
    if (py != null) yValsSet.add(Number(py))
  }
  const xVals = Array.from(xValsSet).sort((a, b) => a - b)
  const yVals = Array.from(yValsSet).sort((a, b) => a - b)

  if (!xVals.length || !yVals.length) {
    return <div className="text-[12px] text-text-tertiary py-8 text-center">No complete runs yet.</div>
  }

  const cellMap = new Map<string, BacktestSummary>()
  for (const r of complete) {
    const key = `${Number(r.params?.[paramX])}|${Number(r.params?.[paramY])}`
    const existing = cellMap.get(key)
    if (!existing || (r.profit_factor ?? -Infinity) > (existing.profit_factor ?? -Infinity)) {
      cellMap.set(key, r)
    }
  }

  const pfs = complete.map(r => r.profit_factor ?? 0)
  const minPf = Math.min(...pfs)
  const maxPf = Math.max(...pfs)

  const CELL_W      = 72
  const CELL_H      = 46
  const LABEL_LEFT  = 64   // space for Y-axis labels + param name
  const LABEL_TOP   = 28   // space for X-axis labels
  const LEGEND_H    = 20
  const LEGEND_PAD  = 14
  const PARAM_LABEL = 14   // bottom X param name
  const PADDING_R   = 16

  const svgW = LABEL_LEFT + xVals.length * CELL_W + PADDING_R
  const gridH = yVals.length * CELL_H
  const svgH  = LABEL_TOP + gridH + LEGEND_PAD + LEGEND_H + PARAM_LABEL + 8

  const LEGEND_W  = Math.min(180, xVals.length * CELL_W)
  const legendX   = LABEL_LEFT
  const legendY   = LABEL_TOP + gridH + LEGEND_PAD

  return (
    <div className="overflow-x-auto">
      <svg width={svgW} height={svgH} className="font-mono">
        {/* X-axis param name */}
        <text
          x={LABEL_LEFT + (xVals.length * CELL_W) / 2}
          y={13}
          textAnchor="middle"
          fontSize={10}
          fill="#9ca3af"
          fontWeight="600"
        >
          {paramX}
        </text>

        {/* X-axis value labels */}
        {xVals.map((x, xi) => (
          <text
            key={`x-${x}`}
            x={LABEL_LEFT + xi * CELL_W + CELL_W / 2}
            y={LABEL_TOP - 6}
            textAnchor="middle"
            fontSize={10}
            fill="#6b7280"
          >
            {x}
          </text>
        ))}

        {/* Y-axis param name (rotated) */}
        <text
          x={0}
          y={0}
          transform={`translate(11, ${LABEL_TOP + gridH / 2}) rotate(-90)`}
          textAnchor="middle"
          fontSize={10}
          fill="#9ca3af"
          fontWeight="600"
        >
          {paramY}
        </text>

        {/* Y-axis value labels */}
        {yVals.map((y, yi) => (
          <text
            key={`y-${y}`}
            x={LABEL_LEFT - 8}
            y={LABEL_TOP + yi * CELL_H + CELL_H / 2 + 4}
            textAnchor="end"
            fontSize={10}
            fill="#6b7280"
          >
            {y}
          </text>
        ))}

        {/* Cells */}
        {yVals.map((y, yi) =>
          xVals.map((x, xi) => {
            const run  = cellMap.get(`${x}|${y}`)
            const pf   = run?.profit_factor ?? null
            const fill = pf != null ? scoreColor(pf, minPf, maxPf) : '#1f2937'
            const cx   = LABEL_LEFT + xi * CELL_W
            const cy   = LABEL_TOP  + yi * CELL_H
            return (
              <g key={`${x}-${y}`}>
                <rect
                  x={cx + 1} y={cy + 1}
                  width={CELL_W - 2} height={CELL_H - 2}
                  rx={3}
                  fill={fill}
                  fillOpacity={pf != null ? 0.88 : 0.18}
                  className={run ? 'cursor-pointer' : ''}
                  onClick={() => run && navigate(`/backtests/runs/${run.run_id}`)}
                >
                  {run && (
                    <title>{`${paramX}=${x}, ${paramY}=${y}\nPF: ${pf?.toFixed(2) ?? '—'}\nP&L: ${run.net_pnl != null ? `$${run.net_pnl.toFixed(0)}` : '—'}`}</title>
                  )}
                </rect>
                {pf != null && (
                  <text
                    x={cx + CELL_W / 2}
                    y={cy + CELL_H / 2 + 4}
                    textAnchor="middle"
                    fontSize={11}
                    fontWeight="600"
                    fill="rgba(255,255,255,0.92)"
                    pointerEvents="none"
                  >
                    {pf.toFixed(2)}
                  </text>
                )}
                {pf == null && (
                  <text
                    x={cx + CELL_W / 2}
                    y={cy + CELL_H / 2 + 4}
                    textAnchor="middle"
                    fontSize={10}
                    fill="#374151"
                    pointerEvents="none"
                  >
                    —
                  </text>
                )}
              </g>
            )
          })
        )}

        {/* Legend — gradient bar */}
        <defs>
          <linearGradient id="heatmap-legend" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%"   stopColor="#ff3b5c" />
            <stop offset="100%" stopColor="#00e5ff" />
          </linearGradient>
        </defs>
        <rect x={legendX} y={legendY} width={LEGEND_W} height={10} rx={3} fill="url(#heatmap-legend)" opacity={0.8} />
        <text x={legendX}           y={legendY + 22} fontSize={9} fill="#6b7280">Low PF</text>
        <text x={legendX + LEGEND_W} y={legendY + 22} fontSize={9} fill="#6b7280" textAnchor="end">High PF</text>
      </svg>

      <p className="text-[11px] text-text-tertiary mt-1">
        Each cell is one parameter combination. Profit factor determines color — brighter = higher.
        Click any cell to open that run.
      </p>
    </div>
  )
}
