// Accepts runner values ("ninjatrader", "mt5") or platform values ("NT8", "MT5").
type Props = { runner: string; className?: string }

function NinjaTraderIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
      <rect width="15" height="15" rx="2.5" fill="#ff6a00"/>
      {/*
        Bold N: left bar + diagonal top-left→bottom-right + right bar.
        Path traces: up left outer, across top-left, diagonal down-right,
        up inner-right, across top-right, down right outer, across bottom-right,
        diagonal up-left, down inner-left, across bottom-left.
      */}
      <path d="M2.5 12V3H4.5L10.5 9.5V3H12.5V12H10.5L4.5 5.5V12H2.5Z" fill="white"/>
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
  const isMt5 = runner === 'mt5' || runner === 'MT5'
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
