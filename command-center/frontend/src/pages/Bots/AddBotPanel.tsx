/**
 * Put a strategy on this account — the list the account panel's "Add bot" opens.
 *
 * 🔴 **One row per STRATEGY, not per running copy, and never used up (2026-09-14).** It used to
 * list only bots on no account at all — so once both of a strategy's copies were spoken for (one
 * live, one demo), there was nothing left to offer a THIRD account, and the only route was a
 * hand-edited instance file. Aaron: *"I could have infinite amount of demo or live accounts and I
 * want my bots on all."* A strategy is now a standing placeholder (`lib/botTemplates.ts`, derived
 * from data the page already has — no new fetch for the list) that is always here, on every
 * account, forever — picking one either hands over a real idle copy that happens to be sitting
 * free (`existingBenchKey`, the ordinary case for a bot nobody has placed yet) or mints a fresh
 * one first (`useCloneBot`, `POST /bots/{key}/clone`) with no separate step the reader ever sees.
 * Placing it does not consume the row; the next account still sees the same strategy.
 *
 * ⚠ **The row says what the ACCOUNT cares about: the strategy's name and its risk per trade.** The
 * symbol went (*"the account doesn't care"*) — placing it rewrites the symbol onto this account's
 * suffix anyway. Risk stays because the account's cap is the budget every share comes out of.
 *
 * 🔴 **A row that does not fit says so and offers the one easy way out.** A real idle bot gets the
 * SERVER's full plan (`useJoinPlans`) and every fix it can offer — `JoinChoices`, unchanged. A
 * strategy with nothing idle yet has no key for the server to plan around until it exists, so it
 * gets the one fix computable from what the panel already knows: join at the room still free
 * (`SimpleMakeRoom`). Raising the cap or rebalancing every bot's share is still a click away on the
 * account's own risk budget — just not folded into this row before a bot exists to write it onto.
 *
 * 🔴 **A LIVE account confirms every add on screen first (2026-09-11)** — the server refuses a
 * move onto a live account without `confirm_live`, unchanged by any of the above: staging happens
 * AFTER a fresh copy exists, never before, so cancelling the confirmation leaves at most one idle
 * spare bot behind — the same resting state benching a real bot already produces, picked up as an
 * ordinary free bot next time, never a duplicate template.
 *
 * ⚠ **An empty account asks for its cap HERE (2026-09-11).** The cap is stored per bot, so an
 * account with no bot has none: the first bot started uncapped, the watchdog started it within a
 * minute, and a cap saved afterwards could not reach the running process. The first add now
 * carries the ceiling; every later bot adopts it on the server. ⚠ Unticked sends `null` —
 * "uncapped" chosen — never nothing, which the server reads as not chosen.
 *
 * ⚠ **It writes nothing itself** — `onPick` hands the choice back and the account panel carries
 * it out through `useJoinAccount`, the same function the bot panel uses. Cloning a fresh copy is
 * the one thing this panel DOES do on its own, because it writes no account and needs none of that
 * machinery — see `useCloneBot`.
 */
import { useState } from 'react'
import { Bot, Check, ChevronDown, Loader2, Minus, Plus, X } from 'lucide-react'
import { useBotAccounts, useCloneBot, useJoinPlans, useRegisteredAccounts } from '@/hooks/useBots'
import type { BotAccountGroup } from '@/types'
import { deriveTemplates, type BotTemplateRow } from '@/lib/botTemplates'
import { DecimalInput } from '@/components/DecimalInput'
import { Shimmer } from '@/components/Shimmer'
import { JoinChoices, LiveConfirm } from './JoinChoices'
import { describeChoice, pct, roomShare, type JoinChoice } from './joinAccount'

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

/** The one fix computable with no server plan: join at the room still free. A strategy with
 *  nothing idle yet has no bot key for `useJoinPlans` to ask the server about, so it cannot offer
 *  raising the cap or rescaling every bot's share the way `JoinChoices` does for a real free bot —
 *  those stay a click away on the account's own risk budget instead of being invented here. */
function SimpleMakeRoom({
  risk,
  room,
  display,
  busy,
  onChoose,
}: {
  risk: number | null
  room: number | null | undefined
  display: string
  busy: boolean
  onChoose: (c: JoinChoice) => void
}) {
  const at = roomShare(room)
  return (
    <div
      data-testid="join-choices-simple"
      className="rounded-md border border-warn/40 bg-warn-muted/40 px-3 py-[10px]"
    >
      <p className="text-[11.5px] text-warn-text leading-[1.5]">
        {display} risks {pct(risk)} a trade — more than this account has room for.
      </p>
      {at != null ? (
        <button
          data-testid="join-at-room"
          disabled={busy}
          onClick={() => onChoose({ kind: 'at-room', riskPct: at })}
          className="group flex items-start gap-[10px] w-full text-left px-[10px] py-[8px] mt-[9px] rounded-md border border-border-default bg-bg-surface hover:border-accent/50 hover:bg-accent-muted transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Minus size={13} className="mt-[2px] shrink-0 text-accent-text" />
          <span className="min-w-0">
            <span className="block text-[12.5px] font-medium text-text-primary">
              Add at {pct(at)} a trade
            </span>
            <span className="block text-[11px] text-text-tertiary mt-[1px] leading-[1.45]">
              Instead of {pct(risk)} — the room still free. Nothing else on the account changes.
            </span>
          </span>
        </button>
      ) : (
        <p className="text-[11.5px] text-text-secondary mt-[6px] leading-[1.5]">
          There is no one-click way to make room. Lower another bot&rsquo;s risk or raise the cap on
          the account, then place {display}.
        </p>
      )}
    </div>
  )
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
  // Templates need no fetch of their own — `useBotAccounts` already lists every bot by account
  // (live, demo or bench) and `useRegisteredAccounts` already says which account is which kind;
  // `deriveTemplates` (lib/botTemplates.ts) just reads the two the way this row needs them.
  const { data: groups, isLoading: groupsLoading } = useBotAccounts()
  const { data: registered, isLoading: registryLoading } = useRegisteredAccounts()
  const isLoading = groupsLoading || registryLoading
  const cloneBot = useCloneBot()
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
  // A strategy has no bot key until it is placed once. Remembered per strategy so a row that
  // just cloned one keeps showing "Adding…" through the account move that follows, instead of
  // losing track of itself the moment the fresh key exists.
  const [clonedKeyByPackage, setClonedKeyByPackage] = useState<Record<string, string>>({})

  const accountEmpty = group.bots.length === 0
  const allTemplates = groups && registered ? deriveTemplates(groups, registered) : []
  // A strategy already ON this account is not offered again — this panel is for filling a gap,
  // never for piling a second copy of one strategy onto a balance that already runs it.
  const alreadyHere = new Set(group.bots.map((b) => b.strategy_package))
  const rows = allTemplates.filter((t) => !alreadyHere.has(t.strategyPackage))

  // Only a REAL, already-idle bot has a key the server can plan a join for. A strategy with
  // nothing idle right now is not asked — there is nothing on disk yet to ask about.
  const ready = rows.filter(
    (t): t is BotTemplateRow & { existingBenchKey: string } => t.existingBenchKey != null
  )
  const plans = useJoinPlans(
    accountEmpty ? null : account,
    ready.map((t) => ({ key: t.existingBenchKey, risk: t.riskPct }))
  )
  const planByKey = new Map(ready.map((t, i) => [t.existingBenchKey, plans[i]?.data]))

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

  // Clone a fresh copy first when this strategy has nothing idle right now, then carry out the
  // exact same pick a real free bot would go through. The clone is invisible on success — the
  // reader only ever sees a strategy being placed, never a bot being created.
  const startPick = async (t: BotTemplateRow, choice: JoinChoice) => {
    let key = t.existingBenchKey
    let display = t.display
    if (!key) {
      const cloned = await cloneBot.mutateAsync(t.sourceKey).catch(() => null)
      if (!cloned) return
      key = cloned.bot_key
      display = cloned.display_name
      setClonedKeyByPackage((m) => ({ ...m, [t.strategyPackage]: key as string }))
    }
    pick(key, display, t.riskPct, choice)
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
            {budgetLine ?? 'Pick a strategy to place here.'}
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
        ) : rows.length === 0 ? (
          <div
            data-testid="no-candidates"
            className="mx-2 mb-2 rounded-md border border-dashed border-border-default px-4 py-5 text-center"
          >
            {allTemplates.length === 0 ? (
              <>
                <p className="text-[12px] text-text-secondary">No strategy is built yet</p>
                <p className="text-[11px] text-text-tertiary mt-[4px] leading-[1.5]">
                  Once one exists it shows up here, on every account, for good.
                </p>
              </>
            ) : (
              <>
                <p className="text-[12px] text-text-secondary">
                  Every strategy is already on this account
                </p>
                <p className="text-[11px] text-text-tertiary mt-[4px] leading-[1.5]">
                  A second copy of one here is not something this panel offers.
                </p>
              </>
            )}
          </div>
        ) : (
          <div className="flex flex-col gap-[4px]">
            {rows.map((t) => {
              const key = t.existingBenchKey ?? clonedKeyByPackage[t.strategyPackage] ?? null
              const running = key !== null && statusByKey.get(key) === 'RUNNING'
              const cloning = cloneBot.isPending && cloneBot.variables === t.sourceKey
              const adding = cloning || (key !== null && pendingKey === key)
              const plan = t.existingBenchKey ? planByKey.get(t.existingBenchKey) : undefined
              // Only a real answer can say "does not fit" — no answer yet is a plain Add.
              const needsRoomWithPlan = !!plan && !plan.fits
              const simpleFits =
                accountEmpty || t.riskPct == null || room == null || t.riskPct <= room
              const needsRoomNoPlan = !t.existingBenchKey && !simpleFits
              const needsRoom = t.existingBenchKey ? needsRoomWithPlan : needsRoomNoPlan
              const blocked = busy || running || !!capProblem || cloning
              const isOpen = needsRoom && openKey === t.strategyPackage
              const isStaged = staged?.key !== undefined && staged?.key === key

              return (
                <div key={t.strategyPackage} className="flex flex-col">
                  <button
                    data-testid={`add-${t.strategyPackage}`}
                    data-needs-room={needsRoom || undefined}
                    disabled={blocked}
                    title={
                      running
                        ? 'This bot is running. Stop it first — it read its account when it started.'
                        : capProblem
                          ? capProblem
                          : needsRoom
                            ? 'Its risk does not fit the room left on this account — pick a way to make room.'
                            : `Add ${t.display} to account ${account}`
                    }
                    onClick={() =>
                      needsRoom
                        ? setOpenKey(isOpen ? null : t.strategyPackage)
                        : void startPick(t, { kind: 'as-is' })
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
                        {t.display}
                      </span>
                      <span
                        className={`block text-[11px] mt-[1px] ${needsRoom ? 'text-warn-text' : 'text-text-tertiary'}`}
                      >
                        {typeof t.riskPct === 'number'
                          ? `Risks ${t.riskPct}% a trade`
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
                  {isOpen &&
                    (t.existingBenchKey && plan ? (
                      <div className="px-2 pb-2 pt-[2px]">
                        <JoinChoices
                          plan={plan}
                          room={room}
                          risk={t.riskPct}
                          display={t.display}
                          busy={busy}
                          onChoose={(c) => void startPick(t, c)}
                        />
                      </div>
                    ) : !t.existingBenchKey ? (
                      <div className="px-2 pb-2 pt-[2px]">
                        <SimpleMakeRoom
                          risk={t.riskPct}
                          room={room}
                          display={t.display}
                          busy={busy || cloning}
                          onChoose={(c) => void startPick(t, c)}
                        />
                      </div>
                    ) : null)}
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
