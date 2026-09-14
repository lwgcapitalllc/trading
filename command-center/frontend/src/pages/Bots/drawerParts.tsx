/**
 * The anatomy the account panel and the bot panel share, so a section reads the same in both.
 *
 * ⚠ **One definition, imported by both** — two hand-written section headings is how the two panels
 * drift into two looks for one app, which is the shell duplication `components/Drawer.tsx` was
 * lifted out to end.
 */
import type { ReactNode } from 'react'
import { ArrowLeft } from 'lucide-react'

/**
 * A section's heading: grey small caps, with an optional control on the right.
 *
 * ⚠ **Grey, not gold (2026-09-12)** — gold on every heading was colour saying nothing, and on these
 * panels colour marks an exception. `hint` carries the explanation a heading used to have as a
 * paragraph under it: on hover, rather than on every open.
 */
export function SectionTitle({
  children,
  aside,
  hint,
}: {
  children: ReactNode
  aside?: ReactNode
  hint?: string
}) {
  return (
    <div className="flex items-center gap-2 mb-[10px] min-h-[26px]">
      <p
        title={hint}
        className={`text-[9.5px] font-semibold uppercase tracking-[0.8px] text-text-tertiary ${
          hint ? 'cursor-help' : ''
        }`}
      >
        {children}
      </p>
      {aside && <div className="ml-auto flex items-center gap-2">{aside}</div>}
    </div>
  )
}

/**
 * One change a pinned Save will write, read as `B-LEG 10% → 8%`. The risk budget's footer and the
 * account settings' footer both list their pending changes with it, so the two read alike.
 */
export function Change({ label, from, to }: { label: string; from: string; to: string }) {
  return (
    <span className="inline-flex items-center gap-[5px] text-[11.5px] px-[8px] py-[3px] rounded-md bg-bg-surface-2 border border-border-subtle">
      <span className="text-text-secondary">{label}</span>
      <span
        title={from}
        className="font-mono tabular-nums text-text-tertiary max-w-[160px] truncate"
      >
        {from}
      </span>
      <span className="text-text-tertiary">→</span>
      <span title={to} className="font-mono tabular-nums text-text-primary max-w-[160px] truncate">
        {to}
      </span>
    </span>
  )
}

/** The labelled way back from a panel's inner step, beside its close button. */
export function BackButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      data-testid="panel-back"
      onClick={onClick}
      className="inline-flex items-center gap-[5px] text-[12px] px-[10px] py-[5px] rounded-md border border-border-default text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors"
    >
      <ArrowLeft size={12} /> Back
    </button>
  )
}
