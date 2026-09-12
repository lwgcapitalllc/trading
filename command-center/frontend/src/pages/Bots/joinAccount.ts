/**
 * Putting a bot ON an account — the one function that does it, the ways to make room when its risk
 * does not fit, and the confirmation a live account needs. Shared by the account panel's Add bot
 * list and the bot panel's account selector, so adding from either side is one behaviour.
 *
 * 🔴 **A bot that did not fit used to be a dead end (2026-09-11).** The move was refused with the
 * sentence saying why, and fixing it took two writes on two panels in the right order — lower a
 * sibling's share or raise the cap, THEN move. The three ways out are now offered where the bot is
 * added, and each is carried out here in the order the server needs.
 *
 * ⚠ **Nothing here decides whether a bot fits.** The plan (`useJoinPlans` / `useFetchRiskPlan`) is
 * the server's answer, and the fixes it offers (`fit_cap`, `fit_shares`) are the server's numbers.
 * The one number read off the page is the account's served room, rounded DOWN to what a share holds.
 *
 * ⚠ **A LIVE destination is confirmed on screen before the move is sent**, and only then is
 * `confirm_live` sent — the server refuses a move onto a live account without it (409). The
 * confirmation names the account and says real money, because a colour alone is the one signal a
 * reader in a hurry does not stop for.
 *
 * ⚠ The buttons and the confirmation are in `JoinChoices.tsx`; this module holds the logic, so a
 * component file exports only components.
 */
import { useState } from 'react'
import { useAssignBotAccount, useSaveAccountRisk } from '@/hooks/useBots'
import type { BotAccountRiskPlan } from '@/types'

/** A percentage as a person reads it: `5%`, `6.67%`, and a dash for a figure nobody measured. */
export const pct = (v: number | null | undefined): string =>
  v == null || !Number.isFinite(v) ? '—' : `${+v.toFixed(2)}%`

/** How a bot joins an account. */
export type JoinChoice =
  /** At its own risk per trade — it fits, or the server is the gate. */
  | { kind: 'as-is' }
  /** At the room still free under the cap, instead of its own share. */
  | { kind: 'at-room'; riskPct: number }
  /** Raise the account's cap first, then join at its own share. */
  | { kind: 'raise-cap'; cap: number }
  /** Scale every bot's share to fit the cap — the joining bot's included. */
  | { kind: 'fit-all'; shares: Record<string, number> }

/**
 * The share a bot can join at, from the account's SERVED room: rounded DOWN to hundredths (what a
 * share holds), and `null` under the 0.1% a share may not go below. Rounding up would hand the bot
 * a sliver more than is free, which the server then refuses.
 */
export function roomShare(room: number | null | undefined): number | null {
  if (room == null || !Number.isFinite(room)) return null
  const r = Math.floor(room * 100 + 1e-9) / 100
  return r >= 0.1 ? r : null
}

/** One sentence saying what a choice will do — the line the live confirmation reads back. */
export function describeChoice(
  choice: JoinChoice,
  display: string,
  risk: number | null,
  plan?: BotAccountRiskPlan | null
): string {
  switch (choice.kind) {
    case 'as-is':
      return `Put ${display} on it at ${pct(risk)} a trade.`
    case 'at-room':
      return `Put ${display} on it at ${pct(choice.riskPct)} a trade, instead of ${pct(risk)}.`
    case 'raise-cap':
      return `Raise its cap to ${pct(choice.cap)}, then put ${display} on it at ${pct(risk)} a trade.`
    case 'fit-all': {
      const names = new Map((plan?.bots ?? []).map((b) => [b.key, b.display]))
      const list = Object.entries(choice.shares)
        .map(([k, v]) => `${names.get(k) ?? k} ${pct(v)}`)
        .join(', ')
      return `Scale every bot to fit its cap (${list}), then put ${display} on it.`
    }
  }
}

/**
 * Carry out a join: any budget write the choice needs FIRST, then the move. One function, so the
 * account panel and the bot panel cannot do it in different orders.
 *
 * ⚠ **The budget write comes first because the move checks the budget as it stands.** Moving first
 * would be refused for the very reason the choice exists to remove.
 * ⚠ **A failure stops the sequence and returns `false`** — the request has already toasted the
 * server's reason. A raised cap or lowered shares left behind by a move that then failed are both
 * the SAFE direction (less risk per trade, or a wider ceiling nothing uses yet), and both are
 * visible on the account panel.
 */
export function useJoinAccount() {
  const assign = useAssignBotAccount()
  const saveRisk = useSaveAccountRisk()
  const [pendingKey, setPendingKey] = useState<string | null>(null)

  const join = async ({
    account,
    botKey,
    display,
    choice,
    riskCapPct,
    live,
  }: {
    account: number
    botKey: string
    display: string
    choice: JoinChoice
    /** The FIRST bot's cap on an empty account; `undefined` everywhere else. */
    riskCapPct?: number | null
    /** Confirmed on screen for a live destination. */
    live: boolean
  }): Promise<boolean> => {
    setPendingKey(botKey)
    try {
      if (choice.kind === 'raise-cap') {
        await saveRisk.mutateAsync({ account, riskCapPct: choice.cap, quiet: true })
      } else if (choice.kind === 'fit-all') {
        const others = Object.fromEntries(
          Object.entries(choice.shares).filter(([k]) => k !== botKey)
        )
        if (Object.keys(others).length > 0)
          await saveRisk.mutateAsync({ account, shares: others, quiet: true })
      }
      await assign.mutateAsync({
        botKey,
        account,
        display,
        riskCapPct,
        riskPct:
          choice.kind === 'at-room'
            ? choice.riskPct
            : choice.kind === 'fit-all'
              ? choice.shares[botKey]
              : undefined,
        confirmLive: live || undefined,
      })
      return true
    } catch {
      return false
    } finally {
      setPendingKey(null)
    }
  }

  return { join, pendingKey, busy: pendingKey !== null }
}
