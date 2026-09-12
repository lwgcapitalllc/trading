/**
 * Put a free bot on this account — the list the account panel's "Add bot" opens.
 *
 * 🔴 **It lists ONLY bots on no account (2026-09-11).** It listed every bot not already here,
 * including bots trading another account, greyed while running — so the demo account offered
 * both LIVE bots, one click from being pulled off real money once stopped. Aaron: *"it should
 * just show available bots that is it."* Moving a bot between accounts is the bot panel's own
 * account selector, where the bot being moved is the subject.
 *
 * ⚠ **The row says what the ACCOUNT cares about: the bot's name and its risk per trade.** The
 * symbol went (*"the account doesn't care"*) — adding a bot rewrites it onto this account's
 * suffix anyway. Risk stays because the account's cap is the budget every share comes out of.
 *
 * 🔴 **A bot that does not fit says so on its row and offers the ways to make room (2026-09-11).**
 * Adding it used to be refused after the click, and the fix took two writes on two panels. Whether
 * it fits is the SERVER's answer (`useJoinPlans`, one plan per free bot) — never worked out here —
 * and the three ways out are `JoinChoices`. A bot the server has not answered for yet is offered a
 * plain Add, and the server is the gate.
 *
 * 🔴 **A LIVE account confirms every add on screen first (2026-09-11)** — the server refuses a
 * move onto a live account without `confirm_live`, and the confirmation is the only place that
 * reads back what is about to happen to real money.
 *
 * 🔴 **An empty account asks for its cap HERE (2026-09-11).** The cap is stored per bot, so an
 * account with no bot has none: the first bot started uncapped, the watchdog started it within a
 * minute, and a cap saved afterwards could not reach the running process. The first add now
 * carries the ceiling; every later bot adopts it on the server. ⚠ Unticked sends `null` —
 * "uncapped" chosen — never nothing, which the server reads as not chosen.
 *
 * ⚠ **It writes nothing itself** — `onPick` hands the choice back and the account panel carries
 * it out through `useJoinAccount`, the same function the bot panel uses.
 */
import { useState } from 'react'
import { Bot, Check, ChevronDown, Loader2, Plus, X } from 'lucide-react'
import { useBotAccounts, useJoinPlans } from '@/hooks/useBots'
import type { BotAccountGroup } from '@/types'
import { DecimalInput } from '@/components/DecimalInput'
import { Shimmer } from '@/components/Shimmer'
import { JoinChoices, LiveConfirm } from './JoinChoices'
import { describeChoice, pct, type JoinChoice } from './joinAccount'

/** One pick out of the list — what the account panel hands to `useJoinAccount`. */
export interface AddPick {
  key: string
  display: string
  choice: JoinChoice
  /** The first bot's cap on an EMPTY account — `undefined` on an account that has bots. */
  riskCapPct?: number | null
  /** The destination is live and the reader confirmed it on screen. */
  live: boolean
}

export function AddBotPanel({
  account,
  group,
  live,
  pendingKey,
  busy,
  onPick,
  onClose,
  statusByKey,
}: {
  account: number
  /** The account being added to — its bots, its cap and its served room. */
  group: BotAccountGroup
  /** The registry marks this account live, so every add is confirmed first. */
  live: boolean
  /** The bot being added right now, so its row can say so. */
  pendingKey: string | null
  busy: boolean
  onPick: (pick: AddPick) => void
  onClose: () => void
  statusByKey: Map<string, string>
}) {
  const { data: groups, isLoading } = useBotAccounts()
  const [capOn, setCapOn] = useState(true)
  const [cap, setCap] = useState<number | null>(10)
  // The row whose ways-to-make-room are out, and a choice waiting on the live confirmation.
  const [openKey, setOpenKey] = useState<string | null>(null)
  const [staged, setStaged] = useState<{
    key: string
    display: string
    risk: number | null
    choice: JoinChoice
  } | null>(null)

  const accountEmpty = group.bots.length === 0
  const free = (groups ?? [])
    .filter((g) => g.kind === 'bench')
    .flatMap((g) => g.bots)
    .filter((b) => !b.unreadable)

  // Whether each fits — the server's answer. NOT asked on an empty account: it has no cap until
  // the first bot sets one, and that cap is chosen right here.
  const plans = useJoinPlans(
    accountEmpty ? null : account,
    free.map((b) => ({ key: b.key, risk: b.risk_pct }))
  )
  const planByKey = new Map(free.map((b, i) => [b.key, plans[i]?.data]))

  const agreedCap = group.cap_agrees ? group.risk_cap_pct : null
  const room = group.room_pct
  // The served room, said ONCE for the whole list rather than on every row.
  const budgetLine = accountEmpty
    ? null
    : !group.cap_agrees
      ? null
      : agreedCap === null
        ? 'No cap on this account — any bot fits.'
        : room == null
          ? null
          : room >= 0
            ? `${pct(room)} of its ${pct(agreedCap)} cap is free.`
            : `Already ${pct(-room)} over its ${pct(agreedCap)} cap.`

  // The server applies the same rule; stating it here keeps Add from being a 422 after the click.
  const capProblem =
    accountEmpty && capOn
      ? cap === null
        ? 'Enter a cap, or untick it to run uncapped.'
        : cap <= 0 || cap > 100
          ? 'A cap is a percentage of the balance: above 0 and at most 100.'
          : null
      : null

  const firstCap = accountEmpty ? (capOn ? cap : null) : undefined

  const pick = (key: string, display: string, risk: number | null, choice: JoinChoice) => {
    setOpenKey(null)
    if (live) {
      setStaged({ key, display, risk, choice })
      return
    }
    onPick({ key, display, choice, riskCapPct: firstCap, live: false })
  }

  return (
    <div
      data-testid="add-bot-row"
      className="rounded-lg border border-border-default bg-bg-sunken overflow-hidden"
    >
      <div className="flex items-start gap-3 px-4 pt-[14px] pb-[12px]">
        <div className="min-w-0">
          <p className="text-[13px] font-semibold text-text-primary leading-tight">
            Add a bot to {account}
          </p>
          <p data-testid="add-room" className="text-[11.5px] text-text-tertiary mt-[4px]">
            {budgetLine ?? 'Free bots — pick one to put here.'}
          </p>
        </div>
        <button
          onClick={onClose}
          aria-label="Close"
          className="ml-auto shrink-0 w-[24px] h-[24px] grid place-items-center rounded-md text-text-tertiary hover:text-text-primary hover:bg-bg-hover transition-colors"
        >
          <X size={13} />
        </button>
      </div>

      {accountEmpty && (
        <div
          data-testid="first-cap"
          className="mx-4 mb-[12px] rounded-md border border-gold-text/25 bg-gold-muted/40 px-3 py-[10px]"
        >
          <p className="text-[9px] font-semibold uppercase tracking-[0.8px] text-gold-text mb-[8px]">
            Risk cap for this account
          </p>
          <div className="flex items-center gap-2 flex-wrap">
            <label className="flex items-center gap-[6px] text-[12px] text-text-secondary cursor-pointer">
              <input
                type="checkbox"
                data-testid="first-cap-on"
                checked={capOn}
                onChange={(e) => setCapOn(e.target.checked)}
              />
              Cap open risk at
            </label>
            <DecimalInput
              value={cap}
              onChange={setCap}
              suffix="%"
              invalid={!!capProblem}
              disabled={!capOn}
              aria-label="Risk cap for this account"
              data-testid="first-cap-input"
              className="w-[84px]"
            />
            <span className="text-[12px] text-text-secondary">of the balance</span>
          </div>
          <p className="text-[10.5px] text-text-tertiary mt-[7px] leading-[1.5]">
            {capOn
              ? 'No bot is here yet, so the first one sets the ceiling. Every bot added after it takes the same cap.'
              : 'This account will run with no ceiling on open risk.'}
          </p>
          {capProblem && (
            <p data-testid="first-cap-problem" className="text-[10.5px] text-neg-text mt-[4px]">
              {capProblem}
            </p>
          )}
        </div>
      )}

      <div className="px-2 pb-2">
        {isLoading ? (
          <div className="flex flex-col gap-[6px] px-2 pb-2">
            <Shimmer className="h-[46px] w-full" />
            <Shimmer className="h-[46px] w-full" />
          </div>
        ) : free.length === 0 ? (
          <div
            data-testid="no-candidates"
            className="mx-2 mb-2 rounded-md border border-dashed border-border-default px-4 py-5 text-center"
          >
            <p className="text-[12px] text-text-secondary">No bot is free</p>
            <p className="text-[11px] text-text-tertiary mt-[4px] leading-[1.5]">
              Every bot is already on an account. To move one here, open it and change its account
              there.
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-[4px]">
            {free.map((b) => {
              const running = statusByKey.get(b.key) === 'RUNNING'
              const adding = pendingKey === b.key
              const plan = planByKey.get(b.key)
              // Only a real answer can say "does not fit" — no answer yet is a plain Add.
              const needsRoom = !!plan && !plan.fits
              const blocked = busy || running || !!capProblem
              const isOpen = needsRoom && openKey === b.key
              const isStaged = staged?.key === b.key
              return (
                <div key={b.key} className="flex flex-col">
                  <button
                    data-testid={`add-${b.key}`}
                    data-needs-room={needsRoom || undefined}
                    disabled={blocked}
                    title={
                      running
                        ? 'This bot is running. Stop it first — it read its account when it started.'
                        : capProblem
                          ? capProblem
                          : needsRoom
                            ? 'Its risk does not fit the room left on this account — pick a way to make room.'
                            : `Add ${b.display} to account ${account}`
                    }
                    onClick={() =>
                      needsRoom
                        ? setOpenKey(isOpen ? null : b.key)
                        : pick(b.key, b.display, b.risk_pct, { kind: 'as-is' })
                    }
                    className="group flex items-center gap-3 w-full px-2 py-[8px] rounded-md text-left border border-transparent hover:border-accent/40 hover:bg-bg-hover transition-colors disabled:cursor-not-allowed disabled:hover:border-transparent disabled:hover:bg-transparent"
                  >
                    <span className="shrink-0 w-[30px] h-[30px] rounded-full grid place-items-center bg-accent-muted text-accent-text border border-accent/30">
                      <Bot size={15} />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span
                        className={`block text-[13px] font-medium truncate ${
                          blocked && !adding ? 'text-text-tertiary' : 'text-text-primary'
                        }`}
                      >
                        {b.display}
                      </span>
                      <span
                        className={`block text-[11px] mt-[1px] ${needsRoom ? 'text-warn-text' : 'text-text-tertiary'}`}
                      >
                        {typeof b.risk_pct === 'number'
                          ? `Risks ${b.risk_pct}% a trade`
                          : 'Risk per trade not stated'}
                        {needsRoom && ' — more than this account has room for'}
                      </span>
                    </span>
                    <span
                      className={`shrink-0 inline-flex items-center gap-[5px] px-[10px] py-[5px] rounded-md text-[11.5px] font-medium border transition-colors ${
                        adding
                          ? 'border-accent/40 text-accent-text bg-accent-muted'
                          : blocked
                            ? 'border-border-default text-text-tertiary'
                            : needsRoom
                              ? 'border-warn/50 text-warn-text group-hover:bg-warn/10'
                              : 'border-accent/40 text-accent-text group-hover:bg-accent/15'
                      }`}
                    >
                      {adding ? (
                        <>
                          <Loader2 size={12} className="animate-spin" /> Adding…
                        </>
                      ) : running ? (
                        'Running'
                      ) : needsRoom ? (
                        <>
                          Make room
                          <ChevronDown
                            size={12}
                            className={`transition-transform ${isOpen ? 'rotate-180' : ''}`}
                          />
                        </>
                      ) : (
                        <>
                          <Plus size={12} /> Add
                        </>
                      )}
                    </span>
                  </button>
                  {isOpen && plan && (
                    <div className="px-2 pb-2 pt-[2px]">
                      <JoinChoices
                        plan={plan}
                        room={room}
                        risk={b.risk_pct}
                        display={b.display}
                        busy={busy}
                        onChoose={(c) => pick(b.key, b.display, b.risk_pct, c)}
                      />
                    </div>
                  )}
                  {isStaged && staged && (
                    <div className="px-2 pb-2 pt-[2px]">
                      <LiveConfirm
                        account={account}
                        what={describeChoice(staged.choice, staged.display, staged.risk, plan)}
                        verb="Add to live account"
                        busy={busy}
                        onConfirm={() => {
                          onPick({
                            key: staged.key,
                            display: staged.display,
                            choice: staged.choice,
                            riskCapPct: firstCap,
                            live: true,
                          })
                          setStaged(null)
                        }}
                        onCancel={() => setStaged(null)}
                      />
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      <div className="flex items-center gap-[6px] px-4 py-[9px] border-t border-border-subtle text-[10.5px] text-text-tertiary">
        <Check size={11} className="shrink-0" />A bot added here trades from its next start.
      </div>
    </div>
  )
}
