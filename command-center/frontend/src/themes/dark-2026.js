/**
 * Dark 2026 — alternate theme for command-center
 *
 * This file is the single source of truth for all color values when the
 * dark-2026 theme is active.
 */

export default {
  // ── Surfaces ─────────────────────────────────────────────────────────────────
  bgBase:      '#03040a',
  bgSunken:    '#0b0b17',
  bgSurface:   '#101024',
  bgSurface2:  '#16162a',
  bgHover:     '#1d1d3c80',
  bgActive:    '#23234a',

  // ── Borders ───────────────────────────────────────────────────────────────────
  borderSubtle:  '#14142b',
  borderDefault: '#1f1f3f',
  borderStrong:  '#2d2d54',

  // ── Text ──────────────────────────────────────────────────────────────────────
  textPrimary:   '#f0f3ff',
  textSecondary: '#c5cadf',
  textTertiary:  '#8f92a7',
  textInverse:   '#03060c',

  // ── Accent — electric cyan ────────────────────────────────────────────────────
  accent:        '#00e5ff',
  accentHover:   '#39f0ff',
  accentMuted:   '#00313d',
  accentText:    '#39f0ff',

  // ── Gold ──────────────────────────────────────────────────────────────────────
  gold:          '#d9a441',
  goldMuted:     '#2d2410',
  goldText:      '#e7bf6b',

  // ── Semantic ──────────────────────────────────────────────────────────────────
  pos:           '#00ff82',
  posMuted:      '#003229',
  posText:       '#45ffad',
  neg:           '#ff496b',
  negMuted:      '#3a0d18',
  negText:       '#ff839a',
  warn:          '#ffb300',
  warnMuted:     '#2f2100',
  warnText:      '#ffd64e',
  neutral:       '#6f7488',

  // ── Chart series ──────────────────────────────────────────────────────────────
  series: ['#00e5ff', '#00ff7f', '#ffb300', '#4da6ff', '#a78bfa', '#ff3b5c'],

  // ── Glow box-shadows ─────────────────────────────────────────────────────────
  glowAccentBox: '0 0 12px rgba(0, 229, 255, 0.35), 0 0 40px rgba(0, 229, 255, 0.14)',
  glowPosBox:    '0 0 12px rgba(0, 255, 130, 0.28), 0 0 40px rgba(0, 255, 130, 0.11)',
  glowNegBox:    '0 0 12px rgba(255, 73, 107, 0.35), 0 0 28px rgba(255, 73, 107, 0.12)',
  glowGoldBox:   '0 0 12px rgba(217, 164, 65, 0.35), 0 0 28px rgba(217, 164, 65, 0.12)',

  // ── Glow drop-shadows ───────────────────────────────────────────────────────
  glowAccentDrop: ['0 0 5px rgba(0,229,255,1.0)',   '0 0 16px rgba(0,229,255,0.65)'],
  glowPosDrop:    ['0 0 5px rgba(0,255,130,1.0)',   '0 0 16px rgba(0,255,130,0.65)'],
  glowNegDrop:    ['0 0 5px rgba(255,73,107,1.0)',   '0 0 16px rgba(255,73,107,0.65)'],
  glowGoldDrop:   ['0 0 5px rgba(255,179,0,1.0)',   '0 0 16px rgba(255,179,0,0.65)'],
}
