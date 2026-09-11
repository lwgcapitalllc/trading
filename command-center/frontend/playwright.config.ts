import { readdirSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { defineConfig, devices } from '@playwright/test'
import { APP_ORIGIN } from './tests/offlineApp'

/**
 * Browser tests for the command center.
 *
 * ⚠ These run against the RUNNING app — `./start.sh` first (backend on :8000, dev server on
 * :5173). There is deliberately no `webServer` block: this repo's backend talks to a live VPS
 * and a live MT5 terminal, and a test runner that boots it on demand is a test runner that can
 * start things on the trading box. Starting it is a person's decision.
 *
 * ⚠ `retries: 0` on purpose — a retry that turns a real flake green is how a broken page ships.
 *
 * TWO PROJECTS (2026-09-10), split by what a spec can reach:
 *
 * - **offline** — specs built on `tests/offline.ts`: every backend call is answered by the spec or
 *   a recording, and anything else is aborted and fails the check. Nothing is shared between two
 *   of them (each page has its own routes and its own clock), so they run FULLY PARALLEL.
 *   ✅ **They need NOTHING running**: the `offline-app` step builds this checkout once per run and
 *   the pages load it from disk (`tests/offlineApp.ts`) — no dev server, no backend.
 * - **chromium** — every other spec. These read the REAL backend and some write to the lab, so
 *   two at once would share one backend's state: **one worker, as before.**
 *
 * ⚠ **A spec is offline because it USES the harness, and that is discovered, never listed** — a
 * typed list is how a spec that reads the real backend ends up running beside itself.
 */
const TESTS = new URL('./tests/', import.meta.url)
const OFFLINE = readdirSync(TESTS)
  .filter((f) => f.endsWith('.spec.ts'))
  .filter((f) => readFileSync(new URL(f, TESTS), 'utf8').includes('offlineTest('))
  .map((f) => `**/${f}`)

// This run's own build folder (tests/offlineApp.ts). Set here, in the runner, so every worker
// inherits the SAME path — a worker re-reading this file keeps the inherited one.
process.env.LWG_OFFLINE_APP ??= join(tmpdir(), `lwg-offline-app-${process.pid}`)

export default defineConfig({
  testDir: './tests',
  workers: 6,
  retries: 0,
  timeout: 60_000,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:5173',
    viewport: { width: 1670, height: 940 },
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'offline-app', testMatch: /offline-app\.setup\.ts$/, teardown: 'offline-app-cleanup' },
    { name: 'offline-app-cleanup', testMatch: /offline-app\.teardown\.ts$/ },
    {
      name: 'offline',
      testMatch: OFFLINE,
      dependencies: ['offline-app'],
      fullyParallel: true,
      use: {
        ...devices['Desktop Chrome'],
        baseURL: APP_ORIGIN,
        // A third of every offline check's CPU went on recording a trace that a green run throws
        // away (MEASURED: 48s -> 32s). These checks replay recorded answers, so a failure repeats:
        // re-run that one check with `--trace on` to get its trace.
        trace: 'off',
        screenshot: 'only-on-failure',
      },
    },
    {
      name: 'chromium',
      testIgnore: OFFLINE,
      workers: 1,
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
