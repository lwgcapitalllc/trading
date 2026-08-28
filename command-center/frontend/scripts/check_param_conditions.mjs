#!/usr/bin/env node
/**
 * The editor's half of the `show_if` / `disable_if` evaluator, pinned outside the browser.
 *
 * Run it:  node scripts/check_param_conditions.mjs
 *   Needs nothing running. It is step 9 of `scripts/run_all_tests.sh`.
 *
 * 🔴 WHY IT EXISTS. This rule has a TWIN in `backend/services/stress_tester.py::_want_holds`, and
 * the two have already disagreed in silence: a fib level is the string `"1.0"` in a dropdown and
 * the number `1.0` in the Custom box, `String(1.0)` is `"1"` in JS and `str(1.0)` is `"1.0"` in
 * Python, so one side said a Custom 1.0 was 1.0 and the other said it was not. A toggle stayed
 * live in exactly the configuration it exists to be dead in, and neither side looked wrong alone.
 *
 * So the CASES are the shared artifact, not the code: `tests/fixtures/param-conditions.json` is
 * read by this script and by `backend/tests/test_param_gates.py`, and both must answer the same.
 * A shape one side learns and the other does not fails on the side that did not learn it.
 *
 * ⚠ The module is TRANSPILED, never re-implemented. A check that restates the rule in its own
 * arithmetic passes against a module that disagrees with it, which is the one thing it is for.
 *
 * ⚠ NON-VACUITY IS BY MUTATION, and the map below was RUN rather than reasoned. That matters:
 * the first version of it was written from inspection and named the wrong cases for three of the
 * seven entries, every time in the flattering direction.
 *
 *   wantHolds:  drop the `gt` branch (fall through to equality) . 11 12 14 15 19 21, condHolds 1 3
 *   wantHolds:  `>=` instead of `>` ............................. 12 14
 *   wantHolds:  an unknown operator reads as MET ................ 22 23
 *   wantHolds:  drop the array branch ........................... 8
 *   wantHolds:  an empty array HOLDS (`every` for `some`) ....... 8 10
 *   sameValue:  drop the numeric branch ......................... 5 6
 *   condHolds:  forget the empty-object guard ................... condHolds 5
 *
 * 🔴 ONE GUARD NO MUTATION HERE CAN KILL, and it is named rather than left looking covered.
 * `numeric`'s boolean check is BEHAVIOURALLY DEAD IN JAVASCRIPT — `typeof true` is `'boolean'`,
 * so the number and string branches both refuse it and the function returns null with or without
 * the guard. It is not dead in Python, where `isinstance(True, int)` is True and dropping the
 * guard makes case 17 pass a checkbox into a numeric gate. The line stays because the two files
 * are read against each other and a missing guard on this side reads as a missing rule.
 *
 * ⚠ Cases 1 2 3 4 7 9 13 16 17 18 20 are killed by no mutation above and are listed rather than
 * quietly left in. Each is a DIRECTION check — the plain equality that must keep working while
 * the new shape lands, and the negative half of a case whose positive half is pinned. A case that
 * cannot go red is worth saying so about.
 *
 * ⚠ Case 5 is the ASYMMETRY this whole arrangement exists for: `1.0` against `"1.0"` dies here
 * when the numeric compare goes, and SURVIVES on the Python side, because `str(1.0)` is `"1.0"`
 * and `String(1.0)` is `"1"`. One evaluator was right by accident for months.
 */
import { readFileSync, writeFileSync, mkdtempSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { tmpdir } from 'node:os'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { transformSync } from 'esbuild'

const HERE = dirname(fileURLToPath(import.meta.url))
const SRC = join(HERE, '..', 'src', 'components', 'paramConditions.ts')
const FIXTURE = join(HERE, '..', 'tests', 'fixtures', 'param-conditions.json')

// The module imports a TYPE from '@/types'. `transformSync` erases type-only imports, so there is
// no alias to resolve at run time — but only because the import is `import type`. A value import
// added there would need a resolver here, and the failure would be an unhelpful MODULE_NOT_FOUND.
const js = transformSync(readFileSync(SRC, 'utf8'), { loader: 'ts', format: 'esm' }).code
const out = join(mkdtempSync(join(tmpdir(), 'paramcond-')), 'paramConditions.mjs')
writeFileSync(out, js)
const { wantHolds, condHolds } = await import(pathToFileURL(out).href)

const { cases } = JSON.parse(readFileSync(FIXTURE, 'utf8'))
let failed = 0

cases.forEach((c, i) => {
  const got = wantHolds(c.actual, c.want)
  if (got !== c.holds) {
    failed += 1
    console.log(
      `  \x1b[31m✗\x1b[0m #${i + 1} ${c.why}\n      ${JSON.stringify(c.actual)} vs ${JSON.stringify(
        c.want
      )} → got ${got}, want ${c.holds}`
    )
  }
})

// `condHolds` on top of it: EVERY key must hold, and an absent condition holds NOTHING.
// ⚠ The empty case is the dangerous direction — `Object.entries({}).every()` is true, so a
// `condHolds` that forgot its own `if (!cond)` guard would call every ungated row dead.
const read = (name) => ({ mode: 'Ticks', arm: 0.75, flag: false })[name]
const both = [
  [{ mode: 'Ticks', arm: { gt: 0 } }, true, 'every key holds'],
  [{ mode: 'Ticks', arm: { gt: 1 } }, false, 'one key fails and the whole condition fails'],
  [{ flag: false, arm: { gt: 0 } }, true, 'a bool key and a threshold key together'],
  [undefined, false, 'no condition at all HOLDS NOTHING — an ungated row stays live'],
  [{}, false, 'and neither does an empty one'],
]
both.forEach(([cond, want, why], i) => {
  const got = condHolds(cond, read)
  if (got !== want) {
    failed += 1
    console.log(`  \x1b[31m✗\x1b[0m condHolds #${i + 1} ${why}\n      got ${got}, want ${want}`)
  }
})

const total = cases.length + both.length
if (failed) {
  console.log(`\x1b[31m✗ param conditions: ${failed}/${total} failed\x1b[0m`)
  process.exit(1)
}
console.log(`\x1b[32m✓\x1b[0m param conditions: ${total} cases`)
