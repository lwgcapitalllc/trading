/** @type {import('tailwindcss').Config} */
// Theme source of truth. Edit colors/fonts/radii here; the prototype.html reflects the same palette.
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Surfaces — deep indigo-black (cyan/green glows pop against purple-dark)
        'bg-base':      '#080810',
        'bg-sunken':    '#0d0d1a',
        'bg-surface':   '#111120',
        'bg-surface-2': '#181828',
        'bg-hover':     '#1e1e3480',
        'bg-active':    '#222240',
        // Borders — indigo-tinted, slightly more visible
        'border-subtle':  '#1a1a2e',
        'border-default': '#222238',
        'border-strong':  '#2c2c48',
        // Text — unchanged; good contrast
        'text-primary':   '#e9eaf0',
        'text-secondary': '#9a9eb0',
        'text-tertiary':  '#5f6373',
        'text-inverse':   '#020e12',
        // Accent — electric cyan (was muted teal #2dd4bf)
        accent:          '#00e5ff',
        'accent-hover':  '#33ecff',
        'accent-muted':  '#002a33',
        'accent-text':   '#33ecff',
        // Gold
        gold:            '#d9a441',
        'gold-muted':    '#2a2010',
        'gold-text':     '#e6bd6a',
        // Semantic — brighter neon variants
        pos:             '#00ff7f',
        'pos-muted':     '#002618',
        'pos-text':      '#33ff99',
        neg:             '#ff3b5c',
        'neg-muted':     '#2d0a12',
        'neg-text':      '#ff6680',
        warn:            '#ffb300',
        'warn-muted':    '#2a1f00',
        'warn-text':     '#ffc933',
        neutral:         '#6b7080',
        // Chart series
        'series-1':  '#00e5ff',
        'series-2':  '#00ff7f',
        'series-3':  '#ffb300',
        'series-4':  '#4da6ff',
        'series-5':  '#a78bfa',
        'series-6':  '#ff3b5c',
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
        'glow-accent': '0 0 12px rgba(0, 229, 255, 0.35), 0 0 40px rgba(0, 229, 255, 0.14)',
        'glow-pos':    '0 0 12px rgba(0, 255, 127, 0.28), 0 0 40px rgba(0, 255, 127, 0.11)',
        'glow-neg':    '0 0 12px rgba(255, 59, 92,  0.35), 0 0 28px rgba(255, 59, 92, 0.12)',
        'glow-gold':   '0 0 12px rgba(217, 164, 65, 0.35), 0 0 28px rgba(217, 164, 65, 0.12)',
      },
      dropShadow: {
        // Apply with drop-shadow-glow-* — works on text, SVG, icons
        'glow-accent': ['0 0 5px rgba(0,229,255,1.0)',   '0 0 16px rgba(0,229,255,0.65)'],
        'glow-pos':    ['0 0 5px rgba(0,255,127,1.0)',   '0 0 16px rgba(0,255,127,0.65)'],
        'glow-neg':    ['0 0 5px rgba(255,59,92,1.0)',   '0 0 16px rgba(255,59,92,0.65)'],
        'glow-gold':   ['0 0 5px rgba(255,179,0,1.0)',   '0 0 16px rgba(255,179,0,0.65)'],
      },
      transitionTimingFunction: {
        ease: 'cubic-bezier(0.4, 0, 0.2, 1)',
      },
      keyframes: {
        shimmer: {
          '0%':   { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(calc(100vw + 60px))' },
        },
        // Address entry slides down and fades in
        fadein: {
          '0%':   { opacity: '0', transform: 'translateY(-6px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        // Horizontal glint that sweeps top-to-bottom across the scan feed
        scanline: {
          '0%':   { top: '-2px' },
          '100%': { top: '100%' },
        },
        // Subtle ping used for the running-state dot
        ping: {
          '75%, 100%': { transform: 'scale(2)', opacity: '0' },
        },
        // Z floats upward and fades — used for sleeping idle state
        floatz: {
          '0%':   { opacity: '0',   transform: 'translateY(0px)' },
          '15%':  { opacity: '0.7'                               },
          '80%':  { opacity: '0.5', transform: 'translateY(-14px)' },
          '100%': { opacity: '0',   transform: 'translateY(-20px)' },
        },
        // Slow breathing pulse for center dot in radar standby
        breathe: {
          '0%, 100%': { transform: 'scale(1)',    opacity: '0.85' },
          '50%':      { transform: 'scale(1.06)', opacity: '1'    },
        },
        // Radar ring — expands from center and fades (scanner standby)
        radarRing: {
          '0%':   { transform: 'scale(0.12)', opacity: '0.75' },
          '70%':  { opacity: '0.18' },
          '100%': { transform: 'scale(1)',    opacity: '0' },
        },
        // ECG scroll — tiles a repeating waveform, slides left at constant speed
        ecgScroll: {
          '0%':   { transform: 'translateX(0px)'    },
          '100%': { transform: 'translateX(-200px)' },
        },
      },
      animation: {
        shimmer:  'shimmer 1.6s ease-in-out infinite',
        fadein:   'fadein 0.15s ease-out forwards',
        scanline: 'scanline 3.5s linear infinite',
        floatz:      'floatz 2.6s ease-in-out infinite',
        breathe:     'breathe 3.5s ease-in-out infinite',
        'radar-ring': 'radarRing 2.8s cubic-bezier(0.2, 0.5, 0.5, 1) infinite',
        'ecg-scroll': 'ecgScroll 2s linear infinite',
      },
    },
  },
  plugins: [],
}
