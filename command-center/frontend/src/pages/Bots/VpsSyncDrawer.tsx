import { Fragment, useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError } from '@/api/client'
import {
  AlertTriangle,
  ArrowRight,
  Check,
  CheckCircle2,
  GitCompare,
  Info,
  Loader2,
  Radar,
  RefreshCw,
  ServerCrash,
  ShieldAlert,
  X,
  XCircle,
} from 'lucide-react'
import { Drawer } from '@/components/Drawer'
import { Shimmer } from '@/components/Shimmer'
import { SYNC_PREVIEW_KEY, useSyncAccounts, useSyncPreview } from '@/hooks/useBots'
import type {
  AccountSync,
  AccountSyncAttention,
  AccountSyncChange,
  AccountSyncDiff,
  AccountSyncPreview,
  ScannedTerminal,
} from '@/types'
import { AccountForm } from './AccountForm'

/**
 * Sync the account list with what the VPS is logged into — SCAN FIRST, then a Sync button.
 *
 * 🔴 **Reversed twice on 2026-09-10, and the second reversal is the shape.** It was "Scan VPS" and
 * only reported; then a sync that wrote on the press (*"not a scan, a sync"*); then Aaron: *"it
 * doesn't show me what it is going to do before I do it… the sync vps button will scan first to
 * show me what is out of sync, then there is a sync button to do the actual syncing."* So opening
 * the drawer runs a READ-ONLY scan that lists every change field by field (was → will be, with the
 * evidence), and the Sync button in the pinned footer applies exactly that list.
 *
 * 🔴 **The press sends the plan it approves, and the server refuses a plan that moved.** A terminal
 * can switch account between the scan and the press; the server re-scans, writes nothing, and hands
 * back the new plan, which replaces the old one here with a banner saying so.
 *
 * 🔴 **Nothing here decides what may change.** The rules are the server's
 * (`services/account_sync.py`) — above all, an account a bot trades is never changed. A second
 * copy of that rule in the browser is two answers about live accounts.
 *
 * ⚠ **Nothing syncs on its own** (*"100% manually triggered by me only"*). Opening the drawer
 * reads; only the Sync button writes.
 */
export function VpsSyncDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  // ⚠ The sync lives on this ALWAYS-MOUNTED shell, so a sync still running when the drawer is
  // closed is still running — and still reported — when it is opened again. Everything else
  // (the scan, the by-hand form) is thrown away on close, so every open is a fresh scan.
  const sync = useSyncAccounts()
  if (!open) return null
  return (
    <OpenSyncDrawer
      sync={sync}
      onClose={() => {
        if (!sync.isPending) sync.reset()
        onClose()
      }}
    />
  )
}

type Sync = ReturnType<typeof useSyncAccounts>

/** Where the drawer is in scan → review → sync. One derivation, read by every part of it. */
type Phase =
  'scanning' | 'scan-failed' | 'refused' | 'blocked' | 'review' | 'in-sync' | 'syncing' | 'saved'

function phaseOf(
  sync: Sync,
  preview: ReturnType<typeof useSyncPreview>,
  receipt: AccountSync | null
): Phase {
  if (sync.isPending) return 'syncing'
  if (receipt) return 'saved'
  const scan = preview.data
  if (!scan) return preview.isError ? 'scan-failed' : 'scanning'
  if (!scan.asked) return 'refused'
  if (scan.blocked) return 'blocked'
  return scan.changes.length > 0 ? 'review' : 'in-sync'
}

function OpenSyncDrawer({ sync, onClose }: { sync: Sync; onClose: () => void }) {
  const qc = useQueryClient()
  // The by-hand form — the only way in for an account sync cannot see (a stopped terminal).
  const [manual, setManual] = useState(false)
  // ⚠ Not asked while a sync is on the wire: the sync answers with its own fresh reading, and a
  // second scan over it would ask the box the same question twice.
  const preview = useSyncPreview(!sync.isPending)
  const scan = preview.data
  const result = sync.data
  const receipt = sync.isSuccess && result && !result.plan_changed ? result : null
  const planChanged = sync.isSuccess && !!result?.plan_changed
  const phase = phaseOf(sync, preview, receipt)

  // A re-scan is a new question: the old plan goes, so it can never be applied by a press that
  // lands while the new one is still being read.
  const scanAgain = () => {
    sync.reset()
    qc.resetQueries({ queryKey: SYNC_PREVIEW_KEY })
  }
  const pending = scan && !scan.blocked ? scan.changes.length : 0

  return (
    <Drawer
      open
      onClose={onClose}
      label="Sync the account list with the VPS"
      title={manual ? 'Add an account by hand' : 'Sync with the VPS'}
      subtitle={
        manual ? (
          'For an account sync can’t see — nothing is written until you save'
        ) : (
          <Checked scan={scan} asking={preview.isLoading} failed={preview.isError} />
        )
      }
      actions={
        manual ? <SmallButton onClick={() => setManual(false)}>Back</SmallButton> : undefined
      }
      footer={
        manual ? undefined : (
          <Footer
            phase={phase}
            pending={pending}
            blocked={scan?.blocked ?? null}
            busy={preview.isFetching || sync.isPending}
            onSync={() => scan && sync.mutate(scan.plan_id)}
            onScanAgain={scanAgain}
            onDone={onClose}
          />
        )
      }
    >
      {manual ? (
        <div className="pt-4">
          <AccountForm onClose={() => setManual(false)} />
        </div>
      ) : (
        <>
          <StepBar phase={phase} />
          <div className="flex flex-col gap-5 pt-4">
            <Hero
              phase={phase}
              scan={scan}
              receipt={receipt}
              scanError={preview.error}
              submittedAt={sync.submittedAt}
            />

            {sync.isError && (
              <Banner tone="neg" title="The sync didn’t finish" testId="sync-error">
                {errorText(sync.error)}
                <p className="mt-2 opacity-80">Scan again to see where your list stands now.</p>
              </Banner>
            )}

            {/* 🔴 NOTHING was written. The list below is the NEW plan, not the one approved —
                pressing Sync again approves this one. */}
            {planChanged && scan && (
              <Banner
                tone="warn"
                title="The VPS changed since your scan, so nothing was saved"
                testId="sync-plan-changed"
              >
                {scan.changes.length > 0
                  ? 'Below is what sync would change now. Check it, then press Sync again.'
                  : 'Your list already matches the VPS as it is now.'}
              </Banner>
            )}

            {receipt && <Receipt receipt={receipt} />}

            {scan?.asked && (
              <div className={phase === 'syncing' ? 'opacity-55 pointer-events-none' : ''}>
                <Plan scan={scan} after={!!receipt} />
              </div>
            )}

            {phase === 'scanning' && <TerminalsSkeleton />}
          </div>
          <ManualAdd onClick={() => setManual(true)} />
        </>
      )}
    </Drawer>
  )
}

// ── Header and footer ────────────────────────────────────────────────────────────────────────

function Checked({
  scan,
  asking,
  failed,
}: {
  scan: AccountSyncPreview | undefined
  asking: boolean
  failed: boolean
}) {
  // FIRST read only. A failed one is not "asking", so a dead link never sits behind a placeholder
  // looking busy.
  if (asking) return <Shimmer className="h-[12px] w-[170px]" />
  if (!scan?.scanned_at) return <>{failed ? 'Couldn’t check the VPS' : null}</>
  const n = scan.terminals.length
  return (
    <>
      Checked {new Date(scan.scanned_at).toLocaleTimeString()}
      {scan.asked ? ` · ${n} terminal${n === 1 ? '' : 's'}` : ''}
    </>
  )
}

/**
 * The one place the drawer ACTS. Pinned, so the button is never scrolled away from.
 *
 * ⚠ **The Sync button says how many changes it applies**, and is offered only over a plan. A
 * disabled Sync over a scan still running says where the action will be; over a blocked plan it
 * carries the reason on its title.
 */
function Footer({
  phase,
  pending,
  blocked,
  busy,
  onSync,
  onScanAgain,
  onDone,
}: {
  phase: Phase
  pending: number
  blocked: string | null
  busy: boolean
  onSync: () => void
  onScanAgain: () => void
  onDone: () => void
}) {
  const dead = phase === 'scan-failed' || phase === 'refused'
  const note =
    phase === 'syncing'
      ? 'Saving, then sending to the VPS…'
      : phase === 'blocked'
        ? 'Sync is off until that’s fixed.'
        : pending > 0 && (phase === 'review' || phase === 'saved')
          ? 'Nothing is saved until you press Sync.'
          : null
  const label = `Sync ${pending} change${pending === 1 ? '' : 's'}`

  let primary: React.ReactNode = null
  if (phase === 'syncing') {
    primary = (
      <PrimaryButton testId="sync-apply" disabled>
        <Loader2 size={13} className="animate-spin" /> Syncing…
      </PrimaryButton>
    )
  } else if (phase === 'scanning' || phase === 'blocked') {
    primary = (
      <PrimaryButton
        testId="sync-apply"
        disabled
        title={phase === 'blocked' ? (blocked ?? '') : 'Waiting for the scan'}
      >
        Sync
      </PrimaryButton>
    )
  } else if (pending > 0) {
    primary = (
      <PrimaryButton testId="sync-apply" disabled={busy} onClick={onSync}>
        {label} <ArrowRight size={13} />
      </PrimaryButton>
    )
  } else if (phase === 'in-sync' || phase === 'saved') {
    primary = (
      <SecondaryButton testId="sync-done" onClick={onDone}>
        Done
      </SecondaryButton>
    )
  }

  return (
    <div className="flex items-center gap-2">
      {note && <p className="mr-auto text-[11.5px] text-text-tertiary">{note}</p>}
      <div className="ml-auto flex items-center gap-2">
        {/* ⚠ The ONLY way forward from a scan that failed or was refused, so there it leads. */}
        {dead ? (
          <PrimaryButton testId="scan-again" disabled={busy} onClick={onScanAgain}>
            <RefreshCw size={12} /> Scan again
          </PrimaryButton>
        ) : (
          <SecondaryButton
            testId="scan-again"
            disabled={busy || phase === 'scanning'}
            onClick={onScanAgain}
          >
            <RefreshCw size={12} /> Scan again
          </SecondaryButton>
        )}
        {primary}
      </div>
    </div>
  )
}

// ── Step bar ─────────────────────────────────────────────────────────────────────────────────

type StepState = 'todo' | 'active' | 'done' | 'failed' | 'skipped'

const STEPS: Record<Phase, [StepState, StepState, StepState]> = {
  scanning: ['active', 'todo', 'todo'],
  'scan-failed': ['failed', 'todo', 'todo'],
  refused: ['failed', 'todo', 'todo'],
  blocked: ['done', 'active', 'failed'],
  review: ['done', 'active', 'todo'],
  'in-sync': ['done', 'done', 'skipped'],
  syncing: ['done', 'done', 'active'],
  saved: ['done', 'done', 'done'],
}

/** Scan → Review → Sync, so the drawer says it is TWO steps before anybody wonders whether opening
 *  it changed something. */
function StepBar({ phase }: { phase: Phase }) {
  const states = STEPS[phase]
  const labels = ['Scan', 'Review', 'Sync']
  return (
    <div data-testid="sync-steps" aria-label="Progress" className="flex items-center gap-2 pt-4">
      {labels.map((label, i) => (
        <Fragment key={label}>
          {i > 0 && (
            <span
              className={`h-px flex-1 ${states[i - 1] === 'done' ? 'bg-pos/40' : 'bg-border-default'}`}
            />
          )}
          <span data-step={label} data-state={states[i]} className="flex items-center gap-[6px]">
            <StepDot state={states[i]} n={i + 1} />
            <span
              className={`text-[11.5px] ${
                states[i] === 'active'
                  ? 'text-text-primary font-semibold'
                  : states[i] === 'failed'
                    ? 'text-neg-text'
                    : 'text-text-tertiary'
              }`}
            >
              {label}
              {states[i] === 'skipped' && ' · not needed'}
            </span>
          </span>
        </Fragment>
      ))}
    </div>
  )
}

function StepDot({ state, n }: { state: StepState; n: number }) {
  const base = 'w-[20px] h-[20px] rounded-full grid place-items-center text-[10.5px] shrink-0'
  if (state === 'done')
    return (
      <span className={`${base} bg-pos-muted border border-pos/50 text-pos-text`}>
        <Check size={11} strokeWidth={3} />
      </span>
    )
  if (state === 'failed')
    return (
      <span className={`${base} bg-neg-muted border border-neg/50 text-neg-text`}>
        <X size={11} strokeWidth={3} />
      </span>
    )
  if (state === 'active')
    return (
      <span
        className={`${base} border border-accent text-accent font-semibold ring-[3px] ring-accent/20`}
      >
        {n}
      </span>
    )
  return (
    <span
      className={`${base} border ${state === 'skipped' ? 'border-dashed' : ''} border-border-default text-text-tertiary`}
    >
      {state === 'skipped' ? '–' : n}
    </span>
  )
}

// ── The hero: the outcome in one card, before any detail ────────────────────────────────────

type Tone = 'accent' | 'gold' | 'pos' | 'warn' | 'neg'

const HERO_TINT: Record<Tone, { card: string; icon: string; title: string }> = {
  accent: {
    card: 'border-accent/35 bg-accent-muted',
    icon: 'bg-accent/15 text-accent',
    title: 'text-accent-text',
  },
  gold: {
    card: 'border-gold/40 bg-gold-muted',
    icon: 'bg-gold/15 text-gold-text',
    title: 'text-gold-text',
  },
  pos: {
    card: 'border-pos/35 bg-pos-muted',
    icon: 'bg-pos/15 text-pos-text',
    title: 'text-pos-text',
  },
  warn: {
    card: 'border-warn/40 bg-warn-muted',
    icon: 'bg-warn/15 text-warn-text',
    title: 'text-warn-text',
  },
  neg: {
    card: 'border-neg/40 bg-neg-muted',
    icon: 'bg-neg/15 text-neg-text',
    title: 'text-neg-text',
  },
}

function Hero({
  phase,
  scan,
  receipt,
  scanError,
  submittedAt,
}: {
  phase: Phase
  scan: AccountSyncPreview | undefined
  receipt: AccountSync | null
  scanError: Error | null
  submittedAt: number
}) {
  const n = scan?.changes.length ?? 0
  const needs = scan?.attention.length ?? 0
  const plural = (k: number, one: string, many: string) => `${k} ${k === 1 ? one : many}`

  let tone: Tone
  let icon: React.ReactNode
  let title: string
  let body: React.ReactNode = null
  let aside: React.ReactNode = null

  switch (phase) {
    case 'scanning':
      tone = 'accent'
      icon = <ScanningIcon />
      title = 'Checking the VPS…'
      body = 'Asking each MT5 terminal which account it’s logged into. Nothing is changed.'
      aside = <Elapsed />
      break
    case 'scan-failed':
      tone = 'neg'
      icon = <ServerCrash size={20} />
      title = 'Couldn’t reach the VPS'
      body = (
        <>
          {errorText(scanError)}
          <p className="mt-1">
            Nothing was changed — the question wasn’t answered, so this says nothing about your
            accounts.
          </p>
        </>
      )
      break
    case 'refused':
      tone = 'warn'
      icon = <ShieldAlert size={20} />
      title = 'The VPS refused the scan'
      body = (
        <>
          {scan?.reason}
          <p className="mt-1">Nothing was changed.</p>
        </>
      )
      break
    case 'blocked':
      tone = 'warn'
      icon = <ShieldAlert size={20} />
      title = 'Sync can’t run right now'
      body = scan?.blocked
      break
    case 'review':
      tone = 'gold'
      icon = <GitCompare size={20} />
      title = `${plural(n, 'change', 'changes')} to make`
      body = (
        <>
          Your list doesn’t match the VPS. Each change is listed below with what it is now and what
          it will be.
          {needs > 0 && ` ${plural(needs, 'thing needs', 'things need')} you as well.`}
        </>
      )
      break
    case 'in-sync':
      tone = 'pos'
      icon = <CheckCircle2 size={20} />
      title = 'Your list matches the VPS'
      body =
        needs > 0
          ? `Nothing for sync to change. ${plural(needs, 'thing needs', 'things need')} you below — sync never changes those.`
          : 'Nothing needs changing.'
      break
    case 'syncing':
      tone = 'accent'
      icon = <Loader2 size={20} className="animate-spin" />
      title = 'Syncing…'
      body = 'Saving the changes to your list, then sending it to the VPS.'
      aside = <Elapsed from={submittedAt || undefined} />
      break
    case 'saved': {
      const saved = receipt?.changes.length ?? 0
      const failed = receipt?.failed.length ?? 0
      const trouble = failed > 0 || !!receipt?.deploy_error
      tone = trouble ? 'warn' : 'pos'
      icon = trouble ? <AlertTriangle size={20} /> : <CheckCircle2 size={20} />
      title =
        saved === 0
          ? 'Nothing could be saved'
          : `Synced — ${plural(saved, 'change', 'changes')} saved`
      body = receipt?.deploy_error
        ? 'Saved on this computer, but not sent to the VPS — see below.'
        : receipt?.deployed
          ? 'Saved and sent to the VPS.'
          : null
      break
    }
  }

  const t = HERO_TINT[tone]
  return (
    <div
      data-testid="sync-hero"
      data-phase={phase}
      className={`rounded-lg border px-4 py-[14px] flex items-start gap-[14px] ${t.card}`}
    >
      <span
        className={`relative w-[40px] h-[40px] rounded-full grid place-items-center shrink-0 ${t.icon}`}
      >
        {icon}
      </span>
      <div className="min-w-0 flex-1">
        <p className={`text-[15px] font-semibold leading-tight ${t.title}`}>{title}</p>
        {body && <div className="text-small text-text-secondary mt-1">{body}</div>}
      </div>
      {aside && <span className="text-[11.5px] text-text-tertiary shrink-0 pt-[2px]">{aside}</span>}
    </div>
  )
}

/** A radar sweep, so a scan that takes a while reads as working rather than hung. Stops for
 *  anyone who has asked their OS for reduced motion. */
function ScanningIcon() {
  return (
    <>
      <span className="absolute inset-0 rounded-full border border-accent/60 motion-safe:animate-radar-ring" />
      <Radar size={20} />
    </>
  )
}

/** Seconds since the step began. ⚠ The interval only sets state from its own callback, and the
 *  component is mounted per step, so it cannot carry one step's clock into the next. */
function Elapsed({ from }: { from?: number }) {
  const [t0] = useState(() => from ?? Date.now())
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])
  const s = Math.max(0, Math.floor((now - t0) / 1000))
  return (
    <span className="font-mono tabular-nums">
      {s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s`}
    </span>
  )
}

// ── What the scan found ──────────────────────────────────────────────────────────────────────

/**
 * The plan, then what it will not touch, then the box itself — in that order, because the reader
 * came to decide whether to press Sync.
 *
 * ⚠ **`after` means this is the list as it is AFTER a sync** (`now`), so anything still in
 * `changes` is something that press did not fix, and is titled that way.
 */
function Plan({ scan, after }: { scan: AccountSyncPreview; after: boolean }) {
  const matches = scan.registry.filter((c) => c.verdict === 'confirmed')
  const wrong = scan.registry.filter((c) => c.verdict === 'contradicted')
  const unchecked = scan.registry.filter((c) => c.verdict === 'unverified')
  return (
    <div className="flex flex-col gap-5">
      {!scan.blocked && scan.changes.length > 0 && (
        <Section title={after ? 'Still out of sync' : 'What sync will change'}>
          {scan.changes.map((c) => (
            <ChangeCard key={`${c.action}-${c.account}`} change={c} />
          ))}
        </Section>
      )}

      {scan.attention.length > 0 && (
        <Section title="Needs you — sync won’t change these">
          {scan.attention.map((a, i) => (
            <AttentionCard key={`${a.account ?? 'terminal'}-${i}`} item={a} />
          ))}
        </Section>
      )}

      <Section title="On the VPS">
        <div className="rounded-lg border border-border-subtle divide-y divide-border-subtle">
          {scan.terminals.map((t) => (
            <TerminalRow key={t.key} terminal={t} />
          ))}
        </div>
      </Section>

      {/* ⚠ Deliberately QUIET. "Couldn't be checked" is not a finding against a row. */}
      {(matches.length > 0 || wrong.length > 0 || unchecked.length > 0) && (
        <div className="text-small text-text-tertiary">
          <p>
            {after ? 'Your list now: ' : 'Your list: '}
            {[
              matches.length > 0 &&
                `${matches.length} match${matches.length === 1 ? 'es' : ''} the VPS`,
              wrong.length > 0 && `${wrong.length} doesn’t`,
              unchecked.length > 0 && `${unchecked.length} couldn’t be checked`,
            ]
              .filter(Boolean)
              .join(' · ')}
          </p>
          {unchecked.length > 0 && (
            <details className="mt-2">
              <summary className="cursor-pointer hover:text-text-secondary">
                Why some couldn’t be checked
              </summary>
              <ul className="mt-2 flex flex-col gap-1 pl-3">
                {unchecked.map((c) => (
                  <li key={c.account}>
                    #{c.account}
                    {c.label ? ` · ${c.label}` : ''} — {c.detail}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </div>
  )
}

/** What one press actually did: saved (with the same field-by-field rows it was approved on), and
 *  what could not be saved. */
function Receipt({ receipt }: { receipt: AccountSync }) {
  return (
    <>
      {/* ⚠ The writes exist on THIS machine and the bots read the copy on the VPS. "Saved" without
          this would describe a change the bots cannot see. */}
      {receipt.deploy_error && (
        <Banner tone="neg" title="Saved here, but not sent to the VPS" testId="sync-deploy-error">
          {receipt.deploy_error}
          <p className="mt-2 opacity-80">
            Your bots read the copy on the VPS, so they won’t see these changes until they’re sent.
          </p>
        </Banner>
      )}
      {receipt.changes.length > 0 && (
        <Section title="What sync changed">
          {receipt.changes.map((c) => (
            <ChangeCard key={`${c.action}-${c.account}`} change={c} saved />
          ))}
        </Section>
      )}
      {receipt.failed.length > 0 && (
        <Section title="Couldn’t be saved">
          {receipt.failed.map((f) => (
            <div
              key={f.account}
              data-testid="sync-failed"
              className="rounded-lg border border-neg/40 bg-neg-muted px-3 py-[10px] flex gap-[10px]"
            >
              <XCircle size={14} className="text-neg-text shrink-0 mt-[2px]" />
              <div className="min-w-0 text-small">
                <p className="font-semibold text-text-primary font-mono">#{f.account}</p>
                <p className="text-neg-text mt-[2px]">{f.reason}</p>
              </div>
            </div>
          ))}
        </Section>
      )}
    </>
  )
}

/**
 * One account's change, field by field: what your list says → what it will say, and how the scan
 * knows. `saved` is the same card after the press, so the receipt reads in the words it was
 * approved in.
 */
function ChangeCard({ change, saved = false }: { change: AccountSyncChange; saved?: boolean }) {
  const isAdd = change.action === 'add'
  return (
    <div
      data-testid={saved ? 'sync-saved' : 'sync-change'}
      className="rounded-lg border border-border-subtle bg-bg-sunken overflow-hidden"
    >
      <div className="flex items-center gap-2 px-3 py-[9px] border-b border-border-subtle">
        {saved ? (
          <Tag tone="pos">
            <Check size={10} strokeWidth={3} /> Saved
          </Tag>
        ) : (
          <Tag tone={isAdd ? 'accent' : 'gold'}>{isAdd ? 'New' : 'Update'}</Tag>
        )}
        <span className="font-mono text-small text-text-primary">#{change.account}</span>
        {change.label && (
          <span className="text-small text-text-secondary truncate">{change.label}</span>
        )}
        {/* ⚠ In words, not only colour: this is the one change that can put real money in play. */}
        {change.live && (
          <span className="ml-auto">
            <Tag tone="neg">Real money</Tag>
          </span>
        )}
      </div>
      {change.diffs.length > 0 && (
        <div className="px-3 py-[10px] flex flex-col gap-[10px]">
          {change.diffs.map((d) => (
            <DiffRow key={d.what} diff={d} />
          ))}
        </div>
      )}
      {(change.said.length > 0 || change.live) && (
        <div className="px-3 pb-[10px] flex flex-col gap-1">
          {change.said.map((s) => (
            <p key={s} className="flex gap-[7px] text-[11.5px] text-text-secondary">
              <Info size={12} className="shrink-0 mt-[2px] text-text-tertiary" />
              {s}
            </p>
          ))}
          {change.live && (
            <p className="text-[11.5px] text-neg-text">
              Sync only {saved ? 'put' : 'puts'} it in your list — no bot moves onto it until you
              say so.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

/**
 * `was → will be`, with the evidence under it.
 *
 * ⚠ **An ADD has no "was"** (`before: null`) — the account is not in your list yet, which is a
 * different fact from a blank field, so no struck-out value is drawn for it.
 */
function DiffRow({ diff }: { diff: AccountSyncDiff }) {
  return (
    <div data-testid="sync-diff" className="grid grid-cols-[118px_1fr] gap-x-3 gap-y-[3px]">
      <span className="text-[11.5px] text-text-tertiary pt-[2px]">{diff.what}</span>
      <span className="flex flex-wrap items-center gap-[6px] min-w-0">
        {diff.before !== null && (
          <>
            <span
              data-testid="diff-before"
              className="font-mono text-[11.5px] px-[6px] py-[1px] rounded-sm bg-neg-muted text-neg-text line-through decoration-neg-text/70 break-all"
            >
              {diff.before}
            </span>
            <ArrowRight size={11} className="text-text-tertiary shrink-0" />
          </>
        )}
        <span
          data-testid="diff-after"
          className="font-mono text-[11.5px] px-[6px] py-[1px] rounded-sm bg-pos-muted text-pos-text break-all"
        >
          {diff.after}
        </span>
      </span>
      {diff.why && (
        <span className="col-start-2 text-[11px] leading-snug text-text-tertiary">{diff.why}</span>
      )}
    </div>
  )
}

function AttentionCard({ item }: { item: AccountSyncAttention }) {
  return (
    <div
      data-testid="sync-attention"
      className="rounded-lg border border-warn/40 bg-warn-muted px-3 py-[10px] flex gap-[10px]"
    >
      <AlertTriangle size={14} className="text-warn-text shrink-0 mt-[2px]" />
      <div className="min-w-0">
        {item.account !== null && (
          <p className="text-small font-semibold text-text-primary">
            <span className="font-mono">#{item.account}</span>
            {item.label ? ` · ${item.label}` : ''}
          </p>
        )}
        <ul className="text-[11.5px] text-warn-text mt-[2px] flex flex-col gap-[3px]">
          {item.said.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ul>
      </div>
    </div>
  )
}

/**
 * The first scan's placeholder for the terminal list. The section title is a fixed word, so it
 * renders REAL rather than shimmering; the plan is not guessed at, because a card-shaped
 * placeholder would promise changes before the box has said there are any.
 */
function TerminalsSkeleton() {
  return (
    <Section title="On the VPS">
      <div className="rounded-lg border border-border-subtle divide-y divide-border-subtle">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="px-3 py-[10px] flex items-center justify-between">
            <Shimmer className="h-[13px] w-[110px]" />
            <Shimmer className="h-[13px] w-[120px]" />
          </div>
        ))}
      </div>
    </Section>
  )
}

/**
 * One terminal, one line: which install, which account, and — only when it needs saying — why.
 *
 * 🔴 **`account: null` never renders alone.** The status line says why it is empty, because a
 * terminal nobody asked and a terminal with no account look identical otherwise.
 */
function TerminalRow({ terminal }: { terminal: ScannedTerminal }) {
  // ⚠ **No bot COUNT.** "Owned by" comes from which bot configs name this terminal, and a benched
  // bot still names it — the first wording said "3 bots trade here" with one of the three
  // trading nothing. A number that includes a bot that is not trading is a wrong number.
  const status =
    terminal.state === 'owned_by_bot'
      ? terminal.account !== null
        ? 'Your bots’ terminal — account reported by the bot'
        : 'Your bots’ terminal — no bot has reported its account yet'
      : terminal.state === 'not_running'
        ? 'Not running, so it couldn’t be checked'
        : terminal.account === null
          ? (terminal.error ?? 'Couldn’t read an account')
          : null
  // The dot says which of the four a row is; the line under it says it in words.
  const dot =
    terminal.state === 'owned_by_bot'
      ? 'bg-accent'
      : terminal.state === 'not_running'
        ? 'bg-text-tertiary'
        : terminal.account === null
          ? 'bg-warn'
          : 'bg-pos'
  return (
    <div className="px-3 py-[10px]">
      <div className="flex items-center justify-between gap-3">
        <span className="flex items-center gap-2 min-w-0">
          <span className={`w-[7px] h-[7px] rounded-full shrink-0 ${dot}`} />
          <span className="text-small text-text-primary truncate" title={terminal.install}>
            {shortName(terminal.install)}
          </span>
        </span>
        <span className="text-small shrink-0 flex items-center gap-2">
          {terminal.account !== null ? (
            <>
              <span className="text-text-primary font-mono">#{terminal.account}</span>
              <KindPill terminal={terminal} />
            </>
          ) : (
            <span className="text-text-tertiary">—</span>
          )}
        </span>
      </div>
      {status && <p className="text-[11.5px] text-text-tertiary mt-[2px] pl-[15px]">{status}</p>}
    </div>
  )
}

/**
 * Demo or live, and what to say when it is not known.
 *
 * ⚠ **"Not reported" and "unrecognised" are different.** A bot reports only the account NUMBER, so
 * a bot-sourced row has no mode by design — nothing is wrong, and a warning colour there is a false
 * alarm on the one terminal that matters most. A terminal the scan itself asked that answered with a
 * flag it did not recognise IS an anomaly, and keeps the warning: guessing "demo" for real money is
 * the failure.
 */
function KindPill({ terminal }: { terminal: ScannedTerminal }) {
  if (terminal.kind === null) {
    if (terminal.account_source === 'bot') {
      return (
        <span
          className="text-small text-text-tertiary"
          title="The bot reports which account it is on, not whether it is demo or live."
        >
          demo/live not reported
        </span>
      )
    }
    return (
      <span
        className="text-small text-warn-text"
        title="The terminal answered with an account type this app does not recognise — whether it is real money is unknown."
      >
        type unknown
      </span>
    )
  }
  return (
    <span
      className={`text-small ${terminal.kind === 'live' ? 'text-neg-text' : 'text-text-tertiary'}`}
    >
      {terminal.kind}
    </span>
  )
}

// ── Small parts ──────────────────────────────────────────────────────────────────────────────

/**
 * The by-hand way in, deliberately quiet and deliberately ALWAYS there.
 *
 * ⚠ **Rendered under every state — scan running, failed, refused.** A stopped terminal can never
 * appear in a scan, and hiding this until the scan answers would leave that account with no way
 * onto the list at all.
 */
function ManualAdd({ onClick }: { onClick: () => void }) {
  return (
    <div className="mt-6 pt-4 border-t border-border-subtle text-small text-text-tertiary">
      Not listed?{' '}
      <button
        data-testid="add-account"
        onClick={onClick}
        className="text-text-secondary underline underline-offset-2 hover:text-text-primary"
      >
        Add it by hand
      </button>{' '}
      — for a terminal that isn’t running, which sync can’t read.
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <p className="text-[9px] font-semibold uppercase tracking-[0.8px] text-gold-text">{title}</p>
      {children}
    </section>
  )
}

function Tag({
  tone,
  children,
}: {
  tone: 'accent' | 'gold' | 'pos' | 'neg'
  children: React.ReactNode
}) {
  const tint = {
    accent: 'bg-accent-muted text-accent-text border-accent/40',
    gold: 'bg-gold-muted text-gold-text border-gold/40',
    pos: 'bg-pos-muted text-pos-text border-pos/40',
    neg: 'bg-neg-muted text-neg-text border-neg/50',
  }[tone]
  return (
    <span
      className={`inline-flex items-center gap-[3px] text-[9.5px] font-semibold uppercase tracking-[0.5px] px-[6px] py-[2px] rounded-sm border ${tint}`}
    >
      {children}
    </span>
  )
}

function Banner({
  tone,
  title,
  testId,
  children,
}: {
  tone: 'neg' | 'warn'
  title: string
  testId?: string
  children?: React.ReactNode
}) {
  const tint = {
    neg: 'bg-neg-muted border-neg/50 text-neg-text',
    warn: 'bg-warn-muted border-warn/50 text-warn-text',
  }[tone]
  return (
    <div data-testid={testId} className={`rounded-lg border px-3 py-[10px] text-small ${tint}`}>
      <p className="font-semibold">{title}</p>
      {children && <div className="mt-1 opacity-90">{children}</div>}
    </div>
  )
}

function PrimaryButton({
  onClick,
  disabled,
  title,
  testId,
  children,
}: {
  onClick?: () => void
  disabled?: boolean
  title?: string
  testId?: string
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      data-testid={testId}
      className="inline-flex items-center gap-[6px] px-4 py-[7px] rounded-md text-[12.5px] font-semibold bg-accent text-bg-base hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-opacity"
    >
      {children}
    </button>
  )
}

function SecondaryButton({
  onClick,
  disabled,
  testId,
  children,
}: {
  onClick: () => void
  disabled?: boolean
  testId?: string
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      data-testid={testId}
      className="inline-flex items-center gap-[6px] px-3 py-[7px] rounded-md text-[12.5px] border border-border-default text-text-secondary hover:text-text-primary hover:bg-bg-hover disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
    >
      {children}
    </button>
  )
}

function SmallButton({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className="text-[12px] px-[10px] py-[5px] rounded-md border border-border-default text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors"
    >
      {children}
    </button>
  )
}

/** The server's own sentence when it sent one, never a status code in front of it. */
function errorText(e: unknown): string {
  if (!e) return ''
  if (e instanceof ApiError) return e.detail
  return String((e as Error).message ?? e)
}

/** `C:\MT5_Scalper` → `MT5_Scalper`. The full path stays in the row's tooltip. */
function shortName(install: string): string {
  const parts = install.split(/[\\/]/).filter(Boolean)
  return parts[parts.length - 1] ?? install
}
