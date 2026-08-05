import { defineConfig, devices } from '@playwright/test'

/**
 * Browser tests for the command center.
 *
 * ⚠ These run against the RUNNING app — `./start.sh` first (backend on :8000, dev server on
 * :5173). There is deliberately no `webServer` block: this repo's backend talks to a live VPS
 * and a live MT5 terminal, and a test runner that boots it on demand is a test runner that can
 * start things on the trading box. Starting it is a person's decision.
 *
 * ⚠ `workers: 1` and `retries: 0` on purpose. The tests intercept API routes and one of them
 * installs a FAKE CLOCK, so parallel workers would be several browsers disagreeing about what
 * time it is; and a retry that turns a real flake green is how a broken page ships.
 */
export default defineConfig({
  testDir: './tests',
  workers: 1,
  retries: 0,
  timeout: 60_000,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:5173',
    viewport: { width: 1670, height: 940 },
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
