import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Activity,
  AlertTriangle,
  GripVertical,
  KeyRound,
  Layers,
  MonitorSmartphone,
  Play,
  Plus,
  ShieldCheck,
  ShieldOff,
  SlidersHorizontal,
  Trash2,
  X,
} from 'lucide-react'
import {
  useBotAccounts,
  useBotSnapshot,
  useBotVersions,
  useSetAccountRiskCap,
  useAssignBotAccount,
  useRegisteredAccounts,
  useRegisterAccount,
  useUnregisterAccount,
  useSetAccountPassword,
} from '@/hooks/useBots'
import { useStrategies } from '@/hooks/useLab'
import { StackConfigModal } from '@/components/StackConfigModal'
import { VersionPill } from '@/components/VersionPill'
import { BotStatusPill } from './BotStatusPill'
import type { BotAccountGroup, BotAccountRegistration, BotDeployedVersion } from '@/types'
import type { UseQueryResult } from '@tanstack/react-query'

/**
 * The height that reaches the bottom of the page from wherever this pane starts.
 *
 * ⚠ **MEASURED, never a `calc()` off assumed chrome.** `100vh - 148px` is right for the top bar,
 * the page padding and the tab row — and wrong the moment anything else is above it, which really
 * happens: the VPS-failure banner appears on a poll, and while it is up a hardcoded height runs the
 * pane's bottom edge off the screen. The measurement costs one `getBoundingClientRect` per render
 * and cannot be wrong about what is actually above it.
 */
function usePaneHeight() {
  const ref = useRef<HTMLDivElement>(null)
  const [h, setH] = useState<number | null>(null)

  // No dependency array on purpose: a banner appearing above this pane moves its top without any
  // state here changing, so the measurement has to run on every render. The setState is guarded on
  // a real difference, so it converges after one pass rather than looping.
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const measure = () => {
      const next = Math.max(420, window.innerHeight - el.getBoundingClientRect().top - 22)
      setH((prev) => (prev === null || Math.abs(prev - next) > 1 ? next : prev))
    }
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  })

  return [ref, h] as const
}

/**
 * How many broker accounts this tab lists — the number on the tab chip.
 *
 * ⚠ **ONE definition, exported, so the chip and the rail cannot disagree.** It counts registered
 * accounts plus any account a bot names that nobody registered, which is exactly the set the rail
 * draws as accounts; the bench and the unreadable-configs rows are states, not accounts, and are
 * deliberately not in it.
 *
 * `undefined` while either query is unanswered — a chip reading `0` on a page that has not loaded
 * says the fleet has no accounts, which is the one answer that is never true here.
 */
export function useAccountCount(): number | undefined {
  const { data: groups } = useBotAccounts()
  const { data: registry } = useRegisteredAccounts()
  if (!registry || !groups) return undefined
  const known = new Set(registry.map((a) => a.account))
  return (
    registry.length +
    groups.filter((g) => g.kind === 'account' && g.account !== null && !known.has(g.account)).length
  )
}

/**
 * The shared-account view: which bots trade one balance, and the one ceiling over it.
 *
 * ⚠ **It is a RAIL + DETAIL, not a stack of cards (rebuilt 2026-08-12).** The card list grew
 * downward for ever, so with more than three accounts the answer to *what is trading where* was
 * a scroll and a memory test; and every fact on a card — broker, number, tier — was set in the
 * same small grey text, so the three things that IDENTIFY an account did not stand out from the
 * three that describe it. The rail is the selector and the only thing that grows; the detail pane
 * is fixed. Same shape as `ConfigureTab`, deliberately — two tabs that both pick one thing out of
 * a list and configure it should not be two different interactions.
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
  const [params, setParams] = useSearchParams()
  const [form, setForm] = useState<'add' | 'edit' | null>(null)
  const [shellRef, paneH] = usePaneHeight()

  const allKeys = useMemo(() => (groups ?? []).flatMap((g) => g.bots.map((b) => b.key)), [groups])
  // Shares `useBotVersion`'s cache entries with the Monitor tab and the Configure banner, so one
  // bot's version is ONE fetch and the three surfaces cannot disagree. See `useBotVersions`.
  const versionQueries = useBotVersions(allKeys)
  const versionByKey = useMemo(
    () => new Map(allKeys.map((k, i) => [k, versionQueries[i]])),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [allKeys.join(','), versionQueries.map((q) => q.dataUpdatedAt).join(',')]
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

  const regByAccount = new Map((registry ?? []).map((a) => [a.account, a]))

  // An entry per REGISTERED account, whether or not a bot is on it yet — that is the whole point
  // of the registry. Before it existed, the first bot on a new account could not be moved from
  // this page at all, which is why the 2026-08-12 ECN migration was a hand-edited VPS config.
  const registered = (registry ?? []).map((a) => ({
    reg: a as BotAccountRegistration | undefined,
    group:
      (groups ?? []).find((g) => g.kind === 'account' && g.account === a.account) ?? emptyGroup(a),
  }))

  // Accounts a bot names that nobody registered. They still work (the move reads the peers), and
  // they are shown with their gap named rather than hidden — a bot trading an account this page
  // cannot describe is exactly what the registry exists to end.
  const unregistered = (groups ?? [])
    .filter((g) => g.kind === 'account' && g.account !== null && !regByAccount.has(g.account))
    .map((g) => ({ reg: undefined, group: g }))

  const others = (groups ?? [])
    .filter((g) => g.kind !== 'account')
    .map((g) => ({ reg: undefined as BotAccountRegistration | undefined, group: g }))

  const entries = [...registered, ...unregistered, ...others]

  // Only an ASSIGNABLE account can be a move target. An account with no terminal on the box would
  // be written, committed, pushed and pulled and then fail at connect() with a message about
  // credentials — pointing the reader at the password rather than at the missing terminal.
  const targets = entries
    .filter((e) => e.group.kind === 'account' && e.group.account !== null)
    .map((e) => ({
      account: e.group.account as number,
      label: nameOf(e.reg, e.group),
      sub: [e.reg?.tier, e.reg?.kind].filter(Boolean).join(' · '),
      assignable: e.reg ? e.reg.assignable : true,
      reason: e.reg?.unassignable_reason ?? '',
    }))

  // ⚠ **The default lands on an account that is TRADING, not on the first one registered.** The
  // registry is ordered by account number, so the first row is whichever login is numerically
  // lowest — on this box a retired Standard demo — and opening on it makes the page's first
  // answer to *what is running* an account with nothing on it.
  const busiest = [...entries]
    .filter((e) => e.group.kind === 'account')
    .sort((a, b) => b.group.bots.length - a.group.bots.length)[0]
  const fallback = busiest?.group.bots.length ? busiest : entries[0]
  const selectedId = params.get('account') ?? idOf(fallback?.group)
  const selected = entries.find((e) => idOf(e.group) === selectedId) ?? fallback

  const select = (id: string) => {
    const next = new URLSearchParams(params)
    next.set('account', id)
    setParams(next, { replace: true })
    setForm(null)
  }

  // ⚠ **This tab answers WHICH ACCOUNT a bot trades; Configure answers HOW it trades.** They are
  // two different writes — one rewrites the login, server, terminal, symbol and cap together, the
  // other edits a runtime parameter — so they are two tabs, and this link is what makes that read
  // as one journey rather than as two places you have to know about.
  const configure = (botKey: string) => {
    const next = new URLSearchParams(params)
    next.set('tab', 'configure')
    next.set('bot', botKey)
    setParams(next, { replace: true })
  }

  if (entries.length === 0) {
    return (
      <div className="flex flex-col items-start gap-3">
        <div className="text-small text-text-tertiary">
          No broker accounts yet — add one, then move a bot onto it.
        </div>
        <AddAccountButton onClick={() => setForm('add')} />
        {form === 'add' && <AccountForm onClose={() => setForm(null)} />}
      </div>
    )
  }

  return (
    // ⚠ **Both panes are the HEIGHT OF THE PAGE and each scrolls inside itself.** Taking exactly
    // the space left below this pane's own top is what makes the two start and end on the same
    // line however long either list gets — a pane sized to its own content leaves the rail
    // floating above a tall detail, or the reverse, which is what "kind of not aligned" looked
    // like from the screen. The height is MEASURED; see `usePaneHeight` for why it is not a
    // `calc()`.
    <div
      ref={shellRef}
      style={paneH ? { height: paneH } : undefined}
      className="flex items-stretch gap-4 min-h-[420px]"
    >
      {/* ── Rail: the only thing that grows ──────────────────────────────────── */}
      <div className="w-[248px] shrink-0 h-full">
        <div
          className="bg-bg-surface border border-border-subtle rounded-lg p-[6px]
                        flex flex-col h-full"
        >
          {/* ⚠ **Add account is ABOVE the list and the list scrolls under it, not the page.**
              Below the list it was already 10px off the bottom of a 940px viewport with five
              accounts registered — so the one control that makes this tab work would have been
              the first thing to disappear as the fleet grew, which is the exact failure the
              rebuild was for. */}
          {/* The count lives on the TAB CHIP, not here — see `useAccountCount`. A number in both
              places is two claims about one set, and the tab is where it is readable without
              opening the tab. */}
          <p
            className="text-[9px] font-semibold uppercase tracking-[0.8px] text-gold-text
                        px-[10px] pt-[6px] pb-[8px] shrink-0"
          >
            Accounts
          </p>
          <div className="px-[4px] pb-[8px] shrink-0">
            <AddAccountButton onClick={() => setForm('add')} full />
          </div>
          <div className="flex flex-col gap-[2px] overflow-y-auto flex-1">
            {entries.map(({ reg, group }) => (
              <RailRow
                key={idOf(group)}
                group={group}
                registration={reg}
                selected={idOf(group) === idOf(selected.group)}
                onSelect={() => select(idOf(group))}
                statusByKey={statusByKey}
              />
            ))}
          </div>
        </div>
      </div>

      {/* ── Detail: one account, the same height as the rail ─────────────────── */}
      <div className="flex-1 min-w-0 h-full">
        {form === 'add' ? (
          <AccountForm onClose={() => setForm(null)} />
        ) : form === 'edit' && selected.reg ? (
          <AccountForm existing={selected.reg} onClose={() => setForm(null)} />
        ) : (
          <AccountDetail
            key={idOf(selected.group)}
            group={selected.group}
            registration={selected.reg}
            targets={targets}
            statusByKey={statusByKey}
            versionByKey={versionByKey}
            onEdit={() => setForm('edit')}
            onConfigure={configure}
          />
        )}
      </div>
    </div>
  )
}

function AddAccountButton({ onClick, full }: { onClick: () => void; full?: boolean }) {
  return (
    <button
      data-testid="add-account"
      onClick={onClick}
      className={`${full ? 'w-full justify-center' : ''} inline-flex items-center gap-[6px] px-3 py-[6px]
                 rounded-md text-small border border-border-default bg-bg-surface text-text-secondary
                 hover:bg-bg-hover hover:text-text-primary transition-colors`}
    >
      <Plus size={12} /> Add account
    </button>
  )
}

/** The rail's identity for a group. `bench` and `unknown` have no account number and are NOT the
 *  same thing — one is a state somebody chose, the other is a fault. */
function idOf(g?: BotAccountGroup): string {
  if (!g) return ''
  if (g.kind !== 'account' || g.account === null) return g.kind
  return String(g.account)
}

/** The name a human recognises. The registry's label wins, then the broker, then the number —
 *  a card headed `Account 700152905` says nothing the row under it does not already say. */
function nameOf(reg: BotAccountRegistration | undefined, g: BotAccountGroup): string {
  if (g.kind === 'bench') return 'Not on an account'
  if (g.kind === 'unknown') return 'Unreadable configs'
  return reg?.broker || reg?.label || `Account ${g.account}`
}

/**
 * How many of an account's bots are actually RUNNING — the one question this tab could not answer.
 *
 * ⚠ **THREE answers, and the third is the whole reason this is a function.** `known` counts the
 * bots the VPS snapshot came back for, so `running: 0` with `known: 0` means NOBODY ASKED, not
 * *nothing is trading*. The accounts endpoint deliberately never touches the VPS, so this page
 * renders in full while the box is unreachable — and reading that silence as *stopped* would tell
 * the reader the fleet is idle at exactly the moment nothing can be checked. Same rule as
 * `has_password`'s `null` one section down, and as `mt5_link` before it.
 *
 * ⚠ **`running > 0` wins even when some bots are unanswered**, because a bot seen RUNNING is a
 * measurement — the unknowns can only add to it.
 *
 * ⚠ **ONE definition, read by the rail row and by the detail chip.** Two hand-written readings is
 * how a green dot in the list ends up beside *nothing running* on the pane it opens.
 */
function liveOf(group: BotAccountGroup, statusByKey: Map<string, string>) {
  let running = 0
  let known = 0
  for (const b of group.bots) {
    const s = statusByKey.get(b.key)
    if (s === undefined) continue
    known++
    if (s === 'RUNNING') running++
  }
  const total = group.bots.length
  return {
    total,
    running,
    /** `true` = trading · `false` = genuinely nothing running · `null` = the VPS was not asked. */
    state: running > 0 ? true : known === total ? false : null,
  }
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
    // No bots, so nothing has been handed out and there is nothing that could overflow. `0`
    // rather than `null` on purpose: `null` here means "a share could not be read", and an
    // account with no bots on it has no unreadable share — it has none at all.
    share_total_pct: 0,
    share_overflow_reason: null,
    magic_clash: [],
  }
}

// ── the rail ────────────────────────────────────────────────────────────────────

/**
 * One account, compressed to the three facts that IDENTIFY it, whether anything is TRADING it,
 * and a warning marker.
 *
 * ⚠ **Broker → number → type, in that order and in that visual weight.** They were three
 * interchangeable pieces of grey `text-micro` on the old card, which is what made an account hard
 * to pick out of a list of them. The number is `font-mono tabular-nums` because it is read
 * digit-by-digit against a broker statement, not as a word.
 *
 * ⚠ **It is a DROP TARGET.** A bot dragged out of the detail pane lands here, which is the one
 * gesture that works when the source and the destination cannot both be on screen as cards.
 */
function RailRow({
  group,
  registration,
  selected,
  onSelect,
  statusByKey,
}: {
  group: BotAccountGroup
  registration?: BotAccountRegistration
  selected: boolean
  onSelect: () => void
  statusByKey: Map<string, string>
}) {
  const assign = useAssignBotAccount()
  const [dropping, setDropping] = useState(false)

  const isAccount = group.kind === 'account' && group.account !== null
  const assignable = registration ? registration.assignable : isAccount
  const live = liveOf(group, statusByKey)

  // 🔴 **A drop fires the SAME mutation the Move menu and the Add bot list fire, deliberately.**
  // It is a second GESTURE for one action, never a second path: a private write here would be a
  // second place for the six-field move to drift out of step with `assign_plan`.
  //
  // ⚠ **There is no staged "pending moves, then hit Deploy" state and there must not be one.**
  // That would be a stored intention able to disagree with what the bots are actually configured
  // to do — the exact shape this tab exists to avoid, and the reason the grouping is derived
  // rather than stored. A drop writes, commits, pushes and pulls, and the toast still says a
  // restart is needed.
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDropping(false)
    const key = e.dataTransfer.getData('text/bot-key')
    if (!key) return
    if (group.bots.some((b) => b.key === key)) return // already here — a no-op deploy
    if (statusByKey.get(key) === 'RUNNING') return // refused server-side too
    if (group.kind === 'unknown') return
    assign.mutate({ botKey: key, account: isAccount ? (group.account as number) : null })
  }

  const warn = registration
    ? !registration.assignable || registration.has_password === false
    : isAccount || group.kind === 'unknown'

  return (
    <button
      data-testid="account-rail-item"
      data-kind={group.kind}
      data-account={isAccount ? group.account : undefined}
      data-dropping={dropping ? 'true' : undefined}
      onClick={onSelect}
      aria-current={selected ? 'true' : undefined}
      onDragOver={(e) => {
        if (!e.dataTransfer.types.includes('text/bot-key')) return
        // ⚠ Only `preventDefault` makes an element a valid drop target, so NOT calling it is what
        // refuses a drop onto an account with no terminal — the cursor says no while the reader
        // is still holding the row, rather than a toast saying so after they let go.
        if (group.kind === 'unknown' || !assignable) return
        e.preventDefault()
        setDropping(true)
      }}
      onDragLeave={() => setDropping(false)}
      onDrop={onDrop}
      className={`w-full text-left px-[10px] py-[9px] rounded-md border transition-colors duration-[100ms] cursor-pointer ${
        dropping
          ? 'bg-accent-muted border-accent'
          : selected
            ? 'bg-accent-muted border-accent/30'
            : 'bg-transparent border-transparent hover:bg-bg-hover'
      }`}
    >
      <div className="flex items-center gap-[6px]">
        <span
          className={`text-[12px] truncate ${
            selected ? 'text-text-primary font-medium' : 'text-text-secondary'
          }`}
        >
          {nameOf(registration, group)}
        </span>
        {warn && (
          <AlertTriangle
            size={10}
            className="ml-auto shrink-0 text-warn-text"
            aria-label="needs attention"
          />
        )}
      </div>

      {isAccount && (
        <div className="text-[11px] font-mono tabular-nums text-text-tertiary mt-[3px]">
          #{group.account}
        </div>
      )}

      <div className="flex items-center gap-[5px] mt-[5px] flex-wrap">
        {registration?.tier && (
          <span
            className="inline-flex text-[9px] font-semibold px-[5px] py-[2px] rounded-pill
                           uppercase tracking-[0.4px] bg-bg-surface-2 text-text-secondary"
          >
            {registration.tier}
          </span>
        )}
        {registration && (
          <span
            className={`inline-flex text-[9px] font-semibold px-[5px] py-[2px] rounded-pill
                            uppercase tracking-[0.4px] ${
                              registration.kind === 'live'
                                ? 'bg-warn-muted text-warn-text'
                                : 'bg-bg-surface-2 text-text-tertiary'
                            }`}
          >
            {registration.kind}
          </span>
        )}
        <RailLive live={live} />
      </div>
    </button>
  )
}

/**
 * Whether anything is TRADING this account, at a glance, in the list.
 *
 * 🔴 **The row used to say `2 bots`, which is a fact about the CONFIG and reads as a fact about
 * the account being live.** Two bots assigned and stopped rendered identically to two bots
 * trading, so the rail — the one place every account is on screen together — could not answer
 * *which of these is running right now*, and the answer was a click plus a read of the State
 * column.
 *
 * ⚠ **The dot is STEADY, never `animate-pulse`.** A bot runs for weeks; permanent motion in a
 * list is read as an alert on day one and as background by day two, and this row sits beside the
 * warning triangle that genuinely wants the eye.
 *
 * ⚠ **`state: null` says `unknown` in words rather than drawing nothing.** A row with no live
 * marker would be indistinguishable from an idle account, which is the same collapse the count
 * itself was guilty of.
 */
function RailLive({ live }: { live: ReturnType<typeof liveOf> }) {
  const { total, running, state } = live
  if (total === 0) return <span className="text-[10px] text-text-tertiary">no bots</span>

  const bots = `${total} bot${total === 1 ? '' : 's'}`
  if (state === true) {
    return (
      <span className="inline-flex items-center gap-[5px] text-[10px] text-pos-text font-medium">
        <span className="w-[6px] h-[6px] rounded-full bg-pos-text shrink-0" aria-hidden />
        {total === 1 ? 'trading' : `${running} of ${total} trading`}
      </span>
    )
  }
  return (
    <span className="text-[10px] text-text-tertiary">
      {bots} · {state === false ? 'idle' : 'unknown'}
    </span>
  )
}

// ── the detail pane ─────────────────────────────────────────────────────────────

type MoveTarget = {
  account: number
  label: string
  sub: string
  assignable: boolean
  reason: string
}

function AccountDetail({
  group,
  registration,
  targets,
  statusByKey,
  versionByKey,
  onEdit,
  onConfigure,
}: {
  group: BotAccountGroup
  /** The registry row, when this account has one. Absent = a legacy account a bot names. */
  registration?: BotAccountRegistration
  targets: MoveTarget[]
  statusByKey: Map<string, string>
  versionByKey: Map<string, UseQueryResult<BotDeployedVersion> | undefined>
  onEdit: () => void
  /** Jump to the Configure tab for one bot — this tab decides WHICH account, that one decides HOW. */
  onConfigure: (botKey: string) => void
}) {
  const setCap = useSetAccountRiskCap()
  const assign = useAssignBotAccount()
  const unregister = useUnregisterAccount()
  const { data: strategies } = useStrategies()
  const [showStack, setShowStack] = useState(false)
  const [adding, setAdding] = useState(false)

  // `null` = uncapped, which is a value rather than a blank field — so the input is only shown
  // when the account is capped, and clearing it is an explicit action.
  const [capped, setCapped] = useState(group.risk_cap_pct !== null)
  const [capValue, setCapValue] = useState(group.risk_cap_pct ?? 10)

  const isAccount = group.kind === 'account' && group.account !== null
  const isBench = group.kind === 'bench'
  // 🔴 **SERVED, not added up here.** This was a local `reduce` with `?? 0` in it until
  // 2026-09-04, which counted a bot whose share could not be read as a bot risking nothing — the
  // one leniency the backend's own check refuses by name. So the page could print a total that
  // fitted under the cap on an account the save would refuse, and the sentence below it
  // ("together they risk N%") was short by a whole bot's share with nothing to say so.
  // `null` means CANNOT TOTAL, and it is rendered as that rather than as a number.
  const totalRisk = group.share_total_pct
  const live = liveOf(group, statusByKey)

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
    return group.bots.map((b) => byPackage.get(b.strategy_package)).filter((x): x is string => !!x)
  }, [strategies, group.bots])

  const save = (value: number | null) => {
    if (group.account === null) return
    setCap.mutate({ account: group.account, riskCapPct: value })
  }

  return (
    // ⚠ **`h-full` + one scrolling body, not a card that grows.** The header stays put while the
    // bot list scrolls under it, so the account you are looking at is never scrolled off the thing
    // you are reading about — and the card's bottom edge lines up with the rail's.
    <div
      data-testid="account-card"
      data-kind={group.kind}
      className="bg-bg-surface border border-border-subtle rounded-lg h-full flex flex-col
                    overflow-hidden"
    >
      {/* ── Identity ────────────────────────────────────────────────────────── */}
      <div className="px-5 pt-4 pb-[14px] border-b border-border-subtle shrink-0">
        <div className="flex items-start gap-3 flex-wrap">
          <div className="min-w-0">
            <div className="flex items-center gap-[10px] flex-wrap">
              <span className="text-[19px] font-semibold text-text-primary leading-none tracking-[-0.2px]">
                {nameOf(registration, group)}
              </span>
              {registration?.tier && (
                <span
                  className="inline-flex text-[10px] font-semibold px-2 py-[3px] rounded-pill
                                 uppercase tracking-[0.4px] bg-bg-surface-2 text-text-secondary"
                >
                  {registration.tier}
                </span>
              )}
              {registration && (
                <span
                  data-testid={registration.kind === 'live' ? 'live-chip' : 'demo-chip'}
                  title={
                    registration.kind === 'live'
                      ? 'A LIVE account. Every action here moves real money.'
                      : undefined
                  }
                  className={`inline-flex text-[10px] font-semibold px-2 py-[3px] rounded-pill
                                  uppercase tracking-[0.4px] ${
                                    registration.kind === 'live'
                                      ? 'bg-warn-muted text-warn-text'
                                      : 'bg-bg-surface-2 text-text-tertiary'
                                  }`}
                >
                  {registration.kind}
                </span>
              )}
            </div>

            {/* The identity line, in the order it is read: number, then where it lives, then how
                it quotes. Separated by hairlines rather than by spacing, so the three facts do not
                run into one string. */}
            <div
              className="flex items-center gap-[10px] mt-[9px] text-micro text-text-tertiary flex-wrap
                            [&>span+span]:before:content-['·'] [&>span+span]:before:mr-[10px]
                            [&>span+span]:before:text-border-default"
            >
              {isAccount && (
                <span className="font-mono tabular-nums text-[13px] text-text-secondary tracking-[0.3px]">
                  #{group.account}
                </span>
              )}
              {(group.server || registration?.server) && (
                <span>{group.server || registration?.server}</span>
              )}
              {registration?.symbol_suffix ? (
                <span>
                  symbols{' '}
                  <span className="font-mono text-text-secondary">
                    {registration.symbol_suffix}
                  </span>
                </span>
              ) : null}
              {isBench && <span>Registered and deliberately not trading</span>}
              {group.kind === 'unknown' && (
                <span>These configs could not be read, so which account they trade is unknown</span>
              )}
            </div>
          </div>

          <div className="ml-auto flex items-center gap-2">
            {registration && (
              <button
                data-testid={`edit-account-${registration.account}`}
                onClick={onEdit}
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
                title={
                  group.bots.length > 0
                    ? 'Move or bench the bots on this account first — removing it would leave them on ' +
                      'an account this page can no longer describe.'
                    : 'Forget this account. It does not touch the stored password.'
                }
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

        {/* ── Readiness chips ───────────────────────────────────────────────── */}
        <div className="flex items-center gap-2 mt-[10px] flex-wrap">
          {/* ⚠ **FIRST, because it is the question the page is opened with.** Everything else on
              this row is about whether the account COULD trade — a password, a terminal, a cap —
              and this one says whether anything IS. It reads the same `liveOf` the rail row does. */}
          {live.total > 0 && (
            <Chip
              testid="running-chip"
              tone={live.state === true ? 'pos' : live.state === false ? 'muted' : 'warn'}
              icon={
                live.state === true ? (
                  <Activity size={9} />
                ) : live.state === null ? (
                  <AlertTriangle size={9} />
                ) : undefined
              }
              title={
                live.state === true
                  ? `${live.running} of ${live.total} bot${live.total === 1 ? '' : 's'} on this ` +
                    'account is running right now, so this balance is being traded.'
                  : live.state === false
                    ? 'Every bot on this account is stopped, so nothing is trading this balance. ' +
                      'The bots are still assigned — start one from the Monitor tab.'
                    : 'The VPS could not be asked, so whether these bots are running is unknown. ' +
                      'It is not the same as nothing running.'
              }
            >
              {live.state === true
                ? `Trading · ${live.running} of ${live.total}`
                : live.state === false
                  ? 'Nothing running'
                  : 'Running state unknown'}
            </Chip>
          )}

          {group.stacked && (
            <Chip
              testid="stacked-chip"
              tone="accent"
              icon={<Layers size={9} />}
              title="More than one bot trades this balance"
            >
              Stacked · {group.bots.length}
            </Chip>
          )}

          {/* ⚠ THREE states, and the third is the one that matters: `null` means the VPS could not
              be asked, which is not the same as "no password". Rendering it as missing sends the
              reader to re-enter a credential that is already there. */}
          {registration && (
            <Chip
              testid="password-chip"
              tone={
                registration.has_password === null
                  ? 'muted'
                  : registration.has_password
                    ? 'pos'
                    : 'warn'
              }
              icon={<KeyRound size={9} />}
              title={
                registration.has_password === null
                  ? 'The VPS could not be asked, so whether a password is stored here is unknown.'
                  : registration.has_password
                    ? 'An MT5 password is stored for this account on the VPS.'
                    : 'No MT5 password is stored, so a bot moved here could not log in.'
              }
            >
              {registration.has_password === null
                ? 'Password unknown'
                : registration.has_password
                  ? 'Password set'
                  : 'No password'}
            </Chip>
          )}

          {registration &&
            (registration.assignable ? (
              <Chip
                testid="terminal-chip"
                tone="pos"
                icon={<MonitorSmartphone size={9} />}
                title={`This account is served by ${registration.mt5_path} on the VPS.`}
              >
                Terminal
              </Chip>
            ) : (
              <Chip
                testid="no-terminal"
                tone="warn"
                icon={<AlertTriangle size={9} />}
                title={registration.unassignable_reason}
              >
                No terminal
              </Chip>
            ))}

          {isAccount && !registration && (
            <Chip
              testid="unregistered"
              tone="muted"
              title="No bot can be moved onto this account from here until it is registered — its
                         server, terminal, symbol suffix and cost profile are only known to the bots
                         already on it."
            >
              Not registered
            </Chip>
          )}

          {isAccount && (
            <Chip
              testid="cap-chip"
              tone={!group.cap_agrees ? 'neg' : group.risk_cap_pct === null ? 'muted' : 'pos'}
              icon={
                group.risk_cap_pct === null && group.cap_agrees ? (
                  <ShieldOff size={9} />
                ) : group.cap_agrees ? (
                  <ShieldCheck size={9} />
                ) : (
                  <AlertTriangle size={9} />
                )
              }
            >
              {group.risk_cap_pct === null && group.cap_agrees
                ? 'Uncapped'
                : group.cap_agrees
                  ? `Cap ${group.risk_cap_pct}%`
                  : 'Cap disagreement'}
            </Chip>
          )}
        </div>
      </div>

      {/* ── Body: everything under the header scrolls, so the identity stays put ── */}
      <div className="flex-1 overflow-y-auto">
        {/* ── What is trading here ────────────────────────────────────────────── */}
        <div className="px-5 py-[11px] border-b border-border-subtle flex items-center gap-[10px]">
          <span className="text-[9px] font-semibold uppercase tracking-[0.8px] text-gold-text">
            {isAccount ? 'Bots on this balance' : 'Bots'}
          </span>
          {group.bots.length > 0 && (
            <span className="text-[10px] font-mono tabular-nums text-text-tertiary">
              {group.bots.length}
            </span>
          )}
          {isAccount && (
            <button
              data-testid="add-bot"
              disabled={registration ? !registration.assignable : false}
              title={
                registration && !registration.assignable
                  ? registration.unassignable_reason
                  : undefined
              }
              onClick={() => setAdding(true)}
              className="ml-auto inline-flex items-center gap-[6px] px-3 py-[5px] rounded-md text-small
                       border border-border-default bg-bg-surface text-text-secondary
                       hover:bg-bg-hover hover:text-text-primary transition-colors
                       disabled:opacity-30 disabled:cursor-not-allowed
                       disabled:hover:bg-bg-surface disabled:hover:text-text-secondary"
            >
              <Plus size={12} /> Add bot
            </button>
          )}
        </div>

        {group.magic_clash.length > 0 && (
          /* The fact the old raw `magic` column was trying to convey, shown only when it is
           true. Two bots on one account sharing an order tag each read the OTHER's orders as
           their own — cancelling them, moving their stops, booking their fills. */
          <div
            data-testid="magic-clash"
            className="mx-5 my-3 text-micro text-neg-text bg-neg-muted rounded px-2 py-[6px]"
          >
            <strong>{group.magic_clash.join(' and ')}</strong> share an order tag, so each would
            read the other's orders as its own — cancelling them, moving their stops and booking
            their fills. They will refuse to start until one is given a different one.
          </div>
        )}

        {isAccount && group.bots.length === 0 ? (
          <div data-testid="no-bots" className="px-5 py-4 text-micro text-text-tertiary">
            No bot trades this account yet.{' '}
            {registration?.assignable === false
              ? 'Log a terminal into it and record that terminal on the account first.'
              : 'Use Add bot above, or drag one here from another account.'}
          </div>
        ) : group.bots.length === 0 ? (
          <div className="px-5 py-4 text-micro text-text-tertiary">Nothing here.</div>
        ) : (
          <table className="w-full border-collapse">
            <thead>
              <tr>
                {[
                  '',
                  'Bot',
                  'Strategy',
                  'Symbol',
                  'Version',
                  'Risk / trade',
                  'Its cap',
                  'State',
                  '',
                ].map((h, i) => (
                  <th
                    key={h || `c${i}`}
                    className="text-left text-[10px] font-semibold uppercase tracking-[0.7px]
                                 text-text-tertiary px-3 py-[8px] bg-bg-surface-2/50
                                 border-b border-border-subtle whitespace-nowrap first:pl-5 last:pr-5"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {group.bots.map((b) => {
                const status = statusByKey.get(b.key)
                const q = versionByKey.get(b.key)
                const running = status === 'RUNNING'
                const movable = !running && !b.unreadable
                return (
                  <tr
                    key={b.key}
                    /* ⚠ A RUNNING bot is not draggable at all, matching the Move menu and the
                       Remove button beside it: it read its config at startup, so a write cannot
                       reach the live process and the page would show it under one account while
                       it traded another. */
                    draggable={movable}
                    data-testid={`bot-row-${b.key}`}
                    onDragStart={(e) => {
                      e.dataTransfer.setData('text/bot-key', b.key)
                      e.dataTransfer.effectAllowed = 'move'
                    }}
                    className={`border-b border-border-subtle last:border-0 text-small
                                hover:bg-bg-hover/40 transition-colors duration-[80ms] ${
                                  movable ? 'cursor-grab active:cursor-grabbing' : ''
                                }`}
                  >
                    {/* ⚠ **The grip is the only thing on screen that SAYS the row can be dragged.**
                      A `draggable` attribute is invisible — the gesture existed for a day with
                      nothing advertising it but a sentence under the rail, which read as an
                      instruction for a feature nobody could find. It is a marker, not a handle:
                      the whole row is the drag source, so grabbing anywhere still works. */}
                    <td
                      className="pl-5 pr-1 py-[9px] w-[22px]"
                      title={
                        movable
                          ? `Drag ${b.display} onto an account in the list on the left to move it. ` +
                            'Or use the Move menu on this row.'
                          : running
                            ? `Stop ${b.display} first — a running bot cannot be moved.`
                            : undefined
                      }
                    >
                      <GripVertical
                        size={13}
                        aria-hidden
                        data-testid={movable ? `grip-${b.key}` : undefined}
                        className={movable ? 'text-text-tertiary/60' : 'text-text-tertiary/20'}
                      />
                    </td>
                    <td className="px-3 py-[9px] text-text-primary font-medium">
                      {b.display}
                      {movable && (
                        <span className="sr-only">
                          {' '}
                          — drag onto an account in the list to move it
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-[9px] text-micro font-mono text-text-tertiary">
                      {b.strategy_package || '—'}
                    </td>
                    <td className="px-3 py-[9px] text-text-secondary whitespace-nowrap">
                      {b.symbol || '—'}
                    </td>
                    <td className="px-3 py-[9px]">
                      <VersionPill version={q?.data} loading={q?.isPending} />
                    </td>
                    <td className="px-3 py-[9px] text-text-secondary font-mono tabular-nums">
                      {b.risk_pct === null ? '—' : `${b.risk_pct}%`}
                    </td>
                    <td className="px-3 py-[9px] text-text-secondary font-mono tabular-nums">
                      {b.unreadable ? 'unknown' : b.cap_pct === null ? 'uncapped' : `${b.cap_pct}%`}
                    </td>
                    <td className="px-3 py-[9px] text-text-secondary">
                      {/* `undefined` is NOT stopped — the snapshot may not have answered. */}
                      {status === undefined ? (
                        <span className="text-text-tertiary">—</span>
                      ) : (
                        <BotStatusPill status={status} />
                      )}
                    </td>
                    <td className="pl-3 pr-5 py-[9px] text-right whitespace-nowrap">
                      {!b.unreadable && (
                        <div className="inline-flex items-center gap-[6px]">
                          {/* Answers "what is Configure for" from the row it applies to: this tab
                            decides WHICH account, that one decides how the bot trades on it. */}
                          <button
                            data-testid={`configure-${b.key}`}
                            onClick={() => onConfigure(b.key)}
                            title={
                              `Open ${b.display} on the Configure tab — its risk, its parameters ` +
                              'and the version it runs. This tab only decides which account it is on.'
                            }
                            className="inline-flex items-center gap-[4px] px-2 py-[3px] rounded text-micro
                                     text-text-tertiary hover:text-text-primary hover:bg-bg-hover
                                     transition-colors"
                          >
                            <SlidersHorizontal size={10} /> Configure
                          </button>
                          <MoveMenu
                            botKey={b.key}
                            display={b.display}
                            from={isAccount ? (group.account as number) : null}
                            targets={targets}
                            running={running}
                            busy={assign.isPending}
                            onMove={(account) => assign.mutate({ botKey: b.key, account })}
                          />
                          {isAccount && (
                            <button
                              data-testid={`remove-${b.key}`}
                              disabled={assign.isPending || running}
                              title={
                                running
                                  ? 'Stop this bot first — it read its account at startup, so moving it ' +
                                    'now would leave the page showing one account while it traded another.'
                                  : `Take ${b.display} off account ${group.account}. It will not start ` +
                                    'again until it is on an account.'
                              }
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
                        </div>
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
            here={new Set(group.bots.map((b) => b.key))}
            busy={assign.isPending}
            onPick={(key) => {
              assign.mutate(
                { botKey: key, account: group.account },
                {
                  onSuccess: () => setAdding(false),
                }
              )
            }}
            onClose={() => setAdding(false)}
            statusByKey={statusByKey}
          />
        )}
      </div>
      {/* ── end of the scrolling body ─────────────────────────────────── */}

      {/* ── The one thing that is genuinely configuration ────────────────────── */}
      {isAccount && (
        <div className="px-5 py-4 border-t border-border-subtle flex flex-col gap-[10px]">
          <div className="flex items-center gap-[10px]">
            <span className="text-[9px] font-semibold uppercase tracking-[0.8px] text-gold-text">
              Account risk cap
            </span>
            <span className="text-micro text-text-tertiary">
              the ceiling every bot on this balance sizes under
            </span>
          </div>

          {!group.cap_agrees && (
            <div
              data-testid="cap-disagreement"
              className="text-micro text-neg-text bg-neg-muted rounded px-2 py-[6px]"
            >
              These bots state different account caps, so the account's real ceiling is whichever
              bot asks — and a bot with no cap fills the balance while a capped one is refused.
              Saving below writes the same value to all of them. A bot will refuse to START in this
              state, which is deliberate.
            </div>
          )}

          {group.cap_unknown && (
            <div className="text-micro text-text-tertiary">
              One config could not be read, so this account's cap cannot be confirmed — and it
              cannot be changed until that is fixed.
            </div>
          )}

          <div
            className="flex items-center gap-3 flex-wrap bg-bg-sunken border border-border-subtle
                          rounded-md px-3 py-[10px]"
          >
            <label className="flex items-center gap-[6px] text-micro text-text-secondary cursor-pointer">
              <input
                type="checkbox"
                data-testid="cap-enabled"
                checked={capped}
                onChange={(e) => setCapped(e.target.checked)}
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
                  onChange={(e) => setCapValue(Number(e.target.value))}
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

          {/* 🔴 **The running total, and it is shown ALWAYS rather than only when something is
              wrong.** Until 2026-09-04 the only place this number appeared was inside the
              take-turns note below, which needs the cap to be at or under the largest single
              share — so the intended configuration (two bots at 5% under a 10% cap) never
              displayed it at all, and the way you found out the shares did not fit was to type a
              number and be refused on save. Splitting a cap between two bots is the whole reason
              this panel exists; the number being split has to be on screen while you do it. */}
          {group.bots.length > 0 && (
            <div data-testid="cap-shares" className="text-micro text-text-tertiary">
              {typeof totalRisk !== 'number' ? (
                <>
                  A bot here states no risk per trade that can be read, so these shares cannot be
                  totalled. An unreadable share is not a share of zero — fix that config before
                  splitting a cap, or the total on screen would be short by a whole bot.
                </>
              ) : group.risk_cap_pct === null ? (
                <>The bots here risk {totalRisk}% per trade between them, under no ceiling.</>
              ) : (
                <>
                  The bots here risk {totalRisk}% per trade between them, against a{' '}
                  {group.risk_cap_pct}% ceiling.
                </>
              )}
            </div>
          )}

          {/* The same sentence the save is refused with, shown BEFORE the save. Served, never
              re-derived here: deciding "does it fit" from two numbers in the browser is the rule
              written twice in two languages that this repo already gates against elsewhere. */}
          {group.share_overflow_reason && (
            <div
              data-testid="cap-overflow"
              className="text-micro text-neg-text bg-neg-muted rounded px-2 py-[6px]"
            >
              {group.share_overflow_reason}
            </div>
          )}

          {/* Not a warning: a fact the two numbers imply and neither states on its own. */}
          {group.cap_takes_turns && (
            <div data-testid="cap-takes-turns" className="text-micro text-text-tertiary">
              At {group.risk_cap_pct}% these bots take turns rather than share — one full-size
              position or resting order fills the whole budget and the other is refused until its
              stop moves.
              {typeof totalRisk === 'number' &&
                ` A cap above ${totalRisk}% lets both hold at once.`}
            </div>
          )}
        </div>
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
 * Move this bot somewhere else, without dragging.
 *
 * ⚠ **It fires the same mutation the drop and the Add bot list fire.** Drag is the fast path and
 * this is the discoverable one — a gesture nothing on screen advertises is a feature only the
 * person who built it knows about, and it is awkward on a trackpad.
 *
 * ⚠ **An unassignable account is LISTED and DISABLED, with the reason in the option itself.**
 * Hiding it makes an account that exists look like one that does not, which is the same rule the
 * Add bot list follows for a running bot.
 */
function MoveMenu({
  botKey,
  display,
  from,
  targets,
  running,
  busy,
  onMove,
}: {
  botKey: string
  display: string
  from: number | null
  targets: MoveTarget[]
  running: boolean
  busy: boolean
  onMove: (account: number | null) => void
}) {
  const elsewhere = targets.filter((t) => t.account !== from)
  if (elsewhere.length === 0 && from === null) return null

  return (
    <select
      data-testid={`move-${botKey}`}
      disabled={running || busy}
      value=""
      title={
        running
          ? `Stop ${display} first — it read its account at startup, so a move could not reach the ` +
            'live process.'
          : `Move ${display} to another account.`
      }
      onChange={(e) => {
        const v = e.target.value
        e.currentTarget.value = ''
        if (!v) return
        onMove(v === 'none' ? null : Number(v))
      }}
      /* ⚠ An explicit width, because a native `<select>` sizes itself to its WIDEST OPTION —
         and an option here is a whole account identity, so the closed control rendered ~320px
         wide to hold a string that is only ever shown in the open popup. */
      className="w-[104px] bg-bg-base border border-border-default rounded px-2 py-[3px] text-micro
                 text-text-secondary hover:text-text-primary transition-colors
                 disabled:opacity-30 disabled:cursor-not-allowed"
    >
      <option value="">Move to…</option>
      {elsewhere.map((t) => (
        <option key={t.account} value={t.account} disabled={!t.assignable}>
          {t.label} #{t.account}
          {t.sub ? ` · ${t.sub}` : ''}
          {t.assignable ? '' : ' — no terminal'}
        </option>
      ))}
      {from !== null && <option value="none">Take off any account</option>}
    </select>
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
function AddBotRow({
  account,
  here,
  busy,
  onPick,
  onClose,
  statusByKey,
}: {
  account: number
  here: Set<string>
  busy: boolean
  onPick: (key: string) => void
  onClose: () => void
  statusByKey: Map<string, string>
}) {
  const { data: groups } = useBotAccounts()

  const candidates = (groups ?? [])
    .flatMap((g) => g.bots.map((b) => ({ ...b, from: g })))
    .filter((b) => !here.has(b.key) && !b.unreadable)

  return (
    <div
      data-testid="add-bot-row"
      className="px-4 py-3 border-t border-border-subtle bg-bg-surface-2 flex flex-col gap-2"
    >
      <div className="flex items-center gap-2">
        <span className="text-micro text-text-secondary">Add a bot to account {account}</span>
        <button onClick={onClose} className="ml-auto text-text-tertiary hover:text-text-primary">
          <X size={12} />
        </button>
      </div>

      {candidates.length === 0 ? (
        <div data-testid="no-candidates" className="text-micro text-text-tertiary">
          Every registered bot is already on this account. A new one needs its instance created in
          the repo first — that is a code change, not something this page can do.
        </div>
      ) : (
        <div className="flex flex-col gap-1">
          {candidates.map((b) => {
            const running = statusByKey.get(b.key) === 'RUNNING'
            return (
              <button
                key={b.key}
                data-testid={`add-${b.key}`}
                disabled={busy || running}
                title={
                  running
                    ? 'This bot is running. Stop it before moving it — it read its account at ' +
                      'startup, so the move could not reach the live process.'
                    : undefined
                }
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
        Adding a bot writes this account's login, server, terminal, symbol and risk cap into its
        config, so the account stays coherent. It applies at that bot's next start.
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
 * because a bot reads only its own config, so it is set on the detail pane (one write, N files)
 * and reported from what the bots actually say. A field here would be a second answer that drifts.
 *
 * ⚠ **The password is WRITE-ONLY.** It is never returned by any endpoint, so an existing account
 * shows whether one is stored and not what it is — the field is blank on an edit and leaving it
 * blank changes nothing. It travels to the git-ignored credentials file on the VPS, never into
 * the git-tracked registry.
 */
function AccountForm({
  existing,
  onClose,
}: {
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
    save.mutate(
      {
        account: num,
        label,
        broker,
        tier,
        kind,
        server,
        mt5_path: mt5Path,
        symbol_suffix: hasSuffix ? suffix : null,
        account_profile: profile,
        note: existing?.note ?? '',
        // Sent on the SAME request when there is one, so the credential lands before the registry
        // row is committed and pushed — a registered account with no password is a visible, fixable
        // state, while a pushed row whose password write failed afterwards reads as complete.
        password: password || undefined,
        deploy: true,
      },
      {
        onSuccess: () => {
          setPwd('')
          onClose()
        },
      }
    )
  }

  return (
    // Same shape as the detail pane it replaces — full height, one scrolling body — so switching
    // between reading an account and editing one does not resize the page under the reader.
    <div
      data-testid="account-form"
      className="bg-bg-surface border border-border-subtle rounded-lg h-full flex flex-col
                    overflow-hidden"
    >
      <div className="flex items-center gap-2 px-5 py-[14px] border-b border-border-subtle shrink-0">
        <div className="text-[15px] text-text-primary font-semibold">
          {existing ? `Edit account ${existing.account}` : 'Add a broker account'}
        </div>
        <button onClick={onClose} className="ml-auto text-text-tertiary hover:text-text-primary">
          <X size={12} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-4 flex flex-col gap-3">
        <div className="grid grid-cols-2 gap-3 max-w-[720px]">
          <Field label="Account number" hint="The MT5 login.">
            <input
              type="number"
              data-testid="f-account"
              value={account}
              disabled={!!existing}
              onChange={(e) => setAccount(e.target.value)}
              className={inputCls}
            />
          </Field>
          <Field
            label="Server"
            hint="An account number IS a login on a server — the pair is the identity."
          >
            <input
              data-testid="f-server"
              value={server}
              placeholder="PUPrime-Demo"
              onChange={(e) => setServer(e.target.value)}
              className={inputCls}
            />
          </Field>
          <Field label="Broker" hint="The name this account is listed under in the rail.">
            <input
              data-testid="f-broker"
              value={broker}
              placeholder="PU Prime"
              onChange={(e) => setBroker(e.target.value)}
              className={inputCls}
            />
          </Field>
          <Field label="Name" hint="Optional. Used instead of the broker when it is set.">
            <input
              data-testid="f-label"
              value={label}
              placeholder="PU Prime ECN demo"
              onChange={(e) => setLabel(e.target.value)}
              className={inputCls}
            />
          </Field>
          <Field label="Tier" hint="The broker's own word for it. Display only.">
            <input
              value={tier}
              placeholder="ECN"
              onChange={(e) => setTier(e.target.value)}
              className={inputCls}
            />
          </Field>
          <Field
            label="Demo or live"
            hint="A live account is tinted and warned on before every fleet action."
          >
            <select
              data-testid="f-kind"
              value={kind}
              onChange={(e) => setKind(e.target.value)}
              className={inputCls}
            >
              <option value="demo">demo</option>
              <option value="live">live</option>
            </select>
          </Field>
          <Field
            label="Terminal path"
            hint="The terminal on the VPS logged into this account. Leave blank and no bot can be assigned — a move would be written, pushed, and then fail at connect time."
          >
            <input
              data-testid="f-path"
              value={mt5Path}
              placeholder="C:\\MT5_FFT\\terminal64.exe"
              onChange={(e) => setMt5Path(e.target.value)}
              className={inputCls}
            />
          </Field>
          <Field
            label="Cost profile"
            hint="Which measured cost model prices this account, e.g. puprime_ecn. Refused if it names no known profile."
          >
            <input
              data-testid="f-profile"
              value={profile}
              placeholder="puprime_ecn"
              onChange={(e) => setProfile(e.target.value)}
              className={inputCls}
            />
          </Field>
        </div>

        {/* The field the 2026-08-12 move forgot. It gets its own block and its own sentence. */}
        <div className="flex flex-col gap-1 border-t border-border-subtle pt-3">
          <label className="flex items-center gap-[6px] text-micro text-text-secondary cursor-pointer">
            <input
              type="checkbox"
              data-testid="f-has-suffix"
              checked={hasSuffix}
              onChange={(e) => setHasSuffix(e.target.checked)}
            />
            This account puts a suffix on its symbols
          </label>
          {hasSuffix && (
            <input
              data-testid="f-suffix"
              value={suffix}
              placeholder=".p"
              onChange={(e) => setSuffix(e.target.value)}
              className={`${inputCls} max-w-[120px]`}
            />
          )}
          <div className="text-micro text-text-tertiary max-w-[720px]">
            Moving a bot here keeps its instrument and swaps the suffix —{' '}
            <span className="font-mono">XAUUSD.s</span> becomes{' '}
            <span className="font-mono">XAUUSD{suffix || '.p'}</span>. Unticked means this broker
            quotes bare symbols. Leave it unticked only if that is true: a bot pointed at a symbol
            its terminal does not quote connects, warms up and receives no bars, which looks exactly
            like a quiet market.
          </div>
        </div>

        <div className="flex flex-col gap-1 border-t border-border-subtle pt-3">
          <Field
            label="MT5 password"
            hint="Stored on the VPS in a git-ignored file and never shown again. Leave blank to keep the current one."
          >
            <input
              type="password"
              data-testid="f-password"
              value={password}
              autoComplete="new-password"
              placeholder={existing?.has_password ? '•••••••• (unchanged)' : ''}
              onChange={(e) => setPwd(e.target.value)}
              className={`${inputCls} max-w-[260px]`}
            />
          </Field>
          {existing && password && (
            <button
              data-testid="save-password"
              disabled={setPassword.isPending}
              onClick={() =>
                setPassword.mutate(
                  { account: existing.account, password },
                  { onSuccess: () => setPwd('') }
                )
              }
              className="self-start px-3 py-[5px] rounded-md text-small bg-accent-muted
                       text-text-primary hover:brightness-110 transition disabled:opacity-40"
            >
              {setPassword.isPending ? 'Saving…' : 'Save password only'}
            </button>
          )}
        </div>
      </div>
      {/* ── end of the scrolling body ─────────────────────────────────── */}

      {/* Pinned, so the one control that commits the form cannot scroll off the way
          Add account did. */}
      <div className="flex items-center gap-2 px-5 py-[12px] border-t border-border-subtle shrink-0">
        <button
          data-testid="save-account"
          disabled={!valid || save.isPending}
          onClick={submit}
          className="px-3 py-[5px] rounded-md text-small bg-accent-muted text-text-primary
                     hover:brightness-110 transition disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {save.isPending ? 'Saving…' : existing ? 'Save account' : 'Add account'}
        </button>
        <button
          onClick={onClose}
          className="px-3 py-[5px] rounded-md text-small border border-border-default
                           bg-bg-surface text-text-secondary hover:bg-bg-hover transition-colors"
        >
          Cancel
        </button>
        <span className="text-micro text-text-tertiary">
          Committed, pushed and pulled onto the VPS. No secret goes into the repo.
        </span>
      </div>
    </div>
  )
}

const inputCls =
  'w-full bg-bg-base border border-border-default rounded px-2 py-[5px] ' +
  'text-small text-text-primary'

/** One readiness fact. Every chip on this tab is this shape, so a new one cannot drift from the
 *  Monitor row's pill sizing the way three hand-written ones did. */
function Chip({
  testid,
  tone,
  icon,
  title,
  children,
}: {
  testid?: string
  tone: 'pos' | 'neg' | 'warn' | 'accent' | 'muted'
  icon?: React.ReactNode
  title?: string
  children: React.ReactNode
}) {
  const cls =
    tone === 'pos'
      ? 'bg-pos-muted text-pos-text'
      : tone === 'neg'
        ? 'bg-neg-muted text-neg-text'
        : tone === 'warn'
          ? 'bg-warn-muted text-warn-text'
          : tone === 'accent'
            ? 'bg-accent-muted text-text-primary'
            : 'bg-bg-surface-2 text-text-tertiary'
  return (
    <span
      data-testid={testid}
      title={title}
      className={`inline-flex items-center gap-[3px] text-[10px] font-semibold px-2 py-[3px]
                      rounded-pill uppercase tracking-[0.4px] cursor-default ${cls}`}
    >
      {icon}
      {children}
    </span>
  )
}

function Field({
  label,
  hint,
  children,
}: {
  label: string
  hint: string
  children: React.ReactNode
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-micro text-text-secondary">{label}</span>
      {children}
      <span className="text-micro text-text-tertiary leading-[1.35]">{hint}</span>
    </label>
  )
}
