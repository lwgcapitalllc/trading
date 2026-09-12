/**
 * The two pieces of adding a bot that the reader SEES — the ways to make room, and the live
 * confirmation. The logic (what each choice writes, and in which order) is `joinAccount.ts`.
 */
import { AlertTriangle, ArrowUp, Scale, Minus, Loader2 } from 'lucide-react'
import type { BotAccountRiskPlan } from '@/types'
import { pct, roomShare, type JoinChoice } from './joinAccount'

/**
 * The ways to make room for a bot whose risk does not fit, as buttons — each one a complete action,
 * so the reader picks an outcome rather than working out a sequence of edits.
 *
 * ⚠ **A way the server cannot offer is not drawn.** No room left means no "join at the room"; a fit
 * that would need a cap past 100% or a share under 0.1% arrives as `null` and has no button. When
 * nothing is left, it says what to do by hand rather than showing an empty box.
 */
export function JoinChoices({
  plan,
  room,
  risk,
  display,
  busy,
  onChoose,
}: {
  /** The server's plan for this bot joining. */
  plan: BotAccountRiskPlan
  /** The account's served room BEFORE the bot joins. */
  room: number | null | undefined
  /** The bot's own risk per trade. */
  risk: number | null
  display: string
  busy: boolean
  onChoose: (c: JoinChoice) => void
}) {
  const at = roomShare(room)
  const names = new Map(plan.bots.map((b) => [b.key, b.display]))
  const fit = plan.fit_shares
  const options: {
    testId: string
    icon: typeof ArrowUp
    title: string
    detail: string
    choice: JoinChoice
  }[] = []
  if (at != null)
    options.push({
      testId: 'join-at-room',
      icon: Minus,
      title: `Add at ${pct(at)} a trade`,
      detail: `${display} risks ${pct(at)} a trade instead of ${pct(risk)} — the room still free. Nothing else on the account changes.`,
      choice: { kind: 'at-room', riskPct: at },
    })
  if (plan.fit_cap != null)
    options.push({
      testId: 'join-raise-cap',
      icon: ArrowUp,
      title: `Raise the cap to ${pct(plan.fit_cap)}`,
      detail: `${display} keeps ${pct(risk)} a trade. Every bot on the account takes the new cap the next time it has no open trade.`,
      choice: { kind: 'raise-cap', cap: plan.fit_cap },
    })
  if (fit)
    options.push({
      testId: 'join-fit-all',
      icon: Scale,
      title: `Scale every bot to fit ${pct(plan.risk_cap_pct)}`,
      detail: Object.entries(fit)
        .map(([k, v]) => `${names.get(k) ?? display} ${pct(v)}`)
        .join(' · '),
      choice: { kind: 'fit-all', shares: fit },
    })

  return (
    <div
      data-testid="join-choices"
      className="rounded-md border border-warn/40 bg-warn-muted/40 px-3 py-[10px]"
    >
      <p className="text-[11.5px] text-warn-text leading-[1.5]">{plan.refused ?? plan.reason}</p>
      {options.length === 0 ? (
        <p className="text-[11.5px] text-text-secondary mt-[6px] leading-[1.5]">
          There is no one-click way to make room. Lower another bot&rsquo;s risk or raise the cap on
          the account, then add {display}.
        </p>
      ) : (
        <>
          <p className="text-[9.5px] font-semibold uppercase tracking-[0.8px] text-text-tertiary mt-[9px] mb-[6px]">
            Make room — pick one
          </p>
          <div className="flex flex-col gap-[5px]">
            {options.map((o) => (
              <button
                key={o.testId}
                data-testid={o.testId}
                disabled={busy}
                onClick={() => onChoose(o.choice)}
                className="group flex items-start gap-[10px] w-full text-left px-[10px] py-[8px] rounded-md border border-border-default bg-bg-surface hover:border-accent/50 hover:bg-accent-muted transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <o.icon size={13} className="mt-[2px] shrink-0 text-accent-text" />
                <span className="min-w-0">
                  <span className="block text-[12.5px] font-medium text-text-primary">
                    {o.title}
                  </span>
                  <span className="block text-[11px] text-text-tertiary mt-[1px] leading-[1.45]">
                    {o.detail}
                  </span>
                </span>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

/**
 * The step before a bot is put on a LIVE account. It names the account, says real money in words,
 * and reads back exactly what will happen — the only point at which a wrong click is still free.
 */
export function LiveConfirm({
  account,
  what,
  verb,
  busy,
  onConfirm,
  onCancel,
}: {
  account: number
  /** What will happen, in one sentence (`describeChoice`). */
  what: string
  /** The confirm button's words — "Add to live account", "Move to live account". */
  verb: string
  busy: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <div
      data-testid="live-confirm"
      className="rounded-md border border-warn/60 bg-warn-muted px-3 py-[11px]"
    >
      <p className="flex items-center gap-[7px] text-[12.5px] font-semibold text-warn-text">
        <AlertTriangle size={13} className="shrink-0" />
        Account {account} is a LIVE account — real money
      </p>
      <p className="text-[12px] text-text-secondary mt-[5px] leading-[1.5]">
        {what} It trades real money from its next start.
      </p>
      <div className="flex items-center gap-2 mt-[10px]">
        <button
          data-testid="live-confirm-go"
          disabled={busy}
          onClick={onConfirm}
          className="inline-flex items-center gap-[6px] px-3 py-[6px] rounded-md text-[12px] font-semibold border border-warn/70 bg-warn/15 text-warn-text hover:bg-warn/25 transition-colors disabled:opacity-50"
        >
          {busy && <Loader2 size={12} className="animate-spin" />}
          {verb}
        </button>
        <button
          data-testid="live-confirm-cancel"
          disabled={busy}
          onClick={onCancel}
          className="px-3 py-[6px] rounded-md text-[12px] border border-border-default text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}
