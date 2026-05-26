/** @type {import('tailwindcss').Config} */
// Generated from algos/command-center/../../../ui/tokens.css
// Keep in sync with tokens.css — do not edit colors/fonts/radii here directly.
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Surfaces
        'bg-base':      '#0e0f13',
        'bg-sunken':    '#15161c',
        'bg-surface':   '#181a20',
        'bg-surface-2': '#1f222a',
        'bg-hover':     '#252833',
        'bg-active':    '#2e313d',
        // Borders
        'border-subtle':  '#262932',
        'border-default': '#313542',
        'border-strong':  '#3d4250',
        // Text
        'text-primary':   '#e9eaf0',
        'text-secondary': '#9a9eb0',
        'text-tertiary':  '#5f6373',
        'text-inverse':   '#06201d',
        // Accent — teal
        accent:          '#2dd4bf',
        'accent-hover':  '#3fe0cc',
        'accent-muted':  '#10302c',
        'accent-text':   '#5fe3d2',
        // Gold
        gold:            '#d9a441',
        'gold-muted':    '#322a18',
        'gold-text':     '#e6bd6a',
        // Semantic
        pos:             '#34d399',
        'pos-muted':     '#0f3027',
        'pos-text':      '#6ee7b7',
        neg:             '#e2554f',
        'neg-muted':     '#361917',
        'neg-text':      '#f08982',
        warn:            '#d9a441',
        'warn-muted':    '#322a18',
        'warn-text':     '#e6bd6a',
        neutral:         '#6b7080',
        // Chart series
        'series-1':  '#2dd4bf',
        'series-2':  '#34d399',
        'series-3':  '#d9a441',
        'series-4':  '#3a9ad9',
        'series-5':  '#8b7ef5',
        'series-6':  '#e2554f',
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
        pop: '0 8px 24px rgba(0, 0, 0, 0.45)',
      },
      transitionTimingFunction: {
        ease: 'cubic-bezier(0.4, 0, 0.2, 1)',
      },
    },
  },
  plugins: [],
}
