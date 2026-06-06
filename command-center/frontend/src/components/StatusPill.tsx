export function StatusPill({ status, size = 'sm' }: { status: string; size?: 'sm' | 'md' }) {
  const isFailed = status.startsWith('failed')
  const label    = isFailed ? 'failed' : status
  const cls      = status === 'complete' ? 'bg-pos-muted text-pos-text'
    : status === 'running'  ? 'bg-accent-muted text-accent'
    : isFailed              ? 'bg-neg-muted text-neg-text'
    : 'bg-bg-hover text-text-secondary'
  const textCls  = size === 'md' ? 'text-[12px] px-3 py-[4px]' : 'text-[11px] px-2 py-[2px]'
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full font-semibold uppercase tracking-[0.4px] flex-shrink-0 ${textCls} ${cls}`}>
      {status === 'running' && (
        <span className="w-[6px] h-[6px] rounded-full bg-accent animate-pulse flex-shrink-0" />
      )}
      {label}
    </span>
  )
}
