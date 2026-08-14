import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  AlertTriangle, ArrowRight, CheckCircle2, ChevronDown, ChevronRight,
  GitCommitHorizontal, HelpCircle, Info, Lock,
  PackageCheck, Snowflake, RotateCcw, SlidersHorizontal, Upload,
} from 'lucide-react'
import {
  useBotSnapshot, useBotParams, useSaveBotRuntime,
  useBotVersion, useBotVersions, usePreviewPromote, usePromoteBot,
} from '@/hooks/useBots'
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

function Card({ title, children, right }: {
  title: string; children: React.ReactNode; right?: React.ReactNode
}) {
  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <p className="text-[9px] font-semibold uppercase tracking-[0.8px] text-gold-text">{title}</p>
        {right}
      </div>
      {children}
    </div>
  )
}

function Row({ label, children, title }: {
  label: string; children: React.ReactNode; title?: string
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
  return `$${(balance * pct / 100).toLocaleString(undefined, { maximumFractionDigits: 2 })}`
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

function versionFlags(v: BotDeployedVersion | undefined): VersionFlags | null {
  if (!v) return null
  const notFrozen = !v.frozen
  const snapshotModified = v.frozen && !v.snapshot_ok
  // The live process reports a 12-char prefix; compare like for like. A mismatch means a
  // promote landed after the bot started, so the NEW code is on disk and the OLD code is
  // still trading — the most misleading state this page can show.
  const restartPending = !!(v.running_hash && v.hash && !v.hash.startsWith(v.running_hash))
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

function FleetCount({ label, n, tone, icon: Icon, title }: {
  label: string
  n: number
  tone: 'warn' | 'neutral'
  icon: typeof AlertTriangle
  title: string
}) {
  const hot = n > 0
  const cls = !hot
    ? 'border-border-subtle/60 text-text-tertiary'
    : tone === 'warn'
      ? 'border-warn/30 bg-warn-muted text-warn-text'
      : 'border-border-default text-text-secondary'
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-[5px] text-[10px] px-[8px] py-[4px] rounded-md border cursor-default ${cls}`}
    >
      <Icon size={10} className="shrink-0" />
      <span className="font-mono tabular-nums font-semibold">{n}</span>
      <span className="whitespace-nowrap">{label}</span>
    </span>
  )
}

function FleetStrip({ bots, flags, unreadable, loading }: {
  bots: BotStatus[]
  flags: (VersionFlags | null)[]
  unreadable: number
  loading: boolean
}) {
  const running = bots.filter(b => b.status === 'RUNNING').length
  const live    = bots.filter(b => b.account_type === 'live').length
  const known   = flags.filter((f): f is VersionFlags => f !== null)

  const restartPending   = known.filter(f => f.restartPending).length
  const notFrozen        = known.filter(f => f.notFrozen).length
  const snapshotModified = known.filter(f => f.snapshotModified).length
  const drifted          = known.filter(f => f.driftCount > 0).length
  const behind           = known.filter(f => f.behind > 0).length

  const clean = known.length > 0 && known.every(f => !f.anyWarn)

  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg px-4 py-[11px] mb-4
                    flex items-center gap-x-[10px] gap-y-[8px] flex-wrap">
      <div className="flex items-baseline gap-[6px] mr-[4px]">
        <span className="text-[9px] font-semibold uppercase tracking-[0.8px] text-gold-text">Fleet</span>
        <span className="text-[11px] text-text-secondary font-mono tabular-nums">
          {bots.length} {bots.length === 1 ? 'bot' : 'bots'}
        </span>
        <span className="text-[11px] text-text-tertiary">·</span>
        <span className="text-[11px] text-text-tertiary font-mono tabular-nums">{running} running</span>
        {live > 0 && (
          <>
            <span className="text-[11px] text-text-tertiary">·</span>
            <span className="text-[11px] font-mono tabular-nums text-warn-text">{live} live</span>
          </>
        )}
      </div>

      <div className="flex items-center gap-[6px] flex-wrap ml-auto">
        <FleetCount
          label="restart pending" n={restartPending} tone="warn" icon={RotateCcw}
          title="Promoted, but the running process still reports the OLD hash — the new version is on disk and the old one is trading."
        />
        <FleetCount
          label="not frozen" n={notFrozen} tone="warn" icon={Snowflake}
          title="Still importing from the repo working tree, so a git pull changes what it trades. Promote it."
        />
        <FleetCount
          label="snapshot edited" n={snapshotModified} tone="warn" icon={AlertTriangle}
          title="The deployed files no longer match their record — edited in place, bypassing promote."
        />
        <FleetCount
          label="settings changed" n={drifted} tone="warn" icon={SlidersHorizontal}
          title="config.json now states settings the deployment does not carry. They take effect at the next promote (risk % applies live)."
        />
        <FleetCount
          label="behind repo" n={behind} tone="neutral" icon={GitCommitHorizontal}
          title="The repo has moved past this deployment. Normal — a bot runs what it was promoted at, not what the repo says today."
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
        {!loading && unreadable === 0 && clean && (
          <span className="text-[10px] text-pos-text ml-[2px]">all deployments clean</span>
        )}
      </div>
    </div>
  )
}

// ── the rail ────────────────────────────────────────────────────────────────────

function RailRow({ bot, flags, unread, selected, onSelect }: {
  bot: BotStatus
  flags: VersionFlags | null
  unread: boolean
  selected: boolean
  onSelect: () => void
}) {
  const isRunning = bot.status === 'RUNNING'
  const isLive    = bot.account_type === 'live'

  return (
    <button
      onClick={onSelect}
      aria-current={selected ? 'true' : undefined}
      className={`w-full text-left px-[10px] py-[9px] rounded-md border transition-colors duration-[100ms] cursor-pointer ${
        selected
          ? 'bg-accent-muted border-accent/30'
          : 'bg-transparent border-transparent hover:bg-bg-hover'
      }`}
    >
      <div className="flex items-center gap-[7px]">
        <span
          title={isRunning ? 'Running' : bot.status === 'ERROR' ? 'Error' : 'Stopped'}
          className={`w-[6px] h-[6px] rounded-full shrink-0 ${
            isRunning ? 'bg-pos shadow-[0_0_6px_#00ff7f]' : 'bg-neg'
          }`}
        />
        <span className={`text-[11px] truncate ${selected ? 'text-text-primary font-medium' : 'text-text-secondary'}`}
              title={bot.name}>
          {bot.name}
        </span>
        {flags?.anyWarn && (
          <AlertTriangle
            size={10}
            className="ml-auto shrink-0 text-warn-text"
            aria-label="version needs attention"
          />
        )}
        {unread && (
          <span className="ml-auto shrink-0 text-[10px] text-text-tertiary" title="Deployment record unreadable">?</span>
        )}
      </div>
      <div className="flex items-center gap-[5px] mt-[5px] pl-[13px]">
        <span className={`inline-flex text-[9px] font-semibold px-[5px] py-[2px] rounded-pill uppercase tracking-[0.4px] ${
          isLive ? 'bg-warn-muted text-warn-text' : 'bg-bg-surface-2 text-text-tertiary'
        }`}>
          {bot.account_type}
        </span>
        <span className="text-[10px] font-mono text-text-tertiary truncate">{bot.account}</span>
      </div>
    </button>
  )
}

// ── which version is deployed, and deploying a new one ──────────────────────────
//
// The card this replaced read `config.json` — the tracked file — and so described what
// SHOULD be deployed rather than what is. Those were the same thing until 2026-08-03, when
// a bot stopped importing from the repo and started running a frozen snapshot. They are now
// routinely different, and the difference is the whole point: you can build version 3 in the
// repo all day and this keeps saying version 2, because version 2 is what is trading.
//
// Everything here comes from the VPS. Nothing is inferred from the local checkout.

function Warn({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-[6px] text-[10px] leading-[1.5] text-amber-400/90
                    bg-amber-400/[0.06] border border-amber-400/20 rounded px-[8px] py-[6px] mt-[8px]">
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
function VersionBanner({ botKey, botLabel }: { botKey: string; botLabel: string }) {
  const { data: v, isLoading, isFetching } = useBotVersion(botKey)
  const preview = usePreviewPromote()
  const promote = usePromoteBot()
  // 🔴 This was a bare `output: string | null`, so a FINISHED deploy rendered under the
  // preview's own caption ("nothing deployed yet") with the Deploy button still sitting
  // there — Aaron pressed Deploy, it worked, and the page gave him no way to tell. **A
  // panel that shows a result has to say which ACTION produced it**; the text alone cannot,
  // because promote.py's own output reads much the same either way.
  const [result, setResult] = useState<
    { kind: 'preview' | 'deploy'; ok: boolean; restarted: boolean; output: string } | null
  >(null)
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
  const c = v?.compare ?? null

  if (isLoading) {
    return <div className="text-[11px] text-text-tertiary px-[14px] py-[12px]">checking versions…</div>
  }

  // Every state that makes this unanswerable has its own fix and none of them is "deploy", so
  // the reason is rendered and no button is offered. A `0` here would read as UP TO DATE,
  // which is the most reassuring answer available and the one most likely to be wrong.
  if (!c || !c.comparable) {
    return (
      <div data-testid="version-banner"
           className="flex items-start gap-[8px] text-[11px] leading-[1.5] text-text-secondary
                      bg-bg-elevated border border-border-subtle rounded-lg px-[14px] py-[12px]">
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
  const willChange = c.setting_changes.filter(s => !s.stated)
  const pinned = c.setting_changes.filter(s => s.stated)
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
        preview.mutate({ botName: botKey }, {
          onSuccess: r => setResult({ kind: 'preview', ok: r.ok, restarted: false, output: r.output }),
        })
      }}
      disabled={busy}
      className={`inline-flex items-center gap-[6px] px-[14px] py-[7px] rounded-md font-medium
                  disabled:opacity-40 ${behind > 0
        ? 'text-[12px] bg-gold-text/20 text-gold-bright hover:bg-gold-text/30 border border-gold-text/40'
        : 'text-[10px] text-text-tertiary hover:text-text-secondary'}`}
    >
      <Upload size={behind > 0 ? 13 : 10} />
      {promote.isPending ? 'deploying…'
        : refreshing ? 'checking…'
        : preview.isPending ? 'working…'
        : behind > 0 ? `Deploy v${c.deployed_version} → v${c.local_version}`
        : 'Re-deploy'}
    </button>
  )

  return (
    /* `data-testid` is a declared TEST SEAM, and it is load-bearing rather than convenience:
       the Risk-per-trade card below carries its own `Deploy` button, so a page-wide
       "no deploy button" assertion passes on a broken banner too — the vacuous-locator trap
       this repo has now hit three times (`svg.first()` was the sidebar logo; a page-wide
       Retry matched the page header's own). */
    <div data-testid="version-banner"
         className={`rounded-lg border px-[14px] py-[12px] ${behind > 0
      ? 'bg-amber-400/[0.07] border-amber-400/30'
      : 'bg-pos-muted/40 border-pos-text/25'}`}>

      <div className="flex items-start justify-between gap-[16px] flex-wrap">
        <div>
          <p className={`flex items-center gap-[7px] text-[13px] font-semibold ${
            behind > 0 ? 'text-amber-300' : 'text-pos-text'}`}>
            {behind > 0 ? <AlertTriangle size={14} /> : <CheckCircle2 size={14} />}
            {behind > 0
              ? `${botLabel} is ${behind} version${behind === 1 ? '' : 's'} behind`
              : `${botLabel} is up to date`}
          </p>
          <div className="flex items-center gap-[22px] mt-[9px] text-[11px]">
            <span className="text-text-tertiary">
              Deployed{' '}
              <span className="text-text-primary font-mono text-[13px]">v{c.deployed_version}</span>
              {v?.promoted_at ? <span className="text-text-tertiary"> · {v.promoted_at}</span> : null}
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
        <p className="text-[10px] text-amber-400/90 mt-[9px] leading-[1.5]"
           title={c.uncommitted_files.join('\n')}>
          Your backtester also has <strong>{dirty} edited file{dirty === 1 ? '' : 's'}</strong>{' '}
          {dirty === 1 ? 'that is' : 'that are'} not committed
          {dirty === 1 ? <> (<span className="font-mono">{c.uncommitted_files[0]}</span>)</> : null}.
          {' '}Not part of v{c.local_version}, and a promote refuses a dirty tree — commit or revert
          first.
        </p>
      )}

      {/* 🔴 The reason a successful deploy can leave a bot behind, and the page said nothing
          about it until 2026-08-14. A promote PULLS on the VPS, so the highest version it can
          ever reach is the one on the remote — a commit sitting unpushed here is unreachable
          however many times Deploy is pressed. `null` means there is no upstream to compare
          against and renders nothing; `[]` is the measured "all pushed" and renders nothing
          too. Only a real count speaks. */}
      {unpushed.length > 0 && (
        <p className="text-[10px] text-amber-400/90 mt-[9px] leading-[1.5]"
           title={unpushed.join('\n')}>
          <strong>{unpushed.length} commit{unpushed.length === 1 ? '' : 's'} touching this bot
          {unpushed.length === 1 ? ' is' : ' are'} not pushed.</strong>{' '}
          A promote pulls on the VPS, so it can only reach{' '}
          <span className="font-mono">v{deployable}</span>
          {deployable != null && c.local_version != null && deployable < c.local_version
            ? <> — push first, or the bot lands {c.local_version - deployable} version
                {c.local_version - deployable === 1 ? '' : 's'} short of your backtester.</>
            : '.'}
        </p>
      )}

      {behind > 0 && !refreshing && (
        <div className="mt-[11px] border-t border-amber-400/20 pt-[10px] space-y-[9px]">
          {willChange.length > 0 ? (
            <div>
              <p className="text-[10px] uppercase tracking-[0.4px] text-text-tertiary mb-[5px]">
                {willChange.length} setting{willChange.length === 1 ? '' : 's'} would change on this bot
              </p>
              {willChange.map(s => (
                <div key={s.name} className="flex items-baseline gap-[8px] text-[11px] py-[2px]" title={s.desc}>
                  <span className="text-text-secondary min-w-[150px]">{s.label}</span>
                  <span className="font-mono text-[10px] text-text-tertiary">
                    {s.is_new ? <em className="not-italic">not in v{c.deployed_version}</em> : s.was}
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
              {pinned.map(s => `${s.label} (${s.was} → ${s.now})`).join(', ')}.
            </p>
          )}

          <button
            onClick={() => setShowChanges(s => !s)}
            className="inline-flex items-center gap-[4px] text-[10px] text-text-tertiary hover:text-text-secondary"
          >
            {showChanges ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
            {c.changes.length} code change{c.changes.length === 1 ? '' : 's'}
          </button>
          {showChanges && (
            <div className="max-h-[200px] overflow-y-auto space-y-[3px] pl-[14px]">
              {c.changes.map(ch => (
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
            <p className={`flex items-center gap-[6px] text-[12px] font-semibold mb-[6px] ${
              result.ok ? 'text-pos-text' : 'text-neg-text'}`}>
              {result.ok ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}
              {/* 🔴 It named `c.local_version` — the BACKTESTER's version, i.e. what the reader
                  asked for rather than what landed. Those differ whenever the deploy could not
                  reach HEAD, which is exactly the unpushed case above: on 2026-08-14 this line
                  read "running v165" over a bot running v164. It is `deployed_version` now, and
                  it is withheld until the refetch answers — a version quoted from the pre-deploy
                  payload is a claim about the thing that just changed. */}
              {result.ok
                ? `Deployed${result.restarted
                    ? ` — ${botLabel} restarted${refreshing ? '' : ` and is running v${c.deployed_version}`}`
                    : ` — restart ${botLabel} to pick it up`}`
                : `Deploy failed — ${botLabel} is untouched and still on v${c.deployed_version}`}
            </p>
          ) : (
            <p className="text-[10px] uppercase tracking-[0.4px] text-text-tertiary mb-[6px]">
              Checked the code on the VPS — nothing deployed yet
            </p>
          )}
          {refreshing && (
            <p className="text-[10px] text-text-tertiary mb-[6px]">re-reading the deployed version…</p>
          )}
          {/* A preview's output IS the thing you read before deciding, and a failure's output is
              the only place the reason lives. A SUCCESS has already been summarised by the green
              line above, so it collapses behind a toggle — that `<pre>` holding the panel open in
              its pre-deploy shape is what made a finished deploy look like a pending one. */}
          {(result.kind === 'preview' || !result.ok || showOutput) && (
            <pre className="text-[10px] leading-[1.45] font-mono text-text-secondary
                            whitespace-pre-wrap break-all max-h-[200px] overflow-y-auto
                            bg-bg-base/60 rounded p-[8px]">{result.output}</pre>
          )}
          <div className="flex items-center gap-[8px] mt-[9px] flex-wrap">
            {/* The deploy button exists ONLY on the preview. Leaving it up after a successful
                deploy is what made a finished promote read as a pending one. */}
            {result.kind === 'preview' && (
              /* The bot is NAMED on the button, not just above it. This is the one control on
                 the page that changes what a live account trades, and the reader arrived here
                 by clicking a rail row — the name is the thing being confirmed. */
              <button
                onClick={() => promote.mutate({ botName: botKey, restart: true }, {
                  onSuccess: r => setResult({
                    kind: 'deploy', ok: r.ok, restarted: r.restarted, output: r.output,
                  }),
                })}
                disabled={busy}
                className="inline-flex items-center gap-[5px] text-[11px] px-[12px] py-[5px]
                           rounded bg-gold-text/20 text-gold-bright hover:bg-gold-text/30
                           border border-gold-text/40 disabled:opacity-40"
              >
                <PackageCheck size={12} /> Deploy &amp; restart <span className="font-mono">{botLabel}</span>
              </button>
            )}
            {deployed && (
              <button
                data-testid="deploy-output-toggle"
                onClick={() => setShowOutput(s => !s)}
                className="text-[10px] px-[10px] py-[5px] rounded text-text-tertiary hover:text-text-secondary"
              >
                {showOutput ? 'Hide output' : 'Show output'}
              </button>
            )}
            <button
              onClick={() => { setResult(null); setShowOutput(false) }}
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
function DeployCard({ botKey }: { botKey: string }) {
  const { data: v, isLoading } = useBotVersion(botKey)

  if (isLoading) return <Card title="Deployed version"><Row label="">loading…</Row></Card>
  if (!v) return <Card title="Deployed version"><Row label="">unavailable</Row></Card>

  const f = versionFlags(v)!

  return (
    <Card title="Deployed version">
      <Row label="Strategy">{fmt(v.strategy_package)}</Row>
      <Row label="Code hash" title={v.hash}>{v.hash ? v.hash.slice(0, 12) : '—'}</Row>
      <Row label="From commit">{fmt(v.commit)}</Row>
      <Row label="Deployed on">{fmt(v.promoted_at)}</Row>
      <Row label="Files">{v.files ? `${v.files} .py` : '—'}</Row>
      <Row label="Repo now">
        {fmt(v.repo_commit)}{f.behind > 0 ? ` · ${f.behind} ahead` : ' · same'}
      </Row>

      {f.notFrozen && (
        <Warn>
          <strong>Not frozen.</strong> This bot still imports from the repo working tree, so a
          pull changes what it trades and can stop it starting. Promote it.
        </Warn>
      )}
      {f.snapshotModified && (
        <Warn>
          <strong>Snapshot modified.</strong> The deployed files no longer match their record —
          someone edited them in place, bypassing promote. Re-promote to re-pin.
        </Warn>
      )}
      {f.restartPending && (
        <Warn>
          <strong>Restart pending.</strong> The running process reports{' '}
          <span className="font-mono">{v.running_hash}</span>, not the deployed hash. The new
          version is on disk but the old one is still trading.
        </Warn>
      )}
      {f.driftCount > 0 && (
        <Warn>
          <strong>{f.driftCount} setting(s) changed since deploy:</strong>{' '}
          <span className="font-mono">{v.params_drift.join(', ')}</span>. They take effect at
          the next promote, except risk % which applies live.
        </Warn>
      )}

      <p className="text-[10px] text-text-tertiary mt-[8px] leading-[1.5] border-t border-border-subtle/60 pt-[8px]">
        This bot runs a frozen copy of its code. Pulling, backtesting or editing the repo does
        not touch it — only promoting does. Deploy from the banner at the top of this page.
      </p>
    </Card>
  )
}

// ── the one editable lever ──────────────────────────────────────────────────────

function RuntimeEditor({ botKey, botLabel, row, balance }: {
  botKey: string; botLabel: string; row: BotParamRow; balance: number | null
}) {
  const current = Number(row.value)
  const [draft, setDraft] = useState<string>(String(current))
  const [confirming, setConfirming] = useState(false)
  const save = useSaveBotRuntime()

  const next = parseFloat(draft)
  const valid = Number.isFinite(next)
    && (row.min == null || next >= row.min)
    && (row.max == null || next <= row.max)
  const dirty = valid && next !== current

  function commit() {
    save.mutate({ botName: botKey, values: { [row.name]: next } },
      { onSuccess: () => setConfirming(false) })
  }

  return (
    <div>
      <div className="flex items-end gap-3">
        <div>
          <p className="text-[10px] text-text-tertiary mb-[3px]">{row.label}</p>
          <div className="flex items-baseline gap-1">
            <span className="text-[22px] font-mono tabular-nums text-text-primary">{fmt(row.value)}</span>
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
              onChange={e => setDraft(e.target.value)}
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

      {row.note && (
        <p className="text-[10px] text-text-tertiary mt-[10px] leading-[1.5] border-t border-border-subtle/60 pt-[8px]">
          <Info size={10} className="inline mr-[4px] -mt-[1px]" />{row.note}
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
function ConfirmRuntime({ botLabel, label, from, to, unit, balance, pending, onCancel, onConfirm }: {
  botLabel: string; label: string; from: number; to: number; unit: string; balance: number | null
  pending: boolean; onCancel: () => void; onConfirm: () => void
}) {
  const bigger = to > from
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onCancel}>
      <div
        className="bg-bg-surface border border-border-default rounded-lg p-5 w-[440px]"
        onClick={e => e.stopPropagation()}
      >
        <p className="text-[13px] font-semibold mb-1">
          Change {label} on <span className="font-mono">{botLabel}</span>
        </p>
        <p className="text-[11px] text-text-tertiary mb-4">
          This commits the instance config, pushes it, and the VPS pulls it.
        </p>

        <div className="bg-bg-sunken border border-border-subtle rounded-md p-3 mb-3">
          <div className="flex items-center justify-center gap-3 font-mono tabular-nums">
            <span className="text-[20px] text-text-tertiary">{from}{unit}</span>
            <span className="text-text-tertiary">→</span>
            <span className={`text-[20px] ${bigger ? 'text-warn-text' : 'text-text-primary'}`}>{to}{unit}</span>
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

function ParamGroup({ group, rows }: { group: string; rows: BotParamRow[] }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border-b border-border-subtle/60 last:border-b-0">
      <button
        onClick={() => setOpen(o => !o)}
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
          {rows.map(r => (
            <Row key={r.name} label={r.label} title={r.desc ?? undefined}>
              {fmt(r.value)}{r.unit ? ` ${r.unit}` : ''}
            </Row>
          ))}
        </div>
      )}
    </div>
  )
}

function BotPanel({ bot }: { bot: BotStatus }) {
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
    (acc[r.group] ??= []).push(r)
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
          {v.runtime.length === 0
            ? <p className="text-[11px] text-text-tertiary">No runtime-editable settings.</p>
            : v.runtime.map(r => (
                <RuntimeEditor key={r.name} botKey={bot.key} botLabel={bot.name}
                                 row={r} balance={bot.balance} />
              ))}
        </Card>
      </div>

      <Card title="Account">
        <Row label="Account">{fmt(v.identity.account)}</Row>
        <Row label="Server">{fmt(v.identity.server)}</Row>
        <Row label="Symbol">{fmt(v.identity.symbol)}</Row>
        <Row label="Timeframe">{fmt(v.identity.timeframe)}</Row>
        <Row label="Terminal" title={v.identity.mt5_path ?? ''}>{terminal}</Row>
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

export function ConfigureTab() {
  const { data: snapshot } = useBotSnapshot()
  const [searchParams, setSearchParams] = useSearchParams()

  const bots = snapshot?.bots ?? []
  // The KEY, not the display name — see `BotStatus.key`. A name is a label chosen for a
  // human and is the field that eventually changes; everything addressable keys off `key`.
  const keys = bots.map(b => b.key)

  // One fetch per bot, sharing DeployCard's cache entries — see `useBotVersions`.
  const versionQueries = useBotVersions(keys)
  const flags     = versionQueries.map(q => versionFlags(q.data))
  const unreadable = versionQueries.filter(q => !q.isPending && !q.data).length
  const loading    = versionQueries.some(q => q.isPending)

  // Selection lives in the URL, like every other tab state in this app — so a link to a
  // specific bot's config is a real link, and a refresh does not silently move you to
  // another bot's promote button.
  //
  // ⚠ Keyed on `bot.key`, never the display name. `?bot=MPC%20SOS%20Fade` is a bookmark
  // that dies the day somebody renames the bot — and the thing it silently falls back to is
  // `bots[0]`, i.e. a DIFFERENT bot's promote button, with the URL still naming the one you
  // wanted. A stale key falls back the same way, but a key is not a label and nobody edits
  // it for readability.
  const requested = searchParams.get('bot')
  const selected = bots.find(b => b.key === requested) ?? bots[0] ?? null

  function selectBot(key: string) {
    const next = new URLSearchParams(searchParams)
    next.set('bot', key)
    setSearchParams(next, { replace: true })
  }

  if (!snapshot) return null
  if (bots.length === 0) {
    return <p className="text-[11px] text-text-tertiary">No bots registered.</p>
  }

  return (
    <div>
      <FleetStrip bots={bots} flags={flags} unreadable={unreadable} loading={loading} />

      <div className="flex items-start gap-4">

        {/* ── Rail ──────────────────────────────────────────────────────────── */}
        <div className="w-[212px] shrink-0 sticky top-0">
          <div className="bg-bg-surface border border-border-subtle rounded-lg p-[6px]">
            <p className="text-[9px] font-semibold uppercase tracking-[0.8px] text-gold-text px-[10px] pt-[6px] pb-[8px]">
              Bots
            </p>
            <div className="flex flex-col gap-[2px]">
              {bots.map((b, i) => (
                <RailRow
                  key={b.key}
                  bot={b}
                  flags={flags[i]}
                  unread={!versionQueries[i]?.isPending && !versionQueries[i]?.data}
                  selected={selected?.key === b.key}
                  onSelect={() => selectBot(b.key)}
                />
              ))}
            </div>
          </div>
          <p className="text-[10px] text-text-tertiary leading-[1.5] mt-[8px] px-[4px]">
            One bot at a time. Only the selected bot's Promote and Deploy controls exist on
            this page.
          </p>
        </div>

        {/* ── Detail ────────────────────────────────────────────────────────── */}
        <div className="flex-1 min-w-0">
          {selected && (
            <>
              {/* Deliberately NOT sticky, and the rail is. The parameter accordion runs well
                  past a screen, so "which bot am I editing" has to survive scrolling — but the
                  RAIL is what answers it, because the rail is the selector and its highlighted
                  row cannot disagree with itself. A second sticky header is a second answer to
                  one question, and it also lands in the 22px trap `frontend/CLAUDE.md` records:
                  `<main>` is a padded scroller, so `top-0` pins 22px LOW and the card headers
                  below scroll up through the transparent strip it leaves. */}
              <div className="pb-[10px] flex items-center gap-2 flex-wrap">
                <span className="text-[14px] font-semibold">{selected.name}</span>
                <span className={`inline-flex text-[10px] font-semibold px-2 py-[3px] rounded-pill uppercase tracking-[0.4px] ${
                  selected.status === 'RUNNING' ? 'bg-pos-muted text-pos-text' : 'bg-neg-muted text-neg-text'
                }`}>
                  {selected.status === 'RUNNING' ? 'Running' : selected.status === 'ERROR' ? 'Error' : 'Stopped'}
                </span>
                <span className={`inline-flex text-[10px] font-semibold px-2 py-[3px] rounded-pill uppercase tracking-[0.4px] ${
                  selected.account_type === 'live'
                    ? 'bg-warn-muted text-warn-text'
                    : 'bg-bg-surface-2 text-text-secondary'
                }`}>
                  {selected.account_type}
                </span>
                <span className="text-[11px] font-mono text-text-tertiary">{selected.account}</span>
              </div>
              <BotPanel key={selected.key} bot={selected} />
            </>
          )}
        </div>
      </div>
    </div>
  )
}
