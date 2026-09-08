#!/usr/bin/env node
/**
 * Every theme COLOUR a component names must exist in the palette.
 *
 * 🔴 **WHY THIS EXISTS.** The instrument dropdown shipped with `bg-bg-raised` as its background.
 * There is no such colour in `tailwind.config.js` — the palette is base / sunken / surface /
 * surface-2 — and **Tailwind drops a class it cannot resolve without a word**: no build error, no
 * console warning, no red test. The panel simply rendered with NO BACKGROUND, sixty instrument
 * rows drawn straight over the form underneath. The same file also carried `hover:text-danger-text`
 * (the colour is `neg-text`), which did nothing at all and looked like a hover somebody chose not
 * to style. Reported from the screen 2026-09-07 — *"the ui has bugs"*.
 *
 * 🔴 **The failure shape is the point, not the two typos.** A colour that does not exist and a
 * colour deliberately set to transparent are THE SAME THING on screen, so nothing in the running
 * app can tell you which one you wrote. That is this repo's rule 7 arriving in CSS: a class name is
 * a CLAIM about a definition somewhere else, and nothing was checking the definition was there.
 *
 * ⚠ **It only judges classes that are unambiguously naming a THEME colour** — the first or last
 * segment matches the palette's own naming, so `text-left`, `border-t`, `bg-black/60` and
 * `text-[11px]` are never candidates. That is deliberate: a check that fires on code which is fine
 * is a check people learn to dismiss, and a dismissed check is worth less than none.
 *
 * ⚠ **It reads the palette from `tailwind.config.js`**, never from a list typed in here. A second
 * copy of the colour names is the thing that goes stale, and it would go stale in the direction
 * that matters — a colour added to the theme would start failing this check.
 *
 * Run: node command-center/frontend/scripts/check_theme_tokens.mjs
 * Step 12 of `scripts/run_all_tests.sh`.
 *
 * ── Watched RED (mutation map, RUN not reasoned, 2026-09-07) ──────────────────────────────
 * Nine mutations, nine killed, each re-run AFTER the guard below was deleted — a fix that
 * reroutes a case can silently un-cover the branch that case used to exercise, and only
 * re-running the whole map shows it.
 *
 *  M1  restore `bg-bg-raised` in InstrumentPicker.tsx        → RED  names bg-raised
 *  M2  restore `hover:text-danger-text` in InstrumentPicker  → RED  names danger-text
 *  M3  rename `bg-surface-2` in tailwind.config.js           → RED  the picker now names a
 *                                                                  colour the palette lost
 *  M4  FIRST_SEGMENTS := empty set                           → RED  self-test misses bg-raised
 *  M5  LAST_SEGMENTS  := empty set                           → RED  self-test misses danger-text
 *  M6  accept every candidate (skip the `valid.has` test)    → RED  self-test: 9 findings, 6 of
 *                                                                  them healthy colours
 *  M8  stop stripping the border SIDE letter                 → RED  self-test: border-t-accent
 *                                                                  and border-l-border-default
 *                                                                  become false positives
 *  M9  judge every one-word class                            → RED  self-test: text-left,
 *                                                                  bg-black, text-base, border-t
 *  M10 scan without stripping comments                       → RED  this repo explains its dead
 *                                                                  colours in comments, so the
 *                                                                  documentation reads as defects
 *
 * (M7 was `drop the arbitrary-value guard` and it SURVIVED — see `isColourRef`.)
 */

import { readFileSync, readdirSync, statSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join, relative } from 'node:path'

const HERE = dirname(fileURLToPath(import.meta.url))
const ROOT = join(HERE, '..')
const SRC = join(ROOT, 'src')

const config = (await import(join(ROOT, 'tailwind.config.js'))).default
const valid = new Set(Object.keys(config.theme.extend.colors))
if (valid.size === 0) {
  console.error('theme tokens: the palette came back empty — the config shape must have moved')
  process.exit(1)
}

// The palette's own naming, derived from the palette. A class is only JUDGED when it looks like it
// is reaching for one of these; everything else is some other kind of utility and is left alone.
const FIRST_SEGMENTS = new Set([...valid].map((k) => k.split('-')[0]))
const LAST_SEGMENTS = new Set(
  [...valid].map((k) => k.split('-').at(-1)).filter((s) => !/^\d+$/.test(s))
)

// The utility prefixes that take a COLOUR. `shadow-` is deliberately absent: it resolves against
// boxShadow, so `shadow-glow-accent` is correct and would read as an unknown colour here.
const PREFIXES = ['bg', 'text', 'border', 'ring', 'fill', 'stroke', 'from', 'via', 'to', 'divide']
const CLASS_RE = new RegExp(`\\b(${PREFIXES.join('|')})-([A-Za-z0-9[\\]._-]+)`, 'g')

// `border-t-accent` colours ONE side. The side letter sits between the prefix and the colour, so
// it has to come off before the rest is judged — otherwise every directional border in the app
// reads as an unknown colour. (It did: 8 false positives on the first run.)
const SIDES = new Set(['t', 'b', 'l', 'r', 'x', 'y', 's', 'e'])

// The palette's one-word colours. Any OTHER single word — `base` in `text-base`, `tertiary`,
// `surface` — is some other utility's value, not a colour, and must not be judged.
const SINGLE_WORD = new Set([...valid].filter((k) => !k.includes('-')))

/** Is this class naming a theme colour at all?
 *
 * 🔴 **There was a guard here rejecting an arbitrary value (`text-[11px]`) and it was DELETED
 * because NO MUTATION COULD KILL IT.** An arbitrary value is one dash-segment, so the
 * single-word rule below already rejects every one of them, and removing the guard changed not
 * one finding across all 108 files. **A branch nothing can kill reads to the next person as a
 * covered branch** — the same call, for the same reason, as the ranking tier deleted from
 * `check_instrument_search.mjs`. */
function isColourRef(rest) {
  const segs = rest.split('-')
  if (segs.length === 1) return SINGLE_WORD.has(segs[0])
  return FIRST_SEGMENTS.has(segs[0]) || LAST_SEGMENTS.has(segs.at(-1))
}

/** The colour a class is reaching for, with any side letter removed. */
function colourOf(rest) {
  const segs = rest.split('-')
  return segs.length > 1 && SIDES.has(segs[0]) ? segs.slice(1).join('-') : rest
}

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walk(p, out)
    else if (/\.(tsx|ts)$/.test(name)) out.push(p)
  }
  return out
}

/** Blank out every comment, keeping the newlines so line numbers still point at real code.
 *
 * 🔴 **Comments EXPLAIN a dead colour; they do not cause one.** This repo writes the rule beside
 * the code, so the file that fixed `bg-bg-raised` names it in a `{/* … *\/}` block directly above
 * the fix — and a per-line strip cannot see that a line is the MIDDLE of one. It reported the
 * explanation as the defect, which is a check arguing with its own documentation. */
function stripComments(text) {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, ' '))
    .replace(/\/\/[^\n]*/g, '')
}

/** Every unknown colour reference in one blob of source, as `{ line, cls, colour }`. */
function scan(text) {
  const bad = []
  stripComments(text)
    .split('\n')
    .forEach((code, i) => {
      for (const [cls, , rest] of code.matchAll(CLASS_RE)) {
        const colour = colourOf(rest.replace(/\/\d+$/, '')) // an opacity suffix is not part of it
        if (!isColourRef(colour)) continue
        if (!valid.has(colour)) bad.push({ line: i + 1, cls, colour })
      }
    })
  return bad
}

// ── Self-test: prove the scanner can actually SAY NO ───────────────────────────────────────────
// Without this, an empty finding list means "the app is clean" and "the scanner is broken" at the
// same time — which is the exact defect this whole file exists to stop.
const PLANTED = `
  const wrong = "bg-bg-raised hover:text-danger-text border-t-bg-nope"
  const fine = "text-left border-t bg-black/60 text-[9px] text-base bg-bg-sunken text-warn-text"
  const alsoFine = "shadow-pop border-t-accent border-l-border-default from-bg-base text-text-tertiary"
`
const plantedBad = scan(PLANTED)
  .map((b) => b.colour)
  .sort()
const wantBad = ['bg-nope', 'bg-raised', 'danger-text']
if (JSON.stringify(plantedBad) !== JSON.stringify(wantBad)) {
  console.error(
    `theme tokens: the scanner failed its own self-test — expected ${JSON.stringify(wantBad)}, got ${JSON.stringify(plantedBad)}`
  )
  process.exit(1)
}

// ── The real scan ──────────────────────────────────────────────────────────────────────────────
let failures = 0
for (const file of walk(SRC)) {
  for (const { line, cls, colour } of scan(readFileSync(file, 'utf8'))) {
    console.error(
      `  ${relative(ROOT, file)}:${line}  ${cls} — “${colour}” is not a colour in this theme`
    )
    failures++
  }
}

if (failures > 0) {
  console.error(
    `\ntheme tokens: ${failures} class(es) name a colour the palette does not define.\n` +
      `Tailwind drops these silently, so the element renders with NO colour at all.\n` +
      `The palette is in command-center/frontend/tailwind.config.js.`
  )
  process.exit(1)
}

console.log(`theme tokens: OK — every colour class resolves (${valid.size} in the palette)`)
