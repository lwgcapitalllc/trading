import type { Ruleset } from '@/types'

const TYPE_CONFIG: Record<string, { label: string; cls: string }> = {
  prop_eval:   { label: 'PROP EVAL',   cls: 'bg-warn-muted text-warn-text' },
  prop_funded: { label: 'PROP FUNDED', cls: 'bg-pos-muted text-pos-text' },
  personal:    { label: 'PERSONAL',    cls: 'bg-accent-muted text-accent' },
  demo:        { label: 'DEMO',        cls: 'bg-bg-hover text-text-secondary' },
}

interface Props {
  ruleset_type: Ruleset['ruleset_type']
  size?: 'xs' | 'sm'
}

export function RulesetTypeBadge({ ruleset_type, size = 'xs' }: Props) {
  const cfg = TYPE_CONFIG[ruleset_type] ?? { label: ruleset_type.toUpperCase(), cls: 'bg-bg-hover text-text-tertiary' }
  const cls = size === 'sm'
    ? `text-[11px] px-2 py-[2px]`
    : `text-[10px] px-[6px] py-[1px]`
  return (
    <span className={`inline-flex items-center rounded font-semibold tracking-[0.4px] uppercase ${cls} ${cfg.cls}`}>
      {cfg.label}
    </span>
  )
}
