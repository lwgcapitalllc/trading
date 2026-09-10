/**
 * A number box the reader TYPES into — no spinner arrows, and no scroll wheel nudging the value.
 *
 * 🔴 Why not `<input type="number">`: the browser draws up/down arrows inside the box, which eat
 * the room the digits need (Aaron, 2026-09-10, on the stack form's risk box: *"I don't like the
 * browser default thing with an arrow up and an arrow down. Just let me freeform enter digits…
 * it's not wide enough for me to see how much percentage I've put in there"*). It also moves the
 * value when a mouse wheel passes over a focused box, which on a risk setting is a silent edit.
 *
 * ⚠ **It reports `null`, never 0, for a box that holds no number** — empty, or `.` mid-typing.
 * The caller decides what an empty box blocks. Reading it as zero is how a cleared risk box would
 * run a strategy at 0% with nothing on screen saying so (rule 1: "nothing" and "zero" are not the
 * same value).
 *
 * ⚠ **A keystroke that would make the text something other than a number is refused**, so the box
 * can only ever hold digits, one decimal point (unless `integer`), and — with `grouping` — the
 * thousands commas it drew itself. There is no minus: every field that uses this is a size, a
 * rate or a count.
 *
 * ⚠ **While focused it shows exactly what was typed; unfocused it shows the committed value**,
 * derived on render rather than synced by an effect, so an outside change (a rerun prefilling the
 * form) always reaches the screen the moment the box is not being edited.
 */

import { useState } from 'react'
import { inputCls } from '@/components/ModalKit'

function display(v: number | null, grouping: boolean): string {
  if (v == null || !Number.isFinite(v)) return ''
  return grouping ? v.toLocaleString('en-US', { maximumFractionDigits: 6 }) : String(v)
}

export function DecimalInput({
  value,
  onChange,
  integer = false,
  grouping = false,
  prefix,
  suffix,
  invalid = false,
  className = '',
  inputClassName = '',
  title,
  placeholder,
  'aria-label': ariaLabel,
  'data-testid': testId,
}: {
  value: number | null
  onChange: (v: number | null) => void
  /** Whole numbers only — for a field the backend stores as an integer (slippage ticks). */
  integer?: boolean
  /** Draw thousands separators while not being edited (a balance). */
  grouping?: boolean
  prefix?: string
  suffix?: string
  invalid?: boolean
  /** On the wrapper — width and layout. */
  className?: string
  /** On the input itself — padding, a border tint. */
  inputClassName?: string
  title?: string
  placeholder?: string
  'aria-label'?: string
  'data-testid'?: string
}) {
  const [focused, setFocused] = useState(false)
  const [text, setText] = useState('')
  const shown = focused ? text : display(value, grouping)
  const allowed = integer ? /^\d*$/ : /^\d*\.?\d*$/

  return (
    <div className={`relative ${className}`}>
      {prefix && (
        <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[12px] text-text-tertiary pointer-events-none">
          {prefix}
        </span>
      )}
      <input
        type="text"
        inputMode={integer ? 'numeric' : 'decimal'}
        autoComplete="off"
        spellCheck={false}
        value={shown}
        title={title}
        placeholder={placeholder}
        aria-label={ariaLabel}
        aria-invalid={invalid || undefined}
        data-testid={testId}
        onFocus={() => {
          // Edited without separators: a comma in the middle of a number being typed is noise.
          setText(display(value, false))
          setFocused(true)
        }}
        onBlur={() => setFocused(false)}
        onChange={(e) => {
          const bare = e.target.value.replace(/,/g, '')
          if (!allowed.test(bare)) return // refused — the box keeps what it had
          setText(bare)
          onChange(bare === '' || bare === '.' ? null : Number(bare))
        }}
        className={`${inputCls} font-mono tabular-nums ${prefix ? 'pl-6' : ''} ${
          suffix ? 'pr-7' : ''
        } ${inputClassName} ${invalid ? 'border-neg-text/60 focus:border-neg-text' : ''}`}
      />
      {suffix && (
        <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[12px] text-text-tertiary pointer-events-none">
          {suffix}
        </span>
      )}
    </div>
  )
}
