type Props = { runner: string; className?: string }

export function RunnerBadge({ runner, className = '' }: Props) {
  const isMt5 = runner === 'mt5'
  return (
    <span
      className={`inline-block text-[10px] font-bold uppercase tracking-wider px-1.5 py-[1px] rounded ${className}`}
      style={{
        color:           isMt5 ? '#3b82f6' : '#10b981',
        backgroundColor: isMt5 ? 'rgba(59,130,246,0.12)' : 'rgba(16,185,129,0.12)',
      }}
    >
      {isMt5 ? 'MT5' : 'NT8'}
    </span>
  )
}
