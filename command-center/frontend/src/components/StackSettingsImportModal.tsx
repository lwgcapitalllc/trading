/**
 * Copy a graded STACK's settings onto its bots — preview, then apply.
 *
 * The pipeline is backtest → stress test → demo → live, and this is the third hop for a whole
 * strategy set rather than one strategy. Its single-bot twin is `SettingsImportModal`; the shape
 * of the flow is deliberately identical, so a reader who has used one has used both.
 *
 * 🔴 **NOTHING IN THIS FILE DECIDES ANYTHING.** Every leg, every change, the account's ceiling,
 * the warnings and the refusal all arrive from the backend, which builds them ONCE and returns the
 * same shape to the preview and the apply. A list assembled here beside one assembled there is two
 * answers about live bots, and only one of them was approved. Do not sort, filter, re-label or
 * re-derive; render what came back.
 *
 * 🔴 **IT IS ALL OR NOTHING, AND THERE IS NO PER-LEG CONTROL — deliberately.** A shared-account
 * stack is a measurement of several strategies competing for one balance and one budget; writing
 * three of its four legs produces a strategy set nobody has measured, and it reads on every screen
 * as a completed copy. Offering a tick box per leg would make that the easy mistake.
 */

import { AlertTriangle, ArrowRight, Check, Info, Lock, X } from 'lucide-react'
import { useStackSettingsImportPreview, useApplyStackSettingsImport } from '@/hooks/useBots'
import type { StackSettingImportPlan } from '@/types'

interface Props {
  stressTestId: string
  /** For the header only — the reader should see which result they are copying from. */
  stackName?: string | null
  grade?: string | null
  onClose: () => void
}

/** A setting value as one short string. Booleans read as On/Off because that is what the bot's own
 *  settings page calls them; `null`/absent reads as "not set", which is a different fact from Off
 *  and must not be collapsed into it. */
function show(v: unknown): string {
  if (v === null || v === undefined) return 'not set'
  if (typeof v === 'boolean') return v ? 'On' : 'Off'
  if (typeof v === 'number') return String(v)
  if (typeof v === 'string') return v === '' ? '(empty)' : v
  return JSON.stringify(v)
}

function ChangeRows({ changes }: { changes: StackSettingImportPlan['legs'][number]['changes'] }) {
  return (
    <div className="rounded-lg border border-border-subtle overflow-hidden">
      {changes.map((c, i) => (
        <div
          key={c.name}
          className={`flex items-center gap-3 px-3 py-2 text-[12px] ${
            i % 2 ? 'bg-bg-sunken' : 'bg-bg-surface'
          }`}
        >
          <span className="font-mono text-text-primary flex-1 min-w-0 truncate">{c.name}</span>
          <span className="font-mono text-text-tertiary text-right w-[120px] truncate">
            {show(c.current)}
          </span>
          <ArrowRight size={12} className="text-text-tertiary flex-shrink-0" />
          <span className="font-mono text-accent text-left w-[160px] truncate">
            {show(c.proposed)}
          </span>
        </div>
      ))}
    </div>
  )
}

function PlanBody({ plan }: { plan: StackSettingImportPlan }) {
  if (plan.blocked) {
    return (
      <div className="rounded-lg border border-neg-text/30 bg-neg-muted p-3.5 flex gap-2.5">
        <Lock size={14} className="text-neg-text flex-shrink-0 mt-[2px]" />
        <div className="text-[12px] text-neg-text leading-relaxed">{plan.blocked}</div>
      </div>
    )
  }

  const totalChanges = plan.legs.reduce((sum, leg) => sum + leg.changes.length, 0)
  const capMoves = !!plan.cap && plan.cap.current !== plan.cap.proposed

  return (
    <div className="flex flex-col gap-4">
      {/* ── The account's own ceiling ───────────────────────────────────────── */}
      {plan.cap && (
        <div className="rounded-lg border border-border-subtle bg-bg-sunken px-3.5 py-3">
          <div className="text-[10px] uppercase tracking-[0.6px] text-text-secondary mb-1.5">
            Account risk ceiling
          </div>
          <div className="flex items-center gap-3 text-[12px]">
            <span className="font-mono text-text-tertiary">{show(plan.cap.current)}</span>
            <ArrowRight size={12} className="text-text-tertiary flex-shrink-0" />
            <span className="font-mono text-accent">{show(plan.cap.proposed)}</span>
            {!capMoves && <span className="text-text-tertiary">— unchanged</span>}
          </div>
          {/* The ceiling is stored per bot, so moving it means writing EVERY bot on the account,
              not only this stack's legs. A bot left behind leaves the account holding two
              different numbers, and then none of them will start. */}
          {capMoves && plan.cap.bots_to_write.length > 0 && (
            <div className="text-[11px] text-text-tertiary leading-relaxed mt-1.5">
              Written to every bot on the account: {plan.cap.bots_to_write.join(', ')}
            </div>
          )}
        </div>
      )}

      {/* ── One block per leg ───────────────────────────────────────────────── */}
      {totalChanges === 0 && !capMoves ? (
        <div className="rounded-lg border border-border-subtle bg-bg-sunken p-3.5 flex gap-2.5">
          <Check size={14} className="text-pos-text flex-shrink-0 mt-[2px]" />
          <div className="text-[12px] text-text-secondary leading-relaxed">
            These bots already match this stack on every setting they can take. Nothing would be
            written.
          </div>
        </div>
      ) : (
        plan.legs.map((leg) => (
          <div key={leg.strategy_id} className="flex flex-col gap-2">
            <div className="flex items-baseline gap-2">
              <span className="text-[12.5px] font-semibold text-text-primary">{leg.bot}</span>
              <span className="text-[11px] text-text-tertiary font-mono">{leg.strategy_id}</span>
              <span className="ml-auto text-[10px] uppercase tracking-[0.6px] text-text-secondary">
                {leg.changes.length} would change
              </span>
            </div>
            {leg.changes.length > 0 && <ChangeRows changes={leg.changes} />}
            {/* NAMED, never dropped in silence: the bot refuses to start on a setting its strategy
                does not declare, and one that vanishes without a word is one the reader believes
                they applied. */}
            {leg.dropped_notes.length > 0 && (
              <div className="rounded-lg border border-border-subtle bg-bg-sunken px-3.5 py-2.5 flex flex-col gap-1.5">
                {leg.dropped_notes.map((n) => (
                  <div key={n} className="flex gap-2.5">
                    <Info size={13} className="text-text-tertiary flex-shrink-0 mt-[2px]" />
                    <div className="text-[12px] text-text-secondary leading-relaxed">{n}</div>
                  </div>
                ))}
              </div>
            )}
            <div className="text-[11px] text-text-tertiary leading-relaxed">
              {leg.unchanged_count} already matching
              {leg.untouched.length > 0 && ` · ${leg.untouched.length} the stack never mentions`}
            </div>
          </div>
        ))
      )}

      {/* ── Warnings: every one is loud and none of them refuses ─────────────── */}
      {plan.warnings.length > 0 && (
        <div className="rounded-lg border border-warn-text/30 bg-warn-muted p-3.5 flex flex-col gap-2">
          {plan.warnings.map((w) => (
            <div key={w} className="flex gap-2.5">
              <AlertTriangle size={13} className="text-warn-text flex-shrink-0 mt-[2px]" />
              <div className="text-[12px] text-warn-text leading-relaxed">{w}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function StackSettingsImportModal({ stressTestId, stackName, grade, onClose }: Props) {
  const { data: plan, isLoading, error } = useStackSettingsImportPreview(stressTestId)
  const apply = useApplyStackSettingsImport()

  const capMoves = !!plan?.cap && plan.cap.current !== plan.cap.proposed
  const totalChanges = plan?.legs.reduce((sum, leg) => sum + leg.changes.length, 0) ?? 0
  // Reflects the PLAN, never a guess made here — see the file header. A button whose only outcome
  // is an error toast is the defect this app has recorded twice.
  const canApply = !!plan && !plan.blocked && (totalChanges > 0 || capMoves) && !apply.isPending

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        data-testid="stack-settings-import-modal"
        className="bg-bg-surface border border-border-default rounded-xl w-full max-w-[680px] shadow-2xl flex flex-col max-h-[88vh] overflow-hidden"
      >
        {/* ── Header ───────────────────────────────────────────────────────────── */}
        <div className="flex items-start justify-between px-5 py-4 border-b border-border-subtle">
          <div className="min-w-0">
            <h2 className="text-[15px] font-semibold text-text-primary">
              Copy this strategy set onto its bots
            </h2>
            <p className="text-[12px] text-text-secondary mt-[3px] leading-relaxed">
              Writes every leg&rsquo;s settings and the account&rsquo;s risk ceiling in one go. It
              does not restart the bots and it does not deploy code.
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-text-tertiary hover:text-text-primary transition-colors flex-shrink-0 ml-3"
          >
            <X size={16} />
          </button>
        </div>

        {/* ── Body ─────────────────────────────────────────────────────────────── */}
        <div className="px-5 py-4 overflow-y-auto flex flex-col gap-4">
          <div className="flex items-start gap-2 text-[12px] leading-relaxed">
            <span className="text-text-tertiary flex-shrink-0 mt-[2px]">From</span>
            <span className="text-text-secondary min-w-0">
              {stackName || 'this stress test'}
              {grade ? ` · graded ${grade}` : ' · not graded'}
              {plan?.account != null && ` · account ${plan.account}`}
            </span>
          </div>

          {isLoading && (
            <div className="text-[12px] text-text-secondary">
              Reading what each bot is set to&hellip;
            </div>
          )}
          {error && (
            <div className="rounded-lg border border-neg-text/30 bg-neg-muted p-3.5 text-[12px] text-neg-text leading-relaxed">
              Could not read what would change. Nothing has been written.
            </div>
          )}
          {plan && <PlanBody plan={plan} />}
        </div>

        {/* ── Footer ───────────────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between gap-3 px-5 py-3.5 border-t border-border-subtle">
          <div className="text-[11px] text-text-tertiary leading-relaxed min-w-0">
            {canApply && <>Every bot keeps trading its current settings until it is restarted.</>}
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              onClick={onClose}
              className="px-3 py-[6px] rounded-md text-[12px] font-medium text-text-secondary hover:text-text-primary border border-border-subtle hover:border-border-default transition-colors"
            >
              Cancel
            </button>
            <button
              disabled={!canApply}
              onClick={() => apply.mutate(stressTestId, { onSuccess: () => onClose() })}
              className={`px-3.5 py-[6px] rounded-md text-[12px] font-medium transition-colors ${
                canApply
                  ? 'bg-accent text-white hover:bg-accent/90'
                  : 'bg-bg-sunken text-text-tertiary cursor-not-allowed border border-border-subtle'
              }`}
            >
              {apply.isPending ? 'Writing…' : 'Apply to every bot'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
