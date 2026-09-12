/**
 * The anatomy the account panel and the bot panel share, so a section reads the same in both.
 *
 * ⚠ **One definition, imported by both** — two hand-written section headings is how the two panels
 * drift into two looks for one app, which is the shell duplication `components/Drawer.tsx` was
 * lifted out to end.
 */
import type { ReactNode } from 'react'

/** A section's heading: gold, small caps, with an optional control on the right. */
export function SectionTitle({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="flex items-center gap-2 mb-[10px] min-h-[26px]">
      <p className="text-[9.5px] font-semibold uppercase tracking-[0.8px] text-gold-text">
        {children}
      </p>
      {aside && <div className="ml-auto flex items-center gap-2">{aside}</div>}
    </div>
  )
}

/**
 * Whether a bot's process is running — THREE states. Red meant *stopped* and was also what an
 * UNANSWERED box drew, so a dead link to the VPS rendered as a list of quietly idle bots; unknown is
 * hollow and says so on hover.
 */
export function StateDot({ status }: { status: string | undefined }) {
  return (
    <span
      title={
        status === undefined
          ? 'The trading box has not answered for this bot — unknown, not stopped.'
          : status === 'RUNNING'
            ? 'Running'
            : 'Stopped'
      }
      className={`inline-block w-[7px] h-[7px] rounded-full shrink-0 ${
        status === undefined
          ? 'border border-text-tertiary'
          : status === 'RUNNING'
            ? 'bg-pos'
            : 'bg-neg'
      }`}
    />
  )
}
