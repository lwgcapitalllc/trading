type Props = { runner: string; className?: string }

function NinjaTraderIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
      <rect width="15" height="15" rx="2.5" fill="#ff6a00"/>
      <path d="M2.5 11.5V3.5H4.4L7.5 8.6L10.6 3.5H12.5V11.5H10.8V6.4L7.5 11.2L4.2 6.4V11.5H2.5Z" fill="white"/>
    </svg>
  )
}

function Mt5Icon() {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
      <rect width="15" height="15" rx="2.5" fill="#1565c0"/>
      {/* Upward arrow in green */}
      <path d="M7.5 2L12 7H9.5V10.5H5.5V7H3L7.5 2Z" fill="#43a047"/>
      {/* Yellow base bar */}
      <rect x="3.5" y="11.5" width="8" height="1.5" rx="0.5" fill="#fdd835"/>
    </svg>
  )
}

export function RunnerBadge({ runner, className = '' }: Props) {
  const isMt5 = runner === 'mt5'
  return (
    <span className={`inline-flex items-center gap-1 ${className}`}>
      {isMt5 ? <Mt5Icon /> : <NinjaTraderIcon />}
      <span
        className="text-[10px] font-bold uppercase tracking-wide"
        style={{ color: isMt5 ? '#4fc3f7' : '#ff6a00' }}
      >
        {isMt5 ? 'MT5' : 'NT8'}
      </span>
    </span>
  )
}
