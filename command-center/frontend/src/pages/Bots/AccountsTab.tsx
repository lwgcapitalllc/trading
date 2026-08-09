import { useMemo, useState } from 'react'
import { AlertTriangle, Layers, Play, ShieldCheck, ShieldOff } from 'lucide-react'
import { useBotAccounts, useBotSnapshot, useSetAccountRiskCap } from '@/hooks/useBots'
import { useStrategies } from '@/hooks/useLab'
import { StackConfigModal } from '@/components/StackConfigModal'
import type { BotAccountGroup } from '@/types'

/**
 * The shared-account view: which bots trade one balance, and the one ceiling over it.
 *
 * ⚠ **Grouping is READ, not configured.** Two bots naming the same `account` in their instance
 * configs are trading one balance whether or not anybody grouped them, so there is no
 * drag-and-drop and no stored membership. A stored grouping would be a second answer that can
 * disagree with what the bots actually do — this app's most-repeated defect.
 *
 * ⚠ **A written cap is not a running cap.** `account_risk_cap_pct` is read by the order bridge
 * at startup and is NOT runtime-reloadable, so every save says a restart is needed. A cap that
 * is saved and not running is the one state that reads as protected and is not.
 */
export function AccountsTab() {
  const { data: groups, isLoading } = useBotAccounts()
  const { data: snapshot } = useBotSnapshot()

  // Running state comes from the SNAPSHOT, joined on `key`. The accounts endpoint deliberately
  // does not touch the VPS, so it answers while the box is unreachable — and `undefined` here
  // means "not asked", never "stopped".
  const runningByKey = useMemo(() => {
    const m = new Map<string, boolean>()
    for (const b of snapshot?.bots ?? []) m.set(b.key, b.status === 'RUNNING')
    return m
  }, [snapshot])

  if (isLoading) return <div className="text-small text-text-tertiary">Loading accounts…</div>
  if (!groups?.length) return <div className="text-small text-text-tertiary">No bots registered.</div>

  return (
    <div className="flex flex-col gap-4">
      {groups.map(g => (
        <AccountCard key={String(g.account ?? 'unknown')} group={g} runningByKey={runningByKey} />
      ))}
    </div>
  )
}

function AccountCard({ group, runningByKey }: {
  group: BotAccountGroup
  runningByKey: Map<string, boolean>
}) {
  const setCap = useSetAccountRiskCap()
  const { data: strategies } = useStrategies()
  const [showStack, setShowStack] = useState(false)

  // `null` = uncapped, which is a value rather than a blank field — so the input is only shown
  // when the account is capped, and clearing it is an explicit action.
  const [capped, setCapped] = useState(group.risk_cap_pct !== null)
  const [capValue, setCapValue] = useState(group.risk_cap_pct ?? 10)

  const unknownAccount = group.account === null
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

  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden"
         data-testid="account-card">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-border-subtle">
        <div>
          <div className="text-small text-text-primary font-medium">
            {unknownAccount ? 'Unreadable configs' : `Account ${group.account}`}
          </div>
          <div className="text-micro text-text-tertiary">
            {unknownAccount
              ? 'These bots could not be read, so which account they trade is unknown'
              : group.server}
          </div>
        </div>

        {group.stacked && (
          <span
            data-testid="stacked-chip"
            title="More than one bot trades this balance"
            className="flex items-center gap-1 text-micro px-2 py-[3px] rounded bg-accent-muted text-text-primary"
          >
            <Layers size={11} /> Stacked · {group.bots.length}
          </span>
        )}

        {!unknownAccount && (
          <span
            data-testid="cap-chip"
            className={`flex items-center gap-1 text-micro px-2 py-[3px] rounded ${
              !group.cap_agrees ? 'bg-negative-muted text-negative'
                : group.risk_cap_pct === null ? 'bg-bg-hover text-text-tertiary'
                : 'bg-positive-muted text-positive'}`}
          >
            {group.risk_cap_pct === null && group.cap_agrees
              ? <><ShieldOff size={11} /> Uncapped</>
              : group.cap_agrees
                ? <><ShieldCheck size={11} /> Cap {group.risk_cap_pct}%</>
                : <><AlertTriangle size={11} /> Cap disagreement</>}
          </span>
        )}

        {group.stacked && stackStrategyIds.length > 1 && (
          <button
            data-testid="backtest-stack"
            onClick={() => setShowStack(true)}
            className="ml-auto flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small border border-border-default bg-bg-surface text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-colors"
          >
            <Play size={12} /> Backtest this stack
          </button>
        )}
      </div>

      {/* ── The one thing that is genuinely configuration ───────────────────── */}
      {!unknownAccount && (
        <div className="px-4 py-3 border-b border-border-subtle flex flex-col gap-2">
          {!group.cap_agrees && (
            <div data-testid="cap-disagreement"
                 className="text-micro text-negative bg-negative-muted rounded px-2 py-[6px]">
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
            <th className="text-left font-normal px-4 py-[6px]">Bot</th>
            <th className="text-left font-normal px-4 py-[6px]">Symbol</th>
            <th className="text-left font-normal px-4 py-[6px]">Magic</th>
            <th className="text-left font-normal px-4 py-[6px]">Risk / trade</th>
            <th className="text-left font-normal px-4 py-[6px]">Its cap</th>
            <th className="text-left font-normal px-4 py-[6px]">State</th>
          </tr>
        </thead>
        <tbody>
          {group.bots.map(b => {
            const running = runningByKey.get(b.key)
            return (
              <tr key={b.key} className="border-t border-border-subtle text-small">
                <td className="px-4 py-[7px] text-text-primary">{b.display}</td>
                <td className="px-4 py-[7px] text-text-secondary">{b.symbol || '—'}</td>
                <td className="px-4 py-[7px] text-text-secondary">{b.magic || '—'}</td>
                <td className="px-4 py-[7px] text-text-secondary">
                  {b.risk_pct === null ? '—' : `${b.risk_pct}%`}
                </td>
                <td className="px-4 py-[7px] text-text-secondary">
                  {b.unreadable ? 'unknown' : b.cap_pct === null ? 'uncapped' : `${b.cap_pct}%`}
                </td>
                <td className="px-4 py-[7px] text-text-secondary">
                  {/* `undefined` is NOT stopped — the snapshot may not have answered. */}
                  {running === undefined ? '—' : running ? 'Running' : 'Stopped'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>

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
