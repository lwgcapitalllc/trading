import type { BotDeployedVersion } from '@/types'

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
