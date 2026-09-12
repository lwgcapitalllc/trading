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
import { ChevronRight, FileText, Play, RotateCcw, Square, Unlink } from 'lucide-react'
import {
  useAssignBotAccount,
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
  BotStatus,
} from '@/types'
import { Drawer } from '@/components/Drawer'
import { Shimmer } from '@/components/Shimmer'
import { botLabel as labelOf } from '@/lib/botLabel'
import { botCondition } from '@/lib/botCondition'
import { StatusDot, StatusText } from '@/components/BotStatus'
import { ParamGroup, VersionBanner } from './ConfigureTab'
import { BotActionPill, type BotAction } from './BotStatusPill'
import { BotRiskEditor } from './BotRiskEditor'
import { SectionTitle } from './drawerParts'
import { JoinChoices, LiveConfirm } from './JoinChoices'
import { describeChoice, useJoinAccount, type JoinChoice } from './joinAccount'

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
  /** Open the account this bot is on, in its own panel. */
  onOpenAccount?: (account: number) => void
}) {
  const { data, isLoading, error } = useBotParams(bot.key)
  const { data: groups } = useBotAccounts()
  const { data: registry } = useRegisteredAccounts()
  const remove = useAssignBotAccount()
  const join = useJoinAccount()
  const fetchPlan = useFetchRiskPlan()

  // Remove takes a second click on the SAME button, the live deploy's pattern. Held per BOT, so a
  // panel re-used for another bot cannot arrive already armed; disarms itself after 6s.
  const [removeArmedFor, setRemoveArmedFor] = useState<string | null>(null)
  const removeArmed = removeArmedFor === bot.key
  useEffect(() => {
    if (!removeArmed) return
    const t = setTimeout(() => setRemoveArmedFor(null), 6_000)
    return () => clearTimeout(t)
  }, [removeArmed])

  // A move the reader has to answer, held per bot for the same reason.
  const [move, setMove] = useState<PendingMove | null>(null)
  const moveHere = move && move.bot === bot.key ? move : null
  const [checkingDest, setCheckingDest] = useState<number | null>(null)

  const running = bot.status === 'RUNNING'
  const v = data as BotParamsView | undefined
  // Where the selector sits: the config's account once the configs are read, the bot's own report
  // until then (display only — Remove waits for the config, below).
  const selected =
    configAccount === undefined ? bot.account || '' : configAccount === null ? '' : configAccount

  const kindOf = (a: number) => (registry ?? []).find((r) => r.account === a)?.kind
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
  const doJoin = async (account: number, choice: JoinChoice, live: boolean) => {
    const ok = await join.join({ account, botKey: bot.key, display: bot.name, choice, live })
    if (ok) setMove(null)
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
    if (!live && !needsRoom) {
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
  const selectBusy = running || remove.isPending || moving || checkingDest !== null
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
      subtitle={
        <div className="flex items-center gap-[7px] flex-wrap mt-[2px]">
          <StatusDot cond={cond} size="list" />
          <StatusText cond={cond} size="list" />
          {typeof configAccount === 'number' ? (
            <>
              <span className="text-text-tertiary">·</span>
              {onOpenAccount ? (
                <button
                  data-testid="bot-account-link"
                  onClick={() => onOpenAccount(configAccount)}
                  title={`Open account ${configAccount} — its balance, its budget and its bots`}
                  className="inline-flex items-center gap-[2px] hover:text-accent transition-colors"
                >
                  account <span className="font-mono">{configAccount}</span>
                  <ChevronRight size={11} />
                </button>
              ) : (
                <span className="font-mono">{configAccount}</span>
              )}
            </>
          ) : configAccount === null ? (
            <>
              <span className="text-text-tertiary">·</span>
              <span>on no account</span>
            </>
          ) : bot.account ? (
            <>
              <span className="text-text-tertiary">·</span>
              <span className="font-mono">{bot.account}</span>
            </>
          ) : null}
        </div>
      }
    >
      {/* ── do ──────────────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 py-[14px] border-b border-border-subtle">
        {pendingAction ? (
          <BotActionPill action={pendingAction} />
        ) : running ? (
          <>
            <button
              onClick={onStop}
              disabled={busy}
              className={`${btnCls} border-neg/40 bg-neg-muted text-neg-text hover:bg-neg/10`}
            >
              <Square size={12} /> Stop
            </button>
            <button
              onClick={onRestart}
              disabled={busy}
              className={`${btnCls} border-border-default text-text-primary hover:bg-bg-hover`}
            >
              <RotateCcw size={12} /> Restart
            </button>
          </>
        ) : (
          <button
            onClick={onStart}
            disabled={busy || !bot.account}
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
      <section className="py-[16px] border-b border-border-subtle">
        <SectionTitle>Account</SectionTitle>
        {/* 🔴 **A RUNNING bot cannot be moved, and it is said BEFORE the gesture.** It read its
         *  account at startup, so the write could not reach the live process: the page would show
         *  it under the new account while it went on trading the old one.
         *  ⚠ **An account with no terminal is LISTED and DISABLED, with the reason in the option.**
         *  Hiding it makes an account that exists look like one that does not. */}
        <div className="flex items-center gap-2 flex-wrap">
          <select
            data-testid={`move-${bot.key}`}
            value={selected}
            disabled={selectBusy}
            title={
              running
                ? `Stop ${bot.name} first — it read its account at startup, so a move ` +
                  'cannot reach the running process.'
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
          {/* 🔴 **Remove from account, as its own button (2026-09-11)** — Aaron: *"we can stop but we
           *  can't remove"*. It BENCHES the bot (still registered, never started by the watchdog).
           *  ⚠ Refused while running; ⚠ a second click on the same button; ⚠ offered only once the
           *  CONFIG says the bot is on an account. */}
          {configAccount != null ? (
            <button
              data-testid={`remove-${bot.key}`}
              disabled={running || remove.isPending || moving}
              title={
                running
                  ? `Stop ${labelOf(bot)} first — it read its account at startup, so removing ` +
                    'it cannot reach the running process.'
                  : removeArmed
                    ? 'Click again to take it off the account.'
                    : `Take ${labelOf(bot)} off account ${configAccount}. It stays stopped until ` +
                      'you add it to an account again.'
              }
              onClick={() => {
                if (!removeArmed) {
                  setRemoveArmedFor(bot.key)
                  return
                }
                setRemoveArmedFor(null)
                remove.mutate({ botKey: bot.key, account: null, display: labelOf(bot) })
              }}
              className={`${btnCls} ${
                removeArmed
                  ? 'border-warn/40 bg-warn-muted text-warn-text hover:bg-warn/10'
                  : 'border-border-default text-text-secondary hover:bg-bg-hover hover:text-text-primary'
              }`}
            >
              <Unlink size={12} />
              {removeArmed ? 'Click again to remove' : 'Remove from account'}
            </button>
          ) : null}
          {(remove.isPending || moving || checkingDest !== null) && (
            <span className="text-[11.5px] text-accent animate-pulse">
              {checkingDest !== null
                ? `Checking account ${checkingDest}…`
                : remove.isPending
                  ? 'Removing…'
                  : 'Moving…'}
            </span>
          )}
        </div>

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
                  moveHere.live
                    ? setMove({ ...moveHere, staged: c })
                    : void doJoin(moveHere.account, c, false)
                }
              />
            ) : moveHere.staged && moveHere.live ? (
              <LiveConfirm
                account={moveHere.account}
                what={describeChoice(moveHere.staged, bot.name, myRisk, moveHere.plan)}
                verb="Move to live account"
                busy={moving}
                onConfirm={() => void doJoin(moveHere.account, moveHere.staged as JoinChoice, true)}
                onCancel={() => setMove(null)}
              />
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

        <p className="text-[11px] text-text-tertiary mt-[8px] leading-[1.5]">
          {running
            ? `Stop ${bot.name} before moving or removing it — it reads its account when it starts.`
            : "A move rewrites the server, terminal and symbol to match. It takes effect at this bot's next start."}
        </p>
      </section>

      {/* ── version, and the only Deploy control ────────────────────────────── */}
      <section className="py-[16px] border-b border-border-subtle">
        {/* 🔴 IT SAYS "DEPLOY" IN THE HEADING (2026-09-06) — *Version* names the noun; the reader is
         *  looking for the verb. */}
        <SectionTitle>Version · deploy new code to this bot</SectionTitle>
        <p className="text-[11px] text-text-tertiary mb-[10px] leading-[1.5] -mt-[4px]">
          Deploying copies the code on the trading box and restarts the bot on it. Until you do, it
          keeps running the version it started with.
        </p>
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
      {/* ⚠ A bot with no record still SAYS so, in the server's own words — never "0 / 0". */}
      <section data-testid="bot-record" className="py-[16px]">
        <SectionTitle>Its record</SectionTitle>
        {!earnings || !earnings.traded ? (
          <p className="text-[12px] text-text-tertiary leading-[1.5]">
            {earnings?.reason ??
              'No decision record has been read for this bot, so nothing here has been measured.'}
          </p>
        ) : (
          <Facts
            rows={[
              ['Won / lost', `${earnings.wins ?? 0} / ${earnings.losses ?? 0}`],
              ['Record covers', `${earnings.records_from} → ${earnings.records_to}`],
            ]}
          />
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
