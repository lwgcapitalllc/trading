import { useMemo, useState } from 'react'
import {
  AlertTriangle, KeyRound, Layers, Play, Plus, ShieldCheck, ShieldOff, Trash2, X,
} from 'lucide-react'
import {
  useBotAccounts, useBotSnapshot, useBotVersions, useSetAccountRiskCap, useAssignBotAccount,
  useRegisteredAccounts, useRegisterAccount, useUnregisterAccount, useSetAccountPassword,
} from '@/hooks/useBots'
import { useStrategies } from '@/hooks/useLab'
import { StackConfigModal } from '@/components/StackConfigModal'
import { VersionPill } from '@/components/VersionPill'
import { BotStatusPill } from './BotStatusPill'
import type { BotAccountGroup, BotAccountRegistration, BotDeployedVersion } from '@/types'
import type { UseQueryResult } from '@tanstack/react-query'

/**
 * The shared-account view: which bots trade one balance, and the one ceiling over it.
 *
 * ⚠ **Grouping is READ, not configured.** Two bots naming the same `account` in their instance
 * configs are trading one balance whether or not anybody grouped them, so there is no stored
 * membership. Adding a bot to an account therefore does not create a record — it writes that
 * account into the bot's own config, which is the only thing anything downstream reads. A stored
 * grouping would be a second answer that can disagree with what the bots actually do.
 *
 * ⚠ **A written account is not a running account.** Neither `account` nor `account_risk_cap_pct`
 * is in `live_config.RUNTIME_RELOADABLE`, so both are read at a bot's startup and nowhere else.
 * Every action here says a restart is needed, because a change that is saved and not running is
 * the one state that reads as done and is not.
 *
 * ⚠ **Every colour here is a THEME TOKEN.** Three classes on this page were `bg-negative-muted` /
 * `text-negative` / `bg-positive-muted` until 2026-08-09 — names that exist in no theme, so
 * Tailwind emitted nothing and the cap chip and the disagreement banner rendered with no colour
 * at all. The real ones are `pos-muted`/`pos-text`, `neg-muted`/`neg-text`, `warn-*`
 * (`tailwind.config.js`). A misspelled token does not fail a build; it silently draws nothing.
 */
export function AccountsTab() {
  const { data: groups, isLoading } = useBotAccounts()
  const { data: registry } = useRegisteredAccounts()
  const { data: snapshot } = useBotSnapshot()
  const [addingAccount, setAddingAccount] = useState(false)

  const allKeys = useMemo(
    () => (groups ?? []).flatMap(g => g.bots.map(b => b.key)),
    [groups],
  )
  // Shares `useBotVersion`'s cache entries with the Monitor tab and the Configure banner, so one
  // bot's version is ONE fetch and the three surfaces cannot disagree. See `useBotVersions`.
  const versionQueries = useBotVersions(allKeys)
  const versionByKey = useMemo(
    () => new Map(allKeys.map((k, i) => [k, versionQueries[i]])),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [allKeys.join(','), versionQueries.map(q => q.dataUpdatedAt).join(',')],
  )

  // Running state comes from the SNAPSHOT, joined on `key`. The accounts endpoint deliberately
  // does not touch the VPS, so it answers while the box is unreachable — and `undefined` here
  // means "not asked", never "stopped".
  const statusByKey = useMemo(() => {
    const m = new Map<string, string>()
    for (const b of snapshot?.bots ?? []) m.set(b.key, b.status)
    return m
  }, [snapshot])

  if (isLoading) return <div className="text-small text-text-tertiary">Loading accounts…</div>

  const regByAccount = new Map((registry ?? []).map(a => [a.account, a]))

  // A card per REGISTERED account, whether or not a bot is on it yet — that is the whole point of
  // the registry. An account with no bots renders as an empty card you can add one to; before it
  // existed, the first bot on a new account could not be moved from this page at all.
  const registered = (registry ?? []).map(a => ({
    reg: a,
    group: (groups ?? []).find(g => g.kind === 'account' && g.account === a.account)
      ?? emptyGroup(a),
  }))

  // Accounts a bot names that nobody registered. They still work (the move reads the peers), and
  // they are shown with their gap named rather than hidden — a bot trading an account this page
  // cannot describe is exactly what the registry exists to end.
  const unregistered = (groups ?? [])
    .filter(g => g.kind === 'account' && g.account !== null && !regByAccount.has(g.account))
    .map(g => ({ reg: undefined, group: g }))

  const others = (groups ?? []).filter(g => g.kind !== 'account')
  const cards = [...registered, ...unregistered]
  // Only an ASSIGNABLE account can be a move target. An account with no terminal on the box would
  // be written, committed, pushed and pulled and then fail at connect() with a message about
  // credentials — pointing the reader at the password rather than at the missing terminal.
  const targets = cards.filter(c => !c.reg || c.reg.assignable).map(c => c.group)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <div className="text-micro text-text-tertiary">
          {cards.length === 0
            ? 'No broker accounts yet — add one, then move a bot onto it.'
            : `${cards.length} account${cards.length === 1 ? '' : 's'}`}
        </div>
        <button
          data-testid="add-account"
          onClick={() => setAddingAccount(v => !v)}
          className="ml-auto inline-flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small
                     border border-border-default bg-bg-surface text-text-secondary
                     hover:bg-bg-hover hover:text-text-primary transition-colors"
        >
          <Plus size={12} /> Add account
        </button>
      </div>

      {addingAccount && <AccountForm onClose={() => setAddingAccount(false)} />}

      {cards.map(({ reg, group }) => (
        <AccountCard
          key={`account:${group.account}`}
          group={group}
          registration={reg}
          accounts={targets}
          statusByKey={statusByKey}
          versionByKey={versionByKey}
        />
      ))}

      {others.map(g => (
        <AccountCard
          key={`${g.kind}:none`}
          group={g}
          accounts={targets}
          statusByKey={statusByKey}
          versionByKey={versionByKey}
        />
      ))}
    </div>
  )
}

/**
 * A registered account nobody is trading yet.
 *
 * ⚠ **`cap_agrees: true` with `risk_cap_pct: null` is the honest reading of an empty account** —
 * no bot states a cap, so there is nothing to disagree about and nothing is capped. Writing
 * `cap_agrees: false` here would draw the disagreement banner over an account with no bots on it.
 */
function emptyGroup(a: BotAccountRegistration): BotAccountGroup {
  return {
    account: a.account,
    server: a.server,
    kind: 'account',
    bots: [],
    risk_cap_pct: null,
    cap_agrees: true,
    cap_unknown: false,
    stacked: false,
    cap_takes_turns: false,
    magic_clash: [],
  }
}

function AccountCard({ group, registration, accounts, statusByKey, versionByKey }: {
  group: BotAccountGroup
  /** The registry row, when this account has one. Absent = a legacy account a bot names. */
  registration?: BotAccountRegistration
  accounts: BotAccountGroup[]
  statusByKey: Map<string, string>
  versionByKey: Map<string, UseQueryResult<BotDeployedVersion> | undefined>
}) {
  const setCap = useSetAccountRiskCap()
  const assign = useAssignBotAccount()
  const unregister = useUnregisterAccount()
  const [editing, setEditing] = useState(false)
  const { data: strategies } = useStrategies()
  const [showStack, setShowStack] = useState(false)
  const [adding, setAdding] = useState(false)

  // `null` = uncapped, which is a value rather than a blank field — so the input is only shown
  // when the account is capped, and clearing it is an explicit action.
  const [capped, setCapped] = useState(group.risk_cap_pct !== null)
  const [capValue, setCapValue] = useState(group.risk_cap_pct ?? 10)

  const isAccount = group.kind === 'account'
  const isBench   = group.kind === 'bench'
  const totalRisk = group.bots.reduce((s, b) => s + (b.risk_pct ?? 0), 0)

  // Map each bot's strategy PACKAGE to the lab's own strategy id, so "Backtest this stack"
  // opens preselected. A package with no scanned strategy is simply not preselected — the
  // modal still lists everything, so a missing match costs a click rather than being silent.
  const stackStrategyIds = useMemo(() => {
    const byPackage = new Map<string, string>()
    for (const s of strategies ?? []) {
      if (s.runner !== 'python') continue
      const pkg = (s.source_path || '').split('/').filter(Boolean).pop()
      if (pkg) byPackage.set(pkg, s.id)
    }
    return group.bots
      .map(b => byPackage.get(b.strategy_package))
      .filter((x): x is string => !!x)
  }, [strategies, group.bots])

  const save = (value: number | null) => {
    if (group.account === null) return
    setCap.mutate({ account: group.account, riskCapPct: value })
  }

  const heading = isAccount
    ? (registration?.label || `Account ${group.account}`)
    : isBench ? 'Not on an account'
    : 'Unreadable configs'
  const subheading = isAccount
    ? [registration && `#${group.account}`, group.server || registration?.server,
       registration?.symbol_suffix ? `symbol${registration.symbol_suffix}` : null]
        .filter(Boolean).join(' · ')
    : isBench ? 'Registered and deliberately not trading — add one to an account to arm it'
    : 'These configs could not be read, so which account they trade is unknown'

  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden"
         data-testid="account-card" data-kind={group.kind}>
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-border-subtle flex-wrap">
        <div>
          <div className="text-small text-text-primary font-medium">{heading}</div>
          <div className="text-micro text-text-tertiary">{subheading}</div>
        </div>

        {group.stacked && (
          <span
            data-testid="stacked-chip"
            title="More than one bot trades this balance"
            className="inline-flex items-center gap-[3px] text-[10px] font-semibold px-2 py-[3px]
                       rounded-pill uppercase tracking-[0.4px] bg-accent-muted text-text-primary
                       cursor-default"
          >
            <Layers size={9} /> Stacked · {group.bots.length}
          </span>
        )}

        {registration?.kind === 'live' && (
          <span data-testid="live-chip"
                title="A LIVE account. Every action on this card moves real money."
                className="inline-flex items-center gap-[3px] text-[10px] font-semibold px-2 py-[3px]
                           rounded-pill uppercase tracking-[0.4px] bg-warn-muted text-warn-text
                           cursor-default">
            Live
          </span>
        )}

        {registration?.tier && (
          <span className="text-micro text-text-tertiary">{registration.tier}</span>
        )}

        {/* ⚠ THREE states, and the third is the one that matters: `null` means the VPS could not
            be asked, which is not the same as "no password". Rendering it as missing sends the
            reader to re-enter a credential that is already there. */}
        {registration && (
          <span
            data-testid="password-chip"
            title={registration.has_password === null
              ? 'The VPS could not be asked, so whether a password is stored here is unknown.'
              : registration.has_password
                ? 'An MT5 password is stored for this account on the VPS.'
                : 'No MT5 password is stored, so a bot moved here could not log in.'}
            className={`inline-flex items-center gap-[3px] text-[10px] font-semibold px-2 py-[3px]
                        rounded-pill uppercase tracking-[0.4px] cursor-default ${
              registration.has_password === null ? 'bg-bg-surface-2 text-text-tertiary'
                : registration.has_password ? 'bg-pos-muted text-pos-text'
                : 'bg-warn-muted text-warn-text'}`}
          >
            <KeyRound size={9} />
            {registration.has_password === null ? 'Password unknown'
              : registration.has_password ? 'Password set' : 'No password'}
          </span>
        )}

        {registration && !registration.assignable && (
          <span data-testid="no-terminal"
                title={registration.unassignable_reason}
                className="inline-flex items-center gap-[3px] text-[10px] font-semibold px-2 py-[3px]
                           rounded-pill uppercase tracking-[0.4px] bg-warn-muted text-warn-text
                           cursor-default">
            <AlertTriangle size={9} /> No terminal
          </span>
        )}

        {isAccount && !registration && (
          <span data-testid="unregistered"
                title="No bot can be moved onto this account from here until it is registered — its
                       server, terminal, symbol suffix and cost profile are only known to the bots
                       already on it."
                className="inline-flex items-center gap-[3px] text-[10px] font-semibold px-2 py-[3px]
                           rounded-pill uppercase tracking-[0.4px] bg-bg-surface-2 text-text-tertiary
                           cursor-default">
            Not registered
          </span>
        )}

        {isAccount && (
          <span
            data-testid="cap-chip"
            className={`inline-flex items-center gap-[3px] text-[10px] font-semibold px-2 py-[3px]
                        rounded-pill uppercase tracking-[0.4px] cursor-default ${
              !group.cap_agrees ? 'bg-neg-muted text-neg-text'
                : group.risk_cap_pct === null ? 'bg-bg-surface-2 text-text-tertiary'
                : 'bg-pos-muted text-pos-text'}`}
          >
            {group.risk_cap_pct === null && group.cap_agrees
              ? <><ShieldOff size={9} /> Uncapped</>
              : group.cap_agrees
                ? <><ShieldCheck size={9} /> Cap {group.risk_cap_pct}%</>
                : <><AlertTriangle size={9} /> Cap disagreement</>}
          </span>
        )}

        <div className="ml-auto flex items-center gap-2">
          {registration && (
            <button
              data-testid={`edit-account-${registration.account}`}
              onClick={() => setEditing(v => !v)}
              className="inline-flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small
                         border border-border-default bg-bg-surface text-text-secondary
                         hover:bg-bg-hover hover:text-text-primary transition-colors"
            >
              Edit
            </button>
          )}
          {/* Refused server-side while a bot names the account; disabled here so the reason is
              readable before the click rather than as a 409 afterwards. */}
          {registration && (
            <button
              data-testid={`unregister-${registration.account}`}
              disabled={group.bots.length > 0 || unregister.isPending}
              title={group.bots.length > 0
                ? 'Move or bench the bots on this account first — removing it would leave them on '
                  + 'an account this page can no longer describe.'
                : 'Forget this account. It does not touch the stored password.'}
              onClick={() => unregister.mutate(registration.account)}
              className="inline-flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small
                         border border-border-default bg-bg-surface text-text-tertiary
                         hover:text-neg-text hover:bg-neg-muted transition-colors
                         disabled:opacity-30 disabled:cursor-not-allowed
                         disabled:hover:bg-bg-surface disabled:hover:text-text-tertiary"
            >
              <Trash2 size={12} />
            </button>
          )}
          {isAccount && (
            <button
              data-testid="add-bot"
              disabled={registration ? !registration.assignable : false}
              title={registration && !registration.assignable
                ? registration.unassignable_reason : undefined}
              onClick={() => setAdding(true)}
              className="inline-flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small
                         border border-border-default bg-bg-surface text-text-secondary
                         hover:bg-bg-hover hover:text-text-primary transition-colors
                         disabled:opacity-30 disabled:cursor-not-allowed
                         disabled:hover:bg-bg-surface disabled:hover:text-text-secondary"
            >
              <Plus size={12} /> Add bot
            </button>
          )}
          {group.stacked && stackStrategyIds.length > 1 && (
            <button
              data-testid="backtest-stack"
              onClick={() => setShowStack(true)}
              className="inline-flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small
                         border border-border-default bg-bg-surface text-text-secondary
                         hover:bg-bg-hover hover:text-text-primary transition-colors"
            >
              <Play size={12} /> Backtest this stack
            </button>
          )}
        </div>
      </div>

      {/* ── The one thing that is genuinely configuration ───────────────────── */}
      {isAccount && (
        <div className="px-4 py-3 border-b border-border-subtle flex flex-col gap-2">
          {group.magic_clash.length > 0 && (
            /* The fact the old raw `magic` column was trying to convey, shown only when it is
               true. Two bots on one account sharing an order tag each read the OTHER's orders as
               their own — cancelling them, moving their stops, booking their fills. */
            <div data-testid="magic-clash"
                 className="text-micro text-neg-text bg-neg-muted rounded px-2 py-[6px]">
              <strong>{group.magic_clash.join(' and ')}</strong> share an order tag, so each would
              read the other's orders as its own — cancelling them, moving their stops and booking
              their fills. They will refuse to start until one is given a different one.
            </div>
          )}

          {!group.cap_agrees && (
            <div data-testid="cap-disagreement"
                 className="text-micro text-neg-text bg-neg-muted rounded px-2 py-[6px]">
              These bots state different account caps, so the account's real ceiling is whichever
              bot asks — and a bot with no cap fills the balance while a capped one is refused.
              Saving below writes the same value to all of them. A bot will refuse to START in
              this state, which is deliberate.
            </div>
          )}

          {group.cap_unknown && (
            <div className="text-micro text-text-tertiary">
              One config could not be read, so this account's cap cannot be confirmed — and it
              cannot be changed until that is fixed.
            </div>
          )}

          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-micro text-text-secondary">Account risk cap</span>

            <label className="flex items-center gap-[6px] text-micro text-text-secondary cursor-pointer">
              <input
                type="checkbox"
                data-testid="cap-enabled"
                checked={capped}
                onChange={e => setCapped(e.target.checked)}
              />
              Capped
            </label>

            {capped && (
              <div className="flex items-center gap-1">
                <input
                  type="number"
                  data-testid="cap-input"
                  min={0.1}
                  max={100}
                  step={0.5}
                  value={capValue}
                  onChange={e => setCapValue(Number(e.target.value))}
                  className="w-[70px] bg-bg-base border border-border-default rounded px-2 py-[4px] text-small text-text-primary"
                />
                <span className="text-micro text-text-tertiary">% of live balance</span>
              </div>
            )}

            <button
              data-testid="cap-save"
              disabled={setCap.isPending || group.cap_unknown}
              onClick={() => save(capped ? capValue : null)}
              className="px-3 py-[5px] rounded-md text-small bg-accent-muted text-text-primary hover:brightness-110 transition disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {setCap.isPending ? 'Saving…' : 'Save cap'}
            </button>

            <span className="text-micro text-text-tertiary">
              Applies at each bot's next start — it is not picked up by a running bot.
            </span>
          </div>

          {/* Not a warning: a fact the two numbers imply and neither states on its own. */}
          {group.cap_takes_turns && (
            <div data-testid="cap-takes-turns" className="text-micro text-text-tertiary">
              At {group.risk_cap_pct}% these bots take turns rather than share — one full-size
              position or resting order fills the whole budget and the other is refused until its
              stop moves. Together they risk {totalRisk}% per trade, so a cap above that lets both
              hold at once.
            </div>
          )}
        </div>
      )}

      {editing && registration && (
        <AccountForm existing={registration} onClose={() => setEditing(false)} />
      )}

      {/* ── The bots on this balance ────────────────────────────────────────── */}
      {isAccount && group.bots.length === 0 ? (
        <div data-testid="no-bots" className="px-4 py-3 text-micro text-text-tertiary">
          No bot trades this account yet.{' '}
          {registration?.assignable === false
            ? 'Log a terminal into it and record that terminal on the account first.'
            : 'Use Add bot above to put one on it.'}
        </div>
      ) : (
      <table className="w-full border-collapse">
        <thead>
          <tr className="text-micro text-text-tertiary">
            {['Bot', 'Symbol', 'Version', 'Risk / trade', 'Its cap', 'State', ''].map(h => (
              <th key={h} className="text-left font-normal px-4 py-[6px]">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {group.bots.map(b => {
            const status = statusByKey.get(b.key)
            const q = versionByKey.get(b.key)
            const running = status === 'RUNNING'
            return (
              <tr key={b.key} className="border-t border-border-subtle text-small">
                <td className="px-4 py-[7px] text-text-primary">{b.display}</td>
                <td className="px-4 py-[7px] text-text-secondary">{b.symbol || '—'}</td>
                <td className="px-4 py-[7px]">
                  <VersionPill version={q?.data} loading={q?.isPending} />
                </td>
                <td className="px-4 py-[7px] text-text-secondary">
                  {b.risk_pct === null ? '—' : `${b.risk_pct}%`}
                </td>
                <td className="px-4 py-[7px] text-text-secondary">
                  {b.unreadable ? 'unknown' : b.cap_pct === null ? 'uncapped' : `${b.cap_pct}%`}
                </td>
                <td className="px-4 py-[7px] text-text-secondary">
                  {/* `undefined` is NOT stopped — the snapshot may not have answered. */}
                  {status === undefined
                    ? <span className="text-text-tertiary">—</span>
                    : <BotStatusPill status={status} />}
                </td>
                <td className="px-4 py-[7px] text-right">
                  {isAccount && !b.unreadable && (
                    <button
                      data-testid={`remove-${b.key}`}
                      disabled={assign.isPending || running}
                      title={running
                        ? 'Stop this bot first — it read its account at startup, so moving it '
                          + 'now would leave the page showing one account while it traded another.'
                        : `Take ${b.display} off account ${group.account}. It will not start `
                          + 'again until it is on an account.'}
                      onClick={() => assign.mutate({ botKey: b.key, account: null })}
                      className="inline-flex items-center gap-[4px] px-2 py-[3px] rounded text-micro
                                 text-text-tertiary hover:text-neg-text hover:bg-neg-muted
                                 transition-colors disabled:opacity-30
                                 disabled:cursor-not-allowed disabled:hover:bg-transparent
                                 disabled:hover:text-text-tertiary"
                    >
                      <X size={10} /> Remove
                    </button>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      )}

      {adding && group.account !== null && (
        <AddBotRow
          account={group.account}
          accounts={accounts}
          busy={assign.isPending}
          onPick={key => {
            assign.mutate({ botKey: key, account: group.account }, {
              onSuccess: () => setAdding(false),
            })
          }}
          onClose={() => setAdding(false)}
          statusByKey={statusByKey}
        />
      )}

      {showStack && (
        <StackConfigModal
          title={`Backtest account ${group.account} as a shared stack`}
          submitLabel="Run shared stack"
          initial={{
            strategyIds: stackStrategyIds,
            mode: 'shared',
            riskCapPct: group.risk_cap_pct ?? undefined,
          }}
          onClose={() => setShowStack(false)}
        />
      )}
    </div>
  )
}

/**
 * Pick a bot to put on this account.
 *
 * ⚠ **The candidates are every registered bot NOT already here**, benched or on another account,
 * because moving a bot between accounts is the same write as adding one from the bench. A running
 * bot is listed and DISABLED rather than hidden: *it is not here* and *it cannot be moved right
 * now* are different answers, and hiding it makes a bot that exists look like one that does not.
 *
 * ⚠ **Nothing to add is a real answer and says what to do about it.** With one bot registered
 * this list is empty, and an empty dropdown with no explanation reads as a broken control — the
 * shape this repo keeps recording as a feature nobody has driven end to end.
 */
function AddBotRow({ account, accounts, busy, onPick, onClose, statusByKey }: {
  account: number
  accounts: BotAccountGroup[]
  busy: boolean
  onPick: (key: string) => void
  onClose: () => void
  statusByKey: Map<string, string>
}) {
  const { data: groups } = useBotAccounts()
  const here = new Set(
    accounts.find(g => g.account === account)?.bots.map(b => b.key) ?? [])

  const candidates = (groups ?? [])
    .flatMap(g => g.bots.map(b => ({ ...b, from: g })))
    .filter(b => !here.has(b.key) && !b.unreadable)

  return (
    <div data-testid="add-bot-row"
         className="px-4 py-3 border-t border-border-subtle bg-bg-surface-2 flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span className="text-micro text-text-secondary">
          Add a bot to account {account}
        </span>
        <button onClick={onClose}
                className="ml-auto text-text-tertiary hover:text-text-primary">
          <X size={12} />
        </button>
      </div>

      {candidates.length === 0 ? (
        <div data-testid="no-candidates" className="text-micro text-text-tertiary">
          Every registered bot is already on this account. A new one needs its instance created
          in the repo first — that is a code change, not something this page can do.
        </div>
      ) : (
        <div className="flex flex-col gap-1">
          {candidates.map(b => {
            const running = statusByKey.get(b.key) === 'RUNNING'
            return (
              <button
                key={b.key}
                data-testid={`add-${b.key}`}
                disabled={busy || running}
                title={running
                  ? 'This bot is running. Stop it before moving it — it read its account at '
                    + 'startup, so the move could not reach the live process.'
                  : undefined}
                onClick={() => onPick(b.key)}
                className="flex items-center gap-2 px-2 py-[6px] rounded text-small text-left
                           text-text-secondary hover:bg-bg-hover hover:text-text-primary
                           transition-colors disabled:opacity-40 disabled:cursor-not-allowed
                           disabled:hover:bg-transparent"
              >
                <span className="text-text-primary">{b.display}</span>
                <span className="text-micro text-text-tertiary">{b.symbol}</span>
                <span className="ml-auto text-micro text-text-tertiary">
                  {b.from.kind === 'bench'
                    ? 'not on an account'
                    : `moves off account ${b.from.account}`}
                </span>
                {running && <BotStatusPill status="RUNNING" />}
              </button>
            )
          })}
        </div>
      )}

      <div className="text-micro text-text-tertiary">
        Adding a bot writes this account's login, server, terminal and risk cap into its config,
        so the account stays coherent. It applies at that bot's next start.
      </div>
    </div>
  )
}

/**
 * Add a broker account, or edit the registered facts about one.
 *
 * 🔴 **This form is the thing that was missing on 2026-08-12.** Every field on it had to be
 * hand-edited into an instance config on the VPS to move the live bot from the Standard demo to
 * the ECN one — and the field that was FORGOTTEN in that edit is the symbol suffix, which is why
 * it is on here with its own explanation rather than buried in an advanced section.
 *
 * ⚠ **There is no risk cap here and there must not be one.** The cap is stored per instance
 * because a bot reads only its own config, so it is set on the card above (one write, N files) and
 * reported from what the bots actually say. A field here would be a second answer that can drift.
 *
 * ⚠ **The password is WRITE-ONLY.** It is never returned by any endpoint, so an existing account
 * shows whether one is stored and not what it is — the field is blank on an edit and leaving it
 * blank changes nothing. It travels to the git-ignored credentials file on the VPS, never into
 * the git-tracked registry.
 */
function AccountForm({ existing, onClose }: {
  existing?: BotAccountRegistration
  onClose: () => void
}) {
  const save = useRegisterAccount()
  const setPassword = useSetAccountPassword()

  const [account, setAccount] = useState(existing ? String(existing.account) : '')
  const [label, setLabel] = useState(existing?.label ?? '')
  const [broker, setBroker] = useState(existing?.broker ?? '')
  const [tier, setTier] = useState(existing?.tier ?? '')
  const [kind, setKind] = useState(existing?.kind ?? 'demo')
  const [server, setServer] = useState(existing?.server ?? '')
  const [mt5Path, setMt5Path] = useState(existing?.mt5_path ?? '')
  // `null` is a real, distinct value here — "nobody recorded it" — so the control is a checkbox
  // plus a text field rather than an empty string, which would mean "this broker quotes bare
  // symbols" and silently strip the suffix off a live instrument.
  const [hasSuffix, setHasSuffix] = useState(existing ? existing.symbol_suffix !== null : true)
  const [suffix, setSuffix] = useState(existing?.symbol_suffix ?? '')
  const [profile, setProfile] = useState(existing?.account_profile ?? '')
  const [password, setPwd] = useState('')

  const num = Number(account)
  const valid = Number.isFinite(num) && num > 0 && server.trim().length > 0

  const submit = () => {
    if (!valid) return
    save.mutate({
      account: num, label, broker, tier, kind, server, mt5_path: mt5Path,
      symbol_suffix: hasSuffix ? suffix : null,
      account_profile: profile, note: existing?.note ?? '',
      // Sent on the SAME request when there is one, so the credential lands before the registry
      // row is committed and pushed — a registered account with no password is a visible, fixable
      // state, while a pushed row whose password write failed afterwards reads as complete.
      password: password || undefined,
      deploy: true,
    }, { onSuccess: () => { setPwd(''); onClose() } })
  }

  return (
    <div data-testid="account-form"
         className="bg-bg-surface border border-border-subtle rounded-lg p-4 flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <div className="text-small text-text-primary font-medium">
          {existing ? `Edit account ${existing.account}` : 'Add a broker account'}
        </div>
        <button onClick={onClose} className="ml-auto text-text-tertiary hover:text-text-primary">
          <X size={12} />
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 max-w-[720px]">
        <Field label="Account number" hint="The MT5 login.">
          <input type="number" data-testid="f-account" value={account} disabled={!!existing}
                 onChange={e => setAccount(e.target.value)} className={inputCls} />
        </Field>
        <Field label="Server" hint="An account number IS a login on a server — the pair is the identity.">
          <input data-testid="f-server" value={server} placeholder="PUPrime-Demo"
                 onChange={e => setServer(e.target.value)} className={inputCls} />
        </Field>
        <Field label="Name" hint="What this card is called. Display only.">
          <input data-testid="f-label" value={label} placeholder="PU Prime ECN demo"
                 onChange={e => setLabel(e.target.value)} className={inputCls} />
        </Field>
        <Field label="Broker" hint="Display only.">
          <input value={broker} placeholder="PU Prime"
                 onChange={e => setBroker(e.target.value)} className={inputCls} />
        </Field>
        <Field label="Tier" hint="The broker's own word for it. Display only.">
          <input value={tier} placeholder="ECN"
                 onChange={e => setTier(e.target.value)} className={inputCls} />
        </Field>
        <Field label="Demo or live"
               hint="A live account is tinted and warned on before every fleet action.">
          <select data-testid="f-kind" value={kind}
                  onChange={e => setKind(e.target.value)} className={inputCls}>
            <option value="demo">demo</option>
            <option value="live">live</option>
          </select>
        </Field>
        <Field label="Terminal path"
               hint="The terminal on the VPS logged into this account. Leave blank and no bot can be assigned — a move would be written, pushed, and then fail at connect time.">
          <input data-testid="f-path" value={mt5Path} placeholder="C:\\MT5_FFT\\terminal64.exe"
                 onChange={e => setMt5Path(e.target.value)} className={inputCls} />
        </Field>
        <Field label="Cost profile"
               hint="Which measured cost model prices this account, e.g. puprime_ecn. Refused if it names no known profile.">
          <input data-testid="f-profile" value={profile} placeholder="puprime_ecn"
                 onChange={e => setProfile(e.target.value)} className={inputCls} />
        </Field>
      </div>

      {/* The field the 2026-08-12 move forgot. It gets its own block and its own sentence. */}
      <div className="flex flex-col gap-1 border-t border-border-subtle pt-3">
        <label className="flex items-center gap-[6px] text-micro text-text-secondary cursor-pointer">
          <input type="checkbox" data-testid="f-has-suffix" checked={hasSuffix}
                 onChange={e => setHasSuffix(e.target.checked)} />
          This account puts a suffix on its symbols
        </label>
        {hasSuffix && (
          <input data-testid="f-suffix" value={suffix} placeholder=".p"
                 onChange={e => setSuffix(e.target.value)}
                 className={`${inputCls} max-w-[120px]`} />
        )}
        <div className="text-micro text-text-tertiary max-w-[720px]">
          Moving a bot here keeps its instrument and swaps the suffix — <span className="font-mono">
          XAUUSD.s</span> becomes <span className="font-mono">XAUUSD{suffix || '.p'}</span>. Unticked
          means this broker quotes bare symbols. Leave it unticked only if that is true: a bot
          pointed at a symbol its terminal does not quote connects, warms up and receives no bars,
          which looks exactly like a quiet market.
        </div>
      </div>

      <div className="flex flex-col gap-1 border-t border-border-subtle pt-3">
        <Field label="MT5 password"
               hint="Stored on the VPS in a git-ignored file and never shown again. Leave blank to keep the current one.">
          <input type="password" data-testid="f-password" value={password} autoComplete="new-password"
                 placeholder={existing?.has_password ? '•••••••• (unchanged)' : ''}
                 onChange={e => setPwd(e.target.value)}
                 className={`${inputCls} max-w-[260px]`} />
        </Field>
        {existing && password && (
          <button
            data-testid="save-password"
            disabled={setPassword.isPending}
            onClick={() => setPassword.mutate({ account: existing.account, password },
                                              { onSuccess: () => setPwd('') })}
            className="self-start px-3 py-[5px] rounded-md text-small bg-accent-muted
                       text-text-primary hover:brightness-110 transition disabled:opacity-40"
          >
            {setPassword.isPending ? 'Saving…' : 'Save password only'}
          </button>
        )}
      </div>

      <div className="flex items-center gap-2">
        <button
          data-testid="save-account"
          disabled={!valid || save.isPending}
          onClick={submit}
          className="px-3 py-[5px] rounded-md text-small bg-accent-muted text-text-primary
                     hover:brightness-110 transition disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {save.isPending ? 'Saving…' : existing ? 'Save account' : 'Add account'}
        </button>
        <span className="text-micro text-text-tertiary">
          Committed, pushed and pulled onto the VPS. No secret goes into the repo.
        </span>
      </div>
    </div>
  )
}

const inputCls = 'w-full bg-bg-base border border-border-default rounded px-2 py-[5px] '
  + 'text-small text-text-primary'

function Field({ label, hint, children }: {
  label: string; hint: string; children: React.ReactNode
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-micro text-text-secondary">{label}</span>
      {children}
      <span className="text-micro text-text-tertiary leading-[1.35]">{hint}</span>
    </label>
  )
}
