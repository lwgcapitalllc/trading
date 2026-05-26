import type { ReactNode } from 'react'

interface StatCardProps {
  label: string
  value: ReactNode
  sub?: ReactNode
  subVariant?: 'pos' | 'neg' | 'neutral'
}

export function StatCard({ label, value, sub, subVariant = 'neutral' }: StatCardProps) {
  const subColor = {
    pos: 'text-pos-text',
    neg: 'text-neg-text',
    neutral: 'text-text-tertiary',
  }[subVariant]

  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg px-[15px] py-[13px]">
      <div className="text-micro text-text-secondary uppercase tracking-[0.6px]">{label}</div>
      <div className="text-[25px] font-semibold mt-[5px] tracking-[-0.5px] mono">{value}</div>
      {sub && <div className={`text-micro mt-[1px] ${subColor}`}>{sub}</div>}
    </div>
  )
}
