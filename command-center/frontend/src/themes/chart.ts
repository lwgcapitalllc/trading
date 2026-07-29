/**
 * Chart color constants — the only place in the app where theme colors must be raw hex
 * (Recharts / SVG props can't use Tailwind classes).
 *
 * All values are derived from the active theme file. When swapping themes,
 * update the import below to point to the new theme file.
 */
import t from './dark-2026.js'

export const C = {
  // Data colors
  pos:    t.pos,
  neg:    t.neg,
  accent: t.accent,
  gold:   t.gold,
  series: t.series,

  // Chart chrome
  tooltipBg:     t.bgSunken,
  tooltipBorder: t.borderStrong,
  axisTick:      t.textTertiary,

  // Subtle grids and reference lines — intentionally low-opacity white,
  // not theme colors, so they work on any dark background.
  grid:        '#ffffff07',
  refLine:     '#ffffff14',
  refLineDim:  '#ffffff08',
} as const
