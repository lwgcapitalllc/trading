import type { ReactNode } from 'react'

interface StatCardProps {
  label: string
  value: ReactNode
  sub?: ReactNode
  subVariant?: 'pos' | 'neg' | 'neutral'
  onClick?: () => void
  disabled?: boolean
}

export function StatCard({ label, value, sub, subVariant = 'neutral', onClick, disabled }: StatCardProps) {
  const subColor = {
    pos: 'text-pos-text',
    neg: 'text-neg-text',
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
        <div className="text-micro text-text-secondary uppercase tracking-[0.6px]">{label}</div>
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
