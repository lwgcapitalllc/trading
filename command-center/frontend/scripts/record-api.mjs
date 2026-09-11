#!/usr/bin/env node
/**
 * Record the backend's answers to a fixed list of READS, for a browser spec to replay offline.
 *
 *     node scripts/record-api.mjs tests/recordings/bots-page.json               # re-record its set
 *     node scripts/record-api.mjs tests/recordings/bots-page.json --add /bots/x  # and add a path
 *
 * 🔴 **THIS IS THE ONE STEP THAT TOUCHES THE REAL BACKEND, AND A PERSON RUNS IT.** Several of these
 * reads reach the trading box (the bot snapshot is an SSH round trip), which is exactly why the
 * specs replay a recording instead of asking. It sends GET and nothing else, to the paths named in
 * the file, so it cannot write anything anywhere.
 *
 * ⚠ **A recording is a claim about the backend's SHAPE that goes stale in silence** — the page
 * moves on, the file does not. `command-center/backend/tests/test_api_recordings.py` validates
 * every answer here against the response model its route declares, so a renamed field goes red in
 * the backend suite rather than as a confusing browser failure. Re-record when it does.
 *
 * ⚠ **Personal data is scrubbed before it is written** — see SCRUB. A recording is committed.
 *
 * ⚠ **One answer per LINE, not indented.** A chart spec is ~4 MB, and indenting it doubled the file
 * in whitespace; one line per answer keeps a re-record's diff to the answers that moved. It is
 * why `.prettierignore` names this folder — the commit hook would re-indent it.
 */
import { readFileSync, writeFileSync, existsSync } from 'node:fs'

const API = process.env.LWG_API ?? 'http://localhost:8000'

/** Paths whose answers name people. Replaced with one placeholder of the same shape. */
const SCRUB = {
  '/bots/users': (rows) =>
    rows.slice(0, 1).map((r) => {
      const out = {}
      for (const [k, v] of Object.entries(r))
        out[k] = typeof v === 'string' ? `user-${k}` : typeof v === 'number' ? 1 : v
      return out
    }),
}

const [file, ...rest] = process.argv.slice(2)
if (!file) {
  console.error('usage: node scripts/record-api.mjs <recording.json> [--add /path ...]')
  process.exit(2)
}
const old = existsSync(file) ? JSON.parse(readFileSync(file, 'utf8')) : { answers: {} }
const paths = new Set(Object.keys(old.answers ?? {}))
for (let i = 0; i < rest.length; i++) if (rest[i] === '--add' && rest[i + 1]) paths.add(rest[++i])
if (paths.size === 0) {
  console.error('nothing to record: the file names no paths and no --add was given')
  process.exit(2)
}

const answers = {}
for (const p of [...paths].sort()) {
  const res = await fetch(API + p, { method: 'GET' }).catch((e) => ({
    ok: false,
    status: e.message,
  }))
  if (!res.ok) {
    console.error(`REFUSED to write a partial recording: GET ${p} -> ${res.status}`)
    process.exit(1)
  }
  const body = await res.json()
  answers[p] = SCRUB[p] ? SCRUB[p](body) : body
  console.log(`  recorded GET ${p}`)
}
const head = { ...old, recorded_at: new Date().toISOString() }
delete head.answers
const lines = Object.entries(answers).map(
  ([p, a]) => `    ${JSON.stringify(p)}: ${JSON.stringify(a)}`
)
const top = Object.entries(head).map(([k, v]) => `  ${JSON.stringify(k)}: ${JSON.stringify(v)},`)
writeFileSync(file, `{\n${top.join('\n')}\n  "answers": {\n${lines.join(',\n')}\n  }\n}\n`)
console.log(`wrote ${Object.keys(answers).length} answers to ${file}`)
