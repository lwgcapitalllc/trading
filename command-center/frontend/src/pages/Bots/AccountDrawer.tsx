/**
 * One trading account: its money, its ceiling, and the bots spending it.
 *
 * 🔴 **The balance and the cap belong HERE and nowhere else.** They were on every bot row of
 * every tab, which is both the duplication Aaron reported and the reason the fleet total
 * double-counted a stacked account — two bots reporting one balance, added together.
 *
 * ⚠ **The cap is the one number on this page that can take the account down.** Every bot on a
 * balance must state the same one or none of them will start, so the write goes to all of them at
 * once and the drawer says plainly that it lands at each bot's next start rather than now.
 *
 * ⚠ **Editing and deleting the account reuse `AccountForm` and the registry hook** rather than
 * new forms — the registry is what makes a first bot on a new account movable at all.
 */
import { useState } from 'react'
import { Play, Pencil, Trash2, X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useSetAccountRiskCap, useUnregisterAccount } from '@/hooks/useBots'
import type { AccountEarnings, BotAccountGroup, BotAccountRegistration } from '@/types'
import { AccountForm, AddBotRow, nameOf } from './AccountsTab'

export function AccountDrawer({
  group,
  reg,
  balance,
  earnings,
  statusByKey,
  onClose,
}: {
  group: BotAccountGroup
  reg: BotAccountRegistration | undefined
  /** Read off the bots, because the accounts endpoint deliberately never touches the VPS. */
  balance: number | null
  /** What this account has MADE and where it came from — computed server-side.
   *  ⚠ The split between the bots and the remainder is never derived here: the page rendering
   *  its own version of that arithmetic is how one surface starts crediting a bot with money
   *  another surface says it did not make. */
  earnings: AccountEarnings | undefined
  statusByKey: Map<string, string>
  onClose: () => void
}) {
  const navigate = useNavigate()
  const setCap = useSetAccountRiskCap()
  const unregister = useUnregisterAccount()

  const account = group.account
  // ⚠ A disagreement is NOT a cap. Quoting one bot's number when they differ would put a figure
  // on screen that no bot is running and hide the one condition that stops them all starting.
  const stated = group.cap_agrees ? group.risk_cap_pct : null
  const [capped, setCapped] = useState(stated !== null)
  const [draft, setDraft] = useState(stated === null ? '10' : String(stated))
  const [editing, setEditing] = useState(false)
  const [adding, setAdding] = useState(false)

  const next = capped ? parseFloat(draft) : null
  const valid = !capped || (Number.isFinite(next as number) && (next as number) > 0)
  const dirty = valid && next !== stated

  // 🔴 **SERVED, never summed here.** `BotAccountGroup.share_total_pct` carries this exact
  // warning in its own type: a local reduce over the bots' shares is how the browser came to
  // print a total that fitted under the ceiling while the backend refused the save for that
  // very reason. This file had grown its own reduce back — safer than the original (it returns
  // null when any share is unreadable rather than counting it as zero) and still a SECOND
  // answer to a question the server already answers, which is the whole defect shape.
  const shareTotal = group.share_total_pct

  return (
    <>
      <div className="fixed inset-0 bg-black/55 z-40" onClick={onClose} />
      <aside
        aria-label="Account settings"
        className="fixed top-0 right-0 bottom-0 w-[min(620px,100%)] bg-bg-surface border-l border-border-default z-50 overflow-y-auto"
      >
        <div className="flex items-start gap-3 px-5 py-[18px] border-b border-border-subtle">
          <div className="min-w-0">
            <p className="text-[16px] font-semibold leading-tight mb-[3px]">{nameOf(reg, group)}</p>
            <div className="text-[11.5px] text-text-secondary font-mono">
              {account ?? '—'}
              {reg?.server ? ` · ${reg.server}` : ''}
              {reg?.kind ? ` · ${reg.kind}` : ''}
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="ml-auto shrink-0 w-[28px] h-[28px] grid place-items-center rounded-md border border-border-default text-text-tertiary hover:text-text-primary hover:bg-bg-hover transition-colors"
          >
            <X size={13} />
          </button>
        </div>

        <div className="px-5 pb-8">
          {/* ── the money, once ───────────────────────────────────────────── */}
          <div className="py-[16px] border-b border-border-subtle">
            <p className="text-[9px] font-semibold uppercase tracking-[0.8px] text-gold-text mb-[6px]">
              Balance
            </p>
            <p className="text-[22px] font-mono tabular-nums leading-none">
              {balance == null ? (
                <span className="text-[13px] text-text-tertiary">
                  not reported — no bot here is answering
                </span>
              ) : (
                '$' +
                balance.toLocaleString('en-US', {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })
              )}
            </p>
            {/* What it OPENED at, and which bot recorded that — a net with no denominator on
             *  screen is a number nobody can check, and here two bots legitimately state
             *  different anchors because each recorded what was there when it arrived. */}
            {earnings?.net_usd != null && earnings.opening_balance != null ? (
              <p className="text-[11px] text-text-tertiary mt-[7px] leading-[1.55]">
                <span className={earnings.net_usd >= 0 ? 'text-pos-text' : 'text-neg-text'}>
                  {earnings.net_usd >= 0 ? '+' : '−'}$
                  {Math.abs(earnings.net_usd).toLocaleString('en-US', {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })}
                  {earnings.net_pct != null &&
                    ` (${earnings.net_pct > 0 ? '+' : ''}${earnings.net_pct.toFixed(1)}%)`}
                </span>{' '}
                since it opened at $
                {earnings.opening_balance.toLocaleString('en-US', {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
                {earnings.opening_from ? `, recorded by ${earnings.opening_from}` : ''}.
              </p>
            ) : (
              earnings?.opening_note && (
                <p className="text-[11px] text-text-tertiary mt-[7px] leading-[1.55]">
                  {earnings.opening_note}
                </p>
              )
            )}
          </div>

          {/* ── the ceiling ───────────────────────────────────────────────── */}
          {account !== null && (
            <div className="py-[16px] border-b border-border-subtle">
              <p className="text-[9px] font-semibold uppercase tracking-[0.8px] text-gold-text mb-[10px]">
                Risk cap
              </p>
              <div className="flex items-center gap-2 flex-wrap">
                <label className="flex items-center gap-[6px] text-[12px] text-text-secondary cursor-pointer">
                  <input
                    type="checkbox"
                    data-testid="cap-enabled"
                    checked={capped}
                    onChange={(e) => setCapped(e.target.checked)}
                  />
                  Capped
                </label>
                <input
                  type="number"
                  data-testid="cap-input"
                  value={draft}
                  disabled={!capped}
                  onChange={(e) => setDraft(e.target.value)}
                  className="w-[68px] text-[12px] font-mono bg-bg-sunken border border-border-default rounded-md px-2 py-[5px] text-text-primary disabled:opacity-40"
                />
                <span className="text-[12px] text-text-secondary">% of balance</span>
                <button
                  data-testid="cap-save"
                  disabled={!dirty || setCap.isPending}
                  onClick={() => setCap.mutate({ account, riskCapPct: next })}
                  className="ml-auto px-3 py-[5px] rounded-md text-[12px] font-medium bg-accent-muted text-text-primary border border-accent/40 hover:bg-accent/15 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {setCap.isPending ? 'Saving…' : 'Save'}
                </button>
              </div>
              {/* ── what the shares actually add up to ──────────────────────
               *
               * 🔴 **These four warnings were on screen until the tabs were collapsed into this
               * drawer on 2026-09-05, and they went with the tab rather than being moved.** The
               * cap EDITOR came across and the things telling you the number is wrong did not,
               * so the one screen that can over-allocate an account lost every check on it.
               * Found on 2026-09-06 by asking why 44 browser tests were red instead of deleting
               * them — the red WAS the finding, exactly as the tests were written to be.
               *
               * ⚠ **Each says the fact only when it is TRUE.** A healthy account shows one plain
               * sentence; a warning that renders on every account is one nobody reads on the day
               * it means something. */}
              <p
                data-testid="cap-shares"
                className="text-[10px] text-text-tertiary mt-[8px] leading-[1.5]"
              >
                The ceiling on open risk across every bot here.
                {shareTotal === null ? (
                  <>
                    {' '}
                    Their shares cannot be totalled — at least one bot here does not state what it
                    risks per trade.
                  </>
                ) : (
                  <>
                    {' '}
                    They risk {shareTotal}% per trade between them
                    {stated !== null ? `, against ${stated}%` : ''}.
                  </>
                )}{' '}
                Applies at each bot's next start — a running bot does not pick it up.
              </p>

              {/* The save is refused for this reason too, so saying it here is what makes the
               *  refusal predictable rather than a surprise at the moment you press Save. */}
              {group.share_overflow_reason && (
                <p
                  data-testid="cap-overflow"
                  className="text-[10.5px] text-warn-text bg-warn-muted border border-warn/40 rounded-md px-[9px] py-[6px] mt-[8px] leading-[1.5]"
                >
                  {group.share_overflow_reason}
                </p>
              )}

              {/* 🔴 The condition that stops every bot here STARTING. `stated` is already forced
               *  to null above so no figure is quoted — but until now nothing said WHY the field
               *  had gone blank, which hid the fault instead of naming it. */}
              {!group.cap_agrees && (
                <p
                  data-testid="cap-disagreement"
                  className="text-[10.5px] text-neg-text bg-neg-muted border border-neg/40 rounded-md px-[9px] py-[6px] mt-[8px] leading-[1.5]"
                >
                  The bots on this balance do not state the same ceiling, so none of them will
                  start. Saving here writes one figure to all of them.
                </p>
              )}

              {/* Not a fault — a consequence worth knowing before you read a quiet week as a
               *  broken bot. */}
              {group.cap_takes_turns && (
                <p
                  data-testid="cap-takes-turns"
                  className="text-[10px] text-text-tertiary mt-[8px] leading-[1.5]"
                >
                  One full-size trade fills this ceiling, so the bots here take turns — whichever is
                  in first blocks the other until it is out.
                </p>
              )}
            </div>
          )}

          {/* ── who is spending it ────────────────────────────────────────── */}
          <div className="py-[16px] border-b border-border-subtle">
            <div className="flex items-center mb-[10px]">
              <p className="text-[9px] font-semibold uppercase tracking-[0.8px] text-gold-text">
                Bots on this balance · {group.bots.length}
              </p>
              {account !== null && (
                <button
                  onClick={() => setAdding(true)}
                  className="ml-auto text-[11px] text-text-secondary hover:text-text-primary transition-colors"
                >
                  + Add bot
                </button>
              )}
            </div>
            {/* 🔴 Two bots sharing an order tag each read the OTHER's orders as its own —
             *  cancelling them, moving their stops, booking their fills. It went off screen with
             *  the tab on 2026-09-05 and is back because it is the only warning here about two
             *  bots actively corrupting each other's book. Shown only when true. */}
            {group.magic_clash.length > 0 && (
              <div
                data-testid="magic-clash"
                className="text-[10.5px] text-neg-text bg-neg-muted border border-neg/40 rounded-md px-[9px] py-[6px] mb-[10px] leading-[1.5]"
              >
                <strong>{group.magic_clash.join(' and ')}</strong> share an order tag, so each would
                read the other's orders as its own — cancelling them, moving their stops and booking
                their fills. They will refuse to start until one is given a different one.
              </div>
            )}
            {group.bots.length === 0 ? (
              <p className="text-[11px] text-text-tertiary">
                Nothing here yet — this account trades nothing.
              </p>
            ) : (
              <div className="flex flex-col gap-[5px]">
                {group.bots.map((b) => (
                  <div key={b.key} className="flex items-center gap-[8px] text-[12px]">
                    <span
                      className={`inline-block w-[6px] h-[6px] rounded-full shrink-0 ${
                        statusByKey.get(b.key) === 'RUNNING' ? 'bg-pos' : 'bg-neg'
                      }`}
                    />
                    <span className="text-text-primary">{b.display}</span>
                    {typeof b.risk_pct === 'number' && (
                      <span className="ml-auto font-mono text-text-tertiary">{b.risk_pct}%</span>
                    )}
                  </div>
                ))}
              </div>
            )}
            {adding && account !== null && (
              <div className="mt-3 -mx-5">
                <AddBotRow
                  account={account}
                  here={new Set(group.bots.map((b) => b.key))}
                  busy={false}
                  onPick={() => setAdding(false)}
                  onClose={() => setAdding(false)}
                  statusByKey={statusByKey}
                />
              </div>
            )}
          </div>

          {/* ── the rare things ───────────────────────────────────────────── */}
          {account !== null && (
            <div className="py-[16px] flex gap-2 flex-wrap">
              <button
                onClick={() => navigate(`/backtests?stack=${account}`)}
                className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small border border-border-default text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-colors"
              >
                <Play size={12} /> Backtest the stack
              </button>
              {reg && (
                <>
                  <button
                    onClick={() => setEditing(true)}
                    className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small border border-border-default text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-colors"
                  >
                    <Pencil size={12} /> Edit
                  </button>
                  <button
                    disabled={group.bots.length > 0 || unregister.isPending}
                    title={
                      group.bots.length > 0
                        ? 'Take its bots off it first'
                        : 'Remove this account from the list'
                    }
                    onClick={() => unregister.mutate(account)}
                    className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small border border-neg/40 bg-neg-muted text-neg-text hover:bg-neg/10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <Trash2 size={12} /> Delete
                  </button>
                </>
              )}
            </div>
          )}

          {editing && reg && (
            <div className="pt-[6px]">
              <AccountForm existing={reg} onClose={() => setEditing(false)} />
            </div>
          )}
        </div>
      </aside>
    </>
  )
}
