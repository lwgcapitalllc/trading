// Accepts runner values ("ninjatrader", "mt5") or platform values ("NT8", "MT5").
type Props = { runner: string; size?: number; className?: string }

export function RunnerBadge({ runner, size = 22, className = '' }: Props) {
  const isMt5 = runner === 'mt5' || runner === 'MT5'
  return (
    <img
      src={isMt5 ? '/mt5-icon.png' : '/nt8-icon.png'}
      alt={isMt5 ? 'MetaTrader 5' : 'NinjaTrader'}
      title={isMt5 ? 'MetaTrader 5' : 'NinjaTrader'}
      width={size}
      height={size}
      className={`inline-block object-contain ${className}`}
    />
  )
}
