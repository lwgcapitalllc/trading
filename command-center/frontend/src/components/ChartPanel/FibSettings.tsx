/**
 * The floating fib editor — ONE drawing's own ladder, opened from that fib's right-click menu.
 *
 * It is a frame around `FibLevelEditor`: position, header, close. The rows and the footer moved into
 * that component on 2026-08-06 so the **Chart settings** panel could host the same editor for the
 * DEFAULT ladder without becoming a second implementation of it.
 *
 * ⚠ **The default ladder is NO LONGER reachable from here** — it lives in Chart settings, which is
 * where a reader looks for how the chart is drawn. `scope` is still on the contract because the
 * editor's footer genuinely differs (this one offers *Use default set* / *Save as default*), and
 * because a `default`-scoped frame is one line away if a second entry point is ever wanted. Do not
 * add one back without deleting the other: two places to edit one ladder is two answers.
 */
import { X } from 'lucide-react'
import { useState } from 'react'
import FibLevelEditor from './FibLevelEditor'
import { type FibLevel } from './fibLevels'

// Feeds the panel's OWN viewport clamp (it places itself, like the right-click menu, rather than
// making every caller do the maths). Keep in sync with the width/max-height in the markup below.
const PANEL_W = 300
const PANEL_H = 396

interface FibSettingsProps {
  /** Cursor/anchor position — the panel floats viewport-fixed here, clamped by the host. */
  x: number
  y: number
  /** `default` = the ladder new + un-customised fibs follow. `drawing` = this one fib's override. */
  scope: 'default' | 'drawing'
  levels: FibLevel[]
  /** Bump to re-seed the rows from `levels` (an outside change: reset, or a new target). */
  resetKey: string
  /** `drawing` scope only — true once this fib's ladder differs from the default. */
  isCustom?: boolean
  onChange: (levels: FibLevel[]) => void
  onClose: () => void
  /** `drawing` scope — promote this ladder to the default (and go back to following it). */
  onSaveAsDefault?: () => void
  /** `drawing` scope — drop the override and follow the default again. */
  onUseDefault?: () => void
  /** `default` scope — back to the factory ladder. */
  onResetFactory?: () => void
}

export default function FibSettings({
  x, y, scope, levels, resetKey, isCustom,
  onChange, onClose, onSaveAsDefault, onUseDefault, onResetFactory,
}: FibSettingsProps) {
  const [count, setCount] = useState<{ shown: number; total: number }>({ shown: 0, total: 0 })

  return (
    <div
      // Stops the host's outside-mousedown close AND the chart body's measure-mode click handler
      // from firing on anything in here.
      onMouseDown={e => e.stopPropagation()}
      onClick={e => e.stopPropagation()}
      className="fixed rounded-md border border-border-subtle bg-bg-surface shadow-xl"
      style={{
        left: Math.max(6, Math.min(x, window.innerWidth - PANEL_W - 6)),
        top: Math.max(6, Math.min(y, window.innerHeight - PANEL_H - 6)),
        width: PANEL_W,
        zIndex: 60,
      }}
    >
      <div className="flex items-center gap-2 border-b border-border-subtle px-3 py-2">
        <span className="text-[11px] font-semibold text-text-primary">
          {scope === 'drawing' ? 'Fib levels · this drawing' : 'Fib levels'}
        </span>
        {scope === 'drawing' && isCustom && (
          <span className="rounded-sm bg-gold-muted px-1.5 py-px text-[9px] font-semibold uppercase tracking-wide text-gold-text">
            Custom
          </span>
        )}
        <span className="ml-auto font-mono text-[10px] text-text-tertiary">
          {count.shown}/{count.total}
        </span>
        <button onClick={onClose} className="text-text-tertiary transition-colors hover:text-text-primary">
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      <FibLevelEditor
        scope={scope}
        levels={levels}
        resetKey={resetKey}
        isCustom={isCustom}
        onChange={onChange}
        onSaveAsDefault={onSaveAsDefault}
        onUseDefault={onUseDefault}
        onResetFactory={onResetFactory}
        onCountChange={(shown, total) => setCount({ shown, total })}
      />
    </div>
  )
}
