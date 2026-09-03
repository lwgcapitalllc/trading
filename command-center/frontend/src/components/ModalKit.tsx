/**
 * The pieces the RUN modal and the STACK modal both build their forms out of.
 *
 * 🔴 **ONE implementation, not two.** These lived in `RunBacktestModal` and the stack form had
 * its own hand-rolled headings, inputs and tooltips — which is why the two read as different
 * apps: same job, same page, three font sizes and two heading styles apart. Reported from the
 * screen 2026-09-03 (*"the layout is really bad, make it feel like the run one"*), and a shared
 * kit is the only version of that fix which stays true — mirroring the styles by hand is how
 * they drifted in the first place.
 *
 * ⚠ **Presentational only.** Nothing here knows about a run, a stack, a broker or a cost. The
 * moment one of these takes a domain object it stops being shareable and the copy comes back.
 */

import { ChevronDown, ChevronRight, Info } from 'lucide-react'

/** The form input, and its label. Every field on both modals uses these two, so a field that
 *  looks different from its neighbour is a mistake rather than a decision. */
export const inputCls =
  'bg-bg-sunken border border-border-subtle rounded-md px-3 py-[6px] text-[13px] text-text-primary w-full focus:outline-none focus:border-accent transition-colors'
export const labelCls = 'block text-[11px] text-text-secondary mb-1'

// ── Tooltip ───────────────────────────────────────────────────────────────────

export function InfoTooltip({
  content,
  side = 'right',
}: {
  content: string
  side?: 'right' | 'left'
}) {
  // 'right' → tooltip opens rightward from the icon (left-side icons)
  // 'left'  → tooltip opens leftward from the icon (right-side icons)
  const anchorCls = side === 'right' ? 'left-0' : 'right-0'
  return (
    <span className="relative group/tip inline-flex items-center ml-1 flex-shrink-0">
      <Info
        size={10}
        className="text-text-tertiary group-hover/tip:text-accent cursor-help transition-colors"
      />
      <span
        className={`absolute ${anchorCls} bottom-[calc(100%+5px)] z-50 hidden group-hover/tip:block w-56 rounded-md bg-bg-surface border border-border-default px-2.5 py-2 text-[11px] text-text-secondary shadow-xl pointer-events-none leading-relaxed`}
      >
        {content}
      </span>
    </span>
  )
}

// ── Section heading ───────────────────────────────────────────────────────────

/**
 * A section title. With `onToggle` it becomes the section's collapse control.
 *
 * ⚠ A collapsed section MUST pass `summary` — the header is then the only thing standing for
 * everything folded away, and a reader who cannot see what a hidden section is set to will open
 * every one of them, which is worse than never having collapsed anything.
 */
export function SectionHead({
  label,
  tooltip,
  open,
  onToggle,
  summary,
}: {
  label: string
  tooltip?: string
  open?: boolean
  onToggle?: () => void
  summary?: string
}) {
  const head = (
    <>
      {label}
      {tooltip && <InfoTooltip content={tooltip} />}
    </>
  )
  const cls =
    'flex items-center gap-1 text-[10px] font-semibold text-text-tertiary uppercase tracking-[0.7px]'
  if (!onToggle) return <div className={`${cls} mb-3`}>{head}</div>
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      className={`${cls} w-full ${open ? 'mb-3' : 'mb-0'} hover:text-text-secondary transition-colors`}
    >
      {open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
      {head}
      {summary && (
        <span className="ml-auto normal-case tracking-normal font-normal text-[11px] text-text-tertiary truncate">
          {summary}
        </span>
      )}
    </button>
  )
}

export function Divider() {
  return <div className="border-t border-border-subtle" />
}
