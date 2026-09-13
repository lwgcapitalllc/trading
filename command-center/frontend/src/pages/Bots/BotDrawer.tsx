/**
 * One bot, and only what you can do to it — its controls, its risk, its account, its version.
 *
 * 🔴 **This replaces a full-page panel that showed a version banner, a risk editor printing a
 * 1,500-word note out of the instance config, an account card, a deploy card and all 116 strategy
 * parameters — at once.** Aaron, 2026-09-05: *"too much information, too much duplication … even
 * the section that says risk per trade, what is all of that information? Why do I care?"*
 *
 * **The things you act on, in the order you act on them — then a fold:** start/stop/logs, risk
 * per trade, account, version. Everything you only ever READ — the symbol, the timeframe, the
 * trade id, the 116 parameters, and the config's own prose about why the risk is what it is —
 * sits under Details.
 *
 * 🔴 **Risk and account moves go through the account's BUDGET (2026-09-11).** The risk editor
 * (`BotRiskEditor`) checks the new share against the account's cap as it is typed and can raise the
 * cap in the same save; a move onto another account asks that account's budget first and, when the
 * bot does not fit, offers the ways to make room instead of a refusal after the click. A move onto
 * a LIVE account is confirmed on screen — the server refuses one without it.
 *
 * ⚠ **The deploy control is the SAME component as before** — `VersionBanner` carries promote with
 * its own confirm, and rewriting it to make a drawer prettier would put a fresh implementation on
 * the path that deploys code to a live account.
 *
 * ⚠ **Nothing is deleted, it is folded.** The parameter list is how you check the bot is the bot
 * that was backtested, and the risk note is the measured reasoning behind a live number.
 */
import { useEffect, useState, type ReactNode } from 'react'
import { ChevronRight, FileText, Play, RotateCcw, Square } from 'lucide-react'
import {
  useBotAccounts,
  useBotParams,
  useFetchRiskPlan,
  useRegisteredAccounts,
} from '@/hooks/useBots'
import type {
  BotAccountRiskPlan,
  BotEarnings,
  BotParamRow,
  BotParamsView,
  BotPromoteJob,
  BotReviewFinding,
  BotStatus,
} from '@/types'
import { Drawer } from '@/components/Drawer'
import { Shimmer } from '@/components/Shimmer'
import { botLabel as labelOf } from '@/lib/botLabel'
import { botCondition, type Condition } from '@/lib/botCondition'
import { StatusText, TONE_TEXT } from '@/components/BotStatus'
import { accountName } from './AccountForm'
import { ParamGroup, VersionBanner } from './ConfigureTab'
import { BotActionPill, type BotAction } from './BotStatusPill'
import { BotRiskEditor } from './BotRiskEditor'
import { SectionTitle } from './drawerParts'
import { JoinChoices, LiveConfirm } from './JoinChoices'
import { describeChoice, useJoinAccount, type JoinChoice } from './joinAccount'
import { useTakeOff } from './takeOff'
import { TakeOffButton } from './TakeOffButton'

function Fold({ label, children }: { label: string; children: ReactNode }) {
  return (
    <details className="border-t border-border-subtle pt-[14px] mt-[2px]">
      <summary className="cursor-pointer text-[11.5px] text-text-tertiary hover:text-text-secondary select-none list-none marker:hidden">
        {label}
      </summary>
      <div className="mt-[12px]">{children}</div>
    </details>
  )
}

function Facts({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-[6px] text-[11.5px]">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-text-tertiary">{k}</dt>
          <dd className="m-0 text-right font-mono tabular-nums text-text-secondary break-all">
            {v}
          </dd>
        </div>
      ))}
    </dl>
  )
}

const btnCls =
  'flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small border transition-colors disabled:opacity-40 disabled:cursor-not-allowed'

/** A move waiting on the reader — a live confirmation, or the ways to make room. */
interface PendingMove {
  bot: string
  account: number
  live: boolean
  plan: BotAccountRiskPlan | null
  /** The choice to confirm on a live account; `null` while the ways to make room are on show. */
  staged: JoinChoice | null
}

const upper = (s: string) => (s ? `${s[0].toUpperCase()}${s.slice(1)}` : s)

/**
 * What is wrong with this bot, spelled out, first thing in its panel.
 *
 * 🔴 **The row said "Needs review" and nothing said what to review (2026-09-12).** Aaron: *"Review
 * what? nothing is telling me what to act on."* The findings lived only on the status's hover. The
 * panel is where a bot is acted on, so each problem is listed here in the bot's and the reviewer's
 * own words — the reviewer's findings one by one, with when that hourly review ran.
 *
 * ⚠ **Nothing is decided here** — which problems exist, and their words, are `botCondition`'s.
 * Nothing renders for a bot with none. ⚠ What the platform found OVER goes under them as one grey
 * line (`ResolvedOnItsOwn`) — never counted, never a status.
 */
function Attention({ cond, resolved }: { cond: Condition; resolved: BotReviewFinding[] }) {
  if (!cond.issues.length && !resolved.length) return null
  return (
    <section
      data-testid="bot-attention"
      className="py-[14px] border-b border-border-subtle flex flex-col gap-[12px]"
    >
      {cond.issues.map((i) =>
        i.findings ? (
          <div key={i.key} data-testid={`attention-${i.key}`} className="flex flex-col gap-[8px]">
            {i.findings.map((f, n) => (
              <div key={n}>
                <p className={`text-[12.5px] font-medium ${TONE_TEXT[f.tone]}`}>{f.title}</p>
                <p className="text-[11.5px] text-text-secondary leading-[1.5] whitespace-pre-line mt-[2px]">
                  {f.detail}
                </p>
              </div>
            ))}
            {i.checkedAt && (
              <p className="text-[10.5px] text-text-tertiary">
                From the hourly record review at{' '}
                {new Date(i.checkedAt).toLocaleTimeString([], {
                  hour: 'numeric',
                  minute: '2-digit',
                })}
                .
              </p>
            )}
          </div>
        ) : (
          <div key={i.key} data-testid={`attention-${i.key}`}>
            <p className={`text-[12.5px] font-medium ${TONE_TEXT[i.tone]}`}>{i.word}</p>
            <p className="text-[11.5px] text-text-secondary leading-[1.5] mt-[2px]">
              {upper(i.detail)}
            </p>
          </div>
        )
      )}
      {resolved.length > 0 && <ResolvedOnItsOwn items={resolved} />}
    </section>
  )
}

/**
 * What the platform closed ON ITS OWN — one grey line until opened (2026-09-13).
 *
 * 🔴 Aaron: *"I don't want to manually mark anything as reviewed. The platform should know that
 * this thing was resolved."* The review files what the record shows has ended — a halt that
 * recovered, a crash it came back from, a link drop that restored — apart from what is still open,
 * and only the open part is a status. This is where the rest goes: never counted, never coloured,
 * one click away, so nothing that happened disappears without a trace.
 */
function ResolvedOnItsOwn({ items }: { items: BotReviewFinding[] }) {
  return (
    <details data-testid="bot-resolved">
      <summary className="cursor-pointer list-none [&::-webkit-details-marker]:hidden text-[11.5px] text-text-tertiary hover:text-text-secondary transition-colors">
        {items.length} resolved on {items.length === 1 ? 'its' : 'their'} own · nothing to do ›
      </summary>
      <ul className="mt-[8px] flex flex-col gap-[8px]">
        {items.map((f) => (
          <li key={f.key}>
            <p className="text-[12px] text-text-secondary">{f.title}</p>
            {f.resolved && <p className="text-[11px] text-text-tertiary mt-[1px]">{f.resolved}</p>}
          </li>
        ))}
      </ul>
    </details>
  )
}

export function BotDrawer({
  bot,
  earnings,
  job,
  onClose,
  onLogs,
  onStart,
  onStop,
  onRestart,
  busy,
  pendingAction = null,
  onStopThen,
  configAccount,
  onOpenAccount,
  fetchedAt,
}: {
  bot: BotStatus
  /** When the trading box took the reading `bot` came from. The version banner measures whether a
   *  restart is still owed off it, the way the row does — one clock, one answer. */
  fetchedAt?: string
  /** The account this bot's CONFIG names — what a move or a removal changes, and what the page's
   *  rows are laid out by. `null` = on no account; `undefined` = the configs are not read yet.
   *  ⚠ Not `bot.account`: that is what the bot last REPORTED, which stays on the old account
   *  until its next start — a bot just taken off an account would still offer Remove. */
  configAccount?: number | null
  /** What THIS bot's own closed trades came to — computed server-side off its decision record.
   *  ⚠ Never the account's growth: two bots on one balance share that. */
  earnings: BotEarnings | undefined
  /** This bot's latest deploy job, from the PAGE's watcher — never polled here, or closing the
   *  drawer mid-deploy would stop the watch. */
  job: BotPromoteJob | null | undefined
  onClose: () => void
  onLogs: () => void
  onStart: () => void
  onStop: () => void
  onRestart: () => void
  busy: boolean
  /** A start/stop/restart of THIS bot still in flight — the same pill the row shows. */
  pendingAction?: BotAction | null
  /** Stop this bot, wait until the box says it has, then run `then` — how a RUNNING bot is moved or
   *  taken off (2026-09-13). `what` finishes "…so it was not ___" if it will not stop in time;
   *  `restart` starts it again once `then` reports the write went through. Resolves once it is
   *  over, whether or not `then` ran.
   *  Held by the PAGE, so closing this panel mid-wait cannot strand a stopped bot on its account. */
  onStopThen?: (
    what: string,
    then: () => Promise<boolean> | void,
    opts?: { restart?: boolean }
  ) => Promise<void> | void
  /** Open the account this bot is on, in its own panel. */
  onOpenAccount?: (account: number) => void
}) {
  const { data, isLoading, error } = useBotParams(bot.key)
  const { data: groups } = useBotAccounts()
  const { data: registry } = useRegisteredAccounts()
  const join = useJoinAccount()
  const fetchPlan = useFetchRiskPlan()

  // Taking it off its account is the SAME flow and button as each row of the account panel
  // (`takeOff.ts`, 2026-09-13): armed by a first press, Removing… from the second, and this panel
  // closes once it is off — a bot on no account has nothing left here.
  const takeOff = useTakeOff(bot.key, onClose)
  const takeOffState = takeOff.stateOf(bot.key)
  const removing = takeOffState === 'removing'

  // A move the reader has to answer, held per bot for the same reason.
  const [move, setMove] = useState<PendingMove | null>(null)
  const moveHere = move && move.bot === bot.key ? move : null
  const [checkingDest, setCheckingDest] = useState<number | null>(null)
  // A move waiting on the stop this panel asked for — the account section says so meanwhile.
  const [after, setAfter] = useState<'move' | null>(null)
  useEffect(() => {
    if (pendingAction === null) setAfter(null)
  }, [pendingAction])

  const running = bot.status === 'RUNNING'
  // 🔴 A bot HOLDING A TRADE stays where it is until the trade closes (2026-09-13): moved or taken
  // off, it would leave that trade open with nothing managing it, and halt on a new account. The
  // server refuses the write off the bot's own record on the box; this says so before the click.
  const holding = running && bot.in_trade === true
  const v = data as BotParamsView | undefined
  // Where the selector sits: the config's account once the configs are read, the bot's own report
  // until then (display only — Remove waits for the config, below).
  const selected =
    configAccount === undefined ? bot.account || '' : configAccount === null ? '' : configAccount

  const regOf = (a: number) => (registry ?? []).find((r) => r.account === a)
  const kindOf = (a: number) => regOf(a)?.kind
  // The account's name as the Bots page's heading gives it — its nickname, else its broker.
  const myAccountName = typeof configAccount === 'number' ? accountName(regOf(configAccount)) : null
  const groupOf = (a: number | null | undefined) =>
    typeof a === 'number'
      ? (groups ?? []).find((g) => g.kind === 'account' && g.account === a)
      : undefined
  const myGroup = groupOf(configAccount)
  // The bot's own share as its config states it — what a move carries to the destination's budget.
  const myRisk =
    (groups ?? []).flatMap((g) => g.bots).find((b) => b.key === bot.key)?.risk_pct ?? null
  // Real money: the registry's word for the account the config names, else the bot's own report.
  const onLive =
    typeof configAccount === 'number'
      ? kindOf(configAccount) === 'live'
      : bot.account_type === 'live'

  /**
   * Every account this bot can be moved TO.
   *
   * 🔴 **Read off the REGISTRY first, not the grouping alone (2026-09-06).** The grouping is derived
   * from the instance configs, so it can only see accounts some bot is ALREADY on — the first bot
   * onto a newly registered account was not offered here at all.
   * ⚠ **An account a bot names that nobody registered is unioned in and counts as assignable** — it
   * works, and dropping it would leave the bot's own current account missing from its own list.
   * ⚠ **The registry entry WINS on a clash**: the grouping has no opinion about whether an account
   * has a terminal, so taking its answer would quietly re-enable one that cannot be assigned.
   */
  const destinations = [
    ...(registry ?? []).map((r) => ({
      account: r.account,
      assignable: r.assignable,
      reason: r.unassignable_reason,
    })),
    ...(groups ?? [])
      .filter((g) => g.kind === 'account' && g.account !== null)
      .map((g) => ({ account: g.account as number, assignable: true, reason: '' })),
  ]
    .filter((d, i, all) => all.findIndex((o) => o.account === d.account) === i)
    .sort((a, b) => a.account - b.account)

  const moving = join.pendingKey === bot.key
  /** Put it on `account`, and say whether that went through. `restarting`: the page starts it
   *  again afterwards, so the toast must not tell the reader to. */
  const doJoin = async (account: number, choice: JoinChoice, live: boolean, restarting = false) => {
    const ok = await join.join({
      account,
      botKey: bot.key,
      display: bot.name,
      choice,
      live,
      restarting,
    })
    if (ok) setMove(null)
    return ok
  }
  /** Move it now — or, on a RUNNING bot, once the page has stopped it and seen it stopped.
   *  `restart`: a move onto a DEMO account, started again once the move has gone through (Aaron,
   *  2026-09-13: "let them automatically start"). Onto a live one it stays stopped until the
   *  reader starts it — the first real-money start is a click. */
  const whenStopped = (then: () => Promise<boolean> | void, restart = false) => {
    if (!running || !onStopThen) return void then()
    setAfter('move')
    void onStopThen('moved', then, { restart })
  }

  /**
   * A destination picked in the selector. Its budget is asked FIRST — the server's plan for this
   * bot joining — so a bot that does not fit is offered the ways to make room rather than refused
   * after the click. A demo account it fits on moves at once; a live one is confirmed on screen.
   * ⚠ A plan that could not be asked does not stop the move — the server is the gate.
   */
  const pickDestination = async (dest: number) => {
    setMove(null)
    const live = kindOf(dest) === 'live'
    let plan: BotAccountRiskPlan | null = null
    if (myRisk != null) {
      setCheckingDest(dest)
      plan = await fetchPlan(dest, { joining: { [bot.key]: myRisk } })
      setCheckingDest(null)
    }
    const needsRoom = plan !== null && !plan.fits
    // ⚠ A RUNNING bot never moves on the pick: it is stopped first, and that is confirmed on screen.
    if (!live && !needsRoom && !running) {
      await doJoin(dest, { kind: 'as-is' }, false)
      return
    }
    setMove({
      bot: bot.key,
      account: dest,
      live,
      plan,
      staged: needsRoom ? null : { kind: 'as-is' },
    })
  }

  const strategyGroups = (v?.strategy ?? []).reduce<Record<string, BotParamRow[]>>((acc, r) => {
    ;(acc[r.group] ??= []).push(r)
    return acc
  }, {})
  const terminal = (v?.identity.mt5_path ?? '').split('\\').filter(Boolean)[0] ?? '—'
  // ⚠ Busy through a removal from its second click, the stop a move waits on, and any start / stop /
  // restart — a move's own start included: the controls stay, not pressable.
  const selectBusy =
    removing || moving || checkingDest !== null || after !== null || pendingAction !== null
  // What a MOVE is doing, which the selector cannot say. ⚠ Never a removal's: its own button says
  // "Removing…" (Aaron, 2026-09-13: "I dont need the text next to the button").
  const busyText =
    after === 'move' && pendingAction === 'stop'
      ? 'Stopping it first, then moving it…'
      : checkingDest !== null
        ? `Checking account ${checkingDest}…`
        : moving
          ? 'Moving…'
          : null
  // The row's own status (2026-09-12): the header said "Running" in green over a HALTED bot.
  const cond = botCondition(bot, { asked: true, onAccount: selected !== '' })

  return (
    <Drawer
      open
      onClose={onClose}
      label={`${bot.name} settings`}
      // 620px, up from 440 (2026-09-06, Aaron: *"make this side panel a little wider"*). Capped,
      // never a fraction of the screen — the page behind it stays the subject.
      width={620}
      // Its name plus LIVE or demo: two copies of one strategy share a name since 2026-09-11, and
      // this panel is where their risk and their code are changed.
      title={labelOf(bot)}
      // 🔴 ITS STATUS AND NOTHING ELSE (2026-09-12). The account's number sat beside the status as a
      // link into the account's panel, so "Needs review · account 34957946 ›" read as one thing:
      // Aaron clicked it to find out what needed review and got the account — *"what needs review,
      // the account or the bot?"* The problems are spelled out in the first section below, and the
      // account is named, with its link, in its own section.
      subtitle={
        <div className="flex items-center mt-[2px]">
          <StatusText cond={cond} size="list" />
        </div>
      }
    >
      {/* ── do ──────────────────────────────────────────────────────────────── */}
      {/* ── what is wrong, before what you can do about it ──────────────────── */}
      <Attention cond={cond} resolved={bot?.review?.resolved ?? []} />

      <div className="flex items-center gap-2 py-[14px] border-b border-border-subtle">
        {/* ⚠ While it is being taken off, its Take off button is the one thing saying so
         *  (2026-09-13, Aaron: "there should just be one button") — no Stopping pill here, and
         *  these stay put, not pressable. */}
        {pendingAction && !removing ? (
          <BotActionPill action={pendingAction} />
        ) : running ? (
          <>
            <button
              onClick={onStop}
              disabled={busy || removing}
              className={`${btnCls} border-neg/40 bg-neg-muted text-neg-text hover:bg-neg/10`}
            >
              <Square size={12} /> Stop
            </button>
            <button
              onClick={onRestart}
              disabled={busy || removing}
              className={`${btnCls} border-border-default text-text-primary hover:bg-bg-hover`}
            >
              <RotateCcw size={12} /> Restart
            </button>
          </>
        ) : (
          <button
            onClick={onStart}
            disabled={busy || removing || !bot.account}
            title={bot.account ? 'Start this bot' : 'Put it on an account first'}
            className={`${btnCls} border-border-default text-text-primary hover:bg-bg-hover hover:border-pos/40`}
          >
            <Play size={12} className="text-pos" /> Start
          </button>
        )}
        <button
          onClick={onLogs}
          className={`${btnCls} border-border-default text-text-secondary hover:bg-bg-hover hover:text-text-primary ml-auto`}
        >
          <FileText size={12} /> Logs
        </button>
      </div>

      {error && (
        <p className="text-[11.5px] text-neg-text py-4">
          Could not read this bot&rsquo;s configuration: {String(error)}
        </p>
      )}

      {/* ── risk per trade ───────────────────────────────────────────────────── */}
      {/* 🔴 Only this section and Details read the bot's settings, so only they wait for them
       *  (2026-09-10) — Version and Account read their own sources. */}
      {(v || isLoading) && (
        <section className="py-[16px] border-b border-border-subtle">
          <SectionTitle>Risk per trade</SectionTitle>
          {!v ? (
            // The editor's shape, so nothing moves when the real one lands.
            <div aria-busy="true" className="flex items-end gap-3">
              <div className="flex flex-col gap-[10px]">
                <Shimmer className="h-[10px] w-[92px]" />
                <Shimmer className="h-[26px] w-[64px]" />
                <Shimmer className="h-[10px] w-[160px]" />
              </div>
              <div className="ml-auto flex items-end gap-2">
                <span className="flex flex-col gap-[6px]">
                  <Shimmer className="h-[10px] w-[52px]" />
                  <Shimmer className="h-[32px] w-[100px]" />
                </span>
                <Shimmer className="h-[32px] w-[64px]" />
              </div>
            </div>
          ) : v.runtime.length === 0 ? (
            <p className="text-[11.5px] text-text-tertiary">
              Nothing here can be changed while it runs.
            </p>
          ) : (
            v.runtime.map((r) => (
              <BotRiskEditor
                key={r.name}
                botKey={bot.key}
                botLabel={labelOf(bot)}
                row={r}
                showLabel={v.runtime.length > 1}
                balance={bot.balance}
                account={configAccount}
                // Only the risk share is part of the account's budget.
                group={r.name === 'exec_risk_pct' ? myGroup : undefined}
                live={onLive}
                onOpenAccount={onOpenAccount}
              />
            ))
          )}
        </section>
      )}

      {/* ── account ─────────────────────────────────────────────────────────── */}
      <section data-testid="bot-account" className="py-[16px] border-b border-border-subtle">
        {/* 🔴 **The account's link lives HERE, not beside the status (2026-09-12)** — in the header
         *  it read as the answer to what needed review. It is a verb, open that account's own
         *  panel, on the section about the account. */}
        <SectionTitle
          aside={
            typeof configAccount === 'number' && onOpenAccount ? (
              <button
                data-testid="bot-account-link"
                onClick={() => onOpenAccount(configAccount)}
                title={`Open account ${configAccount} — its balance, its budget and its bots`}
                className="inline-flex items-center gap-[2px] text-[11.5px] text-text-secondary hover:text-accent transition-colors"
              >
                Open account <ChevronRight size={12} />
              </button>
            ) : undefined
          }
        >
          Account
        </SectionTitle>
        {/* 🔴 **A RUNNING bot can be moved or taken off — it is STOPPED FIRST (2026-09-13).** Aaron:
         *  "it is not intuitive that you have to stop a bot to remove from account … maybe the
         *  remove button should always be there and when we click then it says are you sure bot
         *  will be stopped first?" The rule under it stands: it read its account at startup, so the
         *  server refuses the write while it runs (409), and a page that moved it anyway would show
         *  it under the new account while it traded the old one. What changed is who carries it
         *  out — the confirm says it will be stopped, the PAGE stops it, waits for the box to say
         *  so, then writes (`stopFirst.ts`), and it is left stopped.
         *  ⚠ **An account with no terminal is LISTED and DISABLED, with the reason in the option.**
         *  Hiding it makes an account that exists look like one that does not. */}
        <div className="flex items-center gap-2 flex-wrap">
          <select
            data-testid={`move-${bot.key}`}
            value={selected}
            disabled={selectBusy || holding}
            title={
              holding
                ? `${bot.name} holds a trade, so it stays on this account until that trade closes.`
                : `Move ${bot.name} to another account.`
            }
            onChange={(e) => {
              if (e.target.value === '') return
              const dest = Number(e.target.value)
              if (dest !== configAccount) void pickDestination(dest)
            }}
            // A native select sizes itself to its WIDEST option, and an unassignable account's
            // option carries its reason — so without a width it ran to the panel edge.
            className="w-[240px] max-w-full text-[12.5px] bg-bg-sunken border border-border-default rounded-md px-2 py-[6px] text-text-primary disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {destinations.map((d) => (
              <option key={d.account} value={d.account} disabled={!d.assignable}>
                {d.account}
                {d.assignable ? '' : ` — ${d.reason || 'cannot be assigned'}`}
              </option>
            ))}
            {/* Only what a bot on NO account shows as its value. Taking a bot OFF an account is
             *  the Remove button beside this — the one place it happens (2026-09-11). */}
            {selected === '' && (
              <option value="" disabled>
                Not on an account
              </option>
            )}
          </select>
          {/* The account's name, as its card's heading gives it — the selector shows the number. */}
          {myAccountName && (
            <span data-testid="bot-account-name" className="text-[12px] text-text-secondary">
              {myAccountName}
            </span>
          )}
          {/* 🔴 **Taking it off, as its own button (2026-09-11)** — Aaron: *"we can stop but we
           *  can't remove"*. It BENCHES the bot (still registered, never started by the watchdog).
           *  ⚠ The SAME control as each account-panel row (2026-09-13, `TakeOffButton`): Take off →
           *  Stop and take off → Removing…, then this panel closes. A RUNNING bot is stopped first.
           *  ⚠ Offered only once the CONFIG says the bot is on an account. */}
          {configAccount != null ? (
            <TakeOffButton
              testId={`remove-${bot.key}`}
              state={takeOffState}
              display={labelOf(bot)}
              account={configAccount}
              running={running}
              holding={holding}
              blocked={selectBusy}
              onPress={() =>
                takeOff.press(
                  bot.key,
                  labelOf(bot),
                  running && onStopThen ? (then) => onStopThen('taken off the account', then) : null
                )
              }
            />
          ) : null}
          {busyText && (
            <span data-testid="account-busy" className="text-[11.5px] text-accent animate-pulse">
              {busyText}
            </span>
          )}
        </div>
        {holding && (
          <p data-testid="account-holding" className="mt-2 text-[11.5px] text-text-secondary">
            It holds a trade, so it stays on this account until that trade closes — moved or taken
            off now, nothing would manage it.
          </p>
        )}

        {moveHere && (
          <div data-testid="move-card" className="mt-3 flex flex-col gap-2">
            {moveHere.staged === null && moveHere.plan ? (
              <JoinChoices
                plan={moveHere.plan}
                room={groupOf(moveHere.account)?.room_pct}
                risk={myRisk}
                display={bot.name}
                busy={moving}
                onChoose={(c) =>
                  moveHere.live || running
                    ? setMove({ ...moveHere, staged: c })
                    : void doJoin(moveHere.account, c, false)
                }
              />
            ) : moveHere.staged && moveHere.live ? (
              <LiveConfirm
                account={moveHere.account}
                what={
                  describeChoice(moveHere.staged, bot.name, myRisk, moveHere.plan) +
                  (running
                    ? ' It is running, so it is stopped first, and left stopped until you start it there.'
                    : '')
                }
                verb="Move to live account"
                busy={moving || after !== null}
                onConfirm={() => {
                  const staged = moveHere.staged as JoinChoice
                  // No restart: the first real-money start is the reader's own click.
                  whenStopped(() => doJoin(moveHere.account, staged, true))
                }}
                onCancel={() => setMove(null)}
              />
            ) : moveHere.staged && running ? (
              // A demo move of a RUNNING bot: stopped, moved and started again — said before the
              // click (Aaron, 2026-09-13: "let them automatically start").
              <div
                data-testid="move-stop-first"
                className="flex flex-col gap-2 rounded-md border border-warn/40 bg-warn-muted px-3 py-[10px]"
              >
                <p className="text-[12.5px] text-warn-text leading-[1.5]">
                  {bot.name} is running. It is stopped, moved to account {moveHere.account}, and
                  started again there.
                </p>
                <div className="flex gap-2">
                  <button
                    data-testid="move-stop-confirm"
                    disabled={moving || after !== null}
                    onClick={() => {
                      const staged = moveHere.staged as JoinChoice
                      whenStopped(() => doJoin(moveHere.account, staged, false, true), true)
                    }}
                    className={`${btnCls} border-warn/50 text-warn-text hover:bg-warn/10`}
                  >
                    Move and restart
                  </button>
                  <button
                    data-testid="move-stop-cancel"
                    onClick={() => setMove(null)}
                    className={`${btnCls} border-border-default text-text-secondary hover:bg-bg-hover hover:text-text-primary`}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : null}
            {moveHere.staged === null && (
              <button
                data-testid="move-cancel"
                onClick={() => setMove(null)}
                className="self-start px-3 py-[5px] rounded-md text-[12px] border border-border-default text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-colors"
              >
                Cancel the move
              </button>
            )}
          </div>
        )}

        {/* ⚠ Not while it holds a trade: the line above says why it cannot move at all. */}
        {!holding && (
          <p className="text-[11px] text-text-tertiary leading-[1.5] mt-[8px]">
            {running
              ? 'It is running: a move or a removal stops it first, since it reads its account when it starts. A move onto a demo account starts it again there.'
              : "A move rewrites the server, terminal and symbol to match. It takes effect at this bot's next start."}
          </p>
        )}
      </section>

      {/* ── version, and the only Deploy control ────────────────────────────── */}
      <section className="py-[16px] border-b border-border-subtle">
        {/* 🔴 IT SAYS "DEPLOY" IN THE HEADING (2026-09-06) — *Version* names the noun; the reader is
         *  looking for the verb. What a deploy does moved to the heading's hover (2026-09-12): a
         *  paragraph under it said the same two sentences on every open. */}
        <SectionTitle hint="Deploying copies the code on the trading box and restarts the bot on it. Until you do, it keeps running the version it started with.">
          Version · deploy new code to this bot
        </SectionTitle>
        <VersionBanner
          botKey={bot.key}
          botLabel={labelOf(bot)}
          job={job}
          live={bot.account_type === 'live'}
          liveBot={bot}
          fetchedAt={fetchedAt}
        />
      </section>

      {/* ── its record: only what the row does not already say ─────────────── */}
      {/* ⚠ A bot with no record still SAYS so, in the server's own words.
       *  ⚠ ONE line since 2026-09-12: a two-row table read "0 / 0" beside "2026-09-11 → 2026-09-11"
       *  for a bot that had closed nothing on the one day its record covered. */}
      <section data-testid="bot-record" className="py-[16px]">
        <SectionTitle>Record</SectionTitle>
        {!earnings || !earnings.traded ? (
          <p className="text-[12px] text-text-tertiary leading-[1.5]">
            {earnings?.reason ??
              'No decision record has been read for this bot, so nothing here has been measured.'}
          </p>
        ) : (
          <p className="text-[12px] text-text-secondary leading-[1.5]">
            {(earnings.closed_trades ?? (earnings.wins ?? 0) + (earnings.losses ?? 0)) === 0
              ? 'No closed trades yet'
              : `${earnings.wins ?? 0} won · ${earnings.losses ?? 0} lost`}
            <span className="text-text-tertiary">
              {' · record '}
              {earnings.records_from === earnings.records_to
                ? earnings.records_from
                : `${earnings.records_from} → ${earnings.records_to}`}
            </span>
          </p>
        )}
      </section>

      {/* ── everything you only read ────────────────────────────────────────── */}
      {v && (
        <Fold label={`Details — where it trades, and the ${v.strategy.length} parameters`}>
          <Facts
            rows={[
              ['Strategy', v.version.strategy_package ?? '—'],
              ['Server', v.identity.server ?? '—'],
              ['Symbol', v.identity.symbol ?? '—'],
              ['Timeframe', v.identity.timeframe ?? '—'],
              ['Terminal', terminal],
              ['Trade id', v.identity.magic ?? '—'],
            ]}
          />

          {/* The prose the risk editor does not print — here, where somebody asking *why is it
           *  5%* will look, and nobody else has to read it. */}
          {v.runtime.filter((r) => r.note).length > 0 && (
            <div className="mt-[16px] pt-[12px] border-t border-border-subtle/60">
              <p className="text-[9.5px] font-semibold uppercase tracking-[0.8px] text-text-tertiary mb-[6px]">
                Why these values
              </p>
              {v.runtime
                .filter((r) => r.note)
                .map((r) => (
                  <p
                    key={r.name}
                    className="text-[10.5px] text-text-tertiary leading-[1.55] mb-[10px]"
                  >
                    <span className="text-text-secondary">{r.label}: </span>
                    {r.note}
                  </p>
                ))}
            </div>
          )}

          <div className="mt-[16px] pt-[12px] border-t border-border-subtle/60">
            <p className="text-[10.5px] text-text-tertiary mb-[8px] leading-[1.5]">
              These decide <strong className="text-text-secondary">which trades</strong> it takes,
              so changing one means it is no longer the bot that was backtested. Edit in the lab,
              backtest, then deploy.
            </p>
            {Object.entries(strategyGroups).map(([g, rows]) => (
              <ParamGroup key={g} group={g} rows={rows} />
            ))}
          </div>
        </Fold>
      )}
    </Drawer>
  )
}
