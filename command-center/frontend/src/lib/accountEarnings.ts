import type { AccountEarnings } from '@/types'

/**
 * The NAME of the bot whose reading was taken as the account's opening balance, or `null`.
 *
 * 🔴 **The server sends the bot's KEY (`opening_from`), and the page printed it** — "recorded by
 * sos_fade_demo" (2026-09-11). A key is an identifier, not a name. The account's own earnings list
 * carries every bot that traded it, departed ones included, so the name is read from there.
 * ⚠ A key the list does not hold says nothing rather than printing the identifier.
 */
export function openingRecorder(e: AccountEarnings | undefined): string | null {
  if (!e?.opening_from) return null
  return e.bots.find((b) => b.bot_key === e.opening_from)?.name ?? null
}
