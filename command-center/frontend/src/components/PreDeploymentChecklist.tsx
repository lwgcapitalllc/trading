import { useState } from 'react'
import { CheckSquare, Square, Lock } from 'lucide-react'

const ITEMS = [
  'Strategy has been graded A or B by the robustness test',
  'Strategy has clear stop loss and target rules (not fixed only)',
  'Strategy has at least one daily/weekly circuit breaker',
  'Strategy has been backtested on at least 1 year of data',
  "I have read the strategy's NinjaScript file and understand the logic",
]

function gradeQualifies(grade: string | null | undefined): boolean {
  if (!grade) return false
  return grade === 'A' || grade === 'B'
}

interface Props {
  bestGrade?: string | null
  onAllChecked?: () => void
}

export default function PreDeploymentChecklist({ bestGrade, onAllChecked }: Props) {
  const gradeOk = gradeQualifies(bestGrade)
  const [checked, setChecked] = useState<boolean[]>(Array(ITEMS.length).fill(false))

  const effectiveChecked = checked.map((v, i) => (i === 0 ? (gradeOk ? v : false) : v))
  const allChecked = effectiveChecked.every(Boolean)

  const toggle = (i: number) => {
    if (i === 0 && !gradeOk) return
    const next = [...checked]
    next[i] = !next[i]
    setChecked(next)
    const effective = next.map((v, j) => (j === 0 ? (gradeOk ? v : false) : v))
    if (effective.every(Boolean)) onAllChecked?.()
  }

  return (
    <div className="rounded-lg border border-border-subtle bg-bg-surface p-4 space-y-3">
      <p className="text-sm font-semibold text-text-primary">Pre-Deployment Checklist</p>
      <p className="text-xs text-text-secondary">Confirm all items before marking this strategy ready for a live eval purchase.</p>
      <ul className="space-y-2">
        {ITEMS.map((item, i) => {
          const locked = i === 0 && !gradeOk
          const ticked = effectiveChecked[i]
          return (
            <li
              key={i}
              className={`flex items-start gap-2 ${locked ? 'cursor-not-allowed opacity-60' : 'cursor-pointer group'}`}
              onClick={() => toggle(i)}
            >
              <span className={`mt-0.5 shrink-0 ${ticked ? 'text-pos-text' : locked ? 'text-text-tertiary' : 'text-text-tertiary group-hover:text-text-secondary'}`}>
                {locked ? <Lock size={16} /> : ticked ? <CheckSquare size={16} /> : <Square size={16} />}
              </span>
              <span className={`text-sm ${ticked ? 'text-text-secondary line-through' : 'text-text-primary'}`}>
                {item}
                {locked && (
                  <span className="ml-2 text-xs text-neg-text font-medium">
                    — best grade is {bestGrade ?? 'none'}, must be A or B
                  </span>
                )}
              </span>
            </li>
          )
        })}
      </ul>
      {allChecked && (
        <p className="text-xs text-pos-text font-medium mt-2">All items confirmed — strategy is ready for evaluation.</p>
      )}
    </div>
  )
}
