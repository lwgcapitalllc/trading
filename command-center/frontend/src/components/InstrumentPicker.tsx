/** Pick an instrument from the broker's OWN list, with type-ahead and a recents row.
 *
 * 🔴 **WHAT THIS REPLACES.** Both forms offered ten symbol names typed into the source by hand,
 * and they were Vantage's names while the lab sat attached to PU Prime — a list describing a
 * broker nobody was connected to, on a terminal carrying **1,085 instruments**. Shares, ETFs,
 * crypto, indices, bonds, energy and softs were all unreachable from the form, and the ten that
 * were offered included a bare forex group this account has disabled outright.
 *
 * ⚠ **It stays an INPUT, never a select.** A dropdown is the right way to browse 1,085 names and
 * the wrong way to enter the one you already know, and the previous version kept free typing for
 * exactly that reason. Everything here is additive: type what you like, or pick from the list.
 *
 * 🔴 **The unavailable state is a first-class state, not a spinner that never ends.** When the
 * terminal cannot be asked, this renders a plain text box and SAYS the list could not be loaded.
 * An empty dropdown would read as "this broker offers nothing", and the difference between "no"
 * and "cannot ask" is the distinction that cost this repo 50 blind minutes.
 *
 * ⚠ **Presentational state only.** What gets submitted is the string in `value`; this component
 * never resolves, rebases or validates a symbol. The rebase decision lives in the form that owns
 * the broker selection, and the backend binds it again at run creation.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { Check, ChevronDown, Search, X } from 'lucide-react'
import { inputCls, labelCls } from './ModalKit'
import type { BrokerUniverse } from '@/lib/instrumentSearch'
import { searchInstruments } from '@/lib/instrumentSearch'
import { pushRecent, readRecents, removeRecent } from '@/lib/instrumentRecents'

interface Props {
  value: string
  onChange: (symbol: string) => void
  /** The attached terminal's universe. `undefined` while it loads. */
  universe: BrokerUniverse | undefined
  loading?: boolean
  label?: string
  placeholder?: string
  /** Rendered under the input — the broker-naming warning each form owns. */
  note?: React.ReactNode
}

export function InstrumentPicker({
  value,
  onChange,
  universe,
  loading = false,
  label = 'Instrument',
  placeholder = 'Type a symbol or a name',
  note,
}: Props) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [assetClass, setAssetClass] = useState('')
  const [highlight, setHighlight] = useState(0)
  const wrapRef = useRef<HTMLDivElement>(null)

  const symbols = universe?.symbols ?? null
  const server = universe?.server ?? ''
  const [recents, setRecents] = useState<string[]>([])

  // Recents are bucketed by SERVER, so they can only be read once the terminal has said which one
  // it is on. A blank server reads back nothing rather than the previous broker's list.
  useEffect(() => {
    setRecents(readRecents(server))
  }, [server])

  // Close on a click anywhere else. A dropdown that only closes on Escape is one that follows you
  // down the form and covers the field below it.
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  const { matches, hidden } = useMemo(
    () => searchInstruments(symbols, query, { assetClass }),
    [symbols, query, assetClass]
  )

  useEffect(() => setHighlight(0), [query, assetClass])

  const choose = (symbol: string) => {
    onChange(symbol)
    setRecents(pushRecent(server, symbol))
    setQuery('')
    setOpen(false)
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      setOpen(false)
      return
    }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      if (!open) setOpen(true)
      const step = e.key === 'ArrowDown' ? 1 : -1
      setHighlight((h) => Math.min(Math.max(h + step, 0), Math.max(matches.length - 1, 0)))
      return
    }
    // Enter picks the highlighted row ONLY while the list is open with something in it.
    // Otherwise it must fall through to the form's submit, which is what somebody typing a symbol
    // they already know expects.
    if (e.key === 'Enter' && open && matches[highlight]) {
      e.preventDefault()
      choose(matches[highlight].symbol)
    }
  }

  const unavailable = universe != null && !universe.available
  // 🔴 **A REMEMBERED LIST MUST NEVER PASS AS A FRESH ONE.** When the terminal cannot be re-checked
  // the backend serves the last good read rather than a blank panel — which is right, and is only
  // honest if the page says so. The caption names the TIME and the ACCOUNT it was read from,
  // because the one real hazard is that the terminal moved during the gap, and an account number
  // in front of the reader is what lets them notice.
  const stale = universe?.stale === true
  const readAt = universe?.fetched_at
    ? new Date(universe.fetched_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : null
  // 🔴 **The box only swaps to the QUERY while there is a list to filter.** Focusing blanks the
  // field so you can type a search over it — fine while the dropdown is open, because the current
  // pick is still on screen with a tick beside it. With the terminal unreachable there IS no
  // dropdown, so the same blanking leaves an empty box and nothing anywhere saying what the run is
  // set to. Caught by focusing the real field during a real agent outage, not by reading this.
  // ⚠ The VALUE was never lost either way — it comes back on click-away — which is what makes this
  // the dangerous kind of wrong: it looks like the symbol was cleared and it was not.
  const filtering = open && symbols != null

  return (
    <div className="min-w-0" ref={wrapRef}>
      <label className={labelCls}>{label}</label>

      <div className="relative">
        <input
          type="text"
          value={filtering ? query : value}
          onChange={(e) => {
            setQuery(e.target.value)
            setOpen(true)
            // The box is the value while it is closed, so typing must also move the value —
            // otherwise a hand-typed symbol is lost the moment the list closes without a pick.
            onChange(e.target.value.toUpperCase())
          }}
          onFocus={() => {
            setQuery('')
            setOpen(true)
          }}
          onBlur={() => {
            if (!symbols) setOpen(false)
          }}
          onKeyDown={onKeyDown}
          /* ⚠ While the box is filtering it is EMPTY on purpose — you are typing a search over the
             pick, not editing it. So the current pick becomes the placeholder rather than
             vanishing: the field never reads as blank, and abandoning the search restores it. */
          placeholder={
            loading ? 'Loading the broker’s instruments…' : filtering && value ? value : placeholder
          }
          className={`${inputCls} font-mono pr-7`}
          spellCheck={false}
          autoComplete="off"
        />
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-text-tertiary hover:text-accent"
          title="Browse the broker’s instruments"
        >
          {open ? <Search size={12} /> : <ChevronDown size={12} />}
        </button>

        {/* 🔴 **THE PANEL'S BACKGROUND IS A THEME TOKEN, AND IT MUST BE ONE THAT EXISTS.** This
              read `bg-bg-raised` for its whole first life. There is no such colour in
              `tailwind.config.js` — the palette is base/sunken/surface/surface-2 — and Tailwind
              DROPS a class it cannot resolve without a word. So the dropdown rendered with no
              background at all: 60 instrument rows drawn straight over the form underneath, every
              line of the panel tangled with the settings behind it. ⚠ **A colour that does not
              exist and a colour that is deliberately transparent are the same thing on screen**,
              which is why nothing caught it until it was looked at. Gated now — see
              `scripts/check_theme_tokens.mjs`.
              ⚠ `bg-surface-2` rather than `bg-surface`: the modal itself is `bg-surface`, and a
              panel the same colour as the thing it floats over has no edge. */}
        {open && symbols && (
          <div className="absolute z-30 mt-1 w-full min-w-[420px] rounded-md border border-border-strong bg-bg-surface-2 shadow-pop">
            {/* Asset classes, in the broker's own terms. `All` first so the list is never
                narrowed by something the reader did not choose. */}
            <div className="flex flex-wrap gap-1 p-2 border-b border-border-subtle">
              <ClassChip
                label={`All ${universe?.count ?? ''}`}
                active={assetClass === ''}
                onClick={() => setAssetClass('')}
              />
              {(universe?.classes ?? []).map((c) => (
                <ClassChip
                  key={c.label}
                  label={`${c.label} ${c.count}`}
                  active={assetClass === c.label}
                  onClick={() => setAssetClass(c.label)}
                />
              ))}
            </div>

            <div className="max-h-[280px] overflow-y-auto">
              {matches.length === 0 ? (
                <div className="px-3 py-3 text-[11px] text-text-tertiary">
                  Nothing on {universe?.server || 'this terminal'} matches “{query}”.
                </div>
              ) : (
                matches.map((s, i) => (
                  <button
                    key={s.symbol}
                    type="button"
                    onMouseEnter={() => setHighlight(i)}
                    onClick={() => choose(s.symbol)}
                    className={`w-full text-left px-3 py-[5px] flex items-center gap-2 ${
                      i === highlight ? 'bg-bg-sunken' : ''
                    }`}
                  >
                    <span className="font-mono text-[12px] text-text-primary w-[110px] shrink-0 truncate">
                      {s.symbol}
                    </span>
                    <span className="text-[11px] text-text-secondary truncate flex-1">
                      {s.description}
                    </span>
                    {/* A restriction on the ACCOUNT, shown rather than hidden: the history is
                        still replayable, so the instrument stays pickable and says what it is. */}
                    {!s.tradable && (
                      <span className="text-[9px] text-warn-text shrink-0">
                        {s.trade_mode_label}
                      </span>
                    )}
                    <span className="text-[9px] text-text-tertiary shrink-0 w-[70px] text-right truncate">
                      {s.broker_group}
                    </span>
                    {s.symbol.toUpperCase() === value.trim().toUpperCase() && (
                      <Check size={11} className="text-accent shrink-0" />
                    )}
                  </button>
                ))
              )}
            </div>

            {/* A truncated list and a short one look identical, and one of them means keep typing. */}
            {hidden > 0 && (
              <div className="px-3 py-[6px] border-t border-border-subtle text-[10px] text-text-tertiary">
                {hidden} more match — keep typing to narrow it.
              </div>
            )}
            <div
              className={`px-3 py-[6px] border-t border-border-subtle text-[10px] ${
                stale ? 'text-warn-text' : 'text-text-tertiary'
              }`}
            >
              {universe?.count} instruments on <span className="font-mono">{universe?.server}</span>
              {universe?.account ? ` · ${universe.account}` : ''}
              {stale && readAt ? ` · read at ${readAt}, not re-checked just now` : ''}
            </div>
          </div>
        )}
      </div>

      {/* Recents — one click fills the box.
          🔴 **BELOW THE INPUT, AND THE POSITION IS THE WHOLE POINT.** These sat ABOVE it, which
          reads fine in isolation and is wrong in the form: instrument, bar size and period are
          three columns of ONE grid row aligned at the top, so a chip row appearing above the
          input shoved this field's box ~30px down while its two neighbours stayed put. Picking a
          symbol therefore knocked the row out of line, and it did it at the exact moment of the
          pick, so it read as the form breaking on the click. Reported from the screen 2026-09-07
          (*"after selecting everything goes out of sync"*).
          ⚠ **A control that CHANGES HEIGHT must grow downward when it shares a row.** Anything
          added above it moves the control itself, and the reader's eye is on the control. */}
      {recents.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-[6px]">
          {recents.map((sym) => (
            <span
              key={sym}
              className={`group inline-flex items-center gap-1 rounded px-[6px] py-[2px] text-[10px] font-mono border transition-colors ${
                sym.toUpperCase() === value.trim().toUpperCase()
                  ? 'border-accent text-accent'
                  : 'border-border-subtle text-text-secondary hover:border-accent hover:text-accent'
              }`}
            >
              <button type="button" onClick={() => choose(sym)} title={`Use ${sym}`}>
                {sym}
              </button>
              {/* ⚠ `neg-text`, not `danger-text` — the latter is not a colour in this theme and
                  Tailwind drops it silently, which left this hover doing nothing at all. */}
              <button
                type="button"
                onClick={() => setRecents(removeRecent(server, sym))}
                className="opacity-0 group-hover:opacity-100 text-text-tertiary hover:text-neg-text transition-opacity"
                title="Forget this one"
              >
                <X size={9} />
              </button>
            </span>
          ))}
        </div>
      )}

      {/* 🔴 "Could not ask" gets its own sentence. Silence here would read as a broker with
          nothing to offer, and the box still works — it is a plain text field again. */}
      {/* ⚠ Stated OUTSIDE the dropdown too — a reader who never opens the list still has to know the
          instrument in the box was checked against a remembered universe. */}
      {stale && (
        <div className="mt-[4px] text-[10px] text-warn-text leading-snug">
          Couldn’t re-check the terminal just now, so this is the list read
          {readAt ? ` at ${readAt}` : ' earlier'} from {universe?.server}
          {universe?.account ? ` · ${universe.account}` : ''}.
        </div>
      )}
      {unavailable && (
        <div className="mt-[4px] text-[10px] text-warn-text leading-snug">
          Could not read the broker’s instrument list: {universe?.reason}. Type the symbol exactly
          as the terminal spells it.
        </div>
      )}
      {note}
    </div>
  )
}

function ClassChip({
  label,
  active,
  onClick,
}: {
  label: string
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded px-[6px] py-[2px] text-[10px] border transition-colors ${
        active
          ? 'border-accent text-accent'
          : 'border-border-subtle text-text-secondary hover:text-accent'
      }`}
    >
      {label}
    </button>
  )
}
