import type { ReactNode } from 'react'

interface EmptyStateProps {
  icon: ReactNode
  title: string
  description: string
  action?: ReactNode
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-[90px] px-5 text-center">
      <div className="w-[54px] h-[54px] rounded-[14px] bg-bg-surface border border-border-default flex items-center justify-center text-text-tertiary">
        {icon}
      </div>
      <div className="text-[14px] font-semibold">{title}</div>
      <div className="text-[12px] text-text-tertiary max-w-[340px]">{description}</div>
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}
