import t from './src/themes/electric-indigo.js'

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Surfaces
        'bg-base':      t.bgBase,
        'bg-sunken':    t.bgSunken,
        'bg-surface':   t.bgSurface,
        'bg-surface-2': t.bgSurface2,
        'bg-hover':     t.bgHover,
        'bg-active':    t.bgActive,
        // Borders
        'border-subtle':  t.borderSubtle,
        'border-default': t.borderDefault,
        'border-strong':  t.borderStrong,
        // Text
        'text-primary':   t.textPrimary,
        'text-secondary': t.textSecondary,
        'text-tertiary':  t.textTertiary,
        'text-inverse':   t.textInverse,
        // Accent
        accent:          t.accent,
        'accent-hover':  t.accentHover,
        'accent-muted':  t.accentMuted,
        'accent-text':   t.accentText,
        // Gold
        gold:            t.gold,
        'gold-muted':    t.goldMuted,
        'gold-text':     t.goldText,
        // Semantic
        pos:             t.pos,
        'pos-muted':     t.posMuted,
        'pos-text':      t.posText,
        neg:             t.neg,
        'neg-muted':     t.negMuted,
        'neg-text':      t.negText,
        warn:            t.warn,
        'warn-muted':    t.warnMuted,
        'warn-text':     t.warnText,
        neutral:         t.neutral,
        // Chart series
        'series-1':  t.series[0],
        'series-2':  t.series[1],
        'series-3':  t.series[2],
        'series-4':  t.series[3],
        'series-5':  t.series[4],
        'series-6':  t.series[5],
      },
      fontFamily: {
        sans: ['"Inter"', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"SF Mono"', '"Roboto Mono"', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        display: ['28px', { lineHeight: '1.2' }],
        h1:      ['20px', { lineHeight: '1.3' }],
        h2:      ['16px', { lineHeight: '1.4' }],
        h3:      ['14px', { lineHeight: '1.5' }],
        body:    ['13px', { lineHeight: '1.55' }],
        small:   ['12px', { lineHeight: '1.5' }],
        micro:   ['11px', { lineHeight: '1.45' }],
      },
      fontWeight: {
        regular: '400',
        medium:  '500',
        semi:    '600',
      },
      borderRadius: {
        sm:   '6px',
        md:   '8px',
        lg:   '12px',
        pill: '999px',
      },
      spacing: {
        1: '4px',
        2: '8px',
        3: '12px',
        4: '16px',
        5: '20px',
        6: '24px',
        8: '32px',
      },
      boxShadow: {
        pop:           '0 8px 28px rgba(0, 0, 0, 0.65)',
        'glow-accent': t.glowAccentBox,
        'glow-pos':    t.glowPosBox,
        'glow-neg':    t.glowNegBox,
        'glow-gold':   t.glowGoldBox,
      },
      dropShadow: {
        'glow-accent': t.glowAccentDrop,
        'glow-pos':    t.glowPosDrop,
        'glow-neg':    t.glowNegDrop,
        'glow-gold':   t.glowGoldDrop,
      },
      transitionTimingFunction: {
        ease: 'cubic-bezier(0.4, 0, 0.2, 1)',
      },
      keyframes: {
        shimmer: {
          '0%':   { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(calc(100vw + 60px))' },
        },
        fadein: {
          '0%':   { opacity: '0', transform: 'translateY(-6px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        scanline: {
          '0%':   { top: '-2px' },
          '100%': { top: '100%' },
        },
        ping: {
          '75%, 100%': { transform: 'scale(2)', opacity: '0' },
        },
        floatz: {
          '0%':   { opacity: '0',   transform: 'translateY(0px)' },
          '15%':  { opacity: '0.7'                               },
          '80%':  { opacity: '0.5', transform: 'translateY(-14px)' },
          '100%': { opacity: '0',   transform: 'translateY(-20px)' },
        },
        breathe: {
          '0%, 100%': { transform: 'scale(1)',    opacity: '0.85' },
          '50%':      { transform: 'scale(1.06)', opacity: '1'    },
        },
        radarRing: {
          '0%':   { transform: 'scale(0.12)', opacity: '0.75' },
          '70%':  { opacity: '0.18' },
          '100%': { transform: 'scale(1)',    opacity: '0' },
        },
        ecgScroll: {
          '0%':   { transform: 'translateX(0px)'    },
          '100%': { transform: 'translateX(-200px)' },
        },
      },
      animation: {
        shimmer:      'shimmer 1.6s ease-in-out infinite',
        fadein:       'fadein 0.15s ease-out forwards',
        scanline:     'scanline 3.5s linear infinite',
        floatz:       'floatz 2.6s ease-in-out infinite',
        breathe:      'breathe 3.5s ease-in-out infinite',
        'radar-ring': 'radarRing 2.8s cubic-bezier(0.2, 0.5, 0.5, 1) infinite',
        'ecg-scroll': 'ecgScroll 2s linear infinite',
      },
    },
  },
  plugins: [],
}
