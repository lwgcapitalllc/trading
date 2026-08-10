import { useMemo, useState } from 'react'
import { AlertTriangle, Layers, Play, Plus, ShieldCheck, ShieldOff, X } from 'lucide-react'
import {
  useBotAccounts, useBotSnapshot, useBotVersions, useSetAccountRiskCap, useAssignBotAccount,
} from '@/hooks/useBots'
import { useStrategies } from '@/hooks/useLab'
import { StackConfigModal } from '@/components/StackConfigModal'
import { VersionPill } from '@/components/VersionPill'
import { BotStatusPill } from './BotStatusPill'
import type { BotAccountGroup, BotDeployedVersion } from '@/types'
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
  const { data: snapshot } = useBotSnapshot()

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
  if (!groups?.length) return <div className="text-small text-text-tertiary">No bots registered.</div>

  // Only a real account can be joined: its server, terminal and risk cap are read off the bots
  // already there, so there is nothing for a first bot to adopt.
  const accounts = groups.filter(g => g.kind === 'account')

  return (
    <div className="flex flex-col gap-4">
      {groups.map(g => (
        <AccountCard
          key={`${g.kind}:${g.account ?? 'none'}`}
          group={g}
          accounts={accounts}
          statusByKey={statusByKey}
          versionByKey={versionByKey}
        />
      ))}
    </div>
  )
}

function AccountCard({ group, accounts, statusByKey, versionByKey }: {
  group: BotAccountGroup
  accounts: BotAccountGroup[]
  statusByKey: Map<string, string>
  versionByKey: Map<string, UseQueryResult<BotDeployedVersion> | undefined>
}) {
  const setCap = useSetAccountRiskCap()
  const assign = useAssignBotAccount()
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

  const heading = isAccount ? `Account ${group.account}`
    : isBench ? 'Not on an account'
    : 'Unreadable configs'
  const subheading = isAccount ? group.server
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
          {isAccount && (
            <button
              data-testid="add-bot"
              onClick={() => setAdding(true)}
              className="inline-flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small
                         border border-border-default bg-bg-surface text-text-secondary
                         hover:bg-bg-hover hover:text-text-primary transition-colors"
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

      {/* ── The bots on this balance ────────────────────────────────────────── */}
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
