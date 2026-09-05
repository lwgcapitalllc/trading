/**
 * One bot, and only what you can do to it.
 *
 * 🔴 **This replaces a full-page panel that showed a version banner, a risk editor printing a
 * 1,500-word note out of the instance config, an account card, a deploy card and all 116 strategy
 * parameters — at once.** Aaron, 2026-09-05: *"too much information, too much duplication … even
 * the section that says risk per trade, what is all of that information? Why do I care?"*
 *
 * **Four things you act on, then a fold:** start/stop/logs, risk per trade, version, account.
 * Everything you only ever READ — the symbol, the timeframe, the trade id, the code hash, the
 * 116 parameters, and the config's own prose about why the risk is what it is — sits under
 * Details.
 *
 * ⚠ **The money-path controls are the SAME components as before, not new ones.** `VersionBanner`
 * carries promote (with its preview and its confirm) and `RuntimeEditor` carries the risk change
 * (with its confirm). Rewriting either to make a drawer prettier would put a fresh implementation
 * on the path that deploys code to a live account. Only the NOTE is suppressed, and only here.
 *
 * ⚠ **Nothing is deleted, it is folded.** The parameter list is how you check the bot is the bot
 * that was backtested, and the risk note is the measured reasoning behind a live number.
 */
import { Play, Square, RotateCcw, FileText, X } from 'lucide-react'
import { useBotParams, useAssignBotAccount, useBotAccounts } from '@/hooks/useBots'
import type { BotParamRow, BotParamsView, BotStatus } from '@/types'
import { VersionBanner, RuntimeEditor, ParamGroup } from './ConfigureTab'

function Fold({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <details className="border-t border-border-subtle pt-[14px] mt-[14px]">
      <summary className="cursor-pointer text-[11px] text-text-tertiary hover:text-text-secondary select-none list-none marker:hidden">
        {label}
      </summary>
      <div className="mt-[12px]">{children}</div>
    </details>
  )
}

function Facts({ rows }: { rows: [string, React.ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-[6px] text-[11px]">
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

export function BotDrawer({
  bot,
  onClose,
  onLogs,
  onStart,
  onStop,
  onRestart,
  busy,
}: {
  bot: BotStatus
  onClose: () => void
  onLogs: () => void
  onStart: () => void
  onStop: () => void
  onRestart: () => void
  busy: boolean
}) {
  const { data, isLoading, error } = useBotParams(bot.key)
  const { data: groups } = useBotAccounts()
  const assign = useAssignBotAccount()

  const running = bot.status === 'RUNNING'
  const v = data as BotParamsView | undefined

  // Every account a bot can be moved to, read off the same grouping the rest of the page uses.
  const accounts = (groups ?? [])
    .filter((g) => g.kind === 'account' && g.account !== null)
    .map((g) => g.account as number)

  const strategyGroups = (v?.strategy ?? []).reduce<Record<string, BotParamRow[]>>((acc, r) => {
    ;(acc[r.group] ??= []).push(r)
    return acc
  }, {})

  const terminal = (v?.identity.mt5_path ?? '').split('\\').filter(Boolean)[0] ?? '—'

  return (
    <>
      <div className="fixed inset-0 bg-black/55 z-40" onClick={onClose} />
      <aside
        aria-label={`${bot.name} settings`}
        className="fixed top-0 right-0 bottom-0 w-[min(440px,100%)] bg-bg-surface border-l border-border-default z-50 overflow-y-auto"
      >
        {/* ── who ─────────────────────────────────────────────────────────── */}
        <div className="flex items-start gap-3 px-5 py-[18px] border-b border-border-subtle">
          <div className="min-w-0">
            <p className="text-[16px] font-semibold leading-tight mb-[3px]">{bot.name}</p>
            <div className="flex items-center gap-[7px] text-[11.5px] text-text-secondary">
              <span
                className={`inline-block w-[6px] h-[6px] rounded-full shrink-0 ${
                  running ? 'bg-pos shadow-[0_0_6px_#00ff7f]' : 'bg-neg'
                }`}
              />
              {running ? 'Running' : 'Stopped'}
              {bot.account && (
                <>
                  <span className="text-text-tertiary">·</span>
                  <span className="font-mono">{bot.account}</span>
                </>
              )}
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
          {/* ── do ────────────────────────────────────────────────────────── */}
          <div className="flex gap-2 py-[14px] border-b border-border-subtle">
            {running ? (
              <>
                <button
                  onClick={onStop}
                  disabled={busy}
                  className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small border border-neg/40 bg-neg-muted text-neg-text hover:bg-neg/10 transition-colors disabled:opacity-40"
                >
                  <Square size={12} /> Stop
                </button>
                <button
                  onClick={onRestart}
                  disabled={busy}
                  className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small border border-border-default text-text-primary hover:bg-bg-hover transition-colors disabled:opacity-40"
                >
                  <RotateCcw size={12} /> Restart
                </button>
              </>
            ) : (
              <button
                onClick={onStart}
                disabled={busy || !bot.account}
                title={bot.account ? 'Start this bot' : 'Put it on an account first'}
                className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small border border-border-default text-text-primary hover:bg-bg-hover hover:border-pos/40 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Play size={12} className="text-pos" /> Start
              </button>
            )}
            <button
              onClick={onLogs}
              className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small border border-border-default text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-colors ml-auto"
            >
              <FileText size={12} /> Logs
            </button>
          </div>

          {isLoading && <p className="text-[11px] text-text-tertiary py-4">Loading…</p>}
          {error && (
            <p className="text-[11px] text-neg-text py-4">
              Could not read this bot's configuration: {String(error)}
            </p>
          )}

          {v && (
            <>
              {/* ── risk ──────────────────────────────────────────────────── */}
              <div className="py-[16px] border-b border-border-subtle">
                <p className="text-[9px] font-semibold uppercase tracking-[0.8px] text-gold-text mb-[10px]">
                  Risk per trade
                </p>
                {v.runtime.length === 0 ? (
                  <p className="text-[11px] text-text-tertiary">
                    Nothing here can be changed while it runs.
                  </p>
                ) : (
                  v.runtime.map((r) => (
                    <RuntimeEditor
                      key={r.name}
                      botKey={bot.key}
                      botLabel={bot.name}
                      row={r}
                      balance={bot.balance}
                      hideNote
                    />
                  ))
                )}
              </div>

              {/* ── version, and the only Deploy control ──────────────────── */}
              <div className="py-[16px] border-b border-border-subtle">
                <p className="text-[9px] font-semibold uppercase tracking-[0.8px] text-gold-text mb-[10px]">
                  Version
                </p>
                <VersionBanner botKey={bot.key} botLabel={bot.name} />
              </div>

              {/* ── account ───────────────────────────────────────────────── */}
              <div className="py-[16px]">
                <p className="text-[9px] font-semibold uppercase tracking-[0.8px] text-gold-text mb-[10px]">
                  Account
                </p>
                <div className="flex items-center gap-2 flex-wrap">
                  <select
                    value={bot.account || ''}
                    disabled={assign.isPending}
                    onChange={(e) =>
                      assign.mutate({
                        botKey: bot.key,
                        account: e.target.value === '' ? null : Number(e.target.value),
                      })
                    }
                    className="text-[12px] bg-bg-sunken border border-border-default rounded-md px-2 py-[6px] text-text-primary disabled:opacity-40"
                  >
                    {accounts.map((a) => (
                      <option key={a} value={a}>
                        {a}
                      </option>
                    ))}
                    <option value="">Not on an account</option>
                  </select>
                  {assign.isPending && (
                    <span className="text-[11px] text-accent animate-pulse">Moving…</span>
                  )}
                </div>
                <p className="text-[10px] text-text-tertiary mt-[8px] leading-[1.5]">
                  A move rewrites the server, terminal and symbol to match. It takes effect at this
                  bot's next start.
                </p>
              </div>

              {/* ── everything you only read ──────────────────────────────── */}
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

                {/* The prose the risk editor no longer prints. Here, where somebody asking
                 *why is it 5%* will look, and nobody else has to read it. */}
                {v.runtime.filter((r) => r.note).length > 0 && (
                  <div className="mt-[16px] pt-[12px] border-t border-border-subtle/60">
                    <p className="text-[9px] font-semibold uppercase tracking-[0.8px] text-text-tertiary mb-[6px]">
                      Why these values
                    </p>
                    {v.runtime
                      .filter((r) => r.note)
                      .map((r) => (
                        <p
                          key={r.name}
                          className="text-[10px] text-text-tertiary leading-[1.55] mb-[10px]"
                        >
                          <span className="text-text-secondary">{r.label}: </span>
                          {r.note}
                        </p>
                      ))}
                  </div>
                )}

                <div className="mt-[16px] pt-[12px] border-t border-border-subtle/60">
                  <p className="text-[10px] text-text-tertiary mb-[8px] leading-[1.5]">
                    These decide <strong className="text-text-secondary">which trades</strong> it
                    takes, so changing one means it is no longer the bot that was backtested. Edit
                    in the lab, backtest, then deploy.
                  </p>
                  {Object.entries(strategyGroups).map(([g, rows]) => (
                    <ParamGroup key={g} group={g} rows={rows} />
                  ))}
                </div>
              </Fold>
            </>
          )}
        </div>
      </aside>
    </>
  )
}
