import { useEffect, type ReactNode } from 'react'
import { X } from 'lucide-react'

/**
 * The slide-out panel from the right edge: a dimmed backdrop, a fixed-width sheet, a header with
 * a title and a close button, and a body that scrolls on its own.
 *
 * ⚠ **Every slide-out on the Bots page is this one shell** — the account panel, the bot panel and
 * the Sync VPS drawer (the first two adopted it on 2026-09-11, when they were rebuilt). A change to
 * the look of a drawer is made here, once. `width` is a prop because the account panel runs
 * demo → live inside itself and needs 720px where the bot panel needs 620.
 *
 * ⚠ **Escape closes it**, which neither inline copy does. A panel that covers the page and can
 * only be dismissed with the mouse is a panel people learn to avoid opening.
 *
 * ⚠ **`footer` is PINNED under the scrolling body** — for the one action the whole panel builds up
 * to (Sync, Save). At the end of a long body it is the thing that scrolls out of reach first.
 */
export function Drawer({
  open,
  onClose,
  title,
  subtitle,
  actions,
  label,
  footer,
  width = 620,
  children,
}: {
  open: boolean
  onClose: () => void
  title: ReactNode
  subtitle?: ReactNode
  /** Controls beside the close button, e.g. a rescan. */
  actions?: ReactNode
  /** Accessible name for the sheet. */
  label: string
  /** Pinned under the body; never scrolls. */
  footer?: ReactNode
  /** The sheet's width in px, capped at the screen. ⚠ A CAP, never a fraction of the viewport: a
   *  panel wide enough to hide the list it was opened from is a page you left without meaning to. */
  width?: number
  children: ReactNode
}) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null
  return (
    <>
      <div className="fixed inset-0 bg-black/55 z-40" onClick={onClose} />
      <aside
        aria-label={label}
        style={{ width: `min(${width}px, 100%)` }}
        className="fixed top-0 right-0 bottom-0 bg-bg-surface border-l border-border-default z-50 flex flex-col"
      >
        <div className="flex items-start gap-3 px-5 py-[18px] border-b border-border-subtle shrink-0">
          <div className="min-w-0">
            <p className="text-[16px] font-semibold leading-tight mb-[3px]">{title}</p>
            {subtitle && <div className="text-[11.5px] text-text-secondary">{subtitle}</div>}
          </div>
          <div className="ml-auto flex items-center gap-2 shrink-0">
            {actions}
            <button
              onClick={onClose}
              aria-label="Close"
              className="w-[28px] h-[28px] grid place-items-center rounded-md border border-border-default text-text-tertiary hover:text-text-primary hover:bg-bg-hover transition-colors"
            >
              <X size={13} />
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto px-5 pb-8">{children}</div>
        {footer && (
          <div className="shrink-0 border-t border-border-subtle bg-bg-surface px-5 py-3">
            {footer}
          </div>
        )}
      </aside>
    </>
  )
}
