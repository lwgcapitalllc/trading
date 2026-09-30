import type { Page } from '@playwright/test'

/**
 * Serve `GET /bots/versions` — the rows' fleet version read (2026-09-24) — by asking the page's
 * OWN per-bot `/bots/{key}/version` route for every bot the page lists, and returning the map.
 *
 * ⚠ **Built out of the per-bot answers on purpose, never a second fixture.** The real route builds
 * each bot's entry with the same function as the per-bot read (`_build_version`), so a fleet
 * answer is exactly the per-bot answers side by side; composing it from each spec's own per-bot
 * mock keeps every existing scenario (a deploy that lands, a restart that settles, an unread
 * version) meaning the same thing on the row as on the panel. A bot whose per-bot read fails is
 * LEFT OUT, as the real route leaves out a bot the box did not answer for.
 *
 * ⚠ **The bot keys are taken from answers the page already received** (the account groups and
 * the snapshot), never asked for again: a check that HOLDS the snapshot would hang this route, and
 * an extra request would disturb the checks that count them. It waits for the account list once.
 * ⚠ A page that navigated away or a check that ended mid-read aborts the request quietly.
 */
export async function serveFleetVersions(page: Page) {
  const keys = new Set<string>()
  let accountsAnswered: () => void = () => {}
  const accounts = new Promise<void>((resolve) => (accountsAnswered = resolve))
  page.on('response', async (res) => {
    const path = new URL(res.url()).pathname
    if (path !== '/api/bots/accounts' && path !== '/api/bots/snapshot') return
    try {
      const body = await res.json()
      if (path === '/api/bots/accounts')
        for (const g of Array.isArray(body) ? body : [])
          for (const b of g.bots ?? []) keys.add(b.key)
      else for (const b of body?.bots ?? []) if (b.key) keys.add(b.key)
    } catch {
      // not JSON, or the page went away — nothing to learn from it
    }
    if (path === '/api/bots/accounts') accountsAnswered()
  })
  await page.route('**/api/bots/versions', async (route) => {
    await Promise.race([accounts, new Promise((r) => setTimeout(r, 5_000))])
    try {
      const all = await page.evaluate(
        async (list: string[]) => {
          const out: Record<string, unknown> = {}
          await Promise.all(
            list.map(async (k) => {
              try {
                const r = await fetch(`/api/bots/${encodeURIComponent(k)}/version`)
                if (r.ok) out[k] = await r.json()
              } catch {
                // left out — the real route leaves out a bot it could not read
              }
            })
          )
          return out
        },
        [...keys]
      )
      await route.fulfill({ json: all })
    } catch {
      await route.abort().catch(() => {})
    }
  })
}
