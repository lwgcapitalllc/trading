/**
 * Copy a graded stress test's settings onto a DEMO bot — preview, then apply.
 *
 * The pipeline is backtest → stress test → demo → live, and this is the third hop. Before it
 * existed the only way to move settings from a good result onto a bot was hand-editing that
 * bot's instance config and restarting.
 *
 * 🔴 **NOTHING IN THIS FILE DECIDES ANYTHING.** The list, the warnings, the dropped settings and
 * the refusal all arrive from the backend, which builds them ONCE and returns the same shape to
 * the preview and the apply. A list assembled here beside one assembled there is two answers
 * about a live bot, and only one of them was approved — which is the single failure this whole
 * flow exists to prevent. Do not sort, filter, re-label or re-derive; render what came back.
 *
 * ⚠ **A live bot is refused by the BACKEND, not hidden by this modal.** Live bots are listed and
 * disabled with the reason on them: a bot that silently vanishes from a picker reads as a bug,
 * and the reader needs to see that the demo→live stage exists rather than wonder where their bot
 * went.
 */

import { useState } from 'react'
import { AlertTriangle, ArrowRight, Check, Info, Lock, X } from 'lucide-react'
import { useBotSnapshot, useSettingsImportPreview, useApplySettingsImport } from '@/hooks/useBots'
import type { BotSettingImportPlan } from '@/types'

interface Props {
  stressTestId: string
  /** For the header only — the reader should see which result they are copying from. */
  strategyName?: string | null
  grade?: string | null
  onClose: () => void
}

/** A setting value as one short string. Booleans read as On/Off because that is what the bot's
 *  own settings page calls them; `null`/absent reads as "not set", which is a different fact
 *  from Off and must not be collapsed into it. */
function show(v: unknown): string {
  if (v === null || v === undefined) return 'not set'
  if (typeof v === 'boolean') return v ? 'On' : 'Off'
  if (typeof v === 'number') return String(v)
  if (typeof v === 'string') return v === '' ? '(empty)' : v
  return JSON.stringify(v)
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2 text-[12px] leading-relaxed">
      <span className="text-text-tertiary flex-shrink-0 mt-[2px]">{label}</span>
      <span className="text-text-secondary min-w-0">{children}</span>
    </div>
  )
}

function PlanBody({ plan }: { plan: BotSettingImportPlan }) {
  if (plan.blocked) {
    return (
      <div className="rounded-lg border border-neg-text/30 bg-neg-muted p-3.5 flex gap-2.5">
        <Lock size={14} className="text-neg-text flex-shrink-0 mt-[2px]" />
        <div className="text-[12px] text-neg-text leading-relaxed">{plan.blocked}</div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3.5">
      {/* ── the list the reader approves ─────────────────────────────────────── */}
      {plan.changes.length === 0 ? (
        <div className="rounded-lg border border-border-subtle bg-bg-sunken p-3.5 flex gap-2.5">
          <Check size={14} className="text-pos-text flex-shrink-0 mt-[2px]" />
          <div className="text-[12px] text-text-secondary leading-relaxed">
            This bot already matches the stress test on every setting it can take. Nothing would be
            written.
          </div>
        </div>
      ) : (
        <div>
          <div className="text-[10px] uppercase tracking-[0.6px] text-text-secondary mb-2">
            {plan.changes.length} setting{plan.changes.length === 1 ? '' : 's'} would change
          </div>
          <div className="rounded-lg border border-border-subtle overflow-hidden">
            {plan.changes.map((c, i) => (
              <div
                key={c.name}
                className={`flex items-center gap-3 px-3 py-2 text-[12px] ${
                  i % 2 ? 'bg-bg-sunken' : 'bg-bg-surface'
                }`}
              >
                <span className="font-mono text-text-primary flex-1 min-w-0 truncate">
                  {c.name}
                </span>
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
        </div>
      )}

      {/* ── warnings: every one is loud and none of them refuses ──────────────── */}
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

      {/* ── settings the bot's strategy cannot take ───────────────────────────── */}
      {plan.dropped_notes.length > 0 && (
        <div className="rounded-lg border border-border-subtle bg-bg-sunken p-3.5 flex flex-col gap-2">
          {plan.dropped_notes.map((n) => (
            <div key={n} className="flex gap-2.5">
              <Info size={13} className="text-text-tertiary flex-shrink-0 mt-[2px]" />
              <div className="text-[12px] text-text-secondary leading-relaxed">{n}</div>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-col gap-1 pt-0.5">
        {plan.unchanged_count > 0 && (
          <Row label="Already matching">
            {plan.unchanged_count} setting{plan.unchanged_count === 1 ? '' : 's'}
          </Row>
        )}
        {plan.untouched.length > 0 && (
          <Row label="Left as they are">
            {plan.untouched.length} setting{plan.untouched.length === 1 ? '' : 's'} the run never
            mentions
          </Row>
        )}
      </div>
    </div>
  )
}

export function SettingsImportModal({ stressTestId, strategyName, grade, onClose }: Props) {
  const { data: snapshot } = useBotSnapshot()
  const [botKey, setBotKey] = useState<string | null>(null)

  const bots = snapshot?.bots ?? []
  const { data: plan, isLoading, error } = useSettingsImportPreview(botKey, stressTestId)
  const apply = useApplySettingsImport()

  // Nothing to apply when the plan refuses, proposes nothing, or has not arrived. The button
  // reflects the PLAN rather than a guess made here — see the file header.
  const canApply = !!plan && !plan.blocked && plan.changes.length > 0 && !apply.isPending

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="bg-bg-surface border border-border-default rounded-xl w-full max-w-[640px] shadow-2xl flex flex-col max-h-[88vh] overflow-hidden">
        {/* ── Header ───────────────────────────────────────────────────────────── */}
        <div className="flex items-start justify-between px-5 py-4 border-b border-border-subtle">
          <div className="min-w-0">
            <h2 className="text-[15px] font-semibold text-text-primary">Copy settings to a bot</h2>
            <p className="text-[12px] text-text-secondary mt-[3px] leading-relaxed">
              Writes this stress test&rsquo;s settings onto a demo bot. It does not restart the bot
              and it does not deploy code.
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
          <div className="flex flex-col gap-1">
            <Row label="From">
              {strategyName || 'this stress test'}
              {grade ? ` · graded ${grade}` : ' · not graded'}
            </Row>
          </div>

          {/* Bot picker — live bots are shown and disabled, never hidden. */}
          <div>
            <div className="text-[10px] uppercase tracking-[0.6px] text-text-secondary mb-2">
              Onto which bot
            </div>
            <div className="flex flex-col gap-1.5">
              {bots.length === 0 && (
                <div className="text-[12px] text-text-tertiary">No bots are registered.</div>
              )}
              {bots.map((b) => {
                const isLive = b.account_type === 'live'
                const selected = botKey === b.key
                return (
                  <button
                    key={b.key}
                    disabled={isLive}
                    onClick={() => setBotKey(b.key)}
                    className={`flex items-center gap-2.5 px-3 py-2 rounded-md border text-[12px] text-left transition-colors ${
                      selected
                        ? 'border-accent bg-accent/10 text-text-primary'
                        : isLive
                          ? 'border-border-subtle bg-bg-sunken text-text-tertiary cursor-not-allowed'
                          : 'border-border-subtle bg-bg-sunken text-text-secondary hover:border-border-default'
                    }`}
                  >
                    <span className="font-medium">{b.name}</span>
                    <span className="font-mono text-[11px] text-text-tertiary">{b.key}</span>
                    <span className="ml-auto flex items-center gap-1.5 text-[11px]">
                      {isLive ? (
                        <>
                          <Lock size={11} />
                          live &mdash; a separate stage
                        </>
                      ) : (
                        <span className="text-text-tertiary">demo</span>
                      )}
                    </span>
                  </button>
                )
              })}
            </div>
          </div>

          {botKey && isLoading && (
            <div className="text-[12px] text-text-secondary">Reading the bot&rsquo;s settings…</div>
          )}
          {botKey && error && (
            <div className="rounded-lg border border-neg-text/30 bg-neg-muted p-3.5 text-[12px] text-neg-text leading-relaxed">
              Could not read what would change. Nothing has been written.
            </div>
          )}
          {plan && <PlanBody plan={plan} />}
        </div>

        {/* ── Footer ───────────────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between gap-3 px-5 py-3.5 border-t border-border-subtle">
          <div className="text-[11px] text-text-tertiary leading-relaxed min-w-0">
            {plan && !plan.blocked && plan.changes.length > 0 && (
              <>The bot keeps trading its current settings until it is restarted.</>
            )}
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
              onClick={() =>
                apply.mutate({ botName: botKey!, stressTestId }, { onSuccess: () => onClose() })
              }
              className={`px-3.5 py-[6px] rounded-md text-[12px] font-medium transition-colors ${
                canApply
                  ? 'bg-accent text-white hover:bg-accent/90'
                  : 'bg-bg-sunken text-text-tertiary cursor-not-allowed border border-border-subtle'
              }`}
            >
              {apply.isPending ? 'Writing…' : 'Apply these settings'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
