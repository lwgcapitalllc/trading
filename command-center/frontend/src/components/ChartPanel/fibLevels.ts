/**
 * Fibonacci LEVEL SET — the configurable ladder the fib tool draws, and where it is stored.
 *
 * `overlays.ts` owns how a level is DRAWN; this owns WHICH levels exist. They are split because
 * the ladder is now user-editable (add / remove / retune / recolour / hide a level, including
 * extensions past 1.0 and negatives), and that editing needs a home outside the render template.
 *
 * The ladder is a property of the TOOL, not of one drawing, so it PERSISTS to localStorage (the
 * same tiny getter/setter convention the app's other chart prefs use). A fib DRAWING is still
 * session-only — that is unchanged and deliberate: the levels are a setting, a drawing is work.
 */
import { DEFAULT_FIB_LEVELS, type FibLevel } from './overlays'

export type { FibLevel }
export { DEFAULT_FIB_LEVELS }

const STORE_KEY = 'chartpanel_fib_levels'

/** Colour a freshly added level starts on — the same neutral grey 0 and 1 use, so a new row
 *  reads as "not yet categorised" rather than claiming to belong to the entry or target band. */
export const NEW_LEVEL_COLOR = '#9598a1'

/** A corrupt or hand-edited store must not be able to spawn thousands of figures per fib. */
const MAX_LEVELS = 40

/** The common ladder an "Add level" pulls its next ratio from, in order. Everything the classic
 *  tool offers, retracements first then extensions — so adding a level lands on a real fib number
 *  instead of an arbitrary one, and repeated adds walk outward rather than piling on one value. */
const LADDER = [
  0.236, 0.382, 0.5, 0.618, 0.65, 0.702, 0.786, 0.886, 1, 1.128, 1.272, 1.414, 1.618, 2, 2.618,
]

/** Guard every path that reads levels from outside this module (localStorage today, anything
 *  later): each entry needs a finite ratio and a colour string, everything else is dropped. */
export function sanitizeFibLevels(raw: unknown): FibLevel[] | null {
  if (!Array.isArray(raw)) return null
  const out: FibLevel[] = []
  for (const item of raw) {
    if (typeof item !== 'object' || item === null) continue
    const { ratio, color, visible } = item as Record<string, unknown>
    if (typeof ratio !== 'number' || !Number.isFinite(ratio)) continue
    if (typeof color !== 'string' || color === '') continue
    out.push({ ratio, color, visible: visible === undefined ? true : visible === true })
    if (out.length >= MAX_LEVELS) break
  }
  return out
}

export function loadFibLevels(): FibLevel[] {
  try {
    const stored = localStorage.getItem(STORE_KEY)
    if (!stored) return DEFAULT_FIB_LEVELS
    const parsed = sanitizeFibLevels(JSON.parse(stored))
    // An EMPTY stored array is honoured (the user deleted every level); only a broken/absent
    // store falls back to the factory ladder.
    return parsed ?? DEFAULT_FIB_LEVELS
  } catch {
    return DEFAULT_FIB_LEVELS
  }
}

export function saveFibLevels(levels: FibLevel[]): void {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(levels.slice(0, MAX_LEVELS)))
  } catch {
    /* private mode / quota — the levels still work for this session */
  }
}

/** The ratio a new row should start on: the first ladder value not already in use, else one step
 *  beyond the deepest level present (so adding past 2.618 keeps walking out instead of stalling). */
export function nextFibRatio(levels: FibLevel[]): number {
  const used = new Set(levels.map((l) => l.ratio))
  const fresh = LADDER.find((r) => !used.has(r))
  if (fresh !== undefined) return fresh
  const max = levels.reduce((m, l) => Math.max(m, l.ratio), 0)
  return Math.round((max + 0.5) * 1000) / 1000
}

/** Two ladders are the same ladder when every level matches in ratio, colour AND visibility.
 *  Drives the "this drawing differs from your default" state in the editor. */
export function sameFibLevels(a: FibLevel[], b: FibLevel[]): boolean {
  if (a.length !== b.length) return false
  return a.every(
    (l, i) =>
      l.ratio === b[i].ratio &&
      l.color === b[i].color &&
      (l.visible !== false) === (b[i].visible !== false)
  )
}
