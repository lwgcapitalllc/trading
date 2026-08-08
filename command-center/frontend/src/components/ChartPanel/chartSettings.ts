/**
 * Chart settings — the one place a reader's own preferences about how the chart LOOKS are declared,
 * defaulted and persisted.
 *
 * **This is a registry, not a settings object, and that is the point.** Adding a setting is one
 * field on `ChartSettings`, one default, and one row in `SECTIONS`. The panel renders whatever the
 * registry declares, so nothing in the UI has to be touched to add a colour or a toggle — which is
 * the requirement it was built to (Aaron, 2026-08-06: fib settings, order-block colours, FVG
 * colours, bar colours, "I'll do that as I go").
 *
 * ⚠ **A setting is a PREFERENCE, never a measurement.** Nothing declared here may change what the
 * chart computes, only how it is drawn. The moment a control in this panel changes which trades
 * exist, which gaps qualify, or what a number means, it belongs in the run's own config where it is
 * stored with the run — a display preference silently reshaping a result is this repo's most
 * expensive recurring defect, and it would be undetectable here because the panel is per-browser.
 *
 * ⚠ **Stored settings are MERGED over the defaults, never swapped in.** A blob written before a
 * setting existed must not remove it, and a key that no longer exists must not resurrect it. This
 * is the same rule `reconcileToggles` follows for overlay groups one file over, and it fails the
 * same silent way if broken: the reader's chart quietly loses a control they never turned off.
 */

export interface ChartSettings {
  /** Trade annotations carry their PRICE (`Entry 2635.58`) as well as their name. */
  tradeLabelPrices: boolean
  /** A repainted candlestick-reversal candle names its pattern (`Bearish Engulfing`). */
  candleMarkLabels: boolean
}

export const DEFAULT_CHART_SETTINGS: ChartSettings = {
  // Default ON — it is how the annotations have read since 2026-08-03, when the prices were added
  // deliberately: a bare `SL` says a level exists and makes you read it off the axis. It is a
  // setting now because a 1m re-entry's box is short enough that the chips stack on top of each
  // other, and on that chart the price is what makes them too wide to fit.
  tradeLabelPrices: true,
  // Default OFF (Aaron, 2026-08-08). Every mark draws its own tag with no cross-overlay
  // de-collision — unlike the batched `LABEL` template — so on a run with marks a few bars apart
  // the names sit on top of the neighbouring candles. The COLOUR is the signal; the name is what
  // you switch on when you are asking which pattern it was.
  candleMarkLabels: false,
}

export type SettingKind = 'toggle'

export interface SettingDef {
  key: keyof ChartSettings
  label: string
  kind: SettingKind
  /** One line under the label. Say what the OFF state looks like — that is the part a reader
   *  cannot guess from the name. */
  help?: string
}

/** A section is EITHER a list of registry-driven controls or one named custom block the host
 *  renders. The second exists for editors that already have a component and would be absurd to
 *  express as settings rows — the fib ladder is a scrolling list with its own add / remove /
 *  colour-pick behaviour, and flattening it into `SettingDef`s would be re-implementing it.
 *
 *  ⚠ Keep custom blocks RARE. Every one is a section the registry cannot describe, so it is UI the
 *  next setting cannot reuse — the opposite of the point of this file. A control that fits a widget
 *  kind should be a widget kind, and adding a kind is cheaper than adding a block. */
export type SectionBody =
  | { items: SettingDef[]; custom?: never }
  | { custom: CustomSection; items?: never }

export type CustomSection = 'fibLevels'

export type SettingSection = { title: string } & SectionBody

/** What the panel renders, in order. */
export const SECTIONS: SettingSection[] = [
  {
    title: 'Trades',
    items: [
      {
        key: 'tradeLabelPrices',
        label: 'Show prices in labels',
        kind: 'toggle',
        help: 'Off = just Entry / SL / TP1, with no number beside them.',
      },
    ],
  },
  {
    title: 'Candlestick reversals',
    items: [
      {
        key: 'candleMarkLabels',
        label: 'Name the pattern',
        kind: 'toggle',
        help: 'Off = the candle is painted navy with no tag. Hover still names it.',
      },
    ],
  },
  // The fib TOOL's default ladder. It lived behind its own gear on the drawing toolbar until
  // 2026-08-06 (Aaron's ask to move it here) — which was the wrong home for it twice over: it is
  // not a drawing tool, and a reader looking for how the chart is drawn had no reason to open a
  // popover attached to one. ⚠ The per-DRAWING ladder is deliberately NOT here and stays on that
  // fib's right-click menu: it is a property of one drawing, and the two would otherwise be one
  // control claiming two scopes.
  { title: 'Fib levels', custom: 'fibLevels' },
]

const STORAGE_KEY = 'lwg.chart.settings.v1'

export function loadChartSettings(): ChartSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { ...DEFAULT_CHART_SETTINGS }
    const stored = JSON.parse(raw) as Partial<ChartSettings>
    // Merge, key by key, and only for keys that still exist — see the module note. A stored value of
    // the wrong TYPE is dropped rather than trusted: this blob is editable by hand and by any older
    // build, and a string where a boolean belongs would render as a permanently-on toggle.
    const out = { ...DEFAULT_CHART_SETTINGS }
    for (const k of Object.keys(DEFAULT_CHART_SETTINGS) as (keyof ChartSettings)[]) {
      const v = stored?.[k]
      if (typeof v === typeof DEFAULT_CHART_SETTINGS[k]) (out[k] as unknown) = v
    }
    return out
  } catch {
    // A corrupt or unavailable store must not break the chart — private mode has no localStorage.
    return { ...DEFAULT_CHART_SETTINGS }
  }
}

export function saveChartSettings(s: ChartSettings): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(s))
  } catch {
    // Preferences are best-effort. Losing them is a nuisance; throwing here would take the chart out.
  }
}
