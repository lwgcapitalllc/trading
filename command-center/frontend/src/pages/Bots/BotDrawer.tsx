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
 *
 * ⚠ **620px, up from 440 (2026-09-06, Aaron: *"make this side panel a little wider so it could
 * fit more information in, so there's less up and down scrolling"*).** It is capped rather than
 * a fraction of the viewport because the page BEHIND it stays the subject — a panel wide enough
 * to hide the list it was opened from is a page you have navigated away from without meaning to.
 */
import { Play, Square, RotateCcw, FileText, X } from 'lucide-react'
import {
  useBotParams,
  useAssignBotAccount,
  useBotAccounts,
  useRegisteredAccounts,
} from '@/hooks/useBots'
import type { BotParamRow, BotParamsView, BotStatus, BotEarnings } from '@/types'
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
  earnings,
  onClose,
  onLogs,
  onStart,
  onStop,
  onRestart,
  busy,
}: {
  bot: BotStatus
  /** What THIS bot's own closed trades came to — computed server-side off its decision record.
   *  ⚠ Never the account's growth: two bots on one balance share that, and crediting each with
   *  all of it is the defect this whole section replaced. */
  earnings: BotEarnings | undefined
  onClose: () => void
  onLogs: () => void
  onStart: () => void
  onStop: () => void
  onRestart: () => void
  busy: boolean
}) {
  const { data, isLoading, error } = useBotParams(bot.key)
  const { data: groups } = useBotAccounts()
  const { data: registry } = useRegisteredAccounts()
  const assign = useAssignBotAccount()

  const running = bot.status === 'RUNNING'
  const v = data as BotParamsView | undefined

  /**
   * Every account this bot can be moved TO.
   *
   * 🔴 **Read off the REGISTRY first, not the grouping alone (2026-09-06).** The grouping is
   * derived from the instance configs, so it can only see accounts some bot is ALREADY on — the
   * first bot onto a newly registered account was not offered here at all, and had to be moved by
   * hand-editing a config on the box. That is the precise gap the registry query was written to
   * close, and this control was built against the half that cannot answer it.
   *
   * ⚠ **An account a bot names that nobody registered is unioned in and counts as assignable** —
   * it works (the move reads its peers), and dropping it would leave the bot's own current
   * account missing from the list it is supposed to be selected in.
   *
   * ⚠ **The registry entry WINS on a clash**, which is the whole reason it is listed first: the
   * grouping has no opinion about whether an account has a terminal, so taking its answer would
   * quietly re-enable an account that cannot be assigned.
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
        className="fixed top-0 right-0 bottom-0 w-[min(620px,100%)] bg-bg-surface border-l border-border-default z-50 overflow-y-auto"
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

          {/* ── what it has actually made ─────────────────────────────────── */}
          <div className="py-[16px] border-b border-border-subtle">
            <p className="text-[9px] font-semibold uppercase tracking-[0.8px] text-gold-text mb-[10px]">
              What it has made
            </p>
            {!earnings || !earnings.traded ? (
              <p className="text-[11.5px] text-text-tertiary leading-[1.5]">
                {earnings?.reason ??
                  'No decision record has been read for this bot, so nothing here has been measured.'}
              </p>
            ) : (
              <>
                <div className="flex flex-col mb-[10px]">
                  <span
                    className={`text-[22px] font-mono tabular-nums leading-none ${
                      (earnings.realised_usd ?? 0) > 0
                        ? 'text-pos-text'
                        : (earnings.realised_usd ?? 0) < 0
                          ? 'text-neg-text'
                          : 'text-text-secondary'
                    }`}
                  >
                    {(earnings.realised_usd ?? 0) > 0
                      ? '+'
                      : (earnings.realised_usd ?? 0) < 0
                        ? '−'
                        : ''}
                    $
                    {Math.abs(earnings.realised_usd ?? 0).toLocaleString('en-US', {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}
                  </span>
                  {/* The percentage needs its DENOMINATOR beside it or it is a number with
                   *  no referent — the backtest page's own "1439.7x of what" lesson. On a
                   *  stacked account it matters more: two bots divide by the same opening. */}
                  {earnings.pct_of_opening != null && (
                    <span className="text-[11px] font-mono tabular-nums text-text-tertiary mt-[4px]">
                      {earnings.pct_of_opening > 0 ? '+' : ''}
                      {earnings.pct_of_opening.toFixed(2)}% of the account's opening balance
                    </span>
                  )}
                </div>
                <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-[5px] text-[11px]">
                  {(
                    [
                      ['Closed trades', String(earnings.closed_trades ?? 0)],
                      ['Won / lost', `${earnings.wins ?? 0} / ${earnings.losses ?? 0}`],
                      [
                        'In R',
                        `${(earnings.realised_r ?? 0) > 0 ? '+' : ''}${(earnings.realised_r ?? 0).toFixed(2)}R`,
                      ],
                      ['Record covers', `${earnings.records_from} → ${earnings.records_to}`],
                    ] as [string, string][]
                  ).map(([k, val]) => (
                    <div key={k} className="contents">
                      <dt className="text-text-tertiary">{k}</dt>
                      <dd className="m-0 text-right font-mono tabular-nums text-text-secondary">
                        {val}
                      </dd>
                    </div>
                  ))}
                </dl>
                {/* R travels WITH the dollars, always. The dollar figure compounds off whatever
                 *  balance the account happened to hold, so it is the number least comparable
                 *  between two bots — the repo's compare-R-never-dollars rule, in a drawer. */}
                <p className="text-[10px] text-text-tertiary mt-[8px] leading-[1.5]">
                  Read from this bot's own decision record — its trades only, never the account's.
                  Compare bots on R; the dollars depend on the balance each trade was taken with.
                </p>
              </>
            )}
          </div>

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
                {/* 🔴 IT SAYS "DEPLOY" IN THE HEADING (2026-09-06). Aaron opened with *"you're
                 *  still not telling me how do I promote a bot"* and then found it here himself
                 *  — so the control was reachable and the SECTION NAME was not answering the
                 *  question anybody arrives with. *Version* names the noun; the reader is
                 *  looking for the verb. */}
                <p className="text-[9px] font-semibold uppercase tracking-[0.8px] text-gold-text mb-[3px]">
                  Version · deploy new code to this bot
                </p>
                <p className="text-[10px] text-text-tertiary mb-[10px] leading-[1.5]">
                  Deploying copies the code on the trading box and restarts the bot on it. Until you
                  do, it keeps running the version it started with.
                </p>
                <VersionBanner botKey={bot.key} botLabel={bot.name} />
              </div>

              {/* ── account ───────────────────────────────────────────────── */}
              <div className="py-[16px]">
                <p className="text-[9px] font-semibold uppercase tracking-[0.8px] text-gold-text mb-[10px]">
                  Account
                </p>
                {/* 🔴 **A RUNNING bot cannot be moved, and it is said BEFORE the gesture
                 *  (restored 2026-09-06).** The control was offered unconditionally, so moving a
                 *  live bot took the click and came back as an error toast from the server. The
                 *  server does refuse it — but a page that offers a control the box will reject
                 *  is teaching the reader that its own controls mean nothing.
                 *
                 *  ⚠ It read its account at startup, so the write could not reach the live
                 *  process: the page would show it under the new account while it went on trading
                 *  the old one. That is a screen lying about a live position, not a stale setting.
                 *
                 *  ⚠ **An account with no terminal is LISTED and DISABLED, with the reason in the
                 *  option.** Hiding it makes an account that exists look like one that does not,
                 *  and the write would otherwise be committed and pushed before failing at
                 *  connect() with a message about credentials — pointing whoever reads it at the
                 *  password rather than at the missing terminal. */}
                <div className="flex items-center gap-2 flex-wrap">
                  <select
                    data-testid={`move-${bot.key}`}
                    value={bot.account || ''}
                    disabled={running || assign.isPending}
                    title={
                      running
                        ? `Stop ${bot.name} first — it read its account at startup, so a move ` +
                          'cannot reach the running process.'
                        : `Move ${bot.name} to another account.`
                    }
                    onChange={(e) =>
                      assign.mutate({
                        botKey: bot.key,
                        account: e.target.value === '' ? null : Number(e.target.value),
                      })
                    }
                    className="text-[12px] bg-bg-sunken border border-border-default rounded-md px-2 py-[6px] text-text-primary disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {destinations.map((d) => (
                      <option key={d.account} value={d.account} disabled={!d.assignable}>
                        {d.account}
                        {d.assignable ? '' : ` — ${d.reason || 'cannot be assigned'}`}
                      </option>
                    ))}
                    <option value="">Not on an account</option>
                  </select>
                  {assign.isPending && (
                    <span className="text-[11px] text-accent animate-pulse">Moving…</span>
                  )}
                </div>
                <p className="text-[10px] text-text-tertiary mt-[8px] leading-[1.5]">
                  {running
                    ? `Stop ${bot.name} before moving it — it reads its account when it starts.`
                    : "A move rewrites the server, terminal and symbol to match. It takes effect at this bot's next start."}
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
