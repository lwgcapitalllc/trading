import { useEffect, useRef, useState } from 'react'
import { MoreHorizontal, type LucideIcon } from 'lucide-react'

/** One entry in an `OverflowMenu`. */
export interface OverflowItem {
  key: string
  label: string
  icon?: LucideIcon
  onSelect: () => void
  disabled?: boolean
  /** Why it is disabled, or what it does — on hover. */
  title?: string
  testId?: string
}

/**
 * A "···" button that opens a short list of the actions a row does not need on screen all the time.
 *
 * 🔴 **Only for the SECONDARY actions (2026-09-15).** The Bots page moved a bot's Restart and Logs
 * in here so a row shows one primary button instead of four near-identical icons — Aaron: *"does it
 * feel too busy?"*. Anything a reader goes LOOKING for belongs on the row, not in here: Configure
 * stayed out on purpose, because it had already been lost twice as a control you had to find.
 *
 * ⚠ Closes on a click anywhere else and on Escape — the same two rules the instrument picker's
 * dropdown follows, so a menu never follows you round the page. ⚠ Every click inside stops
 * propagating: the menu sits inside rows that react to clicks of their own.
 */
export function OverflowMenu({
  items,
  label,
  testId,
}: {
  items: OverflowItem[]
  /** What the button opens, for the hover and a screen reader — "More for SOS Fade". */
  label: string
  testId?: string
}) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div ref={wrapRef} className="relative">
      <button
        type="button"
        data-testid={testId}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={label}
        title={label}
        onClick={(e) => {
          e.stopPropagation()
          setOpen((o) => !o)
        }}
        className={`w-[26px] h-[26px] grid place-items-center rounded-md border transition-colors ${
          open
            ? 'border-border-default bg-bg-surface-2 text-text-primary'
            : 'border-transparent text-text-tertiary hover:text-text-primary hover:border-border-default hover:bg-bg-surface-2'
        }`}
      >
        <MoreHorizontal size={13} />
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 top-[calc(100%+4px)] z-20 min-w-[150px] py-[4px] bg-bg-surface-2 border border-border-default rounded-lg shadow-lg"
        >
          {items.map((it) => (
            <button
              key={it.key}
              type="button"
              role="menuitem"
              data-testid={it.testId}
              disabled={it.disabled}
              title={it.title}
              onClick={(e) => {
                e.stopPropagation()
                setOpen(false)
                it.onSelect()
              }}
              className="w-full flex items-center gap-[8px] px-[10px] py-[6px] text-[12px] text-left text-text-secondary hover:bg-bg-hover hover:text-text-primary disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {it.icon && <it.icon size={12} className="shrink-0" />}
              {it.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
