/**
 * Record a narrated walkthrough of the Bots page — `node scripts/record_bots_demo.mjs`.
 *
 * Aaron, 2026-09-05: *"create a video on how I should be using [this] … maybe I need to do a
 * demo on this page using playwright because I don't know."* The page was rebuilt twice in two
 * days and the controls moved; a written list of them is the thing nobody reads.
 *
 * 🔴 **IT ONLY EVER CLICKS READ-ONLY CONTROLS, AND THAT IS ENFORCED HERE RATHER THAN REMEMBERED.**
 * This drives the REAL app, whose backend talks to the live trading box — a click on Stop,
 * Restart, Deploy or the account dropdown is a real action on a live account. `click()` below
 * refuses any target matching `FORBIDDEN` before it touches the page, so a careless step added
 * later fails loudly instead of stopping a bot to make a video look good.
 *
 * ⚠ **It is NOT a test and is deliberately not in `scripts/run_all_tests.sh`.** It asserts
 * nothing, it needs the app up, and a recorder that fails the gate because the fleet changed
 * shape is a recorder somebody deletes.
 *
 * ⚠ **The narration is injected into the PAGE, not burned in afterwards**, so there is no
 * encoder to install and the caption is always in step with what is on screen.
 *
 * Output: `.playwright-mcp/bots-demo/<name>.webm` (git-ignored scratch), path printed at the end.
 */
import { chromium } from 'playwright'
import { mkdirSync, readdirSync, renameSync } from 'node:fs'
import { join, resolve } from 'node:path'

const BASE = process.env.DEMO_BASE ?? 'http://localhost:5173'
const OUT = resolve(process.cwd(), '../../.playwright-mcp/bots-demo')
const SIZE = { width: 1600, height: 900 }

/** Anything that acts on a live bot or a live account. Matched against the SELECTOR string. */
const FORBIDDEN = /stop|restart|start|deploy|promote|delete|remove|save|account-select|cap-save/i

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function main() {
  mkdirSync(OUT, { recursive: true })
  const browser = await chromium.launch()
  const ctx = await browser.newContext({
    viewport: SIZE,
    recordVideo: { dir: OUT, size: SIZE },
    deviceScaleFactor: 1,
  })
  const page = await ctx.newPage()

  const say = async (title, body, ms = 3400) => {
    await page.evaluate(
      ([t, b]) => {
        let el = document.getElementById('__demo_caption')
        if (!el) {
          el = document.createElement('div')
          el.id = '__demo_caption'
          el.style.cssText = [
            'position:fixed',
            'left:50%',
            'bottom:34px',
            'transform:translateX(-50%)',
            'z-index:2147483647',
            'max-width:900px',
            'padding:14px 20px',
            'border-radius:12px',
            'background:rgba(8,8,16,.94)',
            'border:1px solid #2c2c48',
            'box-shadow:0 10px 40px rgba(0,0,0,.6)',
            'font:13.5px/1.55 ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif',
            'color:#c2c6d8',
            'text-align:center',
            'pointer-events:none',
            'transition:opacity .25s',
          ].join(';')
          document.body.appendChild(el)
        }
        el.style.opacity = '1'
        el.innerHTML =
          `<div style="color:#00e5ff;font-weight:600;letter-spacing:.4px;` +
          `text-transform:uppercase;font-size:10.5px;margin-bottom:5px">${t}</div>${b}`
      },
      [title, body]
    )
    await sleep(ms)
  }

  /** Click, but refuse anything that could act on a live bot. */
  const click = async (selector, label) => {
    if (FORBIDDEN.test(selector))
      throw new Error(`demo refused a live-action target: ${label ?? selector}`)
    await page.locator(selector).first().click()
    await sleep(700)
  }

  await page.goto(`${BASE}/bots`, { waitUntil: 'networkidle' })
  await page.waitForSelector('[data-testid="account-card"]', { timeout: 30_000 })
  await sleep(1200)

  await say(
    'The Bots page',
    'One list. <b>Accounts are headings, bots are rows.</b> There are no tabs any more — everything you can change lives behind the thing it belongs to.'
  )

  await say(
    'The top line',
    'How many bots are running, the money across all accounts, and what the fleet is up. The net is summed <b>per account</b> — two bots on one balance share one pot, so adding them would count the same money twice.'
  )

  await say(
    'The account heading',
    'Broker, type, account number, and the risk ceiling. Then the balance, and a green pill: <b>what this account is up since it opened</b>. Hover the pill and it tells you the opening balance and which bot recorded it.'
  )

  await say(
    'A bot row',
    'A coloured bar for identity, a dot for running, the name, and then <b>what that bot itself has made</b> — its own closed trades, never the account’s growth.'
  )

  await say(
    'This is the part that changed',
    'A bot deployed yesterday used to show the same +45% as a bot that had been trading for a month. Now each row shows only its own trades. <b>Extreme Leg reads "no record yet" because it has not closed one.</b>'
  )

  await say(
    'The bar at the bottom',
    'Where the account’s growth actually came from. <b>SOS Fade made 26% of it. The other 74% was not from these bots</b> — a manual fill, a deposit, or a trade older than the record.',
    4600
  )

  await say(
    'To configure a bot',
    'Click its <b>name</b>, or the sliders button on the right of its row. Both open the same panel.'
  )

  await click('[data-testid="bot-row"] button:has-text("SOS Fade")', 'open the SOS Fade drawer')
  await sleep(900)

  await say(
    'Everything about one bot',
    'Start / Stop / Restart / Logs at the top. Then <b>what it has made</b>, <b>risk per trade</b>, <b>which version is deployed</b>, and <b>which account it trades</b>.'
  )

  await say(
    'Risk per trade',
    'Type a new number and press Deploy. It shows you the dollars that percentage is worth at today’s balance before you commit to it.'
  )

  await say(
    'Version',
    'Says whether the bot is on the same version as your backtester, and how far behind if not. <b>This is the only Deploy button on the page</b> — there is deliberately not a second one.'
  )

  const details = page.locator('summary:has-text("Details")')
  if (await details.count()) {
    await details.first().click()
    await sleep(900)
    await say(
      'Details holds the rest',
      'Where it trades, and every strategy parameter. Also <b>why the risk is what it is</b> — the measured reasoning, out of the way but never deleted.'
    )
    await page.mouse.wheel(0, 420)
    await sleep(1400)
    await page.mouse.wheel(0, -420)
  }

  await click('button[aria-label="Close"]', 'close the drawer')

  await say(
    'The account panel',
    'Click the account heading instead of a bot. Balance, the risk cap you can edit, which bots are on it, and a button to backtest them together as a stack.'
  )
  await click('[data-testid="account-card"] > button', 'open the account drawer')
  await sleep(2600)
  await click('button[aria-label="Close"]', 'close the account drawer')

  await say(
    'Accounts with nothing on them',
    'One line each at the bottom. They stay visible because you cannot move a bot onto an account you cannot see — but they do not earn a card.'
  )

  await say(
    'Fleet controls and scheduled jobs',
    'Not here. They live on <b>Overview</b>, because they act on every bot at once and mixing them in made each row’s own buttons look like a fleet kill.'
  )

  await say('That is the page', 'One list, one panel, and every number stated once on the thing it belongs to.', 3600)

  await ctx.close()
  await browser.close()

  const files = readdirSync(OUT).filter((f) => f.endsWith('.webm'))
  const newest = files.map((f) => ({ f, t: 0 })).pop()
  if (newest) {
    const dest = join(OUT, 'bots-walkthrough.webm')
    renameSync(join(OUT, newest.f), dest)
    console.log(`\nvideo: ${dest}`)
  } else {
    console.log('\nno video was written')
  }
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
