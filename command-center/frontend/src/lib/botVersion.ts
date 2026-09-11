import type { BotDeployedVersion, BotVersionCompare } from '@/types'

/**
 * Why a version READ failed, in the server's words — `null` when it did not fail.
 *
 * ⚠ ONE reading of the failure for the pill and the banner, so the two cannot name different
 * causes for one missing version. The server's `detail` when it sent one (`ApiError`), else the
 * error's own message.
 */
export function versionReadFailure(error: unknown): string | null {
  if (!error) return null
  const detail = (error as { detail?: unknown }).detail
  if (typeof detail === 'string' && detail) return detail
  return error instanceof Error ? error.message : String(error)
}

/**
 * The highest version a deploy could land NOW: the backtester's, less every commit touching this
 * bot that is not pushed. A deploy pulls on the trading box, which cannot fetch a commit that only
 * exists on this machine. `null` when the backtester's version is unknown.
 *
 * ⚠ ONE definition, read by the row's version pill and the deploy panel, so the two can never name
 * different targets for one deploy.
 */
export function deployableVersion(c: BotVersionCompare | null | undefined): number | null {
  if (!c || c.local_version == null) return null
  return c.local_version - (c.unpushed_commits?.length ?? 0)
}

/**
 * Would a deploy move this bot FORWARD?
 *
 * 🔴 **False when every version between the bot and the backtester is unpushed (2026-09-10).** The
 * panel offered "Deploy & restart v218 → v218" straight after a deploy that had worked, under a
 * heading saying the bot was still behind — a button that reinstalls what is running and restarts
 * the bot for nothing, and it read as the deploy being stuck. Pushing is the fix there, not deploying.
 */
export function deployWouldAdvance(c: BotVersionCompare | null | undefined): boolean {
  const to = deployableVersion(c)
  return to != null && c?.deployed_version != null && to > c.deployed_version
}

/**
 * Is the NEW code on disk while the OLD code is still trading?
 *
 * `running_hash` is what the live PROCESS stamped into its own `bot_state.json`; `hash` is what
 * the deployment record says is on disk. The process reports a 12-char prefix, so this compares
 * like for like.
 *
 * 🔴 **This lives here, alone, because TWO things need it and they are in different layers.**
 * `ConfigureTab.versionFlags` needs it to draw the badge; `useBotVersion` needs it to decide
 * whether the answer is still settling and therefore worth re-reading. A private copy in the hook
 * would be a second definition of the one state this page exists to report — and the two would
 * drift the moment either side learned something the other did not, leaving a badge that polls
 * for a condition it no longer draws (or worse, draws one it never polls for).
 *
 * ⚠ **It answers `false` for a version that could not be read.** Absent is not "settled" — but it
 * is not "pending" either, and the strip counts an unreadable record separately and says so. A
 * `true` here would make an unreachable box poll forever for an answer it cannot get.
 */
export function isRestartPending(v: BotDeployedVersion | undefined): boolean {
  if (!v) return false
  return !!(v.running_hash && v.hash && !v.hash.startsWith(v.running_hash))
}
