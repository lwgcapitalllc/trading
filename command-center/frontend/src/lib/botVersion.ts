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

/** How far a restart may land after the start a version reading describes and still be that
 *  run — the start record is stamped before the connect and warm-up, uptime after them. */
const SAME_RUN_MS = 10 * 60_000

/**
 * Why this RUNNING bot needs a restart to be on the code the box holds — `null` when it does not,
 * when it is not running (a stopped bot loads the new code when it starts), or when it cannot be
 * told.
 *
 * 🔴 **Two causes, and the version number counts neither (2026-09-12).** A deploy landed on disk
 * and the process still runs the one before it (`isRestartPending`); or the RUNNER — the repo code
 * that talks to the broker and writes what this page reads — moved since the process started.
 * The version counts the strategy only, so the page said "up to date" over a bot eight fixes
 * behind.
 *
 * ⚠ **The reading must describe THIS process.** A version read before a restart still names the
 * old run's start, and without this check the row would go on asking for a restart it just had
 * until something re-read the version. The process's start is the snapshot's own — its time less
 * its uptime — so a process that started well after the reading's start is a newer run.
 */
export function restartReason(
  v: BotDeployedVersion | undefined,
  live: { status: string; uptime_seconds: number | null } | undefined,
  fetchedAt?: string
): string | null {
  if (!v || live?.status !== 'RUNNING') return null
  if (isRestartPending(v))
    return 'A new version is deployed on the box and this bot is still running the one before it. Restart it to switch.'
  const rc = v.running_code
  const n = rc?.changes_waiting
  if (!rc || n == null || n <= 0) return null
  if (live.uptime_seconds != null && rc.started_at) {
    const readStart = Date.parse(rc.started_at)
    const now = fetchedAt ? Date.parse(fetchedAt) : Date.now()
    const procStart = now - live.uptime_seconds * 1000
    if (
      Number.isFinite(readStart) &&
      Number.isFinite(procStart) &&
      procStart > readStart + SAME_RUN_MS
    )
      return null
  }
  // ⚠ RE-DEPLOY, not Restart: a plain restart starts whatever the box's checkout holds, and only a
  // re-deploy fetches the new code onto the box first.
  return (
    `${n} change${n === 1 ? '' : 's'} to the code that runs this bot ${n === 1 ? 'has' : 'have'} ` +
    'landed since it started. The version number counts only the strategy, so it does not show ' +
    `${n === 1 ? 'it' : 'them'}. Re-deploy to pick ${n === 1 ? 'it' : 'them'} up: that fetches ` +
    'the code onto the box and restarts the bot.'
  )
}
