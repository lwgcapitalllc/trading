/**
 * A bot's name as a person reads it where nothing else on screen says which account it is on:
 * `SOS Fade · LIVE`, `SOS Fade · demo`.
 *
 * 🔴 **Two copies of one strategy share a display name since 2026-09-11** (Aaron: *"it's a generic
 * strategy, not a demo specific strategy"*) — a name is the strategy, and demo or live belongs to
 * the account. So a risk-change confirmation or a deploy line naming only "SOS Fade" would not say
 * whether real money is involved. These are the same words every Telegram message uses
 * (`algos/shared/bot_state.labelled`), so the page and the phone agree.
 *
 * ⚠ **A bot on NO account keeps the plain name.** Its `account_type` is then only the registry's
 * hardcoded fallback — a guess about an account it is not on — and a tag built on a guess is the
 * one thing this must never print.
 */
export function botLabel(bot: {
  name: string
  account?: number | string | null
  account_type?: string | null
}): string {
  if (bot.account == null || String(bot.account).trim() === '') return bot.name
  if (bot.account_type === 'live') return `${bot.name} · LIVE`
  if (bot.account_type === 'demo') return `${bot.name} · demo`
  return bot.name
}
