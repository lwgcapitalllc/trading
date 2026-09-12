/**
 * One trading account: its money, the bots spending it, and the budget they share.
 *
 * 🔴 **The balance and the cap belong HERE and nowhere else.** They were on every bot row of
 * every tab, which is both the duplication Aaron reported and the reason the fleet total
 * double-counted a stacked account — two bots reporting one balance, added together.
 *
 * 🔴 **The risk budget is ONE editable thing with ONE Save (2026-09-11).** Each bot's share is a
 * box on its own row, the cap is a box under them, and the pinned footer says exactly what Save
 * will write, whether the result fits (the server's plan, asked as the reader types) and when it
 * takes effect — then writes it all in one commit. Before: a cap box with its own Save beside
 * read-only shares, a toast telling the reader to restart the bots (no longer true — each bot takes
 * a new cap the next time it has no open trade), and a share changeable only from the bot's own
 * panel, where a raise on a full account was refused with no way out on either side.
 *
 * ⚠ **Nothing here adds shares up or decides whether they fit.** The total, the room and the
 * verdict are served, and the two one-click fixes (`fit_cap`, `fit_shares`) are the server's
 * numbers. This page's own reduce once printed a total that fitted while the save was refused.
 *
 * ⚠ **Adding a bot, taking one off and the ways to make room all go through the one move
 * endpoint** (`useJoinAccount`), the path the bot panel uses too. A live account confirms on screen
 * first — the server refuses a move onto one without it.
 *
 * ⚠ **Editing the account and demo → live are STEPS of this panel**, the account's own view swapped
 * out whole — never a modal on top, never a form trailing under the buttons (Aaron, 2026-09-10:
 * *"continue in the side drawer"*).
 */
import { useEffect, useState } from 'react'
import {
  ArrowUp,
  ChevronRight,
  Loader2,
  Pencil,
  Play,
  Plus,
  Rocket,
  Scale,
  Square,
  Trash2,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import {
  useAccountRiskPlan,
  useAssignBotAccount,
  useSaveAccountRisk,
  useUnregisterAccount,
} from '@/hooks/useBots'
import type {
  AccountEarnings,
  BotAccountBot,
  BotAccountGroup,
  BotAccountRegistration,
  BotAccountRiskPlan,
  BotAccountRiskRequest,
} from '@/types'
import { openingRecorder } from '@/lib/accountEarnings'
import { useDebounced } from '@/lib/useDebounced'
import { Drawer } from '@/components/Drawer'
import { DecimalInput } from '@/components/DecimalInput'
import { Shimmer } from '@/components/Shimmer'
import { AccountForm, nameOf } from './AccountForm'
import { AddBotPanel } from './AddBotPanel'
import { GoLivePanel } from './GoLivePanel'
import { KindBadge } from './kind'
import { BotActionPill, type BotAction } from './BotStatusPill'
import { SectionTitle, StateDot } from './drawerParts'
import { pct, useJoinAccount } from './joinAccount'

const chipCls =
  'inline-flex items-center text-[10px] font-semibold px-[7px] py-[2px] rounded-pill uppercase tracking-[0.4px] border'
const actionCls =
  'flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small border transition-colors disabled:opacity-40 disabled:cursor-not-allowed'
const fixCls =
  'inline-flex items-center gap-[5px] px-[10px] py-[5px] rounded-md text-[11.5px] font-medium border border-accent/40 text-accent-text hover:bg-accent/15 transition-colors'
/** One grid for the table's heading and every row under it — a hand-copied column list is how a
 *  heading ends up confidently over the wrong number. */
const ROW_GRID = 'grid grid-cols-[minmax(0,1fr)_66px_112px_136px] items-center gap-3 px-3'

const money = (n: number) =>
  '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

/** One change the footer's Save will write, read as `B-LEG 10% → 8%`. */
function Change({ label, from, to }: { label: string; from: string; to: string }) {
  return (
    <span className="inline-flex items-center gap-[5px] text-[11.5px] px-[8px] py-[3px] rounded-md bg-bg-surface-2 border border-border-subtle">
      <span className="text-text-secondary">{label}</span>
      <span className="font-mono tabular-nums text-text-tertiary">{from}</span>
      <span className="text-text-tertiary">→</span>
      <span className="font-mono tabular-nums text-text-primary">{to}</span>
    </span>
  )
}

/** The server's two ways to make the budget fit, as buttons that fill the draft — never a save. */
function FixButtons({
  plan,
  onCap,
  onShares,
}: {
  plan: BotAccountRiskPlan
  onCap: (cap: number) => void
  onShares: (shares: Record<string, number>) => void
}) {
  if (plan.fit_cap == null && !plan.fit_shares) return null
  return (
    <div data-testid="budget-fixes" className="flex flex-wrap gap-2 mt-[8px]">
      {plan.fit_cap != null && (
        <button
          data-testid="fix-cap"
          onClick={() => onCap(plan.fit_cap as number)}
          className={fixCls}
        >
          <ArrowUp size={11} /> Raise the cap to {pct(plan.fit_cap)}
        </button>
      )}
      {plan.fit_shares && (
        <button
          data-testid="fix-shares"
          onClick={() => onShares(plan.fit_shares as Record<string, number>)}
          className={fixCls}
        >
          <Scale size={11} /> Scale the bots to fit {pct(plan.risk_cap_pct)}
        </button>
      )}
    </div>
  )
}

/**
 * How full the budget is, as a bar. ⚠ Presentation only: the width is the served total over the
 * served cap, and "over" is the server's own overflow reason — never a comparison made here.
 */
function BudgetMeter({
  total,
  cap,
  over,
}: {
  total: number | null
  cap: number | null
  over: boolean
}) {
  if (total == null || cap == null || cap <= 0) return null
  return (
    <div
      className="mt-[12px] h-[6px] rounded-full bg-bg-sunken overflow-hidden"
      title={`${pct(total)} of the ${pct(cap)} cap`}
    >
      <div
        data-testid="budget-meter"
        data-over={over || undefined}
        className={`h-full rounded-full transition-[width] ${over ? 'bg-neg' : 'bg-accent'}`}
        style={{ width: `${Math.min(total / cap, 1) * 100}%` }}
      />
    </div>
  )
}

export function AccountDrawer({
  group,
  reg,
  registry,
  balance,
  balanceReadAt = null,
  earnings,
  startAdding = false,
  asking = false,
  statusByKey,
  onClose,
  onOpenBot,
  onStart,
  onStop,
  pendingKey = null,
  pendingAction = null,
  busy = false,
}: {
  group: BotAccountGroup
  reg: BotAccountRegistration | undefined
  /** Every registered account, because the demo → live promotion needs the DESTINATIONS and this
   *  account's own row cannot name them. */
  registry: BotAccountRegistration[]
  /** Read off the bots, because the accounts endpoint deliberately never touches the VPS. */
  balance: number | null
  /** When `balance` was read, when it is the LAST reading a bot took here because nothing on the
   *  account reports one now. `null` for a live balance. The panel says so beside the figure. */
  balanceReadAt?: string | null
  /** Open with the bot picker already out — the account card's "Add a bot". */
  startAdding?: boolean
  /** What this account has MADE and where it came from — computed server-side. ⚠ The split
   *  between the bots and the remainder is never derived here. */
  earnings: AccountEarnings | undefined
  /** The trading box's FIRST read is still in flight — the balance shimmers rather than saying
   *  nobody is answering, which is only true once it has been asked and failed. */
  asking?: boolean
  statusByKey: Map<string, string>
  onClose: () => void
  /** Open one of this account's bots in its own panel. */
  onOpenBot?: (key: string) => void
  onStart?: (key: string) => void
  onStop?: (key: string) => void
  /** A start/stop still in flight — the same pill the page's row shows. */
  pendingKey?: string | null
  pendingAction?: BotAction | null
  busy?: boolean
}) {
  const navigate = useNavigate()
  const unregister = useUnregisterAccount()
  const takeOff = useAssignBotAccount()
  const join = useJoinAccount()
  const save = useSaveAccountRisk()

  const account = group.account
  const hasBots = group.bots.length > 0
  const live = reg?.kind === 'live'
  const [editing, setEditing] = useState(false)
  const [adding, setAdding] = useState(startAdding)
  const [goingLive, setGoingLive] = useState(false)

  // ── the draft budget ─────────────────────────────────────────────────────────
  //
  // 🔴 **Only the reader's EDITS are state, each bound to the value it was made AGAINST (`from`).**
  // The cap box was once `useState(stated)` — copied when the panel opened — so a panel opened on an
  // empty account and then given bots at 10% read "uncapped" with Save live, and Save would have
  // written "no cap" to every bot. When the served value moves, the edit is dropped rather than
  // saved over a change nobody saw.
  //
  // ⚠ A disagreement is NOT a cap: quoting one bot's number when they differ would put a figure on
  // screen no bot is running and hide the one condition that stops them all starting.
  const stated = group.cap_agrees ? group.risk_cap_pct : null
  const [capEdit, setCapEdit] = useState<{
    capped: boolean
    value: number | null
    from: number | null
  } | null>(null)
  const liveCap = capEdit && capEdit.from === stated ? capEdit : null
  const capped = liveCap ? liveCap.capped : stated !== null
  const capValue = liveCap ? liveCap.value : (stated ?? 10)
  const setCapped = (v: boolean) => setCapEdit({ capped: v, value: capValue, from: stated })
  const setCapValue = (v: number | null) => setCapEdit({ capped, value: v, from: stated })
  const capNext = capped ? capValue : null
  const capValid = !capped || (capValue != null && capValue > 0 && capValue <= 100)
  // With disagreeing caps any touched value is a change — one figure written to all of them is the
  // fix, even when that figure is "none".
  const capDirty = liveCap !== null && (capNext !== stated || !group.cap_agrees)

  const [shareEdits, setShareEdits] = useState<
    Record<string, { value: number | null; from: number | null }>
  >({})
  const shareOf = (b: BotAccountBot) => {
    const e = shareEdits[b.key]
    return e && e.from === b.risk_pct ? e.value : b.risk_pct
  }
  const setShare = (b: BotAccountBot, v: number | null) =>
    setShareEdits((s) => ({ ...s, [b.key]: { value: v, from: b.risk_pct } }))

  const changed: Record<string, number> = {}
  const shareChanges: { key: string; display: string; from: number | null; to: number }[] = []
  let shareBlank = false
  for (const b of group.bots) {
    if (b.unreadable) continue
    const v = shareOf(b)
    if (v === b.risk_pct) continue
    if (v == null || !(v > 0)) {
      shareBlank = true
      continue
    }
    changed[b.key] = v
    shareChanges.push({ key: b.key, display: b.display, from: b.risk_pct, to: v })
  }
  const sharesDirty = shareChanges.length > 0
  const hasEdits = capDirty || sharesDirty || shareBlank
  const editsValid = capValid && !shareBlank
  const discard = () => {
    setCapEdit(null)
    setShareEdits({})
  }

  // ── the server's plan for it ─────────────────────────────────────────────────
  //
  // Asked only while there is something to ask about: an edit, or an account ALREADY over its cap
  // (that plan carries the one-click fixes). Opening the panel on a healthy account asks nothing.
  const body: BotAccountRiskRequest | null =
    account === null || !hasBots
      ? null
      : hasEdits
        ? editsValid
          ? {
              ...(capDirty ? { risk_cap_pct: capNext } : {}),
              ...(sharesDirty ? { shares: changed } : {}),
            }
          : null
        : group.share_overflow_reason
          ? {}
          : null
  const asked = useDebounced(body, 250)
  const plan = useAccountRiskPlan(account, asked)
  const sameBody = JSON.stringify(asked) === JSON.stringify(body)
  // ⚠ A held answer to the PREVIOUS body is not an answer to this one — Save waits for the fresh one.
  const p = plan.data && !plan.isPlaceholderData && sameBody && body ? plan.data : undefined
  const planFailed = plan.isError && sameBody && body !== null
  const checking = body !== null && !p && !planFailed

  const canSave =
    hasEdits &&
    editsValid &&
    !group.cap_unknown &&
    !save.isPending &&
    account !== null &&
    hasBots &&
    (p ? !p.refused : planFailed)

  const saveAll = () => {
    if (account === null) return
    save.mutate(
      {
        account,
        ...(capDirty ? { riskCapPct: capNext } : {}),
        ...(sharesDirty ? { shares: changed } : {}),
      },
      { onSuccess: discard }
    )
  }
  const applyFitCap = (cap: number) => setCapEdit({ capped: true, value: cap, from: stated })
  const applyFitShares = (shares: Record<string, number>) =>
    setShareEdits(
      Object.fromEntries(
        group.bots
          .filter((b) => shares[b.key] !== undefined)
          .map((b) => [b.key, { value: shares[b.key], from: b.risk_pct }])
      )
    )

  // Take off takes a SECOND click on the same button — one press from taking a bot off the account
  // it trades — and disarms itself after 6s, so a stray click later cannot be the second one.
  const [armedKey, setArmedKey] = useState<string | null>(null)
  useEffect(() => {
    if (!armedKey) return
    const t = setTimeout(() => setArmedKey(null), 6_000)
    return () => clearTimeout(t)
  }, [armedKey])

  /**
   * Why a bot cannot be added here, in words — stated ON the control before the click rather than
   * as a refusal after it. ⚠ A password the VPS could not be ASKED about (`null`) blocks nothing:
   * only a definite no does, or the reader is sent to re-enter one that is already there.
   */
  const addBlock =
    reg && !reg.assignable
      ? `Cannot add a bot here — ${reg.unassignable_reason || 'no terminal on the box is logged into it'}.`
      : reg?.has_password === false
        ? 'No password is stored for this account, so a bot put here cannot log in. Add the trading password first (Edit).'
        : null

  /**
   * Why this set cannot go live, or `null` when it can — worst first, ONE reason. ⚠ A bot the box
   * has not answered for is NOT counted as stopped: `statusByKey` holds only what the snapshot
   * reported, and reading silence as *not running* is how a live-money write gets offered on a bot
   * that is trading.
   */
  const anyRunning = group.bots.some((b) => statusByKey.get(b.key) !== 'STOPPED')
  const liveTargets = registry.filter((a) => a.kind === 'live' && a.assignable)
  const goLiveBlock: string | null = anyRunning
    ? 'Stop every bot on this account first — a bot reads its account when it starts, so a move cannot reach a running one'
    : liveTargets.length === 0
      ? 'No live account with a terminal on the box to move them to'
      : null

  // 🔴 SERVED, never summed here — `BotAccountGroup.share_total_pct` carries why in its own type.
  const shareTotal = group.share_total_pct

  // ── the verdict on the draft, in words ───────────────────────────────────────
  const verdict = !editsValid ? (
    <span className="text-neg-text">
      {shareBlank
        ? 'Every bot needs a risk per trade — type one, or Discard.'
        : 'A cap is a percentage of the balance: above 0 and at most 100.'}
    </span>
  ) : group.cap_unknown ? (
    <span className="text-warn-text">
      A bot&rsquo;s config here cannot be read, so nothing can be saved — writing to the rest would
      leave the caps disagreeing.
    </span>
  ) : checking ? (
    <span className="inline-flex items-center gap-[6px] text-text-tertiary">
      <Loader2 size={11} className="animate-spin" /> Checking the budget…
    </span>
  ) : planFailed ? (
    <span className="text-text-tertiary">
      Could not check the budget — the save is checked again when you press it.
    </span>
  ) : p?.refused ? (
    <span data-testid="plan-refused" className="text-warn-text">
      {p.refused}
    </span>
  ) : p && !p.fits ? (
    <span className="text-text-secondary">
      Still over the cap, but this lowers the risk, so it can be saved.
    </span>
  ) : p ? (
    <span className="text-text-secondary">
      {p.risk_cap_pct == null ? (
        'No cap — nothing to fit under.'
      ) : (
        <>
          Fits — the bots would risk <b className="text-text-primary">{pct(p.share_total_pct)}</b>{' '}
          of the {pct(p.risk_cap_pct)} cap.
        </>
      )}{' '}
      <span className="text-text-tertiary">{p.applies}</span>
    </span>
  ) : null

  // ── the pinned footer: exactly what Save will write, and whether it may ──────
  const footer =
    account !== null && hasBots && !editing && !goingLive ? (
      <div data-testid="budget-footer" className="flex items-center gap-3">
        <div className="min-w-0 flex-1">
          {!hasEdits ? (
            <p
              className="text-[12px] text-text-tertiary"
              title="Change a bot's risk or the account's cap above; Save writes all of it in one go."
            >
              Risk budget · no changes
            </p>
          ) : (
            <>
              <div data-testid="budget-changes" className="flex flex-wrap gap-[6px]">
                {shareChanges.map((c) => (
                  <Change key={c.key} label={c.display} from={pct(c.from)} to={pct(c.to)} />
                ))}
                {capDirty && (
                  <Change
                    label="Cap"
                    from={!group.cap_agrees ? 'mixed' : stated === null ? 'none' : pct(stated)}
                    to={capNext === null ? 'none' : pct(capNext)}
                  />
                )}
              </div>
              <div data-testid="budget-verdict" className="text-[11.5px] leading-[1.5] mt-[6px]">
                {verdict}
              </div>
              {p?.reason && <FixButtons plan={p} onCap={applyFitCap} onShares={applyFitShares} />}
            </>
          )}
        </div>
        {hasEdits && (
          <button
            data-testid="budget-discard"
            onClick={discard}
            className="shrink-0 px-3 py-[6px] rounded-md text-[12px] border border-border-default text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-colors"
          >
            Discard
          </button>
        )}
        <button
          data-testid="cap-save"
          disabled={!canSave}
          onClick={saveAll}
          className="shrink-0 inline-flex items-center gap-[6px] px-4 py-[6px] rounded-md text-[12.5px] font-semibold bg-accent-muted text-accent-text border border-accent/50 hover:bg-accent/15 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {save.isPending && <Loader2 size={12} className="animate-spin" />}
          {save.isPending ? 'Saving…' : 'Save'}
        </button>
      </div>
    ) : undefined

  return (
    <Drawer
      open
      onClose={onClose}
      label="Account settings"
      // 720px since 2026-09-10 (Aaron: *"make the drawer wider"*). ⚠ Capped, never a fraction of
      // the screen — a panel wide enough to hide the list it came from is a page you left.
      width={720}
      title={
        // The login leads: it is what the broker, the terminal, every config and every refusal
        // names this account by; the label is a nickname somebody typed here.
        <span className="flex items-baseline gap-[9px] min-w-0">
          <span className="font-mono tabular-nums">{account ?? '—'}</span>
          <span className="truncate font-medium text-text-secondary">{nameOf(reg, group)}</span>
        </span>
      }
      subtitle={
        // 🔴 THE READINESS FACTS. Each answers *why did that move fail* BEFORE somebody makes it —
        // the only moment the answer is worth anything.
        <div className="flex items-center gap-[6px] flex-wrap mt-[5px]">
          <KindBadge kind={reg?.kind} />
          {reg?.server && (
            <span className="font-mono text-[11.5px] text-text-tertiary">{reg.server}</span>
          )}
          {/* ⚠ THREE states: `has_password` is `boolean | null`, and null means the VPS could not be
           *  ASKED. Rendering that as *no password* sends the reader to re-enter a credential that
           *  is already there. A definite no is a BUTTON — it opens the form where it is fixed. */}
          {reg &&
            (reg.has_password === false ? (
              <button
                data-testid="password-chip"
                onClick={() => setEditing(true)}
                title="No password is stored, so a bot put here cannot log in. Click to add the trading password."
                className={`${chipCls} bg-warn-muted text-warn-text border-warn/40 hover:bg-warn/15 transition-colors`}
              >
                no password · add
              </button>
            ) : (
              <span
                data-testid="password-chip"
                title={
                  reg.has_password === true
                    ? 'A password is stored on the trading box. It must be the trading password — with a read-only "investor" one a bot logs in and every order is refused.'
                    : 'The trading box could not be asked whether a password is stored — unknown, not missing.'
                }
                className={`${chipCls} cursor-default ${
                  reg.has_password === true
                    ? 'bg-bg-surface-2 text-text-secondary border-border-subtle'
                    : 'bg-bg-surface-2 text-text-tertiary border-border-strong'
                }`}
              >
                {reg.has_password === true ? 'password set' : 'password unknown'}
              </span>
            ))}
          {reg && !reg.assignable && (
            <span
              data-testid="no-terminal"
              title={
                reg.unassignable_reason ||
                'This account cannot be assigned a bot from here — see the registry entry.'
              }
              className={`${chipCls} cursor-default bg-warn-muted text-warn-text border-warn/40`}
            >
              no terminal
            </span>
          )}
          {/* ⚠ An account a bot NAMES that nobody registered still works — the move reads its
           *  peers — so this says what this page cannot do with it rather than hiding it. */}
          {!reg && account !== null && (
            <span
              data-testid="unregistered"
              title="A bot names this account but nobody registered it here, so this page has no broker, tier or symbol suffix for it. Add it to the registry to move bots onto it."
              className={`${chipCls} cursor-default bg-bg-surface-2 text-text-tertiary border-border-strong`}
            >
              not registered
            </span>
          )}
        </div>
      }
      footer={footer}
    >
      {editing && reg ? (
        <div className="h-full pt-4 pb-1">
          <AccountForm existing={reg} onClose={() => setEditing(false)} />
        </div>
      ) : goingLive && account !== null ? (
        // GoLivePanel carries its own side padding.
        <div className="-mx-5">
          <GoLivePanel
            group={group}
            fromReg={reg}
            registry={registry}
            onBack={() => setGoingLive(false)}
            onClose={onClose}
          />
        </div>
      ) : (
        <>
          {/* ── the money, once ─────────────────────────────────────────────── */}
          <section className="py-[16px] border-b border-border-subtle">
            <SectionTitle>Balance</SectionTitle>
            <p className="text-[24px] font-mono tabular-nums leading-none">
              {balance == null && asking ? (
                <Shimmer className="h-[24px] w-[160px]" />
              ) : balance == null ? (
                <span className="text-[13px] text-text-tertiary">
                  not reported — no bot here is answering
                </span>
              ) : (
                money(balance)
              )}
            </p>
            {/* ⚠ A PAST reading says so — a day-old figure with nothing beside it reads as now. */}
            {balance != null && balanceReadAt && (
              <p
                data-testid="drawer-balance-read-at"
                className="text-[11px] text-text-tertiary mt-[6px]"
              >
                Last read{' '}
                {new Date(balanceReadAt).toLocaleString('en-GB', {
                  day: 'numeric',
                  month: 'short',
                  hour: '2-digit',
                  minute: '2-digit',
                })}{' '}
                {hasBots
                  ? '— no bot here has reported one since it started.'
                  : 'by a bot before it left — no bot is on this account now.'}
              </p>
            )}
            {/* What it OPENED at, and which bot recorded that — a net with no denominator on screen
             *  is a number nobody can check. */}
            {/* 🔴 On the DEPOSITS basis the referent is what went in, not the opening: a deposit or
             *  a withdrawal is taken out of the net and the % is time-weighted (2026-09-12). */}
            {earnings?.net_usd != null &&
            (earnings.net_basis === 'deposits'
              ? earnings.capital_in != null
              : earnings.opening_balance != null) ? (
              <p className="text-[11.5px] text-text-tertiary mt-[8px] leading-[1.55]">
                <span className={earnings.net_usd >= 0 ? 'text-pos-text' : 'text-neg-text'}>
                  {earnings.net_usd >= 0 ? '+' : '−'}
                  {money(Math.abs(earnings.net_usd))}
                  {earnings.net_pct != null &&
                    ` (${earnings.net_pct > 0 ? '+' : ''}${earnings.net_pct.toFixed(1)}%)`}
                </span>{' '}
                {earnings.net_basis === 'deposits' && earnings.capital_in != null ? (
                  <>on {money(earnings.capital_in)} put in, deposits less withdrawals.</>
                ) : earnings.opening_balance != null ? (
                  <>
                    since it opened at {money(earnings.opening_balance)}
                    {openingRecorder(earnings) ? `, recorded by ${openingRecorder(earnings)}` : ''}.
                  </>
                ) : null}
              </p>
            ) : (
              earnings?.opening_note && (
                <p className="text-[11.5px] text-text-tertiary mt-[8px] leading-[1.55]">
                  {earnings.opening_note}
                </p>
              )
            )}
          </section>

          {/* ── who is spending it, and each one's share ───────────────────── */}
          <section className="py-[16px] border-b border-border-subtle">
            <SectionTitle
              aside={
                account !== null && (
                  /* ⚠ DISABLED with the reason on it, never hidden — a control that vanishes
                   *  reads as a feature that does not exist. */
                  <button
                    data-testid="add-bot"
                    disabled={!!addBlock || adding}
                    title={addBlock ?? 'Put a bot on this account'}
                    onClick={() => setAdding(true)}
                    className="inline-flex items-center gap-[5px] px-[11px] py-[5px] rounded-md text-[12px] font-medium border border-accent/40 text-accent-text hover:bg-accent/15 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <Plus size={12} /> Add bot
                  </button>
                )
              }
            >
              Bots on this balance · {group.bots.length}
            </SectionTitle>

            {/* 🔴 Two bots sharing an order tag each read the OTHER's orders as their own. The only
             *  warning here about two bots actively corrupting each other's book; shown when true. */}
            {group.magic_clash.length > 0 && (
              <div
                data-testid="magic-clash"
                className="text-[11px] text-neg-text bg-neg-muted border border-neg/40 rounded-md px-[10px] py-[7px] mb-[10px] leading-[1.5]"
              >
                <strong>{group.magic_clash.join(' and ')}</strong> share an order tag, so each would
                read the other&rsquo;s orders as its own — cancelling them, moving their stops and
                booking their fills. They will refuse to start until one is given a different one.
              </div>
            )}

            {group.bots.length === 0 ? (
              <p data-testid="no-bots" className="text-[12px] text-text-tertiary">
                No bot is on this account now.
              </p>
            ) : (
              <div className="rounded-md border border-border-subtle overflow-hidden">
                <div
                  className={`${ROW_GRID} py-[6px] bg-bg-surface-2 text-[9.5px] font-semibold uppercase tracking-[0.7px] text-text-tertiary`}
                >
                  <span>Bot</span>
                  <span>State</span>
                  <span title="What each bot risks on one trade, as a share of the balance. Change one here and Save below — the account's cap is the budget they all come out of.">
                    Risk a trade
                  </span>
                  <span className="text-right">Actions</span>
                </div>
                {group.bots.map((b) => {
                  const st = statusByKey.get(b.key)
                  const running = st === 'RUNNING'
                  const known = st !== undefined
                  const action = pendingKey === b.key ? pendingAction : null
                  const armed = armedKey === b.key
                  const removing = takeOff.isPending && takeOff.variables?.botKey === b.key
                  const share = shareOf(b)
                  const edited = share !== b.risk_pct
                  return (
                    <div
                      key={b.key}
                      data-testid="account-bot"
                      data-bot={b.key}
                      className={`${ROW_GRID} py-[8px] border-t border-border-subtle`}
                    >
                      <button
                        onClick={() => onOpenBot?.(b.key)}
                        disabled={!onOpenBot}
                        title={`Open ${b.display} — its risk, account, version and settings`}
                        className="group flex items-center gap-[8px] min-w-0 text-left"
                      >
                        <StateDot status={st} />
                        <span className="truncate text-[13px] font-medium text-text-primary group-hover:text-accent transition-colors">
                          {b.display}
                        </span>
                        {onOpenBot && (
                          <ChevronRight
                            size={12}
                            className="shrink-0 text-text-tertiary opacity-0 group-hover:opacity-100 transition-opacity"
                          />
                        )}
                      </button>
                      <span className="text-[11.5px] text-text-tertiary">
                        {!known ? 'unknown' : running ? 'Running' : 'Stopped'}
                      </span>
                      {b.unreadable ? (
                        <span className="text-[11px] text-warn-text">config unreadable</span>
                      ) : (
                        <DecimalInput
                          value={share}
                          onChange={(v) => setShare(b, v)}
                          suffix="%"
                          invalid={share == null && edited}
                          placeholder="unset"
                          aria-label={`${b.display} risk per trade`}
                          data-testid={`share-${b.key}`}
                          className="w-[112px]"
                          inputClassName={edited ? 'border-accent/60' : ''}
                        />
                      )}
                      <div className="flex items-center justify-end gap-[6px]">
                        {action ? (
                          <BotActionPill action={action} />
                        ) : running ? (
                          onStop && (
                            <button
                              data-testid={`stop-${b.key}`}
                              onClick={() => onStop(b.key)}
                              disabled={busy}
                              title={`Stop ${b.display}`}
                              aria-label={`Stop ${b.display}`}
                              className="w-[26px] h-[26px] grid place-items-center rounded-md border border-border-default text-text-secondary hover:text-neg-text hover:border-neg/40 transition-colors disabled:opacity-40"
                            >
                              <Square size={10} />
                            </button>
                          )
                        ) : (
                          known &&
                          onStart && (
                            <button
                              data-testid={`start-${b.key}`}
                              onClick={() => onStart(b.key)}
                              disabled={busy}
                              title={`Start ${b.display}`}
                              aria-label={`Start ${b.display}`}
                              className="w-[26px] h-[26px] grid place-items-center rounded-md border border-border-default text-text-secondary hover:text-pos-text hover:border-pos/40 transition-colors disabled:opacity-40"
                            >
                              <Play size={10} />
                            </button>
                          )
                        )}
                        {/* ⚠ Refused while running (it read its account at startup, so the write
                         *  cannot reach the process) and while the box has not answered — the
                         *  same guard as the bot panel's Remove, stated on the control. */}
                        <button
                          data-testid={`take-off-${b.key}`}
                          disabled={running || !known || removing}
                          title={
                            running
                              ? `Stop ${b.display} first — it read its account when it started, so taking it off cannot reach the running process.`
                              : !known
                                ? 'The trading box has not answered for this bot — wait for its state before taking it off.'
                                : armed
                                  ? 'Click again to take it off the account.'
                                  : `Take ${b.display} off account ${account}. It stays registered and stopped until you add it to an account again.`
                          }
                          onClick={() => {
                            if (!armed) {
                              setArmedKey(b.key)
                              return
                            }
                            setArmedKey(null)
                            takeOff.mutate({ botKey: b.key, account: null, display: b.display })
                          }}
                          className={`px-[9px] h-[26px] rounded-md text-[11.5px] border whitespace-nowrap transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
                            armed
                              ? 'border-warn/50 bg-warn-muted text-warn-text'
                              : 'border-border-default text-text-secondary hover:text-text-primary hover:bg-bg-hover'
                          }`}
                        >
                          {removing ? 'Taking off…' : armed ? 'Click again' : 'Take off'}
                        </button>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}

            {/* ⚠ Stays OPEN after an add, so a second bot is one more click — the added bot leaves
             *  the list when the accounts re-read, and joins the rows above. */}
            {adding && account !== null && (
              <div className="mt-3">
                <AddBotPanel
                  account={account}
                  group={group}
                  live={live}
                  pendingKey={join.pendingKey}
                  busy={join.busy}
                  onPick={(pick) =>
                    void join.join({
                      account,
                      botKey: pick.key,
                      display: pick.display,
                      choice: pick.choice,
                      riskCapPct: pick.riskCapPct,
                      live: pick.live,
                    })
                  }
                  onClose={() => setAdding(false)}
                  statusByKey={statusByKey}
                />
              </div>
            )}
          </section>

          {/* ── the ceiling ─────────────────────────────────────────────────── */}
          {/* 🔴 An account with NO bot has no cap and nothing to store one in — the cap lives in
           *  each bot's config, and saving here answered 404. The first bot added carries it. */}
          {account !== null && !hasBots && (
            <section className="py-[16px] border-b border-border-subtle">
              <SectionTitle>Risk budget</SectionTitle>
              <p data-testid="cap-empty" className="text-[12px] text-text-secondary leading-[1.5]">
                None yet — no bot is on this account. The first bot you add sets it.
              </p>
            </section>
          )}
          {account !== null && hasBots && (
            <section className="py-[16px] border-b border-border-subtle">
              <SectionTitle>Risk budget</SectionTitle>
              <div className="flex items-center gap-2 flex-wrap">
                <label className="flex items-center gap-[7px] text-[12.5px] text-text-secondary cursor-pointer">
                  <input
                    type="checkbox"
                    data-testid="cap-enabled"
                    checked={capped}
                    onChange={(e) => setCapped(e.target.checked)}
                  />
                  Cap open risk at
                </label>
                <DecimalInput
                  value={capValue}
                  onChange={setCapValue}
                  suffix="%"
                  invalid={!capValid}
                  disabled={!capped}
                  aria-label="Account risk cap"
                  data-testid="cap-input"
                  className="w-[92px]"
                  inputClassName={capDirty ? 'border-accent/60' : ''}
                />
                <span className="text-[12.5px] text-text-secondary">
                  of the balance, across every bot here
                </span>
              </div>

              <BudgetMeter total={shareTotal} cap={stated} over={!!group.share_overflow_reason} />
              {/* ⚠ Each warning says the fact only when it is TRUE — a warning on every account is
               *  one nobody reads on the day it means something. */}
              <p
                data-testid="cap-shares"
                className="text-[11.5px] text-text-tertiary mt-[8px] leading-[1.5]"
              >
                {shareTotal === null ? (
                  'Their shares cannot be totalled — at least one bot here does not state what it risks per trade.'
                ) : (
                  <>
                    The bots here risk{' '}
                    <span className="text-text-secondary font-medium">{shareTotal}% per trade</span>{' '}
                    between them{stated !== null ? `, against ${stated}%` : ''}.
                  </>
                )}
              </p>

              {/* The save is refused for this reason too, so saying it here makes the refusal
               *  predictable rather than a surprise at the moment you press Save. */}
              {group.share_overflow_reason && (
                <p
                  data-testid="cap-overflow"
                  className="text-[11px] text-warn-text bg-warn-muted border border-warn/40 rounded-md px-[10px] py-[7px] mt-[8px] leading-[1.5]"
                >
                  {group.share_overflow_reason}
                </p>
              )}
              {!hasEdits && p?.reason && (
                <FixButtons plan={p} onCap={applyFitCap} onShares={applyFitShares} />
              )}

              {/* 🔴 The condition that stops every bot here STARTING — and why the cap is blank. */}
              {!group.cap_agrees && (
                <p
                  data-testid="cap-disagreement"
                  className="text-[11px] text-neg-text bg-neg-muted border border-neg/40 rounded-md px-[10px] py-[7px] mt-[8px] leading-[1.5]"
                >
                  The bots on this balance do not state the same ceiling, so none of them will
                  start. Saving here writes one figure to all of them.
                </p>
              )}

              {/* Not a fault — a consequence worth knowing before a quiet week reads as broken. */}
              {group.cap_takes_turns && (
                <p
                  data-testid="cap-takes-turns"
                  className="text-[11px] text-text-tertiary mt-[8px] leading-[1.5]"
                >
                  One full-size trade fills this ceiling, so the bots here take turns — whichever is
                  in first blocks the other until it is out.
                </p>
              )}
            </section>
          )}

          {/* ── the rare things ─────────────────────────────────────────────── */}
          {account !== null && (
            <div className="py-[16px] flex gap-2 flex-wrap">
              {/* 🔴 ONLY ON A DEMO ACCOUNT (2026-09-11, Aaron: *"backtest these bots should only be
               *  on demo accounts"*). Opens the stack builder filled in with what these bots run.
               *  Disabled, never hidden, under two bots — that is not a stack. */}
              {reg?.kind === 'demo' && (
                <button
                  data-testid="backtest-account-bots"
                  disabled={group.bots.length < 2}
                  title={
                    group.bots.length < 2
                      ? 'A stack needs two or more bots on this account.'
                      : "Opens the stack builder on the Backtests page, filled in with what these bots run — their own settings, charts and risk, and this account's cap."
                  }
                  onClick={() => navigate(`/backtests?tab=stacks&account=${account}`)}
                  className={`${actionCls} border-border-default text-text-secondary hover:bg-bg-hover hover:text-text-primary`}
                >
                  <Play size={12} /> Backtest these bots
                </button>
              )}
              {/* 🔴 PRESENT ONLY ON A DEMO ACCOUNT (2026-09-11) — a move to live from a live account
               *  is not an action at all. ⚠ On a demo account a refusal is still stated ON the
               *  control, never hidden: this is the one people come to this page looking for. */}
              {group.bots.length > 0 && reg?.kind === 'demo' && (
                <button
                  data-testid="go-live"
                  disabled={!!goLiveBlock}
                  title={goLiveBlock ?? 'Move every bot on this account onto a live one'}
                  onClick={() => setGoingLive(true)}
                  className={`${actionCls} border-warn/40 bg-warn-muted text-warn-text hover:bg-warn/10`}
                >
                  <Rocket size={12} /> Take live
                </button>
              )}
              {reg && (
                <>
                  <button
                    onClick={() => setEditing(true)}
                    className={`${actionCls} border-border-default text-text-secondary hover:bg-bg-hover hover:text-text-primary`}
                  >
                    <Pencil size={12} /> Edit
                  </button>
                  {/* ⚠ An account a bot still TRADES cannot be unregistered, and the refusal is
                   *  stated on the control rather than after the click. */}
                  <button
                    data-testid={`unregister-${account}`}
                    disabled={group.bots.length > 0 || unregister.isPending}
                    title={
                      group.bots.length > 0
                        ? 'Take its bots off it first'
                        : 'Remove this account from the list'
                    }
                    onClick={() => unregister.mutate(account)}
                    className={`${actionCls} border-neg/40 bg-neg-muted text-neg-text hover:bg-neg/10`}
                  >
                    <Trash2 size={12} /> Delete
                  </button>
                </>
              )}
            </div>
          )}
        </>
      )}
    </Drawer>
  )
}
