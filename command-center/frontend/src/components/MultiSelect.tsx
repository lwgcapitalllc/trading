/**
 * A dropdown of checkboxes — pick any number of options from one compact control.
 *
 * Presentational only (same rule as `ModalKit`): it knows options, a selection and a toggle, and
 * nothing about what is being picked. The closed button names what is chosen, so the selection
 * is readable without opening it.
 */

import { useEffect, useRef, useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { inputCls } from '@/components/ModalKit'

export interface MultiSelectOption {
  value: string
  label: string
  /** A short neutral chip beside the label (e.g. an account tier). */
  tag?: string
}

export function MultiSelect({
  options,
  selected,
  onToggle,
  onSetAll,
  placeholder = 'Select…',
  invalid = false,
  testId,
}: {
  options: MultiSelectOption[]
  selected: ReadonlySet<string>
  onToggle: (value: string) => void
  /** Offer "Select all / Clear" inside the list. */
  onSetAll?: (all: boolean) => void
  placeholder?: string
  invalid?: boolean
  testId?: string
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey, true)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey, true)
    }
  }, [open])

  const chosen = options.filter((o) => selected.has(o.value))
  const summary =
    chosen.length === 0
      ? placeholder
      : chosen.length === 1
        ? chosen[0].label
        : `${chosen[0].label} +${chosen.length - 1}`
  const allOn = options.length > 0 && chosen.length === options.length

  return (
    <div ref={ref} className="relative" data-testid={testId}>
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        title={chosen.map((o) => o.label).join(', ')}
        className={`${inputCls} flex items-center gap-2 text-left ${
          invalid ? 'border-neg-text/60' : ''
        }`}
      >
        <span className={`flex-1 truncate ${chosen.length === 0 ? 'text-text-tertiary' : ''}`}>
          {summary}
        </span>
        <ChevronDown size={14} className="text-text-tertiary flex-shrink-0" />
      </button>
      {open && (
        <div
          role="listbox"
          aria-multiselectable="true"
          className="absolute z-50 mt-1 w-full min-w-[260px] rounded-md border border-border-default bg-bg-surface shadow-xl py-1 max-h-[280px] overflow-y-auto"
        >
          {options.map((o) => (
            <label
              key={o.value}
              role="option"
              aria-selected={selected.has(o.value)}
              className="flex items-center gap-2.5 px-3 py-1.5 cursor-pointer hover:bg-bg-hover"
            >
              <input
                type="checkbox"
                checked={selected.has(o.value)}
                onChange={() => onToggle(o.value)}
                className="w-3.5 h-3.5 rounded accent-accent flex-shrink-0"
              />
              <span className="text-[12px] text-text-primary flex-1">{o.label}</span>
              {o.tag && (
                <span className="text-[9px] px-[5px] py-[1px] rounded-pill font-semibold uppercase tracking-[0.3px] bg-bg-hover text-text-secondary">
                  {o.tag}
                </span>
              )}
            </label>
          ))}
          {onSetAll && options.length > 1 && (
            <button
              type="button"
              onClick={() => onSetAll(!allOn)}
              className="w-full text-left px-3 py-1.5 mt-1 border-t border-border-subtle text-[11px] text-accent hover:bg-bg-hover"
            >
              {allOn ? 'Clear all' : 'Select all'}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
