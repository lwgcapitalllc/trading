import { useState } from 'react'

import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  GitCommitHorizontal,
  HelpCircle,
  Info,
  Lock,
  PackageCheck,
  Snowflake,
  RotateCcw,
  SlidersHorizontal,
  Upload,
} from 'lucide-react'
import {
  useBotParams,
  useSaveBotRuntime,
  useBotVersion,
  usePreviewPromote,
  usePromoteBot,
} from '@/hooks/useBots'
import { isRestartPending } from '@/lib/botVersion'
import type { BotDeployedVersion, BotParamRow, BotParamsView, BotStatus } from '@/types'

/**
 * What each live bot is actually configured with — and the one lever allowed to move
 * while it runs.
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
 * ── The layout is a MISCLICK guard, not a tidy-up (2026-08-04, closes G11) ─────────────
 *
 * This tab used to map over every registered bot and render a full screen each — risk
 * editor, Account, Deployed version, a 47-row parameter accordion — in a flat stack with
 * no selector. Nothing about it was single-bot by construction (every endpoint is keyed by
 * bot name), and that is exactly what made it dangerous: with three bots registered, the
 * Promote button you want sits between two identical ones you do not, a screen apart, on
 * a page where the wrong click deploys new code onto a live account.
 *
 * So the rail is the feature. **Only the selected bot's controls exist in the DOM** — a
 * Promote button for a bot you did not pick is not there to be hit, which is a property no
 * amount of spacing or confirmation copy can buy. The confirm step names the bot for the
 * same reason.
 */

function fmt(v: unknown): string {
  if (v === null || v === undefined || v === '') return '—'
  if (typeof v === 'boolean') return v ? 'On' : 'Off'
  if (typeof v === 'number') return String(v)
  return String(v)
}

function Card({
  title,
  children,
  right,
}: {
  title: string
  children: React.ReactNode
  right?: React.ReactNode
}) {
  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <p className="text-[9px] font-semibold uppercase tracking-[0.8px] text-gold-text">
          {title}
        </p>
        {right}
      </div>
      {children}
    </div>
  )
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

/** Risk % → dollars on the balance the bot last reported. */
function riskUsd(pct: number, balance: number | null): string {
  if (balance == null || !balance) return ''
  return `$${((balance * pct) / 100).toLocaleString(undefined, { maximumFractionDigits: 2 })}`
}

// ── one reading of a deployment record ──────────────────────────────────────────
//
// The fleet strip, the rail's warning marker and the card's own warning blocks all derive
// from THIS function and nothing else. Three places counting "is this bot's deployment
// claim false" three ways is three answers that can disagree, and the whole point of the
// strip is that it agrees with the card it sends you to.

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

// ── the fleet strip ─────────────────────────────────────────────────────────────
//
// G11's third point: "which bots are behind the repo, which have a restart pending" had no
// single home, even though the per-bot endpoint already returned all of it. It costs no
// extra fetch — the flat stack was already reading every bot's version to render every
// DeployCard, and these are the same cache entries.

/**
 * One count on the strip.
 *
 * 🔴 **A non-zero count is a BUTTON that selects the bot it is talking about.** Aaron, 2026-08-28,
 * reading `1 not frozen`: *"idk what that even means"*. The strip named a condition and a number
 * and nothing else — so answering *which bot?* meant clicking every row in the rail in turn, and
 * the sentence explaining the condition lives on the card you get to by doing that. The count now
 * takes you there, and the tooltip names the bots so the common case needs no click at all.
 *
 * ⚠ **Zero stays a plain `<span>`.** A button that navigates nowhere is the control this repo
 * keeps recording as worse than none — a reader presses it, nothing happens, and the honest
 * conclusion available to them is that the page is broken.
 */
function FleetCount({
  label,
  bots,
  tone,
  icon: Icon,
  title,
  onSelect,
}: {
  label: string
  /** The bots this count is ABOUT — `bots.length` is the number rendered, so a count can never
   *  disagree with the list behind it or send you to a bot it is not counting. */
  bots: BotStatus[]
  tone: 'warn' | 'neutral'
  icon: typeof AlertTriangle
  title: string
  onSelect: (key: string) => void
}) {
  const n = bots.length
  const hot = n > 0
  const cls = !hot
    ? 'border-border-subtle/60 text-text-tertiary'
    : tone === 'warn'
      ? 'border-warn/30 bg-warn-muted text-warn-text'
      : 'border-border-default text-text-secondary'
  const body = (
    <>
      <Icon size={10} className="shrink-0" />
      <span className="font-mono tabular-nums font-semibold">{n}</span>
      <span className="whitespace-nowrap">{label}</span>
    </>
  )
  const shape = `inline-flex items-center gap-[5px] text-[10px] px-[8px] py-[4px] rounded-md border ${cls}`

  if (!hot) {
    return (
      <span title={title} className={`${shape} cursor-default`}>
        {body}
      </span>
    )
  }
  const names = bots.map((b) => b.name).join(', ')
  return (
    <button
      type="button"
      onClick={() => onSelect(bots[0].key)}
      title={`${names} — ${title}`}
      className={`${shape} cursor-pointer hover:brightness-125`}
    >
      {body}
    </button>
  )
}

export function FleetStrip({
  bots,
  flags,
  unreadable,
  loading,
  rechecking,
  onSelect,
}: {
  bots: BotStatus[]
  flags: (VersionFlags | null)[]
  unreadable: number
  loading: boolean
  /** A version is being re-read RIGHT NOW. Distinct from `loading`, which is the first read. */
  rechecking: boolean
  onSelect: (key: string) => void
}) {
  const running = bots.filter((b) => b.status === 'RUNNING').length
  const live = bots.filter((b) => b.account_type === 'live').length
  const known = flags.filter((f): f is VersionFlags => f !== null)

  // Each count is the LIST of bots it is about, not a number counted separately from them —
  // so the figure on a chip and the bot it sends you to cannot come apart.
  const withFlag = (p: (f: VersionFlags) => boolean) =>
    bots.filter((_, i) => {
      const f = flags[i]
      return f !== null && p(f)
    })

  const clean = known.length > 0 && known.every((f) => !f.anyWarn)

  return (
    /* A declared TEST SEAM, for the reason `version-banner` carries one: the words on these chips
       ("restart pending", "behind repo") also appear in the DeployCard's own warnings further down
       the page, so a page-wide locator matches a card that is not this strip and passes against a
       broken one. */
    <div
      data-testid="fleet-strip"
      className="bg-bg-surface border border-border-subtle rounded-lg px-4 py-[11px] mb-4
                    flex items-center gap-x-[10px] gap-y-[8px] flex-wrap"
    >
      <div className="flex items-baseline gap-[6px] mr-[4px]">
        <span className="text-[9px] font-semibold uppercase tracking-[0.8px] text-gold-text">
          Fleet
        </span>
        <span className="text-[11px] text-text-secondary font-mono tabular-nums">
          {bots.length} {bots.length === 1 ? 'bot' : 'bots'}
        </span>
        <span className="text-[11px] text-text-tertiary">·</span>
        <span className="text-[11px] text-text-tertiary font-mono tabular-nums">
          {running} running
        </span>
        {live > 0 && (
          <>
            <span className="text-[11px] text-text-tertiary">·</span>
            <span className="text-[11px] font-mono tabular-nums text-warn-text">{live} live</span>
          </>
        )}
      </div>

      <div className="flex items-center gap-[6px] flex-wrap ml-auto">
        <FleetCount
          label="restart pending"
          bots={withFlag((f) => f.restartPending)}
          tone="warn"
          icon={RotateCcw}
          onSelect={onSelect}
          title="the new code is on disk and the OLD code is still trading. This clears itself once the bot comes back — the page re-checks every 15s while it says so."
        />
        {/* 🔴 It read `not frozen` until 2026-08-28, and that is a word about the MECHANISM
            (a promoted bot runs a frozen snapshot) rather than about what is true of the bot.
            Aaron: *"1 not frozen — idk what that even means"*. What it means to a reader is that
            this bot has never been deployed, so there is no pinned version and it runs whatever
            the repo says at the moment it starts. Say that. */}
        <FleetCount
          label="never deployed"
          bots={withFlag((f) => f.notFrozen)}
          tone="warn"
          icon={Snowflake}
          onSelect={onSelect}
          title="never promoted, so it has no pinned version — it runs whatever is in the repo when it starts, and a git pull changes what it trades. Deploy it."
        />
        <FleetCount
          label="snapshot edited"
          bots={withFlag((f) => f.snapshotModified)}
          tone="warn"
          icon={AlertTriangle}
          onSelect={onSelect}
          title="the deployed files no longer match their record — edited in place, bypassing promote."
        />
        <FleetCount
          label="settings changed"
          bots={withFlag((f) => f.driftCount > 0)}
          tone="warn"
          icon={SlidersHorizontal}
          onSelect={onSelect}
          title="config.json now states settings the deployment does not carry. They take effect at the next promote (risk % applies live)."
        />
        <FleetCount
          label="behind repo"
          bots={withFlag((f) => f.behind > 0)}
          tone="neutral"
          icon={GitCommitHorizontal}
          onSelect={onSelect}
          title="the repo has moved past this deployment. Normal — a bot runs what it was promoted at, not what the repo says today."
        />

        {/* A version that could not be READ is not a healthy one. Counting an unreadable
            record as clean is how a strip comes to say "all clear" about a bot it never
            reached — the same "no data is not the same as cannot ask" rule the MT5 link
            chip exists for. */}
        {unreadable > 0 && (
          <span
            title="Their deployment record could not be read from the VPS — this is unknown, not clean."
            className="inline-flex items-center gap-[5px] text-[10px] px-[8px] py-[4px] rounded-md
                       border border-border-default text-text-tertiary cursor-default"
          >
            <span className="font-mono tabular-nums font-semibold">{unreadable}</span> unreadable
          </span>
        )}
        {loading && <span className="text-[10px] text-text-tertiary">reading…</span>}
        {/* 🔴 A page that re-reads on its own has to SAY it is doing so, or the reader cannot
            tell a live number from a frozen one — and a strip that had gone stale after a
            promote is exactly what taught us that. `loading` is the FIRST read (there is
            nothing on screen yet); this is a re-read over numbers already showing, which is a
            different sentence for a different state. */}
        {!loading && rechecking && (
          <span className="text-[10px] text-text-tertiary">re-checking…</span>
        )}
        {!loading && !rechecking && unreadable === 0 && clean && (
          <span className="text-[10px] text-pos-text ml-[2px]">all deployments clean</span>
        )}
      </div>
    </div>
  )
}

function Warn({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="flex items-start gap-[6px] text-[10px] leading-[1.5] text-amber-400/90
                    bg-amber-400/[0.06] border border-amber-400/20 rounded px-[8px] py-[6px] mt-[8px]"
    >
      <AlertTriangle size={11} className="shrink-0 mt-[1px]" />
      <span>{children}</span>
    </div>
  )
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
export function VersionBanner({ botKey, botLabel }: { botKey: string; botLabel: string }) {
  const { data: v, isLoading, isFetching } = useBotVersion(botKey)
  const preview = usePreviewPromote()
  const promote = usePromoteBot()
  // 🔴 This was a bare `output: string | null`, so a FINISHED deploy rendered under the
  // preview's own caption ("nothing deployed yet") with the Deploy button still sitting
  // there — Aaron pressed Deploy, it worked, and the page gave him no way to tell. **A
  // panel that shows a result has to say which ACTION produced it**; the text alone cannot,
  // because promote.py's own output reads much the same either way.
  const [result, setResult] = useState<{
    kind: 'preview' | 'deploy'
    ok: boolean
    restarted: boolean
    output: string
  } | null>(null)
  const [showChanges, setShowChanges] = useState(false)
  // A FINISHED deploy shows its `<pre>` only on request. The output is the thing you read
  // while deciding whether to press the button and the thing you read when it FAILS — after a
  // success it is 40 lines of confirmation sitting under a green line that already said so,
  // holding the panel open in the shape it had before the deploy. A failure keeps it open.
  const [showOutput, setShowOutput] = useState(false)

  // 🔴 `usePromoteBot` invalidates this bot's version on success, so for the length of that
  // refetch EVERY number on this banner still describes the state BEFORE the deploy — the
  // versions behind, the settings that would change, and the Deploy button's own `v163 → v165`
  // label. Leaving the button live across that window is what makes a finished deploy read as
  // a pending one and invites a second press on stale data.
  const deployed = result?.kind === 'deploy' && result.ok
  const refreshing = deployed && isFetching
  const busy = preview.isPending || promote.isPending || refreshing
  // 🔴 A preview on screen means the question has MOVED to the confirm button below, and this
  // one has nothing left to do — pressing it re-runs the same dry run and re-renders the same
  // panel, which reads as *nothing happened*. Aaron, 2026-08-14: *"I click it. It just keeps
  // repeating the process over and over."* The two-step is the whole safety property of this
  // control, so exactly one of the two buttons may be live at a time; `Cancel` puts it back.
  const awaitingConfirm = result?.kind === 'preview'
  const c = v?.compare ?? null

  if (isLoading) {
    return (
      <div className="text-[11px] text-text-tertiary px-[14px] py-[12px]">checking versions…</div>
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
                      bg-bg-elevated border border-border-subtle rounded-lg px-[14px] py-[12px]"
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
  // The highest version a promote could actually land right now.
  const deployable = c.local_version == null ? null : c.local_version - unpushed.length

  const deployBtn = (
    <button
      onClick={() => {
        setResult(null)
        setShowOutput(false)
        preview.mutate(
          { botName: botKey },
          {
            onSuccess: (r) =>
              setResult({ kind: 'preview', ok: r.ok, restarted: false, output: r.output }),
          }
        )
      }}
      disabled={busy || awaitingConfirm}
      className={`inline-flex items-center gap-[6px] px-[14px] py-[7px] rounded-md font-medium
                  disabled:opacity-40 ${
                    behind > 0
                      ? 'text-[12px] bg-gold-text/20 text-gold-bright hover:bg-gold-text/30 border border-gold-text/40'
                      : 'text-[10px] text-text-tertiary hover:text-text-secondary'
                  }`}
    >
      <Upload size={behind > 0 ? 13 : 10} />
      {/* A greyed button still labelled `Deploy v164 → v167` reads as BROKEN rather than as
          done-its-part, and the reader's next move is to click it again — which is the report.
          The label names where the action went. */}
      {promote.isPending
        ? 'deploying…'
        : refreshing
          ? 'checking…'
          : preview.isPending
            ? 'working…'
            : awaitingConfirm
              ? 'checked — confirm below'
              : behind > 0
                ? `Deploy v${c.deployed_version} → v${c.local_version}`
                : 'Re-deploy'}
    </button>
  )

  return (
    /* `data-testid` is a declared TEST SEAM, and it is load-bearing rather than convenience:
       the Risk-per-trade card below carries its own `Deploy` button, so a page-wide
       "no deploy button" assertion passes on a broken banner too — the vacuous-locator trap
       this repo has now hit three times (`svg.first()` was the sidebar logo; a page-wide
       Retry matched the page header's own). */
    <div
      data-testid="version-banner"
      className={`rounded-lg border px-[14px] py-[12px] ${
        behind > 0
          ? 'bg-amber-400/[0.07] border-amber-400/30'
          : 'bg-pos-muted/40 border-pos-text/25'
      }`}
    >
      <div className="flex items-start justify-between gap-[16px] flex-wrap">
        <div>
          <p
            className={`flex items-center gap-[7px] text-[13px] font-semibold ${
              behind > 0 ? 'text-amber-300' : 'text-pos-text'
            }`}
          >
            {behind > 0 ? <AlertTriangle size={14} /> : <CheckCircle2 size={14} />}
            {behind > 0
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
        </div>
        {deployBtn}
      </div>

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
      {unpushed.length > 0 && (
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
      )}

      {behind > 0 && !refreshing && (
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

      {result && (
        <div className="mt-[11px] border-t border-border-subtle/60 pt-[9px]">
          {result.kind === 'deploy' ? (
            <p
              className={`flex items-center gap-[6px] text-[12px] font-semibold mb-[6px] ${
                result.ok ? 'text-pos-text' : 'text-neg-text'
              }`}
            >
              {result.ok ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}
              {/* 🔴 It named `c.local_version` — the BACKTESTER's version, i.e. what the reader
                  asked for rather than what landed. Those differ whenever the deploy could not
                  reach HEAD, which is exactly the unpushed case above: on 2026-08-14 this line
                  read "running v165" over a bot running v164. It is `deployed_version` now, and
                  it is withheld until the refetch answers — a version quoted from the pre-deploy
                  payload is a claim about the thing that just changed. */}
              {/* Terse on SUCCESS, explicit on FAILURE, and the asymmetry is the point. The
                  header directly above already reads "up to date · Deployed v168 · Backtester
                  v168", so naming the bot and the version again is the same fact three times
                  and it is what made a working confirmation read as complicated. A FAILURE has
                  no such header — the banner still describes the state before the attempt — so
                  it has to say the version itself. */}
              {result.ok
                ? result.restarted
                  ? 'Deployed and restarted'
                  : `Deployed — restart ${botLabel} to pick it up`
                : `Deploy failed — ${botLabel} is untouched and still on v${c.deployed_version}`}
            </p>
          ) : (
            <p className="text-[10px] uppercase tracking-[0.4px] text-text-tertiary mb-[6px]">
              Checked the code on the VPS — nothing deployed yet
            </p>
          )}
          {refreshing && (
            <p className="text-[10px] text-text-tertiary mb-[6px]">
              re-reading the deployed version…
            </p>
          )}
          {/* A preview's output IS the thing you read before deciding, and a failure's output is
              the only place the reason lives. A SUCCESS has already been summarised by the green
              line above, so it collapses behind a toggle — that `<pre>` holding the panel open in
              its pre-deploy shape is what made a finished deploy look like a pending one. */}
          {(result.kind === 'preview' || !result.ok || showOutput) && (
            <pre
              className="text-[10px] leading-[1.45] font-mono text-text-secondary
                            whitespace-pre-wrap break-all max-h-[200px] overflow-y-auto
                            bg-bg-base/60 rounded p-[8px]"
            >
              {result.output}
            </pre>
          )}
          <div className="flex items-center gap-[8px] mt-[9px] flex-wrap">
            {/* The deploy button exists ONLY on the preview. Leaving it up after a successful
                deploy is what made a finished promote read as a pending one. */}
            {result.kind === 'preview' && (
              /* The bot is NAMED on the button, not just above it. This is the one control on
                 the page that changes what a live account trades, and the reader arrived here
                 by clicking a rail row — the name is the thing being confirmed. */
              <button
                onClick={() =>
                  promote.mutate(
                    { botName: botKey, restart: true },
                    {
                      onSuccess: (r) =>
                        setResult({
                          kind: 'deploy',
                          ok: r.ok,
                          restarted: r.restarted,
                          output: r.output,
                        }),
                    }
                  )
                }
                disabled={busy}
                className="inline-flex items-center gap-[5px] text-[11px] px-[12px] py-[5px]
                           rounded bg-gold-text/20 text-gold-bright hover:bg-gold-text/30
                           border border-gold-text/40 disabled:opacity-40"
              >
                <PackageCheck size={12} /> Deploy &amp; restart{' '}
                <span className="font-mono">{botLabel}</span>
              </button>
            )}
            {deployed && (
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
                setResult(null)
                setShowOutput(false)
              }}
              className="text-[10px] px-[10px] py-[5px] rounded text-text-tertiary hover:text-text-secondary"
            >
              {result.kind === 'deploy' ? 'Close' : 'Cancel'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// `botKey` addresses the API and `botLabel` is what a human reads. They are separate props
// on purpose: a display name is the field somebody eventually renames, and a control that
// ACTS on a name acts on nothing the day it changes.
export function DeployCard({ botKey }: { botKey: string }) {
  const { data: v, isLoading } = useBotVersion(botKey)

  if (isLoading)
    return (
      <Card title="Deployed version">
        <Row label="">loading…</Row>
      </Card>
    )
  if (!v)
    return (
      <Card title="Deployed version">
        <Row label="">unavailable</Row>
      </Card>
    )

  const f = versionFlags(v)!

  return (
    <Card title="Deployed version">
      <Row label="Strategy">{fmt(v.strategy_package)}</Row>
      <Row label="Code hash" title={v.hash}>
        {v.hash ? v.hash.slice(0, 12) : '—'}
      </Row>
      <Row label="From commit">{fmt(v.commit)}</Row>
      <Row label="Deployed on">{fmt(v.promoted_at)}</Row>
      <Row label="Files">{v.files ? `${v.files} .py` : '—'}</Row>
      <Row label="Repo now">
        {fmt(v.repo_commit)}
        {f.behind > 0 ? ` · ${f.behind} ahead` : ' · same'}
      </Row>

      {/* "Not frozen" was the MECHANISM's word (a deployed bot runs a frozen snapshot), and it
          told a reader nothing about this bot. What is true of it is that nobody has ever
          deployed it, so it has no pinned version — say that, and the rest follows. */}
      {f.notFrozen && (
        <Warn>
          <strong>Never deployed.</strong> This bot has no pinned version — it imports straight from
          the repo working tree, so a pull changes what it trades and can stop it starting. Deploy
          it from the banner at the top of this page.
        </Warn>
      )}
      {f.snapshotModified && (
        <Warn>
          <strong>Snapshot modified.</strong> The deployed files no longer match their record —
          someone edited them in place, bypassing promote. Re-promote to re-pin.
        </Warn>
      )}
      {/* It says how it CLEARS, because it clears on its own and the page used not to notice —
          a badge that stayed put over a bot that had already come back is what sent somebody
          looking for a restart that had happened. See `useBotVersion`. */}
      {f.restartPending && (
        <Warn>
          <strong>Restart pending.</strong> The running process reports{' '}
          <span className="font-mono">{v.running_hash}</span>, not the deployed hash. The new
          version is on disk but the old one is still trading. This clears itself once the bot comes
          back — the page re-reads it every 15s while it says this.
        </Warn>
      )}
      {f.driftCount > 0 && (
        <Warn>
          <strong>{f.driftCount} setting(s) changed since deploy:</strong>{' '}
          <span className="font-mono">{v.params_drift.join(', ')}</span>. They take effect at the
          next promote, except risk % which applies live.
        </Warn>
      )}

      <p className="text-[10px] text-text-tertiary mt-[8px] leading-[1.5] border-t border-border-subtle/60 pt-[8px]">
        This bot runs a frozen copy of its code. Pulling, backtesting or editing the repo does not
        touch it — only promoting does. Deploy from the banner at the top of this page.
      </p>
    </Card>
  )
}

// ── the one editable lever ──────────────────────────────────────────────────────

export function RuntimeEditor({
  botKey,
  botLabel,
  row,
  balance,
  hideNote = false,
}: {
  botKey: string
  botLabel: string
  row: BotParamRow
  balance: number | null
  /** Suppress the instance config's prose. See the note's own comment below for why. */
  hideNote?: boolean
}) {
  const current = Number(row.value)
  const [draft, setDraft] = useState<string>(String(current))
  const [confirming, setConfirming] = useState(false)
  const save = useSaveBotRuntime()

  const next = parseFloat(draft)
  const valid =
    Number.isFinite(next) &&
    (row.min == null || next >= row.min) &&
    (row.max == null || next <= row.max)
  const dirty = valid && next !== current

  function commit() {
    save.mutate(
      { botName: botKey, values: { [row.name]: next } },
      { onSuccess: () => setConfirming(false) }
    )
  }

  return (
    <div>
      <div className="flex items-end gap-3">
        <div>
          <p className="text-[10px] text-text-tertiary mb-[3px]">{row.label}</p>
          <div className="flex items-baseline gap-1">
            <span className="text-[22px] font-mono tabular-nums text-text-primary">
              {fmt(row.value)}
            </span>
            <span className="text-[11px] text-text-tertiary">{row.unit ?? '%'}</span>
          </div>
          {balance != null && (
            <p className="text-[10px] text-text-tertiary mt-[2px]">
              {riskUsd(current, balance)} per trade at ${balance.toLocaleString()}
            </p>
          )}
        </div>

        <div className="ml-auto flex items-end gap-2">
          <div>
            <p className="text-[10px] text-text-tertiary mb-[3px]">Change to</p>
            <input
              type="number"
              value={draft}
              step={0.5}
              min={row.min ?? undefined}
              max={row.max ?? undefined}
              onChange={(e) => setDraft(e.target.value)}
              className="w-[78px] bg-bg-sunken border border-border-subtle rounded px-[7px] py-[5px] text-[12px] font-mono text-right focus:border-accent/50 outline-none transition-colors"
            />
          </div>
          <button
            disabled={!dirty || save.isPending}
            onClick={() => setConfirming(true)}
            className={`px-3 py-[6px] rounded-md text-small font-medium transition-colors ${
              dirty && !save.isPending
                ? 'bg-accent-muted text-accent-text border border-accent/30 hover:bg-accent/10 cursor-pointer'
                : 'bg-bg-surface-2 text-text-tertiary border border-border-subtle cursor-not-allowed opacity-50'
            }`}
          >
            {save.isPending ? 'Deploying…' : 'Deploy'}
          </button>
        </div>
      </div>

      {!valid && draft !== '' && (
        <p className="text-[10px] text-neg-text mt-[6px]">
          Must be between {row.min} and {row.max}.
        </p>
      )}

      {/* 🔴 **The note is OFF by default since 2026-09-05.** It is the `_`-prefixed prose from the
          instance config — a paragraph a developer wrote about why a number is what it is, and on
          `exec_risk_pct` it runs to some 1,500 words. Printed beside the one control on the page
          it buried the control. Aaron: *"even the section that says risk per trade, what is all
          of that information? Why do I care?"*

          ⚠ **It is HIDDEN, never deleted.** That prose is the measured reasoning behind a live
          risk number and this repo does not throw those away — the drawer shows it under Details,
          where somebody asking *why is it 5%* will look and nobody else has to read it. */}
      {row.note && !hideNote && (
        <p className="text-[10px] text-text-tertiary mt-[10px] leading-[1.5] border-t border-border-subtle/60 pt-[8px]">
          <Info size={10} className="inline mr-[4px] -mt-[1px]" />
          {row.note}
        </p>
      )}

      {confirming && (
        <ConfirmRuntime
          botLabel={botLabel}
          label={row.label}
          from={current}
          to={next}
          unit={row.unit ?? '%'}
          balance={balance}
          pending={save.isPending}
          onCancel={() => setConfirming(false)}
          onConfirm={commit}
        />
      )}
    </div>
  )
}

/**
 * The confirmation carries the NUMBERS, not the question.
 *
 * "Are you sure?" trains you to click yes. A dialog that shows `10% → 5%` and
 * `$200 → $100 per trade` is one you actually read, which is the only thing that makes a
 * confirmation worth having.
 *
 * ⚠ It also carries the BOT NAME (2026-08-04). With a selector above it, the bot being
 * changed is a choice the reader made a scroll ago and can no longer see — and this dialog
 * is the last point at which a wrong row is still free to fix.
 */
function ConfirmRuntime({
  botLabel,
  label,
  from,
  to,
  unit,
  balance,
  pending,
  onCancel,
  onConfirm,
}: {
  botLabel: string
  label: string
  from: number
  to: number
  unit: string
  balance: number | null
  pending: boolean
  onCancel: () => void
  onConfirm: () => void
}) {
  const bigger = to > from
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={onCancel}
    >
      <div
        className="bg-bg-surface border border-border-default rounded-lg p-5 w-[440px]"
        onClick={(e) => e.stopPropagation()}
      >
        <p className="text-[13px] font-semibold mb-1">
          Change {label} on <span className="font-mono">{botLabel}</span>
        </p>
        <p className="text-[11px] text-text-tertiary mb-4">
          This commits the instance config, pushes it, and the VPS pulls it.
        </p>

        <div className="bg-bg-sunken border border-border-subtle rounded-md p-3 mb-3">
          <div className="flex items-center justify-center gap-3 font-mono tabular-nums">
            <span className="text-[20px] text-text-tertiary">
              {from}
              {unit}
            </span>
            <span className="text-text-tertiary">→</span>
            <span className={`text-[20px] ${bigger ? 'text-warn-text' : 'text-text-primary'}`}>
              {to}
              {unit}
            </span>
          </div>
          {balance != null && !!balance && (
            <div className="flex items-center justify-center gap-3 mt-[6px] text-[11px] font-mono tabular-nums text-text-tertiary">
              <span>{riskUsd(from, balance)}</span>
              <span>→</span>
              <span className={bigger ? 'text-warn-text' : ''}>{riskUsd(to, balance)}</span>
              <span>per trade</span>
            </div>
          )}
        </div>

        {bigger && (
          <p className="text-[11px] text-warn-text mb-3 flex gap-[6px]">
            <AlertTriangle size={12} className="shrink-0 mt-[1px]" />
            This increases the risk on every future trade.
          </p>
        )}

        <p className="text-[10px] text-text-tertiary mb-4 leading-[1.5]">
          The bot is <strong className="text-text-secondary">not restarted</strong>. It picks the
          change up at the next bar it is flat — no position open and nothing resting — so a resize
          can never land mid-trade.
        </p>

        <div className="flex gap-2 justify-end">
          <button
            onClick={onCancel}
            className="px-3 py-[6px] rounded-md text-small text-text-secondary border border-border-subtle hover:bg-bg-hover cursor-pointer"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={pending}
            className="px-3 py-[6px] rounded-md text-small font-medium bg-accent-muted text-accent-text border border-accent/30 hover:bg-accent/10 cursor-pointer disabled:opacity-50"
          >
            {pending ? 'Deploying…' : 'Deploy change'}
          </button>
        </div>
      </div>
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

export function BotPanel({ bot }: { bot: BotStatus }) {
  // Every API path takes the KEY — the routes accept either, new code passes the key.
  const { data, isLoading, error } = useBotParams(bot.key)

  if (isLoading) {
    return <div className="text-[11px] text-text-tertiary">Loading {bot.name}…</div>
  }
  if (error || !data) {
    return (
      <div className="text-[11px] text-neg-text">
        Could not read {bot.name}'s configuration: {String(error)}
      </div>
    )
  }

  const v: BotParamsView = data
  const groups = v.strategy.reduce<Record<string, BotParamRow[]>>((acc, r) => {
    ;(acc[r.group] ??= []).push(r)
    return acc
  }, {})

  // NOTE: `v.version` (from config.json) is deliberately no longer rendered. It states what
  // SHOULD be deployed and goes stale the moment the repo moves; DeployCard reads the VPS.
  const terminal = (v.identity.mt5_path ?? '').split('\\').filter(Boolean)[0] ?? '—'

  return (
    <div className="grid grid-cols-2 gap-4 items-start">
      {/* FIRST, full width, and deliberately above the risk editor: "am I behind, and by how
          much" is the question this tab is opened to answer, and it had no answer on the page
          at all until 2026-08-07. It also carries the only Deploy control. */}
      <div className="col-span-2">
        <VersionBanner botKey={bot.key} botLabel={bot.name} />
      </div>

      {/* Risk — the only thing on this page that can be changed */}
      <div className="col-span-2">
        <Card title="Risk per trade">
          {v.runtime.length === 0 ? (
            <p className="text-[11px] text-text-tertiary">No runtime-editable settings.</p>
          ) : (
            v.runtime.map((r) => (
              <RuntimeEditor
                key={r.name}
                botKey={bot.key}
                botLabel={bot.name}
                row={r}
                balance={bot.balance}
              />
            ))
          )}
        </Card>
      </div>

      <Card title="Account">
        <Row label="Account">{fmt(v.identity.account)}</Row>
        <Row label="Server">{fmt(v.identity.server)}</Row>
        <Row label="Symbol">{fmt(v.identity.symbol)}</Row>
        <Row label="Timeframe">{fmt(v.identity.timeframe)}</Row>
        <Row label="Terminal" title={v.identity.mt5_path ?? ''}>
          {terminal}
        </Row>
        <Row label="Magic">{fmt(v.identity.magic)}</Row>
      </Card>

      <DeployCard botKey={bot.key} />

      <div className="col-span-2">
        <Card
          title={`Strategy parameters · ${v.strategy.length}`}
          right={
            <span className="inline-flex items-center gap-[4px] text-[9px] uppercase tracking-[0.4px] text-text-tertiary">
              <Lock size={9} /> read-only
            </span>
          }
        >
          <p className="text-[10px] text-text-tertiary mb-2 leading-[1.5]">
            These decide <strong className="text-text-secondary">which trades</strong> the bot
            takes, so changing one means it is no longer the bot that was backtested. To change
            them: edit in the lab, backtest, then promote — that path re-pins the version hash
            above.
          </p>
          <div>
            {Object.entries(groups).map(([g, rows]) => (
              <ParamGroup key={g} group={g} rows={rows} />
            ))}
          </div>
        </Card>
      </div>
    </div>
  )
}
