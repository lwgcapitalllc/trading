/**
 * 2D heatmap for optimization results where the grid has exactly 2 swept params.
 * X-axis = param A values, Y-axis = param B values, color = objective score (run.profit_factor as proxy).
 * Built with SVG — no external chart library additions needed.
 */

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
  // low → #ff3b5c (red), high → #00e5ff (cyan/green)
  const r = Math.round(lerp(t, 255, 0))
  const g = Math.round(lerp(t, 59, 229))
  const b = Math.round(lerp(t, 92, 255))
  return `rgb(${r},${g},${b})`
}

export function OptimizationHeatmap({ runs, paramX, paramY }: Props) {
  const navigate = useNavigate()

  const complete = runs.filter(r => r.status === 'complete' && r.params)

  // Extract unique x/y axis values (sorted numerically)
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
    return <div className="text-[12px] text-text-tertiary py-6 text-center">No complete runs yet.</div>
  }

  // Build lookup: key=(x,y) → best run by pf
  const cellMap = new Map<string, BacktestSummary>()
  for (const r of complete) {
    const px = Number(r.params?.[paramX])
    const py = Number(r.params?.[paramY])
    const key = `${px}|${py}`
    const existing = cellMap.get(key)
    if (!existing || (r.profit_factor ?? -Infinity) > (existing.profit_factor ?? -Infinity)) {
      cellMap.set(key, r)
    }
  }

  const pfs = complete.map(r => r.profit_factor ?? 0)
  const minPf = Math.min(...pfs)
  const maxPf = Math.max(...pfs)

  const CELL_W = 52
  const CELL_H = 36
  const LABEL_LEFT  = 56
  const LABEL_TOP   = 24
  const PADDING_RIGHT = 8

  const svgW = LABEL_LEFT + xVals.length * CELL_W + PADDING_RIGHT
  const svgH = LABEL_TOP  + yVals.length * CELL_H + 2

  return (
    <div className="overflow-x-auto">
      <svg width={svgW} height={svgH} className="font-mono">
        {/* X-axis labels (top) */}
        {xVals.map((x, xi) => (
          <text
            key={x}
            x={LABEL_LEFT + xi * CELL_W + CELL_W / 2}
            y={14}
            textAnchor="middle"
            fontSize={9}
            fill="#6b7280"
          >
            {x}
          </text>
        ))}

        {/* Y-axis labels (left) */}
        {yVals.map((y, yi) => (
          <text
            key={y}
            x={LABEL_LEFT - 6}
            y={LABEL_TOP + yi * CELL_H + CELL_H / 2 + 4}
            textAnchor="end"
            fontSize={9}
            fill="#6b7280"
          >
            {y}
          </text>
        ))}

        {/* Cells */}
        {yVals.map((y, yi) =>
          xVals.map((x, xi) => {
            const run = cellMap.get(`${x}|${y}`)
            const pf  = run?.profit_factor ?? null
            const fill = pf != null ? scoreColor(pf, minPf, maxPf) : '#1f2937'
            const cx = LABEL_LEFT + xi * CELL_W
            const cy = LABEL_TOP  + yi * CELL_H
            return (
              <g key={`${x}-${y}`}>
                <rect
                  x={cx} y={cy}
                  width={CELL_W - 1} height={CELL_H - 1}
                  rx={2}
                  fill={fill}
                  fillOpacity={pf != null ? 0.85 : 0.25}
                  className={run ? 'cursor-pointer hover:opacity-100' : ''}
                  onClick={() => run && navigate(`/backtests/runs/${run.run_id}`)}
                >
                  {run && (
                    <title>
                      {`${paramX}=${x}, ${paramY}=${y}\nPF: ${pf?.toFixed(2) ?? '—'}\nP&L: ${run.net_pnl != null ? `$${run.net_pnl.toFixed(0)}` : '—'}`}
                    </title>
                  )}
                </rect>
                {pf != null && (
                  <text
                    x={cx + CELL_W / 2}
                    y={cy + CELL_H / 2 + 4}
                    textAnchor="middle"
                    fontSize={9}
                    fill="#e5e7eb"
                    pointerEvents="none"
                  >
                    {pf.toFixed(2)}
                  </text>
                )}
              </g>
            )
          })
        )}

        {/* Axis label captions */}
        <text
          x={LABEL_LEFT + (xVals.length * CELL_W) / 2}
          y={svgH - 0}
          textAnchor="middle"
          fontSize={9}
          fill="#9ca3af"
        >
          {paramX} →
        </text>
      </svg>
      <p className="text-[10px] text-text-tertiary mt-1">
        Color = profit factor (cyan = higher, red = lower). Click a cell to view that run.
        {LABEL_TOP > 0 && ` Y-axis = ${paramY}.`}
      </p>
    </div>
  )
}
