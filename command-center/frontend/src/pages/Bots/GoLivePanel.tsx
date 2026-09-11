/**
 * Demo → live, as a step INSIDE the account drawer — never a modal over it.
 *
 * The last hop of backtest → stress test → demo → live, and the only one that spends real money.
 *
 * 🔴 **REBUILT 2026-09-10, off Aaron's screenshot of the modal it replaced:** *"look how
 * confusing this modal is, make it damn simple… no technical code variable names"* and *"I'd
 * rather not go from a side drawer to a modal — continue in the side drawer and make it wider."*
 * The modal printed each bot's internal key, a table of raw config field names per bot, a note
 * about a setting one strategy does not have, and an amber box of five "warnings" of which four
 * said nothing was wrong. Every fact a reader needs was on it; none of them was findable.
 *
 * What the reader needs, in the order they need it: WHERE it goes (one from → to card), WHAT goes
 * (each bot, its risk, what it did on demo), what is TRUE AFTERWARDS, anything that is actually
 * wrong, and the one typed confirmation. The literal writes are still here — behind *Exactly what
 * changes*, in plain words — because this is the last screen before real money and somebody
 * checking it must be able to.
 *
 * 🔴 **NOTHING IN THIS FILE DECIDES ANYTHING.** The moves, the writes, the warnings, the carried
 * risk ceiling, every refusal and the confirmation phrase arrive from the backend, which plans ONCE
 * and returns the same shape to the preview and the apply. This file only chooses the WORDS.
 *
 * 🔴 **ALL OR NOTHING.** No per-bot tick box: two of three bots on the live account is a strategy
 * set nobody ran, and on every screen afterwards it reads as a finished promotion.
 *
 * 🔴 **THE CONFIRMATION PHRASE IS THE SERVER'S, NEVER BUILT HERE.** It names the destination
 * account, so it cannot be typed from memory or carried over from a different preview.
 *
 * ⚠ **The set is FROZEN when the panel opens.** After the move the demo account holds no bots, and
 * the page's refetch hands the drawer an empty account — read live, the done screen would turn
 * into a refusal that no bots were named.
 *
 * ⚠ **There is no minimum demo record** (Aaron's call). What each bot did is REPORTED and refuses
 * nothing; a bot with no record says so, which is not the same fact as a bot that traded nothing.
 */

import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, ArrowLeft, ArrowRight, CheckCircle2, Lock, Rocket } from 'lucide-react'
import { useGoLivePreview, useApplyGoLive } from '@/hooks/useBots'
import { Shimmer } from '@/components/Shimmer'
import type {
  BotAccountBot,
  BotAccountGroup,
  BotAccountRegistration,
  GoLiveMove,
  GoLivePlan,
  GoLiveRecord,
} from '@/types'

/** "Both bots", "The bot", "All 3 bots" — the set is always named as a whole. */
function setNoun(n: number): string {
  return n === 1 ? 'The bot' : n === 2 ? 'Both bots' : `All ${n} bots`
}

function joinNames(names: string[]): string {
  if (names.length <= 1) return names[0] ?? ''
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
}

function fmtR(r: number): string {
  return `${r > 0 ? '+' : r < 0 ? '−' : ''}${Math.abs(r).toFixed(2)}R`
}

/** What a bot did on demo, in one line. `null` record = could not be read, which is not "none". */
function recordText(r: GoLiveRecord | null): { text: string; warn: boolean } {
  if (!r) return { text: 'Demo record could not be read', warn: true }
  if (!r.traded) return { text: 'No demo record on this machine', warn: true }
  const n = r.closed_trades ?? 0
  const parts = [`${n} trade${n === 1 ? '' : 's'}`]
  if (r.wins != null && r.losses != null) parts.push(`${r.wins} won, ${r.losses} lost`)
  if (r.realised_r != null) parts.push(fmtR(r.realised_r))
  return { text: parts.join(' · '), warn: false }
}

// ── "Exactly what changes": the literal writes, in words ──────────────────────────────────

/** Plain names for the settings a move writes. ⚠ A setting not listed here still renders — as
 *  its name tidied — rather than vanishing: this list is the RECORD of what is written, so nothing
 *  may be dropped from it. */
const WRITE_LABEL: Record<string, string> = {
  account: 'Account',
  server: 'Broker server',
  mt5_path: 'Terminal on the trading box',
  symbol: 'Instrument',
  account_risk_cap_pct: 'Account risk cap',
  account_profile: 'Cost profile',
}

function tidy(name: string): string {
  const s = name.replace(/_/g, ' ')
  return s.charAt(0).toUpperCase() + s.slice(1)
}

function writeValue(
  name: string,
  v: unknown,
  registry: BotAccountRegistration[]
): { text: string; title?: string } {
  if (v === null || v === undefined || v === '') return { text: 'none' }
  if (name === 'account_risk_cap_pct' && typeof v === 'number') return { text: `${v}%` }
  if (name === 'mt5_path' && typeof v === 'string') {
    // The folder names the terminal; the full path is one hover away.
    const parts = v.split(/[\\/]/).filter(Boolean)
    return { text: parts.length > 1 ? parts[parts.length - 2] : v, title: v }
  }
  if (name === 'account_profile' && typeof v === 'string') {
    // A cost profile is an id; the account list knows which broker and tier it prices.
    const a = registry.find((r) => r.account_profile === v)
    return a ? { text: `${a.broker} ${a.tier}`.trim(), title: v } : { text: v }
  }
  return { text: typeof v === 'string' ? v : JSON.stringify(v) }
}

/** Every write for every bot, with the ones they all share stated ONCE and the rest per bot. */
function splitWrites(moves: GoLiveMove[]): {
  shared: [string, unknown][]
  perBot: { move: GoLiveMove; rows: [string, unknown][] }[]
} {
  const all = moves.map((m) => ({ ...m.param_fields, ...m.fields }))
  const names = [...new Set(all.flatMap((w) => Object.keys(w)))]
  const same = (k: string) =>
    all.every((w) => k in w && JSON.stringify(w[k]) === JSON.stringify(all[0][k]))
  const shared = names.filter(same).map((k): [string, unknown] => [k, all[0][k]])
  const perBot = moves
    .map((move, i) => ({
      move,
      rows: names
        .filter((k) => !same(k) && k in all[i])
        .map((k): [string, unknown] => [k, all[i][k]]),
    }))
    .filter((b) => b.rows.length > 0)
  return { shared, perBot }
}

function WriteRows({
  rows,
  registry,
}: {
  rows: [string, unknown][]
  registry: BotAccountRegistration[]
}) {
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-[6px] text-[12px]">
      {rows.map(([k, v]) => {
        const val = writeValue(k, v, registry)
        return (
          <div key={k} className="contents">
            <dt className="text-text-tertiary">{WRITE_LABEL[k] ?? tidy(k)}</dt>
            <dd className="m-0 text-right text-text-primary" title={val.title}>
              {val.text}
            </dd>
          </div>
        )
      })}
    </dl>
  )
}

// ── The panel ──────────────────────────────────────────────────────────────────────────────

export function GoLivePanel({
  group,
  fromReg,
  registry,
  onBack,
  onClose,
}: {
  group: BotAccountGroup
  /** The demo account's own registry row — what the From side of the card describes. */
  fromReg: BotAccountRegistration | undefined
  registry: BotAccountRegistration[]
  onBack: () => void
  onClose: () => void
}) {
  const [bots] = useState<BotAccountBot[]>(() => group.bots)
  const [capNow] = useState(() => (group.cap_agrees ? group.risk_cap_pct : null))
  const botKeys = useMemo(() => bots.map((b) => b.key), [bots])
  const preview = useGoLivePreview()
  const apply = useApplyGoLive()

  // Only LIVE accounts are destinations. One that cannot take a bot is LISTED and DISABLED with
  // the reason, never hidden — a destination that silently vanishes reads as a bug.
  const live = registry.filter((a) => a.kind === 'live')
  const choosable = live.filter((a) => a.assignable)
  // With exactly one live account there is nothing to choose, so it is picked for you. The preview
  // writes nothing, and the typed phrase still stands between this and real money.
  const [account, setAccount] = useState<number | null>(() =>
    choosable.length === 1 ? choosable[0].account : null
  )
  const [typed, setTyped] = useState('')
  const [done, setDone] = useState<GoLivePlan | null>(null)

  useEffect(() => {
    if (account !== null) preview.mutate({ bots: botKeys, account })
    // `mutate` is stable; the preview is asked again only when the destination changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [account])

  // A preview answers for the account it was ASKED about — never shown under a different pick.
  const plan = preview.variables?.account === account ? preview.data : undefined
  const dest = live.find((a) => a.account === account)
  const phrase = plan?.confirm ?? ''
  const ready = !!plan && !plan.blocked && plan.moves.length > 0
  const canApply = ready && typed.trim() === phrase && !apply.isPending
  const noun = setNoun(bots.length)

  if (done) {
    const moved = done.moves.map((m) => m.display || m.bot)
    return (
      <div className="px-5 py-10 flex flex-col items-start gap-3">
        <CheckCircle2 size={28} className="text-pos-text" />
        <h2 className="text-[17px] font-semibold text-text-primary">On the live account</h2>
        <p className="text-[13px] text-text-secondary leading-relaxed">
          {joinNames(moved)} {moved.length === 1 ? 'is' : 'are'} now on live account{' '}
          <span className="font-mono text-text-primary">{done.to_account}</span>
          {dest?.label ? ` (${dest.label})` : ''}.
        </p>
        <p className="text-[13px] text-text-secondary leading-relaxed">
          {moved.length === 1 ? 'It is' : 'They are'} stopped. Start{' '}
          {moved.length === 1 ? 'it' : 'each one'} from the bot list when you're ready — nothing
          trades until you do.
        </p>
        <button
          onClick={onClose}
          className="mt-3 px-4 py-[7px] rounded-md text-[12.5px] font-medium border border-border-default text-text-primary hover:bg-bg-hover transition-colors"
        >
          Close
        </button>
      </div>
    )
  }

  return (
    <div data-testid="go-live-panel">
      <div className="px-5 pb-6">
        <button
          onClick={onBack}
          className="mt-[14px] flex items-center gap-[6px] text-[12px] text-text-tertiary hover:text-text-primary transition-colors"
        >
          <ArrowLeft size={13} /> Back to the account
        </button>

        <h2 className="mt-[14px] text-[18px] font-semibold text-text-primary flex items-center gap-2">
          <Rocket size={16} className="text-warn-text" /> Move to live
        </h2>
        <p className="mt-[5px] text-[13px] text-text-secondary leading-relaxed">
          {noun} leave this demo account and trade a live one instead.
          {bots.length > 1 && ' They move together — all of them or none.'}
        </p>

        {/* ── where to ────────────────────────────────────────────────── */}
        <p className="mt-[22px] mb-[8px] text-[9px] font-semibold uppercase tracking-[0.8px] text-gold-text">
          Live account
        </p>
        {live.length === 0 ? (
          <p className="text-[12.5px] text-text-tertiary leading-relaxed">
            No live account is set up yet. Add one from Sync VPS on the bot list first.
          </p>
        ) : (
          <div className="flex flex-col gap-[6px]">
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
                  }}
                  className={`flex items-center gap-3 px-[14px] py-[10px] rounded-lg border text-left transition-colors ${
                    selected
                      ? 'border-warn/60 bg-warn-muted'
                      : a.assignable
                        ? 'border-border-subtle bg-bg-sunken hover:border-border-default'
                        : 'border-border-subtle bg-bg-sunken opacity-60 cursor-not-allowed'
                  }`}
                >
                  <span className="font-mono tabular-nums text-[13px] font-semibold text-text-primary">
                    {a.account}
                  </span>
                  <span className="text-[13px] text-text-secondary truncate">
                    {a.label || a.broker}
                  </span>
                  <span className="ml-auto text-[11.5px] text-text-tertiary shrink-0">
                    {a.assignable ? `${a.broker} ${a.tier}`.trim() : 'cannot take bots'}
                  </span>
                </button>
              )
            })}
          </div>
        )}

        {/* ── the plan ────────────────────────────────────────────────── */}
        {account !== null && !plan && preview.isPending && (
          <div className="mt-[22px] flex flex-col gap-[10px]" aria-busy="true">
            <Shimmer className="h-[78px] w-full" />
            <Shimmer className="h-[96px] w-full" />
          </div>
        )}

        {account !== null && preview.isError && (
          <div className="mt-[22px] rounded-lg border border-neg/30 bg-neg-muted p-[14px] text-[12.5px] text-neg-text leading-relaxed">
            Couldn't work out the move. Nothing was changed.{' '}
            <button
              onClick={() => preview.mutate({ bots: botKeys, account })}
              className="underline underline-offset-2"
            >
              Try again
            </button>
          </div>
        )}

        {plan?.blocked && (
          <div
            data-testid="go-live-blocked"
            className="mt-[22px] rounded-lg border border-neg/30 bg-neg-muted p-[14px] flex gap-[10px]"
          >
            <Lock size={14} className="text-neg-text shrink-0 mt-[2px]" />
            <p className="text-[12.5px] text-neg-text leading-relaxed">{plan.blocked}</p>
          </div>
        )}

        {ready && plan && (
          <>
            {/* From → to, once. Server and terminal are facts about the ACCOUNT, so they are
                stated here rather than repeated under every bot. */}
            <div className="mt-[22px] grid grid-cols-[1fr_auto_1fr] items-center gap-3 rounded-lg border border-border-subtle bg-bg-sunken px-[16px] py-[14px]">
              <div className="min-w-0">
                <p className="text-[9px] font-semibold uppercase tracking-[0.8px] text-text-tertiary">
                  From · demo
                </p>
                <p className="mt-[4px] font-mono tabular-nums text-[14px] text-text-primary">
                  {plan.from_account}
                </p>
                <p className="text-[12px] text-text-secondary truncate">
                  {fromReg?.label || 'Demo account'}
                </p>
              </div>
              <ArrowRight size={16} className="text-text-tertiary" />
              <div className="min-w-0">
                <p className="text-[9px] font-semibold uppercase tracking-[0.8px] text-warn-text">
                  To · live
                </p>
                <p className="mt-[4px] font-mono tabular-nums text-[14px] font-semibold text-warn-text">
                  {plan.to_account}
                </p>
                <p className="text-[12px] text-text-secondary truncate">
                  {dest?.label || dest?.broker || 'Live account'}
                </p>
              </div>
            </div>

            {/* What goes: each bot, its risk, what it did on demo. */}
            <p className="mt-[22px] mb-[8px] text-[9px] font-semibold uppercase tracking-[0.8px] text-gold-text">
              Moving
            </p>
            <div className="rounded-lg border border-border-subtle divide-y divide-border-subtle">
              {plan.moves.map((m) => {
                const bot = bots.find((b) => b.key === m.bot)
                const rec = recordText(m.record)
                return (
                  <div key={m.bot} className="flex items-center gap-3 px-[14px] py-[10px]">
                    <span className="text-[13px] font-medium text-text-primary min-w-0 truncate">
                      {m.display || m.bot}
                    </span>
                    <span className="text-[12px] text-text-tertiary shrink-0">
                      {typeof bot?.risk_pct === 'number' ? `${bot.risk_pct}% a trade` : ''}
                    </span>
                    <span
                      title="What it did on the demo account. Reported, never a requirement."
                      className={`ml-auto text-[12px] text-right shrink-0 ${
                        rec.warn ? 'text-warn-text' : 'text-text-secondary'
                      }`}
                    >
                      {rec.warn ? rec.text : `On demo: ${rec.text}`}
                    </span>
                  </div>
                )
              })}
              <div className="flex items-center gap-3 px-[14px] py-[10px] text-[12.5px]">
                <span className="text-text-secondary">Account risk cap</span>
                <span className="ml-auto text-text-primary">
                  {plan.cap_pct != null ? `${plan.cap_pct}%` : 'none'}
                  {plan.cap_pct != null && plan.cap_pct === capNow && (
                    <span className="text-text-tertiary"> · same as now</span>
                  )}
                </span>
              </div>
            </div>

            {/* What is true afterwards — fixed facts about this control. */}
            <p className="mt-[22px] mb-[8px] text-[9px] font-semibold uppercase tracking-[0.8px] text-gold-text">
              After you confirm
            </p>
            <ul className="flex flex-col gap-[6px] text-[12.5px] text-text-secondary leading-relaxed">
              <li>
                · {noun === 'The bot' ? 'It sits' : `${noun} sit`} on the live account,{' '}
                <span className="text-text-primary">stopped</span>. Nothing trades until you start{' '}
                {bots.length === 1 ? 'it' : 'them'}.
              </li>
              <li>· This demo account is left with no bots.</li>
              <li>· You get a message on Telegram.</li>
            </ul>

            {/* Only things that ask something of the reader reach this box — see the backend's
                `_warnings`. A clean promotion shows none. */}
            {plan.warnings.length > 0 && (
              <div
                data-testid="go-live-warnings"
                className="mt-[18px] rounded-lg border border-warn/40 bg-warn-muted p-[14px] flex flex-col gap-[8px]"
              >
                {plan.warnings.map((w) => (
                  <div key={w} className="flex gap-[10px]">
                    <AlertTriangle size={13} className="text-warn-text shrink-0 mt-[3px]" />
                    <p className="text-[12.5px] text-warn-text leading-relaxed">{w}</p>
                  </div>
                ))}
              </div>
            )}

            <Details plan={plan} registry={registry} />

            {/* The phrase names the account, so it cannot be typed from memory. Served, never
                built here. */}
            <div className="mt-[22px] rounded-lg border border-warn/40 bg-warn-muted/40 px-[14px] py-[12px]">
              <label htmlFor="go-live-confirm" className="text-[12.5px] text-text-secondary">
                To confirm, type{' '}
                <span className="font-mono font-semibold text-warn-text">{phrase}</span>
              </label>
              <input
                id="go-live-confirm"
                data-testid="go-live-confirm"
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                spellCheck={false}
                autoComplete="off"
                placeholder={phrase}
                className="mt-[8px] w-full bg-bg-sunken border border-border-subtle rounded-md px-[10px] py-[7px] text-[13px] font-mono text-text-primary placeholder:text-text-tertiary/50 focus:outline-none focus:border-warn/60"
              />
            </div>
          </>
        )}
      </div>

      {/* Pinned, so the one action this panel builds up to is never scrolled out of reach. */}
      <div className="sticky bottom-0 flex items-center justify-end gap-2 px-5 py-[12px] border-t border-border-subtle bg-bg-surface">
        <button
          onClick={onBack}
          className="px-[14px] py-[7px] rounded-md text-[12.5px] font-medium text-text-secondary hover:text-text-primary border border-border-subtle hover:border-border-default transition-colors"
        >
          Cancel
        </button>
        <button
          data-testid="go-live-apply"
          disabled={!canApply}
          title={
            !ready
              ? undefined
              : typed.trim() === phrase
                ? undefined
                : `Type ${phrase} above to enable this`
          }
          onClick={() =>
            apply.mutate(
              { bots: botKeys, account: account as number, confirm: typed.trim(), deploy: true },
              {
                onSuccess: (res) => (res.applied ? setDone(res) : onBack()),
                // The server's own refusal is already toasted. Ask again, so the panel shows
                // what is true now — a bot started in the meantime, say — rather than the old plan.
                onError: () => preview.mutate({ bots: botKeys, account: account as number }),
              }
            )
          }
          className={`px-[16px] py-[7px] rounded-md text-[12.5px] font-semibold transition-colors ${
            canApply
              ? 'bg-warn text-bg-base hover:opacity-90'
              : 'bg-bg-sunken text-text-tertiary cursor-not-allowed border border-border-subtle'
          }`}
        >
          {apply.isPending ? 'Moving…' : 'Move to live'}
        </button>
      </div>
    </div>
  )
}

/** The literal writes, in words, behind one click. Shared rows once; anything that differs per
 *  bot under that bot's name. */
function Details({ plan, registry }: { plan: GoLivePlan; registry: BotAccountRegistration[] }) {
  const { shared, perBot } = splitWrites(plan.moves)
  return (
    <details className="mt-[18px] group">
      <summary className="cursor-pointer select-none list-none [&::-webkit-details-marker]:hidden text-[12px] text-text-tertiary hover:text-text-secondary">
        <span className="group-open:hidden">▸</span>
        <span className="hidden group-open:inline">▾</span> Exactly what changes on{' '}
        {plan.moves.length === 1 ? 'the bot' : 'each bot'}
      </summary>
      <div className="mt-[10px] rounded-lg border border-border-subtle bg-bg-sunken px-[14px] py-[12px] flex flex-col gap-[14px]">
        {shared.length > 0 && (
          <div>
            {plan.moves.length > 1 && (
              <p className="mb-[6px] text-[11px] text-text-tertiary">All of them</p>
            )}
            <WriteRows rows={shared} registry={registry} />
          </div>
        )}
        {perBot.map(({ move, rows }) => (
          <div key={move.bot}>
            <p className="mb-[6px] text-[11px] text-text-tertiary">{move.display || move.bot}</p>
            <WriteRows rows={rows} registry={registry} />
          </div>
        ))}
      </div>
    </details>
  )
}
