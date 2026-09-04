import { useState, useMemo, useEffect } from 'react'
import { ChevronRight, ChevronDown } from 'lucide-react'
import type { ParamSchemaEntry } from '@/types'
import { condHolds, sameValue, type ParamValue } from '@/components/paramConditions'

// Shared parameter editor used by Run Backtest, Tuning, and Optimize.
// Layout: Essentials card up front + counted accordions on the left, a live
// explainer panel on the right. Friendly labels/groups/descriptions come from the
// schema (overlaid from a strategy's companion meta.json). Blue = focus, and only
// focus; gold = section-title text. Degrades gracefully when a strategy carries no
// editor metadata (no core flags → no Essentials card, all groups as accordions).

export type { ParamValue }
export type AxisEdit =
  | { mode: 'range'; min: string; max: string; step: string }
  | { mode: 'fixed'; value: string }
  | { mode: 'list'; values: string[] }
export type ParamEditorMode = 'run' | 'tune' | 'optimize'

// ── conditions and value resolution ───────────────────────────────────────────
// Three schema keys read one another's VALUES: `show_if`, `disable_if` and `custom_from`. The
// first two are evaluated in `paramConditions.ts`, which is a separate file for one reason: it
// has a twin in `backend/services/stress_tester.py::param_is_reachable`, and the two must agree
// or the lab perturbs a param the editor will not draw and books the guaranteed 0% change as
// "rock solid". `custom_from` resolution stays here, because it needs the schema.

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

/**
 * True when the param still exists but cannot change anything — see `disable_if` in types.
 *
 * ⚠ Since 2026-08-27 the editor HIDES these rows rather than greying them, so this is one of the
 * two questions `visible` asks. `disable_note` survives the change and is still required on every
 * `disable_if` row: the finished-run params panel has to say why a setting did nothing on a run
 * that has already been taken, and that reader cannot be shown an empty space.
 */
export function isInert(
  p: ParamSchemaEntry,
  schema: ParamSchemaEntry[],
  values: Record<string, ParamValue>
): boolean {
  return condHolds(p.disable_if, readerFor(schema, values).read)
}

/**
 * True when a param could not have affected this configuration AT ALL.
 *
 * Two ways that happens, and they are the same fact from opposite ends: its `show_if` does not
 * hold (the secondary re-entry settings when the secondary is off), or its `disable_if` does.
 * Aaron, 2026-08-20: *"if secondary trades is off in the strategy you DON'T need to show all the
 * params related to it… same goes for anything cascading."*
 *
 * ⚠ Exported for the finished-run params panel, which asks it of a run already taken. The editor
 * asks the same question in two halves instead (`show_if` in `visible`, `disable_if` through
 * `isInert`) because it reads `show_if` off the RAW value and this reads it custom-resolved. No
 * `show_if` in this repo names a `custom_from` target today, so the two agree — the day one does,
 * they diverge silently, and the fix is to make this the single reader rather than to hope.
 *
 * ⚠ Resolved through `readerFor`, so a `custom_from` sibling's value is the one compared — a
 * gate that reads the raw dropdown instead of the Custom number it resolves to gets exactly the
 * cascading case wrong.
 */
export function isOutOfPlay(
  p: ParamSchemaEntry,
  schema: ParamSchemaEntry[],
  values: Record<string, ParamValue>
): boolean {
  const { read } = readerFor(schema, values)
  if (p.show_if && !condHolds(p.show_if, read)) return true
  return condHolds(p.disable_if, read)
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
 * `disable_if` applied, settled ones gone unless moved.
 *
 * ⚠ Exported so the read-only summary and the editor cannot disagree about what a strategy's
 * settings ARE. A summary listing a row the editor does not offer (or missing one it does) is
 * worse than no summary: the reader opens the editor to change something the summary promised.
 * That is also why the `disable_if` clause below is not optional: the day those rows stopped
 * being drawn, a summary that still counted them would have been the disagreement this warning
 * describes.
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
      !isInert(p, filled, values) &&
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
 * ⚠ It shares `visible` / `settled` with the stacked layout, so the two cannot disagree
 * about which rows exist.
 */
function CompactRow(
  props: Props & {
    p: ParamSchemaEntry
    valueOf: (n: string) => ParamValue
  }
) {
  const { p, valueOf, onChange, mode, baseline } = props
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
      <select value={String(v ?? '')} onChange={(e) => set(e.target.value)} className={ctlBase}>
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
      }`}
      title={p.description}
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

/**
 * The words a HUMAN reads for a param, never the field name.
 *
 * ⚠ Exported because the finished-run params panel asks the same question. It used to print the
 * raw field name, so the record of what a run charged was unreadable to anyone not holding the
 * code open — see `ParamsSidePanel` in BacktestDetail.
 */
export const labelOf = (p: ParamSchemaEntry) => p.label || p.display_name || p.name

/**
 * The SHORTEST correct name for a setting — for surfaces that RECORD a run rather than teach it.
 *
 * `label` is written to explain (*Max time: sweep → SOS (minutes)*, *Stop buffer beyond the level
 * (ticks)*), which is right on the run form and far too long for a 248px rail, where it wraps to
 * three lines and buries the value. Aaron, 2026-08-20: *"don't be too verbose and try to explain
 * params in the side bar… they just have to be simple english names."*
 *
 * ⚠ The short name is authored in the strategy's own metadata, never derived — stripping
 * parentheses and units mechanically produces a name nobody chose. ⚠ Optional everywhere: a
 * strategy that writes none falls straight back to `labelOf`, which is what `b_leg` and
 * `bos` do today. ⚠ Units belong to the VALUE, not the name — the value already renders
 * `4320 minutes`, so repeating it in the label says it twice.
 */
export const shortLabelOf = (p: ParamSchemaEntry) => p.short || labelOf(p)

/** A raw field name with no schema entry, made readable: `exec_sl_buf_tk` -> `Sl buf tk`. */
export function prettyName(name: string): string {
  const words = name
    .replace(/^(exec|aplus|bleg)_/, '')
    .replace(/_/g, ' ')
    .trim()
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : name
}

/**
 * A param's VALUE in the same words the editor shows — a bool as its two option labels, a number
 * with its unit. `String(v)` gave `true` / `false`, which says nothing about which way is on.
 * Pass a schema entry whose option tokens are already filled (`fillTokens`), or none at all.
 */
export function valueLabel(p: ParamSchemaEntry | undefined, v: unknown): string {
  if (typeof v === 'boolean' || v === 'true' || v === 'false') {
    const on = v === true || v === 'true'
    if (p?.options) return String(on ? p.options.on : p.options.off)
    return on ? 'On' : 'Off'
  }
  const s = String(v)
  return p?.unit ? `${s} ${p.unit}` : s
}
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
  // 🔴 A ROW WHOSE `disable_if` HOLDS IS HIDDEN, NOT GREYED (Aaron, 2026-08-27: *"hide them, like
  // everything else"*). It used to be drawn greyed with its reason beside it, on the argument that
  // a setting which vanishes reads as one that does not exist — see `param-gates.spec.ts` for the
  // case that argument won in August. It lost to the form it produced: on `sos_fade` SEVENTEEN
  // rows are greyed under the shipped defaults, so a reader hunting the one setting that matters
  // reads past a screen of controls before learning that none of them apply. The old argument
  // protects a reader who is looking for a specific row and needs to be told it is dead; the count
  // decides which reader is the common one, and it is not that one.
  // ⚠ `disable_if` stays a SEPARATE key from `show_if` — they are opposite polarity in the
  // metadata (one names the values that KILL a row, the other the values that revive it), and
  // collapsing them means recomputing the complement of a dropdown's choice list by hand on every
  // row. They now agree about the screen, not about how they are written.
  // ⚠ Read via `isInert` so the `custom_from` resolution is the same one the labels use: a
  // dropdown set to Custom = 1.0 must hide exactly what its own 1.0 hides.
  const inert = (p: ParamSchemaEntry) => isInert(p, params, values)
  const visible = (p: ParamSchemaEntry) =>
    (!p.show_if || condHolds(p.show_if, valueOf)) && !settled(p) && !inert(p)

  // The group the `core` params live in — the one that opens first. Nothing else reads `core`
  // in this layout any more; see the note above `left`.
  const firstCoreGroup = params.find((p) => p.core && visible(p))?.group ?? null

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
      const g = p.group || 'Parameters'
      if (!seen.includes(g)) seen.push(g)
    }
    return seen
  }, [params])

  const focusP = params.find((p) => p.name === focus)
  const focusGroup = focusP?.group ?? null

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

  // 🔴 NO ESSENTIALS CARD, AND NO SIMPLE/EXPERT SWITCH (2026-08-15, Aaron's call).
  //
  // A curation of "the important ones" only earns its place when the rest are HIDDEN. It was
  // built when the accordions were shut and the card was the way in — but it DUPLICATED those
  // params, so a `core` setting appeared both in the card and inside the group it belongs to,
  // and changing one place left the other looking untouched. Simple mode went with it: its only
  // job was hiding the non-core rows, which is a question about a card that no longer exists.
  //
  // ⚠ Every param now appears EXACTLY ONCE, under its own group. `core` still means something —
  // it decides which group opens first — it just no longer means "and also render it up there".
  const left = (
    <>
      {/* Accordions (or Simple-mode hint) */}
      {groups.map((g, gi) => {
        const rows = params.filter((p) => p.group === g && visible(p))
        if (!rows.length) return null
        // ⚠ The group holding the ESSENTIAL params opens first — that is all `core` decides
        // now. Falling back to `gi === 0` keeps a strategy with no core flags working.
        const isOpen = open[g] ?? (g === firstCoreGroup || (!firstCoreGroup && gi === 0))
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
                  />
                ))}
              </div>
            )}
          </div>
        )
      })}

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
        {/* ⚠ Each group is its own bordered SECTION, not a heading over a continuous list.
            Read as one list the 30 rows blur together and the group name stops doing any work —
            "do something to make it visible that these are sections, segregate it from each
            other". The header is the collapse control, so a section can be shut to focus. */}
        {compactGroups.map((g) => (
          <div
            key={g.name}
            className="mb-2 last:mb-0 rounded-lg border border-border-subtle bg-bg-sunken/30 overflow-hidden"
          >
            <button
              type="button"
              onClick={() => toggleGroup2(g.name)}
              aria-expanded={!collapsed[g.name]}
              className={`flex items-center gap-1.5 w-full px-3 py-[7px] text-[10.5px] font-bold uppercase tracking-[0.7px] text-gold-text hover:bg-bg-hover/50 transition-colors ${
                collapsed[g.name] ? '' : 'border-b border-border-subtle'
              }`}
            >
              {collapsed[g.name] ? <ChevronRight size={11} /> : <ChevronDown size={11} />}
              {g.name}
              <span className="ml-auto normal-case tracking-normal font-normal text-[10px] text-text-tertiary">
                {g.rows.length} setting{g.rows.length > 1 ? 's' : ''}
              </span>
            </button>
            {!collapsed[g.name] && (
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-x-6 gap-y-0 px-2.5 py-1.5">
                {g.rows.map((p) => (
                  <CompactRow key={p.name} p={p} {...props} valueOf={valueOf} />
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
            <Explainer p={focusP} mode={mode} valueOf={valueOf} axes={axes} />
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
  }
) {
  const { p, focused, onFocus } = props // widget forwarded to Control via {...props}
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
            <span className="truncate" title={labelOf(p)}>
              {labelOf(p)}
            </span>
          </span>
          <TuneTag {...props} />
        </div>
        {/* line 2 — the control. Every row drawn here is one that can still change something:
            a param its own `disable_if` kills is not rendered at all, so there is no dead state
            to grey and no reason to print. `disable_note` is still READ — by the finished-run
            params panel, which has to say why a setting did nothing on a run already taken. */}
        <div className="flex items-center gap-2 flex-wrap">
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
  }
) {
  const {
    p,
    widget,
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
              onClick={() => {
                onFocus()
                onChange?.(p.name, state)
              }}
              // min-w-0 lets the label truncate instead of forcing the flex child wider than
              // its half; title keeps a clipped label readable.
              title={label}
              className={`flex-1 min-w-0 flex items-center justify-center gap-1.5 px-1.5 text-[12px] font-semibold rounded-md transition-colors ${
                on === state
                  ? 'bg-accent text-bg-base'
                  : 'text-text-tertiary hover:text-text-secondary'
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
}: {
  p: ParamSchemaEntry
  mode: ParamEditorMode
  valueOf: (n: string) => ParamValue
  axes?: Record<string, AxisEdit>
  inline?: boolean
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
