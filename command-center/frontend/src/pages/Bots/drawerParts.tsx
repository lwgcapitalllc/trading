/**
 * The anatomy the account panel and the bot panel share, so a section reads the same in both.
 *
 * ⚠ **One definition, imported by both** — two hand-written section headings is how the two panels
 * drift into two looks for one app, which is the shell duplication `components/Drawer.tsx` was
 * lifted out to end.
 */
import type { ReactNode } from 'react'

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
