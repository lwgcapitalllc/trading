import { useEffect, useRef, useState } from 'react'

/**
 * The value, held back until it has stopped changing for `ms`.
 *
 * Written for a query key built out of a form. TanStack keys on the whole body, so a body that is
 * rebuilt on every keystroke mints a key on every keystroke — and a `useQuery` fires once per key.
 * Typing `XAUUSD` into the stack modal's instrument field was six POSTs, five of them asking about
 * a symbol nobody had finished spelling.
 *
 * ⚠ It compares by JSON, not by reference. The callers here pass a fresh object literal out of a
 * `useMemo`, so a reference check would let a re-render with identical contents through and defeat
 * the whole thing. That also means it is only for SMALL, JSON-safe values — do not debounce a
 * payload with a curve in it.
 *
 * ⚠ The first value is delivered IMMEDIATELY (it is the initial state), so nothing waits `ms` to
 * see its first answer; only subsequent changes are held. A debounce that delayed the first render
 * would look exactly like a slow endpoint.
 */
export function useDebounced<T>(value: T, ms: number): T {
  const [held, setHeld] = useState(value)
  // The last value we PUBLISHED, so an unchanged re-render neither restarts the timer nor
  // schedules a redundant state write.
  const publishedRef = useRef(JSON.stringify(value))

  useEffect(() => {
    const next = JSON.stringify(value)
    if (next === publishedRef.current) return
    const t = setTimeout(() => {
      publishedRef.current = next
      setHeld(value)
    }, ms)
    return () => clearTimeout(t)
  }, [value, ms])

  return held
}
