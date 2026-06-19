import { useState, useMemo, useEffect } from 'react'
import { ChevronRight, ChevronDown } from 'lucide-react'
import type { ParamSchemaEntry } from '@/types'

// Shared parameter editor used by Run Backtest, Tuning, and Optimize.
// Layout: Essentials card up front + counted accordions on the left, a live
// explainer panel on the right. Friendly labels/groups/descriptions come from the
// schema (overlaid from a strategy's companion meta.json). Blue = focus, and only
// focus; gold = section-title text. Degrades gracefully when a strategy carries no
// editor metadata (no core flags → no Essentials card, all groups as accordions).

export type ParamValue = number | boolean | string
export type AxisEdit =
  | { mode: 'range'; min: string; max: string; step: string }
  | { mode: 'fixed'; value: string }
export type ParamEditorMode = 'run' | 'tune' | 'optimize'

interface Props {
  schema: ParamSchemaEntry[]
  mode: ParamEditorMode
  /** Current values (run/tune); for optimize, the run's inherited values (for show_if + display). */
  values: Record<string, ParamValue>
  onChange?: (name: string, value: ParamValue) => void
  /** Tune only — original baseline values, shown as "was X" on changed rows. */
  baseline?: Record<string, unknown>
  /** Optimize only. */
  axes?: Record<string, AxisEdit>
  onToggleAxis?: (name: string) => void
  onUpdateAxis?: (name: string, field: 'min' | 'max' | 'step', value: string) => void
  intErrors?: Record<string, string>
  /** 'panel'  = explainer as a fixed right column (default, for wide modals);
   *  'inline' = explainer drops in under the focused row;
   *  'coach'  = no per-row explainer — the parent renders a pinned <ParamCoach> footer instead
   *             (for narrow rails like the tune dock, where the chart is the hero). */
  explainer?: 'panel' | 'inline' | 'coach'
  /** Fired whenever the focused param changes (incl. on mount) — lets a 'coach' parent
   *  render the teaching footer for the focused row. */
  onFocusChange?: (name: string) => void
}

type Widget = 'toggle' | 'switch' | 'time' | 'number' | 'text'

const labelOf = (p: ParamSchemaEntry) => p.label || p.display_name || p.name
const descOf = (p: ParamSchemaEntry) => p.desc || p.description || ''
const fmt = (v: unknown) => (v === true ? 'on' : v === false ? 'off' : String(v ?? ''))

function widgetOf(p: ParamSchemaEntry, value: ParamValue): Widget {
  if (p.widget) return p.widget
  if (p.type === 'bool') return p.options ? 'toggle' : 'switch'
  if (p.type === 'string') return /^\d{1,2}:\d{2}$/.test(String(value ?? '')) ? 'time' : 'text'
  return 'number'
}

function coerceInput(p: ParamSchemaEntry, raw: string, fallback: ParamValue): ParamValue {
  if (p.type === 'int') { const n = parseInt(raw, 10); return isNaN(n) ? fallback : n }
  if (p.type === 'double') { const n = parseFloat(raw); return isNaN(n) ? fallback : n }
  return raw
}

export function ParamEditor(props: Props) {
  const { schema, mode, values, axes } = props  // the rest are forwarded to Row via {...props}
  const explainer = props.explainer ?? 'panel'

  // strategy-logic params only — foundational config is injected, never user-edited here
  const params = useMemo(() => schema.filter(p => p.category !== 'foundational'), [schema])
  const valueOf = (name: string): ParamValue => {
    const p = params.find(x => x.name === name)
    return values[name] ?? (p?.default as ParamValue)
  }
  const visible = (p: ParamSchemaEntry) =>
    !p.show_if || Object.entries(p.show_if).every(([k, v]) => String(valueOf(k)) === String(v))

  const coreParams = params.filter(p => p.core && visible(p))
  const hasCore = coreParams.length > 0

  const [simple, setSimple] = useState(false)
  const [open, setOpen] = useState<Record<string, boolean>>({})
  const [focus, setFocus] = useState<string>(() => (params.find(p => p.core) ?? params[0])?.name ?? '')

  // Surface the focused param to a 'coach' parent (fires on mount + every focus change).
  const { onFocusChange } = props
  useEffect(() => { onFocusChange?.(focus) }, [focus, onFocusChange])

  // group order = first appearance among non-core params (schema is already ordered)
  const groups = useMemo(() => {
    const seen: string[] = []
    for (const p of params) {
      if (hasCore && p.core) continue
      const g = p.group || 'Parameters'
      if (!seen.includes(g)) seen.push(g)
    }
    return seen
  }, [params, hasCore])

  const focusP = params.find(p => p.name === focus)
  const focusGroup = focusP && !(hasCore && focusP.core) ? focusP.group : null
  const essActive = !!(focusP && hasCore && focusP.core)

  const toggleGroup = (g: string) => setOpen(s => ({ ...s, [g]: !s[g] }))

  const left = (
    <>
        {hasCore && (
          <div className={`flex items-center justify-end pt-3 pb-1 ${explainer === 'panel' ? 'sticky top-0 z-10 bg-bg-surface' : ''}`}>
            <div className="inline-flex bg-bg-sunken border border-border-subtle rounded-lg p-[3px]">
              {(['simple', 'expert'] as const).map(m => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setSimple(m === 'simple')}
                  className={`px-3 py-[5px] rounded-md text-[12px] font-semibold capitalize transition-colors ${
                    (simple ? 'simple' : 'expert') === m ? 'bg-accent text-bg-base' : 'text-text-tertiary hover:text-text-secondary'
                  }`}
                >
                  {m}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Essentials */}
        {hasCore && (
          <div className={`rounded-xl border border-l-[3px] px-3.5 pt-1 pb-2 mt-2 transition-colors ${
            essActive ? 'border-accent/40 border-l-accent bg-accent/5' : 'border-border-subtle border-l-transparent bg-bg-sunken/40'
          }`}>
            <div className={`text-[11px] font-bold uppercase tracking-wider flex items-center gap-2 pt-3 pb-1 ${essActive ? 'text-accent' : 'text-gold-text'}`}>
              <span>★ Essentials</span>
            </div>
            {coreParams.map(p => (
              <Row key={p.name} p={p} {...props} widget={widgetOf(p, valueOf(p.name))} focused={focus === p.name}
                   onFocus={() => setFocus(p.name)} valueOf={valueOf} star starActive={essActive} />
            ))}
          </div>
        )}

        {/* Accordions (or Simple-mode hint) */}
        {hasCore && simple ? (
          <p className="text-[11.5px] italic text-text-tertiary px-1 pt-3">
            Simple mode — {params.filter(p => !p.core && visible(p)).length} more setting(s) hidden. Switch to Expert to see them.
          </p>
        ) : (
          groups.map((g, gi) => {
            const rows = params.filter(p => p.group === g && (!hasCore || !p.core) && visible(p))
            if (!rows.length) return null
            const isOpen = open[g] ?? (!hasCore && gi === 0) // default-open first group when there's no Essentials card
            const active = g === focusGroup
            return (
              <div key={g} className={`rounded-xl border border-l-[3px] mt-2.5 overflow-hidden bg-bg-sunken/40 transition-colors ${
                active ? 'border-accent/40 border-l-accent' : 'border-border-subtle border-l-transparent'
              }`}>
                <button
                  type="button"
                  onClick={() => toggleGroup(g)}
                  className={`w-full flex items-center justify-between px-3.5 py-2.5 ${active ? 'bg-accent/5' : ''}`}
                >
                  <span className={`flex items-center gap-2 text-[12px] font-bold uppercase tracking-wider ${active ? 'text-accent' : 'text-gold-text'}`}>
                    {isOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                    {g}
                  </span>
                  <span className="text-[11px] text-text-tertiary font-medium">{rows.length} setting{rows.length > 1 ? 's' : ''}</span>
                </button>
                {isOpen && (
                  <div className="px-3.5 pb-2 border-t border-border-subtle">
                    {rows.map(p => (
                      <Row key={p.name} p={p} {...props} widget={widgetOf(p, valueOf(p.name))} focused={focus === p.name}
                           onFocus={() => setFocus(p.name)} valueOf={valueOf} />
                    ))}
                  </div>
                )}
              </div>
            )
          })
        )}
    </>
  )

  // Inline / coach mode: single column. Inline drops the explainer under the focused
  // row; coach leaves teaching to the parent's pinned <ParamCoach> footer. Either way the
  // parent frame (e.g. the tune dock) owns scrolling.
  if (explainer !== 'panel') {
    return <div className="px-1">{left}</div>
  }

  // Panel mode: controls on the left, a fixed explainer column on the right.
  return (
    <div className="grid grid-cols-[1fr_300px] rounded-xl border border-border-subtle overflow-hidden bg-bg-surface">
      <div className="px-4 pb-4 max-h-[62vh] overflow-y-auto">{left}</div>
      <div className="border-l border-border-subtle bg-bg-sunken/40">
        <div className="sticky top-0 p-4">
          {focusP ? <Explainer p={focusP} mode={mode} valueOf={valueOf} axes={axes} /> : <span className="text-text-tertiary text-[12px]">Select a parameter.</span>}
        </div>
      </div>
    </div>
  )
}

// ── one parameter row ─────────────────────────────────────────────────────────
function Row(props: Props & {
  p: ParamSchemaEntry; widget: Widget; focused: boolean; onFocus: () => void
  valueOf: (n: string) => ParamValue; star?: boolean; starActive?: boolean
}) {
  const { p, focused, onFocus, star, starActive } = props  // widget forwarded to Control via {...props}
  const showInline = props.explainer === 'inline' && focused
  return (
    <>
      <div
        onClick={onFocus}
        className={`flex items-center justify-between gap-3 px-2 -mx-2 py-2.5 rounded-lg border border-transparent cursor-pointer transition-colors ${
          focused ? 'bg-accent/10' : 'hover:bg-bg-hover'
        }`}
      >
        <div className="flex items-center gap-2 text-[13px] font-semibold text-text-primary min-w-0">
          {star && <span className={`text-[11px] ${starActive ? 'text-accent' : 'text-gold-text'}`}>★</span>}
          <span className="truncate">{labelOf(p)}</span>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0 flex-wrap justify-end">
          <Control {...props} />
        </div>
      </div>
      {showInline && (
        <div className="mb-2 rounded-lg border border-border-subtle border-l-[3px] border-l-accent bg-bg-sunken/60 px-3 py-2.5">
          <Explainer p={p} mode={props.mode} valueOf={props.valueOf} axes={props.axes} inline />
        </div>
      )}
    </>
  )
}

// ── the control (mode-aware) ────────────────────────────────────────────────
function Control(props: Props & { p: ParamSchemaEntry; widget: Widget; onFocus: () => void; valueOf: (n: string) => ParamValue }) {
  const { p, widget, mode, onChange, baseline, axes, onToggleAxis, onUpdateAxis, intErrors, onFocus, valueOf } = props
  const v = valueOf(p.name)

  if (mode === 'optimize') {
    // Only numeric params are sweepable; bools/strings/times are inherited from the run.
    if (widget !== 'number') {
      return <span className="text-[11.5px] text-text-tertiary italic"><span className="font-mono not-italic mr-2 text-text-secondary">{fmt(v)}</span>inherited · not swept</span>
    }
    const ax = axes?.[p.name]
    const swept = ax?.mode === 'range'
    const err = intErrors?.[p.name]
    return (
      <>
        <NumberBox value={swept ? '' : String(v)} disabled={swept} step={p.step} onFocus={onFocus} onInput={() => {}} unit={p.unit} dim={swept} readOnly />
        <button
          type="button"
          onClick={() => onToggleAxis?.(p.name)}
          className={`text-[11px] font-semibold rounded-md px-2.5 py-[6px] border transition-colors ${
            swept ? 'text-accent border-accent/40 bg-accent/10' : 'text-text-tertiary border-border-default bg-bg-sunken hover:text-text-secondary'
          }`}
        >
          {swept ? '✓ sweep' : '⤢ sweep'}
        </button>
        {swept && ax && (
          <div className="flex items-center gap-1.5 basis-full justify-end mt-1.5">
            {(['min', 'max', 'step'] as const).map(f => (
              <span key={f} className={`inline-flex items-center bg-bg-sunken border rounded-md ${err ? 'border-neg-text/60' : 'border-border-default'}`}>
                <label className="text-[10px] text-text-tertiary pl-2 pr-1">{f === 'min' ? 'from' : f === 'max' ? 'to' : 'step'}</label>
                <input
                  value={ax[f]}
                  onChange={e => onUpdateAxis?.(p.name, f, e.target.value)}
                  onFocus={onFocus}
                  className="w-12 bg-transparent py-[6px] pr-2 text-[12px] font-mono tabular-nums text-text-primary outline-none"
                />
              </span>
            ))}
          </div>
        )}
        {swept && err && <span className="basis-full text-right text-[11px] text-neg-text">{err}</span>}
      </>
    )
  }

  // run / tune
  // Only show "was X" when the baseline actually carries this param AND it changed.
  // (A baseline run from before a param existed lacks the key — don't render a blank "was".)
  const hasBase = !!baseline && Object.prototype.hasOwnProperty.call(baseline, p.name)
  const tuneTag = mode === 'tune' && hasBase && String(v) !== String(baseline![p.name])
    ? <span className="text-[10.5px] text-text-tertiary">was <b className="text-gold-text font-mono">{fmt(baseline![p.name])}</b></span>
    : null

  if (widget === 'toggle') {
    const on = v === true
    return (
      <>
        <div className="inline-flex bg-bg-sunken border border-border-default rounded-lg p-[3px] w-[240px]">
          {([false, true] as const).map(state => (
            <button
              key={String(state)}
              type="button"
              onClick={() => { onFocus(); onChange?.(p.name, state) }}
              className={`flex-1 flex items-center justify-center gap-1.5 text-[12px] font-semibold py-[6px] rounded-md transition-colors ${
                on === state ? 'bg-accent text-bg-base' : 'text-text-tertiary hover:text-text-secondary'
              }`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${on === state ? 'bg-bg-base' : 'bg-text-tertiary/50'}`} />
              {state ? p.options?.on : p.options?.off}
            </button>
          ))}
        </div>
        {tuneTag}
      </>
    )
  }

  if (widget === 'switch') {
    const on = v === true
    return (
      <>
        <button type="button" onClick={() => { onFocus(); onChange?.(p.name, !on) }} className="inline-flex items-center gap-2.5">
          <span className={`w-10 h-[23px] rounded-full relative transition-colors ${on ? 'bg-accent' : 'bg-border-default'}`}>
            <span className={`absolute top-[3px] w-[17px] h-[17px] rounded-full transition-all ${on ? 'left-[20px] bg-bg-base' : 'left-[3px] bg-text-secondary'}`} />
          </span>
          <span className="text-[12px] font-semibold text-text-secondary">{on ? 'On' : 'Off'}</span>
        </button>
        {tuneTag}
      </>
    )
  }

  // number / time / text
  return (
    <>
      <NumberBox
        value={String(v)}
        text={widget !== 'number'}
        step={p.step}
        unit={p.unit}
        onFocus={onFocus}
        onInput={raw => onChange?.(p.name, coerceInput(p, raw, v))}
      />
      {tuneTag}
    </>
  )
}

function NumberBox(props: {
  value: string; text?: boolean; disabled?: boolean; readOnly?: boolean; dim?: boolean
  step?: number; unit?: string; onFocus: () => void; onInput: (raw: string) => void
}) {
  const { value, text, disabled, readOnly, dim, step, unit, onFocus, onInput } = props
  return (
    <span className={`inline-flex items-center bg-bg-sunken border border-border-default rounded-lg overflow-hidden w-[170px] ${dim ? 'opacity-40' : ''}`}>
      <input
        type={text ? 'text' : 'number'}
        step={text ? undefined : (step ?? 'any')}
        value={value}
        disabled={disabled}
        readOnly={readOnly}
        onFocus={onFocus}
        onChange={e => onInput(e.target.value)}
        className="flex-1 w-full min-w-0 bg-transparent px-2.5 py-2 text-[13px] font-mono tabular-nums text-text-primary outline-none"
      />
      {unit && <span className="text-[11px] text-text-tertiary px-2.5 self-stretch flex items-center border-l border-border-subtle">{unit}</span>}
    </span>
  )
}

// ── explainer panel ───────────────────────────────────────────────────────────
function Explainer({ p, mode, valueOf, axes, inline }: {
  p: ParamSchemaEntry; mode: ParamEditorMode; valueOf: (n: string) => ParamValue; axes?: Record<string, AxisEdit>; inline?: boolean
}) {
  const v = valueOf(p.name)
  const widget = widgetOf(p, v)
  const ax = axes?.[p.name]
  const swept = mode === 'optimize' && ax?.mode === 'range'

  return (
    <div>
      {/* inline mode skips the eyebrow + big title — the focused row already names it */}
      {!inline && <div className="text-[11px] uppercase tracking-wider text-text-tertiary mb-2">Now editing</div>}
      {!inline && <h3 className="text-[17px] font-semibold mb-2 text-text-primary">{labelOf(p)}</h3>}
      {!inline && p.unit && <span className="inline-block text-[10px] font-bold uppercase tracking-wide text-accent bg-accent/15 border border-accent/40 rounded px-1.5 py-[2px] mb-2.5">{p.unit}</span>}
      {descOf(p) && <p className={`text-text-secondary ${inline ? 'text-[12px] mb-2.5' : 'text-[12.5px] mb-3.5'}`}>{descOf(p)}</p>}

      {swept && ax ? (
        <>
          <KV k="Sweeping" v={`${ax.min} → ${ax.max} / ${ax.step}`} />
          <KV k="Values" v={String(sweepCount(ax))} />
        </>
      ) : (
        <>
          <KV k="Current" v={fmt(v)} />
          <KV k="Default" v={fmt(p.default)} />
          {mode === 'optimize' && widget === 'number' && <KV k="In optimizer" v="held fixed" />}
        </>
      )}

      {widget === 'toggle' && p.options && (
        <div className="mt-1.5">
          {([false, true] as const).map(state => (
            <div key={String(state)} className={`flex items-start gap-2.5 py-2 text-[12px] ${v === state ? 'text-text-primary' : 'text-text-secondary'}`}>
              <span className={`w-2 h-2 rounded-full mt-[5px] flex-shrink-0 ${v === state ? 'bg-accent' : 'bg-text-tertiary/40'}`} />
              <b>{state ? p.options?.on : p.options?.off}</b>
            </div>
          ))}
        </div>
      )}

      {widget === 'number' && p.guide && (
        <div className="flex gap-2 mt-3.5">
          <GuideBox arrow="↓ Lower" text={p.guide[0]} />
          <GuideBox arrow="↑ Higher" text={p.guide[1]} />
        </div>
      )}
    </div>
  )
}

const KV = ({ k, v }: { k: string; v: string }) => (
  <div className="flex justify-between text-[12px] py-2 border-t border-border-subtle">
    <span className="text-text-tertiary">{k}</span>
    <span className="text-text-primary font-mono tabular-nums font-semibold">{v}</span>
  </div>
)
const GuideBox = ({ arrow, text }: { arrow: string; text: string }) => (
  <div className="flex-1 bg-bg-sunken border border-border-subtle rounded-lg p-2.5 text-[11.5px] text-text-secondary">
    <b className="text-accent block mb-1">{arrow}</b>{text}
  </div>
)

function sweepCount(ax: { min: string; max: string; step: string }): number {
  const lo = parseFloat(ax.min), hi = parseFloat(ax.max), st = parseFloat(ax.step)
  if (isNaN(lo) || isNaN(hi) || isNaN(st) || st <= 0 || lo > hi) return 0
  return Math.floor((hi - lo) / st + 1e-9) + 1
}

// ── Pinned coach footer ─────────────────────────────────────────────────────
// Always-on teaching strip for the focused param, rendered by the parent (the tune
// dock) at the bottom of the panel — so the rows above never shift as focus moves.
// Pair with <ParamEditor explainer="coach" onFocusChange={...} />.
export function ParamCoach({ schema, values, focusName }: {
  schema: ParamSchemaEntry[]
  values: Record<string, ParamValue>
  focusName: string | null
}) {
  const params = useMemo(() => schema.filter(p => p.category !== 'foundational'), [schema])
  const p = params.find(x => x.name === focusName)
  if (!p) {
    return <p className="text-[11.5px] italic text-text-tertiary">Select a parameter to see guidance.</p>
  }
  const v = values[p.name] ?? (p.default as ParamValue)
  const widget = widgetOf(p, v)
  const changed = p.default !== undefined && String(v) !== String(p.default)

  return (
    <div>
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <span className="text-[11px] font-bold uppercase tracking-wider text-accent flex items-center gap-1.5 min-w-0">
          <ChevronRight size={12} className="flex-shrink-0" />
          <span className="truncate">{labelOf(p)}</span>
        </span>
        <span className="text-[11px] text-text-tertiary flex-shrink-0">
          now <b className="text-text-primary font-mono">{fmt(v)}</b>
          {changed && <span className="text-text-tertiary"> · default <span className="font-mono">{fmt(p.default)}</span></span>}
        </span>
      </div>

      {descOf(p) && <p className="text-[12px] text-text-secondary leading-snug mb-2">{descOf(p)}</p>}

      {widget === 'number' && p.guide && (
        <div className="flex gap-2">
          <GuideBox arrow="↓ Lower" text={p.guide[0]} />
          <GuideBox arrow="↑ Higher" text={p.guide[1]} />
        </div>
      )}

      {widget === 'toggle' && p.options && (
        <div className="flex gap-2">
          {([false, true] as const).map(state => (
            <div
              key={String(state)}
              className={`flex-1 rounded-lg border px-2.5 py-1.5 text-[11.5px] ${
                v === state ? 'border-accent/40 bg-accent/10 text-text-primary' : 'border-border-subtle bg-bg-sunken text-text-secondary'
              }`}
            >
              <span className="flex items-center gap-1.5">
                <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${v === state ? 'bg-accent' : 'bg-text-tertiary/40'}`} />
                <b>{state ? p.options?.on : p.options?.off}</b>
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
