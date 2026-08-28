/**
 * The condition evaluator behind `show_if` and `disable_if` — pulled OUT of the editor so it can
 * be driven with nothing running.
 *
 * 🔴 IT LIVES HERE BECAUSE IT HAS A TWIN. `backend/services/stress_tester.py` evaluates the same
 * two schema keys, and the two have already disagreed in silence once: a fib level is the string
 * `"1.0"` in a dropdown and the number `1.0` in the Custom box, JS stringified them differently
 * from Python, and a toggle stayed live in exactly the configuration it exists to be dead in.
 * Nothing about that was visible on either side alone.
 *
 * So the cases live in ONE fixture, `tests/fixtures/param-conditions.json`, and both evaluators
 * are driven over it — `scripts/check_param_conditions.mjs` here, `test_param_gates.py` there.
 * A shape one side learns and the other does not now fails on the side that did not learn it.
 *
 * ⚠ Inside the editor this was unreachable from any test that did not boot a browser, which is
 * the reachability lesson `ChartPanel/tradeGeometry.ts` already carries: logic with no seam a
 * test can grab is logic nobody checks.
 */
import type { ParamCondValue } from '@/types'

/** A param's current value, as the editor holds it. */
export type ParamValue = number | boolean | string

/**
 * `null` unless the value is a NUMBER or a string that is one. Booleans are deliberately excluded
 * — `Number(false)` is 0, so a numeric param sitting at 0 would satisfy a `{flag: false}` gate.
 */
export function numeric(v: unknown): number | null {
  if (typeof v === 'boolean') return null
  if (typeof v === 'number') return Number.isFinite(v) ? v : null
  if (typeof v === 'string' && v.trim() !== '') {
    const n = Number(v)
    return Number.isFinite(n) ? n : null
  }
  return null
}

/**
 * 🔴 NUMBERS COMPARE AS NUMBERS, and it is not a nicety.
 *
 * A fib level is the string `"1.0"` in a dropdown and the number `1.0` in the Custom box, and
 * `String(1.0)` is `"1"` — so a stringified compare says a Custom level of 1.0 is not 1.0. That
 * left `exec_sl_deep` live in exactly the configuration it exists to be dead in, caught by
 * `param-gates.spec.ts` rather than by review. Python's `str(1.0)` is `"1.0"`, so the backend
 * mirror happened to be RIGHT while this side was wrong — two evaluators of one rule disagreeing
 * silently, which is why both got this function.
 *
 * Everything else (an enum, a bool, a time) falls back to the stringified compare, which is what
 * `show_if` has always used and why `1` and `"1"` match.
 */
export function sameValue(actual: ParamValue, want: string | number | boolean): boolean {
  const a = numeric(actual)
  const b = numeric(want)
  if (a !== null && b !== null) return a === b
  return String(actual) === String(want)
}

/**
 * One condition's right-hand side against one value. Three shapes, in the order they arrived.
 *
 * - a scalar — equality, via `sameValue`
 * - an array — any of them
 * - `{ gt: n }` — the value is a NUMBER strictly greater than n
 *
 * 🔴 THE COMPARISON SHAPE EXISTS BECAUSE SOME SWITCHES HAVE NO OFF VALUE TO NAME. A rule that
 * arms the stop after a move of N R is off at -1 and also off at 0, and on at every number above
 * — so the row it controls could not be gated by equality without listing every number that is
 * not off. Before this it simply was not gated, and the dependent row sat on screen under a
 * parent that was off, which is the exact defect the cascade exists to remove.
 *
 * ⚠ A NON-NUMBER NEVER SATISFIES `gt`, and a bool is not a number here (`numeric` refuses it) —
 * otherwise `true > 0` would quietly arm a numeric gate off a checkbox.
 * ⚠ Mirrored by `_want_holds` in `backend/services/stress_tester.py`. The two must not drift;
 * `backend/tests/test_param_gates.py` compares them on one fixture.
 */
export function wantHolds(actual: ParamValue, want: ParamCondValue): boolean {
  if (Array.isArray(want)) return want.some((x) => sameValue(actual, x))
  if (want !== null && typeof want === 'object') {
    if ('gt' in want) {
      const a = numeric(actual)
      const b = numeric(want.gt)
      return a !== null && b !== null && a > b
    }
    // An unknown operator must not read as "condition met" — that would SHOW a row a typo was
    // meant to hide, and nothing on screen would look wrong.
    return false
  }
  return sameValue(actual, want)
}

/**
 * Every condition must hold. Shared by `show_if` (to show) and `disable_if` (to disable).
 *
 * ⚠ AN EMPTY CONDITION HOLDS NOTHING, and it has to be said out loud because the natural spelling
 * gets it wrong: `Object.entries({}).every(...)` is `true`, so `{}` would have meant "every row
 * with an empty `disable_if` is dead" here while the python twin (`not cond` covers `{}`) said
 * the opposite. Caught by the shared fixture on the day it was written — no schema uses `{}`
 * today, so nothing on screen would have shown the disagreement until one did.
 */
export function condHolds(
  cond: Record<string, ParamCondValue> | undefined,
  read: (name: string) => ParamValue
): boolean {
  if (!cond || Object.keys(cond).length === 0) return false
  return Object.entries(cond).every(([k, want]) => wantHolds(read(k), want))
}
