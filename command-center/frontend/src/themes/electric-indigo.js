/**
 * Electric Indigo — LWG Capital default theme
 *
 * This file is the single source of truth for all color values.
 *
 * Referenced by:
 *   tailwind.config.js  — builds every Tailwind color token (bg-*, text-*, border-*, etc.)
 *   src/themes/chart.ts — inline constants for Recharts (can't use Tailwind classes)
 *
 * To swap themes:
 *   1. Create a new theme file (copy + modify this one)
 *   2. Update the import in tailwind.config.js → "from './src/themes/<new-theme>.js'"
 *   3. Update the import in src/themes/chart.ts → "from './<new-theme>.js'"
 *   4. Rebuild (npm run dev / npm run build)
 *
 * index.css notes: body background (#080810), scrollbar thumb (#252540), and selection
 * color are hardcoded there for performance. Update those manually when swapping themes
 * — they map to bgBase and bgSurface2 below.
 */

export default {
  // ── Surfaces ─────────────────────────────────────────────────────────────────
  bgBase:      '#080810',   // index.css: body background-color
  bgSunken:    '#0d0d1a',
  bgSurface:   '#111120',
  bgSurface2:  '#181828',   // index.css: scrollbar thumb base
  bgHover:     '#1e1e3480',
  bgActive:    '#222240',

  // ── Borders ───────────────────────────────────────────────────────────────────
  borderSubtle:  '#1a1a2e',
  borderDefault: '#222238',
  borderStrong:  '#2c2c48',

  // ── Text ──────────────────────────────────────────────────────────────────────
  textPrimary:   '#e9eaf0',
  textSecondary: '#c2c6d8',
  textTertiary:  '#8b8fa3',
  textInverse:   '#020e12',

  // ── Accent — electric cyan ────────────────────────────────────────────────────
  accent:        '#00e5ff',
  accentHover:   '#33ecff',
  accentMuted:   '#002a33',
  accentText:    '#33ecff',

  // ── Gold ──────────────────────────────────────────────────────────────────────
  gold:          '#d9a441',
  goldMuted:     '#2a2010',
  goldText:      '#e6bd6a',

  // ── Semantic ──────────────────────────────────────────────────────────────────
  pos:           '#00ff7f',
  posMuted:      '#002618',
  posText:       '#33ff99',
  neg:           '#ff3b5c',
  negMuted:      '#2d0a12',
  negText:       '#ff6680',
  warn:          '#ffb300',
  warnMuted:     '#2a1f00',
  warnText:      '#ffc933',
  neutral:       '#6b7080',

  // ── Chart series ──────────────────────────────────────────────────────────────
  series: ['#00e5ff', '#00ff7f', '#ffb300', '#4da6ff', '#a78bfa', '#ff3b5c'],

  // ── Glow box-shadows ─────────────────────────────────────────────────────────
  // Used in tailwind.config.js boxShadow extension
  glowAccentBox: '0 0 12px rgba(0, 229, 255, 0.35), 0 0 40px rgba(0, 229, 255, 0.14)',
  glowPosBox:    '0 0 12px rgba(0, 255, 127, 0.28), 0 0 40px rgba(0, 255, 127, 0.11)',
  glowNegBox:    '0 0 12px rgba(255, 59, 92,  0.35), 0 0 28px rgba(255, 59, 92, 0.12)',
  glowGoldBox:   '0 0 12px rgba(217, 164, 65, 0.35), 0 0 28px rgba(217, 164, 65, 0.12)',

  // ── Glow drop-shadows ────────────────────────────────────────────────────────
  // Used in tailwind.config.js dropShadow extension
  glowAccentDrop: ['0 0 5px rgba(0,229,255,1.0)',   '0 0 16px rgba(0,229,255,0.65)'],
  glowPosDrop:    ['0 0 5px rgba(0,255,127,1.0)',   '0 0 16px rgba(0,255,127,0.65)'],
  glowNegDrop:    ['0 0 5px rgba(255,59,92,1.0)',   '0 0 16px rgba(255,59,92,0.65)'],
  glowGoldDrop:   ['0 0 5px rgba(255,179,0,1.0)',   '0 0 16px rgba(255,179,0,0.65)'],
}
