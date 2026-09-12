import { AlertTriangle, HelpCircle, Loader2, RotateCcw, Upload, WifiOff } from 'lucide-react'
import type { BotDeployedVersion } from '@/types'
import { Shimmer } from '@/components/Shimmer'
import { deployableVersion, deployWouldAdvance, versionReadFailure } from '@/lib/botVersion'

/**
 * ONE pill for "what version of this bot is deployed", used everywhere a bot is listed — so the
 * rows and the deploy panel cannot give two answers about one deployment.
 *
 * ⚠ **It reports the DEPLOYED version, never the local one.** The backtester's number appears only
 * inside the "behind" state, where it is the thing being subtracted.
 *
 * ⚠ **A version nobody could work out is never drawn as a number.** Never promoted, the deployed
 * commit not fetched here, no git: `v0` would be the reassuring answer to a question nobody could
 * answer. And a read that FAILED is "Unread", never "No version" — one is the box not answering,
 * the other is an answer.
 *
 * 🔴 **CALM WHEN CURRENT, AMBER WHEN IT NEEDS YOU (2026-09-12).** Up to date was a green pill with
 * a tick on every row, which is most of why the demo account read as "everything is green" (Aaron:
 * *"my eyes don't know where to go"*). Every state keeps the outline Aaron asked for on 2026-09-05
 * so the version still reads as a claim; only a state that needs a person is coloured.
 *
 * 🔴 **RESTART — the bot runs OLDER code than the box holds (2026-09-12).** The version counts the
 * strategy only, and the code that runs it (the part that talks to the broker and writes what this
 * page reads) moves only when the bot restarts — so the page said "up to date" over a live bot
 * eight fixes behind. `restart` is `restartReason`'s sentence; the caller decides, this draws.
 *
 * ⚠ **Order: deploying, loading, unread, unknown, behind, restart, not pushed, current.** Behind
 * wins over restart because a deploy restarts too; restart wins over not pushed because it is
 * something the bot needs, where not pushed is something this machine needs.
 *
 * ⚠ **It never wraps and sizes to its text** (`whitespace-nowrap`, `justify-self-start`) — in a
 * grid it stretched to the column, and at 92px the behind state broke onto two lines.
 */

const BASE =
  'inline-flex items-center gap-[4px] text-[11px] font-medium px-[7px] py-[2px] rounded-pill border cursor-default whitespace-nowrap justify-self-start'
const TONE = {
  quiet: 'text-text-secondary border-border-default',
  dim: 'text-text-tertiary border-border-default',
  warn: 'text-warn-text border-warn/50',
  busy: 'text-accent border-accent/50',
}

export function VersionPill({
  version,
  loading,
  deploying,
  error,
  restart,
}: {
  version: BotDeployedVersion | null | undefined
  /** The query has not answered yet. Distinct from "answered, cannot say" — one is a wait and
   *  the other is a finding, and an em-dash for both makes a slow fetch look like a fault. */
  loading?: boolean
  /** A deploy of this bot is running. Wins over every other state, `loading` included. */
  deploying?: boolean
  /** The read FAILED — the box could not be asked. The query's own error. */
  error?: unknown
  /** Why this running bot needs a restart to be on the code the box holds (`restartReason`), or
   *  `null`/absent when it does not. */
  restart?: string | null
}) {
  const c = version?.compare ?? null

  if (deploying) {
    const to = deployableVersion(c)
    return (
      <span
        data-testid="version-pill"
        data-state="deploying"
        title="A deploy of this bot is running. Open it to watch the steps."
        className={`${BASE} ${TONE.busy}`}
      >
        <Loader2 size={10} className="animate-spin" />
        Deploying{to != null ? ` v${to}` : ''}
      </span>
    )
  }

  // The first read is a SHAPE, not a word — the same height as the pill that will land here, so
  // the row does not move when the version answers. See `components/Shimmer.tsx`.
  if (loading) {
    return <Shimmer shape="pill" className="h-[22px] w-[64px] justify-self-start" />
  }

  // Only while there is no earlier reading — a failed REFETCH keeps the last good one on screen.
  const failed = versionReadFailure(error)
  if (!version && failed) {
    return (
      <span
        data-testid="version-pill"
        data-state="unread"
        title={`Could not reach the trading box to read this bot's version — ${failed}. It asks again on the next refresh.`}
        className={`${BASE} ${TONE.dim}`}
      >
        <WifiOff size={10} /> Unread
      </span>
    )
  }

  if (!c || !c.comparable || c.deployed_version === null) {
    return (
      <span
        data-testid="version-pill"
        data-state="unknown"
        title={c?.reason || 'Could not work out which version this bot is running.'}
        className={`${BASE} ${TONE.dim}`}
      >
        <HelpCircle size={10} /> No version
      </span>
    )
  }

  const behind = c.versions_behind ?? 0
  const label = `v${c.deployed_version}`

  if (behind > 0 && deployWouldAdvance(c)) {
    return (
      <span
        data-testid="version-pill"
        data-state="behind"
        title={
          `Deployed ${label}, backtester on v${c.local_version} — ` +
          `${behind} change${behind === 1 ? '' : 's'} to this bot's code waiting to go out. ` +
          `Deploy it from Configure.`
        }
        className={`${BASE} ${TONE.warn}`}
      >
        <AlertTriangle size={10} />
        {label} · {behind} behind
      </span>
    )
  }

  if (restart) {
    return (
      <span
        data-testid="version-pill"
        data-state="restart"
        title={`Deployed ${label}. ${restart}`}
        className={`${BASE} ${TONE.warn}`}
      >
        <RotateCcw size={10} />
        {label} · restart
      </span>
    )
  }

  if (behind > 0) {
    const n = c.unpushed_commits?.length ?? 0
    return (
      <span
        data-testid="version-pill"
        data-state="unpushed"
        title={
          `Deployed ${label} — everything that is pushed. Your backtester is on ` +
          `v${c.local_version}, and the ${n} newer commit${n === 1 ? '' : 's'} touching this bot ` +
          `${n === 1 ? 'is' : 'are'} only on this machine, so a deploy cannot reach ` +
          `${n === 1 ? 'it' : 'them'}. Push, then deploy.`
        }
        className={`${BASE} ${TONE.warn}`}
      >
        <Upload size={10} />
        {label} · not pushed
      </span>
    )
  }

  return (
    <span
      data-testid="version-pill"
      data-state="current"
      title={`Deployed ${label} — the same code the backtester runs.`}
      className={`${BASE} ${TONE.quiet}`}
    >
      {label}
    </span>
  )
}
