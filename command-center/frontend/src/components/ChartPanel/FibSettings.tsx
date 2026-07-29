/**
 * Fib level editor — the TradingView-style "add / remove / retune / recolour a level" panel.
 *
 * It edits ONE ladder, and the host decides whose: the tool's DEFAULT set (every fib that has not
 * been customised follows it live) or ONE drawing's own override. Both use this same component, so
 * the two can never drift in behaviour or look.
 *
 * Editing is LIVE — every keystroke commits upward and the chart redraws — so a level is retuned by
 * watching it move, not by typing a number and pressing OK. That is the whole point of doing this on
 * the chart instead of in a modal.
 *
 * The ratio is held as a STRING while editing. A number input cannot represent "0." or "-" — the
 * states a decimal necessarily passes through as it is typed — and coercing them to 0 mid-keystroke
 * makes the field fight the user. A row whose text is not yet a number simply sits out that frame
 * and returns the moment it parses.
 */
import { useEffect, useRef, useState } from 'react'
import { Eye, EyeOff, Plus, RotateCcw, Trash2, X } from 'lucide-react'
import { NEW_LEVEL_COLOR, nextFibRatio, type FibLevel } from './fibLevels'

// Feeds the panel's OWN viewport clamp (it places itself, like the right-click menu, rather than
// making every caller do the maths). Keep in sync with the width/max-height in the markup below.
const PANEL_W = 300
const PANEL_H = 396

interface Row { ratio: string; color: string; visible: boolean }

const toRows = (levels: FibLevel[]): Row[] =>
  levels.map(l => ({ ratio: String(l.ratio), color: l.color, visible: l.visible !== false }))

const toLevels = (rows: Row[]): FibLevel[] =>
  rows.flatMap(r => {
    const ratio = Number(r.ratio)
    return r.ratio.trim() === '' || !Number.isFinite(ratio) ? [] : [{ ratio, color: r.color, visible: r.visible }]
  })

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
  const [rows, setRows] = useState<Row[]>(() => toRows(levels))
  // Re-seed the rows whenever the host changes the ladder from OUTSIDE the typing loop — a reset,
  // dropping a per-drawing override, or retargeting the panel. Keyed on `resetKey` alone, never on
  // `levels`: `levels` changes on every keystroke (we just committed it), and depending on it would
  // overwrite what is being typed.
  //
  // This MUST be an effect. The tempting version — mutating a "last seen key" ref during render and
  // calling setRows there — is silently broken under StrictMode, which double-invokes the render
  // function: the first (discarded) invocation moves the ref, the second sees it already current
  // and skips the seed, and the reset does nothing at all. Measured, not theorised.
  const seededRef = useRef(levels)
  seededRef.current = levels
  useEffect(() => { setRows(toRows(seededRef.current)) }, [resetKey])

  const commit = (next: Row[]) => { setRows(next); onChange(toLevels(next)) }
  const patch = (i: number, p: Partial<Row>) => commit(rows.map((r, j) => (j === i ? { ...r, ...p } : r)))
  const remove = (i: number) => commit(rows.filter((_, j) => j !== i))

  // A new level is INSERTED in ascending position, not appended: the list is read as a ladder, and
  // one that jumps around after every add stops being scannable.
  const add = () => {
    const ratio = nextFibRatio(toLevels(rows))
    const row: Row = { ratio: String(ratio), color: NEW_LEVEL_COLOR, visible: true }
    const at = rows.findIndex(r => Number(r.ratio) > ratio)
    commit(at < 0 ? [...rows, row] : [...rows.slice(0, at), row, ...rows.slice(at)])
  }

  const shownCount = rows.filter(r => r.visible).length

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
        <span className="ml-auto font-mono text-[10px] text-text-tertiary">{shownCount}/{rows.length}</span>
        <button onClick={onClose} className="text-text-tertiary transition-colors hover:text-text-primary">
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="max-h-[248px] overflow-y-auto py-1">
        {rows.length === 0 && (
          <div className="px-3 py-4 text-center text-[10px] text-text-tertiary">
            No levels — this fib draws nothing.<br />Add one below.
          </div>
        )}
        {rows.map((row, i) => (
          <div key={i} className="flex items-center gap-2 px-2.5 py-1 transition-colors hover:bg-bg-sunken">
            <button
              onClick={() => patch(i, { visible: !row.visible })}
              title={row.visible ? 'Hide this level (keeps it in the set)' : 'Show this level'}
              className="flex-shrink-0 text-text-tertiary transition-colors hover:text-text-primary"
            >
              {row.visible ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />}
            </button>
            <input
              value={row.ratio}
              onChange={e => patch(i, { ratio: e.target.value })}
              inputMode="decimal"
              spellCheck={false}
              className={`w-[74px] flex-shrink-0 rounded border border-border-subtle bg-bg-sunken px-1.5 py-1 font-mono text-[11px] tabular-nums outline-none transition-colors focus:border-accent ${
                row.visible ? 'text-text-primary' : 'text-text-tertiary'
              }`}
            />
            {/* Native colour picker, hidden behind its own swatch so it inherits the panel's look
                instead of the browser's chunky default control. */}
            <label
              className="relative h-5 w-5 flex-shrink-0 cursor-pointer rounded-[3px] border border-border-subtle"
              style={{ background: row.color, opacity: row.visible ? 1 : 0.4 }}
              title="Level colour"
            >
              <input
                type="color"
                value={row.color}
                onChange={e => patch(i, { color: e.target.value })}
                className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
              />
            </label>
            <span className="flex-1 truncate font-mono text-[10px] text-text-tertiary">
              {ratioNote(row.ratio)}
            </span>
            <button
              onClick={() => remove(i)}
              title="Remove this level"
              className="flex-shrink-0 text-text-tertiary transition-colors hover:text-neg-text"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>

      <div className="border-t border-border-subtle px-2.5 py-2">
        <button
          onClick={add}
          className="flex w-full items-center justify-center gap-1.5 rounded border border-border-subtle bg-bg-sunken py-1.5 text-[11px] font-medium text-text-secondary transition-colors hover:border-accent/50 hover:text-text-primary"
        >
          <Plus className="h-3 w-3" /> Add level
        </button>
        <div className="mt-1.5 flex items-center gap-2">
          {scope === 'drawing' ? (
            <>
              <button
                onClick={onUseDefault}
                disabled={!isCustom}
                className="text-[10px] font-medium text-text-tertiary transition-colors hover:text-text-primary disabled:cursor-default disabled:opacity-40 disabled:hover:text-text-tertiary"
              >
                Use default set
              </button>
              <button
                onClick={onSaveAsDefault}
                className="ml-auto text-[10px] font-medium text-accent transition-opacity hover:opacity-80"
              >
                Save as default
              </button>
            </>
          ) : (
            <button
              onClick={onResetFactory}
              className="flex items-center gap-1 text-[10px] font-medium text-text-tertiary transition-colors hover:text-text-primary"
            >
              <RotateCcw className="h-3 w-3" /> Reset to original levels
            </button>
          )}
        </div>
        <p className="mt-1.5 text-[10px] leading-snug text-text-tertiary">
          {scope === 'drawing'
            ? 'Changes apply to this fib only.'
            : 'Applies to new fibs and every fib you have not customised.'}
          {' '}Ratios past 1 or below 0 draw extensions.
        </p>
      </div>
    </div>
  )
}

/** The right-hand hint on each row — what this ratio IS, so the ladder can be read without
 *  decoding numbers. Deliberately generic (no strategy or entry/target language): the panel's one
 *  rule is the chart's, that it knows nothing about what a level is used for. */
function ratioNote(raw: string): string {
  const r = Number(raw)
  if (raw.trim() === '' || !Number.isFinite(r)) return '—'
  if (r === 0 || r === 1) return 'anchor'
  if (r < 0 || r > 1) return 'ext'
  return `${+(r * 100).toFixed(2)}%`
}
