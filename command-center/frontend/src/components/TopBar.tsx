import { useEffect, useState } from 'react'

// ── The affirmation ribbon ────────────────────────────────────────────────────
// Aaron's wording, in his order. Read every day this platform is opened, so it
// lives in the widest continuous space the shell has: the top bar, right of the
// wordmark, which the Refresh button vacated (it moved to the sidebar footer).
const AFFIRMATIONS = [
  'I AM A MULTI-MILLIONAIRE',
  'I AM ABUNDANTLY WEALTHY',
  'I AM FINANCIALLY FREE',
  'I AM GRATEFUL FOR ALL MY BLESSINGS',
  'I ATTRACT MONEY WHEREVER I GO',
  'I AM SUCCESS IN ALL ASPECTS OF MY LIFE',
]

// ── Why it animates the way it does ───────────────────────────────────────────
// The brief is that these register subconsciously, and that rules out the
// obvious treatment. CONTINUOUS motion — a looping shimmer, a pulsing glow —
// stops being seen within minutes: the eye adapts to steady motion and files it
// as background, and until it does, it competes with the numbers on the page
// underneath. Looping motion reads as decoration; motion that FINISHES reads as
// intent.
//
// So the whole budget goes on the ARRIVAL, and then the line holds perfectly
// still for its full turn:
//
//   · words fade up in sequence, so the line assembles at the pace of a voice
//     saying it — the eye travels along and READS it instead of glancing at a
//     block of text that appeared;
//   · the change itself is the attention cue. Most exposure to this bar is
//     peripheral, and peripheral vision is motion-sensitive but low-acuity, so
//     a moment of movement pulls the eye and big high-contrast type is what
//     rewards it;
//   · then nothing moves at all. Still, bright and unchanging for 20 seconds is
//     what makes a line readable enough to absorb — and identical every time it
//     comes round, which is what repetition needs to encode.
//
// The exit is a plain fade, deliberately duller than the entrance: two ends
// competing for attention would make the change feel like an effect.
const HOLD_MS = 20_000   // how long the finished line stays up, dead still
const WORD_MS = 520      // one word's fade-up
const STAGGER = 75       // gap between consecutive words
const EXIT_MS = 400      // the whole line fading out together

type Phase = 'enter' | 'in' | 'out'

function AffirmationRibbon() {
  const [idx, setIdx] = useState(0)
  const [phase, setPhase] = useState<Phase>('in')

  // Honour the OS setting: reduced motion keeps the change (a plain crossfade)
  // and drops the travel and the stagger.
  const [reduceMotion] = useState(
    () => typeof window !== 'undefined'
      && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true,
  )

  const words = AFFIRMATIONS[idx].split(' ')

  // enter → in, on the next painted frame (two rAFs: the first lands in the
  // frame the parked style is applied, the second is the first frame that can
  // animate away from it).
  //
  // ⚠ The timer beside them is not belt-and-braces, it is the fix for a real
  // stall: rAF does not fire in a BACKGROUND tab, while the timers driving the
  // rest of the cycle keep running. Left on rAF alone the ribbon parks in
  // `enter` — invisible — and stays there until the tab is looked at again.
  // Whichever fires first wins; the other is cleaned up.
  useEffect(() => {
    if (phase !== 'enter') return
    let inner = 0
    const outer = requestAnimationFrame(() => { inner = requestAnimationFrame(() => setPhase('in')) })
    const fallback = setTimeout(() => setPhase('in'), 80)
    return () => { cancelAnimationFrame(outer); cancelAnimationFrame(inner); clearTimeout(fallback) }
  }, [phase])

  // in → out, once the line has had its turn.
  useEffect(() => {
    if (phase !== 'in') return
    const t = setTimeout(() => setPhase('out'), HOLD_MS)
    return () => clearTimeout(t)
  }, [phase, idx])

  // out → the next line, parked ready to come up.
  useEffect(() => {
    if (phase !== 'out') return
    const t = setTimeout(() => {
      setIdx(i => (i + 1) % AFFIRMATIONS.length)
      setPhase('enter')
    }, EXIT_MS)
    return () => clearTimeout(t)
  }, [phase])

  // Per-word state. Only the ENTRANCE staggers — the exit takes the line away
  // as one piece, so leaving never performs.
  const wordStyle = (i: number): React.CSSProperties => {
    const rise = reduceMotion ? 0 : 10
    if (phase === 'enter') return { opacity: 0, transform: `translateY(${rise}px)`, transition: 'none' }
    if (phase === 'out') {
      return {
        opacity: 0,
        transform: 'translateY(0)',
        transition: `opacity ${EXIT_MS}ms ease-in`,
      }
    }
    const delay = reduceMotion ? 0 : i * STAGGER
    return {
      opacity: 1,
      transform: 'translateY(0)',
      transition:
        `opacity ${WORD_MS}ms cubic-bezier(0.16,1,0.3,1) ${delay}ms, ` +
        `transform ${WORD_MS}ms cubic-bezier(0.16,1,0.3,1) ${delay}ms`,
    }
  }

  return (
    // Absolutely positioned across the WHOLE bar, so the text sits on the bar's
    // true centre line. Laid out in the flex row instead, it would centre in the
    // space left over beside the wordmark — visibly right of centre.
    <div className="absolute inset-0 flex items-center justify-center px-6 select-none overflow-hidden pointer-events-none">
      {/* A still pool of warm light for the words to sit in. It does not pulse
          and it does not follow the message in and out: it is what makes the
          centre of the bar feel occupied, and anything that moved here would be
          the looping decoration this design is avoiding. */}
      <div
        aria-hidden
        className="absolute w-[min(760px,72%)] h-[40px] rounded-pill"
        style={{
          background: 'radial-gradient(ellipse at center, rgba(217,164,65,0.20) 0%, rgba(0,229,255,0.08) 48%, transparent 72%)',
          filter: 'blur(7px)',
        }}
      />

      {/* One solid, bright colour rather than a gradient across the line: the
          words animate individually, and a gradient can only span the whole line
          or restart per word. Legibility is the point here anyway — a flat warm
          gold on near-black holds its letterforms at a glance, which is what
          peripheral reading needs. */}
      <div
        className="relative flex items-baseline whitespace-nowrap gap-[0.4em] text-[17px] xl:text-[22px] font-black uppercase leading-none tracking-[1.5px] xl:tracking-[2.5px]"
        style={{
          color: '#f7d489',
          // Static glow: presence without smearing the edges of the letters.
          textShadow: '0 0 18px rgba(217,164,65,0.5), 0 0 40px rgba(0,229,255,0.18)',
        }}
      >
        {words.map((w, i) => (
          <span key={`${idx}-${i}`} className="inline-block" style={wordStyle(i)}>
            {w}
          </span>
        ))}
      </div>
    </div>
  )
}

export function TopBar() {
  return (
    <div
      className="h-[56px] flex-shrink-0 bg-bg-base flex items-center px-6 relative"
      style={{
        borderBottom: '1px solid rgba(0,229,255,0.18)',
        boxShadow: '0 1px 0 rgba(0,229,255,0.07), 0 4px 28px rgba(0,0,0,0.55)',
      }}
    >
      {/* Subtle left-side cyan wash */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{ background: 'linear-gradient(90deg, rgba(0,229,255,0.05) 0%, transparent 40%)' }}
      />

      {/* ── Brand wordmark ────────────────────────────────────────── */}
      {/* z-10 keeps it above the bar-wide ribbon layer, which is centred on the
          bar and therefore passes behind it at narrow widths. */}
      <div className="relative z-10 flex items-baseline gap-[6px] select-none flex-shrink-0">
        <span
          className="text-[23px] font-black tracking-tight leading-none"
          style={{
            background: 'linear-gradient(90deg, #00e5ff 0%, #d9a441 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
            filter: 'drop-shadow(0 0 8px rgba(0,229,255,0.6))',
          }}
        >
          TRADING
        </span>
        <span className="text-[23px] font-bold tracking-tight text-white leading-none">
          Operations
        </span>
      </div>

      {/* ── Affirmations ──────────────────────────────────────────── */}
      <AffirmationRibbon />
    </div>
  )
}
