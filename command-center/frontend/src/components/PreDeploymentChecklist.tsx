import { useState } from 'react'
import { CheckSquare, Square } from 'lucide-react'

const ITEMS = [
  'Strategy has been graded A or B by the robustness test',
  'Strategy has clear stop loss and target rules (not fixed only)',
  'Strategy has at least one daily/weekly circuit breaker',
  'Strategy has been backtested on at least 1 year of data',
  "I have read the strategy's NinjaScript file and understand the logic",
]

interface Props {
  onAllChecked?: () => void
}

export default function PreDeploymentChecklist({ onAllChecked }: Props) {
  const [checked, setChecked] = useState<boolean[]>(Array(ITEMS.length).fill(false))
  const allChecked = checked.every(Boolean)

  const toggle = (i: number) => {
    const next = [...checked]
    next[i] = !next[i]
    setChecked(next)
    if (next.every(Boolean)) onAllChecked?.()
  }

  return (
    <div className="rounded-lg border border-border-subtle bg-bg-surface p-4 space-y-3">
      <p className="text-sm font-semibold text-text-primary">Pre-Deployment Checklist</p>
      <p className="text-xs text-text-secondary">Confirm all items before marking this strategy ready for a live eval purchase.</p>
      <ul className="space-y-2">
        {ITEMS.map((item, i) => (
          <li key={i} className="flex items-start gap-2 cursor-pointer group" onClick={() => toggle(i)}>
            <span className={`mt-0.5 shrink-0 ${checked[i] ? 'text-pos-text' : 'text-text-tertiary group-hover:text-text-secondary'}`}>
              {checked[i] ? <CheckSquare size={16} /> : <Square size={16} />}
            </span>
            <span className={`text-sm ${checked[i] ? 'text-text-secondary line-through' : 'text-text-primary'}`}>
              {item}
            </span>
          </li>
        ))}
      </ul>
      {allChecked && (
        <p className="text-xs text-pos-text font-medium mt-2">All items confirmed — strategy is ready for evaluation.</p>
      )}
    </div>
  )
}
