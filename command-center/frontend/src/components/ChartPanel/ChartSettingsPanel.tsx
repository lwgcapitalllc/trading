/**
 * Chart settings panel — renders whatever `chartSettings.SECTIONS` declares.
 *
 * It knows nothing about any individual setting, deliberately. Adding one is a row in the registry;
 * this file only grows when a new WIDGET KIND is needed (a colour, a number), and then it grows once
 * for every setting of that kind that will ever exist.
 *
 * Edits are LIVE — the chart redraws on the change, the same as `FibSettings` — so a preference is
 * judged by looking at the chart rather than by pressing OK and finding out.
 */
import type { ReactNode } from 'react'
import { RotateCcw, X } from 'lucide-react'
import {
  DEFAULT_CHART_SETTINGS, SECTIONS,
  type ChartSettings, type CustomSection, type SettingDef,
} from './chartSettings'

// Feeds the panel's own viewport clamp — it places itself, like FibSettings and the context menu,
// rather than making the host do the maths. Keep in sync with the width/max-height below.
const PANEL_W = 300
const PANEL_H = 560

interface Props {
  /** Anchor position — the panel floats viewport-fixed here, clamped to stay on screen. */
  x: number
  y: number
  settings: ChartSettings
  onChange: (next: ChartSettings) => void
  onClose: () => void
  /** Body for each `custom` section the registry declares. The panel places and titles it; the host
   *  owns what goes inside, because those blocks need state the panel has no business holding (the
   *  fib ladder is the run's own, persisted separately). A section with no renderer is SKIPPED
   *  rather than drawn empty — an empty titled box reads as something that failed to load. */
  renderCustom?: (section: CustomSection) => ReactNode
}

/** The app's switch, not a new one.
 *
 * ⚠ The first version here was hand-rolled — a `translate-x` knob inside a bordered track — and it
 * rendered wrong: the OFF state's 1px border shrinks the content box under `border-box`, so the
 * knob's fixed offsets no longer centred it, and it read as a control that was slightly broken.
 * This is `ParamEditor`'s `switch` widget verbatim (explicit `left`, no transform, no border on the
 * track, the On/Off word beside it), which is the shape every other boolean in this app uses.
 * **Extend the existing control before inventing one** — the house rule, and the reason this looked
 * off in a panel where everything else looked native.
 */
function Toggle({ on, onClick }: { on: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      onClick={onClick}
      className="inline-flex flex-shrink-0 items-center gap-2"
    >
      <span
        className={`relative h-[23px] w-10 rounded-full transition-colors ${
          on ? 'bg-accent' : 'bg-border-default'
        }`}
      >
        <span
          className={`absolute top-[3px] h-[17px] w-[17px] rounded-full transition-all ${
            on ? 'left-[20px] bg-bg-base' : 'left-[3px] bg-text-secondary'
          }`}
        />
      </span>
      <span className="text-[11px] font-semibold text-text-secondary">{on ? 'On' : 'Off'}</span>
    </button>
  )
}

export default function ChartSettingsPanel({
  x, y, settings, onChange, onClose, renderCustom,
}: Props) {
  const isDefault = (Object.keys(DEFAULT_CHART_SETTINGS) as (keyof ChartSettings)[])
    .every(k => settings[k] === DEFAULT_CHART_SETTINGS[k])

  const row = (def: SettingDef) => {
    // One branch per widget kind. `kind` is a union, so adding a kind without handling it here is a
    // type error rather than a silently missing control.
    switch (def.kind) {
      case 'toggle':
        return (
          <Toggle
            on={settings[def.key] as boolean}
            onClick={() => onChange({ ...settings, [def.key]: !settings[def.key] })}
          />
        )
    }
  }

  return (
    <div
      // Stop both, like FibSettings: the chart body's click handler drives measure mode, and a
      // click that reaches it from inside a panel would start a measurement behind the panel.
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
        <span className="text-[11px] font-semibold text-text-primary">Chart settings</span>
        <button
          onClick={() => onChange({ ...DEFAULT_CHART_SETTINGS })}
          disabled={isDefault}
          title="Back to the shipped defaults"
          className="ml-auto text-text-tertiary transition-colors hover:text-text-primary disabled:opacity-30 disabled:hover:text-text-tertiary"
        >
          <RotateCcw className="h-3 w-3" />
        </button>
        <button onClick={onClose} className="text-text-tertiary transition-colors hover:text-text-primary">
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="max-h-[470px] overflow-y-auto py-1">
        {SECTIONS.map(section => {
          const body = section.custom
            ? renderCustom?.(section.custom)
            : section.items!.map(def => (
                <div
                  key={def.key}
                  className="flex items-start gap-2.5 px-3 py-1.5 transition-colors hover:bg-bg-sunken"
                >
                  <div className="min-w-0 flex-1">
                    <div className="text-[11px] font-medium text-text-primary">{def.label}</div>
                    {def.help && (
                      <div className="mt-px text-[10px] leading-snug text-text-tertiary">{def.help}</div>
                    )}
                  </div>
                  <div className="pt-[3px]">{row(def)}</div>
                </div>
              ))
          // A custom section the host did not render is skipped whole, title included.
          if (!body) return null
          return (
            <div key={section.title}>
              <div className="px-3 pt-2 pb-1 text-[9px] font-semibold uppercase tracking-wide text-text-tertiary">
                {section.title}
              </div>
              {body}
            </div>
          )
        })}
      </div>

      <div className="border-t border-border-subtle px-3 py-1.5 text-[9px] leading-snug text-text-tertiary">
        Display only — nothing here changes what the run measured.
      </div>
    </div>
  )
}
