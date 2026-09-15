/**
 * Every strategy this fleet knows, as a standing row for the account panel's "Add bot" — never
 * one row per running copy, and never used up by being placed. See `AddBotPanel.tsx`.
 *
 * **Derived from data the page already has.** `useBotAccounts()` groups every bot by account
 * (`kind: 'account' | 'bench' | 'unknown'`) and `useRegisteredAccounts()` says which real account
 * number is demo or live — nothing here needs its own fetch, which is also why this whole page
 * needed no new endpoint for the LIST: only minting a fresh copy is a real write, and that is one
 * `POST` on the specific bot chosen as the source (`useCloneBot`).
 *
 * Pure, no React, no fetch — so the picking rule is testable without mocking a page.
 */
import type { BotAccountBot, BotAccountGroup, BotAccountRegistration } from '@/types'

export interface BotTemplateRow {
  strategyPackage: string
  display: string
  symbol: string
  riskPct: number | null
  /** The bot this row's numbers are read from right now — never shown as anything but a source. */
  sourceKey: string
  /** A real, already-idle copy of this strategy, if one happens to be sitting free. Placing THAT
   *  is the ordinary move-a-bot flow; its absence means placing this row clones `sourceKey` first. */
  existingBenchKey: string | null
}

/**
 * One row per `strategy_package` seen across every bot, live, demo or benched.
 *
 * **Sourced from whichever copy is most proven, not whichever group sorts first.** A strategy's
 * LIVE copy is its most current, most deliberately tuned configuration — CLAUDE.md calls this out
 * as "its live share" — so it outranks a demo copy, which sometimes trials a change the live bot
 * has not taken yet; a demo (or any other real account) outranks a benched copy, which may be old
 * and idle for reasons that have nothing to do with the strategy's current settings. A bot whose
 * config could not be read never wins — `unreadable` bots carry no `strategy_package` to key on.
 */
export function deriveTemplates(
  groups: BotAccountGroup[],
  accounts: BotAccountRegistration[]
): BotTemplateRow[] {
  const kindByAccount = new Map(accounts.map((a) => [a.account, a.kind]))

  const best = new Map<string, { priority: number; bot: BotAccountBot }>()
  const benchByPackage = new Map<string, string>()

  for (const g of groups) {
    if (g.kind === 'unknown') continue
    const priority = g.kind === 'bench' ? 0 : kindByAccount.get(g.account ?? -1) === 'live' ? 2 : 1
    for (const b of g.bots) {
      if (b.unreadable || !b.strategy_package) continue
      if (g.kind === 'bench' && !benchByPackage.has(b.strategy_package)) {
        benchByPackage.set(b.strategy_package, b.key)
      }
      const current = best.get(b.strategy_package)
      if (!current || priority > current.priority) {
        best.set(b.strategy_package, { priority, bot: b })
      }
    }
  }

  return [...best.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([strategyPackage, { bot }]) => ({
      strategyPackage,
      display: bot.display || strategyPackage,
      symbol: bot.symbol,
      riskPct: bot.risk_pct,
      sourceKey: bot.key,
      existingBenchKey: benchByPackage.get(strategyPackage) ?? null,
    }))
}
