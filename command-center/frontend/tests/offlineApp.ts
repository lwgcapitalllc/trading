/**
 * The app the OFFLINE specs load: a DEVELOPMENT build of this checkout, served from disk by the
 * page's own routes. No dev server, no backend, nothing listening.
 *
 * 🔴 **WHY.** Six workers loading the page from one dev server made that server the bottleneck: a
 * check took 1.3s on one worker and 5.1s on six, because every page asks it for hundreds of
 * separate modules. MEASURED 2026-09-11 on the two Bots specs (93 checks): 90s from the dev server,
 * 48s from this build, 32s with tracing off as well.
 *
 * 🔴 **A DEVELOPMENT build, never a production one, and `buildApp` REFUSES to hand over anything
 * else.** Production React drops StrictMode's double-run of every component, which is how a page
 * that does not clean up after itself gets caught — and the app is only ever run in development
 * (`./start.sh` runs the dev server). A production build would test an app nobody runs.
 *
 * ⚠ **Built once per run, into a folder only that run reads**, so two sessions sharing this clone
 * can run the specs at once, and an edit made mid-run cannot reach half the checks.
 */
import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { extname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { Route } from '@playwright/test'

/**
 * The origin the offline specs load the app from. Nothing on the network answers it: `.test` never
 * resolves, and every request to it is answered from disk. ⚠ **https, not http** — the browser gives
 * clipboard access only to a secure origin, and the Bots page copies logs; `localhost` counts as
 * secure, so on http a check would meet an API the real app has.
 */
export const APP_ORIGIN = 'https://app.test'

const ROOT = fileURLToPath(new URL('..', import.meta.url))

/** The folder this run's build lives in, set once by `playwright.config.ts` and inherited by workers. */
export function appDir(): string {
  const dir = process.env.LWG_OFFLINE_APP
  if (!dir)
    throw new Error(
      'LWG_OFFLINE_APP is not set — run the offline specs through playwright.config.ts'
    )
  return dir
}

/** React's development build carries its full error text; production swaps it for an error code. */
const DEV_REACT_MARKER = 'Invalid hook call'
/** A theme class the app shell uses. Tailwind emits only the classes it found in the source. */
const APP_CSS_MARKER = 'bg-bg-base'

function assetsContaining(dir: string, ext: string, text: string): boolean {
  return readdirSync(dir).some(
    (f) => f.endsWith(ext) && readFileSync(join(dir, f), 'utf8').includes(text)
  )
}

export async function buildApp(outDir: string): Promise<void> {
  const { build } = await import('vite')
  // Vite builds production React unless told otherwise, whatever the mode is called.
  process.env.NODE_ENV = 'development'
  // 🔴 Tailwind finds its config, and the source it scans, from the WORKING folder. Started anywhere
  // else it warns and emits a stylesheet with none of the app's classes (MEASURED: 70 KB -> 13 KB),
  // and an unstyled page can pass a check about what is hidden.
  process.chdir(ROOT)
  await build({
    root: ROOT,
    configFile: join(ROOT, 'vite.config.ts'),
    mode: 'development',
    logLevel: 'warn',
    build: {
      outDir,
      emptyOutDir: true,
      minify: false,
      reportCompressedSize: false,
      chunkSizeWarningLimit: Infinity,
    },
  })
  const assets = join(outDir, 'assets')
  if (!assetsContaining(assets, '.js', DEV_REACT_MARKER))
    throw new Error(
      `the offline build carries PRODUCTION React (no "${DEV_REACT_MARKER}" text in ${assets}) — ` +
        'StrictMode would be off, so the specs would check an app nobody runs'
    )
  if (!assetsContaining(assets, '.css', APP_CSS_MARKER))
    throw new Error(
      `the offline build's stylesheet has none of the app's classes (no ${APP_CSS_MARKER}) — ` +
        'Tailwind did not find its config, so the specs would check an unstyled page'
    )
}

/**
 * Answer one request for the app from this run's build. A path with no extension is a page route,
 * so it gets index.html; a missing file is `null`, for the caller to report.
 */
export function serveApp(route: Route, url: URL): Promise<void> | null {
  const dir = appDir()
  const file = extname(url.pathname) ? join(dir, url.pathname) : join(dir, 'index.html')
  if (!existsSync(file)) return null
  return route.fulfill({ path: file })
}
