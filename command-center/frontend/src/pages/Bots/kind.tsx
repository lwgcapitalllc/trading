/**
 * Live or demo — ONE colour per kind of account, used everywhere a kind appears on the Bots page:
 * the filter switches, the section headings, the chips on the Unassigned list and both panels'
 * headers (Aaron, 2026-09-10: *"the live and demo pills should stand out"*). Amber is real money;
 * cyan is demo.
 *
 * ⚠ **In its own file so the page and both panels read ONE definition** — it lived inside
 * `index.tsx`, and a panel drawing its own amber would be a second answer to "which colour is real
 * money", which is the drift this page keeps being rebuilt to remove.
 *
 * ⚠ **Neither is green or red** — those are reserved for P&L here, so a coloured figure keeps
 * meaning up or down. ⚠ **A kind nobody stated stays grey**: painting it either colour is a guess,
 * and guessing "demo" for real money is the one direction that may not happen.
 */

export const KIND_TINT: Record<
  string,
  { chip: string; text: string; dot: string; on: string; off: string }
> = {
  live: {
    chip: 'bg-warn-muted text-warn-text border-warn/50',
    text: 'text-warn-text',
    dot: 'bg-warn',
    on: 'bg-warn/15 text-warn-text border-warn',
    off: 'text-text-tertiary border-border-default hover:text-warn-text hover:border-warn/50',
  },
  demo: {
    chip: 'bg-accent-muted text-accent-text border-accent/40',
    text: 'text-accent-text',
    dot: 'bg-accent',
    on: 'bg-accent/15 text-accent-text border-accent',
    off: 'text-text-tertiary border-border-default hover:text-accent-text hover:border-accent/50',
  },
}

const NEUTRAL_TINT = {
  chip: 'bg-bg-surface-2 text-text-tertiary border-border-strong',
  text: 'text-text-secondary',
  dot: 'bg-text-tertiary',
}

export const tintOf = (kind: string | null | undefined) => (kind && KIND_TINT[kind]) || NEUTRAL_TINT

export const KIND_NAME: Record<'live' | 'demo', string> = { live: 'Live', demo: 'Demo' }

/** An account's kind as a chip — the same look on its card and on its one-liner. */
export function KindChip({ kind }: { kind: string | undefined }) {
  return (
    <span
      data-testid="kind-chip"
      className={`inline-flex text-[10px] font-semibold px-[7px] py-[2px] rounded-pill uppercase tracking-[0.5px] border ${
        tintOf(kind).chip
      }`}
    >
      {kind ?? 'type unknown'}
    </span>
  )
}

/**
 * The kind at the top of a panel, where the next click may spend real money. A live account says
 * so in words (*Live · real money*), because a colour alone is the one signal a reader in a hurry
 * does not stop for. ⚠ Nothing is drawn for an unknown kind — see the note above.
 */
export function KindBadge({ kind }: { kind: string | null | undefined }) {
  if (kind !== 'live' && kind !== 'demo') return null
  return (
    <span
      data-testid="kind-badge"
      data-kind={kind}
      className={`inline-flex items-center gap-[5px] text-[10px] font-semibold px-[8px] py-[3px] rounded-pill uppercase tracking-[0.6px] border ${KIND_TINT[kind].chip}`}
    >
      <span className={`w-[6px] h-[6px] rounded-full ${KIND_TINT[kind].dot}`} />
      {kind === 'live' ? 'Live · real money' : 'Demo'}
    </span>
  )
}
