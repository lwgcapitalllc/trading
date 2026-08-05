import type { ReactNode } from 'react'

interface StatCardProps {
  label: string
  value: ReactNode
  sub?: ReactNode
  /** `warn` is for a state that is neither healthy nor failed — a bot that is running but
   *  blind, a balance the fleet could not fully report. Painting either of those `neg` claims
   *  a failure, and `neutral` hides it. */
  subVariant?: 'pos' | 'neg' | 'neutral' | 'warn'
  onClick?: () => void
  disabled?: boolean
}

export function StatCard({ label, value, sub, subVariant = 'neutral', onClick, disabled }: StatCardProps) {
  const subColor = {
    pos: 'text-pos-text',
    neg: 'text-neg-text',
    warn: 'text-warn-text',
    neutral: 'text-text-tertiary',
  }[subVariant]

  const baseClass = 'bg-bg-surface border border-border-subtle rounded-lg px-[15px] py-[13px]'

  if (disabled) {
    return (
      <div className={`${baseClass} opacity-35 cursor-not-allowed select-none`}>
        <div className="text-micro text-text-secondary uppercase tracking-[0.6px]">{label}</div>
        <div className="text-[25px] font-semibold mt-[5px] tracking-[-0.5px] mono">{value}</div>
        {sub && <div className={`text-micro mt-[1px] ${subColor}`}>{sub}</div>}
      </div>
    )
  }

  if (onClick) {
    return (
      <button
        onClick={onClick}
        className={`${baseClass} w-full text-left cursor-pointer hover:bg-bg-hover hover:border-border-default transition-colors duration-[120ms]`}
      >
        <div className="flex items-center justify-between">
          <div className="text-micro text-text-secondary uppercase tracking-[0.6px]">{label}</div>
          <span className="text-[11px] text-text-tertiary/40 leading-none">›</span>
        </div>
        <div className="text-[25px] font-semibold mt-[5px] tracking-[-0.5px] mono">{value}</div>
        {sub && <div className={`text-micro mt-[1px] ${subColor}`}>{sub}</div>}
      </button>
    )
  }

  return (
    <div className={baseClass}>
      <div className="text-micro text-text-secondary uppercase tracking-[0.6px]">{label}</div>
      <div className="text-[25px] font-semibold mt-[5px] tracking-[-0.5px] mono">{value}</div>
      {sub && <div className={`text-micro mt-[1px] ${subColor}`}>{sub}</div>}
    </div>
  )
}
