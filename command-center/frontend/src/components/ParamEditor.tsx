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
  | { mode: 'list'; values: string[] }
export type ParamEditorMode = 'run' | 'tune' | 'optimize'

// ── conditions and value resolution ───────────────────────────────────────────
// Three schema keys read one another's VALUES: `show_if`, `disable_if` and `custom_from`. They
// all go through the helpers below so the comparison rule (stringified, "any of these" as an
// array) exists once. `backend/services/stress_tester.py::param_is_reachable` mirrors it — a
// param the editor would grey out must not be perturbed by sensitivity either, or the lab books
// a guaranteed 0% change and reports it as "rock solid".

/**
 * `null` unless the value is a NUMBER or a string that is one. Booleans are deliberately excluded
 * — `Number(false)` is 0, so a numeric param sitting at 0 would satisfy a `{flag: false}` gate.
 */
function numeric(v: unknown): number | null {
  if (typeof v === 'boolean') return null
  if (typeof v === 'number') return Number.isFinite(v) ? v : null
  if (typeof v === 'string' && v.trim() !== '') {
    const n = Number(v)
    return Number.isFinite(n) ? n : null
  }
  return null
}

/**
 * 🔴 NUMBERS COMPARE AS NUMBERS, and it is not a nicety.
 *
 * A fib level is the string `"1.0"` in a dropdown and the number `1.0` in the Custom box, and
 * `String(1.0)` is `"1"` — so a stringified compare says a Custom level of 1.0 is not 1.0. That
 * left `exec_sl_deep` live in exactly the configuration it exists to be dead in, caught by
 * `param-gates.spec.ts` rather than by review. Python's `str(1.0)` is `"1.0"`, so the backend
 * mirror happened to be RIGHT while this side was wrong — two evaluators of one rule disagreeing
 * silently, which is why both got this function.
 *
 * Everything else (an enum, a bool, a time) falls back to the stringified compare, which is what
 * `show_if` has always used and why `1` and `"1"` match.
 */
function sameValue(actual: ParamValue, want: string | number | boolean): boolean {
  const a = numeric(actual)
  const b = numeric(want)
  if (a !== null && b !== null) return a === b
  return String(actual) === String(want)
}

/**
 * 🔴 SETTLED = `hidden` AND still on its default. Both halves, always.
 *
 * The field stays in the strategy and keeps being sent, so hiding one that has been MOVED would
 * put a value on the run that no reader can see — a page unable to show what it is about to
 * submit. Away from its default a settled param comes back on its own, on every surface.
 *
 * ⚠ Exported because three separate surfaces ask this question — the editor (Run / Tune /
 * Optimize), the strategy page, and the finished-run params panel — and a second copy of the
 * `&&` is how one of them starts hiding a moved param. `stress_tester._is_settled` is the fourth
 * evaluator, on the python side, and it mirrors this deliberately.
 */
export function isSettled(p: ParamSchemaEntry, value: ParamValue | undefined): boolean {
  if (!p.hidden || p.default === undefined) return false
  if (value === undefined) return true // never sent ⇒ it is at whatever the default is
  return sameValue(value, p.default as ParamValue)
}

/** Every condition must hold. Shared by `show_if` (to show) and `disable_if` (to disable). */
function condHolds(
  cond: Record<string, string | number | boolean | Array<string | number | boolean>> | undefined,
  read: (name: string) => ParamValue
): boolean {
  if (!cond) return false
  return Object.entries(cond).every(([k, want]) => {
    const actual = read(k)
    return Array.isArray(want) ? want.some((x) => sameValue(actual, x)) : sameValue(actual, want)
  })
}

/** Reads values with `custom_from` resolved — the number a param is ACTUALLY worth right now. */
function readerFor(schema: ParamSchemaEntry[], values: Record<string, ParamValue>) {
  const raw = (name: string): ParamValue => {
    const p = schema.find((x) => x.name === name)
    return values[name] ?? (p?.default as ParamValue)
  }
  // `visible` and `read` are mutually recursive through custom_from → show_if. The recursion
  // terminates because a sibling's show_if names the PARENT dropdown, and a dropdown that is
  // its own custom_from would be a schema error, not a loop we should tolerate silently.
  const visible = (p: ParamSchemaEntry): boolean => !p.show_if || condHolds(p.show_if, raw)
  const read = (name: string): ParamValue => {
    const p = schema.find((x) => x.name === name)
    if (p?.custom_from && p.custom_from !== name) {
      const sib = schema.find((x) => x.name === p.custom_from)
      // The sibling is visible exactly when its typed value is the one in force.
      if (sib && visible(sib)) return raw(p.custom_from)
    }
    return raw(name)
  }
  return { raw, visible, read }
}

/** True when the param still exists but cannot change anything — see `disable_if` in types. */
export function isInert(
  p: ParamSchemaEntry,
  schema: ParamSchemaEntry[],
  values: Record<string, ParamValue>
): boolean {
  return condHolds(p.disable_if, readerFor(schema, values).read)
}

// `{param_name}` in an option label → that param's current (custom-resolved) value. An unknown
// name is left ON SCREEN as `{typo}` rather than blanked: a label that silently loses half its
// sentence is the failure this whole mechanism exists to stop.
const TOKEN = /\{([A-Za-z_][A-Za-z0-9_]*)\}/g

/**
 * A copy of `schema` with every option-label token filled from `values`.
 *
 * Done to the SCHEMA rather than at each render site because option labels are read in five
 * places (the toggle, both explainers, the optimizer's list-sweep chips, and `sweepChoices`),
 * and a token surviving into any one of them shows a reader `{exec_sl_level}`.
 */
export function fillTokens(
  schema: ParamSchemaEntry[],
  values: Record<string, ParamValue>
): ParamSchemaEntry[] {
  if (!schema.some((p) => p.options && /\{/.test(p.options.off + p.options.on))) return schema
  const { read } = readerFor(schema, values)
  const sub = (text: string) =>
    text.replace(TOKEN, (whole, name) =>
      schema.some((x) => x.name === name) ? String(read(name)) : whole
    )
  return schema.map((p) =>
    p.options && /\{/.test(p.options.off + p.options.on)
      ? { ...p, options: { off: sub(p.options.off), on: sub(p.options.on) } }
      : p
  )
}

// The values a NON-numeric param can be swept across. A number takes a from/to/step range; a
// dropdown already carries its own closed set and a bool has exactly two states, so those are
// swept as a LIST instead. Anything else (free text, a time) has no set to walk and stays fixed.
// Values are the raw strings the optimizer will receive — the caller coerces a bool back before it
// ships, because "false" as a string is truthy everywhere it lands.
export function sweepChoices(p: ParamSchemaEntry): { value: string; label: string }[] {
  if (p.choices?.length) return p.choices.map((c) => ({ value: c, label: c }))
  if (p.type === 'bool')
    return [
      { value: 'false', label: String(p.options?.off ?? 'Off') },
      { value: 'true', label: String(p.options?.on ?? 'On') },
    ]
  return []
}

/**
 * The params the editor WOULD render, tokens filled — foundational dropped, `show_if` applied,
 * settled ones gone unless moved.
 *
 * ⚠ Exported so the read-only summary and the editor cannot disagree about what a strategy's
 * settings ARE. A summary listing a row the editor does not offer (or missing one it does) is
 * worse than no summary: the reader opens the editor to change something the summary promised.
 */
export function visibleParams(
  schema: ParamSchemaEntry[],
  values: Record<string, ParamValue>
): ParamSchemaEntry[] {
  const filled = fillTokens(schema, values)
  const { raw } = readerFor(filled, values)
  return filled.filter(
    (p) =>
      p.category !== 'foundational' &&
      (!p.show_if || condHolds(p.show_if, raw)) &&
      !isSettled(p, raw(p.name))
  )
}

/** True when this param is not sitting on the strategy's own default. */
export function isChanged(p: ParamSchemaEntry, v: ParamValue | undefined): boolean {
  if (p.default === undefined || v === undefined) return false
  return !sameValue(v, p.default as ParamValue)
}

/**
 * 🔴 ONE VIEW: SCAN EVERY SETTING AND EDIT ANY OF THEM IN PLACE (2026-08-15).
 *
 * The first attempt at Aaron's *"show me the settings, and only if I want to change one do I go
 * into the parameters"* was a READ-ONLY summary with an Edit button that swapped in the stacked
 * editor. He rejected it, and the reason is the part worth keeping: **a read-only view and an
 * edit view of one thing is one view too many.** It also left the Essentials card meaningless —
 * a curation of "the important ones" only earns its place when the rest are hidden behind
 * accordions, and it DUPLICATED those params, so the same setting appeared twice.
 *
 * So: every setting, grouped, two to a row, each one editable where it sits. ~30px a row against
 * the stacked editor's ~60px, and no mode to be in.
 *
 * ⚠ **No Essentials card and no Simple/Expert switch in this layout.** Every param appears
 * exactly once, under the group it belongs to.
 * ⚠ **Every control is the SAME WIDTH on the right edge**, so the labels form one column and the
 * values another — which is what makes 30 settings scannable rather than a wall.
 * ⚠ It shares `visible` / `settled` / `inert` with the stacked layout, so the two cannot disagree
 * about which rows exist.
 */
function CompactRow(
  props: Props & {
    p: ParamSchemaEntry
    valueOf: (n: string) => ParamValue
    inert: boolean
  }
) {
  const { p, valueOf, inert, onChange, mode, baseline } = props
  const v = valueOf(p.name)
  const changed = isChanged(p, props.values[p.name])
  const tuned =
    mode === 'tune' &&
    baseline &&
    Object.prototype.hasOwnProperty.call(baseline, p.name) &&
    String(v) !== String(baseline[p.name])

  const set = (next: ParamValue) => onChange?.(p.name, next)
  const ctlBase =
    'w-[190px] flex-shrink-0 h-[26px] rounded-md border bg-bg-sunken px-2 text-[12px] font-mono ' +
    'focus:outline-none focus:border-accent transition-colors ' +
    (changed ? 'border-accent/50 text-accent' : 'border-border-subtle text-text-secondary')

  let control
  if (p.choices?.length) {
    control = (
      <select
        value={String(v ?? '')}
        disabled={inert}
        onChange={(e) => set(e.target.value)}
        className={ctlBase}
      >
        {p.choices.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>
    )
  } else if (p.type === 'bool') {
    // A SELECT rather than the stacked layout's segmented toggle: at 168px a two-button toggle
    // truncates labels like `Structure + % ratchet`, and a truncated state label is the one thing
    // this row cannot afford to get wrong.
    control = (
      <select
        value={v === true || v === 'true' ? 'true' : 'false'}
        disabled={inert}
        onChange={(e) => set(e.target.value === 'true')}
        className={ctlBase}
      >
        <option value="false">{String(p.options?.off ?? 'Off')}</option>
        <option value="true">{String(p.options?.on ?? 'On')}</option>
      </select>
    )
  } else if (p.type === 'int' || p.type === 'double') {
    control = (
      <div className="relative w-[190px] flex-shrink-0">
        <input
          type="number"
          step={p.step ?? 'any'}
          min={p.min ?? undefined}
          max={p.max ?? undefined}
          disabled={inert}
          value={String(v ?? '')}
          onChange={(e) => set(coerceInput(p, e.target.value, v))}
          className={`${ctlBase} w-full ${p.unit ? 'pr-[52px]' : ''} invalid:text-neg-text`}
        />
        {p.unit && (
          <span className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] text-text-tertiary pointer-events-none">
            {p.unit}
          </span>
        )}
      </div>
    )
  } else {
    control = (
      <input
        type="text"
        disabled={inert}
        value={String(v ?? '')}
        onChange={(e) => set(e.target.value)}
        className={ctlBase}
      />
    )
  }

  return (
    <div
      data-testid={`param-row-${p.name}`}
      className={`flex items-center gap-3 py-[3px] pl-2 pr-1 rounded border-l-2 min-w-0 hover:bg-bg-hover/60 ${
        changed ? 'border-l-accent/60' : 'border-l-transparent'
      } ${inert ? 'opacity-50' : ''}`}
      title={inert ? p.disable_note : p.description}
    >
      <span className="flex-1 min-w-0 truncate text-[12px] text-text-secondary">
        {labelOf(p)}
        {tuned && baseline && (
          <span className="text-[10px] text-text-tertiary ml-1.5">
            was <b className="text-gold-text font-mono">{fmt(baseline[p.name])}</b>
          </span>
        )}
      </span>
      {control}
    </div>
  )
}

interface Props {
  schema: ParamSchemaEntry[]
  mode: ParamEditorMode
  /** Current values (run/tune); for optimize, the run's inherited values (for show_if + display). */
  values: Record<string, ParamValue>
  onChange?: (name: string, value: ParamValue) => void
  /**
   * `compact` = one dense scannable grid, every row editable in place, no Essentials card and no
   * explainer column. See `CompactRow` for why the read-only-view-plus-Edit-button shape it
   * replaced was wrong. Unset = the stacked layout.
   */
  layout?: 'stacked' | 'compact'
  /** Tune only — original baseline values, shown as "was X" on changed rows. */
  baseline?: Record<string, unknown>
  /** Optimize only. */
  axes?: Record<string, AxisEdit>
  onToggleAxis?: (name: string) => void
  onUpdateAxis?: (name: string, field: 'min' | 'max' | 'step', value: string) => void
  intErrors?: Record<string, string>
  /** Optimize only — let a dropdown / on-off param be swept as a value LIST. Python-runner
   *  strategies only: NT8 and MT5 hand a Start/Step/End range to their own tester, so there is
   *  nowhere for a set of strings to go. Off = those rows stay read-only, as before. */
  allowListSweep?: boolean
  onToggleListValue?: (name: string, value: string) => void
  /** 'panel'  = explainer as a fixed right column (default, for wide modals);
   *  'inline' = explainer drops in under the focused row;
   *  'coach'  = no per-row explainer — the parent renders a pinned <ParamCoach> footer instead
   *             (for narrow rails like the tune dock, where the chart is the hero). */
  explainer?: 'panel' | 'inline' | 'coach'
  /** Fired whenever the focused param changes (incl. on mount) — lets a 'coach' parent
   *  render the teaching footer for the focused row. */
  onFocusChange?: (name: string) => void
}

type Widget = 'toggle' | 'switch' | 'time' | 'number' | 'text' | 'select'

const labelOf = (p: ParamSchemaEntry) => p.label || p.display_name || p.name
// Rows are STACKED: the label (plus any tune "was X" tag) owns one line, the control owns the
// next. Side-by-side put the label in whatever width the fixed-width control left over, so in a
// narrow rail every label truncated to "Arm on di..." and a "was on" tag cropped it further —
// unreadable exactly where the editing happens.
// Every control fills the row (one shared width across toggle/select/number/switch, so the list
// has a single straight edge), capped so a wide Run/Optimize modal doesn't stretch a toggle
// across half the screen. Fixed height keeps a row's height independent of its label.
const CONTROL_W = 'w-full max-w-[420px]'
const CONTROL_H = 'h-[34px]'

const descOf = (p: ParamSchemaEntry) => p.desc || p.description || ''
const fmt = (v: unknown) => (v === true ? 'on' : v === false ? 'off' : String(v ?? ''))

function widgetOf(p: ParamSchemaEntry, value: ParamValue): Widget {
  // `choices` wins over an explicit widget: a param with a closed set of legal values must never
  // be a free-text box. Several strategies read enums by exact string match and fall back to a
  // silent no-op on anything unrecognised, so a typo would disable a filter without saying so.
  if (p.choices?.length) return 'select'
  if (p.widget) return p.widget
  if (p.type === 'bool') return p.options ? 'toggle' : 'switch'
  if (p.type === 'string') return /^\d{1,2}:\d{2}$/.test(String(value ?? '')) ? 'time' : 'text'
  return 'number'
}

function coerceInput(p: ParamSchemaEntry, raw: string, fallback: ParamValue): ParamValue {
  if (p.type === 'int') {
    const n = parseInt(raw, 10)
    return isNaN(n) ? fallback : n
  }
  if (p.type === 'double') {
    const n = parseFloat(raw)
    return isNaN(n) ? fallback : n
  }
  return raw
}

export function ParamEditor(props: Props) {
  const { schema, mode, values, axes } = props // the rest are forwarded to Row via {...props}
  const explainer = props.explainer ?? 'panel'

  // strategy-logic params only — foundational config is injected, never user-edited here.
  // Option-label tokens are filled HERE, once, so every render site below sees plain strings.
  const params = useMemo(
    () => fillTokens(schema, values).filter((p) => p.category !== 'foundational'),
    [schema, values]
  )
  const valueOf = (name: string): ParamValue => {
    const p = params.find((x) => x.name === name)
    return values[name] ?? (p?.default as ParamValue)
  }
  // `show_if: {param: value}` shows the row only when that param equals the value. An ARRAY of
  // values means "any of these" — needed by any enum whose OFF state is one option and whose ON
  // states are several (e.g. a minimum-stop mode of Off / % of price / Fixed $ / x ATR). Without
  // it the dependent row could only be tied to one of the ON values and would stay hidden for
  // the others, which reads as a missing setting rather than a conditional one.
  // 🔴 A `hidden` param is off the screen ONLY while it sits at its default.
  //
  // The field is still in the config and still sent, so hiding one that has been MOVED would put
  // a value on the run that no reader could see — a page that cannot show what it is about to
  // submit, which is the exact defect this lab keeps re-finding. Away from its default it comes
  // back on its own.
  const settled = (p: ParamSchemaEntry) => isSettled(p, valueOf(p.name))
  const settledCount = params.filter(settled).length
  const visible = (p: ParamSchemaEntry) =>
    (!p.show_if || condHolds(p.show_if, valueOf)) && !settled(p)
  // ⚠ `disable_if` is the OPPOSITE polarity — a row that holds it is shown and greyed, not
  // hidden. Read via `isInert` so the `custom_from` resolution is the same one the labels use:
  // a dropdown set to Custom = 1.0 must disable exactly what its own 1.0 disables.
  const inert = (p: ParamSchemaEntry) => isInert(p, params, values)

  const coreParams = params.filter((p) => p.core && visible(p))
  const hasCore = coreParams.length > 0

  const [simple, setSimple] = useState(false)
  const [open, setOpen] = useState<Record<string, boolean>>({})
  // ⚠ The opening focus must be a param that is actually RENDERED. Picking the first `core` one
  // off the raw list opened the explainer on `exec_arm_div` — a SETTLED param with no row on
  // screen — so the panel described a setting the reader could not find.
  const [focus, setFocus] = useState<string>(
    () => (params.find((p) => p.core && visible(p)) ?? params.find(visible))?.name ?? ''
  )

  // Surface the focused param to a 'coach' parent (fires on mount + every focus change).
  const { onFocusChange } = props
  useEffect(() => {
    onFocusChange?.(focus)
  }, [focus, onFocusChange])

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

  const focusP = params.find((p) => p.name === focus)
  const focusGroup = focusP && !(hasCore && focusP.core) ? focusP.group : null
  const essActive = !!(focusP && hasCore && focusP.core)

  const toggleGroup = (g: string) => setOpen((s) => ({ ...s, [g]: !s[g] }))

  // ── compact layout state ─────────────────────────────────────────────────
  // ⚠ Groups start OPEN and the state tracks what is COLLAPSED, not what is open. The whole
  // point of this layout is reading every setting at once; a map of what is open defaults every
  // group to shut the first time it renders, which is the opposite.
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})
  const toggleGroup2 = (g: string) => setCollapsed((s) => ({ ...s, [g]: !s[g] }))
  // Group order is first appearance in the schema, which is the canonical UI order the meta sets.
  // ⚠ Built from the EXPORTED `visibleParams`, not from a second `params.filter(visible)`. The
  // Run modal counts changed settings with that same function, and a private copy here is how the
  // count comes to name a row this grid does not render.
  const compactGroups = useMemo(() => {
    const out: { name: string; rows: ParamSchemaEntry[] }[] = []
    for (const p of visibleParams(schema, values)) {
      const g = p.group || 'Settings'
      const found = out.find((x) => x.name === g)
      if (found) found.rows.push(p)
      else out.push({ name: g, rows: [p] })
    }
    return out
  }, [schema, values])

  const left = (
    <>
      {hasCore && (
        <div
          className={`flex items-center justify-end pt-3 pb-1 ${explainer === 'panel' ? 'sticky top-0 z-10 bg-bg-surface' : ''}`}
        >
          <div className="inline-flex bg-bg-sunken border border-border-subtle rounded-lg p-[3px]">
            {(['simple', 'expert'] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setSimple(m === 'simple')}
                className={`px-3 py-[5px] rounded-md text-[12px] font-semibold capitalize transition-colors ${
                  (simple ? 'simple' : 'expert') === m
                    ? 'bg-accent text-bg-base'
                    : 'text-text-tertiary hover:text-text-secondary'
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
        <div
          className={`rounded-xl border border-l-[3px] px-3.5 pt-1 pb-2 mt-2 transition-colors ${
            essActive
              ? 'border-accent/40 border-l-accent bg-accent/5'
              : 'border-border-subtle border-l-transparent bg-bg-sunken/40'
          }`}
        >
          <div
            className={`text-[11px] font-bold uppercase tracking-wider flex items-center gap-2 pt-3 pb-1 ${essActive ? 'text-accent' : 'text-gold-text'}`}
          >
            <span>★ Essentials</span>
          </div>
          {coreParams.map((p) => (
            <Row
              key={p.name}
              p={p}
              {...props}
              widget={widgetOf(p, valueOf(p.name))}
              focused={focus === p.name}
              onFocus={() => setFocus(p.name)}
              valueOf={valueOf}
              inert={inert(p)}
              star
              starActive={essActive}
            />
          ))}
        </div>
      )}

      {/* Accordions (or Simple-mode hint) */}
      {hasCore && simple ? (
        <p className="text-[11.5px] italic text-text-tertiary px-1 pt-3">
          Simple mode — {params.filter((p) => !p.core && visible(p)).length} more setting(s) hidden.
          Switch to Expert to see them.
        </p>
      ) : (
        groups.map((g, gi) => {
          const rows = params.filter((p) => p.group === g && (!hasCore || !p.core) && visible(p))
          if (!rows.length) return null
          const isOpen = open[g] ?? (!hasCore && gi === 0) // default-open first group when there's no Essentials card
          const active = g === focusGroup
          return (
            <div
              key={g}
              className={`rounded-xl border border-l-[3px] mt-2.5 overflow-hidden bg-bg-sunken/40 transition-colors ${
                active
                  ? 'border-accent/40 border-l-accent'
                  : 'border-border-subtle border-l-transparent'
              }`}
            >
              <button
                type="button"
                onClick={() => toggleGroup(g)}
                className={`w-full flex items-center justify-between px-3.5 py-2.5 ${active ? 'bg-accent/5' : ''}`}
              >
                <span
                  className={`flex items-center gap-2 text-[12px] font-bold uppercase tracking-wider ${active ? 'text-accent' : 'text-gold-text'}`}
                >
                  {isOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                  {g}
                </span>
                <span className="text-[11px] text-text-tertiary font-medium">
                  {rows.length} setting{rows.length > 1 ? 's' : ''}
                </span>
              </button>
              {isOpen && (
                <div className="px-3.5 pb-2 border-t border-border-subtle">
                  {rows.map((p) => (
                    <Row
                      key={p.name}
                      p={p}
                      {...props}
                      widget={widgetOf(p, valueOf(p.name))}
                      focused={focus === p.name}
                      onFocus={() => setFocus(p.name)}
                      valueOf={valueOf}
                      inert={inert(p)}
                    />
                  ))}
                </div>
              )}
            </div>
          )
        })
      )}

      {/* ⚠ The count is SAID OUT LOUD rather than left implicit. A settled param is still in the
          strategy and still being sent, so an editor that simply showed fewer rows would read as
          a strategy with fewer settings — and the next reader would go looking in the code for a
          lever the page had quietly stopped mentioning. */}
      {settledCount > 0 && (
        <p
          data-testid="param-settled-count"
          className="text-[11px] text-text-tertiary italic px-1 pt-3 leading-snug"
        >
          {settledCount} settled setting{settledCount > 1 ? 's' : ''} hidden — still in the
          strategy, still sent at {settledCount > 1 ? 'their defaults' : 'its default'}. Any one
          moved off its default reappears here.
        </p>
      )}
    </>
  )

  // ── Compact: scan everything, edit anything, no modes ─────────────────────
  // Rendered instead of `left` entirely — no Essentials, no Simple/Expert, no explainer column.
  // See `CompactRow` for why the read-only-plus-Edit shape it replaced was wrong.
  if (props.layout === 'compact') {
    return (
      <div data-testid="param-compact">
        {compactGroups.map((g) => (
          <div key={g.name} className="mb-3 last:mb-0">
            <button
              type="button"
              onClick={() => toggleGroup2(g.name)}
              aria-expanded={!collapsed[g.name]}
              className="flex items-center gap-1 w-full text-[10px] font-bold uppercase tracking-[0.7px] text-gold-text/80 hover:text-gold-text transition-colors mb-1"
            >
              {collapsed[g.name] ? <ChevronRight size={10} /> : <ChevronDown size={10} />}
              {g.name}
              <span className="normal-case tracking-normal font-normal text-[10px] text-text-tertiary/70">
                · {g.rows.length}
              </span>
            </button>
            {!collapsed[g.name] && (
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-x-6 gap-y-0">
                {g.rows.map((p) => (
                  <CompactRow key={p.name} p={p} {...props} valueOf={valueOf} inert={inert(p)} />
                ))}
              </div>
            )}
          </div>
        ))}
        {settledCount > 0 && (
          <p
            data-testid="param-settled-count"
            className="text-[10.5px] text-text-tertiary italic pt-2 leading-snug"
          >
            {settledCount} settled setting{settledCount > 1 ? 's' : ''} hidden — still in the
            strategy, still sent at {settledCount > 1 ? 'their defaults' : 'its default'}. Any one
            moved off its default reappears here.
          </p>
        )}
      </div>
    )
  }

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
          {focusP ? (
            <Explainer p={focusP} mode={mode} valueOf={valueOf} axes={axes} inert={inert(focusP)} />
          ) : (
            <span className="text-text-tertiary text-[12px]">Select a parameter.</span>
          )}
        </div>
      </div>
    </div>
  )
}

// ── one parameter row ─────────────────────────────────────────────────────────
function Row(
  props: Props & {
    p: ParamSchemaEntry
    widget: Widget
    focused: boolean
    onFocus: () => void
    valueOf: (n: string) => ParamValue
    /** `disable_if` holds — the row is shown, greyed, and says why. Never hidden. */
    inert: boolean
    star?: boolean
    starActive?: boolean
  }
) {
  const { p, focused, onFocus, star, starActive, inert } = props // widget forwarded to Control via {...props}
  const showInline = props.explainer === 'inline' && focused
  return (
    <>
      <div
        onClick={onFocus}
        className={`px-2 -mx-2 py-2.5 rounded-lg border border-transparent cursor-pointer transition-colors ${
          focused ? 'bg-accent/10' : 'hover:bg-bg-hover'
        }`}
      >
        {/* line 1 — label (full row width, so it reads in full) + the tune "was X" tag */}
        <div className="flex items-baseline justify-between gap-2 mb-1.5">
          <span className="flex items-baseline gap-1.5 text-[13px] font-semibold text-text-primary min-w-0">
            {star && (
              <span
                className={`text-[11px] flex-shrink-0 ${starActive ? 'text-accent' : 'text-gold-text'}`}
              >
                ★
              </span>
            )}
            <span className="truncate" title={labelOf(p)}>
              {labelOf(p)}
            </span>
          </span>
          <TuneTag {...props} />
        </div>
        {/* line 2 — the control. Greyed but still READABLE when inert: the reader has to be able
            to see which state it is stuck in, which is the whole reason it is not hidden. */}
        <div
          className={`flex items-center gap-2 flex-wrap ${inert ? 'opacity-50' : ''}`}
          title={inert ? p.disable_note : undefined}
        >
          <Control {...props} />
        </div>
        {inert && p.disable_note && (
          <p
            data-testid={`param-inert-${p.name}`}
            className="text-[11px] italic text-text-tertiary mt-1.5 leading-snug"
          >
            {p.disable_note}
          </p>
        )}
      </div>
      {showInline && (
        <div className="mb-2 rounded-lg border border-border-subtle border-l-[3px] border-l-accent bg-bg-sunken/60 px-3 py-2.5">
          <Explainer
            p={p}
            mode={props.mode}
            valueOf={props.valueOf}
            axes={props.axes}
            inert={inert}
            inline
          />
        </div>
      )}
    </>
  )
}

// ── tune "was X" tag ─────────────────────────────────────────────────────────
// Lives on the LABEL line, not beside the control: appended to the control it stole width from
// an already-cramped row and pushed the label into an ellipsis.
// Only rendered when the baseline actually carries this param AND it changed. (A baseline run
// from before a param existed lacks the key — don't render a blank "was".)
function TuneTag(props: Props & { p: ParamSchemaEntry; valueOf: (n: string) => ParamValue }) {
  const { p, mode, baseline, valueOf } = props
  if (mode !== 'tune' || !baseline || !Object.prototype.hasOwnProperty.call(baseline, p.name))
    return null
  if (String(valueOf(p.name)) === String(baseline[p.name])) return null
  return (
    <span className="text-[10.5px] text-text-tertiary flex-shrink-0">
      was <b className="text-gold-text font-mono">{fmt(baseline[p.name])}</b>
    </span>
  )
}

// ── the control (mode-aware) ────────────────────────────────────────────────
function Control(
  props: Props & {
    p: ParamSchemaEntry
    widget: Widget
    onFocus: () => void
    valueOf: (n: string) => ParamValue
    inert?: boolean
  }
) {
  const {
    p,
    widget,
    inert,
    mode,
    onChange,
    axes,
    onToggleAxis,
    onUpdateAxis,
    intErrors,
    onFocus,
    valueOf,
  } = props
  const v = valueOf(p.name)

  if (mode === 'optimize') {
    // A non-numeric param has no from/to/step to walk. Where it carries a closed SET of values —
    // a dropdown's options, a bool's two states — it can still be swept as a list; everything else
    // is held at the value it inherits from the source run.
    if (widget !== 'number') {
      const choices = props.allowListSweep ? sweepChoices(p) : []
      if (choices.length < 2) {
        return (
          <span className="text-[11.5px] text-text-tertiary italic">
            <span className="font-mono not-italic mr-2 text-text-secondary">{fmt(v)}</span>inherited
            · not swept
          </span>
        )
      }
      const listAx = axes?.[p.name]
      const listed = listAx?.mode === 'list' ? listAx.values : null
      return (
        <>
          <div className={`flex items-center gap-2 ${CONTROL_W}`}>
            <span
              className={`flex-1 min-w-0 inline-flex items-center bg-bg-sunken border border-border-default rounded-lg px-2.5 ${CONTROL_H} ${listed ? 'opacity-40' : ''}`}
            >
              <span className="text-[13px] font-mono text-text-primary truncate">
                {listed ? '' : fmt(v)}
              </span>
            </span>
            <button
              type="button"
              onClick={() => onToggleAxis?.(p.name)}
              className={`flex-shrink-0 text-[11px] font-semibold rounded-md px-2.5 py-[6px] border transition-colors ${
                listed
                  ? 'text-accent border-accent/40 bg-accent/10'
                  : 'text-text-tertiary border-border-default bg-bg-sunken hover:text-text-secondary'
              }`}
            >
              {listed ? '✓ sweep' : '⤢ sweep'}
            </button>
          </div>
          {listed && (
            <div className="flex items-center gap-1.5 flex-wrap basis-full mt-1.5">
              {choices.map((c) => {
                const on = listed.includes(c.value)
                return (
                  <button
                    key={c.value}
                    type="button"
                    onClick={() => props.onToggleListValue?.(p.name, c.value)}
                    className={`text-[11.5px] rounded-md px-2 py-[5px] border transition-colors ${
                      on
                        ? 'text-accent border-accent/40 bg-accent/10 font-semibold'
                        : 'text-text-tertiary border-border-default bg-bg-sunken hover:text-text-secondary'
                    }`}
                  >
                    {c.label}
                  </button>
                )
              })}
              <span className="text-[11px] text-text-tertiary ml-1">
                {listed.length} of {choices.length}
              </span>
            </div>
          )}
        </>
      )
    }
    const ax = axes?.[p.name]
    const swept = ax?.mode === 'range'
    const err = intErrors?.[p.name]
    return (
      <>
        {/* box + sweep button share the one control width, so the row edge matches every other widget */}
        <div className={`flex items-center gap-2 ${CONTROL_W}`}>
          <NumberBox
            fill
            value={swept ? '' : String(v)}
            disabled={swept}
            step={p.step}
            onFocus={onFocus}
            onInput={() => {}}
            unit={p.unit}
            dim={swept}
            readOnly
          />
          <button
            type="button"
            onClick={() => onToggleAxis?.(p.name)}
            className={`flex-shrink-0 text-[11px] font-semibold rounded-md px-2.5 py-[6px] border transition-colors ${
              swept
                ? 'text-accent border-accent/40 bg-accent/10'
                : 'text-text-tertiary border-border-default bg-bg-sunken hover:text-text-secondary'
            }`}
          >
            {swept ? '✓ sweep' : '⤢ sweep'}
          </button>
        </div>
        {swept && ax && (
          <div className="flex items-center gap-1.5 basis-full mt-1.5">
            {(['min', 'max', 'step'] as const).map((f) => (
              <span
                key={f}
                className={`inline-flex items-center bg-bg-sunken border rounded-md ${err ? 'border-neg-text/60' : 'border-border-default'}`}
              >
                <label className="text-[10px] text-text-tertiary pl-2 pr-1">
                  {f === 'min' ? 'from' : f === 'max' ? 'to' : 'step'}
                </label>
                <input
                  value={ax[f]}
                  onChange={(e) => onUpdateAxis?.(p.name, f, e.target.value)}
                  onFocus={onFocus}
                  className="w-12 bg-transparent py-[6px] pr-2 text-[12px] font-mono tabular-nums text-text-primary outline-none"
                />
              </span>
            ))}
          </div>
        )}
        {swept && err && <span className="basis-full text-[11px] text-neg-text">{err}</span>}
      </>
    )
  }

  // run / tune — the "was X" tune tag renders on the label line (see <TuneTag>)
  if (widget === 'toggle') {
    const on = v === true
    return (
      <div
        className={`inline-flex bg-bg-sunken border border-border-default rounded-lg p-[3px] ${CONTROL_W} ${CONTROL_H}`}
      >
        {([false, true] as const).map((state) => {
          const label = String((state ? p.options?.on : p.options?.off) ?? (state ? 'On' : 'Off'))
          return (
            <button
              key={String(state)}
              type="button"
              // An inert toggle is refused rather than hidden — clicking it would write a value
              // the strategy cannot act on, and a control that accepts a change nothing honours
              // is worse than one that plainly will not move.
              disabled={inert}
              onClick={() => {
                onFocus()
                onChange?.(p.name, state)
              }}
              // min-w-0 lets the label truncate instead of forcing the flex child wider than
              // its half; title keeps a clipped label readable.
              title={label}
              className={`flex-1 min-w-0 flex items-center justify-center gap-1.5 px-1.5 text-[12px] font-semibold rounded-md transition-colors ${
                inert ? 'cursor-not-allowed' : ''
              } ${
                on === state
                  ? 'bg-accent text-bg-base'
                  : `text-text-tertiary ${inert ? '' : 'hover:text-text-secondary'}`
              }`}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${on === state ? 'bg-bg-base' : 'bg-text-tertiary/50'}`}
              />
              <span className="truncate">{label}</span>
            </button>
          )
        })}
      </div>
    )
  }

  if (widget === 'select' && p.choices?.length) {
    return (
      <select
        value={String(v ?? '')}
        onFocus={onFocus}
        onChange={(e) => {
          onFocus()
          onChange?.(p.name, e.target.value)
        }}
        className={`bg-bg-sunken border border-border-default rounded-lg px-2.5 text-[12px] text-text-primary focus:outline-none focus:border-accent transition-colors ${CONTROL_W} ${CONTROL_H}`}
      >
        {p.choices.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>
    )
  }

  if (widget === 'switch') {
    const on = v === true
    return (
      <button
        type="button"
        onClick={() => {
          onFocus()
          onChange?.(p.name, !on)
        }}
        className={`inline-flex items-center gap-2.5 ${CONTROL_W} ${CONTROL_H}`}
      >
        <span
          className={`w-10 h-[23px] rounded-full relative transition-colors ${on ? 'bg-accent' : 'bg-border-default'}`}
        >
          <span
            className={`absolute top-[3px] w-[17px] h-[17px] rounded-full transition-all ${on ? 'left-[20px] bg-bg-base' : 'left-[3px] bg-text-secondary'}`}
          />
        </span>
        <span className="text-[12px] font-semibold text-text-secondary">{on ? 'On' : 'Off'}</span>
      </button>
    )
  }

  // number / time / text
  return (
    <NumberBox
      value={String(v)}
      text={widget !== 'number'}
      step={p.step}
      min={p.min}
      max={p.max}
      unit={p.unit}
      onFocus={onFocus}
      onInput={(raw) => onChange?.(p.name, coerceInput(p, raw, v))}
    />
  )
}

function NumberBox(props: {
  value: string
  text?: boolean
  disabled?: boolean
  readOnly?: boolean
  dim?: boolean
  fill?: boolean
  step?: number
  min?: number
  max?: number
  unit?: string
  onFocus: () => void
  onInput: (raw: string) => void
}) {
  const { value, text, disabled, readOnly, dim, fill, step, min, max, unit, onFocus, onInput } =
    props
  // `fill` = the box shares the control width with a sibling (the optimizer's sweep button)
  return (
    <span
      className={`inline-flex items-center bg-bg-sunken border border-border-default rounded-lg overflow-hidden ${fill ? 'flex-1 min-w-0' : CONTROL_W} ${CONTROL_H} ${dim ? 'opacity-40' : ''}`}
    >
      <input
        type={text ? 'text' : 'number'}
        step={text ? undefined : (step ?? 'any')}
        // The schema has carried `min`/`max` since the scanner was written and nothing read them,
        // so a bounded param looked unbounded. They are a CUE, not a gate — a native number input
        // stops the spinner and marks the field `:invalid` but still lets a value be typed or
        // pasted past the bound, so the strategy's own check is what actually refuses one.
        min={text ? undefined : min}
        max={text ? undefined : max}
        value={value}
        disabled={disabled}
        readOnly={readOnly}
        onFocus={onFocus}
        onChange={(e) => onInput(e.target.value)}
        className="flex-1 w-full min-w-0 bg-transparent px-2.5 self-stretch text-[13px] font-mono tabular-nums text-text-primary outline-none invalid:text-neg"
      />
      {unit && (
        <span className="text-[11px] text-text-tertiary px-2.5 self-stretch flex items-center border-l border-border-subtle">
          {unit}
        </span>
      )}
    </span>
  )
}

// ── explainer panel ───────────────────────────────────────────────────────────
function Explainer({
  p,
  mode,
  valueOf,
  axes,
  inline,
  inert,
}: {
  p: ParamSchemaEntry
  mode: ParamEditorMode
  valueOf: (n: string) => ParamValue
  axes?: Record<string, AxisEdit>
  inline?: boolean
  inert?: boolean
}) {
  const v = valueOf(p.name)
  const widget = widgetOf(p, v)
  const ax = axes?.[p.name]
  const swept = mode === 'optimize' && (ax?.mode === 'range' || ax?.mode === 'list')

  return (
    <div>
      {/* inline mode skips the eyebrow + big title — the focused row already names it */}
      {!inline && (
        <div className="text-[11px] uppercase tracking-wider text-text-tertiary mb-2">
          Now editing
        </div>
      )}
      {!inline && (
        <h3 className="text-[17px] font-semibold mb-2 text-text-primary">{labelOf(p)}</h3>
      )}
      {!inline && p.unit && (
        <span className="inline-block text-[10px] font-bold uppercase tracking-wide text-accent bg-accent/15 border border-accent/40 rounded px-1.5 py-[2px] mb-2.5">
          {p.unit}
        </span>
      )}
      {descOf(p) && (
        <p
          className={`text-text-secondary ${inline ? 'text-[12px] mb-2.5' : 'text-[12.5px] mb-3.5'}`}
        >
          {descOf(p)}
        </p>
      )}

      {/* Above the states, not below: a reader who has just been told what each option does
          needs to know it has no say here BEFORE deciding between them. */}
      {inert && p.disable_note && (
        <p
          data-testid={`param-inert-note-${p.name}`}
          className="text-[12px] text-text-tertiary italic border-l-2 border-border-default pl-2.5 mb-3"
        >
          {p.disable_note}
        </p>
      )}

      {swept && ax?.mode === 'range' ? (
        <>
          <KV k="Sweeping" v={`${ax.min} → ${ax.max} / ${ax.step}`} />
          <KV k="Values" v={String(sweepCount(ax))} />
        </>
      ) : swept && ax?.mode === 'list' ? (
        <>
          <KV k="Sweeping" v={ax.values.join(' · ')} />
          <KV k="Values" v={String(ax.values.length)} />
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
          {([false, true] as const).map((state) => (
            <div
              key={String(state)}
              className={`flex items-start gap-2.5 py-2 text-[12px] ${v === state ? 'text-text-primary' : 'text-text-secondary'}`}
            >
              <span
                className={`w-2 h-2 rounded-full mt-[5px] flex-shrink-0 ${v === state ? 'bg-accent' : 'bg-text-tertiary/40'}`}
              />
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
    <b className="text-accent block mb-1">{arrow}</b>
    {text}
  </div>
)

function sweepCount(ax: { min: string; max: string; step: string }): number {
  const lo = parseFloat(ax.min),
    hi = parseFloat(ax.max),
    st = parseFloat(ax.step)
  if (isNaN(lo) || isNaN(hi) || isNaN(st) || st <= 0 || lo > hi) return 0
  return Math.floor((hi - lo) / st + 1e-9) + 1
}

// ── Pinned coach footer ─────────────────────────────────────────────────────
// Always-on teaching strip for the focused param, rendered by the parent (the tune
// dock) at the bottom of the panel — so the rows above never shift as focus moves.
// Pair with <ParamEditor explainer="coach" onFocusChange={...} />.
export function ParamCoach({
  schema,
  values,
  focusName,
}: {
  schema: ParamSchemaEntry[]
  values: Record<string, ParamValue>
  focusName: string | null
}) {
  const params = useMemo(() => schema.filter((p) => p.category !== 'foundational'), [schema])
  const p = params.find((x) => x.name === focusName)
  if (!p) {
    return (
      <p className="text-[11.5px] italic text-text-tertiary">Select a parameter to see guidance.</p>
    )
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
          {changed && (
            <span className="text-text-tertiary">
              {' '}
              · default <span className="font-mono">{fmt(p.default)}</span>
            </span>
          )}
        </span>
      </div>

      {descOf(p) && (
        <p className="text-[12px] text-text-secondary leading-snug mb-2">{descOf(p)}</p>
      )}

      {widget === 'number' && p.guide && (
        <div className="flex gap-2">
          <GuideBox arrow="↓ Lower" text={p.guide[0]} />
          <GuideBox arrow="↑ Higher" text={p.guide[1]} />
        </div>
      )}

      {widget === 'toggle' && p.options && (
        <div className="flex gap-2">
          {([false, true] as const).map((state) => (
            <div
              key={String(state)}
              className={`flex-1 rounded-lg border px-2.5 py-1.5 text-[11.5px] ${
                v === state
                  ? 'border-accent/40 bg-accent/10 text-text-primary'
                  : 'border-border-subtle bg-bg-sunken text-text-secondary'
              }`}
            >
              <span className="flex items-center gap-1.5">
                <span
                  className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${v === state ? 'bg-accent' : 'bg-text-tertiary/40'}`}
                />
                <b>{state ? p.options?.on : p.options?.off}</b>
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
