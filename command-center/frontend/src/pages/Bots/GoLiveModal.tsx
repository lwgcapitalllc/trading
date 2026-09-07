/**
 * Move a proven strategy set off its demo account and onto a live one — preview, then type the
 * phrase, then apply.
 *
 * The last hop of backtest → stress test → demo → live, and the only one that spends real money.
 *
 * 🔴 **NOTHING IN THIS FILE DECIDES ANYTHING.** The moves, the literal writes, the warnings, the
 * carried risk ceiling and every refusal arrive from the backend, which plans ONCE and returns the
 * same shape to the preview and the apply. A list built here beside one built there is two answers
 * about a live account, and only one of them was read.
 *
 * 🔴 **ALL OR NOTHING.** Two of three bots on the live account is a strategy set nobody ran, and
 * on every screen afterwards it reads as a finished promotion. There is deliberately no per-bot
 * tick box.
 *
 * 🔴 **THE CONFIRMATION PHRASE IS THE SERVER'S, NEVER INVENTED HERE.** It names the destination
 * account, so it cannot be typed from memory or pasted from a different preview — which is the
 * whole reason it is a phrase rather than a checkbox.
 *
 * 🔴 **THERE IS NO MINIMUM DEMO RECORD** (Aaron's call), so what each bot did on demo is REPORTED
 * and refuses nothing. A bot with no record says so in words: no record reaching this machine is
 * not the same fact as a bot that traded nothing, and rendering it as zero would put a number under
 * a decision about real money that nobody measured.
 */

import { useState } from 'react'
import { AlertTriangle, ArrowRight, Lock, Rocket, X } from 'lucide-react'
import { useGoLivePreview, useApplyGoLive } from '@/hooks/useBots'
import type { BotAccountRegistration, GoLivePlan, GoLiveMove } from '@/types'

interface Props {
  /** The bots being promoted, named explicitly — a promotion that inferred its own membership
   *  would be a live-money write nobody typed the members of. */
  botKeys: string[]
  fromAccount: number
  registry: BotAccountRegistration[]
  onClose: () => void
}

function show(v: unknown): string {
  if (v === null || v === undefined) return 'not set'
  if (typeof v === 'boolean') return v ? 'On' : 'Off'
  if (typeof v === 'number') return String(v)
  if (typeof v === 'string') return v === '' ? '(empty)' : v
  return JSON.stringify(v)
}

function FieldRows({ fields }: { fields: Record<string, unknown> }) {
  const keys = Object.keys(fields)
  if (!keys.length) return null
  return (
    <div className="rounded-md border border-border-subtle overflow-hidden">
      {keys.map((k, i) => (
        <div
          key={k}
          className={`flex items-center gap-3 px-3 py-[5px] text-[11.5px] ${
            i % 2 ? 'bg-bg-sunken' : 'bg-bg-surface'
          }`}
        >
          <span className="font-mono text-text-tertiary flex-1 min-w-0 truncate">{k}</span>
          <span className="font-mono text-accent text-right min-w-0 truncate">
            {show(fields[k])}
          </span>
        </div>
      ))}
    </div>
  )
}

/** What this bot did on demo. Three-state: a reason means no record reached this machine, which is
 *  NOT zero trades and is never drawn as one. */
function RecordLine({ move }: { move: GoLiveMove }) {
  const r = move.record
  if (!r) return null
  if (!r.traded) {
    return (
      <div className="text-[11.5px] text-warn-text leading-relaxed">
        No demo record — {r.reason ?? 'nothing reached this machine'}. That is not the same as
        having traded nothing.
      </div>
    )
  }
  return (
    <div className="text-[11.5px] text-text-secondary leading-relaxed">
      On demo: {r.closed_trades ?? '—'} closed
      {r.wins != null && r.losses != null && ` · ${r.wins}W / ${r.losses}L`}
      {r.realised_r != null && ` · ${r.realised_r > 0 ? '+' : ''}${r.realised_r.toFixed(2)}R`}
      {r.records_from && r.records_to && (
        <span className="text-text-tertiary">
          {' '}
          · {r.records_from} → {r.records_to}
        </span>
      )}
    </div>
  )
}

function PlanBody({ plan }: { plan: GoLivePlan }) {
  if (plan.blocked) {
    return (
      <div className="rounded-lg border border-neg-text/30 bg-neg-muted p-3.5 flex gap-2.5">
        <Lock size={14} className="text-neg-text flex-shrink-0 mt-[2px]" />
        <div className="text-[12px] text-neg-text leading-relaxed">{plan.blocked}</div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2 text-[12.5px]">
        <span className="font-mono tabular-nums text-text-secondary">{plan.from_account}</span>
        <ArrowRight size={13} className="text-text-tertiary" />
        <span className="font-mono tabular-nums font-semibold text-warn-text">
          {plan.to_account}
        </span>
        {plan.cap_pct != null && (
          <span className="ml-2 text-[11.5px] text-text-tertiary">
            risk ceiling {plan.cap_pct}% carried across
          </span>
        )}
      </div>

      {/* Every bot, with the LITERAL writes — this is the last screen before real money, so the
          reader gets what will be written rather than a summary of it. */}
      {plan.moves.map((m) => (
        <div key={m.bot} className="flex flex-col gap-2">
          <div className="flex items-baseline gap-2">
            <span className="text-[12.5px] font-semibold text-text-primary">
              {m.display || m.bot}
            </span>
            <span className="text-[11px] text-text-tertiary font-mono">{m.bot}</span>
          </div>
          <RecordLine move={m} />
          <FieldRows fields={m.fields} />
          <FieldRows fields={m.param_fields} />
          {m.notes.length > 0 && (
            <div className="text-[11.5px] text-text-tertiary leading-relaxed">
              {m.notes.join(' · ')}
            </div>
          )}
        </div>
      ))}

      {/* Loud, and none of them refuses. */}
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

export function GoLiveModal({ botKeys, fromAccount, registry, onClose }: Props) {
  const preview = useGoLivePreview()
  const apply = useApplyGoLive()
  const [account, setAccount] = useState<number | null>(null)
  const [typed, setTyped] = useState('')

  // Only LIVE accounts are destinations, and the server refuses a demo one in its own words. An
  // account with no terminal is LISTED and DISABLED with the reason on it, never hidden — a
  // destination that silently vanishes reads as a bug, and the reader needs to see it exists.
  const live = registry.filter((a) => a.kind === 'live')

  const plan = preview.data
  const phrase = plan?.confirm ?? ''
  const canApply =
    !!plan && !plan.blocked && plan.moves.length > 0 && typed === phrase && !apply.isPending

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        data-testid="go-live-modal"
        className="bg-bg-surface border border-warn/40 rounded-xl w-full max-w-[680px] shadow-2xl flex flex-col max-h-[88vh] overflow-hidden"
      >
        <div className="flex items-start justify-between px-5 py-4 border-b border-border-subtle">
          <div className="min-w-0">
            <h2 className="text-[15px] font-semibold text-text-primary flex items-center gap-2">
              <Rocket size={14} className="text-warn-text" />
              Take this set live
            </h2>
            <p className="text-[12px] text-text-secondary mt-[3px] leading-relaxed">
              Moves every bot on account {fromAccount} onto a live account, all together or not at
              all. It does not deploy code and it does not start anything — which account a bot
              trades is read at startup, so nothing is true on the box until you restart them.
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-text-tertiary hover:text-text-primary transition-colors flex-shrink-0 ml-3"
          >
            <X size={16} />
          </button>
        </div>

        <div className="px-5 py-4 overflow-y-auto flex flex-col gap-4">
          <div>
            <div className="text-[10px] uppercase tracking-[0.6px] text-text-secondary mb-2">
              Onto which live account
            </div>
            {live.length === 0 ? (
              <div className="text-[12px] text-text-tertiary leading-relaxed">
                No live account is registered. Add one on this page first — a demo account cannot be
                a destination.
              </div>
            ) : (
              <div className="flex flex-col gap-1.5">
                {live.map((a) => {
                  const selected = account === a.account
                  return (
                    <button
                      key={a.account}
                      disabled={!a.assignable}
                      title={a.assignable ? undefined : a.unassignable_reason}
                      onClick={() => {
                        setAccount(a.account)
                        setTyped('')
                        preview.mutate({ bots: botKeys, account: a.account })
                      }}
                      className={`flex items-center gap-2.5 px-3 py-2 rounded-md border text-[12px] text-left transition-colors ${
                        selected
                          ? 'border-warn/60 bg-warn-muted text-text-primary'
                          : a.assignable
                            ? 'border-border-subtle bg-bg-sunken text-text-secondary hover:border-border-default'
                            : 'border-border-subtle bg-bg-sunken text-text-tertiary cursor-not-allowed'
                      }`}
                    >
                      <span className="font-mono tabular-nums font-semibold">{a.account}</span>
                      <span>{a.label || a.broker}</span>
                      <span className="ml-auto text-[11px] text-text-tertiary">
                        {a.assignable ? a.tier : a.unassignable_reason}
                      </span>
                    </button>
                  )
                })}
              </div>
            )}
          </div>

          {preview.isPending && (
            <div className="text-[12px] text-text-secondary">
              Working out what would move&hellip;
            </div>
          )}
          {preview.isError && (
            <div className="rounded-lg border border-neg-text/30 bg-neg-muted p-3.5 text-[12px] text-neg-text leading-relaxed">
              Could not work out what would move. Nothing has been written.
            </div>
          )}
          {plan && <PlanBody plan={plan} />}

          {/* The phrase names the account, so it cannot be typed from memory or carried over from
              a different preview. It is served, never built here. */}
          {plan && !plan.blocked && plan.moves.length > 0 && (
            <div className="rounded-lg border border-warn/40 bg-warn-muted/40 px-3.5 py-3 flex flex-col gap-2">
              <div className="text-[12px] text-warn-text leading-relaxed">
                Type <span className="font-mono font-semibold">{phrase}</span> to confirm.
              </div>
              <input
                data-testid="go-live-confirm"
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                spellCheck={false}
                autoComplete="off"
                className="w-full bg-bg-sunken border border-border-subtle rounded px-2.5 py-1.5 text-[12.5px] font-mono text-text-primary"
              />
            </div>
          )}
        </div>

        <div className="flex items-center justify-between gap-3 px-5 py-3.5 border-t border-border-subtle">
          <div className="text-[11px] text-text-tertiary leading-relaxed min-w-0">
            {canApply && <>Every bot keeps trading its demo account until it is restarted.</>}
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
                apply.mutate(
                  { bots: botKeys, account: account as number, confirm: typed, deploy: true },
                  { onSuccess: () => onClose() }
                )
              }
              className={`px-3.5 py-[6px] rounded-md text-[12px] font-medium transition-colors ${
                canApply
                  ? 'bg-warn text-bg-base hover:opacity-90'
                  : 'bg-bg-sunken text-text-tertiary cursor-not-allowed border border-border-subtle'
              }`}
            >
              {apply.isPending ? 'Moving…' : 'Move them to live'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
