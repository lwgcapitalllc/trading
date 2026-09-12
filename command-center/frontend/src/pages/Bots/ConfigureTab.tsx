import { useEffect, useState } from 'react'

import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  HelpCircle,
  Loader2,
  RotateCcw,
  Upload,
  WifiOff,
} from 'lucide-react'
import { useBotVersion, useStartPromoteJob } from '@/hooks/useBots'
import {
  deployableVersion,
  deployWouldAdvance,
  isRestartPending,
  restartReason,
  versionReadFailure,
} from '@/lib/botVersion'
import { Shimmer } from '@/components/Shimmer'
import { StepProgress, type Step } from '@/components/StepProgress'
import type { BotDeployedVersion, BotParamRow, BotPromoteJob, BotPromoteStage } from '@/types'

/**
 * The bot panel's money-path pieces: `VersionBanner` (deploy) and `ParamGroup` (the read-only
 * strategy settings). Risk per trade moved to `BotRiskEditor.tsx` on 2026-09-11, when it began
 * saving through the account's budget; the old `RuntimeEditor` and its modal confirm went with it. The file is named for the Configure tab it
 * used to be; that tab, its `BotPanel`, `DeployCard` and fleet strip rendered nothing after the
 * 2026-09-05 rebuild and were deleted on 2026-09-11.
 *
 * This replaced a risk-cap editor whose own footer said the values were "for monitoring
 * reference only": it wrote daily/weekly caps into config fields `algos/live/` does not
 * read. A control that does nothing is worse than no control, because it reads as cover.
 *
 * The editable/read-only split comes from the BACKEND (`services/bot_params.py`) and is
 * never inferred here — `row.editable` is the only thing this file trusts. Strategy
 * parameters are shown in full and locked: changing one means the bot is no longer the
 * bot that was backtested, and the `strategy_source_hash` pin exists to keep that true.
 *
 * ⚠ **Only the OPEN bot's controls exist in the DOM** (it was a flat stack of every bot's screen
 * until 2026-08-04, G11) — a Deploy button for a bot you did not pick is not there to be hit,
 * which no amount of spacing or confirmation copy can buy. The confirm step names the bot too.
 */

function fmt(v: unknown): string {
  if (v === null || v === undefined || v === '') return '—'
  if (typeof v === 'boolean') return v ? 'On' : 'Off'
  if (typeof v === 'number') return String(v)
  return String(v)
}

function Row({
  label,
  children,
  title,
}: {
  label: string
  children: React.ReactNode
  title?: string
}) {
  return (
    <div className="flex items-start justify-between gap-3 py-[5px]" title={title}>
      <span className="text-[11px] text-text-tertiary shrink-0">{label}</span>
      <span className="text-[11px] font-mono tabular-nums text-text-secondary text-right break-all">
        {children}
      </span>
    </div>
  )
}

// ── one reading of a deployment record ──────────────────────────────────────────
//
// The version banner's warnings derive from THIS function and nothing else. Two places counting
// "is this bot's deployment claim false" two ways is two answers that can disagree — the fleet
// strip and `DeployCard` did, before both were deleted on 2026-09-11.

type VersionFlags = {
  notFrozen: boolean
  snapshotModified: boolean
  restartPending: boolean
  driftCount: number
  behind: number
  /** Anything that makes this bot's version claim FALSE. `behind` is not one — the repo
   *  moving ahead of a deployment is the normal state of a bot nobody has promoted today. */
  anyWarn: boolean
}

export function versionFlags(v: BotDeployedVersion | undefined): VersionFlags | null {
  if (!v) return null
  const notFrozen = !v.frozen
  const snapshotModified = v.frozen && !v.snapshot_ok
  // 🔴 The predicate lives in `lib/botVersion`, not here, because `useBotVersion` reads it too —
  // it is what decides whether this record is still settling and worth re-reading. A copy here
  // would let the badge and the poll disagree about the one state this page exists to report.
  const restartPending = isRestartPending(v)
  const driftCount = v.params_drift.length
  return {
    notFrozen,
    snapshotModified,
    restartPending,
    driftCount,
    behind: v.commits_ahead,
    anyWarn: notFrozen || snapshotModified || restartPending || driftCount > 0,
  }
}

// ── "am I behind, and by how much" — the headline the page never had ────────────
//
// 🔴 The version row on the card below read `v0`, and it always would have: `strategy_version`
// is an int `algos/live/live_config.py` defaults to 0 and NOTHING writes. So the one question
// the Configure tab exists to answer had no answer on it — Aaron, 2026-08-07: *"I just wanna
// know what is the version that I have compiled in my backtester versus the version that is
// deployed... and if I'm behind, there should be a big nice button."*
//
// A version here is the number of commits that have touched this bot's trees, so the two
// numbers subtract to the work waiting to go out. Derivation and why not the lab's own
// content-addressed registry: `backend/services/bot_versions.py`.
//
// ⚠ This is the ONLY promote entry point on the page. The card below used to carry its own,
// and two controls firing one destructive action is two places for the confirmation copy, the
// disabled state and the preview gate to drift apart — on the one control that changes what a
// live account trades.
//
// 🔴 **ONE BUTTON AND ONE PROGRESS READOUT, SINCE 2026-09-10.** Aaron: *"a static disabled button
// doesn't catch my focus"* and *"I have to scroll down and there is another button to click to
// deploy and restart … I am only acting on one CTA and there is only 1 progress indicator."* It
// was a Deploy button that ran a dry-run preview, printed its output at the bottom of the panel,
// and put a SECOND button under that output; pressing it greyed out and said nothing for the
// 30–60 seconds the deploy took.
//
// ⚠ **The preview step was dropped, not hidden, and that is a decision about what it bought.** It
// showed `git pull` output nobody reads. What the reader decides on — the settings that would
// change and the code changes — is on this banner BEFORE the click. And the checks the preview ran
// (does it pull, does it build, does it import) are the same checks the real promote runs before it
// swaps anything, refusing and leaving the bot untouched if any fails — they are now the progress
// readout's first steps instead of a separate gate.
//
// ⚠ **A bot on a LIVE account still takes a second click, on the SAME button** — it re-labels
// itself and disarms after a few seconds. One place to act, one extra deliberate press where the
// money is real.
//
// ⚠ **The steps come from the backend job doing them** (`POST /bots/{bot}/promote/job`), never from
// a timer here, and the last one — the bot reporting the new code — is a measurement. The job is
// watched by the PAGE (`usePromoteJobs`) and handed in, so closing the drawer mid-deploy neither
// stops the watch nor loses the finish.
const STEP_LABEL: Record<BotPromoteStage['key'], string> = {
  pull: 'Pull code',
  build: 'Build & check',
  stop: 'Stop bot',
  start: 'Start bot',
  confirm: 'Running new code',
}

const STEP_DOING: Record<BotPromoteStage['key'], string> = {
  pull: 'Pulling the latest code onto the trading box.',
  build: 'Building the new version and checking it loads. The bot keeps trading until this passes.',
  stop: 'Asking the bot to stop. It finishes its current pass first.',
  start: 'Starting the bot on the new version.',
  confirm: 'Waiting for the bot to report that it is running the new version.',
}

function jobSteps(job: BotPromoteJob, target: number | null): Step[] {
  return job.stages.map((s) => ({
    key: s.key,
    label: s.key === 'confirm' && target != null ? `Running v${target}` : STEP_LABEL[s.key],
    state: s.state === 'unconfirmed' ? 'warn' : s.state,
    seconds: s.seconds,
  }))
}

export function VersionBanner({
  botKey,
  botLabel,
  job,
  live = false,
  liveBot,
  fetchedAt,
}: {
  botKey: string
  botLabel: string
  /** This bot's latest deploy job, from the page's watcher (`usePromoteJobs`). The banner does not
   *  poll for it itself: a second watcher is a second 1s timer, and one inside the drawer stops
   *  the moment the drawer closes. */
  job: BotPromoteJob | null | undefined
  /** The bot trades a LIVE account — its deploy takes a second, deliberate click. */
  live?: boolean
  /** The bot as the trading box last reported it — whether it runs, and for how long — so the
   *  banner can tell a process running older code than the box holds. */
  liveBot?: { status: string; uptime_seconds: number | null }
  /** When that report was taken — the same clock the row reads a restart off. */
  fetchedAt?: string
}) {
  const { data: v, isLoading, error, refetch, isFetching } = useBotVersion(botKey)
  const start = useStartPromoteJob()
  // The job this panel is showing. A deploy that is RUNNING is always shown; a finished one only
  // if this panel started it or watched it run — a result from hours ago is not news.
  const [shownJob, setShownJob] = useState<string | null>(null)
  // Where the deploy is heading, captured at the click. A version quoted from the payload AFTER
  // the deploy is a claim about the thing that just changed, so the step label uses the intent.
  const [target, setTarget] = useState<number | null>(null)
  const [armed, setArmed] = useState(false)
  const [showChanges, setShowChanges] = useState(false)
  // A FINISHED deploy shows its output only on request — after a success it is forty lines of
  // confirmation under a line that already said so. A failure keeps it open; the reason lives there.
  const [showOutput, setShowOutput] = useState(false)

  const running = job?.status === 'running'
  // A deploy found RUNNING (the drawer reopened mid-deploy) is adopted, so it stays on screen once
  // it finishes. Set during render, React's pattern for state derived from a changed input — an
  // effect would paint one frame without it first.
  if (running && job && job.job_id !== shownJob) setShownJob(job.job_id)
  // The live confirm disarms itself, so a stray click minutes later cannot be the second one.
  useEffect(() => {
    if (!armed) return
    const t = setTimeout(() => setArmed(false), 6_000)
    return () => clearTimeout(t)
  }, [armed])

  // No `running ||` here: the line above has already adopted any running job, so it would be a
  // branch nothing can reach — MEASURED, a mutation deleting it survived every check.
  const shown = job && job.job_id === shownJob ? job : null
  // ⚠ A job reads finished only once the page has re-read the version (`usePromoteJobs` holds it),
  // so nothing here guards the window where the numbers still describe the state BEFORE the deploy.
  const finished = shown && shown.status !== 'running' ? shown : null
  const busy = running || start.isPending
  const c = v?.compare ?? null

  // The first read is ~4.5s over SSH. It holds the banner's footprint as a shimmer rather than a
  // line of text, so the drawer does not jump when the answer lands. `components/Shimmer.tsx`.
  if (isLoading) {
    return <Shimmer shape="block" className="block w-full h-[58px]" />
  }

  // 🔴 The box could not be ASKED — said as that, never as "Version unknown", which is an answer
  // (2026-09-11). The read no longer toasts, so this is the one place its failure is told. No
  // deploy button: a deploy would reach the same box that just did not answer.
  const unread = versionReadFailure(error)
  if (!v && unread) {
    return (
      <div
        data-testid="version-banner"
        data-state="unread"
        className="flex items-start gap-[8px] text-[11px] leading-[1.5] text-text-secondary
                      bg-bg-surface-2 border border-border-subtle rounded-lg px-[14px] py-[12px]"
      >
        <WifiOff size={13} className="shrink-0 mt-[1px] text-text-tertiary" />
        <span className="min-w-0 flex-1">
          <strong className="text-text-primary">Could not read the version.</strong> The trading box
          did not answer — {unread}
        </span>
        <button
          type="button"
          onClick={() => refetch()}
          disabled={isFetching}
          className="shrink-0 text-[11px] font-medium text-accent-text hover:underline
                     disabled:opacity-50 disabled:no-underline"
        >
          {isFetching ? 'Asking…' : 'Try again'}
        </button>
      </div>
    )
  }

  // Every state that makes this unanswerable has its own fix and none of them is "deploy", so
  // the reason is rendered and no button is offered. A `0` here would read as UP TO DATE,
  // which is the most reassuring answer available and the one most likely to be wrong.
  if (!c || !c.comparable) {
    return (
      <div
        data-testid="version-banner"
        className="flex items-start gap-[8px] text-[11px] leading-[1.5] text-text-secondary
                      bg-bg-surface-2 border border-border-subtle rounded-lg px-[14px] py-[12px]"
      >
        <HelpCircle size={13} className="shrink-0 mt-[1px] text-text-tertiary" />
        <span>
          <strong className="text-text-primary">Version unknown.</strong>{' '}
          {c?.reason || 'Could not work out how this bot compares to the repo.'}
        </span>
      </div>
    )
  }

  const behind = c.versions_behind ?? 0
  const dirty = c.uncommitted_files.length
  // A pinned setting cannot move on a promote, so it is not part of "what would change" — it
  // is listed separately, because *your bot is holding this still* is the reassuring half of
  // the same question and dropping it makes "not affected" look like "not checked".
  const willChange = c.setting_changes.filter((s) => !s.stated)
  const pinned = c.setting_changes.filter((s) => s.stated)
  // `null` is "no upstream to ask" — not "everything is pushed". Both render nothing here, but
  // they must never be collapsed into one value upstream of this line.
  const unpushed = c.unpushed_commits ?? []
  // The highest version a promote could actually land right now. The button names THIS, not the
  // backtester's version — a promote pulls on the VPS and cannot reach an unpushed commit.
  const deployable = deployableVersion(c)
  const heading = deployable ?? c.local_version
  // 🔴 Behind, but only by unpushed commits: a deploy would reinstall what is running. The big
  // button and the "would change" list are withheld, and the heading says push is the fix.
  const advance = deployWouldAdvance(c)
  // 🔴 The code that RUNS the bot moved since it started (2026-09-12). The version counts the
  // strategy only, so this banner said "up to date" over a live bot eight fixes behind. A deploy
  // that would advance already says it, and a deploy on disk the process has not picked up is the
  // restart-pending warning below — this is the third case, and a re-deploy is its fix.
  const restart =
    running || start.isPending || isRestartPending(v) || (behind > 0 && advance)
      ? null
      : restartReason(v, liveBot, fetchedAt)

  const confirmState = finished?.stages.find((s) => s.key === 'confirm')?.state
  // The header is the loudest thing on the panel, so while a deploy is going it SAYS so — the
  // reader's eye lands on the heading before anything else.
  const deploying = running || start.isPending
  const failed = finished?.status === 'failed'

  const fire = () => {
    if (live && !armed) {
      setArmed(true)
      return
    }
    setArmed(false)
    setShowOutput(false)
    setTarget(heading ?? null)
    start.mutate({ botName: botKey }, { onSuccess: (j) => setShownJob(j.job_id) })
  }

  // ONE button. It is withdrawn while a deploy runs (the progress readout is the thing to look
  // at) and after a successful one (the header already says up to date); after a FAILED one it
  // comes back as the way to try again.
  const showButton = !deploying && (!finished || failed)
  const deployBtn = showButton && (
    <button
      data-testid="deploy-button"
      onClick={fire}
      disabled={busy}
      className={`inline-flex items-center gap-[6px] px-[14px] py-[7px] rounded-md font-medium
                  disabled:opacity-40 ${
                    armed
                      ? 'text-[12px] bg-amber-400/20 text-amber-300 hover:bg-amber-400/30 border border-amber-400/50'
                      : advance || failed || restart
                        ? 'text-[12px] bg-gold-text/20 text-gold-text hover:bg-gold-text/30 border border-gold-text/40'
                        : 'text-[10px] text-text-tertiary hover:text-text-secondary'
                  }`}
    >
      {armed ? (
        <AlertTriangle size={13} />
      ) : (
        <Upload size={advance || failed || restart ? 13 : 10} />
      )}
      {armed
        ? 'Click again — this bot trades real money'
        : failed
          ? 'Try again'
          : advance
            ? `Deploy & restart v${c.deployed_version} → v${heading}`
            : restart
              ? 'Re-deploy & restart'
              : 'Re-deploy'}
    </button>
  )

  // The one sentence under the progress bar: what the running step is doing, or how it ended.
  let caption: React.ReactNode = null
  let captionTone = ''
  if (shown && !finished) {
    const active = shown.stages.find((s) => s.state === 'active')
    caption = (
      <>
        {active ? STEP_DOING[active.key] : 'Starting…'}
        <span className="font-mono tabular-nums text-text-tertiary">
          {' '}
          · {Math.round(shown.seconds)}s
        </span>
      </>
    )
  } else if (finished && !failed) {
    if (!finished.result?.restarted) {
      caption = `Deployed — restart ${botLabel} to pick it up.`
      captionTone = 'text-amber-300'
    } else if (confirmState === 'unconfirmed') {
      // The deploy worked; the bot has not SHOWN it yet. Never green — that would claim a
      // measurement nobody took.
      caption = `Deployed and restarted, but ${botLabel} had not reported the new version when the check stopped waiting. Check the bot.`
      captionTone = 'text-amber-300'
    } else {
      caption = `Deployed — ${botLabel} restarted and reported the new version.`
      captionTone = 'text-pos-text font-semibold'
    }
  } else if (failed) {
    // `error` is the backend saying what state the failure left the bot in, which depends on the
    // step it hit. Without one the build REFUSED, and a refused promote touches nothing.
    caption =
      finished.error ??
      `Deploy refused — ${botLabel} is untouched and still on v${c.deployed_version}. The reason is in the output below.`
    captionTone = 'text-neg-text font-semibold'
  }

  return (
    /* `data-testid` is a declared TEST SEAM, and it is load-bearing rather than convenience:
       the Risk-per-trade card below carries its own `Deploy` button, so a page-wide
       "no deploy button" assertion passes on a broken banner too — the vacuous-locator trap
       this repo has now hit three times (`svg.first()` was the sidebar logo; a page-wide
       Retry matched the page header's own). */
    <div
      data-testid="version-banner"
      className={`rounded-lg border px-[14px] py-[12px] ${
        deploying
          ? 'bg-accent/[0.05] border-accent/40'
          : failed
            ? 'bg-neg-muted/30 border-neg-text/40'
            : behind > 0 || restart
              ? 'bg-amber-400/[0.07] border-amber-400/30'
              : 'bg-pos-muted/40 border-pos-text/25'
      }`}
    >
      <div className="flex items-start justify-between gap-[16px] flex-wrap">
        <div>
          <p
            data-testid="version-heading"
            className={`flex items-center gap-[7px] text-[13px] font-semibold ${
              deploying ? 'text-accent' : behind > 0 || restart ? 'text-amber-300' : 'text-pos-text'
            }`}
          >
            {deploying ? (
              <Loader2 size={14} className="animate-spin" />
            ) : restart ? (
              <RotateCcw size={14} />
            ) : behind > 0 && !advance ? (
              <Upload size={14} />
            ) : behind > 0 ? (
              <AlertTriangle size={14} />
            ) : (
              <CheckCircle2 size={14} />
            )}
            {deploying
              ? `Deploying ${botLabel}${(target ?? heading) != null ? ` → v${target ?? heading}` : ''}`
              : restart
                ? `${botLabel} is running older code`
                : behind > 0 && !advance
                  ? `${botLabel} has everything that is pushed`
                  : behind > 0
                    ? `${botLabel} is ${behind} version${behind === 1 ? '' : 's'} behind`
                    : `${botLabel} is up to date`}
          </p>
          <div className="flex items-center gap-[22px] mt-[9px] text-[11px]">
            <span className="text-text-tertiary">
              Deployed{' '}
              <span className="text-text-primary font-mono text-[13px]">v{c.deployed_version}</span>
              {v?.promoted_at ? (
                <span className="text-text-tertiary"> · {v.promoted_at}</span>
              ) : null}
            </span>
            <span className="text-text-tertiary">
              Backtester{' '}
              <span className="text-text-primary font-mono text-[13px]">v{c.local_version}</span>
            </span>
          </div>
          {restart && (
            <p
              data-testid="banner-restart"
              className="text-[11px] text-amber-400/90 mt-[8px] leading-[1.5] max-w-[440px]"
            >
              {restart}
            </p>
          )}
        </div>
        {deployBtn}
      </div>

      {/* THE progress readout — directly under the heading, so nobody scrolls to find where the
          deploy is. It stays after a deploy finishes, showing how each step ended, until Close. */}
      {shown && (
        <div className="mt-[12px] border-t border-border-subtle/60 pt-[12px]">
          <StepProgress
            testId="deploy-progress"
            steps={jobSteps(shown, target ?? (running ? heading : c.deployed_version))}
            caption={
              <span data-testid="deploy-caption" className={captionTone}>
                {caption}
              </span>
            }
          />
          {finished && (
            <>
              {finished.result?.output && (failed || showOutput) && (
                <pre
                  className="text-[10px] leading-[1.45] font-mono text-text-secondary mt-[10px]
                                whitespace-pre-wrap break-all max-h-[200px] overflow-y-auto
                                bg-bg-base/60 rounded p-[8px]"
                >
                  {finished.result.output}
                </pre>
              )}
              <div className="flex items-center gap-[8px] mt-[9px] flex-wrap">
                {!failed && finished.result?.output && (
                  <button
                    data-testid="deploy-output-toggle"
                    onClick={() => setShowOutput((s) => !s)}
                    className="text-[10px] px-[10px] py-[5px] rounded text-text-tertiary hover:text-text-secondary"
                  >
                    {showOutput ? 'Hide output' : 'Show output'}
                  </button>
                )}
                <button
                  onClick={() => {
                    setShownJob(null)
                    setShowOutput(false)
                  }}
                  className="text-[10px] px-[10px] py-[5px] rounded text-text-tertiary hover:text-text-secondary"
                >
                  Close
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {/* 🔴 **THE THREE WARNINGS THAT SAY THE HEADLINE ABOVE IS FALSE (restored 2026-09-06).**
          They lived in `DeployCard` and the fleet strip, and the tab collapse left both
          unrendered — so a bot promoted and never restarted showed a green *up to date* while
          the running process was still trading the old code, and nothing anywhere said so.

          ⚠ **This is the same failure as the four account warnings dropped on 2026-09-06**, one
          screen along: the CONTROL was carried across to the drawer and the checks on it were
          not. A panel that keeps the reassuring half of a claim and loses the contradicting half
          is worse than one that says nothing, because it is read as having checked.

          ⚠ **Derived from `versionFlags`, never re-derived here.** That function is the single
          answer to *is this bot's version claim false*, and its own note says three places
          counting it three ways is three answers that can disagree. */}
      {(() => {
        const f = versionFlags(v)
        if (!f) return null
        return (
          <>
            {f.restartPending && (
              <p
                data-testid="banner-restart-pending"
                className="text-[10px] text-amber-400/90 mt-[9px] leading-[1.5]"
              >
                <strong>Restart pending.</strong> The running process reports{' '}
                <span className="font-mono">{v?.running_hash}</span>, not the deployed one — the new
                version is on disk and the OLD one is still trading. It clears itself once the bot
                comes back, and this is re-read every 15s while it says so.
              </p>
            )}
            {f.snapshotModified && (
              <p
                data-testid="banner-snapshot-modified"
                className="text-[10px] text-amber-400/90 mt-[9px] leading-[1.5]"
              >
                <strong>Snapshot modified.</strong> The deployed files no longer match their record
                — they were edited in place, bypassing deploy. Deploy again to re-pin.
              </p>
            )}
            {f.notFrozen && (
              <p
                data-testid="banner-never-deployed"
                className="text-[10px] text-amber-400/90 mt-[9px] leading-[1.5]"
              >
                <strong>Never deployed.</strong> There is no pinned version, so it runs whatever is
                in the repo when it starts — a pull on the box changes what it trades.
              </p>
            )}
            {f.driftCount > 0 && (
              <p
                data-testid="banner-drift"
                className="text-[10px] text-amber-400/90 mt-[9px] leading-[1.5]"
                title={v?.params_drift.join('\n')}
              >
                <strong>
                  {f.driftCount} setting{f.driftCount === 1 ? '' : 's'} changed since deploy:
                </strong>{' '}
                <span className="font-mono">{v?.params_drift.join(', ')}</span>. They take effect at
                the next deploy, except risk per trade, which applies live.
              </p>
            )}
          </>
        )
      })()}

      {dirty > 0 && (
        <p
          className="text-[10px] text-amber-400/90 mt-[9px] leading-[1.5]"
          title={c.uncommitted_files.join('\n')}
        >
          Your backtester also has{' '}
          <strong>
            {dirty} edited file{dirty === 1 ? '' : 's'}
          </strong>{' '}
          {dirty === 1 ? 'that is' : 'that are'} not committed
          {dirty === 1 ? (
            <>
              {' '}
              (<span className="font-mono">{c.uncommitted_files[0]}</span>)
            </>
          ) : null}
          . Not in v{c.local_version}, so a lab run here is not testing what the bot has. Commit and
          push to deploy them.
        </p>
      )}

      {/* 🔴 The reason a successful deploy can leave a bot behind, and the page said nothing
          about it until 2026-08-14. A promote PULLS on the VPS, so the highest version it can
          ever reach is the one on the remote — a commit sitting unpushed here is unreachable
          however many times Deploy is pressed. `null` means there is no upstream to compare
          against and renders nothing; `[]` is the measured "all pushed" and renders nothing
          too. Only a real count speaks. */}
      {unpushed.length > 0 &&
        (advance || behind <= 0 ? (
          <p
            className="text-[10px] text-amber-400/90 mt-[9px] leading-[1.5]"
            title={unpushed.join('\n')}
          >
            <strong>
              {unpushed.length} commit{unpushed.length === 1 ? '' : 's'} touching this bot
              {unpushed.length === 1 ? ' is' : ' are'} not pushed.
            </strong>{' '}
            A promote pulls on the VPS, so it can only reach{' '}
            <span className="font-mono">v{deployable}</span>
            {deployable != null && c.local_version != null && deployable < c.local_version ? (
              <>
                {' '}
                — push first, or the bot lands {c.local_version - deployable} version
                {c.local_version - deployable === 1 ? '' : 's'} short of your backtester.
              </>
            ) : (
              '.'
            )}
          </p>
        ) : (
          // Every version the bot is behind is unpushed — so the heading above says push, and this
          // says exactly what to push, rather than the "can only reach vN" a deploy would land on.
          <p
            data-testid="banner-unpushed-only"
            className="text-[10px] text-amber-400/90 mt-[9px] leading-[1.5]"
            title={unpushed.join('\n')}
          >
            <strong>
              {unpushed.length} commit{unpushed.length === 1 ? '' : 's'} touching this bot{' '}
              {unpushed.length === 1 ? 'is' : 'are'} only on this machine
            </strong>
            , so the trading box cannot get {unpushed.length === 1 ? 'it' : 'them'} yet. Push, then
            deploy to reach <span className="font-mono">v{c.local_version}</span>.
          </p>
        ))}

      {/* What a deploy would change — read BEFORE the click, so it is withdrawn once a deploy is
          on screen: the question has moved to the progress readout, and after a finish these
          rows describe the state before it. ⚠ Gated on `advance`, not on being behind: when only
          unpushed commits are ahead, a deploy changes none of these. */}
      {advance && !shown && (
        <div className="mt-[11px] border-t border-amber-400/20 pt-[10px] space-y-[9px]">
          {willChange.length > 0 ? (
            <div>
              <p className="text-[10px] uppercase tracking-[0.4px] text-text-tertiary mb-[5px]">
                {willChange.length} setting{willChange.length === 1 ? '' : 's'} would change on this
                bot
              </p>
              {willChange.map((s) => (
                <div
                  key={s.name}
                  className="flex items-baseline gap-[8px] text-[11px] py-[2px]"
                  title={s.desc}
                >
                  <span className="text-text-secondary min-w-[150px]">{s.label}</span>
                  <span className="font-mono text-[10px] text-text-tertiary">
                    {s.is_new ? (
                      <em className="not-italic">not in v{c.deployed_version}</em>
                    ) : (
                      s.was
                    )}
                  </span>
                  <ArrowRight size={9} className="text-text-tertiary shrink-0" />
                  <span className="font-mono text-[10px] text-amber-300">{s.now}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-[11px] text-text-secondary">
              No settings change — this is a code update only.
            </p>
          )}

          {pinned.length > 0 && (
            <p className="text-[10px] text-text-tertiary leading-[1.5]">
              {pinned.length} other setting{pinned.length === 1 ? '' : 's'} changed in the repo but{' '}
              <strong>this bot pins {pinned.length === 1 ? 'it' : 'them'}</strong>, so{' '}
              {pinned.length === 1 ? 'it' : 'they'} will not move:{' '}
              {pinned.map((s) => `${s.label} (${s.was} → ${s.now})`).join(', ')}.
            </p>
          )}

          <button
            onClick={() => setShowChanges((s) => !s)}
            className="inline-flex items-center gap-[4px] text-[10px] text-text-tertiary hover:text-text-secondary"
          >
            {showChanges ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
            {c.changes.length} code change{c.changes.length === 1 ? '' : 's'}
          </button>
          {showChanges && (
            <div className="max-h-[200px] overflow-y-auto space-y-[3px] pl-[14px]">
              {c.changes.map((ch) => (
                <div key={ch.commit} className="text-[10px] leading-[1.45] text-text-secondary">
                  <span className="text-text-tertiary font-mono mr-[6px]">{ch.date}</span>
                  {ch.subject}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── read-only strategy parameters ───────────────────────────────────────────────

export function ParamGroup({ group, rows }: { group: string; rows: BotParamRow[] }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border-b border-border-subtle/60 last:border-b-0">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-2 py-[8px] text-left cursor-pointer"
      >
        <ChevronDown
          size={12}
          className={`text-text-tertiary transition-transform ${open ? '' : '-rotate-90'}`}
        />
        <span className="text-[11px] text-text-secondary">{group}</span>
        <span className="ml-auto text-[10px] text-text-tertiary">{rows.length}</span>
      </button>
      {open && (
        <div className="pb-[8px] pl-[20px]">
          {rows.map((r) => (
            <Row key={r.name} label={r.label} title={r.desc ?? undefined}>
              {fmt(r.value)}
              {r.unit ? ` ${r.unit}` : ''}
            </Row>
          ))}
        </div>
      )}
    </div>
  )
}
